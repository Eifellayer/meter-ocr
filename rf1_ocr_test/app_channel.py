"""Keep the test app's Home Assistant resources distinct from the regular app."""

import os

IS_BETA = os.environ.get("METER_OCR_CHANNEL") == "beta"
APP_NAME = "Meter OCR Beta" if IS_BETA else "Meter OCR"
NAMESPACE = "meter_ocr_beta" if IS_BETA else "rf1"
LABEL_SUFFIX = " (Beta)" if IS_BETA else ""
CHECK_ENTITY = f"sensor.{NAMESPACE}_pruefstatus"
