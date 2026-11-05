"""Modul: Prognose & Lernen.

Verbrauchs- und Solarprognose mit Vertrauenswert; begrenzte, abbrechbare
Lernläufe. Die Prognose berät nur – sie schaltet nie selbst.

Ort im Store: Kategorie "intelligence". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="forecast",
    name_de="Prognose & Lernen",
    name_en="Forecast & Learning",
    summary_de=(
        "Schätzt Verbrauch und Solarertrag mit Vertrauenswert. Begrenzte, jederzeit "
        "abbrechbare Lernläufe. Die Prognose berät nur, sie schaltet nicht."
    ),
    summary_en=(
        "Estimates consumption and solar yield with a confidence value. Bounded, always "
        "cancellable learning runs. The forecast only advises, it does not switch."
    ),
    category=ModuleCategory.INTELLIGENCE,
    default_enabled=True,
    icon="mdi:chart-line",
    requires=("core",),
    provides=("forecast", "learning"),
    reason_de="Vorausschauend planen statt raten.",
    reason_en="Plan ahead instead of guessing.",
)
