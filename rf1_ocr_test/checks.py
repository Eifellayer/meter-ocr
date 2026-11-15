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
        scale = min(3, 2200 / variant.width, 700 / variant.height)
        resized = variant.resize((max(1, round(variant.width * scale)),
                                  max(1, round(variant.height * scale))))
        prepared = ImageOps.expand(resized, border=24, fill=255)
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


def comparison_scope(decimals):
    """Explain precisely which digits participate in a comparison."""
    if decimals == 0:
        return "volle Kubikmeter; Nachkommastellen werden nicht verglichen"
    return f"volle Kubikmeter und {decimals} Nachkommastelle" + ("n" if decimals > 1 else "")


def uncertain_positions(readings, decimals):
    """Return 1-based digit positions, or None when all were unreadable."""
    positions = list(range(5)) + list(range(6, 6 + decimals))
    evidence = [
        {value[position] if len(value) > position else "?" for value in readings}
        for position in positions
    ]
    if not any(any(char in "0123456789" for char in chars) for chars in evidence):
        return None
    return [
        (position >= 6, position - 5 if position >= 6 else position + 1)
        for position, chars in zip(positions, evidence)
        if len(chars) != 1 or not all(char in "0123456789" for char in chars)
    ]


def explain_uncertain_positions(readings, decimals):
    """Explain differences at digit positions relevant to this comparison."""
    positions = uncertain_positions(readings, decimals)
    if positions is None:
        return "Keine Ziffern lesbar. Ausschnitt und Licht prüfen."
    if not positions:
        return "OCR unsicher. Bild prüfen."
    groups = []
    for fractional, title in ((False, "Vor dem Komma"), (True, "Nach dem Komma")):
        digits = [str(index) for is_fractional, index in positions if is_fractional == fractional]
        if digits:
            groups.append(title + ": " + ", ".join(digits) + ".")
    return "OCR unsicher. " + " ".join(groups)


def read_with_retries(read, data, decimals, progress=None, max_attempts=5, trace=None, *, standalone=False):
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
        if trace is not None:
            trace.append(str(value))
        if progress:
            progress(index, f"OCR-Versuch {index} von {max_attempts} abgeschlossen.")
        # Stop immediately on a verified match.
        # Without a reference, a valid OCR result ends the read.
        if status == "match" or (status == "ocr_only" and not standalone):
            return value, True, index

    # No match: show a majority reading for diagnostics if possible.
    majority = len(readings) // 2 + 1
    minimum_votes = max(2, majority) if standalone else majority
    prefix_length = 5 + (decimals + 1 if decimals else 0)
    prefixes = Counter(value[:prefix_length] for value in readings
                       if meter_prefix(value, decimals) is not None)
    prefix = next((value for value, count in prefixes.items() if count >= minimum_votes), None)
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
        return "ocr_unclear", "Zählerstand nicht sicher erkannt. Bitte die unklaren Stellen im Kamerabild prüfen."
    value = meter_prefix(ocr, decimals)
    if value is None:
        return "ocr_unclear", "Zählerstand nicht lesbar. Mindestens eine benötigte Ziffer konnte nicht erkannt werden. Bitte das Kamerabild prüfen."
    if data.get("reference_required") is False:
        return "ocr_only", "Zählerstand gelesen, aber ohne Referenzwert nicht bestätigt. Vergleichseinstellung: " + comparison_scope(decimals) + "."
    source_status = data.get("slfork_value_status") or ""
    if re.match(r"^[EW][0-9]+(?:\s|$)", str(source_status)):
        return "slfork_unclear", "Der ESP meldet ein Problem mit der Zählerablesung. Bitte den Wert direkt am ESP prüfen."
    if data.get("slfork_process_error") in (-1, -2, "-1", "-2"):
        return "slfork_unclear", "Die Messung am ESP wurde abgebrochen. Bitte den ESP prüfen und die nächste Aufnahme abwarten."
    raw = meter_prefix(data["raw_value"], decimals)
    actual = meter_prefix(data["actual_value"], decimals)
    if raw is None or actual is None:
        return "slfork_unclear", "Referenzwert fehlt oder ist ungültig."
    if raw != actual:
        return "slfork_unclear", "Der ESP liefert widersprüchliche Zählerwerte. Bitte den angezeigten Stand am ESP prüfen."
    if value != actual:
        if decimals == 0:
            return "difference", "Abweichung: Die vollen Kubikmeter stimmen nicht überein. Bitte das Zählerbild prüfen."
        return ("difference",
                f"Abweichung: Die Werte stimmen beim Vergleich bis zur {decimals}. Nachkommastelle "
                "nicht überein. Bitte das Zählerbild prüfen.")
    if decimals == 0:
        return "match", "Bestätigt: Die vollen Kubikmeter stimmen überein. Nachkommastellen wurden nicht berücksichtigt."
    if decimals == 1:
        return "match", "Bestätigt: Zählerstand und Referenzwert stimmen bis einschließlich der 1. Nachkommastelle überein."
    return "match", f"Bestätigt: Zählerstand und Referenzwert stimmen bis einschließlich der {decimals}. Nachkommastelle überein."


def rolling_summary(history, now, review_after=REVIEW_AFTER):
    epoch = now.timestamp()
    count = sum(epoch - WINDOW_SECONDS < stamp <= epoch for stamp in history.get("confirmations", ()))
    failure = history.get("failure_since")
    return {
        "matches_last_24h": count,
        "required_matches": REQUIRED_MATCHES,
        "window_started_at_epoch": history.get("started_at"),
        "failure_since_epoch": failure,
        "review_due": failure is not None and epoch - failure >= review_after,
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

