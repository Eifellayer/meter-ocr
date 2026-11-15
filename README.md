# Meter OCR für Home Assistant

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

**Teststand: 0.1.0.** Installiere **Meter OCR Beta** über das [gemeinsame Home-Assistant-Repository](https://github.com/Eifellayer/rf1-kontrollmessung).

Der geprüfte GitHub-Stand liegt auf [stable](https://github.com/Eifellayer/rf1-kontrollmessung/tree/stable). Neue Änderungen werden auf [beta](https://github.com/Eifellayer/rf1-kontrollmessung/tree/beta) getestet. Das Home-Assistant-Repository behält seine bisherige Adresse und verwendet `main` für veröffentlichte Versionen.

**Zählerstände lokal aus Kamerabildern lesen und mit Home Assistant abgleichen.**

Meter OCR liest das Zählerfoto mit **Tesseract OCR**. Mit ESPHome oder einer anderen Home-Assistant-Kamera kann die App einen eigenen OCR-Stand liefern. Mit **AI on the Edge / SLFork** oder einem Referenzsensor prüft sie zusätzlich, ob der vorhandene Messwert zum Bild passt.

Entwickelt für mechanische Gaszähler wie den **Pipersberg G4 RF1**. Das Ziffernfenster hat fünf Vorkommastellen und bei Bedarf bis zu drei Nachkommastellen. Die Messwertausgabe in Home Assistant ist auf Kubikmeter ausgelegt.

> **Privates Hobbyprojekt, keine geeichte Zweitmessung.** OCR kann Ziffern falsch lesen. Für Abrechnungen und Meldungen an den Versorger gilt der direkt am Zähler kontrollierte Stand. Nutzung auf eigene Gefahr; kein garantierter Support.

## Was wird kontrolliert?

Die Standardeinstellung vergleicht **fünf Vorkommastellen, also volle m³**. Erkannte Nachkommastellen werden zusätzlich angezeigt. Ein `?` steht für eine unklare Ziffer. Solange `vergleich_nachkommastellen: 0` eingestellt ist, werden unklare Nachkommastellen nicht bewertet.

Die App holt das letzte vorhandene Foto sowie die zugehörigen Werte aus SLFork. Sie erkennt den Ziffernausschnitt anhand der grünen Rahmen oder nutzt einen eingestellten Bildausschnitt. Tesseract OCR liest den Zählerstand unabhängig aus dem Bild. Bei unklarer oder abweichender Erstlesung probiert sie weitere Bildaufbereitungen **bis zum einstellbaren Maximum von 1 bis 10 Versuchen** (Standard: 5). **Bei der ersten bestätigten Übereinstimmung stoppt die Prüfung sofort.**

Im SLFork-Modus gleicht die App den OCR-Wert mit **Raw Value** und **Actual Value** ab. Im Kameramodus kann ein aktueller kumulierter m³-Sensor als Referenz dienen. Ohne Referenzsensor wird nur das OCR-Ergebnis ausgegeben.

Meldet SLFork **Use Fallback**, zeigt die App den Ersatzwert und dessen bekannte Messzeit separat zur Bildzeit. Bei **Rate Too High (<)** kann SLFork die Referenzzeit weiterstellen, obwohl der Wert gleich bleibt. In diesem Fall nutzt die App die Zeit des letzten bestätigten Abgleichs mit diesem Wert, falls vorhanden. Ist die Messzeit unbekannt, steht das in der Übersicht. Die Plausibilitätsprüfung berücksichtigt die Zeit zum aktuellen Bild und den eingestellten maximalen Durchfluss. Erst ein gültiger Abgleich zählt als Treffer und fließt in den Verbrauch ein.

## Dauerhafte Einstellungen für die automatische Kontrolle

In der Weboberfläche stehen unter **Einstellungen → Automatische Prüfung** die dauerhaft gespeicherten Prüfregeln.

- **Prüfintervall:** 1–1.440 Minuten nach einer erfolgreichen Prüfung, standardmäßig 60 Minuten. Die Änderung gilt bereits für die nächste geplante Prüfung.
- **Vergleich:** Nur volle m³ (0) oder zusätzlich 1–3 Nachkommastellen. Die nicht ausgewählten Nachkommastellen werden ignoriert, nicht gerundet.
- **Max. OCR-Versuche:** 1–10 Versuche pro Zählerbild (Standard: 5). Bei einer bestätigten Übereinstimmung endet die Prüfung sofort.
- **Ziffernfarbe:** Automatisch erkennen (Standard) oder gezielt helle bzw. dunkle Ziffern lesen.
- **Bildbereich:** Ziffernrahmen automatisch erkennen (Standard) oder einen festen Ausschnitt samt Breite der Vorkommastellen dauerhaft verwenden.

Auf **„Speichern“** klicken. Die Einstellungen gelten für die **folgenden automatischen Prüfdurchläufe** und bleiben auch nach einem Neustart erhalten. Wird die Vergleichsgenauigkeit geändert, beginnt die Bestätigungszählung bei der nächsten automatischen Prüfung neu: Treffer mit der bisherigen Genauigkeit gelten nicht als Nachweis für die neue Regel.

Technisch werden die Web-Einstellungen separat im App-Datenverzeichnis (`/data/auto-pruefregeln.json`) abgelegt. Solange diese Datei existiert, haben ihre Werte für Vergleich, Versuche, Ziffernfarbe und Bildbereich **Vorrang vor den entsprechenden Feldern der Home-Assistant-App-Konfiguration**. Ohne gespeicherte Web-Einstellungen verwendet die App die Werte ihrer Konfiguration.

## Bildquelle und Ersteinrichtung

Beim ersten Öffnen einer frischen Installation wählst du unter **Einstellungen → Bildquelle** den Betriebsmodus. Dieselbe Auswahl steht später in der Weboberfläche zur Verfügung.

| Modus | Wann passt er? |
| --- | --- |
| **SLFork / AI on the Edge** | Dein vorhandener ESP liefert das Foto und den Vergleichswert. Gib seine Adresse ein. |
| **Home-Assistant-Kamera** | Wähle eine `camera.*`-Entität und bei Bedarf einen aktuellen Referenzsensor in m³. |
| **ESPHome oder Kamera mit lokaler OCR** | Die Kamera liefert nur das Bild. RF1 liest den Stand lokal und stellt ihn als `sensor.rf1_ocr_zaehlerstand` in m³ bereit. |

Für ESPHome richte eine [ESP32-Kamera](https://esphome.io/components/esp32_camera/) mit [nativer API](https://esphome.io/components/api/) ein und füge das Gerät in Home Assistant hinzu. Prüfe das Kamerabild dort und trage anschließend die `camera.*`-Entität in RF1 ein. Öffne **Manuellen Test**, passe den Bildausschnitt an und übernimm die Vorschau in die Automatik. Die App benötigt für diese Betriebsart weder SLFork noch einen Referenzsensor.

Der OCR-Sensor benötigt eine Mehrheit von mindestens zwei OCR-Profilen desselben Bildes. Bei einer unsicheren Lesung oder einem Rückgang gegenüber dem letzten gültigen Stand derselben Kamera wird er als **nicht verfügbar** gemeldet. Ein OCR-Stand ohne Referenz ist eine eigenständige Ablesung. Für das Energie-Dashboard gibt es einen kumulativen Verbrauchssensor. Ein späterer Wechsel startet die automatische Bestätigungszählung für die neue Quelle neu.

## Kamerabild und Ausschnitt einrichten

Öffne **Testeinstellungen** und wähle unter **Bildbereich** die manuelle Einstellung. Gib die Koordinaten im Originalbild in Pixeln ein. Wenn das Foto seitlich oder auf dem Kopf steht, wähle die passende **Bilddrehung**. Die Breite der Vorkommastellen bezieht sich auf den Ausschnitt nach der Drehung. Mit **Jetzt prüfen** siehst du das Auswertungsergebnis und kannst den getesteten Ausschnitt mitsamt Drehung für die Automatik übernehmen.

Die Voreinstellung erkennt helle oder dunkle Ziffern automatisch. Weitere OCR-Versuche können ungleichmäßiges Licht im Ziffernfenster ausgleichen. Glanzstellen, die Ziffern verdecken, und starke Perspektivverzerrungen erfordern ein besseres Kamerabild. Bei Zählern mit Rollenfenster und kleinen Zeigern lässt sich mit **volle m³** das Rollenfenster einzeln testen. Die Zeiger selbst werden nicht ausgewertet.

Der [Vergleichstest](METER-PHOTO-TESTS.md) dokumentiert zehn öffentliche Zählerfotos und weitere zehn Aufnahmen aus der AI-on-the-Edge-Community.

## Plausibilitätsprüfung und Energie-Dashboard

Für den Verbrauch verwendet Meter OCR automatische Treffer mit Referenz oder übereinstimmende OCR-Versuche im eigenständigen Modus. Der erste gültige Stand setzt die Basis. Danach vergleicht die App den neuen Stand mit der letzten gültigen Messung. Sie verwirft Rücksprünge und Anstiege, die für die verstrichene Zeit zu groß sind. Die berücksichtigte Ziffernauflösung bestimmt den Rundungsspielraum.

Unter **Einstellungen → Automatische Prüfung → Maximaler Durchfluss** trägst du den Qmax-Wert vom Zähler ein. Die Vorgabe für G4 beträgt 6 m³/h. Wechselt die Bildquelle oder die Vergleichsgenauigkeit, dient die nächste gültige Ablesung als Basis für weitere Verbrauchsdifferenzen.

Füge in Home Assistant unter **Energie → Einstellungen → Gasverbrauch** den Sensor **Meter OCR Gasverbrauch gesamt** (`sensor.rf1_verbrauch_gesamt`) hinzu. Er entsteht mit der ersten gültigen Messung und summiert die bestätigten Verbrauchsdifferenzen in m³. Home Assistant berechnet aus diesem kumulativen Wert die Ansichten für Stunde, Tag, Woche und Monat.

## Benachrichtigungen und Prüfstatus

Oben zeigt ein grüner Haken einen bestätigten Vergleich. Bei einem Fehlschlag erscheint zunächst gelb **Letzte Prüfung fehlgeschlagen**. Nach einer Stunde ohne Erfolg kannst du die Details sehen und den Hinweis über **Ignorieren** ausblenden. Fällt die Bildquelle durchgehend eine Stunde aus, erscheint der Hinweis rot.

Öffne **Einstellungen → Benachrichtigungen** und aktiviere **Bei anhaltenden Problemen benachrichtigen**. **Hinweis nach** bestimmt die Wartezeit für den Home-Assistant-Hinweis, auch während SLFork einen Ersatzwert meldet. Mit der zweiten Wartezeit legst du fest, wann ein noch offener Hinweis per Handy-Push oder E-Mail weitergeleitet wird. **0 Stunden** versendet die Nachricht zusammen mit dem Hinweis.

- **Nur in Home Assistant:** Beide optionalen Ziele leer lassen.
- **Handy-Push:** Den Companion-Dienst eintragen, zum Beispiel `notify.mobile_app_mein_handy`.
- **E-Mail:** Die [SMTP-Integration](https://www.home-assistant.io/integrations/smtp/) samt Empfänger in Home Assistant einrichten. Unter **E-Mail oder anderes Ziel** dessen `notify.*`-Entität eintragen, zum Beispiel `notify.meine_email`. Andere Benachrichtigungs-Entitäten funktionieren ebenfalls.

Je Ziel wird pro Vorfall höchstens eine erfolgreiche Nachricht erfasst. Wenn du den Hinweis in Home Assistant schließt oder die automatische Prüfung wieder gelingt, entfallen ausstehende Nachrichten. Manuelle Tests senden keine Nachrichten. Ein bestehender `push_dienst` wird übernommen, bis du die Benachrichtigungen in der Oberfläche speicherst.

## Sprache der Weboberfläche

**Automatisch (Home Assistant)** verwendet die im angemeldeten Home-Assistant-Profil gewählte Sprache, wenn die App über Ingress darauf zugreifen kann. Unterstützt werden Deutsch und Englisch einschließlich Varianten wie `de-AT` und `en-US`. Fehlt eine unterstützte Profilsprache, gilt die erste passende Browsersprache, sonst Deutsch. Eine ausdrückliche Auswahl von **Deutsch** oder **English** wird pro angemeldetem Ingress-Nutzer gespeichert. Die Auswahl **Automatisch** übernimmt beim nächsten Öffnen oder Neuladen wieder das Profil. Ohne eindeutige Ingress-Identität gilt die manuelle Wahl innerhalb der aktuellen Navigation.

## Manueller Test

Unter **Testeinstellungen** kannst du Ziffernfarbe, Vergleichsgenauigkeit, OCR-Versuche und Bildausschnitt für den manuellen Test bearbeiten. Nach **Jetzt prüfen** kannst du einen erprobten Ausschnitt mit **Getesteten Ausschnitt für die Automatik übernehmen** dauerhaft speichern.

Mit **Test starten** prüfst du direkt von der Hauptseite das vorhandene Bild. Die Weboberfläche zeigt den Fortschritt unter dem Startknopf.

1. Anfrage angenommen
2. Bild und Referenzwerte laden
3. OCR-Auswertung, **1 bis maximal 10 Versuche** mit Fortschrittsbalken
4. Ergebnis speichern und abschließen

Der Balken zeigt die abgeschlossenen OCR-Versuche. Währenddessen heißt der Knopf **Prüfung läuft …**. Das Ergebnis erscheint darunter, grün bei Übereinstimmung, gelb bei Abweichung oder Unsicherheit und neutral bei einer erfolgreichen Lesung ohne Referenz. Das **OCR-Testbild** markiert gelesene Ziffern grün und unklare Stellen rot. Ohne erkannte Einzelrahmen sind die Markierungen näherungsweise aufgeteilt.

Unter **„Mehr Infos“** lassen sich die einzelnen OCR-Versuche mit ihren gelesenen Werten ansehen. Bei unsicherer Erkennung nennt das Ergebnis – soweit ermittelbar – die betroffenen Vorkomma- und Nachkommastellen. Eine bestätigte Prüfung erklärt direkt, auf welcher Vergleichsgenauigkeit sie beruht.

Die kompakte Weboberfläche zeigt die wichtigsten Angaben in getrennten Bereichen, Datum und Uhrzeit kurz als **TT.MM.JJ HH:MM** und die Kontrollbilder in einem ausklappbaren Bereich. Technische Diagnosewerte stehen weiterhin in Home Assistant zur Verfügung, ohne die normale Ansicht zu überladen.

**Zwei unterschiedliche Einstellungen:** Die **1 bis 10 OCR-Versuche** betreffen die Auswertung eines einzelnen Bilds. Die **fünf bestätigten automatischen Prüfungen innerhalb von 24 Stunden** sind dagegen ein separates Kontrollziel. Ein manueller Versuch erhöht diese Zahl nicht.

## Automatische Kontrolle

Nach einem Treffer prüft die App standardmäßig nach einer Stunde erneut. Bei Fehlschlägen versucht sie es spätestens nach fünf Minuten. Standardmäßig nach vier Stunden ohne erfolgreiche Prüfung meldet `sensor.rf1_pruefstatus` den Zustand `review_due`. Ein kürzeres Prüfintervall ruft das vorhandene Bild häufiger ab. Die Aufnahmefrequenz des ESP stellst du am Gerät ein.

Ein SLFork-Messzeitpunkt wird automatisch nur einmal gezählt. Alte Bilder lassen sich weiterhin manuell prüfen. Bei einer allgemeinen Home-Assistant-Kamera verwendet die App den Abrufzeitpunkt. Für unabhängige Bestätigungen muss die Kamera aktuelle Bilder liefern. Ein konfigurierter Referenzsensor muss den Stand in `m³` melden und innerhalb von fünf Minuten zum Bildabruf aktualisiert worden sein.

## Voraussetzungen

- Home Assistant mit Supervisor und App-Store (ARM64 oder AMD64)
- **SLFork / AI on the Edge** auf einem im Heimnetz erreichbaren ESP mit gut ausgerichteten Ziffernrahmen, **oder** eine geeignete `camera.*`-Entität in Home Assistant
- Ein lesbares Zählerbild; zum Vergleich ein passender Messwert (im Kameramodus optional ein aktueller kumulierter Sensor in m³)

## Installation

1. In Home Assistant unter **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Eifellayer/rf1-kontrollmessung` hinzufügen.
2. **Meter OCR** installieren.
3. Für SLFork `esp_url` auf die Adresse des ESP setzen (z. B. `http://esp-gaszaehler.local`). Alternativ `kamera_entitaet`, `ausschnitt` und optional `referenz_entitaet` konfigurieren.
4. App starten, **Weboberfläche öffnen** und mit **Jetzt prüfen** eine Testlesung durchführen.

Wer von einer alten lokalen RF1-App auf die Repository-Version wechselt, sollte die Einstellungen zuerst übernehmen und **nur eine Variante gleichzeitig betreiben**. Beide verwenden dieselben Entitäts-IDs; ihre lokal gespeicherten Historien sind voneinander getrennt.

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

## Projekt unterstützen

Meter OCR ist ein kostenloses Hobbyprojekt. Wenn sie dir hilft, freue ich mich über eine [freiwillige PayPal-Spende](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8).

[Änderungsprotokoll](rf1_ocr_test/CHANGELOG.md) · [Home-Assistant-App](rf1_ocr_test/README.md) · [English documentation](README.en.md)
