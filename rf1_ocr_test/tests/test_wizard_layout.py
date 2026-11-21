import os
import unittest

from test_ingress import IngressFixture


class WizardLayoutTest(IngressFixture):
    def test_wizard_has_stepper_and_does_not_jump(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            for width in (390, 1200):
                page = browser.new_page(viewport={"width": width, "height": 844}, locale="de-DE")
                page.set_default_timeout(7000)
                page.goto(self.base + "/")
                dialog = page.locator("#setup-dialog")
                dialog.wait_for(state="visible")
                stepper = page.locator("#setup-stepper li")
                self.assertEqual(4, stepper.count())
                self.assertEqual("current", stepper.nth(0).get_attribute("data-state"))
                before = dialog.bounding_box()
                field = page.locator('#setup-form input[name="fallback_value"]').bounding_box()
                page.locator("#setup-form .setup-step.active details summary").first.click()
                self.assertEqual(before["width"], dialog.bounding_box()["width"])
                self.assertEqual(before["height"], dialog.bounding_box()["height"])
                self.assertEqual(field["x"], page.locator('#setup-form input[name="fallback_value"]').bounding_box()["x"])
                page.screenshot(path=f"/tmp/wizard-{width}-0.png")
                page.locator("#wizard-source-mode").select_option("esphome")
                page.locator('#setup-form [name="camera"]').fill("camera.gasmeter")
                page.locator("#setup-form .setup-step.active .setup-next").click()
                self.assertEqual("done", stepper.nth(0).get_attribute("data-state"))
                self.assertEqual("current", stepper.nth(1).get_attribute("data-state"))
                self.assertEqual(before["width"], dialog.bounding_box()["width"])
                page.screenshot(path=f"/tmp/wizard-{width}-1.png")
                overflow = page.evaluate("document.querySelector('#setup-dialog').scrollWidth - document.querySelector('#setup-dialog').clientWidth")
                self.assertLessEqual(overflow, 0)
                page.close()
            browser.close()


class ReleaseUi040Test(IngressFixture):
    """0.4.0 interface: settings grid, collapsible sections, last attempts, candidate details."""

    def setUp(self):
        super().setUp()
        self.setup_pending = False
        self.source_selected = True
        self.rules.update(fraction_digits=3, integer_digits=5, interval_minutes=10, max_flow_lph=6000,
                          digit_boxes=[], rotation=0)

    def browser(self, playwright):
        return playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))

    def new_page(self, browser, width, locale="de-DE"):
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1, locale=locale)
        page.set_default_timeout(7000)
        return page

    def test_automatic_settings_use_an_even_grid_with_help_below_each_field(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = self.browser(playwright)
            for width in (390, 1200):
                page = self.new_page(browser, width)
                page.goto(self.base + "/?ui=settings")
                page.locator("#automatic-settings > summary").click()
                fields = {name: page.locator(f'#auto-form [name="{name}"]').bounding_box()
                          for name in ("decimals", "attempts", "interval_minutes", "failure_pause_minutes",
                                       "intensive_agreement", "max_flow", "polarity", "crop_mode")}
                pairs = (("decimals", "attempts"), ("interval_minutes", "failure_pause_minutes"),
                         ("intensive_agreement", "max_flow"), ("polarity", "crop_mode"))
                for left, right in pairs:
                    if width == 1200:
                        # Two columns: the controls of one row start at the same height.
                        self.assertEqual(round(fields[left]["y"]), round(fields[right]["y"]), (left, right))
                        self.assertLess(fields[left]["x"], fields[right]["x"])
                    else:
                        self.assertEqual(round(fields[left]["x"]), round(fields[right]["x"]))
                        self.assertLess(fields[left]["y"], fields[right]["y"])
                # Every help text sits directly below its own control.
                for name in ("interval_minutes", "failure_pause_minutes", "intensive_agreement", "max_flow"):
                    control = page.locator(f'#auto-form [name="{name}"]')
                    help_text = page.locator(f'#auto-form .settings-field:has([name="{name}"]) .field-help')
                    if help_text.is_visible():
                        self.assertGreaterEqual(help_text.bounding_box()["y"], control.bounding_box()["y"]
                                                + control.bounding_box()["height"] - 1)
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                self.assertLessEqual(overflow, 0)
                page.screenshot(path=f"/tmp/settings-040-{width}.png", full_page=True)
                page.close()

    def test_collapsible_sections_show_a_rotating_chevron_and_a_large_target(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            page = self.new_page(self.browser(playwright), 390)
            page.goto(self.base + "/?ui=settings")
            page.locator("#automatic-settings > summary").click()
            summary = page.locator("#experiments-settings > summary")
            chevron = "getComputedStyle(document.querySelector('#experiments-settings > summary'), '::before')"
            closed = page.evaluate(chevron + ".transform")
            self.assertNotEqual("none", page.evaluate(chevron + ".content"))
            self.assertGreaterEqual(summary.bounding_box()["height"], 36)
            summary.click()
            page.wait_for_timeout(300)
            self.assertTrue(page.evaluate("document.querySelector('#experiments-settings').open"))
            self.assertNotEqual(closed, page.evaluate(chevron + ".transform"))
            self.assertEqual("true", page.locator("#tab-settings").get_attribute("aria-selected"))
            self.assertEqual("false", page.locator("#tab-overview").get_attribute("aria-selected"))

    def test_wizard_offers_the_experiments_and_keeps_settings_in_step(self):
        from playwright.sync_api import sync_playwright

        self.rules.update(experiments_enabled=False, experiments={"perspective": False})
        with sync_playwright() as playwright:
            browser = self.browser(playwright)
            for width in (390, 1200):
                page = self.new_page(browser, width)
                page.goto(self.base + "/?ui=settings")
                page.locator("#open-setup").click()
                page.evaluate("""() => {
                  for (const step of document.querySelectorAll('#setup-form .setup-step')) step.classList.remove('active');
                  document.querySelector('#setup-form .setup-step[data-step="3"]').classList.add('active');
                }""")
                box = page.locator("#wizard-experiments")
                self.assertEqual("Experimentelle Funktionen (Schattenbetrieb)", box.locator("summary").inner_text().strip())
                box.locator("summary").click()
                box.locator('[name="experiments_enabled"]').check()
                box.locator('[name="experiment_perspective"]').select_option("1")
                self.assertTrue(page.locator('#auto-form [name="experiments_enabled"]').is_checked())
                self.assertEqual("1", page.locator('#auto-form [name="experiment_perspective"]').input_value())
                overflow = page.evaluate("document.querySelector('#setup-dialog').scrollWidth"
                                         " - document.querySelector('#setup-dialog').clientWidth")
                self.assertLessEqual(overflow, 0)
                page.close()

    def test_last_reading_attempts_stay_open_after_the_check(self):
        from playwright.sync_api import sync_playwright

        self.activity = {"state": "working", "detail": "Zählerbild wird gelesen · Versuch 3 von 3", "completed": 3,
                         "total": 3, "reading": "12345.678", "readings": ["12345.678", "12345.679", "12345.6?8"]}
        with sync_playwright() as playwright:
            page = self.new_page(self.browser(playwright), 390)
            page.goto(self.base + "/?ui=overview")
            page.locator("#automatic-digit-grid tbody tr").first.wait_for()
            self.assertTrue(page.locator("#automatic-last-readings").is_hidden())
            self.activity = {"state": "waiting", "detail": "Wartet auf die nächste automatische Prüfung."}
            last = page.locator("#automatic-last-readings")
            last.wait_for(state="visible")
            self.assertEqual("Die letzten Leseversuche", last.locator("summary").inner_text().strip())
            self.assertTrue(page.evaluate("document.querySelector('#automatic-last-readings').open"))
            self.assertTrue(page.locator("#automatic-activity-details").is_hidden())
            # Three attempts plus the result row.
            self.assertEqual(4, page.locator("#automatic-last-digit-grid tbody tr").count())
            page.screenshot(path="/tmp/last-readings-390.png", full_page=True)
            last.locator("summary").click()
            page.wait_for_timeout(200)
            page.reload()
            last.wait_for(state="visible")
            page.wait_for_timeout(300)
            self.assertFalse(page.evaluate("document.querySelector('#automatic-last-readings').open"))
            # The next check replaces the list.
            self.activity = {"state": "working", "detail": "Automatische Prüfung startet …"}
            page.reload()
            page.locator("#automatic-progress").wait_for(state="visible")
            self.assertTrue(last.is_hidden())
            self.activity = {"state": "waiting", "detail": "Wartet auf die nächste automatische Prüfung."}
            page.wait_for_timeout(2500)
            self.assertTrue(last.is_hidden())

        english = self.request("/", accept="en")[0]
        self.assertIn(">Latest reading attempts<", english)

    def calibration_status(self, **extra):
        return {"state": "testing", "stage": "shortlist", "tested": 4, "confirmations": 1, "required": 3,
                "limit": 24, "seconds": 600, "duration": 900, "attempts": 12, "max_attempts": 100,
                "variant": 1, "rotation": 2, **extra}

    def test_candidate_list_shows_hits_merged_frames_hints_and_rejections(self):
        from playwright.sync_api import sync_playwright

        self.calibration = self.calibration_status(
            candidates=[
                {"number": 1, "rotation": 2, "percent": 92, "reading": "12345.67", "selected": True,
                 "hits": 3, "merged": 4, "role": "confirm"},
                {"number": 2, "rotation": -1, "percent": 64, "reading": "12345.6", "hits": 1, "role": "hint"},
            ],
            rejected=[{"reason": "small_label", "box": [10, 10, 60, 30], "rotation": 0},
                      {"reason": "quarter_turn", "box": [100, 20, 140, 220], "rotation": 90},
                      {"reason": "aspect", "box": [5, 5, 300, 290], "rotation": 0}])
        with sync_playwright() as playwright:
            browser = self.browser(playwright)
            for locale, texts in (("de-DE", ("3 Treffer", "4 ähnliche Rahmen zusammengefasst", "nur Suchhilfe",
                                             "Verworfen (3)", "Typenschild", "um 90° gedreht", "Seitenverhältnis")),
                                  ("en-US", ("3 hits", "4 similar frames merged", "search aid only",
                                             "Rejected (3)", "type plate", "turned by 90°", "aspect ratio"))):
                for width in (390, 1200):
                    page = self.new_page(browser, width, locale)
                    page.goto(self.base + "/?ui=overview")
                    panel_box = page.locator("#calibration-overview .calibration-candidate-panel")
                    panel_box.locator("li").first.wait_for()
                    rejected = panel_box.locator(".calibration-rejected")
                    self.assertFalse(page.evaluate(
                        "document.querySelector('#calibration-overview .calibration-rejected').open"))
                    rejected.locator("summary").click()
                    text = panel_box.inner_text()
                    for expected in texts:
                        self.assertIn(expected, text)
                    self.assertEqual("hint", panel_box.locator("li").nth(1).get_attribute("data-role"))
                    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                    self.assertLessEqual(overflow, 0)
                    page.close()
            # Older status data without the new fields shows nothing extra.
            self.calibration = self.calibration_status(
                candidates=[{"number": 1, "rotation": 2, "percent": 92, "reading": "12345.67", "selected": True}])
            page = self.new_page(browser, 390)
            page.goto(self.base + "/?ui=overview")
            panel_box = page.locator("#calibration-overview .calibration-candidate-panel")
            panel_box.locator("li").first.wait_for()
            text = panel_box.inner_text()
            for absent in ("Treffer", "zusammengefasst", "Suchhilfe", "Verworfen"):
                self.assertNotIn(absent, text)


if __name__ == "__main__":
    unittest.main()
