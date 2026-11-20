# AI Meter Reader

[Deutsch](#deutsch) · [English](#english)

## Deutsch

**Version 0.2.9.** Die App liest deinen Zähler lokal aus dem Kamerabild. Sie ist keine geeichte Messung.

### Einrichtung

1. App starten und Weboberfläche öffnen. Der Einrichtungsassistent führt in vier Schritten durch Bildquelle, Zähleranzeige, Bildausschnitt und Hinweise.
2. **Bildquelle:** ESPHome- oder Home-Assistant-Kamera, AI on the Edge / SLFork oder **ESP nur als Kamera** (die App holt nur das Bild und liest selbst).
3. **Selbsteinrichtung:** Die App sucht den Ziffernbereich und bestätigt ihn an mehreren Bildern. Sind sieben Ziffern sicher, läuft die Automatik. Die achte Stelle stimmt sie im Hintergrund fein ab („Optimierung läuft“, mit Höchstdauer).
4. Passt der automatisch gefundene Rahmen nicht, kannst du ihn im Assistenten selbst ziehen.

Wenn **3 Nachkommastellen** eingestellt sind, aber nach der Einrichtung zunächst nur sieben Ziffern bestätigt werden, arbeitet die normale Prüfung vorläufig mit **2 Nachkommastellen**. Das ist keine Änderung der gespeicherten Einstellung. Die sieben bestätigten Ziffern werden dabei exakt **ohne Rundung** mit der Referenz verglichen, sodass eine unbekannte achte Ziffer nicht zu einem Fehlvergleich führt. Die Übersicht kennzeichnet den offenen achten Wert; die separate Hintergrundsuche startet nach Neustarts und nach erfolglosen Versuchen erneut (mit mindestens einer Stunde Abstand zwischen Starts). Die bisher bestätigte siebenstellige Ablesung und die Verbrauchsstatistik bleiben erhalten. Die dritte Nachkommastelle gilt erst nach erfolgreicher Gegenprüfung als bestätigt.

### Bedienung

- **Übersicht:** Zählerstand, Status, letzte und nächste Prüfung, Verbrauch der letzten 24 Stunden.
- **Einstellungen:** Prüfintervall, Vergleichsgenauigkeit, maximaler Durchfluss, Benachrichtigungen.
- **Werkzeuge:** manueller Test mit dem aktuellen Bild und abweichendem Bildausschnitt.
- **Automatik pausieren** hält die Prüfungen an; die Pause übersteht Neustarts.

### Genauigkeit

Standard sind 2 Nachkommastellen. Die dritte Nachkommastelle vergleicht die App nur mit eingeschaltetem **Präzisionsmodus**; er ist experimentell, weil die schnell laufende letzte Rolle oft nicht sicher erkannt wird. Dreht sich die letzte verglichene Rolle gerade, bestätigt sie die Prüfung einmalig mit einer Stelle weniger, statt sie scheitern zu lassen. Ist dieselbe Stelle mehrmals hintereinander unklar, sitzt vermutlich ihr Rahmen neben der Rolle: Die App meldet das und sucht den Rahmen der 8. Ziffer im Hintergrund neu.

Praktisch getestet ist bisher nur ein Gaszähler; Wasserzähler sind ungetestet.

### Plausibilität

- Jede Prüfung wird mit einem zweiten Bild bestätigt.
- Der letzte bestätigte Stand dient als Lesehilfe: Vorkommastellen, die danach unmöglich sind (z. B. eine 8, die als 6 gelesen wird), zählen nicht.
- Die Bilddrehung lässt sich in 0,1°-Schritten einstellen. Bei manuellem Ausschnitt bestimmt die Selbsteinrichtung den Feinwinkel gleich mit, und die App misst die Schräglage der Ziffernreihe danach bei jeder Prüfung und gleicht sie aus, sobald mehrere Messungen übereinstimmen (höchstens ±2°).
- Bleiben nach den OCR-Versuchen bis zu drei Ziffern unklar, verschiebt die App nur deren Rahmen leicht und liest sie neu (höchstens 10 zusätzliche Einzelziffer-Lesungen).
- Sprünge über dem maximalen Durchfluss (Standard 6 m³/h, nach Qmax des Zählers einstellen) werden verworfen.
- Ein einzelner niedrigerer Wert wird verworfen. Zeigen mindestens drei Ablesungen über 15 Minuten stimmig einen niedrigeren Stand, übernimmt die App ihn, ohne negativen oder doppelten Verbrauch zu buchen.

### ESPHome-Kamera mit Blitz (ESP32-CAM)

Im ESPHome Device Builder ein neues ESP32-Gerät anlegen (WLAN, API und OTA erzeugt der Assistent), dann diesen Teil ergänzen. `max_power: 60%` verhindert Neustarts durch die helle LED und mindert Spiegelungen. In der App als Bildquelle **ESPHome-/Home-Assistant-Kamera** wählen und unter **Licht für die Aufnahme** die Blitz-Entität eintragen: Die App schaltet sie wie AI on the Edge kurz ein (1,5 Sekunden), holt das Bild und schaltet sie wieder aus.

```yaml
esp32:
  board: esp32cam

esp32_camera:
  name: Gaszähler
  external_clock:
    pin: GPIO0
    frequency: 20MHz
  i2c_pins:
    sda: GPIO26
    scl: GPIO27
  data_pins: [GPIO5, GPIO18, GPIO19, GPIO21, GPIO36, GPIO39, GPIO34, GPIO35]
  vsync_pin: GPIO25
  href_pin: GPIO23
  pixel_clock_pin: GPIO22
  power_down_pin: GPIO32
  resolution: 800x600
  jpeg_quality: 10
  max_framerate: 2 fps
  idle_framerate: 1 fps
  vertical_flip: false
  horizontal_mirror: true

output:
  - platform: ledc
    pin: GPIO4
    id: blitz_ausgang
    max_power: 60%

light:
  - platform: monochromatic
    id: blitz
    output: blitz_ausgang
    name: Blitz
    restore_mode: ALWAYS_OFF
    default_transition_length: 0s
    on_turn_on:
      - delay: 30s
      - light.turn_off: blitz
```

### Schwierige Bilder, Spiegelungen und Experimente

- **Spiegelung des Blitzes:** Überstrahlt ein Reflex dauerhaft dieselbe Ziffer, erkennt die Selbsteinrichtung das selbst und schließt mit den übrigen Ziffern ab. Die verdeckte Stelle ergänzt die App aus dem letzten bestätigten Stand, wenn nur ein Wert zum maximalen Durchfluss passt. Fehlt ein solcher Stand, bittet die Übersicht einmal um den aktuellen Zählerstand.
- **Experimentelle Funktionen** (Einstellungen → Automatik im Hintergrund verbessern → Experimentelle Funktionen): standardmäßig aus. Angehakte Experimente lesen jedes Bild zusätzlich mit, nur bei freier Rechenleistung; es zählt weiterhin nur das bewährte Ergebnis, beide stehen im Debug-Protokoll (Feld `experiment`). Erstes Experiment: Perspektivkorrektur (Kippung).
- **Fehler melden** (Werkzeuge → Debug-Protokoll, und im Hinweis bei wiederholten Fehlprüfungen): öffnet ein vorausgefülltes GitHub-Formular ohne private Daten. Das Debug-Protokoll hängst du selbst an.

### Home Assistant

| Entität | Inhalt |
| --- | --- |
| `sensor.rf1_ocr_zaehlerstand` | erkannter Zählerstand |
| `sensor.rf1_verbrauch_gesamt` | Gesamtverbrauch für das Energie-Dashboard (als Gas auswählen) |
| `sensor.rf1_verbrauch_gesamt_kwh` | Gesamtverbrauch in kWh, wenn Zustandszahl und Brennwert oder der Umrechnungsfaktor eingetragen sind |
| `sensor.rf1_pruefstatus` | Ergebnis der letzten Prüfung |
| `sensor.rf1_kontrollbild` | letztes Kontrollbild |

Nach einem App-Update oder Neustart lädt die geöffnete Weboberfläche selbst neu. Ist die App nicht erreichbar, steht „Nicht aktuell“ am Zählerstand.

## English

**Version 0.2.9.** The app reads your meter locally from a camera image. It is not a certified measurement.

### Setup

1. Start the app and open the web UI. The setup wizard guides you through image source, meter display, crop and alerts in four steps.
2. **Image source:** ESPHome or Home Assistant camera, AI on the Edge / SLFork, or **ESP as camera only** (the app only fetches the image and reads it itself).
3. **Automatic setup:** the app finds the digit area and confirms it on several images. Once seven digits are certain, automatic checks run. The eighth digit is fine-tuned in the background ("Optimisation running", with a maximum duration).
4. If the detected frame is wrong, draw it yourself in the wizard.

When **3 decimal places** are configured but the setup has only confirmed seven digits, routine checks temporarily compare **2 decimal places**. The saved setting is not changed. The seven verified digits are compared with the reference **without rounding** by the unknown eighth digit. The overview marks the eighth digit as unconfirmed, and the separate background search resumes after restarts and unsuccessful runs (at least one hour between starts). Previously verified seven-digit readings and consumption history remain intact. The third decimal place becomes verified only after a successful cross-check.

### Using the app

- **Overview:** reading, status, last and next check, consumption of the last 24 hours.
- **Settings:** check interval, comparison precision, maximum flow, notifications.
- **Tools:** manual test with the current image and a different crop.
- **Pause automatic checks** stops scheduled checks; the pause survives restarts.

### Precision

By default two decimal places are compared. The third one is compared only with **precision mode** switched on; it is experimental because the fast-moving last roller is often not recognised reliably. If the last compared roller is turning, the app confirms that one check with one decimal place less instead of failing it. If the same digit stays unclear several times in a row, its frame probably sits beside the roller: the app says so and searches the eighth digit's frame again in the background.

So far only one gas meter has been tested in practice; water meters are untested.

### Plausibility

- Every check is confirmed with a second image.
- The last confirmed reading helps reading: whole-number digits that are impossible after it (e.g. an 8 read as 6) do not count.
- Image rotation can be set in 0.1° steps. With a manual crop automatic setup determines the fine angle right away, and the app then measures the tilt of the digit row on every check and corrects it once several measurements agree (at most ±2°).
- If up to three digits stay unclear after the OCR attempts, the app nudges only their frames and reads them again (at most 10 extra single-digit reads).
- Jumps above the maximum flow (default 6 m³/h, set it to the meter's Qmax) are rejected.
- A single lower reading is rejected. If at least three consistent readings over 15 minutes show a lower value, the app accepts it without booking negative or duplicate consumption.

### ESPHome camera with flash (ESP32-CAM)

Create a new ESP32 device in the ESPHome Device Builder (the wizard creates Wi-Fi, API and OTA settings), then add this part. `max_power: 60%` prevents resets caused by the bright LED and reduces glare. In the app choose **ESPHome / Home Assistant camera** as image source and enter the flash entity under **Light for the picture**: like AI on the Edge, the app switches it on briefly (1.5 seconds), takes the picture and switches it off again.

```yaml
esp32:
  board: esp32cam

esp32_camera:
  name: Gaszähler
  external_clock:
    pin: GPIO0
    frequency: 20MHz
  i2c_pins:
    sda: GPIO26
    scl: GPIO27
  data_pins: [GPIO5, GPIO18, GPIO19, GPIO21, GPIO36, GPIO39, GPIO34, GPIO35]
  vsync_pin: GPIO25
  href_pin: GPIO23
  pixel_clock_pin: GPIO22
  power_down_pin: GPIO32
  resolution: 800x600
  jpeg_quality: 10
  max_framerate: 2 fps
  idle_framerate: 1 fps
  vertical_flip: false
  horizontal_mirror: true

output:
  - platform: ledc
    pin: GPIO4
    id: blitz_ausgang
    max_power: 60%

light:
  - platform: monochromatic
    id: blitz
    output: blitz_ausgang
    name: Blitz
    restore_mode: ALWAYS_OFF
    default_transition_length: 0s
    on_turn_on:
      - delay: 30s
      - light.turn_off: blitz
```

### Difficult images, reflections and experiments

- **Flash reflection:** If a reflection permanently washes out the same digit, automatic setup detects it and finishes with the remaining digits. The app fills the hidden digit from the last confirmed reading when only one value fits the maximum flow. Without such a reading the overview asks once for the current meter reading.
- **Experimental functions** (Settings → Improve automatic checks in the background → Experimental functions): off by default. Ticked experiments read each image additionally, only with spare capacity; only the proven result counts, both are written to the debug log (field `experiment`). First experiment: perspective correction (keystone).
- **Report a problem** (Tools → Debug log, and in the notice after repeated failed checks): opens a prefilled GitHub form without private data. Attach the debug log yourself.

### Home Assistant

| Entity | Content |
| --- | --- |
| `sensor.rf1_ocr_zaehlerstand` | recognised meter reading |
| `sensor.rf1_verbrauch_gesamt` | total consumption for the Energy dashboard (select as gas) |
| `sensor.rf1_verbrauch_gesamt_kwh` | total consumption in kWh once gas state factor and calorific value, or the conversion factor, are set |
| `sensor.rf1_pruefstatus` | result of the last check |
| `sensor.rf1_kontrollbild` | latest control image |

After an app update or restart, an open web UI reloads itself. If the app cannot be reached, the reading shows "Not current".

---

[GNU GPLv3 or later](../LICENSE) · [Issues](https://github.com/Eifellayer/meter-ocr/issues)
