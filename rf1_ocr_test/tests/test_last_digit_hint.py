"""Hints about the optional last roller and expiry of outdated digit suggestions."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from test_ingress import IngressFixture


class LastDigitHintTests(IngressFixture):
    def test_outdated_unconfirmed_suggestion_is_no_longer_offered(self):
        self.rules["reflection_estimate_enabled"] = True
        estimate = {"left": "", "digit": "1", "right": "0471.91", "time": 1000}
        self.history.write_text(json.dumps({
            "reflection_estimate": estimate, "reflection_anchor": {"time": 1000 + 2 * 3600, "value": 10472940},
        }))
        self.assertIsNone(json.loads(self.request("/automatic")[0])["reflection_estimate"])
        # A fresh suggestion within the hour stays available.
        self.history.write_text(json.dumps({
            "reflection_estimate": estimate, "reflection_anchor": {"time": 1000 + 600, "value": 10471920},
        }))
        self.assertEqual("1", json.loads(self.request("/automatic")[0])["reflection_estimate"]["digit"])
        # A confirmed value stays visible even when it is older.
        candidate_id = json.loads(self.request("/automatic")[0])["reflection_estimate"]["id"]
        self.assertEqual(303, self.submit("/ergaenzte-ziffer-bestaetigen", estimate_id=candidate_id, digit="1")[0])
        self.history.write_text(json.dumps({
            "reflection_estimate": estimate, "reflection_anchor": {"time": 1000 + 2 * 3600, "value": 10472940},
        }))
        self.assertTrue(json.loads(self.request("/automatic")[0])["reflection_estimate"]["confirmed"])

    def test_page_explains_skipped_and_background_last_digit_in_both_languages(self):
        german = self.request("/")[0]
        english = self.request("/", accept="en")[0]
        self.assertIn('id="hero-digit-note"', german)
        self.assertIn("Ziffer wird nicht verglichen (eingestellt:", german)
        self.assertIn("Ziffer wird im Hintergrund gesucht.", german)
        self.assertIn("Nach dem Speichern sucht die App sie im Hintergrund weiter.", german)
        self.assertEqual(2, german.count('class="calibration-last-digit-note settings-note"'))
        self.assertIn("digit is not compared (setting:", english)
        self.assertIn("the app keeps searching for it in the background", english)

    def test_overview_shows_that_the_eighth_digit_is_not_compared(self):
        from playwright.sync_api import sync_playwright

        self.setup_pending = False
        self.source_selected = True
        self.rules.update(integer_digits=5, fraction_digits=3, decimals=2)
        self.history.write_text(json.dumps({"check_status": "ocr_only", "ocr_value": "10472.94?", "comparison_decimals": 2}))
        Image.new("RGB", (400, 90), "gray").save(self.root / "current.jpg")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base + "/")
            note = page.locator("#hero-digit-note")
            note.wait_for(state="visible")
            self.assertEqual("Die 8. Ziffer wird nicht verglichen (eingestellt: 2 Nachkommastellen).", note.inner_text())
            self.assertEqual("skipped", note.get_attribute("data-state"))
            browser.close()

    def test_background_search_is_visible_on_the_last_roller(self):
        from playwright.sync_api import sync_playwright

        self.setup_pending = False
        self.source_selected = True
        self.rules.update(integer_digits=5, fraction_digits=3, decimals=3)
        self.history.write_text(json.dumps({"check_status": "ocr_only", "ocr_value": "10472.94?",
                                            "comparison_decimals": 2}))
        self.calibration = {"state": "testing", "background": True, "intensive": True, "followup": True,
                            "limit": 100, "tested": 4, "confirmations": 0, "required": 3, "seconds": 540,
                            "duration": 1200, "stage": "capture", "attempts": 12, "max_attempts": 260}
        Image.new("RGB", (400, 90), "gray").save(self.root / "current.jpg")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 390, "height": 844}, locale="de-DE")
            page.set_default_timeout(7000)
            page.goto(self.base + "/")
            note = page.locator("#hero-digit-note")
            page.wait_for_function("document.querySelector('#hero-digit-note').dataset.state === 'searching'")
            self.assertEqual("Die 8. Ziffer wird im Hintergrund gesucht. Noch höchstens 9 min.", note.inner_text())
            self.assertTrue(page.locator("#hero-search-progress").is_visible())
            self.assertEqual(660, page.locator("#hero-search-progress").evaluate("bar => bar.value"))
            self.assertIn("searching", page.locator("#meter-odometer .roller.fraction").last.get_attribute("class"))
            page.screenshot(path=os.environ.get("RF1_SHOT", "/tmp/searching.png"))
            browser.close()
