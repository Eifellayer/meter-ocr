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


class PlainSetupTests(unittest.TestCase):
    """0.4.4: the routine comparison precision must not make the setup stricter."""

    def test_every_setup_of_a_three_decimal_meter_is_the_plain_setup(self):
        for decimals in (0, 1, 2, 3):
            for action in ("setup", "start", "repair"):
                with self.subTest(decimals=decimals, action=action):
                    self.assertTrue(run.plain_setup({"decimals": decimals, "fraction_digits": 3}, action))

    def test_last_digit_jobs_and_short_displays_keep_their_own_rules(self):
        self.assertFalse(run.plain_setup({"decimals": 3, "fraction_digits": 3}, "intensive"))
        self.assertFalse(run.plain_setup({"decimals": 3, "fraction_digits": 3}, "relocate_last"))
        self.assertFalse(run.plain_setup({"decimals": 1, "fraction_digits": 1}, "setup"))
        self.assertTrue(run.plain_setup({"decimals": 2, "fraction_digits": 2}, "setup"))

    def test_whole_cubic_metres_confirm_with_two_decimals(self):
        job = Calibration(5, 0, rank_candidates=True, simplified=True)
        self.assertEqual(2, job.precision({"decimals": 0, "fraction_digits": 3}, False))
        self.assertEqual(2, job.precision({"decimals": 0, "fraction_digits": 3}, True))


class DemoTests(unittest.TestCase):
    """0.5.0: an incomplete demo result must not be kept for the next request."""

    def test_only_a_complete_result_is_kept(self):
        import demo
        from unittest.mock import patch
        demo._complete.clear()
        with patch.object(demo, "read_register", return_value=None):
            self.assertIn("?", demo.run_demo(False)["reading"])
        self.assertEqual({}, demo._complete)
        digits = iter(demo.DEMO_READING.replace(".", "") * 2)
        with patch.object(demo, "read_register", side_effect=lambda *_, **__: next(digits)):
            self.assertEqual(demo.DEMO_READING, demo.run_demo(False)["reading"])
        with patch.object(demo, "read_register", side_effect=AssertionError):
            self.assertEqual(demo.DEMO_READING, demo.run_demo(False)["reading"])
        demo._complete.clear()


class NeededRollerTests(unittest.TestCase):
    """0.5.0: routine checks do not read rollers nobody compares."""

    def read(self, needed):
        from PIL import Image
        register = Image.new("RGB", (800, 100), "black")
        boxes = [(index * 100, 0, index * 100 + 90, 100) for index in range(8)]
        seen = []

        def recognize(picture, light, digits, **_):
            seen.append(picture.size)
            return "7"

        value = run.read_visible_digits(register, 500, boxes[:5], boxes[5:], False, "auto", profile=0,
                                        prefer_boxes=True, recognize=recognize, glyphs=False,
                                        needed_fraction=needed)
        return value, len(seen)

    def test_unneeded_decimal_rollers_stay_unread(self):
        everything, all_reads = self.read(None)
        self.assertEqual("77777.777", everything)
        one, one_reads = self.read(1)
        self.assertEqual("77777.7??", one)
        none, none_reads = self.read(0)
        self.assertEqual("77777.???", none)
        self.assertLess(one_reads, all_reads)
        self.assertLess(none_reads, one_reads)
        self.assertEqual(everything, self.read(3)[0])


if __name__ == "__main__":
    unittest.main()
