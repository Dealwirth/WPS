"""Modul: Heizung & Puffer.

Heizkurven-Verschiebung und Pufferladung werden nur angepasst, wenn es der
Komfort zulässt. Standardmäßig nur lesend – Schreiben erst nach Freigabe.

Ort im Store: Kategorie "devices". Hängt an: core.
"""

from __future__ import annotations

from .._spec import ModuleCategory, ModuleSpec

SPEC = ModuleSpec(
    module_id="heating",
    name_de="Heizung & Puffer",
    name_en="Heating & Buffer",
    summary_de=(
        "Verschiebt Heizkurve und Pufferladung in günstige Zeiten. Komfortgrenzen "
        "bleiben hart; im Zweifel wird nicht eingegriffen."
    ),
    summary_en=(
        "Shifts the heating curve and buffer charging into cheap times. Comfort limits stay "
        "hard; when in doubt it does not intervene."
    ),
    category=ModuleCategory.DEVICES,
    icon="mdi:radiator",
    requires=("core", "thermal"),
    provides=("heating_curve_shift", "buffer_charge"),
    reason_de="Vorheizen mit Sonne statt mit Netzstrom.",
    reason_en="Pre-heat with sun instead of grid power.",
)
