# Changelog

## 0.2.1 Alpha

- Added quick Home Assistant dashboard and Energy dashboard guidance to the setup wizard.
- Moved the voluntary PayPal link into the collapsible About section.
- Kept existing entity IDs, stored settings, and the Alpha release channel.

## 0.2.0 Alpha

## 0.2.0 Alpha

**Meter OCR – Alpha release.** Releases below 0.5 are Alpha and use the regular Home Assistant app as their test channel. There is no separate Beta app before version 0.5. From 0.5 onward, a Beta build is created only for larger changes that need dedicated testing.

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
