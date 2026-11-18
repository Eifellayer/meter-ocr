"""Temporary precision fallback regression tests for the seventh roller."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checks import (
    DEFAULT_INTERVAL_MINUTES,
    SEVENTH_DIGIT_PASS,
    SEVENTH_DIGIT_WAIT_NOTICE,
    SEVENTH_DIGIT_WAIT_SECONDS,
    defer_duplicate_cycle,
    record_sample,
    schedule_next_check,
    seventh_digit_can_pass,
)

from i18n import english_activity, english_result


def sample(stamp, *, raw="12345.87", actual="12345.87", **options):
    return {
        "esp_timestamp": stamp.isoformat(), "raw_value": raw,
        "actual_value": actual, **options,
    }


class SeventhRollerTests(unittest.TestCase):
    def test_one_unclear_seventh_digit_is_only_partially_confirmed_and_waits(self):
        now = datetime.now(timezone.utc)
        history = {}
        data = sample(now)
        readings = ("12345.8?", "12345.81", "12345.82")
        self.assertTrue(record_sample(
            history, data, "12345.8?", timezone.utc, now, 2,
            ocr_confirmed=False, readings=readings,
        ))
        self.assertEqual("match_with_warning", history["status"])
        self.assertEqual(SEVENTH_DIGIT_PASS, history["check_detail"])
        self.assertTrue(history["seventh_digit_wait"])
        self.assertNotIn("last_match_at", history)
        self.assertEqual([], history["confirmations"])
        self.assertNotIn("consumption", history)
        schedule_next_check(history, history["status"], now.timestamp(), DEFAULT_INTERVAL_MINUTES)
        self.assertEqual(now.timestamp() + SEVENTH_DIGIT_WAIT_SECONDS, history["next_check_at"])
        self.assertNotIn("failure_attempts", history)
        self.assertFalse(record_sample(
            history, data, "12345.8?", timezone.utc, now, 2,
            ocr_confirmed=False, readings=readings,
        ))

        next_time = now + timedelta(seconds=SEVENTH_DIGIT_WAIT_SECONDS + 1)
        self.assertTrue(record_sample(
            history, sample(next_time), "12345.87", timezone.utc, next_time, 2,
            readings=("12345.87", "12345.87"),
        ))
        self.assertEqual("match", history["status"])
        self.assertNotIn("seventh_digit_wait", history)
        schedule_next_check(history, history["status"], next_time.timestamp(), DEFAULT_INTERVAL_MINUTES)
        self.assertEqual(next_time.timestamp() + DEFAULT_INTERVAL_MINUTES * 60, history["next_check_at"])
        self.assertEqual(1, len(history["confirmations"]))

    def test_fallback_requires_reliable_source_and_consistent_six_digit_prefix(self):
        now = datetime.now(timezone.utc)
        good = sample(now)
        readings = ("12345.8?", "12345.81", "12345.82")
        self.assertTrue(seventh_digit_can_pass(good, "12345.8?", readings))
        invalid_cases = (
            (sample(now, raw="12345.97"), "12345.8?", readings),
            (sample(now, reference_is_fallback=True), "12345.8?", readings),
            (sample(now, reference_required=False), "12345.8?", readings),
            (sample(now, actual="12345.97", raw="12345.97"), "12345.8?", readings),
            (good, "12346.8?", readings),
            (good, "12345.8?", ("12345.8?", "12344.8?", "12346.8?")),
            (good, "12345.8?", ("12345.8?",)),
            (good, "12345.84", ("12345.84", "12345.84", "12345.84")),
        )
        for data, ocr, values in invalid_cases:
            with self.subTest(data=data, ocr=ocr, readings=values):
                self.assertFalse(seventh_digit_can_pass(data, ocr, values))

    def test_strict_mode_and_other_precision_do_not_downgrade(self):
        now = datetime.now(timezone.utc)
        readings = ("12345.8?", "12345.81", "12345.82")
        for decimals, strict in ((2, True), (3, False), (1, False), (0, False)):
            with self.subTest(decimals=decimals, strict=strict):
                history = {}
                self.assertTrue(record_sample(
                    history, sample(now), "12345.8?", timezone.utc, now,
                    decimals, readings=readings, ocr_confirmed=False,
                    precision_mode=strict,
                ))
                self.assertNotEqual("match_with_warning", history["status"])
                self.assertNotIn("seventh_digit_wait", history)

    def test_english_status_and_wait_notice_are_localized(self):
        self.assertIn("six digits", english_result(SEVENTH_DIGIT_PASS, "match_with_warning", 2))
        self.assertIn("higher meter reading", english_activity("waiting", SEVENTH_DIGIT_WAIT_NOTICE))

    def test_duplicate_picture_does_not_short_circuit_thirty_minute_wait(self):
        now = datetime.now(timezone.utc)
        history = {}
        self.assertTrue(record_sample(
            history, sample(now), "12345.8?", timezone.utc, now, 2,
            ocr_confirmed=False, readings=("12345.8?", "12345.81", "12345.82"),
        ))
        schedule_next_check(history, history["status"], now.timestamp())
        defer_duplicate_cycle(history, now.timestamp() + 10, DEFAULT_INTERVAL_MINUTES)
        self.assertEqual(now.timestamp() + 10 + SEVENTH_DIGIT_WAIT_SECONDS, history["next_check_at"])
        self.assertEqual(0, history.get("failure_attempts", 0))


if __name__ == "__main__":
    unittest.main()
