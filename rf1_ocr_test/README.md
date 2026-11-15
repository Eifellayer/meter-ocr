# Meter OCR – Home-Assistant-App

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

**Liest Zählerstände lokal aus Kamerabildern und kann sie mit einem vorhandenen Messwert abgleichen.** Entwickelt für Pipersberg G4 RF1 und AI on the Edge / SLFork; auch eine passende Home-Assistant-Kamera ist möglich.

Das ist eine **zusätzliche Plausibilitätskontrolle**, kein amtliches Messgerät. OCR-Fehler sind möglich; für eine Abrechnung zählt die direkt am Zähler überprüfte Ablesung. Privates Hobbyprojekt ohne garantierten Support.

Die ausführliche Einführung, Voraussetzungen, Installation und Konfiguration findest du in der [Projektbeschreibung](../README.md).

## Installation

Diese App befindet sich in der Beta-Phase.

Über **Einstellungen → Apps → App installieren → ⋮ → Repositories** die Adresse `https://github.com/Eifellayer/rf1-kontrollmessung` hinzufügen und **Meter OCR** installieren. Im SLFork-Modus die `esp_url` eintragen, starten und die Weboberfläche öffnen.

## Sprache wählen

**Automatisch (Home Assistant)** verwendet nach Möglichkeit die Profilsprache. Deutsch und Englisch lassen sich pro angemeldetem Nutzer dauerhaft auswählen. Fehlt eine unterstützte Profilsprache, verwendet die App die passende Browsersprache oder Deutsch.

## Automatische Kontrolle einstellen

Unter **Einstellungen → Automatische Prüfung** kannst du das Prüfintervall, die Vergleichsgenauigkeit, die Anzahl der OCR-Versuche, die Ziffernfarbe und den Bildausschnitt dauerhaft speichern.

Die gespeicherten Werte gelten ab den folgenden automatischen Prüfungen, auch nach Neustart. Bei einer Änderung der Vergleichsgenauigkeit startet die Bestätigungszählung mit der nächsten automatischen Prüfung neu. Sie liegen in `/data/auto-pruefregeln.json` und haben für diese Prüfregeln Vorrang vor den entsprechenden Optionen der App-Konfiguration. Die anderen App-Einstellungen werden weiterhin in Home Assistant konfiguriert.

## Manueller Test

**Test starten** liest das letzte vorhandene Bild. Fortschritt und Ergebnis erscheinen direkt unter dem Knopf. Über **Testeinstellungen** kannst du Ziffernfarbe, Genauigkeit, Versuchszahl und Ausschnitt für den Test ändern. Nach einem Test mit Vorschau kannst du den Ausschnitt für die Automatik übernehmen.

Die Zahl der OCR-Versuche lässt sich **von 1 bis maximal 10** einstellen (Standard: 5). **Sobald ein Versuch den Vergleichswert bestätigt, endet die Prüfung sofort.** Der Balken zeigt die abgeschlossenen Versuche; eine Enddauer wird nicht geschätzt. Die maximal zehn Versuche sind unabhängig von den **fünf automatischen Treffern innerhalb von 24 Stunden**. Manuelle Tests zählen nicht als automatische Treffer.

Das Testfeld zeigt Grün bei Übereinstimmung und Gelb bei Abweichung oder unsicheren Ziffern. Das **OCR-Testbild** markiert gelesene Ziffern grün und unklare Stellen rot. Bei manuell gesetzten Ausschnitten sind die Ziffernflächen näherungsweise aufgeteilt. **Mehr Infos** zeigt die einzelnen Leseversuche.

## Einstellungen und automatische Prüfung

Standardmäßig zählen **nur volle m³** (`vergleich_nachkommastellen: 0`). Nachkommastellen werden angezeigt, aber bei 0 nicht bewertet. `?` bedeutet unklare Ziffer. Die **automatischen** Prüfregeln lassen sich im eigenen Webbereich dauerhaft speichern. Die erweiterten **manuellen** Testoptionen gelten nur für diesen einen Test. Die übrige App-Konfiguration wird weiterhin in Home Assistant gepflegt.

Nach einem Treffer prüft die App standardmäßig nach 60 Minuten. Bei einem Fehlschlag folgt innerhalb von fünf Minuten ein neuer Versuch. Der gelbe Hinweis zeigt nach einer Stunde Details, auch zum ESP-Ersatzwert und dessen Messzeit. Standardmäßig meldet der Sensor nach vier Stunden ohne erfolgreiche Prüfung `review_due`. Unter **Benachrichtigungen** lassen sich Wartezeiten und Ziele ändern. [Projektbeschreibung](../README.md#benachrichtigungen-und-prüfstatus)

Die Bilddateien liegen unter **Medien → Lokale Medien → rf1**. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` behalten ihre IDs für vorhandene Dashboards und Automationen.

## Projekt freiwillig unterstützen

Der unaufdringliche PayPal-Link steht am unteren Rand der Weboberfläche und in der [GitHub-README](../README.md). Spenden sind freiwillig und keine Voraussetzung für die Nutzung.
