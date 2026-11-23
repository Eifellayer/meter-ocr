"""Camera diagnosis for the app (0.5.42): is the picture of the image source good enough to read?

Looks only at what the app already has: the picture of the last check, the cut-out counter of
that check and the debug log of the last 24 hours. Nothing is fetched and no light is switched.
Returns plain values with a verdict per line, so the page can show them without own logic.
"""

from datetime import datetime, timedelta
import io
import json

from PIL import Image, ImageChops, ImageStat

# Thresholds as for the first-frame assessment of the setup (calibration.image_quality_hints).
DARK, BRIGHT, LOW_CONTRAST = 45, 215, 32
# Stricter than the setup (0.065): a counter cut-out with flat areas must not count as blurred.
SOFT_RATIO = 0.04
OLD_PICTURE = 30 * 60
FAILED_OUTCOMES = ("capture_unavailable", "stale_sample")
SUCCESS_OUTCOMES = ("match", "match_with_warning", "ocr_only")

TEXTS = {
    "picture_missing": ("Noch kein Bild einer Prüfung vorhanden.", "No picture of a check yet."),
    "picture_old": ("Das letzte Prüfbild ist älter als 30 Minuten.", "The last check picture is older than 30 minutes."),
    "dark": ("Zählwerk sehr dunkel: Licht oder Belichtung der Kamera prüfen.",
             "Counter very dark: check the light or the exposure of the camera."),
    "bright": ("Zählwerk überstrahlt: Licht schwächer stellen oder anders ausrichten.",
               "Counter washed out: dim the light or turn it a little."),
    "low_contrast": ("Zählwerk kontrastarm: Ziffern heben sich kaum vom Hintergrund ab.",
                     "Counter low in contrast: the digits barely stand out."),
    "soft": ("Zählwerk unscharf: Fokus der Kamera oder Abstand prüfen.",
             "Counter blurred: check the focus or the distance of the camera."),
    "capture_failures": ("Die Bildquelle lieferte in den letzten 24 Stunden {count}-mal kein neues Bild.",
                         "The image source delivered no new picture {count} times in the last 24 hours."),
    "dark_pictures": ("{count}-mal war das Bild trotz Licht zu dunkel.", "{count} times the picture was too dark despite the light."),
    "ok": ("Keine Auffälligkeiten.", "Nothing unusual."),
}


def picture_values(content):
    """Size, brightness, contrast and sharpness of a JPEG/PNG picture, or None."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            size = image.size
            gray = image.convert("L")
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    small = gray.resize((160, max(8, round(160 * gray.height / max(1, gray.width)))), Image.Resampling.LANCZOS)
    levels = sorted(small.tobytes())
    low, high = levels[len(levels) // 10], levels[len(levels) * 9 // 10]
    width, height = small.size
    across = ImageChops.difference(small.crop((0, 0, width - 2, height)), small.crop((2, 0, width, height)))
    down = ImageChops.difference(small.crop((0, 0, width, height - 2)), small.crop((0, 2, width, height)))
    sharpness = (ImageStat.Stat(across).mean[0] + ImageStat.Stat(down).mean[0]) / 2
    return {"width": size[0], "height": size[1], "brightness": round(ImageStat.Stat(small).mean[0]),
            "low": low, "high": high, "contrast": high - low, "sharpness": round(sharpness, 1)}


def counter_hints(values):
    if not values:
        return []
    hints = []
    if values["high"] < DARK:
        hints.append("dark")
    elif values["low"] > BRIGHT:
        hints.append("bright")
    if values["contrast"] < LOW_CONTRAST:
        hints.append("low_contrast")
    elif values["sharpness"] < SOFT_RATIO * values["contrast"]:
        hints.append("soft")
    return hints


def log_counts(text, now):
    """Checks of the last 24 hours from the debug log: total, successful, failed captures, dark pictures."""
    since = now - timedelta(hours=24)
    counts = {"checks": 0, "successful": 0, "capture_failures": 0, "dark_pictures": 0, "exposure_changes": 0}
    for line in str(text or "").splitlines():
        try:
            entry = json.loads(line)
            stamp = datetime.fromisoformat(str(entry.get("time")))
        except (ValueError, AttributeError):
            continue
        if stamp.tzinfo is None:
            stamp = stamp.astimezone()
        if stamp < since:
            continue
        kind = entry.get("kind")
        if kind == "automatic":
            counts["checks"] += 1
            counts["successful"] += entry.get("outcome") in SUCCESS_OUTCOMES
            counts["capture_failures"] += entry.get("outcome") in FAILED_OUTCOMES
        elif kind == "dark_picture":
            counts["dark_pictures"] += 1
        elif kind == "exposure_adjust":
            counts["exposure_changes"] += 1
    return counts


def diagnose(picture, picture_time, counter, log_text, now=None, language="de"):
    """Everything the page shows: values of picture and counter, counts and the verdict lines."""
    now = now or datetime.now().astimezone()
    index = 1 if language == "en" else 0
    whole = picture_values(picture) if picture else None
    cut_out = picture_values(counter) if counter else None
    counts = log_counts(log_text, now)
    keys = []
    if whole is None:
        keys.append(("picture_missing", {}))
    elif picture_time is not None and (now.timestamp() - picture_time) > OLD_PICTURE:
        keys.append(("picture_old", {}))
    keys += [(hint, {}) for hint in counter_hints(cut_out)]
    if counts["capture_failures"]:
        keys.append(("capture_failures", {"count": counts["capture_failures"]}))
    if counts["dark_pictures"]:
        keys.append(("dark_pictures", {"count": counts["dark_pictures"]}))
    hints = [TEXTS[key][index].format(**values) for key, values in keys] or [TEXTS["ok"][index]]
    return {"picture": whole, "picture_time": picture_time, "counter": cut_out, "counts": counts,
            "hints": hints, "problems": [key for key, _ in keys]}
