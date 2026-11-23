"""0.5.46: consumption and costs of today, this month and this year directly from the app."""

from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from consumption import parse_price, period_values, update_periods, WORK_PRICE_RANGE  # noqa: E402
import panel  # noqa: E402

ZONE = ZoneInfo("Europe/Berlin")
ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")


def at(*parts):
    return datetime(*parts, tzinfo=ZONE).timestamp()


class PeriodTests(unittest.TestCase):
    def test_day_month_year_start_again_at_midnight(self):
        state, changed = update_periods(None, 1_000_000, at(2026, 11, 30, 22, 0), ZONE)
        self.assertTrue(changed)
        self.assertEqual(1_000_000, state["day"]["start"])
        state, _ = update_periods(state, 1_004_000, at(2026, 11, 30, 23, 55), ZONE)
        values = period_values(state, 1_004_000, at(2026, 11, 30, 23, 55), ZONE)
        self.assertEqual(4_000, values["day"]["litres"])
        self.assertEqual(4_000, values["month"]["litres"])
        # New day and new month: the last total before the change is the new start.
        state, changed = update_periods(state, 1_004_500, at(2026, 12, 1, 0, 3), ZONE)
        self.assertTrue(changed)
        values = period_values(state, 1_004_500, at(2026, 12, 1, 0, 3), ZONE)
        self.assertEqual(500, values["day"]["litres"])
        self.assertEqual(500, values["month"]["litres"])
        self.assertEqual(4_500, values["year"]["litres"])
        self.assertEqual(at(2026, 12, 1), values["month"]["begin"])

    def test_new_year(self):
        state, _ = update_periods(None, 50_000, at(2026, 12, 31, 20, 0), ZONE)
        state, _ = update_periods(state, 52_000, at(2026, 12, 31, 23, 50), ZONE)
        state, _ = update_periods(state, 52_300, at(2027, 1, 1, 0, 4), ZONE)
        values = period_values(state, 52_300, at(2027, 1, 1, 0, 4), ZONE)
        self.assertEqual({"day": 300, "month": 300, "year": 300},
                         {key: value["litres"] for key, value in values.items()})

    def test_first_start_uses_the_dated_samples(self):
        samples = [[at(2026, 11, 20, 12, 0), 10_000, 10], [at(2026, 11, 22, 23, 0), 20_000, 10],
                   [at(2026, 11, 23, 8, 0), 23_000, 10]]
        state, _ = update_periods(None, 24_000, at(2026, 11, 23, 13, 0), ZONE, samples)
        values = period_values(state, 24_000, at(2026, 11, 23, 13, 0), ZONE)
        self.assertEqual(4_000, values["day"]["litres"])
        self.assertIsNone(values["day"]["since"])
        # The month began before the first sample: counted since then, and marked as such.
        self.assertEqual(14_000, values["month"]["litres"])
        self.assertEqual(samples[0][0], values["month"]["since"])

    def test_unchanged_state_is_not_saved_again(self):
        state, _ = update_periods(None, 1_000, at(2026, 11, 23, 13, 0), ZONE)
        _, changed = update_periods(state, 1_000, at(2026, 11, 23, 13, 5), ZONE)
        self.assertFalse(changed)

    def test_costs_like_the_bill(self):
        state, _ = update_periods(None, 0, at(2026, 11, 1, 0, 0), ZONE)
        values = period_values(state, 100_000, at(2026, 11, 23, 13, 0), ZONE,
                               kwh_per_m3=10.0, work_price=10.59, base_price=209.87)
        self.assertEqual(1000.0, values["month"]["kwh"])
        self.assertEqual(round(1000 * 0.1059 + 209.87 / 365 * 23, 2), values["month"]["cost"])
        self.assertEqual(round(1000 * 0.1059 + 209.87 / 365 * 327, 2), values["year"]["cost"])
        without = period_values(state, 100_000, at(2026, 11, 23, 13, 0), ZONE)
        self.assertIsNone(without["month"]["kwh"])
        self.assertIsNone(without["month"]["cost"])

    def test_prices(self):
        self.assertEqual(10.59, parse_price("10,59", WORK_PRICE_RANGE))
        self.assertIsNone(parse_price("", WORK_PRICE_RANGE))
        with self.assertRaises(ValueError):
            parse_price("1000", WORK_PRICE_RANGE)


class PublishTests(unittest.TestCase):
    def test_sensors(self):
        import run
        history = {"consumption": {"total_litres": 5_000}}
        rules = {"kwh_conversion_factor": 10.0, "gas_work_price": 10.0, "gas_base_price": 0}
        values, changed = run.gas_period_values(history, rules, at(2026, 11, 23, 13, 0), ZONE)
        self.assertTrue(changed)
        self.assertIn("consumption_periods", history)
        payloads = run.period_sensor_payloads(values, rules, ZONE)
        self.assertEqual({"sensor.rf1_verbrauch_heute", "sensor.rf1_verbrauch_diesen_monat",
                          "sensor.rf1_verbrauch_dieses_jahr", "sensor.rf1_verbrauch_heute_kwh",
                          "sensor.rf1_verbrauch_diesen_monat_kwh", "sensor.rf1_verbrauch_dieses_jahr_kwh",
                          "sensor.rf1_gaskosten_heute", "sensor.rf1_gaskosten_diesen_monat",
                          "sensor.rf1_gaskosten_dieses_jahr"}, set(payloads))
        day = payloads["sensor.rf1_verbrauch_heute"]
        self.assertEqual("0", day["state"])
        self.assertEqual("total", day["attributes"]["state_class"])
        self.assertTrue(day["attributes"]["last_reset"].startswith("2026-11-23T00:00:00"))
        self.assertEqual("EUR", payloads["sensor.rf1_gaskosten_diesen_monat"]["attributes"]["unit_of_measurement"])
        self.assertEqual(2, RUN.count("if publish_periods(history, token, get_auto_rules(), time.time(), zone):"))

    def test_reset_with_statistics_keeps_the_periods(self):
        import run
        kept = run.factory_reset_history({"consumption": {}, "consumption_periods": {"day": {}}}, True)
        self.assertIn("consumption_periods", kept)


class PanelTests(unittest.TestCase):
    def test_price_fields_and_wizard_keeps_saved_prices(self):
        source = (ROOT / "panel.py").read_text(encoding="utf-8")
        self.assertEqual(2, source.count('<input name="gas_work_price"'))
        self.assertEqual(2, source.count('<input name="gas_base_price"'))
        old = {"gas_work_price": 10.59, "gas_base_price": 209.87}
        kept = panel.wizard_energy_factors(lambda key, default=None: default, old)
        self.assertEqual(10.59, kept["gas_work_price"])
        self.assertEqual(209.87, kept["gas_base_price"])
        sent = panel.wizard_energy_factors(lambda key, default=None: {"gas_work_price": "11,2"}.get(key, default), old)
        self.assertEqual(11.2, sent["gas_work_price"])

    def test_overview_periods(self):
        history = {"consumption": {"total_litres": 3_000},
                   "consumption_periods": {"month": {"key": "2026-11", "start": 1_000, "begin": 0, "since": None}}}
        periods = panel.overview_periods(history, {}, at(2026, 11, 23, 13, 0), ZONE)
        self.assertEqual({"month": {"litres": 2_000, "kwh": None, "cost": None, "since": None}}, periods)


if __name__ == "__main__":
    unittest.main()
