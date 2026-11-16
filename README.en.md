# AI Meter Reader for Home Assistant

**Read and verify meter values from camera images directly in Home Assistant.**

**Long-term goal:** AI on the Edge / SLFork should no longer be a requirement. AI Meter Reader aims to get images from Home Assistant and process them locally, with flexible support for different meter types, camera angles, crops, and lighting. This is the project direction, not a claim that every meter is already supported or field-tested.

[Deutsch / German](README.md) · [English](README.en.md)

📘 [German illustrated user guide (PDF)](docs/Bedienungsanleitung-AI-Meter-Reader.pdf) · [App documentation](rf1_ocr_test/DOCS.md)

**Current version: 0.5.2 Stable.** This release focuses on OCR stability, automatic setup and image editing. Pulse sensor work resumes in 0.6 or later.

## Beta testers wanted

Do you use Home Assistant with a gas, water, or other meter? We are looking for testers with different cameras, crops, and lighting conditions. Optional fine-tuning and adaptive intervals need real long-term testing. I use AI on the Edge for real-world checks; other sources and meter types have so far been tested with simulations only. To help, report your app version, meter type, and image source through [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues). Please do not post credentials or unredacted photos containing personal information.

AI Meter Reader reads camera images with **local Tesseract OCR**. It can provide its own reading from an ESPHome or Home Assistant camera, or double-check an existing reading from AI on the Edge / SLFork or a reference sensor.

The current focus is mechanical gas meters with configurable whole and fractional digits. Small pointer dials are not read automatically yet. The Home Assistant reading output currently uses cubic meters; tester feedback will help extend support to more meters and conditions.

AI Meter Reader is a private hobby project for checking meter readings. [Usage notes](#usage-notes)

## What does it check?

By default, the app compares the **five digits for whole cubic meters (m³)**. Up to three decimal places can optionally be included. Values are rounded half up to the selected precision; the next known digit determines the rounding. `?` means a digit was not reliably recognized.

The app downloads the latest available meter image and reference reading from SLFork, or uses the configured Home Assistant camera and optionally a cumulative sensor in m³. It detects digit frames automatically when possible; otherwise you can specify a crop.

At three decimal places, **Precision mode** requires the final digit to match. With this option off, the automatic check can pass with a yellow note after three distinct images fail on the last digit alone. The app uses the reference reading for consumption after checking its plausibility.

If a SLFork measurement cycle aborts or its processed image is too old, the app requests a fresh raw image directly from the ESP camera. It uses the configured crop and rotation. If it can read the raw image, the app shows the reading without an ESP reference and flags image alignment and reference markers as possible causes. This reading does not count toward confirmed checks or consumption.

For an uncertain automatic reading, the app can run up to ten additional image-processing profiles (15 attempts maximum) and combines digits only when a strict majority agrees. After a failed automatic check, it makes up to two more image checks at five-minute intervals. Each check requests the current image; its timestamp determines whether it is new. If all three checks fail, it waits one hour for a higher reading or a new image, then tries again. After a successful match, the selected check interval applies again. A successful OCR read without a reference is shown as **unverified**, not as a confirmed match.

## Install

1. In Home Assistant, open **Settings → Apps → Install app → ⋮ → Repositories** and add **Add-ons by Eifellayer** using the [Stable link](https://github.com/Eifellayer/meter-ocr#stable).
2. Install **AI Meter Reader**. Upgrades retain the app ID, entities and saved settings.
3. Configure `esp_url` for the SLFork ESP, for example `http://esp-gaszaehler.local`. Alternatively configure `kamera_entitaet` and optionally `referenz_entitaet`.
4. Start the app and open its web interface.

A Home Assistant installation with Supervisor is required on **AMD64 or ARM64**. Pulse sensor work resumes in 0.6 or later. Back up your Home Assistant configuration before updating.

## First setup and image source

On first open, a compact setup wizard guides you through the image source, meter type, digit format, crop, schedule and notifications. You can reopen it later; saved values are prefilled for quick edits. Explanations expand on demand. Automatic checks remain separate from manual diagnostics.

Choose an image source first. If you are starting with a camera, **ESPHome / camera** is the recommended choice. The guide next to the selector explains when to use the other modes. **Found in Home Assistant** offers existing cameras and reported AI on the Edge addresses. If you skip setup, automatic checks wait until you save an image source.

Under **AI on the Edge / SLFork**, enable **Use the ESP as a camera only** and enter its address. AI Meter Reader requests a fresh image and reads the meter locally, even if alignment or recognition fails on the ESP. Configure a fixed crop from the raw image if needed.

| Mode | What it uses |
| --- | --- |
| **SLFork / AI on the Edge** | The ESP supplies the image and reference reading. Enter its address. |
| **Home Assistant camera** | Choose a `camera.*` entity and optionally a current reference sensor in m³. |
| **ESPHome or camera with local OCR** | The camera supplies the image. AI Meter Reader reads it locally and publishes `sensor.rf1_ocr_zaehlerstand` in m³. |

For ESPHome, configure an [ESP32 camera](https://esphome.io/components/esp32_camera/) with the [native API](https://esphome.io/components/api/) and add the device to Home Assistant. Check the image there, then select its `camera.*` entity in AI Meter Reader. Use the **manual test** to adjust the crop and apply a working preview to automatic checks. This mode works without SLFork or a reference sensor.

The standalone sensor requires a majority of at least two OCR profiles on the same photo. It reports **unavailable** if the reading is uncertain or goes below the last valid reading from that camera. Standalone OCR values are independent readings. The Energy dashboard uses the separate cumulative consumption sensor. Upgrades retain the active source. Changing the source starts a new automatic confirmation count.

## Set up the camera crop

Under **Automatic checks → Reflections and obscured digits**, optionally reconstruct one missing digit from the previous and next confirmed readings and the maximum flow. A manually entered starting value with its reading time can serve as the first reference. If there is exactly one possible value, select the suggested digit and accept the intermediate reading. The calculated digit is highlighted in yellow. The estimate does not become a new reference or add a separate consumption record. You can hide the suggestion permanently.

Set **Image rotation (°)** in the manual crop settings to correct the angle one degree at a time. Recovery checks try slightly different angles and reuse the angle from a confirmed result for the same camera and crop. In standalone mode, the first image gives a provisional reading. A second image five minutes later must confirm the same value or a plausible increase before it is published.

In camera mode, the app looks for the digit row in the original image. If it cannot find the right area, open the manual test settings and choose **Draw a frame**. Draw around the full digit row and run the test. If the preview looks right, apply the tested crop to automatic checks. If the digits are still hard to read, check the camera angle, focus and lighting.

In the **manual test**, select a manual image region and enter pixel coordinates from the original frame. Use **Clockwise rotation** for sideways or upside-down photos. Measure the width of the whole digits after rotation. Run the test to inspect the result, then apply the tested crop and rotation to automatic checks.

Automatic digit color handles light or dark digits. Later OCR attempts can compensate for uneven lighting in the register. Reflections that cover digits and severe perspective distortion require a clearer camera image. For a meter with a digit register and small pointer dials, test the register at **whole cubic meters** precision. The OCR reads the digit window and leaves the pointer dials unread.

The [photo test report (German)](METER-PHOTO-TESTS.md) documents simulated OCR runs on ten public gas, water and electricity meter images. It is not a hardware test.

> **Test status:** The maintainer uses AI on the Edge / SLFork for real meter tests. Camera and ESPHome modes and other meter types have automated and simulated coverage only; no real-device test is claimed for them.

### Automatic crop and rotation setup

In the setup wizard, select **Learn crop and rotation** under **Image region**. The search starts after saving. You can also start it at any time under **Overview → Automatic setup**. The app shows the remaining time, number of images and rotation being tested. **Automatic setup images** shows the camera frame, highlighted region, rotated crop and OCR reading. A question mark indicates an unclear digit. Choose the maximum number of distinct images to check (4 to 100, default 100). The app tries different crops and angles and saves a setting after three confirmations on distinct images and a final regular OCR check on one more fresh image. Without an external reference or a manually entered starting reading, the meter must show a plausible increase. The search ends after 15 minutes, 100 crop attempts, or when it reaches the image limit. If unsuccessful, it keeps your existing settings. You can stop the search at any time.

## Plausibility check and Energy dashboard

AI Meter Reader records consumption from automatic reference matches or agreeing OCR profiles in standalone mode. The first accepted reading establishes the baseline. Later readings are checked against the last accepted value. An out-of-order time, backwards reading or increase above the configured flow limit is rejected. The check accounts for the selected digit precision.

Under **Automatic check settings → Maximum flow**, enter the Qmax marked on your meter. The G4 default is 6 m³/h. Rejected readings leave the cumulative counter untouched. The first accepted reading after a source or precision change establishes a baseline for later consumption differences.

In Home Assistant, go to **Energy → Configuration → Gas consumption** and select **AI Meter Reader Gasverbrauch gesamt** (`sensor.rf1_verbrauch_gesamt`). The sensor appears after the first accepted reading. It supplies cumulative gas consumption in m³. Home Assistant calculates hourly, daily, weekly and monthly views from this sensor.

## Notifications and automatic status

A green check marks a confirmed comparison. A red warning highlights a current problem at the top of the page. **Ignore** hides the current warning in the web interface. New incidents are shown again, and notification rules still apply.

Open **Notifications** and enable **Notify me if checks keep failing**. Set how many minutes of unsuccessful automatic checks should pass before Home Assistant shows a notice. Set the additional delay for push and email. **0 hours** sends them when the notice appears.

- **Home Assistant only:** Leave both optional destinations blank.
- **Mobile push:** Enter a Companion action such as `notify.mobile_app_my_phone`.
- **Email:** Configure the [SMTP integration](https://www.home-assistant.io/integrations/smtp/) and a recipient in Home Assistant. Enter its `notify.*` entity, such as `notify.my_email`. Other notification entities also work.

Each destination records at most one successful send per incident. Dismissing the Home Assistant notice or a successful automatic check cancels any pending deliveries. Manual tests never send notifications. The legacy `push_dienst` is used until the notification settings are first saved in the web interface.

## Language selection

**Automatic (Home Assistant)** uses the signed-in Home Assistant user's profile language when available through Ingress. German and English include regional variants such as `de-AT` and `en-US`. If the profile language is unavailable or unsupported, the app uses the first supported browser language, then German. Explicit **Deutsch** and **English** choices persist per identified Ingress user. Selecting **Automatic** uses the current profile again on the next open or reload. Without an Ingress user identity, a manual choice lasts for the current navigation.

## Automatic verification

The main screen shows the last recognized value, reference value, verification result, image timestamp, and next scheduled check. Expand **Automatic checks – settings** to change the persistent rules, or **Check images** to see the latest and last-confirmed photos.

| Setting | Purpose |
| --- | --- |
| Comparison | Whole cubic meters only or 1–3 decimal places |
| Max. OCR attempts | 1–10 base profiles per image, default 5 (uncertain automatic readings may use up to 10 additional profiles) |
| Digit color | Automatic detection, light digits, or dark digits |
| Image region | Automatically detect frames, or use a fixed crop and whole-digit width |

Saved automatic rules persist across app restarts. They take precedence over the corresponding Home Assistant configuration fields. When the comparison precision changes, the automatic confirmation count starts over so matches from the old precision are not treated as new evidence.

A successful check is normally repeated after **one hour**. After a failure, up to two additional image checks follow at **five-minute intervals**. If all three checks fail, the app waits **one hour** for a higher reading or new image before trying again. The overview shows the number of failed checks and the wait reason. With the default settings, `sensor.rf1_pruefstatus` reports `review_due` after four hours of failed checks.

Use **Pause automatic checks** to stop scheduled checks and **Resume automatic checks** to continue. A large yellow notice shows the paused state; manual tests remain available. The pause survives app restarts. The overview also tells you whether the app is waiting, capturing an image, or reading it, and whether the ESP/camera returned a fresh image. If the app is stopped or unavailable, an open page reports the lost connection.

Each SLFork measurement timestamp counts at most once. In Home Assistant camera mode, the app uses the fetch time, so independent confirmations rely on the camera supplying fresh images. A configured reference sensor must report in `m³` and have a timestamp within five minutes of the image request.

## Advanced manual test

The **Open manual test** section is collapsed by default. Open it only when you want to diagnose the camera image.

You can independently select digit color, comparison precision, maximum OCR attempts, and a custom crop (`left, top, right, bottom`) with the width of the whole-number digit region. Press **Run check now** to re-evaluate the latest stored image. This does not trigger a new ESP capture and does not increase the automatic confirmation count.

The status is neutral while a test runs, subtly **green only for a confirmed match**, and red for failed checks. The result explicitly states the comparison precision.

Afterward, the **annotated OCR image** outlines recognized digits in green and uncertain digits in red. These colors indicate OCR recognition, **not** reference-value agreement. When individual digit frames are unavailable, boxes are approximate. **More details** shows the OCR values from each attempt and, where possible, the uncertain digit positions.

When a custom crop produces a preview, use **Use tested crop for automatic checks** to save the crop and whole-digit width directly without copying coordinates to another settings page.

## Configuration reference

| Option | Description |
| --- | --- |
| `esp_url` | Base URL of the SLFork ESP |
| `kamera_entitaet` | Optional Home Assistant `camera.*` image source |
| `referenz_entitaet` | Optional cumulative `sensor.*` reading in m³ |
| `ausschnitt` | Fallback crop coordinates in the app configuration |
| `vorkomma_breite` | Width of the whole-number digits within the crop |
| `helle_ziffern` | Legacy default digit-polarity hint |
| `vergleich_nachkommastellen` | Default comparison precision, 0–3 places |
| `ocr_versuche` | Default OCR attempts, 1–10 |
| `zeitzone` | Time zone, normally `Europe/Berlin` |
| `push_dienst` | Legacy default for the optional `notify.mobile_app_…` action |

Existing entity IDs remain **`sensor.rf1_kontrollbild`** and **`sensor.rf1_pruefstatus`**. Check images are stored in **Media → Local Media → rf1**.

## Usage notes

Developed with AI assistance. OCR can misread digits. Check the physical meter for billing and official readings.

To the extent permitted by law, the software is provided without warranties of accuracy, availability or fitness for a particular purpose. Liability for damages arising from its use is excluded to the extent permitted by law. Mandatory liability rules apply, including for intent, gross negligence, injury to life, body or health, and product liability.

[Sources and credits](SOURCES.md)

## Support and optional donations

For questions and bug reports, use the [GitHub issues](https://github.com/Eifellayer/meter-ocr/issues) page. Please include your app version, relevant log lines without secrets, and the result status.

The project is free. If it helped you, you can [make a voluntary PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are never required for use or support.

[German README](README.md) · [Changelog](rf1_ocr_test/CHANGELOG.md) · [App introduction (English)](rf1_ocr_test/README.en.md)
