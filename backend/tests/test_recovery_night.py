"""Per-field resolution of `get_recovery_metrics` (reads/recovery_night.py).

The reported defect: on a Garmin night the tool printed sleep, SpO2 and RHR blank although the
data was in prod. Two causes -- the Garmin branch hardcoded NULL for those fields, and the
Health Connect fallback fired only when the Samsung+HRV union returned ZERO rows, so one Garmin
HRV row suppressed every other source. These tests pin: each field resolves to its own best
source and names it; the sleep order is SLEEP_WRITER_PRIORITY; stages come from one writer;
HRV is never ranked; the resting-HR slot is never filled from a non-resting figure; a new
source slots in by rank alone; absent is '—', never zero.

No network. The loader runs on the in-memory SQLite `db_session`.
"""
from datetime import date, datetime, timedelta, timezone

import models
from reads.recovery_night import (
    FIELD_RANK, SLEEP_RANK, format_night, format_recovery, load_candidates, resolve, resolve_night,
)
from reads.snapshot_reads import SLEEP_WRITER_PRIORITY

NIGHT = date(2026, 10, 24)
GARMIN_PKG = "com.garmin.android.apps.connectmobile"
SAMSUNG_PKG = "com.sec.android.app.shealth"


def _user(db, email="rn@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── resolution (pure) ────────────────────────────────────────────────────────────────────

def test_each_field_takes_its_own_best_source_and_names_it():
    line = format_night(resolve_night(NIGHT, {
        "garmin": {"hrv": 67.0, "spo2": 96.6, "spo2_min": 90.0},
        "garmin_hc": {"tst": 387, "deep": 68, "rem": 59, "light": 260, "sleep_nadir_hr": 49.1},
        "samsung_scraper": {"efficiency": 91, "rr": 14.5},
    }))
    assert "HRV=67 ms [garmin]" in line
    assert "TST=387 min [garmin/HC]" in line
    assert "Deep=68m REM=59m Light=260m Awake=— [garmin/HC]" in line
    assert "SpO2=96.6% (min 90%) [garmin]" in line
    assert "Eff=91% [samsung scraper]" in line and "RR=14.5 br/min [samsung scraper]" in line
    assert "Sleep-nadir HR=49 bpm [garmin/HC]" in line


def test_a_source_that_carries_only_some_fields_does_not_blank_the_others():
    """The row-level gate: a Garmin HRV row used to stop every other source being read."""
    r = resolve_night(NIGHT, {"garmin": {"hrv": 60.0}, "samsung_scraper": {"tst": 410, "sleep_hr": 52}})
    assert r["tst"]["source"] == "samsung_scraper" and r["sleep_hr"]["source"] == "samsung_scraper"
    assert [s for s, _ in r["hrv"]] == ["garmin"]


def test_sleep_order_is_the_snapshot_writer_priority_with_the_scraper_below_every_hc_writer():
    assert SLEEP_RANK[: len(SLEEP_WRITER_PRIORITY)] == tuple(f"{k}_hc" for k in SLEEP_WRITER_PRIORITY)
    assert SLEEP_RANK[-1] == "samsung_scraper"
    r = resolve_night(NIGHT, {"garmin_hc": {"tst": 390}, "samsung_hc": {"tst": 400},
                              "samsung_scraper": {"tst": 410}})
    assert (r["tst"]["source"], r["tst"]["value"]["tst"]) == ("garmin_hc", 390)


def test_stages_come_from_one_writer_never_mixed():
    # Garmin/HC has no awake minutes; the scraper's awake must not be spliced in under Garmin's stages.
    r = resolve_night(NIGHT, {"garmin_hc": {"deep": 60, "rem": 70, "light": 250},
                              "samsung_scraper": {"deep": 90, "rem": 90, "light": 200, "awake": 33}})
    assert r["stages"]["source"] == "garmin_hc"
    assert r["stages"]["value"] == {"deep": 60, "rem": 70, "light": 250, "awake": None}


def test_a_blended_hc_night_gives_duration_but_withholds_the_stage_split():
    r = resolve_night(NIGHT, {"hc_multiple": {"tst": 420, "deep": 60, "rem": 70, "light": 290}})
    assert r["tst"]["source"] == "hc_multiple"
    assert r["stages"] is None


def test_hrv_is_never_ranked_each_instrument_is_shown():
    r = resolve_night(NIGHT, {"garmin": {"hrv": 65.0}, "samsung_scraper": {"hrv": 113.0},
                              "hc_utc_day": {"hrv": 50.0}})
    assert r["hrv"] == [("garmin", 65.0), ("samsung_scraper", 113.0)]       # the HC fallback stays out


def test_the_resting_hr_slot_is_never_filled_from_a_non_resting_figure():
    line = format_night(resolve_night(NIGHT, {
        "garmin_hc": {"sleep_nadir_hr": 49.0}, "hc_aest_day": {"all_day_median_hr": 144.0},
        "samsung_scraper": {"sleep_hr": 55}}))
    assert "RHR=— (no daily-RHR source yet)" in line
    assert "Sleep-nadir HR=49 bpm" in line and "Sleep HR=55 bpm" in line and "All-day median HR=144 bpm" in line


def test_a_new_source_slots_in_by_rank_with_no_other_change():
    """The Personal API migration adds a loader under `garmin_api`; the reader needs no edit."""
    assert FIELD_RANK["daily_rhr"][0] == "garmin_api"
    line = format_night(resolve_night(NIGHT, {"garmin_api": {"daily_rhr": 52.0}}))
    assert "RHR=52 bpm [garmin personal API]" in line


def test_absent_fields_print_a_dash_never_zero():
    line = format_night(resolve_night(NIGHT, {"garmin": {"hrv": 40.0}}))
    for label in ("TST=—", "Eff=—", "SpO2=—", "RR=—", "Sleep-nadir HR=—", "Sleep HR=—"):
        assert label in line
    assert "=0" not in line


def test_a_real_zero_is_kept():
    assert "REM=0m" in format_night(resolve_night(NIGHT, {"garmin_hc": {"deep": 35, "rem": 0, "light": 301}}))


def test_a_night_with_only_the_all_day_median_is_dropped():
    assert resolve({NIGHT: {"hc_aest_day": {"all_day_median_hr": 70.0}}}) == []
    assert format_recovery([], 7) == "No recovery data found in the last 7 days."


# ── loading (SQLite) ─────────────────────────────────────────────────────────────────────

def _spo2_night(db, user, night, values, conf=5.0):
    n = models.Spo2Night(user_id=user.id, captured_at=night, source="garmin",
                         reading_count=len(values), gap_count=0)
    db.add(n)
    db.flush()
    t0 = datetime(night.year, night.month, night.day, tzinfo=timezone.utc)
    for i, v in enumerate(values):
        db.add(models.Spo2Sample(spo2_night_id=n.id, reading_time=t0 + timedelta(minutes=i),
                                 spo2_pct=v, reading_confidence=conf, epoch_duration_s=60))
    db.commit()


def test_loader_reads_garmin_sleep_spo2_and_hrv_for_a_garmin_only_night(db_session):
    u = _user(db_session)
    db_session.add_all([
        models.HrvReading(user_id=u.id, captured_at=NIGHT, source="garmin", rmssd_ms=67.0),
        models.HealthConnectSync(user_id=u.id, date=NIGHT, sleep_duration_minutes=387,
                                 deep_sleep_minutes=68, rem_sleep_minutes=59, light_sleep_minutes=260,
                                 hr_nadir_bpm=49.1, hr_nadir_source_package=GARMIN_PKG,
                                 resting_heart_rate=74.0),
        models.HealthConnectRecordSource(user_id=u.id, record_type="sleep",
                                         record_start="2026-10-23T12:00:00Z", source_package=GARMIN_PKG),
    ])
    db_session.commit()
    _spo2_night(db_session, u, NIGHT, [96.0, 98.0, 90.0, None])

    r = resolve_night(NIGHT, load_candidates(db_session, u.id, NIGHT - timedelta(days=1))[NIGHT])
    assert r["tst"]["source"] == "garmin_hc" and r["stages"]["source"] == "garmin_hc"
    assert r["hrv"] == [("garmin", 67.0)]
    assert r["spo2"]["source"] == "garmin"
    assert round(r["spo2"]["value"]["spo2"], 2) == 94.67 and r["spo2"]["value"]["spo2_min"] == 90.0   # NULL epoch skipped
    assert r["sleep_nadir_hr"]["source"] == "garmin_hc"
    assert r["all_day_median_hr"]["source"] == "hc_aest_day"


def test_loader_marks_a_two_writer_night_as_blended(db_session):
    u = _user(db_session)
    db_session.add_all([
        models.HealthConnectSync(user_id=u.id, date=NIGHT, sleep_duration_minutes=430,
                                 deep_sleep_minutes=60, rem_sleep_minutes=70, light_sleep_minutes=300),
        models.HealthConnectRecordSource(user_id=u.id, record_type="sleep",
                                         record_start="2026-10-23T12:00:00Z", source_package=GARMIN_PKG),
        models.HealthConnectRecordSource(user_id=u.id, record_type="sleep",
                                         record_start="2026-10-23T12:30:00Z", source_package=SAMSUNG_PKG),
    ])
    db_session.commit()
    r = resolve_night(NIGHT, load_candidates(db_session, u.id, NIGHT)[NIGHT])
    assert r["tst"]["source"] == "hc_multiple" and r["stages"] is None


def test_nadir_is_tagged_with_the_writer_it_read_not_the_sleep_writer(db_session):
    u = _user(db_session)
    db_session.add_all([
        models.HealthConnectSync(user_id=u.id, date=NIGHT, sleep_duration_minutes=400,
                                 hr_nadir_bpm=50.0, hr_nadir_source_package=SAMSUNG_PKG),
        models.HealthConnectRecordSource(user_id=u.id, record_type="sleep",
                                         record_start="2026-10-23T12:00:00Z", source_package=GARMIN_PKG),
    ])
    db_session.commit()
    r = resolve_night(NIGHT, load_candidates(db_session, u.id, NIGHT)[NIGHT])
    assert r["tst"]["source"] == "garmin_hc" and r["sleep_nadir_hr"]["source"] == "samsung_hc"


def test_loader_is_scoped_to_the_user_and_the_window(db_session):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    old = NIGHT - timedelta(days=10)
    db_session.add_all([
        models.HrvReading(user_id=a.id, captured_at=NIGHT, source="garmin", rmssd_ms=60.0),
        models.HrvReading(user_id=a.id, captured_at=old, source="garmin", rmssd_ms=61.0),
        models.HrvReading(user_id=b.id, captured_at=NIGHT, source="garmin", rmssd_ms=99.0),
    ])
    db_session.commit()
    got = load_candidates(db_session, a.id, NIGHT - timedelta(days=7))
    assert list(got) == [NIGHT] and got[NIGHT]["garmin"]["hrv"] == 60.0


def test_a_user_with_no_data_renders_the_empty_message(db_session):
    u = _user(db_session)
    assert format_recovery(resolve(load_candidates(db_session, u.id, NIGHT)), 7) == (
        "No recovery data found in the last 7 days.")
