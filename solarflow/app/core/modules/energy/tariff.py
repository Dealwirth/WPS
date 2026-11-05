"""Modul: Tarif-Fenster.

Zeigt die günstigen Stunden (Einspeisetarif, Bezugstarif) und markiert sie im
Plan. Reine Anzeige, ohne Schaltfunktion.

Ort im Store: Kategorie "energy". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="tariff",
    name_de="Tarif-Fenster",
    name_en="Tariff Windows",
    summary_de=(
        "Zeigt die günstigen Zeiten deines Stromtarifs (Einspeise-/Bezugstarif) und "
        "markiert sie im Plan. Reine Anzeige, ohne Schaltfunktion."
    ),
    summary_en=(
        "Shows the cheap windows of your electricity tariff (feed-in/import) and highlights "
        "them in the plan. Display only, no switching."
    ),
    category=ModuleCategory.ENERGY,
    default_enabled=True,
    icon="mdi:clock-time-eight",
    requires=("core",),
    provides=("tariff_windows",),
    reason_de="Günstige Stunden auf einen Blick.",
    reason_en="Cheap hours at a glance.",
)
