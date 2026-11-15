"""Settings for SLFork, Home Assistant camera verification, and standalone OCR."""

import re
from urllib.parse import urlsplit

SOURCE_MODES = ("slfork", "camera", "esphome")
CAMERA = re.compile(r"camera\.[a-z0-9_]+")
REFERENCE = re.compile(r"sensor\.[a-z0-9_]+")


def source_rules(values):
    mode, url, camera, reference = (values[key].strip() for key in ("mode", "url", "camera", "reference"))
    if mode not in SOURCE_MODES:
        raise ValueError("Ungültige Bildquelle")
    if mode == "slfork":
        address = urlsplit(url)
        if (address.scheme not in ("http", "https") or not address.hostname
                or address.username is not None or address.query or address.fragment
                or any(character.isspace() for character in url)):
            raise ValueError("Ungültige SLFork-Adresse")
    if mode != "slfork" and not CAMERA.fullmatch(camera):
        raise ValueError("Ungültige Kamera-Entität")
    if mode == "camera" and reference and not REFERENCE.fullmatch(reference):
        raise ValueError("Ungültiger Referenzsensor")
    return dict(mode=mode, url=url, camera=camera, reference=reference)
