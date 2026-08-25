"""Hevy workout ingestion — persistence, idempotency, dedup, RPE coverage.

Covers the persistence-layer guarantees the Q6 load lane rests on (D-B / D-G):
  * a raw workout upserts to header + per-set rows with correct positional keys;
  * re-ingest is idempotent (PK-upsert; sets replaced in place, not appended);
  * the operator exclusion mark survives a resync (sync never writes it);
  * dedup flags same-window high-similarity pairs — positive, negative, and
    FAIL-CLOSED (a missing timestamp never lets a same-title pair slip through as
    unique), and NEVER auto-deletes;
  * RPE coverage over normal weighted sets is reported as a number.
"""
import asyncio
from datetime import datetime, timezone

import models
import hevy_workouts as hw


def _user(db, uid=1, email="luke@example.com"):
    u = models.User(id=uid, email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _tmpl(db, id_, title, laterality=None, is_custom=False, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=id_, title=title, is_custom=is_custom, owner_user_id=owner, laterality=laterality,
    ))
    db.commit()


def _ex(tid, sets):
    return {"exercise_template_id": tid, "sets": sets}


def _wk(id_, start, title, exercises):
    return {"id": id_, "start_time": start, "end_time": None, "title": title, "exercises": exercises}


# ── Persistence + positional keys ───────────────────────────────────────────

def test_upsert_persists_header_and_sets(db_session):
    _user(db_session)
    now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    w = _wk("w1", "2026-08-24T10:00:00Z", "Upper", [
        _ex("BENCH", [
            {"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0},
            {"type": "warmup", "weight_kg": 60.0, "reps": 5},
        ]),
        _ex("ROW", [{"type": "normal", "weight_kg": 80.0, "reps": 8}]),
    ])
    hw._upsert_workout(db_session, w, 1, now)
    db_session.commit()

    wo = db_session.get(models.HevyWorkout, "w1")
    assert wo.user_id == 1 and wo.title == "Upper"
    # SQLite drops tzinfo on readback (Postgres preserves it); compare tz-naively.
    assert wo.start_time.replace(tzinfo=None) == datetime(2026, 8, 24, 10, 0)
    assert wo.raw["id"] == "w1"                       # full payload kept for recompute

    sets = db_session.query(models.HevySet).order_by(
        models.HevySet.block_index, models.HevySet.set_index
    ).all()
    assert [(s.block_index, s.set_index, s.exercise_template_id, s.type) for s in sets] == [
        (0, 0, "BENCH", "normal"),
        (0, 1, "BENCH", "warmup"),
        (1, 0, "ROW", "normal"),
    ]
    assert sets[0].weight_kg == 100.0 and sets[0].reps == 5 and sets[0].rpe == 8.0


def test_reingest_is_idempotent(db_session):
    _user(db_session)
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    w = _wk("w1", "2026-08-24T10:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    hw._upsert_workout(db_session, w, 1, now)
    db_session.commit()
    hw._upsert_workout(db_session, w, 1, now)         # second ingest, same payload
    db_session.commit()

    assert db_session.query(models.HevyWorkout).count() == 1
    assert db_session.query(models.HevySet).count() == 1   # sets replaced, not doubled


def test_exclusion_mark_survives_resync(db_session):
    """excluded_at / exclusion_reason are operator-owned; a resync must not clear them."""
    _user(db_session)
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    w = _wk("w1", "2026-08-24T10:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    hw._upsert_workout(db_session, w, 1, now)
    db_session.commit()

    wo = db_session.get(models.HevyWorkout, "w1")
    wo.excluded_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    wo.exclusion_reason = "adjudicated duplicate"
    db_session.commit()

    hw._upsert_workout(db_session, w, 1, now)          # resync
    db_session.commit()
    wo = db_session.get(models.HevyWorkout, "w1")
    assert wo.excluded_at is not None
    assert wo.exclusion_reason == "adjudicated duplicate"


# ── Dedup (flag-and-adjudicate, never delete) ───────────────────────────────

def _ingest_and_flag(db, workouts, uid=1):
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    for w in workouts:
        hw._upsert_workout(db, w, uid, now)
    db.commit()
    flagged = hw._recompute_dedup(db, uid)
    db.commit()
    return flagged


def test_dedup_flags_same_day_duplicate(db_session):
    _user(db_session)
    a = _wk("a", "2026-08-24T10:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    b = _wk("b", "2026-08-24T18:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    _ingest_and_flag(db_session, [a, b])

    rows = {w.hevy_id: w for w in db_session.query(models.HevyWorkout).all()}
    assert rows["a"].dedup_flag and rows["a"].dedup_partner_ids == ["b"]
    assert rows["b"].dedup_flag and rows["b"].dedup_partner_ids == ["a"]
    # Flag-and-adjudicate: nothing deleted, nothing auto-excluded.
    assert db_session.query(models.HevyWorkout).count() == 2
    assert rows["a"].excluded_at is None and rows["b"].excluded_at is None


def test_dedup_does_not_flag_distinct_workouts(db_session):
    _user(db_session)
    a = _wk("a", "2026-08-24T10:00:00Z", "Legs", [_ex("SQUAT", [{"type": "normal", "weight_kg": 140.0, "reps": 5}])])
    b = _wk("b", "2026-08-24T18:00:00Z", "Push", [_ex("OHP", [{"type": "normal", "weight_kg": 50.0, "reps": 5}])])
    _ingest_and_flag(db_session, [a, b])
    rows = {w.hevy_id: w for w in db_session.query(models.HevyWorkout).all()}
    assert not rows["a"].dedup_flag and rows["a"].dedup_partner_ids is None
    assert not rows["b"].dedup_flag


def test_dedup_far_apart_same_title_not_flagged(db_session):
    """Same title but weeks apart is a normal repeated session, not a duplicate."""
    _user(db_session)
    a = _wk("a", "2026-08-01T10:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    b = _wk("b", "2026-08-20T10:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    _ingest_and_flag(db_session, [a, b])
    rows = {w.hevy_id: w for w in db_session.query(models.HevyWorkout).all()}
    assert not rows["a"].dedup_flag and not rows["b"].dedup_flag


def test_dedup_fails_closed_on_missing_timestamp(db_session):
    """A workout with no parseable start cannot be shown apart from a same-title peer,
    so it is flagged (fail-closed), never passed through as unique."""
    _user(db_session)
    a = _wk("a", None, "Bench Day", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    b = _wk("b", None, "Bench Day", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    _ingest_and_flag(db_session, [a, b])
    rows = {w.hevy_id: w for w in db_session.query(models.HevyWorkout).all()}
    assert rows["a"].dedup_flag and rows["b"].dedup_flag


def test_dedup_recompute_clears_stale_flag(db_session):
    """Recompute-safe: once a partner is removed, the surviving row's flag clears."""
    _user(db_session)
    a = _wk("a", "2026-08-24T10:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    b = _wk("b", "2026-08-24T18:00:00Z", "Upper", [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])
    _ingest_and_flag(db_session, [a, b])
    # Remove b's sets/row and recompute — a should no longer be flagged.
    db_session.query(models.HevySet).filter_by(workout_id="b").delete()
    db_session.delete(db_session.get(models.HevyWorkout, "b"))
    db_session.commit()
    hw._recompute_dedup(db_session, 1)
    db_session.commit()
    assert db_session.get(models.HevyWorkout, "a").dedup_flag is False


# ── Window + RPE coverage ───────────────────────────────────────────────────

def test_window_filter_and_missing_start_kept():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    cutoff = now.replace(day=25) - __import__("datetime").timedelta(days=180)
    old = _wk("old", "2025-01-01T10:00:00Z", "Ancient", [])
    recent = _wk("recent", "2026-08-01T10:00:00Z", "Recent", [])
    nostart = _wk("nostart", None, "Undated", [])
    assert hw._in_window(recent, cutoff) is True
    assert hw._in_window(old, cutoff) is False
    assert hw._in_window(nostart, cutoff) is True   # kept — never silently dropped


def test_rpe_coverage_counts_only_normal_weighted_sets():
    w = _wk("w", "2026-08-24T10:00:00Z", "Upper", [
        _ex("BENCH", [
            {"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0},   # counted, has rpe
            {"type": "normal", "weight_kg": 100.0, "reps": 5},               # counted, no rpe
            {"type": "warmup", "weight_kg": 60.0, "reps": 5, "rpe": 5.0},    # excluded (warmup)
        ]),
        _ex("PLANK", [{"type": "normal", "duration_seconds": 60}]),          # excluded (no weight)
    ])
    cov = hw._rpe_coverage([w])
    assert cov == {"normal_weighted_sets": 2, "with_rpe": 1, "pct": 50.0}


# ── End-to-end sync with a stubbed client (backfill window + summary) ────────

class _FakeClient:
    def __init__(self, workouts):
        self._workouts = workouts

    async def get_all_workouts(self, page_size=10):
        return {"workouts": self._workouts, "page_count": 1}


def test_sync_one_user_backfills_window_and_reports(db_session, monkeypatch):
    _user(db_session)
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    in_win = _wk("a", "2026-08-24T10:00:00Z", "Upper",
                 [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0}])])
    out_win = _wk("z", "2025-01-01T10:00:00Z", "Ancient",
                  [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5}])])

    monkeypatch.setattr(hw, "HevyClient", lambda api_key: _FakeClient([in_win, out_win]))
    result = asyncio.run(hw.sync_one_user(db_session, 1, "key", days=180, now=now))

    assert result["fetched_total"] == 2
    assert result["in_window"] == 1
    assert result["workouts_upserted"] == 1
    assert result["rpe_coverage"] == {"normal_weighted_sets": 1, "with_rpe": 1, "pct": 100.0}
    assert db_session.query(models.HevyWorkout).count() == 1     # out-of-window not stored
    assert db_session.get(models.HevyWorkout, "a") is not None
