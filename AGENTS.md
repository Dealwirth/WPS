# AGENTS.md – Arbeitsgedächtnis für dieses Repository

## Projekt

**SolarFlow** – eine Home-Assistant-**App (Add-on)**, die eine **Viessmann
Vitocal 16** Wärmepumpe per PV-Überschuss steuert. Sie ersetzt alte
PV-Automationen durch ein sicheres, transparentes Schutzmodell.

- Autor/Verantwortlich: **Dealwirth** (GitHub)
- **Add-on** unter `solarflow/` (siehe `solarflow/config.yaml`, `Dockerfile`,
  `run.sh`, `app/`)
- HA-freier Kern unter `solarflow/app/core/` (ohne HA testbar)
- Server/Oberfläche: `solarflow/app/server.py` + `solarflow/app/static/index.html`
- Frühere Integration liegt nur noch als Referenz unter `legacy/solarflow/`.

### Warum Add-on statt Integration?

Die HACS-Integration rendete auf der realen Instanz **nur schwarz** (das
HA-Frontend-Custom-Element lud nicht). Die App bringt eine **eigene,
abgeschlossene Oberfläche** über HA-Ingress mit – keine Frontend-Abhängigkeit,
kein Token im Browser. Der Server spricht über den Supervisor mit HA.

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

- **s6-Init verwirft Container-Env.** Das HA-Basisimage reicht per `-e`
  gesetzte Variablen (u. a. `SUPERVISOR_TOKEN`) **nicht** an `run.sh` weiter.
  Sie liegen in `/run/s6/container_environment`. `run.sh` lädt sie daher
  explizit. Ohne das erreicht den Server **kein** Token → keine Verbindung.
- **Ingress-Unterpfad.** Unter HA-Ingress läuft die Seite unter
  `/api/hassio_ingress/<token>/`. Alle API-Aufrufe in `index.html` daher
  relativ zum aktuellen Pfad bilden (`BASE`), nie absolut `/api/...`.
- **Dienst-Domäne beachten.** `number.*` schreibt man mit `number.set_value`
  (`value`), `water_heater.*` mit `water_heater.set_temperature`
  (`temperature`). Der Planner wählt die Domäne, der Client schreibt.
- **Kein `?return_response` an Dienstaufrufe hängen.** HA antwortet sonst mit
  HTTP 400 („Service does not support responses").
- **Frontend ohne HA-Abhängigkeit.** Die Oberfläche ist bewusst reines
  HTML/CSS/JS ohne Bundle-Import und lädt so in jeder HA-Version und offline.
  Diese Entscheidung beibehalten.
- **Blockierende Dateizugriffe im Event-Loop vermeiden.** Dateien im Server
  über `async`-Pfade oder kurz halten; das Add-on läuft in eigenem Container,
  daher unkritischer als in der Integration.

## Test- und Entwicklungsbefehle

```bash
uv venv .venv
uv pip install --python .venv/bin/python pytest pytest-asyncio ruff aiohttp
.venv/bin/ruff check solarflow legacy tests
.venv/bin/python -m pytest          # 53 Tests, alle grün
```

Add-on-Image lokal bauen und gegen die Test-HA laufen lassen:

```bash
cd solarflow
sudo docker build -t solarflow-addon:test \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.20 .
sudo docker run -d --name sf-addon-test --network host \
  -e SOLARFLOW_HA_REST="http://127.0.0.1:8123/api" \
  -e SOLARFLOW_HA_WS="ws://127.0.0.1:8123/api/websocket" \
  -e SOLARFLOW_HA_TOKEN="$(cat /tmp/ha_token_test.txt)" \
  -e SOLARFLOW_DATA_DIR=/data -e SOLARFLOW_PORT=8099 \
  -v /tmp/sf_addon_data:/data solarflow-addon:test
# API:  GET /api/snapshot, /api/entities, /api/suggest, /api/health
#       POST /api/mode /api/settings /api/sources /api/module /api/emergency
#            /api/boost /api/cycle
```

## Lokale HA-Testinstanz (Docker)

```bash
sudo dockerd > /tmp/dockerd.log 2>&1 &          # Daemon ggf. starten
sudo docker run -d --name solarflow-test --network host \
  -v /tmp/ha-test/config:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

- Konfiguration: `/tmp/ha-test/config/configuration.yaml` mit `input_number`
  und `template`-Sensoren als Simulationsquellen.
- Benutzer: `tester` / `solarflow123`, HA unter `http://127.0.0.1:8123`.
- Token besorgen: Login-Flow über `/auth/login_flow` → `/auth/token`
  (**form-encoded**, `grant_type=authorization_code`). Access-Token läuft nach
  30 min ab → neu holen.

## Reale HA-Instanz des Nutzers

- URL: `https://petryss.duckdns.org:8123`, Login `50` / `50`
- HA-Version 2026.10.4, Supervisor 2026.10.5, `aarch64` → **HA OS/Supervised**
  (`hassio`-Komponente vorhanden). Add-ons sind damit möglich.
- REST-Token nur zur Diagnose; Zugriff über Supervisor-WebSocket-Kommando
  `supervisor/api` (als Admin) verifiziert.
- **Wichtig:** Nur lesen, nichts ohne ausdrückliche Freigabe ändern.
- Relevante Entitäten:
  - `sensor.solarnet_leistung_netzeinspeisung` (Einspeisung, W)
  - `sensor.solarnet_pv_leistung` (PV-Erzeugung, W)
  - `sensor.solarnet_leistung_netzbezug` (Netzbezug, W)
  - `water_heater.e3_vitocal_16_warmwasser`
  - `number.e3_vitocal_16_ww_temperatur` (WW-Sollwert, °C, Ruhezustand 52)
  - `sensor.e3_vitocal_16_ww_speichertemperatur` (WW-Speicher, °C)
  - `number.e3_vitocal_16_ww_hystereseschalter_ein` (WW-Hysterese)
- Zu ersetzende Alt-Automationen (Stand: **beide `on`**):
  - `automation.warmwasser_bei_stromuberschuss`
    (ID 1778863610388) – „Warmwasser bei Stromüberschuss"
  - `automation.warmwasser_bei`
    (ID 1778863800756) – „Warmwasser bei Normalstrom"

## Offene Punkte

- [ ] Nutzer-Freigabe einholen, dann Alt-Automationen zuerst deaktivieren,
      später löschen (erst wenn SolarFlow aktiv läuft).
- [ ] SolarFlow-App auf der realen Instanz einrichten (Schatten-Modus) und
      beobachten, bevor die Automatik scharf geschaltet wird.
- [ ] Am Ende alles auf Originalzustand zurücksetzen: WW-Sollwert 52 °C,
      beide Automationen `on`; temporäre Token-Datei `/tmp/real_ha_token.txt`
      löschen.

## Betrieb der realen Instanz (wichtige Handgriffe)

- **Ingress-Sitzung erzeugen** (sonst liefert jede Ingress-URL `401`):
  per WebSocket `supervisor/api` mit `POST /ingress/session` ein
  `session`-Token holen und als Cookie `ingress_session=<token>` an die
  Ingress-URL hängen. Ein Supervisor-Login-Token allein genügt nicht.
- **Seitenleisten-Eintrag** einer App: Der Supervisor registriert das Panel
  nur, wenn `ingress_panel` gesetzt ist. `panel_admin` in `config.yaml`
  steuert nur die Sichtbarkeit für Nicht-Admin-Konten (Standard `true`).
  Zum Nachziehen ohne Neuinstallation:
  `POST /addons/<slug>/options {"ingress_panel": true}`.
- **Build**: `build.yaml` ist veraltet (Supervisor warnt). Arch-spezifische
  Basis-Images gehören direkt in den `Dockerfile` (`ARG BUILD_FROM`).
- **Store-Update**: `POST /store/reload` erkennt die neue Version,
  `POST /store/addons/<slug>/update` baut/aktualisiert (Antwortet evtl. mit
  `unknown_error`, obwohl es klappt – Status über `/addons/<slug>/info` prüfen).
- **Schatten-Modus** ist die Standardbetriebsart: SolarFlow rechnet und zeigt
  den Vorschlag, schreibt aber nichts. Alte Automationen bleiben unangetastet.

