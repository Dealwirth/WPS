"""Eine konkrete Geräte-Instanz (vom Nutzer angelegt).

Ein :class:`Device` verbindet eine Vorlage (:class:`DeviceTypeSpec`) mit
echten Home-Assistant-Entitäten und eigenen Schwellen. Es ist reine Daten –
die Bewertung übernimmt die jeweilige Strategie.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class Device:
    """Ein eingerichtetes Gerät."""

    type_id: str
    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    enabled: bool = True
    roles: dict[str, str] = field(default_factory=dict)  # role_key -> entity_id
    settings: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "name": self.name,
            "enabled": self.enabled,
            "roles": dict(self.roles),
            "settings": dict(self.settings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Device:
        roles = data.get("roles") or {}
        settings = data.get("settings") or {}
        return cls(
            type_id=str(data.get("type_id") or ""),
            name=str(data.get("name") or ""),
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            enabled=bool(data.get("enabled", True)),
            roles={str(k): str(v) for k, v in dict(roles).items() if v},
            settings={str(k): float(v) for k, v in dict(settings).items() if isinstance(v, (int, float))},
        )
