# Gaszähler OCR-Kontrolle – Home-Assistant-App

**Kontrolliert einen automatisch erkannten Gaszählerstand mit einer zweiten, lokalen OCR-Lesung aus dem Zählerfoto.** Entwickelt für Pipersberg G4 RF1 und AI on the Edge / SLFork; auch eine passende Home-Assistant-Kamera ist möglich.

Das ist eine **zusätzliche Plausibilitätskontrolle**, kein amtliches Messgerät. OCR-Fehler sind möglich; für eine Abrechnung zählt die direkt am Zähler überprüfte Ablesung. Privates Hobbyprojekt ohne garantierten Support.

Die ausführliche Einführung, Voraussetzungen, Installation und Konfiguration findest du in der [Projektbeschreibung](../README.md).

## Installation

Über **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Thunder86/rf1-kontrollmessung` hinzufügen und **Gaszähler OCR-Kontrolle** installieren. Im SLFork-Modus die `esp_url` eintragen, starten und die Weboberfläche öffnen.

**Ältere lokale Installationen:** Der technische Ordner heißt weiter `rf1_ocr_test`. Beim Update innerhalb derselben App bleiben die Einstellungen normalerweise erhalten. Vor einem Wechsel zwischen lokaler und Repository-App die Einstellungen übernehmen und die alte App stoppen. Beide Varianten dürfen nicht gleichzeitig dieselben Sensoren aktualisieren.

## Automatische Kontrolle einstellen

Die **dauerhaften Prüfregeln** stehen auf der Weboberfläche im Abschnitt **„Automatische Prüfung – Einstellungen“**. Dort lassen sich die Vergleichsgenauigkeit (volle m³ oder 1–3 Nachkommastellen) und die **maximalen OCR-Versuche (1–10)** einstellen und mit **„Speichern“** dauerhaft übernehmen.

Die gespeicherten Werte gelten ab den folgenden automatischen Prüfungen, auch nach Neustart. Sie liegen in `/data/auto-pruefregeln.json` und haben Vorrang vor den beiden entsprechenden Optionen der App-Konfiguration. Die anderen App-Einstellungen werden weiterhin in Home Assistant konfiguriert.

## Was bedeutet „Jetzt prüfen“?

Den Bereich **„Manuellen Test öffnen“** bei Bedarf aufklappen. Dort lassen sich zusätzlich zur Ziffernfarbe, Genauigkeit und Anzahl der OCR-Versuche auch ein **eigener Bildausschnitt und die Breite der Vorkommastellen** einstellen. Diese Testoptionen ändern die automatische Kontrolle nicht. Der Button startet einen manuellen OCR-Test mit dem **letzten vorhandenen Foto**. Er erzeugt keine neue Kameraaufnahme. Die Statusanzeige zeigt **Anfrage → Bildabruf → OCR-Versuche → Ergebnis**. Im Infobereich neben dem Button steht die kurze Erklärung. Während der Prüfung ist der dezent hervorgehobene Button gesperrt und heißt **„Prüfung läuft …“**.

Die Zahl der OCR-Versuche lässt sich **von 1 bis maximal 10** einstellen (Standard: 5). **Sobald ein Versuch den Vergleichswert bestätigt, endet die Prüfung sofort.** Der Balken zeigt die abgeschlossenen Versuche; eine Enddauer wird nicht geschätzt. Die maximal zehn Versuche sind unabhängig von den **fünf automatischen Treffern innerhalb von 24 Stunden**. Manuelle Tests zählen nicht als automatische Treffer.

Die manuelle Testansicht zeigt **sofort das Ergebnis im Statusfeld**: sanftes Grün bei bestätigter Übereinstimmung, dezentes Rot bei Abweichung oder nicht lesbaren Ziffern, neutral ohne Referenzwert. Fehlerhinweise erklären verständlich, was zu prüfen ist. Doppelte Werte sind entfernt; die gemeinsamen Zählerwerte und Bilder stehen übersichtlich in der automatischen Kontrolle. Datum und Zeit sind kompakt. Technische Meldungen bleiben über Home Assistant verfügbar.

## Einstellungen und automatische Prüfung

Standardmäßig zählen **nur volle m³** (`vergleich_nachkommastellen: 0`). Nachkommastellen werden angezeigt, aber bei 0 nicht bewertet. `?` bedeutet unklare Ziffer. Die **automatischen** Prüfregeln lassen sich im eigenen Webbereich dauerhaft speichern. Die erweiterten **manuellen** Testoptionen gelten nur für diesen einen Test. Die übrige App-Konfiguration wird weiterhin in Home Assistant gepflegt.

Nach einem Treffer prüft die App üblicherweise stündlich, bei Unsicherheit etwa alle fünf Minuten. Nach vier Stunden ohne Übereinstimmung entsteht `review_due`. Optional kann eine offene Erinnerung nach weiteren 24 Stunden an die Companion App geschickt werden.

Die Bilddateien liegen unter **Medien → Lokale Medien → rf1**. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` behalten ihre IDs für vorhandene Dashboards und Automationen.
