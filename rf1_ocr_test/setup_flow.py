"""Self-setup: deciding what kind of search a request starts and building its job.

Taken out of ``run.main()`` for 0.5.0. The worker keeps the lock, the running job and the
camera; this module only turns "start a setup" into a prepared ``Calibration``.
"""

from calibration import Calibration, MAX_ATTEMPTS, TIME_LIMIT
from checks import setup_source_id, stationary_partial_active, timestamp_epoch
from consumption import accumulate_consumption
from source_settings import source_check_key
from meter_learning import GEOMETRY_REPAIR_LIMIT, GEOMETRY_REPAIR_SECONDS
from setup_store import last_verified_configured_geometry, plain_setup


def job_kind(rules, action):
    """(plain two-decimal setup?, search for the last digit only?) for ``action``."""
    # A repair confirms the frames with two decimals like a plain setup: the third
    # roller (glare, always turning) must not keep a moved camera from being found again.
    # 0.4.3: a setup that compares two decimals is the same plain setup. Before, only
    # three compared decimals got it; with two (the default after a factory reset) the
    # setup ran the strict path without the 0.4.2 corrections and never confirmed.
    # 0.4.4: and so is every setup of a meter with three decimal rollers, whatever
    # precision the routine checks compare (0 demanded all three decimals here).
    simplified = plain_setup(rules, action)
    intensive = action in ("intensive", "relocate_last")
    if intensive and (rules["fraction_digits"] != 3 or rules["decimals"] != 3):
        raise ValueError("The meter must display three decimal digits")
    return simplified, intensive


def marked_reflection(rules, source, store):
    """The frame and roller positions the user marked as hidden by glare, or (None, ())."""
    marked = rules.get("setup_reflection")
    if (rules["reflection_estimate_enabled"]
            and isinstance(marked, dict) and marked.get("source") == setup_source_id(source)):
        try:
            layout = store.geometry_layout(marked, rules)
            positions = tuple(marked["positions"])
            if (layout.digit_boxes and 1 <= len(positions) <= 2
                    and all(type(index) is int and 0 <= index < len(layout.digit_boxes)
                            for index in positions)):
                return layout, positions
        except (ValueError, TypeError, KeyError):
            pass
    return None, ()


def new_job(action, limit, region, configuration, history, store, previous, now, *, simplified, intensive, make=Calibration):
    """A prepared search job and the remembered good frame it starts from (or None).

    ``configuration`` is (rules, (source, setup pending)) as the worker compares it between runs.
    """
    rules, (source, _) = configuration
    repair = action == "repair"
    scope = store.candidate_scope(configuration, region, simplified, intensive)
    # A new setup starts without the frames of earlier runs: after the camera was
    # moved they only read rubbish first and were even chosen again.
    shortlist = {} if repair or action == "setup" else store.load_calibration_candidates(scope, rules)
    known_good = store.load_known_good_layout(rules, source)
    if known_good is None:
        verified_geometry = last_verified_configured_geometry(history, rules, source_check_key(source))
        if verified_geometry:
            known_good = store.geometry_layout(verified_geometry, rules)
    if intensive:
        previous = store.geometry_layout(rules, rules) if rules["crop_mode"] == "manual" else known_good
        if previous is None:
            raise ValueError("A saved crop is required for the last digit")
    reflected_layout, reflected_positions = (
        (None, ()) if repair or intensive else marked_reflection(rules, source, store))
    background = intensive and (action == "relocate_last" or stationary_partial_active(rules, source))
    job = make(limit=limit, started=now, automatic=repair,
                rank_candidates=not (repair or intensive), shortlist=shortlist,
                      simplified=simplified, intensive=intensive,
                      background=background, followup=background,
                      purpose="relocate" if action == "relocate_last" else "",
                      duration=GEOMETRY_REPAIR_SECONDS if repair else TIME_LIMIT,
                      attempt_limit=GEOMETRY_REPAIR_LIMIT if repair else MAX_ATTEMPTS,
                      previous_layout=previous, region=region,
                      known_good_layout=reflected_layout or known_good,
                      reflected_layout=reflected_layout, reflected_positions=reflected_positions)
    return job, known_good


def reading_baseline(history, source_key, captured, followup, active_rules, precision, zone):
    """The last known meter reading a setup image must not fall below, or None.

    In this order: the confirmed consumption of this source, the reading an earlier part of
    the same setup handed over, the reading the user typed in.
    """
    baseline = history.get("consumption", {})
    if baseline.get("source") == source_key and baseline.get("timestamp", 0) < captured:
        baseline = {**baseline, "source": "calibration"}
    else:
        baseline = None
    if baseline is None and followup:
        baseline = followup
    if baseline is None and active_rules["fallback_value"] and active_rules["fallback_time"]:
        stamp = timestamp_epoch(active_rules["fallback_time"], zone)
        if stamp < captured:
            baseline = accumulate_consumption(
                {}, "calibration", stamp, active_rules["fallback_value"], precision,
                active_rules["max_flow_lph"], active_rules["integer_digits"], confirmed=True,
            )
    return baseline
