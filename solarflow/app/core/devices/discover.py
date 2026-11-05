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


@dataclass(slots=True)
class DetectedDevice:
    """Ein automatisch erkanntes Gerät (noch nicht angelegt)."""

    type_id: str
    name: str
    confidence: float
    roles: dict[str, str]
    matched: tuple[str, ...]  # welche Pflichtrollen belegt sind

    def as_dict(self) -> dict[str, object]:
        return {
            "type_id": self.type_id,
            "name": self.name,
            "confidence": round(self.confidence, 2),
            "roles": dict(self.roles),
            "matched": list(self.matched),
        }


#: Ab so vielen belegten Pflichtrollen gilt ein Typ als sicher erkannt.
_MIN_CONFIDENCE = 0.55


def detect_device_types(
    specs: tuple[DeviceTypeSpec, ...],
    entities: list[EntityInfo],
    *,
    name_hint: str = "",
) -> list[DetectedDevice]:
    """Prüft, welche Vorlagen zu einer Entitätsmenge passen.

    Für jede Vorlage werden die Rollen vorgeschlagen. Ein Vorschlag zählt nur,
    wenn **alle** Pflichtrollen belegt sind (sonst wäre das Gerät nicht
    schaltbar). Ergebnis ist nach Sicherheit sortiert – der beste Treffer
    zuerst. Reine Funktion, ohne Home Assistant testbar.
    """
    results: list[DetectedDevice] = []
    for spec in specs:
        suggestions = {s.key: s for s in suggest_roles(spec, entities, hint=name_hint)}
        roles: dict[str, str] = {}
        for key, sug in suggestions.items():
            if sug.entity_id:
                roles[key] = sug.entity_id
        required = spec.required_roles
        if required and not all(key in roles for key in required):
            continue
        # Ohne Pflichtrolle wären Einzeltreffer zu unscharf (z. B. jede
        # Temperatur-Zahl passt sonst zur Wärmepumpe). Daher mindestens zwei
        # belegte Rollen verlangen.
        if not required and len(roles) < 2:
            continue
        if not roles:
            continue
        # Sicherheit: Mittel der Rollen-Treffer, Pflichtrollen zählen doppelt.
        scores = [s.confidence for s in suggestions.values() if s.entity_id]
        req_scores = [suggestions[k].confidence for k in required if k in suggestions]
        pool = scores + req_scores
        confidence = sum(pool) / len(pool) if pool else 0.0
        if confidence < _MIN_CONFIDENCE:
            continue
        results.append(
            DetectedDevice(
                type_id=spec.type_id,
                name=name_hint or spec.name_de,
                confidence=confidence,
                roles=roles,
                matched=tuple(k for k in required if k in roles),
            )
        )
    results.sort(key=lambda d: -d.confidence)
    return results
