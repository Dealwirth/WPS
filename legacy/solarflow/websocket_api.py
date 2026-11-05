"""Websocket-API für die Oberfläche.

Die Oberfläche ruft nur diese Befehle auf. Jeder Befehl prüft Eingaben und
gibt ausschließlich anzeigbare Daten zurück – Tokens oder Secrets sind nie
Teil eines Snapshots.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, MODE_ACTIVE, MODE_OFF, MODE_SHADOW
from .core.limits import validate_settings
from .core.models import Mode
from .core.modules import resolve_dependencies, store_cards

_LOGGER = logging.getLogger(__name__)


def _runtime(hass: HomeAssistant):
    for data in hass.data.get(DOMAIN, {}).values():
        if isinstance(data, dict) and "runtime" in data:
            return data["runtime"]
    return None


async def _save(hass: HomeAssistant, runtime) -> None:
    data = hass.data.get(DOMAIN, {}).get(runtime.entry_id)
    if data and data.get("store"):
        await data["store"].async_save(runtime.export_state())


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_snapshot)
    websocket_api.async_register_command(hass, ws_set_mode)
    websocket_api.async_register_command(hass, ws_set_settings)
    websocket_api.async_register_command(hass, ws_set_module)
    websocket_api.async_register_command(hass, ws_emergency)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/snapshot"})
@websocket_api.async_response
async def ws_snapshot(hass: HomeAssistant, connection, msg) -> None:
    rt = _runtime(hass)
    if rt is None:
        connection.send_error(msg["id"], "not_found", "SolarFlow ist nicht eingerichtet.")
        return
    connection.send_result(msg["id"], rt.snapshot())


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/set_mode", vol.Required("mode"): vol.In([MODE_OFF, MODE_SHADOW, MODE_ACTIVE])}
)
@websocket_api.async_response
async def ws_set_mode(hass: HomeAssistant, connection, msg) -> None:
    rt = _runtime(hass)
    if rt is None:
        connection.send_error(msg["id"], "not_found", "nicht eingerichtet")
        return
    rt.settings.mode = Mode(msg["mode"])
    await _save(hass, rt)
    rt.log("ok", f"Betriebsart auf {msg['mode']} gesetzt.")
    await rt.async_run_cycle()
    connection.send_result(msg["id"], rt.snapshot())


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/set_settings", vol.Required("settings"): dict})
@websocket_api.async_response
async def ws_set_settings(hass: HomeAssistant, connection, msg) -> None:
    rt = _runtime(hass)
    if rt is None:
        connection.send_error(msg["id"], "not_found", "nicht eingerichtet")
        return
    for key, value in msg["settings"].items():
        if hasattr(rt.settings, key):
            try:
                setattr(rt.settings, key, float(value) if not isinstance(value, bool) else value)
            except (ValueError, TypeError):
                continue
    rt.settings, notes = validate_settings(rt.settings)
    for n in notes:
        rt.log("warn", n)
    await _save(hass, rt)
    rt.log("ok", "Einstellungen gespeichert.")
    await rt.async_run_cycle()
    connection.send_result(msg["id"], rt.snapshot())


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/set_module", vol.Required("module_id"): str, vol.Required("enabled"): bool}
)
@websocket_api.async_response
async def ws_set_module(hass: HomeAssistant, connection, msg) -> None:
    rt = _runtime(hass)
    if rt is None:
        connection.send_error(msg["id"], "not_found", "nicht eingerichtet")
        return
    enabled = set(rt.enabled_modules)
    mid = msg["module_id"]
    if msg["enabled"]:
        enabled = resolve_dependencies(enabled, module_id=mid)
    else:
        from .core.modules import MODULES_BY_ID

        spec = MODULES_BY_ID.get(mid)
        if spec is not None and not spec.optional:
            connection.send_error(msg["id"], "not_allowed", "Das Grundsystem kann nicht deaktiviert werden.")
            return
        enabled.discard(mid)
    rt.enabled_modules = enabled
    await _save(hass, rt)
    connection.send_result(msg["id"], {"modules": store_cards(enabled)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/emergency", vol.Required("on"): bool})
@websocket_api.async_response
async def ws_emergency(hass: HomeAssistant, connection, msg) -> None:
    rt = _runtime(hass)
    if rt is None:
        connection.send_error(msg["id"], "not_found", "nicht eingerichtet")
        return
    rt.emergency_stop = bool(msg["on"])
    if rt.emergency_stop:
        rt.settings.force_boost = False
        await rt._fallback_to_normal()
    rt.log("err" if msg["on"] else "ok", "Not-Aus " + ("ausgelöst." if msg["on"] else "aufgehoben."))
    await _save(hass, rt)
    await rt.async_run_cycle()
    connection.send_result(msg["id"], rt.snapshot())
