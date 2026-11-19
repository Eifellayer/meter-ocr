# Changelog

## 0.1.9

- **Selbsteinrichtung zählt stabiler hoch:** Findet die Einrichtung dieselbe Ziffernreihe auf dem nächsten Bild wieder, nur ein paar Pixel oder ein Grad anders, zählt das jetzt als Bestätigung. Bisher galt das als neuer Rahmen, und die Zählung sprang auf 1/3 zurück. Absichtlich nachjustierte Rahmen zählen weiterhin neu.

## 0.1.8

- **Feinwinkel schon in der Selbsteinrichtung:** Die grobe Suche findet die Ziffern weiterhin in ganzen Grad. Für jeden gefundenen Rahmen misst die Einrichtung auf den Einrichtungsbildern zusätzlich die Schräglage der Ziffernreihe und speichert den Mittelwert als Feinwinkel (bis ±0,5°) gleich mit. Was darüber hinausgeht, gleichen die normalen Prüfungen aus.

## 0.1.7

- **Bilddrehung in 0,1°-Schritten:** z. B. −1,5° statt nur −1° oder −2°.
- **Schräglage automatisch ausgleichen:** Bei manuellem Ausschnitt misst die App bei jeder Prüfung, wie schief die Ziffernreihe liegt (Linie durch die Ziffernmitten, robust gegen eine drehende Rolle). Stimmen sieben Messungen überein und weichen sie um mindestens 0,3° ab, dreht sie das Bild fein nach (höchstens ±2°). Steht im Debug-Protokoll unter `tilt`.
- **Letzter Stand als Lesehilfe:** Vorkommastellen, die nach dem letzten bestätigten Stand und dem maximalen Durchfluss unmöglich sind, zählen nicht mehr mit. Beispiel 19.11.: `10478.65?` statt `1047?.65?`, weil die 8 manchmal als 6 gelesen wurde.
- **Verbrauch auch in kWh:** Unter Einstellungen Zustandszahl und Brennwert von der Gasabrechnung eintragen oder nur den fertigen Umrechnungsfaktor; dann gibt es zusätzlich `sensor.rf1_verbrauch_gesamt_kwh` für das Energie-Dashboard.
- **Kompaktere Formulare:** Auswahl- und Eingabefelder in Einstellungen, Werkzeugen und Einrichtung sind kleiner.
- **Ehrlicherer Fehlertext:** Sind nur einzelne Ziffern unklar, heißt es „Einzelne Ziffern waren nicht eindeutig lesbar. Die App versucht es automatisch weiter.“ statt des Rats, Kamera, Fokus und Licht zu prüfen.

## 0.1.6

- Nachschieben fehlender Ziffern jetzt für bis zu **drei** unklare Stellen (z. B. `1047?.?4?`). Kamera und Winkel ändern sich zwischen zwei Prüfungen praktisch nie; meist sitzen dann nur einzelne Rahmen leicht daneben. Weiterhin höchstens 10 zusätzliche Einzelziffer-Lesungen, und die übrigen Ziffern müssen sicher gelesen sein.

## 0.1.5

- **Fehlende Ziffern nachschieben:** Bleiben nach den OCR-Versuchen eine oder zwei Ziffern unklar (z. B. `10477.9??`), verschiebt die App nur deren Rahmen in kleinen Schritten und liest sie neu, bis beide mit zwei übereinstimmenden OCR-Profilen gelesen sind (höchstens 10 zusätzliche Einzelziffer-Lesungen). Übernommen wird der Wert nur, wenn er zum Vergleichs- bzw. Vorwert passt. Bisher ging das nur für genau eine Ziffer.
- **Präzisionsmodus als experimentell gekennzeichnet:** kurzer Hinweis, dass der Wert genau ist, die schnell laufende letzte Rolle aber oft nicht sicher erkannt wird.

## 0.1.4

- **8. Ziffer über die Rollenmitte:** Die Suche bestimmt zuerst waagerecht die Mitte der letzten Rolle (die etwas weiter entfernt sitzt als die übrigen Ziffern) und verschiebt den Rahmen danach nur noch nach oben und unten. Die Mitte wird nur verwendet, wenn das Verfahren auf demselben Bild die bekannte Nachbarziffer wiederfindet; sonst gelten die bisherigen Positionen.
- **Engerer Suchbereich:** keine Sprünge mehr um eine halbe Ziffernbreite zur Seite, die eine halbe Ziffer in den Rahmen holten und zu Teiltreffern führten.
- **Rahmen sitzt daneben:** Ist die letzte verglichene Stelle mehrmals hintereinander unklar, meldet die App nicht mehr „Rolle drehte sich gerade“, sondern „Rahmen der letzten Stelle sitzt daneben“ und sucht ihn im Hintergrund neu (höchstens einmal pro Stunde).
- **Ruhigere Hinweise:** Eine einzelne Fehlprüfung oder eine bestandene Prüfung mit Hinweis wird dezent angezeigt, ohne gelbe Warnung und ohne „Bitte prüfen“. Erst ab drei Fehlprüfungen in Folge wird der Hinweis deutlich.

## 0.1.3

- Restzeit der Hintergrundsuche nur noch einmal: „Noch höchstens 9 von 20 min“.
- Sieben-Ziffern-Modus gilt als normaler Betrieb: grünes „Alles OK. Die 8. Ziffer wird noch abgesichert.“ statt gelber Warnung; der doppelte Optimierungstext im Automatik-Kasten entfällt.
- Meldungen wie „Einrichtung gespeichert.“ verschwinden nach 10 Sekunden und kommen beim automatischen Neuladen nicht wieder.

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
