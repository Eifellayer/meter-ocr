"""0.5.28: the setup view uses its width – steps on the left, the tested picture on the right."""

import os
from io import BytesIO

from PIL import Image

from test_ingress import IngressFixture


def jpeg(size):
    with BytesIO() as stream:
        Image.new("RGB", size, "gray").save(stream, "JPEG")
        return stream.getvalue()


class SetupLayoutTest(IngressFixture):
    def running_setup(self):
        self.setup_pending = False
        self.source_selected = True
        self.control_calibration("setup", 20)
        self.calibration_images["frame", "15"] = jpeg((800, 600))
        self.calibration_images["crop", "15"] = jpeg((400, 80))
        self.calibration.update(
            state="testing", stage="ocr", tested=3, attempts=7, variant=3, rotation=-3, confirmations=0, seconds=45,
            preview={"frame": 15, "crop": 15, "region": [0.3, 0.2, 0.4, 0.15], "angle": -3, "reading": "1051?.6?"},
            candidates=[{"number": 1, "percent": 62, "reading": "1051?.6?", "rotation": -3, "box": [1, 2, 3, 4],
                         "selected": True}])

    def test_wide_screen_puts_the_picture_beside_the_steps(self):
        from playwright.sync_api import sync_playwright

        self.running_setup()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1280, "height": 1000}, locale="de-DE", reduced_motion="reduce")
            page.set_default_timeout(7000)
            page.goto(self.base + "/?ui=overview")
            overview = page.locator("#calibration-overview")
            timeline = overview.locator(".setup-timeline-box")
            photo = overview.locator(".calibration-photo-panel")
            timeline.wait_for(state="visible")
            photo.locator('img[data-image="frame"]').wait_for(state="visible")
            steps, picture = timeline.bounding_box(), photo.bounding_box()
            # Side by side: the picture starts right of the steps, at about the same height.
            self.assertGreater(picture["x"], steps["x"] + steps["width"] - 1)
            self.assertLess(abs(picture["y"] - steps["y"]), 60)
            # The progress bar sits on top, the folded frame list below everything else.
            progress = page.locator("#calibration-overview-progress").bounding_box()
            self.assertLess(progress["y"], steps["y"])
            candidates = overview.locator(".calibration-candidate-panel")
            candidates.wait_for(state="visible")
            self.assertFalse(candidates.evaluate("node => node.open"))
            self.assertGreater(candidates.bounding_box()["y"], max(steps["y"] + steps["height"],
                                                                    picture["y"] + picture["height"]) - 1)
            # The pictures so far join the right column once there are some.
            self.calibration.update(rounds=[{"image": 1, "reason": "unclear", "reading": "1051?.6?", "seconds": 40.0,
                                             "confirmations": 0}])
            rounds = overview.locator(".setup-rounds-box")
            rounds.wait_for(state="visible")
            self.assertGreater(rounds.bounding_box()["x"], steps["x"] + steps["width"] - 1)
            overview.screenshot(path="/tmp/setup-layout-1280.png")
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            self.assertLessEqual(overflow, 0)
            browser.close()

    def test_small_screen_stacks_and_a_lone_side_takes_the_full_width(self):
        from playwright.sync_api import sync_playwright

        self.running_setup()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 390, "height": 900}, locale="de-DE", reduced_motion="reduce")
            page.set_default_timeout(7000)
            page.goto(self.base + "/?ui=overview")
            overview = page.locator("#calibration-overview")
            timeline = overview.locator(".setup-timeline-box")
            photo = overview.locator(".calibration-photo-panel")
            timeline.wait_for(state="visible")
            photo.wait_for(state="visible")
            self.assertGreater(photo.bounding_box()["y"], timeline.bounding_box()["y"])
            overview.screenshot(path="/tmp/setup-layout-390.png")
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            self.assertLessEqual(overflow, 0)
            page.close()
            # A repair run shows no step list: the picture then uses the whole width.
            self.calibration.update(automatic=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="de-DE", reduced_motion="reduce")
            page.set_default_timeout(7000)
            page.goto(self.base + "/?ui=overview")
            photo = page.locator("#calibration-overview .calibration-photo-panel")
            photo.wait_for(state="visible")
            self.assertFalse(page.locator("#calibration-overview .setup-timeline-box").is_visible())
            layout = page.locator("#calibration-overview .calibration-layout").bounding_box()
            self.assertGreater(photo.bounding_box()["width"], layout["width"] * 0.9)
            browser.close()
