"""`GET /series/load` — the chart read surface (Visuals increment 1).

Read-only over `load_metrics`. These call the route function directly (as
`test_interpretation_endpoint` does) with the in-memory `db_session` — the auth dependency
and query wiring are FastAPI's, not the logic under test. What IS under test: response shape,
the `windows` allowlist, the `days` bound, user scoping, and version pinning (only the current
metrics_version is served, and a window collapses to a single formula_version).
"""
from datetime import datetime, timedelta, timezone

import pytz

import models
from load_metrics import METRICS_VERSION
from routers.series import get_load_series

_AEST = pytz.timezone("Australia/Brisbane")


def _today():
    return datetime.now(_AEST).date()


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _metric(db, *, user_id, day, window, daily_load=100.0, maturity="ok",
            unit="kg_reps", fv="tier0-v1", mv=METRICS_VERSION, computed_at=None):
    db.add(models.LoadMetric(
        user_id=user_id, day=day, load_window=window,
        daily_load=daily_load, fitness=daily_load * 2, fatigue=daily_load,
        form=daily_load, acute_load=daily_load, chronic_load=daily_load,
        load_ratio=1.0, unit=unit, maturity=maturity,
        formula_version=fv, metrics_version=mv,
        computed_at=computed_at or datetime.now(timezone.utc),
    ))
    db.commit()


def _call(db, user, **kw):
    return get_load_series(current_user=user, db=db, **{"days": 90, "windows": None, **kw})


# ---------- shape ----------

def test_shape_is_days_metrics_version_and_windows_with_points(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _metric(db_session, user_id=u.id, day=today, window="mechanical")

    out = _call(db_session, u)

    assert out.days == 90
    assert out.metrics_version == METRICS_VERSION
    assert len(out.windows) == 1
    w = out.windows[0]
    assert w.load_window == "mechanical"
    assert w.unit == "kg_reps"
    assert w.formula_version == "tier0-v1"
    p = w.points[0]
    # Every field the LoadChart consumes is present.
    assert p.day == today.isoformat()
    for attr in ("daily_load", "fitness", "fatigue", "form", "acute_load", "chronic_load", "maturity"):
        assert hasattr(p, attr)


def test_points_are_ascending_by_day(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    for n in (0, 3, 1, 2):  # inserted out of order
        _metric(db_session, user_id=u.id, day=today - timedelta(days=n), window="mechanical")

    out = _call(db_session, u)
    days = [p.day for p in out.windows[0].points]
    assert days == sorted(days)


def test_default_returns_all_populated_windows(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _metric(db_session, user_id=u.id, day=today, window="mechanical", unit="kg_reps")
    _metric(db_session, user_id=u.id, day=today, window="neuromuscular", unit="nm_au")

    out = _call(db_session, u)
    assert {w.load_window for w in out.windows} == {"mechanical", "neuromuscular"}


# ---------- windows allowlist ----------

def test_windows_param_filters_to_the_allowlist(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _metric(db_session, user_id=u.id, day=today, window="mechanical")
    _metric(db_session, user_id=u.id, day=today, window="neuromuscular", unit="nm_au")

    out = _call(db_session, u, windows="mechanical")
    assert [w.load_window for w in out.windows] == ["mechanical"]


def test_unknown_window_matches_nothing_not_an_error(db_session):
    u = _user(db_session, "a@example.com")
    _metric(db_session, user_id=u.id, day=_today(), window="mechanical")

    out = _call(db_session, u, windows="psychological")
    assert out.windows == []


# ---------- days bound ----------

def test_days_bound_excludes_rows_older_than_the_window(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _metric(db_session, user_id=u.id, day=today - timedelta(days=10), window="mechanical", daily_load=10.0)
    _metric(db_session, user_id=u.id, day=today - timedelta(days=200), window="mechanical", daily_load=999.0)

    out = _call(db_session, u, days=90)
    loads = [p.daily_load for p in out.windows[0].points]
    assert loads == [10.0]  # the 200-day-old row is outside the 90-day bound


# ---------- user scoping ----------

def test_a_users_series_contains_nothing_of_anothers(db_session):
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")
    today = _today()
    _metric(db_session, user_id=a.id, day=today, window="mechanical", daily_load=11.0)
    _metric(db_session, user_id=b.id, day=today, window="mechanical", daily_load=22.0)

    out_a = _call(db_session, a)
    out_b = _call(db_session, b)
    assert [p.daily_load for p in out_a.windows[0].points] == [11.0]
    assert [p.daily_load for p in out_b.windows[0].points] == [22.0]


# ---------- version pinning ----------

def test_only_the_current_metrics_version_is_served(db_session):
    u = _user(db_session, "a@example.com")
    today = _today()
    _metric(db_session, user_id=u.id, day=today, window="mechanical", daily_load=5.0, mv=METRICS_VERSION)
    _metric(db_session, user_id=u.id, day=today, window="mechanical", daily_load=999.0, mv="banister-v0")

    out = _call(db_session, u)
    loads = [p.daily_load for p in out.windows[0].points]
    assert loads == [5.0]  # the retired τ-set row is excluded


def test_a_window_collapses_to_the_latest_formula_version(db_session):
    """If a superseded formula_version lingers beside the current one at the same
    metrics_version, the series shows exactly one — the most recently computed — never a
    doubled day."""
    u = _user(db_session, "a@example.com")
    today = _today()
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 6, 1, tzinfo=timezone.utc)
    _metric(db_session, user_id=u.id, day=today, window="mechanical", daily_load=1.0,
            fv="tier0-v0", computed_at=old)
    _metric(db_session, user_id=u.id, day=today, window="mechanical", daily_load=2.0,
            fv="tier0-v1", computed_at=new)

    out = _call(db_session, u)
    w = out.windows[0]
    assert w.formula_version == "tier0-v1"
    assert [p.daily_load for p in w.points] == [2.0]  # one point, the current fv
