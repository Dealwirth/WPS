"""Laufzeit eines SolarFlow-Eintrags.

Hält Zustand, Einstellungen, Protokoll und führt – ausschließlich über das
Sicherheits-Gate – Schreibaktionen aus. Jede Ausführung wird verifiziert und
bei Fehlschlag sicher zurückgenommen.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EV_ENTITY,
    CONF_FEED_IN_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_HEATING_CLIMATE,
    CONF_MAX_GRID_IMPORT_W,
    CONF_MIN_PAUSE_MIN,
    CONF_MIN_RUNTIME_MIN,
    CONF_MODE,
    CONF_PV_ENTITY,
    CONF_SENSOR_MAX_AGE_S,
    CONF_VERIFY_WRITES,
    CONF_WALLBOX_ENTITY,
    CONF_WW_BOOST_TEMP,
    CONF_WW_HYGIENE_MIN_TEMP,
    CONF_WW_HYSTERESIS_NUMBER,
    CONF_WW_MIN_TEMP,
    CONF_WW_NORMAL_TEMP,
    CONF_WW_STORAGE_SENSOR,
    CONF_WW_TEMP_NUMBER,
    CONF_WW_WATER_HEATER,
    DEFAULT_AUDIT_LIMIT,
    DEFAULT_FEED_IN_OFF_W,
    DEFAULT_FEED_IN_ON_W,
    DEFAULT_MAX_GRID_IMPORT_W,
    DEFAULT_MIN_PAUSE_MIN,
    DEFAULT_MIN_RUNTIME_MIN,
    DEFAULT_SENSOR_MAX_AGE_S,
    DEFAULT_WW_BOOST_TEMP,
    DEFAULT_WW_HYGIENE_MIN_TEMP,
    DEFAULT_WW_MIN_TEMP,
    DEFAULT_WW_NORMAL_TEMP,
    EVENT_ACTION,
    EVENT_ALERT,
    HARD_WW_MAX_TEMP,
    HARD_WW_MIN_TEMP,
    MODE_SHADOW,
)
from .core.machine import Machine
from .core.models import Action, Decision, Mode, PlantState, Reading, Settings
from .core.modules import default_enabled_modules, store_cards
from .core.planner import evaluate
from .core.safety import SafetyContext, evaluate_layers

_LOGGER = logging.getLogger(__name__)


class SolarFlowRuntime:
    """Zustand und Ausführung für einen Config-Eintrag."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict[str, Any]) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.config = dict(config)
        self.settings = Settings(
            mode=Mode(config.get(CONF_MODE, MODE_SHADOW)),
            feed_in_on_w=float(config.get("feed_in_on_w", DEFAULT_FEED_IN_ON_W)),
            feed_in_off_w=float(config.get("feed_in_off_w", DEFAULT_FEED_IN_OFF_W)),
            min_runtime_min=float(config.get(CONF_MIN_RUNTIME_MIN, DEFAULT_MIN_RUNTIME_MIN)),
            min_pause_min=float(config.get(CONF_MIN_PAUSE_MIN, DEFAULT_MIN_PAUSE_MIN)),
            ww_boost_temp=float(config.get(CONF_WW_BOOST_TEMP, DEFAULT_WW_BOOST_TEMP)),
            ww_normal_temp=float(config.get(CONF_WW_NORMAL_TEMP, DEFAULT_WW_NORMAL_TEMP)),
            ww_min_temp=float(config.get(CONF_WW_MIN_TEMP, DEFAULT_WW_MIN_TEMP)),
            ww_hygiene_min_temp=float(config.get(CONF_WW_HYGIENE_MIN_TEMP, DEFAULT_WW_HYGIENE_MIN_TEMP)),
            sensor_max_age_s=float(config.get(CONF_SENSOR_MAX_AGE_S, DEFAULT_SENSOR_MAX_AGE_S)),
            max_grid_import_w=float(config.get(CONF_MAX_GRID_IMPORT_W, DEFAULT_MAX_GRID_IMPORT_W)),
            verify_writes=bool(config.get(CONF_VERIFY_WRITES, True)),
        )
        self.machine = Machine()
        self.enabled_modules: set[str] = set(default_enabled_modules())
        self.emergency_stop = False
        self.last_decision: Decision | None = None
        self.last_layers: list = []
        self.previous_feed_in: float | None = None
        self.audit: list[dict[str, Any]] = []
        self.last_error: str | None = None
        self.last_good_temp: float | None = None

    # ------------------------------------------------------------------ #
    # Persistenz
    # ------------------------------------------------------------------ #
    def export_state(self) -> dict[str, Any]:
        return {
            "settings": self.settings.as_dict(),
            "enabled_modules": sorted(self.enabled_modules),
            "emergency_stop": self.emergency_stop,
        }

    def import_state(self, data: dict[str, Any] | None) -> None:
        if not data:
            return
        self.settings = Settings.from_dict(data.get("settings"))
        mods = data.get("enabled_modules")
        if isinstance(mods, list) and mods:
            self.enabled_modules = set(default_enabled_modules()) | {str(m) for m in mods}
        self.emergency_stop = bool(data.get("emergency_stop", False))

    # ------------------------------------------------------------------ #
    # Hilfen
    # ------------------------------------------------------------------ #
    def _read(self, entity_id: str | None) -> Reading | None:
        """Liest eine HA-Entität sicher in ein :class:`Reading`."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return Reading(entity_id=entity_id, value=None, available=False)
        age: float | None = None
        try:
            ts = state.last_updated or state.last_changed
            if ts is not None:
                age = (dt_util.utcnow() - ts).total_seconds()
        except Exception:  # pragma: no cover - defensiv
            age = None
        value: float | None = None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            value = None
        return Reading(
            entity_id=entity_id,
            value=value,
            unit=state.attributes.get("unit_of_measurement"),
            age_s=age,
            available=state.state not in ("unknown", "unavailable", None),
            raw=state.state,
        )

    def _device_bounds(self) -> tuple[float, float]:
        """Gerätegrenzen des Warmwasser-Kreises (min/max), sonst Absolutwerte."""
        lo, hi = HARD_WW_MIN_TEMP, HARD_WW_MAX_TEMP
        state = self.hass.states.get(self.config.get(CONF_WW_WATER_HEATER, ""))
        if state is not None:
            a = state.attributes
            try:
                if a.get("min_temp") is not None:
                    lo = float(a["min_temp"])
                if a.get("max_temp") is not None:
                    hi = float(a["max_temp"])
            except (ValueError, TypeError):
                pass
        return lo, hi

    def _current_setpoint(self, entity_id: str) -> float | None:
        """Aktuell am Gerät gesetzter Sollwert (für die Selbstheilung)."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        value = state.attributes.get("temperature", state.state)
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def log(self, level: str, text: str) -> None:
        self.audit.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "level": level, "text": text})
        if len(self.audit) > DEFAULT_AUDIT_LIMIT:
            self.audit = self.audit[:DEFAULT_AUDIT_LIMIT]

    # ------------------------------------------------------------------ #
    # Regelzyklus
    # ------------------------------------------------------------------ #
    async def async_run_cycle(self) -> Decision:
        """Ein vollständiger Regelzyklus. Gibt die Entscheidung zurück."""
        try:
            return await self._cycle()
        except Exception as err:  # pragma: no cover - defensiv
            self.last_error = str(err)
            self.log("err", f"Fehler im Zyklus: {err}")
            _LOGGER.exception("SolarFlow Zyklus fehlgeschlagen")
            # Sicherer Zustand: zurück auf Normal, aber nur im aktiven Modus.
            return Decision(state=PlantState.NORMAL, blocked=True, reason_de="Fehler – sicherer Zustand")

    async def _cycle(self) -> Decision:
        now = time.monotonic()
        feed_in = self._read(self.config.get(CONF_FEED_IN_ENTITY))
        storage = self._read(self.config.get(CONF_WW_STORAGE_SENSOR))
        grid = self._read(self.config.get(CONF_GRID_IMPORT_ENTITY))
        ww_entity = self.config.get(CONF_WW_WATER_HEATER) or self.config.get(CONF_WW_TEMP_NUMBER) or ""

        if feed_in is None:
            feed_in = Reading(entity_id="", value=None, available=False)

        dmin, dmax = self._device_bounds()
        current_temp = self._current_setpoint(ww_entity)

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
        elif decision.blocked and self.machine.state != PlantState.NORMAL:
            # Schreiben gesperrt -> ehrlich als Normal anzeigen.
            self.machine.apply_inhibit(now, "gesperrt")
        return decision

    async def _execute(self, actions: list[Action]) -> None:
        """Führt erlaubte Aktionen aus und verifiziert sie."""
        for a in actions:
            domain, _, service = a.service.partition(".")
            target = {"entity_id": a.entity_id}
            try:
                self.last_good_temp = float(a.data.get("temperature", self.last_good_temp or 0)) or self.last_good_temp
                await self.hass.services.async_call(domain, service, dict(a.data), target=target, blocking=True)
                self.log("ok", f"{a.service} → {a.entity_id} {a.data} ({a.why})")
                self.hass.bus.async_fire(EVENT_ACTION, {"entity_id": a.entity_id, "data": a.data})
                if self.settings.verify_writes:
                    await self._verify(a)
            except Exception as err:
                self.last_error = str(err)
                self.log("err", f"Schreiben fehlgeschlagen ({a.entity_id}): {err}")
                await self._fallback_to_normal()

    async def _verify(self, a: Action) -> None:
        """Liest den geschriebenen Wert zurück und meldet Abweichungen.

        Wir warten bewusst *nicht* mit ``async_block_till_done`` – das kann
        während des Setups in einen Deadlock laufen. Der Aufruf davor war
        bereits ``blocking=True``, daher genügt ein kurzer Moment.
        """
        await asyncio.sleep(0)
        expected = a.data.get("temperature", a.data.get("value"))
        if expected is None:
            return
        state = self.hass.states.get(a.entity_id)
        if state is None:
            return
        current = state.attributes.get("temperature", state.state)
        try:
            if abs(float(current) - float(expected)) > 0.6:
                self.log("warn", f"Verifikation: {a.entity_id} meldet {current}, erwartet {expected}.")
                self.hass.bus.async_fire(EVENT_ALERT, {"entity_id": a.entity_id, "expected": expected, "got": current})
        except (ValueError, TypeError):
            pass

    async def _fallback_to_normal(self) -> None:
        """Nach einem Fehler sicher auf Normaltemperatur zurückfahren."""
        ww = self.config.get(CONF_WW_WATER_HEATER)
        if not ww:
            return
        try:
            await self.hass.services.async_call(
                "water_heater",
                "set_temperature",
                {"temperature": self.settings.ww_normal_temp},
                target={"entity_id": ww},
                blocking=True,
            )
            self.machine.state = PlantState.NORMAL
            self.log("warn", "Not-Fallback: zurück auf Normaltemperatur.")
        except Exception as err:  # pragma: no cover - defensiv
            self.log("err", f"Not-Fallback fehlgeschlagen: {err}")

    # ------------------------------------------------------------------ #
    # Snapshot für die Oberfläche
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict[str, Any]:
        feed_in = self._read(self.config.get(CONF_FEED_IN_ENTITY))
        storage = self._read(self.config.get(CONF_WW_STORAGE_SENSOR))
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
            "grid_import_w": (self._read(self.config.get(CONF_GRID_IMPORT_ENTITY)) or Reading("", None)).value,
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
            "audit": self.audit[:40],
            "sources": {
                "feed_in": self.config.get(CONF_FEED_IN_ENTITY),
                "pv": self.config.get(CONF_PV_ENTITY),
                "grid_import": self.config.get(CONF_GRID_IMPORT_ENTITY),
                "ww_water_heater": self.config.get(CONF_WW_WATER_HEATER),
                "ww_temp_number": self.config.get(CONF_WW_TEMP_NUMBER),
                "ww_storage_sensor": self.config.get(CONF_WW_STORAGE_SENSOR),
                "ww_hysteresis_number": self.config.get(CONF_WW_HYSTERESIS_NUMBER),
                "heating_climate": self.config.get(CONF_HEATING_CLIMATE),
                "wallbox": self.config.get(CONF_WALLBOX_ENTITY),
                "ev": self.config.get(CONF_EV_ENTITY),
            },
            "last_error": self.last_error,
        }
