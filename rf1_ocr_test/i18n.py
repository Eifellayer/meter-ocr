"""German and English text for the RF1 ingress panel and OCR diagnostics.

The OCR and Home Assistant entity IDs stay language-neutral and unchanged.
The language only affects text shown in the ingress interface.
"""

import re

from checks import (FALLBACK_NOTICE, LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, STANDALONE_PENDING_NOTICE,
                    STANDALONE_REJECTED_NOTICE, STANDALONE_VERIFIED_NOTICE, uncertain_positions)
from layout import MANUAL_ROW_UNCLEAR, RAW_ROW_UNCLEAR


EN_UI = {
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
    "Selbstreparatur bei wiederholten Fehlmessungen": "Self-repair after repeated failed readings",
    "Nach zehn unterschiedlichen Fehlmessungen sichert die App den bisherigen Rahmen und versucht einmal, ihn zu verbessern. Ohne sichere Gegenprobe bleibt der bisherige Rahmen gültig.":
        "After ten distinct failed readings, the app backs up the current crop and tries once to improve it. The current crop stays in use until a replacement passes verification.",
    "Zehn Fehlmessungen. Bitte Bildausschnitt prüfen.": "Ten failed readings. Check the image crop.",
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
    "Prüfe den nächsten Rahmen …": "Checking the next crop …",
    "Ziffernfeld manuell markieren": "Mark digit row manually",
    "Einzelziffernsuche. Offene Stellen von links: ": "Individual digit search. Uncertain positions from the left: ",
    "Ziffernfeld lesbar. Die App wartet auf einen höheren Zählerstand oder einen abgelesenen Startwert.": "The digit row is readable. The app is waiting for a higher reading or a starting reading you enter.",
    "Ziffernfeld bestätigt. Die App prüft mit dem nächsten neuen Bild weiter.": "Digit row confirmed on this image. The app will check again with the next new image.",
    "Ziffernfeld nicht gefunden. Grenze das Ziffernfeld im Kamerabild ein.": "Digit row not found. Mark the digit row in the camera image.",
    "Kein gültiger Vergleichswert für dieses Bild. Die App wartet auf eine neue Messung.": "No valid reference for this image. The app is waiting for a new measurement.",
    "Der gelesene Bereich passt nicht zum Vergleichswert. Prüfe den Vergleichswert und markiere das Ziffernfeld.": "The area read does not match the reference. Check the reference and mark the digit row.",
    "Ziffernfeld auswählen ": "Select digit row ",
    "Die Ziffernreihe scheint gegenüber der Referenz um eine Stelle verschoben.": "The digit row appears shifted by one position relative to the reference.",
    "Kein neues Kamerabild erhalten. Prüfe die Bildquelle.": "No new camera image received. Check the image source.",
    "Grobkalibrierung: Suche nach der Ziffernreihe …": "Coarse calibration: Looking for the digit row …",
    "Feinkalibrierung: Prüfe Rahmen und Drehung am vorhandenen Bild …": "Fine calibration: Testing digit boxes and rotation on the current image …",
    "Noch kein Ziffernbereich gefunden. Warte auf ein neues Bild …": "No digit region found yet. Waiting for a new image …",
    "In diesem Bild wurde kein Ziffernbereich gefunden.": "No digit region was found in this image.",
    "Der Ausschnitt ließ sich nicht auswerten.": "This crop could not be processed.",
    "Mindestens eine benötigte Ziffer blieb unklar.": "At least one required digit remained unclear.",
    "Die OCR-Versuche lieferten unterschiedliche Ziffern.": "The OCR attempts read different digits.",
    "Kein gültiger Vergleichswert zu diesem Bild.": "No valid reference reading for this image.",
    "Der gelesene Stand weicht vom Vergleichswert ab.": "The OCR reading differs from the reference.",
    "Der Stand passt zeitlich nicht zur letzten sicheren Ablesung.": "The reading is implausible given the last confirmed reading and elapsed time.",
    "Der Rahmen ist lesbar. Die App wartet auf einen plausiblen Zähleranstieg.": "The crop is readable. Waiting for a plausible meter increase.",
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
    "Warte auf einen neuen Messzyklus vom ESP …": "Waiting for a new ESP measurement cycle …",
    "Verstrichene Zeit der Selbsteinrichtung": "Elapsed automatic setup time",
    "Selbsteinrichtung startet, sobald die laufende Prüfung beendet ist …":
        "Automatic setup will start once the current check finishes …",
    "Kamerabild wird abgerufen …": "Fetching a camera image …",
    "Suche nach der Ziffernreihe …": "Looking for the digit row …",
    "Prüfe Rahmen ": "Checking frame ",
    " mit Drehung ": " at a rotation of ",
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
    "Warte auf ein neues Kamerabild …": "Waiting for a new camera image …",
    "Prüfe Ausschnitt und Drehung …": "Checking crop and rotation …",
    "Selbsteinrichtung prüft Bildausschnitt und Drehung.": "Automatic setup is checking the crop and rotation.",
    "Erfolgreich eingerichtet. Ausschnitt und Drehung sind übernommen.": "Setup successful. Crop and rotation saved.",
    "Rahmen gefunden. Warte auf ein frisches Bild zur Gegenprüfung …": "Crop found. Waiting for a fresh image to cross-check …",
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
    "Die letzte Stelle kann beim Weiterdrehen schwer lesbar sein. Das kann zu Fehlmeldungen führen.":
        "The last digit can be hard to read as it turns, which can cause false alerts.",
    "Präzisionsmodus: Alle drei Nachkommastellen müssen stimmen": "Precision mode: Require all three decimal places to match",
    "Prüfung bestanden mit Hinweis": "Check passed with a note",
    "Test bestanden mit Hinweis": "Test passed with a note",
    "Letzte Nachkommastelle unsicher": "Last decimal digit uncertain",
    LAST_DIGIT_NOTICE: "Only the third decimal digit is unclear or differs.",
    "Dritte Nachkommastelle intensiv suchen": "Run intensive search for the third decimal digit",
    "Dritte Nachkommastelle manuell markieren": "Mark the third decimal digit manually",
    "Ausschnitt und Drehung gespeichert. Zwei Nachkommastellen bestätigt, die dritte bleibt unbestätigt.":
        "Crop and rotation saved. Two decimal digits confirmed. The third remains unconfirmed.",
    "Die dritte Nachkommastelle ist bei Rollen oft schwer zu erkennen. „Ausschnitt und Drehung lernen“ bestätigt bei der Ersteinrichtung die ersten zwei Stellen. Die dritte bleibt unbestätigt und kann später intensiv gesucht oder im Kamerabild manuell markiert werden.":
        "The third decimal digit on a roller can be hard to read. During initial setup, Learn crop and rotation confirms the first two decimal digits. The third remains unconfirmed. You can run an intensive search or mark it manually on the camera image later.",
    "Dritte Nachkommastelle bestätigt. Die Ziffernrahmen sind übernommen.":
        "Third decimal digit confirmed. The digit frames have been saved.",
    "Dritte Nachkommastelle bleibt unbestätigt. Du kannst später erneut suchen oder sie manuell markieren.":
        "The third decimal digit remains unconfirmed. Search again later or mark it manually.",
    "Ausschnitt gespeichert. Suche jetzt gezielt nach der dritten Nachkommastelle …":
        "Crop saved. Now searching specifically for the third decimal digit …",
    "Prüfe denselben Rahmen mit dem nächsten neuen Bild weiter.":
        "Continuing to check the same crop on the next new image.",
    "Der Ausschnitt ist deutlich weniger scharf oder kontrastreich als zuvor. Warte auf ein besseres Bild.":
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
    "Treffer gesammelt. Warte auf ein frisches Bild für die Gegenprobe.":
        "Matches collected. Waiting for a fresh image for verification.",
    " · Beste Kandidaten: ": " · Best candidates: ",
    "Teste die vermutete Position der letzten Rolle auf diesem Bild …":
        "Testing the estimated position of the last roller on this image …",
    " Vorschlag für die letzte Rolle gefunden. Warte auf Bestätigung mit einem neuen Bild.":
        " Candidate for the last roller found. Waiting for confirmation on a new image.",
    " Für den Rahmen zählen die ersten zwei Nachkommastellen.":
        " The first two decimal digits count toward crop confirmation.",
    " · Feinprüfung der dritten Stelle: ": " · Third-digit verification: ",
    "Grün: gelesen. Gelb: OCR-Versuche weichen ab. Gelb mit ?: Stelle vermutet, Ziffer nicht lesbar. Rot: unklar.":
        "Green: read. Yellow: OCR attempts disagree. Yellow with ?: probable position, unreadable digit. Red: unclear.",
    "Rahmen mit 100 % Übereinstimmung gefunden. Die Intensivprüfung bleibt bei diesem Rahmen und wartet auf ein neues Bild.":
        "Crop found with 100% agreement. The intensive check keeps this crop and waits for a new image.",
    "Ziffernfeld ist lesbar.": "The digit row is readable.",
    " Ohne Vergleichswert wartet die App auf einen plausiblen Anstieg oder einen Startwert.":
        " Without a reference, the app waits for a plausible increase or a starting reading.",
    "Drei Treffer mit 100 %: Grobprüfung beendet. Warte auf ein frisches Bild für die Gegenprobe.":
        "Three matches at 100%: coarse search complete. Waiting for a fresh image for verification.",
    " · Schwankende Stellen im Intensivtest (von links): ": " · Unstable positions in the intensive check (from the left): ",
    "Bester Treffer der Feinprüfung · ": "Best fine-check result · ",
    "Feinprüfung erfolgreich, Gegenprobe offen. Der beste Rahmen steht für den manuellen Test bereit.":
        "Fine check passed, independent verification pending. The best crop is available for the manual check.",
    LAST_DIGIT_PASS: "The first two decimal places match. The third digit remains unconfirmed.",
    "Für den Verbrauch verwendet die App den plausiblen Vergleichswert.": "The app uses the plausible reference reading to calculate consumption.",
    "Ablesung und Vergleichswert weichen ab": "Image reading and reference differ",
    "Vergleiche beide Werte mit dem Stand direkt am Zähler.": "Compare both readings with the value on the meter itself.",
    "Die App prüft automatisch erneut. Bleibt der Unterschied, vergleiche beide Werte mit dem Stand direkt am Zähler.":
        "The app will check again automatically. If the readings still differ, compare both with the value on the meter itself.",
    "Letzte automatische Erkennung": "Latest automatic reading",
    "Schließen": "Close",
    "Originalbild zum Ablesen": "Original image for reading",
    "Später einrichten": "Set up later",
    "Du kannst die Einrichtung jederzeit über „Einrichtung öffnen“ erneut starten.":
        "You can restart setup at any time using “Open setup wizard”.",
    "Stand im Home-Assistant-Dashboard anzeigen": "Show the reading on a Home Assistant dashboard",
    "Wenn AI Meter Reader selbst aus einer ESPHome- oder Home-Assistant-Kamera liest, kannst du den Sensor „OCR-Zählerstand“ zum Dashboard hinzufügen. Seine Entitäts-ID lautet ":
        "When AI Meter Reader reads directly from an ESPHome or Home Assistant camera, you can add its OCR meter reading sensor to your dashboard. Its entity ID is ",
    "Oder füge diese kurze YAML-Konfiguration in eine manuelle Karte ein:":
        "Or paste this short YAML configuration into a manual card:",
    "App-Daten zurücksetzen": "Reset app data",
    "Setzt die AI-Meter-Reader-Einstellungen und Prüfhistorie auf Standardwerte zurück und entfernt gespeicherte Testbilder. Die Home-Assistant-App-Konfiguration und vorhandenen Entitäten bleiben erhalten.":
        "Resets AI Meter Reader settings and check history to defaults and removes saved test images. Home Assistant app configuration and existing entities are kept.",
    "Auf Werkseinstellungen zurücksetzen": "Restore factory settings",
    "Werkseinstellungen wiederherstellen?": "Restore factory settings?",
    "Gespeicherte Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie und Testbilder werden zurückgesetzt. Home-Assistant-App-Konfiguration und Entitätsnamen bleiben erhalten.":
        "Saved image source, OCR and notification settings, check history, and test images will be reset. Home Assistant app configuration and entity IDs will be kept.",
    "Abbrechen": "Cancel",
    "Jetzt zurücksetzen": "Reset now",
    "Werkreset angefordert. Eine laufende Prüfung kann den Reset verzögern. Bitte warte, bis sich die Einrichtung öffnet.":
        "Factory reset requested. A check in progress may delay the reset. Please wait for setup to open.",
    "Werkseinstellungen wiederhergestellt. Die Einrichtung öffnet sich erneut.":
        "Factory settings restored. Setup will open again.",
    "Werkreset läuft noch. Die Einrichtung öffnet sich, sobald er fertig ist.":
        "The reset is still running. Setup will open when it finishes.",
    "Werkreset konnte nicht vollständig ausgeführt werden.":
        "The reset could not be completed.",
    "Die Einrichtung konnte nicht übersprungen werden.": "Setup could not be skipped.",
    "Übersicht": "Overview",
    "Hauptmenü": "Main menu",
    "Ansichten": "Views",
    "Bebilderte Bedienungsanleitung (PDF)": "Illustrated user guide (PDF)",
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
    "Nach einem fehlgeschlagenen automatischen Test folgen bis zu zwei weitere Prüfungen im Abstand von fünf Minuten. Sind alle drei erfolglos, wartet die App eine Stunde und prüft dann erneut. Nach Erfolg gilt wieder dein eingestelltes Intervall. Ein kürzeres Intervall kann helfen, wenn sich der Zähler beim Weiterdrehen vorübergehend schlecht lesen lässt.":
        "After a failed automatic check, up to two more checks follow at five-minute intervals. If all three fail, the app waits one hour before trying again. After a successful check, your selected interval applies again. A shorter interval can help when the meter is temporarily hard to read as it turns.",
    "Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben alle drei Prüfungen erfolglos, wartet AI Meter Reader eine Stunde auf einen höheren Zählerstand oder ein neues Bild und versucht es dann erneut. Beleuchtung, Abstand und Fokus prüfen.": "After a failed automatic check, up to two more image checks follow at five-minute intervals. If all three fail, AI Meter Reader waits one hour for a higher reading or a new image, then tries again. Check lighting, distance, and focus.",
    "Wartet auf die nächste automatische Prüfung.": "Waiting for the next automatic check.",
    "App läuft. Wartet auf die nächste automatische Prüfung.": "App is running and waiting for the next automatic check.",
    "Automatik:": "Automatic checks:",
    "Einrichtung erforderlich. Bitte Bildquelle festlegen.": "Setup required. Choose an image source.",
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
    "Rohbild gelesen. Mögliche Ursache: Bildausrichtung oder Referenzmarken in AI on the Edge.": "Raw image read. Possible cause: image alignment or reference markers in AI on the Edge.",
    "Kamera erreichbar. Frisches Bild empfangen.": "Camera reachable. Fresh image received.",
    "ESP erreichbar, aber Bild ist älter als 15 Minuten oder hat einen ungültigen Zeitstempel.": "ESP reachable, but the image is older than 15 minutes or has an invalid timestamp.",
    "Kamera erreichbar, aber das Bild hat einen ungültigen Zeitstempel.": "Camera reachable, but the image has an invalid timestamp.",
    "ESP erreichbar. Seit der letzten Prüfung kam kein neues Bild; das vorhandene Bild ist noch nicht veraltet.": "ESP reachable. No new image since the last check; the current image is not stale yet.",
    "Home-Assistant-Kamera erreichbar; dieses Bild wurde bereits geprüft.": "Home Assistant camera reachable; this image was already checked.",
    "Home-Assistant-Kamera nicht erreichbar oder Bild unlesbar. Kamera und Zugriff prüfen.": "Home Assistant camera unavailable or image unreadable. Check the camera and access.",
    "ESP nicht erreichbar oder Antwort unvollständig. Adresse und Verbindung prüfen.": "ESP unavailable or response incomplete. Check its address and connection.",
    "Kamerabild wird aufgenommen.": "Capturing a fresh camera image.",
    "Einstellungen gespeichert. Prüfung startet gleich.": "Settings saved. The check is about to start.",
    "Automatische Prüfung startet …": "Starting the automatic check …",
    "Warte auf ein Kamerabild …": "Waiting for a camera image …",
    "Warte auf Bild und Messwerte vom ESP …": "Waiting for the image and reading from the ESP …",
    "Warte auf ein aktuelles Bild vom ESP …": "Waiting for a new image from the ESP …",
    "Intensivtest: Prüfe eine leicht gedrehte Aufnahme.": "Recovery check: testing a slightly rotated image.",
    "Noch kein aktuelles Zählerbild": "No current meter image yet",
    "Fortschritt der automatischen Prüfung": "Automatic check progress",
    "Einstellungen werden gespeichert …": "Saving settings …",
    "Bild und Messwerte werden vom ESP abgerufen.": "Fetching the image and reading from the ESP.",
    "Bild wird vorbereitet.": "Preparing the image.",
    "Automatische Prüfung wird abgeschlossen.": "Finishing the automatic check.",
    "Letzte Prüfung beendet. Nächster Versuch nach kurzer Wartezeit.": "Last check finished. The next attempt follows after a short wait.",
    "Letzte Prüfung beendet. Wartet auf das eingestellte Prüfintervall.": "Last check finished. Waiting for the selected check interval.",
    "Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben alle drei Prüfungen erfolglos, wartet die App eine Stunde auf einen höheren Zählerstand oder ein neues Bild. Beleuchtung, Abstand und Fokus prüfen.": "After a failed automatic check, up to two more image checks follow at five-minute intervals. If all three fail, the app waits one hour for a higher reading or a new image. Check lighting, distance, and focus.",
    "Nach drei fehlgeschlagenen automatischen Prüfungen mit unterschiedlichen Bildabrufen wartet die App eine Stunde und versucht es dann erneut. Nach einem erfolgreichen Abgleich gilt wieder dein eingestelltes Prüfintervall. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.": "After three failed automatic checks using different image captures, the app waits one hour and tries again. After a successful match, the selected interval applies again. Changing comparison precision resets the match count.",
    "Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Bei einer unsicheren Ablesung folgen bis zu zehn zusätzliche Bildauswertungen; die App setzt einzelne Ziffern nur bei einer strikten Mehrheit zusammen. Nach drei fehlgeschlagenen automatischen Prüfungen mit unterschiedlichen Bildabrufen wartet sie eine Stunde auf ein neues Bild oder einen höheren Zählerstand. Prüfe bei wiederholten Fehlern auch Beleuchtung, Abstand und Fokus. Beim Livebild kann AI Meter Reader bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.": "Automatic detection tries to find the digit area. If a reading is uncertain, up to ten extra image analyses follow; digits are combined only when a strict majority agrees. After three failed automatic checks using different image captures, the app waits one hour for a higher reading or a new image. If errors continue, check lighting, distance, and focus. For live images, AI Meter Reader can try up to 10 fresh snapshots within 20 seconds.",
    "SLFork liefert Bild und Messwert. Die Livebild-Quelle ruft bei jeder Prüfung ein aktuelles Standbild deiner Home-Assistant-Kamera ab; ein Video wird nicht dauerhaft ausgewertet. Du kannst dazu einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest AI Meter Reader selbst und prüft die Werte auf Plausibilität.": "SLFork supplies the image and reading. The live image source takes a fresh snapshot from your Home Assistant camera for each check; video is not continuously processed. You can add a meter reading sensor, such as AI on the Edge, for comparison. Without a reference sensor, AI Meter Reader reads the image itself and checks plausibility.",
    "Er ist ein Startwert, solange noch keine sichere automatische Ablesung gespeichert ist. AI Meter Reader prüft die erste Ablesung gegen den Zeitabstand und den maximalen Durchfluss. Danach wird der letzte bestätigte Stand als Referenz genutzt. Ohne Fallback beginnt die Plausibilitätsprüfung mit der ersten sicheren Ablesung.": "This is a starting value until a reliable automatic reading is saved. AI Meter Reader checks the first reading against elapsed time and maximum flow. After that, it uses the latest confirmed reading as its reference. Without a fallback, plausibility checks begin with the first reliable reading.",
    "Letzter bestätigter Abgleich": "Last confirmed match",
    "Einstellungen": "Settings",
    "Automatische Prüfung": "Automatic checks",
    "Prüfintervall (Minuten)": "Check interval (minutes)",
    "Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Bleiben alle drei Prüfungen erfolglos, wartet AI Meter Reader eine Stunde auf einen höheren Zählerstand oder ein neues Bild und versucht es dann erneut. Beleuchtung, Abstand und Fokus prüfen.":
        "After a failed automatic check, up to two more image checks follow at five-minute intervals. If all three fail, AI Meter Reader waits one hour for a higher reading or a new image, then tries again. Check lighting, distance, and focus.",
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
    "Kein Bild vorhanden. Bitte Bildquelle und Verbindung prüfen und den manuellen Test erneut starten.":
        "No image available. Check the image source and connection, then run the manual test again.",
    "Ziffernrollen": "Number rollers",
    "Digitales Zifferndisplay": "Digital numeric display",
    "Ziffernrollen plus Zeiger": "Number rollers plus pointers",
}

EN_DETAILS = {
    FALLBACK_NOTICE: "The ESP is using a fallback reading.",
    "OCR-Zuwachs plausibel. Warte auf den Abgleich.": "OCR increase looks plausible. Waiting for a match.",
    "Für die Plausibilitätsprüfung fehlt ein gültiger Messzeitpunkt.":
        "A valid measurement time is needed to assess the change.",
    "OCR-Stand unsicher.": "OCR reading uncertain.",
    "Zählerstand liegt unter dem letzten gültigen Wert.": "Reading is lower than the last accepted value.",
    "Zählerstand steigt schneller als der eingestellte Durchfluss erlaubt.":
        "Reading increased faster than the configured maximum flow.",
    "Messzeitpunkt liegt vor der letzten gültigen Messung.": "The reading is older than the last accepted measurement.",
    "Der gelesene Stand liegt unter dem letzten OCR-Stand. Bitte das Kamerabild prüfen.":
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
    "Zählerstand nicht sicher erkannt. Bitte die unklaren Stellen im Kamerabild prüfen.":
        "Meter reading uncertain. Please check the unclear digits in the camera image.",
    "Zählerstand nicht lesbar. Mindestens eine benötigte Ziffer konnte nicht erkannt werden. Bitte das Kamerabild prüfen.":
        "Meter reading unreadable. At least one required digit was not recognized. Check the camera image.",
    "Der ESP meldet ein Problem mit der Zählerablesung. Bitte den Wert direkt am ESP prüfen.":
        "The ESP reported a problem reading the meter. Please check the reading on the ESP.",
    "Die Messung am ESP wurde abgebrochen. Bitte den ESP prüfen und die nächste Aufnahme abwarten.":
        "The ESP's measurement was interrupted. Check the ESP and wait for the next image.",
    "Kein gültiger Vergleichswert verfügbar. Bitte den Referenzsensor prüfen oder eine neue Messung abwarten.":
        "No valid reference reading is available. Check the reference sensor or wait for a new reading.",
    "Der ESP liefert widersprüchliche Zählerwerte. Bitte den angezeigten Stand am ESP prüfen.":
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
    match = re.fullmatch(r"Lese Zählerbild: OCR-Versuch (\d+) von (\d+) (?:läuft|abgeschlossen)\.", str(detail or ""))
    if match:
        return f"Reading meter image: OCR attempt {match[1]} of {match[2]}."
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
    if detail in (LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, RAW_ROW_UNCLEAR, MANUAL_ROW_UNCLEAR,
                  STANDALONE_PENDING_NOTICE, STANDALONE_VERIFIED_NOTICE):
        return EN_UI[detail]
    if detail.startswith(STANDALONE_REJECTED_NOTICE):
        reason = detail.removeprefix(STANDALONE_REJECTED_NOTICE).strip()
        return " ".join(filter(None, (EN_UI[STANDALONE_REJECTED_NOTICE], EN_DETAILS.get(reason))))
    if detail in EN_DETAILS:
        return EN_DETAILS[detail]
    for prefix in (
        "Rohbild gelesen. Mögliche Ursache: Bildausrichtung oder Referenzmarken in AI on the Edge.",
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
        attempt = re.fullmatch(r"OCR-Versuch (\d+) von (\d+) (läuft …|abgeschlossen\.)", message)
        if attempt:
            return (f"OCR attempt {attempt[1]} of {attempt[2]} " +
                    ("in progress …" if attempt[3] == "läuft …" else "completed."))
    return message or "No status message."
