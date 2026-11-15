# Entwicklungs- und Freigabeplan

## Releasekanal

- Versionen `0.1.x` bis `0.4.x` sind Alpha. Bis Version 0.5 gibt es keine separate Beta-App; die reguläre Meter-OCR-App ist der Testkanal.
- Ab `0.5` wird eine Beta-Version nur bei größeren Änderungen mit konkretem zusätzlichem Testbedarf angelegt. Kleine Fehlerkorrekturen laufen ohne separaten Beta-Kanal.
- Beta-Testinstallationen müssen eigene Home-Assistant-Entitäten, Einstellungen und Medienpfade erhalten, damit sie parallel testbar sind.
- App-Slug, bestehende Entitäts-IDs, gespeicherte Optionen und Prüfhistorie der regulären App bleiben kompatibel.

## Priorisierte Abnahme

| Priorität | Bereich | Abnahme |
| --- | --- | --- |
| P0 | Kompatibilität und Daten | Bestehende Entitäten, Einstellungen, Historie und Dashboards bleiben erhalten; neue Werte werden plausibilisiert. |
| P0 | Prüfung und Fehlerbehandlung | SLFork-Zeitstempel, Ersatzwerte, ungültige Referenzen, fehlende Bilder und OCR-Unsicherheit werden getrennt und nachvollziehbar behandelt. Automatik und manueller Test bleiben voneinander getrennt. |
| P1 | Einrichtung und mobile Bedienung | Der Assistent führt durch Quelle, Zählerformat, Bildbereich und Prüfplan und lässt sich mit aktuellen Werten erneut öffnen. Oberfläche und manuelle Diagnose funktionieren mobil. |
| P1 | Sprachen und Meldungen | Profilsprache von Home Assistant und manuelle Auswahl funktionieren je Nutzer. Hinweise sind verständlich und optionale Benachrichtigungen abschaltbar. |
| P1 | Bildquellen und Zählertypen | SLFork ist real am Zähler getestet. Alternative Kameras, ESPHome und weitere Bildtypen sind als simuliert gekennzeichnet, bis reale Gerätetests erfolgt sind. |
| P2 | Dokumentation und Freigabe | Deutsch und Englisch stimmen mit der App überein. GitHub Actions prüft OCR, Ingress, JavaScript, Konfiguration und App-Images. |

## 0.2.0 Alpha – aktueller Arbeitsstand

Einrichtung, Live-Kamera-Schnappschüsse, manuelle Diagnose, fallbackbasierte Plausibilitätsprüfung, Prüfintervall, Benachrichtigungswahl, Statusanzeige und deutsch/englische Dokumentation sind umgesetzt. Lokale Tests decken diese Wege ab. Die Home-Assistant-Container-Builds und ein Upgrade in einer echten Supervisor-Installation müssen vor einer Freigabe über GitHub Actions bzw. auf einem Home-Assistant-System bestätigt werden.

## Vor 1.0 noch zu bestätigen

1. GitHub Actions erfolgreich für AMD64 und ARM64.
2. Upgrade mit vorhandener Historie, Einstellungen und Dashboards in einer echten Supervisor-Installation.
3. SLFork mit aktuellen und veralteten Messzyklen sowie Wiederanlauf prüfen.
4. Ingress in Desktop-Browser und Home-Assistant-Companion-App mit mehreren Nutzern testen.
5. Echte Kamera-/Zählertests für alternative Quellen durchführen, bevor sie als real unterstützt beworben werden.
6. Push und E-Mail mit tatsächlich eingerichteten Home-Assistant-Zielen prüfen.
