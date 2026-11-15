"""Regression tests for the meter plausibility check and cumulative consumption."""

from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from consumption import DEFAULT_FLOW_LPH, ImplausibleReading, accumulate_consumption, parse_flow_limit


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
