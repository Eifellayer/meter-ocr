"""Which rollers a routine check has to read (0.5.0, idea Stefan 21.11.2026).

The first three digits of a meter change only when the fourth rolls over (every 100 m³).
Once a complete read confirmed them they are taken over from the last reading instead of
being read again. A complete control read follows at the latest after ten checks or one hour,
after every failed check, before a roll-over of the fourth digit and after changed frames.
Nothing is stored on disk: after a restart the first check reads everything.
"""

SUCCESSFUL = ("match", "match_with_warning", "ocr_only")
ASSUMED_DIGITS = 3
FULL_READ_EVERY = 10          # every tenth check reads all rollers ...
FULL_READ_SECONDS = 60 * 60   # ... and so does the first check after an hour
FULL_READS_AFTER_FAILURE = 3  # complete reads in a row before digits are taken over again


def assumed_prefix(state, rules, counter, now):
    """The leading digits to take over from the confirmed reading, or "" to read everything."""
    digits = rules["integer_digits"]
    if (digits < ASSUMED_DIGITS + 2 or rules.get("crop_mode") != "manual" or not rules.get("digit_boxes")
            or state.get("revision") != rules.get("crop_revision") or state.get("strict", 1) > 0
            or state.get("count", 0) >= FULL_READ_EVERY - 1
            or now - state.get("time", 0) >= FULL_READ_SECONDS):
        return ""
    litres = counter.get("reading_litres") if isinstance(counter, dict) else None
    if type(litres) is not int or litres < 0:
        return ""
    whole = str(litres // 1000).zfill(digits)
    # At 9 the fourth digit is about to carry into the third: read everything until it has.
    # (After the carry the prefix differs from the confirmed one, which also forces a full read.)
    if len(whole) != digits or whole[ASSUMED_DIGITS] == "9" or state.get("whole") != whole[:ASSUMED_DIGITS]:
        return ""
    return whole[:ASSUMED_DIGITS]


def after_check(state, rules, outcome, assumed, reading, now):
    """The state for the next check: ``assumed`` is what this check took over ("" for a full read)."""
    revision = rules.get("crop_revision")
    if outcome not in SUCCESSFUL:
        return {"strict": FULL_READS_AFTER_FAILURE, "revision": revision}
    if assumed:
        return {**state, "count": state.get("count", 0) + 1}
    whole = str(reading or "").replace(",", ".").partition(".")[0]
    confirmed = len(whole) == rules["integer_digits"] and whole.isdigit()
    strict = state.get("strict", 1) if state.get("revision") == revision else 1
    return {"strict": max(0, strict - 1) if confirmed else max(1, strict), "revision": revision,
            "count": 0, "time": now, "whole": whole[:ASSUMED_DIGITS] if confirmed else None}
