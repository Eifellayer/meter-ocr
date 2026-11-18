# AI Meter Reader

[Deutsch](#deutsch) · [English](#english)

## Deutsch

**Version 0.1.0.** Die App liest deinen Zähler lokal aus dem Kamerabild. Sie ist keine geeichte Messung.

### Einrichtung

1. App starten und Weboberfläche öffnen. Der Einrichtungsassistent führt in vier Schritten durch Bildquelle, Zähleranzeige, Bildausschnitt und Hinweise.
2. **Bildquelle:** ESPHome- oder Home-Assistant-Kamera, AI on the Edge / SLFork oder **ESP nur als Kamera** (die App holt nur das Bild und liest selbst).
3. **Selbsteinrichtung:** Die App sucht den Ziffernbereich und bestätigt ihn an mehreren Bildern. Sind sieben Ziffern sicher, läuft die Automatik. Die achte Stelle stimmt sie im Hintergrund fein ab („Optimierung läuft“, mit Höchstdauer).
4. Passt der automatisch gefundene Rahmen nicht, kannst du ihn im Assistenten selbst ziehen.

### Bedienung

- **Übersicht:** Zählerstand, Status, letzte und nächste Prüfung, Verbrauch der letzten 24 Stunden.
- **Einstellungen:** Prüfintervall, Vergleichsgenauigkeit, maximaler Durchfluss, Benachrichtigungen.
- **Werkzeuge:** manueller Test mit dem aktuellen Bild und abweichendem Bildausschnitt.
- **Automatik pausieren** hält die Prüfungen an; die Pause übersteht Neustarts.

### Plausibilität

- Jede Prüfung wird mit einem zweiten Bild bestätigt.
- Sprünge über dem maximalen Durchfluss (Standard 6 m³/h, nach Qmax des Zählers einstellen) werden verworfen.
- Ein einzelner niedrigerer Wert wird verworfen. Zeigen mindestens drei Ablesungen über 15 Minuten stimmig einen niedrigeren Stand, übernimmt die App ihn, ohne negativen oder doppelten Verbrauch zu buchen.

### Home Assistant

| Entität | Inhalt |
| --- | --- |
| `sensor.rf1_ocr_zaehlerstand` | erkannter Zählerstand |
| `sensor.rf1_verbrauch_gesamt` | Gesamtverbrauch für das Energie-Dashboard (als Gas auswählen) |
| `sensor.rf1_pruefstatus` | Ergebnis der letzten Prüfung |
| `sensor.rf1_kontrollbild` | letztes Kontrollbild |

Nach einem App-Update oder Neustart lädt die geöffnete Weboberfläche selbst neu. Ist die App nicht erreichbar, steht „Nicht aktuell“ am Zählerstand.

## English

**Version 0.1.0.** The app reads your meter locally from a camera image. It is not a certified measurement.

### Setup

1. Start the app and open the web UI. The setup wizard guides you through image source, meter display, crop and alerts in four steps.
2. **Image source:** ESPHome or Home Assistant camera, AI on the Edge / SLFork, or **ESP as camera only** (the app only fetches the image and reads it itself).
3. **Automatic setup:** the app finds the digit area and confirms it on several images. Once seven digits are certain, automatic checks run. The eighth digit is fine-tuned in the background ("Optimisation running", with a maximum duration).
4. If the detected frame is wrong, draw it yourself in the wizard.

### Using the app

- **Overview:** reading, status, last and next check, consumption of the last 24 hours.
- **Settings:** check interval, comparison precision, maximum flow, notifications.
- **Tools:** manual test with the current image and a different crop.
- **Pause automatic checks** stops scheduled checks; the pause survives restarts.

### Plausibility

- Every check is confirmed with a second image.
- Jumps above the maximum flow (default 6 m³/h, set it to the meter's Qmax) are rejected.
- A single lower reading is rejected. If at least three consistent readings over 15 minutes show a lower value, the app accepts it without booking negative or duplicate consumption.

### Home Assistant

| Entity | Content |
| --- | --- |
| `sensor.rf1_ocr_zaehlerstand` | recognised meter reading |
| `sensor.rf1_verbrauch_gesamt` | total consumption for the Energy dashboard (select as gas) |
| `sensor.rf1_pruefstatus` | result of the last check |
| `sensor.rf1_kontrollbild` | latest control image |

After an app update or restart, an open web UI reloads itself. If the app cannot be reached, the reading shows "Not current".

---

[GNU GPLv3 or later](../LICENSE) · [Issues](https://github.com/Eifellayer/meter-ocr/issues)
