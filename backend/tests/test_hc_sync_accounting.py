"""GATE 5 — the /sync response accounts for what arrived, what reached a DailyRecord,
and what lost its writer (#235).

Three maps, additive to the existing synced/dates/rejected_pre_2020/sources_captured:
  received     — records per stream as POSTED (before pre-2020 reject).
  aggregated   — records on a date that produced a DailyRecord row. `workouts` is 0
                 by design: HC exercise is source-captured, ingestion held at #189.
                 (Named `aggregated`, not `ingested`, so that honest 0 does not read
                 as a permanent defect — the GATE 1 finding, hardened into the contract.)
  unattributed — records whose writer degraded to 'unknown' (branch-6, orthogonal axis).

Dates are built relative to "now" so the 7-day aggregation window never ages these
payloads out (a fixed-date fixture would pass today and silently fail next week).
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
from routers.health_connect import (
    SyncPayload, SleepSession, HRVRecord, HeartRateRecord, StepsRecord,
    ExerciseRecord, sync,
)


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


def _user(db, email="hc-acct@example.com") -> models.User:
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


_TODAY = datetime.now(timezone.utc).date()


def _iso(d: date, hhmm: str = "03:00:00") -> str:
    return f"{d.isoformat()}T{hhmm}+10:00"      # explicit AEST, unambiguous wake-date


def _full_payload(pkg="com.sec.android.app.shealth", **overrides) -> SyncPayload:
    """One attributed record in each of the five streams, all dated today."""
    base = dict(
        sleep=[SleepSession(startTime=_iso(_TODAY - timedelta(days=1), "22:00:00"),
                            endTime=_iso(_TODAY, "06:00:00"), stages=[], sourcePackage=pkg)],
        hrv=[HRVRecord(time=_iso(_TODAY), rmssd=42.0, sourcePackage=pkg)],
        heartRate=[HeartRateRecord(time=_iso(_TODAY), bpm=50, sourcePackage=pkg)],
        steps=[StepsRecord(date=_TODAY.isoformat(), count=1000, sourcePackage=pkg)],
        workouts=[ExerciseRecord(startTime=_iso(_TODAY, "17:00:00"),
                                 endTime=_iso(_TODAY, "18:00:00"), type=70, sourcePackage=pkg)],
    )
    base.update(overrides)
    return SyncPayload(**base)


def _sync(db, payload) -> dict:
    return sync(payload=payload, current_user=_user(db), db=db)


# ---------- received: all five non-zero; aggregated: four + workouts 0 by design ----------

def test_received_is_nonzero_for_all_five_streams(db_session):
    out = _sync(db_session, _full_payload())
    assert out["received"] == {"sleep": 1, "hrv": 1, "heartRate": 1, "steps": 1, "workouts": 1}


def test_aggregated_populates_four_streams_and_workouts_is_zero_by_design(db_session):
    out = _sync(db_session, _full_payload())
    assert out["aggregated"]["sleep"] == 1
    assert out["aggregated"]["hrv"] == 1
    assert out["aggregated"]["heartRate"] == 1
    assert out["aggregated"]["steps"] == 1
    # Not a drop — HC exercise ingestion into DailyRecord is held at #189.
    assert out["aggregated"]["workouts"] == 0


# ---------- an empty stream reads 0 and still 200 ----------

def test_an_empty_stream_reports_zero_received_and_succeeds(db_session):
    out = _sync(db_session, _full_payload(hrv=[]))
    assert out["received"]["hrv"] == 0
    assert out["aggregated"]["hrv"] == 0
    # other streams unaffected — the sync still processes
    assert out["received"]["steps"] == 1


# ---------- unattributed: branch-6 degrade made observable ----------

def test_a_fully_attributed_payload_reports_zero_unattributed(db_session):
    assert _sync(db_session, _full_payload())["unattributed"] == 0


def test_records_with_no_writer_are_counted_unattributed(db_session):
    # Two records carry no sourcePackage (the branch-6 degrade shape): they capture
    # as 'unknown' and must surface here rather than vanish silently.
    p = _full_payload()
    p.hrv[0].sourcePackage = None
    p.steps[0].sourcePackage = None
    assert _sync(db_session, p)["unattributed"] == 2


# ---------- the reconciliation payload: every count individually explained ----------

def test_received_aggregated_and_rejected_reconcile_on_a_crafted_steps_stream(db_session):
    """Three steps records, each in a different category, asserted individually — the
    strong version: no brittle received = aggregated + rejected identity (unattributed
    is orthogonal and future categories may appear), just each count explained on a
    payload where the maps MUST disagree."""
    old_in_range = _TODAY - timedelta(days=2)      # recent, aggregates
    out_of_window = date(2021, 1, 1)               # >=2020 so not rejected, but out of the 7d window
    payload = _full_payload(steps=[
        StepsRecord(date="2019-06-01", count=10, sourcePackage="pkg"),      # pre-2020 -> rejected
        StepsRecord(date=out_of_window.isoformat(), count=20, sourcePackage="pkg"),  # received, not aggregated
        StepsRecord(date=old_in_range.isoformat(), count=30, sourcePackage="pkg"),   # aggregated
    ])
    out = _sync(db_session, payload)

    assert out["received"]["steps"] == 3            # all three arrived
    assert out["rejected_pre_2020"] == 1            # the 2019 one
    assert out["aggregated"]["steps"] == 1          # only the in-window one fed a row
