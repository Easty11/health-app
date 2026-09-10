"""`GET /series/exercises` + `GET /series/exercise/{id}` — per-exercise progression
(Visuals increment 3). Read-only over `hevy_workouts.raw`.

These call the route functions directly (as `test_series_load` does) with the in-memory
`db_session`; auth and query wiring are FastAPI's, not the logic under test. What IS under
test (the brief's GATES): Epley arithmetic, the rep>cap e1RM exclusion, warmup exclusion,
the dedup/excluded exclusion, per-day collapse, the selector threshold + ordering, and user
scoping.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytz

import models
from routers.series import (
    _aggregate_session,
    _epley_e1rm,
    get_exercise_list,
    get_exercise_series,
)

_AEST = pytz.timezone("Australia/Brisbane")


def _today():
    return datetime.now(_AEST).date()


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _template(db, tid, title):
    db.add(models.HevyExerciseTemplate(id=tid, title=title))
    db.commit()


def _ws(weight, reps, set_type="normal"):
    """A raw Hevy set dict in the live snake_case shape (hevy_format.py)."""
    return {"type": set_type, "weight_kg": weight, "reps": reps}


def _workout(db, *, user_id, day, blocks, dedup=False, excluded=False, hevy_id=None):
    """One HevyWorkout whose `raw.exercises` carries `blocks` = [(template_id, [sets])].

    `start_time` is noon UTC on `day` → 22:00 AEST same day, so `_local_day(start_time)`
    buckets it onto `day` with no edge ambiguity."""
    hevy_id = hevy_id or f"w-{user_id}-{day.isoformat()}-{len(day.isoformat())}-{id(blocks)}"
    raw = {"exercises": [
        {"exercise_template_id": tid, "sets": sets} for tid, sets in blocks
    ]}
    db.add(models.HevyWorkout(
        hevy_id=hevy_id,
        user_id=user_id,
        start_time=datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc),
        raw=raw,
        dedup_flag=dedup,
        excluded_at=datetime.now(timezone.utc) if excluded else None,
    ))
    db.commit()


def _series(db, user, tid, **kw):
    return get_exercise_series(template_id=tid, current_user=user, db=db,
                               **{"days": 180, **kw})


def _list(db, user, **kw):
    return get_exercise_list(current_user=user, db=db, **{"days": 180, **kw})


# ---------- Epley arithmetic (pure) ----------

def test_epley_on_a_known_set():
    # 100 kg × 5 reps → 100 × (1 + 5/30) = 116.666…
    assert _epley_e1rm(100.0, 5) == pytest.approx(100.0 * (1.0 + 5.0 / 30.0))
    # 1RM is its own estimate: reps=1 → weight × (1 + 1/30)
    assert _epley_e1rm(60.0, 1) == pytest.approx(62.0)


def test_session_e1rm_is_the_max_over_working_sets():
    agg = _aggregate_session([_ws(100, 5), _ws(110, 3), _ws(90, 8)])
    # max Epley: 110×(1+3/30)=121 vs 100×1.1667=116.7 vs 90×1.2667=114 → 121, top set 110×3
    assert agg["e1rm_kg"] == pytest.approx(121.0)
    assert agg["top_set"] == {"weight_kg": 110.0, "reps": 3}


# ---------- rep > cap exclusion from e1RM, not volume (D1) ----------

def test_reps_over_cap_excluded_from_e1rm_but_counted_in_volume():
    # 60 kg × 12 reps is above the Epley cap → must not set e1RM, but its 720 kg·reps counts.
    agg = _aggregate_session([_ws(100, 5), _ws(60, 12)])
    assert agg["e1rm_kg"] == pytest.approx(_epley_e1rm(100.0, 5))   # the 5-rep set only
    assert agg["top_set"] == {"weight_kg": 100.0, "reps": 5}
    assert agg["volume_kg_reps"] == pytest.approx(100 * 5 + 60 * 12)  # both sets
    assert agg["working_sets"] == 2


def test_e1rm_null_when_every_set_is_over_cap():
    agg = _aggregate_session([_ws(50, 15), _ws(40, 20)])
    assert agg["e1rm_kg"] is None
    assert agg["top_set"] is None
    assert agg["volume_kg_reps"] == pytest.approx(50 * 15 + 40 * 20)  # volume still populated


# ---------- warmup exclusion (D3) ----------

def test_warmup_sets_are_excluded_everywhere():
    agg = _aggregate_session([_ws(40, 10, "warmup"), _ws(100, 5, "normal"), _ws(120, 2, "failure")])
    assert agg["working_sets"] == 2  # warmup not counted
    assert agg["volume_kg_reps"] == pytest.approx(100 * 5 + 120 * 2)  # warmup volume excluded
    # failure is a working set and eligible for e1RM: 120×(1+2/30)=128 beats 100×1.1667
    assert agg["top_set"] == {"weight_kg": 120.0, "reps": 2}


def test_a_session_of_only_warmups_is_no_point():
    assert _aggregate_session([_ws(40, 10, "warmup")]) is None


# ---------- dedup / excluded exclusion (D3, as the resolver does) ----------

def test_dedup_and_excluded_workouts_contribute_nothing(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _workout(db_session, user_id=u.id, day=today, blocks=[("SQ", [_ws(100, 5)])],
             hevy_id="keep")
    _workout(db_session, user_id=u.id, day=today - timedelta(days=1),
             blocks=[("SQ", [_ws(999, 5)])], dedup=True, hevy_id="dedup")
    _workout(db_session, user_id=u.id, day=today - timedelta(days=2),
             blocks=[("SQ", [_ws(888, 5)])], excluded=True, hevy_id="excl")

    out = _series(db_session, u, "SQ")
    assert [p.date for p in out.points] == [today.isoformat()]  # only the kept day
    assert out.points[0].e1rm_kg == pytest.approx(_epley_e1rm(100.0, 5))


# ---------- per-day collapse (brief step 2) ----------

def test_two_workouts_same_day_collapse_to_one_point(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _workout(db_session, user_id=u.id, day=today, blocks=[("SQ", [_ws(100, 5)])],
             hevy_id="am")
    _workout(db_session, user_id=u.id, day=today, blocks=[("SQ", [_ws(120, 3)])],
             hevy_id="pm")

    out = _series(db_session, u, "SQ")
    assert len(out.points) == 1
    p = out.points[0]
    assert p.volume_kg_reps == pytest.approx(100 * 5 + 120 * 3)  # summed across both
    assert p.e1rm_kg == pytest.approx(_epley_e1rm(120.0, 3))      # max across both
    assert p.working_sets == 2


def test_points_are_ascending_by_date(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    for n in (0, 5, 2, 9):  # inserted out of order
        _workout(db_session, user_id=u.id, day=today - timedelta(days=n),
                 blocks=[("SQ", [_ws(100, 5)])], hevy_id=f"d{n}")
    out = _series(db_session, u, "SQ")
    dates = [p.date for p in out.points]
    assert dates == sorted(dates)


# ---------- selector threshold + ordering (D5) ----------

def test_selector_threshold_and_ordering(db_session):
    u = _user(db_session, "a@example.com")
    _template(db_session, "SQ", "Squat")
    _template(db_session, "BP", "Bench Press")
    today = _today()
    # Squat: 4 session-days; Bench: 3 session-days; Curl: 2 (below threshold → dropped).
    for n in range(4):
        _workout(db_session, user_id=u.id, day=today - timedelta(days=n),
                 blocks=[("SQ", [_ws(100, 5)])], hevy_id=f"sq{n}")
    for n in range(3):
        _workout(db_session, user_id=u.id, day=today - timedelta(days=n),
                 blocks=[("BP", [_ws(80, 5)])], hevy_id=f"bp{n}")
    for n in range(2):
        _workout(db_session, user_id=u.id, day=today - timedelta(days=n),
                 blocks=[("CURL", [_ws(20, 10)])], hevy_id=f"cu{n}")

    items = _list(db_session, u)
    assert [it.template_id for it in items] == ["SQ", "BP"]  # desc by sessions, Curl excluded
    assert items[0].sessions == 4 and items[1].sessions == 3
    assert items[0].title == "Squat" and items[1].title == "Bench Press"


def test_selector_day_with_only_warmups_does_not_count(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    # 3 real session-days + 1 warmup-only day = still only 3 qualifying.
    for n in range(3):
        _workout(db_session, user_id=u.id, day=today - timedelta(days=n),
                 blocks=[("SQ", [_ws(100, 5)])], hevy_id=f"sq{n}")
    _workout(db_session, user_id=u.id, day=today - timedelta(days=10),
             blocks=[("SQ", [_ws(40, 10, "warmup")])], hevy_id="wu")

    items = _list(db_session, u)
    assert len(items) == 1 and items[0].sessions == 3


def test_missing_template_falls_back_to_id_as_title(db_session):
    u = _user(db_session, "a@example.com")  # no HevyExerciseTemplate row seeded
    today = _today()
    for n in range(3):
        _workout(db_session, user_id=u.id, day=today - timedelta(days=n),
                 blocks=[("ORPHAN", [_ws(100, 5)])], hevy_id=f"o{n}")
    items = _list(db_session, u)
    assert items[0].title == "ORPHAN"
    assert _series(db_session, u, "ORPHAN").title == "ORPHAN"


# ---------- user scoping ----------

def test_a_users_series_contains_nothing_of_anothers(db_session):
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")
    today = _today()
    _workout(db_session, user_id=a.id, day=today, blocks=[("SQ", [_ws(100, 5)])], hevy_id="a1")
    _workout(db_session, user_id=b.id, day=today, blocks=[("SQ", [_ws(200, 5)])], hevy_id="b1")

    out_a = _series(db_session, a, "SQ")
    out_b = _series(db_session, b, "SQ")
    assert out_a.points[0].top_set.weight_kg == 100.0
    assert out_b.points[0].top_set.weight_kg == 200.0


def test_days_bound_excludes_older_sessions(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _workout(db_session, user_id=u.id, day=today - timedelta(days=10),
             blocks=[("SQ", [_ws(100, 5)])], hevy_id="recent")
    _workout(db_session, user_id=u.id, day=today - timedelta(days=200),
             blocks=[("SQ", [_ws(999, 5)])], hevy_id="old")

    out = _series(db_session, u, "SQ", days=90)
    assert [p.date for p in out.points] == [(today - timedelta(days=10)).isoformat()]
