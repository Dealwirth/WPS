"""Vorlagen (Gerätetypen) für den Geräte-Store.

Ein :class:`DeviceTypeSpec` beschreibt eine Sorte Gerät (z. B. Wallbox oder
Wärmepumpe). Ein Nutzer legt daraus ein :class:`~core.devices._model.Device`
an – eine konkrete Instanz mit zugeordneten Entitäten und eigenen Schwellen.

Alles hier ist rein: kein Home-Assistant-Import, keine Logik.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DeviceCategory(StrEnum):
    """Gruppen im Store (nur für die Anzeige)."""

    HEAT = "heat"  # Wärme
    ELECTRIC = "electric"  # Strom
    MOBILITY = "mobility"  # Mobilität
    STORAGE = "storage"  # Speicher
    GENERIC = "generic"  # Sonstiges


class RoleKind(StrEnum):
    """Wozu dient eine Entität? Steuert Erkennung und Schreibweise."""

    POWER = "power"  # Leistungssensor (W)
    SENSOR = "sensor"  # Messwert (Temperatur, SOC …)
    SETPOINT = "setpoint"  # schreibbarer Sollwert
    SWITCH = "switch"  # Ein/Aus-Schalter
    CLIMATE = "climate"  # Klimagerät


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """Eine Entität, die ein Gerät braucht oder nutzen kann."""

    key: str
    label_de: str
    label_en: str
    domains: tuple[str, ...]
    kind: RoleKind = RoleKind.SENSOR
    required: bool = False
    keywords: tuple[str, ...] = ()
    hint_de: str = ""
    hint_en: str = ""


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """Ein einstellbarer Wert eines Geräts (für die Oberfläche)."""

    key: str
    label_de: str
    label_en: str
    default: float
    minimum: float
    maximum: float
    step: float = 1.0
    unit: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label_de": self.label_de,
            "label_en": self.label_en,
            "default": self.default,
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class DeviceTypeSpec:
    """Eine Vorlage im Store."""

    type_id: str
    name_de: str
    name_en: str
    summary_de: str
    summary_en: str
    icon: str
    category: DeviceCategory
    strategy: str
    roles: tuple[RoleSpec, ...]
    settings: tuple[SettingSpec, ...] = ()
    safety_level: str = "standard"

    def role(self, key: str) -> RoleSpec | None:
        return next((r for r in self.roles if r.key == key), None)

    @property
    def required_roles(self) -> tuple[str, ...]:
        return tuple(r.key for r in self.roles if r.required)

    def default_settings(self) -> dict[str, float]:
        return {s.key: s.default for s in self.settings}

    def as_dict(self) -> dict[str, object]:
        return {
            "type_id": self.type_id,
            "name_de": self.name_de,
            "name_en": self.name_en,
            "summary_de": self.summary_de,
            "summary_en": self.summary_en,
            "icon": self.icon,
            "category": self.category.value,
            "strategy": self.strategy,
            "safety_level": self.safety_level,
            "roles": [
                {
                    "key": r.key,
                    "label_de": r.label_de,
                    "label_en": r.label_en,
                    "domains": list(r.domains),
                    "kind": r.kind.value,
                    "required": r.required,
                    "hint_de": r.hint_de,
                    "hint_en": r.hint_en,
                }
                for r in self.roles
            ],
            "settings": [s.as_dict() for s in self.settings],
        }
