# Roadmap

Stand: 18. November 2026 · Version **0.1.0**

Ziel: einmal einrichten, danach prüft die App selbstständig und zeigt Unsicherheit offen an. Stabilität geht vor neuen großen Funktionen.

## Als Nächstes

| Aufgabe | Fertig, wenn … |
| --- | --- |
| **Praxis 0.1.0 beobachten** | Neuinstallation und Selbsteinrichtung laufen am echten Zähler; Optimierungs-Anzeige, Neuladen nach Neustart und Assistent auf Handy und Desktop bewährt. |
| **Hinweis zur 8. Ziffer nach der Einrichtung korrigieren** | Wurde nur mit sieben Ziffern eingerichtet, sagt der Hinweis nicht mehr „eingestellt: 2 Nachkommastellen“, sondern dass vorübergehend nur 2 verglichen werden, die eingestellten 3 bleiben und die 8. Ziffer ab etwa einer Stunde nach der Einrichtung im Hintergrund gesucht wird. |
| **Manuelle Korrektur in der Selbsteinrichtung** | Beim Markieren des Rahmens pausiert die Einrichtung; Winkel einstellbar; Ziffernrahmen verschieben und in der Größe ändern; danach geht es mit den korrigierten Rahmen weiter. |
| **Plausibilität nach eigenem Durchschnittsverbrauch** | Große Sprünge zählen nur, wenn sie zum bisherigen Verbrauch passen; bis genug Daten vorliegen, gilt nur der maximale Durchfluss. |
| **Anleitung mit Bildern neu** | Kurze bebilderte Anleitung aus der Demo (keine privaten Zählerfotos). |
| **Einstellungen nachvollziehbar** | Sichtbar, ob ein Wert aus der App-Konfiguration oder aus der Weboberfläche stammt. |
| **Foto-Regressionstests** | Eigene Testbilder mit Sollwerten laufen in GitHub Actions. |

## Mit der ESPHome-Kamera

- Echter Test mit höherer Auflösung am eigenen Zähler (bisher nur simuliert).
- Optionale LED-Steuerung: Licht nur für die Aufnahme ein- und danach sicher wieder ausschalten.

## Später

- Mehrere Zähler mit eigener Quelle, eigenen Rahmen und eigener Historie.
- Hallsensor / Impulszähler über ESPHome als Kontrollquelle.
- Einzelziffern-Klassifikator als Machbarkeitsstudie gegen Tesseract.
- Weitere Zählertypen nach praktischen Tests.

## Regeln

- App-Slug `rf1_ocr_test` und die `rf1_*`-Entitäten bleiben gleich, damit Dashboards und Energie-Statistik weiterlaufen.
- Nur Stable-Releases; jede Änderung über Branch, Pull Request und grüne Prüftests.
- Roadmap und Zwischenstände werden vor jedem größeren Schritt gesichert.
- Erledigtes steht im [Changelog](rf1_ocr_test/CHANGELOG.md), die Zeit vor 0.1.0 im [Rückblick](docs/HISTORY.md).
