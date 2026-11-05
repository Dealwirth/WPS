"""Datenmodell für Store-Karten (Module).

Eine :class:`ModuleSpec` beschreibt genau eine Karte im internen Store.
Die Datenklassen sind bewusst rein: kein Home-Assistant-Import, keine Logik.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ModuleCategory(StrEnum):
    """Store-Kategorien; jeder Kategorie entspricht ein Ordner."""

    BASE = "base"
    ENERGY = "energy"
    DEVICES = "devices"
    INTELLIGENCE = "intelligence"
    SAFETY = "safety"


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    """Eine Karte im internen Store (ein Modul)."""

    module_id: str
    name_de: str
    name_en: str
    summary_de: str
    summary_en: str
    category: ModuleCategory
    icon: str
    optional: bool = True
    default_enabled: bool = False
    safety_level: str = "standard"
    requires: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    reason_de: str = ""
    reason_en: str = ""

    def as_dict(self, *, enabled: bool) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "name_de": self.name_de,
            "name_en": self.name_en,
            "summary_de": self.summary_de,
            "summary_en": self.summary_en,
            "category": self.category.value,
            "icon": self.icon,
            "optional": self.optional,
            "enabled": enabled,
            "default_enabled": self.default_enabled,
            "safety_level": self.safety_level,
            "requires": list(self.requires),
            "provides": list(self.provides),
            "reason_de": self.reason_de,
            "reason_en": self.reason_en,
        }
