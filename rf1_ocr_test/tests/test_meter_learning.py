"""Exercise bounded learning, rollback and provisional digits."""

from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import provisional_digit_estimate
from layout import digit_box_settings, scale_digit_boxes
from meter_learning import alignment_rollback, observe_alignment, observe_flow, observe_geometry_failures, suggested_interval


class MeterLearningTests(TestCase):
    def test_inferred_digits_can_cross_rollover_but_do_not_guess_an_ambiguous_value(self):
        pattern = "0?.?0"
        self.assertEqual("10.00", provisional_digit_estimate(
            "1?.?0", ["1?.?0"] * 3, 1010, {"time": 1000, "value": 9990}, 2, 2, 6000,
        )["reading"])
        self.assertIsNone(provisional_digit_estimate(
            pattern, [pattern] * 3, 1400, {"time": 1000, "value": 1000}, 2, 2, 6000,
        ))
        self.assertIsNone(provisional_digit_estimate(
            "??.00", ["??.00"] * 3, 1010, {"time": 1000, "value": 1000}, 2, 2, 6000,
        ))

    def test_manual_frame_edits_are_independent_and_order_checked(self):
        boxes = [[0, 500, 350, 1000], [400, 0, 1000, 1000]]
        self.assertEqual(boxes, digit_box_settings(boxes, 2))
        self.assertEqual([(0, 30, 70, 60), (80, 0, 200, 60)], scale_digit_boxes(boxes, (200, 60)))
        with self.assertRaises(ValueError):
            digit_box_settings(list(reversed(boxes)), 2)

    def test_background_candidate_needs_improvements_multiple_states_and_can_roll_back(self):
        state, key = {}, ["source"]
        old, candidate = [[0, 0, 1000, 1000]], [[0, 100, 1000, 950]]
        for stamp in range(1, 7):
            value = str(stamp % 2)
            plan = observe_alignment(state, key, stamp, value, "?", old, candidate, value)
            if stamp < 6:
                self.assertIsNone(plan)
        self.assertEqual(candidate, plan)
        self.assertIsNone(alignment_rollback(state, key, candidate, True))
        self.assertEqual(old, alignment_rollback(state, key, candidate, True))

    def test_adaptive_check_returns_to_configured_interval_after_consumption_stops(self):
        state = {}
        source = ["slfork", "http://meter", ""]
        observe_flow(state, source, 100, "123.890", 3, 3, 11, 6000)
        observe_flow(state, source, 400, "123.999", 3, 3, 11, 6000)
        self.assertEqual(5, suggested_interval(60, state, source, 11))
        observe_flow(state, source, 700, "123.999", 3, 3, 12, 6000)
        self.assertEqual({"11", "12"}, set(state["months"]))
        self.assertEqual(60, suggested_interval(60, state, ["different camera"], 11))


    def test_geometry_retry_starts_once_after_ten_distinct_failed_measurements(self):
        state, key = {}, ["camera", "zone"]
        for stamp in range(1, 10):
            self.assertFalse(observe_geometry_failures(state, key, stamp, "ocr_unclear", reading_problem=True))
            self.assertFalse(observe_geometry_failures(state, key, stamp, "ocr_unclear", reading_problem=True))
        self.assertEqual(9, state["failures"])
        self.assertTrue(observe_geometry_failures(state, key, 10, "difference", reading_problem=True))
        self.assertFalse(observe_geometry_failures(state, key, 11, "ocr_unclear", reading_problem=True))
        self.assertFalse(observe_geometry_failures(state, key, 12, "match", reading_problem=False))
        self.assertEqual(0, state["failures"])
        self.assertNotIn("scheduled_at", state)
