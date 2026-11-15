# Gaszähler OCR-Kontrolle – Home-Assistant-App

**Kontrolliert einen automatisch erkannten Gaszählerstand mit einer zweiten, lokalen OCR-Lesung aus dem Zählerfoto.** Entwickelt für Pipersberg G4 RF1 und AI on the Edge / SLFork; auch eine passende Home-Assistant-Kamera ist möglich.

Das ist eine **zusätzliche Plausibilitätskontrolle**, kein amtliches Messgerät. OCR-Fehler sind möglich; für eine Abrechnung zählt die direkt am Zähler überprüfte Ablesung. Privates Hobbyprojekt ohne garantierten Support.

Die ausführliche Einführung, Voraussetzungen, Installation und Konfiguration findest du in der [Projektbeschreibung](../README.md).

## Installation

Über **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Thunder86/rf1-kontrollmessung` hinzufügen und **Gaszähler OCR-Kontrolle** installieren. Im SLFork-Modus die `esp_url` eintragen, starten und die Weboberfläche öffnen.

**Ältere lokale Installationen:** Der technische Ordner heißt weiter `rf1_ocr_test`. Beim Update innerhalb derselben App bleiben die Einstellungen normalerweise erhalten. Vor einem Wechsel zwischen lokaler und Repository-App die Einstellungen übernehmen und die alte App stoppen. Beide Varianten dürfen nicht gleichzeitig dieselben Sensoren aktualisieren.

## Was bedeutet „Jetzt prüfen“?

Der Button startet einen manuellen OCR-Test mit dem **letzten vorhandenen Foto**. Er erzeugt keine neue Kameraaufnahme. Der Status zeigt die Schritte **Anfrage → Bildabruf → OCR-Durchlauf 1–5 → Abschluss**, einen Fortschrittsbalken für tatsächlich absolvierte Aufbereitungen und die verstrichene Zeit.

Bei einer eindeutigen ersten Lesung endet die Prüfung frühzeitig; ansonsten werden bis zu fünf Bildaufbereitungen ausgewertet. Das ist unabhängig von den **fünf automatischen Treffern innerhalb von 24 Stunden**. Manuelle Tests zählen nicht als neue automatische Treffer.

Die manuelle Testansicht zeigt nur Zeitpunkt und Ergebnis; die gemeinsamen Zählerwerte und Bilder stehen übersichtlich in der automatischen Kontrolle. Datum und Zeit sind auf der Oberfläche kompakt dargestellt. Diagnoseangaben wie Prozessfehler bleiben intern und über Home Assistant verfügbar, ohne die normale Ansicht zu überfrachten.

## Einstellungen und automatische Prüfung

Standardmäßig zählen **nur volle m³** (`vergleich_nachkommastellen: 0`). Nachkommastellen werden angezeigt, aber bei 0 nicht bewertet. `?` bedeutet unklare Ziffer. Auf der Weboberfläche einstellbare Testoptionen gelten für den manuellen Test; die dauerhafte Konfiguration gehört zur App.

Nach einem Treffer prüft die App üblicherweise stündlich, bei Unsicherheit etwa alle fünf Minuten. Nach vier Stunden ohne Übereinstimmung entsteht `review_due`. Optional kann eine offene Erinnerung nach weiteren 24 Stunden an die Companion App geschickt werden.

Die Bilddateien liegen unter **Medien → Lokale Medien → rf1**. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` behalten ihre IDs für vorhandene Dashboards und Automationen.
