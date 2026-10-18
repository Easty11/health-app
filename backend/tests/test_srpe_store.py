"""`srpe_store` -- the source-neutral per-session RPE store: the contract, the one writer, the scale declarations.

The contract is tested at the writer (a refused write inserts nothing), and the "nothing else writes" rule by
reading the tree, so a second writer fails here rather than by drift.
"""
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

import models
import srpe_store as ss

T0 = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)
START = datetime(2026, 10, 3, 21, 30, tzinfo=timezone.utc)
STOP = START + timedelta(minutes=45)


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.commit()


def _rec(db, ref="11", raw=40, scale="garmin_0_100", uid=1, now=T0, **kw):
    _user(db, uid)
    return ss.record_observation(db, uid, source="garmin", source_activity_ref=ref, start=START, stop=STOP,
                                 rpe_raw=raw, raw_scale=scale, now=now, **kw)


def _rows(db):
    return db.query(models.SessionRpeObservation).order_by(models.SessionRpeObservation.id).all()


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# -- the scale: the writer converts on the adapter's declared scale ---------------------------------------

@pytest.mark.parametrize("raw,expected", [(40, 4.0), (70, 7.0), (100, 10.0), (0, 0.0), (45, 4.5), (40.0, 4.0)])
def test_the_writer_converts_a_declared_garmin_value_to_cr10(db_session, raw, expected):
    r = _rec(db_session, raw=raw)
    assert (r.rpe_raw, r.raw_scale, r.rpe_cr10) == (float(raw), "garmin_0_100", expected)


def test_a_write_stores_the_window_in_utc_the_feel_and_the_provenance(db_session):
    r = _rec(db_session, feel=25, provenance={"garmin_type": "strength_training"})
    assert (r.source, r.source_activity_ref, r.feel) == ("garmin", "11", 25)
    assert _aware(r.start_time) == START and _aware(r.stop_time) == STOP
    assert r.provenance == {"garmin_type": "strength_training"}


def test_an_activity_ref_is_stored_as_text_whatever_the_source_sent(db_session):
    assert _rec(db_session, ref=24564069469).source_activity_ref == "24564069469"


def test_a_naive_window_is_read_as_utc(db_session):
    _user(db_session)
    r = ss.record_observation(db_session, 1, source="garmin", source_activity_ref="1", start=START.replace(tzinfo=None),
                              stop=None, rpe_raw=40, raw_scale="garmin_0_100", now=T0)
    assert _aware(r.start_time) == START and r.stop_time is None


def test_an_unrated_sighting_is_a_row_with_no_value(db_session):
    r = _rec(db_session, raw=None)
    assert (r.rpe_raw, r.rpe_cr10, r.raw_scale) == (None, None, "garmin_0_100")


# -- fail closed: what the contract refuses, and that a refusal inserts nothing -----------------------------

@pytest.mark.parametrize("scale", ["cr10", "garmin_0_10", "", "GARMIN_0_100", None])
def test_a_scale_the_adapter_did_not_declare_is_refused(db_session, scale):
    with pytest.raises(ss.UnknownScale):
        _rec(db_session, scale=scale)
    assert _rows(db_session) == []


def test_an_unrated_sighting_still_needs_a_declared_scale(db_session):
    with pytest.raises(ss.UnknownScale):
        _rec(db_session, raw=None, scale="mystery")
    assert _rows(db_session) == []


@pytest.mark.parametrize("source", ["in_app", "strava", "", "Garmin"])
def test_a_source_that_has_declared_nothing_is_refused(db_session, source):
    """`in_app` is in the hierarchy but has no writer yet: its first write is refused until it signs."""
    _user(db_session)
    with pytest.raises(ss.UnknownSource):
        ss.record_observation(db_session, 1, source=source, source_activity_ref="1", start=START, stop=STOP,
                              rpe_raw=5, raw_scale="cr10", now=T0)
    assert _rows(db_session) == []


@pytest.mark.parametrize("bad", [-1, 101, 1000, "40", True, [], math.nan, math.inf])
def test_an_unusable_raw_value_is_refused_not_stored_as_unrated(db_session, bad):
    with pytest.raises(ss.SRPEContractError):
        _rec(db_session, raw=bad)
    assert _rows(db_session) == []


def test_a_window_with_no_start_or_a_backwards_stop_is_refused(db_session):
    _user(db_session)
    with pytest.raises(ss.SRPEContractError):
        ss.record_observation(db_session, 1, source="garmin", source_activity_ref="1", start=None, stop=None,
                              rpe_raw=40, raw_scale="garmin_0_100", now=T0)
    with pytest.raises(ss.SRPEContractError):
        ss.record_observation(db_session, 1, source="garmin", source_activity_ref="1", start=START, stop=START,
                              rpe_raw=40, raw_scale="garmin_0_100", now=T0)
    assert _rows(db_session) == []


def test_every_declared_scale_converts_its_own_range_into_zero_to_ten():
    for source, scales in ss.SOURCE_SCALES.items():
        for scale in scales.values():
            assert scale.to_cr10(scale.lo) == 0.0, (source, scale.name)
            assert scale.to_cr10(scale.hi) == 10.0, (source, scale.name)


# -- insert-only, capture-timed ------------------------------------------------------------------------------

def test_a_new_row_never_reuses_an_earlier_capture_time(db_session):
    """The same clock reading twice would collide on the unique key; the later row is placed strictly after."""
    a = _rec(db_session, raw=40)
    b = _rec(db_session, raw=60)
    assert _aware(b.captured_at) > _aware(a.captured_at)
    assert [r.rpe_cr10 for r in _rows(db_session)] == [4.0, 6.0]


def test_the_unique_key_is_per_user_source_activity_and_capture_time(db_session):
    _rec(db_session, ref="11")
    _rec(db_session, ref="12")                                 # another activity, same instant: fine
    _rec(db_session, ref="11", uid=2)                          # another user, same instant: fine
    db_session.add(models.SessionRpeObservation(
        user_id=1, source="garmin", source_activity_ref="11", start_time=START, raw_scale="garmin_0_100",
        captured_at=T0, provenance={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_no_update_or_delete_is_ever_issued_against_the_store(db_session):
    _user(db_session)
    stmts: list[str] = []
    event.listen(db_session.get_bind(), "before_cursor_execute",
                 lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    _rec(db_session, raw=None)
    _rec(db_session, raw=40, now=T0 + timedelta(days=1))
    _rec(db_session, raw=40, now=T0)                           # a clock that went backwards
    touching = [s for s in stmts if "SESSION_RPE_OBSERVATIONS" in s]
    assert touching and not [s for s in touching if s.startswith(("UPDATE", "DELETE"))], touching


def test_the_latest_row_per_activity_is_its_current_value_and_unrated_is_a_value(db_session):
    _rec(db_session, ref="11", raw=40, now=T0)
    _rec(db_session, ref="11", raw=60, now=T0 + timedelta(days=1))
    _rec(db_session, ref="12", raw=50, now=T0)
    _rec(db_session, ref="12", raw=None, now=T0 + timedelta(days=1))   # un-rated later: the current value is "none"
    _rec(db_session, ref="13", raw=80, uid=2)
    cur = ss.latest_by_activity(db_session, 1)
    assert {k: v.rpe_cr10 for k, v in cur.items()} == {("garmin", "11"): 6.0, ("garmin", "12"): None}
    assert set(ss.latest_by_activity(db_session, 2)) == {("garmin", "13")}
    assert set(ss.latest_by_activity(db_session, 1, "strava")) == set()


# -- nothing else writes ---------------------------------------------------------------------------------------

def test_the_writer_is_the_only_code_that_constructs_or_inserts_an_observation():
    """`record_observation` is the one writer. A second constructor, or a raw INSERT, anywhere in the backend
    (tests and the one-off migration copy excepted) fails here."""
    backend = Path(__file__).resolve().parent.parent
    offenders = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith(("tests/", "migrations/", ".venv/")) or rel == "srpe_store.py" or "/site-packages/" in rel:
            continue
        text = path.read_text(encoding="utf-8")
        if (re.search(r"(?<!class )SessionRpeObservation\s*\(", text)
                or re.search(r"insert\s+into\s+session_rpe_observations", text, re.I)
                or re.search(r"insert\(\s*models\.SessionRpeObservation", text)):
            offenders.append(rel)
    assert offenders == []
    assert "SessionRpeObservation(" in (backend / "srpe_store.py").read_text(encoding="utf-8")
