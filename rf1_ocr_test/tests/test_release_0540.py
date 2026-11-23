"""0.5.40: the reading attempts of a check show which digits counted and which were rejected."""

import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import panel  # noqa: E402
from test_ingress import IngressFixture  # noqa: E402


class AttemptColoursTest(IngressFixture):
    def test_counted_and_rejected_digits_and_the_result_like_the_counter(self):
        from playwright.sync_api import sync_playwright

        self.setup_pending = False
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("RF1_CHROMIUM"))
            page = browser.new_page(viewport={"width": 1280, "height": 1000}, locale="de-DE",
                                    reduced_motion="reduce")
            page.set_default_timeout(7000)
            page.goto(self.base)
            # The grid of the last attempts, as the page fills it after a check.
            page.evaluate("""() => renderDigitGrid(document.querySelector('#automatic-last-digit-grid'),
                ['10517.84?', '10517.85?', '10517.84?', '10517.8??'], 2)""")
            grid = page.locator("#automatic-last-digit-grid table")
            votes = grid.locator("tbody tr:not(.digit-result)").evaluate_all(
                "rows => rows.map(row => [...row.querySelectorAll('td')].map(cell => cell.dataset.vote))")
            self.assertEqual(["used"] * 7 + ["unread"], votes[0])
            self.assertEqual(["used"] * 6 + ["rejected", "unread"], votes[1])
            rejected = grid.locator('td[data-vote="rejected"]')
            self.assertEqual(("5", "verworfen"), (rejected.inner_text(), rejected.get_attribute("title")))
            result = grid.locator("tr.digit-result td")
            self.assertEqual(["1", "0", "5", "1", "7", "8", "4", "?"],
                             result.evaluate_all("cells => cells.map(cell => cell.querySelector('.roller').textContent)"))
            self.assertEqual(["whole"] * 5 + ["fraction"] * 3, result.evaluate_all("cells => cells.map(cell => cell.dataset.part)"))
            self.assertEqual("warn", result.nth(6).get_attribute("data-tone"))
            self.assertIn("verworfen", page.locator("#automatic-last-digit-grid .digit-grid-legend").inner_text())
            browser.close()


class TextTests(unittest.TestCase):
    def test_legend_in_both_grids(self):
        self.assertEqual(2, panel.PAGE.count('class="legend digit-grid-legend"'))


if __name__ == "__main__":
    unittest.main()
