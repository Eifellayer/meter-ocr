# Änderungen

## 0.1.0

- **Meter OCR Beta** ist die experimentelle Testausgabe mit eigenen Einstellungen, Sensoren, Benachrichtigungen und Kontrollbildern.
- Die App prüft Bilder von SLFork, ESPHome und Home-Assistant-Kameras. Der manuelle Test bietet eine OCR-Vorschau und die Übernahme von Bildausschnitt und Drehung.
- Auf der Übersicht gibt es einen direkten Teststart mit Fortschritt und einheitlich aufklappbare Einstellungen. Deutsch und Englisch stehen automatisch anhand des Home-Assistant-Profils oder per Auswahl zur Verfügung.
- Das automatische Prüfintervall ist einstellbar. Die Vorgabe beträgt 60 Minuten nach Erfolg und bis zu fünf Minuten nach einem Fehlschlag. Der gelbe Hinweis zeigt nach einer Stunde Details.
- Die ESP-Prüfung unterscheidet aktuelle Werte und Ersatzwerte. Sie prüft den OCR-Stand anhand der Messzeit und des maximalen Durchflusses. Mit einem gültigen Abgleich werden Verbrauchsdaten weitergezählt.
- Bei anhaltenden Prüfproblemen greifen die eingestellten Wartezeiten für Home-Assistant-Hinweise, Handy-Push und E-Mail.
