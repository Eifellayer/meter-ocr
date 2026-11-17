# AI Meter Reader – lokale Zählerablesung für Home Assistant

**Home Assistant App / Add-on für Kamera-OCR am Gaszähler.** Liest mechanische Zähler lokal mit Tesseract, unterstützt ESPHome- und Home-Assistant-Kameras und kann Messwerte von AI on the Edge / SLFork gegenprüfen.

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

📘 [Bebilderte Bedienungsanleitung (PDF)](docs/Bedienungsanleitung-AI-Meter-Reader.pdf) · [App-Dokumentation](rf1_ocr_test/DOCS.md)

**Aktueller Stand: 0.6.3 Stable.** Die Ersteinrichtung prüft gedrehte Aufnahmen. Die Automatik ist auf zehn Minuten voreingestellt, und das Intervall lässt sich anpassen. Die Zähler-Demo läuft ohne Kamera. [Änderungen](rf1_ocr_test/CHANGELOG.md)

**Zählerstände direkt in Home Assistant aus Kamerabildern lesen und prüfen.**

## Ausprobieren und mitmachen

- **Demo ohne Kamera** – App installieren, Weboberfläche öffnen und die Zähler-Demo ausprobieren. Das künstliche Beispiel zeigt OCR, Ausrichtung und eine simulierte verdeckte Ziffer.
- **Eigenen Zähler einrichten** – Bildquelle wählen und die Selbsteinrichtung starten. Drei ausgewählte Nachkommastellen schließen die automatische Feinprüfung der letzten Rolle ein. Bei zwei Stellen entfällt diese Prüfung.
- **Fehler oder Ideen melden** – App-Version, Bildquelle, Zählertyp und die erwartete Ablesung helfen beim Nachstellen. [Support und Rückmeldungen](https://github.com/Eifellayer/meter-ocr/issues)

**Langfristiges Ziel:** AI on the Edge / SLFork soll keine Voraussetzung mehr sein. AI Meter Reader soll Bilder direkt aus Home Assistant beziehen und die Auswertung lokal dort übernehmen – flexibel für unterschiedliche Zählertypen, Kamerawinkel, Bildausschnitte und Lichtverhältnisse. Das ist das Projektziel, kein Versprechen, dass jeder Zähler bereits unterstützt oder praktisch getestet ist.

## Tester und Rückmeldungen willkommen

Du nutzt Home Assistant mit einem Gas-, Wasser- oder anderen Zähler? Gesucht werden Tester mit unterschiedlichen Kameras, Ausschnitten und Lichtverhältnissen. Die zuschaltbare Langzeit-Feinjustierung und die adaptiven Intervalle brauchen echte Langzeittests. Für reale Prüfungen nutze ich selbst AI on the Edge; andere Quellen und Zählertypen sind bislang nur simuliert getestet. Wenn du beim Testen helfen möchtest, melde dich über [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues) und nenne App-Version, Zählertyp und Bildquelle. Bitte keine Zugangsdaten oder ungeschwärzten Fotos mit persönlichen Informationen posten.

AI Meter Reader liest das Zählerfoto mit **Tesseract OCR**. Mit ESPHome oder einer anderen Home-Assistant-Kamera kann die App einen eigenen OCR-Stand liefern. Mit **AI on the Edge / SLFork** oder einem Referenzsensor prüft sie zusätzlich, ob der vorhandene Messwert zum Bild passt.

Der aktuelle Schwerpunkt liegt auf mechanischen Gaszählern mit einstellbaren Ziffern vor und nach dem Komma. Kleine Zeiger und analoge Rädchen werden noch nicht automatisch ausgewertet. Die Messwertausgabe ist derzeit auf Kubikmeter ausgelegt; weitere Zählertypen und Situationen sollen mit Tester-Rückmeldungen schrittweise dazukommen.

AI Meter Reader ist ein öffentliches Hobbyprojekt für die Plausibilitätskontrolle. [Hinweise zur Nutzung](#hinweise-zur-nutzung)

## Was wird kontrolliert?

Die Standardeinstellung vergleicht **fünf Vorkommastellen, also volle m³**. Erkannte Nachkommastellen werden zusätzlich angezeigt. Ein `?` steht für eine unklare Ziffer. Solange `vergleich_nachkommastellen: 0` eingestellt ist, werden Nachkommastellen nicht bewertet. Bei 1–3 Vergleichsstellen wird der Wert auf die gewählte Stelle gerundet (ab 5 aufwärts); die nächste bekannte Ziffer entscheidet über die Rundung.

Die App holt das letzte vorhandene Foto sowie die zugehörigen Werte aus SLFork. Sie erkennt den Ziffernausschnitt anhand der grünen Rahmen oder nutzt einen eingestellten Bildausschnitt. Tesseract OCR liest den Zählerstand unabhängig aus dem Bild. Bei einer unsicheren automatischen Erstlesung nutzt die App bis zu zehn zusätzliche Bildaufbereitungen (höchstens 15 Versuche insgesamt) und setzt Ziffern nur bei einer strikten Mehrheit zusammen. Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Dabei wird das aktuelle Bild der Quelle erneut abgerufen; ob es neu ist, prüft die App am Zeitstempel. Bleiben drei Prüfungen erfolglos, wartet sie eine Stunde auf einen höheren Zählerstand oder ein neues Bild und versucht es dann erneut. Nach einem erfolgreichen Abgleich gilt wieder das eingestellte Prüfintervall.

Im SLFork-Modus gleicht die App den OCR-Wert mit **Raw Value** und **Actual Value** ab. Im Kameramodus kann ein aktueller kumulierter m³-Sensor als Referenz dienen. Ohne Referenzsensor wird nur das OCR-Ergebnis ausgegeben.

Wenn ein SLFork-Messzyklus abbricht oder sein aufbereitetes Bild zu alt ist, fordert die App ein frisches Rohbild direkt von der ESP-Kamera an. Dafür verwendet sie den eingestellten Bildausschnitt und die gewählte Drehung. Gelingt die Ablesung, zeigt die App den Stand ohne ESP-Abgleich und weist auf die Bildausrichtung und Referenzmarken als mögliche Ursache hin. Das Ergebnis zählt weder als bestätigter Abgleich noch für den Verbrauch.

## Dauerhafte Einstellungen für die automatische Kontrolle

In der Weboberfläche stehen unter **„Automatische Prüfung – Einstellungen“** vier dauerhaft gespeicherte Prüfregeln:

- **Vergleich:** Nur volle m³ (0) oder zusätzlich 1–3 Nachkommastellen. Bei Nachkommastellen wird auf die gewählte Genauigkeit gerundet; die nächste bekannte Stelle entscheidet über die Rundung.
- **Präzisionsmodus (optional):** Bei drei Nachkommastellen muss auch die letzte Stelle stimmen. Ohne Häkchen kann die automatische Prüfung mit gelbem Hinweis bestehen, wenn bei drei verschiedenen Aufnahmen nur die dritte Stelle abweicht oder unklar bleibt. Für den Verbrauch verwendet die App dann den plausiblen Vergleichswert.
- **Max. OCR-Versuche:** 1–10 Versuche pro Zählerbild (Standard: 5). Bei einer bestätigten Übereinstimmung endet die Prüfung sofort.
- **Ziffernfarbe:** Automatisch erkennen (Standard) oder gezielt helle bzw. dunkle Ziffern lesen.
- **Bildbereich:** Ziffernrahmen automatisch erkennen (Standard) oder einen festen Ausschnitt samt Breite der Vorkommastellen dauerhaft verwenden.

Auf **„Speichern“** klicken. Die Einstellungen gelten sofort; eine neue automatische Prüfung startet direkt und bleiben auch nach einem Neustart erhalten. Wird die Vergleichsgenauigkeit geändert, beginnt die Bestätigungszählung bei der nächsten automatischen Prüfung neu: Treffer mit der bisherigen Genauigkeit gelten nicht als Nachweis für die neue Regel.

Technisch werden die Web-Einstellungen separat im App-Datenverzeichnis (`/data/auto-pruefregeln.json`) abgelegt. Solange diese Datei existiert, haben ihre Werte für Vergleich, Versuche, Ziffernfarbe und Bildbereich **Vorrang vor den entsprechenden Feldern der Home-Assistant-App-Konfiguration**. Ohne gespeicherte Web-Einstellungen verwendet die App die Werte ihrer Konfiguration.

## Bildquelle und Ersteinrichtung

Beim ersten Öffnen führt ein kompakter Einrichtungsassistent durch Bildquelle, Zählertyp, Stellenformat, Bildbereich, Prüfplan und Benachrichtigungen. Die Einrichtung kann jederzeit erneut geöffnet werden; aktuelle Werte sind vorausgefüllt, sodass sich einzelne Einstellungen schnell ändern lassen. Hilfetexte sind bei Bedarf aufklappbar. Die automatische Prüfung bleibt klar vom manuellen Diagnosebereich getrennt.

Wähle zuerst deine Bildquelle. Wer neu mit einer Kamera startet, wählt am einfachsten **ESPHome / Kamera**. Neben der Auswahl steht, wann die anderen Modi passen. **In Home Assistant gefunden** bietet vorhandene Kameras und gemeldete AI-on-the-Edge-Adressen an. Gaszähler stehen in der Liste oben. Die Automatik wartet auf eine Bildquelle und einen bestätigten Rahmen, einen gespeicherten Startwert oder ein geprüftes Testbild.

| Modus | Wann passt er? |
| --- | --- |
| **SLFork / AI on the Edge** | Dein vorhandener ESP liefert das Foto und den Vergleichswert. Gib seine Adresse ein. |
| **Home-Assistant-Kamera** | Wähle eine `camera.*`-Entität und bei Bedarf einen aktuellen Referenzsensor in m³. |
| **ESPHome oder Kamera mit lokaler Ablesung** | Die Kamera liefert das Bild. AI Meter Reader liest den Stand lokal und stellt ihn als `sensor.rf1_ocr_zaehlerstand` bereit. |

Mit **AI on the Edge / SLFork → ESP nur als Kamera verwenden** genügt die ESP-Adresse. AI Meter Reader holt ein frisches Bild und liest den Zähler selbst, auch wenn die Ausrichtung oder Ablesung am ESP scheitert. Verwende bei Bedarf einen festen Ausschnitt aus dem Rohbild.

Für ESPHome richte eine [ESP32-Kamera](https://esphome.io/components/esp32_camera/) mit [nativer API](https://esphome.io/components/api/) ein und füge das Gerät in Home Assistant hinzu. Prüfe das Kamerabild dort und wähle anschließend die `camera.*`-Entität in AI Meter Reader. Öffne **Manuellen Test**, passe den Bildausschnitt an und übernimm die Vorschau in die Automatik. Die App benötigt für diese Betriebsart weder SLFork noch einen Referenzsensor.

Für eine eigenständige Ablesung braucht die App mehrere übereinstimmende OCR-Versuche derselben Aufnahme. Fünf Minuten später prüft sie den vorläufigen Stand mit einer zweiten Aufnahme. Erst bei gleichbleibendem Stand oder plausiblem Zuwachs gibt sie ihn frei. Bei einer unsicheren Lesung oder einem Rückgang gegenüber dem letzten gültigen Stand derselben Kamera wird er als **nicht verfügbar** gemeldet. Ein OCR-Stand ohne Referenz ist eine eigenständige Ablesung. Für das Energie-Dashboard gibt es einen kumulativen Verbrauchssensor. Ein späterer Wechsel startet die automatische Bestätigungszählung für die neue Quelle neu.

## Kamerabild und Ausschnitt einrichten

Im Kameramodus sucht die App die Ziffernreihe im Originalbild. Wenn der automatische Ausschnitt nicht passt, öffne **Test einstellen → Ausschnitt im Bild ziehen**. Markiere die gesamte Ziffernreihe mit Maus oder Finger und wähle **Jetzt prüfen**. Passt die Vorschau, kannst du den Ausschnitt für die Automatik übernehmen. Sind die Ziffern im gewählten Ausschnitt weiterhin schwer lesbar, prüfe Kamerawinkel, Fokus und Beleuchtung.

Öffne **Manuellen Test** und wähle unter **Bildbereich** die manuelle Einstellung. Gib die Koordinaten im Originalbild in Pixeln ein. Unter **Bilddrehung (°)** kannst du die Neigung gradweise korrigieren. Positive Werte drehen nach rechts, negative nach links. Die Breite der Vorkommastellen bezieht sich auf den Ausschnitt nach der Drehung. Mit **Jetzt prüfen** siehst du das Auswertungsergebnis und kannst den getesteten Ausschnitt mitsamt Drehung für die Automatik übernehmen.

Im automatischen Intensivtest probiert die App bei Bedarf kleine Drehungen aus. Einen Winkel, der zu einem bestätigten Ergebnis geführt hat, übernimmt sie als Ausgangspunkt für dieselbe Kamera und denselben Ausschnitt. Die Voreinstellung erkennt helle oder dunkle Ziffern automatisch. Weitere OCR-Versuche können ungleichmäßiges Licht im Ziffernfenster ausgleichen. Glanzstellen, die Ziffern verdecken, und starke Perspektivverzerrungen erfordern ein besseres Kamerabild. Bei Zählern mit Rollenfenster und kleinen Zeigern lässt sich mit **volle m³** das Rollenfenster einzeln testen. Die Zeiger selbst werden nicht ausgewertet.

Der [Vergleichstest mit zehn Gas-, Wasser- und Stromzählerfotos](METER-PHOTO-TESTS.md) dokumentiert simulierte OCR-Läufe mit öffentlich zugänglichen Bildern. Er ist kein Hardwaretest.

> **Teststand:** Der Maintainer verwendet für Tests an einem realen Zähler ausschließlich AI on the Edge / SLFork. Kamera- und ESPHome-Modi sowie abweichende Zählertypen sind automatisiert und simuliert geprüft; ein realer Gerätetest dafür liegt nicht vor.

Unter **Automatische Prüfung → Spiegelungen und verdeckte Ziffern** kannst du optional eine einzelne Ziffer ergänzen lassen. Die App verwendet den vorherigen und den nächsten sicheren Stand samt Bildzeiten und maximalem Durchfluss. Auch ein einmal manuell abgelesener Startwert kann den ersten Vergleichswert liefern. Wenn es genau eine Möglichkeit gibt, wählst du die vorgeschlagene Ziffer aus und bestätigst den Zwischenstand. Gelb markiert die berechnete Ziffer. Die App verwendet den Zwischenstand weder als neue Referenz noch als zusätzliche Verbrauchsbuchung. Den Vorschlag kannst du dauerhaft ausblenden.

### Selbsteinrichtung für Ausschnitt und Drehung

Wähle **Automatische Selbsteinrichtung (empfohlen)** unter **Bildbereich**. Die Suche startet beim Speichern. Der aktuelle und der nächste Schritt stehen neben der Vorschau. Du kannst die Suche auch über **Übersicht → Werkzeuge → Selbsteinrichtung** starten oder jederzeit stoppen. Nach drei bestätigten Aufnahmen speichert die App den Rahmen und übergibt die Gegenprüfung an die Automatik.

Bei **Manuell einrichten** lädst du ein Kamerabild oder wählst ein Testbild derselben Kamera. Ziehe einen Rahmen um die Ziffern, prüfe bei Bedarf die Drehung und bestätige den Rahmen vor dem Speichern.

## Plausibilitätsprüfung und Energie-Dashboard

Für den Verbrauch verwendet AI Meter Reader automatische Treffer mit Referenz oder übereinstimmende OCR-Versuche im eigenständigen Modus. Der erste gültige Stand setzt die Basis. Danach vergleicht die App den neuen Stand mit der letzten gültigen Messung. Sie verwirft Rücksprünge und Anstiege, die für die verstrichene Zeit zu groß sind. Die berücksichtigte Ziffernauflösung bestimmt den Rundungsspielraum.

Unter **Automatische Prüfung – Einstellungen → Maximaler Durchfluss** trägst du den Qmax-Wert vom Zähler ein. Die Vorgabe für G4 beträgt 6 m³/h. Ein abgelehnter Wert verändert den Verbrauchszähler nicht. Wechselt die Bildquelle oder die Vergleichsgenauigkeit, dient die nächste gültige Ablesung als Basis für weitere Verbrauchsdifferenzen.

Füge in Home Assistant unter **Energie → Einstellungen → Gasverbrauch** den Sensor **AI Meter Reader Gasverbrauch gesamt** (`sensor.rf1_verbrauch_gesamt`) hinzu. Er entsteht mit der ersten gültigen Messung und summiert die bestätigten Verbrauchsdifferenzen in m³. Home Assistant berechnet aus diesem kumulativen Wert die Ansichten für Stunde, Tag, Woche und Monat.

## Benachrichtigungen und Prüfstatus

Oben zeigt ein grüner Haken einen bestätigten Vergleich. Bei einem aktuellen Problem erscheint ein roter Hinweis. **Ignorieren** blendet diesen Vorfall in der Oberfläche aus. Ein neuer Vorfall erscheint wieder, und die Benachrichtigungsregeln gelten weiterhin.

Öffne **Benachrichtigungen** und aktiviere **Bei anhaltenden Problemen benachrichtigen**. **Hinweis nach** bestimmt, wie viele Minuten ohne erfolgreiche automatische Prüfung bis zum Home-Assistant-Hinweis vergehen. Mit der zweiten Wartezeit legst du fest, wann ein noch offener Hinweis per Handy-Push oder E-Mail weitergeleitet wird. **0 Stunden** versendet die Nachricht zusammen mit dem Hinweis.

- **Nur in Home Assistant:** Beide optionalen Ziele leer lassen.
- **Handy-Push:** Den Companion-Dienst eintragen, zum Beispiel `notify.mobile_app_mein_handy`.
- **E-Mail:** Die [SMTP-Integration](https://www.home-assistant.io/integrations/smtp/) samt Empfänger in Home Assistant einrichten. Unter **E-Mail oder anderes Ziel** dessen `notify.*`-Entität eintragen, zum Beispiel `notify.meine_email`. Andere Benachrichtigungs-Entitäten funktionieren ebenfalls.

Je Ziel wird pro Vorfall höchstens eine erfolgreiche Nachricht erfasst. Wenn du den Hinweis in Home Assistant schließt oder die automatische Prüfung wieder gelingt, entfallen ausstehende Nachrichten. Manuelle Tests senden keine Nachrichten. Ein bestehender `push_dienst` wird übernommen, bis du die Benachrichtigungen in der Oberfläche speicherst.

## Sprache der Weboberfläche

**Automatisch (Home Assistant)** verwendet die im angemeldeten Home-Assistant-Profil gewählte Sprache, wenn die App über Ingress darauf zugreifen kann. Unterstützt werden Deutsch und Englisch einschließlich Varianten wie `de-AT` und `en-US`. Fehlt eine unterstützte Profilsprache, gilt die erste passende Browsersprache, sonst Deutsch. Eine ausdrückliche Auswahl von **Deutsch** oder **English** wird pro angemeldetem Ingress-Nutzer gespeichert. Die Auswahl **Automatisch** übernimmt beim nächsten Öffnen oder Neuladen wieder das Profil. Ohne eindeutige Ingress-Identität gilt die manuelle Wahl innerhalb der aktuellen Navigation.

## „Jetzt prüfen“ – erweiterter manueller Test

Der Bereich **„Manuellen Test öffnen“** bleibt im Normalbetrieb zugeklappt. Bei Bedarf aufklappen: Dort lassen sich **Ziffernfarbe, Vergleichsgenauigkeit und maximale OCR-Versuche** für diesen einen Test einstellen. Zusätzlich kann man die automatische Bildausschnitterkennung deaktivieren und einen **manuellen Ausschnitt (links, oben, rechts, unten) sowie die Breite der Vorkommastellen** ausprobieren, ohne die automatischen Prüfregeln zu verändern. Wenn für den manuellen Ausschnitt eine Vorschau erstellt werden konnte, erscheint **„Getesteten Ausschnitt für die Automatik übernehmen“**. So lassen sich die Koordinaten direkt speichern, ohne sie erneut in Home Assistant einzugeben.

Der Button **„Jetzt prüfen“** startet einen manuellen Test mit dem bereits vorhandenen Bild. Er löst keine neue Aufnahme am ESP aus. Die Weboberfläche zeigt unmittelbar den aktuellen Schritt:

1. Anfrage angenommen
2. Bild und Referenzwerte laden
3. OCR-Auswertung: bei unsicherer automatischer Ablesung bis zu 15 begrenzte Versuche; Fortschritt wird in der Oberfläche angezeigt
4. Ergebnis speichern und abschließen

Der Balken zeigt **tatsächlich abgeschlossene OCR-Versuche**, nicht eine geschätzte Laufzeit. Die Schaltfläche wird während der Prüfung zu **„Prüfung läuft …“** und ist vorübergehend gesperrt. Danach erscheint direkt **„Test erfolgreich“** bei Übereinstimmung (dezent grün) oder eine verständliche Fehler- bzw. Abweichungsmeldung (dezent rot). Eine erfolgreiche Bildlesung ohne Referenz wird neutral angezeigt. Der manuelle Test verändert weder den automatischen Zeitplan noch die Trefferzahl. Das **OCR-Testbild** markiert mit **grünen Rahmen** gelesene Ziffern und mit **roten Rahmen** unklare Ziffern. Ohne erkannte Einzelrahmen sind die Rahmen nur eine angenäherte Aufteilung. Grün bedeutet lediglich **als Ziffer gelesen**, nicht automatisch eine Übereinstimmung mit dem Referenzwert.

Unter **„Mehr Infos“** lassen sich die einzelnen OCR-Versuche mit ihren gelesenen Werten ansehen. Bei unsicherer Erkennung nennt das Ergebnis – soweit ermittelbar – die betroffenen Vorkomma- und Nachkommastellen. Eine bestätigte Prüfung erklärt direkt, auf welcher Vergleichsgenauigkeit sie beruht.

Die kompakte Weboberfläche zeigt die wichtigsten Angaben in getrennten Bereichen, Datum und Uhrzeit kurz als **TT.MM.JJ HH:MM** und die Kontrollbilder in einem ausklappbaren Bereich. Technische Diagnosewerte stehen weiterhin in Home Assistant zur Verfügung, ohne die normale Ansicht zu überladen.

**Zwei unterschiedliche Einstellungen:** Die **1 bis 10 OCR-Versuche** betreffen die Auswertung eines einzelnen Bilds. Die **fünf bestätigten automatischen Prüfungen innerhalb von 24 Stunden** sind dagegen ein separates Kontrollziel. Ein manueller Versuch erhöht diese Zahl nicht.

## Automatische Kontrolle

Nach erfolgreichem Abgleich prüft die App normalerweise nach einer Stunde erneut. Nach einem Fehler folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Nach drei erfolglosen Prüfungen wartet sie eine Stunde auf einen höheren Zählerstand oder ein neues Bild und versucht es dann erneut. Die Übersicht zeigt den Fehlprüfungszähler und den jeweiligen Wartehinweis; der genaue Countdown steht bei „Nächste Prüfung“. Standardmäßig meldet `sensor.rf1_pruefstatus` nach vier Stunden ohne erfolgreiche Prüfung `review_due`. Wartezeiten und Benachrichtigungsziele lassen sich einstellen.

Über **„Automatik pausieren“** kannst du automatische Prüfungen anhalten und später fortsetzen. Die gelbe Meldung zeigt die Pause; manuelle Tests bleiben verfügbar. Der Pausenzustand bleibt nach einem Neustart erhalten. Die Übersicht zeigt, ob die App läuft und wartet, ein Bild aufnimmt oder auswertet, sowie ob ESP/Kamera erreichbar sind und warum ein Bild als zu alt oder unlesbar gilt. Wenn die App selbst gestoppt oder vorübergehend nicht erreichbar ist, meldet die geöffnete Oberfläche den Verbindungsverlust.

Die Automatik lässt sich über **„Automatik pausieren“** anhalten und später fortsetzen. Eine gelbe Meldung zeigt den Pausenzustand; manuelle Tests bleiben verfügbar. Das bleibt auch nach einem Neustart erhalten. Im Übersichtsbereich zeigt AI Meter Reader außerdem, ob es auf den nächsten Prüftermin wartet, gerade ein Bild aufnimmt und auswertet oder ob ESP/Kamera kein neues beziehungsweise kein lesbares Bild geliefert hat. Bei gestoppter oder nicht erreichbarer App meldet die geöffnete Oberfläche den Verbindungsverlust.

Ein SLFork-Messzeitpunkt wird automatisch nur einmal gezählt. Alte Bilder lassen sich weiterhin manuell prüfen. Bei einer allgemeinen Home-Assistant-Kamera verwendet die App den Abrufzeitpunkt. Für unabhängige Bestätigungen muss die Kamera aktuelle Bilder liefern. Ein konfigurierter Referenzsensor muss den Stand in `m³` melden und innerhalb von fünf Minuten zum Bildabruf aktualisiert worden sein.

## Voraussetzungen

- Home Assistant mit Supervisor und App-Store (ARM64 oder AMD64)
- **SLFork / AI on the Edge** auf einem im Heimnetz erreichbaren ESP mit gut ausgerichteten Ziffernrahmen, **oder** eine geeignete `camera.*`-Entität in Home Assistant
- Ein lesbares Zählerbild; zum Vergleich ein passender Messwert (im Kameramodus optional ein aktueller kumulierter Sensor in m³)

## Installation

1. In Home Assistant unter **Einstellungen → Apps → App installieren → ⋮ → Repositories** das Repository **Add-ons by Eifellayer** über den [Stable-Link](https://github.com/Eifellayer/meter-ocr#stable) hinzufügen.
2. **AI Meter Reader** installieren. Bei einem Upgrade bleiben App-ID, Entitäten und gespeicherte Einstellungen erhalten.
3. Für SLFork `esp_url` auf die Adresse des ESP setzen (z. B. `http://esp-gaszaehler.local`). Alternativ `kamera_entitaet`, `ausschnitt` und optional `referenz_entitaet` konfigurieren.
4. App starten, **Weboberfläche öffnen** und mit **Jetzt prüfen** eine Testlesung durchführen.

Pulszähler-Erweiterungen folgen frühestens ab 0.6. Bitte vor jedem Update eine Sicherung deiner Home-Assistant-Konfiguration erstellen.

## Wichtige Einstellungen

| Einstellung | Funktion |
| --- | --- |
| `esp_url` | Adresse des SLFork-ESP |
| `vergleich_nachkommastellen` | 0 = volle m³, 1–3 = genauere Vergleichsstellen |
| `ocr_versuche` | Maximale OCR-Versuche je Bild, 1 bis 10 (Standard: 5) |
| `kamera_entitaet` | Optionales Kamerabild aus Home Assistant |
| `referenz_entitaet` | Optionaler kumulierter m³-Sensor im Kameramodus |
| `ausschnitt`, `vorkomma_breite` | Manueller Ziffernbereich, falls nötig |
| `push_dienst` | Ältere Voreinstellung für den Companion-Push |

**Automatik:** Vergleichsgenauigkeit, maximale OCR-Versuche, Ziffernfarbe und Bildbereich im eigenen Einstellungsbereich speichern. **Manuell:** Die erweiterten Testoptionen gelten nur für den geöffneten Einzeltest. Die kurze Erklärung von „Jetzt prüfen“ lässt sich über das Infosymbol aufklappen.

## Wo stehen die Ergebnisse?

- **Weboberfläche öffnen:** Status, manueller Test mit Fortschritt, automatische Kontrolle und Kontrollbilder.
- `sensor.rf1_pruefstatus`: automatischer Prüfstatus und technische Diagnosen.
- `sensor.rf1_kontrollbild`: OCR-Erkennung, Bildzeit, `ocr_attempts` und `matches_last_24h`.
- **Medien → Lokale Medien → rf1:** `kontrollbild.jpg` und `letzter_treffer.jpg`.

Eine Meldung `match` bedeutet Übereinstimmung **bei der eingestellten Genauigkeit** – nicht notwendigerweise, dass jede sichtbare Nachkommastelle erkannt wurde.

## Hinweise zur Nutzung

Mit KI-Unterstützung entwickelt. Die OCR kann Ziffern falsch erkennen. Für Abrechnungen und Meldungen gilt der direkt am Zähler geprüfte Stand.

Soweit gesetzlich zulässig, wird die Software ohne Gewähr für Richtigkeit, Verfügbarkeit oder Eignung bereitgestellt und die Haftung für Schäden aus ihrer Nutzung ausgeschlossen. Es gelten die zwingenden gesetzlichen Haftungsvorschriften, insbesondere bei Vorsatz, grober Fahrlässigkeit, Verletzungen von Leben, Körper oder Gesundheit und nach dem Produkthaftungsrecht.

## Projekt unterstützen

AI Meter Reader ist ein kostenloses Hobbyprojekt. Wenn sie dir hilft, freue ich mich über eine [freiwillige PayPal-Spende](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8).

[Änderungsprotokoll](rf1_ocr_test/CHANGELOG.md) · [Quellen](SOURCES.md) · [Home-Assistant-App](rf1_ocr_test/README.md) · [English documentation](README.en.md)

<img src="assets/project-logo.png" alt="Projektlogo" width="120">

## Projekt teilen

Ein kurzer Text für Smart-Home-Gruppen und soziale Netzwerke

> AI Meter Reader liest mechanische Gaszähler mit lokaler OCR direkt in Home Assistant. Mit automatischer Rahmensuche, Bilddrehung und einer Demo ohne Kamera. Rückmeldungen zu unterschiedlichen Zählern und Kameras sind willkommen.
>
> https://github.com/Eifellayer/meter-ocr
>
> #HomeAssistant #SmartHome #OCR #ESP32CAM #ESPHome #SelfHosted

Suchbegriffe für dieses Projekt sind Home Assistant Add-on, lokale Zählerablesung, Gaszähler OCR, camera meter reading, meter OCR, ESP32-CAM und AI on the Edge.

## Neue Version sofort suchen

In Home Assistant unter **Entwicklerwerkzeuge → Aktionen** diese Aktion ausführen. Sie lädt den App-Katalog unmittelbar neu.

```yaml
action: homeassistant.update_entity
data:
  entity_id: update.meter_ocr_update
```

Sobald die neue Version bei der Update-Entität angezeigt wird, installiert die aktivierte automatische Aktualisierung sie. Alternativ die Installation mit dieser Aktion anstoßen.

```yaml
action: update.install
target:
  entity_id: update.meter_ocr_update
```

Im Home-Assistant-Terminal lässt sich der Katalog mit `ha store reload` neu laden.
