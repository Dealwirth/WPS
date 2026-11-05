"""Der Regelzyklus: von Messwerten zur sicheren Entscheidung.

Diese Funktion verbindet Zustandsmaschine, Bedarfsprüfung und Sicherheits-Gate.
Sie ist der **einzige** Ort, an dem entschieden wird, was geschaltet werden
soll. Der Rückgabewert ist ein :class:`Decision` – eine reine Beschreibung.
Erst die HA-Schicht führt die erlaubten Aktionen aus.
"""

from __future__ import annotations

from .machine import Machine
from .models import Action, Decision, Mode, PlantState, Reading, Settings
from .safety import SafetyContext, gate


def _demand(storage: Reading | None, target_temp: float, hysteresis: float = 2.0) -> bool:
    """Gibt es Wärmebedarf? (Speicher kälter als Ziel − kleine Hysterese.)"""
    if storage is None or not storage.is_number:
        # Ohne Speicherwert nehmen wir Bedarf an – die Temperaturgrenzen schützen.
        return True
    return float(storage.value) < (target_temp - hysteresis)


def evaluate(
    *,
    machine: Machine,
    settings: Settings,
    feed_in: Reading,
    storage: Reading | None,
    grid_import: Reading | None,
    now: float,
    previous_feed_in: float | None,
    device_min: float,
    device_max: float,
    ww_entity: str,
    emergency_stop: bool = False,
    current_temp: float | None = None,
    enabled_modules: set[str] | None = None,
    wallbox_entity: str | None = None,
    wallbox_on: bool | None = None,
) -> Decision:
    """Berechnet die Entscheidung für einen Zyklus.

    ``current_temp`` ist der aktuell am Gerät gesetzte Sollwert. Weicht er vom
    Ziel ab, wird der Zielwert erneut geschrieben – so heilt SolarFlow nach
    einem blockierten oder manuell veränderten Wert von selbst.

    ``enabled_modules`` steuert, welche Module handeln dürfen. Das Wallbox-
    Modul schaltet nur bei ausdrücklicher Freigabe und läuft durch dasselbe
    Sicherheits-Gate. Heizung und flexible Lasten beraten nur.
    """
    modules = enabled_modules or {"core"}
    ctx = SafetyContext(
        feed_in=feed_in,
        settings=settings,
        now=now,
        storage=storage,
        grid_import=grid_import,
        previous_feed_in=previous_feed_in,
        device_min=device_min,
        device_max=device_max,
        emergency_stop=emergency_stop,
        mode=settings.mode,
    )

    steps: list[tuple[str, str]] = []

    # Datenqualität
    from .quality import (
        POWER_MAX_W,
        POWER_MIN_W,
        check_freshness,
        check_jump,
        check_value,
    )

    ok_fresh, f_de, _ = check_freshness(feed_in, settings.sensor_max_age_s)
    ok_range, r_de, _ = check_value(feed_in.value, lo=POWER_MIN_W, hi=POWER_MAX_W)
    ok_jump, j_de, _ = check_jump(feed_in.value, previous_feed_in)
    data_ok = ok_fresh and ok_range and ok_jump

    steps.append(("ok" if ok_fresh else "warn", f"Datenqualität: {f_de}"))
    if not ok_jump:
        steps.append(("warn", f"Plausibilität: {j_de}"))
    if not ok_range:
        steps.append(("warn", f"Bereich: {r_de}"))

    # Bedarf nur relevant für den Übergang in den Boost.
    need = _demand(storage, settings.ww_boost_temp, settings.ww_hysteresis_c)
    storage_temp = storage.value if storage and storage.is_number else "?"
    steps.append(("info", f"Bedarf: {'ja' if need else 'nein'} (Speicher {storage_temp} °C)"))

    feed = feed_in.value if feed_in.is_number else None
    new_state, changed, reason = machine.update(
        now=now,
        feed_in_w=feed,
        data_ok=data_ok,
        demand=need,
        settings=settings,
    )
    steps.append(("ok" if not changed else "warn", f"Zustand: {new_state} – {reason}"))

    # Sollwert bestimmen (nur wenn Automatik scharf ist, wird er gesetzt).
    actions: list[Action] = []
    if new_state == PlantState.BOOST:
        target = settings.ww_boost_temp
    else:
        target = max(settings.ww_normal_temp, settings.ww_min_temp)
    steps.append(("info", f"Zieltemperatur: {target:.0f} °C"))

    # Konvergenz: schreiben bei Zustandswechsel ODER wenn das Gerät vom Ziel
    # abweicht (Selbstheilung nach Blockade oder manueller Änderung).
    drifted = current_temp is None or abs(float(current_temp) - target) > 0.6
    if ww_entity and (changed or drifted):
        why = reason if changed else "Selbstheilung: Sollwert am Gerät abweichend."
        # Dienst und Feld richten sich nach der Domäne: water_heater nutzt
        # ``temperature``, eine number-Entität dagegen ``value``.
        if ww_entity.split(".")[0] == "water_heater":
            service, data = "water_heater.set_temperature", {"temperature": target}
        else:
            service, data = "number.set_value", {"value": target}
        actions.append(Action(entity_id=ww_entity, service=service, data=data, why=why))

    # Bedarfs-Schutz: Boost ohne Bedarf verhindern.
    if new_state == PlantState.BOOST and not need and settings.mode == Mode.ACTIVE:
        steps.append(("warn", "Boost ohne Bedarf – kein Schreiben."))

    # --- Wallbox-Modul (schaltet nur bei Freigabe, über dasselbe Gate) ---
    if "wallbox" in modules and wallbox_entity and feed is not None:
        want_on = feed >= settings.wallbox_on_w
        if want_on and wallbox_on is not True:
            steps.append(("info", f"Wallbox: Überschuss {feed:.0f} W ≥ {settings.wallbox_on_w:.0f} W – Laden frei."))
            actions.append(
                Action(
                    entity_id=wallbox_entity,
                    service="switch.turn_on",
                    data={},
                    why="PV-Überschuss für die Wallbox.",
                )
            )
        elif not want_on and feed <= settings.wallbox_off_w and wallbox_on is True:
            steps.append(("info", f"Wallbox: Überschuss {feed:.0f} W ≤ {settings.wallbox_off_w:.0f} W – Laden aus."))
            actions.append(
                Action(entity_id=wallbox_entity, service="switch.turn_off", data={}, why="Kein Überschuss mehr.")
            )
        else:
            steps.append(
                (
                    "info",
                    f"Wallbox: Hysterese hält (Ein {settings.wallbox_on_w:.0f} W / "
                    f"Aus {settings.wallbox_off_w:.0f} W).",
                )
            )

    # --- Heizung-Modul (nur beratend, kein Schreiben) ---
    if "heating" in modules and need and feed is not None and feed >= settings.feed_in_on_w:
        steps.append(("info", f"Heizung: Vorheizen um {settings.heating_shift_c:.0f} °C möglich (nur Vorschlag)."))

    # --- Prognose-Modul (nur beratend) ---
    if "forecast" in modules:
        steps.append(("info", f"Prognose: Horizont {settings.forecast_horizon_h:.0f} h (nur Anzeige)."))

    allowed, blocked_reasons = gate(actions, ctx)
    blocked = bool(blocked_reasons) or bool(actions and not allowed)

    for r in blocked_reasons:
        steps.append(("blocked", r))

    return Decision(
        state=new_state,
        actions=allowed,
        blocked=blocked,
        reason_de=reason,
        reason_en=reason,
        steps=steps,
    )
