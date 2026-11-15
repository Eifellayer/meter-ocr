# Meter OCR – Home Assistant App

[Deutsch](README.md) · [Project documentation (English)](../README.en.md)

**Local camera OCR and reference checks for Home Assistant.**

This Home Assistant app takes the latest available gas meter image from **AI on the Edge / SLFork**, or from a compatible Home Assistant camera, reads the digits again with **Tesseract OCR**, and optionally compares the result with an existing reference reading. Designed for the **Pipersberg G4 RF1**.

This is an additional plausibility check, **not a certified measurement device**. OCR may be wrong. Read the physical meter for billing and legally relevant measurements. Private hobby project, no warranty or guaranteed support.

## Installation

**Meter OCR** is the regular app. **Meter OCR Beta** is the test app in the same repository.

Add `https://github.com/Eifellayer/meter-ocr` under **Settings → Apps → Install app → ⋮ → Repositories**, then install **Meter OCR**. Set `esp_url` for SLFork, or configure `kamera_entitaet` and an optional `referenz_entitaet` sensor.

## Choose a language

Use **Sprache / Language** to follow your Home Assistant profile or select **Deutsch** or **English**. The app saves explicit choices per identified Ingress user. If the profile language is missing or unsupported, the app falls back to a supported browser language, then German.

## Automatic checks

The always-visible overview contains the most recent OCR result, reference, status, image time and next check. Automatic settings are persistent and can be changed in the web interface:

- **Comparison:** whole cubic meters or up to three decimal places. Decimals outside the configured precision are ignored, not rounded.
- **Maximum OCR attempts:** 1–10 (default 5); stop on the first verified match.
- **Digit color:** auto-detect, light or dark.
- **Image region:** auto-detect digit frames or use a fixed image crop and width.

Changing the precision resets the automatic confirmation counter from the next check. Five automatic confirmations in 24 hours are a separate target from the number of OCR attempts for a single image.

## Advanced manual test

Open **Open manual test** only when you need it. It lets you temporarily override all of the above settings and try a custom crop. **Run check now** reads the most recent image; it does not request a new capture.

The result appears below the progress indicator, using muted green only for a confirmed match, red for failures, and neutral styling while running or without a reference. It explains whether whole cubic meters or decimal places matched. The annotated image outlines digits the OCR recognized in green and unclear ones in red; red or green here does not establish agreement with the reference. The positions may be approximate without detected frames.

Expand **More details** to see the individual attempt readings. When a custom crop produces a preview, you can **Use tested crop for automatic checks** to permanently apply the crop settings you have tried.

## Schedules and files

Successful automatic checks normally run hourly; errors and uncertain readings cause five-minute retries. The default delay for `review_due` is four hours. The **Notifications** panel controls Home Assistant notices, mobile push and email. See the [project guide](../README.en.md#notifications-and-automatic-status).

The app publishes `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus`, and stores the latest/last-confirmed images in **Media → Local Media → rf1**. Neither entity name is translated because dashboards and automations depend on it.

Full options and troubleshooting: [Project documentation](../README.en.md).

Support: [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues). Optional voluntary donation: [PayPal](https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8).
