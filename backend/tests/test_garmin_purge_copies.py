"""`scripts.garmin_purge_copies` -- classes A/B/C, the class B flag, and the guards.

FK-enforced SQLite (conftest), so the sample cascades and the unique keys are real. Every
protected-row claim is asserted by reading the DB afterwards, not by trusting the script's own
report (FEEDBACK section 17: a control must discriminate on the artefact, not on the message).
"""
import io
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import event, text

import database
import models
from scripts import garmin_purge_copies as gp

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
SECRET = "gAAAA-garmin-credential-recognisable"


def _reading(db, uid, night, value, *, source="garmin", samples=2):
    r = models.HrvReading(user_id=uid, captured_at=date.fromisoformat(night), source=source, rmssd_ms=value)
    db.add(r)
    db.flush()
    for i in range(samples):
        db.add(models.HrvSample(hrv_reading_id=r.id, reading_time=NOW.replace(minute=i), rmssd_ms=(value or 0) + i))
    db.commit()
    return r.id


@pytest.fixture()
def world(db_session):
    """Owner 1; wrong user 4 with A (3 copies), B (2 rows the owner lacks, one with NO rmssd); user 5 bystander."""
    db = db_session
    for uid in (1, 4, 5):
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.flush()
    for uid, prov in ((1, "garmin"), (1, "hevy"), (4, "garmin"), (4, "hevy"), (5, "garmin")):
        db.add(models.UserIntegration(user_id=uid, provider=prov, api_key_encrypted=SECRET))
    db.commit()
    for n, v in (("2026-09-10", 50.0), ("2026-09-11", 51.0), ("2026-09-12", 52.0), ("2026-09-13", 53.0)):
        _reading(db, 1, n, v)                                   # owner's real nights
    _reading(db, 1, "2026-09-12", 41.0, source="samsung", samples=0)
    for n, v in (("2026-09-10", 50.0), ("2026-09-11", 51.0), ("2026-09-12", 52.0)):
        _reading(db, 4, n, v)                                   # class A: identical copies
    _reading(db, 4, "2026-08-30", 44.0)                         # class B
    _reading(db, 4, "2026-09-04", None, samples=0)              # class B, empty (the connect-day row)
    _reading(db, 4, "2026-09-12", 60.0, source="samsung", samples=0)   # wrong user's other source
    _reading(db, 5, "2026-09-10", 70.0)                         # bystander
    return db


def _e(db):
    return db.get_bind()


def _n(db, sql, **p):
    return db.execute(text(sql), p).scalar_one()


def _plan(db, wrong=4, owner=1):
    with _e(db).connect() as c:
        return gp.build_plan(c, wrong, owner)


def _dry(db, monkeypatch, *args):
    monkeypatch.setattr(database, "engine", _e(db))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = gp.main(["--wrong-user", "4", "--owner", "1", *args])
    return rc, out.getvalue(), err.getvalue()


def _owner_state(db):
    return (_n(db, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 1"),
            _n(db, "SELECT COALESCE(SUM(rmssd_ms),0) FROM hrv_readings WHERE user_id = 1"),
            _n(db, "SELECT COUNT(*) FROM hrv_samples s JOIN hrv_readings r ON r.id = s.hrv_reading_id WHERE r.user_id = 1"),
            _n(db, "SELECT COUNT(*) FROM user_integrations WHERE user_id = 1"))


# -- classification and the dry run ---------------------------------------------------------

def test_rows_are_sorted_into_the_three_classes(world):
    world.add(models.HrvReading(user_id=4, captured_at=date(2026, 9, 13), source="garmin", rmssd_ms=99.0))  # owner has 53
    world.commit()
    plan = _plan(world)
    assert [r.night for r in plan.of("A")] == ["2026-09-10", "2026-09-11", "2026-09-12"]
    assert [r.night for r in plan.of("B")] == ["2026-08-30", "2026-09-04"]
    assert [r.night for r in plan.of("C")] == ["2026-09-13"]


def test_a_missing_value_on_a_night_the_owner_has_is_class_c_not_a_copy(world):
    world.add(models.HrvReading(user_id=4, captured_at=date(2026, 9, 13), source="garmin", rmssd_ms=None))
    world.commit()
    assert [r.night for r in _plan(world).of("C")] == ["2026-09-13"]


def test_dry_run_lists_every_row_offers_both_commands_and_changes_nothing(world, monkeypatch):
    before = {t: _n(world, f"SELECT COUNT(*) FROM {t}") for t in ("hrv_readings", "hrv_samples", "user_integrations")}
    stmts: list[str] = []
    event.listen(_e(world), "before_cursor_execute", lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    rc, out, err = _dry(world, monkeypatch)
    assert rc == 0, err
    assert stmts and all(s.startswith("SELECT") for s in stmts), stmts
    for night in ("2026-08-30", "2026-09-04", "2026-09-10", "2026-09-12"):
        assert night in out
    assert "A (copies, purge) 3" in out and "B (owner has no row) 2" in out and "C (values differ) 0" in out
    assert "No class C rows." in out and "never touched by --execute" in out.replace("NEVER", "never")
    plan = _plan(world)
    assert f"--execute --confirm {plan.token_a}" in out
    assert f"--execute --reassign-b --confirm {plan.token_b}" in out and plan.token_a != plan.token_b
    assert "non-garmin hrv_readings (NOT touched): samsung=1" in out
    assert {t: _n(world, f"SELECT COUNT(*) FROM {t}") for t in before} == before


def test_report_is_ascii_and_never_carries_the_credential(world, monkeypatch):
    _, out, _ = _dry(world, monkeypatch)
    assert out.isascii() and SECRET not in out and "gAAAA" not in out


def test_frozen_daily_record_copies_are_reported_not_touched(world, monkeypatch):
    world.add(models.DailyRecord(user_id=4, date=date(2026, 9, 11), passive_hrv_ms=51.0))
    world.add(models.DailyRecord(user_id=4, date=date(2026, 9, 12), passive_hrv_ms=33.0))
    world.commit()
    _, out, _ = _dry(world, monkeypatch)
    assert "daily_records with passive_hrv_ms set: 2, of which 1 equal user 1's reading" in out
    ru = gp.execute_purge(_e(world), 4, 1, _plan(world).token_a)
    assert ru.mode == "purge-A"
    assert _n(world, "SELECT COUNT(*) FROM daily_records WHERE user_id = 4") == 2


# -- class A execute ------------------------------------------------------------------------

def test_execute_purges_class_a_and_disconnects_and_touches_nothing_else(world):
    owner_before = _owner_state(world)
    bystander = _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 5")
    res = gp.execute_purge(_e(world), 4, 1, _plan(world).token_a)
    world.expire_all()
    assert (res.integrations_deleted, res.readings_deleted, res.samples_deleted) == (1, 3, 6)
    assert _n(world, "SELECT COUNT(*) FROM user_integrations WHERE user_id = 4 AND provider = 'garmin'") == 0
    assert _n(world, "SELECT COUNT(*) FROM user_integrations WHERE user_id = 4 AND provider = 'hevy'") == 1
    assert [str(r[0]) for r in world.execute(text(
        "SELECT captured_at FROM hrv_readings WHERE user_id = 4 AND source = 'garmin' ORDER BY captured_at"))] \
        == ["2026-08-30", "2026-09-04"]                                    # class B untouched
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'samsung'") == 1
    assert _n(world, "SELECT COUNT(*) FROM hrv_samples s JOIN hrv_readings r ON r.id = s.hrv_reading_id"
                     " WHERE r.user_id = 4 AND r.captured_at = '2026-08-30'") == 2   # B's samples survived
    assert _owner_state(world) == owner_before
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 5") == bystander


def test_execute_needs_the_right_token_for_the_right_mode(world):
    plan = _plan(world)
    for tok in (None, "", "000000000000", plan.token_b):                   # token_b is not a purge token
        with pytest.raises(gp.Refused):
            gp.execute_purge(_e(world), 4, 1, tok)
    with pytest.raises(gp.Refused):
        gp.execute_purge(_e(world), 4, 1, plan.token_a, reassign_b=True)   # token_a is not a reassign token
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'garmin'") == 5


def test_a_change_after_the_dry_run_invalidates_the_token(world):
    tok = _plan(world).token_a
    _reading(world, 4, "2026-09-13", 53.0)          # a sweep adds a night between dry run and execute
    with pytest.raises(gp.Refused, match="does not match"):
        gp.execute_purge(_e(world), 4, 1, tok)


def test_class_c_halts_every_execute_and_offers_no_command(world, monkeypatch):
    world.add(models.HrvReading(user_id=4, captured_at=date(2026, 9, 13), source="garmin", rmssd_ms=99.0))
    world.commit()
    plan = _plan(world)
    _, out, _ = _dry(world, monkeypatch)
    assert "HALT: 1 class C row(s)" in out and "No execute command is offered while class C exists." in out
    assert "--confirm" not in out.split("DRY RUN")[1]
    with pytest.raises(gp.Refused, match="HALT"):
        gp.execute_purge(_e(world), 4, 1, plan.token_a)
    with pytest.raises(gp.Refused, match="HALT"):
        gp.execute_purge(_e(world), 4, 1, plan.token_b, reassign_b=True)
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'garmin'") == 6


def test_a_broken_invariant_rolls_the_whole_purge_back(world, monkeypatch):
    tok = _plan(world).token_a
    samples_before = _n(world, "SELECT COUNT(*) FROM hrv_samples")
    real, calls = gp._snapshot, {"n": 0}

    def skewed(conn, wrong, owner):
        snap = real(conn, wrong, owner)
        calls["n"] += 1
        if calls["n"] == 2:                                                # the AFTER snapshot
            snap["owner_readings"] += 1
        return snap

    monkeypatch.setattr(gp, "_snapshot", skewed)
    with pytest.raises(gp.InvariantError):
        gp.execute_purge(_e(world), 4, 1, tok)
    world.expire_all()
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'garmin'") == 5
    assert _n(world, "SELECT COUNT(*) FROM user_integrations WHERE user_id = 4 AND provider = 'garmin'") == 1
    assert _n(world, "SELECT COUNT(*) FROM hrv_samples") == samples_before > 0


# -- class B reassignment --------------------------------------------------------------------

def test_class_b_is_never_reassigned_by_a_plain_execute(world):
    gp.execute_purge(_e(world), 4, 1, _plan(world).token_a)
    world.expire_all()
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 1 AND captured_at IN ('2026-08-30','2026-09-04')") == 0


def test_reassign_b_moves_exactly_the_class_b_rows_and_their_samples_to_the_owner(world):
    gp.execute_purge(_e(world), 4, 1, _plan(world).token_a)                 # class A first
    world.expire_all()
    owner_before = _owner_state(world)
    res = gp.execute_purge(_e(world), 4, 1, _plan(world).token_b, reassign_b=True)   # fresh token: rows changed
    world.expire_all()
    assert res.mode == "reassign-B" and res.readings_reassigned == 2
    o_read, o_sum, o_samp, o_int = _owner_state(world)
    assert (o_read, o_samp, o_int) == (owner_before[0] + 2, owner_before[2] + 2, owner_before[3])
    assert o_sum == pytest.approx(owner_before[1] + 44.0)                   # the empty row adds nothing
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'garmin'") == 0
    assert _n(world, "SELECT COUNT(*) FROM hrv_samples s JOIN hrv_readings r ON r.id = s.hrv_reading_id"
                     " WHERE r.user_id = 1 AND r.captured_at = '2026-08-30'") == 2   # samples travelled
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'samsung'") == 1


def test_reassign_b_broken_invariant_rolls_back(world, monkeypatch):
    gp.execute_purge(_e(world), 4, 1, _plan(world).token_a)
    tok = _plan(world).token_b
    real, calls = gp._snapshot, {"n": 0}

    def skewed(conn, wrong, owner):
        snap = real(conn, wrong, owner)
        calls["n"] += 1
        if calls["n"] == 2:
            snap["owner_non_garmin"] += 1                                  # something ELSE changed
        return snap

    monkeypatch.setattr(gp, "_snapshot", skewed)
    with pytest.raises(gp.InvariantError):
        gp.execute_purge(_e(world), 4, 1, tok, reassign_b=True)
    world.expire_all()
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 4 AND source = 'garmin'") == 2
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 1 AND captured_at = '2026-08-30'") == 0


def test_reassign_b_with_no_class_b_rows_is_refused(world):
    gp.execute_purge(_e(world), 4, 1, _plan(world).token_a)
    gp.execute_purge(_e(world), 4, 1, _plan(world).token_b, reassign_b=True)
    with pytest.raises(gp.Refused, match="no class B"):
        gp.execute_purge(_e(world), 4, 1, _plan(world).token_b, reassign_b=True)


# -- guards ---------------------------------------------------------------------------------

def test_user_1_can_never_be_the_wrong_user_and_the_pair_must_differ(world, monkeypatch):
    monkeypatch.setattr(database, "engine", _e(world))
    with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
        assert gp.main(["--wrong-user", "1", "--owner", "4"]) == 2
        assert gp.main(["--wrong-user", "1", "--owner", "4", "--execute", "--confirm", "x"]) == 2
        assert gp.main(["--wrong-user", "4", "--owner", "4"]) == 2
    with pytest.raises(gp.Refused):
        gp.execute_purge(_e(world), 1, 4, "x")
    with _e(world).connect() as c, pytest.raises(gp.Refused):
        gp.build_plan(c, 1, 4)
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE user_id = 1 AND source = 'garmin'") == 4


def test_a_non_garmin_source_is_refused_at_the_api(world):
    with _e(world).connect() as c, pytest.raises(gp.Refused, match="only source 'garmin'"):
        gp.build_plan(c, 4, 1, source="samsung")
    with pytest.raises(gp.Refused, match="only source 'garmin'"):
        gp.execute_purge(_e(world), 4, 1, "x", source="samsung")
    assert _n(world, "SELECT COUNT(*) FROM hrv_readings WHERE source = 'samsung'") == 2


def test_unknown_user_is_refused(world):
    with _e(world).connect() as c, pytest.raises(gp.Refused, match="no user with id 99"):
        gp.build_plan(c, 99, 1)


def test_cli_rejects_confirm_or_reassign_without_execute(world, monkeypatch):
    monkeypatch.setattr(database, "engine", _e(world))
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        gp.main(["--wrong-user", "4", "--owner", "1", "--reassign-b"])


def test_cli_execute_prints_the_outcome(world, monkeypatch):
    rc, out, err = _dry(world, monkeypatch, "--execute", "--confirm", _plan(world).token_a)
    assert rc == 0, err
    assert "EXECUTED (committed)" in out and "3 class A readings" in out and out.isascii()
