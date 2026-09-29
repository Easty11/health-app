"""Polar ingest core (`polar_ingest.sync_user`, Q154) and the manual Sync route's contract.

G1 — core, request-free:
  * not connected → NotConnected; expired token + failed refresh → TokenRefreshFailed;
    summary-list failure and zone-fetch failure → PolarApiError; none of them HTTPException.
  * happy path stores + enriches; `run_cascade=False` never calls the cascade,
    `run_cascade=True` calls it exactly once.
  * TRANSPORT (#166 companion): one happy path runs the REAL PolarV4Client over a faked
    httpx layer (summary list, then the `features=zones` one-day fetch), from a stored,
    non-expired token row — no client-method stub.

G2 — `POST /integrations/polar/sync` delegates to the core with its contract unchanged:
  response keys and order, default 365-day window, and the 404 / 424 / 502 mappings with
  the pre-extraction `detail` strings.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import models
import polar_ingest
from auth import get_current_user
from database import get_db
from encryption import encrypt
from routers import polar


# ── fixtures ──────────────────────────────────────────────────────────────────────

def _training_session(sid: str, start: datetime, *, zones_seconds: tuple | None = (600, 300, 0, 0, 120)) -> dict:
    """A v4 training-session body; `zones_seconds` None → zoneless (summary transport)."""
    stop = start + timedelta(minutes=30)
    body: dict = {
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "stopTime": stop.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezoneOffsetMinutes": 600,  # AEST
        "identifier": {"id": sid},
        "sport": {"id": 1},
        "hrAvg": 150, "hrMax": 175, "calories": 300,
        "durationMillis": 30 * 60 * 1000,
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


def _polar_tokens(db, uid=1, *, expired=False):
    expires_at = datetime.now(timezone.utc) + (timedelta(hours=-1) if expired else timedelta(hours=6))
    db.add(models.UserIntegration(user_id=uid, provider="polar", api_key_encrypted=encrypt(json.dumps({
        "access_token": "tok", "refresh_token": "refresh-me",
        "expires_at": expires_at.isoformat(), "scope": None, "token_type": "bearer",
    }))))
    db.commit()


def _recent_naive(days_ago=10, hour=6) -> datetime:
    d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
    return datetime(d.year, d.month, d.day, hour, 0)


class _FakeClient:
    def __init__(self, summary, zoned=None, *, list_raises=None, zones_raises=None):
        self._summary, self._zoned = summary, zoned or []
        self._list_raises, self._zones_raises = list_raises, zones_raises
        self.list_windows: list[tuple[date, date]] = []

    def list_training_sessions_chunked(self, start, end):
        self.list_windows.append((start, end))
        if self._list_raises:
            raise self._list_raises
        return self._summary

    def list_zoned_sessions(self, days):
        if self._zones_raises:
            raise self._zones_raises
        return self._zoned


def _fake(monkeypatch, client):
    monkeypatch.setattr(polar_ingest, "valid_client", lambda uid, db: client)
    return client


def _cascade_recorder(monkeypatch):
    calls: list[int] = []

    def _rec(db, user_id):
        calls.append(user_id)
        return {"recorded": True}

    monkeypatch.setattr(polar_ingest, "run_metabolic_cascade", _rec)
    return calls


def _http(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(polar.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ── G1: failures raise the core's plain exceptions ─────────────────────────────────

def test_not_connected_raises_not_connected(db_session):
    _user(db_session)
    with pytest.raises(polar_ingest.NotConnected):
        polar_ingest.sync_user(db_session, 1, days=30)


def test_token_refresh_failure_raises_token_refresh_failed(db_session, monkeypatch):
    _user(db_session)
    _polar_tokens(db_session, expired=True)

    def _boom(refresh_token):
        raise RuntimeError("Polar refresh endpoint returned 400")

    monkeypatch.setattr(polar_ingest, "refresh_access_token", _boom)
    with pytest.raises(polar_ingest.TokenRefreshFailed) as ei:
        polar_ingest.sync_user(db_session, 1, days=30)
    assert not isinstance(ei.value, HTTPException)
    assert str(ei.value) == "Polar token refresh failed: Polar refresh endpoint returned 400"


def test_summary_api_error_raises_polar_api_error(db_session, monkeypatch):
    _user(db_session)
    _fake(monkeypatch, _FakeClient([], list_raises=RuntimeError("503 upstream")))
    with pytest.raises(polar_ingest.PolarApiError) as ei:
        polar_ingest.sync_user(db_session, 1, days=30)
    assert str(ei.value) == "Polar v4 API error: 503 upstream"
    assert db_session.query(models.AerobicSession).count() == 0


def test_zone_fetch_error_raises_polar_api_error_after_summary_commit(db_session, monkeypatch):
    _user(db_session)
    summary = [_training_session("v4a", _recent_naive(), zones_seconds=None)]
    _fake(monkeypatch, _FakeClient(summary, zones_raises=RuntimeError("400 window")))
    with pytest.raises(polar_ingest.PolarApiError) as ei:
        polar_ingest.sync_user(db_session, 1, days=30)
    assert str(ei.value) == "Polar v4 zone fetch error: 400 window"
    # pass 1 had already committed: the zoneless row is stored, enrichment retried next run
    assert db_session.query(models.AerobicSession).filter_by(source="polar_v4").count() == 1


# ── G1: happy path + the cascade switch ────────────────────────────────────────────

def test_happy_path_stores_enriches_and_skips_cascade_when_off(db_session, monkeypatch):
    _user(db_session)
    start = _recent_naive()
    client = _fake(monkeypatch, _FakeClient(
        [_training_session("v4a", start, zones_seconds=None)],
        zoned=[_training_session("v4a", start)],
    ))
    cascade_calls = _cascade_recorder(monkeypatch)

    out = polar_ingest.sync_user(db_session, 1, days=30, run_cascade=False)

    assert out == {"synced": 1, "enriched": 1, "available": 1}  # no "cascade" key
    assert cascade_calls == []
    row = db_session.query(models.AerobicSession).filter_by(source="polar_v4").one()
    assert [row.z1_seconds, row.z2_seconds, row.z3_seconds, row.z4_seconds, row.z5_seconds] == [600, 300, 0, 0, 120]
    # the window is the caller's `days`, ending tomorrow (UTC)
    today = datetime.now(timezone.utc).date()
    assert client.list_windows == [(today - timedelta(days=30), today + timedelta(days=1))]


def test_run_cascade_true_calls_cascade_once(db_session, monkeypatch):
    _user(db_session)
    _fake(monkeypatch, _FakeClient([_training_session("v4a", _recent_naive())]))
    cascade_calls = _cascade_recorder(monkeypatch)

    out = polar_ingest.sync_user(db_session, 1, days=30)  # run_cascade defaults True

    assert cascade_calls == [1]
    assert out["cascade"] == {"recorded": True}


def test_happy_path_over_faked_transport(db_session, monkeypatch):
    """Real token row → real `valid_client` → real PolarV4Client, httpx faked: the summary
    call carries no feature; the enrichment call is `features=zones` over one day."""
    _user(db_session)
    _polar_tokens(db_session)
    start = _recent_naive()
    calls: list[dict] = []

    def fake_get(self, url, headers=None, params=None):
        calls.append(dict(params))
        zoned = params.get("features") == "zones"
        body = {"trainingSessions": [_training_session("v4t", start, zones_seconds=(600, 300, 0, 0, 120) if zoned else None)]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    out = polar_ingest.sync_user(db_session, 1, days=30, run_cascade=False)

    assert out == {"synced": 1, "enriched": 1, "available": 1}
    assert "features" not in calls[0]
    assert calls[-1]["features"] == "zones"
    assert calls[-1]["from"] == f"{start.date()}T00:00:00"
    assert calls[-1]["to"] == f"{start.date() + timedelta(days=1)}T00:00:00"
    row = db_session.query(models.AerobicSession).filter_by(source="polar_v4").one()
    assert row.z5_seconds == 120


# ── G2: route contract ─────────────────────────────────────────────────────────────

def test_sync_route_response_shape_and_default_window(db_session, monkeypatch):
    user = _user(db_session)
    start = _recent_naive()
    client = _fake(monkeypatch, _FakeClient(
        [_training_session("v4a", start, zones_seconds=None)],
        zoned=[_training_session("v4a", start)],
    ))

    resp = _http(db_session, user).post("/integrations/polar/sync")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert list(body) == ["synced", "enriched", "available", "cascade", "coverage", "notice"]
    assert (body["synced"], body["enriched"], body["available"]) == (1, 1, 1)
    assert body["cascade"]["transform"]["events_written"] == 1  # route keeps the cascade ON
    today = datetime.now(timezone.utc).date()
    assert client.list_windows == [(today - timedelta(days=365), today + timedelta(days=1))]


def test_sync_route_not_connected_is_404(db_session):
    user = _user(db_session)
    resp = _http(db_session, user).post("/integrations/polar/sync")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Polar not connected"}


def test_sync_route_token_refresh_failure_is_424(db_session, monkeypatch):
    user = _user(db_session)
    _polar_tokens(db_session, expired=True)

    def _boom(refresh_token):
        raise RuntimeError("Polar refresh endpoint returned 400")

    monkeypatch.setattr(polar_ingest, "refresh_access_token", _boom)
    resp = _http(db_session, user).post("/integrations/polar/sync")
    assert resp.status_code == 424
    assert resp.json() == {"detail": "Polar token refresh failed: Polar refresh endpoint returned 400"}


def test_sync_route_api_error_is_502(db_session, monkeypatch):
    user = _user(db_session)
    _fake(monkeypatch, _FakeClient([], list_raises=RuntimeError("503 upstream")))
    resp = _http(db_session, user).post("/integrations/polar/sync")
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Polar v4 API error: 503 upstream"}


def test_sync_route_zone_fetch_error_is_502(db_session, monkeypatch):
    user = _user(db_session)
    summary = [_training_session("v4a", _recent_naive(), zones_seconds=None)]
    _fake(monkeypatch, _FakeClient(summary, zones_raises=RuntimeError("400 window")))
    resp = _http(db_session, user).post("/integrations/polar/sync")
    assert resp.status_code == 502
    assert resp.json() == {"detail": "Polar v4 zone fetch error: 400 window"}
