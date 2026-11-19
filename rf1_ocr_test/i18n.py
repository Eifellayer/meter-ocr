"""German and English text for the RF1 ingress panel and OCR diagnostics.

The OCR and Home Assistant entity IDs stay language-neutral and unchanged.
The language only affects text shown in the ingress interface.
"""

import re

from checks import (FALLBACK_NOTICE, LAST_DIGIT_NOTICE, LAST_DIGIT_PASS,
                    SEVENTH_DIGIT_PASS, SEVENTH_DIGIT_WAIT_NOTICE, STANDALONE_PENDING_NOTICE,
                    STANDALONE_REJECTED_NOTICE, STANDALONE_VERIFIED_NOTICE, uncertain_positions)
from layout import MANUAL_ROW_UNCLEAR, PARTLY_UNCLEAR, RAW_ROW_UNCLEAR


EN_UI = {
    "Pause nach drei Fehlprüfungen (Minuten)": "Pause after three failed checks (minutes)",
    "Danach prüft die App wieder normal. Bleibt nur die letzte Rolle unklar, pausiert sie nicht.":
        "Afterwards the app checks normally again. If only the last roller is unclear, it does not pause.",
    "Verbrauch auch in kWh (optional)": "Consumption in kWh too (optional)",
    "Verbrauch auch in kWh": "Consumption in kWh too",
    "Zustandszahl": "Gas state factor (Z)",
    "Brennwert (kWh/m³)": "Calorific value (kWh/m³)",
    "z. B. 0,9636": "e.g. 0.9636",
    "z. B. 11,25": "e.g. 11.25",
    "Die Werte stehen auf der Gasabrechnung oder beim Netzbetreiber. Entweder Zustandszahl und Brennwert eintragen oder nur den fertigen Umrechnungsfaktor (er hat Vorrang). Dann gibt es zusätzlich":
        "The values are on your gas bill or available from the grid operator. Enter either the gas state factor and calorific value or just the finished conversion factor (it takes precedence). There is then also",
    "oder Umrechnungsfaktor": "or conversion factor",
    "z. B. 10,84": "e.g. 10.84",
    "für das Energie-Dashboard. Leer lassen schaltet es ab.": "for the Energy dashboard. Leave empty to switch it off.",
    "Automatische Prüfung angefordert.": "Automatic check requested.",
    "Automatische Prüfung jetzt starten": "Run automatic check now",
    "Eine Nachkommastelle blieb wiederholt unklar. Du kannst den Vergleich auf weniger Stellen begrenzen.":
        "A decimal digit was repeatedly unclear. You can compare fewer digits.",
    "Zwei Leseprofile stimmen überein – Kandidat übernommen":
        "Two profiles agree and the candidate passes the OCR check",
    "Zwei Leseprofile stimmen überein, Vergleich steht noch aus": "Two profiles agree, comparison unresolved",
    "Die OCR-Versuche auf diesem Bild reichen nicht aus. Ein frisches Kamerabild folgt gleich.": "The OCR attempts were inconclusive. A fresh camera image will follow shortly.",
    "Beste Kandidaten der Rahmen-Nachprüfung": "Best crop recheck candidates",
    "Zwei Leseprofile stimmen überein": "Two OCR profiles agree",
    "Leseprofile liefern unterschiedliche Ziffern": "Profiles disagree",
    "Ziffer blieb offen": "Digit remained unclear",
    "Ziffernposition ": "Digit position ",
    "Rahmen im Ausschnitt (px) ": "Crop coordinates (px) ",
    "Die fehlende Ziffer wurde im verschobenen Rahmen direkt gelesen.": "The missing digit was read directly in the shifted box.",
    "Ziffern aus übereinstimmenden OCR-Versuchen zusammengesetzt.": "Digits were combined from agreeing OCR attempts.",
    "Unveränderliche führende Stellen aus dem zuletzt bestätigten Stand ergänzt.":
        "Leading digits that cannot have changed were filled in from the last confirmed reading.",
    "Experimentell · Mehrere Zähler": "Experimental · Multiple meters",
    "Zusätzliche Home-Assistant-Sensoren beobachten. Diese Funktion ist experimentell. Praxistests stehen noch aus.": "Monitor additional Home Assistant sensors. This feature is experimental and has not been field-tested.",
    "Unterstützt fortlaufend steigende Zähler in m³ oder kWh. Pro Zeile eine Entität und optional das Prüfintervall in Minuten, z. B. ": "Supports cumulative meters in m³ or kWh. Enter one entity per line with an optional check interval in minutes, for example ",
    "Zusätzliche Zähler": "Additional meters",
    "Zähler speichern": "Save meters",
    "Zähler gespeichert.": "Meters saved.",
    "Prüfe die Sensor-IDs und Prüfintervalle.": "Check the sensor IDs and intervals.",
    "Verbrauch je Stunde, letzte 24 Stunden": "Hourly usage, last 24 hours",
    "Verbrauch je Stunde": "Hourly usage",
    "Zählerstand lokal aus dem Kamerabild": "Meter reading, locally from the camera image",
    'class="meter-hero-label">Zählerstand<': 'class="meter-hero-label">Meter reading<',
    'aria-label="Zählerstand {ocr}"': 'aria-label="Meter reading {ocr}"',
    "<span>vor 24 h</span><span>jetzt</span>": "<span>24 h ago</span><span>now</span>",
    "Verlauf nach Tag": "Daily history",
    "Letzte Ablesung ": "Last reading ",
    "Wartet auf Daten": "Waiting for data",
    "Wartet auf neuen Sensorwert": "Waiting for a new sensor value",
    "Neuer Ausgangswert gespeichert": "New baseline saved",
    "Möglicher Zählerrücksprung": "Possible meter reset",
    "Kein gültiger Sensorwert": "No valid sensor value",
    "ok: 'Aktuell'": "ok: 'Up to date'",
    "Demo ohne Kamera ausprobieren": "Try the demo without a camera",
    "Zähler-Demo": "Meter demo",
    "Probiere die Erkennung mit einem künstlichen Gaszählerbild. Deine echte Einrichtung und Verbrauchsdaten bleiben getrennt.": "Try OCR on a generated gas meter image. The demo keeps your live settings and consumption data separate.",
    "Schräges Bild prüfen": "Read tilted image",
    "Spiegelung ausprobieren": "Try a reflection",
    "Schräges künstliches Zählerbild": "Generated tilted meter image",
    "Gerader Ausschnitt mit Ziffernrahmen": "Aligned crop with digit boxes",
    "Demo-Bild wird geprüft …": "Reading the demo image …",
    "Abgelesen ": "Read ",
    " m³ · Drehung ": " m³ · Rotation ",
    "Alle Ziffern erkannt.": "All digits read.",
    "Mindestens eine Ziffer blieb offen.": "At least one digit remained unclear.",
    "Aus einem Beispiel-Referenzwert geschätzt: ": "Estimated from the demo reference: ",
    "Die Demo konnte nicht geladen werden. Versuche es noch einmal.": "Could not load the demo. Try again.",
    "Automatik-Nachprüfung: Die App prüft die fehlende Ziffer mit leicht verschobenem Rahmen.":
        "Automatic recheck: reading the missing digit with a slightly shifted box.",
    "Frische Aufnahme für den erwarteten Rollenwechsel eingeplant.":
        "A fresh image is scheduled around the expected roller change.",
    "Roadmap auf GitHub": "Roadmap on GitHub",
    "Automatik wartet auf die Einrichtung. Du kannst sie automatisch oder manuell abschließen.": "Automatic checks are waiting for setup. You can finish setup automatically or manually.",
    "Automatik wartet auf Einrichtung": "Automatic checks are waiting for setup",
    "Selbsteinrichtung wird vorbereitet …": "Preparing automatic setup …",
    "Einrichtung fortsetzen": "Continue setup",
    "Aktueller Schritt": "Current step",
    "Nächster Schritt": "Next step",
    "Kamerabild laden": "Load the camera image",
    "Ziffernreihe finden": "Find the digit row",
    "Rahmen und Drehung prüfen": "Check crop and rotation",
    "Rahmen bestätigen": "Confirm the crop",
    "Letzte Rolle prüfen": "Check the last roller",
    "Ergebnis gegenprüfen": "Verify the result",
    "Ergebnis anzeigen": "Show the result",
    "Rahmen speichern und Automatik starten": "Save the crop and start automatic checks",
    "Geräte suchen": "Search devices",
    "Es wurden keine Geräte gefunden": "No devices found",
    "z. B. Gaszähler": "e.g. gas meter",
    "1. Lade ein Bild deiner Kamera oder wähle ein Testbild derselben Kamera.": "1. Load a camera image or choose a test image from the same camera.",
    "Kamerabild für Rahmen laden": "Load camera image for the crop",
    "Eigenes Bild für den Rahmen": "Use your own image for the crop",
    "2. Ziehe einen Rahmen um die gesamte Ziffernreihe. Lass etwas Rand und spare die Seriennummer aus.": "2. Draw a box around all the meter digits. Leave a small margin and exclude the serial number.",
    "Kamerabild zum Zeichnen des Ziffernrahmens": "Camera image for drawing the digit crop",
    "3. Bilddrehung bei Bedarf (°)": "3. Rotate the image if needed (°)",
    "Koordinaten und Breite bearbeiten": "Edit coordinates and width",
    "4. Prüfe die Vorschau und bestätige den Rahmen.": "4. Check the preview and confirm the crop.",
    "Dieser Rahmen umfasst die Ziffernreihe": "This crop covers the digit row",
    "Kein Bild verfügbar. Prüfe die Bildquelle oder wähle ein Testbild.": "No image available. Check the source or choose a test image.",
    "Ziffernrahmen für Spiegelungen suchen": "Find digit boxes for reflections",
    "Gelbe Rahmen sind möglicherweise gespiegelt. Du kannst bis zu zwei Stellen markieren und die Rahmen ziehen.": "Yellow boxes may be affected by reflections. Mark up to two positions and drag the boxes to adjust them.",
    "Ziffernfeld mit markierten Spiegelungen": "Meter digits with marked reflections",
    "Ziffernrahmen werden gesucht …": "Finding digit boxes …",
    "Kein Ziffernfeld gefunden. Du kannst die Einrichtung direkt fortsetzen.": "No digit row found. You can continue setup.",
    "Ausschnitt mit markierter Spiegelung vorläufig gespeichert. Die verdeckten Ziffern bleiben offen.": "Crop with marked reflections saved provisionally. The obscured digits remain open.",
    "Die sichtbaren Ziffern stützen den markierten Rahmen. Die verdeckten Stellen bleiben offen.": "The visible digits support the marked crop. The obscured digits remain open.",
    "Markierter Rahmen mit sichtbaren Ziffern geprüft. Verdeckte Stellen bleiben offen.": "Marked crop checked using the visible digits. Obscured digits remain open.",
    "Ziffernzeile gefunden · ": "Digit row found · ",
    "Schwelle ": "Threshold ",
    " Ohne Vergleichswert braucht die App einen plausiblen Anstieg oder einen Startwert.": " Without a reference, the app needs a plausible increase or a starting reading.",
    "Die Automatik läuft. In den nächsten 20 Minuten optimiert die App im Hintergrund noch Rahmen und Winkel.":
        "Automatic checks are running. For the next 20 minutes the app keeps optimising frames and angle in the background.",
    "Werkzeuge zur Erkennung": "Meter reading tools",
    "Werkzeuge": "Tools",
    "Prüfdetails": "Check details",
    ">Verbrauch</h2>": ">Consumption</h2>",
    "Diese Stunde": "This hour",
    ">Heute</dt>": ">Today</dt>",
    "Die Statistik füllt sich mit bestätigten Ablesungen.": "The history grows as readings are confirmed.",
    "Verlauf nach Stunde und Tag": "Hourly and daily history",
    "Liegt eine Stunden- oder Tagesgrenze zwischen zwei Ablesungen, verteilt die App den Verbrauch anteilig. Zeiträume ohne Ablesung bleiben leer.":
        "Usage at period boundaries is estimated between two readings. Gaps are left blank.",
    "Letzte 24 Stunden": "Last 24 hours",
    "Letzte 7 Tage": "Last 7 days",
    " · teilweise": " · partial",
    " + ' von ' + sample.activity_total": " + ' of ' + sample.activity_total",
    "Die Ziffernerkennung beginnt, sobald das Bild bereitsteht.": "Digit recognition starts when the image is ready.",
    "Zuletzt gelesen (noch unbestätigt): ": "Latest reading (unconfirmed): ",
    "Bisher keine Ziffer gelesen.": "No digits read yet.",
    "Die App sucht einen passenden Rahmen und Winkel. Nach drei bestätigten Aufnahmen übernimmt die Automatik die Gegenprüfung. Das dauert meist rund fünf Minuten, höchstens 20 Minuten.": "The app looks for a suitable crop and angle. After three confirmed images, the regular reader takes over. The target is five minutes and the limit is 20 minutes.",
    "Startet nach dem Speichern. Nach drei bestätigten Aufnahmen übernimmt die Automatik die Gegenprüfung.": "Starts after saving. After three confirmed images, the regular reader takes over.",
    "Selbsteinrichtung nach 20 Minuten beendet, ohne dass ein Rahmen sicher bestätigt wurde.": "Automatic setup ended after 20 minutes without confirming a reliable crop.",
    "Nachprüfung: Dieselben Ziffern waren wiederholt unklar.": "Rechecking because the same digits were repeatedly unclear.",
    ">Kandidaten</summary>": ">Candidates</summary>",
    "button.textContent = 'Stelle '": "button.textContent = 'Position '",

    "Letzte Rolle auf diesem Bild gelesen. Sie ist noch nicht unabhängig bestätigt.":
        "Last wheel read on this image. Independent confirmation is still pending.",
    "Die letzte Rolle dreht sich noch. Die App wartet auf eine eindeutige Ziffer.":
        "The last wheel is turning. Waiting for a clear digit.",
    "Ziffernrahmen korrigieren": "Adjust digit boxes",
    "Wähle eine Ziffer. Ziehe ihren Rahmen oder passe ihn mit den Tasten darunter an.": "Select a digit. Drag its box or use the buttons below.",
    "Zählerbild mit Ziffernrahmen": "Meter image with digit boxes",
    "Position auf der Anzeige": "Position on the display",
    "Rahmen verschieben": "Move digit box",
    "Nach links": "Left",
    "Nach oben": "Up",
    "Nach unten": "Down",
    "Nach rechts": "Right",
    "Kleiner": "Smaller",
    "Größer": "Larger",
    "Diese Ziffer suchen": "Find this digit",
    "Diesen Rahmen zurücksetzen": "Reset this box",
    "Ziffernrahmen speichern": "Save digit boxes",
    "Ziffernrahmen gespeichert.": "Digit boxes saved.",
    "Kein passendes Kamerabild vorhanden. Es kommt mit der nächsten regulären Prüfung.": "No matching camera image is available. Wait for a regular check.",
    "Die ausgewählte Ziffer wird gesucht …": "Searching for the selected digit …",
    "Bild oder Ausschnitt hat sich geändert. Öffne den Editor erneut.": "The image or crop has changed. Reopen the editor.",
    "Vorgeschlagener Rahmen. Gelesene Ziffer: ": "Suggested box. Digit read: ",
    "Kein sicherer Vorschlag. Du kannst den Rahmen von Hand verschieben.": "No reliable suggestion. You can move the box manually.",
    "Die Änderung konnte nicht verarbeitet werden.": "Could not apply the change.",
    "Vor dem Komma: ": "Before the decimal: ",
    "Nach dem Komma: ": "After the decimal: ",
    "Erkennungsbild": "Recognition image",
    "Letztes Testbild": "Latest test image",
    "Noch kein Testbild verfügbar.": "No test image available yet.",
    "Eindeutig ergänzter Zwischenstand": "Reconstructed intermediate reading",
    "Berechnete Ziffer": "Calculated digit",
    "Für eine unlesbare Ziffer gibt es einen eindeutigen Vorschlag. Wähle die Ziffer aus, um den Zwischenstand zu übernehmen.":
        "There is one plausible value for an unreadable digit. Select it to accept the intermediate reading.",
    "Ziffer auswählen …": "Choose a digit …",
    "Zwischenstand übernehmen": "Accept the intermediate reading",
    "Dieselbe Ziffer ist wiederholt unlesbar. Bei Spiegelungen kannst du sie aus der vorherigen und der nächsten sicheren Ablesung ergänzen lassen.":
        "The same digit has been unreadable repeatedly. For reflections, the previous and next confirmed readings can help reconstruct it.",
    "Zur Einstellung": "Open settings",
    "Vorschlag dauerhaft ausblenden": "Hide this suggestion permanently",
    "ⓘ Spiegelungen und verdeckte Ziffern": "ⓘ Reflections and obscured digits",
    "Einzelne verdeckte Ziffer ergänzen": "Reconstruct one obscured digit",
    "Die App ergänzt eine Ziffer nur, wenn zwischen zwei sicheren Ständen genau ein Wert plausibel ist. Die berechnete Ziffer bleibt gelb. Ein manuell eingetragener Startwert mit Ablesezeit kann als erster Vergleichswert dienen.":
        "The app fills in a digit only when exactly one value is plausible between two confirmed readings. The calculated digit is highlighted in yellow. A manually entered starting value with its reading time can serve as the first reference.",
    "Vorschlag bei wiederholt unlesbarer Ziffer ausblenden": "Hide the suggestion for a repeatedly unreadable digit",
    RAW_ROW_UNCLEAR: "Could not find a clear digit row. Set the crop in the manual test.",
    MANUAL_ROW_UNCLEAR: "The digits are hard to read. Check the image rotation, camera angle, focus and lighting.",
    PARTLY_UNCLEAR: "Some digits could not be read clearly. The app keeps trying automatically.",
    "Selbstreparatur bei wiederholten Fehlmessungen": "Self-repair after repeated failed readings",
    "Die App sucht frühestens nach zwei Stunden anhaltender Erkennungsprobleme einen besseren Rahmen. Probleme nur an der letzten Rolle zählen dabei nicht mit. Der bisherige Rahmen gilt bis zur erfolgreichen Gegenprobe.":
        "The app looks for a better crop after at least two hours of persistent recognition problems. Problems with the last digit alone do not count. The current crop stays in use until a replacement passes verification.",
    "Die App beobachtet, ob die Erkennungsprobleme anhalten.": "The app is checking whether the recognition problems persist.",
    "Die Ziffern werden seit mindestens zwei Stunden nicht sicher erkannt. Prüfe Bildausschnitt, Fokus und Beleuchtung.": "Digits have not been read reliably for at least two hours. Check the crop, focus and lighting.",
    "Gesicherten Ausschnitt wiederherstellen": "Restore the backed-up crop",
    "Gesicherter Ausschnitt wiederhergestellt.": "The backed-up crop has been restored.",
    "Automatische Neukalibrierung ist ausgeschaltet.": "Automatic recalibration is disabled.",
    "Automatische Nachjustierung · ": "Automatic realignment · ",
    "Bei mehrfach unlesbaren Aufnahmen sucht die App auch selbst nach einem besseren Rahmen. Erst nach erfolgreichen Gegenproben übernimmt sie eine Änderung.":
        "After repeated unreadable images, the app also looks for a better crop. It applies a change only after successful cross-checks.",
    " Die Rahmen wurden aus sichtbaren Ziffern und ihren Abständen abgeleitet.":
        " The digit boxes were inferred from visible digits and their spacing.",
    " Die Position der Ziffernrahmen ist angenähert.": " The positions of the digit boxes are approximate.",
    "Bilder geprüft: ": "Images checked: ",
    " · Rahmen getestet: ": " · Crops tested: ",
    " · Restzeit: ": " · Time remaining: ",
    " · Rechenzeit übrig: ": " · Processing time left: ",
    " · Zeit für die Einrichtung: ": " · Setup time left: ",
    "Mehrere Ziffernfelder gefunden.": "Multiple digit rows found.",
    "Ziffernfelder ansehen": "Show digit rows",
    "Zählerstand kurz selbst ablesen (optional)": "Enter the current meter reading (optional)",
    "Der Stand hilft der App beim Einrichten. Zum Überspringen leer lassen und auf „Weiter“ klicken.": "The reading helps the app during setup. To skip it, leave the field empty and select Next.",
    "Ablesezeit ändern": "Change reading time",
    "Kamerabild zum Ablesen laden": "Load camera image for reading",
    "Zählerbild zum Ablesen": "Meter image for reading",
    "Kamerabild wird geladen …": "Loading camera image …",
    "Kein Kamerabild verfügbar. Prüfe die Bildquelle oder lies direkt am Zähler ab.": "No camera image available. Check the source or read the meter directly.",
    "Drehung prüfen: ": "Checking rotation: ",
    "Drehung wird geprüft. Der Winkel steht am Vorschaubild.": "Checking rotation. See the preview for its angle.",
    "Nächster Rahmen wird geprüft …": "Checking the next crop …",
    "Ziffernfeld manuell markieren": "Mark digit row manually",
    "Einzelziffernsuche. Offene Stellen von links: ": "Individual digit search. Uncertain positions from the left: ",
    "Ziffernfeld lesbar. Die App wartet auf einen höheren Zählerstand oder einen abgelesenen Startwert.": "The digit row is readable. The app is waiting for a higher reading or a starting reading you enter.",
    "Ziffernfeld bestätigt. Die App prüft mit dem nächsten neuen Bild weiter.": "Digit row confirmed on this image. The app will check again with the next new image.",
    "Ziffernfeld nicht gefunden. Markiere den ungefähren Bereich im Kamerabild.": "Digit row not found. Mark the digit row in the camera image.",
    "Kein gültiger Vergleichswert für dieses Bild. Die App wartet auf eine neue Messung.": "No valid reference for this image. The app is waiting for a new measurement.",
    "Der gelesene Bereich passt nicht zum Vergleichswert. Prüfe den Vergleichswert und markiere das Ziffernfeld.": "The area read does not match the reference. Check the reference and mark the digit row.",
    "Ziffernfeld auswählen ": "Select digit row ",
    "Die gelesene Ziffernreihe ist gegenüber dem Vergleichswert vermutlich um eine Stelle verschoben.": "The digit row appears shifted by one position relative to the reference.",
    "Kein neues Kamerabild erhalten. Prüfe die Bildquelle.": "No new camera image received. Check the image source.",
    "Grobsuche: Die App sucht die Ziffernreihe …": "Coarse calibration: Looking for the digit row …",
    "Feinkalibrierung: Rahmen und Drehung werden am vorhandenen Bild geprüft …": "Fine calibration: Testing digit boxes and rotation on the current image …",
    "Noch kein Ziffernbereich gefunden. Die App prüft gleich das nächste Bild …": "No digit region found yet. Waiting for a new image …",
    "In diesem Bild wurde kein Ziffernbereich gefunden.": "No digit region was found in this image.",
    "Der Ausschnitt ließ sich nicht auswerten.": "This crop could not be processed.",
    "Mindestens eine benötigte Ziffer blieb unklar.": "At least one required digit remained unclear.",
    "Die OCR-Versuche lieferten unterschiedliche Ziffern.": "The OCR attempts read different digits.",
    "Kein gültiger Vergleichswert zu diesem Bild.": "No valid reference reading for this image.",
    "Der gelesene Stand weicht vom Vergleichswert ab.": "The OCR reading differs from the reference.",
    "Der Stand passt zeitlich nicht zur letzten sicheren Ablesung.": "The reading is implausible given the last confirmed reading and elapsed time.",
    "Der Rahmen ist lesbar. Die App wartet auf einen plausiblen Zähleranstieg.": "The crop is readable. Waiting for a plausible meter increase.",
    "Ziffern bis zur zweiten Nachkommastelle gelesen. Der Rahmen gilt vorläufig, weil noch kein Vergleichswert vorliegt.":
        "Digits read through the second decimal. The crop counts provisionally. A reference reading is missing.",
    "Bis zur zweiten Nachkommastelle bestätigt. Die dritte Nachkommastelle ist noch offen.":
        "Confirmed through the second decimal. The third decimal remains open.",
    "Dieser Rahmen wurde auf dem aktuellen Bild bestätigt.": "This crop was confirmed on the current image.",
    "Die abschließende Gegenprobe war erfolgreich.": "The final cross-check succeeded.",
    "Suchbereich im Kamerabild eingrenzen": "Limit the search area on the camera image",
    "Ziehe einen Rahmen um das Ziffernfeld. Lass etwas Rand und spare die Seriennummer aus.":
        "Draw around the digits. Leave a small margin and keep the serial number outside the box.",
    "Kamerabild zur Auswahl des Suchbereichs": "Camera image for selecting the search area",
    "Kamerabild fehlt. Starte eine Prüfung oder die Selbsteinrichtung, um ein Bild zu laden.":
        "No camera image available. Run a check or start automatic setup to load one.",
    "Im markierten Bereich suchen": "Search in the marked area",
    "Markierung löschen": "Clear selection",
    "Bilder der Selbsteinrichtung": "Automatic setup images",
    "Kamerabild der Selbsteinrichtung": "Camera image used for automatic setup",
    "Aktuelles Kamerabild": "Current camera image",
    "Geprüfter Bildausschnitt mit einzelnen Ziffernrahmen": "Tested crop with individual digit boxes",
    "Geprüfter Ausschnitt": "Tested crop",
    "Die App sucht in diesem Bild nach der Ziffernreihe.": "The app is looking for the digit row in this image.",
    "OCR gelesen: ": "OCR read: ",
    "Ziffern werden gelesen …": "Reading the digits …",
    "Grün: gelesen. Gelb: OCR-Versuche weichen ab. Rot: unklar.":
        "Green: read. Yellow: OCR attempts disagree. Red: unclear.",
    "Die blauen Rahmen zeigen, welche Stellen die App gerade prüft.":
        "The blue boxes show which digit positions are being checked.",
    "Selbsteinrichtung": "Automatic setup",
    "ⓘ Automatik im Hintergrund verbessern": "ⓘ Improve automatic checks in the background",
    "Ziffernrahmen langfristig feinjustieren": "Fine-tune digit boxes over time",
    "Prüfintervall bei erwarteten Rollenwechseln verkürzen (SLFork)":
        "Check sooner when a digit is expected to roll over (SLFork)",
    "Vorläufig ergänzt": "Provisionally reconstructed",
    "Gelb markierte Ziffern sind berechnet. Der Wert dient der Orientierung.":
        "Yellow digits are calculated. The reading is for guidance.",
    "Verdeckte Ziffern ergänzen": "Reconstruct obscured digits",
    "Die App kann je eine verdeckte Stelle vor und nach dem Komma ergänzen, wenn nur ein Ergebnis zum bisherigen Stand und zum maximalen Durchfluss passt. Berechnete Ziffern bleiben gelb. Ein datierter Startwert kann als erster Vergleichswert dienen.":
        "The app can reconstruct one whole digit and one decimal digit when only one reading fits the preceding reading and maximum flow. Calculated digits stay yellow. A dated starting reading can serve as the first reference.",
    "Vorschau mit Bilddrehung": "Preview with rotation",
    "Rahmen einzeln ziehen oder an der unteren Ecke vergrößern. Mit den Pfeiltasten verschieben, mit Umschalt und Pfeiltaste skalieren.":
        "Drag each box or resize it using the bottom corner. Use the arrow keys to move it, or hold Shift and use the arrow keys to resize.",
    "Einzelrahmen zurücksetzen": "Reset digit boxes",
    "Ziffernrahmen ": "Digit box ",
    "Bei AI on the Edge / SLFork liegen reguläre Prüfungen mindestens fünf Minuten auseinander.":
        "Regular AI on the Edge / SLFork checks are at least five minutes apart.",
    "Trage den selbst abgelesenen Stand und die Ablesezeit ein. Die App nutzt ihn als Startwert, solange noch keine sichere automatische Ablesung vorliegt.":
        "Enter the meter reading you observed and when you read it. The app uses it as a starting reading until it has a reliable automatic reading.",
    "Fallback-Zählerstand": "Fallback reading",
    "Fallback-Wert speichern": "Save fallback reading",
    "Fallback-Wert gespeichert.": "Fallback reading saved.",
    "Gefundenen Rahmen im Test prüfen": "Review the suggested crop in a manual test",
    " · Rahmenversuche: ": " · Crop attempts: ",
    "Die App wartet auf den nächsten Messzyklus des ESP …": "Waiting for a new ESP measurement cycle …",
    "Verstrichene Zeit der Selbsteinrichtung": "Elapsed automatic setup time",
    "Selbsteinrichtung startet, sobald die laufende Prüfung beendet ist …":
        "Automatic setup will start once the current check finishes …",
    "Kamerabild wird abgerufen …": "Fetching a camera image …",
    "Die App sucht die Ziffernreihe …": "Looking for the digit row …",
    "'Rahmen ' + status.variant + ' wird mit Drehung ' + status.rotation + '° geprüft …'":
        "'Checking frame ' + status.variant + ' at a rotation of ' + status.rotation + '° …'",
    "Selbsteinrichtung für Ausschnitt und Drehung": "Automatic setup for crop and rotation",
    "Die App tastet sich mit unterschiedlichen Bildern an einen passenden Rahmen und Winkel heran. Nach drei bestätigten Ablesungen prüft sie den gefundenen Rahmen mit einem weiteren Bild und übernimmt ihn dann. Nach 15 Minuten endet der Versuch automatisch.":
        "The app searches for a suitable crop and rotation using different images. After three confirmed readings, it checks the result on one more image before saving. The search automatically ends after 15 minutes.",
    "Ohne externen Vergleichswert hilft ein von Hand abgelesener Startwert. Ohne Startwert wartet die App zusätzlich auf einen plausiblen Zähleranstieg.":
        "A manually entered starting reading helps if there is no external reference. Without either, the app also waits for a plausible increase.",
    "Geprüfte Bilder der Selbsteinrichtung": "Images checked during automatic setup",
    "Startet nach dem Speichern und endet spätestens nach 15 Minuten. Die App übernimmt den Rahmen nach drei Bestätigungen und einer abschließenden Gegenprüfung.":
        "Starts after saving and ends within 15 minutes. The app saves the crop after three confirmations and a final check.",
    "Höchstens so viele unterschiedliche Bilder": "Maximum number of distinct images",
    "Selbsteinrichtung starten": "Start automatic setup",
    "Selbsteinrichtung stoppen": "Stop automatic setup",
    "Nächstes Kamerabild wird angefordert …": "Requesting the next camera image …",
    "Ausschnitt und Drehung werden geprüft …": "Checking crop and rotation …",
    "Selbsteinrichtung prüft Bildausschnitt und Drehung.": "Automatic setup is checking the crop and rotation.",
    "Erfolgreich eingerichtet. Ausschnitt und Drehung sind übernommen.": "Setup successful. Crop and rotation saved.",
    "Rahmen gefunden. Die App wartet auf ein frisches Bild zur Gegenprüfung …": "Crop found. Waiting for a fresh image to cross-check …",
    "Gefundenen Rahmen mit der normalen Prüfung gegenprüfen …": "Cross-checking the crop with the regular OCR check …",
    "Selbsteinrichtung fehlgeschlagen. Prüfe Bildausschnitt, Kamerawinkel und Beleuchtung.":
        "Automatic setup failed. Check the crop, camera angle and lighting.",
    "Nachjustierung nach vier Minuten beendet. Der bisherige Rahmen bleibt gültig.":
        "Automatic realignment ended after four minutes. The previous crop stays in use.",
    "Selbsteinrichtung nach 15 Minuten beendet. Keine Einstellung sicher bestätigt.":
        "Automatic setup ended after 15 minutes without finding a reliable crop and rotation.",
    "Selbsteinrichtung gestoppt.": "Automatic setup stopped.",
    "Ausschnitt und Drehung konnten nicht gespeichert werden.": "Could not save the crop and rotation.",
    "Bilder: ": "Images: ",
    " · Bestätigungen: ": " · Confirmations: ",
    " · Noch ": " · Remaining ",
    "Ausschnitt zurücksetzen": "Reset crop",
    "Ausschnitt zurückgesetzt. Die Automatik sucht die Ziffernreihe wieder selbst.":
        "Crop reset. Automatic checks will locate the digit row again.",
    "Ziehe mit Maus oder Finger einen Rahmen um die gesamte Ziffernreihe.":
        "Draw a frame around the full row of digits with a mouse or finger.",
    "Originalbild zum Einstellen des Ausschnitts": "Original image for setting the crop",
    "Kamerabild wird geladen …": "Loading camera image …",
    "Kein Kamerabild verfügbar. Wähle ein eigenes Bild oder starte einen Test.":
        "No camera image available. Choose your own image or run a test.",
    "Kein Kamerabild verfügbar. Prüfe die Bildquelle oder warte auf die nächste automatische Prüfung.":
        "No camera image available. Check the image source or wait for the next automatic check.",
    "Ausschnitt, Drehung und Einstellungen speichern": "Save crop, rotation and settings",
    "Ausschnitt und Drehung speichern": "Save crop and rotation",
    "Ausschnitt und Drehung für manuelle Tests gespeichert.": "Crop and rotation saved for manual tests.",
    "Einstellungen speichern": "Save settings",
    "Stand aus AI on the Edge oder aus dem gewählten Home-Assistant-Sensor": "Reading from AI on the Edge or the selected Home Assistant sensor",
    "Stand aus der ersten Aufnahme oder aus einer externen Quelle": "Reading from the first image or an external source",
    "Zweite Aufnahme steht aus": "Waiting for the second image",
    "Zählerstand gegengeprüft": "Meter reading cross-checked",
    "Aufnahmen stimmen nicht plausibel überein": "The two images suggest an implausible change",
    STANDALONE_PENDING_NOTICE: "First image read. Waiting for a second snapshot to cross-check the reading.",
    STANDALONE_VERIFIED_NOTICE: "Meter reading cross-checked against a second snapshot.",
    STANDALONE_REJECTED_NOTICE: "The second image does not confirm the first meter reading.",
    "Vergleichswert": "Reference reading",
    "Der Präzisionsmodus ist experimentell. Der Wert selbst ist genau, aber die schnell laufende letzte Rolle wird oft nicht sicher erkannt. Dann prüft die App vorübergehend mit zwei Nachkommastellen.":
        "Precision mode is experimental. The value itself is exact, but the fast-moving last roller is often not "
        "recognised reliably. The app then checks with two decimal places for a while.",
    "Präzisionsmodus: auch die dritte Nachkommastelle vergleichen": "Precision mode: also compare the third decimal place",
    "Prüfung bestanden mit Hinweis": "Check passed with a note",
    "Test bestanden mit Hinweis": "Test passed with a note",
    "Letzte Nachkommastelle unsicher": "Last decimal digit uncertain",
    LAST_DIGIT_NOTICE: "Only the third decimal digit is unclear or differs.",
    "Dritte Nachkommastelle intensiv suchen": "Run intensive search for the third decimal digit",
    "Dritte Nachkommastelle manuell markieren": "Mark the third decimal digit manually",
    "Einrichtung abgeschlossen: Sieben Ziffern sind bestätigt. Die dritte Nachkommastelle prüft die App zusätzlich im Hintergrund.":
        "Setup complete: Seven digits confirmed. The third decimal is being checked additionally.",
    "Eine der ersten sieben Ziffern dreht sich gerade. Der gefundene Rahmen bleibt erhalten; ein frisches Bild wird geprüft.":
        "One of the first seven digits is moving. The crop is retained while a fresh image is checked.",
    "Optimierung läuft: Die Automatik ist aktiv. Im Hintergrund sucht die App noch die dritte Nachkommastelle und verbessert Rahmen und Winkel.":
        "Optimising: automatic checks are active. In the background the app is still locating the third decimal and improving frames and angle.",
    "Dritte Nachkommastelle noch offen. Die Automatik läuft weiterhin mit sieben bestätigten Ziffern.":
        "Third decimal still unconfirmed. Automatic checks continue with seven confirmed digits.",
    "Die Einrichtung bestätigt zuerst sieben Ziffern. Die dritte Nachkommastelle kann anschließend separat geprüft werden.":
        "Setup confirms seven digits first. The third decimal can then be checked separately.",
    "Die Selbsteinrichtung bestätigt zuerst die ersten zwei Nachkommastellen. Die dritte sucht die App danach automatisch im Hintergrund und justiert die Rahmen mit der Zeit selbst nach. Du musst dafür nichts tun.":
        "Automatic setup first confirms the first two decimal digits. The app then searches for the third automatically in the background and fine-tunes the frames over time. You do not need to do anything.",
    "Dritte Nachkommastelle bestätigt. Die Ziffernrahmen sind übernommen.":
        "Third decimal digit confirmed. The digit frames have been saved.",
    "Dritte Nachkommastelle bleibt unbestätigt. Du kannst später erneut suchen oder sie manuell markieren.":
        "The third decimal digit remains unconfirmed. Search again later or mark it manually.",
    "Ausschnitt gespeichert. Die App sucht jetzt gezielt die dritte Nachkommastelle …":
        "Crop saved. Now searching specifically for the third decimal digit …",
    "Derselbe Rahmen wird mit dem nächsten neuen Bild weiter geprüft.":
        "Continuing to check the same crop on the next new image.",
    "Der Ausschnitt ist deutlich weniger scharf oder kontrastreich als zuvor. Die App wartet auf ein besseres Bild.":
        "The crop has noticeably less detail or contrast than before. Waiting for a better image.",
    "Gegenprobe wartet auf ein besseres Bild. Der bestätigte Rahmen bleibt ausgewählt.":
        "Waiting for a better image for verification. The confirmed crop remains selected.",
    "Grobsuche läuft. Die besten Zwischenkandidaten werden gespeichert.":
        "Coarse search in progress. Saving the highest-ranked candidates.",
    "Intensivprüfung für Kandidat ": "Intensive check for candidate ",
    "Grobtests: ": "Coarse attempts: ",
    "Grün bedeutet lesbar. Ein gültiger Vergleichswert für dieses Bild fehlt.":
        "Green means readable. This image has no valid reference reading.",
    "Grün bedeutet lesbar. Der abgelesene Stand passt noch nicht zum Vergleichswert.":
        "Green means readable. The reading does not match the reference yet.",
    "Ziffern sind lesbar. Ohne Vergleichswert wartet die App auf einen plausiblen Anstieg oder einen Startwert.":
        "The digits are readable. Without a reference, the app waits for a plausible increase or a starting reading.",
    "Treffer gesammelt. Die App wartet auf ein frisches Bild für die Gegenprobe.":
        "Matches collected. Waiting for a fresh image for verification.",
    " · Beste Kandidaten: ": " · Best candidates: ",
    "Die vermutete Position der letzten Rolle wird auf diesem Bild getestet …":
        "Testing the estimated position of the last roller on this image …",
    " Vorschlag für die letzte Rolle gefunden. Die Bestätigung folgt mit einem neuen Bild.":
        " Candidate for the last roller found. Waiting for confirmation on a new image.",
    " Für die Rahmenwahl werden die ersten zwei Nachkommastellen verglichen.":
        " Frame selection compares the first two decimal places.",
    " · Feinprüfung der dritten Stelle: ": " · Third-digit verification: ",
    "Grün: gelesen. Gelb: OCR-Versuche weichen ab. Gelb mit ?: Stelle vermutet, Ziffer nicht lesbar. Rot: unklar.":
        "Green: read. Yellow: OCR attempts disagree. Yellow with ?: probable position, unreadable digit. Red: unclear.",
    "Rahmen mit 100 % Übereinstimmung gefunden. Die Intensivprüfung bleibt bei diesem Rahmen und wartet auf ein neues Bild.":
        "Crop found with 100% agreement. The intensive check keeps this crop and waits for a new image.",
    "Ziffernfeld ist lesbar.": "The digit row is readable.",
    " Ohne Vergleichswert wartet die App auf einen plausiblen Anstieg oder einen Startwert.":
        " Without a reference, the app waits for a plausible increase or a starting reading.",
    "Drei Treffer mit 100 %: Grobprüfung beendet. Die App wartet auf ein frisches Bild für die Gegenprobe.":
        "Three matches at 100%: coarse search complete. Waiting for a fresh image for verification.",
    " · Schwankende Stellen im Intensivtest (von links): ": " · Unstable positions in the intensive check (from the left): ",
    "Bester Treffer der Feinprüfung · ": "Best fine-check result · ",
    "Feinprüfung erfolgreich, Gegenprobe offen. Der beste Rahmen steht für den manuellen Test bereit.":
        "Fine check passed, independent verification pending. The best crop is available for the manual check.",
    " · Zeit für Gegenprobe: ": " · Verification time left: ",
    "Hinweis zur Genauigkeit.": "Accuracy warning.",
    " Ohne Gegenprobe kann der übernommene Rahmen spätere Ablesungen ungenauer machen.":
        " Using this crop without verification can make future readings less accurate.",
    "Gegenprobe überspringen und Rahmen übernehmen": "Skip verification and use this crop",
    "Rahmen ohne Gegenprobe übernommen. Spätere Ablesungen können ungenauer sein.":
        "Crop saved without verification. Future readings may be less accurate.",
    "Hinweis zum Kamerabild. ": "Camera image note. ",
    "Das Ziffernfeld wirkt dunkel.": "The digit area appears dark.",
    "Das Ziffernfeld wirkt sehr hell.": "The digit area appears very bright.",
    "Das Ziffernfeld hat wenig Kontrast.": "The digit area has low contrast.",
    "Das Ziffernfeld wirkt unscharf.": "The digit area appears blurry.",
    "Die App prüft zuerst den zuletzt bestätigten Rahmen.": "The app checks the last verified crop first.",
    "Die letzte Rolle war lesbar. Die vorletzte blieb trotz gezielter Prüfung offen.":
        "The last roller was readable. The second-to-last roller remained unclear after a targeted check.",
    "Bei Spiegelungen hilfreich. Die App schätzt verdeckte Stellen nur, wenn Zählerstände und Durchfluss genau eine Ergänzung zulassen. Geschätzte Ziffern bleiben gelb.":
        "Helpful with reflections. The app estimates obscured digits only if the readings and flow allow exactly one possibility. Estimated digits stay yellow.",
    "Ausschnitt vorläufig gespeichert. Die Automatik prüft die sieben lesbaren Stellen. Die dritte Nachkommastelle bleibt vorerst offen.":
        "Crop saved provisionally. The automatic check uses the seven readable digits. The third decimal digit remains open for now.",
    "Letzte Rolle: ": "Last roller: ",
    "Letzte Rolle wird gelesen …": "Reading the last roller …",
    "Nur die letzte Rolle im gespeicherten Ausschnitt wird geprüft …": "Checking only the last roller in the saved crop …",
    "Letzte Rolle gefunden. Die App wartet auf ein frisches Bild zur Gegenprobe …":
        "Last roller found. Waiting for a fresh verification image …",
    "Zähler erfolgreich eingerichtet": "Meter setup complete",
    "In den ersten 20 Minuten optimiert die App Rahmen und Winkel mit zusätzlichen Kontrollmessungen. Einzelne Werte können in dieser Zeit noch abweichen.":
        "During the first 20 minutes the app optimises frames and angle with additional checks. Individual readings may still deviate during this time.",
    "Diagnose der Selbsteinrichtung": "Setup diagnostics",
    LAST_DIGIT_PASS: "The first two decimal places match. The third is not yet confirmed in this check.",
    SEVENTH_DIGIT_PASS: (
        "The first six digits match the reference without rounding. "
        "The seventh digit cannot be read reliably yet, so this check is only "
        "confirmed to the first decimal place. Consumption and configured precision "
        "remain unchanged. Until the reading rises further, the app checks "
        "every 30 minutes."
    ),
    SEVENTH_DIGIT_WAIT_NOTICE: (
        "The seventh digit is unclear. The app waits for the reading to rise "
        "and checks again in 30 minutes."
    ),
    "Für den Verbrauch verwendet die App den plausiblen Vergleichswert.": "The app uses the plausible reference reading to calculate consumption.",
    "Ablesung und Vergleichswert weichen ab": "Image reading and reference differ",
    "Vergleiche beide Werte mit dem Stand direkt am Zähler.": "Compare both readings with the value on the meter itself.",
    "Die App prüft automatisch erneut. Bleibt der Unterschied, vergleiche beide Werte mit dem Stand direkt am Zähler.":
        "The app will check again automatically. If the readings still differ, compare both with the value on the meter itself.",
    "Letzte automatische Erkennung": "Latest automatic reading",
    "Schließen": "Close",
    "Originalbild zum Ablesen": "Original image for reading",
    "Später einrichten": "Set up later",
    "Du kannst die Einrichtung jederzeit über „Einrichtung“ oben rechts erneut starten.":
        "You can restart setup at any time using “Setup” at the top right.",
    "Stand im Home-Assistant-Dashboard anzeigen": "Show the reading on a Home Assistant dashboard",
    "Wenn AI Meter Reader selbst aus einer ESPHome- oder Home-Assistant-Kamera liest, kannst du den Sensor „OCR-Zählerstand“ zum Dashboard hinzufügen. Seine Entitäts-ID lautet ":
        "When AI Meter Reader reads directly from an ESPHome or Home Assistant camera, you can add its OCR meter reading sensor to your dashboard. Its entity ID is ",
    "Oder füge diese kurze YAML-Konfiguration in eine manuelle Karte ein:":
        "Or paste this short YAML configuration into a manual card:",
    "App-Daten zurücksetzen": "Reset app data",
    "Du kannst die Einrichtung vollständig zurücksetzen oder die bestätigten Zählerstands- und Verbrauchsstatistiken behalten. Home-Assistant-App-Konfiguration und Entitäten bleiben in beiden Fällen bestehen.":
        "You can reset all setup data or keep verified meter reading and consumption statistics. Home Assistant app configuration and entities remain in both cases.",
    "Werkseinstellungen – Statistik behalten": "Factory Reset – Keep Statistics",
    "Gespeicherte Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie, Verbrauchsstatistik und Testbilder werden zurückgesetzt. Home-Assistant-App-Konfiguration und Entitätsnamen bleiben erhalten.":
        "Saved image source, OCR and notification settings, check history, consumption statistics and test images will be reset. Home Assistant app configuration and entity IDs remain.",
    "Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie und Testbilder werden zurückgesetzt. Bestätigte Zählerstands- und Verbrauchsstatistiken sowie der kumulierte Verbrauch bleiben erhalten. Anschließend ist eine neue Einrichtung erforderlich.":
        "Image source, OCR and notification settings, check history and test images will be reset. Verified reading and consumption statistics and the cumulative total are kept. You must set up the app again.",
    "Werkseinstellungen wiederhergestellt. Verbrauchsstatistik und Gesamtverbrauch sind erhalten. Die Einrichtung öffnet sich erneut.":
        "Factory settings restored. Consumption statistics and cumulative total were kept. Setup will open again.",
    "Setzt die AI-Meter-Reader-Einstellungen und Prüfhistorie auf Standardwerte zurück und entfernt gespeicherte Testbilder. Die Home-Assistant-App-Konfiguration und vorhandenen Entitäten bleiben erhalten.":
        "Resets AI Meter Reader settings and check history to defaults and removes saved test images. Home Assistant app configuration and existing entities are kept.",
    "Auf Werkseinstellungen zurücksetzen": "Restore factory settings",
    "Werkseinstellungen wiederherstellen?": "Restore factory settings?",
    "Gespeicherte Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie und Testbilder werden zurückgesetzt. Home-Assistant-App-Konfiguration und Entitätsnamen bleiben erhalten.":
        "Saved image source, OCR and notification settings, check history, and test images will be reset. Home Assistant app configuration and entity IDs will be kept.",
    "Abbrechen": "Cancel",
    "Jetzt zurücksetzen": "Reset now",
    "Zurücksetzen angefordert. Eine laufende Prüfung kann das kurz verzögern. Danach öffnet sich die Einrichtung von selbst.":
        "Factory reset requested. A check in progress may delay the reset. Please wait for setup to open.",
    "Werkseinstellungen wiederhergestellt. Die Einrichtung öffnet sich erneut.":
        "Factory settings restored. Setup will open again.",
    "Das Zurücksetzen läuft noch. Die Einrichtung öffnet sich, sobald es fertig ist.":
        "The reset is still running. Setup will open when it finishes.",
    "Das Zurücksetzen wurde nicht vollständig ausgeführt.":
        "The reset could not be completed.",
    "Die Einrichtung konnte nicht übersprungen werden.": "Setup could not be skipped.",
    "Übersicht": "Overview",
    "Hauptmenü": "Main menu",
    "Ansichten": "Views",
    "Anleitung auf GitHub": "Guide on GitHub",
    ">Anleitung</a>": ">Guide</a>",
    "Fallback-Wert für diesen Test (optional)": "Fallback reading for this test (optional)",
    "Am markierten Bild ablesen und hier eintragen. Der Wert wird nur mit dem manuellen Test verglichen und nicht als automatische Referenz gespeichert.":
        "Read the marked image and enter the value here. It is compared only with the manual test and is not saved as the automatic reference.",
    "Über AI Meter Reader": "About AI Meter Reader",
    "Stand und Verbrauch im Dashboard anzeigen": "Show the reading and usage on a dashboard",
    "Für den erkannten Zählerstand im ESPHome- oder Kameramodus: ": "For the recognized meter reading in ESPHome or camera mode: ",
    "Für den Home-Assistant-Energieverbrauch: ": "For Home Assistant energy usage: ",
    "Diese Entität erscheint nach dem ersten gültigen Messwert und kann im Energie-Dashboard als Gasverbrauch ausgewählt werden.": "This entity appears after the first valid reading and can be selected as gas consumption in the Energy dashboard.",
    "So fügst du den Zählerstand einer einfachen Dashboard-Karte hinzu:": "To add the meter reading to a simple dashboard card:",
    "Freiwillig mit PayPal unterstützen": "Support the project voluntarily with PayPal",
    "EifelLayer-Projektlogo": "EifelLayer project logo",
    "Ein privates Hobbyprojekt von EifelLayer. KI-unterstützt entwickelt. Keine geeichte Messung oder Gewähr für OCR-Ergebnisse. Bitte Zählerstände bei Bedarf direkt am Gerät prüfen.": "A private hobby project by EifelLayer, developed with AI assistance. Not a certified measurement and no guarantee of OCR results. Check readings on the physical meter when needed.",
    "Unabhängiger Bildabgleich deines Gaszählerstands mit der vorhandenen Messung. Die OCR liest die Ziffern erneut direkt aus dem Kamerabild – ohne den vom ESP erkannten Wert einfach zu übernehmen.":
        "Independent visual cross-check of your gas meter reading. Local OCR reads the digits again from the camera image instead of simply reusing the ESP's reading.",
    "Automatische Kontrolle": "Automatic verification",
    "Nächste Prüfung": "Next check",
    "Vergleichsgenauigkeit": "Comparison precision",
    "Vergleich": "Comparison",
    "Erkannter Stand": "OCR reading",
    "Referenz": "Reference",
    "ESP-Ersatzwert": "ESP fallback reading",
    "Zeitpunkt unbekannt": "Time unknown",
    "Prüfergebnis": "Check result",
    "Bildzeit": "Image time",
    "Letzte automatische Prüfung": "Last automatic check",
    "Letzte Prüfung": "Last check",
    "Wiederholte Fehlablesung? Ein kürzeres Prüfintervall kann helfen, wenn sich der Zähler nach einer Weile wieder klarer ablesen lässt.": "Repeated reading errors? A shorter check interval can help if the meter becomes easier to read after it turns.",
    "Prüfintervall ändern": "Change check interval",
    "ⓘ Warum das Prüfintervall ändern?": "ⓘ Why change the check interval?",
    "Nach einem fehlgeschlagenen automatischen Test folgen bis zu zwei weitere Prüfungen im Abstand von fünf Minuten. Sind alle drei erfolglos, pausiert die App für die eingestellte Zeit (Standard: 30 Minuten) und prüft dann erneut. Nach Erfolg gilt wieder dein eingestelltes Intervall. Ein kürzeres Intervall kann helfen, wenn sich der Zähler beim Weiterdrehen vorübergehend schlecht lesen lässt.":
        "After a failed automatic check, up to two more checks follow at five-minute intervals. If all three fail, the app pauses for the configured time (default: 30 minutes) before trying again. After a successful check, your selected interval applies again. A shorter interval can help when the meter is temporarily hard to read as it turns.",
    "Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben alle drei Prüfungen erfolglos, pausiert AI Meter Reader für die eingestellte Zeit (Standard: 30 Minuten) und versucht es dann erneut. Prüfe Beleuchtung, Abstand und Fokus.": "After a failed automatic check, up to two more image checks follow at five-minute intervals. If all three fail, AI Meter Reader pauses for the configured time (default: 30 minutes), then tries again. Check lighting, distance, and focus.",
    "Wartet auf die nächste automatische Prüfung.": "Waiting for the next automatic check.",
    "App läuft. Wartet auf die nächste automatische Prüfung.": "App is running and waiting for the next automatic check.",
    "Automatik:": "Automatic checks:",
    "Einrichtung erforderlich: Lege zuerst die Bildquelle fest.": "Setup required. Choose an image source.",
    "Automatik pausiert. Manuelle Tests bleiben verfügbar.": "Automatic checks are paused. Manual tests are still available.",
    "Automatik pausiert": "Automatic checks paused",
    "Es werden keine automatischen Prüfungen gestartet. Manuelle Tests bleiben verfügbar.": "No automatic checks will start. Manual tests remain available.",
    "Es starten keine neuen automatischen Prüfungen. Ein bereits laufender Durchlauf darf noch enden. Manuelle Tests bleiben verfügbar.": "No new automatic checks will start. A check already in progress may finish. Manual tests remain available.",
    "Automatik fortsetzen": "Resume automatic checks",
    "Automatik pausieren": "Pause automatic checks",
    "Keine Verbindung zur App. Sie könnte gestoppt oder vorübergehend nicht erreichbar sein.": "No connection to the app. It may be stopped or temporarily unavailable.",
    "Quelle: ": "Source: ",
    "Noch kein Bildabruf erfolgt.": "No image has been fetched yet.",
    "ESP erreichbar. Bild und Messwerte empfangen.": "ESP reachable. Image and reading received.",
    "Aufbereitetes ESP-Bild fehlt oder ist zu alt. Die App prüft ein frisches Rohbild.": "The processed ESP image is missing or too old. Checking a fresh raw image.",
    "Aufbereitetes ESP-Bild nicht nutzbar. Rohbild ohne ESP-Referenz geprüft.": "The processed ESP image is unusable. A raw image was checked without an ESP reference.",
    "Aufbereitetes ESP-Bild nicht nutzbar. Es konnte kein frisches Rohbild geladen werden.": "The processed ESP image is unusable and a fresh raw image could not be loaded.",
    "Rohbild gelesen. Das aufbereitete ESP-Bild war nicht nutzbar – prüfe in AI on the Edge die Bildausrichtung und die Referenzmarken.": "Raw image read. The processed ESP image was unusable – check image alignment and reference markers in AI on the Edge.",
    "Kamera erreichbar. Frisches Bild empfangen.": "Camera reachable. Fresh image received.",
    "ESP erreichbar, aber das Bild ist älter als 15 Minuten oder hat einen ungültigen Zeitstempel.": "ESP reachable, but the image is older than 15 minutes or has an invalid timestamp.",
    "Kamera erreichbar, aber das Bild hat einen ungültigen Zeitstempel.": "Camera reachable, but the image has an invalid timestamp.",
    "ESP erreichbar. Seit der letzten Prüfung kam kein neues Bild; das vorhandene Bild ist noch nicht veraltet.": "ESP reachable. No new image since the last check; the current image is not stale yet.",
    "Home-Assistant-Kamera erreichbar; dieses Bild wurde bereits geprüft.": "Home Assistant camera reachable; this image was already checked.",
    "Home-Assistant-Kamera nicht erreichbar oder Bild unlesbar. Prüfe Kamera und Zugriff.": "Home Assistant camera unavailable or image unreadable. Check the camera and access.",
    "ESP nicht erreichbar oder Antwort unvollständig. Prüfe Adresse und Verbindung.": "ESP unavailable or response incomplete. Check its address and connection.",
    "Kamerabild wird aufgenommen.": "Capturing a fresh camera image.",
    "Einstellungen gespeichert. Prüfung startet gleich.": "Settings saved. The check is about to start.",
    "Automatische Prüfung startet …": "Starting the automatic check …",
    "Kamerabild wird angefordert …": "Waiting for a camera image …",
    "Die App wartet auf Bild und Messwerte vom ESP …": "Waiting for the image and reading from the ESP …",
    "Die App wartet auf ein aktuelles Bild vom ESP …": "Waiting for a new image from the ESP …",
    "Intensivtest: Die App prüft das Bild leicht gedreht.": "Recovery check: testing a slightly rotated image.",
    "Noch kein aktuelles Zählerbild": "No current meter image yet",
    "Fortschritt der automatischen Prüfung": "Automatic check progress",
    "Einstellungen werden gespeichert …": "Saving settings …",
    "Bild und Messwerte werden vom ESP abgerufen.": "Fetching the image and reading from the ESP.",
    "Bild wird vorbereitet.": "Preparing the image.",
    "Automatische Prüfung wird abgeschlossen.": "Finishing the automatic check.",
    "Letzte Prüfung beendet. Nächster Versuch nach kurzer Wartezeit.": "Last check finished. The next attempt follows after a short wait.",
    "Letzte Prüfung beendet. Wartet auf das eingestellte Prüfintervall.": "Last check finished. Waiting for the selected check interval.",
    "Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben alle drei Prüfungen erfolglos, pausiert die App für die eingestellte Zeit (Standard: 30 Minuten). Prüfe Beleuchtung, Abstand und Fokus.": "After a failed automatic check, up to two more image checks follow at five-minute intervals. If all three fail, the app pauses for the configured time (default: 30 minutes). Check lighting, distance, and focus.",
    "Nach drei fehlgeschlagenen automatischen Prüfungen mit unterschiedlichen Bildabrufen pausiert die App für die eingestellte Zeit (Standard: 30 Minuten) und versucht es dann erneut. Nach einem erfolgreichen Abgleich gilt wieder dein eingestelltes Prüfintervall. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.": "After three failed automatic checks using different image captures, the app pauses for the configured time (default: 30 minutes) and tries again. After a successful match, the selected interval applies again. Changing comparison precision resets the match count.",
    "Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Bei einer unsicheren Ablesung folgen bis zu zehn zusätzliche Bildauswertungen; die App setzt einzelne Ziffern nur bei einer strikten Mehrheit zusammen. Nach drei fehlgeschlagenen automatischen Prüfungen mit unterschiedlichen Bildabrufen pausiert sie für die eingestellte Zeit (Standard: 30 Minuten). Prüfe bei wiederholten Fehlern auch Beleuchtung, Abstand und Fokus. Beim Livebild kann AI Meter Reader bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.": "Automatic detection tries to find the digit area. If a reading is uncertain, up to ten extra image analyses follow; digits are combined only when a strict majority agrees. After three failed automatic checks using different image captures, the app pauses for the configured time (default: 30 minutes). If errors continue, check lighting, distance, and focus. For live images, AI Meter Reader can try up to 10 fresh snapshots within 20 seconds.",
    "SLFork liefert Bild und Messwert. Die Livebild-Quelle ruft bei jeder Prüfung ein aktuelles Standbild deiner Home-Assistant-Kamera ab; ein Video wird nicht dauerhaft ausgewertet. Du kannst dazu einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest AI Meter Reader selbst und prüft die Werte auf Plausibilität.": "SLFork supplies the image and reading. The live image source takes a fresh snapshot from your Home Assistant camera for each check; video is not continuously processed. You can add a meter reading sensor, such as AI on the Edge, for comparison. Without a reference sensor, AI Meter Reader reads the image itself and checks plausibility.",
    "Er ist ein Startwert, solange noch keine sichere automatische Ablesung gespeichert ist. AI Meter Reader prüft die erste Ablesung gegen den Zeitabstand und den maximalen Durchfluss. Danach wird der letzte bestätigte Stand als Referenz genutzt. Ohne Fallback beginnt die Plausibilitätsprüfung mit der ersten sicheren Ablesung.": "This is a starting value until a reliable automatic reading is saved. AI Meter Reader checks the first reading against elapsed time and maximum flow. After that, it uses the latest confirmed reading as its reference. Without a fallback, plausibility checks begin with the first reliable reading.",
    "Letzter bestätigter Abgleich": "Last confirmed match",
    "Einstellungen": "Settings",
    "Automatische Prüfung": "Automatic checks",
    "Prüfintervall (Minuten)": "Check interval (minutes)",
    "Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben alle drei Prüfungen erfolglos, pausiert AI Meter Reader für die eingestellte Zeit (Standard: 30 Minuten) und versucht es dann erneut. Prüfe Beleuchtung, Abstand und Fokus.":
        "After a failed automatic check, up to two more image checks follow at five-minute intervals. If all three fail, AI Meter Reader pauses for the configured time (default: 30 minutes), then tries again. Check lighting, distance, and focus.",
    "Max. OCR-Versuche": "Max. OCR attempts",
    "Übereinstimmung für die Intensivprüfung (%)": "Agreement for the intensive check (%)",
    "Ab diesem Wert wechselt die Selbsteinrichtung in die Intensivprüfung. Eine einzelne vermutete Ziffernposition kann sie auch früher gezielt prüfen.":
        "Automatic setup switches to the intensive check at this threshold. It can check a single suspected digit position sooner.",
    "Ziffernfarbe": "Digit color",
    "Bildbereich (links, oben, rechts, unten)": "Image region (left, top, right, bottom)",
    "Manueller Ausschnitt (links, oben, rechts, unten)": "Custom crop (left, top, right, bottom)",
    "Bilddrehung im Uhrzeigersinn": "Clockwise rotation",
    "Bilddrehung (°)": "Image rotation (°)",
    "Wähle den Ausschnitt im Originalbild. Positive Winkel drehen nach rechts, negative nach links. Die Vorkommabreite gilt nach der Drehung.":
        "Select the crop in the original image. Positive angles turn right; negative angles turn left. The whole-number width applies after rotation.",
    "Wähle den Ausschnitt im Originalbild. Die Vorkommabreite gilt nach der Drehung.":
        "Use coordinates from the original image. The whole-digit width applies after rotation.",
    "Maximaler Durchfluss (m³/h)": "Maximum flow (m³/h)",
    "Qmax steht auf deinem Zähler. Die Vorgabe für einen G4 beträgt 6 m³/h.":
        "Check the Qmax value printed on your meter. The default for G4 is 6 m³/h.",
    "Breite der Vorkommastellen": "Width of whole-number digits",
    "Bildbereich": "Image region",
    "Speichern": "Save",
    "Das Prüfintervall gilt auch für die bereits geplante nächste Prüfung. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.":
        "The interval also applies to the next scheduled check. Changing comparison precision resets the match count.",
    "Manueller Test": "Manual test",
    'id="open-setup">Einrichtung<': 'id="open-setup">Setup<',
    'id="reload-view">Neu laden<': 'id="reload-view">Reload<',
    '<summary>Debug-Protokoll</summary>': '<summary>Debug log</summary>',
    '<summary>Erweitert</summary>': '<summary>Advanced</summary>',
    "Rolle drehte sich gerade": "Roller was turning",
    "Rahmen der letzten Stelle sitzt daneben": "Frame of the last digit is off",
    "Ablesung passt nicht zum letzten Stand": "Reading does not fit the last value",
    "Die App sucht die letzte Stelle selbst im Hintergrund. Nur nötig, wenn das dauerhaft nicht klappt.":
        "The app searches for the last digit in the background by itself. Only needed if that keeps failing.",
    "Die letzten Prüfungen mit allen OCR-Durchläufen, Entscheidung und Verbrauchsstand. Ohne Bilder und Zugangsdaten. Hilfreich für Fehlermeldungen.":
        "The latest checks with all OCR runs, decision and consumption state. No images or credentials. Useful for bug reports.",
    '>Protokoll herunterladen<': '>Download log<',
    '<li data-step="0" data-state="current">Bildquelle</li><li data-step="1">Anzeige</li><li data-step="2">Ausschnitt</li><li data-step="3">Hinweise</li>':
        '<li data-step="0" data-state="current">Source</li><li data-step="1">Display</li><li data-step="2">Crop</li><li data-step="3">Alerts</li>',
    'aria-label="Schritte"': 'aria-label="Steps"',
    "Abweichenden Bildausschnitt ausprobieren": "Try a different image crop",
    "Fortschritt der Hintergrundsuche": "Background search progress",
    "Der Test verwendet den gespeicherten Ausschnitt der Automatik. Dauerhaft änderst du ihn unter Einstellungen → Automatische Prüfung. Hier kannst du eine Variante testen und danach übernehmen.":
        "The test uses the crop saved for automatic checks. To change it permanently, go to Settings → Automatic check. Here you can try a variant and then apply it.",
    "Test einstellen": "Test settings",
    "Test starten": "Start test",
    "Testeinstellungen": "Test settings",
    "Zusätzliche Bild- und OCR-Einstellungen": "Advanced image and OCR settings",
    "Manueller Bildtest": "Manual image test",
    "Jetzt prüfen": "Run check now",
    "Eigenes Testbild (optional, JPG oder PNG)": "Choose a test image (optional, JPG or PNG)",
    "Ein ausgewähltes Bild wird nur für diesen manuellen Test verwendet (max. 3 MB).": "The selected image is used only for this manual test (max. 3 MB).",
    "Speichern und prüfen": "Save and check",
    "ⓘ Was passiert bei „Jetzt prüfen“?": "ⓘ What happens when I run a check?",
    "Die App verwendet das letzte vorhandene Zählerbild oder ein ausgewähltes eigenes JPG-/PNG-Testbild (bis 3 MB). Sie liest die Zahlen aus dem Bild und vergleicht sie mit dem Referenzwert. Sobald die Werte übereinstimmen, stoppt die Prüfung. Andernfalls werden höchstens so viele OCR-Versuche durchgeführt wie eingestellt (1–10). Der Test verändert die automatische Trefferzahl nicht.": "The app uses the latest available meter image or a selected JPG/PNG test image (up to 3 MB). It reads the digits and compares them with the reference. The check stops as soon as they match. Otherwise it runs up to the configured number of OCR attempts (1–10). A manual test does not change the automatic confirmation count.",
    "Ziffern aus mehreren OCR-Versuchen zusammengesetzt.": "Digits combined from multiple OCR attempts.",
    "Die App verwendet das letzte vorhandene Zählerbild, ohne eine neue Aufnahme zu starten. Sie liest die Zahlen aus dem Bild und vergleicht sie mit dem Referenzwert. Sobald die Werte übereinstimmen, stoppt die Prüfung. Andernfalls werden höchstens so viele OCR-Versuche durchgeführt wie eingestellt (1–10). Der Test verändert die automatische Trefferzahl nicht.":
        "The app uses the most recent meter image without triggering a new capture. It independently reads the digits and compares them with the reference value. Checking stops as soon as the values agree; otherwise it tries up to the configured number of OCR attempts (1–10). Manual checks do not affect automatic confirmation counts.",
    "Informationen zum manuellen Bildtest": "Information about the manual image test",
    "Aktueller Schritt: Bereit": "Current step: Ready",
    "Bereit für den manuellen Test.": "Ready to run a manual check.",
    "OCR-Versuche": "OCR attempts",
    "Versuche abgeschlossen: ": "Attempts completed: ",
    "Prüfung läuft …": "Check in progress …",
    "Anfrage angenommen": "Request accepted",
    "Bild und Messwerte": "Image and reference data",
    "OCR-Auswertung": "OCR analysis",
    "Test erfolgreich": "Check successful",
    "Bild gelesen – ohne Vergleich": "Image read – no reference",
    "Test beendet – Abweichung erkannt": "Check complete – mismatch detected",
    "Test beendet – Ziffern nicht sicher erkannt": "Check complete – uncertain digits",
    "Test beendet – Referenzwert unklar": "Check complete – reference uncertain",
    "Test nicht erfolgreich": "Check unsuccessful",
    "Anfrage wird gesendet": "Sending request",
    "Bereit": "Ready",
    "OCR-Versuch": "OCR attempt",
    "1 OCR-Versuch": "1 OCR attempt",
    "Status nicht erreichbar – Verbindung prüfen.": "Status unavailable – check the connection.",
    "Kein Ergebnis.": "No result available.",
    "Mehr Infos: Was wurde bei den OCR-Versuchen gelesen?": "More details: What did each OCR attempt read?",
    "Versuch": "Attempt",
    "Verglichen wurden nur die vollen Kubikmeter (ohne Nachkommastellen).":
        "Only whole cubic meters were compared (decimal digits ignored).",
    "Verglichen wurden die vollen Kubikmeter und ": "Compared whole cubic meters and ",
    " Nachkommastelle(n).": " decimal place(s).",
    "OCR-Testbild mit erkannten Stellen": "OCR image showing recognized digits",
    "Grün:": "Green:",
    "Gelb:": "Yellow:",
    "Rot:": "Red:",
    "Ziffer wurde gelesen": "Digit recognized",
    "Ziffer schwankte zwischen OCR-Versuchen oder wurde aus mehreren Versuchen zusammengesetzt" :
        "Digit varied across OCR attempts or was composed from multiple attempts",
    "Ziffer gelesen": "Digit read",
    "Ziffer weiterhin unklar": "Digit still unclear",
    "Ziffer unklar": "Digit unclear",
    "Die Farben zeigen OCR-Sicherheit, nicht die Übereinstimmung mit dem Referenzstand.":
        "The colors show OCR confidence, not whether the reading matches the reference.",
    "Die Farbrahmen zeigen die OCR-Erkennung, nicht die Übereinstimmung mit dem Referenzstand. Ohne automatisch erkannte Ziffernrahmen sind die Bereiche nur näherungsweise aufgeteilt.":
        "The colored boxes show OCR recognition, not whether the digits match the reference. Without detected digit frames, the individual regions are approximate.",
    "Zählerbild mit grün markierten erkannten Ziffern und rot markierten unklaren Stellen":
        "Meter image with green boxes for recognized digits and red boxes for uncertain digits",
    "Getesteten Ausschnitt für die Automatik übernehmen": "Use tested crop for automatic checks",
    "Bildquelle gespeichert.": "Image source saved.",
    "Bildquelle": "Image source",
    "Wähle, woher das Zählerbild und gegebenenfalls der Vergleichswert kommen.":
        "Choose where the meter image and optional reference reading come from.",
    "Betriebsmodus": "Mode",
    "Die Adresse deines SLFork-Geräts im Heimnetz.": "The address of your SLFork device on your local network.",
    "SLFork-Adresse": "SLFork address",
    "ESP-Adresse": "ESP address",
    "Die Adresse deines ESP-Geräts im Heimnetz.": "The address of your ESP on your home network.",
    "ESP nur als Kamera verwenden": "Use the ESP as a camera only",
    "Wenn der ESP den Zähler nicht zuverlässig liest, kann die App das Bild direkt abrufen und selbst ablesen.":
        "If the ESP cannot read the meter reliably, the app can fetch the image and read it itself.",
    "Die Entitäts-ID der Kamera in Home Assistant.": "The camera entity ID in Home Assistant.",
    "Kamera in Home Assistant": "Camera in Home Assistant",
    "Optionaler Sensor mit aktuellem Zählerstand in Kubikmetern.":
        "Optional sensor that provides the current meter reading in cubic meters.",
    "Vergleichssensor (optional)": "Reference sensor (optional)",
    "Erklärung zu den verfügbaren Modi": "Explanation of the available modes",
    "ⓘ Welcher Modus passt?": "ⓘ Which mode should I choose?",
    "Das Gerät liefert Foto und Vergleichswert.": "The device supplies both the image and the reference reading.",
    "Home-Assistant-Kamera:": "Home Assistant camera:",
    "Die App liest das Bild und vergleicht es mit einem Sensor, falls einer eingetragen ist.":
        "The app reads the image and compares it with a sensor if you specify one.",
    "ESPHome oder Kamera mit lokaler OCR:": "ESPHome or camera with local OCR:",
    "Die Kamera liefert das Foto, die App liest den Stand und stellt ihn als eigenen Sensor bereit.":
        "The camera supplies the image. The app reads it and publishes the reading as a separate sensor.",
    "Automatischer Prüfstatus": "Automatic check status",
    "Zählerstand bestätigt": "Meter reading confirmed",
    "Zählerstand bitte prüfen": "Check the meter reading",
    "Letzte Prüfung fehlgeschlagen": "Last check failed",
    "Blendet diesen Hinweis hier aus. Prüfungen und Benachrichtigungen laufen weiter.":
        "Hide this warning here. Checks and notifications will continue.",
    "Ignorieren": "Ignore",
    "Benachrichtigungen gespeichert.": "Notifications saved.",
    "Beispiele und Erklärung zu den Benachrichtigungen": "Notification examples and help",
    "Benachrichtigungen": "Notifications",
    "Gilt für die automatische Kontrolle. Ein manueller Test löst keinen Versand aus.":
        "Applies to automatic checks. Manual tests do not send notifications.",
    "Bei anhaltenden Problemen benachrichtigen": "Notify me if checks keep failing",
    "So lange muss die automatische Kontrolle ohne Erfolg bleiben, bevor Home Assistant einen Hinweis anzeigt.":
        "Wait this long without a successful automatic check before showing a notice in Home Assistant.",
    "Hinweis nach (Minuten)": "Show notice after (minutes)",
    "Wartezeit für Handy-Push und E-Mail, nachdem der Hinweis erschienen ist. Bei 0 werden beide sofort gesendet.":
        "Wait this long after the notice before sending push or email. Use 0 to send immediately.",
    "Push und E-Mail nach weiteren Stunden": "Send push or email after (additional hours)",
    "Optionaler Dienst deiner Home Assistant Companion App, zum Beispiel notify.mobile_app_mein_handy.":
        "Optional Home Assistant Companion App service, for example notify.mobile_app_my_phone.",
    "Handy-Push (optional)": "Mobile push (optional)",
    "Optionales Benachrichtigungsziel in Home Assistant, zum Beispiel eine SMTP-Empfänger-Entität.":
        "Optional destination in Home Assistant, for example an SMTP recipient entity.",
    "E-Mail oder anderes Ziel (optional)": "Email or other destination (optional)",
    'placeholder="notify.mobile_app_mein_handy"': 'placeholder="notify.mobile_app_my_phone"',
    'placeholder="notify.meine_email"': 'placeholder="notify.my_email"',
    "ⓘ Wie funktioniert der Versand?": "ⓘ How are notifications sent?",
    "Nur einen Hinweis in Home Assistant erhalten? Lass beide optionalen Felder leer.":
        "Leave both optional fields blank to receive a notice in Home Assistant only.",
    "Für E-Mail richte zuerst die SMTP-Integration in Home Assistant ein und trage hier die Entitäts-ID des Empfängers ein. Andere Benachrichtigungs-Entitäten funktionieren ebenfalls.":
        "For email, set up the SMTP integration in Home Assistant and enter the recipient entity ID here. Other notification entities also work.",
    "Wenn die Prüfung wieder gelingt oder du den Hinweis schließt, entfallen noch ausstehende Nachrichten. Je Ziel wird pro Störung eine Nachricht gesendet.":
        "A successful check or dismissing the notice cancels pending messages. Each destination receives one message per incident.",
    "Kontrollbilder": "Check images",
    "? steht für eine unklare Ziffer.": "? indicates an uncertain digit.",
    "Aktuelles Bild": "Current image",
    "Letzter Treffer": "Last confirmed match",
    "Aktuelles Kontrollbild": "Latest check image",
    "Kontrollbild des letzten Treffers": "Image from last match",
    "Noch kein Kontrollbild.": "No check image available yet.",
    "Noch kein bestätigtes Bild.": "No confirmed image available yet.",
    "Kostenloses Hobbyprojekt": "Free hobby project",
    "Freiwillig unterstützen (PayPal)": "Support voluntarily (PayPal)",
    "Automatische Prüfregeln gespeichert.": "Automatic check settings saved.",
    "Getesteten Bildausschnitt für die Automatik übernommen.": "Tested crop saved for automatic checks.",
    "Neue Vergleichsgenauigkeit gespeichert. Die nächste automatische Prüfung zeigt das erste Ergebnis mit dieser Einstellung.":
        "New comparison precision saved. The next automatic check will show the first result using that setting.",
    "Noch kein manueller Test gestartet.": "No manual check has been run yet.",
    "Ein manueller Test läuft bereits.": "A manual check is already in progress.",
    "Status wird geladen …": "Loading status …",
    "Test angenommen. Die Bearbeitung wird hier live angezeigt.":
        "Request accepted. Progress will appear here live.",
    "Jetzt fällig": "Due now",
    "Einrichtung öffnen": "Open setup wizard",
    "Einrichtungsassistent": "Setup wizard",
    "Einmal Schritt für Schritt einrichten oder später einzelne Angaben ändern. Deine aktuellen Einstellungen sind vorausgefüllt.":
        "Set things up step by step, or return later to change individual settings. Your current values are prefilled.",
    "1. Bildquelle": "1. Image source",
    "2. Zähleranzeige": "2. Meter display",
    "3. Bildausschnitt und Prüfplan": "3. Image area and schedule",
    "4. Hinweise und speichern": "4. Alerts and save",
    "Woher kommt das Zählerbild?": "Where does the meter image come from?",
    "Erklärung der Bildquellen": "Image source guide",
    "In Home Assistant gefunden": "Found in Home Assistant",
    "Gerät auswählen …": "Choose a device …",
    "ESPHome / Kamera:": "ESPHome / camera:",
    "Empfohlen für den Einstieg mit einer Kamera. Die App liest den Stand selbst.":
        "Recommended when starting with a camera. The app reads the meter itself.",
    "Home-Assistant-Kamera mit Vergleichswert:": "Home Assistant camera with reference reading:",
    "Die App holt pro Prüfung ein Standbild und kann den Wert mit einem vorhandenen Sensor abgleichen.":
        "The app takes a snapshot for each check and can compare the reading with an existing sensor.",
    "Die App prüft den ESP-Messwert. Du kannst den ESP auch nur als Kamera verwenden.":
        "The app verifies the ESP reading. You can also use the ESP as a camera only.",
    "Home-Assistant-Kamera (Livebild, Standbild je Prüfung)": "Home Assistant camera (live image, one snapshot per check)",
    "Home Assistant camera (snapshot per check)": "Home Assistant camera (live image, one snapshot per check)",
    "ⓘ Welcher Weg passt?": "ⓘ Which source should I choose?",
    "SLFork liefert Bild und Messwert. Bei einer Home-Assistant-Kamera kannst du einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest AI Meter Reader selbst und prüft die Werte auf Plausibilität.":
        "SLFork supplies the image and reading. With a Home Assistant camera, you can add a meter reading sensor, such as AI on the Edge, for comparison. Without one, AI Meter Reader reads the image itself and checks readings for plausibility.",
    "Anzeigeart": "Display type",
    "Ziffern vor dem Komma": "Digits before the decimal point",
    "Nachkommastellen auf dem Zähler": "Decimal places shown on the meter",
    "Verglichen wird bis": "Compare through",
    "Die Vergleichsgenauigkeit darf kleiner sein als die angezeigte Stellenzahl. Kleine Zeiger werden nicht automatisch gelesen; bei Rollen und Zeigern bitte nur die Ziffernrollen einstellen.":
        "You can compare fewer places than the meter shows. Small pointer dials are not read automatically; for a meter with rollers and dials, configure only the roller digits.",
    "Fallback-Zählerstand (optional)": "Fallback meter reading (optional)",
    "Stand abgelesen am": "Reading recorded at",
    "ⓘ Wie wird der Fallback verwendet?": "ⓘ How is the fallback used?",
    "Er ist ein Startwert, solange noch keine sichere automatische Ablesung gespeichert ist. AI Meter Reader prüft die erste Ablesung gegen den Zeitabstand und den maximalen Durchfluss. Danach wird der letzte bestätigte Stand als Referenz genutzt. Ohne Fallback beginnt die Plausibilitätsprüfung mit der ersten sicheren Ablesung.":
        "This is a starting value until a reliable automatic reading has been saved. AI Meter Reader checks the first reading against the elapsed time and maximum flow. After that, it uses the latest confirmed reading as its reference. Without a fallback, plausibility checks begin with the first reliable reading.",
    "OCR-Versuche pro Bild": "OCR attempts per image",
    "Prüfintervall (Minuten)": "Check interval (minutes)",
    "Breite des Vorkomma-Bereichs in Pixeln": "Width of whole-digit area in pixels",
    "ⓘ Bild einrichten": "ⓘ Set up the image",
    "Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Wenn sie das nicht schafft, öffne den manuellen Test: Dort wird das aktuelle Bild mit den erkannten Ziffern angezeigt. Einen getesteten Ausschnitt kannst du danach ausdrücklich für die Automatik übernehmen. Beim Livebild kann AI Meter Reader bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.":
        "Automatic detection tries to find the digit area. If it cannot, open the manual test to see the current image and recognized digits. You can explicitly apply a tested crop to automatic checks. For live images, AI Meter Reader can try up to 10 fresh snapshots within 20 seconds.",
    "SLFork liefert Bild und Messwert. Die Livebild-Quelle ruft bei jeder Prüfung ein aktuelles Standbild deiner Home-Assistant-Kamera ab; ein Video wird nicht dauerhaft ausgewertet. Du kannst dazu einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest AI Meter Reader selbst und prüft die Werte auf Plausibilität.":
        "SLFork supplies the image and reading. The live image source takes a fresh snapshot from your Home Assistant camera for each check; it does not continuously process video. You can add a meter reading sensor, such as AI on the Edge, for comparison. Without one, AI Meter Reader reads the image itself and checks readings for plausibility.",
    "Hinweis zum Teststand": "Testing note",
    "Für reale Tests nutze ich ausschließlich AI on the Edge. Die übrigen Kamera- und Zählermodi sind bisher nur mit simulierten Bildern und automatisierten Tests geprüft.":
        "For real-world tests, I use AI on the Edge only. The other camera and meter modes have so far been checked only with simulated images and automated tests.",
    "Bei anhaltenden Problemen benachrichtigen": "Notify me if problems continue",
    "Push oder E-Mail nach weiteren Stunden": "Send push or email after (additional hours)",
    "ⓘ Keine Benachrichtigung nötig?": "ⓘ Prefer no notifications?",
    "Entferne das Häkchen. Das Statusfeld in der Übersicht bleibt sichtbar; ein manueller Test löst keinen Push oder keine E-Mail aus.":
        "Clear the checkbox. The status remains visible on the overview; manual tests never send push or email notifications.",
    "Einrichtung speichern": "Save setup",
    "Manuellen Bildtest mit Testbild öffnen": "Open manual image test",
    "Einrichtung gespeichert.": "Setup saved.",
    "Fallback-Wert für diesen Test (optional)": "Fallback reading for this test (optional)",
    "Lass den Test zuerst das aktuelle Kamerabild laden. Lies den Stand am Bild ab und trage ihn hier ein, wenn du diesen einzelnen OCR-Test damit vergleichen möchtest. Der Wert wird nicht dauerhaft als automatische Referenz gespeichert.":
        "First let the test load the current camera image. Read the meter value from the image and enter it here to compare this one OCR test. The value is not saved as a permanent automatic reference.",
    "Aktuelles Bild zum Ablesen": "Current image to read",
    "Kein Bild vorhanden. Prüfe Bildquelle und Verbindung und starte den manuellen Test erneut.":
        "No image available. Check the image source and connection, then run the manual test again.",
    "Ziffernrollen": "Number rollers",
    "Digitales Zifferndisplay": "Digital numeric display",
    "Ziffernrollen plus Zeiger": "Number rollers plus pointers",
}

EN_DETAILS = {
    ("Die letzte verglichene Stelle war mehrmals hintereinander unklar. Das liegt vermutlich nicht "
     "an einer drehenden Rolle, sondern daran, dass ihr Rahmen neben der Rolle sitzt. Die App sucht "
     "ihn im Hintergrund neu und prüft bis dahin mit einer Nachkommastelle weniger."):
        "The last compared digit was unclear several times in a row. This is probably not a turning roller but a "
        "frame sitting beside the roller. The app searches for it again in the background and checks with one "
        "decimal place less until then.",
    ("Die letzte verglichene Stelle war mehrmals hintereinander unklar. Vermutlich sitzt ihr "
     "Rahmen neben der Rolle. Bis das korrigiert ist, prüft die App mit einer Nachkommastelle weniger."):
        "The last compared digit was unclear several times in a row. Its frame probably sits beside the roller. "
        "Until this is corrected, the app checks with one decimal place less.",
    ("Die letzte verglichene Rolle war unklar, vermutlich drehte sie sich gerade. Diese Prüfung wurde deshalb mit einer "
     "Nachkommastelle weniger bestätigt. Die nächste Prüfung vergleicht wieder alle Stellen."):
        "The last compared roller was unclear, probably turning. This check was therefore confirmed with one decimal place less. The next check compares all digits again.",
    ("Nur die letzte verglichene Stelle war unklar – vermutlich drehte sich die Rolle gerade. "
     "Die nächste Prüfung folgt automatisch."):
        "Only the last compared digit was unclear – the roller was probably turning. The next check follows automatically.",
    FALLBACK_NOTICE: "The ESP is using a fallback reading.",
    "OCR-Zuwachs plausibel. Warte auf den Abgleich.": "OCR increase looks plausible. Waiting for a match.",
    "Für die Plausibilitätsprüfung fehlt ein gültiger Messzeitpunkt.":
        "A valid measurement time is needed to assess the change.",
    "OCR-Stand unsicher.": "OCR reading uncertain.",
    "Zählerstand liegt unter dem letzten gültigen Wert.": "Reading is lower than the last accepted value.",
    "Zählerstand liegt unter dem letzten gültigen Wert. Bestätigen weitere stimmige Ablesungen den niedrigeren Stand, wird er übernommen.":
        "Reading is lower than the last accepted value. If further consistent readings confirm the lower value, it will be taken over.",
    ("Mehrere stimmige Ablesungen lagen unter dem gespeicherten Stand. Der höhere Wert war ein Lesefehler, "
     "der Zählerstand wurde korrigiert."):
        ("Several consistent readings were below the stored value. The higher value was a misread and the reading "
         "has been corrected."),
    "Zählerstand steigt schneller als der eingestellte Durchfluss erlaubt.":
        "Reading increased faster than the configured maximum flow.",
    "Messzeitpunkt liegt vor der letzten gültigen Messung.": "The reading is older than the last accepted measurement.",
    "Der gelesene Stand liegt unter dem letzten OCR-Stand. Prüfe das Kamerabild.":
        "Reading lower than the previous OCR value. Check the image.",
    "Bild oder Messwert fehlt. Verbindung prüfen.": "Image or reading unavailable. Check the connection.",
    "Bild zu alt oder schon geprüft.": "This image is too old or has already been checked.",
    "Referenzwert fehlt oder ist ungültig.": "Reference reading missing or invalid.",
    "Ausschnitt ungültig. Koordinaten prüfen.": "Invalid crop. Check the coordinates.",
    "OCR fehlgeschlagen. Ziffernbereich prüfen.": "OCR failed. Check the digit area.",

    "Das Prüfergebnis konnte nicht gespeichert werden.": "Could not save the check result.",
    "Das Zählerbild oder die Messwerte sind nicht verfügbar. Bitte die ESP- bzw. Kameraverbindung prüfen.":
        "The meter image or reference data is unavailable. Check the ESP or camera connection.",
    "Das Bild ist zu alt oder wurde schon ausgewertet.":
        "This image is too old or has already been checked.",
    "Zählerstand nicht sicher erkannt. Prüfe die unklaren Stellen im Kamerabild.":
        "Meter reading uncertain. Please check the unclear digits in the camera image.",
    "Zählerstand nicht lesbar. Mindestens eine benötigte Ziffer konnte nicht erkannt werden. Prüfe das Kamerabild.":
        "Meter reading unreadable. At least one required digit was not recognized. Check the camera image.",
    "Der ESP meldet ein Problem mit der Zählerablesung. Prüfe den Wert direkt am ESP.":
        "The ESP reported a problem reading the meter. Please check the reading on the ESP.",
    "Die Messung am ESP wurde abgebrochen. Prüfe den ESP; die nächste Aufnahme folgt automatisch.":
        "The ESP's measurement was interrupted. Check the ESP and wait for the next image.",
    "Kein gültiger Vergleichswert verfügbar. Bitte den Referenzsensor prüfen oder eine neue Messung abwarten.":
        "No valid reference reading is available. Check the reference sensor or wait for a new reading.",
    "Der ESP liefert widersprüchliche Zählerwerte. Prüfe den angezeigten Stand am ESP.":
        "The ESP reports conflicting meter values. Check the reading displayed by the ESP.",
    "Der Bildausschnitt konnte nicht ausgewertet werden. Bitte die Ausschnitt-Koordinaten und die Breite der Vorkommastellen prüfen.":
        "The selected image region could not be analyzed. Check the crop coordinates and whole-digit width.",
    "Die Texterkennung ist fehlgeschlagen. Bitte den Ziffernbereich und die OCR-Installation prüfen.":
        "Text recognition failed. Check the digit area and the OCR installation.",
    "Zählerstand nicht sicher erkannt. Es liegt keine verwertbare OCR-Lesung vor. Bitte Bildausschnitt und Beleuchtung prüfen.":
        "Meter reading uncertain. No usable OCR reading is available. Check the crop and lighting.",
    "Zählerstand nicht sicher erkannt. Die Lesungen stimmen nicht zuverlässig überein. Bitte das Zählerbild prüfen.":
        "Meter reading uncertain. The OCR attempts did not consistently agree. Check the meter image.",
}


def translate_page(source):
    """Translate the static HTML/JavaScript template before .format() escapes it."""
    for german, english in sorted(EN_UI.items(), key=lambda entry: -len(entry[0])):
        source = source.replace(german, english)
    return source


def english_activity(state, detail):
    """Translate concise automatic worker activity, including attempt counters."""
    if detail in EN_UI:
        return EN_UI[detail]
    match = re.fullmatch(r"Zählerbild wird gelesen · Versuch (\d+) von (\d+)", str(detail or ""))
    if match:
        return f"Reading meter image · Attempt {match[1]} of {match[2]}"
    return "Automatic check in progress." if state == "working" else "Waiting for the next automatic check."


def english_uncertain_positions(readings, decimals):
    """Describe each unreliable digit relevant to the configured precision."""
    positions = uncertain_positions(readings, decimals)
    if positions is None:
        return "No digits read. Check the crop and lighting."
    if not positions:
        return "OCR uncertain. Check the image."
    groups = []
    for fractional, title in ((False, "Whole-number digits"), (True, "Decimal digits")):
        digits = [str(index) for is_fractional, index in positions if is_fractional == fractional]
        if digits:
            groups.append(title + ": " + ", ".join(digits) + ".")
    return "OCR uncertain. " + " ".join(groups)


def english_result(detail, status=None, decimals=0, readings=None):
    """Translate a saved result without changing the Home Assistant sensor state."""
    if not isinstance(detail, str):
        return "No result available."
    if detail in (LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, SEVENTH_DIGIT_PASS,
                  RAW_ROW_UNCLEAR, MANUAL_ROW_UNCLEAR, PARTLY_UNCLEAR,
                  STANDALONE_PENDING_NOTICE, STANDALONE_VERIFIED_NOTICE):
        return EN_UI[detail]
    if detail.startswith(STANDALONE_REJECTED_NOTICE):
        reason = detail.removeprefix(STANDALONE_REJECTED_NOTICE).strip()
        return " ".join(filter(None, (EN_UI[STANDALONE_REJECTED_NOTICE], EN_DETAILS.get(reason))))
    if detail in EN_DETAILS:
        return EN_DETAILS[detail]
    for prefix in (
        "Rohbild gelesen. Das aufbereitete ESP-Bild war nicht nutzbar – prüfe in AI on the Edge die Bildausrichtung und die Referenzmarken.",
        "Aufbereitetes ESP-Bild nicht nutzbar. Es konnte kein frisches Rohbild geladen werden.",
    ):
        if detail == prefix:
            return EN_UI[prefix]
        if detail.startswith(prefix + " "):
            return EN_UI[prefix] + " " + english_result(detail[len(prefix) + 1:], status, decimals, readings)
    if detail.startswith(FALLBACK_NOTICE + " "):
        reason = detail[len(FALLBACK_NOTICE) + 1:]
        translated = EN_DETAILS.get(reason.removeprefix("OCR: "), "")
        return " ".join(part for part in (EN_DETAILS[FALLBACK_NOTICE], translated) if part)
    if detail.startswith("Neue Vergleichsgenauigkeit gespeichert."):
        return EN_UI[
            "Neue Vergleichsgenauigkeit gespeichert. Die nächste automatische Prüfung zeigt das erste Ergebnis mit dieser Einstellung."
        ]
    if status == "ocr_unclear":
        return english_uncertain_positions(readings or [], decimals)
    if status == "match" and detail.startswith("Bestätigt: Die ersten ") and "ohne Rundung" in detail:
        return (f"Verified: The first {decimals} decimal places match the reference without rounding. "
                "The next digit is still unconfirmed.")
    if status == "difference" and detail.startswith("Abweichung: Die ersten ") and "ohne Rundung" in detail:
        return (f"Mismatch: The first {decimals} decimal places do not match the reference "
                "without rounding.")
    if status == "match":
        if decimals == 0:
            return "Confirmed: Whole cubic meters match. Decimal digits were ignored."
        place = "decimal place" if decimals == 1 else "decimal places"
        return f"Confirmed: OCR reading and reference match when rounded to {decimals} {place}."
    if status == "difference":
        if decimals == 0:
            return "Mismatch: Whole cubic meters do not match. Check the meter image."
        place = "decimal place" if decimals == 1 else "decimal places"
        return (f"Mismatch: The values do not match when rounded to {decimals} {place}. "
                "Check the meter image.")
    if status == "ocr_only":
        return ("Digits read, but not verified: No reference reading is available. "
                + ("Whole cubic meters only; decimals ignored." if decimals == 0
                   else f"Comparison precision: {decimals} decimal place(s)."))
    if status == "slfork_unclear":
        return "Reference reading uncertain. Check the ESP reading or reference sensor."
    if status == "stale_sample":
        return EN_DETAILS["Das Bild ist zu alt oder wurde schon ausgewertet."]
    if status == "capture_unavailable":
        return EN_DETAILS[
            "Das Zählerbild oder die Messwerte sind nicht verfügbar. Bitte die ESP- bzw. Kameraverbindung prüfen."
        ]
    return EN_DETAILS.get(detail, "Check completed. Please inspect the meter image and reference reading.")


def english_progress(message):
    """Localize progress updates including parameterized OCR attempt counts."""
    translations = {
        "Lade Zählerbild und Referenzdaten …": "Loading meter image and reference data …",
        "Aufbereitetes ESP-Bild fehlt oder ist zu alt. Die App prüft ein frisches Rohbild.":
            EN_UI["Aufbereitetes ESP-Bild fehlt oder ist zu alt. Die App prüft ein frisches Rohbild."],
        "Bild geladen – überprüfe Zeitstempel und Ziffernbereich …":
            "Image loaded – checking timestamp and digit area …",
        "Ergebnis wird gespeichert …": "Saving result …",
        "Prüfung beendet.": "Check complete.",
        "Anfrage angenommen – warte auf die Bildprüfung.":
            "Request accepted – waiting for the image check.",
        "Letzter manueller Test": "Last manual test",
        "Noch kein manueller Test gestartet.": "No manual check has been run yet.",
    }
    if message in translations:
        return translations[message]
    if isinstance(message, str):
        start = re.fullmatch(r"OCR-Prüfung gestartet \(max\. (\d+) Versuche\)\.", message)
        if start:
            return f"OCR analysis started (max. {start[1]} attempts)."
        attempt = re.fullmatch(r"Versuch (\d+) von (\d+) (läuft|abgeschlossen)(?: …|\.)", message)
        if attempt:
            phase, end = ("in progress", " …") if attempt[3] == "läuft" else ("complete", ".")
            return f"Attempt {attempt[1]} of {attempt[2]} {phase}{end}"
    return message or "No status message."
