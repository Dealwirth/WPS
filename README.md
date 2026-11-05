# SolarFlow – sichere PV-Automatik für Home Assistant

SolarFlow schiebt Warmwasser und Laden in die Sonne – **aber nur, wenn es sicher
ist**. Es ersetzt eine Sammlung von Automationen durch eine Integration mit
einem klaren, jederzeit sichtbaren Schutzmodell.

> Dieses Repository wird von einem KI-Agenten (OpenHands) im Auftrag von
> **Dealwirth** gepflegt.

## Warum SolarFlow?

Alte PV-Automationen sind schwer zu durchschauen und im Fehlerfall gefährlich:
Sie schalten, obwohl Daten fehlen, ein Not-Aus aktiv ist oder Grenzen verletzt
werden. SolarFlow dreht das um – **Sicherheit ist die Standardeinstellung**:

- **Startet im Schatten-Modus.** Es beobachtet und schlägt vor, schaltet aber
  nicht, bis du es ausdrücklich freigibst.
- **Zehn Schutz-Ebenen.** Sensor-Plausibilität, Datenalter, Gerätegrenzen,
  Schreib-Verifikation, Selbstheilung, Not-Aus, Watchdog und mehr.
- **Ehrliche Anzeige.** Der Zustand zeigt nie „Überschuss", wenn in Wahrheit
  etwas blockiert. Du siehst jederzeit, *warum* gerade so entschieden wurde.
- **Ein einziger Not-Aus.** Ein Knopf sperrt alles, sofort.

## Funktionen

- Warmwasser-Boost bei PV-Überschuss mit echter Hysterese und Mindestlauf-/
  Mindestpausenzeit (kein Takten).
- Optional: Wallbox und E-Auto-Laden, Heizkreis-Verschiebung.
- Modi **Aus / Schatten / Aktiv** – jederzeit umschaltbar.
- Deutsch und Englisch.
- Seitenleisten-Panel **und** Dashboard-Karten – bewusst ohne Abhängigkeit zum
  HA-Frontend, damit die Oberfläche in jeder HA-Version und offline lädt.
- Alle HA- und HACS-Standards: Config-Flow, Dienste, Entitäten, Diagnose,
  Audit-Protokoll. **Keine Benachrichtigungen.**

## Installation über HACS

1. HACS öffnen → **Integrationen** → Drei-Punkte-Menü → **Benutzerdefinierte
   Repositories**.
2. Dieses Repository hinzufügen, Kategorie **Integration**.
3. SolarFlow installieren und Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → SolarFlow**.
   Der Assistent fragt nach deinen Quellen und zeigt Vorbelegungen.

## Einrichtung

Der Assistent fragt nach:

| Feld | Beispiel (E3 Vitocal 16) |
| --- | --- |
| Einspeisung | `sensor.solarnet_leistung_netzeinspeisung` |
| PV-Erzeugung | `sensor.solarnet_pv_leistung` |
| Netzbezug | `sensor.solarnet_leistung_netzbezug` |
| Warmwasser-Gerät | `water_heater.e3_vitocal_16_warmwasser` |
| WW-Sollwert | `number.e3_vitocal_16_ww_temperatur` |
| WW-Speichertemperatur | `sensor.e3_vitocal_16_ww_speichertemperatur` |

Nach der Einrichtung startet SolarFlow **immer im Schatten-Modus**. Erst wenn
du im Panel auf **Aktiv** schaltest, greift die Automatik.

## Sicherheit

| Ebene | Wirkung |
| --- | --- |
| Sensor-Plausibilität | Unmögliche Werte werden verworfen |
| Daten-Alter | Veraltete Werte stoppen die Automatik |
| Sensor-Ausfall | Ausfall → sicherer Zustand Normal |
| Hysterese & Flankenschutz | Kein Takten, Mindestlauf- und -pausenzeit |
| Harte Temperaturgrenzen | Nie über/unter feste Grenzen |
| Gerätegrenzen | Nur Werte, die das Gerät akzeptiert |
| Schreib-Verifikation | Geschriebener Wert wird zurückgelesen |
| Wiederhol- & Not-Fallback | Kein „Hämmern" auf das Gerät |
| Selbstheilung | Stellt den letzten guten Zustand wieder her |
| Not-Aus & Watchdog | Ein Knopf sperrt alles, sofort |

## Entwicklung

```bash
uv venv .venv
uv pip install --python .venv/bin/python pytest pytest-asyncio ruff
.venv/bin/ruff check custom_components tests
.venv/bin/python -m pytest
```

Der HA-freie Kern (`custom_components/solarflow/core/`) lässt sich ohne
Home Assistant testen. Die HA-Schicht fängt bewusst breit ab – ein Fehler in
einem Zyklus darf die Integration nie anhalten (Fail-safe by design).

## Lizenz

Siehe Repository-Eigentümer.
