"""The /health-connect/sync contract is collapsed to HCA's mapped names and fails
loud on a name break (#234, #235).

Loudness is directional (#235): a MISSING canonical key is fatal (422); an ADDITIVE
unknown key is inert and retained. The negatives below prove the first, the additive
control proves the second, and pairing them is what stops a validator-that-refuses-
everything from reading as green (FEEDBACK §17).

THE SIX-BRANCH COLLAPSE IS NOT SIX 422s. Five branches guard a canonical VALUE and
their rename 422s. The sixth — writer identity (`sourcePackage`) — is OPTIONAL by
design (#175/Q83: identity is not guaranteed; a required field would 422 every
legitimately-untagged record), so its "rename" does not 422. It degrades to a null
writer, coalesced to 'unknown' at capture — the documented tolerated state. That
asymmetry is asserted here, not hidden, because a test claiming a sixth 422 would be
a test asserting a behaviour the design deliberately does not have.
"""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from routers.health_connect import SyncPayload, _aggregate_day, _capture_record_sources
from datetime import date

import models
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import database

_FIXTURE = Path(__file__).parent / "fixtures" / "hc_sync_payload_canonical.json"


def _raw() -> dict:
    return json.loads(_FIXTURE.read_text())


def _mutate(fn) -> dict:
    d = _raw()
    fn(d)
    return d


# ---------- GATE 3 positive control: the golden fixture still parses and populates ----------

def test_the_canonical_fixture_parses_and_aggregates():
    """Positive control (FEEDBACK §17). Without it every 422 below could be a
    validator that refuses everything, which passes the negatives and is useless.
    Identical population to GATE 1 (pre-collapse), so the collapse changed no value."""
    p = SyncPayload(**_raw())
    row = _aggregate_day(date(2026, 8, 23), p)
    assert row["steps"] == 8432
    assert row["resting_heart_rate"] == 51.0
    assert row["hrv_rmssd"] == 41.5
    assert row["sleep_duration_minutes"] == 495
    assert row["deep_sleep_minutes"] == 95
    assert row["rem_sleep_minutes"] == 75
    assert row["sleep_score"] == 10


def test_workout_metadata_is_declared_and_retained():
    """3(c): id/recordingMethod/device are first-class Optional attributes now,
    not silently dropped as they were pre-#234."""
    p = SyncPayload(**_raw())
    w = p.workouts[0]
    assert w.id == "6f1c2a94-3d5e-4b17-9a08-2c7e5d1f4b83"
    assert w.recordingMethod == 0
    assert w.device == 0


# ---------- the five REQUIRED-value rename negatives — each 422, one at a time ----------

@pytest.mark.parametrize("label,mutate,missing_loc", [
    ("bpm<-beatsPerMinute",
     lambda d: d["heartRate"][0].__setitem__("beatsPerMinute", d["heartRate"][0].pop("bpm")),
     ("heartRate", 0, "bpm")),
    ("rmssd<-heartRateVariabilityMillis",
     lambda d: d["hrv"][0].__setitem__("heartRateVariabilityMillis", d["hrv"][0].pop("rmssd")),
     ("hrv", 0, "rmssd")),
    ("date<-startTime (steps)",
     lambda d: d["steps"][0].__setitem__("startTime", d["steps"][0].pop("date")),
     ("steps", 0, "date")),
    ("type<-exerciseType",
     lambda d: d["workouts"][0].__setitem__("exerciseType", d["workouts"][0].pop("type")),
     ("workouts", 0, "type")),
    ("workouts<-exercise (envelope key)",
     lambda d: d.__setitem__("exercise", d.pop("workouts")),
     ("workouts",)),
])
def test_a_canonical_rename_is_rejected(label, mutate, missing_loc):
    with pytest.raises(ValidationError) as exc:
        SyncPayload(**_mutate(mutate))
    locs = [tuple(e["loc"]) for e in exc.value.errors()]
    assert missing_loc in locs, f"{label}: expected a missing-{missing_loc} error, got {locs}"
    assert any(e["type"] in ("missing",) for e in exc.value.errors())


def test_type_present_but_null_is_rejected():
    """The one canonical field whose native type would not reject null without the
    Any->int change: `type` was Optional[Any] (accepts null). #234 makes it required
    int, so key-present-but-null 422s. Distinct error type (int_type), not missing."""
    with pytest.raises(ValidationError) as exc:
        SyncPayload(**_mutate(lambda d: d["workouts"][0].__setitem__("type", None)))
    errs = {(tuple(e["loc"]), e["type"]) for e in exc.value.errors()}
    assert (("workouts", 0, "type"), "int_type") in errs, errs


# ---------- branch 6: writer-identity rename does NOT 422 (optional by design) ----------

def test_writer_identity_rename_degrades_to_unknown_not_422(db_session):
    """The sixth branch is not a sixth 422. sourcePackage is optional (#175/Q83), so
    a payload sending the raw nested dataOrigin instead PARSES — but the writer is no
    longer recovered from it (the reconciler is gone), so identity becomes null and is
    coalesced to 'unknown' at capture. Silent loss of ATTRIBUTION, not of a value — the
    documented tolerated state. This is the finding #235 records, asserted not hidden."""
    d = _mutate(lambda d: [s.__setitem__("dataOrigin", {"packageName": s.pop("sourcePackage")})
                           for s in d["sleep"]])
    p = SyncPayload(**d)                       # parses — no 422
    assert p.sleep[0].sourcePackage is None    # not recovered from dataOrigin
    assert (p.sleep[0].model_extra or {}).get("dataOrigin") == {"packageName": "com.sec.android.app.shealth"}

    u = _user(db_session)
    _capture_record_sources(p, u.id, db_session)
    sleep_row = db_session.query(models.HealthConnectRecordSource).filter_by(
        user_id=u.id, record_type="sleep").one()
    assert sleep_row.source_package == "unknown"   # attribution lost, coalesced


# ---------- additive-key tolerance: the other direction of loudness ----------

def test_an_additive_unknown_top_level_key_is_tolerated_and_retained():
    """extra='allow', not 'forbid': a client that ships ahead of the backend with a new
    key must not fail the whole sync. The key is retained in model_extra, which is what
    makes Step 4's reject-body logging possible."""
    p = SyncPayload(**_mutate(lambda d: d.__setitem__("someNewClientKey", {"x": 1})))
    assert (p.model_extra or {}).get("someNewClientKey") == {"x": 1}


def test_an_additive_unknown_record_key_is_tolerated():
    """The same tolerance one level down — a richer record from a newer client."""
    p = SyncPayload(**_mutate(lambda d: d["heartRate"][0].__setitem__("newSensorField", 7)))
    assert (p.heartRate[0].model_extra or {}).get("newSensorField") == 7


# ---------- an empty required stream is valid; an omitted one is not ----------

def test_an_empty_required_stream_is_valid():
    """Required-but-emptyable: `[]` passes, so a genuinely workout-free day syncs."""
    p = SyncPayload(**_mutate(lambda d: d.__setitem__("workouts", [])))
    assert p.workouts == []


def test_an_omitted_required_stream_is_rejected():
    d = _raw()
    del d["hrv"]
    with pytest.raises(ValidationError) as exc:
        SyncPayload(**d)
    assert ("hrv",) in [tuple(e["loc"]) for e in exc.value.errors()]


# ---------- local db fixture ----------

def _user(db, email="hc-contract@example.com") -> models.User:
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


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
