"""0.5.49: a jump of an unreferenced reading must fit the flow the meter really reaches."""

import unittest

from checks import jump_flow_limit, jump_within_flow


class JumpFlowTests(unittest.TestCase):
    def history(self, peaks, samples=50):
        return {"flow_peaks": {str(20780 + index): value for index, value in enumerate(peaks)},
                "flow_peak_samples": samples}

    def test_limit_is_twice_the_usual_daily_peak_and_ignores_single_outliers(self):
        self.assertEqual(1800, jump_flow_limit(self.history([800, 900, 850, 900, 950, 700, 900]), 6000))
        # Peaks learned from earlier misreads (3.8 m³/h) on two days do not open the limit.
        self.assertEqual(1800, jump_flow_limit(self.history([800, 3800, 850, 900, 3800, 700, 900]), 6000))
        self.assertEqual(1500, jump_flow_limit(self.history([200, 300, 250]), 6000))
        self.assertEqual(1200, jump_flow_limit(self.history([800, 900, 850]), 1200))

    def test_configured_limit_until_enough_readings_were_seen(self):
        self.assertEqual(6000, jump_flow_limit({}, 6000))
        self.assertEqual(6000, jump_flow_limit(self.history([800], samples=3), 6000))

    def test_misread_first_decimal_is_not_reachable_but_real_consumption_is(self):
        anchor = {"time": 1000.0, "value": 10534030}
        later = 1000.0 + 11 * 60
        self.assertFalse(jump_within_flow("10534.74", anchor, later, 2, 5, 1800))
        self.assertTrue(jump_within_flow("10534.20", anchor, later, 2, 5, 1800))
        self.assertTrue(jump_within_flow("10534.35", anchor, later, 2, 5, 1800))
        # After a long pause the same value is reachable again: nothing stays blocked.
        self.assertTrue(jump_within_flow("10534.74", anchor, 1000.0 + 30 * 60, 2, 5, 1800))

    def test_nothing_to_compare_with_never_blocks(self):
        self.assertTrue(jump_within_flow("10534.74", None, 2000.0, 2, 5, 1800))
        self.assertTrue(jump_within_flow("10534.74", {"time": 3000.0, "value": 1}, 2000.0, 2, 5, 1800))
        self.assertTrue(jump_within_flow("1053?.74", {"time": 1000.0, "value": 1}, 2000.0, 2, 5, 1800))


if __name__ == "__main__":
    unittest.main()
