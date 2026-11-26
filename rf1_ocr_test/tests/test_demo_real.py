"""The demo on real, masked camera pictures (0.5.0)."""

from pathlib import Path
import shutil
import unittest

from PIL import Image

import demo

ROOT = Path(__file__).parents[1]


class RealDemoTests(unittest.TestCase):
    def setUp(self):
        demo._real_complete.clear()
        self.addCleanup(demo._real_complete.clear)

    def select(self, frame, overlay, box, width, rotation, whole, fraction, *, digit_boxes):
        self.assertEqual((800, 600), frame.size)
        self.assertEqual((demo.REAL_LAYOUT["box"], -11, 8), (box, rotation, len(digit_boxes)))
        boxes = [(i * 10, 0, i * 10 + 8, 20) for i in range(8)]
        return Image.new("RGB", (80, 20)), width, boxes[:5], boxes[5:], "manual"

    def test_preview_shows_the_picture_without_reading_it(self):
        for picture, angle in (("2", demo.REAL_LAYOUT["rotation"]), ("", -demo.DEMO_ANGLE)):
            shown = demo.demo_preview(picture)
            self.assertEqual((True, angle), (shown["preview"], shown["angle"]))
            self.assertNotIn("reading", shown)
            import base64, io
            with Image.open(io.BytesIO(base64.b64decode(shown["image"]))) as image:
                self.assertEqual("JPEG", image.format)
        with self.assertRaises(ValueError):
            demo.demo_preview("9")

    def test_two_profiles_must_agree_and_only_complete_results_are_kept(self):
        answers = iter(["10501.05", "10501.0?", "10501.05", "10501.05"])
        calls = []

        def read(register, width, whole, fraction, light, polarity, **options):
            calls.append(options)
            return next(answers)

        first = demo.run_real_demo(1, self.select, read)
        self.assertEqual(("10501.0?", False, True), (first["reading"], first["complete"], first["real"]))
        second = demo.run_real_demo(1, self.select, read)
        self.assertEqual(("10501.05", True), (second["reading"], second["complete"]))
        self.assertIs(second, demo.run_real_demo(1, self.select, read))
        self.assertEqual({2}, {options["fraction_digits"] for options in calls})
        self.assertTrue(all(options["prefer_boxes"] for options in calls))

    def test_unknown_pictures_are_refused(self):
        for number in (0, 5, "1", True):
            with self.assertRaises(ValueError):
                demo.run_real_demo(number, self.select, lambda *a, **k: "1")

    def test_pictures_ship_with_the_app_and_show_only_the_register(self):
        files = sorted(demo.REAL_IMAGES.glob("gas-*.png"))
        self.assertEqual(demo.REAL_COUNT, len(files))
        for path in files:
            with Image.open(path) as picture:
                self.assertEqual((570, 260), picture.size)  # the cut-out strip, never a whole camera frame
            self.assertEqual((ROOT / "tests" / "fixtures" / "setup_strips" / path.name).read_bytes(), path.read_bytes())
        self.assertIn("COPY demo_images /demo_images", (ROOT / "Dockerfile").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("tesseract"), "needs the OCR engine")
    def test_a_real_picture_is_read_by_the_apps_own_reader(self):
        import run
        # Generous time: the build machine is several times slower than a desk computer.
        answer = demo.run_real_demo(1, run.select_register, run.read_visible_digits, seconds=600)
        self.assertEqual("10501.05", answer["reading"])


if __name__ == "__main__":
    unittest.main()
