# Changelog

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
