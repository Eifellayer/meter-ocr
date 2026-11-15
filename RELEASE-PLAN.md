# Fahrplan für Version 1.0

Ausgangspunkt ist `main` bei `ee3294c` mit App-Version 0.8.1. Die offenen Issues [#1](https://github.com/Thunder86/rf1-kontrollmessung/issues/1), [#2](https://github.com/Thunder86/rf1-kontrollmessung/issues/2) und [#3](https://github.com/Thunder86/rf1-kontrollmessung/issues/3) sind teilweise umgesetzt. [#4](https://github.com/Thunder86/rf1-kontrollmessung/issues/4) ersetzt den bisherigen browserweiten Sprachmodus.

Die laufende Version 0.8.3 übernimmt 0.8.2 als Basis. Die Beta-Reihe beginnt bei 0.5.0. Die unten aufgeführten Live-Prüfungen gehören zur Freigabe von 1.0.

## GitHub-Zweige

- `stable` enthält den geprüften Stand, einschließlich der laufenden Version 0.8.3.
- `beta` startet von diesem Stand. Künftige Änderungen gehen zuerst auf `beta`. Nach erfolgreichen Prüftests und dokumentierter Abnahme werden sie in `stable` übernommen.
- `main` bleibt der Standardzweig für das bestehende Home-Assistant-Repository. Veröffentlichte Versionen werden aus `stable` nach `main` übernommen.

| Priorität | Arbeit | Abnahme |
| --- | --- | --- |
| P0 | Kompatibilität und sichere Zugriffe | App-Slug, Sensor-IDs, persistente Regeln und Historie erhalten. Supervisor als einziger Ingress-Absender. Core-Anmeldedaten bei Weiterleitungen schützen. |
| P0 | OCR und stabile Prüfungen | Veraltete ESP-Zyklen nicht erneut zählen. Fehlende Referenz, widersprüchliche Lesungen, fehlende Bilder und ungültige Ausschnitte abdecken. Diagnose und Automatik getrennt prüfen. |
| P1 | Profilsprache und mobile Oberfläche | Profilsprache je Nutzer, dauerhafte manuelle Auswahl, stiller Fallback. Kompakte Übersicht und ausklappbare Einstellungen bzw. Diagnose. |
| P1 | Ergebnisse und Ausschnitt | Neutraler laufender Test, Vergleichsgenauigkeit im Ergebnis, begrenzte OCR-Details, richtige Vorschau und Übernahme genau des angezeigten Tests. |
| P2 | Dokumentation und Freigabe | Deutsche und englische Anleitung, automatisierte Regressionstests, dokumentierter Test in einer echten Supervisor-Installation. |

## Architektur und Risiken

`run.py` koordiniert Bildquellen, OCR, Speicherung, Planung und Sensoren. `checks.py` enthält OCR, Vergleich und Zeitfenster. `layout.py` erkennt die SLFork-Rahmen. `panel.py` bedient Ingress und Diagnose. `settings.py` migriert App-Optionen, `reminder.py` verwaltet Home-Assistant-Hinweise und optionale Push-Nachrichten. Der Supervisor startet das Debian-Image auf AMD64 oder ARM64.

- Ein OCR-Profil beendet die Prüfung beim ersten gültigen Referenztreffer. Das schützt nicht vor systematischen Fehlablesungen. Mehrheitswerte dienen der Diagnose, die synthetischen OCR-Tests ersetzen keine Bilder realer Rollenübergänge.
- Im generischen Kameramodus liefert die App den Abrufzeitpunkt. Eine Kamera mit wiederholtem Standbild kann ohne verlässlichen Aufnahmezeitstempel keine unabhängigen Aufnahmezeitpunkte nachweisen.
- Die beiden Quellpfade unterscheiden sich. SLFork prüft den Messzeitstempel vor und nach dem Bildabruf. Im Kameramodus prüft die App Einheit und Aktualität des optionalen Sensors.
- Prüfhistorie, Bilder und Home-Assistant-Zustände werden getrennt geschrieben. Bei einem Prozessabbruch können einzelne Ansichten bis zur nächsten Prüfung unterschiedlich aktuell sein.

## Freigabe vor einem Tag 1.0

1. GitHub Actions müssen auf dem vorgesehenen Freigabestand erfolgreich sein.
2. In einer echten Supervisor-Installation ein Upgrade von 0.8.1 mit vorhandener Historie, Regeln und Dashboards prüfen. Beide Sensoren müssen ihre IDs und verwendeten Attribute behalten.
3. SLFork sowie HA-Kamera mit und ohne Referenz ausführen. Mit tatsächlichen Meterbildern korrekte Treffer, Abweichungen und unsichere Rollen prüfen. Wiederanlauf und optionale Erinnerungen kontrollieren.
4. Ingress im Desktop-Browser und in der Companion App mit zwei HA-Profilen testen. Die Sprache beim Wechsel während eines Tests, nach Speichern, nach Neuladen und bei nicht unterstützter Profilsprache prüfen.
5. Installierbarkeit auf AMD64 und ARM64 bestätigen.

## Umsetzung und Prüfprotokoll

| Bereich | Geprüft |
| --- | --- |
| #1 · Manueller Status | Chromium mit 320 und 1280 Pixeln. Neue Prüfung startet neutral, auch nach einem Treffer. Laufende Aufträge lassen sich durch eine zweite Anfrage nicht ersetzen. |
| #2 · Vergleich | Regressionstests für volle m³ und Dezimalstellen, fehlende Referenz und getrennte Genauigkeit in Automatik und Test. |
| #3 · OCR-Diagnose | Einzelversuche in aufklappbaren Details. Nur verglichene Stellen werden als unklar gemeldet. Bei ausschließlich unlesbaren Versuchen entfallen Positionsangaben. Crop-Vorschau und Übernahme über den Browser geprüft. |
| #4 · Sprache | Zwei nachgebildete Ingress-Nutzer, regionale Sprachcodes, Speichern, Wechsel während eines Tests, Neustart und Browser-Fallback geprüft. Ein fremder Elternkontext wird abgelehnt. |
| Daten und Schnittstellen | Worker-Test mit echten Bilddateien und nachgebildeten HA-Endpunkten. Optionenmigration, Prüfhistorie und beide Sensor-IDs geprüft. Bestehende Historie und Regeln benötigen keine neue Migration. |
| OCR und Toolchain | Lokal 43 Tests unter Python 3.11.18 bestanden, darunter Tesseract 5.5.0 mit einem synthetischen Zählwerk und ein Chromium-Test. Die Kameratests enthalten verschiedene Kontraste, Helligkeitsverläufe, leichte Neigung und einen um 90° gedrehten Ausschnitt aus einem 2560 × 1440-Pixel-Bild. JavaScript-Syntax beider Sprachvarianten geprüft. |

Der Profilsprache-Zugriff verwendet den angemeldeten Home-Assistant-Frontend-Kontext und liest ausschließlich den Sprachschlüssel des aktuellen Nutzers. Der Quellcode-Abgleich umfasst die [Ingress-Einbettung](https://github.com/home-assistant/frontend/blob/2d6ebd26d995ccb6c2445af0bbb305cdcca58cfa/src/panels/app/ha-panel-app.ts), den [Frontend-User-Data-Aufruf](https://github.com/home-assistant/frontend/blob/2d6ebd26d995ccb6c2445af0bbb305cdcca58cfa/src/data/frontend.ts), die [Zuordnung zum Sprachschlüssel](https://github.com/home-assistant/frontend/blob/2d6ebd26d995ccb6c2445af0bbb305cdcca58cfa/src/data/translation.ts) und die [Supervisor-Ingress-Header](https://github.com/home-assistant/supervisor/blob/98a2322374ae3d0c248079d11f7435ad759935fa/supervisor/api/ingress.py).

Der Workflow prüft die App-Images auf AMD64 und ARM64. Ein Live-Upgrade mit Supervisor, reale Zählerbilder einer SLFork- und ESPHome-Kamera, Companion App und Zustellung von Push und SMTP-E-Mail bleiben Freigabeprüfungen.

Die [Foto-Vergleichstests](METER-PHOTO-TESTS.md) dokumentieren zehn reale Anzeigen mit Ausschnitt, sichtbarer Ziffernfolge und OCR-Ergebnis.

### 0.8.3

Die 50 lokalen Tests unter Python 3.11 umfassen den direkten manuellen Start mit Fortschritt, eingeklappte Einstellungen, das erneute Planen nach einem Intervallwechsel und den gelben Hinweis vor Ablauf einer Stunde. Der ESP-Regressionstest prüft den Ersatzwert mit fortgeschriebenem Zeitstempel, den plausiblen OCR-Verlauf, den unveränderten Verbrauch und die anschließende Erholung. Der Benachrichtigungstest simuliert sowohl die Erholung vor Ablauf der Wartezeit als auch den Versand bei anhaltendem Ersatzwert.

Die App wertet die Zeitfelder und den Messstatus aus [SLForks Prozessdaten](https://github.com/Slider0007/AI-on-the-edge-device/blob/develop/docs/API/REST/process_data.md) aus. Beim negativen Grenzwert kann [die Firmware den Ersatzwert-Zeitstempel aktualisieren](https://github.com/Slider0007/AI-on-the-edge-device/blob/v17.4.1-SLFork/code/components/mainprocess_ctrl/ClassFlowPostProcessing.cpp), während sie den alten Wert weiter ausgibt. Der Test deckt diesen Ablauf ab.

Zehn weitere [Aufnahmen aus der AI-on-the-Edge-Community](METER-PHOTO-TESTS.md#083--zehn-aufnahmen-aus-der-ai-on-the-edge-community) ergänzen die OCR-Stichprobe. Keine ergab einen mehrheitlich gelesenen Stand. Die App benötigt für eine Freigabe zur allgemeinen Zählererkennung weitere Tests mit unveränderten Kamerabildern und unterschiedlichen Zählwerken.

## Ergänzungen für die Bedienung

- **Ersteinrichtung und Moduswechsel:** SLFork, Home-Assistant-Kamera mit optionaler Referenz und ESPHome/Kamera mit lokaler OCR. Der Worker-Test durchläuft den Kameraabruf und die Ausgabe des eigenen m³-Sensors. Er prüft Mindestübereinstimmung, PNG-Eingang, niedrigere Folgelesungen und die Trennung von bestätigten Referenztreffern.
- **Status:** Der Browser-Test prüft grünen Haken, roten Hinweis, Ausblenden und einen späteren neuen Vorfall. Unsichere Ziffernpositionen werden in kurzen Gruppen angezeigt.
- **Benachrichtigungen:** Getrennte Wartezeiten, Hinweis in Home Assistant, zusätzlich Push und/oder ein Notify-Ziel. Regressionstests simulieren die Aufrufe, Zustellfehler und Folgeversuche. Es werden dabei keine echten Nachrichten gesendet.
- **Verbrauch:** Tests prüfen den kumulativen m³-Sensor, den letzten gültigen Stand als Basis, Rücksprünge, unrealistische Anstiege, eine andere Vergleichsgenauigkeit und Quellenwechsel. Ein Live-Test mit Home Assistant Recorder und Energie-Dashboard steht aus.
