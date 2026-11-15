"""German and English text for the RF1 ingress panel and OCR diagnostics.

The OCR and Home Assistant entity IDs stay language-neutral and unchanged.
The language only affects text shown in the ingress interface.
"""

import re

from checks import FALLBACK_NOTICE, uncertain_positions


EN_UI = {
    "Übersicht": "Overview",
    "Hauptmenü": "Main menu",
    "Fallback-Wert für diesen Test (optional)": "Fallback reading for this test (optional)",
    "Am markierten Bild ablesen und hier eintragen. Der Wert wird nur mit dem manuellen Test verglichen und nicht als automatische Referenz gespeichert.":
        "Read the marked image and enter the value here. It is compared only with the manual test and is not saved as the automatic reference.",
    "Über Meter OCR": "About Meter OCR",
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
    "Letzter bestätigter Abgleich": "Last confirmed match",
    "Einstellungen": "Settings",
    "Automatische Prüfung": "Automatic checks",
    "Prüfintervall (Minuten)": "Check interval (minutes)",
    "Zeit nach einer erfolgreichen Prüfung. Bei einem Fehler erfolgt der nächste Versuch spätestens nach fünf Minuten.":
        "Wait after a successful check. After a failure, retry within five minutes.",
    "Max. OCR-Versuche": "Max. OCR attempts",
    "Ziffernfarbe": "Digit color",
    "Bildbereich (links, oben, rechts, unten)": "Image region (left, top, right, bottom)",
    "Manueller Ausschnitt (links, oben, rechts, unten)": "Custom crop (left, top, right, bottom)",
    "Bilddrehung im Uhrzeigersinn": "Clockwise rotation",
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
    "Test starten": "Start test",
    "Testeinstellungen": "Test settings",
    "Zusätzliche Bild- und OCR-Einstellungen": "Advanced image and OCR settings",
    "Manueller Bildtest": "Manual image test",
    "Jetzt prüfen": "Run check now",
    "ⓘ Was passiert bei „Jetzt prüfen“?": "ⓘ What happens when I run a check?",
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
    "Rot:": "Red:",
    "Ziffer wurde gelesen": "Digit recognized",
    "Ziffer unklar": "Digit unclear",
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
    "Home-Assistant-Kamera (Livebild, Standbild je Prüfung)": "Home Assistant camera (live image, one snapshot per check)",
    "Home Assistant camera (snapshot per check)": "Home Assistant camera (live image, one snapshot per check)",
    "ⓘ Welcher Weg passt?": "ⓘ Which source should I choose?",
    "SLFork liefert Bild und Messwert. Bei einer Home-Assistant-Kamera kannst du einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest Meter OCR selbst und prüft die Werte auf Plausibilität.":
        "SLFork supplies the image and reading. With a Home Assistant camera, you can add a meter reading sensor, such as AI on the Edge, for comparison. Without one, Meter OCR reads the image itself and checks readings for plausibility.",
    "Anzeigeart": "Display type",
    "Ziffern vor dem Komma": "Digits before the decimal point",
    "Nachkommastellen auf dem Zähler": "Decimal places shown on the meter",
    "Verglichen wird bis": "Compare through",
    "Die Vergleichsgenauigkeit darf kleiner sein als die angezeigte Stellenzahl. Kleine Zeiger werden nicht automatisch gelesen; bei Rollen und Zeigern bitte nur die Ziffernrollen einstellen.":
        "You can compare fewer places than the meter shows. Small pointer dials are not read automatically; for a meter with rollers and dials, configure only the roller digits.",
    "Fallback-Zählerstand (optional)": "Fallback meter reading (optional)",
    "Stand abgelesen am": "Reading recorded at",
    "ⓘ Wie wird der Fallback verwendet?": "ⓘ How is the fallback used?",
    "Er ist ein Startwert, solange noch keine sichere automatische Ablesung gespeichert ist. Meter OCR prüft die erste Ablesung gegen den Zeitabstand und den maximalen Durchfluss. Danach wird der letzte bestätigte Stand als Referenz genutzt. Ohne Fallback beginnt die Plausibilitätsprüfung mit der ersten sicheren Ablesung.":
        "This is a starting value until a reliable automatic reading has been saved. Meter OCR checks the first reading against the elapsed time and maximum flow. After that, it uses the latest confirmed reading as its reference. Without a fallback, plausibility checks begin with the first reliable reading.",
    "OCR-Versuche pro Bild": "OCR attempts per image",
    "Prüfintervall (Minuten)": "Check interval (minutes)",
    "Breite des Vorkomma-Bereichs in Pixeln": "Width of whole-digit area in pixels",
    "ⓘ Bild einrichten": "ⓘ Set up the image",
    "Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Wenn sie das nicht schafft, öffne den manuellen Test: Dort wird das aktuelle Bild mit den erkannten Ziffern angezeigt. Einen getesteten Ausschnitt kannst du danach ausdrücklich für die Automatik übernehmen. Beim Livebild kann Meter OCR bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.":
        "Automatic detection tries to find the digit area. If it cannot, open the manual test to see the current image and recognized digits. You can explicitly apply a tested crop to automatic checks. For live images, Meter OCR can try up to 10 fresh snapshots within 20 seconds.",
    "SLFork liefert Bild und Messwert. Die Livebild-Quelle ruft bei jeder Prüfung ein aktuelles Standbild deiner Home-Assistant-Kamera ab; ein Video wird nicht dauerhaft ausgewertet. Du kannst dazu einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest Meter OCR selbst und prüft die Werte auf Plausibilität.":
        "SLFork supplies the image and reading. The live image source takes a fresh snapshot from your Home Assistant camera for each check; it does not continuously process video. You can add a meter reading sensor, such as AI on the Edge, for comparison. Without one, Meter OCR reads the image itself and checks readings for plausibility.",
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
    if detail in EN_DETAILS:
        return EN_DETAILS[detail]
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
        return (f"Confirmed: The OCR reading matches the reference through decimal place {decimals}.")
    if status == "difference":
        if decimals == 0:
            return "Mismatch: Whole cubic meters do not match. Check the meter image."
        return (f"Mismatch: The values do not match when comparing through decimal place {decimals}. "
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
