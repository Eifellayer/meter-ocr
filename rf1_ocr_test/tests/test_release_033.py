import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MultipleMetersFieldRemovedTest(unittest.TestCase):
    """0.3.3: the confusing "Experimentell · Mehrere Zähler" field is gone (Stefan 20.11.)."""

    def test_field_endpoint_and_module_are_removed(self):
        panel = (ROOT / "panel.py").read_text(encoding="utf-8")
        run = (ROOT / "run.py").read_text(encoding="utf-8")
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("Mehrere Zähler", panel)
        self.assertNotIn("experimentelle-zaehler", panel)
        self.assertNotIn('id="experimental"', panel)
        self.assertNotIn("ExperimentalMeters", run)
        self.assertNotIn("experimental_meters.py", docker)
        self.assertFalse((ROOT / "experimental_meters.py").exists())

    def test_factory_reset_drops_the_old_settings_file(self):
        run = (ROOT / "run.py").read_text(encoding="utf-8")
        self.assertIn('HISTORY.with_name("experimental-meters.json").unlink(missing_ok=True)', run)


if __name__ == "__main__":
    unittest.main()
