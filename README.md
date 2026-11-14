# EifelLayer RF1

> **Privates Hobbyprojekt · Verwendung auf eigene Gefahr**  
> Der Quellcode ist öffentlich zugänglich. Für dieses Projekt wird kein Support angeboten. Wartung und weitere Updates sind freiwillig.  
> Die OCR kann Ziffern falsch erkennen. Für Abrechnungen und Meldungen an den Versorger gilt der direkt am Zähler abgelesene Stand.

Home-Assistant-App zur unabhängigen Bildkontrolle eines Pipersberg G4 RF1 mit lokaler OCR. Sie liest die fünf Vorkommastellen und zeigt erkennbare Nachkommastellen an.

[Änderungen je Version](rf1_ocr_test/CHANGELOG.md)

## Voraussetzungen

- Home Assistant mit Supervisor und App-Store auf ARM64 oder AMD64
- Ein eingerichteter SLFork-ESP, den Home Assistant im Heimnetz erreicht
- Ziffernrahmen in SLFork, die auf den Ziffernrollen liegen

## Installation

1. Öffne **Einstellungen → Apps → App installieren → ⋮ → Repositories** und füge `https://github.com/Thunder86/rf1-kontrollmessung` hinzu.
2. Installiere **RF1 Kontrollmessung** aus **EifelLayer RF1**.
3. Trage unter **Konfiguration → esp_url** die vollständige Adresse deines ESP ein, beispielsweise `http://esp-gaszaehler.local`. Speichere und starte die App.
4. Prüfe `sensor.rf1_pruefstatus` und `sensor.rf1_kontrollbild` in den Entwicklerwerkzeugen. Aktiviere auf der App-Infoseite **Automatische Updates**, wenn Home Assistant künftige Versionen selbst installieren soll.

Wenn du von der lokalen App wechselst, übernimm zuerst deine ESP-Adresse und sonstigen Einstellungen. Stoppe die lokale App vor dem Start der Repository-Version. Beide verwenden dieselben Sensoren. Die lokal gespeicherte Prüfhistorie gehört zur jeweiligen Installation.

## Prüfverhalten

Unter **Weboberfläche öffnen** zeigt RF1 den Countdown bis zur nächsten Prüfung, das Ergebnis und das aktuelle Bild neben dem letzten bestätigten Bild. **Jetzt prüfen** liest die vorhandene Aufnahme ein. Bei SLFork wird ein bereits ausgewerteter Messzyklus kein zweites Mal gezählt.

Mit `vergleich_nachkommastellen` stellst du ein, ob null bis drei Nachkommastellen zählen. Der Standard ist **0**. Die Anzeige enthält die gelesenen Nachkommastellen auch bei einem Vergleich der vollen Kubikmeter. Ein `?` steht für eine unklare oder fehlende Ziffer. Für den Vergleich werden Stellen abgeschnitten, ohne zu runden.

### ESPHome und Pulssensor

Für eine ESPHome-Kamera oder andere Home-Assistant-Kamera setze `kamera_entitaet` auf ihre `camera.*`-Entität. Richte dazu `ausschnitt` und `vorkomma_breite` manuell auf die Rollen ein. Mit leerem Kamerafeld läuft RF1 im SLFork-Modus.

Im Kameramodus kannst du mit `referenz_entitaet` einen kumulierten `sensor.*` in m³ angeben. Ein Pulssensor eignet sich, wenn er den absoluten Stand als Startstand plus Impulse × m³ pro Impuls liefert. Der Faktor richtet sich nach dem Zählertyp. Der Sensor muss den Stand mindestens alle fünf Minuten melden, auch wenn er gleich bleibt. Home Assistant liefert beim Kameraabruf keinen garantierten Aufnahmezeitstempel. Verwende deshalb eine Kamera, die ein aktuelles Bild liefert. Ohne Referenzsensor zeigt RF1 nur die OCR-Lesung an.

Beim Start prüft die App sofort, ob ein frisches, noch nicht ausgewertetes SLFork-Bild vorliegt.

Nach einem Treffer prüft die App nach einer Stunde erneut. Bei Abweichungen, unklarer OCR oder fehlenden aktuellen Daten prüft sie alle fünf Minuten. Nach vier Stunden ohne bestätigte Übereinstimmung zeigt `sensor.rf1_pruefstatus` den Zustand `review_due` an. Diesen Status kannst du in eigenen Automationen verwenden.

Die App liest sowohl normale als auch invertierte Bilder und übernimmt den Ausschnitt aus den SLFork-Ziffernrahmen. Falls die Rahmen fehlen, nutzt sie `ausschnitt` und `vorkomma_breite` aus der App-Konfiguration.

## Optionale Push-Erinnerung

Installiere die Home Assistant Companion App auf deinem Handy und verbinde sie mit Home Assistant. Suche unter **Entwicklerwerkzeuge → Aktionen** nach `notify.mobile_app_`. Trage den vollständigen Namen des Dienstes in der App-Konfiguration unter `push_dienst` ein, zum Beispiel `notify.mobile_app_mein_handy`. Speichere die Konfiguration und starte RF1 Kontrollmessung neu. Ein leeres Feld deaktiviert die Funktion.

Bei `review_due` erscheint ein Hinweis in der Seitenleiste unter **Benachrichtigungen**. Ist er nach 24 Stunden noch offen, sendet die App einmalig einen Push mit **Prüfstatus öffnen** und **Überspringen**. Home Assistant meldet keinen Lesestatus. Schließe den Hinweis, um ihn zu quittieren. **Überspringen** quittiert den aktuellen Fall ebenfalls. Sobald die Messung wieder bestätigt ist, räumt die App den Hinweis auf. Bei einer neuen Störung beginnt die Frist von vorn.

## Einstellungen bei Updates

Ändere Werte weiterhin auf der Konfigurationsseite von Home Assistant. Bei einem Update derselben App bleiben deine Einstellungen erhalten. Die App speichert zusätzlich eine versionierte Kopie in ihrem Datenverzeichnis. Neue Felder erhalten Standardwerte. Migrationen in `settings.py` können gezielt alte Einträge umbenennen oder entfernen. Das frühere `intervall_sekunden` bleibt für ältere Installationen im Supervisor-Schema zulässig und wird aus der wirksamen Konfiguration entfernt.
