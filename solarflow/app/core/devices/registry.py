"""Geräte-Register: Entitäten zu echten HA-Geräten bündeln – rein.

Die HA-Schicht reicht Geräte-, Entitäts- und Bereichs-Register herein; hier
entstehen Gruppen (ein Eintrag je physischem Gerät). So bleibt die Zuordnung
ohne Home Assistant testbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DeviceEntity:
    """Eine Entität mit ihrer Gerätezuordnung."""

    entity_id: str
    domain: str
    name: str = ""
    device_id: str | None = None
    area_id: str | None = None
    device_class: str | None = None
    unit: str | None = None
    state: str | None = None
    disabled: bool = False
    hidden: bool = False


@dataclass(slots=True)
class DeviceGroup:
    """Ein physisches Gerät aus Home Assistant mit seinen Entitäten."""

    key: str
    name: str
    manufacturer: str = ""
    model: str = ""
    area: str = ""
    entities: list[DeviceEntity] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "area": self.area,
            "entity_count": len(self.entities),
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "domain": e.domain,
                    "name": e.name,
                    "device_class": e.device_class,
                    "unit": e.unit,
                    "state": e.state,
                }
                for e in self.entities
            ],
        }


def _label(entity: DeviceEntity) -> str:
    return f"{entity.entity_id} {entity.name}".lower()


def group_by_device(
    entities: list[DeviceEntity],
    devices: dict[str, dict[str, str]],
    areas: dict[str, str],
) -> list[DeviceGroup]:
    """Bündelt Entitäten je Gerät (und eine Restgruppe ohne Gerät)."""
    groups: dict[str, DeviceGroup] = {}
    orphan = DeviceGroup(key="__none__", name="Ohne Gerät")

    for e in entities:
        if e.disabled or e.hidden:
            continue
        if not e.device_id or e.device_id not in devices:
            orphan.entities.append(e)
            continue
        dev = devices[e.device_id]
        g = groups.get(e.device_id)
        if g is None:
            name = dev.get("name_by_user") or dev.get("name") or e.device_id
            area = areas.get(dev.get("area_id") or e.area_id or "", "")
            g = DeviceGroup(
                key=e.device_id,
                name=name,
                manufacturer=dev.get("manufacturer", ""),
                model=dev.get("model", ""),
                area=area,
            )
            groups[e.device_id] = g
        g.entities.append(e)

    out = sorted(groups.values(), key=lambda g: (g.name.lower(), g.key))
    if orphan.entities:
        orphan.entities.sort(key=_label)
        out.append(orphan)
    for g in out:
        g.entities.sort(key=lambda e: (e.domain, e.entity_id))
    return out
