# Roadmap und Freigabeplan

Stand: November 2026 · aktuelle Version **0.6.11 Stable**

**Leitbild „Fire and Forget“:** Einmal möglichst automatisch einrichten. Danach prüft die App eigenständig, übernimmt nur belegte Verbesserungen und zeigt Unsicherheit sichtbar an. Ein errechneter Zwischenstand verändert keine bestätigten Messwerte oder Verbrauchszähler.

**Aktueller Schwerpunkt:** Stabilität und Feinschliff im Alltag vor neuen großen Funktionen.

## Als Nächstes

| Status | Aufgabe | Abnahme |
| --- | --- | --- |
| Beobachten | **Praxis 0.6.10/0.6.11** | Am echten Zähler prüfen, wie oft führende Stellen ergänzt werden und ob die neue Oberfläche in Browser und Companion-App gut bedienbar ist. |
| Offen | **Einstellungen nachvollziehbar machen** | Sichtbar machen, ob ein Wert aus der App-Konfiguration oder aus der Web-Einstellung (`/data/auto-pruefregeln.json`) greift. Alte Felder nur mit Migrationsplan entfernen. |
| Offen | **Reproduzierbare Foto-Regressionstests** | Versionierte Offline-Testbilder mit Sollwerten in GitHub Actions; Regressionen werden gemeldet. Rechte der Ausgangsbilder klären. |
| Offen | **GitHub-Releases, Topics und Screenshot** | Releases zu veröffentlichten Stable-Commits, Repository-Topics, anonymisierter Screenshot nur mit Demo-Daten. |
| Offen | **Drittlizenzen prüfen** | `SOURCES.md` deckt alle mitgelieferten Bausteine (u. a. Tesseract, Python-Pakete) mit Lizenz ab. |

## Mit dem Umstieg auf ESPHome-Kamera

| Aufgabe | Abnahme |
| --- | --- |
| **Realer Test der ESPHome-/Home-Assistant-Kamera** | Bisher nur simuliert. Vor der Bewerbung als „real unterstützt“ am echten Zähler mit höherer Auflösung testen; Bildausschnitt neu einrichten. |
| **Optionale LED-/Blitzsteuerung** | Nur bei ausdrücklicher Entitätszuordnung: Licht vor der Aufnahme ein- und danach – auch bei Fehlern – wieder ausschalten; ursprünglichen Zustand respektieren. |

## Später

Diese Funktionen kommen erst, wenn der Einzelzähler im Alltag zuverlässig läuft.

- **Mehrere Zähler:** Kamera, OCR und Rahmen je Zähler; stabile ID, eigene Quelle, Einstellungen, Referenz, Prüfzeiten und Historie. Mehrzählerbetrieb mit realen Sensoren und Neustarts erproben.
- **Hallsensor / Impulszähler über ESPHome:** Kumulativer Pulssensor als Kontroll- oder Hauptquelle; Impulsfaktor und Entprellung je Gerät; Dubletten, Wiederverbindungen und Neustarts erzeugen keinen Mehrverbrauch. Eine Verbrauchsbuchung hat genau eine Hauptquelle. Konzeptentwurf: [#18](https://github.com/Eifellayer/meter-ocr/pull/18) (veraltet, vor Umsetzung überarbeiten).
- **Langzeit-Abnahme der automatischen Verbesserungen:** Feinjustierung, Ziffernrekonstruktion und adaptive Prüfintervalle über viele Messzyklen, wechselnde Beleuchtung und echte Spiegelungen beobachten; bei nachlassender Erkennung auf die zuletzt funktionierenden Rahmen zurückgehen.
- **Einzelziffern-Klassifikator (Machbarkeitsstudie):** TFLite/ONNX auf AMD64/ARM64 gegen die Tesseract-Basis messen. Kein Austausch ohne belegten Vorteil.
- **Freiwilliger Trainingsdatenexport:** Nur freigegebene Ziffernausschnitte mit bestätigten Labels, Voransicht, kein stiller Upload; Lizenz der Beiträge klären.
- **Weitere Zählertypen** anhand praktischer Tests.

## Vor 1.0 noch zu bestätigen

1. GitHub Actions erfolgreich für AMD64 und ARM64.
2. Upgrade mit vorhandener Historie, Einstellungen und Dashboards in einer echten Supervisor-Installation.
3. SLFork mit aktuellen und veralteten Messzyklen sowie Wiederanlauf.
4. Ingress im Desktop-Browser und in der Companion-App mit mehreren Nutzern.
5. Echte Kamera-/Zählertests für alternative Quellen, bevor sie als real unterstützt beworben werden.
6. Push und E-Mail mit tatsächlich eingerichteten Home-Assistant-Zielen.

## Erledigt

| Version | Ergebnis |
| --- | --- |
| 0.6.11 | Hinweise zur letzten Rolle in Übersicht und Selbsteinrichtung; veraltete Ziffernvorschläge laufen ab. |
| 0.6.10 | Neue Oberfläche mit Rollenzählwerk, Kacheln, 24-Stunden-Diagramm und Reiter „Werkzeuge“; doppelte Bedienelemente zusammengeführt; unveränderliche führende Stellen werden aus dem bestätigten Stand ergänzt; Roadmap nur noch auf GitHub. |
| 0.6.9 | Unklare siebte Ziffer: einzelner Durchlauf wird mit einer Nachkommastelle teilbestätigt, danach 30 Minuten Wartezeit. |
| 0.6.7–0.6.8 | Sieben-Ziffern-Einrichtung wird sofort gespeichert; die achte Ziffer wird im Hintergrund gesucht, ohne die Automatik zu blockieren. |
| 0.6.5–0.6.6 | Reset mit Erhalt der Verbrauchsstatistik; Geräteerkennung im Assistenten robuster. |
| 0.6.0–0.6.4 | Einzelrahmen-Nachprüfung, Rahmenkandidaten in der Diagnose, Winkelvergleich ±1°/±2°, 180°/±90° in der Grobsuche, frisches Bild nach erfolgloser Winkelkorrektur, Demo ohne Kamera, experimenteller Bereich für zusätzliche Home-Assistant-Zähler (Praxistest steht aus). |
| 0.5.x | Selbsteinrichtung mit Live-Vorschau, Einzelrahmen und Drehung, Einrichtungsassistent, Benachrichtigungen, Sprachen DE/EN, Verbrauchsstatistik nach Stunde und Tag, Energie-Dashboard. |
| Lizenz | **GNU GPL-3.0-or-later** für den eigenen Projektcode; Volltext in `LICENSE`. |

Details zu jeder Version stehen im [Changelog](rf1_ocr_test/CHANGELOG.md).

## Releasekanal und Kompatibilität

- Stable ist der reguläre Kanal. Eine Beta wird nur bei größeren Änderungen mit konkretem zusätzlichem Testbedarf angelegt; sie erhält eigene App-ID, Entitäten, Einstellungen und Medienpfade, damit sie parallel testbar ist.
- App-Slug `rf1_ocr_test`, die `rf1_*`-Entitäten, gespeicherte Optionen und die Prüfhistorie bleiben kompatibel und werden nicht aus kosmetischen Gründen umbenannt.

## Arbeitsweise bei KI-gestützter Entwicklung

Diese Regeln gelten für längere Entwicklungsaufträge, unabhängig davon, welcher Assistent oder welche Sitzung sie bearbeitet. Ein Gespräch kann seine Kontextgrenze erreichen, bevor die Aufgabe fertig ist.

1. **Vor Arbeitsbeginn** aktuellen `main`, offene Issues/PRs, Tests und diesen Plan lesen. Bereits Umgesetztes, Überholtes oder Widersprüchliches nicht erneut implementieren.
2. **Früh einen eigenen Branch und einen Draft-PR anlegen**, sobald Codearbeit beginnt. Große Aufträge in kleine, separat prüfbare Schritte aufteilen.
3. **Zwischenergebnisse fortlaufend committen und pushen**, besonders vor langen Tests oder größeren Änderungen. Unfertiges ausdrücklich als *WIP / nicht freigegeben* markieren; nichts Ungetestetes in `main`.
4. **Den Draft-PR als Wiederaufnahmepunkt pflegen:** Ziel, Änderungen/Commits, tatsächliche Testergebnisse, bekannte Fehler, offene Entscheidungen und den konkreten nächsten Schritt.
5. **Beim nächsten Einsatz zuerst den vorhandenen Branch und Draft-PR fortsetzen.** Erst nach erfolgreichen Prüfungen und Abgleich mit `main` veröffentlichen.
6. **Ideen getrennt von Erledigtem führen.** Changelog und Release-Notes beschreiben nur tatsächlich ausgelieferte Funktionen.
