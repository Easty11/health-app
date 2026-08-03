"""CBT-I titration engine — weekly adjudication of the prescribed sleep window.

Controls on TOTAL SLEEP TIME with sleep efficiency as a FLOOR, never as the target
(#107). The window is rolling mean TST plus a buffer; the block exits on TST
plateau with SE held >= 85%, not on SE reaching or stalling at a threshold. An
SE-maximising rule terminates at peak efficiency, ~45 minutes short of need per
#107's sleep-need estimate.

This module is PURE: it takes `Night` records and returns a `CycleDecision`. It
opens no database session, reads no readiness output, and re-implements no clock
arithmetic (all of that is `cbti.timeutil`). The DB adapter lives in `replay.py`
and in the future prescription writer.

Gate order — first failure short-circuits to HOLD with a reason:
  1. SUFFICIENCY  >= 5 valid nights after exclusions
  2. ADHERENCE    actual bedtime vs prescribed, +/-30 min, failing on >= 3 of 7

TIB OVER-RUN is INSTRUMENTED, NOT GATED. Two candidate gates over it were considered
and left un-built. The block-2 evidence that originally drove those rejections is
DISCARDED for outcome claims (prescriptions were extended mid-block, TIB was not held,
and the ledger/diary spans disagree), so any count it produced here is void; what
remains below is only the reasoning that stands on first principles.

  1. A second ADHERENCE ARM on `out_of_bed` vs the wake anchor (+/-30, same
     >=3-of-7 threshold). Structural mismatch: a count-based >=3-of-7 rule responds
     to MANY-AND-SMALL deviations, not FEW-AND-LARGE ones, so it is the wrong
     instrument for wake-end failures IF those are few-and-large. Whether they are
     is NOT ATTESTED — prior block discarded. The arm stays un-built and the
     question open.

  2. A DIRECT TIB gate (mean TIB - window > tolerance). Withdrawn on a
     FIRST-PRINCIPLES ground that needs no block: it measures what the SE floor
     already measures — SE is TST/TIB and over-run is TIB minus window, so the two
     share TIB and move together BY CONSTRUCTION, not as a finding. Redundant with
     the SE floor. (A tolerance would also have to be read off the same block it
     then "validates" — circular — but the redundancy alone is sufficient.)

  The discriminator that matters is SE AT over-run, not over-run MAGNITUDE: a night
  that over-runs at high SE is genuine capacity (slept through the extra time); one
  that over-runs at low SE is time lying awake. The SE floor already separates these
  without a new gate, and gating over-run out as contamination would contradict the
  sleep-need estimate #107 rests on. (The per-cycle SE figures that once illustrated
  this are block-2 outcomes — discarded.)

Regularity (lights-out SD, wake-time SD) is COMPUTED AND REPORTED but does not gate
(#114): retained as an observational construct, not a titration signal — regularity
is context for a reading, not itself a control quantity. (The block-2 correlation and
week-count that argued against gating are discarded — prior block.) Early-morning
awakening is instrumented but never drives compression (#108): observational only.
(Its block-2 clustering figures are discarded.)
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from cbti.timeutil import (
    clock_delta_minutes,
    clock_to_minutes,
    minutes_to_clock,
    signed_offset_minutes,
    tib_minutes,
)

# ── constants ─────────────────────────────────────────────────────────────────
# CHOSEN, not block-derived. 30 min is the standard sleep-restriction-therapy buffer
# added to mean TST when setting the window — a first-principles / literature support
# that stands without the prior block. (A block-2 derivation once co-supported ~30 but
# is discarded for outcome claims; the SRT-buffer support is sufficient on its own.)
BUFFER_MIN = 30

FLOOR_MIN = 300               # 5h00 — never prescribe below this
SE_FLOOR_PCT = 85.0           # #107: efficiency is the floor, not the target
# UNDETERMINABLE FROM THE OBSERVED BLOCK. The three cycles that failed this gate
# had n = 3, 3, 2. Lowering the threshold to 4 changes nothing — all three still
# fail; lowering to 3 rescues two and still leaves one. The block's failures sit
# far below any defensible value, so it cannot distinguish the options.
#
# 5 -> 3 with the move to a 4-night cadence, and this one is FORCED, not chosen: a
# sufficiency threshold of 5 cannot be met inside a 4-night cycle, so leaving it would
# make GATE 1 unsatisfiable and the engine would HOLD forever. 3 of 4 is the loosest
# value that still requires a majority of the cycle. CHOSEN, not derived (unattested).
# INVARIANT: MIN_VALID_NIGHTS < CYCLE_NIGHTS — asserted below.
MIN_VALID_NIGHTS = 3          # sufficiency gate
ADHERENCE_TOL_MIN = 30        # +/- tolerance on bedtime vs prescription — CHOSEN, not derived (unattested; see OPEN_QUESTIONS)
# 3 -> 2, rescaling the numerator to a 4-night denominator: 3-of-7 was very roughly a
# majority-of-half, and 2-of-4 keeps the gate at a comparable strictness rather than
# letting it slacken by accident when the cycle shortened. CHOSEN, not derived.
ADHERENCE_FAIL_N = 2          # >= this many failures in the cycle -> HOLD — CHOSEN, not derived (unattested; see OPEN_QUESTIONS)
# 7 -> 4: the titration is a perpetual small-step hunting search, not a weekly
# converge-and-close arc. No source supports 4 nights specifically — the SRT literature
# has never studied the titration interval as a variable — so this is an operator choice
# adopted engagement-first, paired with the smaller MAX_MOVE_MIN so that 4-night noise
# cannot move the window far. CHOSEN, not derived (unattested; Q55).
CYCLE_NIGHTS = 4
NAP_EXCLUDE_MIN = 0           # Q45: ANY nap-flagged night is excluded, not >20
TRAINING_RECOVERY_MIN = 90    # constrained night floor = session end + 90 min

# UNVALIDATED BY THE OBSERVED BLOCK. Not derived from data; the observed
# prescription moves ranged 1..35 min so this would have clipped one of eight,
# but on replay the cap BOUND IN ZERO of 8 cycles — the block never exercised it.
#
# 30 -> 15: this is now the DITHER STEP of a hunting search, not a safety clip on a
# weekly move. At a 4-night cadence the cap binds most cycles by design — that is the
# mechanism, not a side effect: the window is meant to oscillate in small steps around
# a setpoint, and the reported estimate is the CENTRE of that oscillation
# (`centre_estimate`), never a single cycle's bouncing value. CHOSEN, not derived
# (unattested; Q55).
MAX_MOVE_MIN = 15

# UNVALIDATED BY THE OBSERVED BLOCK. Not specified by the brief; "TST plateau
# across two cycles" needs a tolerance, and 10 is smaller than the smallest
# observed prescription move (16). The replay NEVER PLATEAUED, so this constant
# has no empirical support at all — only synthetic coverage. Same disposition:
# left as-is, recorded as untested, revisited when a block plateaus.
PLATEAU_TOL_MIN = 10

# How many recent cycles the sleep-need estimate averages over. The window itself now
# dithers by +/-MAX_MOVE_MIN and is NOT the estimate; the centre of the dither is.
# CHOSEN, not derived (unattested; Q55) — 4 cycles is roughly a fortnight at the
# 4-night cadence, long enough to average out the oscillation and short enough that a
# genuine drift in sleep need still moves it.
CENTRE_CYCLES = 4

# The cadence cascade, asserted rather than trusted to review: a sufficiency threshold
# at or above the cycle length makes GATE 1 unsatisfiable, so the engine would HOLD on
# every cycle forever and the failure would look like "titration stalled", not like a
# bad constant. Cheap to check at import; impossible to miss if it ever regresses.
assert MIN_VALID_NIGHTS < CYCLE_NIGHTS, (
    f"MIN_VALID_NIGHTS ({MIN_VALID_NIGHTS}) must be < CYCLE_NIGHTS ({CYCLE_NIGHTS}) — "
    "otherwise the sufficiency gate can never be satisfied"
)

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
    lights_out: str | None = None         # diary "tried to sleep" — SE window opens
    out_of_bed: str | None = None         # SE window closes; needed for TIB over-run
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
    # The cycle plateaued: TST flat across two cycles with SE at the floor. A HOLD like
    # any other as far as the ledger is concerned — the window does not move — but the
    # surface distinguishes "converged, holding here" from "held because a gate failed",
    # which are opposite messages. Replaces the `close` decision this branch used to
    # return; the block no longer exits on it.
    converged: bool = False
    # INSTRUMENTED, NOT GATED. Mean TIB over the basis nights minus the prescribed
    # window: how far the window was over-run in practice. Recorded because it
    # cannot yet be adjudicated — see the TIB-gate note above. Mean-based and so
    # outlier-sensitive: a single large-over-run night pulls a small-n cycle mean, so
    # a future threshold must be set against a distribution across blocks, not read
    # off one. (The block-2 night that once illustrated this is discarded for outcome claims.)
    basis_tib_over_run_min: float | None = None
    # INSTRUMENTED, NOT GATED (#124). Nights elapsed since the current prescription's
    # effective_from — the settling period. NOT `basis_`-prefixed: the basis_* fields are
    # properties of the basis window the engine computes; this is passed-in cycle context
    # the engine cannot compute (it has no prescription, only nights and a window), so it
    # is named like the other unprefixed diagnostics (ema_count, move_capped). NOTHING
    # branches on it — the settling parameter is undeterminable from both available
    # sources and the observed failure mode is under-firing, so a fourth gate would move
    # against the defect the data shows. Recorded so a curve can be fit later. None is
    # CORRECT here (no prescription context — replay/tests) and must stay inert: do NOT
    # convert to a gate by analogy to #122, where naps' 0-not-null WAS load-bearing.
    nights_since_effective_from: int | None = None


# ── exclusions ────────────────────────────────────────────────────────────────

def classify_night(night: Night, prescribed_lights_out: str) -> NightVerdict:
    """Decide whether a night counts toward the basis, and if so how its adherence
    was established. Exclusions are RECORDED with a reason, never silently dropped.

    Order matters only for which reason is reported; a night excluded for any
    reason contributes to neither the TST mean nor the adherence count.
    """
    # incomplete data cannot support a basis.
    # MARKER (not implemented): this gates on `se_pct` being present. A pending policy
    # revision retires SE as a control quantity; when that is ratified this predicate
    # must be RESTATED over the recall components (e.g. tst / diary times) rather than
    # SE. Not changed here — the revision is not minted, and redefining the gate now
    # would be building against an unratified spec.
    if night.tst_min is None or night.se_pct is None:
        return NightVerdict(night, False, "incomplete")

    # ALCOHOL. Only a RECORDED non-zero night is excluded. An unrecorded night is
    # admitted and flagged (`alcohol_unknown`), so the basis records how much of it
    # rested on nights assumed clean rather than verified clean.
    #
    # RATIONALE (first-principles): alcohol alters sleep architecture, so a drink
    # night is evidence about a DIFFERENT physiological state than the one being
    # titrated — structurally the same argument as the adherence gate (a night not
    # run to prescription is evidence about a different window). Excluded on that
    # ground, not on any block-2 measurement (the block that once supplied the
    # TST/adjacency figures here is discarded for outcome claims).
    #
    # PENDING POLICY (not implemented): a policy revision would reclass this
    # exclusion as EXCUSABLE rather than DISQUALIFYING. Those classes do not exist
    # in code and the revision is not ratified, so this stays a plain exclusion —
    # building the split now would be constructing against an unratified spec.
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

    # valid — now establish HOW adherence is known for this night.
    # RECALL-ONLY (#127): adherence differences the prescribed lights-out against the
    # DIARY lights_out only. A device-DETECTED onset (samsung_bedtime) is a different
    # construct from a RECALLED lights-out ("tried to sleep"); clinical CBT-I is
    # recall-only by design, and its ~10-min detection lag can flip a borderline night
    # against the ±30 band (Q47). Diary lights_out coverage is complete on the observed
    # block (51/51) so there is no fallback gap, and the Samsung arm never executed on a
    # completed block (samsung_hrv_readings begins 2026-06-08, after block 2 closed) — so
    # nothing historical is revalued. samsung_bedtime is left on the Night dataclass and
    # in replay's _SAMSUNG_SQL (now dead as an adherence input, still populated and
    # counted by the n_with_samsung diagnostic); AdherenceSource='samsung' / n_samsung
    # are now structurally 0. Their removal is deferred, not folded into this change.
    source: AdherenceSource = "none"
    delta = None
    if night.lights_out:
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


def _mean_tib_over_run(verdicts: list[NightVerdict], window_min: int) -> float | None:
    """Mean actual TIB across the basis nights, minus the prescribed window.

    Positive means the window was over-run. Instrumented only — see the module
    docstring for why the two candidate gates over this quantity were rejected.
    """
    tibs = [
        tib_minutes(clock_to_minutes(v.night.lights_out),
                    clock_to_minutes(v.night.out_of_bed))
        for v in verdicts
    ]
    tibs = [t for t in tibs if t is not None]
    if not tibs:
        return None
    return round(statistics.mean(tibs) - window_min, 1)


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

def centre_estimate(windows: list[int], n: int = CENTRE_CYCLES) -> float | None:
    """The sleep-need estimate: the CENTRE of the window dither, not the current window.

    Pure. Takes prescribed window lengths in ledger order (oldest first) and returns the
    mean of the most recent `n`, or None when there is nothing to average.

    WHY THIS EXISTS. Under the hunting search the window oscillates by +/-MAX_MOVE_MIN
    around wherever the setpoint actually is, so any single cycle's window is a sample
    of an oscillation, not an estimate of need — reporting it would make the app look
    like it changes its mind every four nights. The centre is the estimate; the window
    is the probe. A drifting centre is the real signal (see the decision's revisit
    clause: a wandering centre means the extend/compress boundary is biased).

    Deliberately a mean over the last n, not an EMA: with a symmetric dither the mean
    over a whole number of oscillations is unbiased and trivially explainable to the
    person whose sleep it describes. Fewer than `n` windows averages what exists rather
    than returning None — an estimate from 2 cycles is worse than one from 4, but it is
    not nothing, and the caller is told how many it rests on.
    """
    recent = [w for w in windows if w is not None][-n:]
    if not recent:
        return None
    return round(statistics.mean(recent), 1)


def evaluate_cycle(
    nights: list[Night],
    current_window_min: int,
    prescribed_lights_out: str,
    wake_anchor: str,
    prior_basis_tst: list[int] | None = None,
    nights_since_effective_from: int | None = None,
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
        basis_tib_over_run_min=_mean_tib_over_run(valid, current_window_min),
        lights_out_sd_min=_sd_minutes([v.night.lights_out for v in valid]),
        wake_time_sd_min=_sd_minutes([v.night.final_wake for v in valid]),
        ema_count=_ema_count(valid, wake_anchor),
        # instrumented, not gated (#124) — see the dataclass field. Carried into base so
        # it lands on ALL four verdict paths, HOLDs included (a HOLD is exactly where
        # "how few nights had elapsed" matters). None = no prescription context; nothing
        # branches on it, so there is no gate to disable.
        nights_since_effective_from=nights_since_effective_from,
    )

    # ── GATE 1: sufficiency ───────────────────────────────────────────────────
    # The reason NAMES WHAT WAS EXCLUDED, not just the shortfall. At a 4-night cadence
    # with a 3-night threshold the margin is one night, so exclusions starve a cycle far
    # more readily than they did at 7/5 — two nap nights is now enough to stall
    # titration outright. Q45 excludes ANY nap-flagged night (the instrument does not say
    # which day a nap belongs to), so a frequent napper can stall repeatedly while the
    # surface says only "insufficient". Naming the tally makes a stall diagnosable
    # instead of mysterious. This is SURFACING ONLY — no threshold moves, NAP_EXCLUDE_MIN
    # is untouched, and Q45 stays open.
    if len(valid) < MIN_VALID_NIGHTS:
        tally = Counter(excluded.values())
        detail = ", ".join(f"{reason} x{n}" for reason, n in sorted(tally.items()))
        return CycleDecision(
            decision="hold",
            reason=(f"insufficient_nights: {len(valid)} valid of {len(nights)}, "
                    f"need {MIN_VALID_NIGHTS}"
                    + (f" ({len(excluded)} excluded: {detail})" if excluded else "")),
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

    # ── CONVERGED: TST plateau across two cycles, with SE held at the floor ───
    # Not SE stall (#107). Plateau is judged on the basis TST series, so a cycle
    # that merely repeated a HOLD does not count as a plateau observation.
    #
    # THIS NO LONGER RETURNS `close`. #107 exited the block here; the titration is now a
    # perpetual hunting search, so a plateau means "found the spot — hold here and keep
    # watching", not "done". The block stays open and evaluation continues, so a later
    # drift shows up as movement in a live series with its cause alongside it, rather
    # than requiring someone to notice and re-open a closed block from scratch.
    #
    # `close` stays in the `Decision` vocabulary and in the DB CHECK constraint: block 1
    # was imported carrying it (`import_cbti_block.py`) and the ledger is append-only, so
    # retiring the value would invalidate history. The engine simply never emits it now.
    if prior_basis_tst and len(prior_basis_tst) >= 2 and mean_se >= SE_FLOOR_PCT:
        d1 = mean_tst - prior_basis_tst[-1]
        d2 = prior_basis_tst[-1] - prior_basis_tst[-2]
        if abs(d1) <= PLATEAU_TOL_MIN and abs(d2) <= PLATEAU_TOL_MIN:
            return CycleDecision(
                decision="hold",
                converged=True,
                reason=(f"converged: tst_plateau deltas {d2:+d}/{d1:+d} min within "
                        f"{PLATEAU_TOL_MIN}, SE {mean_se} >= {SE_FLOOR_PCT} — "
                        f"window held, block stays open"),
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
