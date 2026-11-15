# Gas Meter OCR Verification for Home Assistant

**An independent, local, image-based second check of camera-read mechanical gas meters.**

[Deutsch / German](README.md) · [English](README.en.md)

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

## Language selection

The web interface offers **Deutsch / English** at the top. Switching language also translates the automatic check settings, manual test, progress updates, OCR results, and diagnostic hints. The language choice is kept in the browser. German remains the default for German-language browsers, and English for English-language browsers.

The language only changes what is shown in the web interface. It does not rename existing Home Assistant entities or modify stored readings.

## Automatic verification

The main screen shows the last recognized value, reference value, verification result, image timestamp, and next scheduled check. The automatic settings can be saved directly in the web interface:

| Setting | Purpose |
| --- | --- |
| Comparison | Whole cubic meters only or 1–3 decimal places |
| Max. OCR attempts | 1–10 profiles per image, default 5 |
| Digit color | Automatic detection, light digits, or dark digits |
| Image region | Automatically detect frames, or use a fixed crop and whole-digit width |

Saved automatic rules persist across app restarts. They take precedence over the corresponding Home Assistant configuration fields. When the comparison precision changes, the automatic confirmation count starts over so matches from the old precision are not treated as new evidence.

A successful automatic check is normally repeated after **one hour**. When a check fails or data is uncertain, it retries after **five minutes**. After four hours without a successful confirmation, `sensor.rf1_pruefstatus` can report `review_due`; an optional mobile notification is available later.

## Advanced manual test

The **Open manual test** section is collapsed by default. Open it only when you want to diagnose the camera image.

You can independently select digit color, comparison precision, maximum OCR attempts, and a custom crop (`left, top, right, bottom`) with the width of the whole-number digit region. Press **Run check now** to re-evaluate the latest stored image. This does not trigger a new ESP capture and does not increase the automatic confirmation count.

The status is neutral while a test runs, subtly **green only for a confirmed match**, and red for failed checks. The result explicitly states the comparison precision.

Afterward, the **annotated OCR image** outlines recognized digits in green and uncertain digits in red. These colors indicate OCR recognition, **not** reference-value agreement. When individual digit frames are unavailable, boxes are approximate. **More details** shows the OCR values from each attempt and, where possible, the uncertain digit positions.

After testing a custom crop, use **Use tested crop for automatic checks** to save the crop and whole-digit width directly without copying coordinates to another settings page.

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
| `push_dienst` | Optional `notify.mobile_app_…` service |

Existing entity IDs remain **`sensor.rf1_kontrollbild`** and **`sensor.rf1_pruefstatus`**. Check images are stored in **Media → Local Media → rf1**.

## Support and optional donations

For questions and bug reports, use the [GitHub issues](https://github.com/Thunder86/rf1-kontrollmessung/issues) page. Please include your app version, relevant log lines without secrets, and the result status.

The project is free. If it helped you, you can [make a voluntary PayPal donation](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8). Donations are never required for use or support.

[German README](README.md) · [Changelog](rf1_ocr_test/CHANGELOG.md) · [App introduction (English)](rf1_ocr_test/README.en.md)
