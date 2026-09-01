"""v4 zone-enrichment folded into the Polar sync (BRIEF-2 / DECISIONS_LOG v4 zone-enrichment).

The v4 summary list omits the HR-zone split, so live-synced `polar_v4` rows land
zoneless and fail-closed skip the metabolic transform. The v4 *feature* mode
(`features='zones'`, one-day window cap) surfaces the split in the ZIP export's exact
schema; the sync now fetches it for the zoneless rows in the window and merges
`z*_seconds` in place, and the on-ingest cascade recomputes `metab-v1`.

Gates covered:
  * TRANSPORT (#166): `list_zoned_sessions` is exercised against a FAKED httpx layer —
    the real request params (`features=zones`, one-day window) and the real
    `_parse_session` are asserted, not a stubbed client method.
  * single-emission A: a v4-ONLY bout that gains zones emits exactly one metabolic event.
  * single-emission B: a dual-lane bout (flow_export + enriched v4 twin) still emits
    exactly once — arbitration keeps the flow_export row canonical (#260).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from connectors.polar import PolarV4Client
from database import get_db
from load_events_metabolic import FORMULA_VERSION_METABOLIC
from routers import polar


# ── fixtures ──────────────────────────────────────────────────────────────────────

def _training_session(sid: str, start: datetime, *, zones_seconds: tuple | None = (600, 300, 0, 0, 120),
                      cardio_load: float | None = 42.0) -> dict:
    """A v4 training-session body. `zones_seconds` None → zoneless (no exercises.zones,
    as the summary transport returns); a tuple → the feature-mode zone split, encoded as
    the export's millisecond `inZone` exactly as `_parse_session` reads it."""
    stop = start + timedelta(minutes=30)
    body: dict = {
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "stopTime": stop.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezoneOffsetMinutes": 600,  # AEST
        "identifier": {"id": sid},
        "sport": {"id": 1},
        "hrAvg": 150, "hrMax": 175, "calories": 300,
        "durationMillis": 30 * 60 * 1000,
        "recoveryTimeMillis": 20 * 3600 * 1000,
        "trainingLoadReport": {"cardioLoad": cardio_load, "muscleLoad": -1.0},
    }
    if zones_seconds is not None:
        body["exercises"] = [{"zones": [{
            "type": "ZONE_TYPE_HEART_RATE",
            "zones": [{"inZone": s * 1000} for s in zones_seconds],
        }]}]
    return body


def _user(db, uid=1):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(polar.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class _FakeClient:
    """Fake v4 client: `list_training_sessions_chunked` is the summary pass,
    `list_zoned_sessions` is the feature-mode enrichment fetch."""
    def __init__(self, summary, zoned=None):
        self._summary = summary
        self._zoned = zoned or []

    def list_training_sessions_chunked(self, start, end):
        return self._summary

    def list_zoned_sessions(self, days):
        return self._zoned


def _recent_naive(days_ago=10, hour=6) -> datetime:
    """A recent wall-clock datetime (naive) inside the default 365-day sync window;
    hour 6 + tz +10h stays on the same calendar date, so session_date is unambiguous."""
    d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
    return datetime(d.year, d.month, d.day, hour, 0)


# ── TRANSPORT (#166): real params + real parse over a faked httpx layer ───────────

def test_list_zoned_sessions_uses_features_zones_and_one_day_windows(monkeypatch):
    calls: list[dict] = []

    def fake_get(self, url, headers=None, params=None):
        calls.append(params)
        req = httpx.Request("GET", url)
        body = {"trainingSessions": [
            _training_session("v4z", datetime(2026, 8, 27, 16, 0), zones_seconds=(1235, 1665, 1147, 529, 16)),
        ]}
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    out = PolarV4Client("tok").list_zoned_sessions([date(2026, 8, 27)])

    # one request, feature token + one-day window exactly as the live API requires
    assert len(calls) == 1
    assert calls[0]["features"] == "zones"
    assert calls[0]["from"] == "2026-08-27T00:00:00"
    assert calls[0]["to"] == "2026-08-28T00:00:00"

    # the real parser reads the returned schema into z*_seconds (source tagged v4)
    fields = PolarV4Client.parse_session(out[0])
    assert [fields[f"z{i}_seconds"] for i in range(1, 6)] == [1235, 1665, 1147, 529, 16]
    assert fields["source"] == "polar_v4"


def test_list_zoned_sessions_scopes_one_call_per_day(monkeypatch):
    seen_days: list[str] = []

    def fake_get(self, url, headers=None, params=None):
        seen_days.append(params["from"])
        return httpx.Response(200, json={"trainingSessions": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    PolarV4Client("tok").list_zoned_sessions([date(2026, 8, 1), date(2026, 8, 3)])
    assert seen_days == ["2026-08-01T00:00:00", "2026-08-03T00:00:00"]


# ── single-emission A: v4-only bout gains zones → one event ───────────────────────

def test_sync_enriches_v4_only_bout_and_emits_exactly_once(db_session, monkeypatch):
    user = _user(db_session)
    start = _recent_naive()
    summary = [_training_session("v4solo", start, zones_seconds=None, cardio_load=None)]  # zoneless summary
    zoned = [_training_session("v4solo", start, zones_seconds=(600, 300, 0, 0, 120))]     # feature-mode split
    monkeypatch.setattr(polar, "_valid_client", lambda uid, db: _FakeClient(summary, zoned=zoned))

    body = _client(db_session, user).post("/integrations/polar/sync").json()

    assert body["synced"] == 1
    assert body["enriched"] == 1

    row = db_session.query(models.AerobicSession).filter_by(source="polar_v4").one()
    assert [row.z1_seconds, row.z2_seconds, row.z3_seconds, row.z4_seconds, row.z5_seconds] == [600, 300, 0, 0, 120]

    tr = body["cascade"]["transform"]
    assert tr["events_written"] == 1
    assert tr["sessions_skipped_no_zones"] == 0
    ev = db_session.query(models.LoadEvent).filter_by(
        user_id=user.id, formula_version=FORMULA_VERSION_METABOLIC).one()
    assert ev.provenance["zone_source"] == "polar_v4"


def test_sync_second_run_reenriches_nothing(db_session, monkeypatch):
    """Once enriched, a v4 row is no longer all-NULL, so a re-sync makes no zone fetch
    and enriches nothing (idempotent)."""
    user = _user(db_session)
    start = _recent_naive()
    summary = [_training_session("v4solo", start, zones_seconds=None, cardio_load=None)]
    zoned = [_training_session("v4solo", start, zones_seconds=(600, 300, 0, 0, 120))]
    ovr = lambda uid, db: _FakeClient(summary, zoned=zoned)
    monkeypatch.setattr(polar, "_valid_client", ovr)

    _client(db_session, user).post("/integrations/polar/sync")
    body2 = _client(db_session, user).post("/integrations/polar/sync").json()
    assert body2["synced"] == 0        # dedup
    assert body2["enriched"] == 0      # already zoned → not targeted


# ── single-emission B: dual-lane bout still emits once (flow_export canonical) ─────

def test_enriched_v4_twin_stays_non_canonical_behind_flow_export(db_session, monkeypatch):
    """A zoneless v4 row and its flow_export twin (v4 synced first, ZIP later) describe
    one bout. Enriching the v4 twin must NOT create a second emission — flow_export
    outranks v4 (#260), so it stays canonical and the bout emits exactly once."""
    user = _user(db_session)
    start = _recent_naive()
    tz = timezone(timedelta(minutes=600))
    st = start.replace(tzinfo=tz)
    sp = (start + timedelta(minutes=30)).replace(tzinfo=tz)

    # flow_export twin (zoned, canonical) + zoneless v4 twin (same bout/interval, same id)
    db_session.add(models.AerobicSession(
        user_id=user.id, source="polar_flow_export", source_session_id="dual",
        session_date=st.date(), start_time=st, stop_time=sp,
        z1_seconds=600, z2_seconds=300, z3_seconds=0, z4_seconds=0, z5_seconds=120,
    ))
    db_session.add(models.AerobicSession(
        user_id=user.id, source="polar_v4", source_session_id="dual",
        session_date=st.date(), start_time=st, stop_time=sp,
        z1_seconds=None, z2_seconds=None, z3_seconds=None, z4_seconds=None, z5_seconds=None,
    ))
    db_session.commit()

    # sync brings nothing new in the summary (both twins already stored); enrichment
    # targets the zoneless v4 row and fills it from the feature fetch.
    zoned = [_training_session("dual", start, zones_seconds=(600, 300, 0, 0, 120))]
    monkeypatch.setattr(polar, "_valid_client", lambda uid, db: _FakeClient([], zoned=zoned))

    body = _client(db_session, user).post("/integrations/polar/sync").json()

    assert body["enriched"] == 1  # the v4 twin WAS enriched
    v4 = db_session.query(models.AerobicSession).filter_by(source="polar_v4").one()
    assert v4.z1_seconds == 600 and v4.z5_seconds == 120

    tr = body["cascade"]["transform"]
    assert tr["events_written"] == 1                    # still exactly one emission
    assert tr["sessions_skipped_non_canonical"] == 1    # the enriched v4 twin
    assert tr["sessions_skipped_no_zones"] == 0
    ev = db_session.query(models.LoadEvent).filter_by(
        user_id=user.id, formula_version=FORMULA_VERSION_METABOLIC).one()
    assert ev.provenance["zone_source"] == "polar_flow_export"  # richer twin wins
