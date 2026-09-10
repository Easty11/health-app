"""Chart read surface — `/series/*` (Visuals increment 1, v1 test 1 "See").

One router for every chart series the surfacing phase draws. It is READ-ONLY over the
already-computed derived stores: it never recomputes load, never touches `load_metrics.py`
or the MCP tool, and mints no new data-meaning. `/series/load` is the first route; the
readiness and per-exercise series (`/series/readiness`, `/series/exercise/{id}`) land here
next and reuse this shape.

Version pinning (the whole reason this is not a naive `SELECT *`):
  * `metrics_version` is ONE axis — `banister-v1`, imported from `load_metrics.METRICS_VERSION`
    so this surface can never drift from the τ-set the rollup actually wrote. Rows at any
    other metrics_version (a retired τ-set) are excluded.
  * `formula_version` is PER-LANE, not global: `tier0-v1` for the mechanical/neuromuscular
    windows, `metab-v1` for the metabolic window (`load_events_metabolic.FORMULA_VERSION_METABOLIC`),
    and psychological is fail-closed (never computed — Q122). There is therefore no single
    formula_version to filter on, and mcp_server pins only its own metabolic lane by literal.
    So this router does NOT filter formula_version; it selects the current-metrics rows and,
    per window, keeps a SINGLE formula_version (the most recently computed) — which under the
    delete-and-reinsert recompute (D-B) is the whole of a window's series today, and stays
    unambiguous if a superseded formula_version ever lingers beside a current one.

Day grain is the operator-local (AEST) calendar day, matching `load_metrics._local_day`
(Q42) — a UTC bound would mis-window an early-morning-AEST row by one day at the `days` edge.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytz
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from load_metrics import METRICS_VERSION

router = APIRouter(prefix="/series", tags=["series"])

# AEST, no DST — the same zone `load_metrics` buckets load into. Kept local (not imported as
# the private `load_metrics._local_day`) so this read surface owns its own dependency, but it
# MUST agree with the rollup's day grain; both name Australia/Brisbane deliberately.
_AEST = pytz.timezone("Australia/Brisbane")


def _today_aest():
    return datetime.now(_AEST).date()


class LoadPoint(BaseModel):
    day: str
    daily_load: float
    fitness: float
    fatigue: float
    form: float
    acute_load: float
    chronic_load: float
    maturity: str  # 'low' (pre-maturity cold-start, surfaced not hidden) | 'ok'


class LoadWindowSeries(BaseModel):
    load_window: str
    unit: str
    formula_version: str
    points: list[LoadPoint]


class LoadSeriesOut(BaseModel):
    days: int
    metrics_version: str
    windows: list[LoadWindowSeries]


@router.get("/load", response_model=LoadSeriesOut)
def get_load_series(
    days: int = Query(90, ge=1, le=730),
    windows: str | None = Query(None, description="comma-separated load_window allowlist; default all populated"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Daily training load per window for the current user, at the current metrics_version,
    ascending by day, over the trailing `days` window.

    `windows` optionally restricts to a comma-separated allowlist; omitted returns every
    populated window. An unknown window name simply matches nothing (no 422 — the set of
    populated windows is data, not contract, and a client asking for a not-yet-lit window
    should get an empty series, not an error)."""
    since = _today_aest() - timedelta(days=days)

    q = db.query(models.LoadMetric).filter(
        models.LoadMetric.user_id == current_user.id,
        models.LoadMetric.metrics_version == METRICS_VERSION,
        models.LoadMetric.day >= since,
    )

    requested: list[str] | None = None
    if windows:
        requested = [w.strip() for w in windows.split(",") if w.strip()]
        if requested:
            q = q.filter(models.LoadMetric.load_window.in_(requested))

    rows = q.order_by(
        models.LoadMetric.load_window,
        models.LoadMetric.day,
    ).all()

    # Group by window; within a window collapse to ONE formula_version (see module docstring).
    by_window: dict[str, list[models.LoadMetric]] = {}
    for r in rows:
        by_window.setdefault(r.load_window, []).append(r)

    out_windows: list[LoadWindowSeries] = []
    for window in sorted(by_window):
        wrows = by_window[window]
        # The current formula_version for this window: the one most recently computed. Ties
        # (same computed_at) break on the version string so the choice is deterministic.
        chosen_fv = max(
            wrows,
            key=lambda r: (r.computed_at, r.formula_version),
        ).formula_version
        wrows = [r for r in wrows if r.formula_version == chosen_fv]
        wrows.sort(key=lambda r: r.day)

        out_windows.append(LoadWindowSeries(
            load_window=window,
            unit=wrows[0].unit,
            formula_version=chosen_fv,
            points=[
                LoadPoint(
                    day=r.day.isoformat(),
                    daily_load=r.daily_load,
                    fitness=r.fitness,
                    fatigue=r.fatigue,
                    form=r.form,
                    acute_load=r.acute_load,
                    chronic_load=r.chronic_load,
                    maturity=r.maturity,
                )
                for r in wrows
            ],
        ))

    return LoadSeriesOut(days=days, metrics_version=METRICS_VERSION, windows=out_windows)


# ── readiness series (Visuals increment 2) ──────────────────────────────────────
#
# The OBSERVED readiness trend for the current user: the 1–5 morning self-report and the
# passive overnight HRV, per day, ascending, over the trailing `days` window. It reshapes the
# `daily_records` store the same way `checkin_v2 GET /history` reads it — a distinct read
# surface, not a call into that router, so `/series/*` owns its own query (mirroring
# `/series/load`).
#
# Deliberately NOT an actual-vs-forecast surface. `model_forecast` / `model_confidence` are
# excluded until Q141 resolves what observed quantity the forecast predicts and on what scale:
# it is written nowhere today (the column is null in prod), and a 0–10 forecast against a 1–5
# ordinal self-report is not a residual. Shipping those two fields here would spec a comparison
# that is both empty and meaningless — the picture would render fine and mean nothing. So this
# carries only what is observed and on a single, honest scale per series.
#
# Nulls are PRESERVED, never coerced: a day with no AM check-in has `morning_readiness = None`
# (and a day with no overnight reading `passive_hrv_ms = None`). The chart draws those as gaps,
# not zeros — a missing self-report is not a readiness of zero.
#
# `days` carries its OWN bound (ge=1, le=730) rather than inheriting `checkin_v2 /history`'s
# default-14: that route is newest-first and unbounded, this one is ascending and explicitly
# ranged to match `/series/load`. No change is made to `/history`.


class ReadinessPoint(BaseModel):
    date: str
    morning_readiness: int | None  # 1–5 self-report; None on a day with no AM check-in
    passive_hrv_ms: float | None   # overnight HRV at capture, ms; None when no reading


class ReadinessSeriesOut(BaseModel):
    days: int
    points: list[ReadinessPoint]


@router.get("/readiness", response_model=ReadinessSeriesOut)
def get_readiness_series(
    days: int = Query(90, ge=1, le=730),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Observed readiness for the current user, ascending by day, over the trailing `days`
    window: the 1–5 morning self-report and passive overnight HRV per day.

    A day appears only if a `daily_records` row exists for it — but a row present with a null
    field keeps that null (drawn as a gap), because "no check-in that day" and "readiness zero"
    are different facts and only the store knows which."""
    since = _today_aest() - timedelta(days=days)

    rows = (
        db.query(models.DailyRecord)
        .filter(
            models.DailyRecord.user_id == current_user.id,
            models.DailyRecord.date >= since,
        )
        .order_by(models.DailyRecord.date.asc())
        .all()
    )

    return ReadinessSeriesOut(
        days=days,
        points=[
            ReadinessPoint(
                date=r.date.isoformat(),
                morning_readiness=r.morning_readiness,
                passive_hrv_ms=r.passive_hrv_ms,
            )
            for r in rows
        ],
    )
