"""Datenqualität: ist ein Messwert frisch und plausibel?

Diese Prüfungen sind die erste Verteidigungslinie. Ein unplausibler,
veralteter oder fehlender Wert führt **nie** zu einer Schaltung – SolarFlow
fällt dann in den sicheren Zustand ``NORMAL`` zurück.
"""

from __future__ import annotations

import math

from .models import Reading

#: Sinnvolle physikalische Grenzen (W). Werte außerhalb gelten als unplausibel.
POWER_MIN_W = -30000.0
POWER_MAX_W = 30000.0
#: Maximale Änderung zwischen zwei Messungen, die noch plausibel ist (W).
POWER_JUMP_MAX_W = 20000.0


def check_freshness(reading: Reading, max_age_s: float) -> tuple[bool, str, str]:
    """Prüft, ob ein Wert frisch genug ist.

    Returns: (ok, detail_de, detail_en)
    """
    if not reading.available:
        return False, "Sensor nicht verfügbar", "sensor unavailable"
    if not reading.is_number:
        return False, "kein gültiger Zahlenwert", "no valid number"
    if reading.age_s is None:
        return False, "Alter unbekannt", "age unknown"
    if reading.age_s > max_age_s:
        return (
            False,
            f"veraltet ({reading.age_s:.0f} s > {max_age_s:.0f} s)",
            f"stale ({reading.age_s:.0f}s > {max_age_s:.0f}s)",
        )
    return True, f"frisch ({reading.age_s:.0f} s)", f"fresh ({reading.age_s:.0f}s)"


def check_value(value: float | None, *, lo: float, hi: float) -> tuple[bool, str, str]:
    """Prüft, ob ein Zahlenwert im erlaubten Bereich liegt."""
    if value is None:
        return False, "kein Wert", "no value"
    if math.isnan(value):
        return False, "ungültig (NaN)", "invalid (NaN)"
    if value < lo or value > hi:
        return False, f"außerhalb {lo:.0f}…{hi:.0f}", f"outside {lo:.0f}…{hi:.0f}"
    return True, "im Bereich", "in range"


def check_jump(
    value: float | None, previous: float | None, max_jump: float = POWER_JUMP_MAX_W
) -> tuple[bool, str, str]:
    """Prüft, ob ein Wert gegenüber der letzten Messung plausibel ist.

    Ein riesiger Sprung kann ein Sensorfehler sein. Wir verwerfen ihn nicht
    sofort, markieren ihn aber – die Entscheidung trifft die Sicherheitsebene.
    """
    if value is None or previous is None:
        return True, "kein Vergleich", "no comparison"
    if abs(value - previous) > max_jump:
        return (
            False,
            f"großer Sprung ({abs(value - previous):.0f} W)",
            f"large jump ({abs(value - previous):.0f}W)",
        )
    return True, "plausibel", "plausible"


def reading_ok(reading: Reading, max_age_s: float) -> bool:
    """Kurzform: ist der Messwert brauchbar?"""
    ok, _, _ = check_freshness(reading, max_age_s)
    return ok and reading.is_number
