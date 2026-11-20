import unittest

from calibration import Calibration
from run import setup_end_log, setup_round_log


class SetupLogTest(unittest.TestCase):
    def test_discarded_images_are_counted_until_a_new_image_is_evaluated(self):
        job = Calibration(limit=10, started=0.0)
        self.assertEqual(setup_round_log(job, {"fetch_seconds": 1.0, "captured": True}, 0.0, 1.0), [])
        self.assertEqual(setup_round_log(job, {"fetch_seconds": 2.0, "captured": True}, 5.0, 7.0), [])
        self.assertEqual(setup_round_log(job, {"fetch_seconds": 0.5, "error": "TimeoutError"}, 10.0, 10.5), [])
        entries = setup_round_log(job, {"fetch_seconds": 1.5, "captured": True, "accepted_at": 20.0}, 18.5, 50.0)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["kind"], "setup_image")
        self.assertEqual(entry["requests"], 4)
        self.assertEqual(entry["discarded"], 2)
        self.assertEqual(entry["errors"], {"TimeoutError": 1})
        self.assertEqual(entry["fetch_s"], 5.0)
        self.assertEqual(entry["eval_s"], 30.0)
        self.assertEqual(job.image_stats, {})

    def test_end_entry_names_state_and_duration(self):
        job = Calibration(limit=10, started=0.0)
        job.state = "timeout"
        entry = setup_end_log(job, 1200.0)
        self.assertEqual(entry["state"], "timeout")
        self.assertEqual(entry["minutes"], 20.0)


if __name__ == "__main__":
    unittest.main()


class LearnableShiftTest(unittest.TestCase):
    def test_rescuing_frames_become_a_learning_candidate_in_thousandths(self):
        from run import learnable_shift
        boxes = [(10 + index * 50, 5, 50 + index * 50, 55) for index in range(8)]
        key, geometry, prefix = learnable_shift(True, ["k"], -1, boxes, (420, 60), 10482)
        self.assertEqual(["k"], key)
        self.assertEqual(-1, geometry[0])
        self.assertEqual([24, 83, 119, 917], geometry[1][0])
        self.assertTrue(all(isinstance(box, list) for box in geometry[1]))
        self.assertEqual(10482, prefix)

    def test_no_candidate_when_disabled_or_invalid(self):
        from run import learnable_shift
        boxes = [(10 + index * 50, 5, 50 + index * 50, 55) for index in range(8)]
        self.assertIsNone(learnable_shift(False, ["k"], 0, boxes, (420, 60), 1))
        self.assertIsNone(learnable_shift(True, ["k"], 0, boxes, (420, 60), None))
        self.assertIsNone(learnable_shift(True, ["k"], 0, list(reversed(boxes)), (420, 60), 1))


class WorthIntensiveTest(unittest.TestCase):
    def test_hopeless_candidates_are_skipped_once_one_reads_well(self):
        from calibration import worth_intensive
        items = [((0,), "meter", []), ((0,), "label90", []), ((0,), "serial", []), ((0,), "close", [])]
        shortlist = {"meter": (88, 1.0, 80), "label90": (0, 0.2, 80), "serial": (12, 0.4, 80), "close": (62, 0.8, 80)}
        kept = [item[1] for item in worth_intensive(items, shortlist, 88, 80)]
        # 0.4.0: below the threshold a frame is only a search aid once another frame reaches it.
        self.assertEqual(["meter"], kept)

    def test_everything_stays_without_a_good_candidate(self):
        from calibration import worth_intensive
        items = [((0,), "a", []), ((0,), "b", [])]
        shortlist = {"a": (50, 1.0, 80), "b": (0, 0.2, 80)}
        self.assertEqual(items, worth_intensive(items, shortlist, 50, 80))


class TrailingDecimalsTest(unittest.TestCase):
    def test_one_or_two_turning_rollers(self):
        from checks import unclear_trailing_decimals
        self.assertEqual(2, unclear_trailing_decimals("10482.8??", 3))
        self.assertEqual(2, unclear_trailing_decimals("10483.0??", 3))
        self.assertEqual(1, unclear_trailing_decimals("10482.81?", 3))
        self.assertEqual(1, unclear_trailing_decimals("10482.8?", 2))

    def test_no_coarser_check_without_a_safe_first_decimal(self):
        from checks import unclear_trailing_decimals
        self.assertEqual(0, unclear_trailing_decimals("10482.??", 2))
        self.assertEqual(0, unclear_trailing_decimals("10482.???", 3))
        self.assertEqual(0, unclear_trailing_decimals("?0482.8??", 3))
        self.assertEqual(0, unclear_trailing_decimals("10482.?1?", 3))
        self.assertEqual(0, unclear_trailing_decimals("10482.812", 3))
