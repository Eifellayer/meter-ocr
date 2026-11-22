import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (anchored_hidden_digits, hidden_fill_reachable, hidden_roller_flow,  # noqa: E402
                    hidden_roller_interval, hidden_roller_span, hidden_fill_with_turning_roller,
                    estimated_hidden_digits)


class HiddenRollerTests(unittest.TestCase):
    """0.5.10, seen live on 22.11.2026: a streak of light hid the first decimal for good."""

    def test_flow_bound_is_the_floor_until_something_was_learned(self):
        self.assertEqual(1500, hidden_roller_flow({}, 6000))
        self.assertEqual(1000, hidden_roller_flow({}, 1000))
        history = {"flow_peaks": {"1": 1200}, "flow_peak_samples": 20}
        self.assertEqual(2400, hidden_roller_flow(history, 6000))

    def test_span_of_the_hidden_roller(self):
        self.assertEqual(100, hidden_roller_span([5], 5, 2))    # first decimal
        self.assertEqual(1000, hidden_roller_span([4], 5, 2))   # whole cubic metres
        self.assertIsNone(hidden_roller_span([6], 5, 2))        # last compared roller
        self.assertIsNone(hidden_roller_span([], 5, 2))

    def test_interval_is_capped_so_one_value_stays_reachable(self):
        self.assertEqual(2, hidden_roller_interval(10, [5], 5, 2, 1500))
        self.assertEqual(10, hidden_roller_interval(10, [4], 5, 2, 1500))
        self.assertEqual(10, hidden_roller_interval(10, [6], 5, 2, 1500))
        self.assertEqual(1, hidden_roller_interval(1, [5], 5, 2, 1500))

    def test_fill_two_minutes_after_the_anchor(self):
        anchor = {"time": 1000.0, "value": 10511550}
        rows = ["10511.?6", "10511.?6", "40541.?6"]
        self.assertTrue(hidden_fill_reachable(anchor, 1150.0, [5], 5, 2, 1500))
        filled = anchored_hidden_digits(rows, anchor, 1150.0, 2, 5, 1500, [5])
        self.assertEqual((["10511.56"] * 3, [5]), filled)

    def test_rollover_of_the_second_decimal_raises_the_hidden_digit(self):
        anchor = {"time": 1000.0, "value": 10511590}
        filled = anchored_hidden_digits(["10511.?0", "10511.?0"], anchor, 1150.0, 2, 5, 1500, [5])
        self.assertEqual((["10511.60"] * 2, [5]), filled)

    def test_old_anchor_asks_for_the_reading_again(self):
        anchor = {"time": 1000.0, "value": 10511550}
        self.assertFalse(hidden_fill_reachable(anchor, 1000.0 + 15 * 60, [5], 5, 2, 1500))
        self.assertFalse(hidden_fill_reachable(None, 2000.0, [5], 5, 2, 1500))
        self.assertIsNone(anchored_hidden_digits(["10511.?6", "10511.?6"], anchor, 1000.0 + 15 * 60, 2, 5, 1500, [5]))


class TurningLastRollerTests(unittest.TestCase):
    """0.5.11, live 22.11.2026 13:28: reading entered as 10511,534, the check read "10511.?3?"."""

    anchor = {"time": 1000.0, "value": 10511534}

    def test_hidden_digit_is_filled_and_the_turning_roller_stays_open(self):
        rows = ["10511.?3?"] * 5
        self.assertIsNone(anchored_hidden_digits(rows, self.anchor, 1037.0, 3, 5, 1500, [5]))
        self.assertEqual("10511.53?", hidden_fill_with_turning_roller(rows, self.anchor, 1037.0, 3, 5, 1500, [5]))

    def test_no_fill_when_the_anchor_is_too_old(self):
        rows = ["10511.?3?"] * 5
        self.assertIsNone(hidden_fill_with_turning_roller(rows, self.anchor, 1000.0 + 3600, 3, 5, 1500, [5]))

    def test_no_fill_without_anchor_or_hidden_slot(self):
        rows = ["10511.?3?"] * 5
        self.assertIsNone(hidden_fill_with_turning_roller(rows, None, 1037.0, 3, 5, 1500, [5]))
        self.assertIsNone(hidden_fill_with_turning_roller(rows, self.anchor, 1037.0, 3, 5, 1500, []))

    def test_other_unreadable_digit_is_not_filled(self):
        rows = ["1051?.?3?"] * 5
        self.assertIsNone(hidden_fill_with_turning_roller(rows, self.anchor, 1037.0, 3, 5, 1500, [5]))


class EstimatedHiddenDecimalTests(unittest.TestCase):
    """0.5.12 (Stefan 22.11.2026, 13:46): estimate a hidden decimal instead of failing for good."""

    def test_lowest_digit_not_below_the_last_reading(self):
        self.assertEqual(("10511.53", [5]), estimated_hidden_digits(["10511.?3"] * 3, 10511500, 2, 5, [5]))
        self.assertEqual(("10511.63", [5]), estimated_hidden_digits(["10511.?3"] * 3, 10511540, 2, 5, [5]))

    def test_turning_last_roller_stays_open(self):
        self.assertEqual(("10511.53?", [5]), estimated_hidden_digits(["10511.?3?"] * 5, 10511100, 3, 5, [5])[0:2]
                         if False else estimated_hidden_digits(["10511.?3?"] * 5, 10511500, 3, 5, [5]))

    def test_without_known_reading_the_lowest_digit_is_taken(self):
        self.assertEqual(("10511.03", [5]), estimated_hidden_digits(["10511.?3"] * 3, None, 2, 5, [5]))

    def test_full_cubic_metres_are_never_estimated(self):
        self.assertIsNone(estimated_hidden_digits(["1051?.23"] * 3, 10510000, 2, 5, [4]))
        self.assertIsNone(estimated_hidden_digits(["1051?.?3"] * 3, 10510000, 2, 5, [5]))

    def test_no_value_at_or_above_the_last_reading(self):
        self.assertIsNone(estimated_hidden_digits(["10511.?3"] * 3, 10511950, 2, 5, [5]))


class EntryDuringRunningCheckTests(unittest.TestCase):
    """0.5.13 (Stefan 22.11.2026, 14:18): a check that was running during the entry asked again."""

    def test_entry_made_while_the_check_was_running(self):
        from run import reading_entered_meanwhile
        before = {"fallback_value": "", "fallback_time": ""}
        after = {"fallback_value": "10511,990", "fallback_time": "2026-11-22T14:16"}
        self.assertTrue(reading_entered_meanwhile(before, after))
        self.assertFalse(reading_entered_meanwhile(after, after))
        self.assertFalse(reading_entered_meanwhile(after, before))
