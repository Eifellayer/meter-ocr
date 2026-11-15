# Changelog

## 0.3.1 Alpha

- Renamed the user-facing app to AI Meter Reader while preserving the Home Assistant app slug, stored options, and existing entity IDs.
- Added up to ten bounded extra OCR variants after an uncertain automatic reading (15 attempts maximum) and strict-majority digit composition.
- Capture a fresh ESP or Home Assistant camera image after the first failed check; after two failed runs, return to the selected interval.
- Added a persistent pause/resume control for automatic checks, with manual tests still available while paused.
- Show live worker activity, source reachability, and clear reasons for stale images or failed image retrieval.
- Successful manual tests restart the automatic timer; only a pass for the same current reference and capture can clear the automatic failure status.
- Added German and English help text for retries, pausing, source status, and shorter intervals.

## 0.3.0 Alpha

- After setup, open the manual test directly and allow a JPG/PNG test image upload up to 3 MB.
- Saving automatic settings starts a new automatic check immediately.
- After the configured OCR attempts, combine digits only when each required position has a strict majority vote; otherwise keep the reading uncertain.
- Verify crop recovery against synthetic meter images at 0°, 90°, 180°, and 270°.
- Keep uploaded test photos out of saved settings and automatic measurement history.

## 0.2.1 Alpha

- Added quick Home Assistant dashboard and Energy dashboard guidance to the setup wizard.
- Decimal comparisons round half up to the selected precision, including carry between digits.
- Wait longer for Home Assistant profile language before showing the first setup screen.
- Moved the voluntary PayPal link into the collapsible About section.
- Kept existing entity IDs, stored settings, and the Alpha release channel.

## 0.2.0 Alpha

## 0.2.0 Alpha

**AI Meter Reader – Alpha release.** Releases below 0.5 are Alpha and use the regular Home Assistant app as their test channel. There is no separate Beta app before version 0.5. From 0.5 onward, a Beta build is created only for larger changes that need dedicated testing.

- Guided first setup for SLFork / AI on the Edge, Home Assistant cameras, and ESPHome cameras with local OCR. The wizard can be reopened later and shows current values for quick changes.
- Meter format settings for whole and fractional digits, display type, comparison precision, crop, rotation, lighting, OCR attempts, check interval and plausibility limit.
- Optional initial fallback reading with timestamp, plus a per-test fallback value. Manual tests now retain their settings and a successful test restarts the automatic timer.
- Live camera checks capture fresh snapshots with up to 10 attempts within 20 seconds. The manual test shows the original source image, annotated OCR preview, or a clear no-image message.
- OCR processing adds lighting correction for uneven illumination. ESP fallback readings are checked against their last valid timestamp and configured flow limit before being accepted.
- Plausible confirmed readings update an increasing total-consumption sensor. Existing `sensor.rf1_*` entity IDs, app slug and media path remain unchanged.
- The overview keeps automatic status separate from manual diagnostics. Help text, language selection, notifications and the setup flow are available in German and English.
- Only AI on the Edge / SLFork has been tested by the maintainer with a real meter. Other camera and meter modes have simulated tests only.

## 0.1.0 Alpha

- Initial Home Assistant app release with local Tesseract OCR verification for AI on the Edge / SLFork meter images.
