from zoneinfo import ZoneInfo
import unittest

from checks import LAST_DIGIT_NOTICE, MOVING_DIGIT_NOTICE, MOVING_DIGITS_NOTICE, WARNING_DETAIL_AFTER
import status_view

NOW = 1_800_000_000.0


def verdict(history, language="de", **options):
    options = {"detail": history.get("check_detail"), "precision_pending": False, "paused": False,
               "setup_pending": False, "partial_eighth_digit": False, "now": NOW, **options}
    return status_view.verdict(history, language, **options)


class StatusViewTests(unittest.TestCase):
    """The overview status, tested without the web server."""

    def test_a_confirmed_reading_is_all_good(self):
        view = verdict({"check_status": "match"})
        self.assertEqual(("ok", "✓", True), (view["tone"], view["icon"], view["routine_ok"]))
        self.assertEqual("Alles OK. Automatik läuft.", view["heading"])
        self.assertEqual("All good. Automatic checks running.", verdict({"check_status": "match"}, "en")["heading"])

    def test_a_paused_automatic_is_not_reported_as_running(self):
        view = verdict({"check_status": "match"}, paused=True)
        self.assertFalse(view["routine_ok"])
        self.assertEqual("Zählerstand bestätigt", view["heading"])

    def test_single_failures_stay_quiet_and_long_ones_ask_for_a_look(self):
        quiet = verdict({"check_status": "ocr_unclear", "failure_attempts": 1, "failure_since": NOW - 60})
        self.assertEqual(("notice", ""), (quiet["tone"], quiet["icon"]))
        repeated = verdict({"check_status": "ocr_unclear", "failure_attempts": status_view.QUIET_FAILURES,
                            "failure_since": NOW - 60})
        self.assertEqual("warning", repeated["tone"])
        long = verdict({"check_status": "ocr_unclear", "failure_attempts": 9,
                        "failure_since": NOW - WARNING_DETAIL_AFTER - 1})
        self.assertEqual("Zählerstand bitte prüfen", long["heading"])
        self.assertTrue(long["show_attempts"])
        self.assertTrue(long["incident"])

    def test_a_turning_roller_is_only_a_note(self):
        view = verdict({"check_status": "ocr_unclear", "check_detail": MOVING_DIGIT_NOTICE, "failure_attempts": 5,
                        "failure_since": NOW - 60})
        self.assertEqual(("notice", "Rolle drehte sich gerade"), (view["tone"], view["heading"]))

    def test_turning_rollers_have_an_english_heading(self):
        for notice, german, english in ((MOVING_DIGIT_NOTICE, "Rolle drehte sich gerade", "Roller was turning"),
                                        (MOVING_DIGITS_NOTICE, "Rollen drehten sich gerade", "Rollers were turning")):
            history = {"check_status": "ocr_unclear", "check_detail": notice, "failure_attempts": 1,
                       "failure_since": NOW - 60}
            self.assertEqual(german, verdict(history)["heading"])
            self.assertEqual(english, verdict(history, "en")["heading"])

    def test_the_eighth_digit_search_is_normal_operation(self):
        view = verdict({"check_status": "match_with_warning", "check_detail": LAST_DIGIT_NOTICE},
                       partial_eighth_digit=True)
        self.assertEqual(("ok", True, ""), (view["tone"], view["routine_ok"], view["detail"]))
        self.assertIn("8. Ziffer", view["heading"])

    def test_new_settings_wait_for_the_next_check(self):
        view = verdict({"check_status": "difference"}, precision_pending=True, detail="Neue Einstellungen")
        self.assertEqual(("neutral", "Automatischer Prüfstatus", "Neue Einstellungen"),
                         (view["tone"], view["heading"], view["detail"]))

    def test_recovery_sentence(self):
        zone = ZoneInfo("Europe/Berlin")
        self.assertEqual((0, False, ""), status_view.recovery({}, "de", False, zone))
        self.assertIn("2 von 3", status_view.recovery({"failure_attempts": 2}, "de", False, zone)[2])
        self.assertIn("pausiert", status_view.recovery({"failure_attempts": 2}, "de", True, zone)[2])
        attempts, suppressed, text = status_view.recovery(
            {"failure_attempts": 4, "retry_suppressed": True, "next_check_at": NOW}, "en", False, zone)
        self.assertEqual((4, True), (attempts, suppressed))
        self.assertIn("Next attempt at about", text)
        self.assertEqual(0, status_view.recovery({"failure_attempts": "x"}, "de", False, zone)[0])


if __name__ == "__main__":
    unittest.main()
