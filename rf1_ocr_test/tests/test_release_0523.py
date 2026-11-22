"""0.5.23: scattered digits read on a label do not stop the search at right angles."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import calibration  # noqa: E402
from calibration import Calibration, Layout, whole_like  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000}
SIDEWAYS_RULES = {**RULES, "crop": "299,32,363,416", "rotation": -90, "width": 240}
SIDEWAYS = Layout((299, 32, 363, 416), -90, 240)
LABEL = Layout((136, 234, 488, 288), 0, 210)
OTHER_LABEL = Layout((232, 132, 648, 182), 0, 250)


def searched_at_right_angles(read_as, rules=RULES, **job):
    calibration_job = Calibration(5, 3, simplified=True, rank_candidates=True, **job)
    with patch.object(calibration, "layouts", return_value=list(read_as)), \
            patch.object(calibration, "quarter_turn_layouts", return_value=[]) as quarter:
        calibration_job.examine(Image.new("RGB", (800, 600), (40, 40, 40)), None, {"reference_required": False},
                                100, rules, lambda tried, profile: read_as[tried], lambda: False)
    return quarter.called


class LabelDigitsTests(unittest.TestCase):
    def test_label_digits_do_not_stop_the_search_for_a_meter_set_up_sideways(self):
        # Seen live: "?11?5.11?" on the label counted as a nearly complete counter row.
        self.assertTrue(searched_at_right_angles(
            {OTHER_LABEL: "??11?.1??", LABEL: "?11?5.11?", SIDEWAYS: "10517.???"}, SIDEWAYS_RULES))

    def test_an_unconfirmed_upright_row_does_not_stop_the_search_for_a_meter_set_up_sideways(self):
        self.assertTrue(searched_at_right_angles({LABEL: "10521.???", SIDEWAYS: "10517.???"}, SIDEWAYS_RULES))

    def test_label_digits_do_not_stop_the_search_for_a_new_setup(self):
        self.assertTrue(searched_at_right_angles({LABEL: "?11?5.11?"}))

    def test_most_whole_digits_of_an_upright_row_still_end_the_search(self):
        self.assertFalse(searched_at_right_angles({LABEL: "10493.3??"}))

    def test_a_reliably_read_upright_row_ends_the_search_also_for_a_meter_set_up_sideways(self):
        # The camera was turned back upright: both profiles agree on the full reading.
        self.assertFalse(searched_at_right_angles({LABEL: "10515.28?", SIDEWAYS: "10517.???"}, SIDEWAYS_RULES))


class WholeDigitsTests(unittest.TestCase):
    def test_only_the_whole_digits_count(self):
        self.assertTrue(whole_like(["1049?.???"], 5))
        self.assertTrue(whole_like(["10493.3??"], 5))
        self.assertFalse(whole_like(["?11?5.11?"], 5))
        self.assertFalse(whole_like(["??3??.???"], 5))

    def test_a_counter_without_decimals(self):
        self.assertTrue(whole_like(["1049?"], 5))
        self.assertFalse(whole_like(["?0?9?"], 5))


if __name__ == "__main__":
    unittest.main()
