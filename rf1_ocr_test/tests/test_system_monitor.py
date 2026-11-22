from collections import namedtuple
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import system_monitor

Times = namedtuple("Times", "user system children_user children_system")


class SystemMonitorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        (self.root / "self").mkdir()
        (self.root / "thermal_zone0").mkdir()
        system_monitor._last.clear()
        self.addCleanup(system_monitor._last.clear)

    def write(self, busy, idle, own):
        (self.root / "stat").write_text(f"cpu  {busy} 0 0 {idle} 0 0 0 0 0 0\ncpu0 1 2 3 4\n")
        (self.root / "meminfo").write_text("MemTotal:  4096000 kB\nMemFree: 1 kB\nMemAvailable:  1024000 kB\n")
        (self.root / "self" / "status").write_text("Name:\tpython\nVmRSS:\t  204800 kB\n")
        (self.root / "loadavg").write_text("1.50 1.00 0.50 1/100 1\n")
        (self.root / "thermal_zone0" / "temp").write_text("51500\n")
        return lambda: Times(own, 0, 0, 0)

    def sample(self, now, times):
        return system_monitor.snapshot(now, proc=self.root, thermal=self.root, times=times, cores=lambda: 4)

    def test_memory_temperature_and_load_are_read(self):
        first = self.sample(0, self.write(100, 900, 1.0))
        self.assertEqual((4000, 1000, 75, 200, 51.5, 1.5),
                         (first["memory_total_mb"], first["memory_available_mb"], first["memory_used_percent"],
                          first["app_memory_mb"], first["temperature_c"], first["load"]))
        self.assertIsNone(first["cpu_percent"])

    def test_percentages_compare_two_samples(self):
        self.sample(0, self.write(100, 900, 1.0))
        second = self.sample(10, self.write(600, 1400, 21.0))
        self.assertEqual(50, second["cpu_percent"])
        self.assertEqual(50, second["app_cpu_percent"])  # 20 s of work in 10 s on 4 cores
        self.assertFalse(system_monitor.busy(second))
        self.assertTrue(system_monitor.busy({**second, "cpu_percent": 90}))

    def test_missing_files_give_no_values_and_no_error(self):
        empty = Path(self.enterContext(TemporaryDirectory()))
        sample = system_monitor.snapshot(0, proc=empty, thermal=empty, times=lambda: Times(0, 0, 0, 0))
        self.assertIsNone(sample["memory_total_mb"])
        self.assertIsNone(sample["temperature_c"])
        self.assertFalse(system_monitor.busy(sample))


if __name__ == "__main__":
    unittest.main()
