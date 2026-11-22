# Roadmap

Stand: November 2026 · Version **0.5.25**

AI Meter Reader liest mechanische Zähler (zuerst Gaszähler) über ein Kamerabild aus – lokal, ohne Cloud. Leitbild ist „Fire and Forget“: Zähler und Kamera auswählen, alles andere erledigt die App selbst und zeigt Unsicherheit offen an.

Erledigtes steht im [Changelog](rf1_ocr_test/CHANGELOG.md), die Zeit vor 0.1.0 im [Rückblick](docs/HISTORY.md). Rückmeldungen und Wünsche gern als [Issue](https://github.com/Eifellayer/meter-ocr/issues).

## Als Nächstes

| Vorhaben | Worum es geht |
| --- | --- |
| **Zählerkamera ausbauen** | Seit 0.5.24 gibt es fertige Firmware mit Installer für vier Boards, seit 0.5.25 fügt der Assistent die neue Kamera selbst in Home Assistant hinzu. Als Nächstes: Rückmeldungen zu XIAO und Waveshare, weitere Boards auf Wunsch, Zusätze wie die WLAN-Diagnose direkt im Assistenten ein- und ausschalten. |
| **Verdeckte Ziffern noch robuster** | Nicht lesbare Nachkommastellen notfalls plausibel aus Zählerstand und Durchfluss schätzen (nie volle Kubikmeter). Seit 0.5.19 misst die App im Schattenmodus, wie gut das ginge. |
| **Schnellere Einrichtung** | Rahmen zuerst danach vorsortieren, ob in jedem Feld eine Ziffer sitzt, und nur die besten Kandidaten aufwendig lesen. |
| **Oberfläche im Smartphone-Stil** | Einstellungen als gruppierte Listen mit großen Tippflächen und weichen Übergängen, wie bei aktuellen Smartphone-Oberflächen. |
| **Licht und Kamera** | Lichttest in der Einrichtung, optional externe LED, Kamera-Diagnose direkt in der App. |
| **Stillstand erkennen** | Steht der Zähler, Prüfungen sparen – erkannt per Bildvergleich der Rollen. |

## Mit der ESPHome-Kamera

- Test mit höherer Auflösung und anderen Kameramodulen.
- LED-Steuerung: Licht nur für die Aufnahme ein- und danach sicher wieder ausschalten.

## Ziel Version 1.0

1.0 kommt erst, wenn die App wirklich fertig ist:

- **Jeder Zähler:** gängige mechanische Zähler (Gas, Wasser, Strom-Ferraris) mit Vor- und Nachkommastellen, roten und schwarzen Rollen, hellen und dunklen Ziffern, Zeigerstellen bei Wasserzählern.
- **Jede Kamera:** ESPHome-Kamera, AI-on-the-Edge-ESP, beliebige Home-Assistant-Kamera, USB- oder Pi-Kamera.
- **Widrige Umstände:** Schräglage, Perspektive, Spiegelungen und Lichtreflexe, Unschärfe, schwaches oder wechselndes Licht – die App erkennt und korrigiert das selbst.
- **Plattformen:** derselbe Kern als Home-Assistant-App und eigenständig per Container (Raspberry Pi ab Zero 2 W, NAS, Mini-PC); später optional als ESPHome-Komponente direkt auf einem ESP32-S3.
- **Qualität:** höchstens 10 % fehlgeschlagene Prüfungen, keine sicheren Fehllesungen, Selbstheilung bei verschobener Kamera, verständliche Oberfläche auf Deutsch und Englisch, Rückmeldungen mehrerer Nutzer mit unterschiedlichen Zählern eingearbeitet.

## Später

- Mehrere Zähler mit eigener Quelle, eigenen Rahmen und eigener Historie.
- Hallsensor oder Impulszähler über ESPHome als Kontrollquelle.
- Kleines Ziffernnetz als Alternative zu Tesseract.
- Weitere Zählertypen, zum Beispiel Digitalanzeigen, nach praktischen Tests.

## Regeln

- App-Slug `rf1_ocr_test` und die `rf1_*`-Entitäten bleiben gleich, damit Dashboards und Energie-Statistik weiterlaufen.
- Nur stabile Releases; jede Änderung über Branch, Pull Request und grüne Prüftests.
- Größere Verhaltensänderungen kommen zuerst als Schattenmodus (liest nur mit), bevor sie wirken.
- Keine echten Zählerbilder im Repository; Tests nutzen ausgeschnittene Ziffernstreifen oder künstliche Bilder.
