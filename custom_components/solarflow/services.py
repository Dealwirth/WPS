"""Dienste von SolarFlow.

Alle Dienste sind idempotent registriert und validieren ihre Eingaben.
Schaltende Dienste laufen über dieselbe Laufzeit und damit über das
Sicherheits-Gate.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    MODE_ACTIVE,
    MODE_OFF,
    MODE_SHADOW,
    SERVICE_CANCEL_BOOST,
    SERVICE_EMERGENCY_STOP,
    SERVICE_FORCE_BOOST,
    SERVICE_RESET_EMERGENCY_STOP,
    SERVICE_RUN_CYCLE,
    SERVICE_SET_MODE,
    SERVICE_SET_SETTINGS,
)
from .core.limits import validate_settings
from .core.models import Mode

_LOGGER = logging.getLogger(__name__)

_SCHEMA_MODE = vol.Schema({vol.Required("mode"): vol.In([MODE_OFF, MODE_SHADOW, MODE_ACTIVE])})
_SCHEMA_SETTINGS = vol.Schema(
    {
        vol.Optional("feed_in_on_w"): vol.Coerce(float),
        vol.Optional("feed_in_off_w"): vol.Coerce(float),
        vol.Optional("min_runtime_min"): vol.Coerce(float),
        vol.Optional("min_pause_min"): vol.Coerce(float),
        vol.Optional("ww_boost_temp"): vol.Coerce(float),
        vol.Optional("ww_normal_temp"): vol.Coerce(float),
        vol.Optional("ww_min_temp"): vol.Coerce(float),
        vol.Optional("ww_hygiene_min_temp"): vol.Coerce(float),
        vol.Optional("sensor_max_age_s"): vol.Coerce(float),
        vol.Optional("max_grid_import_w"): vol.Coerce(float),
        vol.Optional("verify_writes"): vol.Coerce(bool),
    },
    extra=vol.ALLOW_EXTRA,
)


def _runtime(hass: HomeAssistant):
    """Ersten verfügbaren Runtime-Eintrag holen (oder None)."""
    entries = hass.data.get(DOMAIN, {})
    for data in entries.values():
        if isinstance(data, dict) and "runtime" in data:
            return data["runtime"]
    return None


async def _save(hass: HomeAssistant, runtime) -> None:
    data = hass.data.get(DOMAIN, {}).get(runtime.entry_id)
    if data and data.get("store"):
        await data["store"].async_save(runtime.export_state())


async def _refresh(hass: HomeAssistant, runtime) -> None:
    """Laufzeit aktualisieren und die Oberfläche sofort nachziehen."""
    await runtime.async_run_cycle()
    data = hass.data.get(DOMAIN, {}).get(runtime.entry_id)
    if data and data.get("coordinator"):
        await data["coordinator"].async_request_refresh()


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_MODE):
        return

    async def _set_mode(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        rt.settings.mode = Mode(call.data["mode"])
        await _save(hass, rt)
        rt.log("ok", f"Betriebsart auf {call.data['mode']} gesetzt.")
        await _refresh(hass, rt)

    async def _set_settings(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        for key, value in call.data.items():
            if hasattr(rt.settings, key):
                setattr(rt.settings, key, value)
        rt.settings, notes = validate_settings(rt.settings)
        for n in notes:
            rt.log("warn", n)
        await _save(hass, rt)
        rt.log("ok", "Einstellungen gespeichert.")
        await _refresh(hass, rt)

    async def _force_boost(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        rt.settings.force_boost = True
        rt.log("warn", "Boost manuell erzwungen.")
        await _refresh(hass, rt)

    async def _cancel_boost(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        rt.settings.force_boost = False
        rt.log("ok", "Manueller Boost aufgehoben.")
        await _refresh(hass, rt)

    async def _emergency(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        rt.emergency_stop = True
        rt.settings.force_boost = False
        # Einmalig sicher auf Normaltemperatur zurückfahren, dann Hände weg.
        await rt._fallback_to_normal()
        rt.log("err", "NOT-AUS ausgelöst – alle Automatik gesperrt.")
        await _save(hass, rt)
        await _refresh(hass, rt)

    async def _reset_emergency(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        rt.emergency_stop = False
        rt.log("ok", "Not-Aus aufgehoben.")
        await _save(hass, rt)

    async def _run_cycle(call: ServiceCall) -> None:
        rt = _runtime(hass)
        if rt is None:
            return
        await _refresh(hass, rt)

    hass.services.async_register(DOMAIN, SERVICE_SET_MODE, _set_mode, schema=_SCHEMA_MODE)
    hass.services.async_register(DOMAIN, SERVICE_SET_SETTINGS, _set_settings, schema=_SCHEMA_SETTINGS)
    hass.services.async_register(DOMAIN, SERVICE_FORCE_BOOST, _force_boost)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL_BOOST, _cancel_boost)
    hass.services.async_register(DOMAIN, SERVICE_EMERGENCY_STOP, _emergency)
    hass.services.async_register(DOMAIN, SERVICE_RESET_EMERGENCY_STOP, _reset_emergency)
    hass.services.async_register(DOMAIN, SERVICE_RUN_CYCLE, _run_cycle)
