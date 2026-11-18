# AI Meter Reader – Home Assistant App

[Deutsch](README.md) · [Project documentation (English)](../README.en.md)

**Local camera OCR and reference checks for Home Assistant.**

This Home Assistant app reads meter images locally with **Tesseract OCR** and can compare its reading with an existing reference. It supports configurable digit counts and sources such as **AI on the Edge / SLFork**, ESPHome, and Home Assistant cameras. It is currently best suited to mechanical meters with rolling digits.

This is an additional plausibility check, **not a certified measurement device**. OCR may be wrong. Read the physical meter for billing and legally relevant measurements. Private hobby project, no warranty or guaranteed support.

**Setup wizard:** The wizard guides you through the image source, meter format, crop, check interval and notifications. You can reopen it with saved values at any time. The maintainer has tested real meters only with AI on the Edge / SLFork; other modes have simulated tests only.

## Installation

**AI Meter Reader 0.6.9** is on the Stable channel. Starting calibration opens Overview with the setup steps visible. After seven digits are saved, Overview only shows a short background-check status for the optional eighth digit and preserves the normal automatic status.

Add **Add-ons by Eifellayer** under **Settings → Apps → Install app → ⋮ → Repositories** using the [Stable link](https://github.com/Eifellayer/meter-ocr#stable), then install **AI Meter Reader**. Set `esp_url` for SLFork, or configure `kamera_entitaet` and an optional `referenz_entitaet` sensor.

## Choose a language

Use **Sprache / Language** to follow your Home Assistant profile or select **Deutsch** or **English**. The app saves explicit choices per identified Ingress user. If the profile language is missing or unsupported, the app falls back to a supported browser language, then German.

## Automatic checks

The always-visible overview contains the most recent OCR result, reference, status, image time and next check. Automatic settings are persistent and can be changed in the web interface:

- **Comparison:** whole cubic meters or up to three decimal places. Values are rounded half up to the selected precision; the next known digit determines rounding.
- **Maximum OCR attempts:** 1–10 (default 5); stop on the first verified match.
- **Digit color:** auto-detect, light or dark.
- **Image region:** auto-detect digit frames or use a fixed image crop and width.

Saving automatic settings starts a check immediately. Changing the precision resets the automatic confirmation counter from that check. Five automatic confirmations in 24 hours are a separate target from the number of OCR attempts for a single image.

## Advanced manual test

**Save and check** opens the overview and starts the automatic check immediately. A yellow progress bar shows image capture and OCR attempts. Choose **Test your own image** to open the manual test with an upload. It lets you temporarily override all of the above settings and try a custom crop. **Run check now** uses the most recent image, or an optional uploaded JPG/PNG image (up to 3 MB); a live camera source captures a fresh still; an uploaded test image is used as-is.

The result appears below the progress indicator, using muted green only for a confirmed match, red for failures, and neutral styling while running or without a reference. It explains whether whole cubic meters or decimal places matched. The annotated image outlines digits the OCR recognized in green and unclear ones in red; red or green here does not establish agreement with the reference. The positions may be approximate without detected frames.

Expand **More details** to see the individual attempt readings. When a custom crop produces a preview, you can **Use tested crop for automatic checks** to permanently apply the crop settings you have tried.

## Schedules and files

Successful automatic checks run every 10 minutes by default. After a failed check, up to two more image checks follow at five-minute intervals. If all three fail, the app waits one hour for a higher reading or new image, then tries again. After a successful match, the selected interval applies again. If only the seventh of seven required digits is unclear, a valid reference and matching first six digits can partially verify that check at reduced precision without posting consumption. The app visibly explains that it is waiting 30 minutes for a higher reading; the configured precision applies again on the next check. The failed-check count and wait reason appear in the overview. The default delay for `review_due` is four hours. **Pause automatic checks** keeps a large yellow notice visible; manual tests still work. The overview shows whether the app is waiting, capturing an image, or reading it, and whether the ESP/camera returned an image or why it was stale. If the app is stopped or unreachable, an open page reports the lost connection. The **Notifications** panel controls Home Assistant notices, mobile push and email. See the [project guide](../README.en.md#notifications-and-automatic-status).

The app publishes `sensor.rf1_kontrollbild` and `sensor.rf1_pruefstatus`, and stores the latest/last-confirmed images in **Media → Local Media → rf1**. Neither entity name is translated because dashboards and automations depend on it.

Full options and troubleshooting: [Project documentation](../README.en.md).

Support: [GitHub Issues](https://github.com/Eifellayer/meter-ocr/issues). Optional donations are linked in the app under **About AI Meter Reader**.
