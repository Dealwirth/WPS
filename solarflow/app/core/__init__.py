"""HA-freier Rechenkern von SolarFlow.

Dieses Paket importiert **kein** Home Assistant. Dadurch lässt sich die
gesamte Entscheidungslogik ohne laufende HA-Installation testen – genau der
Pfad, der später Geräte schaltet, wird hier abgesichert.
"""

from __future__ import annotations

from . import devices
from .limits import clamp, validate_setpoint, validate_settings
from .models import (
    Action,
    Decision,
    LayerStatus,
    Mode,
    PlantState,
    Reading,
    Settings,
)
from .quality import check_freshness, check_value, reading_ok
from .safety import SafetyContext, evaluate_layers, gate

__all__ = [
    "Action",
    "Decision",
    "LayerStatus",
    "Mode",
    "PlantState",
    "Reading",
    "SafetyContext",
    "Settings",
    "check_freshness",
    "check_value",
    "clamp",
    "devices",
    "evaluate_layers",
    "gate",
    "reading_ok",
    "validate_setpoint",
    "validate_settings",
]
