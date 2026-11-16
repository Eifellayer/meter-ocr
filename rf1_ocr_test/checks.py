"""Independent OCR and restart-safe agreement counts over a rolling window."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
import io
from itertools import product
import re
import subprocess
import time

from PIL import Image, ImageChops, ImageFilter, ImageOps

WINDOW_SECONDS = 24 * 60 * 60
REQUIRED_MATCHES = 5
DEFAULT_INTERVAL_MINUTES = 60
MAX_INTERVAL_MINUTES = 24 * 60
NORMAL_INTERVAL = DEFAULT_INTERVAL_MINUTES * 60
RETRY_INTERVAL = 5 * 60
FAILURE_RETRY_LIMIT = 3
FAILURE_COOLDOWN_INTERVAL = 60 * 60
WARNING_DETAIL_AFTER = 60 * 60
REVIEW_AFTER = 4 * 60 * 60
FRESH_SAMPLE_AGE = 15 * 60
FALLBACK_NOTICE = "Der ESP verwendet einen Ersatzwert."
FALLBACK_STATUS = re.compile(
    r"^(?:E9[123]|00[234])(?:\s|$)|\b(?:use|using) fallback\b|\brate (?:too high|negative)\b",
    re.IGNORECASE,
)
# Cutoff, sharpening, threshold and optional correction for uneven lighting.
OCR_PROFILES = (
    (2, 175, 155, False),
    (0, 125, 125, False),
    (1, 225, 140, True),
    (3, 215, 175, True),
    (6, 200, 180, True),
    (2, 130, 145, False),
    (4, 150, 165, False),
    (1, 185, 155, True),
    (5, 160, 135, False),
    (0, 210, 195, True),
    (2, 140, 135, True),
    (4, 225, 150, False),
    (6, 130, 175, True),
    (3, 160, 190, False),
    (5, 210, 145, True),
)
MAX_CONFIGURED_OCR_ATTEMPTS = 10
MAX_OCR_ATTEMPTS = len(OCR_PROFILES)


def crop_register(picture, crop):
    left, top, right, bottom = crop
    if not (0 <= left < right <= picture.width and 0 <= top < bottom <= picture.height):
        raise ValueError(f"Ausschnitt {crop} liegt außerhalb von {picture.size}")
    return picture.crop(crop)


def read_register(picture, light_digits, digits=5, *, force_polarity=False, profile=OCR_PROFILES[0], deadline=None):
    image = picture.convert("L")
    polarities = (light_digits,) if force_polarity else (light_digits, not light_digits)
    reads = set()
    for invert in polarities:
        gray = ImageOps.invert(image) if invert else image
        value = (read_polarity(gray, digits, profile) if deadline is None
                 else read_polarity(gray, digits, profile, deadline=deadline))
        if value is not None:
            reads.add(value)
    return next(iter(reads)) if len(reads) == 1 else None


def reduce_uneven_lighting(image):
    """Estimate broad shadows on a small image while excluding the dark strokes."""
    background = image.copy()
    background.thumbnail((240, 80))
    kernel = max(5, (background.height // 12) | 1)
    background = background.filter(ImageFilter.MaxFilter(kernel)).filter(ImageFilter.MinFilter(kernel))
    low, high = background.resize((6, 2), Image.Resampling.BILINEAR).getextrema()
    if high - low < 45:
        return image
    background = background.resize(image.size, Image.Resampling.BILINEAR)
    return ImageChops.subtract(image, background, offset=255)


def read_polarity(image, digits, profile, *, deadline=None):
    cutoff, sharpening, threshold, reduce_shadows = profile
    if reduce_shadows:
        image = reduce_uneven_lighting(image)
    gray = ImageOps.autocontrast(image, cutoff=cutoff)
    variants = (
        gray,
        gray.filter(ImageFilter.UnsharpMask(radius=2, percent=sharpening, threshold=2)),
        gray.point(lambda value: 255 if value >= threshold else 0),
    )
    votes = Counter()
    for variant in variants:
        timeout = min(12, deadline - time.monotonic()) if deadline is not None else 12
        if timeout <= 0:
            raise TimeoutError("OCR deadline reached")
        scale = min(3, 2200 / variant.width, 700 / variant.height)
        resized = variant.resize((max(1, round(variant.width * scale)),
                                  max(1, round(variant.height * scale))))
        prepared = ImageOps.expand(resized, border=24, fill=255)
        with io.BytesIO() as png:
            prepared.save(png, "PNG")
            result = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "10" if digits == 1 else "7",
                 "-c", "tessedit_char_whitelist=0123456789"],
                input=png.getvalue(), capture_output=True, timeout=timeout, check=True,
            ).stdout.decode("ascii", errors="ignore").strip()
        if len(result) == digits and re.fullmatch(r"[0-9]+", result):
            votes[result] += 1
    if len(votes) == 1:
        value, count = votes.most_common(1)[0]
        if count >= 2:
            return value
    return None


def meter_prefix(value, decimals, integer_digits=5):
    if type(integer_digits) is not int or not 1 <= integer_digits <= 9:
        return None
    match = re.fullmatch(rf"([0-9]{{1,{integer_digits}}})(?:[.,]([0-9Nn?]+))?", str(value))
    if not match:
        return None
    fractional = (match[2] or "")[:decimals]
    if decimals and (len(fractional) != decimals or not fractional.isdigit()):
        return None
    return int(match[1] + fractional)


def rounded_meter_prefix(value, decimals, integer_digits=5):
    """Return the selected meter precision rounded half up when the next digit is known."""
    prefix = meter_prefix(value, decimals, integer_digits)
    if prefix is None or decimals == 0:
        return prefix
    match = re.fullmatch(rf"([0-9]{{1,{integer_digits}}})(?:[.,]([0-9Nn?]+))?", str(value))
    fraction = match[2] or ""
    if len(fraction) > decimals and fraction[decimals].isdigit() and fraction[decimals] >= "5":
        prefix += 1
    return prefix


def common_exact_precision(first, second, max_decimals, integer_digits=5):
    """Return the finest decimal precision explicitly present and equal in both readings."""
    for decimals in range(max_decimals, -1, -1):
        left = meter_prefix(first, decimals, integer_digits)
        right = meter_prefix(second, decimals, integer_digits)
        if left is not None and right is not None and left == right:
            return decimals
    return None


def manual_confirms_failed_auto(history, sample, ocr, *, status, uploaded_image, image_time,
                                reference_time, source_key, manual_decimals, auto_decimals,
                                ocr_confirmed, integer_digits, reference_overridden=False):
    """Only let a manual pass clear failure for the same automatically checked capture."""
    return (
        status == "match"
        and not uploaded_image
        and not reference_overridden
        and image_time == history.get("last_epoch")
        and history.get("check_source") == source_key
        and (reference_time or image_time)
            == (history.get("last_reference_time") or history.get("last_epoch"))
        and history.get("check_status") in (
            "difference", "ocr_unclear", "slfork_unclear",
        )
        and manual_decimals == auto_decimals
        and compare_sample(sample, ocr, auto_decimals, ocr_confirmed=ocr_confirmed,
                           integer_digits=integer_digits)[0] == "match"
    )


def comparison_scope(decimals):
    """Explain precisely which digits participate in a comparison."""
    if decimals == 0:
        return "volle Kubikmeter; Nachkommastellen werden nicht verglichen"
    return f"volle Kubikmeter und {decimals} Nachkommastelle" + ("n" if decimals > 1 else "")


def uncertain_positions(readings, decimals, integer_digits=5):
    """Return 1-based digit positions, or None when all were unreadable."""
    positions = list(range(integer_digits)) + list(range(integer_digits + 1, integer_digits + 1 + decimals))
    evidence = [
        {value[position] if len(value) > position else "?" for value in readings}
        for position in positions
    ]
    if not any(any(char in "0123456789" for char in chars) for chars in evidence):
        return None
    return [
        (position > integer_digits, position - integer_digits if position > integer_digits else position + 1)
        for position, chars in zip(positions, evidence)
        if len(chars) != 1 or not all(char in "0123456789" for char in chars)
    ]


def explain_uncertain_positions(readings, decimals, integer_digits=5):
    """Explain differences at digit positions relevant to this comparison."""
    positions = uncertain_positions(readings, decimals, integer_digits)
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


def read_with_retries(read, data, decimals, progress=None, max_attempts=5, trace=None, *, standalone=False,
                      integer_digits=5, stop_before_attempt=None, force_all_attempts=False,
                      extra_attempts=0):
    """Read one image up to max_attempts times; stop on the first valid agreement."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_CONFIGURED_OCR_ATTEMPTS:
        raise ValueError("OCR-Versuche müssen zwischen 1 und 10 liegen")
    if type(extra_attempts) is not int or not 0 <= extra_attempts <= 10:
        raise ValueError("Zusätzliche OCR-Versuche müssen zwischen 0 und 10 liegen")
    attempt_limit = min(MAX_OCR_ATTEMPTS, max_attempts + extra_attempts)
    readings = []
    for index, profile in enumerate(OCR_PROFILES[:attempt_limit], start=1):
        if index > 1 and stop_before_attempt and stop_before_attempt():
            break
        if progress:
            progress(index - 1, f"OCR-Versuch {index} von {attempt_limit} läuft …")
        try:
            value = read(profile)
        except subprocess.TimeoutExpired as error:
            print(f"OCR-Variante hat das Zeitlimit überschritten: {error}")
            value = "?" * integer_digits + ("." + "?" * decimals if decimals else "")
        status, _ = compare_sample(data, value, decimals, integer_digits=integer_digits)
        readings.append(value)
        if trace is not None:
            trace.append(str(value))
        if progress:
            progress(index, f"OCR-Versuch {index} von {attempt_limit} abgeschlossen.")
        # Stop immediately on a verified match.
        # Without a reference, a valid OCR result ends the read.
        if status == "match" or (status == "ocr_only" and not standalone and not force_all_attempts):
            return value, True, index
        if standalone and index >= max_attempts:
            majority = len(readings) // 2 + 1
            minimum_votes = max(2, majority)
            prefix_length = integer_digits + (decimals + 1 if decimals else 0)
            prefixes = Counter(item[:prefix_length] for item in readings
                               if meter_prefix(item, decimals, integer_digits) is not None)
            stable = next((item for item, count in prefixes.items() if count >= minimum_votes), None)
            if stable is not None:
                return next(item for item in readings if item.startswith(stable)), True, index

    # Keep stable complete reads, then compose only strict-majority digits.
    majority = len(readings) // 2 + 1
    minimum_votes = max(2, majority) if standalone else majority
    prefix_length = integer_digits + (decimals + 1 if decimals else 0)
    prefixes = Counter(value[:prefix_length] for value in readings
                       if meter_prefix(value, decimals, integer_digits) is not None)
    prefix = next((value for value, count in prefixes.items() if count >= minimum_votes), None)
    display = []
    for column in zip(*readings):
        digit, count = Counter(column).most_common(1)[0]
        display.append(digit if count >= majority else "?")
    if prefix is not None:
        display[:prefix_length] = prefix
    positions = list(range(integer_digits))
    if decimals:
        positions.extend(range(integer_digits + 1, integer_digits + 1 + decimals))
    combined = {}
    for position in positions:
        votes = Counter(value[position] for value in readings
                        if position < len(value) and value[position] in "0123456789")
        digit, count = votes.most_common(1)[0] if votes else ("", 0)
        if count >= majority:
            combined[position] = digit
    for position in range(integer_digits):
        if position in combined:
            display[position] = combined[position]
    if decimals:
        for position in range(integer_digits + 1, integer_digits + 1 + decimals):
            if position in combined and position < len(display):
                display[position] = combined[position]
    complete = len(combined) == len(positions)
    if standalone:
        return "".join(display), prefix is not None or (
            attempt_limit > max_attempts and len(readings) >= 2 and complete
        ), len(readings)
    return "".join(display), prefix is not None or complete, len(readings)


def compare_sample(data, ocr, decimals, *, ocr_confirmed=True, integer_digits=5):
    if data.get("reference_is_fallback"):
        return "slfork_unclear", FALLBACK_NOTICE
    if not ocr_confirmed:
        return "ocr_unclear", "Zählerstand nicht sicher erkannt. Bitte die unklaren Stellen im Kamerabild prüfen."
    value = rounded_meter_prefix(ocr, decimals, integer_digits)
    if value is None:
        return "ocr_unclear", "Zählerstand nicht lesbar. Mindestens eine benötigte Ziffer konnte nicht erkannt werden. Bitte das Kamerabild prüfen."
    if data.get("reference_required") is False:
        return "ocr_only", "Zählerstand gelesen, aber ohne Referenzwert nicht bestätigt. Vergleichseinstellung: " + comparison_scope(decimals) + "."
    source_status = data.get("slfork_value_status") or ""
    if re.match(r"^[EW][0-9]+(?:\s|$)", str(source_status)):
        return "slfork_unclear", "Der ESP meldet ein Problem mit der Zählerablesung. Bitte den Wert direkt am ESP prüfen."
    if data.get("slfork_process_error") in (-1, -2, "-1", "-2"):
        return "slfork_unclear", "Die Messung am ESP wurde abgebrochen. Bitte den ESP prüfen und die nächste Aufnahme abwarten."
    raw = rounded_meter_prefix(data["raw_value"], decimals, integer_digits)
    actual = rounded_meter_prefix(data["actual_value"], decimals, integer_digits)
    if raw is None or actual is None:
        return "slfork_unclear", "Referenzwert fehlt oder ist ungültig."
    if raw != actual:
        return "slfork_unclear", "Der ESP liefert widersprüchliche Zählerwerte. Bitte den angezeigten Stand am ESP prüfen."
    if value != actual:
        if decimals == 0:
            return "difference", "Abweichung: Die vollen Kubikmeter stimmen nicht überein. Bitte das Zählerbild prüfen."
        return ("difference",
                f"Abweichung: Gerundet auf {decimals} Nachkommastelle{'' if decimals == 1 else 'n'} "
                "stimmen die Werte nicht überein. Bitte das Zählerbild prüfen.")
    if decimals == 0:
        return "match", "Bestätigt: Die vollen Kubikmeter stimmen überein. Nachkommastellen wurden nicht berücksichtigt."
    return ("match",
            f"Bestätigt: Gerundet auf {decimals} Nachkommastelle{'' if decimals == 1 else 'n'} "
            "stimmen Zählerstand und Referenzwert überein.")


LAST_DIGIT_NOTICE = "Nur die dritte Nachkommastelle ist unklar oder weicht ab."
LAST_DIGIT_PASS = "Die ersten zwei Nachkommastellen stimmen überein. Die dritte Stelle bleibt unbestätigt."
LAST_DIGIT_RETRIES = 3
SUCCESSFUL_CHECKS = ("match", "match_with_warning", "ocr_only")
STANDALONE_PENDING = "standalone_pending"
STANDALONE_PENDING_NOTICE = "Erstes Bild gelesen. Warte auf die zweite Aufnahme zur Gegenprüfung."
STANDALONE_VERIFIED_NOTICE = "Zählerstand mit einer zweiten Aufnahme gegengeprüft."
STANDALONE_REJECTED_NOTICE = "Die zweite Aufnahme passt nicht zum ersten Zählerstand."
REFLECTION_SUGGEST_AFTER = 3


def single_missing_digit(ocr, readings, decimals, integer_digits):
    """Only one required position may be unknown; all others need majority evidence."""
    size = integer_digits + (decimals + 1 if decimals else 0)
    pattern = str(ocr or "")[:size]
    decimal_part = rf"\.[0-9?]{{{decimals}}}" if decimals else ""
    if not re.fullmatch(rf"[0-9?]{{{integer_digits}}}{decimal_part}", pattern) or pattern.count("?") != 1:
        return None
    votes = max(2, len(readings) // 2 + 1)
    for index, digit in enumerate(pattern):
        if digit.isdigit() and sum(len(value) > index and value[index] == digit for value in readings) < votes:
            return None
    return pattern


def estimate_missing_digit(pattern, stamp, previous, following, decimals, max_flow_lph):
    """Accept a digit only when every other value violates a measured bound."""
    before, after = previous["time"], following["time"]
    if not before < stamp < after or after - before > WINDOW_SECONDS:
        return None
    step = 10 ** (3 - decimals)
    low, high = previous["value"], following["value"]
    candidates = []
    for digit in "0123456789":
        reading = pattern.replace("?", digit)
        value = int(reading.replace(".", "")) * step
        if (low <= value <= high
                and value - low - step <= max_flow_lph * (stamp - before) / 3600
                and high - value - step <= max_flow_lph * (after - stamp) / 3600):
            candidates.append(digit)
    if len(candidates) != 1:
        return None
    left, right = pattern.split("?")
    return {"left": left, "digit": candidates[0], "right": right, "time": stamp}


def provisional_digit_estimate(ocr, readings, stamp, previous, decimals, integer_digits, max_flow_lph):
    """Fill at most one position on each side, only inside a measured flow envelope."""
    if previous is None or not 0 < stamp - previous["time"] <= WINDOW_SECONDS:
        return None
    length = integer_digits + (decimals + 1 if decimals else 0)
    pattern = str(ocr or "")[:length]
    whole, _, fraction = pattern.partition(".")
    if (len(whole) != integer_digits or len(fraction) != decimals
            or not re.fullmatch(r"[0-9?]+", whole) or (fraction and not re.fullmatch(r"[0-9?]+", fraction))
            or whole.count("?") > 1 or fraction.count("?") > 1):
        return None
    positions = [index for index, char in enumerate(pattern) if char == "?"]
    if not positions:
        return None
    votes = max(2, len(readings) // 2 + 1)
    if any(char.isdigit() and sum(len(value) > index and value[index] == char for value in readings) < votes
           for index, char in enumerate(pattern)):
        return None
    step = 10 ** (3 - decimals)
    low = previous["value"]
    high = low + step - 1 + max_flow_lph * (stamp - previous["time"]) / 3600
    match = None
    for digits in product("0123456789", repeat=len(positions)):
        chars = list(pattern)
        for index, digit in zip(positions, digits):
            chars[index] = digit
        reading = "".join(chars)
        value = int(reading.replace(".", "")) * step
        if low <= value <= high:
            if match is not None:
                return None
            match = reading
    return {"reading": match, "positions": positions, "time": stamp} if match is not None else None


def track_reflection(history, ocr, readings, stamp, *, verified, unclear, decimals,
                     integer_digits, max_flow_lph, enabled, manual_anchor=None):
    pattern = single_missing_digit(ocr, readings, decimals, integer_digits) if unclear else None
    anchor = history.get("reflection_anchor")
    previous = max((item for item in (anchor, manual_anchor) if item and item["time"] < stamp),
                   key=lambda item: item["time"], default=None)
    provisional = (provisional_digit_estimate(ocr, readings, stamp, previous, decimals, integer_digits, max_flow_lph)
                   if enabled and unclear else None)
    if provisional:
        history["reflection_live_estimate"] = provisional
    else:
        history.pop("reflection_live_estimate", None)
    if pattern:
        position = pattern.index("?")
        last = history.get("reflection_streak", {})
        count = last.get("count", 0) + 1 if last.get("position") == position else 1
        history["reflection_streak"] = {"position": position, "count": min(count, REFLECTION_SUGGEST_AFTER)}
        if enabled and previous:
            history["reflection_pending"] = {"pattern": pattern, "time": stamp, "previous": previous}
    else:
        history.pop("reflection_streak", None)
    if not enabled:
        history.pop("reflection_pending", None)
        history.pop("reflection_estimate", None)
    if verified:
        value = meter_prefix(ocr, decimals, integer_digits)
        if value is None:
            return
        following = {"time": stamp, "value": value * 10 ** (3 - decimals)}
        pending = history.pop("reflection_pending", None)
        if pending:
            estimate = estimate_missing_digit(pending["pattern"], pending["time"], pending["previous"],
                                              following, decimals, max_flow_lph)
            if estimate:
                history["reflection_estimate"] = estimate
        history["reflection_anchor"] = following


def last_digit_can_pass(history, precision_mode):
    return not precision_mode and history.get("last_digit_failures", 0) >= LAST_DIGIT_RETRIES - 1


def differs_only_at_last_digit(data, ocr, readings, integer_digits=5):
    reference = data.get("actual_value")
    # A reduced comparison still needs trustworthy and consistent source values.
    if compare_sample(data, reference, 3, integer_digits=integer_digits)[0] != "match":
        return False
    if compare_sample(data, ocr, 3, integer_digits=integer_digits)[0] == "match":
        return False
    prefix = meter_prefix(reference, 2, integer_digits)
    if prefix != meter_prefix(data["raw_value"], 2, integer_digits) or prefix != meter_prefix(ocr, 2, integer_digits):
        return False
    agreeing = sum(meter_prefix(reading, 2, integer_digits) == prefix for reading in readings)
    return agreeing >= 2 and agreeing > len(readings) // 2


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
    return timestamp_epoch(data["esp_timestamp"], zone)


def timestamp_epoch(value, zone):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=zone)
    return stamp.timestamp()


def slfork_reference(data, image_time, zone, previous_match):
    """Label carried-forward values and find the time of a trusted observation."""
    actual = data["actual_value"]
    fallback = data.get("slfork_fallback_value")
    status = str(data.get("slfork_value_status") or "")
    try:
        reported_time = timestamp_epoch(data.get("slfork_last_valid_timestamp"), zone)
    except (TypeError, ValueError, OverflowError, OSError):
        reported_time = None

    def amount(value):
        text = str(value).replace(",", ".")
        return Decimal(text) if re.fullmatch(r"[0-9]{1,5}(?:\.[0-9]+)?", text) else None

    fallback_amount = amount(fallback)
    is_fallback = bool(FALLBACK_STATUS.search(status)) or (
        fallback_amount is not None and fallback_amount == amount(actual)
        and reported_time is not None and reported_time != image_time
    )
    if not is_fallback:
        valid = not (re.match(r"^[EW][0-9]+(?:\s|$)", status)
                     or data.get("slfork_process_error") in (-1, -2, "-1", "-2"))
        return {"reference_is_fallback": False, "reference": actual,
                "reference_time": image_time if valid and amount(actual) is not None else None}

    displayed = fallback if fallback_amount is not None else actual
    verified_time = previous_match.get("time")
    # Negative-rate handling can advance the fallback timestamp without updating the value.
    if reported_time is None or reported_time >= image_time:
        reported_time = None
    if (amount(displayed) is not None and amount(displayed) == amount(previous_match.get("reading"))
            and isinstance(verified_time, (int, float)) and verified_time < image_time):
        reported_time = max(verified_time, reported_time or verified_time)
    return {"reference_is_fallback": True, "reference": displayed, "reference_time": reported_time}


def sample_epoch(data, zone, now):
    captured = sample_timestamp(data, zone)
    epoch = now.timestamp()
    return captured if epoch - FRESH_SAMPLE_AGE < captured <= epoch + 60 else None


def record_sample(history, data, ocr, zone, now, decimals=0, *, ocr_confirmed=True, integer_digits=5,
                  readings=(), precision_mode=False):
    """Count each in-window cycle at most once, even after a restart."""
    captured = sample_epoch(data, zone, now)
    if captured is None or captured <= history.get("last_epoch", 0):
        return False

    epoch = now.timestamp()
    if "started_at" not in history:
        history.update(started_at=epoch, confirmations=[], status="no_current_sample")
    history["confirmations"] = [old for old in history["confirmations"] if old > epoch - WINDOW_SECONDS]
    status, detail = compare_sample(data, ocr, decimals, ocr_confirmed=ocr_confirmed,
                                    integer_digits=integer_digits)
    if (decimals == 3 and status in ("difference", "ocr_unclear")
            and differs_only_at_last_digit(data, ocr, readings, integer_digits)):
        can_pass = last_digit_can_pass(history, precision_mode)
        retries = min(history.get("last_digit_failures", 0) + 1, LAST_DIGIT_RETRIES)
        history["last_digit_failures"] = retries
        detail = LAST_DIGIT_NOTICE
        if can_pass:
            status, detail = "match_with_warning", LAST_DIGIT_PASS
    else:
        history.pop("last_digit_failures", None)
    if status == "match":
        history["confirmations"].append(captured)
        history["last_match_at"] = captured
    history.update(last_epoch=captured, status=status, ocr_value=ocr, check_detail=detail)
    return True


def valid_interval_minutes(value):
    return type(value) is int and 1 <= value <= MAX_INTERVAL_MINUTES


def automatic_interval_minutes(interval_minutes, source_mode):
    """Observe SLFork's regular cadence while retaining the user's configured interval."""
    return max(RETRY_INTERVAL // 60, interval_minutes) if source_mode == "slfork" else interval_minutes


def defer_duplicate_cycle(history, fetched_at, interval_minutes):
    """Wait for a fresh cycle without changing the outcome, counters or last check."""
    checked_at = last_check_at(history)
    suppressed = history.get("retry_suppressed", False)
    wait = _check_delay(history["check_status"], interval_minutes, suppressed)
    if not suppressed:
        wait = min(wait, RETRY_INTERVAL)
    if checked_at is not None:
        history["last_check_at"] = checked_at
    history["next_check_at"] = fetched_at + wait
    history["check_interval_minutes"] = interval_minutes


def _check_delay(outcome, interval_minutes, retry_suppressed=False):
    interval = interval_minutes * 60
    if outcome == STANDALONE_PENDING:
        return RETRY_INTERVAL
    if outcome in SUCCESSFUL_CHECKS:
        return interval
    return FAILURE_COOLDOWN_INTERVAL if retry_suppressed else min(interval, RETRY_INTERVAL)


def schedule_next_check(history, outcome, checked_at, interval_minutes=DEFAULT_INTERVAL_MINUTES):
    history["check_status"] = outcome
    history["last_check_at"] = checked_at
    if outcome in (*SUCCESSFUL_CHECKS, STANDALONE_PENDING):
        history.pop("failure_since", None)
        history.pop("failure_attempts", None)
        history.pop("retry_suppressed", None)
    else:
        history.setdefault("failure_since", checked_at)
        history["failure_attempts"] = history.get("failure_attempts", 0) + 1
        if history["failure_attempts"] >= FAILURE_RETRY_LIMIT:
            history["retry_suppressed"] = True
    if outcome == "capture_unavailable":
        history.setdefault("capture_failure_since", checked_at)
    else:
        history.pop("capture_failure_since", None)
    history["next_check_at"] = checked_at + _check_delay(
        outcome, interval_minutes, history.get("retry_suppressed", False)
    )
    history["check_interval_minutes"] = interval_minutes


def last_check_at(history):
    stored = history.get("last_check_at")
    if type(stored) in (int, float) and stored > 0:
        return stored
    deadline = history.get("next_check_at")
    outcome = history.get("check_status")
    if not deadline or not outcome:
        return None
    interval_minutes = history.get("check_interval_minutes", DEFAULT_INTERVAL_MINUTES)
    if not valid_interval_minutes(interval_minutes):
        interval_minutes = DEFAULT_INTERVAL_MINUTES
    return deadline - _check_delay(outcome, interval_minutes, history.get("retry_suppressed", False))


def reschedule_next_check(history, interval_minutes):
    """Apply a new interval relative to the same last check, including older schedules."""
    if history.get("check_interval_minutes", DEFAULT_INTERVAL_MINUTES) == interval_minutes:
        return False
    checked_at = last_check_at(history)
    if checked_at is None:
        return False
    history["next_check_at"] = checked_at + _check_delay(
        history["check_status"], interval_minutes, history.get("retry_suppressed", False)
    )
    history["check_interval_minutes"] = interval_minutes
    return True
