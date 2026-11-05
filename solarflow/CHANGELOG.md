## 2.1.0

- **Jedes Gerät hat sein eigenes Bild** (Emoji) – in Vorlagen festgelegt und je
  Gerät frei wählbar. Gerätekarten und Store-Kacheln zeigen das Bild.
- **Automatische Geräteerkennung**: „Geräte suchen“ prüft die echten
  HA-Geräte und schlägt passende Typen samt Entitäten vor – mit
  Sicherheits-Prozent. „Alle übernehmen“ legt sie in einem Schritt an.
- **Neuer Reiter „Energiefluss“**: stellt PV-Erzeugung, Einspeisung,
  Netzbezug, Gerätesumme und je Gerät die Leistung mit Anteil und
  Eigenverbrauchsquote gegenüber.
- **Schönere, ruhigere Oberfläche**: sanfte Hintergrund-Animationen, weiche
  Übergänge, farbige Akzente je Gerät, klare Karten. Weniger Text, mehr Bild.
- **Bedienung entspannter**: klare Sprache, Kurzinfos, Direktlinks
  (`?tab=…&lang=…`), Geräte lassen sich per Klick auf einen Fund übernehmen.
- Neu: `/api/devices/auto` (GET Vorschläge, POST anlegen) und Vergleichsdaten
  im Status (`compare`). Alle Kernfunktionen weiter ohne Home Assistant testbar.

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
