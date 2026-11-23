"""0.5.37: orientation of the camera picture from labels and red rollers, shadow mode only."""

import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration import Layout  # noqa: E402
from layout import turn_crop  # noqa: E402
import orientation_check  # noqa: E402
import run  # noqa: E402
import shadow_log  # noqa: E402
from test_glyph_match import FIXTURES, STRIPS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def labelled_meter():
    """An invented label plate (no real meter, no serial number)."""
    image = Image.new("RGB", (900, 400), (235, 235, 235))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 36)
    draw.text((20, 20), "Gaszähler G4 Qmax 6 m3/h pmax 0,5 bar", font=font, fill=(0, 0, 0))
    draw.text((20, 300), "1 Imp = 0,01 m3  Baujahr 2019", font=font, fill=(0, 0, 0))
    return image


class LabelTests(unittest.TestCase):
    def test_the_labels_tell_the_clockwise_turn(self):
        for turn in (0, 90, 180, 270):
            guess = orientation_check.label_guess(turn_crop(labelled_meter(), -turn))
            self.assertEqual((turn, False), (guess["rotate"], guess["mirror"]), turn)

    def test_mirrored_labels(self):
        guess = orientation_check.label_guess(ImageOps.mirror(labelled_meter()))
        self.assertEqual((0, True), (guess["rotate"], guess["mirror"]))

    def test_no_text_is_no_evidence(self):
        guess = orientation_check.label_guess(Image.new("RGB", (400, 300), (120, 120, 120)))
        self.assertIsNone(guess["rotate"])


class RedRollerTests(unittest.TestCase):
    def test_real_strips_show_the_red_decimals_on_the_right(self):
        for name, (_, boxes) in STRIPS.items():
            strip = Image.open(FIXTURES / name).convert("RGB")
            self.assertEqual("right", orientation_check.red_side(strip, boxes[:5], boxes[5:])["side"])
            width, height = strip.size
            turned = [(width - r, height - b, width - l, height - t) for l, t, r, b in reversed(boxes)]
            self.assertEqual("left", orientation_check.red_side(strip.rotate(180), turned[:5], turned[5:])["side"])

    def test_without_red_rollers_nothing_is_said(self):
        strip = Image.new("RGB", (400, 60), (30, 30, 30))
        boxes = [(index * 50, 0, index * 50 + 40, 60) for index in range(8)]
        self.assertIsNone(orientation_check.red_side(strip, boxes[:5], boxes[5:])["side"])


class CompareTests(unittest.TestCase):
    def test_frames_turn_clockwise(self):
        self.assertEqual(90, orientation_check.frame_turn(92))
        self.assertEqual(270, orientation_check.frame_turn(-90))
        self.assertEqual(0, orientation_check.frame_turn(3))

    def test_verdict(self):
        upright = {"rotate": 90, "mirror": False}
        self.assertTrue(orientation_check.compare(upright, {"side": "right"}, 90))
        self.assertFalse(orientation_check.compare(upright, {"side": "right"}, -90))
        self.assertFalse(orientation_check.compare({"rotate": None}, {"side": "left"}, 90))
        self.assertIsNone(orientation_check.compare({"rotate": None}, {"side": None}, 90))


class WorkerTests(unittest.TestCase):
    def test_a_saved_setup_is_checked_in_the_shadow_log(self):
        with io.BytesIO() as buffer:
            labelled_meter().save(buffer, "PNG")
            content = buffer.getvalue()
        layout = Layout((100, 100, 420, 160), 0, 200)
        rules = {"integer_digits": 5, "fraction_digits": 3, "image_rotation": 0}
        with TemporaryDirectory() as folder, patch.object(shadow_log, "SHADOW_LOG", Path(folder) / "log.jsonl"):
            run.orientation_shadow(content, layout, rules)
            entry = json.loads(shadow_log.read_text())
        self.assertEqual("orientation", entry["function"])
        self.assertEqual(0, entry["shadow"]["labels"]["rotate"])
        self.assertEqual(0, entry["established"]["frame_turn"])
        self.assertTrue(entry["agree"])

    def test_only_in_shadow_mode(self):
        source = (ROOT / "run.py").read_text(encoding="utf-8")
        self.assertIn("if shadow_log.enabled(get_auto_rules()) and not attempt.automatic:", source)
        self.assertIn("orientation_check.py", (ROOT / "Dockerfile").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
