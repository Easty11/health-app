"""Overlapping syncs of one user must not collide, and a failure must surface as itself.

Prod, 3 Oct 2026: four overlapping `POST /health-connect/sync` requests, one 200 and three 500s,
each `UniqueViolation ... uq_hc_record_source`. `_capture_record_sources` read every existing key,
then added the missing ones through the ORM; a concurrent POST that committed the same keys in
between made the flush raise. The flush happened at `begin_nested()` inside `_persist_hr_samples`,
whose catch-all logged it as an `hr_samples` failure (the wrong table) and swallowed it, leaving the
session unusable: the next query raised and the whole sync rolled back to a 500.

SQLite (the suite's engine) cannot run two POSTs at once, so the race is reproduced the way it
appears to the code: the keys already exist (a concurrent sync committed them) and this request's
earlier read did not see them. The old read-then-add form fails these tests; the ON CONFLICT form
does not read, so it cannot be blinded.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

import models
from routers.health_connect import (
    HeartRateRecord,
    SyncPayload,
    _capture_record_sources,
    _persist_hr_samples,
    sync,
)

GARMIN = "com.garmin.android.apps.connectmobile"


def _user(db, email="hc-race@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _iso(minutes=0, seconds=0):
    return (datetime(2026, 9, 26, 5, 0, 0, tzinfo=timezone.utc)
            + timedelta(minutes=minutes, seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hr(iso, bpm=70, pkg=GARMIN):
    return HeartRateRecord(time=iso, bpm=bpm, sourcePackage=pkg)


def _payload(hr):
    return SyncPayload(sleep=[], hrv=[], heartRate=list(hr), steps=[], workouts=[])


def _sources(db):
    return db.query(models.HealthConnectRecordSource).order_by(
        models.HealthConnectRecordSource.record_start).all()


def _blind_preload(monkeypatch, db):
    """This request's earlier read of the existing keys did not see a concurrent commit."""
    class _Blind:
        def filter_by(self, **_kw):
            return self

        def all(self):
            return []

    real_query = db.query

    def query(*entities, **kw):
        if entities and entities[0] is models.HealthConnectRecordSource:
            return _Blind()
        return real_query(*entities, **kw)

    monkeypatch.setattr(db, "query", query)


# ---- the capture no longer races -----------------------------------------------------------------

def test_a_key_committed_by_a_concurrent_sync_does_not_fail_the_capture(db_session, monkeypatch):
    u = _user(db_session)
    hr = [_hr(_iso(minutes=2 * i)) for i in range(5)]
    _capture_record_sources(_payload(hr), u.id, db_session)
    db_session.commit()                                       # the other POST's commit

    _blind_preload(monkeypatch, db_session)
    inserted, _ = _capture_record_sources(
        _payload(hr + [_hr(_iso(minutes=20))]), u.id, db_session)
    db_session.flush()                                        # the old form raised UniqueViolation here
    db_session.commit()

    assert inserted == 1                                      # only the genuinely new key
    # Core count: `db.query` is still blinded for this model, by design.
    assert db_session.scalar(select(func.count()).select_from(models.HealthConnectRecordSource)) == 6


def test_a_whole_sync_survives_keys_a_concurrent_sync_committed(db_session, monkeypatch):
    """The prod shape end to end: the record_sources keys already exist, this request did not
    see them, and the sync must still return its accounting instead of raising."""
    u = _user(db_session)
    hr = [_hr(_iso(seconds=15 * i), 90 + i) for i in range(10)]
    _capture_record_sources(_payload(hr), u.id, db_session)
    db_session.commit()

    _blind_preload(monkeypatch, db_session)
    out = sync(payload=_payload(hr), current_user=u, db=db_session)

    assert out["sources_captured"] == 0                       # every key already stored
    assert out["hr_samples"] == {"received": 10, "stored": 10, "deduped": 0, "unparseable": 0}
    assert db_session.query(models.HrSample).count() == 10


# ---- capture semantics ---------------------------------------------------------------------------

def test_a_resynced_key_keeps_its_first_synced_at(db_session):
    """Deliberate change: `synced_at` is when the key was FIRST captured, no longer the last
    re-post. Nothing in the backend reads it; first-seen is also the stable arrival evidence."""
    u = _user(db_session)
    hr = [_hr(_iso(minutes=2 * i)) for i in range(3)]
    assert _capture_record_sources(_payload(hr), u.id, db_session)[0] == 3
    db_session.commit()
    first = {r.record_start: r.synced_at for r in _sources(db_session)}

    assert _capture_record_sources(_payload(hr), u.id, db_session)[0] == 0
    db_session.commit()
    db_session.expire_all()
    assert {r.record_start: r.synced_at for r in _sources(db_session)} == first


def test_new_rows_are_counted_once_and_intra_payload_duplicates_collapse(db_session):
    u = _user(db_session)
    hr = [_hr(_iso()), _hr(_iso()), _hr(_iso(minutes=2)), _hr(_iso(), pkg="com.other.app")]
    inserted, unattributed = _capture_record_sources(_payload(hr), u.id, db_session)
    assert inserted == 3                                      # same key twice -> one row; other writer -> own row
    assert unattributed == 0
    assert len(_sources(db_session)) == 3


def test_a_missing_writer_is_still_coalesced_and_counted(db_session):
    u = _user(db_session)
    inserted, unattributed = _capture_record_sources(
        _payload([HeartRateRecord(time=_iso(), bpm=70)]), u.id, db_session)
    assert (inserted, unattributed) == (1, 1)
    assert _sources(db_session)[0].source_package == "unknown"


def test_the_conflict_target_is_the_real_unique_constraint():
    """Postgres is prod; render the statement and tie its conflict columns to the model's own
    `uq_hc_record_source`, so the two cannot drift apart."""
    table = models.HealthConnectRecordSource.__table__
    (uq,) = [c for c in table.constraints
             if isinstance(c, UniqueConstraint) and c.name == "uq_hc_record_source"]
    cols = [c.name for c in uq.columns]
    assert sorted(cols) == ["record_start", "record_type", "source_package", "user_id"]

    stmt = (postgresql.insert(table)
            .values([{"user_id": 1, "record_type": "heart_rate", "record_start": "x",
                      "source_package": "p", "synced_at": datetime(2026, 9, 26, tzinfo=timezone.utc)}])
            .on_conflict_do_nothing(index_elements=["user_id", "record_type", "record_start", "source_package"]))
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (user_id, record_type, record_start, source_package) DO NOTHING" in sql


def test_chunking_stores_everything_and_stays_idempotent(db_session, monkeypatch):
    import routers.health_connect as hc
    monkeypatch.setattr(hc, "HR_SAMPLE_CHUNK", 7)             # 50 rows -> 8 statements
    u = _user(db_session)
    hr = [_hr(_iso(seconds=i)) for i in range(50)]
    assert _capture_record_sources(_payload(hr), u.id, db_session)[0] == 50
    assert _capture_record_sources(_payload(hr), u.id, db_session)[0] == 0
    assert len(_sources(db_session)) == 50


# ---- the hr_samples handler no longer masks a failure that is not its own ------------------------

def test_a_pending_failure_surfaces_as_itself_not_as_an_hr_samples_error(db_session):
    """A pending ORM row that violates `uq_hc_record_source` (what the old read-then-add form
    produced under a race). The handler used to catch the flush, report it as an hr_samples
    failure and return normally; the session was then unusable. It must raise, naming the table."""
    u = _user(db_session)
    _capture_record_sources(_payload([_hr(_iso())]), u.id, db_session)
    db_session.commit()
    db_session.add(models.HealthConnectRecordSource(
        user_id=u.id, record_type="heart_rate", record_start=_iso(), source_package=GARMIN,
        synced_at=datetime.now(timezone.utc)))

    with pytest.raises(IntegrityError) as exc:
        _persist_hr_samples(_payload([_hr(_iso(seconds=30), 71)]), u.id, db_session)
    assert "health_connect_record_sources" in str(exc.value)
    assert "hr_samples" not in str(exc.value)
    db_session.rollback()
