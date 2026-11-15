# Changelog

## In Vorbereitung

- Beim ersten Einrichten wählst du die Bildquelle selbst. Der Assistent erklärt die drei Modi direkt neben der Auswahl und empfiehlt ESPHome für den Einstieg mit einer Kamera.

## 0.4.3 Alpha

- Bei drei Nachkommastellen erklärt die Einrichtung, warum die letzte Stelle Fehlmeldungen verursachen kann.
- Scheitert die automatische Prüfung bei drei verschiedenen Bildern nur an der dritten Stelle, kann sie mit gelbem Hinweis bestehen. Für den Verbrauch verwendet die App den Vergleichswert, wenn er die Plausibilitätsprüfung besteht.
- Der optionale Präzisionsmodus verlangt weiterhin, dass alle drei Nachkommastellen stimmen.
- Bei Fehlprüfungen zeigt der Countdown die tatsächliche Wartezeit. Ein separater manueller Test verschiebt einen laufenden automatischen Wiederholungsversuch nur, wenn er den Fehler auflöst.

## 0.4.2 Alpha

- Statusabfrage und Anzeige des letzten Zählerbilds korrigiert. Fehlt die markierte Vorschau, zeigt die App das Originalbild.
- Die Übersicht erklärt sofort, wenn Ablesung und Vergleichswert voneinander abweichen und was zu prüfen ist.
- Nach der Einrichtung startet die automatische Prüfung sofort. Die Übersicht zeigt in Gelb, auf welches Bild die App wartet und wie weit die OCR ist. Fehlt ein aktuelles Bild, bleibt ein gelber Hinweis sichtbar.
- Der Werkreset zeigt die Wartezeit an. Sobald er fertig ist, sind auch der letzte manuelle Test und seine Vorschau aus der Oberfläche entfernt, und der Einrichtungsassistent öffnet sich.

## 0.4.1 Alpha

- Bei einem abgebrochenen SLFork-Messzyklus oder einem fehlenden oder zu alten Bild prüft die App ein frisches Rohbild vom ESP.
- Gelingt die Ablesung, weist die App auf die Bildausrichtung als mögliche Ursache hin. Der Rohbildstand wird ohne ESP-Abgleich angezeigt und verändert die Verbrauchssumme nicht.

## 0.4.0 Alpha

- Retry automatic failures using up to three image checks: the first retry after five minutes, the second after another five minutes, then a one-hour wait for a higher meter reading or a new image.
- Show the failed-check count and retry/wait explanation in the automatic overview.
- Mark OCR digits yellow when repeated reads disagree or the final result was composed from multiple attempts; keep red for unresolved digits and green for recognized digits.
- Rename the shared image area to **Latest test image / Letztes Testbild** because it can show either an automatic or manual test.
- Refresh automatic app-language selection when the Home Assistant profile language changes, and avoid a red offline message for a single status-poll failure.
- Add a German illustrated user guide PDF and link it from the project and app descriptions.
- Preserve existing Home Assistant entity IDs, settings, and application slug.

## 0.3.1 Alpha

- Renamed the user-facing app to AI Meter Reader while preserving the Home Assistant app slug, stored options, and existing entity IDs.
- Added up to ten bounded extra OCR variants after an uncertain automatic reading (15 attempts maximum) and strict-majority digit composition.
- Capture a fresh ESP or Home Assistant camera image after the first failed check; after two failed runs, return to the selected interval.
- Added a persistent pause/resume control for automatic checks, with manual tests still available while paused.
- Show live worker activity, source reachability, and clear reasons for stale images or failed image retrieval.
- Successful manual tests restart the automatic timer; a pass for the same capture and reference can clear a reading mismatch, but not a stale-image or connection failure.
- Added German and English help text for retries, pausing, source status, and shorter intervals.

## 0.3.0 Alpha

- After setup, open the manual test directly and allow a JPG/PNG test image upload up to 3 MB.
- Saving automatic settings starts a new automatic check immediately.
- After the configured OCR attempts, combine digits only when each required position has a strict majority vote; otherwise keep the reading uncertain.
- Verify crop recovery against synthetic meter images at 0°, 90°, 180°, and 270°.
- Keep uploaded test photos out of saved settings and automatic measurement history.

## 0.2.1 Alpha

- Added quick Home Assistant dashboard and Energy dashboard guidance to the setup wizard.
- Decimal comparisons round half up to the selected precision, including carry between digits.
- Wait longer for Home Assistant profile language before showing the first setup screen.
- Moved the voluntary PayPal link into the collapsible About section.
- Kept existing entity IDs, stored settings, and the Alpha release channel.

## 0.2.0 Alpha

## 0.2.0 Alpha

**AI Meter Reader – Alpha release.** Version 0.4.0 remains on the regular Alpha channel. After 0.4, the optional Hall / pulse sensor integration is planned as the first separate Beta change because it needs hardware testing.

- Guided first setup for SLFork / AI on the Edge, Home Assistant cameras, and ESPHome cameras with local OCR. The wizard can be reopened later and shows current values for quick changes.
- Meter format settings for whole and fractional digits, display type, comparison precision, crop, rotation, lighting, OCR attempts, check interval and plausibility limit.
- Optional initial fallback reading with timestamp, plus a per-test fallback value. Manual tests now retain their settings and a successful test restarts the automatic timer.
- Live camera checks capture fresh snapshots with up to 10 attempts within 20 seconds. The manual test shows the original source image, annotated OCR preview, or a clear no-image message.
- OCR processing adds lighting correction for uneven illumination. ESP fallback readings are checked against their last valid timestamp and configured flow limit before being accepted.
- Plausible confirmed readings update an increasing total-consumption sensor. Existing `sensor.rf1_*` entity IDs, app slug and media path remain unchanged.
- The overview keeps automatic status separate from manual diagnostics. Help text, language selection, notifications and the setup flow are available in German and English.
- Only AI on the Edge / SLFork has been tested by the maintainer with a real meter. Other camera and meter modes have simulated tests only.

## 0.1.0 Alpha

- Initial Home Assistant app release with local Tesseract OCR verification for AI on the Edge / SLFork meter images.
