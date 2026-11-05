"""Regel-Laufzeit von SolarFlow (HA-unabhaengig bis auf den Client).

Haelt Einstellungen, Zustandsmaschine, Protokoll und fuehrt – ausschliesslich
ueber das Sicherheits-Gate – Schreibaktionen aus. Jede Ausfuehrung wird
verifiziert und bei Fehlschlag sicher zurueckgenommen.
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

from core.limits import validate_settings
from core.machine import Machine
from core.models import Action, Decision, Mode, PlantState, Reading, Settings
from core.modules import (
    MODULES_BY_ID,
    default_enabled_modules,
    resolve_dependencies,
    store_cards,
)
from core.planner import evaluate
from core.safety import SafetyContext, evaluate_layers
from ha_client import HomeAssistantClient

_LOGGER = logging.getLogger("solarflow.engine")

HARD_WW_MIN_TEMP = 10.0
HARD_WW_MAX_TEMP = 60.0
DEFAULT_AUDIT_LIMIT = 300

#: Quelle-Schluessel -> (deutscher Name, erlaubte Domaenen)
SOURCE_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {
    "feed_in": ("Einspeisung ins Netz", ("sensor",)),
    "pv": ("PV-Leistung", ("sensor",)),
    "grid_import": ("Netzbezug", ("sensor",)),
    "ww_water_heater": ("Warmwasser", ("water_heater", "climate")),
    "ww_temp_number": ("WW-Solltemperatur", ("number",)),
    "ww_storage_sensor": ("WW-Speichertemperatur", ("sensor",)),
    "ww_hysteresis_number": ("WW-Hysterese", ("number",)),
    "heating_climate": ("Heizung", ("climate",)),
    "wallbox": ("Wallbox", ("switch", "sensor", "select", "number")),
    "ev": ("Fahrzeug", ("sensor", "switch", "number", "lock")),
}


class SolarFlowEngine:
    """Zustand und Ausfuehrung fuer das Add-on."""

    def __init__(self, client: HomeAssistantClient, data_dir: str) -> None:
        self.client = client
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "state.json"
        self.sources: dict[str, str] = {}
        self.settings = Settings()
        self.machine = Machine()
        self.enabled_modules: set[str] = set(default_enabled_modules())
        self.emergency_stop = False
        self.last_decision: Decision | None = None
        self.last_layers: list = []
        self.previous_feed_in: float | None = None
        self.audit: list[dict[str, Any]] = []
        self.last_error: str | None = None
        self.last_good_temp: float | None = None
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._last_seen: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Reaktion auf Zustandsaenderungen
    # ------------------------------------------------------------------ #
    def bind(self) -> None:
        """Bei jeder Aenderung einer Quell-Entitaet sofort einen Zyklus anstossen."""
        self.client.add_state_callback(self._on_states)

    def _on_states(self, states: dict[str, dict]) -> None:
        watched = [v for v in self.sources.values() if v]
        changed = False
        for eid in watched:
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
        # Add-on-Optionen gelten nur beim allerersten Start als Vorbelegung.
        if not data:
            src = opts.get("sources") or {}
            if isinstance(src, dict):
                self.sources = {k: str(v) for k, v in src.items() if k in SOURCE_SPECS and v}
            if isinstance(opts.get("settings"), dict):
                self.settings = Settings.from_dict(opts["settings"])
            if isinstance(opts.get("enabled_modules"), list) and opts["enabled_modules"]:
                self.enabled_modules = set(default_enabled_modules()) | {str(m) for m in opts["enabled_modules"]}
        else:
            self.sources = {k: str(v) for k, v in (data.get("sources") or {}).items() if k in SOURCE_SPECS}
            self.settings = Settings.from_dict(data.get("settings"))
            mods = data.get("enabled_modules")
            if isinstance(mods, list) and mods:
                self.enabled_modules = set(default_enabled_modules()) | {str(m) for m in mods}
            self.emergency_stop = bool(data.get("emergency_stop", False))
        self.settings, _ = validate_settings(self.settings)

    def save(self) -> None:
        payload = {
            "sources": self.sources,
            "settings": self.settings.as_dict(),
            "enabled_modules": sorted(self.enabled_modules),
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

    def _device_bounds(self) -> tuple[float, float]:
        lo, hi = HARD_WW_MIN_TEMP, HARD_WW_MAX_TEMP
        st = self.client.state(self.sources.get("ww_water_heater"))
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

    def _current_setpoint(self, entity_id: str | None) -> float | None:
        st = self.client.state(entity_id)
        if st is None:
            return None
        value = st.get("attributes", {}).get("temperature", st.get("state"))
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

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

    async def _cycle(self) -> Decision:
        now = time.monotonic()
        feed_in = self._read(self.sources.get("feed_in"))
        storage = self._read(self.sources.get("ww_storage_sensor"))
        grid = self._read(self.sources.get("grid_import"))
        ww_entity = self.sources.get("ww_water_heater") or self.sources.get("ww_temp_number") or ""

        if feed_in is None:
            feed_in = Reading(entity_id="", value=None, available=False)

        dmin, dmax = self._device_bounds()
        current_temp = self._current_setpoint(ww_entity)

        wallbox_entity = self.sources.get("wallbox")
        wallbox_on: bool | None = None
        if wallbox_entity:
            wb = self.client.state(wallbox_entity)
            if wb is not None:
                wallbox_on = wb.get("state") == "on"

        decision = evaluate(
            machine=self.machine,
            settings=self.settings,
            feed_in=feed_in,
            storage=storage,
            grid_import=grid,
            now=now,
            previous_feed_in=self.previous_feed_in,
            device_min=dmin,
            device_max=dmax,
            ww_entity=ww_entity,
            emergency_stop=self.emergency_stop,
            current_temp=current_temp,
            enabled_modules=self.enabled_modules,
            wallbox_entity=wallbox_entity,
            wallbox_on=wallbox_on,
        )
        self.previous_feed_in = feed_in.value if feed_in.is_number else self.previous_feed_in
        self.last_decision = decision

        ctx = SafetyContext(
            feed_in=feed_in,
            settings=self.settings,
            now=now,
            storage=storage,
            grid_import=grid,
            previous_feed_in=self.previous_feed_in,
            device_min=dmin,
            device_max=dmax,
            emergency_stop=self.emergency_stop,
            mode=self.settings.mode,
        )
        self.last_layers = evaluate_layers(ctx)

        for status, text in decision.steps:
            if status in ("warn", "blocked"):
                self.log("warn" if status == "warn" else "err", text)

        if decision.actions and not decision.blocked:
            await self._execute(decision.actions)
        elif (
            (self.settings.mode == Mode.OFF or self.emergency_stop)
            and self.machine.state != PlantState.NORMAL
        ):
            # Nur bei Aus/Not-Aus gilt der Ruhezustand. Im Schatten-Modus bleibt
            # der Vorschlag sichtbar (blocked), damit man ihn pruefen kann.
            self.machine.apply_inhibit(now, "gesperrt")
        return decision

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
        ww = self.sources.get("ww_water_heater") or self.sources.get("ww_temp_number")
        if not ww:
            return
        domain = ww.split(".")[0]
        try:
            if domain == "water_heater":
                await self.client.call_service(
                    "water_heater", "set_temperature", {"temperature": self.settings.ww_normal_temp}, entity_id=ww
                )
            else:
                await self.client.call_service(
                    "number", "set_value", {"value": self.settings.ww_normal_temp}, entity_id=ww
                )
            self.machine.state = PlantState.NORMAL
            self.log("warn", "Not-Fallback: zurueck auf Normaltemperatur.")
        except Exception as err:  # defensiv
            self.log("err", f"Not-Fallback fehlgeschlagen: {err}")

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

    async def set_module(self, module_id: str, enabled: bool) -> tuple[bool, str]:
        if enabled:
            self.enabled_modules = resolve_dependencies(self.enabled_modules, module_id=module_id)
        else:
            spec = MODULES_BY_ID.get(module_id)
            if spec is not None and not spec.optional:
                return False, "Das Grundsystem kann nicht deaktiviert werden."
            self.enabled_modules.discard(module_id)
        self.save()
        return True, ""

    async def set_emergency(self, on: bool) -> None:
        self.emergency_stop = bool(on)
        if on:
            self.settings.force_boost = False
            await self._fallback_to_normal()
        self.log("err" if on else "ok", "Not-Aus " + ("ausgeloest." if on else "aufgehoben."))
        self.save()
        await self.async_run_cycle()

    async def force_boost(self, on: bool) -> None:
        self.settings.force_boost = bool(on)
        self.log("warn" if on else "ok", "Manueller Boost " + ("erzwungen." if on else "aufgehoben."))
        self.save()
        await self.async_run_cycle()

    # ------------------------------------------------------------------ #
    # Snapshot fuer die Oberflaeche
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict[str, Any]:
        feed_in = self._read(self.sources.get("feed_in"))
        storage = self._read(self.sources.get("ww_storage_sensor"))
        d = self.last_decision
        return {
            "mode": str(self.settings.mode),
            "state": str(self.machine.state),
            "emergency_stop": self.emergency_stop,
            "blocked": bool(d.blocked) if d else False,
            "reason_de": d.reason_de if d else "",
            "steps": [{"status": s, "text": t} for s, t in (d.steps if d else [])],
            "feed_in_w": feed_in.value if feed_in else None,
            "feed_in_age_s": feed_in.age_s if feed_in else None,
            "storage_temp": storage.value if storage and storage.is_number else None,
            "grid_import_w": (self._read(self.sources.get("grid_import")) or Reading("", None)).value,
            "settings": self.settings.as_dict(),
            "machine_changes": self.machine.changes,
            "runtime_s": self.machine.runtime_s(time.monotonic()),
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
            "modules": store_cards(self.enabled_modules),
            "audit": self.audit[:60],
            "sources": dict(self.sources),
            "source_specs": {k: {"label": v[0], "domains": list(v[1])} for k, v in SOURCE_SPECS.items()},
            "connected": self.client.connected,
            "last_error": self.last_error,
        }
