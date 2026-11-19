"""Prefilled GitHub issue for "Fehler melden" – without private data.

Only the app version, the kind of image source, the meter format, active experiments and
the share of failed checks are included. No addresses, entity IDs, tokens or images.
"""

from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlencode

ISSUES_URL = "https://github.com/Eifellayer/meter-ocr/issues/new"
SOURCE_KINDS = {"slfork": "AI on the Edge / SLFork", "slfork_camera": "ESP nur als Kamera",
                "esphome": "ESPHome-/Home-Assistant-Kamera", "camera": "Home-Assistant-Kamera"}
FAILED = ("ocr_unclear", "difference", "slfork_unclear", "stale_sample", "capture_unavailable")


def failure_share(log_text, now=None, hours=24):
    """Return (failed, total) automatic checks of the last hours from the debug log."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    failed = total = 0
    for line in log_text.splitlines():
        try:
            entry = json.loads(line)
            stamp = datetime.fromisoformat(entry["time"])
        except (ValueError, KeyError, TypeError):
            continue
        if entry.get("kind") != "automatic" or stamp < since:
            continue
        outcome = entry.get("outcome")
        if outcome == "standalone_pending":
            continue
        total += 1
        failed += outcome in FAILED
    return failed, total


def issue_url(version, source_mode, integer_digits, fraction_digits, experiments, log_text,
              language="de", now=None):
    failed, total = failure_share(log_text, now)
    share = f"{failed} von {total} ({round(100 * failed / total)} %)" if total else "keine Prüfungen"
    kind = SOURCE_KINDS.get(source_mode, "unbekannt")
    active = ", ".join(sorted(experiments)) or ("none" if language == "en" else "keine")
    if language == "en":
        share = f"{failed} of {total} ({round(100 * failed / total)} %)" if total else "no checks"
        body = (f"**What happened?**\n\n\n**What did you expect?**\n\n\n"
                f"---\nApp version: {version}\nImage source: {kind}\n"
                f"Meter format: {integer_digits} whole digits, {fraction_digits} decimals\n"
                f"Active experiments: {active}\nFailed checks (24 h): {share}\n\n"
                "Please attach the debug log (Tools → Debug log → Download log) and a screenshot if helpful. "
                "Do not include passwords, tokens or private photos.")
        title = f"[{version}] "
    else:
        body = (f"**Was ist passiert?**\n\n\n**Was hast du erwartet?**\n\n\n"
                f"---\nApp-Version: {version}\nBildquelle: {kind}\n"
                f"Zählerformat: {integer_digits} Vorkomma-, {fraction_digits} Nachkommastellen\n"
                f"Aktive Experimente: {active}\nFehlgeschlagene Prüfungen (24 h): {share}\n\n"
                "Bitte das Debug-Protokoll anhängen (Werkzeuge → Debug-Protokoll → Protokoll herunterladen), "
                "bei Bedarf einen Screenshot. Keine Passwörter, Tokens oder privaten Fotos einfügen.")
        title = f"[{version}] "
    return ISSUES_URL + "?" + urlencode({"template": "bug.yml", "title": title, "labels": "bug", "body": body})
