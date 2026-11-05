"""Zusammensetzung des Stores.

Die Reihenfolge in ``MODULE_SPECS`` ist zugleich die Anzeigereihenfolge.
Ein eigenes Modul wird hier mit zwei Zeilen registriert:

1. ``from .<kategorie>.<module_id> import SPEC as <NAME>_SPEC``
2. die Variable in das Tupel ``MODULE_SPECS`` einreihen

Ein Modul = eine Datei unter ``core/modules/<kategorie>/<module_id>.py``.
"""

from __future__ import annotations

from ._spec import ModuleSpec
from .base.core import SPEC as _CORE
from .devices.flexible_loads import SPEC as _FLEXIBLE_LOADS
from .devices.heating import SPEC as _HEATING
from .devices.thermal import SPEC as _THERMAL
from .devices.wallbox import SPEC as _WALLBOX
from .energy.goals import SPEC as _GOALS
from .energy.tariff import SPEC as _TARIFF
from .intelligence.forecast import SPEC as _FORECAST
from .safety.terminal import SPEC as _SAFETY

MODULE_SPECS: tuple[ModuleSpec, ...] = (
    _CORE,
    _THERMAL,
    _WALLBOX,
    _HEATING,
    _FLEXIBLE_LOADS,
    _TARIFF,
    _GOALS,
    _FORECAST,
    _SAFETY,
)

MODULES_BY_ID: dict[str, ModuleSpec] = {spec.module_id: spec for spec in MODULE_SPECS}
CORE_MODULE = MODULES_BY_ID["core"]
CORE_MODULE_ID = CORE_MODULE.module_id


def default_enabled_modules() -> set[str]:
    """Module, die bei frischer Installation aktiv sind."""
    return {spec.module_id for spec in MODULE_SPECS if spec.default_enabled}


def resolve_dependencies(enabled: set[str], *, module_id: str) -> set[str]:
    """Liefert die Menge der Module, die mit module_id zusammen aktiv sein müssen."""
    result = {module_id}
    changed = True
    while changed:
        changed = False
        for current in tuple(result):
            spec = MODULES_BY_ID.get(current)
            if spec is None:
                continue
            for dep in spec.requires:
                if dep not in result:
                    result.add(dep)
                    changed = True
    return {item for item in result if item in MODULES_BY_ID}


def dependents_of(module_id: str, enabled: set[str]) -> set[str]:
    """Aktive Module, die von module_id abhängen."""
    return {spec.module_id for spec in MODULE_SPECS if module_id in spec.requires and spec.module_id in enabled}


def store_cards(enabled: set[str] | None = None) -> list[dict[str, object]]:
    """Alle Store-Karten mit ihrem aktuellen Zustand."""
    active = enabled or default_enabled_modules()
    return [spec.as_dict(enabled=spec.module_id in active) for spec in MODULE_SPECS]
