# Entwicklungs- und Freigabeplan

## Releasekanal

- Versionen `0.1.x` bis `0.4.x` sind Alpha. Bis Version 0.5 gibt es keine separate Beta-App; die reguläre AI-Meter-Reader-App ist der Testkanal.
- Ab `0.5` wird eine Beta-Version nur bei größeren Änderungen mit konkretem zusätzlichem Testbedarf angelegt. Kleine Fehlerkorrekturen laufen ohne separaten Beta-Kanal.
- Beta-Testinstallationen müssen eigene Home-Assistant-Entitäten, Einstellungen und Medienpfade erhalten, damit sie parallel testbar sind.
- App-Slug, bestehende Entitäts-IDs, gespeicherte Optionen und Prüfhistorie der regulären App bleiben kompatibel.

## Priorisierte Abnahme

| Priorität | Bereich | Abnahme |
| --- | --- | --- |
| P0 | Kompatibilität und Daten | Bestehende Entitäten, Einstellungen, Historie und Dashboards bleiben erhalten; neue Werte werden plausibilisiert. |
| P0 | Prüfung und Fehlerbehandlung | SLFork-Zeitstempel, Ersatzwerte, ungültige Referenzen, fehlende Bilder und OCR-Unsicherheit werden getrennt und nachvollziehbar behandelt. Automatik und manueller Test bleiben voneinander getrennt. |
| P1 | Einrichtung und mobile Bedienung | Der Assistent führt durch Quelle, Zählerformat, Bildbereich und Prüfplan und lässt sich mit aktuellen Werten erneut öffnen. Oberfläche und manuelle Diagnose funktionieren mobil. |
| P1 | Sprachen und Meldungen | Profilsprache von Home Assistant und manuelle Auswahl funktionieren je Nutzer. Hinweise sind verständlich und optionale Benachrichtigungen abschaltbar. |
| P1 | Bildquellen und Zählertypen | SLFork ist real am Zähler getestet. Alternative Kameras, ESPHome und weitere Bildtypen sind als simuliert gekennzeichnet, bis reale Gerätetests erfolgt sind. |
| P2 | Dokumentation und Freigabe | Deutsch und Englisch stimmen mit der App überein. GitHub Actions prüft OCR, Ingress, JavaScript, Konfiguration und App-Images. |

## Leitbild: Fire and Forget

Einmal möglichst automatisch einrichten. Danach prüft die App eigenständig, übernimmt nur belegte Verbesserungen und zeigt Unsicherheit sichtbar an. Ein errechneter Zwischenstand verändert keine bestätigten Messwerte oder Verbrauchszähler.

## 0.5 – Abnahme in dieser Reihenfolge

| Priorität | Arbeit | Abnahme |
| --- | --- | --- |
| P0 | Prüfung und Upgrade | Frische Einrichtung und Upgrade simulieren. Gemeldete Werte müssen bei fehlenden, alten, doppelten und unplausiblen Daten belastbar bleiben. In SLFork liegen reguläre Prüfungen mindestens fünf Minuten auseinander. Manuelle Tests und Grobeinrichtung laufen getrennt. |
| P1 | Live-Bildbearbeitung | Bildausschnitt, Drehung und einzelne Ziffernrahmen stimmen zwischen Vorschau, manuellem Test und Automatik überein. Rot, Gelb und Grün behalten ihre Bedeutung. |
| P1 | Grobeinrichtung | Bis zu 50 Grobversuche, bis zu 260 Rahmenversuche insgesamt und höchstens 20 Minuten für die normale Selbsteinrichtung. Verbesserungen über unabhängige Aufnahmen bestätigen. Den besten brauchbaren Versuch bei Bedarf zur Korrektur anbieten. |
| P1 | Bedienung und Anleitung | Ergebnisse auf der Übersicht, Fallback mit Speichern, sichtbare optionale Ziffernergänzung und dezenter Spendenlink. Bebilderte Anleitung mit synthetischen Beispielen. |
| P2 | Automatische Verbesserungen | Feinjustierung, Ziffernrekonstruktion und adaptive SLFork-Frequenz sind zuschaltbar. Langzeittests am echten Zähler stehen für diese Funktionen noch aus. Saisonprofile brauchen beobachtete Verbräuche aus den betreffenden Monaten. |

## 0.6 – experimentelle Funktionen in Stable

- [x] Zusätzliche kumulative Home-Assistant-Entitäten mit eigenem Intervall und Verlauf überwachen.
- [ ] Kamera, OCR und Rahmen je zusätzlichem Zähler einrichten.
- [ ] Hallsensor als ESPHome-Quelle integrieren. Die Kamera und der Hallsensor können am selben oder an getrennten ESPs hängen.
- [x] Experimentelle Zählerkarten mit Status und Stundenverlauf anzeigen.
- [ ] Reguläre Übersicht und Einstellungen weiter modernisieren.
- [x] Quelle, letzte gültige Ablesung und Ausfallstatus für zusätzliche Home-Assistant-Zähler anzeigen.
- [ ] Impulsfaktor pro Zähler einstellen und Testergebnisse für eingehende Impulse, Dubletten und Neustarts sichtbar machen.
- [x] Stable-App mit einem klar gekennzeichneten experimentellen Bereich ausliefern.
- [ ] Mehrzählerbetrieb mit realen Sensoren und Neustarts erproben.

Nach der ersten Beta prüfen: Kamera und Hallsensor demselben Zähler als Haupt- und Kontrollquelle zuordnen. Eine Verbrauchsbuchung hat genau eine Hauptquelle.

### Abnahmekriterien für 0.6

| Arbeit | Abnahme |
| --- | --- |
| Mehrzähler | Jeder Zähler erhält eine stabile ID, eigene Quelle, Einstellungen, Referenz, Prüfzeiten und Historie. Die Übersicht lässt sich pro Zähler öffnen. |
| ESPHome-Hallsensor | Einen kumulativen ESPHome-Pulssensor als Home-Assistant-Entität pro Zähler auswählen. Ein gemeinsamer oder separater ESP ist möglich. Impulsfaktor und Entprellung werden pro Gerät geprüft. |
| Oberfläche | Zählerwechsel, Status und Stunden- und Tagesverläufe sind mobil und am Desktop gut lesbar. Fehlende und geschätzte Angaben bleiben erkennbar. |
| Verbrauch | Doppelte Sensorwerte und Wiederverbindungen erzeugen keinen Mehrverbrauch. Zählerrücksetzung und Sensorneustart werden getrennt geprüft. |
| Beta parallel zu Stable | Eigene App-ID und getrennte Entitäten, Einstellungen und Medien. Der bestehende OCR-Zähler und seine Historie behalten ihre IDs. |

## Geplante Langzeit-Abnahme

- Ziffernstellungen und Beleuchtung über mehrere Messzyklen beobachten. Eine Rahmenänderung muss auf frischen Bildern besser abschneiden. Bei nachlassender Erkennung auf die zuletzt funktionierenden Rahmen zurückgehen.
- Je eine Vorkomma- und eine Nachkommastelle nur eindeutig aus bestätigtem Anker, erkannten Nachbarstellen und Durchflussgrenze ergänzen. Überträge und die Rückkehr zu vollständiger OCR prüfen.
- Prüfintervalle anhand bestätigter Änderungen und erwarteter Rollenwechsel variieren. Doppelte SLFork-Zyklen verändern die Fehlerzählung nicht. Unklare Fälle bleiben sichtbar.
- Weitere Zählertypen folgen anhand praktischer Tests.

## Abgleich der Anforderungen seit 0.5.4

| Bereich | Stand in 0.6.1 |
| --- | --- |
| Zählerfeld und Drehung | Mehrere Bildbereiche, große Ziffernreihen, manuell gewählter Suchbereich, Ziffernnachbarn, kleine Winkel und eine Rangliste waren bereits vorhanden. Kann die Grobsuche die erste Aufnahme so nicht zuverlässig lesen, prüft sie zusätzlich 180° und beide 90°-Drehungen. |
| Suchbudget und Fortschritt | Bestehende parallele OCR derselben Aufnahme und begrenzte CPU- und Speichernutzung. Die Höchstdauer der normalen Einrichtung schließt Wartezeit ein. Die Anzeige benennt sie als Einrichtungszeit. Die Diagnose zeigt Rahmen, Winkel, Kandidaten und unabhängige Bestätigungen. |
| Einzelziffer | Der bestehende Einzeltest läuft vor der OCR-Zusammensetzung. Normale Rahmen verschieben sich seitlich in gleicher Höhe und Größe. Die letzte Nachkommarolle wird bevorzugt vertikal geprüft. |
| Einrichtung und Betrieb | Die vorhandene Plausibilitätsprüfung, Referenzspeicherung und grüne Erfolgsmeldung bleiben maßgeblich. Gemäß der neueren Anforderung folgt nach dem Erfolg eine sofortige reguläre Prüfung. Dieselbe Prüfung lässt sich jetzt auch von der Übersicht aus anfordern. |
| Unklare Ziffern | Der Assistent bietet die vorhandene rechnerische Ergänzung für je eine Vor- und Nachkommastelle. Bei wiederholt unklaren Nachkommastellen kann die Vergleichsgenauigkeit nach Zustimmung sinken. Für echte Spiegelungen und wechselnde Beleuchtung steht der Langzeittest aus. |

## Arbeitsfortschritt für ChatGPT Work sichern (verbindliche Übergabe)

Diese Regeln gelten für längere Entwicklungsaufträge unabhängig davon, welcher Chat oder welche Work-Sitzung sie bearbeitet. Hintergrund: Ein Chat kann seine Kontext-/Nachrichtenbegrenzung oder Work sein Nutzungskontingent erreichen, bevor die Aufgabe fertig ist. Die exakten Restwerte sind dem ausführenden Modell gegebenenfalls nicht zugänglich.

1. **Vor Arbeitsbeginn** aktuellen `main`, offene Issues/PRs, Tests und diesen Plan lesen. Bereits umgesetzte, überholte oder widersprüchliche Wünsche nicht erneut implementieren.
2. **Früh einen eigenen Branch und einen Draft-PR anlegen**, sobald Codearbeit beginnt. Einen großen Auftrag in kleine, separat überprüfbare Schritte aufteilen.
3. **Zwischenergebnisse fortlaufend committen und pushen**, insbesondere vor langen Tests, weiteren größeren Änderungen oder komplexen Arbeitsschritten. Unfertige Arbeit ausdrücklich als *WIP / nicht freigegeben* markieren; keine ungetesteten Änderungen in `main` übernehmen.
4. **Den Draft-PR als Wiederaufnahmepunkt pflegen:** Ziel, bisherige Änderungen/Commit-SHAs, tatsächliche Testergebnisse, bekannte Fehler, offene Entscheidungen und den *konkret nächsten Schritt* festhalten. Auch bei einem Abbruch muss aus GitHub ersichtlich sein, wie man weiterarbeitet.
5. **Wenn ein Abbruch oder knappes Kontingent erkennbar wird**, möglichst erst den aktuellen kleinen Arbeitsschritt zu einem konsistenten Zwischenstand bringen und sichern. Falls die Plattform sofort stoppt, können weder Abschluss noch Warnung garantiert werden; deshalb nicht auf eine Warnung verlassen.
6. **Beim nächsten Work-Einsatz zuerst den vorhandenen Branch und Draft-PR fortsetzen**, statt bereits erledigte Arbeiten neu zu erzeugen. Erst nach erfolgreichen Prüfungen und Abgleich mit `main` veröffentlichen.
7. **Nicht implementierte Ideen getrennt von erledigten Änderungen führen.** Release-Notes und Changelog beschreiben nur tatsächlich ausgelieferte Funktionen.

**Verbesserungsidee für die ChatGPT-Work-Plattform (nicht Teil dieser App):** Vor Erreichen des Work-Kontingents oder einer Gesprächsgrenze rechtzeitig warnen; bereits begonnene kleine Arbeitsschritte möglichst noch geordnet abschließen lassen bzw. den aktuellen Stand automatisch sichern und zur späteren Fortsetzung anbieten. Dies ist ein Produktwunsch, keine zugesicherte Funktion und kein bereits eingereichtes OpenAI-Feedback.

## Dokumentation und Verbreitung: offene Aufgaben nach 0.6.8

Die Kurz-READMEs und die ausführlichen Anleitungen sind aufgetrennt; die Intervallbeschreibung und die reale Nutzung von **„ESP nur als Kamera“** sind korrigiert. Der offizielle My-Home-Assistant-Link fügt das Repository einfacher hinzu. Die folgende Liste enthält offene Aufgaben und zur Nachvollziehbarkeit die erledigte Lizenzentscheidung; vor einer neuen Umsetzung ist der aktuelle `main`-Stand zu prüfen:

| Priorität | Noch offen | Abnahme / Entscheidung |
| --- | --- | --- |
| Erledigt | **Open-Source-Lizenz** | Der Maintainer hat die **GNU GPL-3.0-or-later** für den eigenen Projektcode gewählt; vollständiger Lizenztext liegt unter `LICENSE`. Weitergegebene abgeleitete Versionen unterliegen den GPL-Quellcodepflichten. Vor einer späteren Lizenzänderung sind alle beteiligten Rechteinhaber und Drittlizenzen zu berücksichtigen. |
| P1 | GitHub-Metadaten und Release | Repository-Topics (z. B. `home-assistant`, `home-assistant-addon`, `ocr`, `esp32-cam`), nachvollziehbare GitHub-Releases anhand veröffentlichter Stable-Commits und ein optionaler Community-Beitrag. GitHub-Releases ersetzen nicht das Supervisor-Update. |
| P1 | Anonymisierter Screenshot / Demo-GIF | Nur Demo-/Beispieldaten veröffentlichen; App-Navigation, Ingress, Status und private Zähler-/Kameradaten unkenntlich machen. Bild auch in englischer README prüfen. |
| P1 | Einstellungen nachvollziehbar machen | Sichtbar machen, ob App-Konfigurationswert oder persistente Web-Einstellung aus `/data/auto-pruefregeln.json` greift. Alte Felder nur mit Migrationsplan und Abwärtskompatibilität entfernen. |
| P1 | Reproduzierbare Foto-Regressionstests | Rechte und Nutzbarkeit der 10 öffentlichen Ausgangsbilder klären, versionierte Offline-Testbilder mit lesbaren Sollwerten und akzeptabler Toleranz hinterlegen. In GitHub Actions bei Codeänderung mitführen; Fehlklassifikation oder Regression melden. |
| P2 | Einzelziffern-Klassifikator (Machbarkeitsstudie) | Geeignete echte und synthetische Trainings-/Testdaten, TFLite/ONNX-Laufzeit auf AMD64/ARM64 sowie Laufzeit, RAM, Genauigkeit und Unsicherheitsbehandlung **gegen die vorhandene Tesseract-Baseline messen**. Kein Austausch ohne belegten Vorteil. |
| P2 | ESPHome-Blitz/LED optional | Nur bei expliziter Entitätszuordnung und Zustimmung: Licht vor Aufnahme ein-, danach auch bei Fehlern wieder ausschalten; ursprünglichen Zustand respektieren. Keine überraschenden Änderungen an fremden Lichtern. |
| P2 | Freiwilliger Trainingsdatenexport | Datenschutz- und Einwilligungsdesign: nur freigegebene einzelne Ziffernausschnitte mit bestätigten Labels, Voransicht, Anonymisierung, kein stiller Upload; Lizenz der Beiträge klären. |

**Kompatibilität:** `rf1_ocr_test` und die bestehenden `rf1_*`-Home-Assistant-Entitäten nicht allein aus kosmetischen Gründen umbenennen; sie sind bereits installierte IDs und Datenquellen.

## Vor 1.0 noch zu bestätigen

1. GitHub Actions erfolgreich für AMD64 und ARM64.
2. Upgrade mit vorhandener Historie, Einstellungen und Dashboards in einer echten Supervisor-Installation.
3. SLFork mit aktuellen und veralteten Messzyklen sowie Wiederanlauf prüfen.
4. Ingress in Desktop-Browser und Home-Assistant-Companion-App mit mehreren Nutzern testen.
5. Echte Kamera-/Zählertests für alternative Quellen durchführen, bevor sie als real unterstützt beworben werden.
6. Push und E-Mail mit tatsächlich eingerichteten Home-Assistant-Zielen prüfen.
