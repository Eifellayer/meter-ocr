"""0.5.19: reflection frames checked against the entered reading, shadow estimate of unclear decimals."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration import Calibration, visible_fits_reading  # noqa: E402
from checks import shadow_decimal_estimate  # noqa: E402

PANEL = (Path(__file__).resolve().parents[1] / "panel.py").read_text(encoding="utf-8")
T0 = 1_800_000_000


class ReflectionPlausibilityTests(unittest.TestCase):
    known = {"value": 10512_534, "time": T0}

    def test_misread_whole_digit_is_rejected(self):
        # Setup read "10515,?2?" while the reading entered was 10512,534.
        self.assertFalse(visible_fits_reading("10515?2?", 5, self.known, 6000, T0 + 60))

    def test_fitting_digits_pass(self):
        self.assertTrue(visible_fits_reading("10512?3?", 5, self.known, 6000, T0 + 60))
        # One cubic metre either side is tolerated (picture just before the entry, rollover).
        self.assertTrue(visible_fits_reading("10511?9?", 5, self.known, 6000, T0))
        self.assertTrue(visible_fits_reading("10513?0?", 5, self.known, 0, T0))

    def test_hidden_whole_digit_still_checked(self):
        self.assertTrue(visible_fits_reading("105?2?3?", 5, self.known, 6000, T0))
        self.assertFalse(visible_fits_reading("106?2?3?", 5, self.known, 6000, T0))

    def test_flow_widens_the_range(self):
        later = T0 + 3 * 3600
        self.assertFalse(visible_fits_reading("10530?0?", 5, self.known, 1000, later))
        self.assertTrue(visible_fits_reading("10515?0?", 5, self.known, 1000, later))

    def test_without_known_reading_nothing_is_checked(self):
        self.assertTrue(visible_fits_reading("10515?2?", 5, None, 6000, T0))
        self.assertTrue(visible_fits_reading("?????", 5, self.known, 6000, T0))

    def test_calibration_uses_known_reading(self):
        job = Calibration(limit=10, started=0.0)
        self.assertTrue(job.visible_fits_known_reading("10515?2?", 5, T0))
        job.known_reading, job.known_flow = dict(self.known), 6000
        self.assertFalse(job.visible_fits_known_reading("10515?2?", 5, T0 + 60))
        job.auto_glare = {"layout": None, "positions": (5,), "visible": "10515?2?", "count": 1}
        job.drop_glare()
        self.assertIsNone(job.auto_glare)

    def test_panel_explains_a_mismatch(self):
        self.assertIn("glare_mismatch", PANEL)
        self.assertIn("passen nicht zum eingetragenen Zählerstand", PANEL)
        self.assertIn("do not fit the meter reading you entered", PANEL)


class ShadowDecimalEstimateTests(unittest.TestCase):
    anchor = {"value": 10512_530, "time": T0}

    def test_single_reachable_completion(self):
        result = shadow_decimal_estimate(["10512.?4", "10512.?4"], self.anchor, T0 + 600, 2, 5, 300)
        self.assertEqual({"pattern": "10512.?4", "reachable": 1, "lowest": "10512.54", "highest": "10512.54"},
                         result)

    def test_range_of_completions(self):
        result = shadow_decimal_estimate(["10512.??", "10512.??"], self.anchor, T0 + 3600, 2, 5, 300)
        self.assertEqual("10512.52", result["lowest"])
        self.assertGreater(result["reachable"], 1)

    def test_whole_cubic_metres_are_never_estimated(self):
        self.assertIsNone(shadow_decimal_estimate(["1051?.54", "1051?.54"], self.anchor, T0 + 600, 2, 5, 300))

    def test_no_anchor_or_nothing_unclear(self):
        self.assertIsNone(shadow_decimal_estimate(["10512.?4"], None, T0, 2, 5, 300))
        self.assertIsNone(shadow_decimal_estimate(["10512.54", "10512.54"], self.anchor, T0 + 600, 2, 5, 300))


if __name__ == "__main__":
    unittest.main()
