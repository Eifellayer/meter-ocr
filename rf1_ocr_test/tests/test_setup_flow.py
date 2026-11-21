from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from calibration import Layout
import setup_flow
from setup_store import SetupStore

RULES = {"integer_digits": 5, "fraction_digits": 3, "decimals": 0, "polarity": "auto", "meter_display": "rollers",
         "crop_mode": "auto", "crop": "", "crop_revision": "", "rotation": 0, "width": 0,
         "reflection_estimate_enabled": False}
SOURCE = {"mode": "camera", "camera": "camera.meter", "url": "", "reference": "", "selected": True}


class SetupFlowTests(unittest.TestCase):
    """Which search a request starts, tested without the worker."""

    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.store = SetupStore(folder / "good.json", folder / "candidates.json",
                                lambda path, content, mode: path.write_bytes(content))

    def job(self, action, rules=RULES, **options):
        simplified, intensive = setup_flow.job_kind(rules, action)
        return setup_flow.new_job(action, 4, None, (rules, (SOURCE, False)), {}, self.store, None, 0.0,
                                  simplified=simplified, intensive=intensive, **options)

    def test_setup_and_repair_are_plain_whatever_the_checks_compare(self):
        for decimals in (0, 1, 2, 3):
            self.assertEqual((True, False), setup_flow.job_kind(dict(RULES, decimals=decimals), "setup"))
        self.assertEqual((True, False), setup_flow.job_kind(RULES, "repair"))

    def test_the_last_digit_search_needs_three_compared_decimals(self):
        with self.assertRaises(ValueError):
            setup_flow.job_kind(RULES, "intensive")
        self.assertEqual((False, True), setup_flow.job_kind(dict(RULES, decimals=3), "intensive"))

    def test_a_new_setup_ignores_stored_candidates_and_a_restart_keeps_them(self):
        layout = Layout((100, 80, 500, 160), -3, 250)
        scope = self.store.candidate_scope((RULES, (SOURCE, False)), None, True, False)
        self.store.save_calibration_candidates(scope, {layout: (100, 30.0)})
        self.assertEqual({}, self.job("setup")[0].shortlist)
        self.assertEqual({layout: (100, 30.0)}, self.job("start")[0].shortlist)

    def test_the_remembered_frame_is_the_starting_point(self):
        layout = Layout((100, 80, 500, 160), -3, 250)
        self.store.remember_known_good_layout(RULES, SOURCE, layout)
        job, known_good = self.job("setup")
        self.assertEqual(layout, known_good)
        self.assertEqual(layout, job.known_good_layout)
        self.assertFalse(job.automatic)
        self.assertTrue(self.job("repair")[0].automatic)

    def test_the_last_digit_search_needs_a_saved_frame(self):
        with self.assertRaises(ValueError):
            self.job("intensive", dict(RULES, decimals=3))


if __name__ == "__main__":
    unittest.main()
