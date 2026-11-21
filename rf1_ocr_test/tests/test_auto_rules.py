import unittest

import auto_rules
from settings import DEFAULTS


class AutoRulesTests(unittest.TestCase):
    """The rule file has one shape; these tests run without the worker."""

    def setUp(self):
        self.options = dict(DEFAULTS, vergleich_nachkommastellen=2)
        self.rules = auto_rules.default_rules(self.options)

    def test_defaults_follow_the_app_options(self):
        self.assertEqual(2, self.rules["decimals"])
        self.assertEqual(self.options["ocr_versuche"], self.rules["attempts"])
        self.assertEqual("auto", self.rules["crop_mode"])
        self.assertFalse(self.rules["precision_mode"])
        self.assertEqual((5, 3), (self.rules["integer_digits"], self.rules["fraction_digits"]))

    def test_stored_rules_without_core_fields_are_unusable(self):
        self.assertIsNone(auto_rules.stored_rules({"decimals": 7, "attempts": 5}, self.options))
        self.assertIsNone(auto_rules.stored_rules({"attempts": 5}, self.options))

    def test_stored_rules_repair_invalid_fields(self):
        rules = auto_rules.stored_rules({
            "decimals": 3, "attempts": 4, "polarity": "pink", "crop_mode": "sideways", "fraction_digits": 2,
            "meter_display": "abacus", "max_flow_lph": -1, "fallback_value": "abc", "experiments": {"unknown": True},
        }, self.options)
        self.assertEqual("auto", rules["polarity"])
        self.assertEqual("auto", rules["crop_mode"])
        self.assertEqual(self.options["ausschnitt"], rules["crop"])
        self.assertEqual(2, rules["decimals"])  # never more than the meter shows
        self.assertEqual("rollers", rules["meter_display"])
        self.assertEqual("", rules["fallback_value"])
        self.assertNotIn("unknown", rules["experiments"])

    def test_a_round_trip_keeps_the_rules(self):
        saved = auto_rules.changed_rules(self.rules, dict(self.rules, decimals=1, attempts=7))
        loaded = auto_rules.stored_rules(saved, self.options)
        for key in ("decimals", "attempts", "polarity", "crop_mode", "crop", "width", "integer_digits",
                    "fraction_digits", "meter_display", "interval_minutes", "max_flow_lph"):
            with self.subTest(key=key):
                self.assertEqual(saved[key], loaded[key])

    def test_changes_are_validated(self):
        for values in ({"decimals": 4}, {"attempts": 0}, {"polarity": "pink"}, {"crop_mode": "x"},
                       {"max_flow_lph": 0}, {"fallback_value": "12x"}, {"precision_mode": "yes"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                auto_rules.changed_rules(self.rules, dict(self.rules, **values))

    def test_a_changed_frame_drops_the_frame_revision(self):
        current = dict(self.rules, crop_revision="abc")
        moved = auto_rules.changed_rules(current, dict(current, crop="60,60,560,130"))
        self.assertEqual("", moved["crop_revision"])
        self.assertEqual("abc", auto_rules.changed_rules(current, dict(current, attempts=6))["crop_revision"])


    def test_frames_changed_in_the_web_interface_belong_to_the_user(self):
        manual = dict(self.rules, crop_mode="manual", crop="60,60,560,130", width=300)
        marked = auto_rules.user_frames(self.rules, manual)
        self.assertEqual("user", marked["frames_origin"])
        saved = auto_rules.changed_rules(self.rules, marked)
        self.assertTrue(auto_rules.frames_locked(saved))
        # Saving other settings later does not change who placed the frames ...
        self.assertNotIn("frames_origin", auto_rules.user_frames(saved, {"crop_mode": "manual", "attempts": 6}))
        self.assertEqual("user", auto_rules.user_frames(saved, dict(saved, attempts=6))["frames_origin"])
        # ... a self-setup takes them over, and the automatic crop has no owner.
        by_setup = auto_rules.changed_rules(saved, dict(saved, frames_origin="setup"))
        self.assertFalse(auto_rules.frames_locked(by_setup))
        self.assertEqual("", auto_rules.changed_rules(saved, dict(saved, crop_mode="auto"))["frames_origin"])
        self.assertEqual("user", auto_rules.stored_rules(saved, self.options)["frames_origin"])
        self.assertEqual("", auto_rules.stored_rules(dict(saved, frames_origin="alien"), self.options)["frames_origin"])


if __name__ == "__main__":
    unittest.main()
