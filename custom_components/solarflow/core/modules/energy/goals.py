"""Modul: Ziele & Berichte.

Eigenverbrauch, Autarkie, CO₂ und Ersparnis als einfache Kennzahlen. Reine
Anzeige und Auswertung.

Ort im Store: Kategorie "energy". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="goals",
    name_de="Ziele & Berichte",
    name_en="Goals & Reports",
    summary_de=(
        "Zeigt Eigenverbrauch, Autarkie, CO₂ und Ersparnis in einfachen Zahlen. "
        "Reine Anzeige und Auswertung, ohne Schaltfunktion."
    ),
    summary_en=(
        "Shows self-consumption, autarky, CO₂ and savings in simple numbers. Display and reporting only, no switching."
    ),
    category=ModuleCategory.ENERGY,
    icon="mdi:chart-donut",
    requires=("core",),
    provides=("self_consumption", "autarky", "co2", "savings"),
    reason_de="Sehen, was die Sonne wirklich bringt.",
    reason_en="See what the sun really brings.",
)
