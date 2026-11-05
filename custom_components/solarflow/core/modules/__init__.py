"""Interner Modul-Store von SolarFlow.

Stabile öffentliche Schnittstelle – die HA-Schicht und die Oberfläche greifen
nur hierauf zu, nie direkt auf einzelne Moduldateien.
"""

from __future__ import annotations

from ._registry import (
    CORE_MODULE,
    CORE_MODULE_ID,
    MODULE_SPECS,
    MODULES_BY_ID,
    default_enabled_modules,
    dependents_of,
    resolve_dependencies,
    store_cards,
)
from ._spec import ModuleCategory, ModuleSpec

__all__ = [
    "CORE_MODULE",
    "CORE_MODULE_ID",
    "MODULES_BY_ID",
    "MODULE_SPECS",
    "ModuleCategory",
    "ModuleSpec",
    "default_enabled_modules",
    "dependents_of",
    "resolve_dependencies",
    "store_cards",
]
