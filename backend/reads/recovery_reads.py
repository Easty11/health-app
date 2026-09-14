"""
canonical_hrv(user_id, db, *, since, as_of, limit) -> list[HrvReading]
arbitrate(readings) -> list  (pure; sets `.canonical` on each row)
hrv_deviation(user_id, db, *, for_date, ...) -> dict
representative_source(deviation_result) -> dict | None

Read-time HRV consumption over `hrv_readings` (source-tagged). Two functions,
two models — and a deliberate transition between them:

* `canonical_hrv` / `arbitrate` — the SUPERSEDED `_SOURCE_RANK` arbitration:
  "one source wins the night." Kept CALLABLE (recovery.py — unmounted, Q151 — is
  the last caller, plus the row-reading plumbing both readers share), but no NEW
  consumer may call it. See Part 3 / the exit below.

* `hrv_deviation` — the CORRECT multi-source consumption model (#292): two devices
  measuring the same night are two instruments, not two candidates for one truth.
  Never blend raw ms (the offset is non-constant — 0-48 ms across 5 dual-wear
  nights). Normalise each source to its OWN rolling baseline (z-score), combine the
  deviations by weight, and surface cross-source disagreement as CONFIDENCE, not as
  a hidden loser. This supersedes arbitration; downstream reads the object, never a
  bare scalar.

Fine cut between them (Part 1 / Part 3): the source-tagged ROW-READING plumbing
(`_hrv_rows`) is shared infrastructure both depend on. Only the SELECTION layer —
`_SOURCE_RANK`, `_rank`, `_win_key`, `arbitrate`, the derived `.canonical` flag —
is superseded. The exit deletes the selection layer and keeps the plumbing.

THE EXIT (mandatory, specced now so it isn't forgotten — cf. Q151, an unmounted
reader nobody consumes but nobody kills):
  1. Once no consumer calls the arbitration selection (`.canonical`) — today only
     the unmounted recovery.py does; its disposition is Q151 — delete `_SOURCE_RANK`
     and the arbitration branch, KEEP `_hrv_rows`.
  2. If a future need for a single arbitrated number arises, derive it from the
     deviation model via `representative_source` (highest-weight source), NOT from a
     resurrected rank.
  3. Until deletion the arbitration branch stays callable but no new consumer may
     call it — enforced by review + this docstring. Tracked: OPEN_QUESTIONS Q153.

The `.canonical` flag is DERIVED and never persisted — there is no `canonical`
column (same principle as `reads/aerobic_reads.py`). HRV SCALAR ONLY: this module
consumes `hrv_readings` and nothing else; sleep/SpO2/architecture stay on their
existing sources.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import models


# ─────────────────────────────────────────────────────────────────────────────
# Deviation-reader constants (#292).
#
# PROVISIONAL — informed by n=5 dual-wear DELOAD nights only; tune after 3-4 weeks
# of representative-load overlap. AGREEMENT_HIGH / AGREEMENT_MED are the primary
# calibration targets. All are parameterised (never hard-coded at the call site):
# every threshold below is a keyword default on `hrv_deviation`.
# ─────────────────────────────────────────────────────────────────────────────
BASELINE_WINDOW = 28      # days, rolling per-source baseline window
MIN_BASELINE_N = 21       # nights: a source counts as "mature" at 21
MIN_BASELINE_SD = 3.0     # ms: SD floor, prevents z-blowup on a stable window
SETTLING_NIGHTS = 10      # post-phase-change settling period
FLAT_THRESHOLD = 0.5      # sigma: dead-zone; |z| below this is neutral
AGREEMENT_HIGH = 1.0      # sigma: cross-source gap for `high`   (calibration target)
AGREEMENT_MED = 2.0       # sigma: cross-source gap for `medium` (calibration target)
RECENCY_FACTOR = 1.0      # nightly use; hook for a future backfill-combine


# ─────────────────────────────────────────────────────────────────────────────
# SUPERSEDED arbitration selection layer (see THE EXIT above). No new consumer.
# ─────────────────────────────────────────────────────────────────────────────
# Fidelity rank — higher wins when two sources report the same night. Garmin's pull
# carries the richer summary (status band + baseline + weekly avg + 5-min series);
# Samsung is nightly-only. An unknown source ranks below all known ones.
_SOURCE_RANK = {
    "garmin": 2,
    "samsung": 1,
}
_UNKNOWN_RANK = 0


def _rank(source: Optional[str]) -> int:
    return _SOURCE_RANK.get(source or "", _UNKNOWN_RANK)


def _win_key(reading) -> tuple:
    """Ordering key for 'which row of a same-night group is canonical'. LARGER wins:
    higher source rank, then higher id (a deterministic final discriminator so a group
    always yields exactly ONE canonical — never zero, which would drop the night)."""
    return (_rank(reading.source), reading.id if reading.id is not None else 0)


def arbitrate(readings: list) -> list:
    """Set `.canonical` (bool) on every reading in `readings`, in place.

    Group by `(user_id, captured_at)`; within a group the row with the max `_win_key`
    is canonical, all others False. A night with a single source is canonical by
    default. Returns the same list for convenience.

    SUPERSEDED by `hrv_deviation` (#292). No new consumer — see THE EXIT.
    """
    groups: dict[tuple, list] = {}
    for r in readings:
        groups.setdefault((r.user_id, r.captured_at), []).append(r)

    for group in groups.values():
        winner = max(group, key=_win_key)
        for r in group:
            r.canonical = r is winner
    return readings


# ─────────────────────────────────────────────────────────────────────────────
# Shared row-reading plumbing (KEPT past the exit — both readers depend on it).
# ─────────────────────────────────────────────────────────────────────────────
def _hrv_rows(
    user_id: int,
    db: Session,
    *,
    since: Optional[date] = None,
    as_of: Optional[date] = None,
) -> list:
    """Source-tagged `hrv_readings` rows for a user, `captured_at` DESC.

    `since` is a lower bound (captured_at >= since); `as_of` an upper bound
    (captured_at <= as_of). No arbitration, no `.canonical` — this is the shared
    infrastructure `canonical_hrv` and `hrv_deviation` both read; the fine cut in
    THE EXIT removes the selection layer and keeps exactly this.
    """
    q = (
        db.query(models.HrvReading)
        .filter(models.HrvReading.user_id == user_id)
        .order_by(models.HrvReading.captured_at.desc())
    )
    if since is not None:
        q = q.filter(models.HrvReading.captured_at >= since)
    if as_of is not None:
        q = q.filter(models.HrvReading.captured_at <= as_of)
    return q.all()


def canonical_hrv(
    user_id: int,
    db: Session,
    *,
    since: Optional[date] = None,
    as_of: Optional[date] = None,
    limit: Optional[int] = None,
) -> list:
    """HRV readings for a user, each carrying a derived `.canonical` flag.

    SUPERSEDED by `hrv_deviation` (#292): this returns the single arbitration WINNER
    per night, discarding the cross-source divergence that is itself signal. Kept
    callable for the unmounted recovery.py (Q151) and as the row-reading host; NO NEW
    CONSUMER may call it — see THE EXIT at module top.

    `since` is a lower bound (captured_at >= since); `as_of` an upper bound
    (captured_at <= as_of). Both are applied BEFORE arbitration, so a night's
    counterpart from another source is never dropped out of its group. Arbitration
    then runs over the whole windowed set BEFORE `limit` is applied, so truncation
    likewise never splits a night.
    """
    rows = _hrv_rows(user_id, db, since=since, as_of=as_of)
    arbitrate(rows)
    if limit is not None:
        rows = rows[:limit]
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# The deviation + confidence reader (#292) — correct multi-source consumption.
# ─────────────────────────────────────────────────────────────────────────────
def hrv_deviation(
    user_id: int,
    db: Session,
    *,
    for_date: date,
    phase_change_date: Optional[date] = None,
    baseline_window: int = BASELINE_WINDOW,
    min_baseline_n: int = MIN_BASELINE_N,
    min_baseline_sd: float = MIN_BASELINE_SD,
    settling_nights: int = SETTLING_NIGHTS,
    flat_threshold: float = FLAT_THRESHOLD,
    agreement_high: float = AGREEMENT_HIGH,
    agreement_med: float = AGREEMENT_MED,
    recency_factor: float = RECENCY_FACTOR,
) -> dict:
    """Per-source-normalised HRV deviation + cross-source confidence for `for_date`.

    Each source's most recent reading at or before `for_date` is z-scored against
    that source's OWN rolling baseline; the per-source deviations are combined by
    weight, and cross-source (dis)agreement becomes confidence. Never blends raw ms.

    Output contract (downstream reads the object, never a bare scalar)::

        {
          combined_z: float,
          direction: "up" | "down" | "flat",
          confidence: "high"|"medium"|"medium_low"|"low"|"very_low"|"conflicted"|"flat",
          baseline_state: "normal" | "settling" | "building",
          sources: [{source, z, rmssd, baseline_mean, baseline_sd,
                     baseline_n, weight, mature}, ...],
          agreement_gap: float,
          n_contributing: int,
        }

    A compact surface uses `combined_z` + `confidence`; a readout uses `sources[]`;
    a consumer needing one ms scalar takes `representative_source(...)["rmssd"]`.

    NOTE on the confidence value set: the #292 brief's output-contract line lists the
    five primary tiers (high/medium/low/very_low/conflicted); the brief's confidence
    TABLE additionally specifies `flat` (all-flat night — confident-NEUTRAL, direction
    flat: "nothing's happening" is NOT "we don't know", so it is never very_low) and
    single-mature-source `medium_low`. This reader emits the full table faithfully
    rather than fold those two into a tier that would misstate them.

    `phase_change_date`: if set and `for_date` is within `settling_nights` of it, the
    baseline is treated as unsettled — deviation is still emitted, `baseline_state`
    is "settling", and confidence is capped at "low" (§ FEEDBACK 2.5, degrade to
    caution). Settling nights are INCLUDED in the baseline (flag the verdict, not the
    input). Consumers with training-phase context may pass it; it defaults off.
    """
    rows = _hrv_rows(user_id, db, as_of=for_date)

    by_source: dict[str, list] = defaultdict(list)
    for r in rows:
        if r.rmssd_ms is None:
            continue
        by_source[r.source or "unknown"].append(r)   # each list stays captured_at DESC

    sources_out: list[dict] = []
    for source, srows in by_source.items():
        today_row = srows[0]                          # latest reading <= for_date
        today_rmssd = today_row.rmssd_ms
        lo = today_row.captured_at - timedelta(days=baseline_window)
        baseline_vals = [
            x.rmssd_ms
            for x in srows
            if lo <= x.captured_at < today_row.captured_at and x.rmssd_ms is not None
        ]
        baseline_n = len(baseline_vals)
        if baseline_n == 0:
            # First observed night for this source: no history to deviate from.
            baseline_mean = today_rmssd
            baseline_sd = min_baseline_sd
            z = 0.0
        else:
            baseline_mean = sum(baseline_vals) / baseline_n
            if baseline_n >= 2:
                var = sum((v - baseline_mean) ** 2 for v in baseline_vals) / baseline_n
                baseline_sd = max(math.sqrt(var), min_baseline_sd)
            else:
                baseline_sd = min_baseline_sd
            z = (today_rmssd - baseline_mean) / baseline_sd

        maturity_factor = min(1.0, baseline_n / min_baseline_n) if min_baseline_n else 1.0
        coverage_factor = 1.0                          # binary v1 (reading present);
        #   sample-count/window-coverage hook once a connector exposes it.
        weight = coverage_factor * recency_factor * maturity_factor
        sources_out.append({
            "source": source,
            "z": z,
            "rmssd": today_rmssd,
            "baseline_mean": baseline_mean,
            "baseline_sd": baseline_sd,
            "baseline_n": baseline_n,
            "weight": weight,
            "mature": baseline_n >= min_baseline_n,
        })

    # Deterministic ordering for stable readouts: strongest deviation first.
    sources_out.sort(key=lambda s: (-abs(s["z"]), s["source"]))

    n_contributing = len(sources_out)
    total_w = sum(s["weight"] for s in sources_out)
    if total_w > 0:
        combined_z = sum(s["weight"] * s["z"] for s in sources_out) / total_w
    else:
        combined_z = 0.0

    zs = [s["z"] for s in sources_out]
    agreement_gap = (max(zs) - min(zs)) if len(zs) >= 2 else 0.0

    active = [s for s in sources_out if abs(s["z"]) >= flat_threshold]
    has_up = any(s["z"] >= flat_threshold for s in active)
    has_down = any(s["z"] <= -flat_threshold for s in active)
    opposite = has_up and has_down
    mature = [s for s in sources_out if s["mature"]]

    settling = (
        phase_change_date is not None
        and 0 <= (for_date - phase_change_date).days < settling_nights
    )

    # ── direction ──
    if combined_z >= flat_threshold:
        direction = "up"
    elif combined_z <= -flat_threshold:
        direction = "down"
    else:
        direction = "flat"

    # ── confidence ──
    if n_contributing == 0:
        confidence = "very_low"
        direction = "flat"
    elif not active:
        # All contributing sources inside the dead-zone: confident-neutral.
        confidence = "flat"
        direction = "flat"
    elif opposite and n_contributing >= 2:
        # Sources disagree on direction outside the dead-zone: surface both, no verdict.
        confidence = "conflicted"
        direction = "flat"
    elif n_contributing >= 2:
        # Same direction (dead-zone sources are neutral, not disagreement).
        if len(mature) >= 2:
            if agreement_gap <= agreement_high:
                confidence = "high"
            elif agreement_gap <= agreement_med:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            confidence = "low"          # agree on direction but < 2 mature sources
    else:  # n_contributing == 1
        confidence = "medium_low" if mature else "very_low"

    # ── baseline_state ──
    if settling:
        baseline_state = "settling"
    elif not mature:
        baseline_state = "building"
    else:
        baseline_state = "normal"

    # Settling caps positive confidence at low; very_low and conflicted are left as-is
    # (an unsettled baseline cannot manufacture confidence, nor resolve a conflict).
    if settling and confidence in {"high", "medium", "medium_low", "flat"}:
        confidence = "low"

    return {
        "combined_z": combined_z,
        "direction": direction,
        "confidence": confidence,
        "baseline_state": baseline_state,
        "sources": sources_out,
        "agreement_gap": agreement_gap,
        "n_contributing": n_contributing,
    }


def representative_source(deviation_result: dict) -> Optional[dict]:
    """The one `sources[]` entry a scalar consumer reads a single ms value from.

    Part-3 rule: derive a single number from the deviation model (highest-weight
    source), NEVER from a resurrected `_SOURCE_RANK`. Ties break deterministically:
    weight, then baseline maturity (`baseline_n`), then |z|, then source name. Returns
    None when no source contributed. Consumers read `["rmssd"]` (and `["baseline_mean"]`
    for an ms deviation) off the returned entry.
    """
    srcs = deviation_result.get("sources") or []
    if not srcs:
        return None
    return max(
        srcs,
        key=lambda s: (s["weight"], s["baseline_n"], abs(s["z"]), s["source"]),
    )
