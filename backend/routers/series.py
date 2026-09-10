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
from load_metrics import METRICS_VERSION, _local_day

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


# ── per-exercise strength progression (Visuals increment 3) ──────────────────────
#
# Per-template e1RM + volume over time — the first chart Hevy can't draw, because the phase
# markers the page overlays (training_phases) are ours, not theirs. Read-only over the raw
# Hevy substrate (`hevy_workouts.raw`, the recompute source of truth), NOT over a derived
# store: no per-template rollup exists, so e1RM and volume are computed here at read time from
# the logged sets. It mints no data-meaning the load path doesn't already own — Epley is the
# standard open e1RM estimator, and volume is kg·reps as logged.
#
# Design calls (brief D1–D5, logged at merge):
#   * D1 e1RM = Epley `weight × (1 + reps/30)` per working set; the SESSION value is the max.
#     Epley degrades above ~10 reps, so a set with reps > 10 does NOT contribute to e1RM —
#     but it DOES count toward volume (the strength signal and the work signal diverge there).
#   * D2 Volume = Σ(weight_kg × reps) over the session's working sets, kg·reps. Its own unit,
#     its own axis (the #186 shared-axis⇒shared-unit guard would refuse an e1RM/volume overlay).
#   * D3 Working sets only: a set typed `warmup` is excluded; `normal`/`failure`/`dropset` (and
#     an untyped set, which the transform reads as `normal`) are included. Workouts with
#     `excluded_at` set or `dedup_flag` true are excluded — the SAME filter `engine/resolver`
#     applies, so this surface and the load path see one population.
#   * D5 The selector lists templates with ≥ 3 qualifying session-days in range, most-frequent
#     first. A qualifying session-day is one on which the template carries ≥ 1 working set.
#
# Day grain is `_local_day` (the rollup's AEST day, Q42) — imported, not re-derived, so a
# session buckets onto the SAME day the load series uses (FEEDBACK §39: anchor on the helper
# the load path actually calls, never a parallel copy that can silently re-skew).

# Working set types (D3): everything except `warmup`. An untyped set defaults to `normal`
# (the `load_events` transform convention), so it counts — only an explicit `warmup` is cut.
_EPLEY_REP_CAP = 10  # reps > cap do not contribute to e1RM (D1); they still count to volume.


def _epley_e1rm(weight_kg: float, reps: int) -> float:
    """Epley one-rep-max estimate: weight × (1 + reps/30). Pure; the strength signal (D1)."""
    return weight_kg * (1.0 + reps / 30.0)


def _is_working_set(raw_set: dict) -> bool:
    """A working set (D3): any set NOT typed `warmup`. Matches the transform's default-normal
    reading of an absent type (`load_events._set_line`)."""
    return (raw_set.get("type") or "normal").lower() != "warmup"


def _aggregate_session(raw_sets: list[dict]) -> dict | None:
    """Collapse one template's sets on ONE session-day to a point, or None if no working set.

    e1RM is the max Epley over working sets with reps in [1, cap] and a logged weight (D1);
    None when none qualifies. Volume sums weight×reps over ALL working sets that carry both
    (a reps>cap set is excluded from e1RM but included here, D1/D2). `top_set` is the set that
    produced the max e1RM. `working_sets` counts every non-warmup set, scorable or not."""
    working = [s for s in raw_sets if _is_working_set(s)]
    if not working:
        return None

    volume = 0.0
    best_e1rm: float | None = None
    top_set: dict | None = None
    for s in working:
        weight = s.get("weight_kg")
        reps = s.get("reps")
        if weight is None or reps is None:
            continue
        weight = float(weight)
        reps = int(reps)
        volume += weight * reps
        if 1 <= reps <= _EPLEY_REP_CAP:
            e = _epley_e1rm(weight, reps)
            if best_e1rm is None or e > best_e1rm:
                best_e1rm = e
                top_set = {"weight_kg": weight, "reps": reps}

    return {
        "e1rm_kg": best_e1rm,
        "top_set": top_set,
        "volume_kg_reps": volume,
        "working_sets": len(working),
    }


def _session_days_by_template(
    db: Session, user_id: int, since, *, template_id: str | None = None
) -> dict[str, dict]:
    """{template_id: {day: [raw_set, ...]}} for the user's in-range, non-excluded,
    non-dedup workouts. Grouped by `_local_day` so multiple same-day workouts collapse onto
    one session-day (brief step 2). `template_id` narrows to a single template when given.

    The exclusion filter is `engine/resolver`'s exactly (D3): `excluded_at IS NULL` AND
    `dedup_flag IS NOT TRUE`. The local-day bound is applied in Python off `_local_day` rather
    than on the UTC `start_time` column, so an early-AEST row is not mis-windowed at the edge
    (the resolver does the same)."""
    today = _today_aest()
    rows = (
        db.query(models.HevyWorkout)
        .filter(
            models.HevyWorkout.user_id == user_id,
            models.HevyWorkout.excluded_at.is_(None),
            models.HevyWorkout.dedup_flag.isnot(True),
        )
        .all()
    )

    by_template: dict[str, dict] = {}
    for w in rows:
        if w.start_time is None:
            continue
        day = _local_day(w.start_time)
        if not (since <= day <= today):
            continue
        for ex in (w.raw or {}).get("exercises", []) or []:
            tid = ex.get("exercise_template_id")
            if not tid:
                continue  # #79 — a block with no template id has nothing to key on
            if template_id is not None and tid != template_id:
                continue
            day_sets = by_template.setdefault(tid, {}).setdefault(day, [])
            day_sets.extend(ex.get("sets", []) or [])

    return by_template


def _title_map(db: Session, template_ids) -> dict[str, str]:
    """template_id → catalogue title for the given ids. A template absent from the local
    catalogue (#79 hole) is simply not in the map; the caller falls back to the id."""
    if not template_ids:
        return {}
    rows = (
        db.query(models.HevyExerciseTemplate.id, models.HevyExerciseTemplate.title)
        .filter(models.HevyExerciseTemplate.id.in_(list(template_ids)))
        .all()
    )
    return {tid: title for tid, title in rows}


class ExerciseListItem(BaseModel):
    template_id: str
    title: str
    sessions: int  # qualifying session-days in range (D5)


class TopSet(BaseModel):
    weight_kg: float
    reps: int


class ExercisePoint(BaseModel):
    date: str
    e1rm_kg: float | None      # None when no set qualifies under Epley (D1); volume still set
    top_set: TopSet | None     # the set that produced the max e1RM; None when e1rm_kg is None
    volume_kg_reps: float
    working_sets: int


class ExerciseSeriesOut(BaseModel):
    template_id: str
    title: str
    points: list[ExercisePoint]


@router.get("/exercises", response_model=list[ExerciseListItem])
def get_exercise_list(
    days: int = Query(90, ge=1, le=730),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The exercise selector's source (brief step 1): the user's templates with ≥ 3 qualifying
    session-days in the trailing `days` window, most-frequent first (D5).

    A session-day qualifies for a template when the template carries ≥ 1 working set that day —
    the same qualification that makes a point in `/series/exercise/{id}`, so `sessions` equals
    the number of points that route would return. Ties on count break on title for a stable
    order."""
    since = _today_aest() - timedelta(days=days)
    by_template = _session_days_by_template(db, current_user.id, since)

    counts: dict[str, int] = {}
    for tid, days_map in by_template.items():
        n = sum(1 for day_sets in days_map.values() if _aggregate_session(day_sets) is not None)
        if n >= 3:
            counts[tid] = n

    titles = _title_map(db, counts.keys())
    items = [
        ExerciseListItem(template_id=tid, title=titles.get(tid, tid), sessions=n)
        for tid, n in counts.items()
    ]
    items.sort(key=lambda it: (-it.sessions, it.title))
    return items


@router.get("/exercise/{template_id}", response_model=ExerciseSeriesOut)
def get_exercise_series(
    template_id: str,
    days: int = Query(90, ge=1, le=730),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-session strength progression for one template (brief step 2), ascending by session
    date, over the trailing `days` window: one point per session-day (D1–D3).

    `e1rm_kg` is null on a day whose only working sets are above the Epley rep cap or carry no
    weight — volume is still populated there, because the work was real even when the 1RM
    estimate would be unreliable. A template with no qualifying session-days returns an empty
    series (not a 404): the set of populated templates is data, not contract (mirrors
    `/series/load`'s unknown-window handling)."""
    since = _today_aest() - timedelta(days=days)
    by_template = _session_days_by_template(db, current_user.id, since, template_id=template_id)

    title = _title_map(db, [template_id]).get(template_id, template_id)

    days_map = by_template.get(template_id, {})
    points: list[ExercisePoint] = []
    for day in sorted(days_map):
        agg = _aggregate_session(days_map[day])
        if agg is None:
            continue
        points.append(ExercisePoint(
            date=day.isoformat(),
            e1rm_kg=agg["e1rm_kg"],
            top_set=TopSet(**agg["top_set"]) if agg["top_set"] else None,
            volume_kg_reps=agg["volume_kg_reps"],
            working_sets=agg["working_sets"],
        ))

    return ExerciseSeriesOut(template_id=template_id, title=title, points=points)
