"""Binärsensoren von SolarFlow (Schutz-Anzeige)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    add([SolarFlowSafetySensor(coordinator, entry), SolarFlowEmergencySensor(coordinator, entry)])


class _Base(CoordinatorEntity, BinarySensorEntity):
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


class SolarFlowSafetySensor(_Base):
    _attr_icon = "mdi:shield-alert"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "safety", "Schutz aktiv")

    @property
    def is_on(self):
        return bool(self._snap.get("blocked"))


class SolarFlowEmergencySensor(_Base):
    _attr_icon = "mdi:alert-octagon"
    _attr_device_class = "problem"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "emergency", "Not-Aus")

    @property
    def is_on(self):
        return bool(self._snap.get("emergency_stop"))
