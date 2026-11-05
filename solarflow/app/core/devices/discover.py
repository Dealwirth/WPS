"""Rollenbezogene Geräteerkennung – reine Funktionen.

Reicht man Domänen, Namen und Attribute herein, entsteht pro Rolle ein
Vorschlag. So bleibt die Erkennung ohne Home Assistant testbar und lässt
sich gegen echte Entity-Listen prüfen.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..discovery import EntityInfo
from ._spec import DeviceTypeSpec, RoleKind, RoleSpec


@dataclass(slots=True)
class RoleSuggestion:
    """Ein Vorschlag für eine Rolle eines Geräts."""

    key: str
    entity_id: str | None = None
    confidence: float = 0.0
    candidates: list[str] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "entity_id": self.entity_id,
            "confidence": round(self.confidence, 2),
            "candidates": self.candidates or [],
        }


def _score(info: EntityInfo, role: RoleSpec, hint: str) -> float:
    hay = f"{info.entity_id} {info.name} {hint}".lower()
    hits = sum(0.2 for k in role.keywords if k in hay)
    unit = (info.unit or "").lower()
    if role.kind == RoleKind.POWER and unit in ("w", "kw"):
        hits += 0.2
    if role.kind == RoleKind.SENSOR and "%" in unit and "soc" in role.keywords:
        hits += 0.2
    # Die Domäne allein genügt nicht – sonst passt jedes Gerät zu jeder Rolle.
    if hits == 0:
        return 0.0
    if info.domain in role.domains:
        hits += 0.4
    return min(hits, 1.0)


def suggest_roles(spec: DeviceTypeSpec, entities: list[EntityInfo], *, hint: str = "") -> list[RoleSuggestion]:
    """Erzeugt je Rolle der Vorlage einen Vorschlag (ggf. leer)."""
    out: list[RoleSuggestion] = []
    for role in spec.roles:
        scored: list[tuple[str, float]] = []
        for e in entities:
            sc = _score(e, role, hint)
            if sc > 0:
                scored.append((e.entity_id, sc))
        scored.sort(key=lambda x: -x[1])
        if scored:
            out.append(
                RoleSuggestion(role.key, scored[0][0], scored[0][1], [e for e, _ in scored[:5]])
            )
        else:
            out.append(RoleSuggestion(role.key, None, 0.0, []))
    return out
