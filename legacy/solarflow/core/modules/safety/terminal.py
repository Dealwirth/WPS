"""Modul: Sicherheitsterminal.

Dauerüberwachung, Not-Aus, Selbstheilung und Ereignisprotokoll. Es ist die
letzte Instanz und kann alles sperren.

Ort im Store: Kategorie "safety". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="safety",
    name_de="Sicherheitsterminal",
    name_en="Safety Terminal",
    summary_de=(
        "Dauerüberwachung, Not-Aus, Selbstheilung und ein vollständiges Ereignisprotokoll. "
        "Die letzte Instanz – sie kann jede Automatik sofort sperren."
    ),
    summary_en=(
        "Continuous monitoring, emergency stop, self-healing and a full event log. "
        "The last instance – it can lock down all automation at once."
    ),
    category=ModuleCategory.SAFETY,
    default_enabled=True,
    icon="mdi:shield-check",
    requires=("core",),
    provides=("monitoring", "emergency_stop", "self_healing", "audit"),
    reason_de="Nichts geht verloren, im Zweifel wird sicher abgeschaltet.",
    reason_en="Nothing is lost; when in doubt it shuts down safely.",
)
