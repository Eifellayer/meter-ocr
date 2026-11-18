"""Check automatic readings and keep a restart-safe cumulative gas consumption counter."""

from bisect import bisect_left, bisect_right
from datetime import datetime, time, timedelta
import re

from checks import FALLBACK_NOTICE, meter_prefix

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
LOWER_PENDING = "Zählerstand liegt unter dem letzten gültigen Wert. Bestätigen weitere stimmige Ablesungen den niedrigeren Stand, wird er übernommen."
LOWER_RECOVERED = ("Mehrere stimmige Ablesungen lagen unter dem gespeicherten Stand. Der höhere Wert war ein Lesefehler, "
                   "der Zählerstand wurde korrigiert. Verbrauch wird erst wieder gebucht, wenn der frühere Höchststand erreicht ist.")


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


def accumulate_consumption(previous, source, stamp, reading, decimals, max_flow_lph, integer_digits=5,
                           allow_lower=False):
    """Return a proposed new counter state. Rejected and repeated readings add nothing.

    allow_lower accepts a reading below the stored maximum after track_lower_series
    confirmed it. The maximum stays the booking anchor, so no negative and no double
    consumption is booked: counting resumes once the meter passes the old maximum.
    """
    prefix = meter_prefix(reading, decimals, integer_digits)
    if prefix is None:
        raise ValueError("Ungültiger Zählerstand")
    step = 10 ** (3 - decimals)
    current = prefix * step
    total = previous.get("total_litres", 0)
    anchor = current
    floor = current
    if previous.get("source") == source:
        elapsed = stamp - previous["timestamp"]
        observed = current - previous["reading_litres"]
        if elapsed <= 0:
            raise ImplausibleReading(INVALID_TIME)
        previous_anchor = previous.get("anchor_litres", previous["reading_litres"])
        # floor: lowest acceptable reading. It equals the anchor unless a confirmed
        # misread has been corrected; then it follows the real meter below the anchor.
        previous_floor = previous.get("floor_litres", previous_anchor)
        if current + step <= previous_floor and not allow_lower:
            raise ImplausibleReading(LOWER_READING)
        # Truncated readings represent an interval, not an exact quantity.
        if observed - previous["step_litres"] > max_flow_lph * elapsed / 3600:
            raise ImplausibleReading(EXCESSIVE_INCREASE)
        # A change of precision shifts the numeric baseline without measuring consumption.
        if step == previous["step_litres"]:
            total += max(0, current - previous_anchor)
        anchor = max(current, previous_anchor)
        floor = current if allow_lower else max(current, previous_floor)
    return {
        "source": source,
        "timestamp": stamp,
        "reading_litres": current,
        "anchor_litres": anchor,
        "floor_litres": floor,
        "step_litres": step,
        "total_litres": total,
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
                    integer_digits,
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
