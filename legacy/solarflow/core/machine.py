"""Zustandsmaschine der Anlage mit echter Hysterese.

Sie ersetzt den fragilen Zähler-Latch der alten Automation. Kernidee:

* **Ein** bei ``feed_in_on_w``, **Aus** bei ``feed_in_off_w`` (echte Hysterese).
* **Mindestlaufzeit**: ein Boost läuft mindestens ``min_runtime_min``.
* **Mindestpause**: nach einem Boost wird ``min_pause_min`` gewartet.
* Bei unklaren Daten oder Fehler fällt sie **immer** auf ``NORMAL`` zurück.

Die Klasse ist zustandslos gegenüber Home Assistant und damit direkt testbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import PlantState, Settings


@dataclass
class Machine:
    """Endlicher Automat für den Warmwasser-Zustand."""

    state: PlantState = PlantState.NORMAL
    since: float = 0.0  # Zeitpunkt des letzten Zustandswechsels
    last_boost_end: float = -1e12  # Ende des letzten Boosts (für Mindestpause)
    changes: int = 0  # Zähler der Wechsel (Diagnose)
    history: list[tuple[float, str]] = field(default_factory=list)

    def _go(self, new: PlantState, now: float, reason: str) -> bool:
        if new == self.state:
            return False
        if self.state == PlantState.BOOST:
            self.last_boost_end = now
        self.state = new
        self.since = now
        self.changes += 1
        self.history.append((now, str(new)))
        if len(self.history) > 200:
            self.history = self.history[-200:]
        return True

    def runtime_s(self, now: float) -> float:
        return now - self.since

    def apply_inhibit(self, now: float, reason: str) -> bool:
        """Kehrt in den Ruhezustand zurück, wenn Schreiben gesperrt ist.

        Damit zeigt die Anzeige ehrlich „Normal“, wenn Not-Aus, Schattenmodus
        oder eine blockierte Schutz-Ebene das Schalten verhindern.
        """
        return self._go(PlantState.NORMAL, now, reason)

    def update(
        self,
        *,
        now: float,
        feed_in_w: float | None,
        data_ok: bool,
        demand: bool,
        settings: Settings,
    ) -> tuple[PlantState, bool, str]:
        """Berechnet den nächsten Zustand.

        Returns: (state, changed, reason_de)
        """
        # 1) Kein klarer Wert oder Fehler -> sicherer Zustand.
        if not data_ok or feed_in_w is None:
            changed = self._go(PlantState.NORMAL, now, "keine gültigen Daten")
            return self.state, changed, "Keine gültigen Daten – sicherer Zustand Normal."

        # 2) Urlaub: keine Automatik, nur Normal.
        if settings.holiday:
            changed = self._go(PlantState.NORMAL, now, "Urlaub")
            return self.state, changed, "Urlaubsmodus – keine Automatik."

        on = settings.feed_in_on_w
        off = settings.feed_in_off_w

        if self.state == PlantState.NORMAL:
            # Bedingungen für Boost?
            if feed_in_w < on:
                return self.state, False, f"Einspeisung {feed_in_w:.0f} W < {on:.0f} W."
            if not demand:
                return self.state, False, "Kein Wärmebedarf – Speicher schon warm genug."
            pause_ok = (now - self.last_boost_end) >= settings.min_pause_min * 60.0
            if not pause_ok:
                rest = settings.min_pause_min * 60.0 - (now - self.last_boost_end)
                return self.state, False, f"Mindestpause läuft noch ({rest / 60:.0f} min)."
            changed = self._go(PlantState.BOOST, now, "Überschuss")
            return self.state, changed, f"Überschuss {feed_in_w:.0f} W ≥ {on:.0f} W – Boost startet."

        # state == BOOST
        if settings.force_boost:
            return self.state, False, "Boost wird manuell gehalten."
        # Ziel erreicht: Speicher ist warm genug -> zurück auf Normal.
        if not demand:
            changed = self._go(PlantState.NORMAL, now, "Speicher warm genug")
            return self.state, changed, "Speicher hat die Zieltemperatur erreicht."
        runtime_ok = self.runtime_s(now) >= settings.min_runtime_min * 60.0
        if feed_in_w <= off and runtime_ok:
            changed = self._go(PlantState.NORMAL, now, "Überschuss vorbei")
            return self.state, changed, f"Einspeisung {feed_in_w:.0f} W ≤ {off:.0f} W – zurück auf Normal."
        if feed_in_w <= off and not runtime_ok:
            rest = settings.min_runtime_min * 60.0 - self.runtime_s(now)
            return self.state, False, f"Mindestlaufzeit läuft noch ({rest / 60:.0f} min)."
        return self.state, False, f"Boost hält ({feed_in_w:.0f} W)."
