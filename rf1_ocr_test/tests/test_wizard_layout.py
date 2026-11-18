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


if __name__ == "__main__":
    unittest.main()
