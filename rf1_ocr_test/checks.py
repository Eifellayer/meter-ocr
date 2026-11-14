"""Independent OCR and restart-safe agreement counts over a rolling window."""
from collections import Counter
from datetime import datetime
import io
import re
import subprocess

from PIL import ImageFilter, ImageOps

WINDOW_SECONDS = 24 * 60 * 60
REQUIRED_MATCHES = 5
NORMAL_INTERVAL = 60 * 60
RETRY_INTERVAL = 5 * 60
REVIEW_AFTER = 4 * 60 * 60
FRESH_SAMPLE_AGE = 15 * 60


def crop_register(picture, crop):
    left, top, right, bottom = crop
    if not (0 <= left < right <= picture.width and 0 <= top < bottom <= picture.height):
        raise ValueError(f"Ausschnitt {crop} liegt außerhalb von {picture.size}")
    return picture.crop(crop)


def read_register(picture, light_digits):
    image = picture.convert("L")
    reads = {
        value for invert in (light_digits, not light_digits)
        if (value := read_polarity(ImageOps.invert(image) if invert else image)) is not None
    }
    return next(iter(reads)) if len(reads) == 1 else None


def read_polarity(image):
    gray = ImageOps.autocontrast(image, cutoff=2)
    variants = (
        gray,
        gray.filter(ImageFilter.UnsharpMask(radius=2, percent=175, threshold=2)),
        gray.point(lambda value: 255 if value >= 155 else 0),
    )
    votes = Counter()
    for variant in variants:
        prepared = ImageOps.expand(variant.resize((variant.width * 3, variant.height * 3)),
                                   border=24, fill=255)
        with io.BytesIO() as png:
            prepared.save(png, "PNG")
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "7",
                 "-c", "tessedit_char_whitelist=0123456789"],
                input=png.getvalue(), capture_output=True, timeout=12, check=True,
            ).stdout.decode("ascii", errors="ignore").strip()
        if re.fullmatch(r"[0-9]{5}", result):
            votes[result] += 1
    if len(votes) == 1:
        value, count = votes.most_common(1)[0]
        if count >= 2:
            return value
    return None


def whole_m3(value):
    # SLFork can send more than three decimal places. Only the whole part must be readable.
    match = re.fullmatch(r"([0-9]{1,5})(?:\.[0-9Nn]+)?", str(value))
    return int(match[1]) if match else None


def rolling_summary(history, now):
    epoch = now.timestamp()
    count = sum(epoch - WINDOW_SECONDS < stamp <= epoch for stamp in history.get("confirmations", ()))
    failure = history.get("failure_since")
    return {
        "matches_last_24h": count,
        "required_matches": REQUIRED_MATCHES,
        "window_started_at_epoch": history.get("started_at"),
        "failure_since_epoch": failure,
        "review_due": failure is not None and epoch - failure >= REVIEW_AFTER,
        "check_status": history.get("check_status"),
        "next_check_at_epoch": history.get("next_check_at"),
    }


def record_sample(history, data, ocr, zone, now):
    """Count each in-window cycle at most once, even after a restart."""
    if "started_at" not in history:
        history.update(started_at=now.timestamp(), confirmations=[], status="no_current_sample")
    epoch = now.timestamp()
    stamp = datetime.fromisoformat(data["esp_timestamp"])
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=zone)
    captured = stamp.timestamp()
    if not epoch - FRESH_SAMPLE_AGE < captured <= epoch + 60:
        return False
    if captured <= history.get("last_epoch", 0):
        return False

    history["confirmations"] = [old for old in history["confirmations"] if old > epoch - WINDOW_SECONDS]
    raw = whole_m3(data["raw_value"])
    actual = whole_m3(data["actual_value"])
    value = whole_m3(ocr)
    if value is None:
        status = "ocr_unclear"
    elif raw is None or actual is None or raw != actual:
        status = "slfork_unclear"
    elif value == actual:
        status = "match"
        history["confirmations"].append(captured)
    else:
        status = "difference"
    history.update(last_epoch=captured, status=status, ocr_value=ocr)
    return True


def schedule_next_check(history, outcome, checked_at):
    history["check_status"] = outcome
    if outcome == "match":
        history.pop("failure_since", None)
        interval = NORMAL_INTERVAL
    else:
        history.setdefault("failure_since", checked_at)
        interval = RETRY_INTERVAL
    history["next_check_at"] = checked_at + interval
