# AI Meter Reader

**Version 0.5.6** · [English](README.en.md) · [Anleitung](rf1_ocr_test/DOCS.md) · [Änderungen](rf1_ocr_test/CHANGELOG.md) · [Roadmap](RELEASE-PLAN.md)

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
- Sind drei Nachkommastellen eingestellt, aber nur sieben Ziffern bestätigt, zeigt die App **3 eingestellt / 2 vorläufig verglichen** und wiederholt die Suche nach der achten Ziffer auch nach Neustarts.
- Stellt `sensor.rf1_ocr_zaehlerstand` und `sensor.rf1_verbrauch_gesamt` (Energie-Dashboard) bereit.
- Optional: Abgleich mit einem vorhandenen Sensor, Benachrichtigungen, Demo ohne Kamera.

## Prüfrhythmus

| Situation | Nächste Prüfung |
| --- | --- |
| Erfolgreiche Prüfung | eingestelltes Intervall, standardmäßig 10 Minuten |
| 1. oder 2. Fehlprüfung | 2 Minuten bei freier Rechenleistung, sonst 5 Minuten |
| Nur die 7. Ziffer unsicher, Rest per Referenz bestätigt | 30 Minuten |
| 3 Fehlprüfungen in Folge | Pause, einstellbar, Standard 30 Minuten (keine Pause, wenn nur die letzte Rolle unklar ist) |

## Getestet

Praktisch erprobt ist die App bisher nur an **einem Gaszähler** (Rollenzählwerk, ESP32-CAM mit AI on the Edge als Kamera). Wasserzähler und andere Gaszähler sind nicht praktisch getestet; ein Test mit öffentlichen Ziffernbildern verschiedener Wasser- und Gaszähler zeigte, dass fremde Zählwerke deutlich schlechter gelesen werden (unklare Stellen meldet die App, statt zu raten). Rückmeldungen mit eigenen Zählern sind sehr willkommen.

## Hinweise

Die OCR ist keine geeichte Messung; für Abrechnungen gilt der Stand am Gerät. Fehler und Ideen bitte als [GitHub Issue](https://github.com/Eifellayer/meter-ocr/issues) (ohne Zugangsdaten oder private Fotos) oder per E-Mail an [amr@eifel-layer.de](mailto:amr@eifel-layer.de). Beta-Tester mit anderen Zählern sind willkommen. Lizenz: [GNU GPLv3 oder später](LICENSE), Drittsoftware siehe [SOURCES.md](SOURCES.md). Wie das Projekt entstanden ist: [Rückblick](docs/HISTORY.md).

[Projekt unterstützen](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8) (freiwillig)
