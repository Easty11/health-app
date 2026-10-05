"""Pin: a zero-length phase row (`closed_on == entered_on`) is never read as the phase in force (#379 item 4).

A same-day correction closes the row it replaces on the day that row was entered, so the ledger
holds rows that never covered a day (#317 ruled this; #379 keeps appending). The readers must not
see them: `phase_at` answers over the half-open interval `entered_on <= d < closed_on`, which is
empty for such a row, and every open-phase reader goes through `current_training_phase`, whose
filter is `closed_on IS NULL`. Nothing here changes behaviour; it makes the exclusion fail loudly
if a refactor ever loosens either bound.

Rows are written through `_apply_open_phase` (the core the transition shares), not `open_phase`, so
this file does not depend on the direct-open wrapper.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

import current_state as current_state_mod
import models
from auth import get_current_user
from database import get_db
from engine import profile as profile_mod
from engine import resolver as resolver_mod
from engine import training_phase as phase_mod
from load_metrics import _local_day
from routers import engine as engine_router
from routers import training_phase as phase_router


def _user(db, email="zero-length-pin@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


_MICROCYCLE = {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": [
    {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]}]}


def _open(db, uid, label, entered_on, microcycle=None):
    """Open a phase through the shared core (closes the open row at `entered_on`) and commit."""
    payload = {
        "label": label, "probe_posture": "held", "entered_on": str(entered_on),
        "asserted_by": "user", "asserted_on": str(entered_on), "source": "api",
    }
    if microcycle is not None:
        payload["microcycle"] = microcycle
    phase = phase_mod._apply_open_phase(db, uid, payload)
    db.commit()
    db.refresh(phase)
    return phase


def _is_zero_length(row):
    return row.closed_on is not None and row.closed_on == row.entered_on


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(phase_router.router)
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


D = date(2026, 9, 7)


# ── phase_at ─────────────────────────────────────────────────────────────────

def test_phase_at_skips_zero_length_rows_with_a_same_day_successor(db_session):
    u = _user(db_session)
    a = _open(db_session, u.id, "a", D)
    b = _open(db_session, u.id, "b", D)       # same-day correction: a is now D -> D
    c = _open(db_session, u.id, "c", D)       # and again: b is now D -> D
    for row in (a, b):
        db_session.refresh(row)
        assert _is_zero_length(row)           # the fixture really holds zero-length rows

    # d == entered_on == closed_on, with a successor on the same day: the successor, never a or b.
    assert phase_mod.phase_at(db_session, u.id, D).id == c.id
    assert phase_mod.phase_at(db_session, u.id, D + timedelta(days=1)).id == c.id
    assert phase_mod.phase_at(db_session, u.id, D - timedelta(days=1)) is None


def test_phase_at_returns_nothing_on_the_day_of_a_same_day_baseline_close(db_session):
    """Opened and closed to baseline on the same day: no successor, so the day has no phase."""
    u = _user(db_session)
    today = _local_day()
    only = _open(db_session, u.id, "oops", today)
    phase_mod.close_phase(db_session, u.id, "opened by mistake")
    db_session.refresh(only)
    assert _is_zero_length(only)

    assert phase_mod.phase_at(db_session, u.id, today) is None
    assert phase_mod.phase_at(db_session, u.id, today - timedelta(days=1)) is None


def test_phase_at_never_returns_a_zero_length_row_across_a_mixed_ledger(db_session):
    """Sweep every day over a ledger that interleaves real blocks with zero-length corrections."""
    u = _user(db_session)
    p1 = _open(db_session, u.id, "p1", date(2026, 9, 1))
    p2 = _open(db_session, u.id, "p2", date(2026, 9, 7))    # closes p1 (6 days); p2 -> zero-length
    p3 = _open(db_session, u.id, "p3", date(2026, 9, 7))    # correction: closes p2 same day
    p4 = _open(db_session, u.id, "p4", date(2026, 9, 10))   # closes p3 (3 days); p4 -> zero-length
    p5 = _open(db_session, u.id, "p5", date(2026, 9, 10))   # correction: closes p4 same day
    rows = {r.id: r for r in db_session.query(models.TrainingPhase).filter_by(user_id=u.id)}
    assert {r.label for r in rows.values() if _is_zero_length(r)} == {"p2", "p4"}

    expected = {
        date(2026, 8, 31): None,
        date(2026, 9, 1): p1.id, date(2026, 9, 6): p1.id,
        date(2026, 9, 7): p3.id, date(2026, 9, 9): p3.id,
        date(2026, 9, 10): p5.id, date(2026, 9, 20): p5.id,
    }
    d = date(2026, 8, 25)
    while d <= date(2026, 9, 25):
        got = phase_mod.phase_at(db_session, u.id, d)
        assert got is None or not _is_zero_length(got), f"{d}: returned zero-length row {got.label}"
        if d in expected:
            assert (got.id if got else None) == expected[d], d
        d += timedelta(days=1)


# ── current_training_phase ───────────────────────────────────────────────────

def test_current_training_phase_is_the_open_row_not_a_zero_length_one(db_session):
    u = _user(db_session)
    a = _open(db_session, u.id, "a", D)
    b = _open(db_session, u.id, "b", D)
    db_session.refresh(a)
    assert _is_zero_length(a)
    assert phase_mod.current_training_phase(db_session, u.id).id == b.id


def test_current_training_phase_is_none_when_only_zero_length_rows_remain(db_session):
    u = _user(db_session)
    today = _local_day()
    _open(db_session, u.id, "oops", today)
    phase_mod.close_phase(db_session, u.id, "opened by mistake")
    assert phase_mod.current_training_phase(db_session, u.id) is None


def test_current_training_phase_filters_on_closed_not_on_ordering(db_session):
    """A closed zero-length row that sorts FIRST (same entered_on, higher id) is still not returned:
    the exclusion is the `closed_on IS NULL` filter, not luck in the ORDER BY."""
    u = _user(db_session)
    open_row = _open(db_session, u.id, "open", D)
    stray = models.TrainingPhase(
        user_id=u.id, label="stray", probe_posture="held", entered_on=D, closed_on=D,
        close_reason="stray", asserted_by="user", asserted_on=D, source="api",
    )
    db_session.add(stray)
    db_session.commit()
    assert stray.id > open_row.id and _is_zero_length(stray)

    assert phase_mod.current_training_phase(db_session, u.id).id == open_row.id


# ── the other open-phase readers (all route through current_training_phase) ──

def _only_zero_length_rows(db, u):
    today = _local_day()
    # Each row carries a microcycle, so a leak into the resolver would surface as a phase window.
    _open(db, u.id, "a", today, _MICROCYCLE)
    _open(db, u.id, "b", today, _MICROCYCLE)   # a: zero-length
    phase_mod.close_phase(db, u.id, "ended")   # b: zero-length, no successor
    rows = db.query(models.TrainingPhase).filter_by(user_id=u.id).all()
    assert len(rows) == 2 and all(_is_zero_length(r) for r in rows)


def test_every_open_phase_reader_sees_baseline_when_only_zero_length_rows_exist(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    _only_zero_length_rows(db_session, u)
    c = _client(db_session, u)
    today = _local_day()

    # GET /engine/phase
    assert c.get("/engine/phase").json()["training_phase"] is None
    # /engine/phase/transition/draft (the wizard's read)
    draft = c.get("/engine/phase/transition/draft").json()
    assert draft["current_phase"] is None and draft["outgoing_review"] == []
    # /engine/next injects no training_phase block
    assert "training_phase" not in c.get("/engine/next").json()
    # resolver: never a phase-sourced window (the weekly template governs, or nothing does)
    window = resolver_mod.resolve_window(db_session, u.id, today)
    assert window is None or window.source != "phase"
    # current_state (feeds chat context and the HRV settling date)
    assert current_state_mod.current_state(u.id, db_session, today).training_phase is None


def test_the_readers_see_the_open_successor_and_history_hides_nothing(db_session):
    u = _user(db_session)
    a = _open(db_session, u.id, "a", D)
    b = _open(db_session, u.id, "b", D)
    c = _client(db_session, u)

    assert c.get("/engine/phase").json()["training_phase"]["id"] == b.id
    # Append-only stays visible: the zero-length row is still in the ledger.
    hist = c.get("/engine/phase/history").json()["history"]
    assert {r["id"] for r in hist} == {a.id, b.id}


def test_only_two_engine_functions_query_the_phase_table():
    """Tripwire on the pin's own coverage: `phase_at` and `current_training_phase` are the only
    engine functions that query `TrainingPhase` for a day or the open row. A third reader must be
    added to this file, so this count fails when one appears."""
    import inspect
    assert inspect.getsource(phase_mod).count("db.query(models.TrainingPhase)") == 2
