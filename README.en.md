# Gas Meter OCR Verification for Home Assistant

**An independent, local, image-based second check of camera-read mechanical gas meters.**

[Deutsch / German](README.md) · [English](README.en.md)

**Release status: Beta.** Versions below 0.5.0 are alpha. The beta phase starts at 0.5.0, and the first stable version is 1.0.0.

This community project checks whether a reading produced by an ESP or Home Assistant sensor really matches the visible digits on the gas meter. Instead of trusting the first reading, it analyzes the latest camera image again with **local Tesseract OCR**. It is a plausibility check, not a separate certified meter.

Designed for the **Pipersberg G4 RF1** with **AI on the Edge / SLFork**. A compatible Home Assistant camera can also supply the image. The `rf1_ocr_test` directory, app slug, and existing Home Assistant entity IDs are retained for compatibility.

> **Private hobby project, not a certified instrument.** OCR can misread digits. Check the physical meter directly for billing or official readings. Provided without warranty or guaranteed support.

## What does it check?

By default, the app compares the **five digits for whole cubic meters (m³)**. Up to three decimal places can optionally be included. Ignored decimal digits are displayed when available but **do not affect the result**. `?` means a digit was not reliably recognized. Digits are truncated for comparison, never rounded.

The app downloads the latest available meter image and reference reading from SLFork, or uses the configured Home Assistant camera and optionally a cumulative sensor in m³. It detects digit frames automatically when possible; otherwise you can specify a crop.

For each image, OCR can attempt between **1 and 10 different processing profiles** (default 5). As soon as an attempt confirms the configured precision against the valid reference reading, processing stops. A successful OCR read without a reference is shown as **unverified**, not as a confirmed match.

## Install

1. In Home Assistant, open **Settings → Apps → Install app → ⋮ → Repositories** and add:
   `https://github.com/Thunder86/rf1-kontrollmessung`
2. Install **Gaszähler OCR-Kontrolle** (Gas Meter OCR Verification).
3. Configure `esp_url` for the SLFork ESP, for example `http://esp-gaszaehler.local`. Alternatively configure `kamera_entitaet` and optionally `referenz_entitaet`.
4. Start the app and open its web interface.

A Home Assistant installation with Supervisor is required; supported platforms are **AMD64 and ARM64**. Only one installed variant should publish the same sensor IDs at a time.

## First setup and image source

On a fresh installation, open the web interface and choose a mode under **Image source**. You can change it in the same place later.

| Mode | What it uses |
| --- | --- |
| **SLFork / AI on the Edge** | The ESP supplies the image and reference reading. Enter its address. |
| **Home Assistant camera** | Choose a `camera.*` entity and optionally a current reference sensor in m³. |
| **ESPHome or camera with local OCR** | The camera supplies the image. RF1 reads it locally and publishes `sensor.rf1_ocr_zaehlerstand` in m³. |

For ESPHome, configure an [ESP32 camera](https://esphome.io/components/esp32_camera/) with the [native API](https://esphome.io/components/api/) and add the device to Home Assistant. Check the image there, then select its `camera.*` entity in RF1. Use the **manual test** to adjust the crop and apply a working preview to automatic checks. This mode works without SLFork or a reference sensor.

The standalone sensor requires a majority of at least two OCR profiles on the same photo. It reports **unavailable** if the reading is uncertain or goes below the last valid reading from that camera. Standalone OCR values have no reference confirmation or long-term statistics configuration. Upgrades retain the active source. Changing the source starts a new automatic confirmation count.

## Notifications and automatic status

A green check marks a confirmed comparison. A red warning highlights a current problem at the top of the page. **Ignore** hides the current warning in the web interface. New incidents are shown again, and notification rules still apply.

Open **Notifications** and enable **Notify me if checks keep failing**. Set how many minutes of unsuccessful automatic checks should pass before Home Assistant shows a notice. Set the additional delay for push and email. **0 hours** sends them when the notice appears.

- **Home Assistant only:** Leave both optional destinations blank.
- **Mobile push:** Enter a Companion action such as `notify.mobile_app_my_phone`.
- **Email:** Configure the [SMTP integration](https://www.home-assistant.io/integrations/smtp/) and a recipient in Home Assistant. Enter its `notify.*` entity, such as `notify.my_email`. Other notification entities also work.

Each destination records at most one successful send per incident. Dismissing the Home Assistant notice or a successful automatic check cancels any pending deliveries. Manual tests never send notifications. The legacy `push_dienst` is used until the notification settings are first saved in the web interface.

## Language selection

**Automatic (Home Assistant)** uses the signed-in Home Assistant user's profile language when available through Ingress. German and English include regional variants such as `de-AT` and `en-US`. If the profile language is unavailable or unsupported, the app uses the first supported browser language, then German. Explicit **Deutsch** and **English** choices persist per identified Ingress user. Selecting **Automatic** uses the current profile again on the next open or reload. Without an Ingress user identity, a manual choice lasts for the current navigation.

Version 0.8.1 used a browser-wide preference. To keep an explicit language, select it once in each account after upgrading. The app uses the authenticated frontend connection to read the profile and stores the manual choice per user.

## Automatic verification

The main screen shows the last recognized value, reference value, verification result, image timestamp, and next scheduled check. Expand **Automatic checks – settings** to change the persistent rules, or **Check images** to see the latest and last-confirmed photos.

| Setting | Purpose |
| --- | --- |
| Comparison | Whole cubic meters only or 1–3 decimal places |
| Max. OCR attempts | 1–10 profiles per image, default 5 |
| Digit color | Automatic detection, light digits, or dark digits |
| Image region | Automatically detect frames, or use a fixed crop and whole-digit width |

Saved automatic rules persist across app restarts. They take precedence over the corresponding Home Assistant configuration fields. When the comparison precision changes, the automatic confirmation count starts over so matches from the old precision are not treated as new evidence.

A successful automatic check is normally repeated after **one hour**. When a check fails or data is uncertain, it retries after **five minutes**. With the default settings, `sensor.rf1_pruefstatus` reports `review_due` after four hours of failed checks.

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

## Support and optional donations

For questions and bug reports, use the [GitHub issues](https://github.com/Thunder86/rf1-kontrollmessung/issues) page. Please include your app version, relevant log lines without secrets, and the result status.

The project is free. If it helped you, you can [make a voluntary PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are never required for use or support.

[German README](README.md) · [Changelog](rf1_ocr_test/CHANGELOG.md) · [App introduction (English)](rf1_ocr_test/README.en.md)
