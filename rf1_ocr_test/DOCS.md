# AI Meter Reader

Deutsch: [Vollständige Anleitung](../README.md) · [Deutsch – App](README.md)

English: [Full documentation](../README.en.md) · [English – App](README.en.md)

## Deutsch

Diese App liest Zählerbilder lokal aus und kann den erkannten Stand mit einem Referenzwert abgleichen. Sie ist keine geeichte Messung.

Mit KI-Unterstützung entwickelt. Für Abrechnungen und Meldungen gilt der direkt am Zähler geprüfte Stand. [Hinweise zur Nutzung und Haftung](https://github.com/Eifellayer/meter-ocr#hinweise-zur-nutzung)

1. Richte die `esp_url` für den SLFork-ESP ein oder wähle eine Home-Assistant-Kamera (`kamera_entitaet`) und optional einen Referenzsensor (`referenz_entitaet`).
2. Starte die App, öffne ihre Weboberfläche und wähle unter **Bildquelle** den Betriebsmodus. ESPHome-Kameras können Bilder für die lokale OCR ohne SLFork liefern.
3. Unter **Sprache / Language** kannst du die Home-Assistant-Profilsprache übernehmen oder Deutsch bzw. Englisch wählen.
4. Unter **Automatische Prüfung – Einstellungen** stellst du die Vergleichsgenauigkeit, OCR-Versuche, Ziffernfarbe und den Bildbereich dauerhaft ein.
5. Öffne **Manuellen Test öffnen** für eine Probe mit dem letzten Bild. Dort findest du OCR-Einzelwerte, die farbig umrandeten Ziffern und die Möglichkeit, einen getesteten Bildausschnitt für die Automatik zu übernehmen.

Der Einrichtungsassistent kann jederzeit erneut geöffnet werden. Unter **Benachrichtigungen** lassen sich Hinweis, Companion-Push und E-Mail konfigurieren. Releases bis 0.5 sind Alpha; es gibt keinen separaten Beta-Kanal. Ab 0.5 ist eine Beta größeren Änderungen mit zusätzlichem Testbedarf vorbehalten. Der Maintainer testet reale Zähler ausschließlich mit AI on the Edge / SLFork. Andere Modi sind simuliert getestet. Für das Energie-Dashboard stellst du den maximalen Durchfluss nach Qmax ein und wählst `sensor.rf1_verbrauch_gesamt` als Gasverbrauch. [Plausibilitätsprüfung und Energie-Dashboard](../README.md#plausibilitätsprüfung-und-energie-dashboard)

Über **Automatik pausieren** lassen sich automatische Prüfungen anhalten; manuelle Tests bleiben verfügbar. Der Statusbereich erklärt außerdem Wartezeit, Bildverarbeitung, Quellenverbindung und veraltete Bilder. Die Pause bleibt nach Neustarts erhalten. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` bleiben unverändert. Support: [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues).

## English

The app independently reads the latest meter image locally and can check the result against a reference from SLFork or a Home Assistant sensor. It is not a certified meter.

Developed with AI assistance. Check the physical meter for billing and official readings. [Usage and liability notes](https://github.com/Eifellayer/meter-ocr/blob/main/README.en.md#usage-notes)

1. Enter the SLFork ESP URL in `esp_url`, or configure a Home Assistant camera (`kamera_entitaet`) and optional reference sensor (`referenz_entitaet`).
2. Start the app and choose a mode under **Image source**. An ESPHome camera can provide images for local OCR without SLFork.
3. Use **Sprache / Language** to follow your Home Assistant profile or select German or English.
4. Under **Automatic checks – settings**, save the comparison precision, maximum OCR attempts, digit color, and image crop. These settings persist across restarts.
5. Expand **Open manual test** when you need to troubleshoot an image. The annotated preview shows green boxes for recognized digits and red for uncertain ones; **More details** lists each OCR attempt. A tested custom crop can be saved for automatic checks.

The setup wizard can be reopened at any time. Under **Notifications**, configure Home Assistant notices, Companion push or email. Releases below 0.5 are Alpha with no separate Beta channel. From 0.5 onward, Beta builds are reserved for larger changes that need dedicated testing. The maintainer tests real meters only with AI on the Edge / SLFork; other modes have simulated tests only. Set maximum flow to the meter's Qmax and select `sensor.rf1_verbrauch_gesamt` as gas consumption in the Energy dashboard. [Plausibility check and Energy dashboard](../README.en.md#plausibility-check-and-energy-dashboard)

Pause scheduled checks with **Pause automatic checks**; manual tests remain available. The status area explains waiting, image processing, source connectivity, and stale images. The pause survives restarts. Entity IDs `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus` remain unchanged.

For full setup, explanation of comparison rules, schedules and troubleshooting, consult the [English guide](../README.en.md). For help or bug reports, open a [GitHub issue](https://github.com/Eifellayer/meter-ocr/issues).

---

Private, free hobby project. Optional [PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are not required.
