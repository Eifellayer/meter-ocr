"""Live view of the background work for the overview.

With the box "Hintergrundarbeit anzeigen" ticked, the overview lists every piece of work the app
does beside the automatic check, shown like the check itself: whether it runs, what it does,
picture, digits read, progress and result. Pure formatting; it changes nothing.
"""

from experiments import EXPERIMENTS

EXPERIMENTS_EN = {"perspective": "Perspective correction (keystone)",
                  "seven_segment": "Digital display: read segments directly"}

STAGES = {
    "de": {"queued": "Wartet auf den Start", "capture": "Bild der letzten Prüfung übernehmen",
           "shortlist": "Rahmen vergleichen", "refine": "Rahmen fein nachjustieren",
           "angle": "Drehung prüfen", "digit_probe": "Position der letzten Rolle testen",
           "last_digit": "Letzte Rolle lesen", "ocr": "Ziffern lesen",
           "verify_wait": "Wartet auf das nächste Prüfbild zur Gegenprobe", "verify": "Gegenprobe"},
    "en": {"queued": "Waiting to start", "capture": "Taking over the picture of the last check",
           "shortlist": "Comparing frames", "refine": "Fine-tuning the frames",
           "angle": "Checking the rotation", "digit_probe": "Testing the position of the last roller",
           "last_digit": "Reading the last roller", "ocr": "Reading digits",
           "verify_wait": "Waiting for the next check picture to cross-check", "verify": "Cross-check"},
}

TEXT = {
    "de": {
        "fine": "Letzte Nachkommastelle bestimmen", "idle": "Auswertung zwischen den Prüfungen",
        "shadow": "Neue Leseverfahren testen (Schattenmodus)", "recovery": "Unklares Ergebnis nachprüfen",
        "running": "läuft", "waiting": "wartet", "done": "fertig", "skipped": "ausgelassen", "idle_state": "nichts zu tun",
        "with_check": "läuft parallel zur automatischen Prüfung",
        "wait_cpu": "Startet, sobald das Gerät zwischen zwei Prüfungen Kapazität frei hat.",
        "wait_images": "Wertet die Bilder der regulären Prüfungen aus, wenn das Gerät nicht ausgelastet ist.",
        "reason_experiment": "Neues Leseverfahren mit dem Bild der letzten Prüfung testen",
        "reason_unclear_check": "Unklare Stellen der letzten Prüfung erneut lesen",
        "reason_control": "Kontrolllesung",
        "busy": "Gerät war ausgelastet (Last {load}); der Test wird in der Wartezeit nachgeholt",
        "stable": "Bewährtes Verfahren", "no_result": "kein Ergebnis", "same": "gleich", "different": "abweichend",
        "reread": "Stelle {position}: {digit}", "nothing": "Seit dem Start der App gab es noch keine Hintergrundaufgaben.",
        "confirmed": "nicht nötig, Prüfung war bestätigt", "plan": "Versuch {done} von {total}",
        "reasons": {"hidden_known": "Nicht nötig: Die verdeckte Stelle ergänzt die App aus dem Zählerstand. Andere unklare Stellen liest sie in der Pause bis zur nächsten Prüfung noch einmal.",
                    "too_many_unclear": "Zu viele Stellen unklar – die nächste Prüfung versucht es mit einem neuen Bild.",
                    "matched": "nicht nötig, Prüfung war bestätigt", "disabled": "ausgeschaltet",
                    "paused": "Automatik pausiert", "no_capture_time": "Die Aufnahmezeit des Bildes fehlt.",
                    "fallback_reference": "Kein frischer Vergleichswert vorhanden."},
        "deferred": "läuft nur in der Pause zwischen zwei Prüfungen",
        "after_check": "wird nach dieser Prüfung ausgewertet",
        "results": {"shifted": "Rahmen verschoben, Wert gefunden", "timeout": "Zeitbudget aufgebraucht",
                    "found": "Wert gefunden", "none": "nichts gefunden"},
        "confirmations": "Bestätigungen {done} von {required}", "images": "Bilder: {images}",
        "gave_up": "Aufgegeben: letzte Ziffer nicht lesbar",
    },
    "en": {
        "fine": "Pinning down the last decimal", "idle": "Analysis between checks",
        "shadow": "Testing new reading methods (shadow mode)", "recovery": "Re-checking an unclear result",
        "running": "running", "waiting": "waiting", "done": "done", "skipped": "skipped", "idle_state": "nothing to do",
        "with_check": "runs alongside the automatic check",
        "wait_cpu": "Starts as soon as the device has spare capacity between two checks.",
        "wait_images": "Evaluates the pictures of the regular checks when the device is not busy.",
        "reason_experiment": "Testing a new reading method with the picture of the last check",
        "reason_unclear_check": "Re-reading unclear digits of the last check",
        "reason_control": "Control reading",
        "busy": "Device was busy (load {load}); the test is caught up in the waiting time",
        "stable": "Proven method", "no_result": "no result", "same": "same", "different": "different",
        "reread": "Position {position}: {digit}", "nothing": "No background tasks since the app started.",
        "confirmed": "not needed, the check was confirmed", "plan": "Attempt {done} of {total}",
        "reasons": {"hidden_known": "Not needed: the app fills in the hidden digit from the meter reading. Other unclear digits are read again in the pause before the next check.",
                    "too_many_unclear": "Too many digits unclear – the next check tries again with a new picture.",
                    "matched": "not needed, the check was confirmed", "disabled": "switched off",
                    "paused": "automatic checks paused", "no_capture_time": "The capture time of the picture is missing.",
                    "fallback_reference": "No fresh comparison value available."},
        "deferred": "runs only in the pause between two checks",
        "after_check": "evaluated after this check",
        "results": {"shifted": "frame shifted, value found", "timeout": "time budget used up",
                    "found": "value found", "none": "nothing found"},
        "confirmations": "Confirmations {done} of {required}", "images": "Images: {images}",
        "gave_up": "Given up: last digit not readable",
    },
}


def _text(language):
    return TEXT["en" if language == "en" else "de"]


def _entry(key, title, state, text, **fields):
    entry = {"id": key, "title": title, "state": state, "state_label": text.get(state, state),
             "step": "", "image": None, "reading": "", "completed": None, "total": None, "result": "", "at": None}
    entry.update({name: value for name, value in fields.items() if value is not None})
    return entry


def fine_search(status, language="de"):
    """The background calibration (intensive setup of the last digit, frame relocation)."""
    text = _text(language)
    if not isinstance(status, dict) or not status.get("background"):
        return None
    state = status.get("state")
    stages = STAGES["en" if language == "en" else "de"]
    running = state == "testing"
    if state in ("waiting", "testing"):
        shown = "running" if running else "waiting"
        step = stages.get(status.get("stage"), "") if running else text["wait_images"]
        result = ""
    else:
        shown = "done"
        step = ""
        result = text["gave_up"] if state == "gave_up" else state or ""
    candidates = status.get("candidates") or []
    selected = next((row for row in candidates if row.get("selected")), candidates[0] if candidates else None)
    details = [text["confirmations"].format(done=status.get("confirmations", 0), required=status.get("required", 3)),
               text["images"].format(images=status.get("tested", 0))]
    return _entry("fine", text["fine"], shown, text, step=step,
                  reading=(selected or {}).get("reading") or "", result=result or " · ".join(details),
                  completed=status.get("attempts"), total=status.get("max_attempts") if running else None)


def idle(record, pending, language="de"):
    """Waiting-time work: re-reading unclear digits or catching up on a skipped experiment."""
    text = _text(language)
    if record is None and not pending:
        return None
    if record is None or (pending and record.get("state") != "running"):
        reason = (pending or {}).get("reason", "")
        return _entry("idle", text["idle"], "waiting", text, step=text.get("reason_" + reason, reason),
                      image=(pending or {}).get("image"), result=text["wait_cpu"])
    reason = record.get("reason", "")
    step = text.get("reason_" + reason, reason)
    if record.get("state") == "running":
        return _entry("idle", text["idle"], "running", text, step=step, image=record.get("image"),
                      reading=record.get("stable") or "", at=record.get("at"))
    reread = record.get("reread") or []
    if reread:
        result = " · ".join(text["reread"].format(position=item.get("position"), digit=item.get("digit", "?"))
                            for item in reread if isinstance(item, dict))
    else:
        result = shadow_result(record.get("experiment"), language)
    return _entry("idle", text["idle"], "done", text, step=step, image=record.get("image"),
                  reading=record.get("stable") or "", result=result, at=record.get("at"))


def shadow_result(experiment, language="de"):
    text = _text(language)
    if not isinstance(experiment, dict):
        return ""
    if experiment.get("skipped"):
        return text["busy"].format(load=experiment.get("load", "?"))
    labels = EXPERIMENTS_EN if language == "en" else EXPERIMENTS
    stable = "".join(ch for ch in str(experiment.get("stable") or "") if ch.isdigit() or ch == "?")
    parts = []
    for name, label in labels.items():
        result = experiment.get(name)
        if not isinstance(result, dict):
            continue
        reading = result.get("reading")
        if not reading:
            verdict = text["no_result"]
        else:
            digits = "".join(ch for ch in str(reading) if ch.isdigit() or ch == "?")
            verdict = f"{reading} ({text['same'] if digits == stable and '?' not in digits else text['different']})"
        parts.append(f"{label}: {verdict}")
    return " · ".join(parts)


def shadow(record, automatic_running, language="de"):
    """Shadow mode of the last check (or of the waiting time)."""
    text = _text(language)
    if record is None:
        return None
    experiment = record.get("experiment") or {}
    if experiment.get("skipped") == "deferred":
        return _entry("shadow", text["shadow"], "waiting", text, image=record.get("image"),
                      step=text["deferred"], at=record.get("at"))
    state = "skipped" if experiment.get("skipped") else "done"
    return _entry("shadow", text["shadow"], state, text, image=record.get("image"),
                  reading=str(experiment.get("stable") or record.get("stable") or ""),
                  result=shadow_result(experiment, language), at=record.get("at"))


def recovery(record, automatic_running, language="de"):
    """Follow-up search of the last check (shifted frames for unclear digits)."""
    text = _text(language)
    if record is None:
        return None
    if automatic_running:
        # 0.5.33: while a check runs, the record still belongs to the previous check; its result
        # ("time budget used up") read as the result of the check that had only just started.
        return _entry("recovery", text["recovery"], "waiting", text, step=text["after_check"])
    log = record.get("recovery") or {}
    plan = log.get("plan") or {}
    if not log.get("tried"):
        reason = log.get("reason")
        return _entry("recovery", text["recovery"], "skipped", text, image=record.get("image"),
                      reading=record.get("ocr") or "",
                      result=text["confirmed"] if reason == "confirmed" else text["reasons"].get(reason, str(reason or "")),
                      at=record.get("at"))
    step = text["plan"].format(done=plan.get("done", 0), total=plan.get("total", 0)) if plan else ""
    result = text["results"].get(log.get("result"), str(log.get("result") or ""))
    return _entry("recovery", text["recovery"], "done", text, step=step, image=record.get("image"),
                  reading=log.get("pattern") or record.get("ocr") or "", result=result,
                  completed=plan.get("done"), total=plan.get("total"), at=record.get("at"))


def entries(state, calibration_status, pending, automatic_running, language="de"):
    """All background work, in a fixed order; an empty list gets one neutral line in the page."""
    found = [fine_search(calibration_status, language), idle(state.get("idle"), pending, language),
             shadow(state.get("shadow"), automatic_running, language),
             recovery(state.get("recovery"), automatic_running, language)]
    return [entry for entry in found if entry]
