# AI Meter Reader

**Version 0.2.1** · [Deutsch](README.md) · [Guide](rf1_ocr_test/DOCS.md) · [Changelog](rf1_ocr_test/CHANGELOG.md) · [Roadmap](RELEASE-PLAN.md)

<img src="assets/project-logo.png" alt="AI Meter Reader" width="110">

Home Assistant app that reads mechanical meters (mainly gas meters with digit rollers) locally from a camera image. No cloud, no subscription AI: Tesseract OCR runs on your Home Assistant (ARM64 or AMD64).

## Quick start

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FEifellayer%2Fmeter-ocr)

1. Add the repository (link above, or `https://github.com/Eifellayer/meter-ocr` under **Settings → Apps → Install app → ⋮ → Repositories**).
2. Install **AI Meter Reader**, start it and open the web UI.
3. Pick the image source in the setup wizard: ESPHome / Home Assistant camera, AI on the Edge / SLFork, or **ESP as camera only**.
4. Start automatic setup. The app finds the digit area, confirms it on several images and then checks on its own.

## What it does

- Reads the meter from the camera image and confirms every check with a second image.
- Marks unreadable digits instead of guessing and never books negative or duplicate consumption.
- When three decimal places are configured but only seven digits are verified, the UI says **3 configured / 2 provisionally checked** and resumes the eighth-digit background search after restarts.
- Provides `sensor.rf1_ocr_zaehlerstand` and `sensor.rf1_verbrauch_gesamt` (Energy dashboard).
- Optional: comparison with an existing sensor, notifications, demo without a camera.

## Check schedule

| Situation | Next check |
| --- | --- |
| Successful check | configured interval, 10 minutes by default |
| 1st or 2nd failed check | 2 minutes when the host has spare capacity, otherwise 5 minutes |
| Only the 7th digit unclear, rest confirmed by reference | 30 minutes |
| 3 failed checks in a row | pause, adjustable, 30 minutes by default (no pause if only the last roller is unclear) |

## Tested with

So far the app has only been tried in practice on **one gas meter** (roller counter, ESP32-CAM running AI on the Edge as the camera). Water meters and other gas meters have not been tested in practice; a test with public digit images from various water and gas meters showed that unfamiliar counters are read noticeably worse (the app reports unclear digits instead of guessing). Feedback with your own meter is very welcome.

## Notes

OCR is not a certified measurement; the physical meter counts for billing. Report bugs and ideas as a [GitHub issue](https://github.com/Eifellayer/meter-ocr/issues) (no credentials or private photos). License: [GNU GPLv3 or later](LICENSE), third-party software in [SOURCES.md](SOURCES.md). How the project came about: [history](docs/HISTORY.md).

[Support the project](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8) (optional)
