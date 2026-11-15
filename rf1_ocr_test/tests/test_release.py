"""Smoke and regression checks for OCR result logic and ingress page."""

import sys
import unittest
from pathlib import Path
from string import Formatter

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from PIL import Image  # noqa: E402
from checks import compare_sample, explain_uncertain_positions, read_with_retries  # noqa: E402
from i18n import english_progress, english_result, english_uncertain_positions, translate_page  # noqa: E402
from panel import PAGE  # noqa: E402
from run import draw_test_preview  # noqa: E402


def formatted_page(language="de"):
    template = translate_page(PAGE) if language == "en" else PAGE
    fields = {name for _, name, _, _ in Formatter().parse(template) if name is not None}
    return template.format(**{field: "" if field == "profile_script" else "0" for field in fields})


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.data = {"raw_value": "12345.120", "actual_value": "12345.120"}

    def test_full_cubic_meters_ignore_fractional_digits(self):
        status, message = compare_sample(self.data, "12345.???", 0)
        self.assertEqual("match", status)
        self.assertIn("vollen Kubikmeter", message)
        self.assertIn("Nachkommastellen wurden nicht berücksichtigt", message)

    def test_decimal_precision_is_strict(self):
        status, message = compare_sample(self.data, "12345.199", 1)
        self.assertEqual("match", status)
        self.assertIn("1. Nachkommastelle", message)
        self.assertEqual("difference", compare_sample(self.data, "12345.199", 2)[0])

    def test_ocr_stops_after_first_agreement(self):
        trace = []
        calls = []
        def read(profile):
            calls.append(profile)
            return "12345.???"
        value, confirmed, attempts = read_with_retries(
            read, self.data, 0, max_attempts=10, trace=trace)
        self.assertEqual(("12345.???", True, 1), (value, confirmed, attempts))
        self.assertEqual(["12345.???"], trace)
        self.assertEqual(1, len(calls))

    def test_uncertain_position_mentions_digit_not_fraction(self):
        msg = explain_uncertain_positions(
            ["12345.???", "12945.???", "12345.???"], 0)
        self.assertEqual("OCR unsicher. Vor dem Komma: 3.", msg)
        self.assertNotIn("Nach dem Komma", msg)
        msg_fraction = explain_uncertain_positions(
            ["12345.100", "12345.900"], 1)
        self.assertEqual("OCR unsicher. Nach dem Komma: 1.", msg_fraction)

    def test_uncertain_result_groups_multiple_positions(self):
        message = explain_uncertain_positions(["12345.143", "98746.243"], 1)
        self.assertEqual("OCR unsicher. Vor dem Komma: 1, 2, 3, 5. Nach dem Komma: 1.", message)

    def test_standalone_requires_repeatable_reading(self):
        data = {"reference_required": False}
        for readings, expected in (
            (["12345.???", "12345.???"], ("12345.???", True, 2)),
            (["12345.???", "12395.???"], ("123?5.???", False, 2)),
            (["12345.???"], ("12345.???", False, 1)),
        ):
            with self.subTest(readings=readings):
                values = iter(readings)
                self.assertEqual(expected, read_with_retries(
                    lambda _: next(values), data, 0, max_attempts=len(readings), standalone=True))

    def test_conflicting_reads_do_not_become_a_confirmed_match(self):
        values = iter(["12345.100", "12395.100", "12365.100"])
        trace = []
        value, confirmed, attempts = read_with_retries(
            lambda _: next(values),
            {"raw_value": "99999.000", "actual_value": "99999.000"},
            0, max_attempts=3, trace=trace)
        self.assertEqual(3, attempts)
        self.assertFalse(confirmed)
        self.assertEqual(3, len(trace))
        self.assertIn("?", value)


class PanelTests(unittest.TestCase):
    def test_panel_template_and_donation_footer(self):
        page = formatted_page()
        self.assertIn("Meter OCR", page)
        self.assertIn("FG4Q7VKQJ9BW8", page)
        self.assertIn("Manuellen Test öffnen", page)
        self.assertIn("Getesteten Ausschnitt für die Automatik übernehmen", page)
        self.assertIn('id="test-preview"', page)
        self.assertIn('id="ocr-details"', page)

    def test_english_page_translates_controls_and_remains_format_safe(self):
        page = formatted_page("en")
        self.assertIn("Meter OCR", page)
        self.assertIn("Automatic verification", page)
        self.assertIn("Open manual test", page)
        self.assertIn("Use tested crop for automatic checks", page)
        self.assertIn("More details", page)
        self.assertIn("Check in progress", page)
        self.assertIn('name="lang" value="0"', page)
        self.assertNotIn("Manuellen Test öffnen", page)

    def test_english_status_and_specific_digit_diagnostics(self):
        self.assertIn("attempt 2 of 5", english_progress("OCR-Versuch 2 von 5 läuft …"))
        self.assertIn("decimal place 2", english_result(
            "Bestätigt: Zählerstand und Referenzwert stimmen überein.",
            "match", 2))
        self.assertIn("Whole-number digits: 3", english_uncertain_positions(
            ["12345.???", "12945.???"], 0))
        self.assertNotIn("Decimal digits", english_uncertain_positions(
            ["12345.???", "12945.???"], 0))
        self.assertIn("ESP", english_result(
            "Der ESP meldet ein Problem mit der Zählerablesung. Bitte den Wert direkt am ESP prüfen.",
            "slfork_unclear", 0))

    def test_overlay_green_for_read_digit_red_for_unknown(self):
        source = Image.new("RGB", (500, 100), "white")
        preview = draw_test_preview(source, 400, [], [], "1234?.?21")
        self.assertEqual((36, 170, 92), preview.getpixel((1, 3)))
        self.assertEqual((203, 65, 77), preview.getpixel((321, 3)))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("--write-js", "--write-js-en"):
        page = formatted_page("en" if sys.argv[1] == "--write-js-en" else "de")
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]
        Path(sys.argv[2]).write_text(script, encoding="utf-8")
    else:
        unittest.main()
