"""
Psychological window — a RESIDUAL producer plus a LIFE-LOAD modulator (S4 §3).

Two concerns, two clocks, both computed at READ time (derived, never persisted —
same principle as `reads/recovery_reads.py` / `reads/aerobic_reads.py`; no schema):

  • life_load_bias(...)          — FAST signal (days-τ). A down-only boolean fed to
                                   the selection re-rank as a SIBLING to
                                   `readiness_hint` (DECISIONS_LOG #8 shape). Build
                                   + wire now.
  • psychological_residual(...)  — SLOW signal (~7-day τ). actual sRPE minus what
                                   objective load predicts (a ridge regression), the
                                   subjective-vs-objective DECOUPLING marker (#28).
                                   Producer builds now; its consumer (a block-level
                                   plan) is DEFERRED until that surface lands — this
                                   module emits the smoothed value and stubs no fake
                                   consumer.

WHY A RESIDUAL, NOT A BANISTER STOCK (resolves Q122 → the divergence-criterion horn).
Psychological is deliberately NOT a Banister fitness/fatigue pair (S4 §3.1, forbidden):
`load_metrics.py` is FAIL-CLOSED for it (no `psychological` fatigue-τ key), and that
guard STAYS. This window builds no psychological "fitness". It measures the gap between
how hard a day FELT (session-RPE × duration) and how hard the objective load says it
should have felt — a positive residual = felt harder than the load predicts.

DOWN-ONLY, FAIL-CLOSED (S4 gate 1). Neither output can ever grant upward permission.
`life_load_bias` can only ADD a recovery bias; absent data → False. The residual is a
diagnostic the (deferred) consumer may only bias DOWN with.

PREDICTORS ARE THE ACUTE PER-DAY IMPULSE, NOT THE EWMA STOCKS (S4 D3). We regress
actual sRPE on the day's `daily_load` per physical window (the same impulse that feeds
Banister — sum of that day's `load_events`), NOT on the fitness/fatigue stocks:
regressing out the fatigue stock would erase the very decoupling the residual exists to
catch. Psychological `load_events` are NEVER a predictor (exclusivity, gate 2).

GRAIN (S4 D2): per-training-day. `session_rpe` is one-per-day (a whole-day-retrospective
RPE captured at PM check-in — a known recency bias vs the ~30-min-post-session target,
S4 LOG; v1 accepts current timing). A day with more than one session is FLAGGED, never
silently averaged under one RPE (gate 5): duration is SUMMED (total training time paired
with the one whole-day RPE) and the day is recorded in `multi_session_days`.

NO NUMPY. The S4 brief assumed numpy "already used by the load transforms"; it is not a
dependency of this repo (`load_metrics.py` uses `math`). The ridge is a 3-predictor
closed form, so it is implemented in pure Python here — no new dependency (gate 4).
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

import models
from load_events import FORMULA_VERSION as _FV_STRENGTH, WINDOW_MECHANICAL, WINDOW_NEUROMUSCULAR
from load_events_metabolic import FORMULA_VERSION_METABOLIC as _FV_METABOLIC, WINDOW_METABOLIC
from load_metrics import _local_day  # identical AEST day-bucketing as the Banister rollup

# ---------------------------------------------------------------------------
# REASONED-PRIOR constants — calibratable, never magic numbers (S4 §3.5/§3.7).
# ---------------------------------------------------------------------------

# The physical windows whose per-day `daily_load` impulse are the ridge predictors,
# each PAIRED with the formula_version its producing transform writes. These are NOT
# one version: the Hevy transform writes mechanical + neuromuscular under `tier0-v1`
# (load_events.FORMULA_VERSION) while the aerobic transform writes metabolic under
# `metab-v1` (load_events_metabolic.FORMULA_VERSION_METABOLIC). Filtering on a single
# version therefore SILENTLY drops a whole window — metabolic never entered the fit —
# so we match the (window, version) PAIR and never sum a window across versions.
# Imported from the transforms so a version bump there cannot drift this pairing.
# `psychological` is DELIBERATELY absent — it is never a predictor of its own residual
# (exclusivity, gate 2), mirroring load_metrics' fail-closed window allowlist.
PREDICTOR_WINDOW_VERSIONS: dict[str, str] = {
    WINDOW_MECHANICAL: _FV_STRENGTH,
    WINDOW_METABOLIC: _FV_METABOLIC,
    WINDOW_NEUROMUSCULAR: _FV_STRENGTH,
}
PREDICTOR_WINDOWS: tuple[str, ...] = tuple(PREDICTOR_WINDOW_VERSIONS)

# Ridge penalty. Predictors are standardised (z-scored) before the fit, so λ is
# scale-invariant and a mild λ=1.0 is the standard small-N default: enough to tame the
# by-construction collinearity of the three load windows without swamping the signal.
RIDGE_LAMBDA = 1.0

# Cold-start HARD FLIP (S4 §3.5). Below this many PAIRED days the residual is not
# emitted at all (life-load-only mode); at/above it, residual on. No confidence-weighted
# ramp (S4 §5 — build only if the flip proves jumpy).
N_COLDSTART_PAIRED_DAYS = 15

# τ (days) for the EWMA smoothing the residual series. One τ on the residual only —
# there is NO fitness/fatigue τ pair anywhere in this window. ~7 d starting point.
RESIDUAL_TAU_DAYS = 7.0

# ── life-load modulator ──────────────────────────────────────────────────────
# Fast accumulation EWMA over a combined stress+poor-sleep severity in [0, 1].
LIFE_LOAD_TAU_DAYS = 3.0          # days-τ — stress accumulates and decays fast
LIFE_LOAD_LOOKBACK_DAYS = 21      # window read back from as_of to seed the EWMA
# Poor-sleep normalisation against canonical TST (#254 true TST). At/above TARGET → 0
# (not poor); at/below FLOOR → 1 (worst). Minutes.
SLEEP_TARGET_MIN = 480.0          # 8 h
SLEEP_FLOOR_MIN = 300.0           # 5 h
# Monotone combine weights (sum to 1); renormalised over whichever components a day has.
W_STRESS = 0.5
W_SLEEP = 0.5
# The EWMA severity at/above which `life_load_bias` fires. 0.60 keeps a neutral day
# (life_load≈3, ~target sleep → ~0.5) BELOW the line, so the flag marks genuinely
# elevated load, not the baseline. Down-only, so erring toward firing is the safe side
# (a spurious down-bias is inert; only a spurious UP would be unsafe — gate 1).
SEVERITY_THRESHOLD = 0.60


# ---------------------------------------------------------------------------
# Pure math — ridge + time-aware EWMA (no DB)
# ---------------------------------------------------------------------------

def _solve(a: list[list[float]], b: list[float]) -> Optional[list[float]]:
    """Solve the small linear system a·x = b by Gaussian elimination with partial
    pivoting. Returns None if singular (degenerate — caller falls back). Pure Python;
    the system is (#predictors)×(#predictors), tiny by construction."""
    n = len(b)
    # Augmented matrix (copy — never mutate the caller's rows).
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        piv = m[col][col]
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col] / piv
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


@dataclass(frozen=True)
class RidgeFit:
    """A fitted ridge model over standardised predictors, plus the per-row residuals."""
    intercept: float                 # = mean(y) (y is centred; predictors are centred)
    beta: list[float]                # coefficients on the STANDARDISED predictors
    means: list[float]               # per-predictor mean (for scoring new rows)
    stds: list[float]                # per-predictor std (0 → treated as constant column)
    predicted: list[float]           # ŷ per training row
    residuals: list[float]           # y − ŷ per training row


def ridge_fit(x: list[list[float]], y: list[float], *, lam: float = RIDGE_LAMBDA) -> RidgeFit:
    """Closed-form ridge on standardised predictors with an UNPENALISED intercept.

    β = (ZᵀZ + λI)⁻¹ Zᵀ y_c   where Z is column-standardised X and y_c is centred y.
    The intercept is mean(y) (recovered because both sides are centred), so it is never
    shrunk toward zero. A zero-variance predictor column contributes nothing (its
    standardised column is all-zero) rather than dividing by zero.

    Requires len(x) == len(y) >= 1 and every row the same width; the caller (the
    producer) only fits once it has N_COLDSTART_PAIRED_DAYS rows.
    """
    n = len(y)
    p = len(x[0]) if x else 0
    means = [sum(row[j] for row in x) / n for j in range(p)]
    # Sample std (n-1); guard tiny variance to "constant column".
    stds: list[float] = []
    for j in range(p):
        var = sum((row[j] - means[j]) ** 2 for row in x) / max(1, n - 1)
        stds.append(math.sqrt(var) if var > 1e-18 else 0.0)

    def _z(row: list[float]) -> list[float]:
        return [((row[j] - means[j]) / stds[j]) if stds[j] > 0 else 0.0 for j in range(p)]

    z = [_z(row) for row in x]
    y_mean = sum(y) / n
    yc = [yi - y_mean for yi in y]

    # Normal equations (ZᵀZ + λI) β = Zᵀ yc.
    ztz = [[sum(z[r][i] * z[r][j] for r in range(n)) for j in range(p)] for i in range(p)]
    for i in range(p):
        ztz[i][i] += lam
    zty = [sum(z[r][i] * yc[r] for r in range(n)) for i in range(p)]

    beta = _solve(ztz, zty) or [0.0] * p  # singular → intercept-only (predict the mean)

    predicted = [y_mean + sum(z[r][j] * beta[j] for j in range(p)) for r in range(n)]
    residuals = [y[r] - predicted[r] for r in range(n)]
    return RidgeFit(
        intercept=y_mean, beta=beta, means=means, stds=stds,
        predicted=predicted, residuals=residuals,
    )


def ewma_time_aware(
    series: list[tuple[date, float]], *, tau_days: float
) -> Optional[float]:
    """Latest value of a time-aware EWMA over a date→value series.

    `series` need not be sorted; empty → None. A calendar GAP decays the running mean
    toward the new observation: weight-on-old = e^(−Δdays/τ), so a stale smoothed value
    yields to a fresh point after a long gap (the right behaviour for an accumulation
    signal). The first point seeds the mean.
    """
    if not series:
        return None
    ordered = sorted(series, key=lambda t: t[0])
    ewma = ordered[0][1]
    prev_day = ordered[0][0]
    for day, val in ordered[1:]:
        gap = max(0, (day - prev_day).days)
        w_old = math.exp(-gap / tau_days) if tau_days > 0 else 0.0
        ewma = w_old * ewma + (1.0 - w_old) * val
        prev_day = day
    return ewma


# ---------------------------------------------------------------------------
# DB reads (query-only helpers — the module's read seam)
# ---------------------------------------------------------------------------

def _aest_today() -> date:
    import pytz
    return datetime.now(pytz.timezone("Australia/Brisbane")).date()


def _daily_load_by_window(db: Session, user_id: int) -> dict[date, dict[str, float]]:
    """AEST-day → {physical window → Σ daily_load} from `load_events`.

    Reads `load_events` ONLY (never raw Hevy/aerobic payloads — same discipline as
    load_metrics) and buckets to the user-local day with the IDENTICAL `_local_day`
    rule, so this residual's predictors sit on the same calendar as the Banister rollup.

    Matches each window to its PRODUCING formula_version (PREDICTOR_WINDOW_VERSIONS) as
    a (window, version) pair — mechanical/neuromuscular under tier0-v1, metabolic under
    metab-v1. A window is summed only within its own version, never across versions, and
    a window whose events sit under a different version than expected simply do not enter
    (they are not this window's canonical load). A psychological load_event never enters
    as a predictor (gate 2). Undated events cannot be placed on a day and are skipped.
    """
    pair_filter = or_(*[
        and_(models.LoadEvent.load_window == w, models.LoadEvent.formula_version == v)
        for w, v in PREDICTOR_WINDOW_VERSIONS.items()
    ])
    events = db.execute(
        select(models.LoadEvent).where(
            models.LoadEvent.user_id == user_id,
            models.LoadEvent.occurred_at.is_not(None),
            pair_filter,
        )
    ).scalars().all()
    out: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in events:
        if e.occurred_at is None:  # defensive; query already excludes
            continue
        out[_local_day(e.occurred_at)][e.load_window] += float(e.load)
    return out


def _duration_min_by_day(db: Session, user_id: int) -> dict[date, tuple[float, int]]:
    """AEST-day → (Σ session duration minutes, session count).

    Duration is resolved at READ time from the session stores (S4 D4 — no new column,
    migration-free):
      • `aerobic_sessions.duration_minutes`, keyed on `session_date` (already a local
        date).
      • Hevy `hevy_workouts`, duration = end_time − start_time, bucketed to the AEST day
        of `start_time` via the same `_local_day` rule.
    Durations SUM within a day and the session count is retained so a multi-session day
    is flagged, never averaged (gate 5). A session with no usable duration contributes
    no minutes but still counts toward the session tally.
    """
    out_min: dict[date, float] = defaultdict(float)
    out_n: dict[date, int] = defaultdict(int)

    for s in db.execute(
        select(models.AerobicSession).where(models.AerobicSession.user_id == user_id)
    ).scalars().all():
        day = s.session_date
        out_n[day] += 1
        if s.duration_minutes is not None and s.duration_minutes > 0:
            out_min[day] += float(s.duration_minutes)

    for w in db.execute(
        select(models.HevyWorkout).where(models.HevyWorkout.user_id == user_id)
    ).scalars().all():
        if w.start_time is None:
            continue
        day = _local_day(w.start_time)
        out_n[day] += 1
        if w.end_time is not None:
            mins = (w.end_time - w.start_time).total_seconds() / 60.0
            if mins > 0:
                out_min[day] += mins

    return {d: (out_min.get(d, 0.0), out_n.get(d, 0)) for d in out_n}


def _session_rpe_by_day(db: Session, user_id: int) -> dict[date, float]:
    """AEST-day → session_rpe (0–10) for days where it was captured (training days)."""
    rows = db.execute(
        select(models.DailyRecord.date, models.DailyRecord.session_rpe).where(
            models.DailyRecord.user_id == user_id,
            models.DailyRecord.session_rpe.is_not(None),
        )
    ).all()
    return {d: float(rpe) for d, rpe in rows if rpe is not None}


# ---------------------------------------------------------------------------
# Residual producer (SLOW; consumer deferred)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PsychologicalResidual:
    """The smoothed subjective-vs-objective residual. Positive = felt harder than the
    objective load predicts (the decoupling marker). A DIAGNOSTIC — a consumer may bias
    DOWN with it, never up (gate 1). Its block-level consumer is deferred."""
    smoothed_residual: float          # time-aware EWMA of the residual series (~7 d τ)
    latest_residual: float            # the most recent paired day's raw residual
    latest_day: date
    n_paired_days: int
    multi_session_days: list[date]    # days with >1 session (grain caveat, gate 5)


def psychological_residual(
    user_id: int, db: Session, *, as_of: Optional[date] = None
) -> Optional[PsychologicalResidual]:
    """Compute the smoothed psychological residual, or None in cold-start.

    A day is PAIRED iff `session_rpe` is present AND its physical load is resolvable
    (a resolvable session duration > 0 that day — `actual_sRPE = session_rpe ×
    duration_min` needs it). Predictors are the day's per-window `daily_load` impulse
    (0 where a window logged nothing — a legitimate value, not missing). Below
    N_COLDSTART_PAIRED_DAYS paired days → None (life-load-only mode; no residual, no
    confidence-weighted ramp). At/above → ridge-fit and EWMA-smooth.
    """
    as_of = as_of or _aest_today()

    rpe_by_day = _session_rpe_by_day(db, user_id)
    dur_by_day = _duration_min_by_day(db, user_id)
    load_by_day = _daily_load_by_window(db, user_id)

    # Assemble paired rows in ascending date order (≤ as_of).
    paired_days: list[date] = []
    x: list[list[float]] = []
    y: list[float] = []
    multi_session_days: list[date] = []
    for day in sorted(rpe_by_day):
        if day > as_of:
            continue
        dur, n_sessions = dur_by_day.get(day, (0.0, 0))
        if dur <= 0:
            continue  # physical load not resolvable → not a paired day
        actual = rpe_by_day[day] * dur
        loads = load_by_day.get(day, {})
        x.append([float(loads.get(w, 0.0)) for w in PREDICTOR_WINDOWS])
        y.append(actual)
        paired_days.append(day)
        if n_sessions > 1:
            multi_session_days.append(day)

    if len(paired_days) < N_COLDSTART_PAIRED_DAYS:
        return None  # cold-start hard flip: life-load-only mode

    fit = ridge_fit(x, y)
    series = list(zip(paired_days, fit.residuals))
    smoothed = ewma_time_aware(series, tau_days=RESIDUAL_TAU_DAYS)
    return PsychologicalResidual(
        smoothed_residual=round(smoothed, 6) if smoothed is not None else 0.0,
        latest_residual=round(fit.residuals[-1], 6),
        latest_day=paired_days[-1],
        n_paired_days=len(paired_days),
        multi_session_days=multi_session_days,
    )


# ---------------------------------------------------------------------------
# Life-load modulator (FAST; wired into selection now)
# ---------------------------------------------------------------------------

def _sleep_severity(tst_min: Optional[float]) -> Optional[float]:
    """Poor-sleep severity in [0, 1] from canonical TST minutes, or None if absent.
    At/above SLEEP_TARGET_MIN → 0; at/below SLEEP_FLOOR_MIN → 1; linear between."""
    if tst_min is None:
        return None
    if tst_min >= SLEEP_TARGET_MIN:
        return 0.0
    if tst_min <= SLEEP_FLOOR_MIN:
        return 1.0
    return (SLEEP_TARGET_MIN - tst_min) / (SLEEP_TARGET_MIN - SLEEP_FLOOR_MIN)


def _stress_severity(life_load: Optional[int]) -> Optional[float]:
    """Psychosocial-stress severity in [0, 1] from life_load (1–5, higher = worse),
    or None if absent. 1→0 … 5→1."""
    if life_load is None:
        return None
    ll = max(1, min(5, int(life_load)))
    return (ll - 1) / 4.0


def _combine_severity(stress: Optional[float], sleep: Optional[float]) -> Optional[float]:
    """Monotone combine of the two 0..1 severities, renormalising the weights over
    whichever components are present. None only if BOTH are absent."""
    parts: list[tuple[float, float]] = []
    if stress is not None:
        parts.append((W_STRESS, stress))
    if sleep is not None:
        parts.append((W_SLEEP, sleep))
    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / wsum


def life_load_severity(
    user_id: int, db: Session, *, as_of: Optional[date] = None
) -> Optional[float]:
    """The EWMA (fast, days-τ) of combined stress+poor-sleep severity over the recent
    window, or None when no life-load data is present at all (fail-closed).

    Reads `daily_records` ONCE per call: `life_load` (self-report) and the CANONICAL
    sleep already snapshotted there — `passive_sleep_min`, the frozen #254 true TST used
    everywhere else (S4 gate 3: read the canonical sleep, mint no second estimate; and
    it is NEVER fed into a physical window). A day with neither component is skipped; a
    day with one uses that one.
    """
    as_of = as_of or _aest_today()
    since = as_of - timedelta(days=LIFE_LOAD_LOOKBACK_DAYS)
    rows = db.execute(
        select(
            models.DailyRecord.date,
            models.DailyRecord.life_load,
            models.DailyRecord.passive_sleep_min,
        ).where(
            models.DailyRecord.user_id == user_id,
            models.DailyRecord.date >= since,
            models.DailyRecord.date <= as_of,
        )
    ).all()

    series: list[tuple[date, float]] = []
    for day, life_load, sleep_min in rows:
        sev = _combine_severity(
            _stress_severity(life_load),
            _sleep_severity(float(sleep_min) if sleep_min is not None else None),
        )
        if sev is not None:
            series.append((day, sev))
    return ewma_time_aware(series, tau_days=LIFE_LOAD_TAU_DAYS)


def life_load_bias(
    user_id: int, db: Session, *, as_of: Optional[date] = None
) -> bool:
    """Down-only life-load flag for the selection re-rank (S4 §3 emit contract).

    True iff the EWMA severity crosses SEVERITY_THRESHOLD. FAIL-CLOSED to False when
    life-load data is absent (severity None). By construction the flag can only ADD a
    recovery bias — never license up (gate 1).
    """
    sev = life_load_severity(user_id, db, as_of=as_of)
    if sev is None:
        return False
    return sev >= SEVERITY_THRESHOLD
