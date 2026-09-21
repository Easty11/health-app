"""Per-POST sync telemetry — health_connect_sync_events (HCA DECISIONS #40; cross-ref HCA Q22).

One row per POST to /health-connect/sync capturing the client build fingerprint
(`client`) and per-stream fetch telemetry (`fetchMeta`). Capture only: it filters
nothing, changes no aggregation, adds no read surface. These gates cover:

  a) client + fetchMeta  -> exactly ONE event row; git_sha + fetch_meta round-trip
     (incl. oldestAt/newestAt, truncated, endedOnFailure).
  b) neither key         -> 200 (validates, no 422), ONE row, git_sha IS NULL.
  c) periodDays=7 fanning to N date-rows -> still exactly ONE event row (per-POST grain).
  d) a "-dirty" gitSha   -> stored verbatim.

(e — existing sync tests unregressed — is the rest of the suite, run whole.)

Dates are relative to "now" so the 7-day aggregation window never ages a fixture out.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models
from routers.health_connect import SyncPayload, sync


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


def _user(db, email="hc-sync-event@example.com") -> models.User:
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


_TODAY = datetime.now(timezone.utc).date()


def _iso(d: date, hhmm: str = "03:00:00") -> str:
    return f"{d.isoformat()}T{hhmm}+10:00"      # explicit AEST, unambiguous wake-date


def _empty_streams() -> dict:
    return {"sleep": [], "hrv": [], "heartRate": [], "steps": [], "workouts": []}


def _steps_on(days) -> list[dict]:
    return [{"date": (_TODAY - timedelta(days=n)).isoformat(), "count": 100 + n,
             "sourcePackage": "com.sec.android.app.shealth"} for n in days]


def _validate(**top) -> SyncPayload:
    """Build via model_validate on a raw dict — mirrors what FastAPI does with the
    JSON body, so `client`/`fetchMeta` go through ClientInfo/FetchMetaEntry parsing and
    an omitted key exercises the real 'does an old build 422?' path."""
    body = _empty_streams()
    body.update(top)
    return SyncPayload.model_validate(body)


def _sync(db, payload) -> dict:
    return sync(payload=payload, current_user=_user(db), db=db)


def _events(db) -> list[models.HealthConnectSyncEvent]:
    return db.query(models.HealthConnectSyncEvent).all()


# ---------- a) client + fetchMeta round-trip, exactly one row ----------

def test_client_and_fetchmeta_persist_one_row_that_round_trips(db_session):
    payload = _validate(
        client={"gitSha": "6fd8b3e", "builtAt": "2026-09-21T05:02:53.536Z",
                "appVersion": "1.0.0", "platform": "android"},
        fetchMeta={
            "heartRate": {"received": 987, "oldestAt": "2026-09-14T00:00:00Z",
                          "newestAt": "2026-09-21T04:00:00Z", "pages": 1,
                          "truncated": True, "endedOnFailure": False},
            "sleep": {"received": 12, "oldestAt": "2026-09-14T22:00:00Z",
                      "newestAt": "2026-09-21T06:00:00Z", "pages": 1,
                      "truncated": False, "endedOnFailure": False},
        },
    )
    _sync(db_session, payload)

    rows = _events(db_session)
    assert len(rows) == 1
    row = rows[0]

    # fingerprint
    assert row.git_sha == "6fd8b3e"
    assert row.built_at == "2026-09-21T05:02:53.536Z"
    assert row.app_version == "1.0.0"
    assert row.platform == "android"
    assert row.period_days == 7            # default, no periodDays sent

    # fetch_meta verbatim, including the alarm fields
    fm = row.fetch_meta
    assert set(fm) == {"heartRate", "sleep"}
    assert fm["heartRate"]["received"] == 987
    assert fm["heartRate"]["oldestAt"] == "2026-09-14T00:00:00Z"
    assert fm["heartRate"]["newestAt"] == "2026-09-21T04:00:00Z"
    assert fm["heartRate"]["truncated"] is True
    assert fm["heartRate"]["endedOnFailure"] is False
    assert fm["sleep"]["truncated"] is False

    # server-clock synced_at, not the client's syncedAt
    assert row.synced_at is not None


# ---------- b) neither key: validates (no 422), one row, git_sha NULL ----------

def test_old_build_payload_validates_and_writes_a_null_git_sha_row(db_session):
    # model_validate is where a 422 would be raised if `client`/`fetchMeta` were
    # required — omitting both must succeed.
    payload = _validate()      # no client, no fetchMeta
    assert payload.client is None
    assert payload.fetchMeta == {}

    _sync(db_session, payload)

    rows = _events(db_session)
    assert len(rows) == 1
    assert rows[0].git_sha is None         # the "still on an old build" signal
    assert rows[0].built_at is None
    assert rows[0].fetch_meta is None
    assert rows[0].period_days == 7


# ---------- c) per-POST grain: N date-rows, still ONE event row ----------

def test_a_multi_date_post_still_writes_exactly_one_event_row(db_session):
    # Steps across four distinct in-window days -> four health_connect_syncs rows,
    # but the fingerprint describes the POST, not a date: exactly one event row.
    user = _user(db_session)
    payload = _validate(periodDays=7,
                        client={"gitSha": "abc1234"},
                        steps=_steps_on([0, 1, 2, 3]))
    out = sync(payload=payload, current_user=user, db=db_session)

    assert out["synced"] == 4                                  # fanned out to 4 date-rows
    date_rows = db_session.query(models.HealthConnectSync).filter_by(user_id=user.id).count()
    assert date_rows == 4
    event_rows = db_session.query(models.HealthConnectSyncEvent).filter_by(user_id=user.id).all()
    assert len(event_rows) == 1
    assert event_rows[0].git_sha == "abc1234"


# ---------- d) a "-dirty" gitSha is stored verbatim ----------

def test_dirty_git_sha_is_stored_verbatim(db_session):
    _sync(db_session, _validate(client={"gitSha": "6fd8b3e-dirty"}))
    rows = _events(db_session)
    assert len(rows) == 1
    assert rows[0].git_sha == "6fd8b3e-dirty"
