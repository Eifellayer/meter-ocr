"""0.5.36: an own log for procedures in shadow mode, apart from the debug log."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import background_view  # noqa: E402
import panel  # noqa: E402
import run  # noqa: E402
import shadow_log  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")


class ShadowLogTests(unittest.TestCase):
    def test_entries_and_summary(self):
        with TemporaryDirectory() as folder, patch.object(shadow_log, "SHADOW_LOG", Path(folder) / "log.jsonl"):
            shadow_log.record("standstill", image="t1", shadow={"stationary": True}, established={"before": "1", "now": "1"},
                              agree=True)
            shadow_log.record("standstill", shadow={"stationary": True}, agree=False)
            shadow_log.record("decimal_estimate", shadow={"lowest": "10517.80"}, agree="yes")
            lines = [json.loads(line) for line in shadow_log.read_text().splitlines()]
            self.assertEqual(["standstill", "standstill", "decimal_estimate"], [line["function"] for line in lines])
            self.assertIsNone(lines[2]["agree"])
            overview = shadow_log.summary(shadow_log.read_text())
            self.assertEqual((2, 2, 1, 1), tuple(overview["standstill"][key]
                                                 for key in ("entries", "compared", "agree", "differ")))
            self.assertEqual("Stillstand per Bildvergleich", overview["standstill"]["label"])
            self.assertEqual(1, len(shadow_log.read_text(1).splitlines()))

    def test_the_log_is_trimmed(self):
        with TemporaryDirectory() as folder, patch.object(shadow_log, "SHADOW_LOG", Path(folder) / "log.jsonl"), \
                patch.object(shadow_log, "MAX_ENTRIES", 3):
            for index in range(5):
                shadow_log.record("standstill", shadow={"index": index})
            self.assertEqual([2, 3, 4], [json.loads(line)["shadow"]["index"]
                                         for line in shadow_log.read_text().splitlines()])

    def test_only_with_experimental_functions(self):
        self.assertTrue(shadow_log.enabled({"experiments_enabled": True}))
        self.assertFalse(shadow_log.enabled({"experiments_enabled": False}))
        self.assertFalse(shadow_log.enabled(None))
        self.assertIn("if shadow_log.enabled(active_rules) and not ocr_confirmed and not hidden_slots:", RUN)
        self.assertIn("if not shadow_on:\n                stationary_state[\"last\"] = None", RUN)
        self.assertNotIn('kind="shadow_decimal_estimate"', RUN)


class ComparisonTests(unittest.TestCase):
    def test_estimate_against_the_confirmed_reading_of_the_same_check(self):
        estimate = {"lowest": "10517.80", "highest": "10517.89"}
        self.assertTrue(run.estimate_agrees(estimate, "ocr_only", "10517.84?", 2, 5))
        self.assertFalse(run.estimate_agrees(estimate, "match", "10517.91?", 2, 5))
        self.assertIsNone(run.estimate_agrees(estimate, "ocr_unclear", "10517.8??", 2, 5))

    def test_standstill_against_both_readings(self):
        self.assertTrue(run.standstill_agrees({"stationary": True}, "10517.845", "10517.845"))
        self.assertFalse(run.standstill_agrees({"stationary": True}, "10517.845", "10517.851"))
        self.assertTrue(run.standstill_agrees({"stationary": False}, "10517.845", "10517.851"))
        # 0.5.43: compared on the positions both read.
        self.assertTrue(run.standstill_agrees({"stationary": True}, "10517.84?", "10517.845"))
        self.assertIsNone(run.standstill_agrees({"stationary": True}, None, "10517.845"))

    def test_experiments_move_to_the_shadow_log(self):
        record = {"experiment": {"stable": "10517.84", "load": 0.5,
                                 "perspective": {"reading": "10517.84", "seconds": 2.0},
                                 "seven_segment": {"reading": "1?517.84"}}}
        with TemporaryDirectory() as folder, patch.object(shadow_log, "SHADOW_LOG", Path(folder) / "log.jsonl"):
            kept = run.log_experiments(record, {"image": "t1"})
            entries = [json.loads(line) for line in shadow_log.read_text().splitlines()]
            overview = background_view.summary("", shadow_log.read_text())
        self.assertEqual({"shadow_log": ["perspective", "seven_segment"]}, kept["experiment"])
        self.assertEqual({"perspective": True, "seven_segment": None},
                         {entry["function"]: entry["agree"] for entry in entries})
        self.assertEqual(1, overview["experiments"]["perspective"]["same"])
        self.assertEqual(1, overview["experiments"]["seven_segment"]["unclear"])
        skipped = {"experiment": {"skipped": "busy"}}
        self.assertIs(skipped, run.log_experiments(skipped, {}))


class PanelTests(unittest.TestCase):
    def test_section_and_routes(self):
        self.assertIn('<details id="shadow-log">', panel.PAGE)
        self.assertIn('href="schattenmodus-protokoll"', panel.PAGE)
        source = (ROOT / "panel.py").read_text(encoding="utf-8")
        self.assertIn('if path == "/schattenmodus-protokoll":', source)
        self.assertIn('if path == "/schattenmodus-uebersicht":', source)
        self.assertIn("shadow_log.py", (ROOT / "Dockerfile").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
