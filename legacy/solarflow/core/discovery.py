"""Geräte- und Fähigkeitserkennung – als reine Funktionen.

Die HA-Schicht reicht Domänen, Namen und Attribute herein; hier entstehen
Vorschläge (``Suggestion``). So bleibt die Erkennung ohne HA testbar und
lässt sich gegen echte Entity-Listen prüfen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EntityInfo:
    """Minimalinformation über eine Entität für die Erkennung."""

    entity_id: str
    domain: str
    name: str = ""
    device_class: str | None = None
    unit: str | None = None
    state: str | None = None


@dataclass(slots=True)
class Suggestion:
    """Ein Erkennungsvorschlag für eine Rolle."""

    role: str
    label_de: str
    label_en: str
    entity_id: str | None = None
    confidence: float = 0.0
    note_de: str = ""
    note_en: str = ""
    candidates: list[str] = field(default_factory=list)


def _score(info: EntityInfo, keywords: tuple[str, ...], domains: tuple[str, ...]) -> float:
    score = 0.0
    if info.domain in domains:
        score += 0.4
    hay = (info.entity_id + " " + info.name).lower()
    for k in keywords:
        if k in hay:
            score += 0.2
    return min(score, 1.0)


def suggest(entities: list[EntityInfo]) -> list[Suggestion]:
    """Erzeugt Vorschläge für die typischen SolarFlow-Rollen."""
    out: list[Suggestion] = []

    def best(keywords: tuple[str, ...], domains: tuple[str, ...]) -> tuple[str | None, float, list[str]]:
        scored = []
        for e in entities:
            sc = _score(e, keywords, domains)
            if sc > 0:
                scored.append((e.entity_id, sc))
        scored.sort(key=lambda x: -x[1])
        if not scored:
            return None, 0.0, []
        return scored[0][0], scored[0][1], [e for e, _ in scored[:5]]

    # Einspeisung / Netz
    eid, conf, cand = best(("einspeis", "feed", "export", "grid_export", "netzeinspeisung"), ("sensor",))
    out.append(
        Suggestion(
            "feed_in",
            "Einspeisung ins Netz",
            "Grid feed-in",
            eid,
            conf,
            "Leistung, die ins Netz geht (PV-Überschuss).",
            "Power exported to the grid.",
            cand,
        )
    )

    eid, conf, cand = best(("pv_leistung", "pv power", "solar", "erzeugung", "generation"), ("sensor",))
    out.append(Suggestion("pv", "PV-Leistung", "PV power", eid, conf, "", "", cand))

    eid, conf, cand = best(("netzbezug", "import", "grid_import", "bezug"), ("sensor",))
    out.append(Suggestion("grid_import", "Netzbezug", "Grid import", eid, conf, "", "", cand))

    # Warmwasser
    eid, conf, cand = best(("warmwasser", "hot_water", "dhw", "ww"), ("water_heater",))
    out.append(
        Suggestion(
            "ww_water_heater",
            "Warmwasser",
            "Hot water",
            eid,
            conf,
            "Warmwasser-Kreis der Wärmepumpe.",
            "Heat-pump hot-water circuit.",
            cand,
        )
    )

    eid, conf, cand = best(("ww_temperatur", "ww_temp", "dhw_temperature"), ("number",))
    out.append(Suggestion("ww_temp_number", "WW-Solltemperatur", "DHW setpoint", eid, conf, "", "", cand))

    eid, conf, cand = best(("speichertemperatur", "ww_speicher", "dhw_storage", "tank"), ("sensor",))
    out.append(
        Suggestion("ww_storage_sensor", "WW-Speichertemperatur", "DHW storage temperature", eid, conf, "", "", cand)
    )

    eid, conf, cand = best(("hysterese", "hysteresis"), ("number",))
    out.append(Suggestion("ww_hysteresis_number", "WW-Hysterese", "DHW hysteresis", eid, conf, "", "", cand))

    # Heizung
    eid, conf, cand = best(("heizung", "heating", "climate"), ("climate",))
    out.append(Suggestion("heating_climate", "Heizung", "Heating", eid, conf, "", "", cand))

    # Wallbox / EV
    eid, conf, cand = best(
        ("wallbox", "wattpilot", "charger", "ladestation"), ("switch", "sensor", "select", "number", "button")
    )
    out.append(Suggestion("wallbox", "Wallbox", "Wallbox", eid, conf, "", "", cand))

    eid, conf, cand = best(("ioniq", "ev_", "fahrzeug", "vehicle", "car"), ("switch", "sensor", "number", "lock"))
    out.append(Suggestion("ev", "Fahrzeug", "Vehicle", eid, conf, "", "", cand))

    return out
