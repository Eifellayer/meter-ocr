# AI Meter Reader – Home-Assistant-App

**Sprache / Language:** [Deutsch](README.md) · [English](README.en.md)

**Liest Zählerstände lokal aus Kamerabildern und kann sie mit einem vorhandenen Messwert abgleichen.** Geeignet für mechanische Rollenzähler mit einstellbarer Stellenzahl und verschiedene Bildquellen wie AI on the Edge / SLFork, ESPHome oder Home-Assistant-Kameras.

Das ist eine **zusätzliche Plausibilitätskontrolle**, kein amtliches Messgerät. OCR-Fehler sind möglich; für eine Abrechnung zählt die direkt am Zähler überprüfte Ablesung. Privates Hobbyprojekt ohne garantierten Support.

Der Einrichtungsassistent führt durch Bildquelle, Zählerformat, Bildausschnitt, Prüfintervall und Benachrichtigungen. Er lässt sich jederzeit erneut öffnen und übernimmt die gespeicherten Werte. Der Maintainer hat reale Zählertests ausschließlich mit AI on the Edge / SLFork durchgeführt; andere Modi wurden simuliert getestet.

Die ausführliche Einführung, Voraussetzungen, Installation und Konfiguration findest du in der [Projektbeschreibung](../README.md).

## Installation

**AI Meter Reader 0.6.5** ist auf Stable. Unter „App-Daten zurücksetzen“ stehen nun ein vollständiger Werksreset und ein zweiter Reset mit Erhalt der Zählerstands- und Verbrauchsstatistik zur Auswahl. Die optionalen Langzeitfunktionen bleiben zuschaltbar.

Über **Einstellungen → Apps → App installieren → ⋮ → Repositories** den [Stable-Link](https://github.com/Eifellayer/meter-ocr#stable) hinzufügen und **AI Meter Reader** installieren. Im SLFork-Modus die `esp_url` eintragen, starten und die Weboberfläche öffnen.

## Sprache wählen

**Automatisch (Home Assistant)** verwendet nach Möglichkeit die Profilsprache. Deutsch und Englisch lassen sich pro angemeldetem Nutzer dauerhaft auswählen. Fehlt eine unterstützte Profilsprache, verwendet die App die passende Browsersprache oder Deutsch.

## Automatische Kontrolle einstellen

Die **dauerhaften Prüfregeln** stehen auf der Weboberfläche im Abschnitt **„Automatische Prüfung – Einstellungen“**. Dort lassen sich die Vergleichsgenauigkeit (volle m³ oder 1–3 Nachkommastellen; bei Nachkommastellen wird auf die gewählte Stelle gerundet), die **maximalen OCR-Versuche (1–10)**, die **Ziffernfarbe (automatisch, hell oder dunkel)** und der **Bildausschnitt (automatisch oder fest)** einstellen und mit **„Speichern“** dauerhaft übernehmen.

Die gespeicherten Werte bleiben auch nach einem Neustart erhalten. Nach dem Speichern startet sofort eine neue automatische Prüfung; bei geänderter Vergleichsgenauigkeit beginnt die Bestätigungszählung mit dieser Prüfung neu. Sie liegen in `/data/auto-pruefregeln.json` und haben für diese Prüfregeln Vorrang vor den entsprechenden Optionen der App-Konfiguration. Die anderen App-Einstellungen werden weiterhin in Home Assistant konfiguriert.

## Was bedeutet „Jetzt prüfen“?

Den Bereich **„Manuellen Test öffnen“** bei Bedarf aufklappen. Dort lassen sich zusätzlich zur Ziffernfarbe, Genauigkeit und Anzahl der OCR-Versuche auch ein **eigener Bildausschnitt und die Breite der Vorkommastellen** einstellen. Diese Testoptionen ändern die automatische Kontrolle nicht. Wenn ein manueller Ausschnitt eine Vorschau erzeugt, kann man die Koordinaten direkt über **„Getesteten Ausschnitt für die Automatik übernehmen“** dauerhaft speichern. **„Speichern und prüfen“** öffnet nach der Einrichtung die Übersicht und startet die automatische Prüfung sofort. Ein gelber Balken zeigt den Bildabruf und die OCR-Versuche. Über **„Eigenes Bild testen“** kann ein **eigenes JPG- oder PNG-Bild bis 3 MB** ausgewählt werden; ohne Upload nutzt der Test das letzte vorhandene Kamerabild. Bei einer Livebild-Quelle holt der Test ein neues Standbild; mit einem Upload verwendet er ausschließlich das ausgewählte Testbild. Die Statusanzeige zeigt **Anfrage → Bildabruf → OCR-Versuche → Ergebnis**. Im Infobereich neben dem Button steht die kurze Erklärung. Während der Prüfung ist der dezent hervorgehobene Button gesperrt und heißt **„Prüfung läuft …“**.

Bei einer unsicheren automatischen Ablesung folgen bis zu zehn zusätzliche Bildauswertungen (höchstens 15 insgesamt). Ziffern werden nur bei einer strikten Mehrheit zusammengesetzt. Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Nach drei Fehlprüfungen wartet die App eine Stunde auf einen höheren Zählerstand oder ein neues Bild und versucht es erneut. Der Zähler der Fehlprüfungen und der Grund der Wartezeit stehen direkt in der Übersicht. Der OCR-Fortschrittsbalken zeigt abgeschlossene Versuche; eine Enddauer wird nicht geschätzt. Die maximal 15 OCR-Versuche je Bild sind unabhängig von den **fünf automatischen Treffern innerhalb von 24 Stunden**. Manuelle Tests zählen nicht als automatische Treffer.

Die manuelle Testansicht zeigt **sofort das Ergebnis im Statusfeld**: sanftes Grün bei bestätigter Übereinstimmung, dezentes Rot bei Abweichung oder nicht lesbaren Ziffern, neutral während der Prüfung und ohne Referenzwert. Das **OCR-Testbild** zeigt grüne Rahmen an gelesenen Ziffern und rote Rahmen an unklaren Stellen. Bei manuell gesetzten Ausschnitten sind die Ziffernflächen näherungsweise aufgeteilt. Die Rahmenfarbe sagt **nicht** aus, ob die Ziffer mit dem Referenzwert übereinstimmt. Unter **„Mehr Infos“** werden die einzelnen Leseversuche aufgeführt. Fehlerhinweise erklären verständlich, was zu prüfen ist. Erkannter Stand und Referenz des Einzeltests stehen im Testergebnis. Die automatischen Kontrollbilder sind separat aufklappbar. Datum und Zeit sind kompakt. Technische Meldungen bleiben über Home Assistant verfügbar.

## Einstellungen und automatische Prüfung

Standardmäßig zählen **nur volle m³** (`vergleich_nachkommastellen: 0`). Nachkommastellen werden angezeigt, aber bei 0 nicht bewertet. `?` bedeutet unklare Ziffer. Die **automatischen** Prüfregeln lassen sich im eigenen Webbereich dauerhaft speichern. Die erweiterten **manuellen** Testoptionen gelten nur für diesen einen Test. Die übrige App-Konfiguration wird weiterhin in Home Assistant gepflegt.

Nach einem Treffer prüft die App standardmäßig stündlich. Nach einer Fehlprüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben drei Prüfungen erfolglos, wartet die App eine Stunde auf einen höheren Zählerstand oder ein neues Bild. Nach einem erfolgreichen Abgleich gilt wieder das eingestellte Intervall. Standardmäßig meldet der Sensor nach vier Stunden ohne erfolgreiche Prüfung `review_due`. Unter **Benachrichtigungen** lassen sich Wartezeiten und Ziele ändern. Details stehen in der [Projektbeschreibung](../README.md#benachrichtigungen-und-prüfstatus).

Über **„Automatik pausieren“** hältst du automatische Prüfungen an. Eine auffällige gelbe Meldung zeigt die Pause; manuelle Tests funktionieren weiter. Die Pause bleibt nach einem Neustart bestehen. In der Übersicht siehst du außerdem, ob die App wartet, ein Bild aufnimmt oder es auswertet, und ob ESP oder Kamera erreichbar waren. Sie erklärt auch, ob das Bild zu alt, bereits geprüft oder nicht lesbar war. Ist die App gestoppt oder nicht erreichbar, meldet die geöffnete Seite den Verbindungsverlust.

Die Bilddateien liegen unter **Medien → Lokale Medien → rf1**. Die bestehenden Entitäten `sensor.rf1_kontrollbild` und `sensor.rf1_pruefstatus` behalten ihre IDs für vorhandene Dashboards und Automationen.

## Projekt freiwillig unterstützen

Der PayPal-Link steht in der Weboberfläche unter **Über AI Meter Reader**. Spenden sind freiwillig und keine Voraussetzung für die Nutzung.
