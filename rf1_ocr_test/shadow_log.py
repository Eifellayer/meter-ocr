"""Own log for procedures in shadow mode, apart from the debug log (0.5.36).

A procedure in shadow mode runs beside the established one and changes neither published
values nor the behaviour of the app. Each entry says what the shadow procedure found and what
the established procedure did with the same picture, and whether both agree, so a procedure is
switched on only after it proved itself. Entries are written only while "Experimentelle
Funktionen testen" is on; with the switch off the procedures do not run at all.

One JSON object per line: time, function, image, shadow, established, agree (true, false or
null when the picture did not allow a comparison).
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock

SHADOW_LOG = Path("/data/schattenmodus-protokoll.jsonl")
MAX_ENTRIES = 1000
_lock = Lock()

# Shown in the app; the keys are the "function" values of the entries.
FUNCTIONS = {
    "decimal_estimate": "Schätzung unklarer Nachkommastellen",
    "standstill": "Stillstand per Bildvergleich",
    "perspective": "Perspektivkorrektur",
    "seven_segment": "Sieben-Segment-Erkennung",
    "orientation": "Ausrichtung des Kamerabilds",
}


def enabled(rules):
    """Shadow procedures run only with "Experimentelle Funktionen testen" switched on."""
    return isinstance(rules, dict) and bool(rules.get("experiments_enabled"))


def record(function, *, shadow, established=None, agree=None, image=None, **fields):
    """Append one entry; trim the file to the newest MAX_ENTRIES lines. Never raises."""
    entry = {"time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
             "function": function}
    if image:
        entry["image"] = image
    entry["shadow"] = shadow
    if established not in (None, "", [], {}):
        entry["established"] = established
    entry["agree"] = agree if agree in (True, False) else None
    for key, value in fields.items():
        if value not in (None, "", [], {}):
            entry[key] = value
    try:
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with _lock:
            lines = SHADOW_LOG.read_text(encoding="utf-8").splitlines() if SHADOW_LOG.exists() else []
            lines.append(line)
            if len(lines) > MAX_ENTRIES:
                lines = lines[-MAX_ENTRIES:]
            temporary = SHADOW_LOG.with_suffix(".tmp")
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(SHADOW_LOG)
    except (OSError, TypeError, ValueError):
        pass


def read_text(limit=None):
    try:
        lines = SHADOW_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    if limit:
        lines = lines[-limit:]
    return "\n".join(lines) + ("\n" if lines else "")


def clear():
    try:
        SHADOW_LOG.unlink()
    except OSError:
        pass


def summary(text):
    """Per function: entries, comparable entries, agreeing and differing ones, first and last time."""
    result = {}
    for line in str(text or "").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("function"), str):
            continue
        name = entry["function"]
        counted = result.setdefault(name, {"label": FUNCTIONS.get(name, name), "entries": 0, "compared": 0,
                                           "agree": 0, "differ": 0, "first": None, "last": None})
        counted["entries"] += 1
        if entry.get("agree") is True:
            counted["compared"] += 1
            counted["agree"] += 1
        elif entry.get("agree") is False:
            counted["compared"] += 1
            counted["differ"] += 1
        counted["first"] = counted["first"] or entry.get("time")
        counted["last"] = entry.get("time") or counted["last"]
    return result
