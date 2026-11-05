"""Geräte-Store von SolarFlow.

Öffentliche Schnittstelle: Katalog der Vorlagen, Anlegen/Prüfen von Geräten
und die rollenbezogene Erkennung. HA-Schicht und Oberfläche greifen nur
hierauf zu.
"""

from __future__ import annotations

from ._model import Device
from ._spec import DeviceCategory, DeviceTypeSpec, RoleKind, RoleSpec, SettingSpec
from .catalog import DEVICE_TYPES
from .discover import DetectedDevice, detect_device_types, suggest_roles
from .registry import DeviceEntity, DeviceGroup, group_by_device
from .strategies import DeviceAssessment, DeviceContext, assess

TYPES_BY_ID: dict[str, DeviceTypeSpec] = {t.type_id: t for t in DEVICE_TYPES}


def missing_required_roles(device: Device) -> list[str]:
    """Rollen, die zwingend eine Entität brauchen, aber keine haben."""
    spec = TYPES_BY_ID.get(device.type_id)
    if spec is None:
        return []
    return [key for key in spec.required_roles if not device.roles.get(key)]


def type_cards() -> list[dict[str, object]]:
    """Alle Vorlagen als Store-Karten."""
    return [t.as_dict() for t in DEVICE_TYPES]


def make_device(
    type_id: str,
    *,
    name: str = "",
    roles: dict[str, str] | None = None,
    settings: dict[str, float] | None = None,
    emoji: str = "",
) -> Device | None:
    """Legt ein Gerät aus einer Vorlage an (mit sicheren Standardwerten)."""
    spec = TYPES_BY_ID.get(type_id)
    if spec is None:
        return None
    merged = spec.default_settings()
    for k, v in (settings or {}).items():
        if k in merged:
            try:
                merged[k] = float(v)
            except (TypeError, ValueError):
                continue
    return Device(
        type_id=type_id,
        name=name or spec.name_de,
        roles={str(k): str(v) for k, v in (roles or {}).items() if v},
        settings=merged,
        emoji=emoji or "",
    )


def clamp_device_settings(device: Device) -> list[str]:
    """Klemmt Geräte-Einstellungen auf die Vorlagen-Grenzen."""
    spec = TYPES_BY_ID.get(device.type_id)
    if spec is None:
        return []
    notes: list[str] = []
    for s in spec.settings:
        if s.key not in device.settings:
            device.settings[s.key] = float(s.default)
            continue
        val = float(device.settings[s.key])
        if val < s.minimum or val > s.maximum:
            val = max(s.minimum, min(s.maximum, val))
            notes.append(f"{s.label_de}: auf {val:g} begrenzt.")
        device.settings[s.key] = val
    # Ausschaltschwelle muss unter der Einschaltschwelle liegen.
    if "on_w" in device.settings and "off_w" in device.settings and device.settings["off_w"] >= device.settings["on_w"]:
        device.settings["off_w"] = max(0.0, device.settings["on_w"] - 100.0)
        notes.append("Ausschaltschwelle lag über Einschaltschwelle – angepasst.")
    if (
        "normal_temp" in device.settings
        and "boost_temp" in device.settings
        and device.settings["boost_temp"] < device.settings["normal_temp"]
    ):
        device.settings["boost_temp"] = device.settings["normal_temp"]
        notes.append("Boost-Temperatur lag unter Normal – angehoben.")
    return notes


def device_view(device: Device) -> dict[str, object]:
    """Gerät inkl. Vorlagen-Daten für die Oberfläche."""
    spec = TYPES_BY_ID.get(device.type_id)
    data = device.as_dict()
    if spec is not None:
        data["spec"] = spec.as_dict()
        data["icon"] = spec.icon
        data["emoji"] = device.emoji or spec.emoji
        data["accent"] = spec.accent
        data["name_de"] = spec.name_de
        data["name_en"] = spec.name_en
    return data


def device_emoji(device: Device) -> str:
    """Bild (Emoji) eines Geräts – eigene Wahl vor Vorlagen-Bild."""
    spec = TYPES_BY_ID.get(device.type_id)
    return device.emoji or (spec.emoji if spec else "🧩")


def device_accent(device: Device) -> str:
    """Akzentfarbe eines Geräts."""
    spec = TYPES_BY_ID.get(device.type_id)
    return spec.accent if spec else "violet"


__all__ = [
    "DEVICE_TYPES",
    "TYPES_BY_ID",
    "DetectedDevice",
    "Device",
    "DeviceAssessment",
    "DeviceCategory",
    "DeviceContext",
    "DeviceEntity",
    "DeviceGroup",
    "DeviceTypeSpec",
    "RoleKind",
    "RoleSpec",
    "SettingSpec",
    "assess",
    "clamp_device_settings",
    "detect_device_types",
    "device_accent",
    "device_emoji",
    "device_view",
    "group_by_device",
    "make_device",
    "missing_required_roles",
    "suggest_roles",
    "type_cards",
]
