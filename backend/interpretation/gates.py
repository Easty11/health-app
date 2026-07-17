"""Gate arithmetic for the foundation producer — pure functions, no I/O.

Three mechanical questions per marker:
  delta       — how did it move vs the prior draw?
  news_gate   — gate 1, delta arm ONLY (raw; 4b may append relation basis and demote)
  range_gate  — gate 2, driven by the LAB flag; computed_flag is withheld (V2)

The one deliberate asymmetry, both faces of it recorded here:
  * range_gate.is_out_of_range reads `lab_flag` — a lab-asserted breach — and
    NEVER computes from bounds (computed_flag is withheld per contract V2).
  * delta.crossed_ref DOES compute from per-report bounds, because it is a
    prior->current TRANSITION, not a point-in-time breach assertion; a lab flag
    on a single draw cannot express "was out, now in".
So bounds decide crossed_ref; the lab flag decides the breach. They are
different questions and use different inputs by design.
"""
from __future__ import annotations

import json
from pathlib import Path

from reads.labs_reads import LabRow

_LEVER_DICTIONARY_PATH = Path(__file__).resolve().parent.parent / "reference" / "lever_dictionary.json"

# A lab_flag value that does NOT assert a breach. Any other non-null flag (H, L,
# HH, *, A, ...) is treated as the lab asserting out-of-range.
_NON_BREACH_FLAGS = {"", "N", "NORMAL"}


def _load_lever_dictionary() -> dict:
    with open(_LEVER_DICTIONARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_LEVER_DICTIONARY = _load_lever_dictionary()


def min_meaningful_delta(marker_canonical: str | None, dictionary: dict | None = None) -> dict:
    """The authored per-marker read-constant, projected to {mode, value}, or the
    conservative default.

    Reads ONLY `marker_interpretation[m].min_meaningful_delta` and `_defaults`
    — never `levers[]` (that is 4b's asset surface). An authored entry whose
    `value` is null (e.g. `ast` — "CVi unverified") falls back exactly as its
    own note instructs. `evidence_refs`/`note` are asset citation payload and
    are NOT part of a delta, so they are projected away.
    """
    d = dictionary if dictionary is not None else _LEVER_DICTIONARY
    entry = d.get("marker_interpretation", {}).get(marker_canonical or "", {}).get("min_meaningful_delta")
    if not entry or entry.get("value") is None:
        entry = d["_defaults"]["min_meaningful_delta_fallback"]
    return {"mode": entry["mode"], "value": entry["value"]}


def _in_range(row: LabRow) -> bool | None:
    """Is the value inside the per-report reference interval? None = undecidable
    (no value, or no bounds). Honours the exclusive-bound flags. Used ONLY for
    crossed_ref — never for the breach assertion."""
    if row.value_num is None:
        return None
    if row.ref_low is None and row.ref_high is None:
        return None
    if row.ref_low is not None:
        if row.ref_low_exclusive:
            if not row.value_num > row.ref_low:
                return False
        elif not row.value_num >= row.ref_low:
            return False
    if row.ref_high is not None:
        if row.ref_high_exclusive:
            if not row.value_num < row.ref_high:
                return False
        elif not row.value_num <= row.ref_high:
            return False
    return True


def range_gate(row: LabRow) -> dict:
    """Gate 2 — driven by the LAB flag, pure. is_out_of_range is true iff the
    lab asserted a breach flag. computed_flag is never read (withhold-computed,
    V2). `flag` echoes lab_flag verbatim."""
    flag = row.lab_flag
    is_out = flag is not None and flag.strip().upper() not in _NON_BREACH_FLAGS
    return {"is_out_of_range": is_out, "flag": flag}


def delta(current: LabRow, prior: LabRow | None) -> dict | None:
    """How the marker moved. None on a first observation (prior absent).

    Censored (either draw carries a `<`/`>` operator): the true magnitude is
    unknown, so abs/pct are null, min_meaningful_delta is omitted, and magnitude
    collapses to within_noise (or meaningful if a bound was crossed — crossed_ref
    is a bounds comparison, still computable). Equal censored bounds ->
    direction "flat".
    """
    if prior is None:
        return None

    censored = bool(current.value_operator or prior.value_operator)

    direction = "flat"
    if current.value_num is not None and prior.value_num is not None:
        if current.value_num > prior.value_num:
            direction = "up"
        elif current.value_num < prior.value_num:
            direction = "down"

    cur_in, prior_in = _in_range(current), _in_range(prior)
    crossed_ref = None
    if cur_in is not None and prior_in is not None and cur_in != prior_in:
        crossed_ref = "into_range" if cur_in else "out_of_range"

    if censored:
        return {
            "direction": direction,
            "abs_change": None,
            "pct_change": None,
            "crossed_ref": crossed_ref,
            "magnitude": "meaningful" if crossed_ref else "within_noise",
            "censored": True,
        }

    abs_change = pct_change = None
    if current.value_num is not None and prior.value_num is not None:
        abs_change = round(current.value_num - prior.value_num, 6)
        if prior.value_num != 0:
            pct_change = round((current.value_num - prior.value_num) / abs(prior.value_num) * 100, 1)

    mmd = min_meaningful_delta(current.marker_canonical)
    return {
        "direction": direction,
        "abs_change": abs_change,
        "pct_change": pct_change,
        "crossed_ref": crossed_ref,
        "magnitude": _magnitude(abs_change, pct_change, crossed_ref, mmd),
        "censored": False,
        "min_meaningful_delta": mmd,
    }


def _magnitude(abs_change, pct_change, crossed_ref, mmd: dict) -> str:
    """meaningful iff a bound was crossed OR |change| >= threshold. The
    sub-threshold split is DISPLAY-ONLY (no gate effect): marginal if
    |change| >= 0.5 x threshold, else within_noise. Mode-aware: relative
    thresholds compare against |pct|/100, absolute against |abs|."""
    if crossed_ref is not None:
        return "meaningful"

    threshold = mmd.get("value")
    observed = None
    if mmd.get("mode") == "relative":
        if pct_change is not None:
            observed = abs(pct_change) / 100.0
    elif abs_change is not None:
        observed = abs(abs_change)

    if observed is None or threshold is None:
        return "within_noise"
    if observed >= threshold:
        return "meaningful"
    if observed >= 0.5 * threshold:
        return "marginal"
    return "within_noise"


def news_gate(delta_obj: dict | None) -> dict:
    """Gate 1, DELTA ARM ONLY (raw). is_news = (magnitude meaningful) OR
    (crossed_ref set). basis names only delta/crossed arms — NO relation basis
    (4b appends and may demote). A first observation is not news."""
    if delta_obj is None:
        return {"is_news": False, "basis": ["no_prior_first_observation"]}

    crossed = delta_obj["crossed_ref"]
    magnitude = delta_obj["magnitude"]
    is_news = crossed is not None or magnitude == "meaningful"

    basis: list[str] = []
    if crossed is not None:
        basis.append(f"crossed_ref_{crossed}")
    if magnitude == "meaningful":
        basis.append("delta_meaningful")
    elif magnitude == "marginal":
        basis.append("delta_marginal")
    elif delta_obj["direction"] == "flat":
        basis.append("flat_vs_prior")
    else:
        basis.append("delta_within_min_meaningful")

    return {"is_news": is_news, "basis": basis}
