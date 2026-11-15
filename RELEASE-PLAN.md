# Fahrplan für Version 1.0

Ausgangspunkt ist `main` bei `ee3294c` mit App-Version 0.8.1. Die offenen Issues [#1](https://github.com/Thunder86/rf1-kontrollmessung/issues/1), [#2](https://github.com/Thunder86/rf1-kontrollmessung/issues/2) und [#3](https://github.com/Thunder86/rf1-kontrollmessung/issues/3) sind teilweise umgesetzt. [#4](https://github.com/Thunder86/rf1-kontrollmessung/issues/4) ersetzt den bisherigen browserweiten Sprachmodus.

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
