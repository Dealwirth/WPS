"""Reine Datentypen des Kerns (kein Home-Assistant-Import).

Diese Modelle beschreiben, *was* SolarFlow weiß und *was* es tun möchte.
Sie enthalten bewusst keine Logik und keine HA-Abhängigkeit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Mode(StrEnum):
    """Betriebsart der Automatik."""

    OFF = "off"  # keine Automatik, nur Schutz und Anzeige
    SHADOW = "shadow"  # beobachten und vorschlagen, niemals schalten
    ACTIVE = "active"  # Automatik scharf, Grenzen bleiben aktiv


class PlantState(StrEnum):
    """Zustand der Anlage (Warmwasser)."""

    NORMAL = "normal"  # Grundtemperatur, Netzbezug möglich
    BOOST = "boost"  # Sonne wird genutzt, höhere Temperatur


@dataclass(slots=True)
class Reading:
    """Ein einzelner Messwert mit Gültigkeitsinformationen."""

    entity_id: str
    value: float | None
    unit: str | None = None
    age_s: float | None = None
    available: bool = True
    raw: str | None = None

    @property
    def is_number(self) -> bool:
        return self.value is not None


@dataclass(slots=True)
class Settings:
    """Alle regelbaren Werte. Standardwerte sind konservativ."""

    mode: Mode = Mode.SHADOW
    feed_in_on_w: float = 1800.0
    feed_in_off_w: float = 900.0
    min_runtime_min: float = 15.0
    min_pause_min: float = 10.0
    ww_boost_temp: float = 60.0
    ww_normal_temp: float = 52.0
    ww_min_temp: float = 45.0
    ww_hygiene_min_temp: float = 50.0
    sensor_max_age_s: float = 300.0
    max_grid_import_w: float = 11000.0
    verify_writes: bool = True
    holiday: bool = False
    force_boost: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": str(self.mode),
            "feed_in_on_w": self.feed_in_on_w,
            "feed_in_off_w": self.feed_in_off_w,
            "min_runtime_min": self.min_runtime_min,
            "min_pause_min": self.min_pause_min,
            "ww_boost_temp": self.ww_boost_temp,
            "ww_normal_temp": self.ww_normal_temp,
            "ww_min_temp": self.ww_min_temp,
            "ww_hygiene_min_temp": self.ww_hygiene_min_temp,
            "sensor_max_age_s": self.sensor_max_age_s,
            "max_grid_import_w": self.max_grid_import_w,
            "verify_writes": self.verify_writes,
            "holiday": self.holiday,
            "force_boost": self.force_boost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> Settings:
        """Baut Settings aus einem gespeicherten Dict, ohne zu crashen."""
        s = cls()
        if not data:
            return s
        for key, value in data.items():
            if not hasattr(s, key):
                continue
            current = getattr(s, key)
            try:
                if isinstance(current, bool):
                    setattr(s, key, bool(value))
                elif isinstance(current, Mode):
                    setattr(s, key, Mode(str(value)))
                elif isinstance(current, (int, float)):
                    setattr(s, key, float(value))  # type: ignore[arg-type]
                else:
                    setattr(s, key, value)
            except (ValueError, TypeError):
                continue
        return s


@dataclass(slots=True)
class Action:
    """Eine geplante Schreibaktion (noch nicht ausgeführt)."""

    entity_id: str
    service: str  # z. B. "water_heater.set_temperature"
    data: dict[str, object] = field(default_factory=dict)
    why: str = ""


@dataclass(slots=True)
class LayerStatus:
    """Zustand einer Schutz-Ebene für die Oberfläche."""

    idx: int
    key: str
    name_de: str
    name_en: str
    status: str  # ok | warn | blocked | active
    detail_de: str = ""
    detail_en: str = ""


@dataclass(slots=True)
class Decision:
    """Ergebnis eines Regelzyklus."""

    state: PlantState
    actions: list[Action] = field(default_factory=list)
    blocked: bool = False
    reason_de: str = ""
    reason_en: str = ""
    steps: list[tuple[str, str]] = field(default_factory=list)  # (status, text)
