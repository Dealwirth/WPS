"""Schalter von SolarFlow (Betriebsart und Urlaub)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODE_ACTIVE, MODE_SHADOW
from .core.models import Mode


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    add([SolarFlowAutomationSwitch(coordinator, entry), SolarFlowHolidaySwitch(coordinator, entry)])


class _Base(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "SolarFlow",
            "manufacturer": "SolarFlow",
        }

    @property
    def _snap(self) -> dict:
        return self.coordinator.data or {}


class SolarFlowAutomationSwitch(_Base):
    """An = Automatik scharf (active), Aus = Schatten (shadow)."""

    _attr_icon = "mdi:auto-mode"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "automation", "Automatik")

    @property
    def is_on(self):
        return self._snap.get("mode") == MODE_ACTIVE

    async def async_turn_on(self, **kwargs):
        await self._set(MODE_ACTIVE)

    async def async_turn_off(self, **kwargs):
        await self._set(MODE_SHADOW)

    async def _set(self, mode: str):
        runtime = self.coordinator.runtime
        runtime.settings.mode = Mode(mode)
        await _persist(self.hass, self.coordinator)
        await self.coordinator.async_request_refresh()


class SolarFlowHolidaySwitch(_Base):
    _attr_icon = "mdi:airplane"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "holiday", "Urlaubsmodus")

    @property
    def is_on(self):
        return bool(self._snap.get("settings", {}).get("holiday"))

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)

    async def _set(self, value: bool):
        self.coordinator.runtime.settings.holiday = value
        await _persist(self.hass, self.coordinator)
        await self.coordinator.async_request_refresh()


async def _persist(hass: HomeAssistant, coordinator) -> None:
    """Speichert die Laufzeit-Einstellungen sicher."""
    runtime = coordinator.runtime
    data = hass.data.get(DOMAIN, {}).get(runtime.entry_id)
    if data and data.get("store"):
        await data["store"].async_save(runtime.export_state())
