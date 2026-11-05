"""Konstanten der SolarFlow-Integration.

SolarFlow verschiebt Warmwasser, Heizung und Ladung in die Sonnenstunden –
aber nur, wenn Daten frisch und plausibel sind, Grenzen eingehalten werden
und der Nutzer die Automatik ausdrücklich freigegeben hat.

Alle Nutzertexte erscheinen in Deutsch und Englisch. Fehlercodes sind stabil
und beginnen mit ``SF-``.
"""

from __future__ import annotations

DOMAIN = "solarflow"
NAME = "SolarFlow"
VERSION = "0.1.0"

#: Seitenleiste
PANEL_URL_PATH = "solarflow"
PANEL_WEBCOMPONENT = "solarflow-panel"
PANEL_TITLE = "SolarFlow"
PANEL_ICON = "mdi:solar-power"
STATIC_URL = "/solarflow_static"
CARDS_URL = "/solarflow_cards"

#: Speicher
STORAGE_KEY = "solarflow.runtime.{entry_id}"
STORAGE_VERSION = 1

#: Konfiguration – Quellen (aus HA gewählt)
CONF_FEED_IN_ENTITY = "feed_in_entity"
CONF_PV_ENTITY = "pv_entity"
CONF_GRID_IMPORT_ENTITY = "grid_import_entity"
CONF_WW_WATER_HEATER = "ww_water_heater"
CONF_WW_TEMP_NUMBER = "ww_temp_number"
CONF_WW_STORAGE_SENSOR = "ww_storage_sensor"
CONF_WW_HYSTERESIS_NUMBER = "ww_hysteresis_number"
CONF_HEATING_CLIMATE = "heating_climate"
CONF_WALLBOX_ENTITY = "wallbox_entity"
CONF_EV_ENTITY = "ev_entity"

#: Optionen – Regelverhalten
CONF_MODE = "mode"
CONF_FEED_IN_ON_W = "feed_in_on_w"
CONF_FEED_IN_OFF_W = "feed_in_off_w"
CONF_MIN_RUNTIME_MIN = "min_runtime_min"
CONF_MIN_PAUSE_MIN = "min_pause_min"
CONF_WW_BOOST_TEMP = "ww_boost_temp"
CONF_WW_NORMAL_TEMP = "ww_normal_temp"
CONF_WW_MIN_TEMP = "ww_min_temp"
CONF_WW_HYGIENE_MIN_TEMP = "ww_hygiene_min_temp"
CONF_SENSOR_MAX_AGE_S = "sensor_max_age_s"
CONF_MAX_GRID_IMPORT_W = "max_grid_import_w"
CONF_VERIFY_WRITES = "verify_writes"

#: Modi
MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ACTIVE = "active"
MODES = (MODE_OFF, MODE_SHADOW, MODE_ACTIVE)

#: Standardwerte (bewusst konservativ)
DEFAULT_FEED_IN_ON_W = 1800.0
DEFAULT_FEED_IN_OFF_W = 900.0
DEFAULT_MIN_RUNTIME_MIN = 15.0
DEFAULT_MIN_PAUSE_MIN = 10.0
DEFAULT_WW_BOOST_TEMP = 60.0
DEFAULT_WW_NORMAL_TEMP = 52.0
DEFAULT_WW_MIN_TEMP = 45.0
DEFAULT_WW_HYGIENE_MIN_TEMP = 50.0
DEFAULT_SENSOR_MAX_AGE_S = 300.0
DEFAULT_MAX_GRID_IMPORT_W = 11000.0

#: Gerätegrenzen (werden beim Setup gegen echte Attribute geprüft)
HARD_WW_MIN_TEMP = 10.0
HARD_WW_MAX_TEMP = 60.0

DEFAULT_UPDATE_INTERVAL_SECONDS = 15
DEFAULT_AUDIT_LIMIT = 300

#: Dienste
SERVICE_SET_MODE = "set_mode"
SERVICE_SET_SETTINGS = "set_settings"
SERVICE_FORCE_BOOST = "force_boost"
SERVICE_CANCEL_BOOST = "cancel_boost"
SERVICE_EMERGENCY_STOP = "emergency_stop"
SERVICE_RESET_EMERGENCY_STOP = "reset_emergency_stop"
SERVICE_RUN_CYCLE = "run_cycle"

#: Ereignisse
EVENT_ACTION = f"{DOMAIN}_action"
EVENT_ALERT = f"{DOMAIN}_alert"

#: Eigene Entitäten
ENTITY_MODE = "switch.solarflow_automatik"
ENTITY_STATE = "sensor.solarflow_zustand"
ENTITY_FEED_IN = "sensor.solarflow_einspeisung"
ENTITY_SAFETY = "binary_sensor.solarflow_schutz_aktiv"
