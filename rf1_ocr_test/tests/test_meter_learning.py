"""Exercise bounded learning, rollback and provisional digits."""

from pathlib import Path
import sys
from unittest import TestCase

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import OCR_PROFILES, lighting_ocr_profiles, provisional_digit_estimate
from layout import digit_box_settings, scale_digit_boxes
from meter_learning import local_geometry_trials, note_local_improvement, note_local_issue, alignment_rollback, observe_alignment, observe_flow, observe_geometry_failures, plan_reflection_recheck, suggested_interval


class MeterLearningTests(TestCase):
    def test_background_local_trials_need_repeated_positions_on_fresh_frames(self):
        state = {}
        key = ["camera", "geometry"]
        self.assertFalse(note_local_issue(state, key, 10, [0]))
        self.assertFalse(note_local_issue(state, key, 20, [0]))
        self.assertFalse(note_local_issue(state, key, 20, [0]))
        self.assertTrue(note_local_issue(state, key, 30, [0]))
        self.assertFalse(note_local_issue(state, key, 40, []))
        boxes = [[20, 10, 280, 940], [300, 10, 590, 940], [620, 10, 970, 940]]
        trials = list(local_geometry_trials(boxes, [0]))
        self.assertEqual([0, 0, 0, 0, -1, 1, -2, 2], [angle for angle, _ in trials])
        self.assertTrue(all(candidate[1:] == boxes[1:] for _, candidate in trials))
        self.assertTrue(all(candidate[0][2] - candidate[0][0] == 260 for _, candidate in trials))

        state = {}
        for stamp, reading in ((10, 123), (20, 123), (30, 123)):
            self.assertFalse(note_local_improvement(state, key, stamp, [1, boxes], reading))
        self.assertTrue(note_local_improvement(state, key, 40, [1, boxes], 124))

    def test_shadow_profile_is_prioritized_for_dim_or_uneven_images(self):
        dim = Image.new("L", (180, 40), 45)
        self.assertEqual(OCR_PROFILES[2], lighting_ocr_profiles(dim)[1])
        balanced = Image.new("L", (180, 40), 180)
        for row in range(0, 40, 4):
            balanced.paste(20, (0, row, 180, row + 2))
        self.assertEqual(OCR_PROFILES, lighting_ocr_profiles(balanced))
        uneven = balanced.copy()
        uneven.paste(35, (0, 0, 90, 40))
        self.assertEqual(OCR_PROFILES[2], lighting_ocr_profiles(uneven)[1])

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


    def test_geometry_retry_needs_distinct_failures_over_forty_minutes(self):
        state, key = {}, [["camera"], "zone"]
        for stamp in (100, 400, 700, 2499):
            self.assertFalse(observe_geometry_failures(state, key, stamp, "ocr_unclear", reading_problem=True))
            self.assertFalse(observe_geometry_failures(state, key, stamp, "ocr_unclear", reading_problem=True))
        self.assertTrue(observe_geometry_failures(state, key, 2500, "difference", reading_problem=True))
        # One repair per two hours while the readings keep failing.
        self.assertFalse(observe_geometry_failures(state, key, 9000, "difference", reading_problem=True))
        self.assertTrue(observe_geometry_failures(state, key, 9700, "difference", reading_problem=True))

    def test_a_plausible_reading_restarts_the_forty_minute_window(self):
        state, key = {}, [["camera"], "zone"]
        for stamp in (100, 400, 700):
            self.assertFalse(observe_geometry_failures(state, key, stamp, "ocr_unclear", reading_problem=True))
        self.assertFalse(observe_geometry_failures(state, key, 760, "ocr_only", reading_problem=False))
        self.assertNotIn("first_failure_at", state)
        for stamp in (1000, 1300, 2500, 3399):
            self.assertFalse(observe_geometry_failures(state, key, stamp, "difference", reading_problem=True))
        self.assertTrue(observe_geometry_failures(state, key, 3400, "difference", reading_problem=True))

    def test_single_roll_failures_cannot_trigger_geometry_repair(self):
        state, key = {}, [["camera"], "zone"]
        for stamp in range(300, 3600, 300):
            self.assertFalse(observe_geometry_failures(state, key, stamp, "ocr_unclear", reading_problem=False))
        self.assertEqual(0, state["failures"])


class ReflectionScheduleTests(TestCase):
    def test_forecast_uses_visible_suffix_and_recent_flow(self):
        history = {"consumption_statistics": {"source": "meter", "samples": [[1200, 10, 1], [1800, 70, 1]]}}
        self.assertEqual(72, plan_reflection_recheck(history, "meter", "10465.9?", "10465.9?2", 1801, 5, 3, 300))
        self.assertEqual(20, plan_reflection_recheck(history, "meter", "10465.9?", "10465.9?9", 1802, 5, 3, 300))
        self.assertIsNone(plan_reflection_recheck(history, "meter", "1046?.94", "1046?.942", 1803, 5, 3, 300))

    def test_waits_for_the_second_half_and_limits_fast_checks_without_a_flow_history(self):
        history = {}
        self.assertIsNone(plan_reflection_recheck(history, "meter", "10465.9?", "10465.9?4", 1800, 5, 3, 300))
        for stamp in (1801, 1831, 1861):
            self.assertEqual(30, plan_reflection_recheck(history, "meter", "10465.9?", "10465.9?7", stamp, 5, 3, 300))
        self.assertIsNone(plan_reflection_recheck(history, "meter", "10465.9?", "10465.9?8", 1891, 5, 3, 300))
        self.assertEqual(30, plan_reflection_recheck(history, "meter", "10465.94?", "10465.94?", 1921, 5, 3, 300))

    def test_stationary_confirmed_meter_and_earlier_regular_check_do_not_trigger_fast_polling(self):
        history = {"consumption_statistics": {"source": "meter", "samples": [[1200, 10, 1], [1800, 10, 1]]}}
        self.assertIsNone(plan_reflection_recheck(history, "meter", "10465.9?", "10465.9?9", 1801, 5, 3, 300))
        self.assertIsNone(plan_reflection_recheck(history, "other", "10465.9?", "10465.9?9", 1802, 5, 3, 15))
        self.assertNotIn("reflection_rechecks", history)
