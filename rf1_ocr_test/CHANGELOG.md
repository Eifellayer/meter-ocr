# Changelog

## 0.6.6 Stable

- Die Auswahl „In Home Assistant gefunden“ bleibt im Einrichtungsassistenten immer sichtbar, auch wenn nach einem Home-Assistant-Neustart vorübergehend keine Geräte erkannt werden. Im Auswahlfeld steht dann „Es wurden keine Geräte gefunden“.
- Die Gerätesuche wird bei erneutem Öffnen der Einrichtung wiederholt, falls sie zuvor leer war. Kein zusätzlicher Suchbutton oder Statusbereich.
- Wenn die Home-Assistant-Template-Abfrage keine Geräte liefert, versucht die App die bestehende Geräteerkennung zusätzlich über die Zustands-API. Regressionstests sichern die Anzeige und das Fallback ab.

## 0.6.5 Stable

- Zusätzlicher Button „Factory Reset – Statistik behalten“ im Bereich „App-Daten zurücksetzen“. Der bisherige vollständige Reset bleibt unverändert.
- Der neue Reset entfernt OCR-Einrichtung, Bildquelle, Benachrichtigungen, Kalibrierung, Testbilder und Prüfergebnisse, erhält aber kumulierten Verbrauch und die gespeicherten Stunden-/Tagesstatistiken. Auch die Messhistorie experimenteller Zusatzzähler bleibt für eine spätere Wiedereinrichtung erhalten.
- Bei erneuter Einrichtung mit einer anderen Bildquelle bleiben vorhandene Statistikwerte erhalten; die erste neue Messung setzt die neue Basis, ohne künstlichen Verbrauch zu erzeugen. Die neue Einrichtung ist vor weiteren automatischen Prüfungen erforderlich.
- Separate Bestätigung für den Reset mit Statistikerhalt; serverseitige Eingabeprüfung und Regressionstests für beide Resetvarianten.

## 0.6.4 Stable

- Bleibt die automatische Zählerprüfung nach tatsächlich durchgeführten kleinen Winkelkorrekturen weiterhin unklar oder abweichend, fordert die App bei direkt abrufbaren Kameras einmalig nach 15 Sekunden ein neues Bild an. Die vorhandene Fehlerbegrenzung und Prüfung auf unabhängige Aufnahmen bleiben bestehen.
- Die Statusmeldung für die schnelle Bildnachprüfung wurde verständlicher formuliert.

## 0.6.3 Stable

- Bei drei ausgewählten Nachkommastellen prüft die Einrichtung die letzte Rolle automatisch und bestätigt abschließend den vollständigen Stand auf einem frischen Bild. Bei weniger Stellen entfällt diese Feinprüfung. Die Oberfläche erklärt die gewählte Prüfung.
- Die Selbsteinrichtung vergleicht ±1° und ±2° auch bei sieben lesbaren Stellen und bei bereits begonnenen Bestätigungen. Der Vergleich erfolgt vor der Übernahme und gilt für den tatsächlich geprüften Rahmen.
- Die Intensivprüfung der letzten Rolle sucht zusätzlich bis zu einer halben Rahmenbreite und -höhe um die Ausgangsposition, einschließlich diagonaler Verschiebungen. Die benachbarten Rollen dienen als weiterer Positionsvorschlag.

## 0.6.2 Stable

- Die Selbsteinrichtung prüft bei einem vollständigen Treffer bei 0° zusätzlich ±1° und ±2°. Bei derselben Ablesung gewinnt der Winkel mit mehr übereinstimmenden OCR-Profilen. Gleich gute Varianten behalten den Ausgangswinkel.

## 0.6.1 Stable

- Zehn Minuten sind für die Automatik vorausgewählt. Gespeicherte Intervalle bleiben frei einstellbar.
- Die Übersicht kann einen regulären Automatiklauf anfordern. Bei erfolgreicher Zusatzprüfung bleibt der nächste bereits geplante Termin bestehen.
- Wiederholt unklare Nachkommastellen führen zu einer Empfehlung. Erst die Bestätigung ändert die Vergleichsgenauigkeit.
- Schon in der Grobsuche des ersten Bildes kommen 180° und ±90° infrage, wenn die übliche Ausrichtung keinen belastbaren Treffer liefert.
- Die Einzelziffer-Nachprüfung verschiebt normale Rahmen seitlich. Bei der letzten Nachkommarolle kommen vertikale Varianten zuerst. Für isolierte Ziffern kann die OCR zwei alternative Segmentierungen vergleichen.

## 0.6.0 Stable

- Die Automatik prüft zuerst einen verschobenen Einzelrahmen. Erst danach kann sie Ziffern aus übereinstimmenden OCR-Versuchen derselben Aufnahme zusammensetzen. Ein begrenzter früher Folgeabruf kann ein ungeeignetes Kamerabild ersetzen.
- Die Diagnose nennt bis zu drei Rahmenkandidaten mit Position, Drehung und OCR-Übereinstimmung. Nach erneut bestätigter Selbsteinrichtung erscheint die grüne Erfolgskarte wieder.
- Die Zähler-Demo zeigt mit einem künstlichen schrägen Bild, wie Ausrichtung, OCR und Spiegelungsergänzung funktionieren.
- Der optionale Bereich „Experimentell“ beobachtet zusätzliche kumulative Home-Assistant-Zähler in m³ und kWh mit jeweils eigenem Intervall und Verlauf. Praxistests stehen aus.

## 0.5.37 Stable

- Fehlt bei einer Automatikprüfung genau eine erforderliche Ziffer, prüft die App ihren Rahmen im selben Bild mit kleinen Verschiebungen. Zwei OCR-Profile müssen die Ziffer gleich lesen. Zusammen bleiben reguläre Prüfung und Nachprüfung bei höchstens 15 Versuchen.
- Bei aktivierter Spiegelungsergänzung plant die App begrenzte schnellere Kameraprüfungen anhand der fehlenden Rolle und des zuletzt bestätigten Verbrauchs.

## 0.5.36 Stable

- Automatische Prüfungen warten auf die Einrichtung. Ein bestätigter Rahmen, ein gespeicherter Startwert oder ein gültiges, manuell geprüftes Testbild kann die Automatik freigeben.
- Die empfohlene automatische Selbsteinrichtung zeigt den aktuellen und nächsten Schritt. Der manuelle Assistent führt vom Kamerabild über einen gezeichneten Rahmen zur Vorschau und Bestätigung.
- Größere Bedienelemente, Gerätesuche und Vorrang für Gaszähler in der Quellenliste erleichtern die Auswahl auf dem Handy.
- Die Roadmap zeigt die geplanten Funktionen der 0.6-Beta in der App.

## 0.5.35 Stable

- Die Verbrauchsübersicht zeigt die aktuelle Stunde und den heutigen Tag in m³. Der aufklappbare Verlauf zeigt 24 Stunden und sieben Tage anhand bestätigter Ablesungen.
- Die Erfolgskarte der Ersteinrichtung zeigt zusätzlich die Anzahl der Rahmenversuche und geprüften Bilder.
- Der OCR-Fortschritt verwendet wieder „Versuch 1 von 5“ mit der jeweils gültigen Versuchszahl.

## 0.5.34 Stable

- Die Übersicht zeigt nach der Ersteinrichtung eine grüne Erfolgskarte mit der Dauer. Sie verschwindet nach dem ersten vollständigen Automatiklauf.
- Der OCR-Status nennt das Versuchslimit. Aufklappbare Prüfdetails zeigen abgeschlossene Versuche und die letzte vorläufige Ablesung.
- Selbsteinrichtung, Ziffernrahmenkorrektur und manuelle Tests stehen unten im Werkzeugbereich. Ein Link in der Navigation öffnet ihn direkt.

## 0.5.33 Stable

- Die Selbsteinrichtung schlägt mögliche Spiegelungsstellen zwischen lesbaren Nachbarziffern vor. Bis zu zwei Positionen lassen sich markieren und die Rahmen korrigieren. Drei passende Bilder erlauben einen vorläufigen Rahmen mit offenen Ziffern.
- Nach drei bestätigten Aufnahmen übernimmt die reguläre Automatik die Gegenprüfung. Die Einrichtung hat ein Ziel von fünf Minuten und ein Limit von 20 Minuten. Die erste unklare Kontrollmessung erscheint als Hinweis. Direkt auslösbare Kameras werden dann nach 15 Sekunden erneut abgefragt.
- Die Diagnose zeigt Kandidaten mit Prozentwert und gelesener Ziffernfolge. Die eingestellte Übereinstimmungsschwelle erklärt den Start der Feinprüfung.
- Bei aktivierter Langzeit-Feinjustierung lösen wiederholt unklare Stellen kleine lokale Versuche im regulären OCR-Budget aus. Neue Rahmen werden erst nach mehreren plausiblen Aufnahmen und mehr als einem Zählerstand übernommen.
- Das Standard-Prüfintervall beträgt 30 Minuten. Bei Lesefehlern hält der Home-Assistant-Sensor den letzten bestätigten Stand derselben Quelle und kennzeichnet ihn als Fallback.

## 0.5.32 Stable

- Wenn höchstens zwei Pflichtstellen offen sind und mindestens drei andere Stellen übereinstimmend lesbar sind, prüft die Selbsteinrichtung zuerst kleine Verschiebungen der betroffenen Einzelrahmen. Bei Bedarf testet sie danach nur die Winkel einen Grad links und rechts vom aktuellen Winkel.

## 0.5.31 Stable

- Bei der vereinfachten Einrichtung führt ein sonst übereinstimmender Zählerstand mit offener zweiter Nachkommastelle zur gezielten Nachprüfung auf demselben Bild. Kleinste Verschiebungen des betreffenden Rahmens haben Vorrang.
- Die dritte Nachkommastelle, die übrigen Rahmen und der bisherige Bildwinkel bleiben bei der Nachprüfung unberührt.
- Nach erfolgreicher Zweistellen-Gegenprobe versucht die App kurz, die dritte Stelle auf derselben Aufnahme zu lesen. Ein Treffer wird als vorläufiger Hinweis gezeigt und verändert den bestätigten Rahmen nicht.

## 0.5.30 Stable

- Die gezielte Feinprüfung der letzten Rolle nutzt bis zu drei Bilder aus dem MJPEG-Stream einer direkt eingebundenen ESP-Kamera oder einer Home-Assistant-Kamera mit lokaler OCR. Wenn der Stream ausfällt, verwendet sie Einzelbilder.
- Erkennt die OCR in zwei Profilen einen Wechsel zwischen benachbarten Ziffern, wartet die Feinprüfung auf eine eindeutige Aufnahme. Ein Stream-Abruf zählt höchstens als eine Bestätigung.

## 0.5.29 Stable

- Die gezielte Nachprüfung der linken Ziffern verschiebt nur vorhandene Einzelrahmen. Breite und Höhe bleiben erhalten.
- Geschätzte Ziffernfenster dienen nur zum Nachlesen. Sie ersetzen keinen gespeicherten Rahmen. Wenn die Nachprüfung scheitert, bleiben der bisherige Kandidat und seine Bestätigungen erhalten.

## 0.5.28 Stable

- Nach zwei Rahmenbestätigungen prüft die App unklare linke Ziffern gezielt auf demselben Bild. Sie testet zusätzliche OCR-Profile und bei Bedarf kleine Verschiebungen der betreffenden Einzelrahmen.
- Die übrigen Ziffernrahmen, der Ausschnitt und der Drehwinkel bleiben bei dieser Prüfung erhalten. Ein angepasster Rahmen sammelt eigene Bestätigungen.

## 0.5.27 Stable

- Der Einrichtungsassistent zeigt „Ausschnitt und Drehung lernen“ als erste und empfohlene Auswahl. Bereits gespeicherte Einstellungen bleiben beim erneuten Öffnen vorausgewählt.

## 0.5.26 Stable

- Die Übersicht zeigt nach erfolgreicher regulärer Ablesung kurz und bündig „Alles OK. Automatik läuft.“. Einrichtungsmeldungen laufen aus und bleiben in der Diagnose nachlesbar.
- Laufende Prüfungen, fehlende Gegenproben, Pausen und Fehler behalten ihren eigenen Status. Auch vorläufig eingerichtete Zähler mit zwei bestätigten Nachkommastellen verwenden die passende Statusanzeige.

## 0.5.25 Stable

- Bei der vereinfachten Einrichtung zählen übereinstimmende Lesungen bis zur zweiten Nachkommastelle. Fehlt der Vergleichswert, zählt der Rahmen vorläufig. Ein vorhandener, abweichender Vergleichswert blockiert die Bestätigung.
- Die Einrichtung nutzt zusätzliche OCR-Profile für die Bestätigung des Rahmens, wenn zwei Profile dieselben benötigten Ziffern lesen und kein Profil einen anderen vollständigen Wert liefert.

## 0.5.24 Stable

- Die Übersicht öffnet nach gespeicherter Kalibrierung einen Editor für vorhandene Ziffernrahmen. Ein Rahmen lässt sich einzeln verschieben, skalieren und zurücksetzen.
- „Diese Ziffer suchen“ prüft gezielt nur die ausgewählte Stelle. Der Vorschlag lässt sich prüfen und manuell speichern.
- Dunkle oder ungleichmäßig beleuchtete Ausschnitte erhalten früher vorhandene OCR-Profile für Schattenkorrektur. Ein vollständiger 100-%-Treffer beendet die Grobsuche auf dem Bild und erhält gezielte Intensivprüfungen mit zeitversetzten Kontrollaufnahmen.

## 0.5.23 Stable

- Eine automatische Rahmensuche startet pro Fehlerserie höchstens einmal und frühestens nach zwei Stunden anhaltender Erkennungsprobleme. Plausible Messungen beenden die Fehlerserie.
- Bei vorläufiger Einrichtung bleibt der gespeicherte Rahmen mit zwei Nachkommastellen in Betrieb. Die Feinprüfung der dritten Nachkommastelle lässt sich manuell starten.

## 0.5.22 Stable

- Nach der ersten bestätigten Einrichtung speichert die App den Referenzstand und prüft 20 Minuten lang regulär in höchstens fünfminütigem Abstand.
- Die automatische Selbstoptimierung wartet 60 Minuten, auch nach einem Neustart. Danach startet sie nur bei den vorgesehenen Auslösern.
- Die Übersicht zeigt eine kurze Erfolgsmeldung. Technische Einzelheiten bleiben in den Einstellungen aufklappbar.

## 0.5.21 Stable

- Die Feinprüfung der letzten Rolle liest nur diese Ziffer, verwendet den gespeicherten Drehwinkel und verschiebt bei Bedarf ausschließlich den letzten Einzelrahmen. Neue Bilder werden alle zwei Sekunden angefragt.

## 0.5.20 Stable

- Bei stillstehendem Zähler kann die vereinfachte Einrichtung den Rahmen nach drei frischen, übereinstimmenden Bildern vorläufig speichern. Sie speichert keinen bestätigten Zählerstand und prüft automatisch auf zwei Nachkommastellen weiter und startet die Feinprüfung wieder, sobald die offene Rolle zuverlässig lesbar erscheint.

## 0.5.19 Stable

- Die Selbsteinrichtung prüft zuerst den zuletzt bestätigten Rahmen derselben Bildquelle und Ziffernaufteilung. Erst wenn er nicht mehr passt, beginnt die weitere Rahmensuche.
- Bei der Feinprüfung wird eine unklare vorletzte Rolle gezielt nachgeprüft, wenn nur sie offen ist. Ein geänderter Rahmen sammelt seine eigenen Bestätigungen.
- Bei einer neuen Grobsuche vergleicht die App die Ziffernbereiche vor der Winkelprüfung. Am besten Kandidaten prüft sie kleine Winkel auch bei einem lesbaren Ausgangsbild.
- Die optionale rechnerische Ergänzung verdeckter Ziffern ist im Assistenten sichtbar.

## 0.5.18 Stable

- Nach 3/3 Treffern kann die Gegenprobe der Feinprüfung bewusst übersprungen werden. Die App warnt vor möglichen ungenaueren Ablesungen und kennzeichnet den übernommenen Rahmen als ohne Gegenprobe gespeichert.
- Nach erfolgreicher Einrichtung öffnet sich die Übersicht. Die Automatik startet und kann den bestätigten Einrichtungsstand als Referenz verwenden.
- Eine kurze Bildprüfung am Anfang weist auf auffällige Helligkeit, wenig Kontrast oder mögliche Unschärfe hin.
- Fehlt zur automatischen Bestätigung nur die zweite Aufnahme, fragt die App nach fünf Sekunden ein frisches Bild an. Ein zwischengespeichertes Bild zählt nicht noch einmal.

## 0.5.17 Stable

- Nach 3/3 Treffern hat die Gegenprobe der Feinprüfung ein eigenes Zeitfenster von vier Minuten.
- Endet die Gegenprobe ohne Bestätigung, zeigt die Feinprüfung ihr Bild mit der höchsten Übereinstimmung und bietet den besten Rahmen zur manuellen Prüfung an.

## 0.5.16 Stable

- Nach dem ersten Treffer der Feinprüfung zählt das Variantenlimit nicht mehr gegen die Bestätigung desselben Rahmens auf frischen Bildern.

## 0.5.15 Stable

- Die Übereinstimmung für den Wechsel von der Grobsuche zur Intensivprüfung ist einstellbar. Der Standardwert beträgt 80 Prozent.
- Der angezeigte Prozentwert berücksichtigt alle sichtbaren Ziffernpositionen. Bei einer offenen Stelle kann das Bild den Rahmen bestätigen, die Anzeige bleibt unter 100 Prozent.
- Ergibt eine frühe Intensivprüfung keinen Treffer, setzt das nächste Bild die noch verfügbare Grobsuche fort.
- Der Startwert-Hinweis bleibt während weiterer Bildprüfungen sichtbar.
- Beim dritten vollständig übereinstimmenden Bild prüft die App den ausgewählten Rahmen sofort mit zusätzlichen OCR-Profilen. Die Gegenprobe bleibt unabhängig.

## 0.5.14 Stable

- Ab 90 Prozent Übereinstimmung beginnt die Intensivprüfung. Bei verlässlichen 100 Prozent bleibt die Prüfung beim gefundenen Rahmen.
- Eine einzelne vermutete Ziffernposition ohne lesbare Ziffer erscheint gelb mit einem Fragezeichen.
- Sobald ein Ziffernrahmen vorliegt, werden Drehwinkel bereits in der Grobsuche und bei gespeicherten Zwischenkandidaten geprüft.
- Bei drei eingestellten Nachkommastellen und ausgeschaltetem Präzisionsmodus genügen die ersten zwei Stellen auch beim erneuten Start der Selbsteinrichtung. Die Feinprüfung der dritten Stelle zeigt einen eigenen Zähler.

## 0.5.13 Stable

- Die Grobsuche endet bei einem verlässlichen Treffer oder nach 50 Versuchen. Bis zu fünf der besten Kandidaten werden gespeichert und intensiver geprüft.
- Nach zwei Bestätigungen prüft die Selbsteinrichtung denselben Rahmen weiter und wiederholt bei Bedarf die Gegenprobe. Deutlich schlechtere Bilder werden dafür übersprungen.
- Nach der vereinfachten Ersteinrichtung wird der bestätigte Ausschnitt gespeichert. Die App kann den Rahmen der offenen dritten Stelle schon auf dem vorhandenen Bild testen. Ein Vorschlag wird anschließend im selben Ausschnitt mit neuen Bildern geprüft.

## 0.5.12 Stable

- Bei drei eingestellten Nachkommastellen kalibriert die Ersteinrichtung zunächst auf zwei bestätigte Stellen. Die dritte kann anschließend intensiv gesucht oder im Kamerabild manuell markiert werden.

## 0.5.11 Stable

- Beim optionalen Startwert lässt sich ein Kamerabild schon vor dem Speichern der Einrichtung laden.
- Bei der Ersteinrichtung ist „Ausschnitt und Drehung lernen“ vorausgewählt.

## 0.5.10 Stable

- Der Einrichtungsassistent fragt gleich zu Beginn nach einem optionalen, selbst abgelesenen Startwert und trägt die Uhrzeit automatisch ein.

- In einem dunklen Zählfenster werden die Einzelrahmen aus den sichtbaren Ziffernpositionen abgeleitet. Dadurch kann ein breiter Rand den Rahmenabstand nicht mehr vorgeben.
- Fehlt genau eine Vorkommastelle, kann eine zusätzliche Zeilenlesung sie ergänzen, sofern sie mit allen bereits einzeln gelesenen Stellen übereinstimmt.

## 0.5.9 Stable

- Die Vorschau zeigt beim Winkeltest den gedrehten Ausschnitt und das OCR-Ergebnis. Danach kehrt sie zum besten Winkel zurück.
- Neben einem klar erkannten Zählfenster werden deutlich kleinere, getrennte Beschriftungen vor der OCR ausgefiltert.

## 0.5.8 Stable

- Die Selbsteinrichtung vergleicht zuerst kleine Drehungen in Ein-Grad-Schritten.
- Die Einzelziffernsuche startet erst bei höchstens drei offenen Stellen und prüft bis zu sechs Varianten in höchstens zwölf Sekunden OCR-Zeit.

## 0.5.7 Stable

- Die Selbsteinrichtung vergleicht die groben Bildkandidaten, bevor sie höchstens einen Bereich pro Bild feinjustiert.
- Die Kalibrierungsübersicht bietet einen direkten Einstieg zum manuellen Markieren des Ziffernfelds.

## 0.5.6 Stable

- Bei einem neuen Suchlauf hat die Bildsuche Vorrang vor alten Rahmen und ESP-Markierungen.
- Stimmen beide OCR-Lesungen mit der eingestellten Vergleichsgenauigkeit überein, folgt direkt die Bestätigung mit frischen Bildern.
- Die Kalibrierungskarte behält ihre Reihenfolge bei, wenn Status und Bilder eingeblendet werden.

## 0.5.5 Stable

- Größere, gleichmäßige Ziffernreihen werden bei der Selbsteinrichtung bevorzugt. Ähnlich plausible Felder lassen sich im Kamerabild anklicken.
- Klar unpassende Reihen werden im laufenden Suchlauf zurückgestellt. Pro Aufnahme werden höchstens 30 Rahmen geprüft.

## 0.5.4

- Die Selbsteinrichtung trennt die Bildwartezeit von der Rechenzeit und beendet die Bildsuche bei ausbleibenden Aufnahmen nach sechs Minuten.
- Die Grobsuche prüft feinere Drehwinkel. Die Feinsuche variiert zuerst schwache Ziffernrahmen und nutzt vorhandene Aufnahmen für mehrere parallele OCR-Versuche.
- Die normale Überwachung läuft währenddessen weiter. Änderungen am Ausschnitt benötigen weiterhin unabhängige Aufnahmen und eine abschließende Gegenprüfung.

## 0.5.2 Stable

- Die Selbsteinrichtung lässt sich auf das markierte Ziffernfeld im aktuellen Kamerabild einschränken.
- Längere Ziffernreihen werden bei der automatischen Rahmensuche nicht in passend kurze Kandidaten zerlegt.

## 0.5.1 Stable

- Die Selbsteinrichtung zeigt das Kamerabild mit markiertem Suchbereich, den gedrehten Ausschnitt und die Ziffern pro OCR-Versuch live an.
- Bilder, getestete Rahmen und Restzeit sind eindeutig beschriftet. Wenn die Suche keine Ziffernreihe findet, probiert die App auch den bereits eingestellten Ausschnitt und erklärt, warum ein Versuch ohne Bestätigung blieb.
- Die Nachbarsuche leitet fehlende Ziffernrahmen aus sichtbaren Ziffern, Rahmenbreite und Abstand ab. Neue Rahmen werden weiterhin erst nach bestätigter OCR übernommen.
- Die optionale Selbstreparatur meldet nach zehn unterschiedlichen Fehlmessungen einen einmaligen Suchlauf und sichert die Einstellungen. Der bisherige Rahmen wird zuerst geprüft und kann über die Einstellungen wiederhergestellt werden. Im Assistenten ist die Option bei einer Neueinrichtung vorausgewählt.

## 0.5.0 Stable

- Echtzeitvorschau für Bilddrehung und einzeln verschiebbare Ziffernrahmen im manuellen Test und in der Automatik.
- Grobeinrichtung mit bis zu 100 Rahmenversuchen, 100 unterschiedlichen Bildern und höchstens 15 Minuten Laufzeit. Auf Wunsch lässt sich ein noch nicht bestätigter Rahmen im manuellen Test korrigieren.
- Reguläre SLFork-Prüfungen liegen mindestens fünf Minuten auseinander. Identische Messzyklen zählen bei Bestätigungen und Fehlprüfungen nur einmal.
- Optionale Langzeit-Feinjustierung und adaptive SLFork-Prüfintervalle als zuschaltbare Funktionen für die Langzeiterprobung.
- Vorläufige Ergänzung einer fehlenden Stelle je Zählerseite, wenn nur ein Messwert plausibel ist. Der Verbrauchszähler erhält weiterhin nur bestätigte Werte.
- Eigene Speichern-Schaltfläche für den Fallback-Startwert und sichtbarer Spendenlink am Seitenende.

## 0.4.10 Alpha

- „Ausschnitt und Drehung lernen“ ist im Einrichtungsassistenten auswählbar und startet nach dem Speichern.
- Die Selbsteinrichtung hat einen direkten Einstieg in der Übersicht und eine eigene Karte in den Einstellungen.
- Der gelernte Rahmen wird nach einer Gegenprüfung für Automatik und manuellen Test übernommen. Erfolg erscheint grün, Fehlschlag rot.
- Der Zeitbalken läuft auch während des Bildabrufs. Status, Prüfzahl, Bestätigungen und getesteter Drehwinkel sind live sichtbar.
- Die Option zum Ergänzen einer verdeckten Ziffer ist in den Automatik-Einstellungen direkt sichtbar.

## 0.4.9 Alpha

- Optionale Selbsteinrichtung für Ausschnitt und Drehung. Einstellbares Limit von 4 bis 50 unterschiedlichen Bildern, höchstens fünf Minuten und Übernahme nach mindestens drei bestätigten Aufnahmen.

## 0.4.8 Alpha

- „Rahmen ziehen“ zeigt das Kamerabild direkt in den Test- und Automatik-Einstellungen.
- Ausschnitt und Bilddrehung lassen sich zusammen speichern. Der manuelle Test kann seine Einstellungen auch ohne Testlauf speichern.
- Speichern und Ausschnitt-Reset stehen im selben Bereich und sind optisch getrennt.

## 0.4.7 Alpha

- Die bebilderte Bedienungsanleitung ist direkt über den Menüpunkt „Anleitung“ erreichbar.

- Der Bildausschnitt lässt sich im manuellen Test zurücksetzen. In den Automatik-Einstellungen stellt der Knopf die automatische Ausschnitterkennung wieder her.

## 0.4.6 Alpha

- Die Bilddrehung ist im manuellen Test gradweise einstellbar und kann mit dem Ausschnitt für die Automatik übernommen werden. Bei schwer lesbaren Ziffern weist die App auf diese Einstellung hin.
- Im automatischen Intensivtest prüft die App bei einer unsicheren Ablesung auch eine leichte Drehung nach links und rechts. Ein bestätigter Winkel wird für diese Kamera und diesen Ausschnitt als neuer Startwinkel übernommen. Die bisherigen Versuchslimits bleiben in Kraft.
- Im eigenständigen Modus dient die erste Aufnahme als vorläufiger Vergleichswert. Nach fünf Minuten prüft die App den Stand anhand einer zweiten Aufnahme und gibt ihn bei plausibler Entwicklung frei.

- Bei wiederholt verdeckter Ziffer kann die App optional einen eindeutigen Zwischenstand aus zwei sicheren Ablesungen ergänzen. Die berechnete Ziffer muss manuell ausgewählt werden und bleibt gelb markiert. Den Vorschlag kann man dauerhaft ausblenden.

## 0.4.5 Alpha

- Das letzte Testbild ist beim Öffnen der Übersicht bereits ausgeklappt.
- Der Kameramodus sucht die Ziffernreihe auch ohne vorhandene SLFork-Markierungen.
- Im manuellen Test kannst du den Bildausschnitt mit Maus oder Finger ziehen. Sind die Ziffern danach noch schwer lesbar, weist die App auf Kamerawinkel, Fokus und Beleuchtung hin.

## 0.4.4 Alpha

- Beim ersten Einrichten wählst du die Bildquelle selbst. Der Assistent erklärt die drei Modi direkt neben der Auswahl und empfiehlt ESPHome für den Einstieg mit einer Kamera.

- Der Assistent bietet vorhandene Kamera-Entitäten und erkannte AI-on-the-Edge-Adressen aus Home Assistant an. Die Auswahl füllt das passende Feld aus.
- Ein vorhandener AI-on-the-Edge-ESP kann nur als Kamera dienen. Die App fordert ein frisches Bild an, liest den Stand selbst und prüft ihn auf Plausibilität.

## 0.4.3 Alpha

- Bei drei Nachkommastellen erklärt die Einrichtung, warum die letzte Stelle Fehlmeldungen verursachen kann.
- Scheitert die automatische Prüfung bei drei verschiedenen Bildern nur an der dritten Stelle, kann sie mit gelbem Hinweis bestehen. Für den Verbrauch verwendet die App den Vergleichswert, wenn er die Plausibilitätsprüfung besteht.
- Der optionale Präzisionsmodus verlangt weiterhin, dass alle drei Nachkommastellen stimmen.
- Bei Fehlprüfungen zeigt der Countdown die tatsächliche Wartezeit. Ein separater manueller Test verschiebt einen laufenden automatischen Wiederholungsversuch nur, wenn er den Fehler auflöst.

## 0.4.2 Alpha

- Statusabfrage und Anzeige des letzten Zählerbilds korrigiert. Fehlt die markierte Vorschau, zeigt die App das Originalbild.
- Die Übersicht erklärt sofort, wenn Ablesung und Vergleichswert voneinander abweichen und was zu prüfen ist.
- Nach der Einrichtung startet die automatische Prüfung sofort. Die Übersicht zeigt in Gelb, auf welches Bild die App wartet und wie weit die OCR ist. Fehlt ein aktuelles Bild, bleibt ein gelber Hinweis sichtbar.
- Der Werkreset zeigt die Wartezeit an. Sobald er fertig ist, sind auch der letzte manuelle Test und seine Vorschau aus der Oberfläche entfernt, und der Einrichtungsassistent öffnet sich.

## 0.4.1 Alpha

- Bei einem abgebrochenen SLFork-Messzyklus oder einem fehlenden oder zu alten Bild prüft die App ein frisches Rohbild vom ESP.
- Gelingt die Ablesung, weist die App auf die Bildausrichtung als mögliche Ursache hin. Der Rohbildstand wird ohne ESP-Abgleich angezeigt und verändert die Verbrauchssumme nicht.

## 0.4.0 Alpha

- Retry automatic failures using up to three image checks: the first retry after five minutes, the second after another five minutes, then a one-hour wait for a higher meter reading or a new image.
- Show the failed-check count and retry/wait explanation in the automatic overview.
- Mark OCR digits yellow when repeated reads disagree or the final result was composed from multiple attempts; keep red for unresolved digits and green for recognized digits.
- Rename the shared image area to **Latest test image / Letztes Testbild** because it can show either an automatic or manual test.
- Refresh automatic app-language selection when the Home Assistant profile language changes, and avoid a red offline message for a single status-poll failure.
- Add a German illustrated user guide PDF and link it from the project and app descriptions.
- Preserve existing Home Assistant entity IDs, settings, and application slug.

## 0.3.1 Alpha

- Renamed the user-facing app to AI Meter Reader while preserving the Home Assistant app slug, stored options, and existing entity IDs.
- Added up to ten bounded extra OCR variants after an uncertain automatic reading (15 attempts maximum) and strict-majority digit composition.
- Capture a fresh ESP or Home Assistant camera image after the first failed check; after two failed runs, return to the selected interval.
- Added a persistent pause/resume control for automatic checks, with manual tests still available while paused.
- Show live worker activity, source reachability, and clear reasons for stale images or failed image retrieval.
- Successful manual tests restart the automatic timer; a pass for the same capture and reference can clear a reading mismatch, but not a stale-image or connection failure.
- Added German and English help text for retries, pausing, source status, and shorter intervals.

## 0.3.0 Alpha

- After setup, open the manual test directly and allow a JPG/PNG test image upload up to 3 MB.
- Saving automatic settings starts a new automatic check immediately.
- After the configured OCR attempts, combine digits only when each required position has a strict majority vote; otherwise keep the reading uncertain.
- Verify crop recovery against synthetic meter images at 0°, 90°, 180°, and 270°.
- Keep uploaded test photos out of saved settings and automatic measurement history.

## 0.2.1 Alpha

- Added quick Home Assistant dashboard and Energy dashboard guidance to the setup wizard.
- Decimal comparisons round half up to the selected precision, including carry between digits.
- Wait longer for Home Assistant profile language before showing the first setup screen.
- Moved the voluntary PayPal link into the collapsible About section.
- Kept existing entity IDs, stored settings, and the Alpha release channel.

## 0.2.0 Alpha

## 0.2.0 Alpha

**AI Meter Reader – Alpha release.** Version 0.4.0 remains on the regular Alpha channel. After 0.4, the optional Hall / pulse sensor integration is planned as the first separate Beta change because it needs hardware testing.

- Guided first setup for SLFork / AI on the Edge, Home Assistant cameras, and ESPHome cameras with local OCR. The wizard can be reopened later and shows current values for quick changes.
- Meter format settings for whole and fractional digits, display type, comparison precision, crop, rotation, lighting, OCR attempts, check interval and plausibility limit.
- Optional initial fallback reading with timestamp, plus a per-test fallback value. Manual tests now retain their settings and a successful test restarts the automatic timer.
- Live camera checks capture fresh snapshots with up to 10 attempts within 20 seconds. The manual test shows the original source image, annotated OCR preview, or a clear no-image message.
- OCR processing adds lighting correction for uneven illumination. ESP fallback readings are checked against their last valid timestamp and configured flow limit before being accepted.
- Plausible confirmed readings update an increasing total-consumption sensor. Existing `sensor.rf1_*` entity IDs, app slug and media path remain unchanged.
- The overview keeps automatic status separate from manual diagnostics. Help text, language selection, notifications and the setup flow are available in German and English.
- Only AI on the Edge / SLFork has been tested by the maintainer with a real meter. Other camera and meter modes have simulated tests only.

## 0.1.0 Alpha

- Initial Home Assistant app release with local Tesseract OCR verification for AI on the Edge / SLFork meter images.
