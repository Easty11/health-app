"""
Ratios (Q27 v1): the two read-time routes for a declared `Ratio` (taxonomy.py).

A ratio is never stored. Two routes compute it:

  route (i)  `log_derived` - from the Hevy log (cable / machine e1RM, `engine/log_strength.py`).
             Numerator and denominator are paired on the SAME session-day only (no window). A day that
             does not pair is accounted for, not just dropped: `half_not_logged_days` (one region has
             sets that day, the other has none) and `no_eligible_e1rm_days` (both have sets, at least
             one has no scorable e1RM - with the reason, per template). Sets score up to the ratio's
             own `log_rep_ceiling`, not the See-test's cap. Per side with sets in BOTH regions (left,
             right, or bilateral when both are bilateral) - sides are never
             mixed. `baseline` is the median of the first three pairs (null under three); `current`
             is the median of the last three pairs within 42 days of today (null if fewer than
             three are that recent). `delta_pct` is the move from baseline to current. The reference
             is always internal: no norm shares the instrument.
  route (ii) `observed` - from `capability_observations`: the latest numerator and the latest
             denominator that share a protocol and were taken within 14 days of each other (two
             separate clinic visits are not one read). The reference gate decides whether a band
             may be shown beside it.

Neither route writes anything. Neither produces a label, a flag, a score or a threshold: the output
is numbers, dates, the move over time, and the governing reference with its reason.
"""
from __future__ import annotations

import statistics
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from reads import strength_reads
from . import log_strength
from . import observations as observations_mod
from . import taxonomy
from .reference import evaluate_reference
from .taxonomy import SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT

BASELINE_PAIRS = 3           # first N same-day pairs
CURRENT_PAIRS = 3            # last N same-day pairs inside the currency window
CURRENCY_DAYS = 42           # a "current" pair is at most this many days old
OBSERVED_WINDOW_DAYS = 14    # route (ii): numerator and denominator within this many days

LOG_REFERENCE = {
    "governing": "internal",
    "reason": "log-derived (cable/machine); no norm shares the instrument",
}

_SIDE_ORDER = (SIDE_LEFT, SIDE_RIGHT, SIDE_BILATERAL)


def _pairs_for_side(num_pts: list[dict], den_pts: list[dict]) -> list[dict]:
    num = {p["day"]: p for p in num_pts}
    den = {p["day"]: p for p in den_pts}
    both = sorted(set(num) & set(den))
    pairs = []
    for day in both:
        n, d = num[day]["e1rm_kg"], den[day]["e1rm_kg"]
        pairs.append({
            "day": day, "numerator_e1rm_kg": n, "denominator_e1rm_kg": d,
            "ratio": (n / d) if d else None,
        })
    return pairs


def _day_accounting(
    pairs: list[dict], num_pts: list[dict], den_pts: list[dict],
    num_inel: list[dict], den_inel: list[dict], ratio: taxonomy.Ratio,
) -> dict[str, Any]:
    """Where every non-paired session-day went, for one side. A day is "had sets" for a region when it
    is scorable there or listed ineligible there. `half_not_logged`: exactly one region had sets.
    `no_eligible_e1rm`: both regions had sets, so at least one had none scorable - its ineligible entries
    (template, reason) are listed. The two counts are disjoint and together are every unpaired day."""
    paired = {p["day"] for p in pairs}
    num_had = {p["day"] for p in num_pts} | {e["day"] for e in num_inel}
    den_had = {p["day"] for p in den_pts} | {e["day"] for e in den_inel}
    half_not_logged = num_had ^ den_had
    no_eligible = (num_had & den_had) - paired
    detail = sorted(
        ({"day": str(e["day"]), "half": half, "region": region, "template_id": e["template_id"],
          "reason": e["reason"]}
         for half, region, entries in (("numerator", ratio.numerator[0], num_inel),
                                       ("denominator", ratio.denominator[0], den_inel))
         for e in entries if e["day"] in no_eligible),
        key=lambda r: (r["day"], r["half"] != "numerator", r["template_id"]),   # numerator first
    )
    return {
        "paired_days": len(paired),
        "half_not_logged_days": len(half_not_logged),
        "no_eligible_e1rm_days": len(no_eligible),
        "no_eligible_e1rm": detail,
    }


def _median(pairs: list[dict]) -> float | None:
    vals = [p["ratio"] for p in pairs if p["ratio"] is not None]
    return statistics.median(vals) if vals and len(vals) == len(pairs) else None


def log_derived(
    db: Session, user_id: int, ratio_key: str, since: date | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    ratio = taxonomy.ratio_by_key(ratio_key)
    if ratio is None:
        raise ValueError(f"unknown ratio_key: {ratio_key!r}")
    today = today or strength_reads._today_aest()

    ceiling = ratio.log_rep_ceiling
    num = log_strength.e1rm_by_side(db, user_id, ratio.numerator[0], rep_cap=ceiling, since=since)
    den = log_strength.e1rm_by_side(db, user_id, ratio.denominator[0], rep_cap=ceiling, since=since)
    # A side is present in a region when it has sets there, scorable or not: a side whose only logged
    # days were ineligible must still be reported (with its reasons), not vanish.
    num_sides = set(num.series) | set(num.ineligible)
    den_sides = set(den.series) | set(den.ineligible)

    sides_out: dict[str, Any] = {}
    for side in _SIDE_ORDER:
        if side not in num_sides or side not in den_sides:
            continue
        pairs = _pairs_for_side(num.series.get(side, []), den.series.get(side, []))
        accounting = _day_accounting(
            pairs, num.series.get(side, []), den.series.get(side, []),
            num.ineligible.get(side, []), den.ineligible.get(side, []), ratio)
        baseline_pairs = pairs[:BASELINE_PAIRS]
        baseline = _median(baseline_pairs) if len(baseline_pairs) == BASELINE_PAIRS else None
        recent = [p for p in pairs if (today - p["day"]).days <= CURRENCY_DAYS]
        current_pairs = recent[-CURRENT_PAIRS:]
        current = _median(current_pairs) if len(current_pairs) == CURRENT_PAIRS else None
        delta_pct = ((current - baseline) / baseline * 100) if (baseline and current is not None) else None
        sides_out[side] = {
            "pairs": [{**p, "day": str(p["day"])} for p in pairs],
            "n_pairs": len(pairs),
            **accounting,
            # DEPRECATED (one release, then dropped): the two unpaired counts summed. Read the three
            # counts above. Not the old value on a log with ineligible-only days: those are now counted.
            "unpaired_days": accounting["half_not_logged_days"] + accounting["no_eligible_e1rm_days"],
            "baseline": baseline,
            "baseline_days": [str(p["day"]) for p in baseline_pairs] if baseline is not None else [],
            "current": current,
            "current_days": [str(p["day"]) for p in current_pairs] if current is not None else [],
            "delta_pct": delta_pct,
            "reference": dict(LOG_REFERENCE),
        }

    return {
        "ratio_key": ratio_key,
        "route": "log_derived",
        "sides": sides_out,
        "rep_ceiling": ceiling,
        # Sides with sets in one region and not the other cannot pair (never mixed).
        "unmatched_sides": {
            "numerator_only": sorted(s for s in num_sides if s not in den_sides),
            "denominator_only": sorted(s for s in den_sides if s not in num_sides),
        },
        "pairing": "same session-day only",
        "currency_days": CURRENCY_DAYS,
    }


def _series_desc(db: Session, user_id: int, region_key: str, measure_key: str, side: str):
    rows = observations_mod.series(
        db, user_id, region_key=region_key, measure_key=measure_key, side=side)
    return list(reversed(rows))   # newest first (series() is oldest first)


def observed(db: Session, user_id: int, ratio_key: str) -> dict[str, Any]:
    ratio = taxonomy.ratio_by_key(ratio_key)
    if ratio is None:
        raise ValueError(f"unknown ratio_key: {ratio_key!r}")
    num_measure = taxonomy.measure_for(*ratio.numerator)

    sides_out: dict[str, Any] = {}
    for side in num_measure.sides():
        num_rows = _series_desc(db, user_id, *ratio.numerator, side)
        den_rows = _series_desc(db, user_id, *ratio.denominator, side)
        chosen = None
        for n in num_rows:
            for dn in den_rows:
                if dn.protocol == n.protocol and abs((n.observed_on - dn.observed_on).days) <= OBSERVED_WINDOW_DAYS:
                    chosen = (n, dn)
                    break
            if chosen:
                break
        if chosen is None:
            continue
        n, dn = chosen
        sides_out[side] = {
            "numerator": observations_mod.observation_to_dict(n),
            "denominator": observations_mod.observation_to_dict(dn),
            "ratio": (n.value / dn.value) if dn.value else None,
            "protocol": n.protocol,
            "days_apart": abs((n.observed_on - dn.observed_on).days),
            "reference": evaluate_reference(("ratio", ratio_key), [n, dn]),
        }
    return {
        "ratio_key": ratio_key,
        "route": "observed",
        "sides": sides_out,
        "window_days": OBSERVED_WINDOW_DAYS,
    }


def ratio_overview(db: Session, user_id: int, ratio_key: str) -> dict[str, Any]:
    ratio = taxonomy.ratio_by_key(ratio_key)
    if ratio is None:
        raise ValueError(f"unknown ratio_key: {ratio_key!r}")
    return {
        "ratio": taxonomy.ratio_as_dict(ratio),
        "log_derived": log_derived(db, user_id, ratio_key),
        "observed": observed(db, user_id, ratio_key),
    }


def all_ratio_overviews(db: Session, user_id: int) -> list[dict[str, Any]]:
    return [ratio_overview(db, user_id, r.key) for r in taxonomy.all_ratios()]
