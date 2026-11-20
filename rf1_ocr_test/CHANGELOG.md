# Changelog

## 0.3.1

- **Einrichtung bestätigt das gefundene Zählwerk wieder (kritisch):** Jede fein nachjustierte Fassung desselben Rahmens (z. B. −12° statt −13°, Ziffernrahmen leicht verschoben) galt bisher als neuer Kandidat und setzte die Bestätigungen zurück – heute 16 Bilder mit richtiger Lesung (10492,09 → 10492,18 …), aber 0 von 3 Bestätigungen und Abbruch nach 20 Minuten. Jetzt zählt jedes Bild desselben Zählwerks (Außenrahmen ≥ 80 % deckungsgleich, Drehung ±2°, gleiche Ziffernzahl) als Bestätigung; die Zählerstandsfolge muss weiterhin zum möglichen Durchfluss passen, sodass ein versetzter Rahmen nicht bestätigt wird.
- **Abgebrochene Einrichtung startet nach dem Update von selbst neu:** Ist die letzte Selbsteinrichtung am Zeitlimit gescheitert und hat die Automatik seitdem nichts sicher gelesen, beginnt die App nach dem Update einmal selbst eine neue Einrichtung – auch wenn noch ein alter Rahmen gespeichert ist. Niemand muss etwas antippen.
- **Keine 30-Minuten-Pause mehr, während die Lesefehler-Korrektur sammelt:** Liegt eine Ablesung nur unter einem vermutlich falsch gebuchten Stand und passt zur laufenden Korrektur, zählt sie nicht mehr als Fehlprüfung. Die Automatik prüft im normalen kurzen Takt weiter und schließt die Korrektur nach 15 Minuten ab, statt eine halbe Stunde zu pausieren (heute 13:57–14:41).
- **Schutz gegen falsche „Korrekturen“:** Ein niedrigerer Stand wird nur dann als Korrektur gesammelt, wenn er höchstens 2 m³ oder das Doppelte des möglichen Durchflusses seit dem gespeicherten Stand darunter liegt. Ein um eine Stelle versetzter Rahmen („04912…“ statt „10491…“) kann so nie den Zählerstand ersetzen; solche Ablesungen bleiben normale Fehlprüfungen.
- **Bewährter Rahmen aus älteren Versionen bleibt Startpunkt:** Ein vor 0.2.10 gespeicherter Rahmen wird auch dann zuerst geprüft, wenn sich seitdem eine Einstellung ohne Einfluss auf das Bild geändert hat (passende Ziffernzahl vorausgesetzt). Die Einrichtung bestätigt ihn wie bisher an frischen Bildern. Neue Einträge merken sich zusätzlich die Kamera.

## 0.3.0

- **„So weit ist die Einrichtung“:** Während der Selbsteinrichtung zeigt die Übersicht oben eine senkrechte Fortschrittsliste aller Arbeitsschritte: Kamerabild holen · Zählwerk finden · Rahmen und Drehung prüfen · Rahmen bestätigen (n/3) · Einrichtung speichern · im Hintergrund: letzte Stelle verfeinern (optional). Erledigte Schritte bekommen ein Häkchen und ein kurzes Ergebnis (z. B. „2 Bilder“, „beste Übereinstimmung 88 %“), der laufende Schritt ist hervorgehoben und nennt in Klartext, was gerade passiert („Rahmen 2 von 4 · Drehung −13° · 1 von 3 Bestätigungen“), ausstehende Schritte sind grau. Darunter eine kleine Statistik (Bilder, getestete Rahmen, bisherige Dauer, beste Übereinstimmung). Ohne Animation bei „Bewegung reduzieren“.
- **Gefundene Rahmen immer sichtbar:** Die Kandidatenliste steht während der Einrichtung aufgeklappt unter der Fortschrittsliste – je Rahmen Nummer, Drehung, Übereinstimmung und letzte Lesung; der gerade geprüfte Rahmen ist hervorgehoben.
- **Prüfdetails ausgeklappt mit Ziffern je Versuch:** Während einer automatischen Prüfung sind die Prüfdetails aufgeklappt (wer sie zuklappt, behält das) und zeigen eine kleine Tabelle: Spalten = Ziffernstellen (Vorkomma/Nachkomma getrennt, nicht verglichene Stellen blass), Zeilen = Versuche, darunter das Ergebnis je Stelle (grün einig, gelb abweichend, rot unklar). Auf dem Handy seitlich scrollbar.
## 0.2.10

- **Kein falscher Kubikmeter mehr bei uneinigen Lesungen:** Heute Mittag lasen 3 von 5 Lesungen eines Bildes 10491,4 und 2 von 5 10490,4 – die App nahm die Mehrheit, der Zähler stand aber bei 10490,6. Widersprechen sich Lesungen bei einer Vorkommastelle mit mindestens zwei Stimmen je Ziffer, bleibt die Stelle jetzt offen (lieber unklar als falsch). Ausnahme: eine Rolle, die gerade weiterdreht (rechts daneben steht 9 oder 0). Der zu hohe Stand korrigiert sich über die vorhandene Lesefehler-Korrektur (nach drei stimmigen niedrigeren Ablesungen über mindestens 15 Minuten); dafür werden niedrigere Ziffern nicht mehr als „unmöglich“ ausgeblendet, wenn der gespeicherte Stand selbst falsch ist; zu viel gebuchter Verbrauch wird nicht doppelt gezählt, die nächsten Buchungen gleichen ihn aus.
- **Kamera zu dunkel eingestellt? Die App regelt nach:** Bleibt das Bild auch mit eingeschaltetem Blitz deutlich dunkler als gewohnt, erhöht die App die Verstärkung der Kamera (ESPHome-Regler am selben Gerät, z. B. „Verstärkung“) in kleinen Schritten, höchstens alle 5 Minuten und höchstens bis 20. Debug-Protokoll: `exposure_adjust`. Vorher wartet sie nach einem dunklen Bild ein zweites Mal etwas länger auf den Blitz.
- **Zählerstand-Sensor bleibt nach einer Einrichtung verfügbar:** Bis zur ersten neuen Ablesung zeigt `sensor.rf1_ocr_zaehlerstand` den zuletzt gebuchten Stand (`is_fallback: true`) statt „nicht verfügbar“.
- **Bewährter Rahmen geht nicht mehr verloren:** Der zuletzt bewährte Rahmen gilt jetzt für dieselbe Kamera und dieselbe Ziffernzahl – unabhängig von Bildquellen-Modus, Vergleichssensor, Licht, Ziffernfarbe oder Anzeigeart. Bisher reichte eine solche Änderung im Assistenten, und die nächste Einrichtung begann wieder bei „Ziffernreihe finden“ (`known_good: false`).
## 0.2.9

- **Bilder ohne Blitz erkennen und neu aufnehmen:** Die App merkt sich, wie hell Bilder mit Blitz normalerweise sind. Ist ein Bild deutlich dunkler (Licht noch nicht an oder kurz vorher von außen ausgeschaltet, z. B. durch einen „Blitz dauerhaft an“-Schalter am ESP), schaltet sie das Licht ein, wartet und nimmt sofort ein neues Bild. So wird aus einem dunklen Bild keine Fehlprüfung („1????.???“) mehr. Das gilt für Prüfungen, Einrichtung und Vorschau.
- **Funktionierender Rahmen bleibt Ausgangspunkt:** Jede mit einem zweiten Bild bestätigte Prüfung merkt sich den Rahmen als „bewährt“. Wird die Einrichtung erneut gestartet (auch über den Assistenten), prüft sie diesen Rahmen zuerst, statt bei null zu beginnen. Bisher geschah das nur nach bestimmten Einrichtungen, darum begann die Einrichtung heute früh wieder mit „Ziffernreihe finden“.
- **Debug-Protokoll:** Jeder Start einer Einrichtung oder Hintergrundsuche wird mit Auslöser protokolliert (`setup_start`: Nutzer, Update, Wiederholung, Selbstreparatur, 8. Ziffer, Rahmen-Nachsuche), dunkle Bilder als `dark_picture`.
## 0.2.8

- **Neu-suchen-Knopf auf dem Handy wieder klein:** Im Einrichtungsassistenten zog eine Regel für schmale Bildschirme den Knopf ↻ neben „In Home Assistant gefunden“ auf volle Breite; die Auswahlliste war kaum noch zu sehen. Der Knopf ist jetzt immer 44 × 44 px groß, die Liste nutzt den Rest der Zeile.
## 0.2.7

- **Geräte neu suchen:** Im Einrichtungsassistenten steht neben „In Home Assistant gefunden“ ein kleiner Knopf ↻ („Neu suchen“). Antwortet Home Assistant gerade nicht (z. B. direkt nach einem Neustart) oder ist die Liste leer, sucht die App nach einigen Sekunden einmal selbst erneut und sagt, wenn Home Assistant nicht erreichbar ist.
## 0.2.6

- **Versionsnummer unten auf jeder Seite:** Übersicht, Einstellungen, Werkzeuge und Einrichtung zeigen unten dezent „AI Meter Reader 0.2.6“ mit Link zu den Änderungen.
## 0.2.5

- **Lieber unklar als falsch:** Am Kamerabild von heute Nacht liest die Texterkennung eine unscharfe 6 in mehreren Einstellungen übereinstimmend als 5 und eine unscharfe 7 als 4. Die Ziffernvorlagen sahen jeweils die richtige Ziffer vorn, wurden aber überstimmt. Jetzt gilt: Liegt die gelesene Ziffer in den Vorlagen deutlich hinter der besten (bzw. bei 5/6 schon knapp), bleibt die Stelle offen. Auch die Rahmenverschiebung übernimmt eine Ziffer nur noch, wenn die Vorlagen keine andere Ziffer klar bevorzugen (1/7 ausgenommen, die verwechseln die Vorlagen selbst).
## 0.2.4

- **Unklare Nachkommastellen werden wieder per Rahmenverschiebung gerettet:** Bei Kameras galt für die ganze Prüfung ein Zeitfenster von 20 Sekunden. Seit die Ziffernvorlagen mitlesen, war es nach zwei, drei Lesungen aufgebraucht, und die Verschiebung einzelner Rahmen startete gar nicht mehr („Versuch 5 von 15“). Sie liest das schon aufgenommene Bild und bekommt jetzt ein eigenes Budget von 25 Sekunden. Rahmen der Nachkommastellen werden dabei weiter seitlich verschoben (bis zu einem Viertel der Rahmenbreite), und der rote Rand des Nachkommafelds gilt nicht mehr als „abgeschnittene Ziffer“. Am Kamerabild von heute Nacht wird die 1 an der 7. Stelle so gelesen, die vorher nie erkannt wurde.
- **Keine 7 statt 1:** Die Ziffernvorlagen halten die 1 dieses Zählers (mit langer Fahne) leicht für eine 7. Zwischen 1 und 7 übernimmt die App eine Vorlage jetzt nur noch bei deutlichem Abstand.
- **Debug-Protokoll:** Neues Feld `recovery` je Prüfung – ob die Rahmenverschiebung versucht wurde, warum nicht, mit welchem Ergebnis und wie lange.
## 0.2.3

- **Funktionierende Einrichtung bleibt erhalten:** Ein Tippen auf einen vorgeschlagenen Ziffernbereich im Vorschaubild startet die Selbsteinrichtung nicht mehr sofort neu, sondern markiert den Bereich nur; gestartet wird erst mit dem Knopf darunter. Startet eine neue Einrichtung trotzdem, prüft sie den zuletzt bestätigten Rahmen immer zuerst – auch wenn ein anderer Suchbereich gewählt ist. So setzt sich kein Rahmen auf dem Gehäuserand durch, solange der alte Rahmen weiter liest.
- **Richtige Stelle im Hinweis:** „Die Suche nach der 8. Ziffer wird automatisch wiederholt“ statt „1. Ziffer“, wenn gerade nur eine Ziffer im Hintergrund gelesen wird.
## 0.2.2

- **Blitzreflex nie als Ziffer lesen:** Die erste Automatik nach der Einrichtung zeigte, dass die Texterkennung in der überstrahlten Stelle eine 7 oder 5 „erfindet“. Eine Stelle unter dem Reflex wird jetzt gar nicht mehr gelesen und nur aus dem letzten bekannten Stand ergänzt. Der Reflex wird zusätzlich auch bei eng gezeichneten Ziffernrahmen erkannt.
## 0.2.1

- **Unscharfe Ziffern lesen (Härtetest mit absichtlich unscharfer, schräger Kamera und Blitzreflex):** Neben der Texterkennung vergleicht die App jede Ziffer mit unscharf gerechneten Ziffernvorlagen. Liest Tesseract eine Stelle nicht, übernimmt die App die Vorlage nur bei klarem Abstand zur zweitbesten Ziffer; widerspricht die Vorlage einer gelesenen Ziffer deutlich, bleibt die Stelle offen. An den Kamerabildern des Härtetests werden die 0 und die 8 jetzt gelesen, die vorher nie erkannt wurden.
- **Verdeckte und unsichere Vorkommastellen aus dem letzten bekannten Stand:** Fehlen danach noch Vorkommastellen (z. B. unter dem Blitzreflex), ergänzt die App sie aus dem zuletzt bekannten Zählerstand und dem maximalen Durchfluss – nur wenn genau ein Wert passt oder die Vorlagen einen Wert klar bevorzugen. Das hilft der Selbsteinrichtung und der Automatik; die übliche Gegenprüfung mit zwei Bildern bleibt.
## 0.2.0

- **Ziffernrahmen auf die Ziffer zentriert:** Die Einrichtung rückt jeden Rahmen seitlich auf die hellen Striche der Ziffer. Bisher konnte ein Lichtreflex den Rahmen so verschieben, dass eine 8 halb abgeschnitten war.
- **Spiegelung selbst erkennen (Fire and Forget):** Überstrahlt der Blitz dauerhaft dieselbe Ziffer, schließt die Selbsteinrichtung mit den übrigen Ziffern ab und merkt sich die verdeckte Stelle wie eine markierte Spiegelung. Die Automatik ergänzt sie aus dem letzten bestätigten Stand, wenn nur ein Wert zum maximalen Durchfluss passt; sonst fragt die Übersicht einmal nach dem aktuellen Zählerstand.
- **Experimentelle Funktionen im Schattenbetrieb:** Neuer Schalter (standardmäßig aus) mit Häkchen je Experiment. Erstes Experiment: Perspektivkorrektur (Kippung). Gelesen wird nur bei freier Rechenleistung, es zählt nur das bewährte Ergebnis; das Debug-Protokoll speichert beide (`experiment`). Endpunkt `/testbild-streifen` (nur mit Experimentiermodus) liefert den ausgeschnittenen Ziffernstreifen als Base64.
- **Fehler melden:** Knopf unter Werkzeuge → Debug-Protokoll und Link im Hinweis bei wiederholten Fehlprüfungen; öffnet ein vorausgefülltes GitHub-Issue ohne private Daten. Issue-Vorlage im Repository.

## 0.1.26

- Fire and Forget: Findet die Selbsteinrichtung nach drei schnellen Wiederholungen noch keinen sicheren Rahmen, versucht die App es danach stündlich von selbst erneut, statt stehen zu bleiben. Wird die Kamera später scharfgestellt oder die Spiegelung des Blitzes beseitigt, richtet sich die App ohne Antippen ein. Der Hinweis nennt die häufigsten Ursachen (unscharfes Bild, Spiegelung auf den Ziffern).

## 0.1.25

- Zählwerk mit ESPHome-Kameras finden: Die Selbsteinrichtung sucht das Zählwerkfenster jetzt zuerst über die hellen Ziffern selbst (lokaler Kontrast) statt nur über ein dunkles Fenster. Ein Lichtreflex auf einer Ziffer, der rote Nachkommabereich, ein Strichcode oder die Seriennummer darunter stören nicht mehr. Die Schräglage der Ziffernreihe wird gemessen und das Bild vor dem Lesen gerade gedreht.
- Ziffernrahmen im gefundenen Fenster werden auch bei dunklem, ungleichmäßig beleuchtetem Bild an die Ziffern angepasst.
- Fire and Forget: Nach einem App-Update startet die Selbsteinrichtung einmal von selbst neu, wenn noch kein bestätigter Rahmen vorliegt. Eine laufende Automatik bleibt unberührt.

## 0.1.24

- Blitz der Kamera standardmäßig an: Bei ESPHome- und Home-Assistant-Kameras sucht die App selbst das Licht, das zum selben Gerät gehört (z. B. die Blitz-LED des ESP), und schaltet es für jede Aufnahme ein. Neuer Schalter „Blitz der Kamera verwenden“ (Standard an). Ein eingetragenes externes Licht hat Vorrang.

## 0.1.23

- „Licht für die Aufnahme“: Der Beispieltext im leeren Feld sah wie ein eingetragener Wert aus („light.esp_gaszaehler_blitz“). Jetzt steht dort „leer = ohne Licht, z. B. light.kamera_blitz“.

## 0.1.22

- Licht für die Aufnahme bleibt nicht mehr an: Nach dem Ausschalten liest die App den Zustand zurück und wiederholt den Befehl bis zu viermal, wenn das Licht noch „an“ meldet. Ein ausgelasteter Kamera-ESP hatte „Licht aus“ verzögert oder gar nicht umgesetzt.
- Anleitung: ESPHome-Beispiel mit Abschaltung nach 30 Sekunden im ESP selbst, aktueller Bildrate (Standbilder höchstens eine Sekunde alt) und ohne Drehung/Spiegelung durch ESPHome.

## 0.1.21

- Blitzlicht für Home-Assistant- und ESPHome-Kameras: Neues Feld „Licht für die Aufnahme“ bei der Bildquelle (Assistent und Einstellungen). Die App schaltet das Licht wie AI on the Edge für jede Aufnahme kurz ein, wartet 1,5 Sekunden, holt das Bild und schaltet es wieder aus – auch wenn der Abruf fehlschlägt. Ein Licht, das vorher schon an war, bleibt an.
- Anleitung: ESPHome-Konfiguration für die ESP32-CAM mit Blitz-LED als Licht-Entität.

## 0.1.20

- Laufendes Gas: Sind die Vorkommastellen und die erste Nachkommastelle sicher und nur die letzten zwei verglichenen Stellen unklar (z. B. „10482.8??“), bestätigt die App diese Prüfung mit zwei Nachkommastellen weniger, statt sie scheitern zu lassen. Gebucht wird nur bis zur bestätigten Stelle. Scheitert die Prüfung trotzdem, zählt sie wie bei einer drehenden letzten Rolle nicht für die Pause.
- Adaptives Prüfintervall für alle Bildquellen: Die App lernt den Durchfluss jetzt auch aus Ständen, die mit einem zweiten Bild bestätigt wurden, und prüft früher, wenn eine Rolle bald umspringt. Bisher nur bei AI on the Edge / SLFork. Neue Installationen und Werksresets haben es eingeschaltet; bestehende Einstellungen bleiben.

## 0.1.19

- Einrichtung schneller und ohne Unsinn: Liest ein Kandidat das Zählwerk schon gut (mindestens die eingestellte Übereinstimmung, z. B. 88 %), prüft die App Kandidaten ohne Erkennung (0 %) oder mit mehr als 40 Prozentpunkten Abstand nicht mehr intensiv nach, etwa um 90° gedrehtes Kleingedrucktes oder die Seriennummer.
- Hinweis zur Grobprüfung: „Grobprüfung: Die App testet mehrere feste Rahmen und Winkel und schaltet danach auf die Feinjustierung um …“.

## 0.1.18

- Winkel nach der Einrichtung: Misst die Einrichtung eine Schräglage über ±0,5°, behält sie wie bisher höchstens ±0,5° als Feinwinkel und gibt den Rest als Startwert an die laufende Schräglagenkorrektur. Die ersten automatischen Prüfungen arbeiten so sofort mit dem gemessenen Winkel, statt sich über viele Prüfungen heranzutasten (Beobachtung: −0,5° gespeichert, −1,5° gemessen, die 8 wurde als 6 gelesen).
- Nachprüfung lernt mit: Rettet ein leicht verschobener Rahmen eine Prüfung, wird diese Verschiebung als Kandidat an die lokale Feinausrichtung übergeben. Gespeichert wird sie wie dort erst nach drei frischen Bildern mit zwei verschiedenen Zählerständen; bei Fehlprüfungen nimmt die App sie zurück.
- Einrichtung ohne Ergebnis: Endet eine selbst gestartete Einrichtung ergebnislos, startet die App sie nach 5 Minuten automatisch neu (höchstens dreimal), statt dauerhaft auf „wartet auf Einrichtung“ zu stehen.
- Hinweis bei der Suche nach der 8. Ziffer: „(noch höchstens 4 min)“ statt „Noch höchstens 4 von 4 min“.

## 0.1.17

- Debug-Protokoll für die Selbsteinrichtung: Je ausgewertetem Bild ein Eintrag `setup_image` mit Anzahl der Bildanforderungen, verworfenen Doppelbildern, Abruffehlern, Abruf- und Auswertedauer, Bestätigungen und Lesestand; am Ende ein Eintrag `setup_end` mit Ergebnis und Dauer. Damit lässt sich klären, warum die Einrichtung manchmal nur alle paar Minuten ein neues Bild zählt.
- Texte überarbeitet (DE und EN): Statusmeldungen beschreiben, was die App tut, statt wie eine Aufforderung zu klingen („Nächstes Kamerabild wird angefordert …“ statt „Warte auf ein neues Kamerabild …“). Hinweise wie „Bitte … prüfen“ sind direkte Handlungshinweise („Prüfe …“).
- Veraltete Angabe korrigiert: Nach drei Fehlprüfungen pausiert die App für die eingestellte Zeit (Standard 30 Minuten), nicht mehr eine Stunde.
- Klarere Meldungen zur siebten Ziffer, zur gestörten Erkennung nach zwei Stunden, zum Zurücksetzen, zur Stundenverteilung im Verbrauch und zu Leseprofilen.

## 0.1.16

- Texte nach der Einrichtung: „In den nächsten 20 Minuten optimiert die App im Hintergrund noch Rahmen und Winkel.“ und „Optimierung läuft (noch höchstens X min): Alle Ziffern sind gelesen, die App verbessert noch Rahmen und Winkel.“ Die doppelte Minutenangabe entfällt; der Hinweis zu 2 von 3 Nachkommastellen steht jetzt am Ende.
- Texte überarbeitet: Statusmeldungen der Einrichtung als Zustand statt als Aufforderung („Ausschnitt und Drehung werden geprüft …“ statt „Prüfe …“), klarere Meldungen zu dritter Nachkommastelle, Rohbild-Fallback, Gegenprüfung und eingeschränkter Genauigkeit (DE und EN).

## 0.1.15

- **Schräglage pendelt sich dauerhaft ein:** Der gelernte Ausgleich bleibt erhalten, wenn die App einzelne Rahmen (z. B. die letzte Stelle) neu setzt; bisher begann er dann wieder bei null. Er korrigiert jetzt in kleineren Schritten (70 % der gemessenen Abweichung, ab 0,2°) und läuft dauerhaft weiter mit.
- **Mehr Messpunkte:** Gemessen wird über alle Ziffern bis zur vorletzten (bisher nur die Vorkommastellen). Ziffern, deren rechter Nachbar gerade 8 oder 9 zeigt, lässt die Messung aus – der Übertrag hebt sie schon leicht an.

## 0.1.14

- **Schneller wieder prüfen:** Nach einer Fehlprüfung prüft die App nach 2 statt 5 Minuten erneut, wenn der Rechner gerade Luft hat (Prozessorlast). Die Pause nach drei Fehlprüfungen ist jetzt einstellbar (Einstellungen → „Pause nach drei Fehlprüfungen“), Standard 30 statt 60 Minuten.
- **Keine Pause und kein „Bitte prüfen“, wenn nur die letzte Rolle unklar ist:** Dann war alles andere gelesen; die App schaut einfach bald wieder hin. Auch „Rahmen der letzten Stelle sitzt daneben“ ist kein gelber Warnhinweis mehr, weil die App das selbst behebt.
- **Ganze Rahmenreihe leicht verschieben:** Bleibt eine Prüfung unklar, versucht die App bis zu drei Mal, alle Rahmen gemeinsam ein Stück nach oben, unten oder zur Seite zu setzen. Übernommen wird ein Wert nur, wenn zwei Leseverfahren übereinstimmen, keine Ziffer angeschnitten ist und der Wert plausibel ist.
- **Hinweise führen zur Einstellung:** Ein Klick auf den Hinweis „… Fehlprüfungen … Nächster Versuch gegen …“ öffnet direkt die passende Einstellung.

## 0.1.13

- Meldung nach erfolgreicher Einrichtung: „Die Automatik läuft. In den nächsten 20 Minuten stimmt die App die Rahmen noch im Hintergrund fein ab.“ statt „… prüft sie häufiger“.
- **kWh im Einrichtungsassistenten:** Zustandszahl und Brennwert oder der fertige Umrechnungsfaktor lassen sich jetzt auch im Assistenten eintragen (aufklappbar, optional), nicht nur unter Einstellungen.
- Hinweis im Einrichtungsassistenten aktualisiert: Die dritte Nachkommastelle sucht die App nach der Einrichtung automatisch im Hintergrund und justiert die Rahmen selbst nach – nicht mehr „kann später intensiv gesucht oder manuell markiert werden“.

## 0.1.12

- **Schräglagenmessung korrigiert:** Sie misst nur noch innerhalb der Ziffernrahmen und erkennt helle Fensterkanten (Zeilen, die fast über den ganzen Rahmen leuchten) als solche. Vorher geriet die beleuchtete Kante des Zählwerkfensters mit in die Messung und ergab Werte wie 16°, die verworfen wurden – der Ausgleich blieb dadurch wirkungslos.

## 0.1.11

- **Neusuche des Rahmens wird angezeigt:** Sitzt der Rahmen der letzten Stelle neben der Rolle und sucht die App ihn im Hintergrund neu, steht das jetzt unter dem Zählerstand („… wird gerade im Hintergrund neu gesucht“, mit Restzeit). Danach steht dort zwei Stunden lang, wann der Rahmen automatisch neu gesetzt wurde.
- Debug-Protokoll: Die Schräglagenmessung schreibt jetzt bei jeder Prüfung den Messwert oder den Grund, warum nicht gemessen wurde.

## 0.1.10

- **Fehler behoben – Teiltreffer an der letzten Stelle:** Das Nachschieben fehlender Ziffern (0.1.5) konnte den Rahmen der letzten Rolle neben der Rolle lassen; eine angeschnittene 9 wurde als 4 gelesen und übernommen. Jetzt wird die letzte Rolle vor dem Nachschieben auf die Rollenmitte gesetzt (wie die Suche aus 0.1.4) und nur noch nach oben und unten verschoben.
- **Angeschnittene Ziffern werden nicht mehr gelesen:** Läuft eine Ziffer in einem verschobenen Rahmen an den linken oder rechten Rand, verwirft die App diese Lesung – beim Nachschieben, bei der Suche nach der 8. Ziffer und bei deren Neusuche.
- Die langfristige Feinjustierung der Rahmen verschiebt die letzte Rolle nicht mehr seitlich.

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
