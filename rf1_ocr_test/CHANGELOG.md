# Änderungen

## 0.6.2

- Optionaler Hinweis in Home Assistant und einmalige Push-Erinnerung nach 24 Stunden. Offene Fälle lassen sich quittieren oder überspringen.
- Versionierte Konfiguration mit Standardwerten und Migrationen für neue, umbenannte und veraltete Einstellungen.
- Anleitung für die Einrichtung des Push-Dienstes und dieses Changelog.

## 0.6.1

- Versionswechsel zum Prüfen des automatischen Updates aus dem GitHub-Repository.

## 0.6.0

- Stündlicher Abgleich bei erfolgreicher Messung. Bei Abweichungen wird alle fünf Minuten erneut geprüft.
- Prüfbedarf nach vier Stunden ohne Treffer. Der Beginn der Störung bleibt bei einem Neustart erhalten.

## 0.5.0

- Automatischer Bildausschnitt anhand der SLFork-Ziffernrahmen.
- OCR für normale und invertierte Bilder.

## 0.4.1

- Vergleich der vollen Kubikmeter auch bei vier oder mehr Nachkommastellen von SLFork.

## 0.4.0

- Lokale Gegenkontrolle der vollen Kubikmeter mit einem rollierenden 24-Stunden-Fenster und fünf bestätigten Messungen als Ziel.

## 0.2.0

- Kontrollbild und zugehörige SLFork-Messung in Home Assistant bereitgestellt.

## 0.1.0

- Erster lokaler OCR-Probelauf mit Ausgabe im App-Protokoll.
