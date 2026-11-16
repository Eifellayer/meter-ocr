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

## 0.5 Beta – Abnahme in dieser Reihenfolge

| Priorität | Arbeit | Abnahme |
| --- | --- | --- |
| P0 | Prüfung und Upgrade | Frische Einrichtung und Upgrade simulieren. Gemeldete Werte müssen bei fehlenden, alten, doppelten und unplausiblen Daten belastbar bleiben. In SLFork liegen reguläre Prüfungen mindestens fünf Minuten auseinander. Manuelle Tests und Grobeinrichtung laufen getrennt. |
| P1 | Live-Bildbearbeitung | Bildausschnitt, Drehung und einzelne Ziffernrahmen stimmen zwischen Vorschau, manuellem Test und Automatik überein. Rot, Gelb und Grün behalten ihre Bedeutung. |
| P1 | Grobeinrichtung | Höchstens 100 Rahmenversuche, 100 unterschiedliche Aufnahmen und 15 Minuten Laufzeit. Geprüfte Rahmen vergleichen und vor der Übernahme auf einem weiteren Bild bestätigen. Den besten brauchbaren Versuch bei Bedarf zur Korrektur anbieten. |
| P1 | Bedienung und Anleitung | Ergebnisse auf der Übersicht, Fallback mit Speichern, sichtbare optionale Ziffernergänzung und dezenter Spendenlink. Bebilderte Anleitung mit synthetischen Beispielen. |
| P2 | Automatische Verbesserungen | Feinjustierung, Ziffernrekonstruktion und adaptive SLFork-Frequenz sind zuschaltbar. Langzeittests am echten Zähler bleiben Teil der Beta. Saisonprofile brauchen beobachtete Verbräuche aus den betreffenden Monaten. |

## Geplante Langzeit-Abnahme

- Ziffernstellungen und Beleuchtung über mehrere Messzyklen beobachten. Eine Rahmenänderung muss auf frischen Bildern besser abschneiden. Bei nachlassender Erkennung auf die zuletzt funktionierenden Rahmen zurückgehen.
- Je eine Vorkomma- und eine Nachkommastelle nur eindeutig aus bestätigtem Anker, erkannten Nachbarstellen und Durchflussgrenze ergänzen. Überträge und die Rückkehr zu vollständiger OCR prüfen.
- Prüfintervalle anhand bestätigter Änderungen und erwarteter Rollenwechsel variieren. Doppelte SLFork-Zyklen verändern die Fehlerzählung nicht. Unklare Fälle bleiben sichtbar.
- Mehrere Zähler und zusätzliche Zählertypen folgen als eigene Erweiterungen. Der Pulszähler-Entwurf wird frühestens für **0.6** weiterentwickelt.

## Vor 1.0 noch zu bestätigen

1. GitHub Actions erfolgreich für AMD64 und ARM64.
2. Upgrade mit vorhandener Historie, Einstellungen und Dashboards in einer echten Supervisor-Installation.
3. SLFork mit aktuellen und veralteten Messzyklen sowie Wiederanlauf prüfen.
4. Ingress in Desktop-Browser und Home-Assistant-Companion-App mit mehreren Nutzern testen.
5. Echte Kamera-/Zählertests für alternative Quellen durchführen, bevor sie als real unterstützt beworben werden.
6. Push und E-Mail mit tatsächlich eingerichteten Home-Assistant-Zielen prüfen.
