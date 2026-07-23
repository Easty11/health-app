"""CBT-I titration engine — weekly adjudication of the prescribed sleep window.

Controls on TOTAL SLEEP TIME with sleep efficiency as a FLOOR, never as the target
(#107). The window is rolling mean TST plus a buffer; the block exits on TST
plateau with SE held >= 85%, not on SE reaching or stalling at a threshold. An
SE-maximising rule terminates at peak efficiency, which on the observed block is
roughly 45 minutes short of need.

This module is PURE: it takes `Night` records and returns a `CycleDecision`. It
opens no database session, reads no readiness output, and re-implements no clock
arithmetic (all of that is `cbti.timeutil`). The DB adapter lives in `replay.py`
and in the future prescription writer.

Gate order — first failure short-circuits to HOLD with a reason:
  1. SUFFICIENCY  >= 5 valid nights after exclusions
  2. ADHERENCE    actual bedtime vs prescribed, +/-30 min, failing on >= 3 of 7

Regularity (lights-out SD, wake-time SD) is COMPUTED AND REPORTED but does not
gate (#114): across the observed block, lights-out SD against weekly mean SE gives
r = -0.206, and a >0.5h gate would have blocked five of eight weeks including the
two best. Early-morning awakening is instrumented but never drives compression
(#108) — wakes cluster time-locked at 04:32 +/-21 min and do not track window
length.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from cbti.timeutil import (
    clock_delta_minutes,
    clock_to_minutes,
    minutes_to_clock,
    signed_offset_minutes,
)

# ── constants ─────────────────────────────────────────────────────────────────
# Derived from the observed block (#115): differencing each prescribed window
# against the mean TST of its preceding seven nights gave +36/+45/+36/+27/+16/
# +48/+65 — median +36. 30 is adopted at the conservative end, where it also
# coincides with the standard sleep-restriction buffer: two supports, not one.
BUFFER_MIN = 30

FLOOR_MIN = 300               # 5h00 — never prescribe below this
SE_FLOOR_PCT = 85.0           # #107: efficiency is the floor, not the target
MIN_VALID_NIGHTS = 5          # sufficiency gate
ADHERENCE_TOL_MIN = 30        # +/- tolerance on bedtime vs prescription
ADHERENCE_FAIL_N = 3          # >= this many failures in the cycle -> HOLD
CYCLE_NIGHTS = 7
NAP_EXCLUDE_MIN = 0           # Q45: ANY nap-flagged night is excluded, not >20
TRAINING_RECOVERY_MIN = 90    # constrained night floor = session end + 90 min

# UNVALIDATED BY THE OBSERVED BLOCK. Not derived from data; the observed
# prescription moves ranged 1..35 min so this would have clipped one of eight,
# but on replay the cap BOUND IN ZERO of 8 cycles — the block never exercised it.
# Left at 30 deliberately rather than tuned: a better number cannot be chosen
# from data that never reached the constraint. Revisit when a block binds it.
MAX_MOVE_MIN = 30

# UNVALIDATED BY THE OBSERVED BLOCK. Not specified by the brief; "TST plateau
# across two cycles" needs a tolerance, and 10 is smaller than the smallest
# observed prescription move (16). The replay NEVER PLATEAUED, so this constant
# has no empirical support at all — only synthetic coverage. Same disposition:
# left as-is, recorded as untested, revisited when a block plateaus.
PLATEAU_TOL_MIN = 10

Decision = Literal["adopt", "extend", "hold", "compress", "close"]
AdherenceSource = Literal["samsung", "diary", "none"]


# ── inputs ────────────────────────────────────────────────────────────────────

@dataclass
class Night:
    """One diary night, already joined to its passive and training context.

    `samsung_bedtime` must come from the `context = 'passive_overnight'` allowlist
    and nowhere else. `training_end` is the stop_time of a session on the calendar
    day preceding the wake date, or None.
    """
    date: date                            # wake date; the diary's own row-date
    tst_min: int | None = None
    se_pct: float | None = None           # 0-100
    lights_out: str | None = None         # diary "tried to sleep"
    final_wake: str | None = None
    naps_min: int | None = None
    alcohol_units: int | None = None      # None means NOT RECORDED, not zero
    samsung_bedtime: str | None = None    # passive_overnight only
    training_end: datetime | None = None
    travel_or_match: bool = False


@dataclass
class NightVerdict:
    night: Night
    valid: bool
    reason: str | None = None             # exclusion reason when not valid
    adherence_source: AdherenceSource = "none"
    adherence_delta_min: int | None = None
    adherent: bool | None = None
    alcohol_unknown: bool = False         # admitted, but not verified clean


@dataclass
class CycleDecision:
    decision: Decision
    reason: str
    window_minutes: int
    prescribed_lights_out: str
    wake_anchor: str
    basis_tst_min: int | None = None
    basis_se_pct: float | None = None
    basis_nights_n: int = 0
    basis_n_samsung: int = 0
    basis_n_diary: int = 0
    # how much of this decision rested on nights ASSUMED clean rather than
    # verified clean — provenance, recorded regardless of the predicate's setting
    basis_n_alcohol_unknown: int = 0
    basis_window_start: date | None = None
    basis_window_end: date | None = None
    excluded_nights: dict[str, str] = field(default_factory=dict)
    # diagnostic-only, never gating
    lights_out_sd_min: float | None = None
    wake_time_sd_min: float | None = None
    ema_count: int = 0
    move_capped: bool = False


# ── exclusions ────────────────────────────────────────────────────────────────

def classify_night(night: Night, prescribed_lights_out: str) -> NightVerdict:
    """Decide whether a night counts toward the basis, and if so how its adherence
    was established. Exclusions are RECORDED with a reason, never silently dropped.

    Order matters only for which reason is reported; a night excluded for any
    reason contributes to neither the TST mean nor the adherence count.
    """
    # incomplete data cannot support a basis
    if night.tst_min is None or night.se_pct is None:
        return NightVerdict(night, False, "incomplete")

    # ALCOHOL. Only a RECORDED non-zero night is excluded. An unrecorded night is
    # admitted and flagged (`alcohol_unknown`), so the basis says how much of it
    # rested on nights assumed clean rather than verified clean.
    #
    # Excluding unknowns as well was tried and refuted on the observed block: it
    # removed 29 of 53 nights and starved the sufficiency gate to eight straight
    # HOLDs with no titration at all. Three lines of evidence licensed admitting
    # them — TST (unknown 383 vs zero 370 vs drink 430) and WASO (22 / 20 / 30)
    # both place unknowns with the zeros, while SE at 2.5-vs-2.1 is noise against
    # a within-group SD of 6-11; and decisively, ZERO of 19 blanks sit adjacent
    # to a drink night where ~3.7 would be expected under random placement
    # (p = 0.0033). That actively refutes "blank means drank and did not log",
    # which is the only hypothesis conservative exclusion was guarding against.
    #
    # RATIONALE, CORRECTED. Exclusion was originally justified as keeping
    # pharmacologically SUPPRESSED sleep out of the window estimate. The data
    # refutes that mechanism: drink nights carry the block's HIGHEST TST (430 vs
    # 370), with higher WASO at equal SE — i.e. more time in bed, not less sleep.
    # They are nights run under a different regime, later to bed or later up, so
    # the filter is functioning as a NON-ADHERENCE PROXY and overlaps the
    # adherence gate rather than acting independently of it.
    if night.alcohol_units is not None and night.alcohol_units > 0:
        return NightVerdict(night, False, "alcohol")

    # naps: Q45 — the VA instrument does not say which day a recorded nap belongs
    # to, so nap-flagged nights are excluded entirely rather than attributed.
    if night.naps_min is not None and night.naps_min > NAP_EXCLUDE_MIN:
        return NightVerdict(night, False, "nap")

    if night.travel_or_match:
        return NightVerdict(night, False, "travel_or_match")

    # constrained training night: the prescription is unreachable because the
    # session ended too late for it. Not a compliance failure — a physical floor.
    if night.training_end is not None and night.lights_out is not None:
        earliest = night.training_end + timedelta(minutes=TRAINING_RECOVERY_MIN)
        rx_min = clock_to_minutes(prescribed_lights_out)
        earliest_min = earliest.hour * 60 + earliest.minute
        if rx_min is not None and earliest_min > rx_min:
            return NightVerdict(night, False, "training_constrained")

    # valid — now establish HOW adherence is known for this night
    source: AdherenceSource = "none"
    delta = None
    if night.samsung_bedtime:
        source = "samsung"
        delta = clock_delta_minutes(prescribed_lights_out, night.samsung_bedtime)
    elif night.lights_out:
        source = "diary"
        delta = clock_delta_minutes(prescribed_lights_out, night.lights_out)
    adherent = None if delta is None else abs(delta) <= ADHERENCE_TOL_MIN
    return NightVerdict(night, True, None, source, delta, adherent,
                        alcohol_unknown=night.alcohol_units is None)


# ── diagnostics (computed, never gating) ──────────────────────────────────────

def _sd_minutes(clocks: list[str | None]) -> float | None:
    vals = [clock_to_minutes(c) for c in clocks]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    # centre so 23:50 and 00:10 are 20 apart, not 1420 — the shortest-path
    # offset is timeutil's, not re-derived here
    ref = vals[0]
    centred = [ref + signed_offset_minutes(ref, v) for v in vals]
    return round(statistics.stdev(centred), 2)


def _ema_count(verdicts: list[NightVerdict], anchor: str) -> int:
    """Early-morning awakenings: final wake before the anchor. #108 — instrumented,
    diagnostic, and explicitly not permitted to drive compression."""
    a = clock_to_minutes(anchor)
    n = 0
    for v in verdicts:
        w = clock_to_minutes(v.night.final_wake)
        if a is not None and w is not None and 0 < (a - w) <= 240:
            n += 1
    return n


# ── the cycle ─────────────────────────────────────────────────────────────────

def evaluate_cycle(
    nights: list[Night],
    current_window_min: int,
    prescribed_lights_out: str,
    wake_anchor: str,
    prior_basis_tst: list[int] | None = None,
) -> CycleDecision:
    """Adjudicate one weekly cycle. `nights` is the trailing window (<= 7 nights).

    Gates run in order and the FIRST failure short-circuits to HOLD carrying its
    reason — a later gate never overrides an earlier failure, so a HOLD always
    names the first thing that was wrong rather than the last thing checked.
    """
    nights = sorted(nights, key=lambda n: n.date)[-CYCLE_NIGHTS:]
    verdicts = [classify_night(n, prescribed_lights_out) for n in nights]
    valid = [v for v in verdicts if v.valid]
    excluded = {v.night.date.isoformat(): v.reason for v in verdicts if not v.valid}

    n_samsung = sum(1 for v in valid if v.adherence_source == "samsung")
    n_diary = sum(1 for v in valid if v.adherence_source == "diary")
    n_alc_unknown = sum(1 for v in valid if v.alcohol_unknown)

    base = dict(
        prescribed_lights_out=prescribed_lights_out,
        wake_anchor=wake_anchor,
        basis_nights_n=len(valid),
        basis_n_samsung=n_samsung,
        basis_n_diary=n_diary,
        basis_n_alcohol_unknown=n_alc_unknown,
        basis_window_start=nights[0].date if nights else None,
        basis_window_end=nights[-1].date if nights else None,
        excluded_nights=excluded,
        lights_out_sd_min=_sd_minutes([v.night.lights_out for v in valid]),
        wake_time_sd_min=_sd_minutes([v.night.final_wake for v in valid]),
        ema_count=_ema_count(valid, wake_anchor),
    )

    # ── GATE 1: sufficiency ───────────────────────────────────────────────────
    if len(valid) < MIN_VALID_NIGHTS:
        return CycleDecision(
            decision="hold",
            reason=f"insufficient_nights: {len(valid)} valid of {len(nights)}, need {MIN_VALID_NIGHTS}",
            window_minutes=current_window_min, **base,
        )

    mean_tst = round(statistics.mean(v.night.tst_min for v in valid))
    mean_se = round(statistics.mean(v.night.se_pct for v in valid), 2)
    base.update(basis_tst_min=mean_tst, basis_se_pct=mean_se)

    # ── GATE 2: adherence ─────────────────────────────────────────────────────
    # A window that is not being run cannot be extended on the strength of the
    # sleep it produced — the TST would be evidence about a different window.
    failures = [v for v in valid if v.adherent is False]
    if len(failures) >= ADHERENCE_FAIL_N:
        return CycleDecision(
            decision="hold",
            reason=(f"adherence: {len(failures)} of {len(valid)} valid nights outside "
                    f"+/-{ADHERENCE_TOL_MIN}min (source samsung={n_samsung} diary={n_diary})"),
            window_minutes=current_window_min, **base,
        )

    # ── EXIT: TST plateau across two cycles, with SE held at the floor ────────
    # Not SE stall (#107). Plateau is judged on the basis TST series, so a cycle
    # that merely repeated a HOLD does not count as a plateau observation.
    if prior_basis_tst and len(prior_basis_tst) >= 2 and mean_se >= SE_FLOOR_PCT:
        d1 = mean_tst - prior_basis_tst[-1]
        d2 = prior_basis_tst[-1] - prior_basis_tst[-2]
        if abs(d1) <= PLATEAU_TOL_MIN and abs(d2) <= PLATEAU_TOL_MIN:
            return CycleDecision(
                decision="close",
                reason=(f"tst_plateau: deltas {d2:+d}/{d1:+d} min within "
                        f"{PLATEAU_TOL_MIN}, SE {mean_se} >= {SE_FLOOR_PCT}"),
                window_minutes=current_window_min, **base,
            )

    # ── titrate ───────────────────────────────────────────────────────────────
    target = max(FLOOR_MIN, mean_tst + BUFFER_MIN)
    move = target - current_window_min
    capped = abs(move) > MAX_MOVE_MIN
    if capped:
        move = MAX_MOVE_MIN if move > 0 else -MAX_MOVE_MIN
    new_window = max(FLOOR_MIN, current_window_min + move)

    if new_window > current_window_min:
        decision, verb = "extend", "extended"
    elif new_window < current_window_min:
        decision, verb = "compress", "compressed"
    else:
        decision, verb = "hold", "unchanged"

    anchor_min = clock_to_minutes(wake_anchor)
    # minutes_to_clock wraps internally; no modulo needed at the call site
    new_lights_out = (minutes_to_clock(anchor_min - new_window)
                      if anchor_min is not None else prescribed_lights_out)

    base["prescribed_lights_out"] = new_lights_out
    return CycleDecision(
        decision=decision,
        reason=(f"{verb} {current_window_min}->{new_window}min "
                f"(mean TST {mean_tst} + {BUFFER_MIN} buffer"
                + (f", move capped at {MAX_MOVE_MIN}" if capped else "") + ")"),
        window_minutes=new_window,
        move_capped=capped,
        **base,
    )
