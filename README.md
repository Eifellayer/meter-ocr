# Gaszähler OCR-Kontrolle für Home Assistant

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

**Versionsstatus: Beta.** Unter 0.5.0 gilt Alpha, ab 0.5.0 bis vor 1.0.0 Beta und ab 1.0.0 stabil.

**Unabhängige optische Zweitprüfung für automatisch ausgelesene mechanische Gaszähler.**

Du liest deinen Gaszähler bereits mit Kamera und ESP aus, möchtest aber prüfen, ob die erkannten Ziffern wirklich zum Zählerbild passen? Diese App liest das vorhandene Foto **ein zweites Mal lokal mit Tesseract OCR** und vergleicht die Ziffern mit dem vorhandenen Messwert. Damit ist sie eine zusätzliche Plausibilitätskontrolle, kein zweiter Gaszähler.

Entwickelt für den **Pipersberg G4 RF1** mit **AI on the Edge / SLFork**. Eine geeignete Home-Assistant-Kamera kann alternativ als Bildquelle dienen. „RF1“ bleibt aus Kompatibilitätsgründen in bestehenden Entitäts-IDs und im App-Verzeichnis erhalten.

> **Privates Hobbyprojekt, keine geeichte Zweitmessung.** OCR kann Ziffern falsch lesen. Für Abrechnungen und Meldungen an den Versorger gilt der direkt am Zähler kontrollierte Stand. Nutzung auf eigene Gefahr; kein garantierter Support.

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

Beim ersten Öffnen einer frischen Installation wählst du unter **Bildquelle** den Betriebsmodus. Dieselbe Auswahl steht später in der Weboberfläche zur Verfügung.

| Modus | Wann passt er? |
| --- | --- |
| **SLFork / AI on the Edge** | Dein vorhandener ESP liefert das Foto und den Vergleichswert. Gib seine Adresse ein. |
| **Home-Assistant-Kamera** | Wähle eine `camera.*`-Entität und bei Bedarf einen aktuellen Referenzsensor in m³. |
| **ESPHome oder Kamera mit lokaler OCR** | Die Kamera liefert nur das Bild. RF1 liest den Stand lokal und stellt ihn als `sensor.rf1_ocr_zaehlerstand` in m³ bereit. |

Für ESPHome richte eine [ESP32-Kamera](https://esphome.io/components/esp32_camera/) mit [nativer API](https://esphome.io/components/api/) ein und füge das Gerät in Home Assistant hinzu. Prüfe das Kamerabild dort und trage anschließend die `camera.*`-Entität in RF1 ein. Öffne **Manuellen Test**, passe den Bildausschnitt an und übernimm die Vorschau in die Automatik. Die App benötigt für diese Betriebsart weder SLFork noch einen Referenzsensor.

Der OCR-Sensor benötigt eine Mehrheit von mindestens zwei OCR-Profilen desselben Bildes. Bei einer unsicheren Lesung oder einem Rückgang gegenüber dem letzten gültigen Stand derselben Kamera wird er als **nicht verfügbar** gemeldet. Ein OCR-Stand ohne Referenz ist keine bestätigte Messung und wird nicht für Langzeitstatistiken eingerichtet. Bestehende Installationen übernehmen zuerst ihre bisherige Bildquelle. Ein späterer Wechsel startet die automatische Bestätigungszählung für die neue Quelle neu.

## Benachrichtigungen und Prüfstatus

Oben zeigt ein grüner Haken einen bestätigten Vergleich. Bei einem aktuellen Problem erscheint ein roter Hinweis. **Ignorieren** blendet diesen Vorfall in der Oberfläche aus. Ein neuer Vorfall erscheint wieder, und die Benachrichtigungsregeln gelten weiterhin.

Öffne **Benachrichtigungen** und aktiviere **Bei anhaltenden Problemen benachrichtigen**. **Hinweis nach** bestimmt, wie viele Minuten ohne erfolgreiche automatische Prüfung bis zum Home-Assistant-Hinweis vergehen. Mit der zweiten Wartezeit legst du fest, wann ein noch offener Hinweis per Handy-Push oder E-Mail weitergeleitet wird. **0 Stunden** versendet die Nachricht zusammen mit dem Hinweis.

- **Nur in Home Assistant:** Beide optionalen Ziele leer lassen.
- **Handy-Push:** Den Companion-Dienst eintragen, zum Beispiel `notify.mobile_app_mein_handy`.
- **E-Mail:** Die [SMTP-Integration](https://www.home-assistant.io/integrations/smtp/) samt Empfänger in Home Assistant einrichten. Unter **E-Mail oder anderes Ziel** dessen `notify.*`-Entität eintragen, zum Beispiel `notify.meine_email`. Andere Benachrichtigungs-Entitäten funktionieren ebenfalls.

Je Ziel wird pro Vorfall höchstens eine erfolgreiche Nachricht erfasst. Wenn du den Hinweis in Home Assistant schließt oder die automatische Prüfung wieder gelingt, entfallen ausstehende Nachrichten. Manuelle Tests senden keine Nachrichten. Ein bestehender `push_dienst` wird übernommen, bis du die Benachrichtigungen in der Oberfläche speicherst.

## Sprache der Weboberfläche

**Automatisch (Home Assistant)** verwendet die im angemeldeten Home-Assistant-Profil gewählte Sprache, wenn die App über Ingress darauf zugreifen kann. Unterstützt werden Deutsch und Englisch einschließlich Varianten wie `de-AT` und `en-US`. Fehlt eine unterstützte Profilsprache, gilt die erste passende Browsersprache, sonst Deutsch. Eine ausdrückliche Auswahl von **Deutsch** oder **English** wird pro angemeldetem Ingress-Nutzer gespeichert. Die Auswahl **Automatisch** übernimmt beim nächsten Öffnen oder Neuladen wieder das Profil. Ohne eindeutige Ingress-Identität gilt die manuelle Wahl innerhalb der aktuellen Navigation.

Die frühere Sprachauswahl von 0.8.1 war browserweit. Wähle eine gewünschte dauerhafte Sprache nach dem Update einmal im jeweiligen Konto. Die App übernimmt die Sprache aus der bereits angemeldeten Frontend-Verbindung. In den App-Einstellungen wird nur die manuelle Auswahl je Nutzer gespeichert.

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

1. In Home Assistant unter **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Thunder86/rf1-kontrollmessung` hinzufügen.
2. **Gaszähler OCR-Kontrolle** installieren.
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

Die Gaszähler OCR-Kontrolle ist ein kostenloses Hobbyprojekt. Wenn sie dir hilft, freue ich mich über eine [freiwillige PayPal-Spende](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8).

[Änderungsprotokoll](rf1_ocr_test/CHANGELOG.md) · [Installationshinweise für lokale Altversionen](rf1_ocr_test/README.md) · [English documentation](README.en.md)
