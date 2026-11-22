import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (anchored_hidden_digits, hidden_fill_reachable, hidden_roller_flow,  # noqa: E402
                    hidden_roller_interval, hidden_roller_span)


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
