# Rückblick: Entwicklung bis zum Neustart als 0.1.0

Am 18. November 2026 wurde die Versionierung auf 0.1.0 zurückgesetzt und die Git-Historie neu begonnen. Die alte Historie (516 Commits, alle Branches bis 0.6.12) liegt beim Maintainer als Git-Bundle vor. Diese Seite fasst zusammen, was bis dahin entstanden ist.

## Ausgangslage

Der Gaszähler wurde zunächst mit einem ESP32-CAM und **AI on the Edge / SLFork** abgelesen. Dessen Werte waren nicht immer verlässlich, daher entstand eine Home-Assistant-App, die das Kamerabild selbst mit Tesseract liest und gegen den ESP-Wert prüft. Später wurde der ESP nur noch als Kamera genutzt („ESP nur als Kamera“); die App liest seitdem eigenständig.

## Etappen

| Alte Versionen | Ergebnis |
| --- | --- |
| 0.1–0.4 (Alpha) | OCR mit festem Bildausschnitt, Vergleich mit SLFork, Mehrfachversuche, manueller Test mit markierten Ziffern, Home-Assistant-Kameras und Referenzsensoren als Quelle. |
| 0.5.x | Selbsteinrichtung mit Live-Vorschau, Einzelrahmen pro Ziffer und Drehung, Einrichtungsassistent, Benachrichtigungen, Deutsch/Englisch, Verbrauch nach Stunde und Tag, Energie-Dashboard-Sensor. |
| 0.6.0–0.6.6 | Feste Prüfintervalle mit Wartezeiten nach Fehlversuchen, Einzelrahmen-Nachprüfung, Winkelkorrektur, Demo ohne Kamera, Reset mit Erhalt der Verbrauchsstatistik. |
| 0.6.7–0.6.9 | Einrichtung wird nach sieben sicheren Ziffern gespeichert; die achte Stelle wird im Hintergrund gesucht. Eine unklare siebte Ziffer kann mit Referenz kurz überbrückt werden. |
| 0.6.10–0.6.11 | Neue Oberfläche (Zählwerk-Anzeige, Status-Chip, 24-Stunden-Diagramm, Reiter Übersicht/Einstellungen/Werkzeuge), führende Stellen werden aus dem bestätigten Stand ergänzt. |
| 0.6.12 | Selbstkorrektur nach einem zu hohen Lesefehler, ohne negativen oder doppelten Verbrauch. |

## Erkenntnisse

- Die letzte Rolle (dritte Nachkommastelle) ist wegen Bewegung und Spiegelungen oft unlesbar; deshalb reicht für die Einrichtung eine sichere siebte Stelle.
- Ein Kamerabild ist ehrlich, die OCR nicht immer: Prüfungen werden mit einem zweiten Bild bestätigt, und Sprünge über dem maximalen Durchfluss werden verworfen.
- Öffentliche Fotos fremder Zähler (Wikimedia, AI-on-the-Edge-Forum) ließen sich mit der damaligen Auswertung kaum lesen; verlässlich getestet ist bisher nur der eigene Gaszähler.
- Entwickelt wurde mit KI-Unterstützung (zuerst ChatGPT/Codex, später Claude). Dabei entstanden viele kleine Releases und sehr ausführliche Texte; der Neustart bündelt das.
