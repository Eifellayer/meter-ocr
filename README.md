# Gaszähler OCR-Kontrolle für Home Assistant

**Unabhängige optische Zweitprüfung für automatisch ausgelesene mechanische Gaszähler.**

Du liest deinen Gaszähler bereits mit Kamera und ESP aus, möchtest aber prüfen, ob die erkannten Ziffern wirklich zum Zählerbild passen? Diese App liest das vorhandene Foto **ein zweites Mal lokal mit Tesseract OCR** und vergleicht die Ziffern mit dem vorhandenen Messwert. Damit ist sie eine zusätzliche Plausibilitätskontrolle, kein zweiter Gaszähler.

Entwickelt für den **Pipersberg G4 RF1** mit **AI on the Edge / SLFork**. Eine geeignete Home-Assistant-Kamera kann alternativ als Bildquelle dienen. „RF1“ bleibt aus Kompatibilitätsgründen in bestehenden Entitäts-IDs und im App-Verzeichnis erhalten.

> **Privates Hobbyprojekt, keine geeichte Zweitmessung.** OCR kann Ziffern falsch lesen. Für Abrechnungen und Meldungen an den Versorger gilt der direkt am Zähler kontrollierte Stand. Nutzung auf eigene Gefahr; kein garantierter Support.

## Was wird kontrolliert?

Die Standardeinstellung vergleicht **fünf Vorkommastellen, also volle m³**. Erkannte Nachkommastellen werden zusätzlich angezeigt. Ein `?` steht für eine unklare Ziffer. Solange `vergleich_nachkommastellen: 0` eingestellt ist, werden unklare Nachkommastellen nicht bewertet.

Die App holt das letzte vorhandene Foto sowie die zugehörigen Werte aus SLFork. Sie erkennt den Ziffernausschnitt anhand der grünen Rahmen oder nutzt einen eingestellten Bildausschnitt. Tesseract OCR liest den Zählerstand unabhängig aus dem Bild. Bei unklarer oder abweichender Erstlesung probiert sie **bis zu vier weitere Bildaufbereitungen desselben Fotos**. Eine passende Lesung kann den Durchlauf frühzeitig beenden.

Im SLFork-Modus gleicht die App den OCR-Wert mit **Raw Value** und **Actual Value** ab. Im Kameramodus kann ein aktueller kumulierter m³-Sensor als Referenz dienen. Ohne Referenzsensor wird nur das OCR-Ergebnis ausgegeben.

## „Jetzt prüfen“ – Live-Status

Der Button startet einen **manuellen Test mit dem bereits vorhandenen Bild**. Er löst keine neue Aufnahme am ESP aus. Die Weboberfläche zeigt unmittelbar den aktuellen Schritt:

1. Anfrage angenommen
2. Bild und Referenzwerte laden
3. OCR-Auswertung, **bis zu fünf Durchläufe** mit Fortschrittsbalken
4. Ergebnis speichern und abschließen

Der Balken zeigt **tatsächlich abgeschlossene OCR-Aufbereitungen** an, dazu die verstrichenen Sekunden. Eine feste Restdauer wird nicht behauptet, da die Laufzeit variiert und ein guter Treffer bereits im ersten Durchlauf möglich ist. Der manuelle Test verändert weder den automatischen Zeitplan noch die Trefferzahl.

Die kompakte Weboberfläche zeigt die wichtigsten Angaben in getrennten Bereichen, Datum und Uhrzeit kurz als **TT.MM.JJ HH:MM** und die Kontrollbilder übersichtlich nebeneinander. Technische Diagnosewerte stehen weiterhin in Home Assistant zur Verfügung, ohne die normale Ansicht zu überladen.

**Zwei unterschiedliche Fünfer-Zahlen:** Die bis zu **fünf OCR-Durchläufe** betreffen ein einzelnes Bild. Die **fünf bestätigten automatischen Prüfungen innerhalb von 24 Stunden** sind dagegen ein separates Kontrollziel. Auch ein einzelner manueller Durchlauf erhöht diese Zahl nicht.

## Automatische Kontrolle

Nach erfolgreichem Abgleich prüft die App normalerweise nach einer Stunde erneut. Bei Abweichungen, unklarer Erkennung oder fehlenden Daten versucht sie es alle fünf Minuten. Nach vier Stunden ohne bestätigte Übereinstimmung meldet `sensor.rf1_pruefstatus` den Zustand `review_due`. Ein optionaler Hinweis kann nach weiteren 24 Stunden einmalig als Push gesendet werden.

Ein Messzeitpunkt wird automatisch nur einmal gezählt. Alte Bilder werden nicht als neue automatische Treffer gewertet; für manuelle Tests können sie dennoch nochmals ausgewertet werden.

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
| `kamera_entitaet` | Optionales Kamerabild aus Home Assistant |
| `referenz_entitaet` | Optionaler kumulierter m³-Sensor im Kameramodus |
| `ausschnitt`, `vorkomma_breite` | Manueller Ziffernbereich, falls nötig |
| `push_dienst` | Optionaler Benachrichtigungsdienst |

Die Einstellungen „Ziffernfarbe“ und „Vergleichsgenauigkeit“ auf der Weboberfläche gelten für den **manuellen Test**; die dauerhaft verwendeten Optionen werden in der App-Konfiguration verwaltet.

## Wo stehen die Ergebnisse?

- **Weboberfläche öffnen:** Status, manueller Test mit Fortschritt, automatische Kontrolle und Kontrollbilder.
- `sensor.rf1_pruefstatus`: automatischer Prüfstatus und technische Diagnosen.
- `sensor.rf1_kontrollbild`: OCR-Erkennung, Bildzeit, `ocr_attempts` und `matches_last_24h`.
- **Medien → Lokale Medien → rf1:** `kontrollbild.jpg` und `letzter_treffer.jpg`.

Eine Meldung `match` bedeutet Übereinstimmung **bei der eingestellten Genauigkeit** – nicht notwendigerweise, dass jede sichtbare Nachkommastelle erkannt wurde.

[Änderungsprotokoll](rf1_ocr_test/CHANGELOG.md) · [Installationshinweise für lokale Altversionen](rf1_ocr_test/README.md)
