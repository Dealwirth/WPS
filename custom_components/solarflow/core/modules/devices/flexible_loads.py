"""Modul: Flexible Lasten.

Waschmaschine, Trockner, Geschirrspüler, Pumpen und Steckdosen lassen sich
zeitlich in die Sonne schieben – mit Zeit- und Leistungsgrenzen.

Ort im Store: Kategorie "devices". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="flexible_loads",
    name_de="Flexible Lasten",
    name_en="Flexible Loads",
    summary_de=(
        "Schiebt Waschmaschine, Trockner, Geschirrspüler, Pumpen und Steckdosen in die "
        "Sonnenstunden. Zeit- und Leistungsgrenzen bleiben hart."
    ),
    summary_en=(
        "Shifts washing machine, dryer, dishwasher, pumps and sockets into sunny hours. "
        "Time and power limits stay hard."
    ),
    category=ModuleCategory.DEVICES,
    default_enabled=False,
    icon="mdi:washing-machine",
    requires=("core",),
    provides=("scheduled_loads",),
    reason_de="Große Verbraucher laufen, wenn Strom übrig ist.",
    reason_en="Big consumers run when power is left over.",
)
