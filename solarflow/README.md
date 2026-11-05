# SolarFlow

Sichere PV-Überschuss-Automatik mit **Geräte-Store** – für Wärmepumpe,
Warmwasser, Wallbox, Speicher, Poolpumpe und mehr – als
Home-Assistant-**App (Add-on)**.

SolarFlow schiebt Warmwasser, Heizung und Ladung in die Sonnenstunden – aber
nur, wenn Daten frisch und plausibel sind, Grenzen eingehalten werden und du
die Automatik ausdrücklich freigegeben hast. Es startet **immer im
Schatten-Modus**: beobachten und vorschlagen, niemals schalten, bis du
bewusst auf **Aktiv** schaltest.

## Installation

1. Einstellungen → Add-ons → Add-on-Store → ⋮ → **Repositories**
2. `https://github.com/Dealwirth/WPS` hinzufügen
3. **SolarFlow** installieren und starten
4. In der Seitenleiste auf **SolarFlow** klicken

## Bedienung in 3 Schritten

1. **Quellen** wählen (oder „Automatisch erkennen“) – Einspeisung, PV,
   Netzbezug.
2. Im Reiter **Geräte** aus dem Store ein Gerät hinzufügen und seine
   Entitäten zuordnen (oder „Automatisch erkennen“ nutzen).
3. Auf **Aktiv** schalten, wenn der Schatten-Modus plausible Vorschläge zeigt.

## Geräte-Store

Ein Gerät ist eine Vorlage aus dem Store plus die Entitäten deiner Anlage.
SolarFlow kennt unter anderem: Wärmepumpe/Warmwasser, Heizstab, Klimaanlage,
Wallbox, E-Auto-Laden, PV-Speicher, Poolpumpe, Bewässerung, Waschmaschine,
Trockner, Geschirrspüler und freie Verbraucher. Jedes Gerät hat eigene
Schwellen und lässt sich einzeln pausieren.

## Sicherheit

Zehn Schutz-Ebenen prüfen jeden Zyklus, ein Not-Aus sperrt alles sofort, und
jede Schreibung wird zurückgelesen. Keine Benachrichtigungen, kein
Dauerfeuer. Im Zweifel fällt SolarFlow auf den sicheren Zustand zurück.
