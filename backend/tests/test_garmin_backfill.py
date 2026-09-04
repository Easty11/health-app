"""Garmin HRV historical backfill from the account data export — parse-vs-oracle,
insert-only safety (no sample-wipe), idempotency, and dry-run.

No real export and no network: a synthetic `*healthStatusData.json` written to a temp
dir is checked against a hand-computed oracle, and the DB path runs against the
in-memory SQLite `db_session` fixture. The safety test proves the load can never touch
a live-synced night's 5-min series.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import models
from scripts.garmin_backfill import backfill, parse_export

# Fixture from the brief: normal night, ONBOARDING (0.0 baselines), out-of-bounds
# value, and a null value. Oracle → 2 parsed nights, 2 dropped (bounds + null).
_FIXTURE = [
    {"calendarDate": "2026-06-01", "metrics": [
        {"type": "HRV", "value": 45.0, "baselineLowerLimit": 30.0, "baselineUpperLimit": 60.0, "status": "IN_RANGE"}]},
    {"calendarDate": "2026-06-02", "metrics": [
        {"type": "HRV", "value": 52.0, "baselineLowerLimit": 0.0, "baselineUpperLimit": 0.0, "status": "ONBOARDING"}]},
    {"calendarDate": "2026-06-03", "metrics": [
        {"type": "HRV", "value": 900.0, "baselineLowerLimit": 0.0, "baselineUpperLimit": 0.0, "status": "BELOW"}]},
    {"calendarDate": "2026-06-04", "metrics": [
        {"type": "HRV", "value": None, "status": "ONBOARDING"}]},
]


@pytest.fixture()
def export_dir(tmp_path) -> Path:
    """Write the synthetic export under a directory, named as Garmin names it, so the
    directory-glob path is exercised too."""
    (tmp_path / "1234_healthStatusData.json").write_text(
        json.dumps(_FIXTURE), encoding="utf-8"
    )
    return tmp_path


def _user(db, uid=4):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


# ── parse vs oracle ───────────────────────────────────────────────────────────────

def test_parse_maps_nights_against_oracle(export_dir):
    nights, dropped = parse_export(str(export_dir))

    # 2 valid nights (06-01, 06-02); 2 dropped (06-03 out of bounds, 06-04 null).
    assert dropped == 2
    assert [n["captured_at"] for n in nights] == [date(2026, 6, 1), date(2026, 6, 2)]

    normal = nights[0]
    assert normal["reading"] == {
        "rmssd_ms": 45.0, "baseline_low": 30.0, "baseline_high": 60.0,
    }
    # status / weekly_avg deliberately absent → they land NULL.
    assert "status" not in normal["reading"]
    assert "weekly_avg" not in normal["reading"]
    assert normal["samples"] == []   # export has no 5-min series

    onboarding = nights[1]
    assert onboarding["reading"] == {
        "rmssd_ms": 52.0, "baseline_low": None, "baseline_high": None,  # 0.0 → NULL
    }
    assert onboarding["samples"] == []


# ── normal insert path: status NULL, baselines mapped, samples empty ───────────────

def test_backfill_inserts_absent_nights(db_session, export_dir):
    user = _user(db_session)
    nights, _ = parse_export(str(export_dir))
    stats = backfill(db_session, user.id, "garmin", nights, dry_run=False)

    assert stats["inserted"] == 2 and stats["skipped_existing"] == 0
    assert stats["date_range"] == (date(2026, 6, 1), date(2026, 6, 2))

    rows = {r.captured_at: r for r in
            db_session.query(models.HrvReading).filter_by(user_id=user.id).all()}
    assert set(rows) == {date(2026, 6, 1), date(2026, 6, 2)}

    normal = rows[date(2026, 6, 1)]
    assert (normal.rmssd_ms, normal.baseline_low, normal.baseline_high) == (45.0, 30.0, 60.0)
    assert normal.status is None and normal.weekly_avg is None
    onboarding = rows[date(2026, 6, 2)]
    assert onboarding.rmssd_ms == 52.0
    assert onboarding.baseline_low is None and onboarding.baseline_high is None

    # No samples for any backfilled night.
    assert db_session.query(models.HrvSample).count() == 0


# ── SAFETY (mandatory gate): a pre-existing night is skipped, its samples survive ──

def test_backfill_skips_existing_and_preserves_samples(db_session, export_dir):
    user = _user(db_session)

    # Pre-seed 2026-06-01 as a live-synced night WITH a 5-min sample.
    existing = models.HrvReading(
        user_id=user.id, captured_at=date(2026, 6, 1), source="garmin",
        rmssd_ms=99.0, status="BALANCED",
    )
    db_session.add(existing)
    db_session.flush()
    db_session.add(models.HrvSample(
        hrv_reading_id=existing.id,
        reading_time=datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
        rmssd_ms=88.0,
    ))
    db_session.commit()
    samples_before = db_session.query(models.HrvSample).count()
    assert samples_before == 1

    nights, _ = parse_export(str(export_dir))
    stats = backfill(db_session, user.id, "garmin", nights, dry_run=False)

    # 06-01 skipped (already present), 06-02 inserted.
    assert stats["inserted"] == 1 and stats["skipped_existing"] == 1

    kept = db_session.query(models.HrvReading).filter_by(
        user_id=user.id, captured_at=date(2026, 6, 1), source="garmin").one()
    assert kept.id == existing.id          # same row, untouched
    assert kept.rmssd_ms == 99.0           # NOT overwritten to 45.0
    assert kept.status == "BALANCED"       # NOT overwritten

    # The load can never wipe a live-synced night's series.
    assert db_session.query(models.HrvSample).count() == samples_before
    surviving = db_session.query(models.HrvSample).filter_by(
        hrv_reading_id=existing.id).one()
    assert surviving.rmssd_ms == 88.0


# ── idempotency: a second real run inserts nothing ────────────────────────────────

def test_backfill_is_idempotent(db_session, export_dir):
    user = _user(db_session)
    nights, _ = parse_export(str(export_dir))

    first = backfill(db_session, user.id, "garmin", nights, dry_run=False)
    assert first["inserted"] == 2

    nights2, _ = parse_export(str(export_dir))
    second = backfill(db_session, user.id, "garmin", nights2, dry_run=False)
    assert second["inserted"] == 0 and second["skipped_existing"] == 2
    assert db_session.query(models.HrvReading).filter_by(user_id=user.id).count() == 2


# ── dry-run writes nothing ────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(db_session, export_dir):
    user = _user(db_session)
    nights, dropped = parse_export(str(export_dir))
    stats = backfill(db_session, user.id, "garmin", nights, dry_run=True)

    assert stats["inserted"] == 2          # reports what a real run WOULD do
    assert dropped == 2
    assert db_session.query(models.HrvReading).count() == 0   # but wrote nothing
    assert db_session.query(models.HrvSample).count() == 0
