"""Check automatic readings and keep a restart-safe cumulative gas consumption counter."""

from bisect import bisect_left, bisect_right
from datetime import datetime, time, timedelta
import re

from checks import FALLBACK_NOTICE, LOWER_PENDING_NOTICE, meter_prefix

DEFAULT_FLOW_LPH = 6_000
MAX_FLOW_LPH = 999_999_999

LOWER_READING = "Zählerstand liegt unter dem letzten gültigen Wert."
EXCESSIVE_INCREASE = "Zählerstand steigt schneller als der eingestellte Durchfluss erlaubt."
INVALID_TIME = "Messzeitpunkt liegt vor der letzten gültigen Messung."
FALLBACK_PLAUSIBLE = "OCR-Zuwachs plausibel. Warte auf den Abgleich."
FALLBACK_UNKNOWN_TIME = "Für die Plausibilitätsprüfung fehlt ein gültiger Messzeitpunkt."
FALLBACK_UNCLEAR_OCR = "OCR-Stand unsicher."
LOWER_RECOVERY_READINGS = 3
LOWER_RECOVERY_SECONDS = 15 * 60
LOWER_PENDING = LOWER_PENDING_NOTICE
LOWER_RECOVERED = ("Mehrere stimmige Ablesungen lagen unter dem gespeicherten Stand. Der höhere Wert war ein Lesefehler, "
                   "der Zählerstand wurde korrigiert.")


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


# Gas billing: kWh = m³ × Zustandszahl (state factor) × Brennwert (calorific value, kWh/m³).
STATE_FACTOR_RANGE = (0.8, 1.1)
CALORIFIC_RANGE = (8.0, 13.0)
# Some bills only state the finished conversion factor (Umrechnungsfaktor = Z × Hs).
CONVERSION_RANGE = (6.0, 14.0)


def parse_energy_factor(text, limits):
    """Optional factor from the settings form; empty means "not set"."""
    text = str(text or "").strip().replace(",", ".")
    if not text:
        return None
    if not re.fullmatch(r"[0-9]{1,2}(?:\.[0-9]{1,4})?", text):
        raise ValueError("Ungültiger Umrechnungswert")
    value = round(float(text), 4)
    if not limits[0] <= value <= limits[1]:
        raise ValueError("Umrechnungswert außerhalb des üblichen Bereichs")
    return value


def valid_energy_factor(value, limits):
    return round(float(value), 4) if type(value) in (int, float) and limits[0] <= value <= limits[1] else None


def kwh_factor(state_factor, calorific_value, conversion_factor=None):
    """kWh per m³: the bill's finished conversion factor, otherwise Zustandszahl × Brennwert."""
    if conversion_factor is not None:
        return conversion_factor
    if state_factor is None or calorific_value is None:
        return None
    return state_factor * calorific_value


def energy_kwh(total_litres, state_factor, calorific_value, conversion_factor=None):
    """Consumption in kWh, or None until the billing factors are set."""
    factor = kwh_factor(state_factor, calorific_value, conversion_factor)
    if type(total_litres) is not int or factor is None:
        return None
    return round(total_litres / 1000 * factor, 2)


def track_lower_series(series, stamp, reading, decimals, max_flow_lph, integer_digits=5):
    """Collect consecutive readings below the stored maximum and decide when they prove a misread.

    A gas meter cannot run backwards. A *single* lower reading is therefore rejected.
    If several later readings agree with each other (never falling, never faster than
    the maximum flow) over a minimum time span, the earlier higher value was a misread.
    Returns the updated series and whether the lower readings are confirmed.
    """
    prefix = meter_prefix(reading, decimals, integer_digits)
    if prefix is None or type(stamp) not in (int, float):
        return [], False
    step = 10 ** (3 - decimals)
    litres = prefix * step
    rows = [row for row in (series or []) if isinstance(row, list) and len(row) == 2]
    if rows:
        last_stamp, last_litres = rows[-1]
        if stamp <= last_stamp:
            return rows, False
        consistent = (last_litres - step <= litres
                      and litres - last_litres - step <= max_flow_lph * (stamp - last_stamp) / 3600)
        if not consistent:
            rows = []
    rows = [*rows, [stamp, litres]][-2 * LOWER_RECOVERY_READINGS:]
    confirmed = len(rows) >= LOWER_RECOVERY_READINGS and rows[-1][0] - rows[0][0] >= LOWER_RECOVERY_SECONDS
    return rows, confirmed


LOWER_DROP_MIN_LITRES = 2_000


def plausible_lower_drop(previous, stamp, reading, decimals, max_flow_lph, integer_digits=5):
    """Is a reading below the stored value close enough to be a correction of a misread?

    A misread booked shortly before is off by a digit step, not by thousands of cubic
    metres. A frame shifted by one digit ("04912" instead of "10491") must never be taken
    as a correction. Allowed: at least 2 m³, or twice the flow limit (at most the
    default 6 m³/h) over the time since the stored value was taken.
    """
    prefix = meter_prefix(reading, decimals, integer_digits)
    if prefix is None or not isinstance(previous, dict) or type(stamp) not in (int, float):
        return False
    stored = max(value for value in (previous.get("reading_litres"), previous.get("anchor_litres"),
                                     previous.get("pending_litres"), 0) if type(value) is int)
    stored_at = previous.get("timestamp")
    hours = max(0.0, stamp - stored_at) / 3600 if type(stored_at) in (int, float) else 0.0
    flow = min(max_flow_lph, DEFAULT_FLOW_LPH) if max_flow_lph else DEFAULT_FLOW_LPH
    limit = max(LOWER_DROP_MIN_LITRES, 2 * flow * hours)
    return 0 < stored - prefix * 10 ** (3 - decimals) <= limit


CONFIRM_MIN_SECONDS = 4 * 60


def accumulate_consumption(previous, source, stamp, reading, decimals, max_flow_lph, integer_digits=5,
                           allow_lower=False, require_consistent=False, confirmed=False):
    """Return a proposed new counter state. Consumption is booked only for confirmed readings.

    A new reading first becomes *pending*. It is booked once a later reading, taken at
    least CONFIRM_MIN_SECONDS afterwards, agrees with it (not lower, not faster than the
    maximum flow). A pending value that a later reading contradicts was a misread and is
    discarded without booking anything, so a too-high misread never blocks later
    bookings. The first reading of a source is a pending start value in the same way.

    allow_lower accepts a reading below a confirmed anchor after track_lower_series
    proved the anchor wrong. Nothing booked is taken back; if nothing was booked since
    the start value, the anchor simply moves to the corrected reading.

    require_consistent raises instead of discarding when the pending value is
    contradicted (used to cross-check two images of one check).

    confirmed marks a reading that an independent reference already confirmed (e.g. an
    agreeing SLFork value or a user-entered start value); it is booked immediately.
    """
    prefix = meter_prefix(reading, decimals, integer_digits)
    if prefix is None:
        raise ValueError("Ungültiger Zählerstand")
    step = 10 ** (3 - decimals)
    current = prefix * step
    total = previous.get("total_litres", 0)
    if previous.get("source") != source:
        if confirmed:
            return {
                "source": source, "timestamp": stamp, "reading_litres": current, "step_litres": step,
                "total_litres": total, "start_total": total,
                "anchor_litres": current, "anchor_time": stamp, "anchor_step": step, "floor_litres": current,
                "pending_litres": None, "pending_time": None, "pending_step": None,
            }
        return {
            "source": source, "timestamp": stamp, "reading_litres": current, "step_litres": step,
            "total_litres": total, "start_total": total,
            "anchor_litres": None, "anchor_time": None, "anchor_step": None, "floor_litres": None,
            "pending_litres": current, "pending_time": stamp, "pending_step": step,
        }
    if stamp - previous["timestamp"] <= 0:
        raise ImplausibleReading(INVALID_TIME)
    legacy = "pending_litres" not in previous
    anchor = previous.get("anchor_litres", previous["reading_litres"]) if legacy else previous.get("anchor_litres")
    anchor_time = previous["timestamp"] if legacy else previous.get("anchor_time")
    anchor_step = previous["step_litres"] if legacy else previous.get("anchor_step")
    floor = previous.get("floor_litres", anchor)
    if floor is None:
        floor = anchor
    start_total = previous.get("start_total")
    if legacy and total == 0:
        start_total = 0
    if (anchor is not None and floor is not None and floor < anchor
            and start_total is not None and total == start_total):
        # A corrected misread on which nothing was booked: no reason to wait for it.
        anchor, anchor_time = floor, previous["timestamp"]
    pending = None if legacy else previous.get("pending_litres")
    pending_time = None if legacy else previous.get("pending_time")
    pending_step = None if legacy else previous.get("pending_step")

    def flow_ok(base, base_time, base_step):
        return current - base - base_step <= max_flow_lph * (stamp - base_time) / 3600

    if anchor is not None:
        if current + step <= floor and not allow_lower:
            raise ImplausibleReading(LOWER_READING)
        if not flow_ok(anchor, anchor_time, anchor_step):
            raise ImplausibleReading(EXCESSIVE_INCREASE)
        if allow_lower and current < anchor:
            if start_total is not None and total == start_total:
                anchor, anchor_time, anchor_step = current, stamp, step
            floor = current
    new_pending, new_pending_time, new_pending_step = current, stamp, step
    if confirmed:
        if anchor is None:
            anchor, anchor_time, anchor_step = current, stamp, step
        else:
            total += max(0, current - anchor)
            if current > anchor:
                anchor, anchor_time, anchor_step = current, stamp, step
        floor = max(floor, current) if floor is not None and not allow_lower else current
        new_pending = new_pending_time = new_pending_step = None
    elif pending is not None:
        consistent = current + step > pending and flow_ok(pending, pending_time, pending_step)
        if not consistent and require_consistent:
            raise ImplausibleReading(LOWER_READING if current + step <= pending else EXCESSIVE_INCREASE)
        if consistent and stamp - pending_time < CONFIRM_MIN_SECONDS:
            # Too soon to prove anything: keep the older pending value for the next check.
            new_pending, new_pending_time, new_pending_step = pending, pending_time, pending_step
        elif consistent and pending >= (floor if floor is not None else pending):
            if anchor is None:
                anchor, anchor_time, anchor_step = pending, pending_time, pending_step
            else:
                total += max(0, pending - anchor)
                if pending > anchor:
                    anchor, anchor_time, anchor_step = pending, pending_time, pending_step
            floor = max(floor, pending) if floor is not None else pending
    return {
        "source": source,
        "timestamp": stamp,
        "reading_litres": current,
        "step_litres": step,
        "total_litres": total,
        "start_total": start_total,
        "anchor_litres": anchor,
        "anchor_time": anchor_time,
        "anchor_step": anchor_step,
        "floor_litres": floor,
        "pending_litres": new_pending,
        "pending_time": new_pending_time,
        "pending_step": new_pending_step,
    }


def fallback_detail(sample, image_time, ocr, readings, previous, source, max_flow_lph, integer_digits=5):
    """Assess repeatable OCR against dated readings, without accepting consumption."""
    for decimals in (3, 2, 1, 0):
        prefix = meter_prefix(ocr, decimals, integer_digits)
        if prefix is not None and sum(meter_prefix(value, decimals, integer_digits) == prefix
                                      for value in readings) * 2 > len(readings):
            break
    else:
        return f"{FALLBACK_NOTICE} {FALLBACK_UNCLEAR_OCR}"

    baselines = []
    if previous.get("source") == source and previous["timestamp"] < image_time:
        baselines.append(previous)
    reference, reference_time = sample["reference"], sample["reference_time"]
    if reference_time is not None:
        for reference_decimals in (3, 2, 1, 0):
            if meter_prefix(reference, reference_decimals) is not None:
                baselines.append(accumulate_consumption(
                    {}, source, reference_time, reference, reference_decimals, max_flow_lph,
                    integer_digits, confirmed=True,
                ))
                break
    if not baselines:
        return f"{FALLBACK_NOTICE} {FALLBACK_UNKNOWN_TIME}"

    try:
        for baseline in baselines:
            accumulate_consumption(baseline, source, image_time, ocr, decimals, max_flow_lph,
                                   integer_digits)
    except ImplausibleReading as error:
        return f"{FALLBACK_NOTICE} OCR: {error}"
    return f"{FALLBACK_NOTICE} {FALLBACK_PLAUSIBLE}"


STATISTICS_DAYS = 7
STATISTICS_HOURS = 24
MAX_STATISTICS_GAP = 2 * 3600


def record_consumption_sample(series, source, counter, *, preserve_on_source_change=False):
    """Keep dated snapshots, optionally bridging an explicit reset across image-source changes.

    accumulate_consumption keeps the cumulative total when a source changes and
    starts a new reading baseline. The first point here therefore adds no
    artificial consumption; the historical samples remain available.
    """
    stamp, total, step = (counter[key] for key in ("timestamp", "total_litres", "step_litres"))
    samples = series.get("samples", []) if (series.get("source") == source or preserve_on_source_change) else []
    if samples and stamp <= samples[-1][0]:
        return series
    cutoff = stamp - (STATISTICS_DAYS + 1) * 86400
    first = max(0, bisect_left(samples, cutoff, key=lambda sample: sample[0]) - 1)
    return {"source": source, "samples": [*samples[first:], [stamp, total, step]]}


def consumption_statistics(series, source, now, zone):
    """Calculate local hourly and daily consumption from confirmed intervals."""
    samples = series.get("samples", []) if series.get("source") == source else []
    samples = samples[:bisect_right(samples, now, key=lambda sample: sample[0])]
    local = datetime.fromtimestamp(now, zone)
    hour = local.replace(minute=0, second=0, microsecond=0).timestamp()
    hour_starts = [hour - offset * 3600 for offset in range(STATISTICS_HOURS)]
    day_starts = [datetime.combine(local.date() - timedelta(days=offset), time.min, zone).timestamp()
                  for offset in range(STATISTICS_DAYS)]
    hour_labels = [datetime.fromtimestamp(stamp, zone).strftime("%d.%m. %H:%M") for stamp in hour_starts]

    def summarize(start, end, label):
        litres = covered = 0
        estimated = False
        begin = max(0, bisect_right(samples, start, key=lambda sample: sample[0]) - 1)
        stop = bisect_left(samples, end, key=lambda sample: sample[0])
        for left, right in zip(samples[begin:stop], samples[begin + 1:stop + 1]):
            first, previous, step = left
            last, current, next_step = right
            overlap = min(end, last) - max(start, first)
            if overlap <= 0 or step != next_step or current < previous:
                continue
            duration = last - first
            if overlap < duration and duration > MAX_STATISTICS_GAP:
                continue
            covered += overlap
            litres += (current - previous) * overlap / duration
            estimated |= overlap < duration and current > previous
        return {"label": label, "litres": round(litres) if covered else None,
                "partial": 0 < covered < end - start - .001, "estimated": estimated}

    hours = []
    for index, (stamp, label) in enumerate(zip(hour_starts, hour_labels)):
        if hour_labels.count(label) > 1:
            label += datetime.fromtimestamp(stamp, zone).strftime(" (%z)")
        hours.append(summarize(stamp, hour_starts[index - 1] if index else now, label))
    days = [summarize(stamp, day_starts[index - 1] if index else now,
                      datetime.fromtimestamp(stamp, zone).strftime("%d.%m.%Y"))
            for index, stamp in enumerate(day_starts)]
    return {"hours": hours, "days": days}
