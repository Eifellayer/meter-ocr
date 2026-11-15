# Meter OCR

Deutsch: [Vollständige Anleitung](../README.md) · [Deutsch – App](README.md)

English: [Full documentation](../README.en.md) · [English – App](README.en.md)

## Deutsch

Diese App überprüft den automatisch ausgelesenen mechanischen Gaszähler mit **lokaler OCR** und kann den gelesenen Stand mit einem Referenzwert abgleichen. Sie ist keine geeichte Messung.

1. Richte die `esp_url` für den SLFork-ESP ein oder wähle eine Home-Assistant-Kamera (`kamera_entitaet`) und optional einen Referenzsensor (`referenz_entitaet`).
2. Starte die App, öffne ihre Weboberfläche und wähle unter **Bildquelle** den Betriebsmodus. ESPHome-Kameras können Bilder für die lokale OCR ohne SLFork liefern.
3. Unter **Sprache / Language** kannst du die Home-Assistant-Profilsprache übernehmen oder Deutsch bzw. Englisch wählen.
4. Unter **Einstellungen → Automatische Prüfung** legst du Prüfintervall, Vergleichsgenauigkeit, OCR-Versuche, Ziffernfarbe und Bildbereich fest.
5. Wähle **Test starten** für eine Probe mit dem letzten Bild. **Testeinstellungen** öffnet die Eingaben für einen individuellen Test. Im Ergebnis kannst du einen geprüften Ausschnitt für die Automatik übernehmen.

Unter **Benachrichtigungen** lassen sich Hinweis, Companion-Push und E-Mail konfigurieren. Für das Energie-Dashboard stellst du den maximalen Durchfluss nach Qmax ein und wählst `sensor.rf1_verbrauch_gesamt` als Gasverbrauch. [Plausibilitätsprüfung und Energie-Dashboard](../README.md#plausibilitätsprüfung-und-energie-dashboard)

Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` bleiben unverändert. Support: [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues).

## English

The app performs an **independent local OCR reading of your most recent gas meter image** and can check it against a reference reading from SLFork or a Home Assistant sensor. It is not a certified meter.

1. Enter the SLFork ESP URL in `esp_url`, or configure a Home Assistant camera (`kamera_entitaet`) and optional reference sensor (`referenz_entitaet`).
2. Start the app and choose a mode under **Image source**. An ESPHome camera can provide images for local OCR without SLFork.
3. Use **Sprache / Language** to follow your Home Assistant profile or select German or English.
4. Under **Settings → Automatic checks**, save the check interval, comparison precision, maximum OCR attempts, digit color and image crop.
5. Select **Start test** to check the latest image. **Test settings** lets you adjust the crop or other test options. You can save a tested crop for automatic checks.

Under **Notifications**, configure Home Assistant notices, Companion push or email. Set maximum flow to the meter's Qmax and select `sensor.rf1_verbrauch_gesamt` as gas consumption in the Energy dashboard. [Plausibility check and Energy dashboard](../README.en.md#plausibility-check-and-energy-dashboard)

The entity IDs `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus` do not change when switching language.

For full setup, explanation of comparison rules, schedules and troubleshooting, consult the [English guide](../README.en.md). For help or bug reports, open a [GitHub issue](https://github.com/Eifellayer/meter-ocr/issues).

---

Private, free hobby project. Optional [PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are not required.
