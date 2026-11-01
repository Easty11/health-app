"""The readers that used to print the whole-day `session_rpe` now print each session's door rating and source.

Historic day values are rendered nowhere (they were never session ratings); `daily_records.session_rpe` is written
by nothing and read by nothing. Each reader is driven from rows: a day record carrying a stale day value, a Hevy
workout and a Pilates, one rated `in_app` and one by Garmin.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import mcp_server
import models
import routers.checkin_v2 as c2
import srpe_store
from aerobic_format import format_day_ratings
from auth import get_current_user
from context_builder import _section_daily_record
from database import get_db
from reads.srpe_reads import aerobic_bout, hevy_bout, session_ratings

DAY = date(2026, 10, 31)
GARMIN_PKG = "com.garmin.android.apps.connectmobile"


def _utc(hh, mm=0):
    return datetime(2026, 10, 31, hh, mm, tzinfo=timezone.utc)


@pytest.fixture
def day(db_session, monkeypatch):
    """31 Oct: a stale day value on the record, a Hevy workout rated in_app 8, a Pilates rated by Garmin 3."""
    u = models.User(email="d@x.io", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    db_session.add(models.DailyRecord(user_id=u.id, date=DAY, am_timestamp=_utc(0), morning_readiness=3,
                                      sleep_quality=3, fatigue=3, motivation=3, life_load=3,
                                      pm_timestamp=_utc(12), today_rating=3, session_rpe=9.0))   # the stale day value
    db_session.add(models.HevyWorkout(hevy_id="h1", user_id=u.id, start_time=_utc(2),
                                      end_time=_utc(2) + timedelta(minutes=55), title="Upper body", raw={}))
    pil = models.AerobicSession(user_id=u.id, source="health_connect", source_session_id="p", session_date=DAY,
                                start_time=_utc(8), stop_time=_utc(8) + timedelta(minutes=52), sport_name="Pilates",
                                duration_minutes=52.0, source_package=GARMIN_PKG, z2_seconds=600)
    db_session.add(pil)
    db_session.commit()
    w = db_session.query(models.HevyWorkout).one()
    srpe_store.record_observation(db_session, u.id, source="in_app", source_activity_ref="hevy:h1", bout=hevy_bout(w),
                                  rpe_raw=8, raw_scale="cr10", now=_utc(11))
    srpe_store.record_observation(db_session, u.id, source="garmin", source_activity_ref="g1", start=_utc(8),
                                  stop=_utc(8) + timedelta(minutes=52), rpe_raw=30, raw_scale="garmin_0_100", now=_utc(11))
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    monkeypatch.setattr(c2, "_today_aest", lambda: DAY)
    return u


EXPECTED = "Upper body 8/10 in_app; Pilates 3/10 garmin"


def test_the_formatter_names_each_session_its_rating_and_source_and_says_unrated(db_session, day):
    rated = session_ratings(db_session, day.id, since=DAY, until=DAY)
    assert format_day_ratings(rated) == EXPECTED
    assert format_day_ratings([]) == "—"
    db_session.query(models.SessionRpeObservation).delete()
    db_session.commit()
    assert format_day_ratings(session_ratings(db_session, day.id, since=DAY, until=DAY)) == "Upper body unrated; Pilates unrated"


def test_mcp_checkin_history_prints_the_per_session_ratings_and_not_the_day_value(db_session, day, monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [
        {"date": DAY, "sleep_quality": 3, "fatigue": 3, "soreness": None, "motivation": 3, "life_load": 3,
         "alcohol_units": None, "hrv_ms": None, "morning_readiness": 3, "source": "daily_records"}])
    out = mcp_server.get_checkin_history(days=7)
    assert f"session_rpe=[{EXPECTED}]" in out
    assert "9.0" not in out and "session_rpe=9" not in out


def test_mcp_checkin_history_accepts_string_dates_from_a_raw_sqlite_read(db_session, day, monkeypatch):
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [
        {"date": DAY.isoformat(), "sleep_quality": 3, "fatigue": 3, "soreness": None, "motivation": 3, "life_load": 3,
         "alcohol_units": None, "hrv_ms": None, "morning_readiness": 3, "source": "daily_records"}])
    assert f"session_rpe=[{EXPECTED}]" in mcp_server.get_checkin_history(days=7)


def test_the_chat_daily_record_section_prints_the_per_session_line_and_never_the_day_value(db_session, day):
    rec = db_session.query(models.DailyRecord).one()
    line = format_day_ratings(session_ratings(db_session, day.id, since=DAY, until=DAY))
    text = _section_daily_record(rec, None, line)
    assert f"Session RPE, per session (source): {EXPECTED}" in text
    assert "Session RPE: 9" not in text and "9.0/10" not in text
    assert "per session" not in _section_daily_record(rec, None, None)           # no ratings: no line


def test_the_history_route_carries_each_days_sessions_with_their_rating_and_source(db_session, day):
    app = FastAPI()
    app.include_router(c2.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: day
    body = TestClient(app).get("/checkin-v2/history", params={"days": 7}).json()
    [rec] = [r for r in body if r["date"] == DAY.isoformat()]
    assert "session_rpe" not in rec
    assert [(s["label"], s["rpe"], s["source"]) for s in rec["sessions"]] == [
        ("Upper body", 8.0, "in_app"), ("Pilates", 3.0, "garmin")]


def test_nothing_reads_or_writes_the_retired_column():
    """`daily_records.session_rpe` is written by nothing and read by nothing: outside the model, the migrations and
    the tests, no module has an attribute access, a keyword, a dict key or a SQL statement naming it. Docstrings
    and comments (which explain the retirement) are ignored: the check is on the AST."""
    import ast
    import re
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent
    offenders = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith(("tests/", "migrations/", ".venv/")) or "/site-packages/" in rel or rel == "models.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                      and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for n in ast.walk(tree):
            hit = (
                (isinstance(n, ast.Attribute) and n.attr == "session_rpe")
                or (isinstance(n, ast.keyword) and n.arg == "session_rpe")
                or (isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
                    and (n.value == "session_rpe"
                         or (re.search(r"\bsession_rpe\b", n.value) and re.search(r"\b(select|insert|update|from)\b", n.value, re.I))))
            )
            if hit:
                offenders.append(f"{rel}:{getattr(n, 'lineno', '?')}")
    assert offenders == [], offenders
