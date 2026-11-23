"""Debug log of a chosen period for sharing with the support, without device names (0.5.39).

Users should not have to black out anything themselves before they attach the log to a public
issue. Meter readings, times and reading results stay; Home Assistant entity names, the names
and addresses of the image source, web and network addresses, e-mail addresses and anything
that looks like a key or token are replaced.
"""

from datetime import datetime, timedelta
import json
import re

PERIODS = {"1": 1, "6": 6, "24": 24, "72": 72, "all": None}
DEVICE = "<gerät>"
ADDRESS = "<adresse>"
SECRET = "<geheim>"
# Fields that only ever name a device.
DEVICE_FIELDS = {"entity", "entity_id", "camera", "device", "label", "host", "url", "base"}

ENTITY_DOMAINS = ("alarm_control_panel|automation|binary_sensor|button|camera|climate|cover|device_tracker|event|fan|"
                  "image|input_boolean|input_button|input_number|input_select|input_text|light|lock|media_player|"
                  "number|person|remote|scene|script|select|sensor|siren|switch|text|update|vacuum|valve|water_heater|"
                  "weather|zone")
PATTERNS = (
    (re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+", re.IGNORECASE), ADDRESS),
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), ADDRESS),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), ADDRESS),
    (re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.IGNORECASE), ADDRESS),
    (re.compile(r"\b[\w-]+\.(?:local|lan|home|fritz\.box|internal)\b", re.IGNORECASE), ADDRESS),
    (re.compile(rf"\b(?:{ENTITY_DOMAINS})\.[a-z0-9_]+\b"), DEVICE),
    (re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b"), SECRET),
)


def _names(names):
    """Longest first, so a name containing another one is replaced whole."""
    return sorted({str(name).strip() for name in names or () if name and len(str(name).strip()) >= 3},
                  key=len, reverse=True)


def clean_text(value, names=()):
    text = str(value)
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    for name in _names(names):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", DEVICE, text, flags=re.IGNORECASE)
    return text


def clean(value, names=(), key=None):
    """The value with device names, addresses and secrets replaced, keeping its structure."""
    if isinstance(value, dict):
        return {item_key: clean(item, names, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [clean(item, names) for item in value]
    if isinstance(value, str):
        if key in DEVICE_FIELDS:
            return DEVICE
        return clean_text(value, names)
    return value


def export(text, hours=None, names=(), now=None):
    """Debug-log lines of the last ``hours`` (all with None), cleaned; broken lines are left out."""
    since = None
    if hours is not None:
        now = now or datetime.now().astimezone()
        since = now - timedelta(hours=hours)
    lines = []
    for line in str(text or "").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if since is not None:
            try:
                stamp = datetime.fromisoformat(str(entry.get("time")))
            except ValueError:
                continue
            if stamp.tzinfo is None:
                stamp = stamp.astimezone()
            if stamp < since:
                continue
        lines.append(json.dumps(clean(entry, names), ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def source_names(source):
    """Names and addresses of the configured image source that must not leave the app."""
    if not isinstance(source, dict):
        return []
    names = [source.get(key) for key in ("label", "camera", "reference", "url")]
    url = str(source.get("url") or "")
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url, flags=re.IGNORECASE).split("/")[0].split(":")[0]
    camera = str(source.get("camera") or "")
    if "." in camera:
        names.append(camera.split(".", 1)[1])
    return [name for name in [*names, host] if name and str(name) not in ("camera", "slfork", "esp")]
