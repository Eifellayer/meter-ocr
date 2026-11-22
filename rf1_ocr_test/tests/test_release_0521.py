"""0.5.21: a meter turned by a right angle that also hangs a few degrees askew."""

import sys
import unittest
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration  # noqa: E402
from calibration import quarter_rotation, quarter_turn_layouts  # noqa: E402
from test_release_040 import tilted_meter  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000}


def sideways_meter(tilt):
    """Synthetic meter (cut-out digit strip, no serial number) turned a quarter and ``tilt`` degrees.

    ``turn_crop(frame, -90 + tilt)`` levels it again.
    """
    return tilted_meter(tilt, serial=False).transpose(Image.Transpose.ROTATE_270)


class QuarterTurnTiltTests(unittest.TestCase):
    def test_a_sideways_meter_keeps_its_measured_tilt(self):
        rotations = {layout.rotation for layout in quarter_turn_layouts(sideways_meter(5), RULES, None)}
        self.assertTrue(rotations & {-86, -85, -84}, rotations)

    def test_the_tilted_frame_holds_the_whole_counter(self):
        frame = sideways_meter(5)
        tilted = [layout for layout in quarter_turn_layouts(frame, RULES, None) if -86 <= layout.rotation <= -84]
        straight = [layout for layout in quarter_turn_layouts(sideways_meter(0), RULES, None)
                    if layout.rotation == -90]
        self.assertTrue(tilted and straight)
        # A frame levelled by the tilt is wider across the counter than one cut for an upright row.
        width = max(layout.box[2] - layout.box[0] for layout in tilted)
        self.assertGreater(width, max(layout.box[2] - layout.box[0] for layout in straight))

    def test_a_straight_sideways_meter_still_uses_a_plain_quarter_turn(self):
        rotations = {layout.rotation for layout in quarter_turn_layouts(sideways_meter(0), RULES, None)}
        self.assertIn(-90, rotations)
        self.assertFalse({rotation for rotation in rotations if rotation % 90}, rotations)

    def test_no_measured_tilt_keeps_the_old_upright_search(self):
        seen = []
        original = calibration.layouts

        def recording(*args, **kwargs):
            seen.append(kwargs.get("skew"))
            return original(*args, **kwargs)

        calibration.layouts = recording
        try:
            list(quarter_turn_layouts(Image.new("RGB", (300, 200), (90, 90, 90)), RULES, None))
        finally:
            calibration.layouts = original
        self.assertEqual([None, None, None], seen)


class PhotographedStripTests(unittest.TestCase):
    """Cut-out digit strip of a counter turned sideways and about 5° askew (nothing else of the meter)."""

    @staticmethod
    def frame():
        strip = Image.open(Path(__file__).with_name("fixtures") / "sideways_tilted_strip.png").convert("RGB")
        canvas = Image.new("RGB", (800, 600), (95, 95, 95))
        canvas.paste(strip, (280, 0))
        return canvas

    def test_the_tilt_is_measured_in_the_turned_picture(self):
        self.assertIn(calibration.estimate_skew(calibration.turn_crop(self.frame(), -90)), (4, 5, 6))

    def test_the_setup_proposes_the_tilted_quarter_turn(self):
        rotations = {layout.rotation for layout in quarter_turn_layouts(self.frame(), RULES, None)}
        self.assertTrue(rotations & {-86, -85, -84}, rotations)


class QuarterRotationTests(unittest.TestCase):
    def test_tilt_is_added_to_the_right_angle(self):
        self.assertEqual(-85, quarter_rotation(-90, 5))
        self.assertEqual(87, quarter_rotation(90, -3))

    def test_upside_down_stays_within_half_a_turn(self):
        self.assertEqual(-176, quarter_rotation(180, 4))
        self.assertEqual(176, quarter_rotation(180, -4))

    def test_no_tilt_keeps_the_right_angle_unchanged(self):
        for quarter in (180, 90, -90):
            with self.subTest(quarter=quarter):
                self.assertEqual(quarter, quarter_rotation(quarter, 0))


if __name__ == "__main__":
    unittest.main()
