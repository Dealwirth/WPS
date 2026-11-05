"""Modul: Wallbox & Laden (Wattpilot, Ioniq).

PV-Überschussladen mit Phasenlogik, Mindestladedauer und Ziel-SOC. Reine
Unterstützung der vorhandenen Wallbox-Logik – SolarFlow greift nur ein, wenn
es ausdrücklich freigegeben ist.

Ort im Store: Kategorie "devices". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="wallbox",
    name_de="Wallbox & Laden",
    name_en="Wallbox & Charging",
    summary_de=(
        "Unterstützt das PV-Überschussladen der Wallbox und den Ladeplan des Fahrzeugs. "
        "Phasenumschaltung, Mindestladedauer und Ziel-SOC werden respektiert."
    ),
    summary_en=(
        "Supports wallbox PV surplus charging and the vehicle charge plan. Phase switching, "
        "minimum charging time and target SOC are respected."
    ),
    category=ModuleCategory.DEVICES,
    default_enabled=False,
    icon="mdi:ev-station",
    requires=("core",),
    provides=("wallbox_surplus", "ev_charge_plan"),
    reason_de="Sonnenstrom ins Auto statt ins Netz.",
    reason_en="Sun power into the car instead of the grid.",
)
