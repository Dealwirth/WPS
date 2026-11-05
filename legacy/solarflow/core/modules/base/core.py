"""Modul: SolarFlow Grundsystem (immer aktiv).

Zeigt PV-Erzeugung, Verbrauch, Netzbezug und Einspeisung, erkennt Geräte,
schützt Grenzen, prüft Daten und verhindert unsinnige Automatik.

Ort im Store: Kategorie "base", nicht abschaltbar.
Hängt an: nichts – alle anderen Module verlangen mindestens dieses.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="core",
    name_de="SolarFlow Grundsystem",
    name_en="SolarFlow Core",
    summary_de=(
        "Immer aktiv. Zeigt PV-Erzeugung, Verbrauch, Netzbezug und Einspeisung. "
        "Erkennt Geräte, schützt Grenzen, prüft Daten und verhindert unsinnige Automatik."
    ),
    summary_en=(
        "Always active. Shows PV generation, consumption, grid import and export. "
        "Detects devices, protects limits, checks data and prevents unsafe automation."
    ),
    category=ModuleCategory.BASE,
    icon="mdi:solar-power",
    optional=False,
    default_enabled=True,
    safety_level="mandatory",
    provides=("energy_balance", "device_discovery", "fallback", "limits", "data_quality", "audit"),
    reason_de="Die Grundlage für alle anderen Module.",
    reason_en="The foundation for every other module.",
)
