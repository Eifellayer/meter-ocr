"""Rules of the automatic check: defaults, loading the stored file, validating changes.

One place for the shape of ``auto-pruefregeln.json``. The functions are pure: they read no
file and keep no state, so they can be tested without the worker (0.5.0 restructuring).
"""

from datetime import datetime
import re

from calibration import DEFAULT_INTENSIVE_AGREEMENT, valid_intensive_agreement
from checks import (DEFAULT_FAILURE_PAUSE_MINUTES, DEFAULT_INTERVAL_MINUTES, MAX_FAILURE_PAUSE_MINUTES,
                    MIN_FAILURE_PAUSE_MINUTES, meter_prefix, valid_interval_minutes)
from consumption import (CALORIFIC_RANGE, CONVERSION_RANGE, DEFAULT_FLOW_LPH, MAX_FLOW_LPH, STATE_FACTOR_RANGE,
                         valid_energy_factor)
import experiments
from layout import crop_coordinates, digit_box_settings, fine_rotation as valid_fine_rotation


# Who placed the saved frames: the user by hand ("user") or the self-setup ("setup").
# Frames placed by hand are never moved by the automatic fine tuning (0.5.0).
FRAME_ORIGINS = ("user", "setup")
FRAME_KEYS = ("crop", "width", "rotation", "rotation_fine", "digit_boxes")


def user_frames(current, values):
    """``values`` as saved from the web interface: changed manual frames belong to the user."""
    if values.get("crop_mode", current.get("crop_mode")) != "manual":
        return values
    changed = (current.get("crop_mode") != "manual"
               or any(key in values and values[key] != current.get(key) for key in FRAME_KEYS))
    return {**values, "frames_origin": "user"} if changed else values


def frames_locked(rules):
    """Must the automatic leave the saved frames exactly as they are?"""
    return rules.get("crop_mode") == "manual" and rules.get("frames_origin") == "user"


def valid_experiments(value):
    """Only known experiments, each switched on or off."""
    value = value if isinstance(value, dict) else {}
    return {name: value.get(name) is True for name in experiments.EXPERIMENTS}


def default_rules(options):
    """Rules of a fresh installation, from the app options."""
    default_decimals = options["vergleich_nachkommastellen"]
    default_attempts = options["ocr_versuche"]
    return {"decimals": default_decimals, "attempts": default_attempts, "polarity": "auto",
                  "intensive_agreement": DEFAULT_INTENSIVE_AGREEMENT,
                  "precision_mode": default_decimals == 3, "fine_alignment_enabled": False, "adaptive_interval_enabled": True, "self_repair_enabled": False,
                  "experiments_enabled": False, "experiments": {},
                  "reflection_estimate_enabled": False, "reflection_suggestion_hidden": False,
            "quality_hint_hidden": False,
                  "reflection_confirmed_id": "",
                  "crop_mode": "auto", "crop": options["ausschnitt"],
                  "width": options["vorkomma_breite"], "rotation": 0, "crop_revision": "", "digit_boxes": [],
                  "max_flow_lph": DEFAULT_FLOW_LPH, "interval_minutes": DEFAULT_INTERVAL_MINUTES,
                  "integer_digits": 5, "fraction_digits": 3, "meter_display": "rollers",
                  "fallback_value": "", "fallback_time": "", "frames_origin": ""}


def stored_rules(saved_rules, options):
    """The stored rules with every field checked, or None when the file is unusable."""
    if (type(saved_rules.get("decimals")) is int and 0 <= saved_rules["decimals"] <= 3
            and type(saved_rules.get("attempts")) is int and 1 <= saved_rules["attempts"] <= 10):
        polarity = saved_rules.get("polarity", "auto")
        if polarity not in ("auto", "light", "dark"):
            polarity = "auto"
        crop_mode = saved_rules.get("crop_mode", "auto")
        crop_text = saved_rules.get("crop", options["ausschnitt"])
        width = saved_rules.get("width", options["vorkomma_breite"])
        rotation = saved_rules.get("rotation", 0)
        try:
            crop_coordinates(crop_text, width, rotation)
            if crop_mode not in ("auto", "manual"):
                raise ValueError("Ungültiger Ausschnittmodus")
        except ValueError:
            crop_mode, crop_text, width, rotation = (
                "auto", options["ausschnitt"], options["vorkomma_breite"], 0
            )
        max_flow = saved_rules.get("max_flow_lph", DEFAULT_FLOW_LPH)
        if type(max_flow) is not int or not 1 <= max_flow <= MAX_FLOW_LPH:
            max_flow = DEFAULT_FLOW_LPH
        interval_minutes = saved_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)
        if not valid_interval_minutes(interval_minutes):
            interval_minutes = DEFAULT_INTERVAL_MINUTES
        intensive_agreement = saved_rules.get("intensive_agreement", DEFAULT_INTENSIVE_AGREEMENT)
        if not valid_intensive_agreement(intensive_agreement):
            intensive_agreement = DEFAULT_INTENSIVE_AGREEMENT
        integer_digits = saved_rules.get("integer_digits", 5)
        if type(integer_digits) is not int or not 1 <= integer_digits <= 9:
            integer_digits = 5
        fraction_digits = saved_rules.get("fraction_digits", 3)
        if type(fraction_digits) is not int or not 0 <= fraction_digits <= 3:
            fraction_digits = 3
        meter_display = saved_rules.get("meter_display", "rollers")
        if meter_display not in ("rollers", "digital", "mixed"):
            meter_display = "rollers"
        decimals = min(saved_rules["decimals"], fraction_digits)
        fallback_value = saved_rules.get("fallback_value", "")
        fallback_time = saved_rules.get("fallback_time", "")
        if not isinstance(fallback_value, str) or not isinstance(fallback_time, str):
            fallback_value, fallback_time = "", ""
        if fallback_value:
            try:
                if (not re.fullmatch(r"[0-9]{1,9}(?:[.,][0-9]{1,3})?", fallback_value)
                        or meter_prefix(fallback_value, decimals, integer_digits) is None):
                    raise ValueError("Ungültiger Fallback")
                datetime.fromisoformat(fallback_time)
            except ValueError:
                fallback_value, fallback_time = "", ""
        else:
            fallback_time = ""
        try:
            digit_boxes = digit_box_settings(saved_rules.get("digit_boxes"), integer_digits + fraction_digits)
        except ValueError:
            digit_boxes = []
        return {"decimals": saved_rules["decimals"],
                      "attempts": saved_rules["attempts"], "polarity": polarity,
                      "crop_mode": crop_mode, "crop": crop_text, "width": width, "rotation": rotation,
                      "rotation_fine": (valid_fine_rotation(saved_rules.get("rotation_fine", 0))
                                        if crop_mode == "manual" else 0.0),
                      "digit_boxes": digit_boxes if crop_mode == "manual" else [],
                      "crop_revision": (str(saved_rules.get("crop_revision", ""))[:30]
                                        if crop_mode == "manual" else ""),
                      "max_flow_lph": max_flow, "interval_minutes": interval_minutes,
                      "failure_pause_minutes": (saved_rules.get("failure_pause_minutes")
                                                if type(saved_rules.get("failure_pause_minutes")) is int
                                                and MIN_FAILURE_PAUSE_MINUTES <= saved_rules["failure_pause_minutes"]
                                                <= MAX_FAILURE_PAUSE_MINUTES
                                                else DEFAULT_FAILURE_PAUSE_MINUTES),
                      "gas_state_factor": valid_energy_factor(saved_rules.get("gas_state_factor"),
                                                              STATE_FACTOR_RANGE),
                      "calorific_value": valid_energy_factor(saved_rules.get("calorific_value"),
                                                             CALORIFIC_RANGE),
                      "kwh_conversion_factor": valid_energy_factor(saved_rules.get("kwh_conversion_factor"),
                                                                   CONVERSION_RANGE),
                      "last_frame_relocated_at": (saved_rules.get("last_frame_relocated_at")
                                                  if type(saved_rules.get("last_frame_relocated_at")) in (int, float)
                                                  else None),
                      "integer_digits": integer_digits, "fraction_digits": fraction_digits,
                      "meter_display": meter_display, "fallback_value": fallback_value,
                      "precision_mode": saved_rules.get("precision_mode") is True or saved_rules["decimals"] == 3,
                      "calibration_reference": saved_rules.get("calibration_reference"),
                      "setup_completed": saved_rules.get("setup_completed"),
                      "setup_success": saved_rules.get("setup_success"),
                      "setup_input_source": saved_rules.get("setup_input_source"),
                      "setup_pending_source": saved_rules.get("setup_pending_source"),
                      "setup_pending_started": saved_rules.get("setup_pending_started"),
                      "setup_pending_metrics": saved_rules.get("setup_pending_metrics"),
                      "setup_reflection": saved_rules.get("setup_reflection"),
                      "frames_origin": (saved_rules.get("frames_origin") if crop_mode == "manual"
                                  and saved_rules.get("frames_origin") in FRAME_ORIGINS else ""),
                "stationary_partial_scope": saved_rules.get("stationary_partial_scope"),
                      "skew_seed": saved_rules.get("skew_seed") if isinstance(saved_rules.get("skew_seed"), dict) else None,
                      "intensive_agreement": intensive_agreement,
                      "fine_alignment_enabled": saved_rules.get("fine_alignment_enabled") is True,
                      "self_repair_enabled": saved_rules.get("self_repair_enabled") is True,
                      "adaptive_interval_enabled": saved_rules.get("adaptive_interval_enabled") is True,
                      "experiments_enabled": saved_rules.get("experiments_enabled") is True,
                      "experiments": valid_experiments(saved_rules.get("experiments")),
                      "reflection_estimate_enabled": saved_rules.get("reflection_estimate_enabled") is True,
                      "reflection_suggestion_hidden": saved_rules.get("reflection_suggestion_hidden") is True,
                "quality_hint_hidden": saved_rules.get("quality_hint_hidden") is True,
                      "reflection_confirmed_id": str(saved_rules.get("reflection_confirmed_id", ""))[:80],
                      "fallback_time": fallback_time, "decimals": decimals}
    return None


def changed_rules(auto_rules, values):
    """The current rules with ``values`` applied; ValueError names an invalid setting."""
    integer_digits = values.get("integer_digits", auto_rules["integer_digits"])
    fraction_digits = values.get("fraction_digits", auto_rules["fraction_digits"])
    meter_display = values.get("meter_display", auto_rules["meter_display"])
    fallback_value = values.get("fallback_value", auto_rules["fallback_value"])
    fallback_time = values.get("fallback_time", auto_rules["fallback_time"])
    precision_mode = values.get("precision_mode", auto_rules["precision_mode"])
    intensive_agreement = values.get("intensive_agreement", auto_rules["intensive_agreement"])
    if not valid_intensive_agreement(intensive_agreement):
        raise ValueError("Ungültige Übereinstimmung für die Intensivprüfung")
    self_repair = values.get("self_repair_enabled", auto_rules["self_repair_enabled"])
    fine_alignment = values.get("fine_alignment_enabled", auto_rules["fine_alignment_enabled"])
    adaptive_interval = values.get("adaptive_interval_enabled", auto_rules["adaptive_interval_enabled"])
    reflection_estimate_enabled = values.get("reflection_estimate_enabled", auto_rules["reflection_estimate_enabled"])
    reflection_suggestion_hidden = values.get("reflection_suggestion_hidden", auto_rules["reflection_suggestion_hidden"])
    reflection_confirmed_id = values.get("reflection_confirmed_id", auto_rules["reflection_confirmed_id"])
    if (type(values.get("decimals")) is not int or not 0 <= values["decimals"] <= fraction_digits
            or type(values.get("attempts")) is not int or not 1 <= values["attempts"] <= 10
            or values.get("polarity") not in ("auto", "light", "dark")
            or values.get("crop_mode") not in ("auto", "manual")
            or type(integer_digits) is not int or not 1 <= integer_digits <= 9
            or type(fraction_digits) is not int or not 0 <= fraction_digits <= 3
            or meter_display not in ("rollers", "digital", "mixed")
            or type(precision_mode) is not bool or type(fine_alignment) is not bool or type(adaptive_interval) is not bool or type(self_repair) is not bool
            or type(reflection_estimate_enabled) is not bool or type(reflection_suggestion_hidden) is not bool
            or not isinstance(reflection_confirmed_id, str) or len(reflection_confirmed_id) > 80
            or not isinstance(fallback_value, str) or not isinstance(fallback_time, str)):
        raise ValueError("Ungültige Einstellungen für die automatische Kontrolle")
    if fallback_value:
        if (not re.fullmatch(r"[0-9]{1,9}(?:[.,][0-9]{1,3})?", fallback_value)
                or meter_prefix(fallback_value, values["decimals"], integer_digits) is None):
            raise ValueError("Ungültiger Fallback-Zählerstand")
        try:
            datetime.fromisoformat(fallback_time)
        except ValueError as error:
            raise ValueError("Ungültige Ablesezeit für den Fallback") from error
    else:
        fallback_time = ""
    rotation = values.get("rotation", 0)
    coords = crop_coordinates(values["crop"], values["width"], rotation)
    max_flow = values.get("max_flow_lph", DEFAULT_FLOW_LPH)
    if type(max_flow) is not int or not 1 <= max_flow <= MAX_FLOW_LPH:
        raise ValueError("Ungültiger maximaler Durchfluss")
    interval_minutes = values.get("interval_minutes", auto_rules["interval_minutes"])
    if not valid_interval_minutes(interval_minutes):
        raise ValueError("Ungültiges Prüfintervall")
    updated_rules = {**auto_rules, **values, "rotation": rotation,
                     "rotation_fine": valid_fine_rotation(values.get("rotation_fine", auto_rules.get("rotation_fine", 0))),
                     "max_flow_lph": max_flow,
                     "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                     "fraction_digits": fraction_digits, "meter_display": meter_display,
                     "precision_mode": precision_mode, "fine_alignment_enabled": fine_alignment,
                     "adaptive_interval_enabled": adaptive_interval, "self_repair_enabled": self_repair,
                     "experiments_enabled": values.get("experiments_enabled", auto_rules.get("experiments_enabled")) is True,
                     "experiments": valid_experiments(values.get("experiments", auto_rules.get("experiments"))),
                     "reflection_estimate_enabled": reflection_estimate_enabled,
                     "reflection_suggestion_hidden": reflection_suggestion_hidden,
                     "quality_hint_hidden": values.get("quality_hint_hidden", auto_rules.get("quality_hint_hidden")) is True,
                     "reflection_confirmed_id": reflection_confirmed_id,
                     "fallback_value": fallback_value, "fallback_time": fallback_time}
    updated_rules["crop"] = ",".join(str(part) for part in coords)
    if updated_rules["crop_mode"] != "manual" or updated_rules.get("frames_origin") not in FRAME_ORIGINS:
        updated_rules["frames_origin"] = ""
    updated_rules["digit_boxes"] = (digit_box_settings(updated_rules.get("digit_boxes"), integer_digits + fraction_digits)
                                    if updated_rules["crop_mode"] == "manual" else [])
    if (updated_rules["crop_revision"] == auto_rules["crop_revision"]
            and any(updated_rules[key] != auto_rules[key] for key in ("crop_mode", "crop", "rotation", "width", "digit_boxes"))):
        updated_rules["crop_revision"] = ""
    return updated_rules


# Settings that only change what the page shows. They never restart a check and must not
# cancel a running setup (0.5.1: hiding the picture-quality hint during a setup cancelled it).
VIEW_PREFERENCES = ("reflection_suggestion_hidden", "reflection_confirmed_id", "quality_hint_hidden")


def only_view_changed(before, after):
    """True when the two rule sets differ in nothing but view preferences."""
    keys = set(before) | set(after)
    return all(before.get(key) == after.get(key) for key in keys if key not in VIEW_PREFERENCES)


def carry_view_preferences(configuration, rules):
    """The remembered setup configuration ``(rules, source)`` with the current view preferences.

    A running setup compares its configuration with the current one and stops when they
    differ. View preferences are taken over so that changing one is not a difference.
    """
    if configuration is None:
        return None
    remembered, source = configuration
    return {**remembered, **{key: rules[key] for key in VIEW_PREFERENCES if key in rules}}, source
