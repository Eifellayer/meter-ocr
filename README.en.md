# AI Meter Reader – local meter OCR for Home Assistant

**Version 0.6.11 Stable** · [Deutsch](README.md) · [Changelog](rf1_ocr_test/CHANGELOG.md)

Read mechanical meter registers locally from camera images with Tesseract OCR. Optionally verify results against **AI on the Edge / SLFork** or a Home Assistant sensor. Primarily designed for rolling-digit gas meters with configurable decimal digits. Requires Home Assistant with Supervisor (ARM64 or AMD64).

<img src="assets/project-logo.png" alt="AI Meter Reader project logo" width="120">

## Quick start

[![Add app repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FEifellayer%2Fmeter-ocr)

1. **Add the repository:** Open the link above, or enter `https://github.com/Eifellayer/meter-ocr` under **Settings → Apps → Install app → ⋮ → Repositories**.
2. **Install AI Meter Reader**, start it and open the web interface.
3. **Choose an image source:** AI on the Edge / SLFork, ESP as camera only, ESPHome, or a Home Assistant camera.
4. **Start automatic setup:** Overview shows each setup step. Once seven digits have been confirmed, routine checks can begin; an optional eighth digit is examined in the background.
5. If needed, use **Overview → Tools → Manual test** to adjust the crop, rotation or lighting. A camera-free **demo** is also available.

This link pre-fills the repository dialog; it does **not** automatically install the app. If it fails, add the repository URL manually. See the [illustrated German guide](docs/Bedienungsanleitung-AI-Meter-Reader.pdf) for example screens.

## Features

- **Local OCR:** configurable digit count, automatic or manual crop, rotation, retry profiles and single-digit checks.
- **Verification:** comparison with reference readings, explicit uncertainty markers, and plausible consumption bounds.
- **Automation:** configurable schedule, failure cooldowns, notifications and `sensor.rf1_verbrauch_gesamt` for the Energy dashboard.
- **Seven plus one digit:** a verified seven-digit crop stays in service while the hard-to-read third decimal digit is investigated separately. An unclear seventh digit can be partially verified using the first six digits and a reliable reference for one check only, without posting consumption.
- **Preserve statistics:** a separate factory reset option retains total consumption and consumption history.

### When does it check?

| Situation | Next check |
| --- | --- |
| Successful routine check | Configured interval, **10 minutes by default** |
| First or second failed check | After **5 minutes**, subject to fresh images |
| Only the seventh digit is uncertain, six digits match a valid reference (when two decimal digits are required) | Wait **30 minutes** for a higher reading; partial verification without posting consumption |
| Three consecutive failed checks | **60-minute** cooldown |
| Setup and optional adaptive functions | May temporarily run more often; see the Overview countdown |

## Documentation and testing

- [Detailed operation, rules and configuration](docs/DETAILS.en.md) · [Deutsche Dokumentation](docs/DETAILS.md)
- [Illustrated German PDF guide](docs/Bedienungsanleitung-AI-Meter-Reader.pdf) · [App documentation](rf1_ocr_test/DOCS.md)
- [Public meter photo test report (German)](METER-PHOTO-TESTS.md) · [Sources](SOURCES.md) · [Roadmap](RELEASE-PLAN.md)

**Field testing:** AI on the Edge / SLFork and **ESP as camera only** have been used with a real ESP/gas meter. Independent ESPHome camera setups, other Home Assistant cameras, and additional meter types have automated or simulated coverage but still need separate real-device verification. The historical photo report is not yet a full image-regression suite executed by CI.

## Stable

The stable repository URL is `https://github.com/Eifellayer/meter-ocr`. Normal upgrades retain the app ID, existing `rf1_*` entities and saved readings. **`rf1_ocr_test` is the historical app directory and slug, retained for compatibility**, not a separate test channel. Back up Home Assistant before major upgrades.

To refresh the update status, run `homeassistant.update_entity` on `update.meter_ocr_update` in **Developer tools → Actions**. If automatic app updates are enabled, the available update should install; otherwise use `update.install` for the same entity. [Details](docs/DETAILS.en.md#check-for-a-new-release-immediately).

## Feedback and contributions

Use [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues) and include the version, source, meter type and expected reading. **Do not post credentials or unredacted private photos.** This free hobby project is open source under the **GNU GPL version 3 or any later version**. Forks and independent improvements are welcome. If you distribute a modified version, the GPL requires providing the complete corresponding source under its conditions. The maintainer still decides what goes into the official app. See [LICENSE](LICENSE) and [third-party credits](SOURCES.md).

## Usage notes

OCR readings are **not certified measurements**. Check the physical meter for billing and official readings. The software is provided without warranty to the extent permitted by law, without limiting mandatory liability requirements.

[Optional donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8) · [GitHub](https://github.com/Eifellayer/meter-ocr)
