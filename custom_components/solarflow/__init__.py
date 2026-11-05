"""SolarFlow – Wärme und Ladung in die Sonne schieben, aber sicher.

Diese Datei richtet einen Config-Eintrag ein: Laufzeit, Coordinator,
Entitäten, Dienste, Panel und Karten. Beim Entfernen werden nur eigene
Daten gelöscht – fremde Home-Assistant-Entitäten bleiben unberührt.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .coordinator import SolarFlowCoordinator
from .runtime import SolarFlowRuntime

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Richtet einen SolarFlow-Eintrag ein."""
    hass.data.setdefault(DOMAIN, {})

    runtime = SolarFlowRuntime(hass, entry.entry_id, {**entry.data, **entry.options})
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id))
    stored = await store.async_load()
    runtime.import_state(stored)

    coordinator = SolarFlowCoordinator(hass, runtime)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "runtime": runtime,
        "coordinator": coordinator,
        "store": store,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Dienste (idempotent)
    from .services import async_register_services

    await async_register_services(hass)

    # Panel und Karten nur einmal registrieren
    from .panel import async_register_panel

    await async_register_panel(hass)

    from .websocket_api import async_register_websocket

    async_register_websocket(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entlädt einen Eintrag."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data and data.get("store"):
            await data["store"].async_save(data["runtime"].export_state())
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entfernt nur die eigenen Daten (Store). Fremde Entitäten bleiben."""
    try:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id))
        await store.async_remove()
    except Exception:  # pragma: no cover - defensiv
        _LOGGER.debug("SolarFlow Store konnte nicht entfernt werden")


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Bei Optionsänderung neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
