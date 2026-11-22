"""Work between two routine checks, without new camera images (0.5.0).

The app keeps the pictures of the last two checks (the regular picture and the one of the
cross-check). In the waiting time it may look at them again with a small budget; it never
fetches a picture or switches the light for that. The pictures stay in the app's data folder
and are overwritten by every check.
"""

from pathlib import Path

KEPT_IMAGES = 2
MAX_IMAGE_BYTES = 3_000_000


def image_paths(folder):
    """Newest first: where the pictures of the last checks are kept."""
    return [Path(folder) / f"letzte-pruefung-{number}.jpg" for number in range(1, KEPT_IMAGES + 1)]


def remember_check_image(folder, content, write):
    """Keep ``content`` as the newest check picture; the one before moves to second place.

    ``write(path, content, mode)`` stores a file atomically. Returns True when it was kept.
    """
    if not isinstance(content, (bytes, bytearray)) or not 0 < len(content) <= MAX_IMAGE_BYTES:
        return False
    newest, older = image_paths(folder)
    try:
        if newest.exists():
            if newest.read_bytes() == bytes(content):
                return False  # the same picture again (e.g. the source delivered nothing new)
            newest.replace(older)
        write(newest, bytes(content), 0o600)
    except OSError:
        return False
    return True


def kept_images(folder):
    """The stored pictures, newest first, as bytes."""
    pictures = []
    for path in image_paths(folder):
        try:
            pictures.append(path.read_bytes())
        except OSError:
            continue
    return pictures


def forget_images(folder):
    for path in image_paths(folder):
        path.unlink(missing_ok=True)


# --- When the waiting time may be used -------------------------------------------------
# Only a few tests in between, never load the machine (a Raspberry Pi)
# needlessly, and only with the pictures already taken.
MAX_READS_PER_WAIT = 6        # digit reads (each one OCR process) between two checks
MIN_SECONDS_AFTER_CHECK = 20  # let the machine settle after a check
MIN_SECONDS_BEFORE_CHECK = 60  # stay clear of the next check
REASONS = ("unclear_check", "experiment", "control")


def next_reason(candidates, turn):
    """Pick one task per waiting time, taking turns when several are due (0.5.15).

    When there is too much for one pause, do the tasks alternately
    between the checks instead of squeezing all of them into one block. ``candidates`` are the
    reasons that apply to the last check in order of priority; ``turn`` counts the pauses.
    Returns the chosen reason or "".
    """
    due = [reason for reason in candidates if reason in REASONS]
    return due[turn % len(due)] if due else ""


def keep_recent(jobs, newest):
    """Work of the last two checks, newest first; ``None`` marks a check that left nothing.

    A check and its cross-check are two pictures: both may be looked at again, anything
    older is dropped.
    """
    return [newest, *jobs][:KEPT_IMAGES]


def budget(now, last_check, next_check, system_sample, reason, used=0):
    """How many reads the app may still do in this waiting time (0 = leave the machine alone).

    ``reason`` says why there is anything to do: the last check was unclear, an experiment is
    switched on, or a control read is due. Without a reason nothing runs. ``system_sample`` is
    ``system_monitor.snapshot()``; a busy or hot machine gets no extra work.
    """
    if reason not in REASONS or used >= MAX_READS_PER_WAIT:
        return 0
    if type(last_check) not in (int, float) or type(next_check) not in (int, float):
        return 0
    if now - last_check < MIN_SECONDS_AFTER_CHECK or next_check - now < MIN_SECONDS_BEFORE_CHECK:
        return 0
    sample = system_sample or {}
    cpu, memory, heat = sample.get("cpu_percent"), sample.get("memory_used_percent"), sample.get("temperature_c")
    # Stricter than "busy": extra work only on a machine that is clearly idle.
    if (cpu is not None and cpu >= 50) or (memory is not None and memory >= 85) or (heat is not None and heat >= 70):
        return 0
    return MAX_READS_PER_WAIT - used
