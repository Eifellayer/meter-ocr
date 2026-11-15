# Entwicklung und Freigabe

Die reguläre App liegt auf `stable`. Änderungen werden zuerst auf `beta` geprüft. Der Standardzweig `main` stellt beide Einträge über ein gemeinsames Home-Assistant-Repository bereit.

| Priorität | Abnahme |
| --- | --- |
| P0 | Beide App-Einträge sind installierbar. Sensoren, Bilder und Benachrichtigungen der Testausgabe sind getrennt. |
| P0 | SLFork-Ersatzwerte und unplausible Lesungen verändern den bestätigten Verbrauch nicht. Automatik und manueller Test haben getrennte Ergebnisse. |
| P1 | Sprache, Einrichtung, Fortschritt und Ausschnittübernahme funktionieren im Ingress auf Desktop und Smartphone. |
| P1 | Die OCR-Stichprobe umfasst verschiedene Zählwerke, Lichtverhältnisse und Kamerawinkel. Ergebnisse stehen im [Foto-Testbericht](METER-PHOTO-TESTS.md). |
| P2 | Die deutsche und englische Dokumentation beschreibt Setup, Optionen und die Grenzen der Erkennung. |

## Beta bereitstellen

1. Änderungen auf `beta` prüfen und GitHub Actions ausführen.
2. Den geprüften Commit lokal abrufen und im Katalogzweig `bash scripts/package-beta.sh origin/beta` ausführen. Der Ordner `meter_ocr_beta` enthält den geprüften App-Quellstand. Die genaue Revision steht in `meter_ocr_beta/SOURCE`.
3. Den Katalog als Pull Request auf `main` prüfen. GitHub Actions vergleichen die Beta mit dem Quellstand und bauen beide Apps für AMD64 und ARM64.
4. Akzeptierte Änderungen über `stable` in den regulären App-Eintrag übernehmen und die Version für den Store aktualisieren.

Vor einer 1.0-Freigabe gehören auch eine Neuinstallation in einem echten Supervisor, eine Prüfung mit aktuellen SLFork- und ESPHome-Bildern, Ingress in der Companion App und die bestätigte Zustellung von Hinweisen zur Abnahme.
