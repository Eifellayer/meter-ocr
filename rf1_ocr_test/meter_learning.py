"""Conservative learning from regular, independently confirmed meter readings."""

import subprocess
import time

from PIL import ImageOps

from checks import OCR_PROFILES, RETRY_INTERVAL, meter_prefix, read_register
from layout import digit_box_settings, normalize_digit_boxes, scale_digit_boxes

ALIGNMENT_CONFIRMATIONS = 6
ALIGNMENT_ROLLBACK_FAILURES = 2


def note_local_issue(state, key, stamp, positions):
    """Allow a local probe only for the same issue on three separate captures."""
    if state.get("key") != key:
        state.clear()
        state["key"] = key
    if stamp <= state.get("stamp", 0):
        return False
    previous = state.get("positions")
    state["stamp"] = stamp
    state["positions"] = positions
    state["count"] = state.get("count", 0) + 1 if positions and positions == previous else int(bool(positions))
    return state["count"] >= 3


def note_local_improvement(state, key, stamp, geometry, reading):
    """Require agreement across fresh images and more than one meter reading."""
    if state.get("key") == key and stamp <= state.get("stamp", 0):
        return False
    if state.get("key") != key or state.get("geometry") != geometry:
        state.clear()
        state.update(key=key, geometry=geometry, count=0, readings=[])
    state["stamp"] = stamp
    state["count"] += 1
    if reading not in state["readings"]:
        state["readings"] = (state["readings"] + [reading])[-2:]
    return state["count"] >= 3 and len(state["readings"]) >= 2


def local_geometry_trials(boxes, positions):
    """Move only the uncertain cells, preserving their size and order."""
    if boxes:
        for axis, sign in ((0, -1), (0, 1), (1, -1), (1, 1)):
            shifted = [list(box) for box in boxes]
            for index in positions:
                box = shifted[index]
                width = box[axis + 2] - box[axis]
                step = sign * max(1, width // 18)
                step = max(-box[axis], min(step, 1000 - box[axis + 2]))
                box[axis] += step
                box[axis + 2] += step
            if shifted != boxes:
                try:
                    yield 0, digit_box_settings(shifted, len(boxes))
                except ValueError:
                    pass
    for angle in (-1, 1, -2, 2):
        yield angle, boxes


def widen_digit_boxes(boxes, size, pixels=2):
    """Create a conservative wider per-digit grid for glyphs such as 1/8.

    The expansion is clipped to the register and normalized so neighbouring
    frames cannot overlap. It is used only as a secondary calibration trial.
    """
    if not boxes:
        return []
    w, h = size
    scaled = scale_digit_boxes(boxes, size)
    wider = []
    for left, top, right, bottom in scaled:
        wider.append((max(0, left - pixels), max(0, top - pixels),
                      min(w, right + pixels), min(h, bottom + pixels)))
    try:
        return digit_box_settings(normalize_digit_boxes(wider, size), len(boxes))
    except ValueError:
        return []


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
    refined = [tighten_digit_box(image, box) for box in boxes]
    try:
        return digit_box_settings(normalize_digit_boxes(refined, register.size), count)
    except ValueError:
        return []


def tighten_digit_box(image, original):
    left, top, right, bottom = original
    crop = image.crop(original)
    if crop.width < 8 or crop.height < 12:
        return original
    gray = ImageOps.autocontrast(crop, cutoff=3)
    border = gray.resize((8, 8))
    sides = [border.getpixel((x, y)) for y in range(8) for x in (0, 7)]
    background = sorted(sides)[len(sides) // 2]
    mask = gray.point(lambda value: 255 if abs(value - background) >= 82 else 0)
    box = mask.getbbox()
    if not box or box[2] - box[0] < .32 * crop.width or box[3] - box[1] < .4 * crop.height:
        return original
    margin = max(2, min(crop.size) // 10)
    return (max(left, left + box[0] - margin), max(top, top + box[1] - margin),
            min(right, left + box[2] + margin), min(bottom, top + box[3] + margin))


def suggest_single_digit_box(register, boxes, index, polarity):
    """Read only the selected slot and return a proposal when two profiles agree."""
    image = register.convert("L")
    pixels = scale_digit_boxes(boxes, image.size)
    left, top, right, bottom = original = pixels[index]
    width, height = right - left, bottom - top
    # Keep the search between the centers of adjacent rolls.
    minimum = (sum(pixels[index - 1][::2]) + 1) // 2 if index else 0
    maximum = sum(pixels[index + 1][::2]) // 2 if index + 1 < len(boxes) else image.width
    dx, dy = max(1, width // 4), max(1, height // 5)
    windows = [
        (max(minimum, left - dx), max(0, top - dy),
         min(maximum, right + dx), min(image.height, bottom + dy)),
        (max(minimum, left - dx), top, right - dx, bottom),
        (left + dx, top, min(maximum, right + dx), bottom),
        (left, max(0, top - dy), right, bottom - dy),
        (left, top + dy, right, min(image.height, bottom + dy)),
    ]
    deadline = time.monotonic() + 7
    tried = {original}
    for window in windows:
        if window[2] - window[0] < 8 or window[3] - window[1] < 12:
            continue
        proposal = tighten_digit_box(image, window)
        if proposal in tried:
            continue
        tried.add(proposal)
        normalized = list(normalize_digit_boxes([proposal], image.size)[0])
        candidate = list(boxes)
        candidate[index] = normalized
        try:
            digit_box_settings(candidate, len(boxes))
        except ValueError:
            continue
        if normalized == boxes[index]:
            continue
        try:
            digit_crop = image.crop(proposal)
            reading = read_register(digit_crop, polarity != "dark", 1, force_polarity=polarity != "auto",
                                    profile=OCR_PROFILES[0], deadline=deadline)
            if reading and reading == read_register(
                    digit_crop, polarity != "dark", 1, force_polarity=polarity != "auto",
                    profile=OCR_PROFILES[1], deadline=deadline):
                return {"box": normalized, "digit": reading}
        except (OSError, subprocess.SubprocessError):
            break
    return None


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


GEOMETRY_REPAIR_FAILURES = 3
GEOMETRY_REPAIR_SECONDS = 4 * 60
GEOMETRY_REPAIR_LIMIT = 20
GEOMETRY_FAILURE_DURATION = 2 * 60 * 60


def observe_geometry_failures(state, key, stamp, outcome, *, reading_problem):
    """Request one bounded repair per sustained failure streak."""
    if state.get("key") != key:
        state.clear()
        state.update(key=key, failures=0)
    if stamp <= state.get("stamp", 0):
        return False
    state["stamp"] = stamp
    if not reading_problem or outcome not in ("ocr_unclear", "difference"):
        state["failures"] = 0
        state.pop("first_failure_at", None)
        state.pop("scheduled_at", None)
        return False
    if "first_failure_at" not in state:
        state.update(first_failure_at=stamp, failures=0)
        state.pop("scheduled_at", None)
    state["failures"] = min(GEOMETRY_REPAIR_FAILURES, state["failures"] + 1)
    if (state["failures"] < GEOMETRY_REPAIR_FAILURES or state.get("scheduled_at")
            or stamp - state["first_failure_at"] < GEOMETRY_FAILURE_DURATION):
        return False
    state["scheduled_at"] = stamp
    return True
