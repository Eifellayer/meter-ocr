"""0.5.39: debug log of a chosen period for the support, without device names or addresses."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bug_report  # noqa: E402
import panel  # noqa: E402
import support_log  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
SOURCE = {"mode": "camera", "label": "Kellerkamera Gas", "camera": "camera.keller_gaszaehler",
          "reference": "sensor.gas_referenz", "url": "http://192.168.1.50:8080/"}


def line(hours_ago, **fields):
    return json.dumps({"time": (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds"), **fields})


LOG = "\n".join([
    line(30, kind="automatic", ocr="10517.83?", outcome="ocr_only"),
    line(2, kind="exposure_adjust", entity="number.keller_gaszaehler_gain", old=2, new=3),
    line(1, kind="automatic", ocr="10518.07?", outcome="ocr_unclear", readings=["10518.07?", "10518.0??"],
         detail="Kamera camera.keller_gaszaehler unter http://192.168.1.50:8080/capture nicht erreichbar",
         consumption={"reading_litres": 10518070, "total_litres": 38620}),
    line(0.5, kind="setup_start", note="Kellerkamera Gas an esp-gas.local, Mail an someone@example.org",
         token="abcdef0123456789abcdef0123456789abcdef01", mac="aa:bb:cc:dd:ee:ff"),
    "kein json",
])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.names = support_log.source_names(SOURCE)

    def test_only_the_chosen_period(self):
        self.assertEqual(3, len(support_log.export(LOG, 24, self.names, NOW).splitlines()))
        self.assertEqual(2, len(support_log.export(LOG, 1, self.names, NOW).splitlines()))
        self.assertEqual(4, len(support_log.export(LOG, None, self.names, NOW).splitlines()))

    def test_no_device_names_addresses_or_secrets(self):
        text = support_log.export(LOG, None, self.names, NOW)
        for secret in ("keller", "Kellerkamera", "192.168", "esp-gas.local", "example.org", "abcdef0123",
                       "aa:bb:cc", "gas_referenz", "http"):
            self.assertNotIn(secret.lower(), text.lower(), secret)

    def test_readings_times_and_results_stay(self):
        entries = [json.loads(item) for item in support_log.export(LOG, None, self.names, NOW).splitlines()]
        automatic = entries[2]
        self.assertEqual(("10518.07?", "ocr_unclear", ["10518.07?", "10518.0??"]),
                         (automatic["ocr"], automatic["outcome"], automatic["readings"]))
        self.assertEqual(10518070, automatic["consumption"]["reading_litres"])
        self.assertEqual((NOW - timedelta(hours=1)).isoformat(timespec="seconds"), automatic["time"])
        self.assertEqual("<gerät>", entries[1]["entity"])
        self.assertIn("<adresse>", automatic["detail"])

    def test_meter_readings_and_versions_are_no_addresses(self):
        self.assertEqual("Stand 10517.83 mit Version 0.5.39", support_log.clean_text("Stand 10517.83 mit Version 0.5.39"))

    def test_names_count_only_as_whole_words(self):
        names = support_log.source_names({"label": "Gas", "camera": "camera.gas"})
        self.assertEqual("<gerät> zeigt Gaszähler", support_log.clean_text("Gas zeigt Gaszähler", names))


class PanelTests(unittest.TestCase):
    def test_download_with_period(self):
        self.assertIn('id="support-log-period"', panel.PAGE)
        self.assertIn('href="support-protokoll?stunden=24"', panel.PAGE)
        self.assertIn('if path == "/support-protokoll":', (ROOT / "panel.py").read_text(encoding="utf-8"))
        self.assertIn("support_log.py", (ROOT / "Dockerfile").read_text(encoding="utf-8"))

    def test_the_bug_report_points_to_it(self):
        url = bug_report.issue_url("0.5.39", "camera", 5, 3, [], "")
        self.assertIn("F%C3%BCr+den+Support+herunterladen", url)


if __name__ == "__main__":
    unittest.main()
