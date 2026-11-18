# Changelog

## 0.1.1

- **Verbrauch erst nach Bestätigung buchen:** Ein neuer Stand zählt erst, wenn die nächste Prüfung (mindestens 4 Minuten später) ihn bestätigt. Ein zu hoher Lesefehler wird verworfen, bucht nichts und blockiert nichts – kein Warten mehr auf einen falschen Höchststand. Der Startwert der Einrichtung wird genauso bestätigt.
- **Debug-Protokoll** unter „Werkzeuge“: letzte Prüfungen mit allen OCR-Durchläufen, Entscheidung und Verbrauchsstand, zum Ansehen und Herunterladen.
- Hinweis zur 8. Ziffer zeigt jetzt die eingestellte und die vorübergehend verglichene Genauigkeit sowie den Start der Hintergrundsuche.
- Fehlprüfungen nennen den Grund (z. B. „Ablesung passt nicht zum letzten Stand“, „Rolle drehte sich gerade“); nach drei Fehlprüfungen steht die Uhrzeit des nächsten Versuchs dabei.
- Tipp zum Prüfintervall nur noch bei wirklich unlesbaren Ziffern; Status-Chip zeigt „Prüft …“ während einer Prüfung.
- Knöpfe für die dritte Nachkommastelle klein unter „Erweitert“; kompaktere Navigation auf dem Handy.

## 0.1.0

Neustart der Versionierung mit frischer Historie. Funktionsstand entspricht der bisherigen Entwicklung (Rückblick in [docs/HISTORY.md](../docs/HISTORY.md)), dazu:

- Hintergrundsuche heißt „Optimierung läuft“, sobald alle Ziffern gelesen sind, mit Höchstdauer und Restzeit.
- Veraltete Ansicht wird erkannt: „Nicht aktuell“ am Zählerstand, Neu-laden-Knopf, automatisches Neuladen nach App-Neustart. Anzeigefehler werden getrennt gemeldet und ins App-Protokoll geschrieben.
- Einrichtungsassistent im neuen Design mit Schrittanzeige; das Layout springt beim Aufklappen nicht mehr.
- Dokumentation neu und knapp geschrieben.
