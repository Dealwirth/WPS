"""Katalog der Gerätetypen.

Hier stehen alle Vorlagen, die im Store auswählbar sind. Eine neue Sorte
Gerät = ein Eintrag in ``DEVICE_TYPES``. Die Reihenfolge ist die Anzeige-
reihenfolge im Store.
"""

from __future__ import annotations

from ._spec import DeviceCategory as Cat
from ._spec import DeviceTypeSpec, RoleKind, RoleSpec, SettingSpec

# Wiederverwendbare Rollen ------------------------------------------------- #

_R_POWER = RoleSpec(
    "power", "Leistung", "Power", ("sensor",), RoleKind.POWER, keywords=("power", "leistung", "watt")
)
_R_SOC = RoleSpec(
    "soc",
    "Ladestand",
    "State of charge",
    ("sensor",),
    RoleKind.SENSOR,
    keywords=("soc", "battery", "ladestand", "akku"),
)
_R_SWITCH = RoleSpec(
    "switch",
    "Schalter",
    "Switch",
    ("switch", "input_boolean"),
    RoleKind.SWITCH,
    required=True,
    keywords=("wallbox", "pumpe", "pump", "heizstab", "steckdose", "plug", "charger", "laden"),
)
_R_STORAGE = RoleSpec(
    "storage",
    "Speichertemperatur",
    "Storage temperature",
    ("sensor",),
    RoleKind.SENSOR,
    keywords=("speicher", "storage", "tank", "warmwasser", "dhw", "boiler"),
)
_R_SETPOINT = RoleSpec(
    "setpoint",
    "Solltemperatur",
    "Setpoint temperature",
    ("number", "water_heater"),
    RoleKind.SETPOINT,
    keywords=("temperatur", "temperature", "soll", "setpoint", "ww"),
)
_R_CLIMATE = RoleSpec(
    "climate",
    "Klimagerät",
    "Climate device",
    ("climate",),
    RoleKind.CLIMATE,
    keywords=("heizung", "heating", "klima", "climate", "wp"),
)


def _surplus_settings(*, on: float, off: float, target_soc: bool = False) -> tuple[SettingSpec, ...]:
    base = (
        SettingSpec("on_w", "Einschalten ab (W)", "Switch on at (W)", on, 0, 20000, 100, "W"),
        SettingSpec("off_w", "Ausschalten ab (W)", "Switch off at (W)", off, 0, 20000, 100, "W"),
        SettingSpec("min_on_min", "Mindestlaufzeit (min)", "Min runtime (min)", 5, 0, 240, 1, "min"),
        SettingSpec("min_off_min", "Mindestpause (min)", "Min pause (min)", 5, 0, 240, 1, "min"),
    )
    if not target_soc:
        return base
    return (
        *base,
        SettingSpec("target_soc", "Ziel-Ladestand (%)", "Target state of charge (%)", 80, 0, 100, 1, "%"),
        SettingSpec("min_soc", "Mindest-Ladestand (%)", "Minimum state of charge (%)", 20, 0, 100, 1, "%"),
    )


_THERMAL_SETTINGS = (
    SettingSpec("boost_temp", "Boost-Temperatur (°C)", "Boost temperature (°C)", 60, 10, 90, 1, "°C"),
    SettingSpec("normal_temp", "Normaltemperatur (°C)", "Normal temperature (°C)", 52, 10, 90, 1, "°C"),
    SettingSpec("hysteresis_c", "Bedarf-Hysterese (K)", "Demand hysteresis (K)", 2, 0, 15, 0.5, "K"),
    SettingSpec("on_w", "Boost ein ab (W)", "Boost on at (W)", 1800, 0, 20000, 100, "W"),
    SettingSpec("off_w", "Boost aus ab (W)", "Boost off at (W)", 900, 0, 20000, 100, "W"),
)


DEVICE_TYPES: tuple[DeviceTypeSpec, ...] = (
    # ---------------------------------------------------------------- Wärme
    DeviceTypeSpec(
        type_id="heat_pump",
        emoji="♨️",
        accent="amber",
        name_de="Wärmepumpe / Warmwasser",
        name_en="Heat pump / Hot water",
        summary_de="Erwärmt Warmwasser bei PV-Überschuss – mit Hysterese statt Takten.",
        summary_en="Heats hot water on PV surplus – with hysteresis instead of cycling.",
        icon="mdi:heat-pump",
        category=Cat.HEAT,
        strategy="thermal_boost",
        roles=(_R_STORAGE, _R_SETPOINT, _R_CLIMATE, _R_POWER),
        settings=_THERMAL_SETTINGS,
    ),
    DeviceTypeSpec(
        type_id="heating_rod",
        emoji="🔥",
        accent="coral",
        name_de="Heizstab / Tauchsieder",
        name_en="Heating rod / Immersion heater",
        summary_de="Schaltet einen Heizstab nach Überschuss und Speichertemperatur.",
        summary_en="Switches a heating rod by surplus and storage temperature.",
        icon="mdi:water-boiler",
        category=Cat.HEAT,
        strategy="thermal_boost",
        roles=(_R_STORAGE, _R_SETPOINT, _R_POWER),
        settings=_THERMAL_SETTINGS,
    ),
    DeviceTypeSpec(
        type_id="air_conditioner",
        emoji="❄️",
        accent="sky",
        name_de="Klimaanlage",
        name_en="Air conditioner",
        summary_de="Nutzt Überschuss zum Vorheizen/Vorkühlen – nur Vorschlag, kein Zwang.",
        summary_en="Uses surplus for pre-heating/pre-cooling – suggestion only.",
        icon="mdi:air-conditioner",
        category=Cat.HEAT,
        strategy="climate_boost",
        roles=(_R_CLIMATE, _R_POWER),
        settings=(
            SettingSpec("shift_c", "Verschiebung (°C)", "Shift (°C)", 2, 0, 10, 0.5, "°C"),
            SettingSpec("on_w", "Aktiv ab (W)", "Active at (W)", 2500, 0, 20000, 100, "W"),
        ),
    ),
    # --------------------------------------------------------------- Strom
    DeviceTypeSpec(
        type_id="wallbox",
        emoji="🚗",
        accent="teal",
        name_de="Wallbox",
        name_en="Wallbox",
        summary_de="Lädt das Auto mit PV-Überschuss – Mindestlaufzeit und Ziel-Ladestand werden beachtet.",
        summary_en="Charges the car on PV surplus – minimum runtime and target SoC respected.",
        icon="mdi:ev-station",
        category=Cat.MOBILITY,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER, _R_SOC),
        settings=_surplus_settings(on=4200, off=2000, target_soc=True),
    ),
    DeviceTypeSpec(
        type_id="ev_charger",
        emoji="🔌",
        accent="sky",
        name_de="E-Auto / Ladegerät",
        name_en="EV / Charger",
        summary_de="Einfaches Überschussladen für ein Ladegerät oder eine schaltbare Ladesteckdose.",
        summary_en="Simple surplus charging for a charger or switchable socket.",
        icon="mdi:car-electric",
        category=Cat.MOBILITY,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER, _R_SOC),
        settings=_surplus_settings(on=2000, off=800, target_soc=True),
    ),
    DeviceTypeSpec(
        type_id="battery",
        emoji="🔋",
        accent="violet",
        name_de="PV-Speicher (Batterie)",
        name_en="PV battery",
        summary_de="Beobachtet den Speicher und schont die Reserve – schreibt nichts.",
        summary_en="Watches the battery and protects the reserve – writes nothing.",
        icon="mdi:battery-charging",
        category=Cat.STORAGE,
        strategy="battery_reserve",
        roles=(_R_SOC, _R_POWER),
        settings=(
            SettingSpec("min_soc", "Mindest-Ladestand (%)", "Minimum state of charge (%)", 20, 0, 100, 1, "%"),
            SettingSpec("reserve_soc", "Reserve ab (%)", "Reserve from (%)", 30, 0, 100, 1, "%"),
        ),
    ),
    DeviceTypeSpec(
        type_id="pool_pump",
        emoji="🏊",
        accent="sky",
        name_de="Poolpumpe",
        name_en="Pool pump",
        summary_de="Lässt die Poolpumpe bevorzugt bei Sonne laufen.",
        summary_en="Runs the pool pump preferably in the sun.",
        icon="mdi:pool",
        category=Cat.ELECTRIC,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER),
        settings=_surplus_settings(on=800, off=200),
    ),
    DeviceTypeSpec(
        type_id="water_pump",
        emoji="💧",
        accent="sky",
        name_de="Pumpe / Bewässerung",
        name_en="Pump / Irrigation",
        summary_de="Bewässerung oder Pumpe laufen bei Überschuss.",
        summary_en="Irrigation or pump runs on surplus.",
        icon="mdi:water-pump",
        category=Cat.ELECTRIC,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER),
        settings=_surplus_settings(on=600, off=150),
    ),
    DeviceTypeSpec(
        type_id="washing_machine",
        emoji="🧺",
        accent="violet",
        name_de="Waschmaschine",
        name_en="Washing machine",
        summary_de="Startet die Waschmaschine nur bei genügend Überschuss.",
        summary_en="Starts the washing machine only with enough surplus.",
        icon="mdi:washing-machine",
        category=Cat.ELECTRIC,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER),
        settings=_surplus_settings(on=1000, off=200),
    ),
    DeviceTypeSpec(
        type_id="dryer",
        emoji="🌀",
        accent="pink",
        name_de="Trockner",
        name_en="Dryer",
        summary_de="Trockner läuft bei Überschuss.",
        summary_en="Dryer runs on surplus.",
        icon="mdi:tumble-dryer",
        category=Cat.ELECTRIC,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER),
        settings=_surplus_settings(on=1000, off=200),
    ),
    DeviceTypeSpec(
        type_id="dishwasher",
        emoji="🍽️",
        accent="teal",
        name_de="Geschirrspüler",
        name_en="Dishwasher",
        summary_de="Geschirrspüler startet bei Überschuss.",
        summary_en="Dishwasher starts on surplus.",
        icon="mdi:dishwasher",
        category=Cat.ELECTRIC,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER),
        settings=_surplus_settings(on=1000, off=200),
    ),
    DeviceTypeSpec(
        type_id="generic_switch",
        emoji="⚡",
        accent="amber",
        name_de="Freier Verbraucher",
        name_en="Generic load",
        summary_de="Beliebiger schaltbarer Verbraucher – Steckdose, Relais, Gerät.",
        summary_en="Any switchable load – socket, relay, appliance.",
        icon="mdi:power-plug",
        category=Cat.GENERIC,
        strategy="surplus_switch",
        roles=(_R_SWITCH, _R_POWER),
        settings=_surplus_settings(on=1500, off=500),
    ),
)
