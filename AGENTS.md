# AGENTS.md – Arbeitsgedächtnis für dieses Repository

## Projekt

**SolarFlow** – eine HACS-installierbare Home-Assistant-Integration, die eine
**Viessmann Vitocal 16** Wärmepumpe per PV-Überschuss steuert. Sie ersetzt alte
PV-Automationen durch ein sicheres, transparentes Schutzmodell.

- Autor/Verantwortlich: **Dealwirth** (GitHub)
- Integration liegt unter `custom_components/solarflow/`
- HA-freier Kern unter `custom_components/solarflow/core/` (ohne HA testbar)
- Oberfläche: `frontend/solarflow-panel.js` (Panel) und
  `frontend/cards/solarflow-cards.js` (Dashboard-Karten)

## Harte Anforderungen des Nutzers (nicht verhandelbar)

1. **Bunter, einfacher, einzigartiger als das Alte.** Die neue Oberfläche soll
   farbiger und schlichter sein als die alte PVM-Lösung.
2. **Alles, was HA und HACS können, soll unterstützt werden.**
3. **KEINE Benachrichtigungen.** Nirgends `persistent_notification`,
   `notify.*` oder Ähnliches verwenden.
4. **Alte Automationen erst ersetzen, wenn die neue Funktion nachweislich
   läuft.** Erst deaktivieren, dann löschen.
5. **Neue Funktion nur testen, wenn sie vollständig fertig ist.**
6. **Widerstandsfähig, unzerstörbar, einfach zu konfigurieren.**

## Startverhalten (wichtig)

Die Integration startet **immer im Schatten-Modus** (`MODE_SHADOW`). Sie
beobachtet und schlägt vor, schaltet aber nicht, bis der Nutzer ausdrücklich
auf **Aktiv** schaltet. Das ist Absicht und darf nicht geändert werden.

## Ehrliche Anzeige (bereits umgesetzt)

Der angezeigte Zustand darf **nie** „Überschuss/Boost" melden, wenn in
Wahrheit etwas blockiert (Not-Aus, Schatten-Modus, blockierte Schutz-Ebene).
Umgesetzt in `core/machine.py` (`apply_inhibit`, `runtime_s`) und `runtime.py`
(Entscheidungsschritte, warn/blocked). Bei Änderungen daran immer
`tests/core/` mitlaufen lassen.

## Fail-safe by design

Die HA-Schicht fängt bewusst breit ab: Ein Fehler in einem Zyklus darf die
Integration **nie** anhalten. Deshalb sind in `pyproject.toml` für
`runtime.py`, `panel.py` und `__init__.py` die Ruff-Regeln `BLE001`/`S110`
bewusst ignoriert. Nicht „aufräumen".

## Module & benutzerdefinierte Schwellen

Jedes Modul in `core/modules/` trägt ein `default_enabled`-Flag. Anzeige- und
Sicherheitsmodule (core, thermal, safety, tariff, goals, forecast) sind
standardmäßig an; **schaltende** Zusatzmodule (wallbox, heating,
flexible_loads) bleiben aus, bis der Nutzer sie freigibt. Das Wallbox-Modul
schaltet über dasselbe Sicherheits-Gate wie Warmwasser; Heizung und flexible
Lasten beraten nur.

Alle Schwellen sind benutzerdefiniert einstellbar – im Panel (Tab
„Einstellungen", gruppiert), im Options-Flow und über den Dienst
`set_settings`. Neue Schwellen immer an **drei** Stellen ergänzen:
`core/models.py` (Settings + `as_dict`), `core/limits.py` (Klemmen), sowie
Panel/`const.py`/`config_flow.py`/`services.py`. Danach `tests/core/` laufen
lassen.

## Reale Installation (Stand 2026-11)

- Läuft auf dem echten HA (`https://petryss.duckdns.org:8123`, HA 2026.10.4)
  via HACS-Custom-Repository `Dealwirth/WPS`, Release `v0.2.0`.
- Config-Entry `SolarFlow` mit diesen echten Entitäten:
  - Einspeisung `sensor.solarnet_leistung_netzeinspeisung`
  - PV `sensor.solarnet_pv_leistung`
  - Netzbezug `sensor.solarnet_leistung_netzbezug`
  - WW `water_heater.e3_vitocal_16_warmwasser`,
    Sollwert `number.e3_vitocal_16_ww_temperatur`,
    Speicher `sensor.e3_vitocal_16_ww_speichertemperatur`,
    Hysterese `number.e3_vitocal_16_ww_hystereseschalter_ein`
  - Heizung `climate.e3_vitocal_16_heizung`
  - Wallbox `switch.gerage_wattpilot_pv_surplus`
- **Startet im Schatten-Modus.** `switch.solarflow_automatik` bleibt aus, bis
  der Nutzer bewusst auf Aktiv schaltet. Alte Automationen bleiben unangetastet,
  bis die neue Funktion nachweislich läuft (harte Nutzeranforderung).

## Bekannte Fallstricke

- **Blockierende Dateizugriffe im Event-Loop vermeiden.** Das Lesen von
  `manifest.json` in `panel.py` muss über `hass.async_add_executor_job`
  laufen, sonst warnt HA („Detected blocking call to read_text").
- **Frontend ohne HA-Abhängigkeit.** Panel und Karten sind bewusst einfache
  Custom Elements mit Shadow DOM – kein LitElement, kein Bundle-Import. Sie
  laden so in jeder HA-Version und offline. Diese Entscheidung beibehalten.
- **Cache-Busting.** `panel.py` hängt `?v={manifest_version}` an die
  Modul-URLs. Nach Änderungen an `manifest.json` version erhöhen.
- **HA-Frontend in Tests nicht extrahieren.** Der Inhalts-Extraktor sieht
  Shadow-DOM nicht. Zur visuellen Prüfung eine Harness-Seite unter
  `config/www/` bauen, die das echte JS + einen echten Snapshot lädt.

## Test- und Entwicklungsbefehle

```bash
uv venv .venv
uv pip install --python .venv/bin/python pytest pytest-asyncio ruff websockets
.venv/bin/ruff check custom_components tests
.venv/bin/python -m pytest          # aktuell 38 Tests, alle grün
node --check custom_components/solarflow/frontend/solarflow-panel.js
node --check custom_components/solarflow/frontend/cards/solarflow-cards.js
```

## Lokale HA-Testinstanz (Docker)

```bash
sudo dockerd > /tmp/dockerd.log 2>&1 &          # Daemon ggf. starten
sudo docker run -d --name solarflow-test --network host \
  -v /tmp/ha-test/config:/config \
  -v /workspace/project/WPS/custom_components/solarflow:/config/custom_components/solarflow \
  ghcr.io/home-assistant/home-assistant:stable
```

- Konfiguration: `/tmp/ha-test/config/configuration.yaml` mit `input_number`
  und `template`-Sensoren als Simulationsquellen.
- Benutzer: `tester` / `solarflow123`, HA unter `http://127.0.0.1:8123`.
- Token besorgen: Login-Flow über `/auth/login_flow` → `/auth/token`
  (**form-encoded**, `grant_type=authorization_code`). Access-Token läuft nach
  30 min ab → neu holen.
- WS-API: `python3 -m pip install websockets`; Befehle `solarflow/snapshot`,
  `solarflow/set_mode`, `solarflow/set_settings`, `solarflow/set_module`,
  `solarflow/emergency`.

## Reale HA-Instanz des Nutzers (nur lesend!)

- URL: `https://petryss.duckdns.org:8123`, Login `50` / `50`
- HA-Version 2026.10.4, `location_name: Home`
- **Wichtig:** Nur lesen, nichts ohne ausdrückliche Freigabe ändern.
- Relevante Entitäten:
  - `sensor.solarnet_leistung_netzeinspeisung` (Einspeisung, W)
  - `sensor.solarnet_pv_leistung` (PV-Erzeugung, W)
  - `sensor.solarnet_leistung_netzbezug` (Netzbezug, W)
  - `water_heater.e3_vitocal_16_warmwasser`
  - `number.e3_vitocal_16_ww_temperatur` (WW-Sollwert, °C)
  - `sensor.e3_vitocal_16_ww_speichertemperatur` (WW-Speicher, °C)
- Zu ersetzende Alt-Automationen (aktuell `on`):
  - `automation.warmwasser_bei_stromuberschuss`
    (ID 1778863610388) – „Warmwasser bei Stromüberschuss"
  - `automation.warmwasser_bei`
    (ID 1778863800756) – „Warmwasser bei Normalstrom"

## Offene Punkte

- [ ] Nutzer-Freigabe einholen, dann Alt-Automationen zuerst deaktivieren,
      später löschen (erst wenn SolarFlow aktiv läuft).
- [ ] SolarFlow auf der realen Instanz einrichten (Schatten-Modus) und
      beobachten, bevor die Automatik scharf geschaltet wird.
- [ ] Bei Veröffentlichung: GitHub-Repository `Dealwirth/WPS` muss öffentlich
      sein, damit HACS es findet; Release/Tag `v0.1.0` anlegen.
