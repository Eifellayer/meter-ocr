"""0.5.42: camera diagnosis from the last check picture and the debug log."""

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import camera_diagnosis  # noqa: E402
import panel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def jpeg(image):
    with io.BytesIO() as buffer:
        image.save(buffer, "JPEG", quality=92)
        return buffer.getvalue()


def counter(background=30, ink=220, blur=0):
    image = Image.new("L", (400, 80), background)
    draw = ImageDraw.Draw(image)
    for index in range(8):
        draw.rectangle((10 + index * 48, 15, 40 + index * 48, 65), outline=ink, width=5)
    return image.filter(ImageFilter.GaussianBlur(blur)) if blur else image


def log(*entries):
    return "\n".join(json.dumps({"time": (NOW - timedelta(hours=hours)).isoformat(), **fields})
                     for hours, fields in entries)


class DiagnosisTests(unittest.TestCase):
    def test_a_good_picture(self):
        result = camera_diagnosis.diagnose(jpeg(counter().convert("RGB")), NOW.timestamp() - 60, jpeg(counter()),
                                           log((1, {"kind": "automatic", "outcome": "ocr_only"})), NOW)
        self.assertEqual([], result["problems"])
        self.assertEqual(["Keine Auffälligkeiten."], result["hints"])
        self.assertEqual((1, 1), (result["counts"]["checks"], result["counts"]["successful"]))
        self.assertEqual((400, 80), (result["picture"]["width"], result["picture"]["height"]))

    def test_dark_blurred_old_and_failing(self):
        dark = camera_diagnosis.diagnose(jpeg(counter(5, 35).convert("RGB")), NOW.timestamp() - 3600,
                                         jpeg(counter(5, 35)), log(
                                             (2, {"kind": "automatic", "outcome": "capture_unavailable"}),
                                             (3, {"kind": "automatic", "outcome": "stale_sample"}),
                                             (30, {"kind": "automatic", "outcome": "capture_unavailable"}),
                                             (1, {"kind": "dark_picture"})), NOW)
        self.assertEqual(["picture_old", "dark", "low_contrast", "capture_failures", "dark_pictures"], dark["problems"])
        self.assertIn("2-mal kein neues Bild", " ".join(dark["hints"]))
        # Good contrast but hardly any edges: blurred. A real cut-out with flat areas is not.
        self.assertEqual(["soft"], camera_diagnosis.counter_hints({"high": 200, "low": 40, "contrast": 160, "sharpness": 5}))
        strip = (ROOT / "tests" / "fixtures" / "esphome_blur_strip_0057.png").read_bytes()
        self.assertEqual([], camera_diagnosis.counter_hints(camera_diagnosis.picture_values(strip)))

    def test_nothing_yet_and_english(self):
        result = camera_diagnosis.diagnose(None, None, None, "", NOW, language="en")
        self.assertEqual(["No picture of a check yet."], result["hints"])


class PanelTests(unittest.TestCase):
    def test_section_and_route(self):
        self.assertIn('<details id="camera-diagnosis">', panel.PAGE)
        self.assertIn('if path == "/kamera-diagnose":', (ROOT / "panel.py").read_text(encoding="utf-8"))
        self.assertIn("camera_diagnosis.py", (ROOT / "Dockerfile").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
