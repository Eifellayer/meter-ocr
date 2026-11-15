# Änderungen

## 0.8.0

- **Automatik und Test getrennt:** Die automatische Kontrolle steht im Vordergrund, der erweiterte manuelle Test bleibt eingeklappt.
- Vergleichsgenauigkeit, maximale OCR-Versuche, Ziffernfarbe und Bildausschnitt lassen sich dauerhaft direkt in der Weboberfläche speichern.
- **Bildausschnitt übernehmen:** Nach einem Test mit manuell definiertem Ausschnitt können seine Koordinaten und die Vorkommabreite direkt für die automatische Kontrolle übernommen werden.
- **Visuelle OCR-Diagnose:** Das letzte manuelle Testbild zeigt grüne Rahmen für gelesene Ziffern und rote Rahmen für unklare Stellen. Ohne automatisch erkannte Ziffernrahmen werden die Bereiche näherungsweise aufgeteilt. Die Rahmen zeigen Lesbarkeit, keine Referenzübereinstimmung.
- **Mehr Infos:** Einzelne OCR-Versuche sind aufklappbar, und bei unsicheren Ergebnissen werden die relevanten Ziffernpositionen beschrieben. Bestätigungen und Abweichungen nennen die eingestellte Vergleichsgenauigkeit.
- Während einer laufenden Prüfung bleibt das Statusfeld neutral; erst das endgültige Ergebnis wird dezent grün beziehungsweise rot markiert.
- **Freiwillige Unterstützung:** Kleiner PayPal-Link ganz unten in der Weboberfläche sowie GitHub-Sponsor-Link, ohne Pflicht oder Einfluss auf die Funktionen.
- Regressionstests für Vergleichslogik, Frühausstieg der OCR, unsichere Stellen, HTML-Vorlage und farbige OCR-Rahmen ergänzt. Änderungen der gespeicherten Automatikregeln überstehen Neustarts.
- Bestehender technischer App-Slug und Home-Assistant-Entitätsnamen bleiben unverändert.

## 0.7.2

- Die Hauptansicht zeigt zuerst den Zustand der automatischen Kontrolle. Ihre Vergleichsgenauigkeit (volle m³ oder 1–3 Nachkommastellen), Ziffernfarbe (automatisch/hell/dunkel) und maximale Anzahl der OCR-Versuche (1–10) lassen sich dort dauerhaft speichern.
- Gespeicherte automatische Prüfregeln bleiben über Neustarts erhalten und gelten für zukünftige Prüfungen; sie haben für diese beiden Einstellungen Vorrang vor der App-Konfiguration. Bei einer geänderten Genauigkeit werden bisherige Treffer nicht als neue Bestätigungen übernommen.
- „Manuellen Test öffnen“ ist ein eigener, zunächst geschlossener Diagnosebereich und überlädt die Alltagsansicht nicht.
- Der manuelle Test bietet zusätzliche Einstellungen für Ziffernfarbe, Vergleichsgenauigkeit, OCR-Versuche sowie optional einen manuellen Bildausschnitt und die Breite der Vorkommastellen. Diese Werte verändern die Automatik nicht.
- Bestehende Home-Assistant-Entitätsnamen und die gespeicherte Prüfhistorie bleiben erhalten.

## 0.7.1

- Die maximale Zahl der OCR-Versuche ist in der App und für den manuellen Test von 1 bis 10 wählbar (Standard 5). Beim ersten bestätigten Treffer endet die Auswertung sofort.
- Nach dem manuellen Test erscheint das Ergebnis direkt im Statusbereich. Unklare, abweichende oder fehlende Messwerte erhalten verständliche Hinweise statt technischer Mehrheits-/Versuchsmeldungen.
- Dezente grüne Markierung nur bei bestätigter Übereinstimmung, dezente rote Markierung bei Problemen; ansonsten neutral.
- „Jetzt prüfen“ ist zurückhaltend eingefärbt und wird während der laufenden Prüfung zu „Prüfung läuft …“ (nicht erneut anklickbar).
- Längere Erklärung hinter einem aufklappbaren Infosymbol, keine unzuverlässigen Restzeitangaben und keine separate doppelte manuelle Ergebniskarte.

## 0.7.0

- Verständlicher App-Name „Gaszähler OCR-Kontrolle“, technische IDs bleiben erhalten.
- Live-Fortschritt beim manuellen Test: Anfrage, Bildabruf, aktueller OCR-Schritt, tatsächlich abgeschlossene Durchläufe (max. 5) und verstrichene Zeit.
- Kompakte und mobilfreundliche Weboberfläche mit Karten, übersichtlichen Kontrollbildern und Datum im Kurzformat.
- Doppelte Zählerangaben aus der manuellen Testzusammenfassung entfernt. Technische Meldungen wie Messbetrieb und Prozessfehlercode bleiben für die Diagnose verfügbar, werden aber nicht mehr standardmäßig angezeigt.
- Ausführliche GitHub- und App-Dokumentation: Zweck, Voraussetzungen, Installation, Bilder, Vergleichslogik und Unterschied zwischen fünf OCR-Aufbereitungen und fünf bestätigten automatischen Treffern.


## 0.6.10

- Bei einer abweichenden oder unklaren OCR liest die App dasselbe Bild insgesamt fünfmal mit unterschiedlicher Aufbereitung. Eine Lesung muss bei der eingestellten Genauigkeit zur gültigen Referenz passen. Pro Messbild zählt höchstens ein Treffer.
- Die Anzahl der OCR-Durchläufe steht im Prüfprotokoll, in den Details des manuellen Tests und im Attribut `ocr_attempts` des Kontrollbilds.
- Die Weboberfläche und der Prüfstatus zeigen Firmwaremeldungen von AI on the Edge (SLFork) mit Wertstatus, Prozessfehler und Zeit des letzten gültigen Werts. Ein verworfener Stand zählt nicht als Treffer.

## 0.6.9

- Mehrfaches Klicken auf „Jetzt prüfen“ zeigt eine Rückmeldung auf der RF1-Seite. Bei einem wartenden Test werden die neuesten Einstellungen verwendet.

## 0.6.8

- Auf der RF1-Seite lassen sich Ziffernfarbe und Vergleichsgenauigkeit für „Jetzt prüfen“ einstellen. Die Ziffernfarbe kann automatisch erkannt oder manuell auf hell oder dunkel festgelegt werden.

## 0.6.7

- „Jetzt prüfen“ zeigt ein eigenes OCR-Testergebnis, auch für ältere oder bereits ausgewertete Bilder. Wiederverwendete Bilder werden gekennzeichnet. Manuelle Tests zählen nicht als automatische Treffer.

## 0.6.6

- Wenn die fünf Vorkommastellen als Zeile unklar sind, prüft RF1 sie anhand der automatisch erkannten SLFork-Rahmen einzeln. Unklare Stellen erscheinen als Fragezeichen.

## 0.6.5

- „Jetzt prüfen“ funktioniert hinter Home Assistant Ingress auch ohne den Browser-Header `Sec-Fetch-Site`. Ein Formular-Token schützt den Button vor fremden Anfragen.

## 0.6.4

- App-Oberfläche mit Countdown, „Jetzt prüfen“, verständlichem Prüfergebnis und Bildvergleich mit dem letzten Treffer.
- Erkannte Nachkommastellen werden separat ausgewiesen. Unsichere Stellen erscheinen als Fragezeichen. Die Vergleichsgenauigkeit ist auf null bis drei Stellen einstellbar.
- Home-Assistant-Kameras wie ESPHome als optionale Bildquelle. Ein zeitnaher kumulierter m³-Sensor kann als Referenz dienen, auch bei Pulsmessung.

## 0.6.3

- Beim Start wertet RF1 ein frisches, noch nicht geprüftes SLFork-Bild sofort aus.
- Alte und bereits geprüfte Bilder zählen beim Neustart nicht erneut. Ohne neues Bild bleibt der geplante nächste Check bestehen.

## 0.6.2

- Optionaler Hinweis in Home Assistant und einmalige Push-Erinnerung nach 24 Stunden. Offene Fälle lassen sich quittieren oder überspringen.
- Versionierte Konfiguration mit Standardwerten und Migrationen für neue, umbenannte und veraltete Einstellungen.
- Anleitung für die Einrichtung des Push-Dienstes und dieses Changelog.

## 0.6.1

- Versionswechsel zum Prüfen des automatischen Updates aus dem GitHub-Repository.

## 0.6.0

- Stündlicher Abgleich bei erfolgreicher Messung. Bei Abweichungen wird alle fünf Minuten erneut geprüft.
- Prüfbedarf nach vier Stunden ohne Treffer. Der Beginn der Störung bleibt bei einem Neustart erhalten.

## 0.5.0

- Automatischer Bildausschnitt anhand der SLFork-Ziffernrahmen.
- OCR für normale und invertierte Bilder.

## 0.4.1

- Vergleich der vollen Kubikmeter auch bei vier oder mehr Nachkommastellen von SLFork.

## 0.4.0

- Lokale Gegenkontrolle der vollen Kubikmeter mit einem rollierenden 24-Stunden-Fenster und fünf bestätigten Messungen als Ziel.

## 0.2.0

- Kontrollbild und zugehörige SLFork-Messung in Home Assistant bereitgestellt.

## 0.1.0

- Erster lokaler OCR-Probelauf mit Ausgabe im App-Protokoll.
