# EifelLayer RF1

Home-Assistant-App zur unabhängigen Bildkontrolle eines Pipersberg G4 RF1 mit SLFork und lokaler OCR. Sie vergleicht die fünf Vorkommastellen mit dem SLFork-Wert.

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

Nach einem Treffer prüft die App nach einer Stunde erneut. Bei Abweichungen, unklarer OCR oder fehlenden aktuellen Daten prüft sie alle fünf Minuten. Nach vier Stunden ohne bestätigte Übereinstimmung zeigt `sensor.rf1_pruefstatus` den Zustand `review_due` an. Diesen Status kannst du in eigenen Automationen verwenden.

Die App liest sowohl normale als auch invertierte Bilder und übernimmt den Ausschnitt aus den SLFork-Ziffernrahmen. Falls die Rahmen fehlen, nutzt sie `ausschnitt` und `vorkomma_breite` aus der App-Konfiguration.
