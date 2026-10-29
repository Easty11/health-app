"""Garmin HRV server-side ingestion lane — normalisation, bounds, idempotency, reconnect-not-500, and
read-time arbitration.

The HRV pull runs through the Personal API only (#449, PR-B): the real `PersonalClient` is driven against a fake
host at the transport layer. `GarminClient.from_token` (the DI token, which now serves the attach route and epoch
SpO2) is monkeypatched where the token endpoint builds a client. Fixtures are canned `/hrv-service/hrv/{date}`
payloads checked against hand-computed oracles (the reconciliation-fixture pattern).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
import garmin_personal_lanes as gpl
from connectors import garmin_personal as gp
from connectors.garmin import (
    GarminClient,
    GarminReconnectError,
    normalize_hrv_day,
)
from encryption import decrypt, encrypt
from garmin_personal_fakes import FAKE_KEY, FakeHost
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


def _connect_personal(db, uid, key=FAKE_KEY):
    db.add(models.UserIntegration(user_id=uid, provider="garmin_personal", api_key_encrypted=encrypt(key)))
    db.commit()


def _connect_di(db, uid, token="INITIAL_TOKEN_BLOB"):
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encrypt(token)))
    db.commit()


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(garmin.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture()
def host(monkeypatch):
    """The fake Personal API host, wired in wherever the service builds a client."""
    h = FakeHost()
    orig = gpl.personal_client
    monkeypatch.setattr(gpl, "personal_client", lambda db, uid, *, transport=None: orig(db, uid, transport=h.transport()))
    return h


def _serve(host, cdate, payload):
    host.set(gp.HRV_PATH.format(date=cdate), payload)


# ── idempotency: re-run overwrites parent, replaces children, no dup ─────────────

def test_sync_is_idempotent_and_replaces_children(db_session, host):
    user = _user(db_session)
    _connect_personal(db_session, user.id)

    _serve(host, "2026-08-15", _hrv_payload("2026-08-15"))
    r1 = garmin.sync_hrv_for_user(db_session, user.id, date(2026, 8, 15), date(2026, 8, 15))
    assert r1["readings_upserted"] == 1 and r1["samples_upserted"] == 2

    reading = db_session.query(models.HrvReading).filter_by(user_id=user.id).one()
    first_id = reading.id
    assert reading.rmssd_ms == 42.0 and reading.transport == "personal_api"

    # Re-run the same night with a changed summary + a single (different) sample.
    _serve(host, "2026-08-15", _hrv_payload("2026-08-15", last_night_avg=55,
                                            readings=(("2026-08-15T06:00:00.0", 60),)))
    garmin.sync_hrv_for_user(db_session, user.id, date(2026, 8, 15), date(2026, 8, 15))

    rows = db_session.query(models.HrvReading).filter_by(user_id=user.id).all()
    assert len(rows) == 1                      # no duplicate parent
    assert rows[0].id == first_id              # same row, overwritten in place
    assert rows[0].rmssd_ms == 55.0            # summary overwritten

    samples = db_session.query(models.HrvSample).filter_by(hrv_reading_id=first_id).all()
    assert len(samples) == 1                    # children replaced, not appended
    assert samples[0].rmssd_ms == 60.0


# ── no personal key: there is no DI fallback ──────────────────────────────────────

class _NoDI:
    """Any DI login on the HRV path is a defect (PR-B)."""
    calls = 0

    @classmethod
    def from_token(cls, token_json):
        cls.calls += 1
        raise AssertionError("the DI lane must not serve HRV")


def test_a_user_with_only_a_DI_token_is_not_pulled_and_never_logs_in_to_DI(db_session, monkeypatch):
    user = _user(db_session)
    _connect_di(db_session, user.id)
    monkeypatch.setattr(garmin.GarminClient, "from_token", _NoDI.from_token)
    with pytest.raises(gpl.NoPersonalKey):
        garmin.sync_hrv_for_user(db_session, user.id, date(2026, 8, 15), date(2026, 8, 15))
    assert _NoDI.calls == 0 and db_session.query(models.HrvReading).count() == 0


def test_refresh_endpoint_reports_no_personal_key_and_never_errors_the_card(db_session, monkeypatch):
    user = _user(db_session)
    _connect_di(db_session, user.id)
    monkeypatch.setattr(garmin.GarminClient, "from_token", _NoDI.from_token)
    resp = _client(db_session, user).post("/integrations/garmin/refresh?force=true")
    assert resp.status_code == 200
    assert resp.json()["skipped"] is True and resp.json()["reason"] == "no_personal_key"


# ── auth failure → reconnect state, never 500 ─────────────────────────────────────

def test_from_token_maps_auth_error_to_reconnect(monkeypatch):
    from garminconnect import GarminConnectAuthenticationError

    class _DeadGarmin:
        def login(self, token_json):
            raise GarminConnectAuthenticationError("token expired")

    monkeypatch.setattr("connectors.garmin.Garmin", lambda *a, **k: _DeadGarmin())
    with pytest.raises(GarminReconnectError):
        GarminClient.from_token("dead-blob")


def test_sync_endpoint_returns_424_when_the_personal_key_is_refused(db_session, host):
    user = _user(db_session)
    _connect_personal(db_session, user.id)
    host.exchange_status = 401
    resp = _client(db_session, user).post("/integrations/garmin/sync?from=2026-08-15&to=2026-08-15")
    assert resp.status_code == 424
    detail = resp.json()["detail"]
    assert "garmin_personal_attach.py" in detail and "garmin_login" not in detail     # the retired pointer (Q242)


def test_sync_endpoint_404_when_not_connected(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    resp = client.post("/integrations/garmin/sync")
    assert resp.status_code == 404


# ── token endpoint stores encrypted, never plaintext ─────────────────────────────

class _AttachFake:
    """The attach path verifies the account first (G4): a client with a profile id and a dump."""

    def __init__(self, blob):
        self._blob = blob

    def profile_id(self):
        return "555001"

    def dump_token(self):
        return self._blob


def test_token_endpoint_stores_encrypted_blob(db_session, monkeypatch):
    user = _user(db_session)
    client = _client(db_session, user)
    monkeypatch.setattr(garmin.GarminClient, "from_token",
                        classmethod(lambda cls, token_json: _AttachFake(token_json)))
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


def test_canonical_hrv_as_of_upper_bounds_and_keeps_night_complete(db_session):
    """as_of is an upper bound (captured_at <= as_of) applied BEFORE arbitration, so a
    contested night on the boundary keeps BOTH source rows in the group — arbitration
    stays complete and deterministic, never truncated mid-night by the bound."""
    user = _user(db_session)
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=date(2026, 8, 14), source="garmin", rmssd_ms=40),
        # 8/15 is contested — both sources report the boundary night.
        models.HrvReading(user_id=user.id, captured_at=date(2026, 8, 15), source="samsung", rmssd_ms=50),
        models.HrvReading(user_id=user.id, captured_at=date(2026, 8, 15), source="garmin", rmssd_ms=42),
        # 8/16 is strictly after the bound — must be excluded.
        models.HrvReading(user_id=user.id, captured_at=date(2026, 8, 16), source="garmin", rmssd_ms=44),
    ])
    db_session.commit()

    rows = canonical_hrv(user.id, db_session, as_of=date(2026, 8, 15))
    assert {r.captured_at for r in rows} == {date(2026, 8, 14), date(2026, 8, 15)}  # 8/16 dropped

    aug15 = [r for r in rows if r.captured_at == date(2026, 8, 15)]
    assert len(aug15) == 2                                   # full contested group retained
    canon15 = [r for r in aug15 if r.canonical]
    assert len(canon15) == 1                                 # exactly one canonical
    assert canon15[0].source == "garmin" and canon15[0].rmssd_ms == 42   # Garmin outranks Samsung

    aug14 = [r for r in rows if r.captured_at == date(2026, 8, 14)]
    assert len(aug14) == 1 and aug14[0].canonical is True    # single-source night canonical

    # since + as_of together window to exactly the boundary night, group still complete.
    windowed = canonical_hrv(
        user.id, db_session, since=date(2026, 8, 15), as_of=date(2026, 8, 15)
    )
    assert {r.captured_at for r in windowed} == {date(2026, 8, 15)}
    assert len(windowed) == 2
