"""Regel-Laufzeit von SolarFlow (HA-unabhängig bis auf den Client).

Hält Einstellungen, Geräte-Store, Protokoll und führt – ausschließlich über
das Sicherheits-Gate – Schreibaktionen aus. Jede Ausführung wird verifiziert
und bei Fehlschlag sicher zurückgenommen.

Der Kern ist **gerätegetrieben**: Für jedes eingerichtete Gerät bewertet die
passende Strategie den PV-Überschuss und liefert Vorschläge. Erst das Gate
entscheidet, ob geschaltet wird.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.devices import (
    TYPES_BY_ID,
    Device,
    DeviceContext,
    DeviceEntity,
    DeviceGroup,
    assess,
    clamp_device_settings,
    device_view,
    group_by_device,
    make_device,
    missing_required_roles,
    suggest_roles,
    type_cards,
)
from core.discovery import EntityInfo
from core.limits import validate_settings
from core.models import Action, Decision, Mode, PlantState, Reading, Settings
from core.safety import SafetyContext, evaluate_layers, gate
from ha_client import HomeAssistantClient

_LOGGER = logging.getLogger("solarflow.engine")

HARD_WW_MIN_TEMP = 10.0
HARD_WW_MAX_TEMP = 90.0
DEFAULT_AUDIT_LIMIT = 300

#: Globale Quelle-Schluessel -> (deutscher Name, erlaubte Domaenen)
SOURCE_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {
    "feed_in": ("Einspeisung ins Netz", ("sensor",)),
    "pv": ("PV-Leistung", ("sensor",)),
    "grid_import": ("Netzbezug", ("sensor",)),
}

#: Rollen, deren Entität einen Sollwert trägt (Temperatur).
_SETPOINT_ROLES = ("setpoint", "climate")


class SolarFlowEngine:
    """Zustand und Ausführung für das Add-on."""

    def __init__(self, client: HomeAssistantClient, data_dir: str) -> None:
        self.client = client
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "state.json"
        self.sources: dict[str, str] = {}
        self.settings = Settings()
        self.devices: list[Device] = []
        self.emergency_stop = False
        self.last_decision: Decision | None = None
        self.last_layers: list = []
        self.last_assessments: list = []
        self.previous_feed_in: float | None = None
        self.audit: list[dict[str, Any]] = []
        self.last_error: str | None = None
        self.last_good_temp: float | None = None
        #: Laufzeit je Gerät: since (Ein-Zeitpunkt), last_off (für Mindestpause).
        self.device_runtime: dict[str, dict[str, float]] = {}
        #: Zwischengespeichertes HA-Geräte-Register (Entitäten je Gerät).
        self._groups: list[DeviceGroup] = []
        self._registry_fetched: float = 0.0
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._last_seen: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Reaktion auf Zustandsaenderungen
    # ------------------------------------------------------------------ #
    def bind(self) -> None:
        """Bei jeder Aenderung einer Quell-Entitaet sofort einen Zyklus anstossen."""
        self.client.add_state_callback(self._on_states)

    def _watched_entities(self) -> list[str]:
        ids = [v for v in self.sources.values() if v]
        for d in self.devices:
            ids.extend(v for v in d.roles.values() if v)
        return ids

    def _on_states(self, states: dict[str, dict]) -> None:
        changed = False
        for eid in self._watched_entities():
            cur = (states.get(eid) or {}).get("state")
            if self._last_seen.get(eid) != cur:
                self._last_seen[eid] = cur
                changed = True
        if changed:
            self._wake.set()

    async def wait_for_change(self, timeout: float) -> None:
        """Wartet auf eine Quellaenderung oder laeuft nach ``timeout`` weiter."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=timeout)
        self._wake.clear()

    # ------------------------------------------------------------------ #
    # Persistenz
    # ------------------------------------------------------------------ #
    def load(self, options: dict[str, Any] | None = None) -> None:
        data: dict[str, Any] = {}
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
            except Exception:  # defensiv
                data = {}
        opts = options or {}
        if not data:
            src = opts.get("sources") or {}
            if isinstance(src, dict):
                self.sources = {k: str(v) for k, v in src.items() if k in SOURCE_SPECS and v}
            if isinstance(opts.get("settings"), dict):
                self.settings = Settings.from_dict(opts["settings"])
            devices = opts.get("devices")
            if isinstance(devices, list):
                self.devices = self._load_devices(devices)
            else:
                self.devices = self._migrate_legacy_sources()
        else:
            self.sources = {k: str(v) for k, v in (data.get("sources") or {}).items() if k in SOURCE_SPECS}
            self.settings = Settings.from_dict(data.get("settings"))
            self.emergency_stop = bool(data.get("emergency_stop", False))
            self.devices = self._load_devices(data.get("devices") or [])
            if not self.devices:
                self.devices = self._migrate_legacy_sources(data)
        for d in self.devices:
            for n in clamp_device_settings(d):
                self.log("warn", f"{d.name}: {n}")
        self.settings, _ = validate_settings(self.settings)

    def _load_devices(self, raw: list) -> list[Device]:
        out: list[Device] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            dev = Device.from_dict(item)
            if dev.type_id in TYPES_BY_ID:
                out.append(dev)
        return out

    def _migrate_legacy_sources(self, data: dict[str, Any] | None = None) -> list[Device]:
        """Baut aus den alten festen Quellen ein Wärmepumpen-Gerät (Umstieg)."""
        src = dict(self.sources)
        if data:
            src = {k: str(v) for k, v in (data.get("sources") or {}).items() if v}
        setpoint = src.get("ww_water_heater") or src.get("ww_temp_number") or ""
        storage = src.get("ww_storage_sensor") or ""
        power = src.get("pv") or ""
        if not (setpoint or storage):
            return []
        roles: dict[str, str] = {}
        if storage:
            roles["storage"] = storage
        if setpoint:
            roles["setpoint"] = setpoint
        if power:
            roles["power"] = power
        dev = make_device("heat_pump", name="Wärmepumpe", roles=roles)
        return [dev] if dev else []

    def save(self) -> None:
        payload = {
            "sources": self.sources,
            "settings": self.settings.as_dict(),
            "devices": [d.as_dict() for d in self.devices],
            "emergency_stop": self.emergency_stop,
        }
        try:
            self.state_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        except Exception:  # defensiv
            _LOGGER.debug("Zustand konnte nicht gespeichert werden", exc_info=True)

    # ------------------------------------------------------------------ #
    # Hilfen
    # ------------------------------------------------------------------ #
    def _read(self, entity_id: str | None) -> Reading | None:
        if not entity_id:
            return None
        st = self.client.state(entity_id)
        if st is None:
            return Reading(entity_id=entity_id, value=None, available=False)
        age: float | None = None
        ts = st.get("last_updated") or st.get("last_changed")
        if ts:
            try:
                age = time.time() - datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
            except Exception:
                age = None
        value: float | None = None
        try:
            value = float(st.get("state"))
        except (ValueError, TypeError):
            value = None
        return Reading(
            entity_id=entity_id,
            value=value,
            unit=st.get("attributes", {}).get("unit_of_measurement"),
            age_s=age,
            available=st.get("state") not in ("unknown", "unavailable", None),
            raw=st.get("state"),
        )

    def _state_of(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        st = self.client.state(entity_id)
        return st.get("state") if st else None

    def _current_setpoint(self, entity_id: str | None) -> float | None:
        st = self.client.state(entity_id)
        if st is None:
            return None
        value = st.get("attributes", {}).get("temperature", st.get("state"))
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _device_bounds(self, device: Device) -> tuple[float, float]:
        """Grenzen des Geräts aus den Attributen (Fallback: sichere Standardwerte)."""
        lo, hi = HARD_WW_MIN_TEMP, HARD_WW_MAX_TEMP
        entity = device.roles.get("setpoint") or device.roles.get("climate")
        st = self.client.state(entity) if entity else None
        if st is not None:
            a = st.get("attributes", {})
            try:
                if a.get("min_temp") is not None:
                    lo = float(a["min_temp"])
                if a.get("max_temp") is not None:
                    hi = float(a["max_temp"])
            except (ValueError, TypeError):
                pass
        return lo, hi

    def _primary_bounds(self) -> tuple[float, float]:
        for d in self.devices:
            spec = TYPES_BY_ID.get(d.type_id)
            if d.enabled and spec and spec.strategy == "thermal_boost":
                return self._device_bounds(d)
        return HARD_WW_MIN_TEMP, HARD_WW_MAX_TEMP

    def log(self, level: str, text: str) -> None:
        self.audit.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "level": level, "text": text})
        if len(self.audit) > DEFAULT_AUDIT_LIMIT:
            self.audit = self.audit[:DEFAULT_AUDIT_LIMIT]

    async def set_sources(self, sources: dict[str, str]) -> None:
        for k, v in sources.items():
            if k in SOURCE_SPECS:
                self.sources[k] = str(v) if v else ""
        self._last_seen.clear()
        self.save()

    # ------------------------------------------------------------------ #
    # Geräte-Store
    # ------------------------------------------------------------------ #
    def add_device(self, type_id: str, *, name: str = "", roles: dict[str, str] | None = None) -> Device | None:
        dev = make_device(type_id, name=name, roles=roles)
        if dev is None:
            return None
        self.devices.append(dev)
        self._last_seen.clear()
        self.save()
        return dev

    def update_device(self, device_id: str, patch: dict[str, Any]) -> Device | None:
        dev = next((d for d in self.devices if d.id == device_id), None)
        if dev is None:
            return None
        if patch.get("name"):
            dev.name = str(patch["name"])
        if "enabled" in patch:
            dev.enabled = bool(patch["enabled"])
        if isinstance(patch.get("roles"), dict):
            for k, v in patch["roles"].items():
                if v:
                    dev.roles[str(k)] = str(v)
                else:
                    dev.roles.pop(str(k), None)
        if isinstance(patch.get("settings"), dict):
            for k, v in patch["settings"].items():
                try:
                    dev.settings[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
        for n in clamp_device_settings(dev):
            self.log("warn", f"{dev.name}: {n}")
        self._last_seen.clear()
        self.save()
        return dev

    def remove_device(self, device_id: str) -> bool:
        before = len(self.devices)
        self.devices = [d for d in self.devices if d.id != device_id]
        self.device_runtime.pop(device_id, None)
        if len(self.devices) != before:
            self.save()
            return True
        return False

    def discover_device(self, type_id: str, name_hint: str = "", device_key: str = "") -> dict[str, str]:
        """Schlägt je Rolle eine Entität vor – bevorzugt aus dem gewählten Gerät."""
        spec = TYPES_BY_ID.get(type_id)
        if spec is None:
            return {}
        infos = [self._entity_info(g) for g in self._entity_pool(device_key)]
        return {s.key: (s.entity_id or "") for s in suggest_roles(spec, infos, hint=name_hint)}

    def _entity_pool(self, device_key: str) -> list[DeviceEntity]:
        """Entitäten des gewählten HA-Geräts – sonst alle bekannten."""
        if device_key:
            group = next((g for g in self._groups if g.key == device_key), None)
            if group is not None:
                return list(group.entities)
        return [e for g in self._groups for e in g.entities] or self._all_entities()

    def _all_entities(self) -> list[DeviceEntity]:
        return [
            DeviceEntity(
                entity_id=e["entity_id"],
                domain=e["domain"],
                name=e.get("name") or "",
                device_class=e.get("device_class"),
                unit=e.get("unit"),
                state=e.get("state"),
            )
            for e in self.client.entity_catalog()
        ]

    @staticmethod
    def _entity_info(e: DeviceEntity) -> EntityInfo:
        return EntityInfo(
            entity_id=e.entity_id,
            domain=e.domain,
            name=e.name,
            device_class=e.device_class,
            unit=e.unit,
            state=e.state,
        )

    async def refresh_registry(self, force: bool = False) -> list[DeviceGroup]:
        """Liest das HA-Geräte-Register (mit Cache) und bündelt es zu Gruppen."""
        now = time.monotonic()
        if not force and self._groups and (now - self._registry_fetched) < 120:
            return self._groups
        try:
            registry = await self.client.fetch_registry()
            raw_devices = registry.get("devices", [])
            raw_entities = registry.get("entities", [])
            raw_areas = registry.get("areas", [])
        except Exception as err:  # defensiv: ohne Register weiterarbeiten
            self.last_error = str(err)
            _LOGGER.debug("Geräte-Register nicht verfügbar", exc_info=True)
            if not self._groups:
                self._groups = [DeviceGroup(key="__none__", name="Ohne Gerät", entities=self._all_entities())]
            return self._groups

        states = {e["entity_id"]: e for e in self.client.entity_catalog()}
        devices = {
            d["id"]: {
                "name": d.get("name") or "",
                "name_by_user": d.get("name_by_user") or "",
                "manufacturer": d.get("manufacturer") or "",
                "model": d.get("model") or "",
                "area_id": d.get("area_id") or "",
            }
            for d in raw_devices
            if d.get("id")
        }
        areas = {a["area_id"]: a.get("name", "") for a in raw_areas if a.get("area_id")}

        entities: list[DeviceEntity] = []
        for e in raw_entities:
            eid = e.get("entity_id")
            if not eid or e.get("entity_category") == "diagnostic":
                continue
            st = states.get(eid, {})
            entities.append(
                DeviceEntity(
                    entity_id=eid,
                    domain=eid.split(".")[0],
                    name=e.get("name") or e.get("original_name") or st.get("name") or eid,
                    device_id=e.get("device_id"),
                    area_id=e.get("area_id"),
                    device_class=st.get("device_class"),
                    unit=st.get("unit"),
                    state=st.get("state"),
                    disabled=bool(e.get("disabled_by")),
                    hidden=bool(e.get("hidden_by")),
                )
            )
        self._groups = group_by_device(entities, devices, areas)
        self._registry_fetched = now
        return self._groups

    def device_groups(self) -> list[dict[str, object]]:
        return [g.as_dict() for g in self._groups]

    def device_types(self) -> list[dict[str, object]]:
        """Alle Geräte-Vorlagen für den Store."""
        return type_cards()

    # ------------------------------------------------------------------ #
    # Regelzyklus
    # ------------------------------------------------------------------ #
    async def async_run_cycle(self) -> Decision:
        async with self._lock:
            try:
                return await self._cycle()
            except Exception as err:  # defensiv: nie anhalten
                self.last_error = str(err)
                self.log("err", f"Fehler im Zyklus: {err}")
                _LOGGER.exception("SolarFlow Zyklus fehlgeschlagen")
                return Decision(state=PlantState.NORMAL, blocked=True, reason_de="Fehler – sicherer Zustand")

    def _surplus_ok(self, feed_in: Reading) -> bool:
        from core.quality import POWER_MAX_W, POWER_MIN_W, check_freshness, check_jump, check_value

        ok_fresh, _, _ = check_freshness(feed_in, self.settings.sensor_max_age_s)
        ok_range, _, _ = check_value(feed_in.value, lo=POWER_MIN_W, hi=POWER_MAX_W)
        ok_jump, _, _ = check_jump(feed_in.value, self.previous_feed_in)
        return ok_fresh and ok_range and ok_jump

    def _build_context(self, device: Device, feed_in: Reading, surplus_ok: bool, now: float) -> DeviceContext:
        spec = TYPES_BY_ID[device.type_id]
        values: dict[str, Reading] = {}
        states: dict[str, str] = {}
        for role_key, entity in device.roles.items():
            if not entity:
                continue
            if role_key in _SETPOINT_ROLES:
                values[role_key] = Reading(entity_id=entity, value=self._current_setpoint(entity), available=True)
            else:
                r = self._read(entity)
                if r is not None:
                    values[role_key] = r
            states[role_key] = self._state_of(entity) or ""
        rt = self.device_runtime.get(device.id, {})
        runtime_s = (now - rt["since"]) if rt.get("since") else 0.0
        return DeviceContext(
            device=device,
            spec=spec,
            feed_in_w=feed_in.value if feed_in.is_number else None,
            surplus_ok=surplus_ok,
            values=values,
            states=states,
            now=now,
            runtime_s=runtime_s,
            grid_import_w=(self._read(self.sources.get("grid_import")) or Reading("", None)).value,
        )

    def _track_runtime(self, device: Device, was_on: bool, is_on: bool, now: float) -> None:
        rt = self.device_runtime.setdefault(device.id, {})
        if is_on and not was_on:
            rt["since"] = now
        elif not is_on:
            if was_on:
                rt["last_off"] = now
            rt.pop("since", None)

    async def _cycle(self) -> Decision:
        now = time.monotonic()
        feed_in = self._read(self.sources.get("feed_in")) or Reading(entity_id="", value=None, available=False)
        grid = self._read(self.sources.get("grid_import"))
        surplus_ok = self._surplus_ok(feed_in)

        all_actions: list[Action] = []
        self.last_assessments = []
        steps: list[tuple[str, str]] = []

        for device in self.devices:
            if not device.enabled:
                continue
            missing = missing_required_roles(device)
            if missing:
                steps.append(
                    ("warn", f"{device.name}: Pflicht-Zuordnung fehlt ({', '.join(missing)}) – pausiert.")
                )
                continue
            ctx = self._build_context(device, feed_in, surplus_ok, now)
            assessment = assess(ctx)
            self.last_assessments.append(assessment)
            all_actions.extend(assessment.actions)
            was_on = ctx.states.get("switch") == "on"
            is_on = was_on
            if any(a.service == "switch.turn_on" for a in assessment.actions):
                is_on = True
            if any(a.service == "switch.turn_off" for a in assessment.actions):
                is_on = False
            self._track_runtime(device, was_on, is_on, now)
            if assessment.reason_de:
                steps.append(("info", f"{assessment.name}: {assessment.reason_de}"))

        self.previous_feed_in = feed_in.value if feed_in.is_number else self.previous_feed_in

        if not surplus_ok:
            steps.append(("blocked", "Keine gültigen Überschussdaten – sicherer Zustand."))

        dmin, dmax = self._primary_bounds()
        ctx = SafetyContext(
            feed_in=feed_in,
            settings=self.settings,
            now=now,
            grid_import=grid,
            previous_feed_in=self.previous_feed_in,
            device_min=dmin,
            device_max=dmax,
            emergency_stop=self.emergency_stop,
            mode=self.settings.mode,
        )
        self.last_layers = evaluate_layers(ctx)

        allowed, blocked_reasons = gate(all_actions, ctx)
        blocked = bool(blocked_reasons) or bool(all_actions and not allowed)
        for r in blocked_reasons:
            steps.append(("blocked", r))

        state = PlantState.BOOST if any(a.active for a in self.last_assessments) else PlantState.NORMAL
        reason = self._summary_reason(state, blocked)
        decision = Decision(
            state=state,
            actions=allowed,
            blocked=blocked,
            reason_de=reason,
            reason_en=reason,
            steps=steps,
        )
        self.last_decision = decision

        for status, text in steps:
            if status in ("warn", "blocked"):
                self.log("warn" if status == "warn" else "err", text)

        if allowed and not blocked:
            await self._execute(allowed)
        return decision

    def _summary_reason(self, state: PlantState, blocked: bool) -> str:
        active = [a for a in self.last_assessments if a.active]
        if not self.devices:
            return "Noch keine Geräte eingerichtet – im Store Geräte hinzufügen."
        if blocked:
            if active:
                return f"{len(active)} Gerät(e) möchten schalten – gesperrt (Schatten/Not-Aus/Daten)."
            return "Keine Schaltung – Sicherheit hält."
        if state == PlantState.BOOST:
            names = ", ".join(a.name for a in active[:3])
            return f"Überschuss aktiv für: {names}."
        return "Kein Überschuss – alles im Ruhezustand."

    async def _execute(self, actions: list[Action]) -> None:
        for a in actions:
            domain, _, service = a.service.partition(".")
            try:
                target_val = a.data.get("temperature", a.data.get("value"))
                if target_val is not None:
                    self.last_good_temp = float(target_val)
                await self.client.call_service(domain, service, dict(a.data), entity_id=a.entity_id)
                self.log("ok", f"{a.service} → {a.entity_id} {a.data} ({a.why})")
                if self.settings.verify_writes:
                    await self._verify(a)
            except Exception as err:
                self.last_error = str(err)
                self.log("err", f"Schreiben fehlgeschlagen ({a.entity_id}): {err}")
                await self._fallback_to_normal()

    async def _verify(self, a: Action) -> None:
        await asyncio.sleep(1.0)
        expected = a.data.get("temperature", a.data.get("value"))
        if expected is None:
            return
        st = self.client.state(a.entity_id)
        if st is None:
            return
        current = st.get("attributes", {}).get("temperature", st.get("state"))
        try:
            if abs(float(current) - float(expected)) > 0.6:
                self.log("warn", f"Verifikation: {a.entity_id} meldet {current}, erwartet {expected}.")
        except (ValueError, TypeError):
            pass

    async def _fallback_to_normal(self) -> None:
        """Nach einem Schreibfehler: alle Sollwerte sicher auf Normal setzen."""
        for device in self.devices:
            spec = TYPES_BY_ID.get(device.type_id)
            if spec is None or spec.strategy != "thermal_boost":
                continue
            entity = device.roles.get("setpoint") or device.roles.get("climate")
            if not entity:
                continue
            normal = device.settings.get("normal_temp", 52.0)
            domain = entity.split(".")[0]
            try:
                if domain == "water_heater":
                    await self.client.call_service(
                        "water_heater", "set_temperature", {"temperature": normal}, entity_id=entity
                    )
                elif domain == "climate":
                    await self.client.call_service(
                        "climate", "set_temperature", {"temperature": normal}, entity_id=entity
                    )
                else:
                    await self.client.call_service("number", "set_value", {"value": normal}, entity_id=entity)
                self.log("warn", f"Not-Fallback: {device.name} auf Normal.")
            except Exception as err:  # defensiv
                self.log("err", f"Not-Fallback fehlgeschlagen ({device.name}): {err}")

    # ------------------------------------------------------------------ #
    # Aenderungen von aussen
    # ------------------------------------------------------------------ #
    async def set_mode(self, mode: str) -> None:
        self.settings.mode = Mode(mode)
        self.log("ok", f"Betriebsart auf {mode} gesetzt.")
        self.save()
        await self.async_run_cycle()

    async def set_settings(self, values: dict[str, Any]) -> list[str]:
        for key, value in values.items():
            if hasattr(self.settings, key):
                try:
                    if isinstance(getattr(self.settings, key), bool):
                        setattr(self.settings, key, bool(value))
                    elif key == "mode":
                        setattr(self.settings, key, Mode(str(value)))
                    else:
                        setattr(self.settings, key, float(value))
                except (ValueError, TypeError):
                    continue
        self.settings, notes = validate_settings(self.settings)
        for n in notes:
            self.log("warn", n)
        self.log("ok", "Einstellungen gespeichert.")
        self.save()
        await self.async_run_cycle()
        return notes

    async def set_emergency(self, on: bool) -> None:
        self.emergency_stop = bool(on)
        if on:
            self.settings.force_boost = False
            await self._fallback_to_normal()
        self.log("err" if on else "ok", "Not-Aus " + ("ausgeloest." if on else "aufgehoben."))
        self.save()
        await self.async_run_cycle()

    # ------------------------------------------------------------------ #
    # Snapshot fuer die Oberflaeche
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict[str, Any]:
        feed_in = self._read(self.sources.get("feed_in"))
        d = self.last_decision
        primary_storage = None
        for dev in self.devices:
            if dev.roles.get("storage"):
                primary_storage = self._read(dev.roles["storage"])
                break
        return {
            "mode": str(self.settings.mode),
            "state": str(d.state) if d else "normal",
            "emergency_stop": self.emergency_stop,
            "blocked": bool(d.blocked) if d else False,
            "reason_de": d.reason_de if d else "",
            "steps": [{"status": s, "text": t} for s, t in (d.steps if d else [])],
            "feed_in_w": feed_in.value if feed_in else None,
            "feed_in_age_s": feed_in.age_s if feed_in else None,
            "storage_temp": primary_storage.value if primary_storage and primary_storage.is_number else None,
            "grid_import_w": (self._read(self.sources.get("grid_import")) or Reading("", None)).value,
            "settings": self.settings.as_dict(),
            "layers": [
                {
                    "idx": ly.idx,
                    "key": ly.key,
                    "status": ly.status,
                    "name_de": ly.name_de,
                    "name_en": ly.name_en,
                    "detail_de": ly.detail_de,
                    "detail_en": ly.detail_en,
                }
                for ly in self.last_layers
            ],
            "device_types": type_cards(),
            "devices": [device_view(d) for d in self.devices],
            "assessments": [a.as_dict() for a in self.last_assessments],
            "audit": self.audit[:60],
            "sources": dict(self.sources),
            "source_specs": {k: {"label": v[0], "domains": list(v[1])} for k, v in SOURCE_SPECS.items()},
            "connected": self.client.connected,
            "last_error": self.last_error,
        }
