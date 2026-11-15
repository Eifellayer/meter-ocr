# Bildprüfung und Anonymisierung

**Prüfdatum:** 15. November 2026
**Zweck:** Vor Veröffentlichung der bebilderten Bedienungsanleitung prüfen, ob Projektbilder Zählerdaten oder andere persönliche Kennungen zeigen.

## Bereits veröffentlichte Bilder

- Die erreichbare Git-Historie und alle dabei vorhandenen Branch-Referenzen wurden nach Bild- und PDF-Dateien durchsucht.
- Zusätzlich wurden die aktuellen GitHub-Bäume von `main`, `stable` und `beta` verglichen.
- In den älteren Projektständen war nur `assets/project-logo.png` als Bilddatei vorhanden. Das Logo zeigt keine Zähler, Zählerstände, Nummern, Barcodes oder QR-Codes.
- In den geprüften Ständen wurden keine früheren Fotos des Nutzerzählers gefunden.

## Neue Bilder für die Anleitung

- `images/housing-prototypes.jpg` zeigt die gedruckten Gehäuse. Das Foto enthält keine Zählerdaten oder erkennbaren Identifikationscodes.
- `images/camera-installation-anonymized.jpg` zeigt die montierte Kamera. Auf dem Zähler sind alle Beschriftungen, Serien- und Modellangaben sowie Codes abgedeckt. Sichtbar bleibt ausschließlich das mechanische Zählwerk mit dem Zählerstand.
- Beide Dateien wurden ohne EXIF-Metadaten gespeichert. Die Anleitung bettet nur diese bereinigten Versionen ein.

Die Historienprüfung deckt alle zum Prüfzeitpunkt erreichbaren Branches ab. Dateien in nicht erreichbaren oder außerhalb dieses Repositories gespeicherten Kopien sind davon nicht erfasst.

## Aktuelle Anleitung

Die Fotos der Gehäuse und der Zählermontage wurden aus der PDF und den aktuellen Anleitungsdateien entfernt. Bereits veröffentlichte Versionsstände behalten ihre Dateien.
