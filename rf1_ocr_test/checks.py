"""Independent OCR and restart-safe agreement counts over a rolling window."""
from collections import Counter
from datetime import datetime
from decimal import Decimal
import io
import hashlib
import json
from itertools import product
import re
import subprocess
import time

from PIL import Image, ImageChops, ImageFilter, ImageOps

WINDOW_SECONDS = 24 * 60 * 60
REQUIRED_MATCHES = 5
DEFAULT_INTERVAL_MINUTES = 10
LEGACY_INTERVAL_MINUTES = 60
MAX_INTERVAL_MINUTES = 24 * 60
NORMAL_INTERVAL = DEFAULT_INTERVAL_MINUTES * 60
RETRY_INTERVAL = 5 * 60
STANDALONE_SECOND_CAPTURE_DELAY = 5
STANDALONE_CACHED_CAPTURE_DELAY = 15
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


def lighting_ocr_profiles(picture):
    """Try existing shadow-correction profiles sooner on dim or uneven images."""
    gray = picture.convert("L").resize((64, 20), Image.Resampling.BILINEAR)
    levels = sorted(gray.tobytes())
    low, high = levels[len(levels) // 10], levels[len(levels) * 9 // 10]
    zones = gray.resize((4, 2), Image.Resampling.BOX).tobytes()
    if high < 75 or high - low < 45 or max(zones) - min(zones) >= 45:
        return (OCR_PROFILES[0], OCR_PROFILES[2], OCR_PROFILES[1], *OCR_PROFILES[3:])
    return OCR_PROFILES


def crop_register(picture, crop):
    left, top, right, bottom = crop
    if not (0 <= left < right <= picture.width and 0 <= top < bottom <= picture.height):
        raise ValueError(f"Ausschnitt {crop} liegt außerhalb von {picture.size}")
    return picture.crop(crop)


def read_register(picture, light_digits, digits=5, *, force_polarity=False, profile=OCR_PROFILES[0], deadline=None,
                  process_env=None, isolated_digit=False):
    image = picture.convert("L")
    polarities = (light_digits,) if force_polarity else (light_digits, not light_digits)
    reads = set()
    limits = {}
    if deadline is not None:
        limits["deadline"] = deadline
    if process_env is not None:
        limits["process_env"] = process_env
    if isolated_digit and digits == 1:
        limits["isolated_digit"] = True
    for invert in polarities:
        gray = ImageOps.invert(image) if invert else image
        value = read_polarity(gray, digits, profile, **limits)
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


def read_polarity(image, digits, profile, *, deadline=None, process_env=None, isolated_digit=False):
    cutoff, sharpening, threshold, reduce_shadows = profile
    if reduce_shadows:
        image = reduce_uneven_lighting(image)
    gray = ImageOps.autocontrast(image, cutoff=cutoff)
    variants = (
        gray,
        gray.filter(ImageFilter.UnsharpMask(radius=2, percent=sharpening, threshold=2)),
        gray.point(lambda value: 255 if value >= threshold else 0),
    )
    def read_variant(variant, segmentation):
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
                ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", str(segmentation),
                 "-c", "tessedit_char_whitelist=0123456789"],
                input=png.getvalue(), capture_output=True, timeout=timeout, check=True,
                **({"env": process_env} if process_env is not None else {}),
            ).stdout.decode("ascii", errors="ignore").strip()
        return result if len(result) == digits and result.isascii() and result.isdigit() else None

    votes = Counter(filter(None, (read_variant(variant, 10 if digits == 1 else 7) for variant in variants)))
    if len(votes) == 1:
        value, count = votes.most_common(1)[0]
        if count >= 2:
            return value
    if isolated_digit and not votes:
        # A tightly marked, high-contrast glyph can be missed by single-character
        # segmentation. Accept the extra evidence only from an isolated shape.
        binary = gray.point(lambda value: 255 if value >= min(148, max(140, threshold)) else 0)
        ink = ImageOps.invert(binary)
        bounds = ink.getbbox()
        if bounds and 0.04 <= ink.histogram()[255] / (ink.width * ink.height) <= 0.42:
            left, top, right, bottom = bounds
            if (left > 0 and top > 0 and right < ink.width and bottom < ink.height
                    and bottom - top >= ink.height * .35 and right - left >= ink.width * .15):
                value = read_variant(binary, 8)
                if value and value == read_variant(binary, 13):
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
                      extra_attempts=0, profiles=OCR_PROFILES, defer_composition=False,
                      exact_prefix=False):
    """Read one image up to max_attempts times; stop on the first valid agreement."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_CONFIGURED_OCR_ATTEMPTS:
        raise ValueError("OCR-Versuche müssen zwischen 1 und 10 liegen")
    if type(extra_attempts) is not int or not 0 <= extra_attempts <= 10:
        raise ValueError("Zusätzliche OCR-Versuche müssen zwischen 0 und 10 liegen")
    attempt_limit = min(MAX_OCR_ATTEMPTS, max_attempts + extra_attempts)
    readings = []
    for index, profile in enumerate(profiles[:attempt_limit], start=1):
        if index > 1 and stop_before_attempt and stop_before_attempt():
            break
        if progress:
            progress(index - 1, f"Versuch {index} von {attempt_limit} läuft …")
        try:
            value = read(profile)
        except subprocess.TimeoutExpired as error:
            print(f"OCR-Variante hat das Zeitlimit überschritten: {error}")
            value = "?" * integer_digits + ("." + "?" * decimals if decimals else "")
        status, _ = compare_sample(data, value, decimals, integer_digits=integer_digits,
                                   exact_prefix=exact_prefix)
        readings.append(value)
        if trace is not None:
            trace.append(str(value))
        if progress:
            progress(index, f"Versuch {index} von {attempt_limit} abgeschlossen.")
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

    value, confirmed = resolve_ocr_readings(
        readings, decimals, integer_digits, standalone=standalone,
        standalone_composition=attempt_limit > max_attempts, compose=not defer_composition,
    )
    return value, confirmed, len(readings)


def resolve_ocr_readings(readings, decimals, integer_digits, *, standalone=False,
                         standalone_composition=False, compose=True):
    # Keep stable complete reads, then compose only strict-majority digits.
    majority = len(readings) // 2 + 1
    minimum_votes = max(2, majority) if standalone else majority
    prefix_length = integer_digits + (decimals + 1 if decimals else 0)
    prefixes = Counter(value[:prefix_length] for value in readings
                       if meter_prefix(value, decimals, integer_digits) is not None)
    prefix = next((value for value, count in prefixes.items() if count >= minimum_votes), None)
    if not compose:
        if prefix is not None:
            return next(value for value in readings if value.startswith(prefix)), True
        return max(readings, key=lambda value: sum(ch.isdigit() for ch in value[:prefix_length]), default=""), False
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
            standalone_composition and len(readings) >= 2 and complete
        )
    return "".join(display), prefix is not None or complete


def compare_sample(data, ocr, decimals, *, ocr_confirmed=True, integer_digits=5, exact_prefix=False):
    if data.get("reference_is_fallback"):
        return "slfork_unclear", FALLBACK_NOTICE
    if not ocr_confirmed:
        return "ocr_unclear", "Zählerstand nicht sicher erkannt. Bitte die unklaren Stellen im Kamerabild prüfen."
    prefix_reader = meter_prefix if exact_prefix else rounded_meter_prefix
    value = prefix_reader(ocr, decimals, integer_digits)
    if value is None:
        return "ocr_unclear", "Zählerstand nicht lesbar. Mindestens eine benötigte Ziffer konnte nicht erkannt werden. Bitte das Kamerabild prüfen."
    if data.get("reference_required") is False:
        return "ocr_only", "Zählerstand gelesen, aber ohne Referenzwert nicht bestätigt. Vergleichseinstellung: " + comparison_scope(decimals) + "."
    source_status = data.get("slfork_value_status") or ""
    if re.match(r"^[EW][0-9]+(?:\s|$)", str(source_status)):
        return "slfork_unclear", "Der ESP meldet ein Problem mit der Zählerablesung. Bitte den Wert direkt am ESP prüfen."
    if data.get("slfork_process_error") in (-1, -2, "-1", "-2"):
        return "slfork_unclear", "Die Messung am ESP wurde abgebrochen. Bitte den ESP prüfen und die nächste Aufnahme abwarten."
    raw = prefix_reader(data["raw_value"], decimals, integer_digits)
    actual = prefix_reader(data["actual_value"], decimals, integer_digits)
    if raw is None or actual is None:
        return "slfork_unclear", "Referenzwert fehlt oder ist ungültig."
    if raw != actual:
        return "slfork_unclear", "Der ESP liefert widersprüchliche Zählerwerte. Bitte den angezeigten Stand am ESP prüfen."
    if value != actual:
        if decimals == 0:
            return "difference", "Abweichung: Die vollen Kubikmeter stimmen nicht überein. Bitte das Zählerbild prüfen."
        if exact_prefix:
            return ("difference", f"Abweichung: Die ersten {decimals} Nachkommastellen "
                    "stimmen ohne Rundung nicht mit der Referenz überein.")
        return ("difference",
                f"Abweichung: Gerundet auf {decimals} Nachkommastelle{'' if decimals == 1 else 'n'} "
                "stimmen die Werte nicht überein. Bitte das Zählerbild prüfen.")
    if decimals == 0:
        return "match", "Bestätigt: Die vollen Kubikmeter stimmen überein. Nachkommastellen wurden nicht berücksichtigt."
    if exact_prefix:
        return ("match", f"Bestätigt: Die ersten {decimals} Nachkommastellen "
                "stimmen ohne Rundung mit der Referenz überein. Die nächste Stelle bleibt unbestätigt.")
    return ("match",
            f"Bestätigt: Gerundet auf {decimals} Nachkommastelle{'' if decimals == 1 else 'n'} "
            "stimmen Zählerstand und Referenzwert überein.")


LAST_DIGIT_NOTICE = "Nur die dritte Nachkommastelle ist unklar oder weicht ab."
LAST_DIGIT_PASS = "Die ersten zwei Nachkommastellen stimmen überein. Die dritte Stelle bleibt unbestätigt."
LAST_DIGIT_RETRIES = 3
SEVENTH_DIGIT_WAIT_SECONDS = 30 * 60
SEVENTH_DIGIT_WAIT_NOTICE = (
    "Warte auf einen höheren Zählerstand. Die nächste automatische Prüfung erfolgt "
    "wegen der unklaren siebten Ziffer in 30 Minuten."
)
SEVENTH_DIGIT_PASS = (
    "Die ersten sechs Ziffern stimmen mit der gültigen Referenz überein (ohne Rundung). "
    "Die siebte Ziffer ist noch nicht sicher lesbar: Für diesen Durchlauf nur "
    "eine Nachkommastelle teilbestätigt. Der Verbrauch und die eingestellte "
    "Genauigkeit bleiben unverändert. Die App wartet auf einen höheren "
    "Zählerstand; deshalb wird das Prüfintervall vorübergehend auf 30 Minuten gesetzt."
)
SUCCESSFUL_CHECKS = ("match", "match_with_warning", "ocr_only")
STANDALONE_PENDING = "standalone_pending"
STANDALONE_PENDING_NOTICE = "Erstes Bild gelesen. Warte auf die zweite Aufnahme zur Gegenprüfung."
STANDALONE_VERIFIED_NOTICE = "Zählerstand mit einer zweiten Aufnahme gegengeprüft."
STANDALONE_REJECTED_NOTICE = "Die zweite Aufnahme passt nicht zum ersten Zählerstand."
REFLECTION_SUGGEST_AFTER = 3


def missing_digit_pattern(ocr, decimals, integer_digits):
    """Find a single missing digit among the positions required for comparison."""
    size = integer_digits + (decimals + 1 if decimals else 0)
    pattern = str(ocr or "")[:size]
    decimal_part = rf"\.[0-9?]{{{decimals}}}" if decimals else ""
    if not re.fullmatch(rf"[0-9?]{{{integer_digits}}}{decimal_part}", pattern) or pattern.count("?") != 1:
        return None
    return pattern


def single_missing_digit(ocr, readings, decimals, integer_digits):
    """Require majority evidence for all the visible neighbours."""
    pattern = missing_digit_pattern(ocr, decimals, integer_digits)
    if pattern is None:
        return None
    votes = max(2, len(readings) // 2 + 1)
    for index, digit in enumerate(pattern):
        if digit.isdigit() and sum(len(value) > index and value[index] == digit for value in readings) < votes:
            return None
    return pattern


def disputed_digit_pattern(readings, decimals, integer_digits):
    """A frame is worth rechecking when exactly one required position lacks agreement."""
    length = integer_digits + (decimals + 1 if decimals else 0)
    rows = [value[:length] for value in readings]
    shape = rf"[0-9?]{{{integer_digits}}}" + (rf"\.[0-9?]{{{decimals}}}" if decimals else "")
    if len(rows) < 2 or any(not re.fullmatch(shape, row) for row in rows):
        return None
    consensus = "".join(column[0] if len(set(column)) == 1 else "?" for column in zip(*rows))
    return consensus if consensus.count("?") == 1 else None


def recommended_comparison_decimals(history, decimals, integer_digits):
    """Offer a lower comparison precision after repeated trouble on one decimal place."""
    if decimals < 2:
        return None
    if decimals == 3 and history.get("last_digit_failures", 0) >= 2:
        return 2
    issue = history.get("reflection_streak", {})
    position = issue.get("position")
    if (history.get("check_status") == "ocr_unclear" and issue.get("count", 0) >= 2
            and type(position) is int and integer_digits + 2 <= position <= integer_digits + decimals):
        return position - integer_digits - 1
    return None


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


ANCHORED_LEADING_NOTICE = "Unveränderliche führende Stellen aus dem zuletzt bestätigten Stand ergänzt."


def anchor_bounds(anchor, stamp, decimals, max_flow_lph):
    """Return the litre range a meter can show at stamp after a verified anchor."""
    if (not isinstance(anchor, dict) or type(anchor.get("value")) is not int
            or type(anchor.get("time")) not in (int, float)
            or type(stamp) not in (int, float) or type(max_flow_lph) not in (int, float) or max_flow_lph <= 0):
        return None
    elapsed = stamp - anchor["time"]
    if not 0 < elapsed <= WINDOW_SECONDS or anchor["value"] < 0:
        return None
    step = 10 ** (3 - decimals)
    low = anchor["value"]
    return low, low + step + int(max_flow_lph * elapsed / 3600)


def anchored_leading_digits(readings, anchor, stamp, decimals, integer_digits, max_flow_lph):
    """Fill unreadable leading whole digits that cannot have changed since a verified reading.

    Between the anchor and the maximum possible flow, every reachable value shares
    a common leading prefix. Only unclear positions inside that prefix are filled.
    A majority reading that contradicts the anchor aborts the fill. Returns the
    normalized readings and the filled 0-based positions, or None.
    """
    bounds = anchor_bounds(anchor, stamp, decimals, max_flow_lph)
    if bounds is None or not readings or not 1 <= integer_digits <= 9:
        return None
    low, high = (value // 1000 for value in bounds)
    if high >= 10 ** integer_digits:
        return None
    lowest, highest = str(low).zfill(integer_digits), str(high).zfill(integer_digits)
    frozen = 0
    while frozen < integer_digits and lowest[frozen] == highest[frozen]:
        frozen += 1
    rows = [str(value) for value in readings]
    if frozen == 0 or any(len(row) < integer_digits or not re.fullmatch(r"[0-9?]+", row[:integer_digits])
                          for row in rows):
        return None
    majority = len(rows) // 2 + 1
    filled = []
    for position in range(frozen):
        votes = Counter(row[position] for row in rows if row[position].isdigit())
        digit, count = votes.most_common(1)[0] if votes else ("", 0)
        if count >= majority:
            if digit != lowest[position]:
                return None
        else:
            filled.append(position)
    if not filled:
        return None
    normalized = [lowest[:frozen] + row[frozen:] for row in rows]
    return normalized, filled


def within_anchor_bounds(ocr, anchor, stamp, decimals, integer_digits, max_flow_lph):
    """Accept an anchored result only inside the physically reachable range."""
    bounds = anchor_bounds(anchor, stamp, decimals, max_flow_lph)
    value = meter_prefix(ocr, decimals, integer_digits)
    if bounds is None or value is None:
        return False
    step = 10 ** (3 - decimals)
    litres = value * step
    # One display step below tolerates a jittering last roller between two photographs.
    return bounds[0] - step <= litres <= bounds[1]


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


def seventh_digit_can_pass(data, ocr, readings, integer_digits=5):
    """Safely accept six matching digits when only the seventh roller is unclear.

    This is a *partial* reference comparison without rounding. Do not synthesize a
    precise OCR reading, confirm consumption, or modify configured precision.
    """
    if data.get("reference_required") is False or len(readings) < 2:
        return False
    reference = data.get("actual_value")
    if not reference or compare_sample(data, reference, 2, integer_digits=integer_digits)[0] != "match":
        return False
    prefix = meter_prefix(reference, 1, integer_digits)
    if (prefix is None or meter_prefix(data["raw_value"], 1, integer_digits) != prefix
            or meter_prefix(ocr, 1, integer_digits) != prefix):
        return False
    agreeing = [
        str(reading).replace(",", ".").partition(".")[2][1:2]
        for reading in readings if meter_prefix(reading, 1, integer_digits) == prefix
    ]
    if len(agreeing) < 2 or len(agreeing) <= len(readings) // 2:
        return False
    # A consistently recognized but *wrong* seventh digit is a real mismatch,
    # not a roller transition. The seventh position must actually be uncertain.
    digit_votes = Counter(value for value in agreeing if value.isdigit())
    return not digit_votes or digit_votes.most_common(1)[0][1] * 2 <= len(agreeing)


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
                  readings=(), precision_mode=False, exact_prefix=False):
    """Count each in-window cycle at most once, even after a restart."""
    captured = sample_epoch(data, zone, now)
    if captured is None or captured <= history.get("last_epoch", 0):
        return False

    epoch = now.timestamp()
    if "started_at" not in history:
        history.update(started_at=epoch, confirmations=[], status="no_current_sample")
    history["confirmations"] = [old for old in history["confirmations"] if old > epoch - WINDOW_SECONDS]
    status, detail = compare_sample(data, ocr, decimals, ocr_confirmed=ocr_confirmed,
                                    integer_digits=integer_digits, exact_prefix=exact_prefix)
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
    if (decimals == 2 and not precision_mode and status in ("difference", "ocr_unclear")
            and seventh_digit_can_pass(data, ocr, readings, integer_digits)):
        status, detail = "match_with_warning", SEVENTH_DIGIT_PASS
        history["seventh_digit_wait"] = True
    else:
        history.pop("seventh_digit_wait", None)
    if status == "match":
        history["confirmations"].append(captured)
        history["last_match_at"] = captured
    history.update(last_epoch=captured, status=status, ocr_value=ocr, check_detail=detail)
    return True


def valid_interval_minutes(value):
    return type(value) is int and 1 <= value <= MAX_INTERVAL_MINUTES


SETUP_STABILIZATION_SECONDS = 20 * 60
SETUP_OPTIMIZATION_PAUSE_SECONDS = 60 * 60
SETUP_CHECK_INTERVAL_MINUTES = 5


def setup_source_id(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def stationary_partial_active(rules, source):
    revision = rules.get("crop_revision")
    return (rules["decimals"] == 3 and not rules.get("precision_mode") and bool(revision)
            and rules.get("stationary_partial_scope") == setup_source_id([source, revision]))


# A failed optional eighth-digit search must not permanently strand a saved
# seven-digit setup. Retry infrequently and remember the deadline across restarts.
EIGHTH_DIGIT_RETRY_SECONDS = 60 * 60


def eighth_digit_retry_due(rules, source, history, now):
    """Can a saved seven-digit setup attempt its optional eighth digit again?"""
    deadline = history.get("eighth_digit_retry_at", 0)
    return (stationary_partial_active(rules, source)
            and rules.get("fraction_digits") == 3
            and (type(deadline) not in (int, float) or now >= deadline))


def resume_optional_eighth_digit(history, rules, source, now, begin):
    """Start one bounded fine-check and persist its next allowable retry time."""
    if not eighth_digit_retry_due(rules, source, history, now) or not begin():
        return False
    history["eighth_digit_retry_at"] = now + EIGHTH_DIGIT_RETRY_SECONDS
    return True


def setup_deadlines(rules, source):
    completed = rules.get("setup_completed")
    if isinstance(completed, dict) and completed.get("source") == setup_source_id(source):
        stamp = completed.get("time")
        if type(stamp) in (int, float) and 0 < stamp < 10 ** 12:
            return stamp + SETUP_STABILIZATION_SECONDS, stamp + SETUP_OPTIMIZATION_PAUSE_SECONDS
    return 0, 0


def stabilization_interval(interval, until, now):
    return min(interval, SETUP_CHECK_INTERVAL_MINUTES) if now < until else interval


def automatic_interval_minutes(interval_minutes, source_mode):
    """Observe SLFork's regular cadence while retaining the user's configured interval."""
    return max(RETRY_INTERVAL // 60, interval_minutes) if source_mode == "slfork" else interval_minutes


def defer_duplicate_cycle(history, fetched_at, interval_minutes):
    """Wait for a fresh cycle without changing the outcome, counters or last check."""
    checked_at = last_check_at(history)
    suppressed = history.get("retry_suppressed", False)
    seventh_wait = bool(history.get("seventh_digit_wait"))
    wait = _check_delay(history["check_status"], interval_minutes, suppressed,
                        seventh_digit_wait=seventh_wait)
    if not suppressed and not seventh_wait:
        wait = min(wait, RETRY_INTERVAL)
    if checked_at is not None:
        history["last_check_at"] = checked_at
    history["next_check_at"] = fetched_at + wait
    history["check_interval_minutes"] = interval_minutes


def _check_delay(outcome, interval_minutes, retry_suppressed=False, *, seventh_digit_wait=False):
    interval = interval_minutes * 60
    if outcome == "match_with_warning" and seventh_digit_wait:
        return SEVENTH_DIGIT_WAIT_SECONDS
    if outcome == STANDALONE_PENDING:
        return STANDALONE_SECOND_CAPTURE_DELAY
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
        outcome, interval_minutes, history.get("retry_suppressed", False),
        seventh_digit_wait=bool(history.get("seventh_digit_wait")),
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
    interval_minutes = history.get("check_interval_minutes", LEGACY_INTERVAL_MINUTES)
    if not valid_interval_minutes(interval_minutes):
        interval_minutes = LEGACY_INTERVAL_MINUTES
    return deadline - _check_delay(
        outcome, interval_minutes, history.get("retry_suppressed", False),
        seventh_digit_wait=bool(history.get("seventh_digit_wait")),
    )


def reschedule_next_check(history, interval_minutes):
    """Apply a new interval relative to the same last check, including older schedules."""
    if history.get("check_interval_minutes", LEGACY_INTERVAL_MINUTES) == interval_minutes:
        return False
    checked_at = last_check_at(history)
    if checked_at is None:
        return False
    history["next_check_at"] = checked_at + _check_delay(
        history["check_status"], interval_minutes, history.get("retry_suppressed", False),
        seventh_digit_wait=bool(history.get("seventh_digit_wait")),
    )
    history["check_interval_minutes"] = interval_minutes
    return True
