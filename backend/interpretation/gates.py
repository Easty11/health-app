"""Gate arithmetic for the foundation producer — pure functions, no I/O.

Four mechanical questions per marker:
  delta       — how did it move vs the prior draw?
  news_gate   — gate 1, TWO arms: the delta arm (raw) and the safety arm.
                4b may append a relation basis and may demote the DELTA arm.
                It may NEVER demote the safety arm — see below.
  range_gate  — gate 2, driven by the LAB flag; computed_flag is withheld (V2)
  safety_gate — gate 3, a LEVEL compared to an authored policy constant

The three gates answer different questions from different authorities:
  * delta compares a value to its own predecessor.
  * range_gate compares it to the interval the LAB shipped with the report.
  * safety_gate compares it to a number from OUTSIDE the data that does not
    care what preceded it and is not the lab's opinion.
So output may legitimately carry range_gate.is_out_of_range False alongside
safety_gate.status "in_band". Both are correct, from two authorities. The
renderer shows both with their sources; it does not reconcile them.

THE SAFETY ARM IS NOT DEMOTABLE. 4b's relation arm may demote delta-driven
news — "AST rose but GGT is normal, so this is muscle" legitimately makes a
delta story not worth surfacing. Nothing may demote a band change. Explaining
WHY a value rose is a different claim from whether it should surface, and no
mechanistic account makes a haematocrit of 0.52 not worth showing. Written
down before demotion logic exists, so that logic inherits the constraint
rather than discovering it.

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

_SAFETY_THRESHOLDS_PATH = Path(__file__).resolve().parent.parent / "reference" / "safety_thresholds.json"
_MARKER_CANONICAL_PATH = Path(__file__).resolve().parent.parent / "reference" / "marker_canonical.json"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_SAFETY_THRESHOLDS = _load_json(_SAFETY_THRESHOLDS_PATH)
_UNIT_ESTABLISHED = {
    e["marker_canonical"]: e.get("unit_established")
    for e in _load_json(_MARKER_CANONICAL_PATH)["entries"]
}

# A censoring operator either points the SAME way as the threshold direction (so the
# bound is evidence the true value is at least/most that far along) or the opposite way.
_AGREES = {"above": {">", ">="}, "below": {"<", "<="}}


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


def _undecidable(reason: str, entry: dict | None = None) -> dict:
    return {
        "status": None,
        "band_key": None,
        "threshold_value": None,
        "direction": (entry or {}).get("direction"),
        "contested": (entry or {}).get("contested"),
        "evidence_refs": [],
        "band_change": None,
        "undecidable_reason": reason,
    }


def _breached_band(value: float, direction: str, bands: list[dict]) -> dict | None:
    """The HIGHEST breached band, or None. 'Highest' means most severe along
    `direction`: for `above` that is the largest threshold cleared, for `below`
    the smallest."""
    hits = [b for b in bands
            if (value >= b["value"] if direction == "above" else value <= b["value"])]
    if not hits:
        return None
    return max(hits, key=lambda b: b["value"]) if direction == "above" \
        else min(hits, key=lambda b: b["value"])


def _severity(band: dict | None, direction: str) -> float | None:
    """Orders bands so escalated/de_escalated can be decided without assuming the
    asset lists them in order."""
    if band is None:
        return None
    return band["value"] if direction == "above" else -band["value"]


def _resolve_band(row: LabRow | None, entry: dict) -> tuple[dict | None, str | None]:
    """(band, undecidable_reason) for one row against one asset entry."""
    if row is None:
        return None, "no_value"
    if row.value_num is None:
        return None, "no_value"

    marker = row.marker_canonical
    direction = entry["direction"]
    established = _UNIT_ESTABLISHED.get(marker, "__absent__")

    if established not in (None, "__absent__"):
        if row.unit_canonical != established:
            return None, "unit_mismatch"
    else:
        lo, hi = entry.get("value_plausibility", (None, None))
        if lo is not None and not (lo <= row.value_num <= hi):
            return None, "implausible_value"

    bands = entry.get("bands", [])
    op = row.value_operator

    if op:
        # Censoring destroys a MAGNITUDE; it does not necessarily destroy a threshold
        # comparison. So this deliberately does NOT inherit delta's blanket rule.
        if op in _AGREES[direction]:
            band = _breached_band(row.value_num, direction, bands)
            if band is not None:
                # ">0.55" with direction above and a band at 0.54: the true value is
                # at least 0.55, so the band is cleared whatever the real number is.
                return band, None
            # ">0.30" against a band at 0.50 is NOT "not in band" — the true value is
            # unbounded above and could sit in any band. Reporting not_in_band here
            # would be a false negative on a safety gate, the one direction never to
            # be wrong in. The brief's table does not enumerate this case; it is
            # resolved to indeterminate deliberately (#104).
            return None, "censored_indeterminate"
        return None, "censored_indeterminate"

    return _breached_band(row.value_num, direction, bands), None


def safety_gate(current: LabRow, prior: LabRow | None, thresholds: dict | None = None) -> dict:
    """Gate 3 — a LEVEL against an authored policy constant.

    Unlike delta (value vs its predecessor) and range_gate (value vs the interval the
    lab shipped), this compares a value to a number from outside the data. It fires on
    a level, not a transition: a persistently elevated value that has not moved at all
    still surfaces.

    Returns status/band_key/threshold_value/direction/contested/evidence_refs/
    band_change/undecidable_reason. `status` is None whenever the comparison could not
    be made, and `undecidable_reason` always says why.
    """
    asset = thresholds if thresholds is not None else _SAFETY_THRESHOLDS
    entry = asset.get("thresholds", {}).get(current.marker_canonical or "")
    if not entry:
        return _undecidable("no_asset")

    band, reason = _resolve_band(current, entry)
    if reason is not None:
        return _undecidable(reason, entry)

    prior_band, prior_reason = _resolve_band(prior, entry)
    direction = entry["direction"]

    cur_sev = _severity(band, direction)
    pri_sev = _severity(prior_band, direction)

    if band is not None and (prior is None or prior_reason is not None):
        band_change = "first_observation_in_band"
    elif band is not None and prior_band is None:
        band_change = "entered"
    elif band is not None and cur_sev > pri_sev:
        band_change = "escalated"
    elif band is not None and cur_sev < pri_sev:
        band_change = "de_escalated"
    elif band is None and prior_band is not None and prior_reason is None:
        band_change = "exited"
    else:
        band_change = None

    return {
        "status": "in_band" if band is not None else "not_in_band",
        "band_key": band["band_key"] if band else None,
        "threshold_value": band["value"] if band else None,
        "direction": direction,
        "contested": entry.get("contested"),
        "evidence_refs": list(band.get("evidence_refs", [])) if band else [],
        "band_change": band_change,
        "undecidable_reason": None,
    }


def news_gate(delta_obj: dict | None, safety_gate: dict | None = None) -> dict:
    """Gate 1, TWO arms.

    Delta arm (raw): is_news = (magnitude meaningful) OR (crossed_ref set). A first
    observation is not news on this arm.

    Safety arm (optional keyword, default None so every pre-existing call site behaves
    identically): when a `safety_gate` dict is passed and its `band_change` is non-null,
    is_news is forced true and `safety_band_<change>` is appended to basis.

    The return shape is EXACTLY {is_news, basis} on every path. The safety arm appends
    to `basis`; it never adds a sibling key. Three tests pin this dict whole
    (`fsh`, `ast`, `vitamin_d`), and that is deliberate — the shape is contract surface.

    NOT DEMOTABLE: 4b may append a relation basis and may demote the delta arm. It must
    never demote a band change. See the module docstring.
    """
    band_change = (safety_gate or {}).get("band_change")

    if delta_obj is None:
        if band_change:
            return {"is_news": True,
                    "basis": ["no_prior_first_observation", f"safety_band_{band_change}"]}
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

    if band_change:
        is_news = True
        basis.append(f"safety_band_{band_change}")

    return {"is_news": is_news, "basis": basis}
