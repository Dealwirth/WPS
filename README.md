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
- Eigene, farbige Oberfläche über Home-Assistant-Ingress – bewusst ohne
  Abhängigkeit zum HA-Frontend, damit sie in jeder HA-Version und offline
  lädt. Kein Token im Browser.
- Audit-Protokoll und ehrliche Statusanzeige. **Keine Benachrichtigungen.**

## Installation als Home-Assistant-App (Add-on)

Der empfohlene Weg ist die **App (Add-on)** – sie bringt ihre eigene,
farbige Oberfläche mit und lädt in jeder HA-Version und offline:

1. **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**
2. `https://github.com/Dealwirth/WPS` hinzufügen
3. **SolarFlow** installieren und starten
4. In der Seitenleiste auf **SolarFlow** klicken

Die App liest und schreibt Home Assistant über den Supervisor. Es liegt **kein
Token im Browser** – die Oberfläche spricht nur mit dem lokalen Server.

## Einrichtung

In der Oberfläche unter **Quellen** wählen (oder „Automatisch erkennen“):

| Feld | Beispiel (E3 Vitocal 16) |
| --- | --- |
| Einspeisung | `sensor.solarnet_leistung_netzeinspeisung` |
| PV-Erzeugung | `sensor.solarnet_pv_leistung` |
| Netzbezug | `sensor.solarnet_leistung_netzbezug` |
| WW-Sollwert | `number.e3_vitocal_16_ww_temperatur` |
| WW-Speichertemperatur | `sensor.e3_vitocal_16_ww_speichertemperatur` |
| WW-Hysterese | `number.e3_vitocal_16_ww_hystereseschalter_ein` |

Nach dem Start läuft SolarFlow **immer im Schatten-Modus**. Erst wenn du auf
**Aktiv** schaltest, greift die Automatik.

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
uv pip install --python .venv/bin/python pytest pytest-asyncio ruff aiohttp
.venv/bin/ruff check solarflow legacy tests
.venv/bin/python -m pytest
```

Der HA-freie Kern (`solarflow/app/core/`) lässt sich ohne Home Assistant
testen. Der Server (`solarflow/app/server.py`) und die HA-Anbindung
(`ha_client.py`) kommen ohne HA-Import aus. Die frühere Integration liegt als
Referenz unter `legacy/solarflow/`. Die HA-Schicht fängt bewusst breit ab –
ein Fehler in einem Zyklus darf die Automatik nie anhalten (Fail-safe by
design).

## Lizenz

Siehe Repository-Eigentümer.
