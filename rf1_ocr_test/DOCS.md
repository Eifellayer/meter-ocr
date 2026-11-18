# AI Meter Reader

Deutsch: [Schnellstart](../README.md) · [Ausführliche Anleitung](../docs/DETAILS.md) · [Deutsch – App](README.md)

English: [Quick start](../README.en.md) · [Detailed documentation](../docs/DETAILS.en.md) · [English – App](README.en.md)

📘 [Bebilderte Bedienungsanleitung als PDF](../docs/Bedienungsanleitung-AI-Meter-Reader.pdf) - deutscher Schnelleinstieg zu Einrichtung, Bildtest, Status und Dashboard. Die Anleitung wird bei größeren Funktions- oder Ablaufänderungen aktualisiert; kleine Umbenennungen erfordern keine neue Ausgabe.

## Deutsch

Diese App liest Zählerbilder lokal aus und kann den erkannten Stand mit einem Referenzwert abgleichen. Sie ist keine geeichte Messung. Der Projektcode steht unter [GNU GPLv3 oder später](../LICENSE); weitergegebene Bearbeitungen müssen die GPL-Bedingungen für Quellcode und Lizenzhinweise einhalten.

Mit KI-Unterstützung entwickelt. Für Abrechnungen und Meldungen gilt der direkt am Zähler geprüfte Stand. [Hinweise zur Nutzung und Haftung](https://github.com/Eifellayer/meter-ocr#hinweise-zur-nutzung)

1. Richte die `esp_url` für den SLFork-ESP ein oder wähle eine Home-Assistant-Kamera (`kamera_entitaet`) und optional einen Referenzsensor (`referenz_entitaet`).
2. Starte die App, öffne ihre Weboberfläche und wähle unter **Bildquelle** den Betriebsmodus. ESPHome-Kameras können Bilder für die lokale OCR ohne SLFork liefern.
3. Unter **Sprache / Language** kannst du die Home-Assistant-Profilsprache übernehmen oder Deutsch bzw. Englisch wählen.
4. Unter **Automatische Prüfung – Einstellungen** stellst du die Vergleichsgenauigkeit, OCR-Versuche, Ziffernfarbe und den Bildbereich dauerhaft ein.
5. Öffne **Manuellen Test öffnen** für eine Probe mit dem letzten Bild. Dort findest du OCR-Einzelwerte, die farbig umrandeten Ziffern und die Möglichkeit, einen getesteten Bildausschnitt für die Automatik zu übernehmen.

Bei der siebenstelligen Prüfung kann ab 0.6.9 eine ausschließlich unlesbare siebte Ziffer vorübergehend mit einer sicheren Sechs-Ziffern-Teilbestätigung überbrückt werden, wenn die Referenz gültig und die übrigen Stellen mehrheitlich stabil sind. Die App wartet dann **30 Minuten** auf einen höheren Stand und erklärt die Wartezeit; gespeicherte Genauigkeit und Verbrauch bleiben unverändert. Bei Präzisionsmodus oder fehlender verlässlicher Referenz bleibt die reguläre strenge Prüfung bestehen.

**0.6.12 Stable** gliedert die Oberfläche in **Übersicht**, **Einstellungen** und **Werkzeuge**. Den manuellen Test findest du unter Werkzeuge; den Bildausschnitt änderst du dauerhaft unter Einstellungen → Automatische Prüfung. Der Einrichtungsassistent kann jederzeit erneut geöffnet werden. Seit 0.6.8 leitet beim Start der Selbsteinrichtung zur Übersicht weiter, zeigt dort die Einzelschritte und blendet nach dem Speichern von sieben bestätigten Ziffern die anschließende Feinprüfung der achten Ziffer auf einen kurzen Hintergrundhinweis zusammen. Unter **Benachrichtigungen** lassen sich Hinweis, Companion-Push und E-Mail konfigurieren. Langzeit-Feinjustierung und adaptive Intervalle sind zuschaltbar und brauchen Praxistests. Experimentelle Zusatzsensoren sind vorhanden; die vollständige Hallsensor-/Impulszähler-Anbindung bleibt geplant. An einem realen ESP-Gaszähler wurden AI on the Edge / SLFork und **ESP nur als Kamera** getestet; eigenständige ESPHome- und andere Home-Assistant-Kameraquellen sowie andere Zählertypen sind derzeit automatisiert oder simuliert geprüft. Für das Energie-Dashboard stellst du den maximalen Durchfluss nach Qmax ein und wählst `sensor.rf1_verbrauch_gesamt` als Gasverbrauch. [Plausibilitätsprüfung und Energie-Dashboard](../docs/DETAILS.md#plausibilitätsprüfung-und-energie-dashboard)

Über **Automatik pausieren** lassen sich automatische Prüfungen anhalten; manuelle Tests bleiben verfügbar. Der Statusbereich erklärt außerdem Wartezeit, Bildverarbeitung, Quellenverbindung und veraltete Bilder. Die Pause bleibt nach Neustarts erhalten. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` bleiben unverändert. Support: [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues).

## English

The app independently reads the latest meter image locally and can check the result against a reference from SLFork or a Home Assistant sensor. It is not a certified meter.

Developed with AI assistance. Check the physical meter for billing and official readings. [Usage and liability notes](https://github.com/Eifellayer/meter-ocr/blob/main/README.en.md#usage-notes)

1. Enter the SLFork ESP URL in `esp_url`, or configure a Home Assistant camera (`kamera_entitaet`) and optional reference sensor (`referenz_entitaet`).
2. Start the app and choose a mode under **Image source**. An ESPHome camera can provide images for local OCR without SLFork.
3. Use **Sprache / Language** to follow your Home Assistant profile or select German or English.
4. Under **Automatic checks – settings**, save the comparison precision, maximum OCR attempts, digit color, and image crop. These settings persist across restarts.
5. Expand **Open manual test** when you need to troubleshoot an image. The annotated preview shows green boxes for recognized digits and red for uncertain ones; **More details** lists each OCR attempt. A tested custom crop can be saved for automatic checks.

**0.6.12 Stable** organises the interface into **Overview**, **Settings** and **Tools**. The manual test is under Tools; change the image crop permanently under Settings → Automatic check. The setup wizard can be reopened at any time. Since 0.6.8 the app switches to Overview when automatic setup starts, shows the full setup steps, then reduces the optional eighth-digit check to a short background notice once seven digits have been saved. Under **Notifications**, configure Home Assistant notices, Companion push or email. Fine-tuning and adaptive intervals are optional and still need long-term field testing. Experimental extra entities are available, but dedicated hall-sensor/pulse-meter support is still planned. AI on the Edge / SLFork and **ESP as camera only** have been tested on a real ESP/gas meter; independent ESPHome and other camera sources plus other meter types currently have automated or simulated coverage. Set maximum flow to the meter's Qmax and select `sensor.rf1_verbrauch_gesamt` as gas consumption in the Energy dashboard. [Plausibility check and Energy dashboard](../docs/DETAILS.en.md#plausibility-check-and-energy-dashboard)

Pause scheduled checks with **Pause automatic checks**; manual tests remain available. The status area explains waiting, image processing, source connectivity, and stale images. The pause survives restarts. Entity IDs `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus` remain unchanged.

For full setup, comparison rules, schedules and troubleshooting, consult the [English detailed guide](../docs/DETAILS.en.md). For help or bug reports, open a [GitHub issue](https://github.com/Eifellayer/meter-ocr/issues).

---

Free and open-source hobby project, licensed under [GNU GPLv3 or later](../LICENSE). Optional [PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are not required.

## Factory Reset mit Erhalt der Verbrauchsstatistik

Unter **App-Daten zurücksetzen** stehen zwei Schaltflächen: Der bisherige vollständige Reset löscht auch die Statistik. **Factory Reset – Statistik behalten** entfernt Einstellungen, Bildquelle, Kalibrierungen, Prüfdetails und Testbilder, erhält jedoch den kumulierten Verbrauch sowie die gespeicherten Zählerstands-/Verbrauchsstatistiken. Für experimentelle Zusatzsensoren bleiben die bisherigen Messdaten gespeichert; die Überwachung muss danach erneut eingerichtet werden. Nach dem Reset ist eine erneute Einrichtung erforderlich. Bei einer anderen Bildquelle wird kein Verbrauch für den Quellenwechsel erfunden. Home-Assistant-Entitätsnamen und bestehende Langzeitstatistik im Home-Assistant-Recorder werden nicht verändert.
