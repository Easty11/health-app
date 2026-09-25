"""Q130 HRV consumption — source-agnostic `/recovery/summary` `hrv` block + Samsung
unification into `hrv_readings` (dual-write helper + held backfill migration SQL).

No network. The DB path runs against the in-memory SQLite `db_session` fixture; the
`/summary` path uses a TestClient with `get_db`/`get_current_user` overridden (the
`test_garmin_hrv` pattern). The Samsung dual-write is tested through the importable
`_mirror_passive_overnight_hrv` helper rather than the `/samsung-hrv/sync` endpoint,
whose Postgres `on_conflict_do_update` does not run on SQLite.

Note on the same-date collapse: the SamsungHRVReading model still declares the stale
2-column `uq_samsung_hrv_user_date`, so the create_all'd test DB cannot hold two contexts
on one (user, date). The backfill's collapse-to-passive_overnight is therefore a prod-only
property (live constraint is `uq_samsung_hrv_user_date_context`, per migration
e1f2a3b4c5d6); here we prove context exclusion across distinct dates plus insert-only /
idempotency, which is what the SQL guard controls.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import models
from auth import get_current_user
from database import get_db
from routers import recovery
from routers.checkin_v2 import AMCheckInIn, _snapshot_passive, _today_aest, get_prefill, submit_am
from routers.samsung_hrv import HRVReadingIn, _mirror_passive_overnight_hrv


# ── import the exact backfill SQL the migration runs ──────────────────────────────
_MIG = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions"
    / "c1d2e3f4a5b6_backfill_samsung_hrv_into_hrv_readings.py"
)
_spec = importlib.util.spec_from_file_location("backfill_mig", _MIG)
_backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backfill)
BACKFILL_SQL = _backfill.BACKFILL_SQL


def _user(db, uid=4):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(recovery.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ── Stage A: scraper dual-write helper ────────────────────────────────────────────

def test_mirror_writes_passive_overnight_into_hrv_readings(db_session):
    user = _user(db_session)
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 1), hrv_ms=48.0, context="passive_overnight"),
    )
    db_session.commit()

    row = db_session.query(models.HrvReading).filter_by(user_id=user.id).one()
    assert (row.source, row.captured_at, row.rmssd_ms) == ("samsung", date(2026, 6, 1), 48.0)
    assert row.status is None and row.baseline_low is None and row.baseline_high is None
    assert row.weekly_avg is None
    assert db_session.query(models.HrvSample).count() == 0   # Samsung is nightly-only


def test_mirror_skips_session_and_calibration_and_null(db_session):
    user = _user(db_session)
    for ctx in ("session", "calibration"):
        _mirror_passive_overnight_hrv(
            db_session, user.id,
            HRVReadingIn(captured_at=date(2026, 6, 2), hrv_ms=50.0, context=ctx),
        )
    # passive_overnight but hrv_ms nulled out of range by the pydantic guard → skipped
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 3), hrv_ms=9999.0, context="passive_overnight"),
    )
    db_session.commit()
    assert db_session.query(models.HrvReading).count() == 0


def test_mirror_rescrape_updates_without_duplicating(db_session):
    user = _user(db_session)
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 4), hrv_ms=50.0, context="passive_overnight"),
    )
    db_session.commit()
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 4), hrv_ms=55.0, context="passive_overnight"),
    )
    db_session.commit()

    rows = db_session.query(models.HrvReading).filter_by(user_id=user.id).all()
    assert len(rows) == 1 and rows[0].rmssd_ms == 55.0


# ── Stage A: held backfill migration SQL ──────────────────────────────────────────

def _seed_samsung(db, uid, cdate, hrv_ms, context="passive_overnight"):
    db.add(models.SamsungHRVReading(
        user_id=uid, captured_at=cdate, hrv_ms=hrv_ms, context=context))


def test_backfill_sql_inserts_only_passive_overnight_with_hrv(db_session):
    user = _user(db_session)
    _seed_samsung(db_session, user.id, date(2026, 5, 1), 40.0, "passive_overnight")   # → insert
    _seed_samsung(db_session, user.id, date(2026, 5, 2), 41.0, "session")             # excluded
    _seed_samsung(db_session, user.id, date(2026, 5, 3), 42.0, "calibration")         # excluded
    _seed_samsung(db_session, user.id, date(2026, 5, 4), None, "passive_overnight")   # null → excluded
    db_session.commit()

    db_session.execute(text(BACKFILL_SQL))
    db_session.commit()

    rows = db_session.query(models.HrvReading).filter_by(user_id=user.id).all()
    assert {(r.captured_at, r.source, r.rmssd_ms) for r in rows} == {
        (date(2026, 5, 1), "samsung", 40.0),
    }
    assert all(r.status is None and r.baseline_low is None for r in rows)


def test_backfill_sql_is_insert_only_and_idempotent(db_session):
    user = _user(db_session)
    # A night already present (e.g. dual-written or a Garmin night): must be untouched.
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=date(2026, 5, 1), source="samsung", rmssd_ms=99.0))
    _seed_samsung(db_session, user.id, date(2026, 5, 1), 40.0, "passive_overnight")   # NOT EXISTS → skip
    _seed_samsung(db_session, user.id, date(2026, 5, 5), 44.0, "passive_overnight")   # absent → insert
    db_session.commit()

    db_session.execute(text(BACKFILL_SQL))
    db_session.commit()

    # Pre-existing row untouched (not overwritten to 40.0), new night inserted.
    kept = db_session.query(models.HrvReading).filter_by(
        user_id=user.id, captured_at=date(2026, 5, 1), source="samsung").one()
    assert kept.rmssd_ms == 99.0
    assert db_session.query(models.HrvReading).filter_by(
        user_id=user.id, captured_at=date(2026, 5, 5)).one().rmssd_ms == 44.0

    before = db_session.query(models.HrvReading).count()
    db_session.execute(text(BACKFILL_SQL))   # second run
    db_session.commit()
    assert db_session.query(models.HrvReading).count() == before   # idempotent — inserts 0


# ── Stage B: source-agnostic /summary hrv block ───────────────────────────────────

def test_summary_hrv_block_populated_for_garmin_only_user(db_session):
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="garmin",
        rmssd_ms=42.0, status="BALANCED", baseline_low=38.0, baseline_high=58.0))
    db_session.commit()

    body = _client(db_session, user).get("/recovery/summary").json()
    hrv = body["hrv"]
    assert hrv["latest"]["source"] == "garmin"
    assert hrv["latest"]["rmssd_ms"] == 42.0
    assert hrv["latest"]["status"] == "BALANCED"
    assert hrv["latest"]["baseline_low"] == 38.0 and hrv["latest"]["baseline_high"] == 58.0
    assert hrv["trend"] == [{"date": cdate.isoformat(), "rmssd": 42.0}]
    assert hrv["baseline_mean"] == 42.0 and hrv["baseline_n"] == 1
    # A Garmin-only user has no Samsung rows — the device block stays empty, not errored.
    assert body["samsung"]["today"] is None and body["samsung"]["baseline_n"] == 0


def test_summary_hrv_block_populated_for_samsung_user(db_session):
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    # Unified row (as the backfill/dual-write would write it).
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="samsung", rmssd_ms=50.0))
    # The device row still exists (sleep lives there) — samsung block reads it.
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=cdate, hrv_ms=50.0, context="passive_overnight"))
    db_session.commit()

    body = _client(db_session, user).get("/recovery/summary").json()
    assert body["hrv"]["latest"]["source"] == "samsung"
    assert body["hrv"]["latest"]["rmssd_ms"] == 50.0
    assert body["hrv"]["baseline_mean"] == 50.0
    # samsung block still populated independently from the device table.
    assert body["samsung"]["today"]["hrv_ms"] == 50.0


def test_summary_both_source_night_shows_canonical_source(db_session):
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="samsung", rmssd_ms=50.0))
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="garmin", rmssd_ms=42.0,
        status="BALANCED"))
    db_session.commit()

    hrv = _client(db_session, user).get("/recovery/summary").json()["hrv"]
    # Garmin outranks Samsung → canonical; exactly one trend entry for the contested night.
    assert hrv["latest"]["source"] == "garmin" and hrv["latest"]["rmssd_ms"] == 42.0
    assert hrv["trend"] == [{"date": cdate.isoformat(), "rmssd": 42.0}]
    assert hrv["baseline_n"] == 1


def test_summary_device_blocks_byte_identical_to_pre_change_snapshot(db_session):
    """Adding `hrv` must not disturb the `samsung`/`health_connect` keys."""
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=cdate, hrv_ms=50.0, sleep_hr_bpm=54,
        context="passive_overnight"))
    db_session.add(models.HealthConnectSync(
        user_id=user.id, date=cdate, steps=8000, resting_heart_rate=52,
        synced_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)))
    # A hrv_readings row too, to prove the hrv block is built without touching the others.
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="garmin", rmssd_ms=42.0))
    db_session.commit()

    body = _client(db_session, user).get("/recovery/summary").json()

    # samsung block — exactly the pre-change shape/values.
    assert body["samsung"] == {
        "today": {
            "captured_at": cdate.isoformat(),
            "hrv_ms": 50.0,
            "sleep_hr_bpm": 54,
            "respiratory_rate": None,
            "spo2_average_pct": None,
            "sleep_efficiency_pct": None,
            "sleep_duration_minutes": None,
            "deep_minutes": None,
            "rem_minutes": None,
            "light_minutes": None,
            "awake_minutes": None,
            "bedtime": None,
            "wake_time": None,
        },
        "trend": [{"date": cdate.isoformat(), "rmssd": 50.0}],
        "baseline_mean": 50.0,
        "baseline_sd": None,
        "baseline_n": 1,
    }
    # health_connect block — unchanged.
    assert body["health_connect"] == {
        # SQLite does not preserve tz on the DateTime(timezone=True) round-trip, so the
        # isoformat is naive here; on Postgres it carries +00:00. Substrate detail — the
        # point of this test is that adding `hrv` leaves this block untouched.
        "last_synced": "2026-06-01T10:00:00",
        "date": cdate.isoformat(),
        "steps": 8000,
        "resting_heart_rate": 52,
        "hrv_rmssd": None,
        "sleep_duration_minutes": None,
        "sleep_score": None,
        "total_days_synced": 1,
    }
    assert body["has_data"] is True


# ── Stage B (consumption): the check-in HRV reads the CURRENT wake-day live ──────
#
# HRV staleness (#327): `_snapshot_passive` no longer snapshots HRV (sleep only), and Save
# no longer writes daily_records.passive_hrv_ms. The prefill tile reads
# `select_wakeday_hrv(require_current_day=True)` — Garmin headlines a same-wake-day pair
# (both surfaced) — and `hrv_vs_baseline` is the SAME primary source's deviation from its
# own rolling baseline. These replace four `_snapshot_passive(...)["passive_hrv_ms"]` tests:
# garmin-only / samsung-only carry over as prefill tests; the contested-night test changes
# MEANING (the check-in tile follows the selector's Garmin-primary headline, not the
# deviation model's highest-weight representative — that rule still governs the gated
# deviation object, pinned in test_hrv_deviation); the "later night must not leak" test is
# subsumed by day-equality and replaced by a Save-writes-nothing test.


def _prefill(db, user):
    return get_prefill(current_user=user, db=db)


def test_prefill_garmin_only_night_returns_garmin_rmssd(db_session):
    user = _user(db_session)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=_today_aest(), source="garmin", rmssd_ms=42.0))
    db_session.commit()

    out = _prefill(db_session, user)
    assert (out.hrv_ms, out.hrv_source, out.hrv_state) == (42.0, "garmin", "value")


def test_prefill_samsung_only_night_returns_samsung_rmssd(db_session):
    user = _user(db_session)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=_today_aest(), source="samsung", rmssd_ms=50.0))
    db_session.commit()

    out = _prefill(db_session, user)
    assert (out.hrv_ms, out.hrv_source) == (50.0, "samsung")


def test_g3_prefill_contested_night_garmin_primary_both_surfaced(db_session):
    """G3: a same-wake-day pair → Garmin primary, Samsung surfaced as the secondary; the
    baseline delta is GARMIN's own (never Samsung's more mature baseline)."""
    user = _user(db_session)
    today = _today_aest()
    for i in range(1, 11):    # Samsung: fuller baseline (higher deviation-model weight)
        db_session.add(models.HrvReading(
            user_id=user.id, captured_at=today - timedelta(days=i),
            source="samsung", rmssd_ms=50.0))
    for i in range(1, 3):     # Garmin: thin baseline @40
        db_session.add(models.HrvReading(
            user_id=user.id, captured_at=today - timedelta(days=i),
            source="garmin", rmssd_ms=40.0))
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=today, source="samsung", rmssd_ms=50.0),
        models.HrvReading(user_id=user.id, captured_at=today, source="garmin", rmssd_ms=42.0),
    ])
    db_session.commit()

    out = _prefill(db_session, user)
    assert out.hrv_state == "pair"
    assert (out.hrv_ms, out.hrv_source) == (42.0, "garmin")
    assert (out.hrv_secondary_ms, out.hrv_secondary_source) == (50.0, "samsung")
    assert out.hrv_vs_baseline == 2.0             # 42 − Garmin's own mean 40


def test_g2_prefill_only_dead_source_is_stale_withheld_no_number(db_session):
    """G2 (prefill): a dead source's last reading + mature baseline → no number, no delta,
    state stale_withheld (the tile renders "–")."""
    user = _user(db_session)
    today = _today_aest()
    for i in range(20, 48):
        db_session.add(models.HrvReading(
            user_id=user.id, captured_at=today - timedelta(days=i),
            source="samsung", rmssd_ms=113.0))
    db_session.commit()

    out = _prefill(db_session, user)
    assert out.hrv_state == "stale_withheld"
    assert out.hrv_ms is None and out.hrv_vs_baseline is None and out.hrv_source is None


def test_save_does_not_write_passive_hrv_ms_even_with_a_current_day_reading(db_session):
    """S3: Save no longer denormalises HRV — the column is retained read-only for history."""
    user = _user(db_session)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=_today_aest(), source="garmin", rmssd_ms=47.0))
    db_session.commit()

    body = AMCheckInIn(
        morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3)
    record = submit_am(body=body, current_user=user, db=db_session)

    assert record.passive_hrv_ms is None
    assert "passive_hrv_ms" not in _snapshot_passive(user.id, _today_aest(), db_session)


def test_prior_day_garmin_row_is_not_snapshotted_as_today(db_session):
    """End-to-end (#327 recency gate): a Garmin row from YESTERDAY must not flow through
    submit_am's snapshot into today's daily_records.passive_hrv_ms. This test previously
    asserted the opposite (47.0) — that WAS the staleness bug: a prior-day reading
    presented as today's."""
    user = _user(db_session)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=_today_aest() - timedelta(days=1),
        source="garmin", rmssd_ms=47.0))
    db_session.commit()

    body = AMCheckInIn(
        morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3)
    record = submit_am(body=body, current_user=user, db=db_session)

    assert record.passive_hrv_ms is None


# ── G4: MCP readiness reads the AEST wake-day, not the UTC date ────────────────
def test_g4_mcp_readiness_wake_day_is_aest_at_0700():
    """At 07:00 AEST the UTC date is still yesterday. The readiness read keys on the
    Brisbane wake-day, so under the same-wake-day gate it reads TODAY's night."""
    from mcp_server import _aest_wake_day

    seven_am_aest_as_utc = datetime(2026, 9, 23, 21, 0, tzinfo=timezone.utc)  # 07:00 +10
    assert seven_am_aest_as_utc.date() == date(2026, 9, 23)          # the old (wrong) key
    assert _aest_wake_day(seven_am_aest_as_utc) == date(2026, 9, 24)


def test_g4_mcp_readiness_snapshot_uses_the_aest_helper():
    """Structural pin: the readiness tool body passes the AEST wake-day to hrv_deviation,
    never `datetime.now(timezone.utc).date()` (the tool body needs Postgres, so this reads
    its source the way the other mcp tests pin tool bodies)."""
    import inspect as _inspect
    import mcp_server

    src = _inspect.getsource(mcp_server.get_readiness_snapshot)
    dev_call = src[src.index("hrv_deviation("):src.index("representative_source(_dev)")]
    assert "_wake_day" in dev_call
    assert "timezone.utc" not in dev_call


def test_mcp_readiness_hrv_line_never_prints_a_stale_number():
    from mcp_server import _readiness_hrv_line

    wd = date(2026, 9, 24)
    stale = {"stale_sources": [{"source": "samsung", "last_captured_at": date(2026, 9, 4)}]}
    line = _readiness_hrv_line(None, stale, wd)
    assert "113" not in line and "—" in line and "samsung 2026-09-04" in line
    rep = {"source": "garmin", "rmssd": 62.4}
    assert _readiness_hrv_line(rep, {"stale_sources": []}, wd) == "  HRV: 62 ms (garmin, 2026-09-24)"


# ── G2 (S3): passive_sleep_min is SAME wake-day only ─────────────────────────────
def test_g2_yesterdays_hc_sleep_is_not_last_nights(db_session):
    """An HC row for YESTERDAY's wake-day only → the prefill tile is None and Save writes
    passive_sleep_min NULL. (Previously the latest row <= today was taken, so a prior
    night's sleep was shown and frozen as last night's.)"""
    user = _user(db_session)
    db_session.add(models.HealthConnectSync(
        user_id=user.id, date=_today_aest() - timedelta(days=1), sleep_duration_minutes=412))
    db_session.commit()

    assert _prefill(db_session, user).sleep_min is None
    body = AMCheckInIn(
        morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3)
    assert submit_am(body=body, current_user=user, db=db_session).passive_sleep_min is None


def test_s3_todays_hc_sleep_is_shown_and_saved(db_session):
    user = _user(db_session)
    db_session.add(models.HealthConnectSync(
        user_id=user.id, date=_today_aest(), sleep_duration_minutes=341))
    db_session.commit()

    assert _prefill(db_session, user).sleep_min == 341
    body = AMCheckInIn(
        morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3)
    assert submit_am(body=body, current_user=user, db=db_session).passive_sleep_min == 341
