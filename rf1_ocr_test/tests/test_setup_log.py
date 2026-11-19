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
