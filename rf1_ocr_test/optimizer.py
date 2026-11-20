"""Silent self-improvement of the saved frame with the pictures of the automatic checks (0.4.0).

Stefan (20.11.2026, 19:04/19:45): when the rear digits stay unclear, the recheck first tries the
saved angle ±1° and ±2°, then moves the frames of the decimal digits up and down – not only
sideways. Every trial is read with two OCR profiles on the picture the check already took (no
extra images). A slow machine manages only a few trials per picture, so the plan is kept in the
history and continues on the next picture where it stopped. A trial is saved permanently only if
it reads measurably better over several pictures and never contradicts a digit the current frame
read surely; the previous geometry stays as a fallback and every change is logged
(``optimize_saved``).
"""

ANGLE_STEPS = (1, -1, 2, -2)
VERTICAL_STEPS = (2, -2, 4, -4, 6, -6)
TRIALS = tuple(f"a{step:+d}" for step in ANGLE_STEPS) + tuple(f"v{step:+d}" for step in VERTICAL_STEPS)

# Adoption: tested on at least this many pictures, on average this many more sure digits than the
# current frame on the same pictures, better on at least two of them and never a contradiction.
MIN_IMAGES = 3
MIN_GAIN = .5
MIN_WINS = 2
# Time per recheck: planned from the measured seconds per OCR read on this machine.
MIN_SECONDS = 25
MAX_SECONDS = 60
PLANNED_READS = 6
DEFAULT_READ_SECONDS = 4.0
# Share of the recheck time for the trials; the rest stays for the single-digit search.
TRIAL_SHARE = .6
# After a full round without a winner the plan starts again after this many checks.
REST_CHECKS = 12


def read_seconds(state):
    value = (state or {}).get("read_s")
    return value if isinstance(value, (int, float)) and value > 0 else DEFAULT_READ_SECONDS


def note_read_time(state, seconds, reads):
    """Moving average of the seconds per OCR read (whole row, one profile)."""
    if reads <= 0 or seconds <= 0:
        return state
    sample = seconds / reads
    old = state.get("read_s")
    state["read_s"] = round(sample if not isinstance(old, (int, float)) else .7 * old + .3 * sample, 2)
    return state


def recheck_seconds(state):
    """Time budget of one recheck on this machine (25–60 s)."""
    return max(MIN_SECONDS, min(MAX_SECONDS, round(read_seconds(state) * PLANNED_READS)))


def trials_per_image(state):
    """How many trials (two reads each) fit into this check's share of the budget, at least one."""
    return max(1, int(recheck_seconds(state) * TRIAL_SHARE // (2 * read_seconds(state))))


def reset(state, key):
    state.clear()
    state.update(key=key, cursor=0, rounds=0, stats={}, rest=0)
    return state


def plan(state, key, read_state=None):
    """The optimizer state for this geometry (a new geometry starts a fresh plan)."""
    if state.get("key") != key:
        timing = state.get("read_s")
        reset(state, key)
        if timing is not None:
            state["read_s"] = timing
    return state


def next_trials(state, count):
    """The next trials of the plan, continuing where the last picture stopped."""
    if state.get("rest", 0) > 0:
        state["rest"] -= 1
        return []
    cursor = state.get("cursor", 0)
    return list(TRIALS[cursor:cursor + count])


def advance(state, done):
    """Mark trials as done; after the full list one round is complete."""
    state["cursor"] = state.get("cursor", 0) + done
    if state["cursor"] >= len(TRIALS):
        state["cursor"] = 0
        state["rounds"] = state.get("rounds", 0) + 1
        if best_trial(state) is None:
            state["rest"] = REST_CHECKS
    return state


def progress(state):
    """(done, total) of the current round for the display."""
    return min(state.get("cursor", 0), len(TRIALS)), len(TRIALS)


def sure_digits(readings, count):
    """Positions where both readings show the same digit."""
    rows = [str(value).replace(".", "").replace(",", "")[:count] for value in readings]
    if len(rows) < 2 or any(len(row) < count for row in rows):
        return 0, {}
    sure = {index: rows[0][index] for index in range(count)
            if rows[0][index].isdigit() and all(row[index] == rows[0][index] for row in rows[1:])}
    return len(sure), sure


def note_result(state, trial, trial_readings, base_readings, count):
    """Compare a trial with the current frame on the same picture."""
    trial_sure, trial_digits = sure_digits(trial_readings, count)
    base_sure, base_digits = sure_digits(base_readings, count)
    contradiction = any(trial_digits.get(index, digit) != digit for index, digit in base_digits.items()
                        if index in trial_digits)
    stats = state.setdefault("stats", {}).setdefault(trial, {"images": 0, "gain": 0, "wins": 0, "contradict": 0})
    stats["images"] += 1
    stats["gain"] += trial_sure - base_sure
    stats["wins"] += int(trial_sure > base_sure)
    stats["contradict"] += int(contradiction)
    return trial_sure, base_sure, contradiction


def best_trial(state):
    """The trial that is measurably better over several pictures, or None."""
    best = None
    for trial, stats in (state.get("stats") or {}).items():
        if (stats["images"] < MIN_IMAGES or stats["contradict"] or stats["wins"] < MIN_WINS
                or stats["gain"] / stats["images"] < MIN_GAIN):
            continue
        rank = (stats["gain"] / stats["images"], stats["wins"])
        if best is None or rank > best[0]:
            best = rank, trial
    return best[1] if best else None


def trial_geometry(trial, rotation, digit_boxes, register_height, integer_digits):
    """(rotation, normalized digit boxes) of a trial; vertical steps move the decimal digits only."""
    kind, step = trial[0], int(trial[1:])
    boxes = [list(box) for box in digit_boxes]
    if kind == "a":
        return rotation + step, boxes
    shift = round(step * 1000 / max(1, register_height))
    for box in boxes[integer_digits:]:
        if box[1] + shift < 0 or box[3] + shift > 1000:
            return None
        box[1] += shift
        box[3] += shift
    return rotation, boxes


def describe(trial):
    kind, step = trial[0], int(trial[1:])
    return f"Winkel {step:+d}°" if kind == "a" else f"Nachkommastellen {step:+d} px senkrecht"
