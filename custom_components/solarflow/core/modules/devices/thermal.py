"""Modul: Thermische Flexibilität (Warmwasser & Wärmepumpe).

Warmwasser darf im Überschussfenster wärmer werden – aber nur innerhalb von
Temperatur-, Hygiene- und Komfortgrenzen. Das ist das Kernmodul dieser
Integration und setzt die alte Viessmann/PV-Automation robust um.

Ort im Store: Kategorie "devices". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="thermal",
    name_de="Thermische Flexibilität",
    name_en="Thermal Flexibility",
    summary_de=(
        "Warmwasser wird bei PV-Überschuss aufgeladen – nur innerhalb von Temperatur-, "
        "Hygiene- und Komfortgrenzen. Echte Hysterese statt Taktung."
    ),
    summary_en=(
        "Hot water is charged on PV surplus – only within temperature, hygiene and comfort "
        "limits. Real hysteresis instead of cycling."
    ),
    category=ModuleCategory.DEVICES,
    icon="mdi:heat-pump",
    requires=("core",),
    provides=("hot_water_boost", "heat_pump_plan"),
    reason_de="Wärme dann erzeugen, wenn die Sonne scheint.",
    reason_en="Generate heat when the sun shines.",
)
