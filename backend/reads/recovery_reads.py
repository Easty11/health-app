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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import models


# ─────────────────────────────────────────────────────────────────────────────
# Deviation-reader constants (#292).
#
# CALIBRATION-GATED — informed by n=5 dual-wear DELOAD nights only; tune after 3-4 weeks
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
RECENCY_FACTOR = 1.0      # weight multiplier for a CONTRIBUTING source — always 1.0,
#   because recency is enforced upstream as a binary GATE, not a weight: a source
#   contributes only if it has a reading ON `for_date` (same wake-day). A source whose
#   latest reading is older is excluded from weighting, combined_z, confidence and
#   representative_source, and reported in `stale_sources` instead (#NEXT — supersedes
#   the old "hook for a future backfill-combine" placeholder, which let a dead source's
#   last reading + frozen mature baseline be reported as today's).


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

    Each source's reading ON `for_date` (same wake-day — the recency gate, #NEXT) is
    z-scored against that source's OWN rolling baseline; the per-source deviations are
    combined by weight, and cross-source (dis)agreement becomes confidence. Never blends
    raw ms. A source whose latest reading is BEFORE `for_date` does not contribute (not
    to weighting, combined_z, confidence or representative_source): it is listed in
    `stale_sources` with its last date, so "absent today" is distinguishable from "never
    any". A dead source's last reading and frozen mature baseline is never today's HRV.

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
          stale_sources: [{source, last_captured_at}, ...],   # no reading on for_date
        }

    A compact surface uses `combined_z` + `confidence`; a readout uses `sources[]`;
    a consumer needing one ms scalar takes `representative_source(...)["rmssd"]`.

    Confidence value set — CANONICAL, 7 values (ratified #293): high, medium,
    medium_low, low, very_low, conflicted, flat. `flat` is confident-NEUTRAL (every
    contributing source inside the dead-zone, |z| < flat_threshold — "nothing's
    happening" is NOT "we don't know", so it is never very_low); `medium_low` is a
    single mature source (no corroboration). These are distinct tiers and must NOT be
    folded into high/medium. The #292 design brief's five-value enum is superseded.

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
    stale_out: list[dict] = []
    for source, srows in by_source.items():
        today_row = srows[0]                          # latest reading <= for_date
        # ── recency gate (#NEXT): same wake-day or it does not contribute ──
        if today_row.captured_at != for_date:
            stale_out.append({"source": source, "last_captured_at": today_row.captured_at})
            continue
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
    stale_out.sort(key=lambda s: s["source"])

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
        "stale_sources": stale_out,
    }


def representative_source(deviation_result: dict) -> Optional[dict]:
    """The one `sources[]` entry a scalar consumer reads a single ms value from.

    Part-3 rule: derive a single number from the deviation model (highest-weight
    source), NEVER from a resurrected `_SOURCE_RANK`. Ties break deterministically:
    weight, then baseline maturity (`baseline_n`), then |z|, then source name. Returns
    None when no source contributed — including when every source is stale (no reading
    on `for_date`; see the recency gate on `hrv_deviation`). Consumers read `["rmssd"]` (and `["baseline_mean"]`
    for an ms deviation) off the returned entry.
    """
    srcs = deviation_result.get("sources") or []
    if not srcs:
        return None
    return max(
        srcs,
        key=lambda s: (s["weight"], s["baseline_n"], abs(s["z"]), s["source"]),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Wake-day HRV selector — "what HRV do I show for a wake-day, honestly?"
#
# STANDALONE read helper. NOTHING consumes it yet (deliberate): it is the
# precondition for the check-in HRV denorm (whose read currently uses
# `hrv_deviation` with `for_date` as an UPPER BOUND — latest reading <= for_date,
# which silently returns a stale prior-day value when today's has not landed). This
# helper closes that seam: an explicit current-day gate that NEVER returns a
# reading whose `captured_at != wake_day`, plus source labelling, a same-wake-day-
# only cross-source delta, and hard guards on the two silent-wrong modes.
#
# `hrv_readings.captured_at` is a `Date` = the WAKE-DAY (the night), one row per
# (user, captured_at, source) — so this reads by DAY EQUALITY, never a range. It
# does not touch / modify `hrv_deviation`, `representative_source`,
# `_pick_latest_hrv`, or the arbitration layer; it CALLS `hrv_deviation` read-only
# for the primary source's baseline maturity (surfaced, never gated on).
# ─────────────────────────────────────────────────────────────────────────────

# Headline precedence on a same-wake-day pair (rule 4): richer source wins the
# HEADLINE, both are surfaced. Mirrors #298's `_HRV_SOURCE_RANK` (garmin > samsung
# > unknown) so the selector and the card agree on which source leads a contested
# night. `source` is an unconstrained String, so an unknown source ranks 0.
_WAKEDAY_SOURCE_RANK = {"garmin": 2, "samsung": 1}


def _aest_today() -> date:
    """The Australia/Brisbane (no-DST) wake-date "now" — the operator-local day the
    rest of the codebase buckets on (load_metrics, psychological_reads). Injected via
    `today=` in tests so the current-day gate never reads a hidden wall clock. `pytz`
    is imported lazily (mirrors `psychological_reads._aest_today`) — the module carries
    no hard top-level tz dependency, and the injected-`today` paths never import it."""
    import pytz

    return datetime.now(pytz.timezone("Australia/Brisbane")).date()


@dataclass(frozen=True)
class HrvSelection:
    """The honest answer to "what HRV do I show for (user, wake_day)?".

    `state` is the discriminator; the other fields are populated per state:

      "value"          one source for the day → `primary` set, no delta.
      "pair"           two sources SAME wake_day → `primary` + `secondary` + `delta_ms`
                       (headline = richer source, BOTH surfaced, never silent-dropped).
      "absent"         no reading for the day → caller renders "–". `primary` None.
      "stale_withheld" require_current_day and no current-day reading BUT an earlier
                       reading exists → absent-to-the-caller (primary None) but flagged,
                       so a caller can tell "no data yet" from "never any". The stale
                       earlier value is NEVER returned.
      "config_error"   >2 distinct sources for the day → `primary` None, never a silent
                       2-of-3 pick.

    `primary`/`secondary`: {"source": str, "rmssd_ms": float, "captured_at": date} | None.
    `captured_at` is carried so a caller (esp. the card, require_current_day=false) can
    label the value's date.
    `delta_ms`: int, primary − secondary; ONLY in "pair" (same-wake-day, rule 5).
    `possible_tz_split`: a second source has a reading on wake_day±1 but NOT wake_day —
    possibly the same physical night split by an un-tz-normalised upstream. FLAGGED,
    never auto-merged (rule 6).
    `sources_seen`: sorted distinct sources present ON the headlined day (empty when absent).
    `baseline_state`: for the primary source only, passed through from `hrv_deviation`'s
    per-source maturity — "baselined" (mature) | "building" (not yet) | None (no primary).
    Surfaced honestly; the value is NEVER gated on it, and the delta shows regardless of
    baseline maturity (ratified). ("settling" is not produced here — this helper takes no
    phase_change_date; a consumer that needs it reads `hrv_deviation` directly.)
    """
    state: str
    primary: Optional[dict] = None
    secondary: Optional[dict] = None
    delta_ms: Optional[int] = None
    possible_tz_split: bool = False
    sources_seen: list[str] = field(default_factory=list)
    baseline_state: Optional[str] = None


def _reading_dict(r) -> dict:
    return {"source": r.source, "rmssd_ms": r.rmssd_ms, "captured_at": r.captured_at}


def _primary_baseline_state(
    db: Session, user_id: int, primary_row
) -> Optional[str]:
    """Per-source baseline maturity for the headline reading, read from the ratified
    #292 machinery (never reimplemented, never modified). `hrv_deviation` at the
    reading's own date recomputes the primary source's rolling baseline; we surface
    only its `mature` flag as an honest advisory. None if the source didn't contribute
    (shouldn't happen for a value-bearing headline row, but degrade safely)."""
    dev = hrv_deviation(user_id, db, for_date=primary_row.captured_at)
    for s in dev.get("sources") or []:
        if s["source"] == primary_row.source:
            return "baselined" if s["mature"] else "building"
    return None


def select_wakeday_hrv(
    db: Session,
    user_id: int,
    wake_day: date,
    *,
    require_current_day: bool,
    today: Optional[date] = None,
) -> HrvSelection:
    """Select the HRV to show for `(user_id, wake_day)`, across sources, honestly.

    `require_current_day=True` (check-in use): the value must belong to the CURRENT
    day. `wake_day` is today by the caller's contract; `today` (injected, defaults to
    AEST "now") is what makes "current" testable. No reading whose `captured_at` equals
    the current wake_day → `absent`, or `stale_withheld` if the user has any earlier
    reading. A prior-day value is NEVER returned — this is the whole point of the helper.

    `require_current_day=False` (card use): headline the NEWEST available reading, with
    its date carried so the caller can label it. Never fabricates a cross-day pair.

    Reads `hrv_readings` (source-tagged, wake-day-keyed) only. Value-bearing rows only
    (`rmssd_ms` NOT NULL — a NULL-HRV row is nothing to headline).
    """
    today = today or _aest_today()

    rows = (
        db.query(models.HrvReading)
        .filter(
            models.HrvReading.user_id == user_id,
            models.HrvReading.rmssd_ms.isnot(None),
        )
        .order_by(models.HrvReading.captured_at.desc(), models.HrvReading.id.desc())
        .all()
    )

    # The day we headline. require_current_day pins it to the current day (wake_day,
    # only when that IS today — else there is no current reading by definition); the
    # card takes the newest available day.
    if require_current_day:
        target_day = wake_day if wake_day == today else None
    else:
        target_day = rows[0].captured_at if rows else None

    day_rows = [r for r in rows if r.captured_at == target_day] if target_day else []

    # ── tz-divergence guard (rule 6) ──
    # A source NOT present on the headlined day but present on wake_day±1 may be the
    # same physical night split across a tz boundary. Flag it; never auto-merge. The
    # guard anchors on the headlined day (== wake_day when require_current_day).
    possible_tz_split = False
    if target_day is not None and day_rows:
        day_sources = {r.source for r in day_rows}
        adjacent = {target_day - timedelta(days=1), target_day + timedelta(days=1)}
        adjacent_sources = {r.source for r in rows if r.captured_at in adjacent}
        possible_tz_split = bool(adjacent_sources - day_sources)

    # ── no reading for the headlined day ──
    if not day_rows:
        # require_current_day: distinguish "data exists, just not current" (withhold the
        # stale value, flag it) from "never any data". The card path only lands here with
        # no rows at all → absent.
        state = "stale_withheld" if (require_current_day and rows) else "absent"
        return HrvSelection(
            state=state,
            possible_tz_split=possible_tz_split,
            sources_seen=[],
        )

    # One row per (day, source) by the unique constraint — sources are already distinct.
    by_source = {r.source: r for r in day_rows}
    sources_seen = sorted(by_source)

    # ── >2-source guard (rule 7): never silently pick 2-of-3 ──
    if len(sources_seen) > 2:
        return HrvSelection(
            state="config_error",
            possible_tz_split=possible_tz_split,
            sources_seen=sources_seen,
        )

    # ── single source → value ──
    if len(sources_seen) == 1:
        primary_row = day_rows[0]
        return HrvSelection(
            state="value",
            primary=_reading_dict(primary_row),
            possible_tz_split=possible_tz_split,
            sources_seen=sources_seen,
            baseline_state=_primary_baseline_state(db, user_id, primary_row),
        )

    # ── two sources SAME wake_day → pair (delta valid, rule 5) ──
    ordered = sorted(
        day_rows,
        key=lambda r: _WAKEDAY_SOURCE_RANK.get(r.source, 0),
        reverse=True,
    )
    primary_row, secondary_row = ordered[0], ordered[1]
    delta_ms = round(primary_row.rmssd_ms - secondary_row.rmssd_ms)
    return HrvSelection(
        state="pair",
        primary=_reading_dict(primary_row),
        secondary=_reading_dict(secondary_row),
        delta_ms=delta_ms,
        possible_tz_split=possible_tz_split,
        sources_seen=sources_seen,
        baseline_state=_primary_baseline_state(db, user_id, primary_row),
    )
