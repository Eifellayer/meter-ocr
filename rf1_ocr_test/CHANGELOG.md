# Changelog

## 0.1.1

- Nach der bestätigten Sieben-Ziffern-Einrichtung wird die separat laufende Suche nach der achten Ziffer nach App-Neustarts und erfolglosen Suchläufen automatisch wiederaufgenommen. Zwischen erneuten Starts liegt mindestens eine Stunde; eine laufende Suche wird nicht unterbrochen.
- Die Übersicht unterscheidet jetzt eindeutig zwischen **3 eingestellten Nachkommastellen** und **2 vorläufig verglichenen**. Die achte Ziffer bleibt unbestätigt, bis sie tatsächlich nachgeprüft wurde. Ein solcher Teilmodus wird nicht mehr fälschlich als vollständig grüner Erfolg dargestellt.
- Der vorläufige Zwei-Stellen-Vergleich prüft exakt die ersten sieben Ziffern **ohne Rundung anhand der unbestätigten achten Stelle**; er kann dadurch bei `10475.15?` und Referenz `10475.155` korrekt den siebenstelligen Präfix bestätigen. Regulär eingestellte Vergleichsgenauigkeiten behalten ihre Rundungsregel.
- Bestehender siebenstelliger Prüf- und Verbrauchsstand sowie gespeicherte Einstellungen bleiben unverändert. Tests decken Zeitplanung, Neustart, Geltungsbereich und den Anzeigezustand ab.

## 0.1.0

Neustart der Versionierung mit frischer Historie. Funktionsstand entspricht der bisherigen Entwicklung (Rückblick in [docs/HISTORY.md](../docs/HISTORY.md)), dazu:

- Hintergrundsuche heißt „Optimierung läuft“, sobald alle Ziffern gelesen sind, mit Höchstdauer und Restzeit.
- Veraltete Ansicht wird erkannt: „Nicht aktuell“ am Zählerstand, Neu-laden-Knopf, automatisches Neuladen nach App-Neustart. Anzeigefehler werden getrennt gemeldet und ins App-Protokoll geschrieben.
- Einrichtungsassistent im neuen Design mit Schrittanzeige; das Layout springt beim Aufklappen nicht mehr.
- Dokumentation neu und knapp geschrieben.
