import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calibration import IMAGE_WAIT_LIMIT

ROOT = Path(__file__).resolve().parents[1]
RUN = (ROOT / "run.py").read_text(encoding="utf-8")


class BackgroundStatusTest(unittest.TestCase):
    def test_background_search_is_not_reported_as_image_timeout(self):
        # Routine checks come about every 11 minutes, longer than the image wait limit.
        self.assertLess(IMAGE_WAIT_LIMIT, 11 * 60)
        start = RUN.index("    def calibration_status():")
        body = RUN[start:RUN.index("    def calibration_image(", start)]
        self.assertIn('status["state"] == "waiting" and not calibration.background', body)


if __name__ == "__main__":
    unittest.main()
