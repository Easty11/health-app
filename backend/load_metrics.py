"""Q6 gate 3 — the daily load rollup: `load_events` → `load_metrics`.

The top of the two-level derived store (DECISIONS_LOG #28/#32, D-B). Gate 2's
`load_events` (per session-window) is read here and rolled to one per-(user, day,
load_window) row carrying the Banister Fitness/Fatigue/Form curves (#32) and the #33
ΔLoad acute:chronic ratio. This transform reads `load_events` ONLY — never the raw Hevy
payload (D-B: a derived layer recomputes from the layer below, not from source).

Per D-B the stored stocks are a RECOMPUTE, never a migration. Two version axes pin a
row's identity: `formula_version` (inherited from the load_events transform) and
`metrics_version` (this layer's τ-set / EWMA identity). A τ tune bumps `metrics_version`
and delete-and-reinserts per `(user, formula_version, metrics_version)`; a `form` k-change
is a form-column refresh derivable from the stored stocks alone — neither a stock
recompute nor a `metrics_version` bump.

Windows are computed only where `load_events` supply rows (today: mechanical,
neuromuscular). The fatigue-τ table has NO `psychological` key, so that window is
FAIL-CLOSED — a psychological load_event produces no metric row until a τ prior is minted
(OPEN_QUESTIONS Q122). `metabolic` carries a τ (provisioned) and lights up the moment a
Metabolic→load_events transform feeds it; no re-architecting.

Re-runnable CLI (mirrors load_events.py):
    python backend/load_metrics.py                       # every keyed user, defaults
    python backend/load_metrics.py --user 1 --as-of 2026-08-27
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# REASONED-PRIOR constants — the recompute identity (metrics_version pins the τ-set)
# ---------------------------------------------------------------------------

METRICS_VERSION = "banister-v1"

# Banister time constants (#32). Fitness τ is common to all windows; fatigue τ is
# per-window. The fatigue dict is the window allowlist: a window with no key here is
# NEVER computed (fail-closed) — `psychological` is deliberately absent (Q122).
TAU_FITNESS_DAYS = 42
TAU_FATIGUE_DAYS = {
    "mechanical": 10,
    "neuromuscular": 6,
    "metabolic": 4,        # provisioned — lights up when a metabolic transform feeds load_events
}
FORM_K = 1               # form = fitness − k·fatigue; read-time-refreshable, no version bump

# ΔLoad (#33): acute:chronic over daily_load, rest days counted as 0.
ACUTE_DAYS = 7
CHRONIC_DAYS = 28

# maturity: the window's curve is 'low'-confidence until it has this much continuous history.
MATURITY_DAYS = 42

# Day grain is user-local. AEST = UTC+10, no DST. See `_local_day` for the S1 fork.
_AEST = pytz.timezone("Australia/Brisbane")


def _local_day(occurred_at: datetime) -> date:
    """The user-local (AEST) calendar day a load_event belongs to.

    Mirrors `routers/health_connect._wake_date`: treat the stored instant as UTC (attach
    UTC to a naive value, as `hevy_workouts._parse_dt` produces), then convert to AEST
    before taking the date — so an early-morning-AEST session is not mis-bucketed onto the
    prior UTC day.

    **S1 RELEASE-GATE (DECISIONS gate-3 entry).** This is correct IFF `load_events.occurred_at`
    (= `hevy_workouts.start_time`) is a TRUE UTC INSTANT. If a stored `start_time` turns out
    to be a naive-LOCAL wall-clock coerced to UTC (clock already local), this over-adds +10
    and the rule must become `occurred_at.date()` directly — a one-line change here plus the
    near-midnight reconciliation-oracle expectation. Confirm against one real stored value
    (clock vs a known training time) before release; the code alone cannot disambiguate."""
    dt = occurred_at if occurred_at.tzinfo is not None else occurred_at.replace(tzinfo=timezone.utc)
    return dt.astimezone(_AEST).date()


# ---------------------------------------------------------------------------
# Per-window daily series (pure — the recompute math, no DB)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DayMetric:
    day: date
    daily_load: float
    fitness: float
    fatigue: float
    form: float
    acute_load: float
    chronic_load: float
    load_ratio: float | None
    maturity: str


def _trailing_mean(loads: list[float], i: int, n: int) -> float:
    """Mean of `loads` over the trailing `n` calendar days ending at index `i`
    (inclusive), clamped to available history — days before the series start do not
    exist and are NOT counted as zero; rest days inside the window ARE zero."""
    window = loads[max(0, i - n + 1): i + 1]
    return sum(window) / len(window)


def compute_window_series(
    daily_by_day: dict[date, float],
    as_of: date,
    *,
    tau_fatigue_days: float,
) -> list[DayMetric]:
    """Walk a CONTINUOUS daily calendar from the first load day to `as_of` and compute
    the Banister stocks + ΔLoad per day. Rest days (and tail days past the last session)
    carry `daily_load=0` and still decay. Seeds `fitness(d0-1)=fatigue(d0-1)=0`.

        fitness(d) = fitness(d-1)·e^(-1/42)          + daily_load(d)
        fatigue(d) = fatigue(d-1)·e^(-1/τ_fatigue)   + daily_load(d)
        form(d)    = fitness(d) − FORM_K·fatigue(d)
    """
    if not daily_by_day:
        return []
    d0 = min(daily_by_day)
    if as_of < d0:
        return []
    n_days = (as_of - d0).days + 1
    days = [d0 + timedelta(days=k) for k in range(n_days)]
    loads = [float(daily_by_day.get(d, 0.0)) for d in days]

    decay_fit = math.exp(-1.0 / TAU_FITNESS_DAYS)
    decay_fat = math.exp(-1.0 / tau_fatigue_days)

    out: list[DayMetric] = []
    fitness = 0.0
    fatigue = 0.0
    for i, d in enumerate(days):
        load = loads[i]
        fitness = fitness * decay_fit + load
        fatigue = fatigue * decay_fat + load
        form = fitness - FORM_K * fatigue
        acute = _trailing_mean(loads, i, ACUTE_DAYS)
        chronic = _trailing_mean(loads, i, CHRONIC_DAYS)
        ratio = (acute / chronic) if chronic > 0 else None
        maturity = "ok" if (i + 1) >= MATURITY_DAYS else "low"
        out.append(DayMetric(
            day=d, daily_load=load,
            fitness=fitness, fatigue=fatigue, form=form,
            acute_load=acute, chronic_load=chronic, load_ratio=ratio,
            maturity=maturity,
        ))
    return out


# ---------------------------------------------------------------------------
# Orchestrator (DB): recompute a user's load_metrics from load_events
# ---------------------------------------------------------------------------

def compute_load_metrics(
    db: Session,
    user_id: int,
    *,
    formula_version: str = "tier0-v1",
    metrics_version: str = METRICS_VERSION,
    as_of: date | None = None,
    now: datetime | None = None,
) -> dict:
    """Recompute all `load_metrics` for one user from `load_events`.

    Reads `load_events` for `(user, formula_version)` with `occurred_at IS NOT NULL`
    (undated events cannot be placed on a day — mirrors the e1RM undated-skip), buckets
    each to its user-local day and window, sums to `daily_load`, walks a continuous daily
    calendar per window to `as_of`, and REPLACES the user's rows for this
    `(formula_version, metrics_version)` (delete-then-insert — idempotent recompute, D-B).
    """
    as_of = as_of or datetime.now(_AEST).date()
    now = now or datetime.now(timezone.utc)

    events = db.execute(
        select(models.LoadEvent).where(
            models.LoadEvent.user_id == user_id,
            models.LoadEvent.formula_version == formula_version,
            models.LoadEvent.occurred_at.is_not(None),
        )
    ).scalars().all()

    # window -> {local_day -> Σ load}; and window -> unit (window-native, never crossed)
    daily: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    unit_by_window: dict[str, str] = {}
    undated_skipped = 0
    for e in events:
        if e.occurred_at is None:      # defensive; the query already excludes these
            undated_skipped += 1
            continue
        day = _local_day(e.occurred_at)
        if day > as_of:                # a rollup as-of T never consumes load logged after T
            continue
        daily[e.load_window][day] += float(e.load)
        unit_by_window[e.load_window] = e.unit

    # Replace this (formula_version, metrics_version)'s rows for the user (idempotent).
    db.execute(
        delete(models.LoadMetric).where(
            models.LoadMetric.user_id == user_id,
            models.LoadMetric.formula_version == formula_version,
            models.LoadMetric.metrics_version == metrics_version,
        )
    )

    rows_written = 0
    windows_computed: list[str] = []
    windows_skipped_no_tau: list[str] = []
    for window, day_map in daily.items():
        tau_fat = TAU_FATIGUE_DAYS.get(window)
        if tau_fat is None:
            # Fail-closed: no fatigue-τ prior for this window (e.g. psychological, Q122).
            windows_skipped_no_tau.append(window)
            continue
        series = compute_window_series(day_map, as_of, tau_fatigue_days=tau_fat)
        for m in series:
            db.add(models.LoadMetric(
                user_id=user_id,
                day=m.day,
                load_window=window,
                daily_load=round(m.daily_load, 6),
                fitness=round(m.fitness, 6),
                fatigue=round(m.fatigue, 6),
                form=round(m.form, 6),
                acute_load=round(m.acute_load, 6),
                chronic_load=round(m.chronic_load, 6),
                load_ratio=(round(m.load_ratio, 6) if m.load_ratio is not None else None),
                unit=unit_by_window[window],
                maturity=m.maturity,
                formula_version=formula_version,
                metrics_version=metrics_version,
                computed_at=now,
            ))
            rows_written += 1
        windows_computed.append(window)

    db.commit()
    return {
        "formula_version": formula_version,
        "metrics_version": metrics_version,
        "as_of": as_of.isoformat(),
        "rows_written": rows_written,
        "windows_computed": sorted(windows_computed),
        "windows_skipped_no_tau": sorted(windows_skipped_no_tau),
        "undated_skipped": undated_skipped,
    }


def compute_all_users(
    db: Session,
    *,
    only_user_id: int | None = None,
    formula_version: str = "tier0-v1",
    metrics_version: str = METRICS_VERSION,
    as_of: date | None = None,
) -> dict:
    """Recompute load_metrics for one user or every keyed user."""
    from hevy_templates import users_with_hevy_key

    kw = dict(formula_version=formula_version, metrics_version=metrics_version, as_of=as_of)
    if only_user_id is not None:
        return {"users": 1, "per_user": {only_user_id: compute_load_metrics(db, only_user_id, **kw)}}
    per_user: dict[int, dict] = {}
    for uid, _ in users_with_hevy_key(db):
        per_user[uid] = compute_load_metrics(db, uid, **kw)
    return {"users": len(per_user), "per_user": per_user}


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Recompute Q6 gate-3 load_metrics from load_events.")
    parser.add_argument("--user", type=int, default=None, help="only this user id")
    parser.add_argument("--formula-version", default="tier0-v1", help="load_events formula_version to roll up")
    parser.add_argument("--metrics-version", default=METRICS_VERSION, help="τ-set / EWMA identity")
    parser.add_argument("--as-of", default=None, help="ISO date; default = today (AEST)")
    args = parser.parse_args()

    from database import SessionLocal

    _as_of = date.fromisoformat(args.as_of) if args.as_of else None
    _db = SessionLocal()
    try:
        _result = compute_all_users(
            _db,
            only_user_id=args.user,
            formula_version=args.formula_version,
            metrics_version=args.metrics_version,
            as_of=_as_of,
        )
        print(_result)
    finally:
        _db.close()
