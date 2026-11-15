# Gaszähler OCR-Kontrolle – Home-Assistant-App

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

**Kontrolliert einen automatisch erkannten Gaszählerstand mit einer zweiten, lokalen OCR-Lesung aus dem Zählerfoto.** Entwickelt für Pipersberg G4 RF1 und AI on the Edge / SLFork; auch eine passende Home-Assistant-Kamera ist möglich.

Das ist eine **zusätzliche Plausibilitätskontrolle**, kein amtliches Messgerät. OCR-Fehler sind möglich; für eine Abrechnung zählt die direkt am Zähler überprüfte Ablesung. Privates Hobbyprojekt ohne garantierten Support.

Die ausführliche Einführung, Voraussetzungen, Installation und Konfiguration findest du in der [Projektbeschreibung](../README.md).

## Installation

Über **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Thunder86/rf1-kontrollmessung` hinzufügen und **Gaszähler OCR-Kontrolle** installieren. Im SLFork-Modus die `esp_url` eintragen, starten und die Weboberfläche öffnen.

**Ältere lokale Installationen:** Der technische Ordner heißt weiter `rf1_ocr_test`. Beim Update innerhalb derselben App bleiben die Einstellungen normalerweise erhalten. Vor einem Wechsel zwischen lokaler und Repository-App die Einstellungen übernehmen und die alte App stoppen. Beide Varianten dürfen nicht gleichzeitig dieselben Sensoren aktualisieren.

## Sprache wählen

**Automatisch (Home Assistant)** verwendet nach Möglichkeit die Profilsprache. Deutsch und Englisch lassen sich pro angemeldetem Nutzer dauerhaft auswählen. Fehlt eine unterstützte Profilsprache, verwendet die App die passende Browsersprache oder Deutsch. Details zum Wechsel von 0.8.1 stehen in der [Projektbeschreibung](../README.md#sprache-der-weboberfläche).

## Automatische Kontrolle einstellen

Die **dauerhaften Prüfregeln** stehen auf der Weboberfläche im Abschnitt **„Automatische Prüfung – Einstellungen“**. Dort lassen sich die Vergleichsgenauigkeit (volle m³ oder 1–3 Nachkommastellen), die **maximalen OCR-Versuche (1–10)**, die **Ziffernfarbe (automatisch, hell oder dunkel)** und der **Bildausschnitt (automatisch oder fest)** einstellen und mit **„Speichern“** dauerhaft übernehmen.

Die gespeicherten Werte gelten ab den folgenden automatischen Prüfungen, auch nach Neustart. Bei einer Änderung der Vergleichsgenauigkeit startet die Bestätigungszählung mit der nächsten automatischen Prüfung neu. Sie liegen in `/data/auto-pruefregeln.json` und haben für diese Prüfregeln Vorrang vor den entsprechenden Optionen der App-Konfiguration. Die anderen App-Einstellungen werden weiterhin in Home Assistant konfiguriert.

## Was bedeutet „Jetzt prüfen“?

Den Bereich **„Manuellen Test öffnen“** bei Bedarf aufklappen. Dort lassen sich zusätzlich zur Ziffernfarbe, Genauigkeit und Anzahl der OCR-Versuche auch ein **eigener Bildausschnitt und die Breite der Vorkommastellen** einstellen. Diese Testoptionen ändern die automatische Kontrolle nicht. Wenn ein manueller Ausschnitt eine Vorschau erzeugt, kann man die Koordinaten direkt über **„Getesteten Ausschnitt für die Automatik übernehmen“** dauerhaft speichern. Der Button startet einen manuellen OCR-Test mit dem **letzten vorhandenen Foto**. Er erzeugt keine neue Kameraaufnahme. Die Statusanzeige zeigt **Anfrage → Bildabruf → OCR-Versuche → Ergebnis**. Im Infobereich neben dem Button steht die kurze Erklärung. Während der Prüfung ist der dezent hervorgehobene Button gesperrt und heißt **„Prüfung läuft …“**.

Die Zahl der OCR-Versuche lässt sich **von 1 bis maximal 10** einstellen (Standard: 5). **Sobald ein Versuch den Vergleichswert bestätigt, endet die Prüfung sofort.** Der Balken zeigt die abgeschlossenen Versuche; eine Enddauer wird nicht geschätzt. Die maximal zehn Versuche sind unabhängig von den **fünf automatischen Treffern innerhalb von 24 Stunden**. Manuelle Tests zählen nicht als automatische Treffer.

Die manuelle Testansicht zeigt **sofort das Ergebnis im Statusfeld**: sanftes Grün bei bestätigter Übereinstimmung, dezentes Rot bei Abweichung oder nicht lesbaren Ziffern, neutral während der Prüfung und ohne Referenzwert. Das **OCR-Testbild** zeigt grüne Rahmen an gelesenen Ziffern und rote Rahmen an unklaren Stellen. Bei manuell gesetzten Ausschnitten sind die Ziffernflächen näherungsweise aufgeteilt. Die Rahmenfarbe sagt **nicht** aus, ob die Ziffer mit dem Referenzwert übereinstimmt. Unter **„Mehr Infos“** werden die einzelnen Leseversuche aufgeführt. Fehlerhinweise erklären verständlich, was zu prüfen ist. Erkannter Stand und Referenz des Einzeltests stehen im Testergebnis. Die automatischen Kontrollbilder sind separat aufklappbar. Datum und Zeit sind kompakt. Technische Meldungen bleiben über Home Assistant verfügbar.

## Einstellungen und automatische Prüfung

Standardmäßig zählen **nur volle m³** (`vergleich_nachkommastellen: 0`). Nachkommastellen werden angezeigt, aber bei 0 nicht bewertet. `?` bedeutet unklare Ziffer. Die **automatischen** Prüfregeln lassen sich im eigenen Webbereich dauerhaft speichern. Die erweiterten **manuellen** Testoptionen gelten nur für diesen einen Test. Die übrige App-Konfiguration wird weiterhin in Home Assistant gepflegt.

Nach einem Treffer prüft die App üblicherweise stündlich, bei Unsicherheit etwa alle fünf Minuten. Standardmäßig meldet der Sensor nach vier Stunden ohne erfolgreiche Prüfung `review_due`. Unter **Benachrichtigungen** lassen sich Wartezeiten und Ziele ändern. Details stehen in der [Projektbeschreibung](../README.md#benachrichtigungen-und-prüfstatus).

Die Bilddateien liegen unter **Medien → Lokale Medien → rf1**. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` behalten ihre IDs für vorhandene Dashboards und Automationen.

## Projekt freiwillig unterstützen

Der unaufdringliche PayPal-Link steht am unteren Rand der Weboberfläche und in der [GitHub-README](../README.md). Spenden sind freiwillig und keine Voraussetzung für die Nutzung.
