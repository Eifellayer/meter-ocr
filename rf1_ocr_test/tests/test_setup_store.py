from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from calibration import Layout
import setup_store

RULES = {"integer_digits": 5, "fraction_digits": 3, "decimals": 2, "polarity": "auto", "meter_display": "rollers"}
SOURCE = {"mode": "camera", "camera": "camera.meter", "url": "", "reference": ""}


class SetupStoreTests(unittest.TestCase):
    """What a setup keeps between runs, tested without the worker."""

    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.store = setup_store.SetupStore(folder / "good.json", folder / "candidates.json",
                                            lambda path, content, mode: path.write_bytes(content))
        self.layout = Layout((100, 80, 500, 160), -3, 250)

    def test_the_good_frame_survives_settings_that_do_not_move_the_digits(self):
        self.store.remember_known_good_layout(RULES, SOURCE, self.layout)
        changed = dict(RULES, polarity="dark", decimals=0, meter_display="digital")
        self.assertEqual(self.layout, self.store.load_known_good_layout(changed, dict(SOURCE, reference="sensor.x")))
        self.assertIsNone(self.store.load_known_good_layout(RULES, dict(SOURCE, camera="camera.other")))
        self.assertIsNone(self.store.load_known_good_layout(dict(RULES, fraction_digits=2), SOURCE))

    def test_candidates_belong_to_one_scope(self):
        scope = self.store.candidate_scope((RULES, SOURCE), None, True, False)
        self.store.save_calibration_candidates(scope, {self.layout: (100, 31.5)})
        self.assertEqual({self.layout: (100, 31.5)}, self.store.load_calibration_candidates(scope, RULES))
        other = self.store.candidate_scope((dict(RULES, decimals=3), SOURCE), None, True, False)
        self.assertNotEqual(scope, other)
        self.assertEqual({}, self.store.load_calibration_candidates(other, RULES))

    def test_a_write_error_does_not_stop_the_setup(self):
        def refuse(*_):
            raise OSError
        self.store.write = refuse
        self.store.remember_known_good_layout(RULES, SOURCE, self.layout)
        self.assertIsNone(self.store.load_known_good_layout(RULES, SOURCE))


if __name__ == "__main__":
    unittest.main()
