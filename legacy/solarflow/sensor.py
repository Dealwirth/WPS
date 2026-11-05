"""Sensoren von SolarFlow (Anzeige)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    add(
        [
            SolarFlowStateSensor(coordinator, entry),
            SolarFlowFeedInSensor(coordinator, entry),
            SolarFlowStorageSensor(coordinator, entry),
            SolarFlowChangesSensor(coordinator, entry),
        ]
    )


class _Base(CoordinatorEntity, SensorEntity):
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
            "model": "Energie-Assistent",
        }

    @property
    def _snap(self) -> dict:
        return self.coordinator.data or {}


class SolarFlowStateSensor(_Base):
    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "state", "Zustand")

    @property
    def native_value(self):
        s = self._snap.get("state", "normal")
        return {"normal": "Normal", "boost": "Überschuss"}.get(s, s)

    @property
    def extra_state_attributes(self):
        s = self._snap
        return {
            "betriebsart": s.get("mode"),
            "notaus": s.get("emergency_stop"),
            "blockiert": s.get("blocked"),
            "grund": s.get("reason_de"),
            "einspeisung_w": s.get("feed_in_w"),
            "speicher_c": s.get("storage_temp"),
            "wechsel": s.get("machine_changes"),
        }


class SolarFlowFeedInSensor(_Base):
    _attr_icon = "mdi:transmission-tower-export"
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "feed_in", "Einspeisung")

    @property
    def native_value(self):
        return self._snap.get("feed_in_w")


class SolarFlowStorageSensor(_Base):
    _attr_icon = "mdi:water-thermometer"
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "storage", "Speichertemperatur")

    @property
    def native_value(self):
        return self._snap.get("storage_temp")


class SolarFlowChangesSensor(_Base):
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "changes", "Umschaltungen")

    @property
    def native_value(self):
        return self._snap.get("machine_changes")
