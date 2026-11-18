# AI Meter Reader – lokale Zählerablesung für Home Assistant

**Version 0.6.8 Stable** · [English](README.en.md) · [Änderungen](rf1_ocr_test/CHANGELOG.md)

Liest mechanische Zähler aus Kamerabildern lokal mit Tesseract OCR und prüft den Stand optional gegen **AI on the Edge / SLFork** oder einen Home-Assistant-Sensor. Geeignet insbesondere für Gaszähler mit Rollenziffern und einstellbaren Nachkommastellen. Die App benötigt Home Assistant mit Supervisor (ARM64 oder AMD64).

<img src="assets/project-logo.png" alt="AI Meter Reader – Projektlogo" width="120">

## Schnellstart

[![App-Repository in Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FEifellayer%2Fmeter-ocr)

1. **Repository hinzufügen:** Obigen Link öffnen oder unter **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Eifellayer/meter-ocr` eintragen.
2. **AI Meter Reader installieren**, starten und die Weboberfläche öffnen.
3. **Bildquelle wählen:** AI on the Edge / SLFork, ESP nur als Kamera, ESPHome oder eine Home-Assistant-Kamera.
4. **Selbsteinrichtung starten:** Die Übersicht zeigt die einzelnen Suchschritte. Nach bestätigten sieben Ziffern läuft die normale Prüfung; eine optionale achte Stelle wird im Hintergrund weiter untersucht.
5. Unter **Übersicht → Werkzeuge → Manueller Test** bei Bedarf Bildausschnitt, Drehung oder Beleuchtung prüfen. Auch ohne Kamera steht eine **Demo** bereit.

Der Link öffnet den Dialog zum Hinzufügen des Repositories, nicht automatisch die Installation. Wenn er nicht funktioniert, die Adresse aus Schritt 1 manuell eintragen. Eine [bebilderte Anleitung](docs/Bedienungsanleitung-AI-Meter-Reader.pdf) zeigt die Bedienung anhand nachgezeichneter Beispielbilder.

## Was ist bereits möglich?

- **Lokale OCR:** flexible Ziffernanzahl, automatischer oder manueller Rahmen, Drehung, nachvollziehbare Mehrfachversuche und Einzelziffernprüfung.
- **Plausibilitätsprüfung:** Abgleich mit vorhandenem Sensorwert, Kennzeichnung unlesbarer Ziffern statt ungesicherter Messwerte und Schutz vor unplausiblen Verbrauchssprüngen.
- **Automatik:** einstellbares Intervall, Fehlversuch-Wartezeiten, Benachrichtigungen und optionaler Energie-Dashboard-Sensor `sensor.rf1_verbrauch_gesamt`.
- **Sieben plus eine Stelle:** der bestätigte Sieben-Ziffern-Rahmen bleibt aktiv, auch wenn die dritte Nachkommastelle durch Spiegelung oder Rollenbewegung unlesbar bleibt.
- **Statistik erhalten:** separater Factory Reset, der Gesamtverbrauch und Verbrauchsstatistik beibehält.

### Wann prüft die App?

| Situation | Zeit bis zur nächsten Prüfung |
| --- | --- |
| Erfolgreiche reguläre Prüfung | Eingestelltes Intervall, **standardmäßig 10 Minuten** |
| Erste oder zweite Fehlprüfung | **5 Minuten** (sofern ein neues Bild verfügbar ist) |
| Drei Fehlprüfungen in Folge | **60 Minuten** Abkühlzeit |
| Ersteinrichtung / optionale adaptive Funktionen | Können vorübergehend häufiger prüfen; die Übersicht nennt den nächsten Termin |

## Dokumentation und Teststand

- [Ausführliche Bedienung, Prüfregeln und Konfiguration](docs/DETAILS.md) · [English details](docs/DETAILS.en.md)
- [Bebilderte Bedienungsanleitung (PDF)](docs/Bedienungsanleitung-AI-Meter-Reader.pdf) · [App-Dokumentation](rf1_ocr_test/DOCS.md)
- [Öffentliche Foto-Vergleichstests](METER-PHOTO-TESTS.md) · [Quellen](SOURCES.md) · [Entwicklungsplan](RELEASE-PLAN.md)

**Praxistests:** AI on the Edge / SLFork und **„ESP nur als Kamera“** wurden an einem realen ESP/Gaszähler verwendet. Für eigenständige ESPHome- und andere Home-Assistant-Kameras sowie weitere Zählertypen gibt es automatisierte oder simulierte Tests; weitere echte Gerätetests sind willkommen. Die Fototests sind ein dokumentierter Referenzstand und noch keine vollständige CI-Bildtestsuite.

## Stable

Der reguläre Kanal wird über `https://github.com/Eifellayer/meter-ocr` eingebunden. Bestehende App-IDs, `rf1_*`-Entitäten und gespeicherte Messdaten werden bei normalen Updates beibehalten. **`rf1_ocr_test` ist aus Kompatibilitätsgründen weiterhin der App-Ordner und Slug**, kein eigener Testkanal. Vor einem Upgrade ist ein Home-Assistant-Backup empfehlenswert.

Bei ausstehendem Update kann in **Entwicklerwerkzeuge → Aktionen** `homeassistant.update_entity` für `update.meter_ocr_update` den Update-Status abfragen. Installation erfolgt danach automatisch, falls aktiviert, andernfalls über `update.install` für dieselbe Entität. [Details](docs/DETAILS.md#neue-version-sofort-suchen).

## Mitmachen und Rückmeldungen

Fehlerberichte und Vorschläge bitte als [GitHub Issue](https://github.com/Eifellayer/meter-ocr/issues) mit App-Version, Bildquelle, Zählertyp und erwartetem Ergebnis melden. **Keine Zugangsdaten oder ungeschwärzten privaten Fotos veröffentlichen.** Das Projekt ist ein kostenloses Hobbyprojekt; eine explizite Open-Source-Lizenz ist noch nicht festgelegt. Beiträge und Weiterverwendungsrechte sollten deshalb vorab geklärt werden.

## Hinweise zur Nutzung

Die OCR ist **keine geeichte Messung**. Für Abrechnung und offizielle Meldungen gilt der direkt am Gerät kontrollierte Zählerstand. Die Software wird soweit gesetzlich zulässig ohne Gewähr bereitgestellt; zwingende gesetzliche Haftungsvorschriften bleiben unberührt.

[Projekt unterstützen](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8) (freiwillig) · [GitHub](https://github.com/Eifellayer/meter-ocr)
