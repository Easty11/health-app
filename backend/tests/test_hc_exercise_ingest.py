"""Stage-1 HC exercise ingest (#189 discharged, #309).

A synced HC exercise record becomes ONE `aerobic_sessions` row (source='health_connect',
zoneless). Gates:
  S1  — admission: com.hevy mirrors dropped; identical-start lower-writer-class mirrors
        dropped; both counted, never silent. Independent detections (starts apart) survive.
  S2  — write: upsert on (user, 'health_connect', source_session_id=HC id | package|start);
        session_date = LOCAL (AEST) day; z*_seconds NULL (INV-7).
  G1  — the four-record bout yields exactly ONE canonical; flipping writer ranks flips it.
  G3  — an ingested zoneless HC session emits NO metabolic load_event, +1 skipped_no_zones.
  G4  — the 23:30-UTC → next-Brisbane-day trap for session_date.
  G5  — idempotent re-sync: same payload twice → same rows, same ids.
"""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
import load_events_metabolic
from reads.aerobic_reads import arbitrate, arbitrated_sessions
from routers import health_connect as hc
from routers.health_connect import ExerciseRecord, SyncPayload, sync

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"
WITHINGS = "com.withings.wiscale2"


@pytest.fixture()
def db_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    database.Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()


def _user(db, email="hc-ingest@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _z(iso_no_tz: str) -> str:
    """A UTC ISO instant (explicit Z)."""
    return f"{iso_no_tz}Z"


def _ex(start, stop, *, pkg, type=70, sid="x", rec=None):
    return ExerciseRecord(startTime=start, endTime=stop, type=type,
                          sourcePackage=pkg, id=sid, recordingMethod=rec)


def _sync_workouts(db, user, records) -> dict:
    payload = SyncPayload(sleep=[], hrv=[], heartRate=[], steps=[], workouts=records)
    return sync(payload=payload, current_user=user, db=db)


def _hc_rows(db):
    return db.query(models.AerobicSession).filter_by(source="health_connect").all()


# ---------- S2: a lone record ingests one zoneless row ----------

def test_lone_exercise_ingests_one_zoneless_row(db_session):
    u = _user(db_session)
    out = _sync_workouts(db_session, u, [
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T06:45:00"), pkg=GARMIN, type=56, sid="g1", rec=1),
    ])
    assert out["exercise_ingest"]["ingested"] == 1
    assert out["aggregated"]["workouts"] == 1
    rows = _hc_rows(db_session)
    assert len(rows) == 1
    r = rows[0]
    assert r.source_package == GARMIN
    assert r.source_session_id == "g1"
    assert r.sport_id == "56" and r.sport_name == "Running"
    assert r.recording_method == 1
    assert r.duration_minutes == 45.0
    # Zoneless — NULL, not the column default 0 (INV-7 keys on "not measured").
    assert (r.z1_seconds, r.z2_seconds, r.z3_seconds, r.z4_seconds, r.z5_seconds) == \
        (None, None, None, None, None)


# ---------- S1 + G1: four-record bout ----------

def _four_record_bout():
    # garmin@t0 + withings@t0 (mirror) + shealth@t0+30s (independent) + withings@t0+30s (mirror)
    return [
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T06:45:00"), pkg=GARMIN, sid="g1"),
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T06:44:00"), pkg=WITHINGS, sid="w1"),
        _ex(_z("2026-08-01T06:00:30"), _z("2026-08-01T06:45:30"), pkg=SHEALTH, sid="s1"),
        _ex(_z("2026-08-01T06:00:30"), _z("2026-08-01T06:44:00"), pkg=WITHINGS, sid="w2"),
    ]


def test_four_record_bout_drops_mirrors_keeps_independent_detections(db_session):
    u = _user(db_session)
    out = _sync_workouts(db_session, u, _four_record_bout())
    assert out["exercise_ingest"]["ingested"] == 2
    assert out["exercise_ingest"]["mirrors_dropped"] == 2
    kept = {r.source_package for r in _hc_rows(db_session)}
    assert kept == {GARMIN, SHEALTH}      # both Withings mirrors gone


def test_four_record_bout_yields_exactly_one_canonical(db_session):  # G1
    u = _user(db_session)
    _sync_workouts(db_session, u, _four_record_bout())
    rows = arbitrated_sessions(u.id, db_session)
    canonical = [r for r in rows if r.canonical]
    assert len(canonical) == 1
    # Garmin & shealth are equal writer class (wearable); the ladder picks the earlier start.
    assert canonical[0].source_package == GARMIN


def test_four_record_bout_rank_flip_flips_survivors(db_session, monkeypatch):  # G1 mutation §18
    """Invert the writer-class ranks (aggregator now outranks wearable) and the SAME payload
    keeps the Withings rows instead — proving the rank table is load-bearing at admission, not
    incidental to the id/order tie-break."""
    inverted = {"wearable_native": 0, "aggregator_mirror": 2, "unknown": 1}
    monkeypatch.setattr(hc, "writer_class_rank",
                        lambda pkg: inverted[hc.writer_class(pkg)])
    u = _user(db_session)
    _sync_workouts(db_session, u, _four_record_bout())
    kept = {r.source_package for r in _hc_rows(db_session)}
    assert kept == {WITHINGS}


# ---------- S1: hevy mirror dropped, never ingested ----------

def test_hevy_record_dropped_not_ingested(db_session):
    u = _user(db_session)
    out = _sync_workouts(db_session, u, [
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T07:00:00"), pkg="com.hevy", sid="h1"),
    ])
    assert out["exercise_ingest"]["hevy_dropped"] == 1
    assert out["exercise_ingest"]["ingested"] == 0
    assert _hc_rows(db_session) == []


# ---------- S2: null-id fallback + unknown writer ----------

def test_null_id_uses_package_start_fallback(db_session):
    u = _user(db_session)
    out = _sync_workouts(db_session, u, [
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T06:30:00"), pkg=GARMIN, sid=None),
    ])
    assert out["exercise_ingest"]["id_fallback"] == 1
    assert _hc_rows(db_session)[0].source_session_id == f"{GARMIN}|{_z('2026-08-01T06:00:00')}"


def test_unknown_writer_still_ingested_and_counted(db_session):
    u = _user(db_session)
    out = _sync_workouts(db_session, u, [
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T06:30:00"), pkg="com.random.tracker", sid="r1"),
    ])
    assert out["exercise_ingest"]["ingested"] == 1
    assert out["exercise_ingest"]["unknown_writer"] == 1
    assert _hc_rows(db_session)[0].source_package == "com.random.tracker"


# ---------- G5: idempotent re-sync ----------

def test_idempotent_resync_same_rows_same_ids(db_session):
    u = _user(db_session)
    records = _four_record_bout()
    _sync_workouts(db_session, u, records)
    ids_first = sorted((r.id, r.source_session_id) for r in _hc_rows(db_session))
    out2 = _sync_workouts(db_session, u, records)
    ids_second = sorted((r.id, r.source_session_id) for r in _hc_rows(db_session))
    assert ids_first == ids_second        # same rows, same primary ids
    assert out2["exercise_ingest"]["ingested"] == 2
    assert out2["exercise_ingest"]["mirrors_dropped"] == 2


# ---------- G4: local-day trap ----------

def test_local_day_trap_late_utc_lands_next_brisbane_day(db_session):
    u = _user(db_session)
    # 23:30Z on 08-01 is 09:30 on 08-02 in Brisbane (+10) — session_date must be 08-02.
    _sync_workouts(db_session, u, [
        _ex(_z("2026-08-01T23:30:00"), _z("2026-08-02T00:15:00"), pkg=GARMIN, sid="late"),
    ])
    assert _hc_rows(db_session)[0].session_date == date(2026, 8, 2)


# ---------- G3: ingested zoneless HC emits no metabolic load_event ----------

def test_ingested_zoneless_hc_emits_no_metabolic_load_event(db_session):
    u = _user(db_session)
    _sync_workouts(db_session, u, [
        _ex(_z("2026-08-01T06:00:00"), _z("2026-08-01T06:30:00"), pkg=GARMIN, sid="z1"),
    ])
    result = load_events_metabolic.compute_metabolic_load_events(db_session, u.id)
    db_session.commit()
    assert result["events_written"] == 0
    assert result["sessions_skipped_no_zones"] == 1
    metabolic = (
        db_session.query(models.LoadEvent)
        .filter_by(user_id=u.id,
                   formula_version=load_events_metabolic.FORMULA_VERSION_METABOLIC)
        .all()
    )
    assert metabolic == []
