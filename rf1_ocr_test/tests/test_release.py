"""Smoke and regression checks for OCR result logic and ingress page."""

import sys
import unittest
from pathlib import Path
from string import Formatter
import yaml

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from PIL import Image  # noqa: E402
from checks import (compare_sample, common_exact_precision, explain_uncertain_positions,
                    manual_confirms_failed_auto, read_with_retries, schedule_next_check,
                    MAX_OCR_ATTEMPTS)  # noqa: E402
from i18n import english_progress, english_result, english_uncertain_positions, translate_page  # noqa: E402
from panel import PAGE  # noqa: E402
from run import draw_test_preview  # noqa: E402
import checks as _checks_for_timing
_checks_for_timing.system_idle = lambda: False  # deterministic retry timing in tests


def formatted_page(language="de"):
    template = translate_page(PAGE) if language == "en" else PAGE
    fields = {name for _, name, _, _ in Formatter().parse(template) if name is not None}
    values = dict.fromkeys(fields, "0")
    values.update(profile_script="", app_name="AI Meter Reader")
    return template.format(**values)


class AppIdentityTests(unittest.TestCase):
    def test_release_metadata_preserves_stable_app_identity(self):
        config = yaml.safe_load((APP / "config.yaml").read_text(encoding="utf-8"))
        repository = yaml.safe_load((APP.parent / "repository.yaml").read_text(encoding="utf-8"))
        self.assertEqual("0.5.41", config["version"])
        self.assertEqual("rf1_ocr_test", config["slug"])
        self.assertEqual("AI Meter Reader", config["name"])
        self.assertNotIn("stage", config)
        # 0.5.18: only the time zone is a visible option; the legacy fields stay optional in the schema.
        self.assertEqual({"zeitzone"}, set(config["options"]))
        self.assertIn("esp_url", config["schema"])
        self.assertTrue(all(str(kind).endswith("?") for key, kind in config["schema"].items() if key != "zeitzone"))
        for language in ("de", "en"):
            names = yaml.safe_load((APP / "translations" / f"{language}.yaml").read_text(encoding="utf-8"))
            self.assertEqual(set(config["schema"]), set(names["configuration"]))
        self.assertEqual("https://github.com/Eifellayer/meter-ocr", repository["url"])

    def test_app_keeps_existing_home_assistant_entities_and_media_path(self):
        import run
        self.assertEqual("sensor.rf1_kontrollbild", run.ENTITY)
        self.assertEqual("sensor.rf1_pruefstatus", run.CHECK_ENTITY)
        self.assertEqual("sensor.rf1_ocr_zaehlerstand", run.OCR_ENTITY)
        self.assertEqual("sensor.rf1_verbrauch_gesamt", run.CONSUMPTION_ENTITY)
        self.assertEqual("/media/rf1", str(run.DESTINATION.parent))

    def test_camera_requests_disable_caching_for_fresh_retry_images(self):
        from io import BytesIO
        from unittest.mock import patch
        import run
        with patch.object(run, "open_core", return_value=BytesIO(b"image")) as fetch:
            self.assertEqual(b"image", run.get_bytes("http://supervisor/core/api/camera_proxy/camera.meter", "token"))
        request = fetch.call_args.args[0]
        self.assertEqual("no-cache, no-store", request.get_header("Cache-control"))
        self.assertEqual("no-cache", request.get_header("Pragma"))


class VersionFooterTests(unittest.TestCase):
    def test_every_page_shows_the_installed_version_in_the_footer(self):
        for language in ("de", "en"):
            page = formatted_page(language)
            self.assertIn('class="app-version"', page)
            self.assertIn("CHANGELOG.md", page)


class DocumentationTests(unittest.TestCase):
    def test_readmes_are_short_and_link_to_the_guide(self):
        for quickstart, title in (("README.md", "Schnellstart"), ("README.en.md", "Quick start")):
            with self.subTest(quickstart=quickstart):
                page = (APP.parent / quickstart).read_text(encoding="utf-8")
                self.assertLess(len(page), 4000)
                self.assertIn(title, page)
                self.assertIn("](rf1_ocr_test/DOCS.md)", page)
                self.assertIn("Version 0.5.41", page)
                self.assertIn("supervisor_add_addon_repository", page)
                self.assertIn("repository_url=https%3A%2F%2Fgithub.com%2FEifellayer%2Fmeter-ocr", page)
                self.assertIn("](docs/HISTORY.md)", page)

    def test_documentation_describes_real_check_intervals_and_current_version(self):
        de = (APP.parent / "README.md").read_text(encoding="utf-8")
        en = (APP.parent / "README.en.md").read_text(encoding="utf-8")
        app_docs = (APP / "DOCS.md").read_text(encoding="utf-8")
        for text in ("10 Minuten", "5 Minuten", "Standard 30 Minuten", "ESP nur als Kamera"):
            self.assertIn(text, de)
        for text in ("10 minutes by default", "5 minutes", "30 minutes by default", "ESP as camera only"):
            self.assertIn(text, en)
        self.assertIn("Version 0.5.41", app_docs)
        self.assertIn("sensor.rf1_verbrauch_gesamt", app_docs)
        changelog = (APP / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 0.5.41", changelog)
        self.assertIn("## 0.1.0", changelog)
        self.assertNotIn("## 0.6", changelog)

    def test_complete_copyleft_license_is_present(self):
        license_text = (APP.parent / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("GNU GENERAL PUBLIC LICENSE"))
        self.assertIn("Version 3, 29 June 2007", license_text)
        self.assertIn("END OF TERMS AND CONDITIONS", license_text)
        self.assertGreater(len(license_text), 30000)
        for readme in ("README.md", "README.en.md"):
            text = (APP.parent / readme).read_text(encoding="utf-8")
            self.assertIn("](LICENSE)", text)

    def test_documentation_reference_files_exist(self):
        for path in ("docs/HISTORY.md", "assets/project-logo.png", "rf1_ocr_test/CHANGELOG.md",
                     "rf1_ocr_test/DOCS.md", "RELEASE-PLAN.md", "SOURCES.md"):
            with self.subTest(path=path):
                self.assertTrue((APP.parent / path).is_file(), path)


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
        self.assertEqual("difference", status)
        self.assertIn("Gerundet auf 1 Nachkommastelle", message)
        self.assertEqual("difference", compare_sample(self.data, "12345.199", 2)[0])

    def test_decimal_comparison_rounds_the_selected_precision_half_up(self):
        reference = {"raw_value": "10447.6528", "actual_value": "10447.6528"}
        status, message = compare_sample(reference, "10447.653", 3)
        self.assertEqual("match", status)
        self.assertIn("Gerundet auf 3 Nachkommastellen", message)
        self.assertEqual("difference", compare_sample(reference, "10447.652", 3)[0])
        carry = {"raw_value": "9.995", "actual_value": "10.00"}
        self.assertEqual("match", compare_sample(carry, "10.00", 2, integer_digits=4)[0])

    def test_manual_result_can_report_a_more_precise_match(self):
        self.assertEqual(3, common_exact_precision("10448.087", "10448.0870", 4))
        self.assertEqual(2, common_exact_precision("10448.087", "10448.0869", 4))

    def test_auto_cycle_can_use_fifteen_reads_with_majority_composition(self):
        # 12:3 is clear enough; an 8:7 split on a whole digit stays open since 0.2.10.
        readings = iter(["12345.120"] * 12 + ["12346.120"] * 3)
        value, confirmed, attempts = read_with_retries(
            lambda _: next(readings), {"raw_value": "99999.000", "actual_value": "99999.000"},
            0, max_attempts=5, extra_attempts=10)
        self.assertEqual(15, MAX_OCR_ATTEMPTS)
        self.assertEqual(("12345.120", True, 15), (value, confirmed, attempts))

    def test_manual_success_only_clears_same_failed_auto_capture(self):
        history = {"last_epoch": 100, "last_reference_time": 100, "check_source": ["camera", "cam", "sensor"],
                   "check_status": "ocr_unclear"}
        sample = {"raw_value": "10448.0870", "actual_value": "10448.0870"}
        kwargs = dict(status="match", uploaded_image=False, image_time=100, reference_time=100,
                      source_key=["camera", "cam", "sensor"], manual_decimals=2, auto_decimals=2,
                      ocr_confirmed=True, integer_digits=5)
        self.assertTrue(manual_confirms_failed_auto(history, sample, "10448.087", **kwargs))
        self.assertFalse(manual_confirms_failed_auto(history, sample, "10448.087", **{**kwargs, "image_time": 101}))
        self.assertFalse(manual_confirms_failed_auto(history, sample, "10448.087", **{**kwargs, "uploaded_image": True}))
        for excluded in ("stale_sample", "capture_unavailable"):
            self.assertFalse(manual_confirms_failed_auto(
                {**history, "check_status": excluded}, sample, "10448.087", **kwargs))

    def test_three_failed_runs_back_off_for_one_hour_then_success_resets_counter(self):
        history = {}
        schedule_next_check(history, "ocr_unclear", 1_000, 60)
        self.assertEqual(1_000 + 300, history["next_check_at"])
        schedule_next_check(history, "ocr_unclear", 1_300, 60)
        self.assertFalse(history.get("retry_suppressed", False))
        self.assertEqual(1_300 + 300, history["next_check_at"])
        schedule_next_check(history, "ocr_unclear", 1_600, 60)
        self.assertTrue(history["retry_suppressed"])
        self.assertEqual(1_600 + 1_800, history["next_check_at"])  # default pause 30 min
        self.assertEqual(3, history["failure_attempts"])
        schedule_next_check(history, "ocr_unclear", 5_200, 60)
        self.assertEqual(5_200 + 1_800, history["next_check_at"])
        self.assertEqual(4, history["failure_attempts"])
        schedule_next_check(history, "match", 8_800, 60)
        self.assertNotIn("retry_suppressed", history)
        self.assertNotIn("failure_attempts", history)

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

    def test_position_consensus_combines_partial_reads_after_all_ten_attempts(self):
        data = {"raw_value": "99999.999", "actual_value": "99999.999"}
        values = iter([
            "12345.120", "123?5.120", "12345.12?", "123?5.12?", "12?45.120",
            "12345.120", "12345.120", "123?5.120", "12345.12?", "12345.12?",
        ])
        value, confirmed, attempts = read_with_retries(
            lambda _: next(values), {"reference_required": False}, 3, max_attempts=10,
            force_all_attempts=True)
        self.assertEqual(("12345.120", True, 10), (value, confirmed, attempts))

    def test_automatic_composition_can_be_deferred_until_after_frame_recheck(self):
        from checks import disputed_digit_pattern, resolve_ocr_readings

        reads = ["12344.94?", "12344.942", "12344.942", "12344.942"]
        trace = []
        data = {"raw_value": "99999.999", "actual_value": "99999.999"}
        value, confirmed, attempts = read_with_retries(
            lambda _: reads[len(trace)],
            data, 3, max_attempts=4, trace=trace, defer_composition=True,
        )
        self.assertEqual(("12344.942", True, 4), (value, confirmed, attempts))
        self.assertEqual("12344.94?", disputed_digit_pattern(trace, 3, 5))
        partials = ["12344.94?", "12344.9?2", "12344.?42"]
        trace.clear()
        value, confirmed, attempts = read_with_retries(
            lambda _: partials[len(trace)], {"reference_required": False}, 3,
            max_attempts=3, trace=trace, standalone=True, defer_composition=True,
        )
        self.assertFalse(confirmed)
        self.assertEqual(("12344.942", True), resolve_ocr_readings(
            trace, 3, 5, standalone=True, standalone_composition=True,
        ))

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
        self.assertIn("AI Meter Reader", page)
        self.assertIn("FG4Q7VKQJ9BW8", page)
        self.assertIn("Über AI Meter Reader", page)
        self.assertIn("Freiwillig mit PayPal unterstützen", page)
        self.assertIn('details class="about-project"', page)
        self.assertIn("Stand und Verbrauch im Dashboard anzeigen", page)
        self.assertIn("sensor.rf1_verbrauch_gesamt", page)
        self.assertIn("Projekt von EifelLayer auf GitHub", page)
        self.assertIn(">Manueller Test</button>", page)
        self.assertIn('id="automatic-activity"', page)
        self.assertIn("Aktuelles Testbild", page)
        self.assertIn("Gelb:", page)
        self.assertIn('id="automatic-recovery"', page)
        self.assertIn("automaticStatusFailures >= 3", page)
        self.assertIn("Verbindung zur App kurz unterbrochen", page)
        self.assertIn('id="reload-view"', page)
        self.assertIn("anzeigefehler?m=", page)
        self.assertNotIn("Keine Verbindung zur App. Sie könnte gestoppt", page)
        self.assertIn('id="open-interval-settings"', page)
        self.assertNotIn("Test einstellen", page)
        self.assertIn("Testeinstellungen", page)
        self.assertIn('id="settings"', page)
        self.assertIn("Getesteten Ausschnitt für die Automatik übernehmen", page)
        self.assertIn('id="test-preview"', page)
        self.assertIn('id="manual-test-area"', page)
        self.assertNotIn('id="start-check"', page)
        self.assertIn('id="view-tools"', page)
        self.assertIn('id="manual-crop-override"', page)
        self.assertNotIn('id="open-demo-overview"', page)
        self.assertNotIn('id="open-calibration"', page)
        self.assertIn('id="open-manual-settings"', page)
        self.assertEqual(1, page.count('id="test-preview-image"'))
        self.assertIn("automatikvorschau.jpg", page)
        self.assertIn('id="setup-dialog"', page)
        self.assertIn('id="setup-skip-form"', page)
        self.assertIn("document.body.appendChild(setupDialog)", page)
        self.assertIn('id="reset-dialog"', page)
        self.assertIn("App-Daten zurücksetzen", page)
        self.assertIn("sensor.rf1_ocr_zaehlerstand", page)
        self.assertIn('id="ocr-details"', page)

    def test_english_page_translates_controls_and_remains_format_safe(self):
        page = formatted_page("en")
        self.assertIn("AI Meter Reader", page)
        self.assertIn("Automatic verification", page)
        self.assertIn("Overview", page)
        self.assertIn("Show the reading on a Home Assistant dashboard", page)
        self.assertIn("Show the reading and usage on a dashboard", page)
        self.assertIn("Support the project voluntarily with PayPal", page)
        self.assertIn("Reset app data", page)
        self.assertIn("Set up later", page)
        self.assertIn(">Manual test</button>", page)
        self.assertIn("Try a different image crop", page)
        self.assertIn('id="open-setup">Setup<', page)
        self.assertIn("Test settings", page)
        self.assertIn("Test settings", page)
        self.assertIn("Use tested crop for automatic checks", page)
        self.assertIn("More details", page)
        self.assertIn("Check in progress", page)
        self.assertIn('name="lang" value="0"', page)
        self.assertNotIn("Manueller Test", page)

    def test_english_status_and_specific_digit_diagnostics(self):
        self.assertIn("Attempt 2 of 5 in progress", english_progress("Versuch 2 von 5 läuft …"))
        self.assertIn("rounded to 2 decimal places", english_result(
            "Bestätigt: Zählerstand und Referenzwert stimmen überein.",
            "match", 2))
        self.assertIn("Whole-number digits: 3", english_uncertain_positions(
            ["12345.???", "12945.???"], 0))
        self.assertNotIn("Decimal digits", english_uncertain_positions(
            ["12345.???", "12945.???"], 0))
        self.assertIn("ESP", english_result(
            "Der ESP meldet ein Problem mit der Zählerablesung. Prüfe den Wert direkt am ESP.",
            "slfork_unclear", 0))

    def test_overlay_green_for_read_digit_red_for_unknown(self):
        source = Image.new("RGB", (500, 100), "white")
        preview = draw_test_preview(source, 400, [], [], "1234?.?21")
        self.assertEqual((36, 170, 92), preview.getpixel((1, 3)))
        self.assertEqual((203, 65, 77), preview.getpixel((321, 3)))

    def test_overlay_marks_suspected_unreadable_position_yellow(self):
        source = Image.new("RGB", (500, 100), "white")
        preview = draw_test_preview(source, 500, [], [], "1234?", 5, 0, suspected_slots=(4,))
        self.assertEqual((241, 184, 54), preview.getpixel((401, 3)))

    def test_overlay_marks_variable_or_composed_digits_yellow(self):
        source = Image.new("RGB", (500, 100), "white")
        varied = draw_test_preview(source, 500, [], [], "12345", 5, 0,
                                   readings=["12345", "12945"])
        self.assertEqual((241, 184, 54), varied.getpixel((201, 3)))
        composed = draw_test_preview(source, 500, [], [], "12345", 5, 0,
                                     readings=["12345", "12346"], composed=True)
        self.assertEqual((241, 184, 54), composed.getpixel((1, 3)))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("--write-js", "--write-js-en"):
        page = formatted_page("en" if sys.argv[1] == "--write-js-en" else "de")
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]
        Path(sys.argv[2]).write_text(script, encoding="utf-8")
    else:
        unittest.main()
