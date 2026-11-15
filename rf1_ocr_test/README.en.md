# Meter OCR – Home Assistant App

[Deutsch](README.md) · [Project documentation (English)](../README.en.md)

**Local camera OCR and reference checks for Home Assistant.**

This Home Assistant app takes the latest available gas meter image from **AI on the Edge / SLFork**, or from a compatible Home Assistant camera, reads the digits again with **Tesseract OCR**, and optionally compares the result with an existing reference reading. Designed for the **Pipersberg G4 RF1**.

This is an additional plausibility check, **not a certified measurement device**. OCR may be wrong. Read the physical meter for billing and legally relevant measurements. Private hobby project, no warranty or guaranteed support.

## Installation

This app is in beta.

Add `https://github.com/Eifellayer/meter-ocr` under **Settings → Apps → Install app → ⋮ → Repositories**, then install **Meter OCR**. Set `esp_url` for SLFork, or configure `kamera_entitaet` and an optional `referenz_entitaet` sensor.

## Choose a language

Use **Sprache / Language** to follow your Home Assistant profile or select **Deutsch** or **English**. The app saves explicit choices per identified Ingress user. If the profile language is missing or unsupported, the app falls back to a supported browser language, then German.

## Automatic checks

The overview shows the latest OCR result, reference, image time, last automatic check and last confirmed match. Save the following options under **Settings → Automatic checks**.

- **Check interval:** 1–1,440 minutes after success, default 60.
- **Comparison:** whole cubic meters or up to three decimal places. Decimals outside the configured precision are ignored, not rounded.
- **Maximum OCR attempts:** 1–10 (default 5); stop on the first verified match.
- **Digit color:** auto-detect, light or dark.
- **Image region:** auto-detect digit frames or use a fixed image crop and width.

Changing the precision resets the automatic confirmation counter from the next check. Five automatic confirmations in 24 hours are a separate target from the number of OCR attempts for a single image.

## Manual test

Select **Start test** to read the latest available image. Open **Test settings** to adjust the crop, comparison precision, digit color or attempts for this test.

The result appears below the progress indicator. Green marks a confirmed match and yellow marks a mismatch or uncertainty. The preview uses green outlines for recognized digits and red for unclear digits. The positions are approximate when the image has no detectable frames.

Expand **More details** to see the individual attempt readings. When a custom crop produces a preview, you can **Use tested crop for automatic checks** to permanently apply the crop settings you have tried.

## Schedules and files

Successful checks repeat after 60 minutes by default. Failed checks retry within five minutes. Yellow notices show details after an hour of failed checks, including the known time of an ESP fallback reading. The default delay for `review_due` is four hours. **Notifications** controls Home Assistant notices, mobile push and email. [Project guide](../README.en.md#notifications-and-automatic-status)

The app publishes `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus`, and stores the latest/last-confirmed images in **Media → Local Media → rf1**. Neither entity name is translated because dashboards and automations depend on it.

Full options and troubleshooting: [Project documentation](../README.en.md).

Support: [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues). Optional voluntary donation: [PayPal](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8).
