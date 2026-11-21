"""What shadow mode and the work between the checks delivered (0.5.0).

Reads the debug log and counts, per experiment, how often it ran and whether it read the same
digits as the stable check. Pure evaluation for the extended view; it changes nothing.
"""

import json
import re

from experiments import EXPERIMENTS


def _digits(value):
    return re.sub(r"[^0-9?]", "", str(value or ""))


def _same(stable, reading):
    """Compare only as many trailing-aligned digits as both sides have, ignoring the comma."""
    stable, reading = _digits(stable), _digits(reading)
    return bool(stable) and "?" not in reading and stable == reading


def _count(result, stable, entry):
    entry["runs"] += 1
    if not isinstance(result, dict) or result.get("error"):
        entry["errors"] += 1
        return
    reading = result.get("reading")
    if not reading:
        entry["no_result"] += 1
    elif _same(stable, reading):
        entry["same"] += 1
    elif "?" in _digits(reading):
        entry["unclear"] += 1
    else:
        entry["different"] += 1
    if isinstance(result.get("seconds"), (int, float)):
        entry["seconds"] += result["seconds"]


def summary(text):
    """Evaluate debug-log text (one JSON object per line); broken lines are skipped."""
    tested = {name: {"label": label, "runs": 0, "same": 0, "different": 0, "unclear": 0, "no_result": 0,
                     "errors": 0, "seconds": 0.0} for name, label in EXPERIMENTS.items()}
    result = {"checks": 0, "skipped_busy": 0, "experiments": tested, "last": None,
              "idle": {"runs": 0, "experiments": 0, "reread": 0, "resolved": 0, "last": None}}
    for line in str(text or "").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        kind, record = entry.get("kind"), entry.get("experiment")
        if kind == "automatic":
            result["checks"] += 1
        elif kind == "idle":
            idle = result["idle"]
            idle["runs"] += 1
            idle["last"] = entry.get("time")
            idle["experiments"] += 1 if isinstance(record, dict) else 0
            for item in entry.get("reread") or []:
                if isinstance(item, dict):
                    idle["reread"] += 1
                    idle["resolved"] += 1 if str(item.get("digit", "?")).isdigit() else 0
        else:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("skipped"):
            result["skipped_busy"] += 1
            continue
        for name, entry_count in tested.items():
            if name in record:
                _count(record[name], record.get("stable"), entry_count)
                result["last"] = entry.get("time")
    for entry_count in tested.values():
        runs = entry_count["runs"] - entry_count["errors"]
        entry_count["seconds"] = round(entry_count.pop("seconds") / runs, 2) if runs > 0 else None
    return result
