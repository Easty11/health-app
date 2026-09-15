"""Multi-source HRV on the recovery surfaces — the card (`/health/summary`) and the MCP
`get_recovery_metrics` table now show the newest reading ACROSS sources with its source
label, instead of a Samsung-scoped view that could never surface Garmin.

Decision gate (DECISIONS_LOG — "Garmin HRV surfaces on the recovery card"): Garmin HRV
rows land in `hrv_readings` (source='garmin'); the card's `/health/summary` and the MCP
recovery table were both Samsung-scoped, so a Garmin night was invisible even once
ingested. These tests pin: (1) newest-across-sources selection with a deterministic
tie-break to the richer source, (2) the source label travelling in the payload, (3) no
Samsung history dropped, (4) Samsung-native baseline never pinned to a Garmin number, and
(5) the multi-source formatter never collapsing or dropping a source.

No network. `/health/summary` runs against the in-memory SQLite `db_session` via a
TestClient with `get_db`/`get_current_user` overridden (the `test_hrv_consumption`
pattern); the MCP formatter is exercised as a pure helper (the `test_mcp_as_of_stamp`
pattern — the `@mcp.tool()` body needs Postgres + a bearer token).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from routers import health
from routers.health import _pick_latest_hrv
from mcp_server import _format_recovery_metrics


def _user(db, uid=4):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _summary(db, user) -> dict:
    return _client(db, user).get("/summary").json()


# ── the pure picker ────────────────────────────────────────────────────────────────

def test_pick_latest_hrv_newest_date_wins():
    got = _pick_latest_hrv([
        {"captured_at": date(2026, 9, 14), "hrv_ms": 113, "source": "samsung"},
        {"captured_at": date(2026, 9, 15), "hrv_ms": 78, "source": "garmin"},
    ])
    assert got["source"] == "garmin" and got["hrv_ms"] == 78


def test_pick_latest_hrv_same_night_tie_breaks_to_richer_source():
    got = _pick_latest_hrv([
        {"captured_at": date(2026, 9, 14), "hrv_ms": 113, "source": "samsung"},
        {"captured_at": date(2026, 9, 14), "hrv_ms": 65, "source": "garmin"},
    ])
    assert got["source"] == "garmin" and got["hrv_ms"] == 65


def test_pick_latest_hrv_ignores_null_hrv_and_empty():
    assert _pick_latest_hrv([]) is None
    assert _pick_latest_hrv([{"captured_at": date(2026, 9, 14), "hrv_ms": None, "source": "garmin"}]) is None


# ── /health/summary: source-labelled headline across sources ─────────────────────────

def test_summary_headlines_newest_garmin_over_older_samsung(db_session):
    """The reported bug: Samsung 14th shows while Garmin has the 15th. The card must now
    headline the Garmin 15th, labelled — while Samsung sleep/baseline stay put."""
    user = _user(db_session)
    d14, d15 = date(2026, 9, 14), date(2026, 9, 15)
    # Samsung device row (sleep lives here) + its mirror into hrv_readings.
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=d14, hrv_ms=113.0, sleep_hr_bpm=55,
        deep_minutes=60, rem_minutes=90, context="passive_overnight"))
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=d14, source="samsung", rmssd_ms=113.0))
    # Garmin last-night HRV, newer, no sleep.
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=d15, source="garmin", rmssd_ms=78.0,
        status="BALANCED", baseline_low=40.0, baseline_high=90.0))
    db_session.commit()

    body = _summary(db_session, user)
    assert body["latest_hrv"]["source"] == "garmin"
    assert body["latest_hrv"]["hrv_ms"] == 78.0
    assert body["latest_hrv"]["captured_at"] == d15.isoformat()
    assert body["latest_hrv"]["status"] == "BALANCED"
    # Samsung device block + its native baseline are untouched (sleep still the 14th).
    assert body["latest"]["captured_at"] == d14.isoformat()
    assert body["latest"]["deep_minutes"] == 60
    assert body["vs_baseline"] is not None  # samsung-native, still computed


def test_summary_same_night_tie_labels_garmin_but_keeps_samsung_sleep(db_session):
    user = _user(db_session)
    d = date(2026, 9, 14)
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=d, hrv_ms=113.0, sleep_hr_bpm=55,
        context="passive_overnight"))
    db_session.add(models.HrvReading(user_id=user.id, captured_at=d, source="samsung", rmssd_ms=113.0))
    db_session.add(models.HrvReading(user_id=user.id, captured_at=d, source="garmin", rmssd_ms=65.0))
    db_session.commit()

    body = _summary(db_session, user)
    assert (body["latest_hrv"]["source"], body["latest_hrv"]["hrv_ms"]) == ("garmin", 65.0)
    assert body["latest"]["sleep_hr_bpm"] == 55  # sleep still Samsung's


def test_summary_samsung_only_night_still_labelled_samsung(db_session):
    """No Garmin at all: the headline is the Samsung reading, sourced from the device row
    even when its mirror into hrv_readings is absent (held backfill) — never dropped."""
    user = _user(db_session)
    d = date(2026, 9, 14)
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=d, hrv_ms=113.0, context="passive_overnight"))
    db_session.commit()

    body = _summary(db_session, user)
    assert body["latest_hrv"]["source"] == "samsung"
    assert body["latest_hrv"]["hrv_ms"] == 113.0


def test_summary_garmin_only_user_surfaces_hrv_without_samsung_device_row(db_session):
    """A Garmin-only user has no Samsung device row: the old code returned latest=None and
    showed nothing. The headline HRV must still surface (latest stays None for sleep)."""
    user = _user(db_session)
    d = date(2026, 9, 15)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=d, source="garmin", rmssd_ms=78.0))
    db_session.commit()

    body = _summary(db_session, user)
    assert body["latest"] is None                       # no Samsung sleep
    assert body["latest_hrv"]["source"] == "garmin"     # but HRV is shown
    assert body["latest_hrv"]["hrv_ms"] == 78.0


def test_summary_no_data_returns_null_headline(db_session):
    user = _user(db_session)
    body = _summary(db_session, user)
    assert body["latest"] is None and body["latest_hrv"] is None


def test_summary_preserves_existing_samsung_keys(db_session):
    """Additive: `latest_hrv` is new; every pre-existing key/value is unchanged."""
    user = _user(db_session)
    d = date(2026, 9, 14)
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=d, hrv_ms=50.0, context="passive_overnight"))
    db_session.commit()

    body = _summary(db_session, user)
    assert set(body) == {"latest", "trend", "baseline_hrv", "vs_baseline", "latest_hrv"}
    assert body["baseline_hrv"] == 50.0
    assert body["trend"] == [{"captured_at": d.isoformat(), "hrv_ms": 50.0}]
    assert body["latest"]["hrv_ms"] == 50.0


# ── MCP formatter: both sources, labelled, never collapsed ───────────────────────────

def _row(captured_at, source, hrv_ms, **sleep):
    base = {
        "captured_at": captured_at, "source": source, "hrv_ms": hrv_ms,
        "sleep_hr_bpm": None, "respiratory_rate": None, "sleep_efficiency_pct": None,
        "actual_sleep_time_minutes": None, "deep_minutes": None, "rem_minutes": None,
        "light_minutes": None, "awake_minutes": None, "spo2_average_pct": None,
    }
    base.update(sleep)
    return base


def test_format_recovery_metrics_labels_both_sources_on_one_night():
    rows = [
        _row("2026-09-14", "samsung", 113.0, sleep_hr_bpm=55, deep_minutes=60, rem_minutes=90),
        _row("2026-09-14", "garmin", 65.0),
    ]
    out = _format_recovery_metrics(rows, 7)
    assert "sources: garmin, samsung" in out
    assert "2026-09-14 [samsung]: HRV=113 ms" in out
    assert "2026-09-14 [garmin]: HRV=65 ms" in out
    # Garmin carries no sleep architecture → those fields render as '—', not fabricated.
    garmin_line = next(ln for ln in out.splitlines() if "[garmin]" in ln)
    assert "Deep=—m" in garmin_line and "RHR=—" in garmin_line


def test_format_recovery_metrics_empty():
    assert _format_recovery_metrics([], 7) == "No recovery data found in the last 7 days."
