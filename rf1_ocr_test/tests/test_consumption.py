"""Regression tests for the meter plausibility check and cumulative consumption."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from unittest import TestCase
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from consumption import (DEFAULT_FLOW_LPH, ImplausibleReading, accumulate_consumption,
                         consumption_statistics, parse_flow_limit, record_consumption_sample)


class ConsumptionTests(TestCase):
    source = ["esphome", "camera.meter", ""]

    def update(self, previous, stamp, reading, decimals=3, source=None):
        return accumulate_consumption(previous, self.source if source is None else source,
                                      stamp, reading, decimals, DEFAULT_FLOW_LPH)

    def test_invalid_measurement_does_not_move_the_baseline(self):
        first = self.update({}, 0, "12345.000")
        self.assertEqual(0, first["total_litres"])
        with self.assertRaisesRegex(ImplausibleReading, "schneller"):
            self.update(first, 60, "12346.000")
        with self.assertRaisesRegex(ImplausibleReading, "unter"):
            self.update(first, 60, "12344.990")
        with self.assertRaisesRegex(ImplausibleReading, "Messzeitpunkt"):
            self.update(first, 0, "12345.000")
        second = self.update(first, 60, "12345.080")
        self.assertEqual(80, second["total_litres"])

    def test_rounding_allows_crossing_a_whole_cubic_metre_boundary(self):
        first = self.update({}, 0, "12345.???", decimals=0)
        second = self.update(first, 5, "12346.???", decimals=0)
        self.assertEqual(1000, second["total_litres"])
        with self.assertRaises(ImplausibleReading):
            self.update(second, 10, "12348.???", decimals=0)

    def test_changing_source_or_precision_contributes_no_phantom_usage(self):
        first = self.update({}, 0, "12345.000")
        second = self.update(first, 60, "12345.060")
        coarser = self.update(second, 120, "12345.???", decimals=0)
        next_whole = self.update(coarser, 180, "12346.???", decimals=0)
        other = self.update(next_whole, 240, "00004.250", source=["esphome", "camera.other", ""])
        self.assertEqual(60, coarser["total_litres"])
        self.assertEqual(1000, next_whole["total_litres"])
        self.assertEqual(1000, other["total_litres"])
        self.assertEqual(4250, other["reading_litres"])

    def test_flow_limit_accepts_the_local_decimal_separator(self):
        self.assertEqual(2500, parse_flow_limit("2,5"))
        self.assertEqual(10001, parse_flow_limit("10.001"))
        for value in ("0", "nan", "-5", "2.0001", "9999999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_flow_limit(value)


class ConsumptionStatisticsTests(TestCase):
    midnight = datetime(2026, 11, 17, tzinfo=timezone.utc).timestamp()

    def record(self, points):
        series = {}
        for offset, total, step in points:
            series = record_consumption_sample(series, "meter", {
                "timestamp": self.midnight + offset, "total_litres": total, "step_litres": step,
            })
        return series

    def summarize(self, points, now):
        return consumption_statistics(self.record(points), "meter", self.midnight + now, timezone.utc)

    def test_distributes_increment_across_hour_and_midnight_and_marks_the_estimate(self):
        stats = self.summarize([(-900, 100, 1), (900, 160, 1), (2700, 200, 1)], 2700)
        self.assertEqual({"label": "17.11. 00:00", "litres": 70, "partial": False, "estimated": True},
                         stats["hours"][0])
        self.assertEqual({"label": "16.11. 23:00", "litres": 30, "partial": True, "estimated": True},
                         stats["hours"][1])
        self.assertEqual([70, 30], [bucket["litres"] for bucket in stats["days"][:2]])
        self.assertIsNone(stats["days"][2]["litres"])

    def test_gaps_and_precision_changes_remain_distinct_from_measured_zero(self):
        stats = self.summarize([(0, 100, 1), (4 * 3600, 220, 1),
                                (5 * 3600, 220, 10), (6 * 3600, 220, 10)], 6 * 3600 + 1)
        self.assertEqual(0, stats["hours"][1]["litres"])
        self.assertIsNone(stats["hours"][2]["litres"])
        self.assertIsNone(stats["hours"][3]["litres"])
        self.assertEqual(120, stats["days"][0]["litres"])
        self.assertTrue(stats["days"][0]["partial"])
        self.assertFalse(stats["days"][0]["estimated"])

    def test_retention_keeps_only_recent_samples_and_the_boundary_anchor(self):
        day = 86400
        series = self.record([(i * day, i * 20, 1) for i in range(20)])
        self.assertEqual(self.midnight + 10 * day, series["samples"][0][0])
        duplicate = record_consumption_sample(series, "meter", {
            "timestamp": self.midnight + 19 * day, "total_litres": 500, "step_litres": 1,
        })
        self.assertEqual(series, duplicate)
        other = consumption_statistics(series, "other", self.midnight + 20 * day, timezone.utc)
        self.assertIsNone(other["days"][0]["litres"])

    def test_repeated_clock_hour_is_labelled_twice_on_the_autumn_clock_change(self):
        zone = ZoneInfo("Europe/Berlin")
        start = datetime(2026, 10, 25, 2, tzinfo=zone)
        samples = [[start.timestamp(), 10, 1], [start.replace(fold=1).timestamp(), 40, 1],
                   [(start + timedelta(hours=1)).timestamp(), 50, 1]]
        result = consumption_statistics({"source": "meter", "samples": samples}, "meter", samples[-1][0], zone)
        self.assertEqual(["25.10. 02:00 (+0100)", "25.10. 02:00 (+0200)"],
                         [hour["label"] for hour in result["hours"][1:3]])
        self.assertEqual([10, 30], [hour["litres"] for hour in result["hours"][1:3]])
        self.assertEqual(40, result["days"][0]["litres"])
