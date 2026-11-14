# RF1 Kontrollmessung

> **Privates Hobbyprojekt · Verwendung auf eigene Gefahr**  
> Der Quellcode ist öffentlich zugänglich. Für dieses Projekt wird kein Support angeboten. Wartung und weitere Updates sind freiwillig.  
> Die OCR kann Ziffern falsch erkennen. Für Abrechnungen und Meldungen an den Versorger gilt der direkt am Zähler abgelesene Stand.

Dieses Update ersetzt den lokalen **RF1 OCR Probelauf**. Der Ordnername
`rf1_ocr_test` bleibt für das Update bestehen.

1. Den Ordner `rf1_ocr_test` aus der ZIP in dieselbe Samba-Freigabe
   `local_apps` kopieren und die vorhandenen Dateien überschreiben.
2. In Home Assistant unter **Einstellungen → Apps → App installieren** im
   Drei-Punkte-Menü **Nach Updates suchen** wählen.
3. Die vorhandene App auf die neueste Version aktualisieren und bei Bedarf starten.
   Beim Update bleiben die App-Einstellungen und gespeicherten Treffer erhalten.

## Prüfintervall und Sichtprüfung

Unter **Weboberfläche öffnen** findest du den Countdown, **Jetzt prüfen**
und den Vergleich mit dem letzten bestätigten Bild. Erkannte Nachkommastellen
werden angezeigt. Unklare Stellen erscheinen als `?`. Die Einstellung
`vergleich_nachkommastellen` bestimmt die Genauigkeit des Vergleichs (0–3).
ESPHome- und andere Home-Assistant-Kameras lassen sich über `kamera_entitaet`
einbinden. Im Kameramodus ist ein absoluter m³-Zählerstand aus einem Sensor
als Referenz möglich, auch wenn dieser aus Impulsen berechnet wird.

Nach einem Treffer prüft die App nach einer Stunde erneut. Bei einer Abweichung,
einem unklaren Bild oder fehlenden aktuellen Daten prüft sie alle fünf Minuten.
Vier Stunden ohne bestätigte Übereinstimmung setzen
`sensor.rf1_pruefstatus` auf `review_due`. Eine Übereinstimmung beendet die
engmaschige Prüfung sofort. Die App speichert den Beginn der Störung und
den nächsten Prüfzeitpunkt über Neustarts hinweg.

Die App holt das ausgerichtete JPEG und die Werte derselben SLFork-Messung.
Tesseract liest die fünf Vorkommastellen.
Mindestens zwei Bildaufbereitungen müssen denselben Wert ergeben. Eine
abweichende vollständige Lesung gilt als mehrdeutig. Ein Treffer zählt,
wenn der OCR-Wert mit den ganzen Kubikmetern aus **Raw Value** und
**Actual Value** übereinstimmt. Ab Version 0.4.1 werden dabei auch SLFork-Werte
mit vier oder mehr Nachkommastellen verarbeitet, indem nur der Vorkommateil
für den Vergleich verwendet wird.
Jeder Messzeitpunkt zählt einmal und bleibt 24 Stunden lang berücksichtigt,
auch über Mitternacht und Neustarts hinweg.

Das Original liegt unter **Medien → Lokale Medien → rf1 → kontrollbild.jpg**.
In `sensor.rf1_kontrollbild` stehen der kompakte Ziffernausschnitt, sein
Zeitstempel und `matches_last_24h`. Der Ausschnitt enthält die Nachkommastellen
für eine mögliche Sichtprüfung. Das Protokoll meldet **Kontrollbild bereit**
mit OCR-Wert und Prüfergebnis.

Die App sucht die grünen Ziffernrahmen im SLFork-Bild mit Markierungen und
liest die fünf Vorkommastellen aus dem ausgerichteten Bild ohne Markierungen.
Die OCR prüft die normale und die invertierte Darstellung. Im Sensorattribut
`crop_source` und im Protokoll zeigt `auto` den automatisch gewählten Ausschnitt.
Bei fehlenden oder nicht erkennbaren Rahmen verwendet die App die Werte
`ausschnitt` und `vorkomma_breite` aus ihrer Konfiguration und meldet `manual`.
Die Ziffernrahmen in SLFork müssen auf den Rollen liegen.

## Optionale Push-Erinnerung

Trage unter `push_dienst` den Benachrichtigungsdienst deiner Home Assistant
Companion App ein, etwa `notify.mobile_app_mein_handy`. Lass das Feld leer,
wenn die Erinnerung ausgeschaltet bleiben soll.

Nach vier Stunden ohne bestätigten Stand erscheint ein Hinweis unter
**Benachrichtigungen**. Bleibt er weitere 24 Stunden offen, folgt einmalig
ein Push. Schließen des Hinweises oder **Überspringen** im Push quittiert
diesen Fall. Bei einer neuen Störung beginnt die Frist erneut.
