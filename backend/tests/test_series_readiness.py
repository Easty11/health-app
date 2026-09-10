"""`GET /series/readiness` — the observed-readiness chart read surface (Visuals increment 2).

Read-only over `daily_records`. These call the route function directly (as `test_series_load`
does) with the in-memory `db_session` — the auth dependency and query wiring are FastAPI's, not
the logic under test. What IS under test: response shape, ascending-by-day order, the `days`
bound, user scoping, and NULL PRESERVATION (a missing self-report stays null, never a zero).

Deliberately asserts the shape carries ONLY `date`, `morning_readiness`, `passive_hrv_ms` — the
forecast/confidence pair is excluded by design until Q141 (a 0–10 forecast against a 1–5 ordinal
is not a residual, and the column is written nowhere today).
"""
from datetime import datetime, timedelta, timezone

import pytz

import models
from routers.series import get_readiness_series

_AEST = pytz.timezone("Australia/Brisbane")


def _today():
    return datetime.now(_AEST).date()


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _record(db, *, user_id, day, morning_readiness=3, passive_hrv_ms=45.0):
    db.add(models.DailyRecord(
        user_id=user_id, date=day,
        morning_readiness=morning_readiness, passive_hrv_ms=passive_hrv_ms,
    ))
    db.commit()


def _call(db, user, **kw):
    return get_readiness_series(current_user=user, db=db, **{"days": 90, **kw})


# ---------- shape ----------

def test_shape_is_days_and_points_with_the_three_observed_fields(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _record(db_session, user_id=u.id, day=today, morning_readiness=4, passive_hrv_ms=52.0)

    out = _call(db_session, u)

    assert out.days == 90
    assert len(out.points) == 1
    p = out.points[0]
    assert p.date == today.isoformat()
    assert p.morning_readiness == 4
    assert p.passive_hrv_ms == 52.0
    # The forecast/confidence pair is intentionally absent from the point shape (Q141).
    assert not hasattr(p, "model_forecast")
    assert not hasattr(p, "model_confidence")


def test_points_are_ascending_by_day(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    for n in (0, 3, 1, 2):  # inserted out of order
        _record(db_session, user_id=u.id, day=today - timedelta(days=n))

    out = _call(db_session, u)
    dates = [p.date for p in out.points]
    assert dates == sorted(dates)


# ---------- null preservation ----------

def test_a_null_self_report_stays_null_not_zero(db_session):
    """A day with a record but no AM check-in keeps morning_readiness null — the chart draws a
    gap, and a gap is not a readiness of zero. Same for a missing overnight HRV."""
    u = _user(db_session, "a@example.com")
    today = _today()
    _record(db_session, user_id=u.id, day=today - timedelta(days=1),
            morning_readiness=None, passive_hrv_ms=None)
    _record(db_session, user_id=u.id, day=today,
            morning_readiness=5, passive_hrv_ms=60.0)

    out = _call(db_session, u)
    assert [p.morning_readiness for p in out.points] == [None, 5]
    assert [p.passive_hrv_ms for p in out.points] == [None, 60.0]


# ---------- days bound ----------

def test_days_bound_excludes_records_older_than_the_window(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _record(db_session, user_id=u.id, day=today - timedelta(days=10), morning_readiness=2)
    _record(db_session, user_id=u.id, day=today - timedelta(days=200), morning_readiness=1)

    out = _call(db_session, u, days=90)
    assert [p.morning_readiness for p in out.points] == [2]  # the 200-day-old row is outside


# ---------- user scoping ----------

def test_a_users_series_contains_nothing_of_anothers(db_session):
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")
    today = _today()
    _record(db_session, user_id=a.id, day=today, morning_readiness=2)
    _record(db_session, user_id=b.id, day=today, morning_readiness=4)

    out_a = _call(db_session, a)
    out_b = _call(db_session, b)
    assert [p.morning_readiness for p in out_a.points] == [2]
    assert [p.morning_readiness for p in out_b.points] == [4]
