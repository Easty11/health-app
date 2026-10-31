"""Q140 / Q171 / Q136: the operator-local (AEST) day is the day, not the UTC date.

AEST = UTC+10, no DST. At 07:00 AEST on 2026-10-31 the UTC instant is 21:00 on 2026-10-30, so a
naive UTC `date.today()` / `datetime.now(utc).date()` is one day behind the operator's day. Each
test freezes the clock at exactly that instant and asserts the AEST date wins.
"""
from __future__ import annotations

import datetime as dt
from datetime import date

import pytest
import time_machine
from sqlalchemy.dialects import postgresql

import mcp_server
import models
from injury_trajectory import evaluate
from routers.knowledge import expire_stale_entries

# 07:00 AEST on Sat 2026-10-31 == 21:00Z on Fri 2026-10-30.
SEVEN_AM_AEST = dt.datetime(2026, 10, 30, 21, 0, tzinfo=dt.timezone.utc)
AEST_DAY = date(2026, 10, 31)
UTC_DAY = date(2026, 10, 30)


def _user(db):
    u = models.User(email="skew@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── Q140: expire_stale_entries ────────────────────────────────────────────────────

def test_expire_stale_entries_uses_the_aest_day(db_session):
    u = _user(db_session)
    # Expired on the AEST calendar (expires_at < 2026-10-31) but NOT on the UTC calendar
    # (expires_at == 2026-10-30 is not < 2026-10-30): the skew window.
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="preference", key="lapsed", value={}, source="chat", expires_at=UTC_DAY))
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="preference", key="still_live", value={}, source="chat", expires_at=AEST_DAY))
    db_session.commit()

    with time_machine.travel(SEVEN_AM_AEST, tick=False):
        assert expire_stale_entries(u.id, db_session) == 1

    active = {e.key: e.active for e in db_session.query(models.UserKnowledgeEntry).all()}
    assert active == {"lapsed": False, "still_live": True}


# ── Q140: injury_trajectory.evaluate fallback ─────────────────────────────────────

def test_evaluate_fallback_today_is_the_aest_day(db_session):
    u = _user(db_session)
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key="inj", source="chat",
        value={"body_part": "calf", "side": "left",
               "trajectory": {"shape": "resolving_by", "resolve_by": UTC_DAY.isoformat()}}))
    db_session.commit()

    # resolve_by == the UTC date: "overdue" only once the day is 2026-10-31, which at
    # 07:00 AEST it already is. A UTC fallback (2026-10-30) would not flag it.
    with time_machine.travel(SEVEN_AM_AEST, tick=False):
        out = evaluate(u.id, db_session)
    assert [d["key"] for d in out["divergences"]] == ["calf_left"]


# ── Q171: MCP session windows ─────────────────────────────────────────────────────

@pytest.fixture
def mcp_world(db_session, monkeypatch):
    u = _user(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [])
    seen: list[date] = []

    def spy(user_id, db, *, since=None, limit=None):
        seen.append(since)
        return []

    monkeypatch.setattr(mcp_server, "arbitrated_sessions", spy)
    return seen


def test_get_training_sessions_window_is_keyed_on_the_aest_day(mcp_world):
    with time_machine.travel(SEVEN_AM_AEST, tick=False):
        mcp_server.get_training_sessions(days=28)
    assert mcp_world[0] == date(2026, 10, 3)        # AEST 10-31 minus 28, not UTC 10-30 minus 28


def test_readiness_snapshot_seven_day_window_is_keyed_on_the_aest_day(mcp_world):
    with time_machine.travel(SEVEN_AM_AEST, tick=False):
        mcp_server.get_readiness_snapshot()
    assert date(2026, 10, 24) in mcp_world           # AEST 10-31 minus 7, not UTC 10-30 minus 7
    assert date(2026, 10, 23) not in mcp_world


# ── Q136: model constraint agrees with the live schema; the sync upsert runs on SQLite ──

def test_samsung_hrv_model_unique_constraint_is_the_live_three_column_key():
    uqs = [c for c in models.SamsungHRVReading.__table__.constraints
           if c.__class__.__name__ == "UniqueConstraint"]
    assert [(c.name, [col.name for col in c.columns]) for c in uqs] == [
        ("uq_samsung_hrv_user_date_context", ["user_id", "captured_at", "context"])]


def test_samsung_sync_upserts_per_night_and_context_on_sqlite(db_session):
    """The `/samsung-hrv/sync` DB path now runs on the test substrate, and the substrate agrees
    with prod on how many rows a (user, night) holds: one per context, updated in place."""
    from routers.samsung_hrv import HRVReadingIn, SyncRequest, sync_readings

    u = _user(db_session)
    night = date(2026, 10, 30)

    def sync(**kw):
        return sync_readings(
            SyncRequest(readings=[HRVReadingIn(captured_at=night, **kw)]), db=db_session, current_user=u)

    assert sync(hrv_ms=60.0) == {"synced": 1}
    sync(hrv_ms=64.0)                                   # same night + context: updates in place
    sync(hrv_ms=41.0, context="calibration")             # same night, other context: a second row

    rows = {r.context: r.hrv_ms for r in db_session.query(models.SamsungHRVReading).filter_by(user_id=u.id)}
    assert rows == {"passive_overnight": 64.0, "calibration": 41.0}
