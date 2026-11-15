"""German and English text for the RF1 ingress panel and OCR diagnostics.

The OCR and Home Assistant entity IDs stay language-neutral and unchanged.
The language only affects text shown in the ingress interface.
"""

import re


EN_UI = {
    "Gaszähler OCR-Kontrolle": "Gas Meter OCR Verification",
    "Unabhängiger Bildabgleich deines Gaszählerstands mit der vorhandenen Messung. Die OCR liest die Ziffern erneut direkt aus dem Kamerabild – ohne den vom ESP erkannten Wert einfach zu übernehmen.":
        "Independent visual cross-check of your gas meter reading. Local OCR reads the digits again from the camera image instead of simply reusing the ESP's reading.",
    "Automatische Kontrolle": "Automatic verification",
    "Nächste Prüfung": "Next check",
    "Vergleichsgenauigkeit": "Comparison precision",
    "Vergleich": "Comparison",
    "Erkannter Stand": "OCR reading",
    "Referenz": "Reference",
    "Prüfergebnis": "Check result",
    "Bildzeit": "Image time",
    "Automatische Prüfung – Einstellungen": "Automatic checks – settings",
    "Max. OCR-Versuche": "Max. OCR attempts",
    "Ziffernfarbe": "Digit color",
    "Bildbereich (links, oben, rechts, unten)": "Image region (left, top, right, bottom)",
    "Manueller Ausschnitt (links, oben, rechts, unten)": "Custom crop (left, top, right, bottom)",
    "Breite der Vorkommastellen": "Width of whole-number digits",
    "Bildbereich": "Image region",
    "Speichern": "Save",
    "Gilt dauerhaft ab der nächsten automatischen Prüfung. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.":
        "Saved rules apply from the next automatic check and persist after restart. Changing the comparison precision resets the confirmation count.",
    "Manuellen Test öffnen": "Open manual test",
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
    "Status wird geladen …": "Loading status …",
    "Test angenommen. Die Bearbeitung wird hier live angezeigt.":
        "Request accepted. Progress will appear here live.",
    "Jetzt fällig": "Due now",
}

EN_DETAILS = {
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


def english_uncertain_positions(readings, decimals, *, manual=False):
    """Describe each unreliable digit relevant to the configured precision."""
    if not readings:
        return EN_DETAILS[
            "Zählerstand nicht sicher erkannt. Es liegt keine verwertbare OCR-Lesung vor. Bitte Bildausschnitt und Beleuchtung prüfen."
        ]
    positions = list(range(5)) + list(range(6, 6 + decimals))
    uncertain = []
    for pos in positions:
        chars = {str(value)[pos] if len(str(value)) > pos else "?" for value in readings}
        if len(chars) == 1 and all(char.isdigit() for char in chars):
            continue
        place = f"whole-number digit {pos + 1} from the left" if pos < 5 else f"decimal digit {pos - 5}"
        candidates = sorted(char for char in chars if char.isdigit())
        if len(candidates) > 1:
            place += " (read as " + " or ".join(candidates) + ")"
        uncertain.append(place)
    if not uncertain:
        return "Meter reading uncertain. The OCR attempts did not consistently agree. Check the image."
    return ("Meter reading uncertain. Unclear positions: " + "; ".join(uncertain) +
            (". See individual attempts under 'More details'." if manual
             else ". Check the image crop, lighting, and digits."))


def english_result(detail, status=None, decimals=0, readings=None, *, manual=False):
    """Translate a saved result without changing the Home Assistant sensor state."""
    if not isinstance(detail, str):
        return "No result available."
    if detail in EN_DETAILS:
        return EN_DETAILS[detail]
    if detail.startswith("Neue Vergleichsgenauigkeit gespeichert."):
        return EN_UI[
            "Neue Vergleichsgenauigkeit gespeichert. Die nächste automatische Prüfung zeigt das erste Ergebnis mit dieser Einstellung."
        ]
    if status == "ocr_unclear":
        return english_uncertain_positions(readings or [], decimals, manual=manual)
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
