import json
import unittest

import background_view


def lines(*entries):
    return "\n".join(json.dumps(entry) for entry in entries) + "\nkaputt{\n"


class SummaryTests(unittest.TestCase):
    def test_experiments_are_compared_with_the_stable_reading(self):
        result = background_view.summary(lines(
            {"kind": "automatic", "time": "t1", "experiment": {
                "stable": "10490.67", "seven_segment": {"reading": "1049067", "seconds": 0.02},
                "perspective": {"reading": "1049?67", "seconds": 2.0}}},
            {"kind": "automatic", "time": "t2", "experiment": {
                "stable": "10490.67", "seven_segment": {"reading": "1049167", "seconds": 0.04},
                "perspective": {"measured": None, "reading": None, "seconds": 0.1}}},
            {"kind": "automatic", "time": "t3", "experiment": {"skipped": "busy", "load": 1.2}},
            {"kind": "automatic", "time": "t4", "experiment": {"stable": "1", "perspective": {"error": "OSError"}}},
            {"kind": "manual", "experiment": {"stable": "1", "seven_segment": {"reading": "1"}}},
        ))
        self.assertEqual((4, 1, "t4"), (result["checks"], result["skipped_busy"], result["last"]))
        segment, perspective = result["experiments"]["seven_segment"], result["experiments"]["perspective"]
        self.assertEqual((2, 1, 1, 0.03), tuple(segment[key] for key in ("runs", "same", "different", "seconds")))
        self.assertEqual((3, 1, 1, 1), tuple(perspective[key] for key in ("runs", "unclear", "no_result", "errors")))

    def test_work_in_the_waiting_time_is_counted_separately(self):
        result = background_view.summary(lines(
            {"kind": "idle", "time": "t1", "reason": "unclear_check",
             "reread": [{"position": 5, "digit": "7"}, {"position": 7, "digit": "?"}]},
            {"kind": "idle", "time": "t2", "reason": "experiment",
             "experiment": {"stable": "12", "seven_segment": {"reading": "12", "seconds": 0.01}}},
        ))
        self.assertEqual({"runs": 2, "experiments": 1, "reread": 2, "resolved": 1, "last": "t2"}, result["idle"])
        self.assertEqual(1, result["experiments"]["seven_segment"]["same"])

    def test_empty_log_gives_zeroes(self):
        result = background_view.summary("")
        self.assertEqual(0, result["checks"])
        self.assertIsNone(result["experiments"]["perspective"]["seconds"])


if __name__ == "__main__":
    unittest.main()
