"""Garmin HRV server-side ingestion lane — normalisation, bounds, idempotency,
refresh-token writeback, reconnect-not-500, and read-time arbitration.

No live Garmin call: the connector's underlying `garminconnect.Garmin` is a fake, and
`GarminClient.from_token` is monkeypatched where the endpoint/service builds a client.
Fixtures are canned `/hrv-service/hrv/{date}` payloads checked against hand-computed
oracles (the reconciliation-fixture pattern).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from connectors.garmin import (
    GarminClient,
    GarminReconnectError,
    normalize_hrv_day,
)
from encryption import decrypt, encrypt
from reads.recovery_reads import arbitrate, canonical_hrv
from routers import garmin


# ── canned Garmin HRV payloads ────────────────────────────────────────────────────

def _hrv_payload(
    cdate: str,
    *,
    last_night_avg=42,
    weekly_avg=45,
    status="BALANCED",
    baseline=(38, 58),
    readings=((("2026-08-15T05:00:00.0"), 44), (("2026-08-15T05:05:00.0"), 40)),
) -> dict:
    """One `/hrv-service/hrv/{date}` response body."""
    return {
        "hrvSummary": {
            "calendarDate": cdate,
            "weeklyAvg": weekly_avg,
            "lastNightAvg": last_night_avg,
            "status": status,
            "baseline": {"balancedLow": baseline[0], "balancedUpper": baseline[1]},
        },
        "hrvReadings": [{"readingTimeGMT": t, "hrvValue": v} for t, v in readings],
    }


class _FakeGarmin:
    """Stands in for `garminconnect.Garmin` — serves canned days by date, records the
    token blob it would dump (for writeback assertions)."""

    def __init__(self, by_date: dict[str, dict], token: str = "REFRESHED_TOKEN_BLOB"):
        self._by_date = by_date
        self._token = token

        class _Client:
            def __init__(self, token):
                self._token = token

            def dumps(self):
                return self._token

        self.client = _Client(token)

    def get_hrv_data(self, cdate):
        return self._by_date.get(cdate)


# ── normalisation vs oracle ─────────────────────────────────────────────────────

def test_normalize_maps_summary_and_series_to_storage_shape():
    out = normalize_hrv_day(_hrv_payload("2026-08-15"), "2026-08-15")
    assert out["captured_at"] == date(2026, 8, 15)
    assert out["reading"] == {
        "rmssd_ms": 42.0,
        "status": "BALANCED",
        "baseline_low": 38.0,
        "baseline_high": 58.0,
        "weekly_avg": 45.0,
    }
    assert out["samples"] == [
        {"reading_time": datetime(2026, 8, 15, 5, 0, 0, tzinfo=timezone.utc), "rmssd_ms": 44.0},
        {"reading_time": datetime(2026, 8, 15, 5, 5, 0, tzinfo=timezone.utc), "rmssd_ms": 40.0},
    ]


def test_normalize_falls_back_to_queried_date_when_summary_omits_it():
    payload = _hrv_payload("2026-08-15")
    del payload["hrvSummary"]["calendarDate"]
    out = normalize_hrv_day(payload, "2026-08-15")
    assert out["captured_at"] == date(2026, 8, 15)


def test_normalize_skips_empty_day():
    assert normalize_hrv_day(None, "2026-08-15") is None
    assert normalize_hrv_day({"hrvSummary": {}, "hrvReadings": []}, "2026-08-15") is None


def test_get_hrv_range_loops_days_and_drops_empty(monkeypatch):
    by_date = {
        "2026-08-15": _hrv_payload("2026-08-15"),
        # 2026-08-16 absent → Garmin has no data → dropped
        "2026-08-17": _hrv_payload("2026-08-17", readings=(("2026-08-17T05:00:00.0", 50),)),
    }
    client = GarminClient(_FakeGarmin(by_date))
    days = client.get_hrv_range(date(2026, 8, 15), date(2026, 8, 17))
    assert [d["captured_at"] for d in days] == [date(2026, 8, 15), date(2026, 8, 17)]


# ── bounds: out-of-range RMSSD nulled/skipped, siblings kept ─────────────────────

def test_bounds_null_nightly_avg_skip_bad_sample_keep_rest():
    payload = _hrv_payload(
        "2026-08-15",
        last_night_avg=9999,          # absurd RMSSD → nulled
        weekly_avg=45,                # valid → kept
        readings=(
            ("2026-08-15T05:00:00.0", 0),      # 0 ms out of range → skipped
            ("2026-08-15T05:05:00.0", 44),     # valid → kept
            ("2026-08-15T05:10:00.0", 500),    # >400 → skipped
        ),
    )
    out = normalize_hrv_day(payload, "2026-08-15")
    assert out["reading"]["rmssd_ms"] is None
    assert out["reading"]["weekly_avg"] == 45.0        # sibling survives
    assert out["reading"]["status"] == "BALANCED"      # sibling survives
    assert out["samples"] == [
        {"reading_time": datetime(2026, 8, 15, 5, 5, 0, tzinfo=timezone.utc), "rmssd_ms": 44.0},
    ]


# ── DB path: user + client harness ───────────────────────────────────────────────

def _user(db, uid=1):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _connect_garmin(db, uid, token="INITIAL_TOKEN_BLOB"):
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encrypt(token)))
    db.commit()


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(garmin.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _patch_from_token(monkeypatch, fake_garmin):
    """Make GarminClient.from_token (used inside the service) return a client wrapping
    the fake — no network, no real auth."""
    monkeypatch.setattr(
        garmin.GarminClient, "from_token",
        classmethod(lambda cls, token_json: GarminClient(fake_garmin)),
    )


# ── idempotency: re-run overwrites parent, replaces children, no dup ─────────────

def test_sync_is_idempotent_and_replaces_children(db_session, monkeypatch):
    user = _user(db_session)
    _connect_garmin(db_session, user.id)

    first = _FakeGarmin({"2026-08-15": _hrv_payload("2026-08-15")})
    _patch_from_token(monkeypatch, first)
    r1 = garmin.sync_hrv_for_user(db_session, user.id, date(2026, 8, 15), date(2026, 8, 15))
    assert r1["readings_upserted"] == 1 and r1["samples_upserted"] == 2

    reading = db_session.query(models.HrvReading).filter_by(user_id=user.id).one()
    first_id = reading.id
    assert reading.rmssd_ms == 42.0

    # Re-run the same night with a changed summary + a single (different) sample.
    second = _FakeGarmin({
        "2026-08-15": _hrv_payload(
            "2026-08-15", last_night_avg=55,
            readings=(("2026-08-15T06:00:00.0", 60),),
        )
    })
    _patch_from_token(monkeypatch, second)
    garmin.sync_hrv_for_user(db_session, user.id, date(2026, 8, 15), date(2026, 8, 15))

    rows = db_session.query(models.HrvReading).filter_by(user_id=user.id).all()
    assert len(rows) == 1                      # no duplicate parent
    assert rows[0].id == first_id              # same row, overwritten in place
    assert rows[0].rmssd_ms == 55.0            # summary overwritten

    samples = db_session.query(models.HrvSample).filter_by(hrv_reading_id=first_id).all()
    assert len(samples) == 1                    # children replaced, not appended
    assert samples[0].rmssd_ms == 60.0


# ── refresh-token writeback ───────────────────────────────────────────────────────

def test_refresh_token_is_written_back_encrypted(db_session, monkeypatch):
    user = _user(db_session)
    _connect_garmin(db_session, user.id, token="INITIAL_TOKEN_BLOB")

    fake = _FakeGarmin({"2026-08-15": _hrv_payload("2026-08-15")}, token="REFRESHED_TOKEN_BLOB")
    _patch_from_token(monkeypatch, fake)
    garmin.sync_hrv_for_user(db_session, user.id, date(2026, 8, 15), date(2026, 8, 15))

    row = db_session.query(models.UserIntegration).filter_by(user_id=user.id, provider="garmin").one()
    assert decrypt(row.api_key_encrypted) == "REFRESHED_TOKEN_BLOB"


# ── auth failure → reconnect state, never 500 ─────────────────────────────────────

def test_from_token_maps_auth_error_to_reconnect(monkeypatch):
    from garminconnect import GarminConnectAuthenticationError

    class _DeadGarmin:
        def login(self, token_json):
            raise GarminConnectAuthenticationError("token expired")

    monkeypatch.setattr("connectors.garmin.Garmin", lambda *a, **k: _DeadGarmin())
    with pytest.raises(GarminReconnectError):
        GarminClient.from_token("dead-blob")


def test_sync_endpoint_returns_424_on_reconnect(db_session, monkeypatch):
    user = _user(db_session)
    _connect_garmin(db_session, user.id)

    def _raise(cls, token_json):
        raise GarminReconnectError("token can no longer authenticate")

    monkeypatch.setattr(garmin.GarminClient, "from_token", classmethod(_raise))
    client = _client(db_session, user)
    resp = client.post("/integrations/garmin/sync?from=2026-08-15&to=2026-08-15")
    assert resp.status_code == 424
    assert "reconnect" in resp.json()["detail"].lower()


def test_sync_endpoint_404_when_not_connected(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    resp = client.post("/integrations/garmin/sync")
    assert resp.status_code == 404


# ── token endpoint stores encrypted, never plaintext ─────────────────────────────

def test_token_endpoint_stores_encrypted_blob(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    resp = client.post("/integrations/garmin/token", json={"token": "TOKEN_BLOB_XYZ"})
    assert resp.status_code == 201

    row = db_session.query(models.UserIntegration).filter_by(user_id=user.id, provider="garmin").one()
    assert row.api_key_encrypted != "TOKEN_BLOB_XYZ"          # not plaintext
    assert decrypt(row.api_key_encrypted) == "TOKEN_BLOB_XYZ"


def test_token_endpoint_rejects_empty(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    resp = client.post("/integrations/garmin/token", json={"token": "   "})
    assert resp.status_code == 422


# ── arbitration ───────────────────────────────────────────────────────────────────

class _Row:
    """Minimal stand-in for an HrvReading for the pure arbitrate() test."""
    def __init__(self, user_id, captured_at, source, id):
        self.user_id = user_id
        self.captured_at = captured_at
        self.source = source
        self.id = id
        self.canonical = None


def test_arbitrate_single_source_night_is_canonical():
    rows = [_Row(1, date(2026, 8, 15), "garmin", 10)]
    arbitrate(rows)
    assert rows[0].canonical is True


def test_arbitrate_contested_night_higher_rank_wins():
    garmin_row = _Row(1, date(2026, 8, 15), "garmin", 10)
    samsung_row = _Row(1, date(2026, 8, 15), "samsung", 11)
    arbitrate([samsung_row, garmin_row])
    assert garmin_row.canonical is True
    assert samsung_row.canonical is False
    # Exactly one canonical in the contested night.
    assert sum(1 for r in (garmin_row, samsung_row) if r.canonical) == 1


def test_arbitrate_separate_nights_each_canonical():
    a = _Row(1, date(2026, 8, 15), "garmin", 10)
    b = _Row(1, date(2026, 8, 16), "garmin", 11)
    arbitrate([a, b])
    assert a.canonical is True and b.canonical is True


def test_canonical_hrv_windows_and_flags(db_session):
    user = _user(db_session)
    # Two nights, both single-source Garmin.
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=date(2026, 8, 14), source="garmin", rmssd_ms=40),
        models.HrvReading(user_id=user.id, captured_at=date(2026, 8, 15), source="garmin", rmssd_ms=42),
    ])
    db_session.commit()

    rows = canonical_hrv(user.id, db_session, since=date(2026, 8, 15))
    assert len(rows) == 1
    assert rows[0].captured_at == date(2026, 8, 15)
    assert rows[0].canonical is True
