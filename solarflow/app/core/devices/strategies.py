"""Strategien: aus PV-Überschuss sichere Geräteaktionen ableiten.

Jede Strategie ist eine **reine Funktion** von :class:`DeviceContext` zu
:class:`DeviceAssessment`. Sie kennt nur Rollen, Werte und Schwellen – kein
Home Assistant, keine Zeit. Dadurch ist sie vollständig testbar und die
Ausführung bleibt beim zentralen Sicherheits-Gate.

Die zurückgegebenen Aktionen sind *Vorschläge*. Ob sie ausgeführt werden,
entscheidet ausschließlich das Gate (Modus, Not-Aus, Datenqualität).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Action, Reading
from ._model import Device
from ._spec import DeviceTypeSpec, RoleKind


@dataclass(slots=True)
class DeviceContext:
    """Alles, was eine Strategie braucht – bereits eingelesen."""

    device: Device
    spec: DeviceTypeSpec
    feed_in_w: float | None
    surplus_ok: bool
    values: dict[str, Reading] = field(default_factory=dict)  # role_key -> Reading
    states: dict[str, str] = field(default_factory=dict)  # role_key -> Zustand
    now: float = 0.0
    runtime_s: float = 0.0
    grid_import_w: float | None = None


@dataclass(slots=True)
class DeviceAssessment:
    """Ergebnis der Bewertung eines Geräts für einen Zyklus."""

    device_id: str
    name: str
    type_id: str
    icon: str
    enabled: bool
    active: bool = False
    state: str = "idle"  # idle | charging | heating | holding | ready | blocked
    reason_de: str = ""
    reason_en: str = ""
    actions: list[Action] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    emoji: str = "🧩"
    accent: str = "violet"

    def as_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "type_id": self.type_id,
            "icon": self.icon,
            "emoji": self.emoji,
            "accent": self.accent,
            "enabled": self.enabled,
            "active": self.active,
            "state": self.state,
            "reason_de": self.reason_de,
            "reason_en": self.reason_en,
            "details": self.details,
        }


# ---------------------------------------------------------------------- #
# Hilfen
# ---------------------------------------------------------------------- #
def _num(ctx: DeviceContext, role: str) -> float | None:
    r = ctx.values.get(role)
    return r.value if r and r.is_number else None


def _setting(ctx: DeviceContext, key: str, fallback: float) -> float:
    if key in ctx.device.settings:
        try:
            return float(ctx.device.settings[key])
        except (TypeError, ValueError):
            return fallback
    for s in ctx.spec.settings:
        if s.key == key:
            return float(s.default)
    return fallback


def _write_action(entity_id: str, target: float, *, why: str) -> Action:
    """Wählt Dienst und Feld passend zur Domäne."""
    domain = entity_id.split(".")[0]
    if domain == "water_heater":
        return Action(
            entity_id=entity_id,
            service="water_heater.set_temperature",
            data={"temperature": target},
            why=why,
        )
    if domain == "climate":
        return Action(entity_id=entity_id, service="climate.set_temperature", data={"temperature": target}, why=why)
    return Action(entity_id=entity_id, service="number.set_value", data={"value": target}, why=why)


def _switch_state(ctx: DeviceContext, role: str) -> str | None:
    return ctx.states.get(role)


# ---------------------------------------------------------------------- #
# Strategien
# ---------------------------------------------------------------------- #
def _assess_surplus_switch(ctx: DeviceContext) -> DeviceAssessment:
    """Ein/Aus-Gerät (Wallbox, Poolpumpe, Heizstab, Steckdose, EV)."""
    d = ctx.device
    sw = d.roles.get("switch")
    a = DeviceAssessment(
        device_id=d.id, name=d.name, type_id=d.type_id, icon=ctx.spec.icon, enabled=d.enabled
    )
    if not sw:
        a.state = "blocked"
        a.reason_de = "Kein Schalter zugeordnet."
        a.reason_en = "No switch assigned."
        return a

    on = _switch_state(ctx, "switch") == "on"
    a.active = on
    power = _num(ctx, "power")
    soc = _num(ctx, "soc")
    if power is not None:
        a.details["power_w"] = round(power)
    if soc is not None:
        a.details["soc"] = round(soc)

    on_w = _setting(ctx, "on_w", 4200.0)
    off_w = _setting(ctx, "off_w", 2000.0)
    min_on_min = _setting(ctx, "min_on_min", 5.0)
    target_soc = _setting(ctx, "target_soc", 0.0)

    if ctx.feed_in_w is None or not ctx.surplus_ok:
        a.state = "blocked"
        a.reason_de = "Keine gültigen Daten – keine Schaltung."
        a.reason_en = "No valid data – not switching."
        return a

    feed = ctx.feed_in_w
    a.details["feed_in_w"] = round(feed)

    # SOC-Grenzen (falls ein Ladestand vorhanden ist).
    if soc is not None and target_soc > 0 and soc >= target_soc:
        if on:
            a.state = "holding"
            a.reason_de = f"Ladestand {soc:.0f} % erreicht – halten."
            a.reason_en = f"State of charge {soc:.0f} % reached – holding."
            return a
        a.state = "ready"
        a.reason_de = f"Ladestand {soc:.0f} % – Ziel erreicht."
        a.reason_en = f"State of charge {soc:.0f} % – target reached."
        return a

    if not on:
        if feed >= on_w:
            a.state = "charging"
            a.reason_de = f"Überschuss {feed:.0f} W ≥ {on_w:.0f} W – einschalten."
            a.reason_en = f"Surplus {feed:.0f} W ≥ {on_w:.0f} W – switch on."
            a.actions.append(Action(entity_id=sw, service="switch.turn_on", data={}, why="PV-Überschuss."))
        else:
            a.state = "idle"
            a.reason_de = f"Überschuss {feed:.0f} W < {on_w:.0f} W – warten."
            a.reason_en = f"Surplus {feed:.0f} W < {on_w:.0f} W – waiting."
        return a

    # Gerät ist an.
    if feed <= off_w:
        if ctx.runtime_s >= min_on_min * 60.0:
            a.state = "idle"
            a.reason_de = f"Überschuss {feed:.0f} W ≤ {off_w:.0f} W – ausschalten."
            a.reason_en = f"Surplus {feed:.0f} W ≤ {off_w:.0f} W – switch off."
            a.actions.append(Action(entity_id=sw, service="switch.turn_off", data={}, why="Kein Überschuss mehr."))
        else:
            rest = min_on_min * 60.0 - ctx.runtime_s
            a.state = "holding"
            a.reason_de = f"Mindestlaufzeit läuft noch ({rest / 60:.0f} min)."
            a.reason_en = f"Minimum runtime still running ({rest / 60:.0f} min)."
        return a

    a.state = "charging"
    a.reason_de = f"Lädt mit Überschuss ({feed:.0f} W)."
    a.reason_en = f"Charging on surplus ({feed:.0f} W)."
    return a


def _assess_thermal_boost(ctx: DeviceContext) -> DeviceAssessment:
    """Wärmeerzeugung mit PV-Überschuss (Wärmepumpe, Warmwasser, Heizstab)."""
    d = ctx.device
    sp = d.roles.get("setpoint") or d.roles.get("climate")
    a = DeviceAssessment(
        device_id=d.id, name=d.name, type_id=d.type_id, icon=ctx.spec.icon, enabled=d.enabled
    )
    if not sp:
        a.state = "blocked"
        a.reason_de = "Kein Sollwert zugeordnet."
        a.reason_en = "No setpoint assigned."
        return a

    boost = _setting(ctx, "boost_temp", 60.0)
    normal = _setting(ctx, "normal_temp", 52.0)
    hysteresis = _setting(ctx, "hysteresis_c", 2.0)
    on_w = _setting(ctx, "on_w", 1800.0)
    off_w = _setting(ctx, "off_w", 900.0)

    storage = _num(ctx, "storage")
    current = _num(ctx, "setpoint") if "setpoint" in d.roles else None
    if storage is not None:
        a.details["storage_temp"] = round(storage, 1)
    if current is not None:
        a.details["setpoint"] = round(current, 1)
    a.details["boost_temp"] = boost
    a.details["normal_temp"] = normal

    if ctx.feed_in_w is None or not ctx.surplus_ok:
        a.state = "blocked"
        a.reason_de = "Keine gültigen Daten – sicherer Sollwert Normal."
        a.reason_en = "No valid data – safe setpoint Normal."
        a.details["target_temp"] = normal
        return a

    feed = ctx.feed_in_w
    a.details["feed_in_w"] = round(feed)
    need = storage is None or storage < (boost - hysteresis)
    currently_boosting = current is not None and abs(current - boost) < 0.6
    threshold = off_w if currently_boosting else on_w
    want_boost = bool(need and feed >= threshold)

    target = boost if want_boost else normal
    a.details["target_temp"] = target
    a.active = want_boost

    if want_boost:
        a.state = "heating"
        a.reason_de = f"Überschuss {feed:.0f} W – auf {target:.0f} °C aufheizen."
        a.reason_en = f"Surplus {feed:.0f} W – heat to {target:.0f} °C."
    else:
        a.state = "idle"
        if storage is not None and not need:
            a.reason_de = f"Speicher warm genug ({storage:.1f} °C) – Normal {target:.0f} °C."
            a.reason_en = f"Storage warm enough ({storage:.1f} °C) – normal {target:.0f} °C."
        else:
            a.reason_de = f"Überschuss {feed:.0f} W reicht nicht – Normal {target:.0f} °C."
            a.reason_en = f"Surplus {feed:.0f} W not enough – normal {target:.0f} °C."

    # Selbstheilung: schreiben, wenn der Sollwert abweicht.
    if current is None or abs(current - target) > 0.6:
        why = "PV-Überschuss." if want_boost else "Zurück auf Normal."
        a.actions.append(_write_action(sp, target, why=why))
    return a


def _assess_battery_reserve(ctx: DeviceContext) -> DeviceAssessment:
    """PV-Speicher: nur beobachten und beraten (schreibt nichts)."""
    d = ctx.device
    a = DeviceAssessment(
        device_id=d.id, name=d.name, type_id=d.type_id, icon=ctx.spec.icon, enabled=d.enabled
    )
    soc = _num(ctx, "soc")
    power = _num(ctx, "power")
    min_soc = _setting(ctx, "min_soc", 20.0)
    reserve_soc = _setting(ctx, "reserve_soc", 30.0)
    if soc is not None:
        a.details["soc"] = round(soc)
    if power is not None:
        a.details["power_w"] = round(power)
    a.details["min_soc"] = min_soc
    a.active = soc is not None and soc < reserve_soc
    if soc is None:
        a.state = "blocked"
        a.reason_de = "Kein Ladestand verfügbar."
        a.reason_en = "No state of charge available."
    elif soc < reserve_soc:
        a.state = "holding"
        a.reason_de = f"Ladestand {soc:.0f} % – Reserve halten, Speicher schonen."
        a.reason_en = f"State of charge {soc:.0f} % – keep reserve."
    else:
        a.state = "ready"
        a.reason_de = f"Ladestand {soc:.0f} % – Speicher frei für Überschuss."
        a.reason_en = f"State of charge {soc:.0f} % – battery free for surplus."
    return a


def _assess_climate_boost(ctx: DeviceContext) -> DeviceAssessment:
    """Klimagerät: nur beraten (Vorheizen/Vorkühlen bei Überschuss)."""
    d = ctx.device
    a = DeviceAssessment(
        device_id=d.id, name=d.name, type_id=d.type_id, icon=ctx.spec.icon, enabled=d.enabled
    )
    shift = _setting(ctx, "shift_c", 2.0)
    on_w = _setting(ctx, "on_w", 2500.0)
    if ctx.feed_in_w is None or not ctx.surplus_ok:
        a.state = "blocked"
        a.reason_de = "Keine gültigen Daten – kein Vorschlag."
        a.reason_en = "No valid data – no suggestion."
        return a
    feed = ctx.feed_in_w
    a.details["feed_in_w"] = round(feed)
    a.details["shift_c"] = shift
    if feed >= on_w:
        a.state = "ready"
        a.active = True
        a.reason_de = f"Überschuss {feed:.0f} W – um {shift:.0f} °C vorheizen möglich (nur Vorschlag)."
        a.reason_en = f"Surplus {feed:.0f} W – pre-heat by {shift:.0f} °C possible (suggestion only)."
    else:
        a.state = "idle"
        a.reason_de = f"Überschuss {feed:.0f} W – kein Vorheizen nötig."
        a.reason_en = f"Surplus {feed:.0f} W – no pre-heating needed."
    return a


STRATEGIES = {
    "surplus_switch": _assess_surplus_switch,
    "ev_charge": _assess_surplus_switch,
    "thermal_boost": _assess_thermal_boost,
    "battery_reserve": _assess_battery_reserve,
    "climate_boost": _assess_climate_boost,
}


def assess(ctx: DeviceContext) -> DeviceAssessment:
    """Bewertet ein Gerät mit seiner Strategie."""
    fn = STRATEGIES.get(ctx.spec.strategy, _assess_surplus_switch)
    a = fn(ctx)
    a.emoji = ctx.device.emoji or ctx.spec.emoji
    a.accent = ctx.spec.accent
    return a


def role_kind_of(spec: DeviceTypeSpec, key: str) -> RoleKind | None:
    r = spec.role(key)
    return r.kind if r else None
