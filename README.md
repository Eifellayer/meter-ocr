# Meter OCR für Home Assistant

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

**Aktueller Stand: 0.2.1 Alpha.** Bis Version 0.5 gibt es keine separate Beta-App; getestet wird über die reguläre Meter-OCR-App. Ab 0.5 gibt es Beta-Versionen nur bei größeren Änderungen mit zusätzlichem Testbedarf.

**Zählerstände direkt in Home Assistant aus Kamerabildern lesen und prüfen.**

**Langfristiges Ziel:** AI on the Edge / SLFork soll keine Voraussetzung mehr sein. Meter OCR soll Bilder direkt aus Home Assistant beziehen und die Auswertung lokal dort übernehmen – flexibel für unterschiedliche Zählertypen, Kamerawinkel, Bildausschnitte und Lichtverhältnisse. Das ist das Projektziel, kein Versprechen, dass jeder Zähler bereits unterstützt oder praktisch getestet ist.

## Beta-Tester gesucht

Du nutzt Home Assistant mit einem Gas-, Wasser- oder anderen Zähler? Gesucht werden Tester mit unterschiedlichen Kameras, Ausschnitten und Lichtverhältnissen. Der reguläre App-Stand ist bis Version 0.5 der Testkanal. Für reale Prüfungen nutze ich selbst AI on the Edge; andere Quellen und Zählertypen sind bislang nur simuliert getestet. Wenn du beim Testen helfen möchtest, melde dich über [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues) und nenne App-Version, Zählertyp und Bildquelle. Bitte keine Zugangsdaten oder ungeschwärzten Fotos mit persönlichen Informationen posten.

Meter OCR liest das Zählerfoto mit **Tesseract OCR**. Mit ESPHome oder einer anderen Home-Assistant-Kamera kann die App einen eigenen OCR-Stand liefern. Mit **AI on the Edge / SLFork** oder einem Referenzsensor prüft sie zusätzlich, ob der vorhandene Messwert zum Bild passt.

Der aktuelle Schwerpunkt liegt auf mechanischen Gaszählern mit einstellbaren Ziffern vor und nach dem Komma. Kleine Zeiger und analoge Rädchen werden noch nicht automatisch ausgewertet. Die Messwertausgabe ist derzeit auf Kubikmeter ausgelegt; weitere Zählertypen und Situationen sollen mit Tester-Rückmeldungen schrittweise dazukommen.

Meter OCR ist ein privates Hobbyprojekt für die Plausibilitätskontrolle. [Hinweise zur Nutzung](#hinweise-zur-nutzung)

## Was wird kontrolliert?

Die Standardeinstellung vergleicht **fünf Vorkommastellen, also volle m³**. Erkannte Nachkommastellen werden zusätzlich angezeigt. Ein `?` steht für eine unklare Ziffer. Solange `vergleich_nachkommastellen: 0` eingestellt ist, werden unklare Nachkommastellen nicht bewertet.

Die App holt das letzte vorhandene Foto sowie die zugehörigen Werte aus SLFork. Sie erkennt den Ziffernausschnitt anhand der grünen Rahmen oder nutzt einen eingestellten Bildausschnitt. Tesseract OCR liest den Zählerstand unabhängig aus dem Bild. Bei unklarer oder abweichender Erstlesung probiert sie weitere Bildaufbereitungen **bis zum einstellbaren Maximum von 1 bis 10 Versuchen** (Standard: 5). **Bei der ersten bestätigten Übereinstimmung stoppt die Prüfung sofort.**

Im SLFork-Modus gleicht die App den OCR-Wert mit **Raw Value** und **Actual Value** ab. Im Kameramodus kann ein aktueller kumulierter m³-Sensor als Referenz dienen. Ohne Referenzsensor wird nur das OCR-Ergebnis ausgegeben.

## Dauerhafte Einstellungen für die automatische Kontrolle

In der Weboberfläche stehen unter **„Automatische Prüfung – Einstellungen“** vier dauerhaft gespeicherte Prüfregeln:

- **Vergleich:** Nur volle m³ (0) oder zusätzlich 1–3 Nachkommastellen. Die nicht ausgewählten Nachkommastellen werden ignoriert, nicht gerundet.
- **Max. OCR-Versuche:** 1–10 Versuche pro Zählerbild (Standard: 5). Bei einer bestätigten Übereinstimmung endet die Prüfung sofort.
- **Ziffernfarbe:** Automatisch erkennen (Standard) oder gezielt helle bzw. dunkle Ziffern lesen.
- **Bildbereich:** Ziffernrahmen automatisch erkennen (Standard) oder einen festen Ausschnitt samt Breite der Vorkommastellen dauerhaft verwenden.

Auf **„Speichern“** klicken. Die Einstellungen gelten für die **folgenden automatischen Prüfdurchläufe** und bleiben auch nach einem Neustart erhalten. Wird die Vergleichsgenauigkeit geändert, beginnt die Bestätigungszählung bei der nächsten automatischen Prüfung neu: Treffer mit der bisherigen Genauigkeit gelten nicht als Nachweis für die neue Regel.

Technisch werden die Web-Einstellungen separat im App-Datenverzeichnis (`/data/auto-pruefregeln.json`) abgelegt. Solange diese Datei existiert, haben ihre Werte für Vergleich, Versuche, Ziffernfarbe und Bildbereich **Vorrang vor den entsprechenden Feldern der Home-Assistant-App-Konfiguration**. Ohne gespeicherte Web-Einstellungen verwendet die App die Werte ihrer Konfiguration.

## Bildquelle und Ersteinrichtung

Beim ersten Öffnen führt ein kompakter Einrichtungsassistent durch Bildquelle, Zählertyp, Stellenformat, Bildbereich, Prüfplan und Benachrichtigungen. Die Einrichtung kann jederzeit erneut geöffnet werden; aktuelle Werte sind vorausgefüllt, sodass sich einzelne Einstellungen schnell ändern lassen. Hilfetexte sind bei Bedarf aufklappbar. Die automatische Prüfung bleibt klar vom manuellen Diagnosebereich getrennt.

| Modus | Wann passt er? |
| --- | --- |
| **SLFork / AI on the Edge** | Dein vorhandener ESP liefert das Foto und den Vergleichswert. Gib seine Adresse ein. |
| **Home-Assistant-Kamera** | Wähle eine `camera.*`-Entität und bei Bedarf einen aktuellen Referenzsensor in m³. |
| **ESPHome oder Kamera mit lokaler OCR** | Die Kamera liefert nur das Bild. RF1 liest den Stand lokal und stellt ihn als `sensor.rf1_ocr_zaehlerstand` in m³ bereit. |

Für ESPHome richte eine [ESP32-Kamera](https://esphome.io/components/esp32_camera/) mit [nativer API](https://esphome.io/components/api/) ein und füge das Gerät in Home Assistant hinzu. Prüfe das Kamerabild dort und trage anschließend die `camera.*`-Entität in RF1 ein. Öffne **Manuellen Test**, passe den Bildausschnitt an und übernimm die Vorschau in die Automatik. Die App benötigt für diese Betriebsart weder SLFork noch einen Referenzsensor.

Der OCR-Sensor benötigt eine Mehrheit von mindestens zwei OCR-Profilen desselben Bildes. Bei einer unsicheren Lesung oder einem Rückgang gegenüber dem letzten gültigen Stand derselben Kamera wird er als **nicht verfügbar** gemeldet. Ein OCR-Stand ohne Referenz ist eine eigenständige Ablesung. Für das Energie-Dashboard gibt es einen kumulativen Verbrauchssensor. Ein späterer Wechsel startet die automatische Bestätigungszählung für die neue Quelle neu.

## Kamerabild und Ausschnitt einrichten

Öffne **Manuellen Test** und wähle unter **Bildbereich** die manuelle Einstellung. Gib die Koordinaten im Originalbild in Pixeln ein. Wenn das Foto seitlich oder auf dem Kopf steht, wähle die passende **Bilddrehung**. Die Breite der Vorkommastellen bezieht sich auf den Ausschnitt nach der Drehung. Mit **Jetzt prüfen** siehst du das Auswertungsergebnis und kannst den getesteten Ausschnitt mitsamt Drehung für die Automatik übernehmen.

Die Voreinstellung erkennt helle oder dunkle Ziffern automatisch. Weitere OCR-Versuche können ungleichmäßiges Licht im Ziffernfenster ausgleichen. Glanzstellen, die Ziffern verdecken, und starke Perspektivverzerrungen erfordern ein besseres Kamerabild. Bei Zählern mit Rollenfenster und kleinen Zeigern lässt sich mit **volle m³** das Rollenfenster einzeln testen. Die Zeiger selbst werden nicht ausgewertet.

Der [Vergleichstest mit zehn Gas-, Wasser- und Stromzählerfotos](METER-PHOTO-TESTS.md) dokumentiert simulierte OCR-Läufe mit öffentlich zugänglichen Bildern. Er ist kein Hardwaretest.

> **Teststand:** Der Maintainer verwendet für Tests an einem realen Zähler ausschließlich AI on the Edge / SLFork. Kamera- und ESPHome-Modi sowie abweichende Zählertypen sind automatisiert und simuliert geprüft; ein realer Gerätetest dafür liegt nicht vor.

## Plausibilitätsprüfung und Energie-Dashboard

Für den Verbrauch verwendet Meter OCR automatische Treffer mit Referenz oder übereinstimmende OCR-Versuche im eigenständigen Modus. Der erste gültige Stand setzt die Basis. Danach vergleicht die App den neuen Stand mit der letzten gültigen Messung. Sie verwirft Rücksprünge und Anstiege, die für die verstrichene Zeit zu groß sind. Die berücksichtigte Ziffernauflösung bestimmt den Rundungsspielraum.

Unter **Automatische Prüfung – Einstellungen → Maximaler Durchfluss** trägst du den Qmax-Wert vom Zähler ein. Die Vorgabe für G4 beträgt 6 m³/h. Ein abgelehnter Wert verändert den Verbrauchszähler nicht. Wechselt die Bildquelle oder die Vergleichsgenauigkeit, dient die nächste gültige Ablesung als Basis für weitere Verbrauchsdifferenzen.

Füge in Home Assistant unter **Energie → Einstellungen → Gasverbrauch** den Sensor **Meter OCR Gasverbrauch gesamt** (`sensor.rf1_verbrauch_gesamt`) hinzu. Er entsteht mit der ersten gültigen Messung und summiert die bestätigten Verbrauchsdifferenzen in m³. Home Assistant berechnet aus diesem kumulativen Wert die Ansichten für Stunde, Tag, Woche und Monat.

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
3. OCR-Auswertung, **1 bis maximal 10 Versuche** mit Fortschrittsbalken
4. Ergebnis speichern und abschließen

Der Balken zeigt **tatsächlich abgeschlossene OCR-Versuche**, nicht eine geschätzte Laufzeit. Die Schaltfläche wird während der Prüfung zu **„Prüfung läuft …“** und ist vorübergehend gesperrt. Danach erscheint direkt **„Test erfolgreich“** bei Übereinstimmung (dezent grün) oder eine verständliche Fehler- bzw. Abweichungsmeldung (dezent rot). Eine erfolgreiche Bildlesung ohne Referenz wird neutral angezeigt. Der manuelle Test verändert weder den automatischen Zeitplan noch die Trefferzahl. Das **OCR-Testbild** markiert mit **grünen Rahmen** gelesene Ziffern und mit **roten Rahmen** unklare Ziffern. Ohne erkannte Einzelrahmen sind die Rahmen nur eine angenäherte Aufteilung. Grün bedeutet lediglich **als Ziffer gelesen**, nicht automatisch eine Übereinstimmung mit dem Referenzwert.

Unter **„Mehr Infos“** lassen sich die einzelnen OCR-Versuche mit ihren gelesenen Werten ansehen. Bei unsicherer Erkennung nennt das Ergebnis – soweit ermittelbar – die betroffenen Vorkomma- und Nachkommastellen. Eine bestätigte Prüfung erklärt direkt, auf welcher Vergleichsgenauigkeit sie beruht.

Die kompakte Weboberfläche zeigt die wichtigsten Angaben in getrennten Bereichen, Datum und Uhrzeit kurz als **TT.MM.JJ HH:MM** und die Kontrollbilder in einem ausklappbaren Bereich. Technische Diagnosewerte stehen weiterhin in Home Assistant zur Verfügung, ohne die normale Ansicht zu überladen.

**Zwei unterschiedliche Einstellungen:** Die **1 bis 10 OCR-Versuche** betreffen die Auswertung eines einzelnen Bilds. Die **fünf bestätigten automatischen Prüfungen innerhalb von 24 Stunden** sind dagegen ein separates Kontrollziel. Ein manueller Versuch erhöht diese Zahl nicht.

## Automatische Kontrolle

Nach erfolgreichem Abgleich prüft die App normalerweise nach einer Stunde erneut. Bei Abweichungen, unklarer Erkennung oder fehlenden Daten versucht sie es alle fünf Minuten. Standardmäßig nach vier Stunden ohne erfolgreiche Prüfung meldet `sensor.rf1_pruefstatus` den Zustand `review_due`. Die Wartezeiten und zusätzliche Benachrichtigungsziele lassen sich in der Weboberfläche einstellen.

Ein SLFork-Messzeitpunkt wird automatisch nur einmal gezählt. Alte Bilder lassen sich weiterhin manuell prüfen. Bei einer allgemeinen Home-Assistant-Kamera verwendet die App den Abrufzeitpunkt. Für unabhängige Bestätigungen muss die Kamera aktuelle Bilder liefern. Ein konfigurierter Referenzsensor muss den Stand in `m³` melden und innerhalb von fünf Minuten zum Bildabruf aktualisiert worden sein.

## Voraussetzungen

- Home Assistant mit Supervisor und App-Store (ARM64 oder AMD64)
- **SLFork / AI on the Edge** auf einem im Heimnetz erreichbaren ESP mit gut ausgerichteten Ziffernrahmen, **oder** eine geeignete `camera.*`-Entität in Home Assistant
- Ein lesbares Zählerbild; zum Vergleich ein passender Messwert (im Kameramodus optional ein aktueller kumulierter Sensor in m³)

## Installation

1. In Home Assistant unter **Einstellungen → Apps → App installieren → ⋮ → Repositories** das Repository **Add-ons by Eifellayer** über den [gemeinsamen Link](https://github.com/Eifellayer/meter-ocr) hinzufügen.
2. **Meter OCR (Alpha)** installieren. Releases unter 0.5 sind Alpha und verwenden dieselbe reguläre App als Teststand.
3. Für SLFork `esp_url` auf die Adresse des ESP setzen (z. B. `http://esp-gaszaehler.local`). Alternativ `kamera_entitaet`, `ausschnitt` und optional `referenz_entitaet` konfigurieren.
4. App starten, **Weboberfläche öffnen** und mit **Jetzt prüfen** eine Testlesung durchführen.

Bis Version 0.5 gibt es keine separate Beta-App. Ab 0.5 ist ein Beta-Kanal größeren Änderungen mit zusätzlichem Testbedarf vorbehalten. Bitte vor jedem Update eine Sicherung deiner Home-Assistant-Konfiguration erstellen.

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

Meter OCR ist ein kostenloses Hobbyprojekt. Wenn sie dir hilft, freue ich mich über eine [freiwillige PayPal-Spende](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8).

[Änderungsprotokoll](rf1_ocr_test/CHANGELOG.md) · [Quellen](SOURCES.md) · [Home-Assistant-App](rf1_ocr_test/README.md) · [English documentation](README.en.md)

<img src="assets/project-logo.png" alt="Projektlogo" width="120">
