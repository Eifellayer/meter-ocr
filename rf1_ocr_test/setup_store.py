"""Self-setup: what is stored between runs and the rules that decide how a setup starts.

Taken out of ``run.main()`` for 0.5.0 so that the setup can be changed and tested without
the worker loop. Nothing here talks to the camera or to Home Assistant.
"""

import hashlib
import json
import os
from pathlib import Path
import time

from calibration import Layout, SHORTLIST_LIMIT
from checks import (SUCCESSFUL_CHECKS, setup_deadlines, setup_source_id, setup_tilt, without_light)
import debug_log
from layout import crop_coordinates, digit_box_settings, fine_rotation as valid_fine_rotation

SETUP_RETRY_SECONDS = 300
SETUP_RETRY_LIMIT = 3
# After the quick retries the setup keeps trying hourly, so a later fix at the camera
# (focus, glare) is picked up without anyone tapping a button.
SETUP_RETRY_LONG_SECONDS = 3600


def geometry_check_key(rules, source_key):
    return [source_key, rules["crop_mode"], rules["crop"], rules["rotation"], rules["width"],
            rules["integer_digits"], rules["fraction_digits"], rules["crop_revision"]]


def last_verified_configured_geometry(history, rules, source_key):
    """Recover an existing saved crop only when history corroborates its revision."""
    recorded = history.get("geometry_recovery", {})
    if (rules["crop_mode"] == "manual" and rules["crop_revision"]
            and history.get("check_status") in ("match", "ocr_only")
            and not history.get("ocr_rotation_adjustment")
            and recorded.get("key") == geometry_check_key(rules, source_key)
            and recorded.get("stamp") == history.get("last_epoch")
            and recorded.get("failures") == 0):
        return rules
    return None


def usable_known_good_geometry(saved, scopes, digits):
    """The remembered frame if it fits this camera and digit count, else None.

    A file from 0.2.9 or older ("camera" missing) was keyed on settings that do not move
    the digits (source mode, reference sensor, display style). It is still offered as the
    starting point when the digit count matches; the setup checks it on fresh images
    before anything is saved (20.11.).
    """
    if not isinstance(saved, dict) or not isinstance(saved.get("geometry"), dict):
        return None
    if saved.get("scope") in scopes:
        return saved["geometry"]
    if "camera" not in saved and len(saved["geometry"].get("digit_boxes") or ()) == digits:
        return saved["geometry"]
    return None


def calibration_source_id(source):
    return hashlib.sha256(json.dumps(without_light(source), sort_keys=True).encode()).hexdigest()


def setup_retry_delay(count):
    """Seconds until the next automatic setup restart after `count` earlier restarts."""
    return SETUP_RETRY_SECONDS if count < SETUP_RETRY_LIMIT else SETUP_RETRY_LONG_SECONDS


def app_build():
    """Identify the installed app version; changes with every update."""
    version = os.environ.get("BUILD_VERSION", "").strip()
    if version:
        return version
    try:
        return hashlib.sha256(Path(__file__).with_name("run.py").read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def plain_setup(rules, action):
    """Does this job confirm the frames with two decimals (the plain setup)?

    The comparison precision is a rule for the routine checks. A setup must not ask for more
    than they do: with "whole cubic metres" (0) and no reference it demanded all three decimals,
    including the fast last roller, and never confirmed (0.4.4).
    """
    return action in ("setup", "start", "repair") and (
        rules["fraction_digits"] == 3 or rules["decimals"] in (2, 3))


def setup_autostart_due(history, build, job, attempted):
    """Restart an unfinished setup once per installed version, without user interaction.

    Only after a setup was started before; choosing a source alone does not start one.
    """
    return job is None and bool(build) and history.get("setup_autostart_build") != build and attempted()


def setup_attempted_before():
    try:
        return '"kind": "setup_' in debug_log.read_text(debug_log.MAX_ENTRIES)
    except (OSError, ValueError):
        return False


def last_setup_unfinished(text=None):
    """True if the newest user/update setup ran out of time or failed and nothing read since.

    Then a new version restarts the setup on its own after the update, even though an older
    frame is still stored (setup timed out, automatic read only "?????.9??").
    """
    try:
        lines = (debug_log.read_text(debug_log.MAX_ENTRIES) if text is None else text).splitlines()
    except (OSError, ValueError):
        return False
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("kind")
        if kind == "automatic" and entry.get("outcome") in SUCCESSFUL_CHECKS:
            return False
        if kind == "setup_start" and entry.get("trigger") in ("user", "update", "retry"):
            return False
        if kind == "setup_end" and entry.get("purpose") == "setup":
            return entry.get("state") in ("timeout", "failed")
    return False


def saved_layout_rules(rules, source, attempt, layout, tilts, *, provisional=False, verified=False, reflected=False):
    """The rules to store when a setup saves ``layout`` (frame, angle, setup bookkeeping)."""
    reference = rules.get("calibration_reference") if attempt.intensive else None
    if not provisional and attempt.reference_reading is not None:
        precision = {1: 3, 10: 2, 100: 1, 1000: 0}[attempt.counter["step_litres"]]
        head, _, fraction = attempt.reference_reading.replace(",", ".").partition(".")
        reading = f"{head}.{fraction[:precision]}" if precision else head
        reference = {
            "reading": reading, "time": attempt.counter["timestamp"], "precision": precision,
            "source": calibration_source_id(source), "integer_digits": rules["integer_digits"],
            "image_id": attempt.reference_image_id,
        }
    completed = rules.get("setup_completed")
    previous_completion, _ = setup_deadlines(rules, source)
    finished = time.time()
    elapsed = max(0, round(time.monotonic() - attempt.started))
    metrics = {"frames_tested": attempt.attempts, "images_checked": len(attempt.seen)}
    success = rules.get("setup_success")
    if verified and (not attempt.intensive or attempt.setup_last_digit) and not attempt.automatic and reference:
        success = {"source": setup_source_id(source), "time": finished, "duration_seconds": elapsed, **metrics}
        if not previous_completion:
            completed = success
    revision = str(time.time_ns())
    # 0.5.14 (B7): a setup saved with a reflection also starts with two
    # decimals; the last roller is searched later in the background like after every setup.
    partial = provisional or reflected or verified and attempt.simplified
    partial_scope = calibration_source_id([source, revision]) if partial else None
    pending_source = setup_source_id(source) if provisional else rules.get("setup_pending_source")
    pending_started = finished - elapsed if provisional else rules.get("setup_pending_started")
    pending_metrics = metrics if provisional else rules.get("setup_pending_metrics")
    fine = rules.get("rotation_fine", 0.0) if layout.settings().get("rotation") == rules.get("rotation") else 0.0
    # Fine angle within ±0.5°; the rest of the measured tilt seeds the routine correction.
    fine, seed = setup_tilt(tilts, fine)
    saved_geometry = layout.settings()
    skew_seed = {"key": [saved_geometry["crop"], saved_geometry["width"], saved_geometry["rotation"],
                         valid_fine_rotation(fine)], "offset": seed}
    relocated = {"last_frame_relocated_at": time.time()} if attempt.purpose == "relocate" and not provisional else {}
    return {**rules, **layout.settings(), **relocated, "rotation_fine": valid_fine_rotation(fine),
                     "crop_revision": revision, "skew_seed": skew_seed, "frames_origin": "setup",
                     "setup_input_source": setup_source_id(source),
                     "calibration_reference": reference, "stationary_partial_scope": partial_scope,
                     "setup_completed": completed, "setup_success": success,
                     "setup_pending_source": None if completed else pending_source,
                     "setup_pending_started": None if completed else pending_started,
                     "setup_pending_metrics": None if completed else pending_metrics}


class SetupStore:
    """The remembered good frame and the shortlist of frame candidates on disk."""

    def __init__(self, known_good_path, candidates_path, write):
        self.known_good_path, self.candidates_path, self.write = known_good_path, candidates_path, write

    def known_good_scope(self, rules, source):
        # Only what moves the digits in the picture: which camera and how many digits.
        # Source mode, reference sensor, light, polarity or display style do not, and a
        # changed setting there must not throw away a frame that read for hours (20.11.).
        camera = source.get("camera") or str(source.get("url") or "").rstrip("/")
        return calibration_source_id(["known-good", camera, rules["integer_digits"], rules["fraction_digits"]])

    def legacy_known_good_scope(self, rules, source):
        format_keys = ("integer_digits", "fraction_digits", "meter_display", "polarity")
        return calibration_source_id([source, [rules[key] for key in format_keys]])

    def geometry_layout(self, geometry, rules):
        box = crop_coordinates(geometry["crop"], geometry["width"], geometry["rotation"])
        boxes = digit_box_settings(geometry["digit_boxes"], rules["integer_digits"] + rules["fraction_digits"])
        return Layout(box, geometry["rotation"], geometry["width"], tuple(map(tuple, boxes)))

    def load_known_good_layout(self, rules, source):
        try:
            saved = json.loads(self.known_good_path.read_text(encoding="utf-8"))
            geometry = usable_known_good_geometry(
                saved, (self.known_good_scope(rules, source), self.legacy_known_good_scope(rules, source)),
                rules["integer_digits"] + rules["fraction_digits"])
            if geometry is not None:
                return self.geometry_layout(geometry, rules)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
        return None

    def remember_known_good_layout(self, rules, source, layout):
        if layout == self.load_known_good_layout(rules, source):
            return
        camera = source.get("camera") or str(source.get("url") or "").rstrip("/")
        saved = {"scope": self.known_good_scope(rules, source), "camera": camera, "geometry": layout.settings()}
        try:
            self.write(self.known_good_path, json.dumps(saved).encode(), 0o600)
        except OSError:
            print("Der bestätigte Rahmen konnte nicht als Ausgangspunkt gespeichert werden.")

    def candidate_scope(self, configuration, region, simplified, intensive):
        rules, source = configuration
        relevant = ("integer_digits", "fraction_digits", "decimals", "polarity", "meter_display")
        # The app version belongs to the scope: frames found by an older version are not reused.
        key = [without_light(source), [rules[name] for name in relevant], region, simplified, intensive, app_build()]
        return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()

    def load_calibration_candidates(self, scope, rules):
        try:
            saved = json.loads(self.candidates_path.read_text(encoding="utf-8"))
            if saved["scope"] != scope:
                return {}
            result = {}
            for item in saved["candidates"][:SHORTLIST_LIMIT]:
                geometry, score = item["geometry"], item["score"]
                if (len(score) not in (2, 3) or type(score[0]) is not int or not 0 <= score[0] <= 100
                        or type(score[1]) not in (int, float) or not 0 <= score[1] <= 255
                        or (len(score) == 3 and (type(score[2]) is not int or not score[0] <= score[2] <= 100))):
                    continue
                result[self.geometry_layout(geometry, rules)] = tuple(score)
            return result
        except (OSError, ValueError, TypeError, KeyError):
            return {}

    def save_calibration_candidates(self, scope, shortlist):
        candidates = [{"geometry": layout.settings(), "score": score} for layout, score in shortlist.items()]
        self.write(self.candidates_path,
                     json.dumps({"scope": scope, "candidates": candidates}).encode(), 0o600)
