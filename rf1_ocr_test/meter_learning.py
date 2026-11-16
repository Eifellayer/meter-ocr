"""Conservative learning from regular, independently confirmed meter readings."""

from PIL import ImageOps

from checks import RETRY_INTERVAL, meter_prefix
from layout import digit_box_settings, normalize_digit_boxes, scale_digit_boxes

ALIGNMENT_CONFIRMATIONS = 6
ALIGNMENT_ROLLBACK_FAILURES = 2


def propose_digit_boxes(register, current, whole_width, integer_digits, fraction_digits):
    """Keep the digit centers ordered and tighten each frame around visible strokes."""
    count = integer_digits + fraction_digits
    w, h = register.size
    if w < count * 8 or h < 12:
        return []
    if current:
        boxes = scale_digit_boxes(current, register.size)
    else:
        whole = [round(i * whole_width / integer_digits) for i in range(integer_digits + 1)]
        fraction = [whole_width + round(i * (w - whole_width) / fraction_digits)
                    for i in range(1, fraction_digits + 1)]
        edges = whole + fraction
        boxes = [(left, 0, right, h) for left, right in zip(edges, edges[1:])]
    image = register.convert("L")
    refined = []
    for original in boxes:
        left, top, right, bottom = original
        crop = image.crop(original)
        if crop.width < 8 or crop.height < 12:
            refined.append(original)
            continue
        gray = ImageOps.autocontrast(crop, cutoff=3)
        # Subtract the background tone at the outer edges, without assuming polarity.
        border = gray.resize((8, 8))
        sides = [border.getpixel((x, y)) for y in range(8) for x in (0, 7)]
        background = sorted(sides)[len(sides) // 2]
        mask = gray.point(lambda value: 255 if abs(value - background) >= 82 else 0)
        box = mask.getbbox()
        if box and 0.32 * crop.width <= box[2] - box[0] and 0.4 * crop.height <= box[3] - box[1]:
            margin = max(2, min(crop.size) // 10)
            refined.append((max(left, left + box[0] - margin), max(top, top + box[1] - margin),
                            min(right, left + box[2] + margin), min(bottom, top + box[3] + margin)))
        else:
            refined.append(original)
    try:
        return digit_box_settings(normalize_digit_boxes(refined, register.size), count)
    except ValueError:
        return []


def observe_alignment(state, key, stamp, expected, baseline, current, candidate, trial):
    """Keep bounded reference states and require a better result on fresh frames."""
    if state.get("key") != key:
        state.clear()
        state.update(key=key, seen={}, observations=0)
    if stamp <= state.get("stamp", 0):
        return None
    state["stamp"] = stamp
    state["observations"] = min(9999, state["observations"] + 1)
    seen = state["seen"]
    for index, digit in enumerate(expected):
        if digit.isdigit():
            position = str(index)
            seen[position] = "".join(sorted(set(seen.get(position, "") + digit)))
    if not candidate or candidate == current:
        return None
    if candidate != state.get("candidate"):
        state.update(candidate=candidate, confirmations=0, improvements=0)
    pairs = [(index, digit) for index, digit in enumerate(expected) if digit.isdigit()]
    if not pairs or any(index >= len(trial) or trial[index] != digit for index, digit in pairs):
        state.update(confirmations=0, improvements=0)
        return None
    state["confirmations"] += 1
    if any(index >= len(baseline) or baseline[index] != digit for index, digit in pairs):
        state["improvements"] += 1
    changed = [index for index, (before, after) in enumerate(zip(current, candidate)) if before != after]
    if not current:
        changed = list(range(len(candidate)))
    datum = [str(index + (1 if "." in expected and index >= expected.index(".") else 0)) for index in changed]
    if (state["confirmations"] >= ALIGNMENT_CONFIRMATIONS and state["improvements"] >= 2
            and len(datum) == len(changed) and all(len(seen.get(position, "")) >= 2 for position in datum)):
        state["applied"] = candidate
        state["rollback"] = current
        state["failures"] = 0
        state.pop("candidate", None)
        return candidate
    return None


def alignment_rollback(state, key, current, failed):
    if state.get("key") != key or state.get("applied") != current:
        return None
    state["failures"] = state.get("failures", 0) + 1 if failed else 0
    if state["failures"] < ALIGNMENT_ROLLBACK_FAILURES:
        return None
    old = state.pop("rollback", [])
    state.pop("applied", None)
    state.pop("candidate", None)
    state.pop("confirmations", None)
    return old


def observe_flow(state, source, timestamp, reading, decimals, digits, month, maximum_flow):
    """Estimate recent and monthly flow from confirmed cumulative readings."""
    prefix = meter_prefix(reading, decimals, digits)
    if prefix is None:
        return
    value = prefix * 10 ** (3 - decimals)
    if state.get("source") != source or state.get("precision") != decimals:
        state.clear()
        state.update(source=source, precision=decimals, months={})
    previous = state.get("timestamp")
    if previous is not None:
        elapsed = timestamp - previous
        if elapsed <= 0:
            return
        delta = value - state["litres"]
        if 0 <= delta and elapsed <= 24 * 60 * 60:
            rate = delta * 3600 / elapsed
            if rate <= maximum_flow:
                month_key = str(month)
                recent = state.get("recent", rate)
                seasonal = state["months"].get(month_key, rate)
                state["recent"] = 0.65 * recent + 0.35 * rate
                state["months"][month_key] = 0.85 * seasonal + 0.15 * rate
    state.update(timestamp=timestamp, litres=value)


def suggested_interval(configured, state, source, month):
    if state.get("source") != source or "recent" not in state:
        return configured
    recent = state["recent"]
    rate = max(recent, state["months"].get(str(month), 0)) if recent > 0 else 0
    if rate <= 0:
        return configured
    # Forecast the next movement at the recorded precision, including a 9-to-0 rollover.
    step = 10 ** (3 - state["precision"])
    boundary = step * 10
    remaining = boundary - state["litres"] % boundary
    minutes = remaining * 60 / rate
    return min(configured, max(RETRY_INTERVAL // 60, int(minutes)))


GEOMETRY_REPAIR_FAILURES = 10
GEOMETRY_REPAIR_SECONDS = 4 * 60
GEOMETRY_REPAIR_LIMIT = 20


def observe_geometry_failures(state, key, stamp, outcome, *, reading_problem):
    """Request one bounded recalibration after distinct unreadable frames."""
    if state.get("key") != key:
        state.clear()
        state.update(key=key, failures=0)
    if stamp <= state.get("stamp", 0):
        return False
    state["stamp"] = stamp
    if outcome in ("match", "match_with_warning", "ocr_only"):
        state["failures"] = 0
        state.pop("scheduled_at", None)
    elif reading_problem and outcome in ("ocr_unclear", "difference"):
        state["failures"] = min(GEOMETRY_REPAIR_FAILURES, state["failures"] + 1)
    else:
        return False
    if state["failures"] < GEOMETRY_REPAIR_FAILURES or state.get("scheduled_at"):
        return False
    state["scheduled_at"] = stamp
    return True
