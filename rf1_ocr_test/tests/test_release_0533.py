"""0.5.33: the automatic check and the demo show their steps like the setup; the current test image."""

import json
import os
from pathlib import Path
import sys
import time
import unittest
from io import BytesIO

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import background_live  # noqa: E402
import demo  # noqa: E402
import run  # noqa: E402
from test_ingress import IngressFixture  # noqa: E402


class RecoveryWhileCheckingTests(unittest.TestCase):
    def test_the_result_of_the_previous_check_is_not_shown_while_a_check_runs(self):
        record = {"recovery": {"tried": True, "plan": {"done": 4, "total": 10}, "result": "timeout"},
                  "ocr": "10511.0??", "image": None, "at": 3.0}
        running = background_live.recovery(record, True)
        self.assertEqual("waiting", running["state"])
        self.assertEqual("wird nach dieser Prüfung ausgewertet", running["step"])
        self.assertEqual("", running["result"])
        finished = background_live.recovery(record, False)
        self.assertEqual("Zeitbudget aufgebraucht", finished["result"])


class PhaseTests(unittest.TestCase):
    def test_the_activity_names_the_step_of_the_check(self):
        self.assertEqual("capture", run.activity_phase("working", "Kamerabild wird angefordert …"))
        self.assertEqual("read", run.activity_phase("working", "Zählerbild wird gelesen · Versuch 2 von 5"))
        self.assertEqual("recheck", run.activity_phase("working", run.SINGLE_DIGIT_RECHECK))
        self.assertEqual("recheck", run.activity_phase("working", "Nachprüfung: Dieselben Ziffern waren wiederholt unklar."))
        self.assertIsNone(run.activity_phase("waiting", "Wartet auf die nächste automatische Prüfung."))


class DemoPictureTests(unittest.TestCase):
    def test_the_demo_uses_the_picture_of_the_automatic_check(self):
        calls = []

        def draw(register, width, whole, fraction, reading, *args, **options):
            calls.append((reading, options.get("readings")))
            return register.copy()

        demo._complete.clear()
        result = demo.run_demo(False, draw=draw)
        self.assertTrue(result["styled"])
        self.assertEqual(result["reading"], calls[0][0])
        self.assertEqual(2, len(calls[0][1]))


def jpeg(size):
    with BytesIO() as stream:
        Image.new("RGB", size, "gray").save(stream, "JPEG")
        return stream.getvalue()


class CheckStepsTest(IngressFixture):
    def test_the_check_shows_its_steps_beside_the_current_test_image(self):
        from playwright.sync_api import sync_playwright

        self.setup_pending = False
        now = time.time()
        self.history.write_text(json.dumps({
            "check_status": "ocr_unclear", "ocr_value": "1051?.42", "last_epoch": now - 120,
            "last_check_at": now - 100, "next_check_at": now + 600, "ocr_readings": ["1051?.42", "1051?.4?"],
        }))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1280, "height": 1000}, locale="de-DE",
                                    reduced_motion="reduce")
            page.set_default_timeout(7000)
            page.goto(self.base)
            box = page.locator("#check-timeline-box")
            box.wait_for(state="visible")
            self.assertEqual("So läuft die Prüfung", box.locator("h3").inner_text())
            failed = box.locator('li[data-step="read"]')
            self.assertEqual("failed", failed.get_attribute("data-state"))
            self.assertIn("1051?,42", failed.inner_text())
            self.assertEqual("done", box.locator('li[data-step="image"]').get_attribute("data-state"))
            self.assertEqual("todo", box.locator('li[data-step="save"]').get_attribute("data-state"))
            self.assertIn("Nächste Prüfung:", box.locator(".setup-timeline-stats").inner_text())
            self.assertEqual("Aktuelles Testbild", page.locator("#preview-heading").inner_text())

            # A check runs: the step that runs now is current, with its attempt.
            self.activity = {"state": "working", "detail": "Zählerbild wird gelesen · Versuch 2 von 5",
                             "completed": 1, "total": 5, "reading": "10517.6?", "phase": "read"}
            current = box.locator('li[data-state="current"]')
            # The page asks every 15 s while waiting and every 2 s during a check.
            current.filter(has_text="Ziffern lesen").wait_for(timeout=20000)
            self.assertIn("Versuch 2 von 5", current.inner_text())
            self.assertEqual("done", box.locator('li[data-step="image"]').get_attribute("data-state"))
            # Its own cut-out is shown at once, labelled as the picture of this check, not dimmed.
            Image.new("RGB", (200, 45), "white").save(self.automatic_preview, "JPEG")
            page.locator("#preview-time").filter(has_text="Bild dieser Prüfung").wait_for()
            self.assertFalse(page.locator("#test-preview-image").evaluate(
                "image => image.classList.contains('preview-outdated')"))

            # Finished and confirmed: every step ticked, the reading taken over.
            self.history.write_text(json.dumps({
                "check_status": "ocr_only", "ocr_value": "10517.63", "last_epoch": time.time() - 5,
                "last_check_at": time.time(), "next_check_at": time.time() + 600,
            }))
            self.activity = {"state": "waiting", "detail": "Wartet auf die nächste automatische Prüfung."}
            box.locator('li[data-step="save"][data-state="done"]').filter(has_text="10517,63 m³").wait_for(
                timeout=20000)
            self.assertEqual("optional", box.locator('li[data-step="recheck"]').get_attribute("data-state"))
            page.screenshot(path="/tmp/check-steps-0533.png", full_page=True)
            browser.close()


class DemoStepsTest(IngressFixture):
    def test_the_demo_shows_its_steps_beside_the_pictures(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1280, "height": 1000}, locale="de-DE",
                                    reduced_motion="reduce")
            page.set_default_timeout(22000)
            page.goto(self.base)
            page.locator("#open-demo-setup").click()
            demo = page.locator("#demo-dialog")
            steps = demo.locator("#demo-timeline-box")
            steps.locator('li[data-step="result"]').filter(has_text="12344,942 m³").wait_for()
            self.assertEqual(["done"] * 4, steps.locator("li").evaluate_all("rows => rows.map(row => row.dataset.state)"))
            self.assertIn("Drehung −5°", steps.locator('li[data-step="align"]').inner_text())
            self.assertIn("2 Leseversuche", steps.locator('li[data-step="read"]').inner_text())
            self.assertTrue(demo.get_by_text("Grau:", exact=True).is_visible())
            page.screenshot(path="/tmp/demo-steps-0533.png")
            browser.close()


if __name__ == "__main__":
    unittest.main()
