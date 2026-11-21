"""0.4.3: digit frames keep the angle they were fitted at; plain setup also with two decimals."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import calibration  # noqa: E402
import run  # noqa: E402
from calibration import Calibration, Layout  # noqa: E402

BOXES = tuple((125 * index + 10, 300, 125 * index + 115, 700) for index in range(8))
RULES = {"decimals": 2, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000}


def frame(number):
    return Image.new("RGB", (100, 30), (0, 20, number))


class AngleTests(unittest.TestCase):
    def sweep(self, layout):
        job = Calibration(5, 0, rank_candidates=True)
        sample = {"reference_required": False}
        return job.sweep_angles(layout, ["12345.67?", "12345.67?"], sample, RULES,
                                lambda *_: "12345.67?", lambda: False, None, set(), 100)

    def test_fitted_frames_stay_at_their_angle_when_others_read_the_same(self):
        layout = Layout((0, 0, 400, 80), -12, 250, BOXES, method="register_window")
        self.assertEqual(-12, self.sweep(layout)[0].rotation)

    def test_plain_crop_still_prefers_the_smaller_turn(self):
        layout = Layout((0, 0, 400, 80), -12, 250)
        self.assertEqual(-9, self.sweep(layout)[0].rotation)


class TwoDecimalSetupTests(unittest.TestCase):
    def test_complete_two_decimal_row_of_the_meter_window_skips_other_candidates(self):
        window = Layout((0, 0, 95, 20), -12, 60, BOXES, method="register_window")
        label = Layout((0, 12, 60, 29), 0, 40)
        reads = []

        def read(layout, _profile):
            reads.append(layout)
            return "12345.67?" if layout == window else "?????.???"

        job = Calibration(5, 0, rank_candidates=True)   # not "simplified": two decimals are compared
        with patch.object(calibration, "layouts", return_value=[window, label]), \
                patch.object(calibration, "quarter_turn_layouts", return_value=[]):
            job.examine(frame(1), None, {"reference_required": False}, 101, RULES, read, lambda: False,
                        angle_read=read)
        self.assertNotIn(label, reads)
        self.assertEqual({-12}, {layout.rotation for layout in reads})
        self.assertEqual(1, job.confirmations)


class SetupLogTests(unittest.TestCase):
    def test_setup_image_entry_lists_what_each_frame_read(self):
        job = Calibration(5, 0, simplified=True)
        job.seen.add("a")
        log = {"fetch_seconds": 1.0, "accepted_at": 10.0, "error": None, "captured": True,
               "reads": ["register_window 1,2,3,4 -12° P0 12345.67?"]}
        entry = run.setup_round_log(job, log, 5.0, 20.0)[0]
        self.assertEqual(log["reads"], entry["reads"])
        self.assertTrue(entry["simplified"])
        self.assertEqual(0, entry["partial_hits"])


if __name__ == "__main__":
    unittest.main()
