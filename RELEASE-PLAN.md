# Roadmap

Stand: 18. November 2026 · Version **0.1.3**

**Leitbild „Fire and Forget“ (Nutzer 18.11.):** Die App soll möglichst autonom arbeiten. Der Nutzer wählt nur Zähler und Kamera; alles andere (Grob- und Feineinrichtung, letzte Stelle, Genauigkeit, Fehlerkorrektur) erledigt sie selbst und zeigt Unsicherheit offen an. Manuelle Knöpfe sind nur Notfallwerkzeuge. Stabilität geht vor neuen großen Funktionen.

## Als Nächstes

| Aufgabe | Fertig, wenn … |
| --- | --- |
| **Praxis 0.1.3 beobachten** | Verbrauch wird erst nach Bestätigung gebucht, ohne Warten auf alte Höchststände; Hinweise und Debug-Protokoll im Alltag hilfreich. |
| **Laufende Rolle / Genauigkeit nach Durchfluss (beobachten)** | Die Fehlprüfungen am 18.11. kamen nicht vom Durchfluss, sondern vom falschen Startwert (in 0.1.1 behoben). Nur umsetzen, wenn das Debug-Protokoll zeigt, dass eine drehende Rolle bei hohem Verbrauch Prüfungen scheitern lässt: dann niedrigeren Wert nehmen bzw. vorübergehend eine Stelle weniger vergleichen, mit Hinweis „Zähler läuft gerade schnell“. |
| **Fremde Zähler und Wasserzähler** | Test 18.11. mit ca. 2000 öffentlichen Ziffernbildern (Wasser-/Gaszähler): Einzelziffern nur zu etwa 45 % richtig, „1“ besonders schwach (oft unklar oder als 4 gelesen). Praktisch getestet ist nur der eigene Gaszähler (Stromzähler bereits vernetzt, Wasserzähler nicht zugänglich). Verbesserung über einen Einzelziffern-Klassifikator prüfen (siehe Später). |
| **Vorprüfung ohne geöffnete App** | Sobald Bildquelle bzw. Kamera feststeht, startet die Grob-Einrichtung von selbst im Hintergrund, auch wenn niemand die Weboberfläche offen hat. |
| **Auffindbarkeit** | Repository-Beschreibung und Topics (home-assistant, ocr, gas-meter …), Screenshot mit Demo-Daten im README, Vorstellung im Home-Assistant-Forum/Community-Store vorbereiten. |
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
