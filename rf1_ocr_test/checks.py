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
OCR_PROFILES = (
    (2, 175, 155),
    (0, 125, 125),
    (1, 225, 140),
    (4, 150, 165),
    (6, 200, 180),
    (2, 130, 145),
    (3, 215, 175),
    (1, 185, 155),
    (5, 160, 135),
    (0, 210, 195),
)
MAX_OCR_ATTEMPTS = len(OCR_PROFILES)


def crop_register(picture, crop):
    left, top, right, bottom = crop
    if not (0 <= left < right <= picture.width and 0 <= top < bottom <= picture.height):
        raise ValueError(f"Ausschnitt {crop} liegt außerhalb von {picture.size}")
    return picture.crop(crop)


def read_register(picture, light_digits, digits=5, *, force_polarity=False, profile=OCR_PROFILES[0]):
    image = picture.convert("L")
    polarities = (light_digits,) if force_polarity else (light_digits, not light_digits)
    reads = {
        value for invert in polarities
        if (value := read_polarity(ImageOps.invert(image) if invert else image, digits, profile)) is not None
    }
    return next(iter(reads)) if len(reads) == 1 else None


def read_polarity(image, digits, profile):
    cutoff, sharpening, threshold = profile
    gray = ImageOps.autocontrast(image, cutoff=cutoff)
    variants = (
        gray,
        gray.filter(ImageFilter.UnsharpMask(radius=2, percent=sharpening, threshold=2)),
        gray.point(lambda value: 255 if value >= threshold else 0),
    )
    votes = Counter()
    for variant in variants:
        prepared = ImageOps.expand(variant.resize((variant.width * 3, variant.height * 3)),
                                   border=24, fill=255)
        with io.BytesIO() as png:
            prepared.save(png, "PNG")
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "10" if digits == 1 else "7",
                 "-c", "tessedit_char_whitelist=0123456789"],
                input=png.getvalue(), capture_output=True, timeout=12, check=True,
            ).stdout.decode("ascii", errors="ignore").strip()
        if len(result) == digits and re.fullmatch(r"[0-9]+", result):
            votes[result] += 1
    if len(votes) == 1:
        value, count = votes.most_common(1)[0]
        if count >= 2:
            return value
    return None


def meter_prefix(value, decimals):
    match = re.fullmatch(r"([0-9]{1,5})(?:[.,]([0-9Nn?]+))?", str(value))
    if not match:
        return None
    fractional = (match[2] or "")[:decimals]
    if decimals and (len(fractional) != decimals or not fractional.isdigit()):
        return None
    return int(match[1] + fractional)


def read_with_retries(read, data, decimals, progress=None, max_attempts=5):
    """Read one image up to max_attempts times; stop on the first valid agreement."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_OCR_ATTEMPTS:
        raise ValueError("OCR-Versuche müssen zwischen 1 und 10 liegen")
    readings = []
    for index, profile in enumerate(OCR_PROFILES[:max_attempts], start=1):
        if progress:
            progress(index - 1, f"OCR-Versuch {index} von {max_attempts} läuft …")
        try:
            value = read(profile)
        except subprocess.TimeoutExpired as error:
            print(f"OCR-Variante hat das Zeitlimit überschritten: {error}")
            value = "?????.???"
        status, _ = compare_sample(data, value, decimals)
        readings.append(value)
        if progress:
            progress(index, f"OCR-Versuch {index} von {max_attempts} abgeschlossen.")
        # Stop immediately on a verified match.
        # Without a reference, a valid OCR result ends the read.
        if status in ("match", "ocr_only"):
            return value, True, index

    # No match: show a majority reading for diagnostics if possible.
    majority = len(readings) // 2 + 1
    prefix_length = 5 + (decimals + 1 if decimals else 0)
    prefixes = Counter(value[:prefix_length] for value in readings
                       if meter_prefix(value, decimals) is not None)
    prefix = next((value for value, count in prefixes.items() if count >= majority), None)
    display = []
    for column in zip(*readings):
        digit, count = Counter(column).most_common(1)[0]
        display.append(digit if count >= majority else "?")
    display = "".join(display)
    if prefix is not None:
        display = prefix + display[prefix_length:]
    return display, prefix is not None, len(readings)


def compare_sample(data, ocr, decimals, *, ocr_confirmed=True):
    if not ocr_confirmed:
        return "ocr_unclear", "Die OCR-Versuche ergeben keine Mehrheit für die eingestellten Stellen."
    value = meter_prefix(ocr, decimals)
    if value is None:
        return "ocr_unclear", "OCR konnte die eingestellten Stellen nicht eindeutig lesen."
    if data.get("reference_required") is False:
        return "ocr_only", "OCR ausgewertet. Es ist kein Referenzsensor eingestellt."
    source_status = data.get("slfork_value_status") or ""
    if re.match(r"^[EW][0-9]+(?:\s|$)", str(source_status)):
        return "slfork_unclear", "AI on the Edge meldet eine Warnung oder einen Fehler zum Zählerstand."
    if data.get("slfork_process_error") in (-1, -2, "-1", "-2"):
        return "slfork_unclear", "AI on the Edge hat den Messzyklus abgebrochen."
    raw = meter_prefix(data["raw_value"], decimals)
    actual = meter_prefix(data["actual_value"], decimals)
    if raw is None or actual is None:
        return "slfork_unclear", "Der Referenzwert fehlt, ist zu alt oder hat zu wenige lesbare Stellen."
    if raw != actual:
        return "slfork_unclear", "Rohwert und übernommener Referenzwert weichen voneinander ab."
    if value != actual:
        return "difference", "OCR und Referenzwert weichen bei der eingestellten Genauigkeit ab."
    return "match", "OCR und Referenzwert stimmen überein."


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
        "last_match_at_epoch": history.get("last_match_at"),
        "check_detail": history.get("check_detail"),
    }


def sample_timestamp(data, zone):
    stamp = datetime.fromisoformat(data["esp_timestamp"])
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=zone)
    return stamp.timestamp()


def sample_epoch(data, zone, now):
    captured = sample_timestamp(data, zone)
    epoch = now.timestamp()
    return captured if epoch - FRESH_SAMPLE_AGE < captured <= epoch + 60 else None


def record_sample(history, data, ocr, zone, now, decimals=0, *, ocr_confirmed=True):
    """Count each in-window cycle at most once, even after a restart."""
    captured = sample_epoch(data, zone, now)
    if captured is None or captured <= history.get("last_epoch", 0):
        return False

    epoch = now.timestamp()
    if "started_at" not in history:
        history.update(started_at=epoch, confirmations=[], status="no_current_sample")
    history["confirmations"] = [old for old in history["confirmations"] if old > epoch - WINDOW_SECONDS]
    status, detail = compare_sample(data, ocr, decimals, ocr_confirmed=ocr_confirmed)
    if status == "match":
        history["confirmations"].append(captured)
        history["last_match_at"] = captured
    history.update(last_epoch=captured, status=status, ocr_value=ocr, check_detail=detail)
    return True


def schedule_next_check(history, outcome, checked_at):
    history["check_status"] = outcome
    if outcome in ("match", "ocr_only"):
        history.pop("failure_since", None)
        interval = NORMAL_INTERVAL
    else:
        history.setdefault("failure_since", checked_at)
        interval = RETRY_INTERVAL
    history["next_check_at"] = checked_at + interval

