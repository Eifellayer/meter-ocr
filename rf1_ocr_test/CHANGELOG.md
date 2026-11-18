# Changelog

## 0.1.3

- Restzeit der Hintergrundsuche nur noch einmal: „Noch höchstens 9 von 20 min“.
- Sieben-Ziffern-Modus gilt als normaler Betrieb: grünes „Alles OK. Die 8. Ziffer wird noch abgesichert.“ statt gelber Warnung; der doppelte Optimierungstext im Automatik-Kasten entfällt.

## 0.1.2

- **Verbrauch erst nach Bestätigung buchen:** Ein neuer Stand zählt erst, wenn die nächste Prüfung (mindestens 4 Minuten später) ihn bestätigt. Ein zu hoher Lesefehler wird verworfen, bucht nichts und blockiert nichts – kein Warten mehr auf einen falschen Höchststand. Der Startwert der Einrichtung wird genauso bestätigt.
- **Debug-Protokoll** unter „Werkzeuge“: letzte Prüfungen mit allen OCR-Durchläufen, Entscheidung und Verbrauchsstand, zum Ansehen und Herunterladen.
- Hinweis zur 8. Ziffer zeigt jetzt die eingestellte und die vorübergehend verglichene Genauigkeit sowie den Start der Hintergrundsuche.
- Fehlprüfungen nennen den Grund (z. B. „Ablesung passt nicht zum letzten Stand“, „Rolle drehte sich gerade“); nach drei Fehlprüfungen steht die Uhrzeit des nächsten Versuchs dabei.
- Tipp zum Prüfintervall nur noch bei wirklich unlesbaren Ziffern; Status-Chip zeigt „Prüft …“ während einer Prüfung.
- Knöpfe für die dritte Nachkommastelle klein unter „Erweitert“; kompaktere Navigation auf dem Handy.
- **Genauigkeit vereinfacht:** Standard sind 2 Nachkommastellen; die dritte nur mit Präzisionsmodus. Der alte strenge Präzisionsmodus („alle drei Stellen müssen stimmen“) entfällt.
- **Drehende Rolle:** Ist nur die letzte verglichene Stelle unklar, bestätigt die App die Prüfung einmalig mit einer Nachkommastelle weniger, statt sie scheitern zu lassen.
- **Farbige Rollen:** Die OCR nutzt den Farbkanal mit dem stärksten Kontrast (z. B. für rote Nachkommarollen). Im Test mit öffentlichen Ziffernbildern verschiedener Zähler rund zehn Prozentpunkte mehr richtig erkannte Ziffern.
- README: Hinweis, dass bisher nur ein Gaszähler praktisch getestet ist.

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
