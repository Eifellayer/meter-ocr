"""Status of the automatic check as shown on the overview: tone, heading and text.

Pure functions from a stored check result to what the user reads. Taken out of
``panel.py`` for 0.5.0; tests run without the web server.
"""

from datetime import datetime

from checks import (FRAME_OFF_NOTICE, FRAME_OFF_WAIT_NOTICE, LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, MOVING_DIGIT_NOTICE,
                    MOVING_NOTICES, STANDALONE_PENDING, STANDALONE_REJECTED_NOTICE, STANDALONE_VERIFIED_NOTICE,
                    WARNING_DETAIL_AFTER)
from checks import (HIDDEN_ESTIMATE_NOTICE, HIDDEN_FILLED_NOTICE, HIDDEN_FILLED_TURNING_NOTICE,
                    REDUCED_PRECISION2_NOTICE, REDUCED_PRECISION_NOTICE)
from consumption import EXCESSIVE_INCREASE, LOWER_PENDING, LOWER_READING
from i18n import EN_UI, english_result
from layout import MANUAL_ROW_UNCLEAR, PARTLY_UNCLEAR, RAW_ROW_UNCLEAR

QUIET_FAILURES = 3
CALM_PASS_NOTICES = (REDUCED_PRECISION_NOTICE, REDUCED_PRECISION2_NOTICE, HIDDEN_FILLED_NOTICE,
                     HIDDEN_FILLED_TURNING_NOTICE, HIDDEN_ESTIMATE_NOTICE)


def verdict(history, language, *, detail, precision_pending, paused, setup_pending, partial_eighth_digit, now,
            last_digit_given_up=False):
    """Tone, heading, icon and text for the last automatic check."""
    status = history.get("check_status") or history.get("status")
    tone = "neutral"
    heading = "Automatischer Prüfstatus"
    icon = ""
    incident = ""
    show_attempts = False
    if not precision_pending and status == "match":
        tone, heading, icon = "ok", "Zählerstand bestätigt", "✓"
    elif not precision_pending and status == STANDALONE_PENDING:
        heading = "Zweite Aufnahme steht aus"
    elif (not precision_pending and status == "ocr_only"
          and history.get("check_detail") == STANDALONE_VERIFIED_NOTICE):
        tone, heading, icon = "ok", "Zählerstand gegengeprüft", "✓"
    elif (not precision_pending and status == "ocr_only"
          and history.get("check_detail") in CALM_PASS_NOTICES):
        # 0.5.14 (B6): the check passed; a turning roller or a digit
        # filled from the meter reading is a remark, not a problem.
        tone, heading, icon = "ok", "Prüfung bestanden", "✓"
    elif not precision_pending and status == "match_with_warning":
        tone, heading, icon = "notice", "Prüfung bestanden mit Hinweis", ""
        if history.get("check_detail") == LAST_DIGIT_PASS:
            explanation = "Für den Verbrauch verwendet die App den plausiblen Vergleichswert."
            detail = f"{detail} {EN_UI[explanation] if language == 'en' else explanation}"
    elif not precision_pending and status in (
        "difference", "ocr_unclear", "slfork_unclear", "stale_sample", "capture_unavailable",
    ):
        failure_since = history.get("failure_since")
        prolonged = failure_since is not None and now - failure_since >= WARNING_DETAIL_AFTER
        tone, heading, icon = "warning", "Letzte Prüfung fehlgeschlagen", "!"
        if not prolonged and history.get("failure_attempts", 0) < QUIET_FAILURES:
            # A single failed check usually resolves itself with the next roller position.
            # Show it quietly; only repeated failures get the prominent warning.
            tone, icon = "notice", ""
        if prolonged:
            heading = "Zählerstand bitte prüfen"
            capture_failure_since = history.get("capture_failure_since", failure_since)
            if (status == "capture_unavailable" and capture_failure_since is not None
                    and now - capture_failure_since >= WARNING_DETAIL_AFTER):
                tone = "problem"
            incident = str(failure_since) if tone == "warning" else f"critical-{failure_since}"
            show_attempts = status == "ocr_unclear"
        elif status in ("stale_sample", "capture_unavailable") and not history.get("last_epoch"):
            heading = "Noch kein aktuelles Zählerbild"
            detail = ("The app retries automatically as soon as the image source delivers a new image."
                      if language == "en" else
                      "Die App versucht es automatisch erneut, sobald die Bildquelle ein neues Bild liefert.")
        else:
            detail = ""
        if str(history.get("check_detail", "")).startswith(STANDALONE_REJECTED_NOTICE):
            heading = "Aufnahmen stimmen nicht plausibel überein"
            detail = (history["check_detail"] if language == "de" else
                      english_result(history["check_detail"], status))
        elif history.get("check_detail") in (RAW_ROW_UNCLEAR, MANUAL_ROW_UNCLEAR, PARTLY_UNCLEAR):
            detail = history["check_detail"] if language == "de" else EN_UI[history["check_detail"]]
        elif history.get("check_detail") in MOVING_NOTICES:
            heading = "Rolle drehte sich gerade" if history.get("check_detail") == MOVING_DIGIT_NOTICE else "Rollen drehten sich gerade"
            detail = history["check_detail"] if language == "de" else english_result(history["check_detail"], status)
            # Everything but the turning last roller was read: no reason for "Bitte prüfen".
            tone, icon = "notice", ""
        elif history.get("check_detail") in (LOWER_PENDING, LOWER_READING, EXCESSIVE_INCREASE):
            heading = "Ablesung passt nicht zum letzten Stand"
            detail = history["check_detail"] if language == "de" else english_result(history["check_detail"], status)
        elif history.get("check_detail") == LAST_DIGIT_NOTICE:
            heading = "Letzte Nachkommastelle unsicher"
            detail = LAST_DIGIT_NOTICE if language == "de" else EN_UI[LAST_DIGIT_NOTICE]
        elif status == "difference":
            heading = "Ablesung und Vergleichswert weichen ab" if not prolonged else heading
            instructions = ("Vergleiche beide Werte mit dem Stand direkt am Zähler."
                            if prolonged or paused else
                            "Die App prüft automatisch erneut. Bleibt der Unterschied, vergleiche beide Werte mit dem Stand direkt am Zähler.")
            detail = instructions if language == "de" else EN_UI[instructions]
    if not precision_pending and history.get("check_detail") in (FRAME_OFF_NOTICE, FRAME_OFF_WAIT_NOTICE):
        heading = "Rahmen der letzten Stelle sitzt daneben"
        detail = (history["check_detail"] if language == "de"
                  else english_result(history["check_detail"], status))
        # The app handles this itself; no reason for "Bitte prüfen".
        if tone in ("ok", "warning", "notice"):
            tone, icon = ("neutral", icon) if tone == "ok" else ("notice", "")
    if language == "en":
        heading = EN_UI[heading]
    adjustment = history.get("ocr_rotation_adjustment", 0)
    if not precision_pending and status in ("match", "ocr_only") and type(adjustment) is int and adjustment:
        rotation_note = (f"Read with an image rotation of {adjustment:+d}°."
                         if language == "en" else f"Mit Bilddrehung von {adjustment:+d}° gelesen.")
        detail = " ".join(part for part in (detail, rotation_note) if part)
    grace = (not precision_pending and history.get("setup_first_check_unclear")
             and history.get("failure_attempts") == 1 and tone in ("warning", "notice"))
    if grace:
        tone, icon, incident = "neutral", "", ""
        heading = ("First automatic check still unclear" if language == "en" else
                   "Erste automatische Prüfung noch unklar")
        detail = ("The app will try again with a fresh image." if language == "en" else
                  "Die App prüft mit einem frischen Bild erneut.")
    # In the seven-digit mode the third decimal is compared only as far as it is
    # stable; the eighth digit is searched in the background for days. That is
    # normal operation, so the last-digit hint is not a warning there.
    last_digit_only = (partial_eighth_digit and not precision_pending
                       and history.get("check_detail") in (LAST_DIGIT_NOTICE, LAST_DIGIT_PASS))
    routine_ok = ((tone == "ok" or last_digit_only) and not paused and not setup_pending
                  and history.get("source_connection_status") != "error")
    if routine_ok and partial_eighth_digit:
        # Normal operation in the seven-digit mode: no warning. The hero note
        # above the reading already explains the eighth digit.
        tone, icon, incident = "ok", "✓", ""
        heading = ("All good. The 8th digit is still being confirmed." if language == "en"
                   else "Alles OK. Die 8. Ziffer wird noch abgesichert.")
        if last_digit_given_up:
            heading = ("All good. Checks run with 7 digits, the last roller was not found." if language == "en"
                       else "Alles OK. Prüfung mit 7 Ziffern, die letzte Rolle wurde nicht gefunden.")
        detail = ""
    elif routine_ok:
        heading = "All good. Automatic checks running." if language == "en" else "Alles OK. Automatik läuft."
        detail = ""
    return {"tone": tone, "heading": heading, "icon": icon, "incident": incident,
            "show_attempts": show_attempts, "detail": detail, "routine_ok": routine_ok}


def recovery(history, language, paused, zone):
    """(failed checks in a row, retries paused, the sentence that says what happens next)."""
    try:
        failure_attempts = max(0, int(history.get("failure_attempts", 0) or 0))
    except (TypeError, ValueError):
        failure_attempts = 0
    retry_suppressed = bool(history.get("retry_suppressed"))
    if failure_attempts and paused:
        recovery_notice = (f"Previous failed checks: {failure_attempts}. Automatic checks are paused."
                           if language == "en" else
                           f"Bisherige Fehlprüfungen: {failure_attempts}. Die Automatik ist pausiert.")
    elif failure_attempts and retry_suppressed:
        next_at = history.get("next_check_at")
        clock = (datetime.fromtimestamp(next_at, zone).strftime("%H:%M")
                 if type(next_at) in (int, float) and next_at > 0 else "")
        recovery_notice = (
            f"{failure_attempts} automatic checks failed. The app pauses briefly and then tries again."
            + (f" Next attempt at about {clock}." if clock else "")
            if language == "en" else
            f"{failure_attempts} automatische Prüfungen fehlgeschlagen. Die App pausiert kurz "
            "und versucht es dann erneut." + (f" Nächster Versuch gegen {clock} Uhr." if clock else "")
        )
    elif failure_attempts:
        recovery_notice = (
            f"Failed checks: {failure_attempts} of 3. The app will check again automatically."
            if language == "en" else
            f"Fehlprüfungen: {failure_attempts} von 3. Die App prüft automatisch erneut."
        )
    else:
        recovery_notice = ""
    return failure_attempts, retry_suppressed, recovery_notice
