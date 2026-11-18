# Roadmap

Stand: 18. November 2026 · Version **0.1.0**

Ziel: einmal einrichten, danach prüft die App selbstständig und zeigt Unsicherheit offen an. Stabilität geht vor neuen großen Funktionen.

## Als Nächstes

| Aufgabe | Fertig, wenn … |
| --- | --- |
| **Praxis 0.1.0 beobachten** | Neuinstallation und Selbsteinrichtung laufen am echten Zähler; Optimierungs-Anzeige, Neuladen nach Neustart und Assistent auf Handy und Desktop bewährt. |
| **Anzeige der Einrichtung mit sieben Ziffern korrigieren** | Der Hinweis zeigt die eingestellten 3 Nachkommastellen und dass vorübergehend nur 2 verglichen werden; die Suche nach der 8. Ziffer ist sichtbar angekündigt (Start ca. 1 h nach der Einrichtung) statt still pausiert. (Nutzerhinweis 18.11., zweimal gemeldet) |
| **Laufende 7. Ziffer bei hohem Verbrauch nicht als Fehler werten** | Dreht sich die 2. Nachkommastelle gerade (Lesungen schwanken zwischen n und n+1), gilt der niedrigere Wert als bestätigt, statt „Prüfung fehlgeschlagen“ und 60 Minuten Pause. Bucht nie zu viel, da der Zähler nur vorwärts läuft. |
| **Genauigkeit an den aktuellen Durchfluss anpassen** | Die App berechnet den Durchfluss aus den letzten bestätigten Ständen. Dreht sich die letzte verglichene Rolle schneller, als sie sicher lesbar ist, vergleicht sie vorübergehend eine Stelle weniger und zeigt z. B. „Zähler läuft gerade schnell (ca. 10 l/min) – vorübergehend 1 Nachkommastelle“. Sinkt der Verbrauch, geht sie automatisch zur eingestellten Genauigkeit zurück. (Nutzeridee 18.11.) |
| **Startwert der Einrichtung absichern und Korrektur ohne Verbrauchsverlust** | 18.11.: Die Einrichtung übernahm 10475,70 statt ca. 10475,0x; die Selbstkorrektur griff, bucht aber bis zum falschen Höchststand (~0,5 m³) nichts. Startwert erst nach zweiter stimmiger Prüfung als Anker nehmen; war der zu hohe Wert nur der Startanker (kein Verbrauch darauf gebucht), Anker direkt auf den korrigierten Stand setzen. |
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
