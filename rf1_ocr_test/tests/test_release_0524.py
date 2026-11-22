"""0.5.24: source cards in the setup wizard and the one-click meter camera."""

import os
import unittest

from test_ingress import IngressFixture

from source_settings import DISCOVERY_TEMPLATE, KIT_MODEL, discovered_sources

KIT_CAMERA = {"mode": "esphome", "camera": "camera.zaehlerkamera_a1b2c3_bild", "label": "Zählerkamera a1b2c3 Bild",
              "available": True, "kit": True}


class KitDiscoveryTest(unittest.TestCase):
    def test_meter_camera_is_marked_and_listed_first(self):
        sources = discovered_sources({
            "cameras": [{"camera": "camera.gaszaehler", "label": "Gaszähler"},
                        {"camera": "camera.zaehlerkamera_a1b2c3_bild", "label": "Zählerkamera a1b2c3 Bild", "kit": True},
                        {"camera": "camera.offline_kit", "label": "Zählerkamera alt", "kit": True, "available": False}],
            "devices": [{"url": "http://esp-meter", "label": "Gas meter"}]})
        self.assertEqual(["camera.zaehlerkamera_a1b2c3_bild", "http://esp-meter", "camera.gaszaehler", "camera.offline_kit"],
                         [source.get("camera") or source["url"] for source in sources])
        self.assertTrue(sources[0]["kit"])
        # Other cameras keep their old shape.
        self.assertNotIn("kit", sources[2])

    def test_only_a_real_true_marks_the_meter_camera(self):
        sources = discovered_sources({"cameras": [{"camera": "camera.a", "label": "A", "kit": "true"}]})
        self.assertNotIn("kit", sources[0])

    def test_template_recognises_the_firmware_model_and_survives_entities_without_device(self):
        self.assertEqual(KIT_MODEL, "zaehlerkamera")
        self.assertIn("{% set KIT_MODEL = 'zaehlerkamera' %}", DISCOVERY_TEMPLATE)
        self.assertIn("'kit': model == KIT_MODEL", DISCOVERY_TEMPLATE)
        # device_attr() raises for entities without a device: every call is guarded.
        self.assertEqual(DISCOVERY_TEMPLATE.count("if device else ''"), 2)


class KitWizardTest(IngressFixture):
    def page(self, playwright, width=1200, locale="de-DE"):
        browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
        page = browser.new_page(viewport={"width": width, "height": 900}, locale=locale)
        page.set_default_timeout(7000)
        return browser, page

    def test_cards_replace_the_select_and_open_the_meter_camera_panel(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser, page = self.page(playwright)
            page.goto(self.base + "/")
            cards = page.locator("#wizard-source-cards .source-card")
            self.assertEqual(4, cards.count())
            self.assertEqual("", page.locator("#wizard-source-mode").input_value())
            self.assertFalse(page.locator("#wizard-kit").is_visible())
            # Without a choice, "Weiter" points at the cards instead of the hidden select.
            page.locator("#setup-form .setup-step.active .setup-next").click()
            self.assertTrue(page.locator("#wizard-source-cards-hint").is_visible())
            self.assertIn("needs-choice", page.locator("#wizard-source-cards").get_attribute("class"))

            cards.filter(has_text="Zählerkamera bauen").click()
            self.assertEqual("esphome", page.locator("#wizard-source-mode").input_value())
            self.assertEqual("true", cards.nth(0).get_attribute("aria-checked"))
            self.assertEqual("false", cards.nth(1).get_attribute("aria-checked"))
            self.assertFalse(page.locator("#wizard-source-cards-hint").is_visible())
            self.assertTrue(page.locator("#wizard-kit").is_visible())
            self.assertFalse(page.locator("#wizard-stream-hint").is_visible())
            install = page.locator("#wizard-kit-install")
            self.assertEqual("https://eifellayer.github.io/meter-ocr/?board=auto&lang=de", install.get_attribute("href"))
            self.assertEqual("_blank", install.get_attribute("target"))
            page.locator(".kit-board", has_text="XIAO ESP32S3 Sense").click()
            self.assertIn("board=xiao-esp32s3-sense", install.get_attribute("href"))
            page.locator("#wizard-kit").screenshot(path="/tmp/kit-panel-1200.png")
            page.locator(".source-mode-guide").screenshot(path="/tmp/source-cards-1200.png")

            cards.filter(has_text="Kamera aus Home Assistant").click()
            self.assertEqual("esphome", page.locator("#wizard-source-mode").input_value())
            self.assertFalse(page.locator("#wizard-kit").is_visible())
            self.assertTrue(page.locator("#wizard-stream-hint").is_visible())
            self.assertEqual("/config/integrations/dashboard/add?domain=generic",
                             page.locator("#wizard-stream-hint a").get_attribute("href"))

            cards.filter(has_text="AI on the Edge").click()
            self.assertEqual("slfork", page.locator("#wizard-source-mode").input_value())
            self.assertTrue(page.locator("#wizard-source-url").is_visible())
            self.assertFalse(page.locator("#wizard-stream-hint").is_visible())
            # The kit board choices are not part of the setup form.
            self.assertEqual(0, page.evaluate("[...document.querySelector('#setup-form').elements]"
                                              ".filter(field => field.name === 'kit_board').length"))
            browser.close()

    def test_the_new_meter_camera_is_picked_up_by_itself(self):
        from playwright.sync_api import sync_playwright

        self.suggestions = [{"mode": "esphome", "camera": "camera.water_meter", "label": "Water meter"}]
        with sync_playwright() as playwright:
            browser, page = self.page(playwright, width=390)
            page.clock.install()
            page.goto(self.base + "/")
            page.locator("#wizard-source-cards .source-card").first.click()
            status = page.locator("#wizard-kit-status")
            self.assertNotEqual("found", status.get_attribute("data-state"))
            # The camera arrives in Home Assistant while the wizard waits.
            self.suggestions = [KIT_CAMERA, {"mode": "esphome", "camera": "camera.water_meter", "label": "Water meter"}]
            page.clock.run_for(11000)
            page.wait_for_function("document.querySelector('#wizard-kit-status').dataset.state === 'found'")
            self.assertIn("Zählerkamera gefunden: Zählerkamera a1b2c3 Bild", status.text_content())
            self.assertEqual(KIT_CAMERA["camera"], page.locator('#setup-form [name="camera"]').input_value())
            self.assertIn("Zählerkamera · Zählerkamera a1b2c3 Bild",
                          page.locator("#wizard-discovered-source option:checked").text_content())
            page.locator("#wizard-kit").screenshot(path="/tmp/kit-panel-390.png")
            overflow = page.evaluate("document.querySelector('#setup-dialog').scrollWidth - "
                                     "document.querySelector('#setup-dialog').clientWidth")
            self.assertLessEqual(overflow, 0)
            browser.close()

    def test_english_page_translates_the_cards(self):
        page = self.request("/", accept="en")[0]
        for text in ("Build a meter camera", "Camera from Home Assistant", "Camera with reference reading",
                     "Meter camera in one click", "Install firmware", "Detect automatically",
                     "Add it to Home Assistant as a camera"):
            self.assertIn(text, page)
        for german in ("Zählerkamera bauen", "Kamera aus Home Assistant", "Firmware installieren",
                       "Welches Board hast du?"):
            self.assertNotIn(german, page)
        self.assertIn("?board=auto&amp;lang=en", page)


if __name__ == "__main__":
    unittest.main()
