"""Check automatic readings and keep a restart-safe cumulative gas consumption counter."""

import re

from checks import meter_prefix

DEFAULT_FLOW_LPH = 6_000
MAX_FLOW_LPH = 999_999_999

LOWER_READING = "Zählerstand liegt unter dem letzten gültigen Wert."
EXCESSIVE_INCREASE = "Zählerstand steigt schneller als der eingestellte Durchfluss erlaubt."
INVALID_TIME = "Messzeitpunkt liegt vor der letzten gültigen Messung."


class ImplausibleReading(ValueError):
    """A reading conflicts with the last accepted observation."""


def format_cubic_metres(litres):
    whole, fraction = divmod(litres, 1000)
    return f"{whole}.{fraction:03d}".rstrip("0").rstrip(".") if fraction else str(whole)


def parse_flow_limit(text):
    match = re.fullmatch(r"([0-9]{1,6})(?:[.,]([0-9]{1,3}))?", text.strip())
    if not match:
        raise ValueError("Ungültiger maximaler Durchfluss")
    litres = int(match[1]) * 1000 + int((match[2] or "").ljust(3, "0"))
    if not 1 <= litres <= MAX_FLOW_LPH:
        raise ValueError("Der maximale Durchfluss muss größer als null sein")
    return litres


def accumulate_consumption(previous, source, stamp, reading, decimals, max_flow_lph):
    """Return a proposed new counter state. Rejected and repeated readings add nothing."""
    prefix = meter_prefix(reading, decimals)
    if prefix is None:
        raise ValueError("Ungültiger Zählerstand")
    step = 10 ** (3 - decimals)
    current = prefix * step
    total = previous.get("total_litres", 0)
    anchor = current
    if previous.get("source") == source:
        elapsed = stamp - previous["timestamp"]
        observed = current - previous["reading_litres"]
        if elapsed <= 0:
            raise ImplausibleReading(INVALID_TIME)
        previous_anchor = previous.get("anchor_litres", previous["reading_litres"])
        if current + step <= previous_anchor:
            raise ImplausibleReading(LOWER_READING)
        # Truncated readings represent an interval, not an exact quantity.
        if observed - previous["step_litres"] > max_flow_lph * elapsed / 3600:
            raise ImplausibleReading(EXCESSIVE_INCREASE)
        # A change of precision shifts the numeric baseline without measuring consumption.
        if step == previous["step_litres"]:
            total += max(0, current - previous_anchor)
        anchor = max(current, previous_anchor)
    return {
        "source": source,
        "timestamp": stamp,
        "reading_litres": current,
        "anchor_litres": anchor,
        "step_litres": step,
        "total_litres": total,
    }
