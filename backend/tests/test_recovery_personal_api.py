"""Garmin Personal API in the recovery readers (Q243): rank on (source, transport), the new card
fields, the implausible-night guard, and the two sibling readers.

Synthetic nights only; the numbers echo the shapes seen in prod (a 12-hour start-time shift in one
Health Connect session; a 144 bpm count-weighted median) but are not anyone's data.

The loader and resolver run on the in-memory SQLite `db_session`; the snapshot and the card run
end to end the way test_snapshot_sleep_writer / test_card_sleep_repoint wire them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import mcp_server
import models
from auth import get_current_user
from database import get_db
from reads import hc_sleep
from reads.recovery_night import (
    FIELD_RANK, format_night, format_recovery, load_candidates, resolve, resolve_night,
)
from reads.snapshot_reads import latest_sleep_night, sleep_snapshot_lines
from routers import health

NIGHT = date(2026, 10, 25)
GARMIN_PKG = "com.garmin.android.apps.connectmobile"
SAMSUNG_PKG = "com.sec.android.app.shealth"


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


@pytest.fixture
def user(db_session):
    u = models.User(email="pa@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    return u


def _api_night(db, u, night=NIGHT, *, tst_s=432 * 60, deep_s=59 * 60, rem_s=25 * 60, light_s=348 * 60,
               awake_s=53 * 60, start=None, end=None, eff=89.1, rr=(15.0, 11.0, 19.0),
               spo2=(96.0, 84.0), score=45, transport="personal_api"):
    start = start or _utc(2026, 10, 24, 13, 35)
    end = end or _utc(2026, 10, 24, 21, 40)
    db.add(models.SleepNight(
        user_id=u.id, captured_at=night, source="garmin", transport=transport,
        sleep_start=start, sleep_end=end, sleep_time_s=tst_s, deep_s=deep_s, rem_s=rem_s,
        light_s=light_s, awake_s=awake_s, respiration_avg=rr[0], respiration_low=rr[1],
        respiration_high=rr[2], spo2_avg_pct=spo2[0], spo2_lowest_pct=spo2[1], sleep_score=score,
        efficiency_pct=eff, efficiency_formula="garmin_window_tst_over_span_v1"))
    db.commit()


def _hc_night(db, u, night=NIGHT, *, tst=430, deep=55, rem=90, light=285, start=None, end=None,
              nadir=49.0, pkg=GARMIN_PKG):
    db.add_all([
        models.HealthConnectSync(
            user_id=u.id, date=night, sleep_duration_minutes=tst, deep_sleep_minutes=deep,
            rem_sleep_minutes=rem, light_sleep_minutes=light, hr_nadir_bpm=nadir,
            hr_nadir_source_package=pkg, resting_heart_rate=70.0,
            sleep_start=start or _utc(2026, 10, 24, 13, 30), sleep_end=end or _utc(2026, 10, 24, 21, 40)),
        models.HealthConnectRecordSource(
            user_id=u.id, record_type="sleep",
            record_start=f"{(night - timedelta(days=1)).isoformat()}T13:30:00Z", source_package=pkg),
    ])
    db.commit()


def _resolved(db, u, night=NIGHT):
    return resolve_night(night, load_candidates(db, u.id, night - timedelta(days=1)).get(night, {}))


# -- S1: rank on (source, transport) ----------------------------------------------------------------

def test_the_personal_api_outranks_health_connect_for_sleep(db_session, user):
    _api_night(db_session, user)
    _hc_night(db_session, user)
    r = _resolved(db_session, user)
    assert r["tst"]["source"] == "garmin_api" and r["tst"]["value"]["tst"] == 432
    assert r["stages"]["source"] == "garmin_api"
    assert r["stages"]["value"] == {"deep": 59, "rem": 25, "light": 348, "awake": 53}


def test_health_connect_stays_the_fallback_for_a_user_without_a_personal_key(db_session, user):
    _hc_night(db_session, user)
    r = _resolved(db_session, user)
    assert r["tst"]["source"] == "garmin_hc" and r["tst"]["value"]["tst"] == 430


def test_the_stage_split_is_one_source_the_api_awake_is_never_spliced_under_hc_stages(db_session, user):
    _hc_night(db_session, user)
    db_session.add(models.SleepNight(user_id=user.id, captured_at=NIGHT, source="garmin",
                                     transport="personal_api", awake_s=3000))     # awake only
    db_session.commit()
    r = _resolved(db_session, user)
    assert r["stages"]["source"] == "garmin_hc" and r["stages"]["value"]["awake"] is None


def test_epoch_spo2_beats_the_api_summary_and_the_summary_is_the_permanent_fallback(db_session, user):
    _api_night(db_session, user, spo2=(96.0, 84.0))
    assert _resolved(db_session, user)["spo2"]["source"] == "garmin_api"
    n = models.Spo2Night(user_id=user.id, captured_at=NIGHT, source="garmin", reading_count=3, gap_count=0)
    db_session.add(n)
    db_session.flush()
    for i, v in enumerate((95.0, 97.0, 90.0)):
        db_session.add(models.Spo2Sample(spo2_night_id=n.id, reading_time=_utc(2026, 10, 24, 14, i),
                                         spo2_pct=v, reading_confidence=5.0, epoch_duration_s=60))
    db_session.commit()
    r = _resolved(db_session, user)
    assert r["spo2"]["source"] == "garmin_di" and r["spo2"]["value"]["spo2_min"] == 90.0
    assert "SpO2=94.0% (min 90%) [garmin/di]" in format_night(r)


def test_the_api_spo2_summary_prints_its_own_transport(db_session, user):
    _api_night(db_session, user, spo2=(96.0, 84.0))
    assert "SpO2=96.0% (min 84%) [garmin/api]" in format_night(_resolved(db_session, user))


def test_the_daily_rhr_is_daily_physiology_and_never_the_zones_figure_or_a_sleep_hr(db_session, user):
    db_session.add(models.DailyPhysiology(user_id=user.id, date=NIGHT, source="garmin",
                                          transport="personal_api", resting_hr_bpm=51, rhr_7d_avg_bpm=58))
    db_session.add(models.SleepNight(user_id=user.id, captured_at=NIGHT, source="garmin",
                                     transport="personal_api", sleep_time_s=400 * 60))
    db_session.commit()
    r = _resolved(db_session, user)
    assert r["daily_rhr"]["source"] == "garmin_api" and r["daily_rhr"]["value"]["daily_rhr"] == 51
    line = format_night(r)
    assert "RHR=51 bpm [garmin/api]" in line and "58" not in line      # the 7-day average is not read


def test_hrv_tag_shows_the_transport_the_row_was_written_by(db_session, user):
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=NIGHT, source="garmin", rmssd_ms=60.0,
                          transport="personal_api"),
        models.HrvReading(user_id=user.id, captured_at=NIGHT - timedelta(days=1), source="garmin",
                          rmssd_ms=58.0, transport="di"),
        models.HrvReading(user_id=user.id, captured_at=NIGHT - timedelta(days=2), source="garmin",
                          rmssd_ms=57.0),
    ])
    db_session.commit()
    text = format_recovery(resolve(load_candidates(db_session, user.id, NIGHT - timedelta(days=3))), 7)
    assert "HRV=60 ms [garmin/api]" in text and "HRV=58 ms [garmin/di]" in text
    assert "HRV=57 ms [garmin]" in text                                 # no transport recorded: no claim


# -- S2: the new fields on the card -----------------------------------------------------------------

def test_the_line_carries_awake_derived_efficiency_respiration_range_and_score(db_session, user):
    _api_night(db_session, user)
    line = format_night(_resolved(db_session, user))
    assert "Awake=53m [garmin/api]" in line
    assert "Eff=89% [garmin/api, derived]" in line
    assert "RR=15.0 br/min (low 11, high 19) [garmin/api]" in line
    assert "Sleep score=45 [garmin/api]" in line


def test_a_source_without_a_respiration_range_prints_the_average_alone(db_session, user):
    line = format_night(resolve_night(NIGHT, {"samsung_scraper": {"rr": 14.5}}))
    assert "RR=14.5 br/min [samsung scraper]" in line and "low" not in line


# -- S3: the implausible night ----------------------------------------------------------------------

def _shifted_hc_night(db, u):
    """User 1's 25 Oct shape: the session starts exactly 12 h before the true start, light absorbs it."""
    _hc_night(db, u, tst=1151, deep=59, rem=25, light=1067, nadir=61.4,
              start=_utc(2026, 10, 24, 1, 35), end=_utc(2026, 10, 24, 21, 39))


def test_a_shifted_hc_night_is_withheld_with_its_reason_and_the_api_night_stands(db_session, user):
    _api_night(db_session, user)
    _shifted_hc_night(db_session, user)
    r = _resolved(db_session, user)
    assert r["tst"]["source"] == "garmin_api" and r["tst"]["value"]["tst"] == 432
    assert "garmin_hc" in r["withheld"] and "1151 min exceeds 12 h" in r["withheld"]["garmin_hc"]
    assert "Withheld: garmin/HC sleep — TST 1151 min exceeds 12 h" in format_night(r)


def test_the_guard_holds_on_the_hc_path_alone_and_takes_the_nadir_with_the_night(db_session, user):
    _shifted_hc_night(db_session, user)
    r = _resolved(db_session, user)
    assert r["tst"] is None and r["stages"] is None and r["sleep_nadir_hr"] is None
    line = format_night(r)
    assert "TST=—" in line and "1067" not in line and "1151 min" in line      # the reason names it once
    assert "Sleep-nadir HR=—" in line
    assert [n["night"] for n in resolve({NIGHT: load_candidates(db_session, user.id, NIGHT)[NIGHT]})] == [NIGHT]


def test_the_threshold_is_twelve_hours_inclusive():
    assert hc_sleep.MAX_PLAUSIBLE_TST_MIN == 720
    assert hc_sleep.night_implausibility(720) is None
    assert hc_sleep.night_implausibility(721) is not None


def test_stage_minutes_beyond_the_sessions_own_span_are_refused():
    start, end = _utc(2026, 10, 24, 22), _utc(2026, 10, 25, 5)               # 420 min
    assert hc_sleep.night_implausibility(420, 421, start, end) is None      # one minute of floor slack
    why = hc_sleep.night_implausibility(400, 430, start, end)
    assert why and "stage sum 430 min" in why and "span of 420 min" in why


def test_a_real_long_night_below_the_threshold_is_read(db_session, user):
    _hc_night(db_session, user, tst=603, deep=80, rem=120, light=403,
              start=_utc(2026, 10, 24, 11), end=_utc(2026, 10, 24, 21, 30))
    r = _resolved(db_session, user)
    assert r["tst"]["value"]["tst"] == 603 and not r["withheld"]


def test_the_guard_applies_to_the_personal_api_lane_too(db_session, user):
    _api_night(db_session, user, tst_s=900 * 60, deep_s=0, rem_s=0, light_s=900 * 60, eff=None)
    _hc_night(db_session, user)
    r = _resolved(db_session, user)
    assert r["tst"]["source"] == "garmin_hc" and "garmin_api" in r["withheld"]


# -- S4: the all-day median ---------------------------------------------------------------------------

def test_the_all_day_median_is_stored_and_not_read(db_session, user):
    _hc_night(db_session, user)                                    # resting_heart_rate=70.0 stored
    cand = load_candidates(db_session, user.id, NIGHT)[NIGHT]
    assert not any("all_day_median_hr" in c for c in cand.values() if isinstance(c, dict))
    assert "All-day" not in format_recovery(resolve(load_candidates(db_session, user.id, NIGHT)), 7)
    assert FIELD_RANK.get("all_day_median_hr") is None


# -- S5: the sibling readers --------------------------------------------------------------------------

def test_latest_sleep_night_resolves_every_figure_for_an_api_night(db_session, user):
    _api_night(db_session, user)
    db_session.add(models.DailyPhysiology(user_id=user.id, date=NIGHT, source="garmin",
                                          transport="personal_api", resting_hr_bpm=51))
    db_session.commit()
    s = latest_sleep_night(db_session, user.id)
    assert (s["night"], s["source"], s["transport"]) == ("2026-10-25", "garmin", "personal_api")
    assert s["duration_min"] == 432 and s["awake_min"] == 53
    assert s["efficiency_pct"] == 89.1 and s["efficiency_derived"] is True
    assert s["resp_rate"] == 15.0 and s["spo2_pct"] == 96.0 and s["resting_hr_bpm"] == 51
    assert s["sleep_hr_bpm"] is None                               # the ring's figure; no ring here
    assert s["field_sources"]["efficiency"] == "Garmin (Personal API)"


def test_an_hc_night_takes_the_figures_it_lacks_from_other_sources_on_the_same_night(db_session, user):
    _hc_night(db_session, user)
    db_session.add(models.DailyPhysiology(user_id=user.id, date=NIGHT, source="garmin",
                                          transport="personal_api", resting_hr_bpm=52))
    db_session.add(models.SamsungHRVReading(user_id=user.id, captured_at=NIGHT, context="passive_overnight",
                                            sleep_efficiency_pct=93, sleep_hr_bpm=48))
    db_session.commit()
    s = latest_sleep_night(db_session, user.id)
    assert s["transport"] == "health_connect" and s["duration_min"] == 430
    assert s["efficiency_pct"] == 93 and s["field_sources"]["efficiency"] == "Samsung scraper"
    assert s["resting_hr_bpm"] == 52 and s["sleep_hr_bpm"] == 48


def test_the_snapshot_resting_hr_is_the_daily_rate_and_absent_when_there_is_none(db_session, user):
    _api_night(db_session, user)
    s = latest_sleep_night(db_session, user.id)
    assert "  Resting HR: — (no daily resting rate)" in sleep_snapshot_lines(s)
    db_session.add(models.SamsungHRVReading(user_id=user.id, captured_at=NIGHT, context="passive_overnight",
                                            sleep_hr_bpm=48))
    db_session.commit()
    lines = sleep_snapshot_lines(latest_sleep_night(db_session, user.id))
    assert "  Resting HR: — (no daily resting rate)" in lines              # the ring's 48 is not borrowed
    assert any(l.startswith("  Sleep HR: 48 bpm") for l in lines)
    db_session.add(models.DailyPhysiology(user_id=user.id, date=NIGHT, source="garmin",
                                          transport="personal_api", resting_hr_bpm=51))
    db_session.commit()
    assert "  Resting HR: 51 bpm · Garmin" in sleep_snapshot_lines(
        latest_sleep_night(db_session, user.id))


def test_the_snapshot_labels_the_derived_efficiency_and_names_a_withheld_night(db_session, user):
    _api_night(db_session, user, night=NIGHT - timedelta(days=1))
    _shifted_hc_night(db_session, user)
    s = latest_sleep_night(db_session, user.id)
    assert s["night"] == "2026-10-24"                                   # the withheld newest night is skipped ...
    lines = sleep_snapshot_lines(s)
    assert any("derived from the device's own sleep window" in l for l in lines)
    assert any(l.startswith("  Withheld: garmin/HC sleep for 2026-10-25") for l in lines)  # ... and said so


def test_the_card_payload_keeps_its_shape_and_gains_the_new_keys(db_session, user):
    _api_night(db_session, user)
    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    sleep = TestClient(app).get("/summary").json()["latest_sleep"]
    for key in ("night", "source", "source_label", "writers", "blended", "duration_min", "deep_min",
                "rem_min", "light_min", "score", "efficiency_pct", "awake_min", "resp_rate",
                "sleep_hr_bpm", "spo2_pct", "bedtime", "wake_time"):
        assert key in sleep
    assert sleep["source_label"] == "Garmin" and sleep["awake_min"] == 53
