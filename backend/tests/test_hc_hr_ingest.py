"""HC sync persists raw HR (`hr_samples`) and no longer wipes enrichment (Q159 stage 2, S2, G1).

  * every `payload.heartRate` record is stored (after the pre-2020 reject), source-neutral,
    writer coalesced to 'unknown', idempotent on re-post, chunked on both engines;
  * the `_ingest_exercise_sessions` UPDATE never touches `z*_seconds` / `hr_avg` / `hr_max`
    (it used to rewrite `z*` to NULL on every re-sync), the INSERT still writes NULL not 0;
  * a failure of the HR insert is isolated: reported in the response, never rolls back the day
    aggregates or exercise rows riding the same commit.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import sqlite as sqlite_dialect

import models
from routers import health_connect as hc
from routers.health_connect import ExerciseRecord, HeartRateRecord, SyncPayload, sync

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"


def _user(db, email="hr-ingest@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _hr(iso, bpm, pkg=GARMIN):
    return HeartRateRecord(time=iso, bpm=bpm, sourcePackage=pkg)


def _post(db, user, hr=(), workouts=()):
    payload = SyncPayload(sleep=[], hrv=[], heartRate=list(hr), steps=[], workouts=list(workouts))
    return sync(payload=payload, current_user=user, db=db)


def _stored(db):
    return db.query(models.HrSample).order_by(models.HrSample.sample_time, models.HrSample.source_package).all()


def _iso(minutes=0, seconds=0):
    # Yesterday 05:00Z, relative to the clock: the sync only counts days inside its window
    # (`since = today - periodDays`), so a fixed date silently stopped syncing a week on (6 Oct 2026).
    base = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
    return (base + timedelta(minutes=minutes, seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- every record is stored ---------------------------------------------------------------------

def test_every_heart_rate_record_is_persisted_source_neutral(db_session):
    u = _user(db_session)
    out = _post(db_session, u, hr=[_hr(_iso(seconds=15 * i), 100 + i) for i in range(20)])
    assert out["hr_samples"] == {"received": 20, "stored": 20, "deduped": 0, "unparseable": 0}
    rows = _stored(db_session)
    assert len(rows) == 20
    assert {(r.source, r.source_package, r.user_id) for r in rows} == {("health_connect", GARMIN, u.id)}
    assert [r.bpm for r in rows] == [100 + i for i in range(20)]            # bpm kept as received


def test_a_missing_writer_is_coalesced_to_unknown_not_null(db_session):
    u = _user(db_session)
    _post(db_session, u, hr=[HeartRateRecord(time=_iso(), bpm=80)])
    assert [r.source_package for r in _stored(db_session)] == ["unknown"]


def test_two_writers_at_one_instant_are_two_rows(db_session):
    u = _user(db_session)
    _post(db_session, u, hr=[_hr(_iso(), 140, GARMIN), _hr(_iso(), 90, SHEALTH)])
    assert [(r.source_package, r.bpm) for r in _stored(db_session)] == [(GARMIN, 140), (SHEALTH, 90)]


def test_pre_2020_records_are_rejected_before_persistence(db_session):
    u = _user(db_session)
    out = _post(db_session, u, hr=[_hr("1970-01-01T00:00:00Z", 70), _hr(_iso(), 80)])
    assert out["rejected_pre_2020"] == 1
    # `received["heartRate"]` is AS POSTED (2); `hr_samples.received` is what reached the store step,
    # i.e. after the pre-2020 reject (1) — the two reconcile via `rejected_pre_2020`.
    assert out["received"]["heartRate"] == 2
    assert out["hr_samples"]["received"] == 1 and out["hr_samples"]["stored"] == 1
    assert [r.bpm for r in _stored(db_session)] == [80]


def test_samples_outside_the_sync_window_are_still_kept(db_session):
    """A deep sync re-posts history: HR is NOT bounded by periodDays (that bound is for day rows)."""
    u = _user(db_session)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = _post(db_session, u, hr=[_hr(old, 77)])
    assert out["hr_samples"]["stored"] == 1


def test_implausible_bpm_is_stored_not_filtered_at_write(db_session):
    """Plausibility is a zone-time rule; a wrong bound must be correctable by a recompute."""
    u = _user(db_session)
    _post(db_session, u, hr=[_hr(_iso(), 255), _hr(_iso(seconds=5), 12)])
    assert [r.bpm for r in _stored(db_session)] == [255, 12]


# ---- idempotent --------------------------------------------------------------------------------------

def test_a_repost_stores_nothing_new(db_session):
    u = _user(db_session)
    hr = [_hr(_iso(seconds=15 * i), 100 + i) for i in range(30)]
    first = _post(db_session, u, hr=hr)
    second = _post(db_session, u, hr=hr)
    assert first["hr_samples"]["stored"] == 30 and second["hr_samples"]["stored"] == 0
    assert db_session.query(models.HrSample).count() == 30


def test_a_repost_with_a_few_new_samples_stores_only_those(db_session):
    u = _user(db_session)
    _post(db_session, u, hr=[_hr(_iso(seconds=15 * i), 100) for i in range(10)])
    out = _post(db_session, u, hr=[_hr(_iso(seconds=15 * i), 100) for i in range(14)])
    assert out["hr_samples"]["stored"] == 4 and db_session.query(models.HrSample).count() == 14


def test_a_resent_sample_never_changes_the_stored_bpm(db_session):
    u = _user(db_session)
    _post(db_session, u, hr=[_hr(_iso(), 100)])
    _post(db_session, u, hr=[_hr(_iso(), 111)])
    assert [r.bpm for r in _stored(db_session)] == [100]


def test_intra_payload_same_second_duplicates_collapse_and_are_counted(db_session):
    u = _user(db_session)
    out = _post(db_session, u, hr=[_hr("2026-09-28T05:00:00.100Z", 100), _hr("2026-09-28T05:00:00.900Z", 101)])
    assert out["hr_samples"] == {"received": 2, "stored": 1, "deduped": 1, "unparseable": 0}


def test_an_unparseable_time_is_dropped_and_counted_never_guessed(db_session):
    u = _user(db_session)
    out = _post(db_session, u, hr=[_hr("2026-09-28Tnot-a-time", 100), _hr(_iso(), 90)])
    assert out["hr_samples"]["unparseable"] == 1 and out["hr_samples"]["stored"] == 1


def test_chunking_stores_everything_and_stays_idempotent(db_session, monkeypatch):
    monkeypatch.setattr(hc, "HR_SAMPLE_CHUNK", 7)                            # 50 rows -> 8 statements
    u = _user(db_session)
    hr = [_hr(_iso(seconds=i), 100 + (i % 40)) for i in range(50)]
    assert _post(db_session, u, hr=hr)["hr_samples"]["stored"] == 50
    assert _post(db_session, u, hr=hr)["hr_samples"]["stored"] == 0
    assert db_session.query(models.HrSample).count() == 50


def test_the_postgres_dialect_path_emits_on_conflict_do_nothing():
    """Both engines run the same statement shape. SQLite is the suite's engine; render the
    Postgres form to prove `ON CONFLICT (user_id, sample_time, source, source_package) DO NOTHING`."""
    from sqlalchemy.dialects import postgresql
    stmt = (postgresql.insert(models.HrSample.__table__)
            .values([{"user_id": 1, "sample_time": datetime(2026, 9, 28, tzinfo=timezone.utc), "bpm": 1,
                      "source": "health_connect", "source_package": "p"}])
            .on_conflict_do_nothing(index_elements=["user_id", "sample_time", "source", "source_package"]))
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (user_id, sample_time, source, source_package) DO NOTHING" in sql


# ---- failure isolation ----------------------------------------------------------------------------------

def test_an_hr_insert_failure_is_reported_and_does_not_roll_back_the_rest_of_the_sync(db_session, monkeypatch):
    u = _user(db_session)

    real_insert = sqlite_dialect.insert

    def _boom(table, *a, **k):
        # Selective: record_sources capture shares this insert path and must keep working.
        if table.name == "hr_samples":
            raise RuntimeError("hr insert broke")
        return real_insert(table, *a, **k)
    monkeypatch.setattr(sqlite_dialect, "insert", _boom)

    ex = ExerciseRecord(startTime=_iso(), endTime=_iso(minutes=30), type=79, sourcePackage=GARMIN, id="w1")
    out = _post(db_session, u, hr=[_hr(_iso(), 90)], workouts=[ex])
    assert out["hr_samples"]["error"] == "RuntimeError: hr insert broke" and out["hr_samples"]["stored"] == 0
    assert out["exercise_ingest"]["ingested"] == 1 and out["synced"] >= 1       # the rest committed
    assert db_session.query(models.AerobicSession).count() == 1
    assert db_session.query(models.HealthConnectSync).count() >= 1
    assert db_session.query(models.HrSample).count() == 0


# ---- re-sync preserves enrichment (the S0(a)(ii) bug) --------------------------------------------------------

def _ex(**kw):
    base = dict(startTime=_iso(), endTime=_iso(minutes=30), type=79, sourcePackage=GARMIN, id="w1")
    base.update(kw)
    return ExerciseRecord(**base)


def test_an_enriched_row_survives_a_resync_byte_identical_in_its_zone_fields(db_session):
    """Fixture from the probe that confirmed the bug: enrich, re-sync the same payload, read back.
    Before S2 `z*` went back to NULL (hr_avg/hr_max survived); now none of the five zones, hr_avg or
    hr_max moves. Mutation: restoring `z*=null()` to the shared `fields` dict fails this."""
    u = _user(db_session)
    _post(db_session, u, workouts=[_ex()])
    row = db_session.query(models.AerobicSession).one()
    row.z1_seconds, row.z2_seconds, row.z3_seconds, row.z4_seconds, row.z5_seconds = 0, 600, 900, 200, 100
    row.hr_avg, row.hr_max = 140, 171
    db_session.commit()
    snap = lambda r: (r.z1_seconds, r.z2_seconds, r.z3_seconds, r.z4_seconds, r.z5_seconds, r.hr_avg, r.hr_max)
    before = snap(row)

    out = _post(db_session, u, workouts=[_ex()])
    assert out["exercise_ingest"]["ingested"] == 1
    db_session.expire_all()
    assert snap(db_session.query(models.AerobicSession).one()) == before == (0, 600, 900, 200, 100, 140, 171)


def test_a_resync_still_refreshes_the_fields_ingest_owns(db_session):
    u = _user(db_session)
    _post(db_session, u, workouts=[_ex()])
    _post(db_session, u, workouts=[_ex(endTime=_iso(minutes=45))])
    db_session.expire_all()
    r = db_session.query(models.AerobicSession).one()
    assert r.duration_minutes == 45.0 and r.sport_name == "Walking"


def test_a_fresh_insert_is_still_null_zoned_not_zero(db_session):
    """INV-7 keys on 'not measured': the INSERT writes SQL NULL, never the column default 0."""
    u = _user(db_session)
    _post(db_session, u, workouts=[_ex()])
    db_session.expire_all()
    r = db_session.query(models.AerobicSession).one()
    assert (r.z1_seconds, r.z2_seconds, r.z3_seconds, r.z4_seconds, r.z5_seconds) == (None,) * 5
    assert r.hr_avg is None and r.hr_max is None
