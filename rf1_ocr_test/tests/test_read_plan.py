import unittest

import read_plan

RULES = {"integer_digits": 5, "crop_mode": "manual", "digit_boxes": [[0, 0, 1, 1]] * 8, "crop_revision": "r1"}
COUNTER = {"reading_litres": 10501820}


class ReadPlanTests(unittest.TestCase):
    """When the leading digits are taken over and when everything is read again."""

    def confirmed(self, now=1000.0, reading="10501.82"):
        return read_plan.after_check({}, RULES, "ocr_only", "", reading, now)

    def test_the_first_check_reads_everything(self):
        self.assertEqual("", read_plan.assumed_prefix({}, RULES, COUNTER, 1000.0))

    def test_after_a_complete_confirmed_read_the_leading_digits_are_taken_over(self):
        self.assertEqual("105", read_plan.assumed_prefix(self.confirmed(), RULES, COUNTER, 1100.0))

    def test_every_tenth_check_and_every_hour_reads_everything(self):
        state = self.confirmed()
        for _ in range(read_plan.FULL_READ_EVERY - 1):
            self.assertEqual("105", read_plan.assumed_prefix(state, RULES, COUNTER, 1100.0))
            state = read_plan.after_check(state, RULES, "ocr_only", "105", "10501.90", 1100.0)
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, COUNTER, 1100.0))
        state = read_plan.after_check(state, RULES, "match", "", "10501.95", 1200.0)
        self.assertEqual("105", read_plan.assumed_prefix(state, RULES, COUNTER, 1300.0))
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, COUNTER, 1200.0 + read_plan.FULL_READ_SECONDS))

    def test_a_failed_check_needs_three_complete_reads(self):
        state = read_plan.after_check(self.confirmed(), RULES, "ocr_unclear", "105", "105?1.8?", 1100.0)
        for stamp in (1200.0, 1300.0):
            self.assertEqual("", read_plan.assumed_prefix(state, RULES, COUNTER, stamp))
            state = read_plan.after_check(state, RULES, "ocr_only", "", "10501.90", stamp)
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, COUNTER, 1400.0))
        state = read_plan.after_check(state, RULES, "ocr_only", "", "10501.90", 1400.0)
        self.assertEqual("105", read_plan.assumed_prefix(state, RULES, COUNTER, 1500.0))

    def test_near_a_roll_over_of_the_fourth_digit_everything_is_read(self):
        state = self.confirmed()
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, {"reading_litres": 10591000}, 1100.0))
        self.assertEqual("105", read_plan.assumed_prefix(state, RULES, {"reading_litres": 10581000}, 1100.0))
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, {"reading_litres": 10611000}, 1100.0))

    def test_changed_frames_missing_frames_and_short_meters_read_everything(self):
        state = self.confirmed()
        self.assertEqual("", read_plan.assumed_prefix(state, dict(RULES, crop_revision="r2"), COUNTER, 1100.0))
        self.assertEqual("", read_plan.assumed_prefix(state, dict(RULES, crop_mode="auto"), COUNTER, 1100.0))
        self.assertEqual("", read_plan.assumed_prefix(state, dict(RULES, digit_boxes=[]), COUNTER, 1100.0))
        self.assertEqual("", read_plan.assumed_prefix(state, dict(RULES, integer_digits=4), COUNTER, 1100.0))
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, None, 1100.0))

    def test_an_incomplete_full_read_confirms_nothing(self):
        state = read_plan.after_check({}, RULES, "ocr_only", "", "1?501.82", 1000.0)
        self.assertEqual("", read_plan.assumed_prefix(state, RULES, COUNTER, 1100.0))


if __name__ == "__main__":
    unittest.main()
