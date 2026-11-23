"""0.5.41: shadow mode – would frames with more filled digit fields first find the counter sooner?"""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calibration  # noqa: E402
from calibration import Calibration, Layout, presort_ranks  # noqa: E402
import run  # noqa: E402
import shadow_log  # noqa: E402

RULES = {"decimals": 3, "fraction_digits": 3, "integer_digits": 5, "max_flow_lph": 6000, "learned_flow_lph": None}
LABEL = Layout((20, 205, 290, 275), 0, 150, method="neighbours")
METER = Layout((300, 200, 700, 280), 0, 250, method="register_window")


class RankTests(unittest.TestCase):
    def test_ranks(self):
        seen = [(LABEL, 2), (Layout((0, 0, 10, 10), 0, 5), None), (METER, 8)]
        self.assertEqual((3, 1), presort_ranks(seen, METER))
        self.assertEqual((1, 2), presort_ranks(seen, LABEL))
        self.assertIsNone(presort_ranks(seen, Layout((1, 1, 2, 2), 0, 1)))

    def test_ties_keep_the_tested_order(self):
        self.assertEqual((2, 2), presort_ranks([(LABEL, 5), (METER, 5)], METER))


class SetupTests(unittest.TestCase):
    def test_the_setup_notes_the_tested_frames_only_in_shadow_mode(self):
        def read(layout, profile):
            return "10517.835" if layout is METER or layout == METER else "?2???.???"

        for shadow in (True, False):
            job = Calibration(5, 3, simplified=True, rank_candidates=True)
            job.presort_shadow = shadow
            with patch.object(calibration, "layouts", return_value=[LABEL, METER]), \
                    patch.object(calibration, "quarter_turn_layouts", return_value=[]):
                job.examine(Image.new("RGB", (800, 600), (40, 40, 40)), None, {"reference_required": False},
                            1000, RULES, read, lambda: False, None)
            self.assertEqual([LABEL, METER] if shadow else [], [layout for layout, _ in job.presort_seen])

    def test_the_result_goes_to_the_shadow_log(self):
        job = Calibration(5, 3)
        job.candidate, job.presort_seen = METER, [(LABEL, 1), (METER, 8)]
        with TemporaryDirectory() as folder, patch.object(shadow_log, "SHADOW_LOG", Path(folder) / "log.jsonl"):
            run.log_presort(job, "t1")
            entry = json.loads(shadow_log.read_text())
        self.assertEqual(("presort", 1, 2, True), (entry["function"], entry["shadow"]["rank"],
                                                   entry["established"]["rank"], entry["agree"]))

    def test_one_frame_is_no_choice(self):
        job = Calibration(5, 3)
        job.candidate, job.presort_seen = METER, [(METER, 8)]
        with TemporaryDirectory() as folder, patch.object(shadow_log, "SHADOW_LOG", Path(folder) / "log.jsonl"):
            run.log_presort(job, "t1")
            self.assertEqual("", shadow_log.read_text())


if __name__ == "__main__":
    unittest.main()
