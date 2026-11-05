"""Einrichtungsassistent und Optionen.

Der Assistent fragt in einfachen Schritten nach den Quellen und zeigt
Vorbelegungen. Er schlägt keine Automatik vor, die nicht ausdrücklich
freigegeben wurde: Der Startmodus ist immer "Schatten".
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EV_ENTITY,
    CONF_FEED_IN_ENTITY,
    CONF_FORECAST_HORIZON_H,
    CONF_GRID_IMPORT_ENTITY,
    CONF_HEATING_CLIMATE,
    CONF_HEATING_SHIFT_C,
    CONF_MAX_GRID_IMPORT_W,
    CONF_MODE,
    CONF_PV_ENTITY,
    CONF_SENSOR_MAX_AGE_S,
    CONF_WALLBOX_ENTITY,
    CONF_WALLBOX_MIN_CHARGE_A,
    CONF_WALLBOX_OFF_W,
    CONF_WALLBOX_ON_W,
    CONF_WW_BOOST_TEMP,
    CONF_WW_HYGIENE_MIN_TEMP,
    CONF_WW_HYSTERESIS_C,
    CONF_WW_HYSTERESIS_NUMBER,
    CONF_WW_MIN_TEMP,
    CONF_WW_NORMAL_TEMP,
    CONF_WW_STORAGE_SENSOR,
    CONF_WW_TEMP_NUMBER,
    CONF_WW_WATER_HEATER,
    DEFAULT_FEED_IN_OFF_W,
    DEFAULT_FEED_IN_ON_W,
    DEFAULT_FORECAST_HORIZON_H,
    DEFAULT_HEATING_SHIFT_C,
    DEFAULT_MAX_GRID_IMPORT_W,
    DEFAULT_MIN_PAUSE_MIN,
    DEFAULT_MIN_RUNTIME_MIN,
    DEFAULT_SENSOR_MAX_AGE_S,
    DEFAULT_WALLBOX_MIN_CHARGE_A,
    DEFAULT_WALLBOX_OFF_W,
    DEFAULT_WALLBOX_ON_W,
    DEFAULT_WW_BOOST_TEMP,
    DEFAULT_WW_HYGIENE_MIN_TEMP,
    DEFAULT_WW_HYSTERESIS_C,
    DEFAULT_WW_MIN_TEMP,
    DEFAULT_WW_NORMAL_TEMP,
    DOMAIN,
    MODE_SHADOW,
)

_ENTITY = selector.EntitySelector
_NUM = selector.NumberSelector


def _ent(domains: list[str] | None = None, device_class: list[str] | None = None):
    cfg: dict[str, Any] = {}
    if domains:
        cfg["domain"] = domains
    if device_class:
        cfg["device_class"] = device_class
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


def _num(minv: float, maxv: float, step: float, unit: str):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minv, max=maxv, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _opt(key: str, default: Any, selector_obj):
    """Optionales Feld; ohne Vorbelegung wird kein None gesetzt.

    Ein ``None``-Standardwert würde vom Entity-Selector als ungültig
    abgelehnt – deshalb lassen wir das Feld dann ganz weg.
    """
    if default in (None, ""):
        return vol.Optional(key), selector_obj
    return vol.Optional(key, default=default), selector_obj


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        dict(
            [
                _opt(CONF_FEED_IN_ENTITY, defaults.get(CONF_FEED_IN_ENTITY), _ent(["sensor"])),
                _opt(CONF_PV_ENTITY, defaults.get(CONF_PV_ENTITY), _ent(["sensor"])),
                _opt(CONF_GRID_IMPORT_ENTITY, defaults.get(CONF_GRID_IMPORT_ENTITY), _ent(["sensor"])),
                _opt(CONF_WW_WATER_HEATER, defaults.get(CONF_WW_WATER_HEATER), _ent(["water_heater"])),
                _opt(CONF_WW_TEMP_NUMBER, defaults.get(CONF_WW_TEMP_NUMBER), _ent(["number"])),
                _opt(
                    CONF_WW_STORAGE_SENSOR,
                    defaults.get(CONF_WW_STORAGE_SENSOR),
                    _ent(["sensor"], ["temperature"]),
                ),
                _opt(CONF_WW_HYSTERESIS_NUMBER, defaults.get(CONF_WW_HYSTERESIS_NUMBER), _ent(["number"])),
                _opt(CONF_HEATING_CLIMATE, defaults.get(CONF_HEATING_CLIMATE), _ent(["climate"])),
                _opt(
                    CONF_WALLBOX_ENTITY,
                    defaults.get(CONF_WALLBOX_ENTITY),
                    _ent(["switch", "sensor", "select", "number"]),
                ),
                _opt(CONF_EV_ENTITY, defaults.get(CONF_EV_ENTITY), _ent(["sensor", "switch", "number"])),
            ]
        )
    )


class SolarFlowConfigFlow(ConfigFlow, domain=DOMAIN):
    """Assistent für die erste Einrichtung."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="SolarFlow", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SolarFlowOptionsFlow(config_entry)


class SolarFlowOptionsFlow(OptionsFlow):
    """Einstellungen und Regelverhalten."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            merged = {**current, **user_input}
            return self.async_create_entry(title="", data=merged)

        schema = _schema(current).extend(
            {
                vol.Optional(CONF_MODE, default=current.get(CONF_MODE, MODE_SHADOW)): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value="off", label="Aus (nur Schutz/Anzeige)"),
                            selector.SelectOptionDict(value="shadow", label="Schatten (beobachten, nicht schalten)"),
                            selector.SelectOptionDict(value="active", label="Aktiv (Automatik scharf)"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("feed_in_on_w", default=current.get("feed_in_on_w", DEFAULT_FEED_IN_ON_W)): _num(
                    0, 20000, 50, "W"
                ),
                vol.Optional("feed_in_off_w", default=current.get("feed_in_off_w", DEFAULT_FEED_IN_OFF_W)): _num(
                    0, 20000, 50, "W"
                ),
                vol.Optional("min_runtime_min", default=current.get("min_runtime_min", DEFAULT_MIN_RUNTIME_MIN)): _num(
                    0, 720, 1, "min"
                ),
                vol.Optional("min_pause_min", default=current.get("min_pause_min", DEFAULT_MIN_PAUSE_MIN)): _num(
                    0, 720, 1, "min"
                ),
                vol.Optional(CONF_WW_BOOST_TEMP, default=current.get(CONF_WW_BOOST_TEMP, DEFAULT_WW_BOOST_TEMP)): _num(
                    10, 60, 1, "°C"
                ),
                vol.Optional(
                    CONF_WW_NORMAL_TEMP, default=current.get(CONF_WW_NORMAL_TEMP, DEFAULT_WW_NORMAL_TEMP)
                ): _num(10, 60, 1, "°C"),
                vol.Optional(CONF_WW_MIN_TEMP, default=current.get(CONF_WW_MIN_TEMP, DEFAULT_WW_MIN_TEMP)): _num(
                    10, 60, 1, "°C"
                ),
                vol.Optional(
                    CONF_WW_HYGIENE_MIN_TEMP, default=current.get(CONF_WW_HYGIENE_MIN_TEMP, DEFAULT_WW_HYGIENE_MIN_TEMP)
                ): _num(10, 60, 1, "°C"),
                vol.Optional(
                    CONF_SENSOR_MAX_AGE_S, default=current.get(CONF_SENSOR_MAX_AGE_S, DEFAULT_SENSOR_MAX_AGE_S)
                ): _num(10, 3600, 10, "s"),
                vol.Optional(
                    CONF_MAX_GRID_IMPORT_W, default=current.get(CONF_MAX_GRID_IMPORT_W, DEFAULT_MAX_GRID_IMPORT_W)
                ): _num(1000, 60000, 100, "W"),
                vol.Optional(
                    CONF_WW_HYSTERESIS_C, default=current.get(CONF_WW_HYSTERESIS_C, DEFAULT_WW_HYSTERESIS_C)
                ): _num(0, 15, 0.5, "°C"),
                vol.Optional(
                    CONF_WALLBOX_ON_W, default=current.get(CONF_WALLBOX_ON_W, DEFAULT_WALLBOX_ON_W)
                ): _num(0, 20000, 100, "W"),
                vol.Optional(
                    CONF_WALLBOX_OFF_W, default=current.get(CONF_WALLBOX_OFF_W, DEFAULT_WALLBOX_OFF_W)
                ): _num(0, 20000, 100, "W"),
                vol.Optional(
                    CONF_WALLBOX_MIN_CHARGE_A,
                    default=current.get(CONF_WALLBOX_MIN_CHARGE_A, DEFAULT_WALLBOX_MIN_CHARGE_A),
                ): _num(6, 32, 1, "A"),
                vol.Optional(
                    CONF_HEATING_SHIFT_C, default=current.get(CONF_HEATING_SHIFT_C, DEFAULT_HEATING_SHIFT_C)
                ): _num(0, 10, 0.5, "°C"),
                vol.Optional(
                    CONF_FORECAST_HORIZON_H,
                    default=current.get(CONF_FORECAST_HORIZON_H, DEFAULT_FORECAST_HORIZON_H),
                ): _num(1, 72, 1, "h"),
                vol.Optional("verify_writes", default=current.get("verify_writes", True)): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
