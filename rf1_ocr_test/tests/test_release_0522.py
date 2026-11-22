"""0.5.22: the right-angle search is not blocked by a frame that is itself at a right angle."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import calibration  # noqa: E402
from calibration import Calibration, Layout, upright_layout  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000}
SIDEWAYS = Layout((299, 32, 363, 416), -90, 240)
UPRIGHT = Layout((100, 230, 400, 292), -3, 190)


def picture():
    return Image.new("RGB", (800, 600), (40, 40, 40))


def searched_at_right_angles(layout, reading, rules=RULES, **job):
    calibration_job = Calibration(5, 3, **job)
    with patch.object(calibration, "layouts", return_value=[layout]), \
            patch.object(calibration, "quarter_turn_layouts", return_value=[]) as quarter:
        calibration_job.examine(picture(), None, {"reference_required": False}, 100, rules,
                                lambda tried, profile: reading, lambda: False)
    return quarter.called


class RightAngleSearchTests(unittest.TestCase):
    def test_a_sideways_frame_reading_the_whole_digits_does_not_block_the_search(self):
        # The old, too narrow frame at −90° reads "10513" but never the decimals.
        self.assertTrue(searched_at_right_angles(SIDEWAYS, "10513.???"))

    def test_an_upright_frame_reading_the_whole_digits_still_ends_the_search(self):
        self.assertFalse(searched_at_right_angles(UPRIGHT, "10513.???"))

    def test_the_repair_searches_right_angles_for_a_meter_set_up_sideways(self):
        rules = {**RULES, "crop": "299,32,363,416", "rotation": -90, "width": 240}
        self.assertTrue(searched_at_right_angles(SIDEWAYS, "10513.???", rules, automatic=True))

    def test_the_repair_of_an_upright_meter_keeps_away_from_right_angles(self):
        rules = {**RULES, "crop": "100,230,400,292", "rotation": -3, "width": 190}
        self.assertFalse(searched_at_right_angles(UPRIGHT, "?????.???", rules, automatic=True))

    def test_a_repair_without_a_saved_frame_keeps_away_from_right_angles(self):
        self.assertFalse(searched_at_right_angles(UPRIGHT, "?????.???", RULES, automatic=True))

    def test_upright_means_less_than_45_degrees(self):
        self.assertTrue(upright_layout(Layout((0, 0, 10, 10), -20, 5)))
        self.assertFalse(upright_layout(Layout((0, 0, 10, 10), -85, 5)))
        self.assertFalse(upright_layout(Layout((0, 0, 10, 10), 176, 5)))


if __name__ == "__main__":
    unittest.main()
