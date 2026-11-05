"""Die Schutz-Ebenen (Fail-safe) und das zentrale Ausführungs-Gate.

Zehn Ebenen prüfen jeden Zyklus. Fällt eine aus, greift die nächste. Kein
Weg führt an :func:`gate` vorbei – jede Schaltung muss es passieren.

Ebenen
------
1. Sensor-Plausibilität (Bereich)
2. Daten-Alter
3. Sensor-Ausfall / fehlender Wert
4. Hysterese & Flankenschutz (Info, keine Blockade)
5. Harte Temperaturgrenzen
6. Gerätegrenzen (Schreibwerte klemmen)
7. Schreib-Verifikation (Rücklesen)
8. Wiederhol- & Not-Fallback
9. Selbstheilung
10. Not-Aus & Watchdog
"""

from __future__ import annotations

from dataclasses import dataclass

from .limits import (
    WW_TEMP_ABS_MAX,
    WW_TEMP_ABS_MIN,
    validate_setpoint,
)
from .models import Action, LayerStatus, Mode, Reading, Settings
from .quality import (
    POWER_MAX_W,
    POWER_MIN_W,
    check_freshness,
    check_jump,
    check_value,
)

LAYER_DEFS: tuple[tuple[str, str, str], ...] = (
    ("plausibility", "Sensor-Plausibilität", "Sensor plausibility"),
    ("freshness", "Daten-Alter", "Data age"),
    ("sensor_fail", "Sensor-Ausfall", "Sensor failure"),
    ("hysteresis", "Hysterese & Flankenschutz", "Hysteresis & edge guard"),
    ("temp_bounds", "Harte Temperaturgrenzen", "Hard temperature bounds"),
    ("device_bounds", "Gerätegrenzen", "Device bounds"),
    ("write_verify", "Schreib-Verifikation", "Write verification"),
    ("retry_fallback", "Wiederhol- & Not-Fallback", "Retry & fallback"),
    ("self_heal", "Selbstheilung", "Self-healing"),
    ("emergency", "Not-Aus & Watchdog", "Emergency stop & watchdog"),
)


@dataclass(slots=True)
class SafetyContext:
    """Alle Eingaben, die die Schutz-Ebenen brauchen."""

    feed_in: Reading
    settings: Settings
    now: float
    storage: Reading | None = None
    grid_import: Reading | None = None
    previous_feed_in: float | None = None
    device_min: float = WW_TEMP_ABS_MIN
    device_max: float = WW_TEMP_ABS_MAX
    emergency_stop: bool = False
    mode: Mode = Mode.SHADOW


def evaluate_layers(ctx: SafetyContext) -> list[LayerStatus]:
    """Bewertet alle zehn Ebenen und gibt ihren Zustand zurück."""
    out: list[LayerStatus] = []
    s = ctx.settings

    # 1) Plausibilität (Bereich + Sprung)
    ok_range, d_de, d_en = check_value(ctx.feed_in.value, lo=POWER_MIN_W, hi=POWER_MAX_W)
    ok_jump, j_de, _j_en = check_jump(ctx.feed_in.value, ctx.previous_feed_in)
    st1 = "ok" if (ok_range and ok_jump) else "warn"
    out.append(
        LayerStatus(
            1,
            "plausibility",
            LAYER_DEFS[0][1],
            LAYER_DEFS[0][2],
            st1,
            d_de + (" · " + j_de if not ok_jump else ""),
            d_en,
        )
    )

    # 2) Frische
    ok_fresh, f_de, f_en = check_freshness(ctx.feed_in, s.sensor_max_age_s)
    out.append(
        LayerStatus(2, "freshness", LAYER_DEFS[1][1], LAYER_DEFS[1][2], "ok" if ok_fresh else "blocked", f_de, f_en)
    )

    # 3) Sensor-Ausfall
    fail = not ok_fresh or not ok_range
    out.append(
        LayerStatus(
            3,
            "sensor_fail",
            LAYER_DEFS[2][1],
            LAYER_DEFS[2][2],
            "blocked" if fail else "ok",
            "Ausfall – sicherer Zustand Normal" if fail else "Sensor liefert Werte",
            "failure – safe state Normal" if fail else "sensor reports",
        )
    )

    # 4) Hysterese (nur Info)
    out.append(
        LayerStatus(
            4,
            "hysteresis",
            LAYER_DEFS[3][1],
            LAYER_DEFS[3][2],
            "active",
            f"Ein {s.feed_in_on_w:.0f} W / Aus {s.feed_in_off_w:.0f} W, "
            f"Lauf {s.min_runtime_min:.0f} min, Pause {s.min_pause_min:.0f} min",
            f"on {s.feed_in_on_w:.0f}W / off {s.feed_in_off_w:.0f}W, "
            f"run {s.min_runtime_min:.0f}min, pause {s.min_pause_min:.0f}min",
        )
    )

    # 5) Temperaturgrenzen
    b_ok = WW_TEMP_ABS_MIN <= s.ww_normal_temp <= WW_TEMP_ABS_MAX and s.ww_boost_temp <= WW_TEMP_ABS_MAX
    out.append(
        LayerStatus(
            5,
            "temp_bounds",
            LAYER_DEFS[4][1],
            LAYER_DEFS[4][2],
            "ok" if b_ok else "warn",
            f"Boost {s.ww_boost_temp:.0f} °C ≤ Max {WW_TEMP_ABS_MAX:.0f} °C"
            if b_ok
            else "Grenzen verletzt – werden geklemmt",
            "within limits" if b_ok else "violated – will be clamped",
        )
    )

    # 6) Gerätegrenzen
    out.append(
        LayerStatus(
            6,
            "device_bounds",
            LAYER_DEFS[5][1],
            LAYER_DEFS[5][2],
            "active",
            f"Gerät erlaubt {ctx.device_min:.0f}–{ctx.device_max:.0f} °C",
            f"device allows {ctx.device_min:.0f}–{ctx.device_max:.0f}°C",
        )
    )

    # 7) Schreib-Verifikation
    out.append(
        LayerStatus(
            7,
            "write_verify",
            LAYER_DEFS[6][1],
            LAYER_DEFS[6][2],
            "active" if s.verify_writes else "warn",
            "Nach dem Setzen wird zurückgelesen" if s.verify_writes else "deaktiviert",
            "value is read back" if s.verify_writes else "disabled",
        )
    )

    # 8) Wiederhol-/Not-Fallback
    out.append(
        LayerStatus(
            8,
            "retry_fallback",
            LAYER_DEFS[7][1],
            LAYER_DEFS[7][2],
            "active",
            "Fehlschlag → kein Dauerfeuer, zurück auf Normal",
            "failure → no hammering, back to Normal",
        )
    )

    # 9) Selbstheilung
    out.append(
        LayerStatus(
            9,
            "self_heal",
            LAYER_DEFS[8][1],
            LAYER_DEFS[8][2],
            "active",
            "Alter guter Zustand wird wiederhergestellt",
            "restores last good state",
        )
    )

    # 10) Not-Aus
    out.append(
        LayerStatus(
            10,
            "emergency",
            LAYER_DEFS[9][1],
            LAYER_DEFS[9][2],
            "blocked" if ctx.emergency_stop else "ok",
            "AKTIV – alles gesperrt" if ctx.emergency_stop else "bereit",
            "ACTIVE – all locked" if ctx.emergency_stop else "armed",
        )
    )

    return out


def blocking_reasons(ctx: SafetyContext) -> list[tuple[str, str]]:
    """Liste der Gründe, die eine Schaltung verhindern (key, text_de)."""
    reasons: list[tuple[str, str]] = []
    if ctx.mode == Mode.OFF:
        reasons.append(("mode_off", "Betriebsart Aus – es wird nicht geschaltet."))
    if ctx.mode == Mode.SHADOW:
        reasons.append(("mode_shadow", "Schatten-Modus – nur Vorschlag, keine Schaltung."))
    if ctx.emergency_stop:
        reasons.append(("emergency", "Not-Aus ist aktiv."))

    ok_fresh, f_de, _ = check_freshness(ctx.feed_in, ctx.settings.sensor_max_age_s)
    if not ok_fresh:
        reasons.append(("sensor", f"Messwert nicht brauchbar ({f_de})."))
    ok_range, r_de, _ = check_value(ctx.feed_in.value, lo=POWER_MIN_W, hi=POWER_MAX_W)
    if not ok_range:
        reasons.append(("range", f"Messwert unplausibel ({r_de})."))
    ok_jump, j_de, _ = check_jump(ctx.feed_in.value, ctx.previous_feed_in)
    if not ok_jump:
        reasons.append(("jump", f"Messwert springt unplausibel ({j_de})."))
    return reasons


def gate(actions: list[Action], ctx: SafetyContext) -> tuple[list[Action], list[str]]:
    """Das zentrale Gate: lässt nur sichere Aktionen durch.

    Jede Schreibaktion wird zusätzlich auf die Gerätegrenzen geklemmt.
    Returns: (erlaubte Aktionen, Gründe für Blockade)
    """
    reasons = [text for _, text in blocking_reasons(ctx)]
    if reasons:
        return [], reasons

    safe: list[Action] = []
    for a in actions:
        data = dict(a.data)
        if "temperature" in data and isinstance(data["temperature"], (int, float)):
            data["temperature"] = validate_setpoint(
                float(data["temperature"]),
                device_min=ctx.device_min,
                device_max=ctx.device_max,
            )
        if "value" in data and isinstance(data["value"], (int, float)):
            data["value"] = validate_setpoint(
                float(data["value"]),
                device_min=ctx.device_min,
                device_max=ctx.device_max,
            )
        safe.append(Action(a.entity_id, a.service, data, a.why))
    return safe, []
