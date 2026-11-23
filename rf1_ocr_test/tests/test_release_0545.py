"""0.5.45: every procedure in shadow mode can be chosen on its own, like the experiments."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auto_rules import valid_experiments  # noqa: E402
import experiments  # noqa: E402
import panel  # noqa: E402
import shadow_log  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")


class ChoiceTests(unittest.TestCase):
    def test_procedures_are_on_by_default_and_can_be_switched_off(self):
        rules = {"experiments_enabled": True, "experiments": {}}
        for name in experiments.SHADOW_PROCEDURES:
            self.assertTrue(shadow_log.enabled(rules, name), name)
        self.assertFalse(shadow_log.enabled(rules, "perspective"))
        rules["experiments"] = {"orientation": False}
        self.assertFalse(shadow_log.enabled(rules, "orientation"))
        self.assertTrue(shadow_log.enabled(rules, "presort"))
        self.assertFalse(shadow_log.enabled({"experiments_enabled": False}, "presort"))

    def test_stored_choices(self):
        stored = valid_experiments({"perspective": True, "standstill": False, "presort": "ja"})
        self.assertEqual({"perspective": True, "seven_segment": False, "decimal_estimate": True,
                          "standstill": False, "orientation": True, "presort": True}, stored)

    def test_each_procedure_has_its_own_switch(self):
        self.assertIn('if shadow_log.enabled(active_rules, "decimal_estimate")', RUN)
        self.assertIn('shadow_on = shadow_log.enabled(active_rules, "standstill")', RUN)
        self.assertIn('shadow_log.enabled(get_auto_rules(), "orientation")', RUN)
        self.assertIn('shadow_log.enabled(active_rules, "presort")', RUN)


class PanelTests(unittest.TestCase):
    def test_all_procedures_appear_in_both_boxes(self):
        html = panel.experiment_options({"experiments": {"standstill": False, "perspective": True}})
        for name in [*experiments.EXPERIMENTS, *experiments.SHADOW_PROCEDURES]:
            self.assertIn(f'<select name="experiment_{name}">', html)
        self.assertIn('<select name="experiment_standstill"><option value="off" selected>', html)
        self.assertIn('<select name="experiment_orientation"><option value="off">Aus</option><option value="1" selected>', html)
        self.assertIn("Ausrichtung des Kamerabilds erkennen", html)
        self.assertIn("Detect the orientation of the camera picture", panel.experiment_options({}, "en"))
        self.assertEqual(2, panel.PAGE.count("{experiment_options}"))

    def test_saving_reads_every_procedure(self):
        fields = {"experiments_enabled": "1", "experiment_presort": "1", "experiment_standstill": "off"}
        saved = panel.experiment_settings(lambda name: fields.get(name, ""))
        self.assertTrue(saved["experiments"]["presort"])
        self.assertFalse(saved["experiments"]["standstill"])


if __name__ == "__main__":
    unittest.main()
