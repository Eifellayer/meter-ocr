import unittest
from pathlib import Path

PANEL = (Path(__file__).resolve().parents[1] / "panel.py").read_text(encoding="utf-8")


class StaleViewTest(unittest.TestCase):
    def test_render_errors_are_not_connection_errors(self):
        render = PANEL.index("  try {{\n    automaticStatusFailures = 0;")
        connection = PANEL.index("showStale('offline')")
        self.assertLess(connection, render)
        self.assertIn("showStale('render')", PANEL)

    def test_restart_reloads_page(self):
        self.assertIn("sample.instance !== pageInstance", PANEL)
        self.assertIn('summary["instance"] = INSTANCE_ID', PANEL)
        self.assertIn("location.reload()", PANEL)

    def test_readable_last_digit_is_optimisation(self):
        self.assertIn("noteState = 'optimizing'", PANEL)
        self.assertIn("Höchstdauer", PANEL)
        self.assertNotIn("Statusaktualisierung kurz fehlgeschlagen", PANEL)


if __name__ == "__main__":
    unittest.main()
