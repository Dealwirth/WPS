"""Harte Grenzen: was darf niemals überschritten werden?

Hier wird jeder Schreibwert auf die echten Gerätegrenzen geklemmt und jede
Einstellung auf vernünftige Werte geprüft. Grenzen sind der Schutz gegen
Tippfehler und gegen unerwartete Sensorwerte.
"""

from __future__ import annotations

from .models import Settings

#: Absolute Grenzen der Integration (unabhängig vom Gerät).
WW_TEMP_ABS_MIN = 10.0
WW_TEMP_ABS_MAX = 60.0
FEED_IN_ABS_MIN = 0.0
FEED_IN_ABS_MAX = 20000.0
TIME_ABS_MIN = 0.0
TIME_ABS_MAX = 720.0
AGE_ABS_MIN = 10.0
AGE_ABS_MAX = 3600.0
GRID_ABS_MIN = 1000.0
GRID_ABS_MAX = 60000.0


def clamp(value: float, lo: float, hi: float) -> float:
    """Begrenzt einen Wert sicher auf [lo, hi] (lo/hi werden getauscht falls nötig)."""
    if lo > hi:
        lo, hi = hi, lo
    return max(lo, min(hi, value))


def validate_setpoint(value: float, *, device_min: float, device_max: float) -> float:
    """Klemmt einen Sollwert auf die Schnittmenge aus Geräte- und Absolutgrenzen."""
    lo = max(device_min, WW_TEMP_ABS_MIN)
    hi = min(device_max, WW_TEMP_ABS_MAX)
    return clamp(value, lo, hi)


def validate_settings(s: Settings) -> tuple[Settings, list[str]]:
    """Prüft und korrigiert Einstellungen. Gibt (Settings, Hinweise) zurück.

    Ungültige Werte werden auf sichere Standardwerte gezogen, statt einen
    Fehler zu werfen – die Oberfläche darf nie in einen kaputten Zustand
    geraten.
    """
    notes: list[str] = []

    s.ww_boost_temp = clamp(s.ww_boost_temp, WW_TEMP_ABS_MIN, WW_TEMP_ABS_MAX)
    s.ww_normal_temp = clamp(s.ww_normal_temp, WW_TEMP_ABS_MIN, WW_TEMP_ABS_MAX)
    s.ww_min_temp = clamp(s.ww_min_temp, WW_TEMP_ABS_MIN, WW_TEMP_ABS_MAX)
    s.ww_hygiene_min_temp = clamp(s.ww_hygiene_min_temp, WW_TEMP_ABS_MIN, WW_TEMP_ABS_MAX)

    s.feed_in_on_w = clamp(s.feed_in_on_w, FEED_IN_ABS_MIN, FEED_IN_ABS_MAX)
    s.feed_in_off_w = clamp(s.feed_in_off_w, FEED_IN_ABS_MIN, FEED_IN_ABS_MAX)
    s.min_runtime_min = clamp(s.min_runtime_min, TIME_ABS_MIN, TIME_ABS_MAX)
    s.min_pause_min = clamp(s.min_pause_min, TIME_ABS_MIN, TIME_ABS_MAX)
    s.sensor_max_age_s = clamp(s.sensor_max_age_s, AGE_ABS_MIN, AGE_ABS_MAX)
    s.max_grid_import_w = clamp(s.max_grid_import_w, GRID_ABS_MIN, GRID_ABS_MAX)

    # Hysterese: Aus muss unter Ein liegen, sonst taktet die Anlage.
    if s.feed_in_off_w >= s.feed_in_on_w:
        s.feed_in_off_w = max(FEED_IN_ABS_MIN, s.feed_in_on_w - 100.0)
        notes.append("Ausschaltschwelle lag über Einschaltschwelle – angepasst.")
    # Boost muss über Normal liegen.
    if s.ww_boost_temp < s.ww_normal_temp:
        s.ww_boost_temp = s.ww_normal_temp
        notes.append("Boost-Temperatur lag unter Normal – angehoben.")
    # Hygiene darf Normal nicht überschreiten.
    if s.ww_hygiene_min_temp > s.ww_normal_temp:
        s.ww_hygiene_min_temp = s.ww_normal_temp
        notes.append("Hygienetemperatur lag über Normal – gesenkt.")
    if s.ww_min_temp > s.ww_normal_temp:
        s.ww_min_temp = s.ww_normal_temp
        notes.append("Mindesttemperatur lag über Normal – gesenkt.")

    return s, notes
