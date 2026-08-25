"""Tier-0 strength load transform — `hevy_workouts.raw` → `load_events` (Q6 gate 2).

The derive half of the two-level load store (DECISIONS_LOG #28/#32, D-B/D-C/D-D).
Gate 1 persisted the untouched Hevy payload (`hevy_workouts` / `hevy_sets`); this
transform reads it and emits one Mechanical and one Neuromuscular `load_events` row
per session, in the window-native units of D-A. The daily `load_metrics` + Banister
rollup (gate 3) reads `load_events`, never the raw payload.

Per D-B the computed history is a RECOMPUTE, never a migration: every coefficient,
band, and bridging constant below is a REASONED PRIOR (#32) tagged with
`FORMULA_VERSION`. A correction bumps the version and re-derives from source — it does
not edit landed rows. `compute_load_events` is therefore delete-and-reinsert per
(user, `FORMULA_VERSION`) and idempotent on re-run.

Three rules from the brief's BUILD-step-2 supersessions (these GOVERN over the older
ROADMAP row-79 agenda wording, which was stale):

  * RPE is a PER-SET fact, date-independent. A set with an `rpe` bands on (reps, RPE)
    whatever its date; a set without one takes the reps-band prior. NO imputation, ever.
  * e1RM is fitted from ALL RPE-present working sets, ANY date (rolling 60 d, per
    template). An RPE-absent set may CONSUME a fit but never UPDATES it.
  * LOAD SUMS SETS AS LOGGED. Unilateral work is genuine work — 3 sets/leg of 40kg×10
    is 2400 kg·reps, at parity with the bilateral equivalent — so the D-E laterality
    pairing NEVER discounts cost (its supersession narrows halving to the
    movement-count / asymmetry instrument). Pairing and indeterminate-tag detection are
    retained in `provenance` only, surfaced for that instrument, never applied to load.

`EPOCH_RPE_COMPLETE` survives for exactly one, DIAGNOSTIC use: a rep-based workout on or
after it that carries no RPE at all is a planned-vs-performed artifact signature (D-G
hardening candidate), flagged in `provenance`. It appears in NO cost or e1RM code path.

The mechanism is pure functions over normalized sets (`compute_set_load`,
`epley_with_rir`, `rolling_e1rm`); the DB orchestrator only reads sessions and persists.
The transform reads `excluded_at` from day one — a dedup-adjudicated artifact (D-G)
never enters load.

Re-runnable CLI:
    python backend/load_events.py                # recompute all keyed users
    python backend/load_events.py --user 1       # one user
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import models
from laterality import detect_session_pairing

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# REASONED-PRIOR constants (all provenance-labelled #32; tagged by FORMULA_VERSION)
# ---------------------------------------------------------------------------

FORMULA_VERSION = "tier0-v1"

# Operator input (brief): the date from which RPE logging is complete. DIAGNOSTIC ONLY —
# a rep-based workout on/after this date carrying no RPE at all is a planned-vs-performed
# artifact signature (D-G hardening candidate), surfaced in provenance. It gates NO cost
# and NO e1RM path: RPE is a per-set fact and bands on (reps, RPE) whatever the date.
EPOCH_RPE_COMPLETE = date(2026, 5, 11)

# Operator input (brief): used as the effective load for a PURE bodyweight movement
# (a rep/timed set with no external `weight_kg`). Weighted-bodyweight sets (an added
# plate logged in `weight_kg`) use the plate weight alone at Tier 0 — a known
# undercount, surfaced (see the module OPEN_QUESTIONS gap), not silently corrected.
BODYWEIGHT_KG = 102.0

WINDOW_MECHANICAL = "mechanical"
WINDOW_NEUROMUSCULAR = "neuromuscular"
UNIT_MECHANICAL = "kg_reps"       # weight_kg × reps (+ bridged non-rep), D-A window-native
UNIT_NEUROMUSCULAR = "nm_au"      # f(RIR)·h(I) / reps-band prior — dimensionless AU

# Non-rep bridging (D-D): map kg·m and kg·s into the Mechanical kg·reps series via one
# rep-equivalent-per-unit constant each. NM from non-rep work = 0 at Tier 0.
K_DIST = 0.3      # rep-equiv per metre
K_TIME = 0.05     # rep-equiv per second

# e1RM: per-template Epley-with-RIR, rolling window, fitted from RPE-usable sets.
E1RM_WINDOW_DAYS = 60
H_NO_E1RM = 0.5   # h(I) fallback when a template has no e1RM fit in-window


def _mech_mult(rir: int) -> float:
    """m(RIR): Mechanical band multiplier. >=4 → 1.0, 2–3 → 1.15, 0–1 → 1.30."""
    if rir >= 4:
        return 1.0
    if rir >= 2:
        return 1.15
    return 1.30


def _f_rir(rir: int) -> float:
    """f(RIR): NM proximity-to-failure factor. >=5 → 0, 4 → .25, 3 → .5, 2 → .75,
    1 → .9, 0 → 1.0."""
    return {0: 1.0, 1: 0.9, 2: 0.75, 3: 0.5, 4: 0.25}.get(rir, 0.0)


def _h_intensity(intensity: float) -> float:
    """h(I) = 0.25 + 0.75 × clamp((I − 0.40) / 0.45, 0, 1). Bounded intensity modifier
    (velocity-mandate proxy, D-C); I = effective_weight / e1RM."""
    x = (intensity - 0.40) / 0.45
    x = max(0.0, min(1.0, x))
    return 0.25 + 0.75 * x


def _nm_reps_prior(reps: int) -> float:
    """RPE-absent NM reps-band prior. reps<=5 → .6, 6–11 → .35, >=12 → .15. Used when a
    rep set has no usable RPE — a coarse proximity-to-failure prior from rep count
    alone (no h(I), no imputed RPE)."""
    if reps <= 5:
        return 0.6
    if reps <= 11:
        return 0.35
    return 0.15


def _rir_from_rpe(rpe: float) -> int:
    """RIR = 10 − RPE, banded to the nearest integer (half-up), clamped to >= 0.

    Hevy logs RPE in half points, so RIR lands on halves; the m()/f() tables are keyed
    at integers. Half-up rounding (RIR 1.5 → 2) is the documented Tier-0 banding — a
    deterministic choice, flagged for Tier-1 review (module OPEN_QUESTIONS gap)."""
    return max(0, math.floor((10.0 - rpe) + 0.5))


def _effective_weight(weight_kg: float | None) -> float:
    """External load if present and positive, else the operator bodyweight. See
    `BODYWEIGHT_KG` for the weighted-bodyweight caveat."""
    if weight_kg is not None and weight_kg > 0:
        return float(weight_kg)
    return BODYWEIGHT_KG


# ---------------------------------------------------------------------------
# Per-set load (pure, D-C/D-D)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetLoad:
    """One set's Mechanical + Neuromuscular contribution and the provenance flags the
    gap-recording blob aggregates. `skip` marks a set with no scorable data (no reps,
    no distance, no duration) — it contributes nothing and is not counted."""
    mechanical: float = 0.0
    neuromuscular: float = 0.0
    skip: bool = False
    is_warmup: bool = False
    is_non_rep: bool = False
    non_rep_mech: float = 0.0
    rpe_used: bool = False       # NM via f(RIR)·h(I)
    reps_banded: bool = False    # NM via RPE-absent reps prior (a gap)
    is_failure: bool = False
    e1rm_used: bool | None = None  # h(I) used a fitted e1RM (True) or the 0.5 fallback (False); None if N/A


def compute_set_load(
    s: dict[str, Any],
    *,
    e1rm: float | None,
) -> SetLoad:
    """Score one normalized set (keys: type, weight_kg, reps, duration_seconds,
    distance_meters, rpe — the live snake_case shape, #68).

    RPE is per-set and date-independent: a set with an `rpe` bands on (reps, RPE); one
    without takes the reps-band prior (no imputation). `e1rm` is the template's fitted
    e1RM as of the session (None → h(I)=0.5). Pure and deterministic.
    """
    set_type = (s.get("type") or "normal").lower()
    is_warmup = set_type == "warmup"
    is_failure = set_type == "failure"
    reps = s.get("reps")
    weight = s.get("weight_kg")
    dist = s.get("distance_meters")
    dur = s.get("duration_seconds")
    rpe = s.get("rpe")

    # ── Non-rep work (carries/sleds, timed holds): D-D bridging, NM = 0 ──────────
    if reps is None and (dist is not None or dur is not None):
        eff_w = _effective_weight(weight)
        mech = 0.0
        if dist is not None:
            mech += eff_w * float(dist) * K_DIST
        if dur is not None:
            mech += eff_w * float(dur) * K_TIME
        if is_warmup:
            mech *= 0.5
        return SetLoad(
            mechanical=mech, neuromuscular=0.0,
            is_warmup=is_warmup, is_non_rep=True, non_rep_mech=mech,
        )

    # ── No scorable data ────────────────────────────────────────────────────────
    if reps is None:
        return SetLoad(skip=True)

    eff_w = _effective_weight(weight)

    # RIR: a failure set is RIR 0 by definition (a set-type fact, no `rpe` needed).
    # Otherwise RIR comes from a present RPE (any date), else it is unknown.
    if is_failure:
        rir: int | None = 0
    elif rpe is not None:
        rir = _rir_from_rpe(float(rpe))
    else:
        rir = None

    # ── Mechanical: weight × reps × m(RIR); RPE-absent → m = 1.0; warmup ×0.5 ────
    m = _mech_mult(rir) if rir is not None else 1.0
    mech = eff_w * float(reps) * m
    if is_warmup:
        mech *= 0.5

    # ── Neuromuscular ───────────────────────────────────────────────────────────
    if is_warmup:
        # Warmups excluded from NM (D-C).
        return SetLoad(
            mechanical=mech, neuromuscular=0.0, is_warmup=True, is_failure=is_failure,
        )
    if rir is not None:
        # RPE-dominant path: f(RIR)·h(I). I = effective_weight / e1RM.
        if e1rm is not None and e1rm > 0:
            h = _h_intensity(eff_w / e1rm)
            e1rm_used = True
        else:
            h = H_NO_E1RM
            e1rm_used = False
        nm = _f_rir(rir) * h
        return SetLoad(
            mechanical=mech, neuromuscular=nm,
            rpe_used=not is_failure, is_failure=is_failure, e1rm_used=e1rm_used,
        )
    # RPE-absent rep set → coarse reps-band prior (no h(I), no imputation).
    nm = _nm_reps_prior(int(reps))
    return SetLoad(mechanical=mech, neuromuscular=nm, reps_banded=True)


# ---------------------------------------------------------------------------
# e1RM fit (pure, rolling 60 d, RPE-usable only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class E1rmSample:
    """One RPE-usable set's Epley-with-RIR e1RM estimate, dated by its session."""
    template_id: str
    when: date
    e1rm: float


def epley_with_rir(weight_kg: float, reps: int, rir: float) -> float:
    """Epley-with-RIR: w × (1 + (reps + RIR) / 30). RIR here is the CONTINUOUS
    10 − RPE (not the banded integer) — the estimator wants the true reserve."""
    return weight_kg * (1.0 + (reps + rir) / 30.0)


def e1rm_samples(sessions: list["Session_"]) -> list[E1rmSample]:
    """Every RPE-present, weighted rep set → an e1RM estimate, ANY date (failure sets,
    which carry no `rpe`, do NOT fit e1RM — 'fitted from RPE-present sets only'). An
    undated session cannot be placed in a rolling window, so it is skipped for
    sampling."""
    out: list[E1rmSample] = []
    for sess in sessions:
        if sess.when is None:
            continue
        for block_index, template_id, s in sess.sets:
            rpe = s.get("rpe")
            reps = s.get("reps")
            weight = s.get("weight_kg")
            if rpe is None or reps is None or weight is None or weight <= 0:
                continue
            rir = 10.0 - float(rpe)
            out.append(E1rmSample(
                template_id=template_id,
                when=sess.when,
                e1rm=epley_with_rir(float(weight), int(reps), rir),
            ))
    return out


def rolling_e1rm(
    samples: list[E1rmSample],
    template_id: str,
    as_of: date | None,
    *,
    window_days: int = E1RM_WINDOW_DAYS,
) -> float | None:
    """Best (max) e1RM estimate for `template_id` in (as_of − window, as_of]. Includes
    the as-of day so a session's own top set can set its intensity reference. Returns
    None when the window holds no RPE-usable estimate for the template (→ h(I)=0.5)."""
    if as_of is None:
        return None
    floor = as_of - timedelta(days=window_days)
    best: float | None = None
    for smp in samples:
        if smp.template_id != template_id:
            continue
        if floor <= smp.when <= as_of:
            if best is None or smp.e1rm > best:
                best = smp.e1rm
    return best


# ---------------------------------------------------------------------------
# Session shaping
# ---------------------------------------------------------------------------

@dataclass
class Session_:
    """A non-excluded persisted workout, normalized for the transform."""
    hevy_id: str
    when: date | None                       # session calendar date (epoch/e1RM key)
    occurred_at: datetime | None            # full timestamp for the load_events row
    # (block_index, template_id, raw_set) in log order
    sets: list[tuple[int, str, dict[str, Any]]] = field(default_factory=list)

    @property
    def blocks(self) -> list[tuple[int, str]]:
        """Distinct (block_index, template_id) in log order — the laterality input."""
        seen: set[int] = set()
        out: list[tuple[int, str]] = []
        for block_index, template_id, _ in self.sets:
            if block_index not in seen:
                seen.add(block_index)
                out.append((block_index, template_id))
        return out


def _iter_raw_sets(raw: dict[str, Any]) -> Iterable[tuple[int, str, dict[str, Any]]]:
    """(block_index, template_id, set) for a raw Hevy workout, skipping blocks with no
    template id (#79 — nothing to key on). Mirrors `hevy_workouts._iter_sets` shape."""
    for block_index, ex in enumerate(raw.get("exercises", []) or []):
        template_id = ex.get("exercise_template_id")
        if not template_id:
            continue
        for s in (ex.get("sets", []) or []):
            yield block_index, template_id, s


def _session_from_row(row: Any) -> Session_:
    raw = row.raw or {}
    when = row.start_time.date() if row.start_time is not None else None
    return Session_(
        hevy_id=row.hevy_id,
        when=when,
        occurred_at=row.start_time,
        sets=list(_iter_raw_sets(raw)),
    )


# ---------------------------------------------------------------------------
# Session → (Mechanical, Neuromuscular) load events
# ---------------------------------------------------------------------------

def compute_session_events(
    sess: Session_,
    *,
    laterality_by_template: dict[str, str | None],
    e1rm_by_template: dict[str, float | None],
) -> dict[str, dict[str, Any]]:
    """Two window aggregates ({window: {load, unit, provenance}}) for one session.

    LOAD SUMS SETS AS LOGGED — the D-E laterality pairing NEVER discounts cost
    (unilateral work is genuine work). `detect_session_pairing` is retained for
    provenance only: `paired_templates` (a `unilateral` template in >=2 blocks — the
    movement-count / asymmetry signal) and `indeterminate_laterality` (an untagged
    template in >=2 blocks — surfaced, never guessed) both travel in the blob and feed
    the asymmetry instrument, not the load sum.

    Epoch DIAGNOSTIC (`post_epoch_zero_rpe`): a session on/after `EPOCH_RPE_COMPLETE`
    whose working (non-warmup) rep sets carry no RPE at all is a planned-vs-performed
    artifact signature (D-G hardening candidate). Diagnostic only — it changes no load.
    """
    pairing = detect_session_pairing(sess.blocks, laterality_by_template)
    paired_templates = sorted(pairing.paired.keys())
    indeterminate_templates = sorted(pairing.indeterminate.keys())

    mech_load = 0.0
    nm_load = 0.0
    mech_p = {"sets": 0, "warmup_sets": 0, "non_rep_sets": 0, "non_rep_load": 0.0}
    nm_p = {
        "sets": 0, "rpe_sets": 0, "reps_banded_sets": 0, "failure_sets": 0,
        "non_rep_excluded_sets": 0,
        "e1rm_fit_templates": set(), "e1rm_fallback_templates": set(),
    }
    working_rep_sets = 0        # non-warmup rep sets — the diagnostic's denominator
    working_rep_with_rpe = 0

    for block_index, template_id, s in sess.sets:
        sl = compute_set_load(s, e1rm=e1rm_by_template.get(template_id))
        if sl.skip:
            continue

        # Load sums as logged — no laterality factor.
        mech_load += sl.mechanical
        nm_load += sl.neuromuscular

        # Mechanical provenance
        mech_p["sets"] += 1
        if sl.is_warmup:
            mech_p["warmup_sets"] += 1
        if sl.is_non_rep:
            mech_p["non_rep_sets"] += 1
            mech_p["non_rep_load"] += sl.non_rep_mech
            nm_p["non_rep_excluded_sets"] += 1
            continue  # non-rep contributes nothing to NM (D-D)

        # Neuromuscular provenance (rep sets only)
        if sl.is_warmup:
            continue  # warmup excluded from NM
        working_rep_sets += 1
        if s.get("rpe") is not None or sl.is_failure:
            working_rep_with_rpe += 1  # a failure tag is explicit effort data, not a bare artifact
        nm_p["sets"] += 1
        if sl.is_failure:
            nm_p["failure_sets"] += 1
        if sl.rpe_used or sl.is_failure:
            nm_p["rpe_sets"] += 1
        if sl.reps_banded:
            nm_p["reps_banded_sets"] += 1
        if sl.e1rm_used is True:
            nm_p["e1rm_fit_templates"].add(template_id)
        elif sl.e1rm_used is False:
            nm_p["e1rm_fallback_templates"].add(template_id)

    post_epoch = sess.when is not None and sess.when >= EPOCH_RPE_COMPLETE
    post_epoch_zero_rpe = post_epoch and working_rep_sets > 0 and working_rep_with_rpe == 0

    shared_prov = {
        "paired_templates": paired_templates,
        "indeterminate_laterality": indeterminate_templates,
        "post_epoch_zero_rpe": post_epoch_zero_rpe,
    }
    mech_p["non_rep_load"] = round(mech_p["non_rep_load"], 6)
    nm_p["e1rm_fit_templates"] = sorted(nm_p["e1rm_fit_templates"])
    nm_p["e1rm_fallback_templates"] = sorted(nm_p["e1rm_fallback_templates"])

    return {
        WINDOW_MECHANICAL: {
            "load": round(mech_load, 6),
            "unit": UNIT_MECHANICAL,
            "provenance": {**mech_p, **shared_prov},
        },
        WINDOW_NEUROMUSCULAR: {
            "load": round(nm_load, 6),
            "unit": UNIT_NEUROMUSCULAR,
            "provenance": {**nm_p, **shared_prov},
        },
    }


# ---------------------------------------------------------------------------
# Orchestrator (DB): recompute a user's load_events from source
# ---------------------------------------------------------------------------

def _laterality_map(db: Session) -> dict[str, str | None]:
    """template id → laterality tag, across all templates (global; #61 default-wins is
    resolved at sync)."""
    rows = db.execute(
        select(models.HevyExerciseTemplate.id, models.HevyExerciseTemplate.laterality)
    ).all()
    return {r.id: r.laterality for r in rows}


def compute_load_events(
    db: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recompute all `load_events` for one user from `hevy_workouts.raw`.

    Reads NON-excluded workouts only (`excluded_at IS NULL`, D-G) ordered by session
    date, fits per-template rolling-60 d e1RM from RPE-usable sets, scores each session
    into Mechanical + Neuromuscular rows, and REPLACES the user's rows for this
    `FORMULA_VERSION` (delete-then-insert — idempotent recompute, D-B). Other formula
    versions' rows are untouched. Returns per-user counts + coverage.
    """
    now = now or datetime.now(timezone.utc)
    lat_map = _laterality_map(db)

    rows = db.execute(
        select(models.HevyWorkout)
        .where(
            models.HevyWorkout.user_id == user_id,
            models.HevyWorkout.excluded_at.is_(None),
        )
        .order_by(models.HevyWorkout.start_time)
    ).scalars().all()
    sessions = [_session_from_row(r) for r in rows]

    samples = e1rm_samples(sessions)

    # Replace this version's rows for the user (idempotent recompute).
    db.execute(
        delete(models.LoadEvent).where(
            models.LoadEvent.user_id == user_id,
            models.LoadEvent.formula_version == FORMULA_VERSION,
        )
    )

    events_written = 0
    e1rm_fit_sessions = 0
    reps_banded_sessions = 0
    indeterminate_sessions = 0
    artifact_signature_sessions = 0
    for sess in sessions:
        e1rm_by_template = {
            tid: rolling_e1rm(samples, tid, sess.when)
            for _, tid in sess.blocks
        }
        windows = compute_session_events(
            sess,
            laterality_by_template=lat_map,
            e1rm_by_template=e1rm_by_template,
        )
        for window, agg in windows.items():
            db.add(models.LoadEvent(
                user_id=user_id,
                source="hevy",
                source_ref=sess.hevy_id,
                window=window,
                occurred_at=sess.occurred_at,
                load=agg["load"],
                unit=agg["unit"],
                formula_version=FORMULA_VERSION,
                provenance=agg["provenance"],
                computed_at=now,
            ))
            events_written += 1
        nm_prov = windows[WINDOW_NEUROMUSCULAR]["provenance"]
        if nm_prov["e1rm_fit_templates"]:
            e1rm_fit_sessions += 1
        if nm_prov["reps_banded_sets"]:
            reps_banded_sessions += 1
        if nm_prov["indeterminate_laterality"]:
            indeterminate_sessions += 1
        if nm_prov["post_epoch_zero_rpe"]:
            artifact_signature_sessions += 1

    db.commit()
    return {
        "formula_version": FORMULA_VERSION,
        "sessions": len(sessions),
        "events_written": events_written,
        "sessions_with_e1rm_fit": e1rm_fit_sessions,
        "sessions_reps_banded": reps_banded_sessions,
        "sessions_indeterminate_laterality": indeterminate_sessions,
        "sessions_artifact_signature": artifact_signature_sessions,
    }


def compute_all_users(db: Session, *, only_user_id: int | None = None) -> dict[str, Any]:
    """Recompute load_events for one user or every keyed user."""
    from hevy_templates import users_with_hevy_key

    if only_user_id is not None:
        return {"users": 1, "per_user": {only_user_id: compute_load_events(db, only_user_id)}}
    per_user: dict[int, Any] = {}
    for uid, _ in users_with_hevy_key(db):
        per_user[uid] = compute_load_events(db, uid)
    return {"users": len(per_user), "per_user": per_user}


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Recompute Tier-0 load_events from hevy_workouts.")
    parser.add_argument("--user", type=int, default=None, help="only this user id")
    args = parser.parse_args()

    from database import SessionLocal

    _db = SessionLocal()
    try:
        _result = compute_all_users(_db, only_user_id=args.user)
        print(_result)
    finally:
        _db.close()
