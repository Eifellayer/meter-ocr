import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import debug_log
from checks import only_last_compared_unclear

PANEL = (Path(__file__).resolve().parents[1] / "panel.py").read_text(encoding="utf-8")


class DebugLogTests(TestCase):
    def test_entries_are_rolled_and_counter_is_reduced(self):
        with TemporaryDirectory() as folder, patch.object(debug_log, "DEBUG_LOG", Path(folder) / "log.jsonl"), \
                patch.object(debug_log, "MAX_ENTRIES", 3):
            for index in range(5):
                debug_log.record(kind="automatic", ocr=f"1047{index}.000", detail="",
                                 consumption={"anchor_litres": 1, "pending_litres": 2, "secret": "x"})
            rows = [json.loads(line) for line in debug_log.read_text().splitlines()]
            self.assertEqual(["10472.000", "10473.000", "10474.000"], [row["ocr"] for row in rows])
            self.assertNotIn("detail", rows[0])
            self.assertEqual({"anchor_litres": 1, "pending_litres": 2}, rows[0]["consumption"])
            self.assertEqual(1, len(debug_log.read_text(1).splitlines()))

    def test_panel_offers_log_and_advanced_buttons(self):
        self.assertIn('id="debug-log"', PANEL)
        self.assertIn('if path == "/debug-protokoll":', PANEL)
        advanced = PANEL.index('id="calibration-advanced"')
        self.assertLess(advanced, PANEL.index('id="calibration-intensive"'))

    def test_single_unclear_last_compared_digit(self):
        self.assertTrue(only_last_compared_unclear("10475.1??", 2))
        self.assertFalse(only_last_compared_unclear("10475.12?", 2))
        self.assertFalse(only_last_compared_unclear("1047?.12?", 2))
