# Gaszähler OCR-Kontrolle / Gas Meter OCR Verification

Deutsch: [Vollständige Anleitung](../README.md) · [Deutsch – App](README.md)

English: [Full documentation](../README.en.md) · [English – App](README.en.md)

## Deutsch

Diese App überprüft den automatisch ausgelesenen mechanischen Gaszähler mit einer **zweiten lokalen OCR-Auswertung des vorhandenen Kamerabilds**. Sie ist keine geeichte Messung.

1. Richte die `esp_url` für den SLFork-ESP ein oder wähle eine Home-Assistant-Kamera (`kamera_entitaet`) und optional einen Referenzsensor (`referenz_entitaet`).
2. Starte die App und öffne ihre Weboberfläche.
3. Wähle bei Bedarf oben **Sprache / Language**.
4. Unter **Automatische Prüfung – Einstellungen** stellst du die Vergleichsgenauigkeit, OCR-Versuche, Ziffernfarbe und den Bildbereich dauerhaft ein.
5. Öffne **Manuellen Test öffnen** für eine Probe mit dem letzten Bild. Dort findest du OCR-Einzelwerte, die farbig umrandeten Ziffern und die Möglichkeit, einen getesteten Bildausschnitt für die Automatik zu übernehmen.

Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` bleiben unverändert. Support: [GitHub Issues](https://github.com/Thunder86/rf1-kontrollmessung/issues).

## English

The app performs an **independent local OCR reading of your most recent gas meter image** and checks it against the reference reading from SLFork or a Home Assistant sensor. It is not a certified meter.

1. Enter the SLFork ESP URL in `esp_url`, or configure a Home Assistant camera (`kamera_entitaet`) and optional reference sensor (`referenz_entitaet`).
2. Start the app and open its web interface.
3. Use **Sprache / Language** at the top to select English.
4. Under **Automatic checks – settings**, save the comparison precision, maximum OCR attempts, digit color, and image crop. These settings persist across restarts.
5. Expand **Open manual test** when you need to troubleshoot an image. The annotated preview shows green boxes for recognized digits and red for uncertain ones; **More details** lists each OCR attempt. A tested custom crop can be saved for automatic checks.

The entity IDs `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus` do not change when switching language.

For full setup, explanation of comparison rules, schedules and troubleshooting, consult the [English guide](../README.en.md). For help or bug reports, open a [GitHub issue](https://github.com/Thunder86/rf1-kontrollmessung/issues).

---

Private, free hobby project. Optional [PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are not required.
