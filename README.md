# AI Meter Reader

**Version 0.1.0** · [English](README.en.md) · [Anleitung](rf1_ocr_test/DOCS.md) · [Änderungen](rf1_ocr_test/CHANGELOG.md) · [Roadmap](RELEASE-PLAN.md)

<img src="assets/project-logo.png" alt="AI Meter Reader" width="110">

Home-Assistant-App, die mechanische Zähler (vor allem Gaszähler mit Ziffernrollen) lokal per Kamera abliest. Kein Cloud-Dienst, keine Abo-KI: Tesseract-OCR auf deinem Home Assistant (ARM64 oder AMD64).

## Schnellstart

[![Repository in Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FEifellayer%2Fmeter-ocr)

1. Repository hinzufügen (Link oben oder `https://github.com/Eifellayer/meter-ocr` unter **Einstellungen → Apps → App installieren → ⋮ → Repositories**).
2. **AI Meter Reader** installieren, starten, Weboberfläche öffnen.
3. Im Einrichtungsassistenten die Bildquelle wählen: ESPHome-/Home-Assistant-Kamera, AI on the Edge / SLFork oder **ESP nur als Kamera**.
4. Selbsteinrichtung starten. Die App sucht den Ziffernbereich, bestätigt ihn mit mehreren Bildern und prüft danach automatisch.

## Was die App macht

- Liest den Zählerstand aus dem Kamerabild und bestätigt jede Prüfung mit einem zweiten Bild.
- Erkennt unlesbare Ziffern, statt zu raten, und bucht keinen negativen oder doppelten Verbrauch.
- Stellt `sensor.rf1_ocr_zaehlerstand` und `sensor.rf1_verbrauch_gesamt` (Energie-Dashboard) bereit.
- Optional: Abgleich mit einem vorhandenen Sensor, Benachrichtigungen, Demo ohne Kamera.

## Prüfrhythmus

| Situation | Nächste Prüfung |
| --- | --- |
| Erfolgreiche Prüfung | eingestelltes Intervall, standardmäßig 10 Minuten |
| 1. oder 2. Fehlprüfung | 5 Minuten |
| Nur die 7. Ziffer unsicher, Rest per Referenz bestätigt | 30 Minuten |
| 3 Fehlprüfungen in Folge | 60 Minuten Pause |

## Hinweise

Die OCR ist keine geeichte Messung; für Abrechnungen gilt der Stand am Gerät. Fehler und Ideen bitte als [GitHub Issue](https://github.com/Eifellayer/meter-ocr/issues) (ohne Zugangsdaten oder private Fotos). Lizenz: [GNU GPLv3 oder später](LICENSE), Drittsoftware siehe [SOURCES.md](SOURCES.md). Wie das Projekt entstanden ist: [Rückblick](docs/HISTORY.md).

[Projekt unterstützen](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8) (freiwillig)
