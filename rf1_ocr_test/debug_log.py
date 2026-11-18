"""Small rolling debug log of automatic and manual checks (no images, no credentials)."""

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock

DEBUG_LOG = Path("/data/debug-protokoll.jsonl")
MAX_ENTRIES = 600
_lock = Lock()


def _counter(counter):
    if not isinstance(counter, dict):
        return None
    keys = ("reading_litres", "anchor_litres", "pending_litres", "floor_litres", "total_litres")
    return {key: counter.get(key) for key in keys if key in counter}


def record(**fields):
    """Append one entry; trim the file to the newest MAX_ENTRIES lines. Never raises."""
    entry = {"time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
    for key, value in fields.items():
        if key == "consumption":
            value = _counter(value)
        if value not in (None, "", [], {}):
            entry[key] = value
    try:
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with _lock:
            lines = DEBUG_LOG.read_text(encoding="utf-8").splitlines() if DEBUG_LOG.exists() else []
            lines.append(line)
            if len(lines) > MAX_ENTRIES:
                lines = lines[-MAX_ENTRIES:]
            temporary = DEBUG_LOG.with_suffix(".tmp")
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(DEBUG_LOG)
    except (OSError, TypeError, ValueError):
        pass


def read_text(limit=None):
    try:
        lines = DEBUG_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    if limit:
        lines = lines[-limit:]
    return "\n".join(lines) + ("\n" if lines else "")


def clear():
    try:
        DEBUG_LOG.unlink()
    except OSError:
        pass
