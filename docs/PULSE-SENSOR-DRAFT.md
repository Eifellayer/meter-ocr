# Impulssensor als zusätzliche Gegenprüfung

Entwurf für die Beta vor Version 0.5. Aufbau und Ablesung werden mit einem Hall-Sensor an ESPHome geprüft, sobald die Hardware verfügbar ist.

## Einrichtung

Die Kamera bleibt die Quelle für den sichtbaren Zählerstand. Im Einrichtungsassistenten und in den Einstellungen kommt ein optionaler Abschnitt **„Impulssensor zur Gegenprüfung“** hinzu. Unterstützt werden Hall-, Magnet- und andere Impulsgeber, die ihren fortlaufenden Impulszähler als Sensor in Home Assistant anbieten. Eine Angabe in Impulsen pro Minute reicht dafür nicht aus.

1. Den ESPHome-Sensor für die **Summe der Impulse** aus den Home-Assistant-Entitäten auswählen. Bei ESPHome kann etwa [Pulse Meter mit `total`](https://esphome.io/components/sensor/pulse_meter/#counting-total-pulses) diese Summe liefern.
2. Den auf dem Zähler oder im Datenblatt angegebenen **Verbrauch je Impuls** eintragen. Die Einrichtung zeigt die Einheit des Zählers an. Es gibt keinen angenommenen Standardfaktor.
3. Einen gut lesbaren Zählerstand mit dem gleichzeitig erfassten Impulsstand als Ausgangspunkt bestätigen. Der manuell bestätigte Stand lässt sich direkt am aktuellen Kamerabild ablesen.

## Automatische Prüfung

Die App rechnet die Impulse seit dem Ausgangspunkt in Verbrauch um und vergleicht den erwarteten Stand mit der Kameraablesung. Die zulässige Abweichung berücksichtigt die Impulsauflösung, das Ziffernformat und den zeitlichen Abstand zwischen Bild und Vergleichswert. Die Plausibilitätsgrenzen und die Einheiten des Zählers gelten weiter.

- **Stimmig:** Die Übersicht zeigt die zusätzliche Bestätigung durch den Impulssensor.
- **Abweichung:** Die App behält den letzten plausiblen Wert und zeigt einen kurzen Hinweis im bestehenden Prüfstatus. Eine dauerhafte Abweichung folgt den eingestellten Benachrichtigungsregeln.
- **Sensor nicht verfügbar oder Zähler zurückgesetzt:** Der Pulsvergleich pausiert, bis wieder ein vertrauenswürdiger Ausgangspunkt vorliegt. Die Kamera kann weiterhin nach den Regeln ihres Modus lesen. Ein Reset darf keinen Verbrauchssprung auslösen.

Der Impulsstand dient zunächst als zusätzliche Gegenprüfung. Der bestehende Verbrauchssensor für das Energie-Dashboard bleibt die gemeinsame Ausgabe. Nach einer Abweichung wird der Ausgangspunkt nur durch einen bewusst bestätigten Abgleich geändert.

## Test am ESP

- **Impulse zählen:** Mehrere ganze Impulse am realen Zähler mit dem ESPHome-Stand vergleichen. Prüfen, ob ein Magnet zu Doppelzählungen führt und wie sich eine Entprellung auswirkt.
- **Verbrauch abgleichen:** Den Faktor anhand der Zählerangabe prüfen und die Differenz mehrerer Kamerabilder mit den Impulsen vergleichen. Auch bei Stillstand, langsamer Bewegung und einem Rollenwechsel prüfen.
- **Neustart und Ausfall:** ESP und Home Assistant getrennt neu starten. Prüfen, wie der konkrete ESPHome-Zähler seinen Stand wiederherstellt und was bei fehlenden Daten, Rücksprung oder Wechsel der Entität angezeigt wird.
- **Abweichung und Erholung:** Eine falsche OCR-Ziffer, verspätete Sensordaten und einen verpassten Impuls simulieren. Danach die Rückkehr zum normalen Betrieb prüfen.

Die Beta wird zum Testen veröffentlicht, wenn der Sensor angeschlossen und ESPHome eingerichtet ist. Nach erfolgreichem Test und eventuellen Korrekturen folgt die Freigabe als **0.5 Stable**.
