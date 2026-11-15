# Meter OCR for Home Assistant

**Local camera OCR for Home Assistant with ESPHome and AI on the Edge / SLFork.**

[Deutsch / German](README.md) · [English](README.en.md)

**Test build: 0.1.0.** Install **Meter OCR Beta** from the [shared Home Assistant repository](https://github.com/Eifellayer/rf1-kontrollmessung).

The tested GitHub branch is [stable](https://github.com/Eifellayer/rf1-kontrollmessung/tree/stable). Future changes are tested on [beta](https://github.com/Eifellayer/rf1-kontrollmessung/tree/beta). The existing Home Assistant repository URL continues to use `main` for published versions.

Meter OCR reads camera images with **local Tesseract OCR**. It can provide its own reading from an ESPHome or Home Assistant camera, or double-check an existing reading from AI on the Edge / SLFork or a reference sensor.

Designed for mechanical gas meters such as the **Pipersberg G4 RF1**. The register format is five whole digits, with up to three decimal digits. The current Home Assistant sensor output uses cubic meters.

> **Private hobby project, not a certified instrument.** OCR can misread digits. Check the physical meter directly for billing or official readings. Provided without warranty or guaranteed support.

## What does it check?

By default, the app compares the **five digits for whole cubic meters (m³)**. Up to three decimal places can optionally be included. Ignored decimal digits are displayed when available but **do not affect the result**. `?` means a digit was not reliably recognized. Digits are truncated for comparison, never rounded.

The app downloads the latest available meter image and reference reading from SLFork, or uses the configured Home Assistant camera and optionally a cumulative sensor in m³. It detects digit frames automatically when possible; otherwise you can specify a crop.

When SLFork reports **Use Fallback**, the app shows the fallback reading and its known time separately from the image time. With **Rate Too High (<)**, SLFork can advance that timestamp while keeping the same reading. The app then uses the time of its last confirmed match for that value when available. It marks unknown measurement times explicitly. The plausibility check uses the elapsed time and maximum flow. A valid match is required to count the reading toward confirmations and consumption.

For each image, OCR can attempt between **1 and 10 different processing profiles** (default 5). As soon as an attempt confirms the configured precision against the valid reference reading, processing stops. A successful OCR read without a reference is shown as **unverified**, not as a confirmed match.

## Install

1. In Home Assistant, open **Settings → Apps → Install app → ⋮ → Repositories** and add:
   `https://github.com/Eifellayer/rf1-kontrollmessung`
2. Install **Meter OCR**.
3. Configure `esp_url` for the SLFork ESP, for example `http://esp-gaszaehler.local`. Alternatively configure `kamera_entitaet` and optionally `referenz_entitaet`.
4. Start the app and open its web interface.

A Home Assistant installation with Supervisor is required; supported platforms are **AMD64 and ARM64**. Only one installed variant should publish the same sensor IDs at a time.

## First setup and image source

On a fresh installation, open the web interface and choose a mode under **Settings → Image source**. You can change it in the same place later.

| Mode | What it uses |
| --- | --- |
| **SLFork / AI on the Edge** | The ESP supplies the image and reference reading. Enter its address. |
| **Home Assistant camera** | Choose a `camera.*` entity and optionally a current reference sensor in m³. |
| **ESPHome or camera with local OCR** | The camera supplies the image. RF1 reads it locally and publishes `sensor.rf1_ocr_zaehlerstand` in m³. |

For ESPHome, configure an [ESP32 camera](https://esphome.io/components/esp32_camera/) with the [native API](https://esphome.io/components/api/) and add the device to Home Assistant. Check the image there, then select its `camera.*` entity in RF1. Use the **manual test** to adjust the crop and apply a working preview to automatic checks. This mode works without SLFork or a reference sensor.

The standalone sensor requires a majority of at least two OCR profiles on the same photo. It reports **unavailable** if the reading is uncertain or goes below the last valid reading from that camera. Standalone OCR values are independent readings. The Energy dashboard uses the separate cumulative consumption sensor. Upgrades retain the active source. Changing the source starts a new automatic confirmation count.

## Set up the camera crop

Under **Test settings**, specify an image region and enter pixel coordinates from the original frame. Use **Clockwise rotation** for sideways or upside-down photos. Measure the width of the whole digits after rotation. Run the test to inspect the result, then apply the tested crop and rotation to automatic checks.

Automatic digit color handles light or dark digits. Later OCR attempts can compensate for uneven lighting in the register. Reflections that cover digits and severe perspective distortion require a clearer camera image. For a meter with a digit register and small pointer dials, test the register at **whole cubic meters** precision. The OCR reads the digit window and leaves the pointer dials unread.

The [photo test report (German)](METER-PHOTO-TESTS.md) covers ten public meter photos and another ten contributed by AI on the Edge users.

## Plausibility check and Energy dashboard

Meter OCR records consumption from automatic reference matches or agreeing OCR profiles in standalone mode. The first accepted reading establishes the baseline. Later readings are checked against the last accepted value. An out-of-order time, backwards reading or increase above the configured flow limit is rejected. The check accounts for the selected digit precision.

Under **Settings → Automatic checks → Maximum flow**, enter the Qmax marked on your meter. The G4 default is 6 m³/h. Rejected readings leave the cumulative counter untouched. The first accepted reading after a source or precision change establishes a baseline for later consumption differences.

In Home Assistant, go to **Energy → Configuration → Gas consumption** and select **Meter OCR Gasverbrauch gesamt** (`sensor.rf1_verbrauch_gesamt`). The sensor appears after the first accepted reading. It supplies cumulative gas consumption in m³. Home Assistant calculates hourly, daily, weekly and monthly views from this sensor.

## Notifications and automatic status

A green check marks a confirmed comparison. A failed check first shows a short yellow notice. After an hour of failed checks, the notice includes details and an **Ignore** button. An image source that has been unavailable for an hour is marked in red.

Open **Settings → Notifications** and enable **Notify me if checks keep failing**. Set how many minutes to wait before Home Assistant shows a notice, including when SLFork keeps using a fallback reading. Set the additional delay for push and email. **0 hours** sends them when the notice appears.

- **Home Assistant only:** Leave both optional destinations blank.
- **Mobile push:** Enter a Companion action such as `notify.mobile_app_my_phone`.
- **Email:** Configure the [SMTP integration](https://www.home-assistant.io/integrations/smtp/) and a recipient in Home Assistant. Enter its `notify.*` entity, such as `notify.my_email`. Other notification entities also work.

Each destination records at most one successful send per incident. Dismissing the Home Assistant notice or a successful automatic check cancels any pending deliveries. Manual tests never send notifications. The legacy `push_dienst` is used until the notification settings are first saved in the web interface.

## Language selection

**Automatic (Home Assistant)** uses the signed-in Home Assistant user's profile language when available through Ingress. German and English include regional variants such as `de-AT` and `en-US`. If the profile language is unavailable or unsupported, the app uses the first supported browser language, then German. Explicit **Deutsch** and **English** choices persist per identified Ingress user. Selecting **Automatic** uses the current profile again on the next open or reload. Without an Ingress user identity, a manual choice lasts for the current navigation.

## Automatic verification

The main screen shows the reading, reference, status, image time, last automatic check, last confirmed match and next check. Open **Settings → Automatic checks** to change the persistent rules, or **Check images** to see the latest and last-confirmed photos.

| Setting | Purpose |
| --- | --- |
| Check interval | 1–1,440 minutes after a successful check, default 60. Applies to the next scheduled check. |
| Comparison | Whole cubic meters only or 1–3 decimal places |
| Max. OCR attempts | 1–10 profiles per image, default 5 |
| Digit color | Automatic detection, light digits, or dark digits |
| Image region | Automatically detect frames, or use a fixed crop and whole-digit width |

Saved automatic rules persist across app restarts. They take precedence over the corresponding Home Assistant configuration fields. When the comparison precision changes, the automatic confirmation count starts over so matches from the old precision are not treated as new evidence.

A successful automatic check repeats after **one hour** by default. After a failed check, the app retries within **five minutes**. With the default settings, `sensor.rf1_pruefstatus` reports `review_due` after four hours of failed checks. A shorter interval polls SLFork more often. Capture frequency is configured on the ESP.

Each SLFork measurement timestamp counts at most once. In Home Assistant camera mode, the app uses the fetch time, so independent confirmations rely on the camera supplying fresh images. A configured reference sensor must report in `m³` and have a timestamp within five minutes of the image request.

## Manual test

Select **Start test** on the main screen to check the latest available image. The progress indicator and result appear below the button.

Open **Test settings** to choose digit color, comparison precision, maximum OCR attempts and an image crop. The crop uses `left, top, right, bottom` and the width of the whole-number digit region. Select **Run check now** to apply those settings to the test. Manual tests use the existing image and leave automatic confirmation counts unchanged.

The status is neutral while a test runs, green for a confirmed match, and yellow for a mismatch or uncertain reading. The result explicitly states the comparison precision.

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

## Support and optional donations

For questions and bug reports, use the [GitHub issues](https://github.com/Eifellayer/rf1-kontrollmessung/issues) page. Please include your app version, relevant log lines without secrets, and the result status.

The project is free. If it helped you, you can [make a voluntary PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are never required for use or support.

[German README](README.md) · [Changelog](rf1_ocr_test/CHANGELOG.md) · [App introduction (English)](rf1_ocr_test/README.en.md)
