"""`scripts.garmin_verify` -- the read-only stored-vs-app HRV check used to verify the Garmin fix."""
import io
from contextlib import redirect_stdout
from datetime import date

import pytest
from sqlalchemy import event

import database
import models
from scripts import garmin_verify as gv


@pytest.fixture()
def db(db_session):
    for uid in (1, 4):
        db_session.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db_session.flush()
    for uid, night, v in ((1, "2026-09-27", 39.0), (4, "2026-09-27", 31.0),
                          (1, "2026-09-28", 50.0), (4, "2026-09-28", 50.0)):
        db_session.add(models.HrvReading(user_id=uid, captured_at=date.fromisoformat(night), source="garmin", rmssd_ms=v))
    db_session.commit()
    return db_session


def _run(db, monkeypatch, *argv):
    monkeypatch.setattr(database, "engine", db.get_bind())
    out = io.StringIO()
    with redirect_stdout(out):
        rc = gv.main(list(argv))
    return rc, out.getvalue()


def test_matching_values_pass_and_the_run_is_read_only(db, monkeypatch):
    stmts: list[str] = []
    event.listen(db.get_bind(), "before_cursor_execute", lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    rc, out = _run(db, monkeypatch, "--night", "2026-09-27", "--expect", "1=39", "4=31")
    assert rc == 0 and "RESULT: ALL PASS" in out
    assert "user 1: expected 39 ms  stored: 39 ms  PASS" in out and "user 4: expected 31 ms  stored: 31 ms  PASS" in out
    assert all(s.startswith("SELECT") for s in stmts) and out.isascii()


def test_a_wrong_value_fails(db, monkeypatch):
    rc, out = _run(db, monkeypatch, "--night", "2026-09-27", "--expect", "1=39", "4=39")   # the mix-up value
    assert rc == 1 and "user 4: expected 39 ms  stored: 31 ms  FAIL" in out and "RESULT: FAIL" in out


def test_a_missing_reading_is_a_fail_not_a_silent_pass(db, monkeypatch):
    rc, out = _run(db, monkeypatch, "--night", "2026-09-01", "--expect", "4=31")
    assert rc == 1 and "NO READING  FAIL" in out


def test_tolerance_absorbs_app_rounding(db, monkeypatch):
    db.execute(models.HrvReading.__table__.update().where(models.HrvReading.user_id == 4).values(rmssd_ms=31.4))
    db.commit()
    assert _run(db, monkeypatch, "--night", "2026-09-27", "--expect", "4=31")[0] == 0
    assert _run(db, monkeypatch, "--night", "2026-09-27", "--expect", "4=31", "--tolerance", "0.1")[0] == 1


def test_identical_nights_are_reported_as_a_copy_signature(db, monkeypatch):
    _, out = _run(db, monkeypatch, "--night", "2026-09-27", "--expect", "1=39", "4=31")
    assert "users 1 and 4 hold an IDENTICAL garmin value: 1  (a copy signature" in out       # 2026-09-28


def test_bad_arguments_are_refused(db, monkeypatch):
    assert _run(db, monkeypatch, "--night", "2026-09-27", "--expect", "one=39")[0] == 2
    assert _run(db, monkeypatch, "--night", "not-a-date", "--expect", "1=39")[0] == 2
