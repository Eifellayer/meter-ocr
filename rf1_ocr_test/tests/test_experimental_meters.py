from datetime import datetime, timezone
import json
from tempfile import TemporaryDirectory
from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experimental_meters import ExperimentalMeters, meter_config, read_meter


class ExperimentalMeterTests(TestCase):
    def test_setup_reset_can_keep_experimental_meter_readings_without_running_monitors(self):
        with TemporaryDirectory() as directory:
            file = Path(directory) / "meters.json"
            write = lambda path, content, mode: path.write_bytes(content)
            meter = ExperimentalMeters(file, lambda _: {}, write, timezone.utc)
            states = {"sensor.water": {"unit": "m³", "reading": 2000, "total": 1000,
                                        "timestamp": 100, "series": {
                                            "source": "m³", "samples": [[100, 1000, 1]]},
                                        "next": 999, "status": "ok"}}
            meter._save({"sensor.water": 30}, states)
            meter.reset(keep_statistics=True)
            self.assertEqual({}, meter.settings)
            self.assertNotIn("next", meter.states["sensor.water"])
            reloaded = ExperimentalMeters(file, lambda _: {}, write, timezone.utc)
            self.assertEqual(1000, reloaded.states["sensor.water"]["total"])
            self.assertEqual({}, reloaded.settings)
            reloaded.reset()
            self.assertFalse(file.exists())

    def reading(self, stamp, value, unit="m³"):
        return {"state": str(value), "last_updated": datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                "attributes": {"unit_of_measurement": unit, "state_class": "total_increasing"}}

    def test_each_sensor_has_its_own_interval(self):
        self.assertEqual({"sensor.water": 15, "sensor.power": 30}, meter_config("sensor.water, 15\nsensor.power"))
        for invalid in ("switch.test", "sensor.water, 4", "sensor.rf1_verbrauch_gesamt", "sensor.water\nsensor.water"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                meter_config(invalid)

    def test_duplicates_and_resets_do_not_add_consumption(self):
        water = read_meter({}, self.reading(100, 100), 100)
        water = read_meter(water, self.reading(200, 101), 200)
        self.assertEqual(1000, water["total"])
        self.assertEqual(1000, read_meter(water, self.reading(200, 101), 300)["total"])
        pending = read_meter(water, self.reading(300, 0), 300)
        self.assertEqual("reset_pending", pending["status"])
        water = read_meter(pending, self.reading(400, 1), 400)
        self.assertEqual(("reset", 1000), (water["status"], water["total"]))
        self.assertEqual(2000, read_meter(water, self.reading(500, 2), 500)["total"])
        power = read_meter({}, self.reading(500, 8, "kWh"), 500)
        self.assertEqual(("kWh", 0), (power["unit"], power["total"]))
