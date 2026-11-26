"""0.5.50: a turning last roller is not re-read, moved or reported as a misplaced frame."""

import unittest

from checks import meter_running, turning_tail_unclear


class TurningRollerTests(unittest.TestCase):
    def test_only_trailing_compared_decimals_count(self):
        self.assertEqual(1, turning_tail_unclear("10563.8??", 2))
        self.assertEqual(2, turning_tail_unclear("10563.???", 2))
        self.assertEqual(1, turning_tail_unclear("10563.83?", 3))
        self.assertEqual(0, turning_tail_unclear("10563.832", 2))
        self.assertEqual(0, turning_tail_unclear("1056?.8??", 2))
        self.assertEqual(0, turning_tail_unclear("10563.?3?", 2))
        self.assertEqual(0, turning_tail_unclear("10563", 0))

    def test_running_when_the_readable_part_is_above_the_last_confirmed_reading(self):
        anchor = {"time": 1000.0, "value": 10563830}
        self.assertTrue(meter_running("10563.9??", 2, 5, anchor, None, 1600.0))
        self.assertFalse(meter_running("10563.8??", 2, 5, anchor, None, 1600.0))
        self.assertTrue(meter_running("10564.???", 2, 5, anchor, None, 1600.0))

    def test_running_when_the_last_accepted_readings_differ_and_are_recent(self):
        anchor = {"time": 1000.0, "value": 10563830}
        counter = {"reading_litres": 10563830, "anchor_litres": 10563750, "anchor_time": 400.0}
        self.assertTrue(meter_running("10563.8??", 2, 5, anchor, counter, 1600.0))
        # Standstill: nothing was used between the last two readings, or it is long ago.
        still = {"reading_litres": 10563830, "anchor_litres": 10563830, "anchor_time": 400.0}
        self.assertFalse(meter_running("10563.8??", 2, 5, anchor, still, 1600.0))
        self.assertFalse(meter_running("10563.8??", 2, 5, anchor, counter, 400.0 + 2 * 3600))
        self.assertFalse(meter_running("10563.8??", 2, 5, None, None, None))


if __name__ == "__main__":
    unittest.main()
