"""'Fehler melden' builds a GitHub link without private data."""

from datetime import datetime, timezone
import json
from unittest import TestCase
from urllib.parse import parse_qs, urlsplit

import bug_report

NOW = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)


def log(*outcomes, hours_ago=1):
    stamp = NOW.replace(hour=20 - hours_ago).isoformat()
    return "\n".join(json.dumps({"time": stamp, "kind": "automatic", "outcome": outcome,
                                 "ocr": "10483.3??"}) for outcome in outcomes)


class BugReportTests(TestCase):
    def test_failure_share_counts_only_finished_automatic_checks_of_the_last_day(self):
        text = "\n".join([log("ocr_unclear", "ocr_only", "standalone_pending", "match"),
                          log("ocr_unclear", hours_ago=19),
                          json.dumps({"time": NOW.isoformat(), "kind": "setup_image"}), "kaputt"])
        self.assertEqual((2, 4), bug_report.failure_share(text, NOW))
        old = json.dumps({"time": "2026-11-17T10:00:00+00:00", "kind": "automatic", "outcome": "ocr_unclear"})
        self.assertEqual((0, 0), bug_report.failure_share(old, NOW))

    def test_link_contains_version_source_kind_and_share_but_no_private_values(self):
        url = bug_report.issue_url("0.2.0", "esphome", 5, 3, ["perspective"],
                                   log("ocr_unclear", "ocr_only"), now=NOW)
        parts = urlsplit(url)
        self.assertEqual("https://github.com/Eifellayer/meter-ocr/issues/new", f"{parts.scheme}://{parts.netloc}{parts.path}")
        query = parse_qs(parts.query)
        body = query["body"][0]
        self.assertIn("App-Version: 0.2.0", body)
        self.assertIn("ESPHome-/Home-Assistant-Kamera", body)
        self.assertIn("1 von 2 (50 %)", body)
        self.assertIn("perspective", body)
        self.assertEqual(["bug.yml"], query["template"])
        for private in ("camera.", "http://", "10483", "192.168", "Bearer"):
            self.assertNotIn(private, body)

    def test_english_link_and_unknown_source(self):
        body = parse_qs(urlsplit(bug_report.issue_url("0.2.0", "", 5, 3, [], "", language="en", now=NOW)).query)["body"][0]
        self.assertIn("Image source: unbekannt", body)
        self.assertIn("no checks", body)
        self.assertIn("Active experiments: none", body)
