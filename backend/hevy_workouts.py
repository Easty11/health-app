"""Hevy workout ingestion — persist workouts + sets, backfill, dedup flagging.

The persistence half of the Q6 four-window strength-load lane (DECISIONS_LOG
#28/#32; brief steps 1-2, D-B / D-G). Fetches a user's Hevy workout history,
upserts it into `hevy_workouts` + `hevy_sets`, and flags — never drops —
same-window high-similarity duplicates for operator adjudication.

Keyed on the Hevy workout `id` (PK-upsert), so re-running over the same 180-day
window is idempotent (D-G: dedup is flag-and-adjudicate, never delete). Sets are
replaced in place per workout on each ingest (natural key
`workout_id, block_index, set_index`), so a corrected/edited workout re-ingests
cleanly.

Two ownership rules, both mirroring `hevy_templates._upsert_template`'s
"never clobber an app-owned annotation on resync":

  * `excluded_at` / `exclusion_reason` — the operator adjudication mark. This
    module NEVER writes them, so a resync preserves an exclusion.
  * `dedup_flag` / `dedup_partner_ids` — sync-DERIVED and recompute-safe: reset
    then recomputed over the user's whole persisted history each run.

Re-runnable CLI:
    python backend/hevy_workouts.py                 # sync all keyed users, 180d
    python backend/hevy_workouts.py --days 90       # narrower window
    python backend/hevy_workouts.py --user 1        # one user
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import models
from connectors.hevy import HevyClient
from hevy_templates import user_hevy_key, users_with_hevy_key

logger = logging.getLogger(__name__)

# Fitness τ ≈ 42 d (#28/#32) wants a clean chronic ramp; 180 d gives >4 τ of
# lead-in. 90 d is already connector-verified — 180 d is the same path, further back.
DEFAULT_BACKFILL_DAYS = 180

# Dedup (D-G). Two workouts are a same-window high-similarity pair when their
# start_times fall within PROXIMITY and either their exercise-template sets overlap
# at >= JACCARD_MIN or they carry the same non-empty title. PROXIMITY is 24 h rather
# than a strict calendar day so a session re-logged across midnight (the live
# "16/17 Jun" pair) is still caught; the similarity test is what keeps a genuine
# consecutive-day split from tripping it. Flag-only: over-flagging is the safe
# direction because the operator adjudicates and nothing is auto-excluded.
_DEDUP_PROXIMITY = timedelta(hours=24)
_DEDUP_JACCARD_MIN = 0.5


# ---------------------------------------------------------------------------
# Raw payload parsing
# ---------------------------------------------------------------------------

def _parse_dt(raw: Any) -> datetime | None:
    """ISO-8601 → aware datetime (UTC-normalised), or None if absent/unparseable.

    Mirrors `audit_exercise_tag_coverage._workout_start`'s tolerance (`Z` suffix).
    A None here is load-bearing for fail-closed dedup: a workout whose start cannot
    be placed can never be shown NOT to coincide with another, so it is compared on
    title alone rather than silently treated as unique.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("unparseable Hevy timestamp %r", raw)
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iter_sets(workout: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield one flat dict per set with its (block_index, set_index) position.

    `block_index` is the exercise's ordinal in the workout, `set_index` the set's
    ordinal in the exercise — enumerate order, matching how `context_builder`
    renders them. Reads the live-verified snake_case set shape (#68): `type`,
    `weight_kg`, `reps`, `duration_seconds`, `distance_meters`, `rpe`. A set with no
    `exercise_template_id` on its parent exercise is skipped (nothing to key on, #79).
    """
    for block_index, ex in enumerate(workout.get("exercises", []) or []):
        template_id = ex.get("exercise_template_id")
        if not template_id:
            continue
        for set_index, s in enumerate(ex.get("sets", []) or []):
            yield {
                "exercise_template_id": template_id,
                "block_index": block_index,
                "set_index": set_index,
                "type": s.get("type"),
                "weight_kg": s.get("weight_kg"),
                "reps": s.get("reps"),
                "duration_seconds": s.get("duration_seconds"),
                "distance_meters": s.get("distance_meters"),
                "rpe": s.get("rpe"),
            }


def _template_ids(workout: dict[str, Any]) -> frozenset[str]:
    """Distinct exercise_template_ids used in a workout — the dedup similarity set."""
    return frozenset(
        ex.get("exercise_template_id")
        for ex in (workout.get("exercises", []) or [])
        if ex.get("exercise_template_id")
    )


def _norm_title(title: str | None) -> str:
    return (title or "").strip().lower()


# ---------------------------------------------------------------------------
# Dedup detection (flag-and-adjudicate, D-G)
# ---------------------------------------------------------------------------

def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|A∩B| / |A∪B|. Two empty sets are NOT similar (0.0) — an empty-vs-empty match
    would flag every logging-only workout as a mutual duplicate."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _same_window(a_start: datetime | None, b_start: datetime | None) -> bool:
    """Do two workouts fall in the same dedup window?

    Fail-closed: if EITHER start is missing we cannot prove they are apart, so we
    treat them as in-window and let the similarity test decide. Two timestamped
    workouts must fall within `_DEDUP_PROXIMITY`.
    """
    if a_start is None or b_start is None:
        return True
    return abs(a_start - b_start) <= _DEDUP_PROXIMITY


def detect_duplicate_pairs(
    workouts: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """hevy_id → set of hevy_ids it is a same-window high-similarity duplicate of.

    Pure function over lightweight workout dicts, each carrying `hevy_id`, `start`
    (aware datetime|None) and `template_ids` (frozenset) and `title`. Symmetric:
    if A pairs with B, B pairs with A. Deterministic — no clock, no ordering
    dependence. This is the whole dedup mechanism; ingestion just persists its output.
    """
    partners: dict[str, set[str]] = {w["hevy_id"]: set() for w in workouts}
    for i in range(len(workouts)):
        for j in range(i + 1, len(workouts)):
            a, b = workouts[i], workouts[j]
            if not _same_window(a["start"], b["start"]):
                continue
            title_match = bool(_norm_title(a["title"])) and _norm_title(a["title"]) == _norm_title(b["title"])
            jaccard = _jaccard(a["template_ids"], b["template_ids"])
            if title_match or jaccard >= _DEDUP_JACCARD_MIN:
                partners[a["hevy_id"]].add(b["hevy_id"])
                partners[b["hevy_id"]].add(a["hevy_id"])
    return partners


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _upsert_workout(db: Session, w: dict[str, Any], user_id: int, now: datetime) -> str | None:
    """Upsert one raw Hevy workout + its sets. Returns the hevy_id, or None if the
    payload carries no id (unkeyable — skipped rather than minting a null PK).

    PRESERVES `excluded_at`/`exclusion_reason` on an existing row (never assigned
    here). Replaces the workout's sets in place: delete-then-insert keyed on the
    natural position key, so an edited/corrected re-ingest is clean.
    """
    hevy_id = w.get("id")
    if not hevy_id:
        logger.warning("Hevy workout with no id — skipping (unkeyable)")
        return None

    row = db.get(models.HevyWorkout, hevy_id)
    if row is None:
        row = models.HevyWorkout(hevy_id=hevy_id, user_id=user_id)
        db.add(row)
    # user_id is re-affirmed but never re-owned to another user by a resync.
    row.user_id = user_id
    row.start_time = _parse_dt(w.get("start_time") or w.get("created_at"))
    row.end_time = _parse_dt(w.get("end_time"))
    row.title = w.get("title") or w.get("name")
    row.raw = w
    row.synced_at = now
    # excluded_at / exclusion_reason: deliberately untouched.

    # Parent-before-child, made EXPLICIT (#239 follow-up). `SessionLocal` runs
    # autoflush=False and these models carry FK columns but no `relationship()`, so
    # the unit of work does NOT order the workout INSERT ahead of its set INSERTs on
    # its own: at a single end-of-loop commit it can emit the `hevy_sets` batch while
    # parent `hevy_workouts` rows are still pending, tripping
    # `hevy_sets_workout_id_fkey`. (Masked on SQLite until PRAGMA foreign_keys=ON.)
    # Flushing the parent here guarantees it exists before any child row is inserted,
    # and also anchors the delete-then-insert set replacement on resync.
    db.flush()

    # Replace sets in place.
    db.execute(delete(models.HevySet).where(models.HevySet.workout_id == hevy_id))
    for s in _iter_sets(w):
        db.add(models.HevySet(workout_id=hevy_id, **s))

    return hevy_id


def _recompute_dedup(db: Session, user_id: int) -> int:
    """Recompute dedup flags over ALL of a user's persisted workouts. Recompute-safe:
    resets every flag first, then sets the flagged ones — so a workout that stops
    being a duplicate (its partner was excluded and re-synced away) clears cleanly.
    Returns the count of flagged workouts. Never touches `excluded_at`.
    """
    rows = db.execute(
        select(
            models.HevyWorkout.hevy_id,
            models.HevyWorkout.start_time,
            models.HevyWorkout.title,
            models.HevyWorkout.raw,
        ).where(models.HevyWorkout.user_id == user_id)
    ).all()

    workouts = [
        {
            "hevy_id": r.hevy_id,
            "start": r.start_time if r.start_time is None or r.start_time.tzinfo else r.start_time.replace(tzinfo=timezone.utc),
            "title": r.title,
            "template_ids": _template_ids(r.raw or {}),
        }
        for r in rows
    ]
    partners = detect_duplicate_pairs(workouts)

    # Reset then set — one bulk reset, then per-flagged updates.
    db.execute(
        update(models.HevyWorkout)
        .where(models.HevyWorkout.user_id == user_id)
        .values(dedup_flag=False, dedup_partner_ids=None)
    )
    flagged = 0
    for hevy_id, partner_set in partners.items():
        if partner_set:
            db.execute(
                update(models.HevyWorkout)
                .where(models.HevyWorkout.hevy_id == hevy_id)
                .values(dedup_flag=True, dedup_partner_ids=sorted(partner_set))
            )
            flagged += 1
    return flagged


def _in_window(w: dict[str, Any], cutoff: datetime) -> bool:
    """Is this workout inside the backfill window? A workout with no parseable start
    is KEPT — excluding it would silently drop history the load path may need, and a
    missing timestamp is a data-quality signal, not a reason to discard the row."""
    start = _parse_dt(w.get("start_time") or w.get("created_at"))
    return start is None or start >= cutoff


async def sync_one_user(
    db: Session,
    user_id: int,
    api_key: str,
    *,
    days: int = DEFAULT_BACKFILL_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Sync one user's Hevy workouts into the store, then recompute dedup flags.

    Fetches the full history via `get_all_workouts` (page_count termination lives in
    the client), filters to the `days` window, PK-upserts each workout + its sets,
    commits once, then recomputes dedup. Returns per-user counts including RPE
    coverage over normal weighted sets (the backfill assertion the brief requires).
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    client = HevyClient(api_key)

    resp = await client.get_all_workouts()
    all_workouts = resp.get("workouts", []) or []
    in_window = [w for w in all_workouts if _in_window(w, cutoff)]

    workouts_upserted = 0
    sets_upserted = 0
    for w in in_window:
        hevy_id = _upsert_workout(db, w, user_id, now)
        if hevy_id is not None:
            workouts_upserted += 1
            sets_upserted += sum(1 for _ in _iter_sets(w))
    db.commit()

    flagged = _recompute_dedup(db, user_id)
    db.commit()

    rpe = _rpe_coverage(in_window)
    return {
        "fetched_total": len(all_workouts),
        "in_window": len(in_window),
        "workouts_upserted": workouts_upserted,
        "sets_upserted": sets_upserted,
        "dedup_flagged": flagged,
        "rpe_coverage": rpe,
    }


def _rpe_coverage(workouts: list[dict[str, Any]]) -> dict[str, Any]:
    """RPE coverage over NORMAL WEIGHTED sets — the backfill quality number the brief
    asks be reported (not eyeballed). A normal weighted set is `type == 'normal'`
    (or unset) with a non-null `weight_kg`; warmups/dropsets/failures and non-weight
    sets are out of scope for the Neuromuscular RPE channel."""
    total = 0
    with_rpe = 0
    for w in workouts:
        for s in _iter_sets(w):
            set_type = s.get("type") or "normal"
            if set_type != "normal" or s.get("weight_kg") is None:
                continue
            total += 1
            if s.get("rpe") is not None:
                with_rpe += 1
    pct = round(100.0 * with_rpe / total, 1) if total else None
    return {"normal_weighted_sets": total, "with_rpe": with_rpe, "pct": pct}


async def sync_workouts(
    db: Session,
    *,
    only_user_id: int | None = None,
    days: int = DEFAULT_BACKFILL_DAYS,
) -> dict[str, Any]:
    """Sync keyed users' Hevy workouts. `only_user_id` scopes to one user."""
    if only_user_id is not None:
        api_key = user_hevy_key(db, only_user_id)
        if api_key is None:
            return {"users": 0, "detail": f"user {only_user_id} has no Hevy key"}
        result = await sync_one_user(db, only_user_id, api_key, days=days)
        return {"users": 1, "per_user": {only_user_id: result}}

    per_user: dict[int, Any] = {}
    for uid, api_key in users_with_hevy_key(db):
        per_user[uid] = await sync_one_user(db, uid, api_key, days=days)
    return {"users": len(per_user), "per_user": per_user}


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Sync Hevy workouts into the store.")
    parser.add_argument("--user", type=int, default=None, help="only this user id")
    parser.add_argument("--days", type=int, default=DEFAULT_BACKFILL_DAYS, help="backfill window")
    args = parser.parse_args()

    from database import SessionLocal

    _db = SessionLocal()
    try:
        _result = asyncio.run(sync_workouts(_db, only_user_id=args.user, days=args.days))
        print(_result)
    finally:
        _db.close()
