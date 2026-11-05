## 2.0.1

- **Echte HA-Geräte im Store**: der Store liest das Home-Assistant-Geräte-,
  Entitäts- und Bereichs-Register und zeigt echte Geräte zum Zuordnen.
- **Mehrere gleiche Geräte** möglich (z. B. zwei Wallboxen), jedes schaltet
  unabhängig.
- Geräte ohne Pflicht-Entität werden angezeigt, aber nie geschaltet.
- Fehler behoben: `/api/device_types` antwortete mit 500; die Oberfläche lädt
  das Geräte-Register jetzt bei Bedarf statt in jedem Statusabruf.

## 2.0.0

- **Geräte-Store**: beliebige Geräte hinzufügen, nicht nur die Wärmepumpe.
- Vorlagen für Wärmepumpe, Heizstab, Klimaanlage, Wallbox, E-Auto, Speicher,
  Poolpumpe, Bewässerung, Waschmaschine, Trockner, Geschirrspüler und freie
  Verbraucher.
- Je Gerät eigene Entitäten, Schwellen und Ein/Aus – automatische Erkennung
  passender Entitäten.
- Modul-System durch Geräte-Strategien ersetzt (Überschuss schalten,
  thermischer Boost, Speicher-Reserve, Klima-Vorschlag).
- Alte feste Quellen werden beim Umstieg automatisch zu einem
  Wärmepumpen-Gerät.

## 1.0.0

- Erste veröffentlichte App-Version.
- Sichere PV-Überschussregelung der Viessmann Vitocal 16 (Warmwasser).
- Zehn Schutz-Ebenen, Not-Aus, Schatten-Modus als Startzustand.
- Farbige Oberfläche mit Modul-Store, allen Schwellen und Quellenwahl.
- Liest Home Assistant über den Supervisor, schreibt nur über das Sicherheits-Gate.
