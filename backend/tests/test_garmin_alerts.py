"""S5: the staleness card's Garmin alerts -- loud, never skipped. Read-only on stored rows."""
from datetime import date, datetime, timedelta, timezone

import pytest

import garmin_raw
import models
from reads import freshness_reads as fr

NOW = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)          # 11:00 on 25 Oct in Brisbane
TODAY = date(2026, 10, 25)


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.commit()


def _personal(db, expires, uid=1):
    db.add(models.UserIntegration(user_id=uid, provider="garmin_personal", api_key_encrypted="x", key_expires_on=expires))
    db.commit()


def _di(db, uid=1):
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted="x"))
    db.commit()


def _night(db, d, uid=1):
    db.add(models.Spo2Night(user_id=uid, captured_at=d, source="garmin", reading_count=400, gap_count=0))
    db.commit()


def _codes(db, uid=1):
    return {a["code"]: a["severity"] for a in fr.garmin_alerts(db, uid, NOW)}


@pytest.mark.parametrize("days,expected", [
    (200, None), (31, None), (30, "amber"), (8, "amber"), (7, "red"), (0, "red"), (-3, "red")])
def test_key_days_to_expiry_thresholds(db_session, days, expected):
    _user(db_session)
    _personal(db_session, TODAY + timedelta(days=days))
    got = {c: s for c, s in _codes(db_session).items() if "key" in c}
    assert (list(got.values())[0] if got else None) == expected
    if days < 0:
        assert "garmin_key_expired" in got


def test_an_unrecorded_expiry_is_flagged_not_assumed_fine(db_session):
    _user(db_session)
    _personal(db_session, None)
    assert _codes(db_session) == {"garmin_key_expiry_unknown": "amber"}


def test_a_refused_key_is_a_loud_token_alert(db_session):
    _user(db_session)
    _personal(db_session, TODAY + timedelta(days=200))
    garmin_raw.record_lane(db_session, 1, "personal_token", "auth_failed", "PersonalAuthError: token exchange refused: HTTP 401")
    a = fr.garmin_alerts(db_session, 1, NOW)
    assert [(x["code"], x["severity"]) for x in a] == [("garmin_token_failed", "red")]


def test_a_failed_personal_lane_is_amber_and_an_ok_or_empty_one_is_silent(db_session):
    _user(db_session)
    _personal(db_session, TODAY + timedelta(days=200))
    garmin_raw.record_lane(db_session, 1, "personal_hrv", "ok")
    garmin_raw.record_lane(db_session, 1, "personal_wellness", "empty")
    garmin_raw.record_lane(db_session, 1, "personal_selfeval", "error", "errors=2")
    assert _codes(db_session) == {"garmin_lane_failed:personal_selfeval": "amber"}


def test_the_DI_spo2_lane_failing_is_red_even_when_recent_nights_exist(db_session):
    _user(db_session)
    _di(db_session)
    _night(db_session, TODAY)
    garmin_raw.record_lane(db_session, 1, "di_spo2", "skipped_needs_refresh")
    assert _codes(db_session) == {"garmin_di_spo2_failed": "red"}


@pytest.mark.parametrize("newest_days_ago,loud", [(0, False), (1, False), (2, False), (3, True), (10, True)])
def test_more_than_two_nights_without_epoch_data_is_loud(db_session, newest_days_ago, loud):
    _user(db_session)
    _di(db_session)
    _night(db_session, TODAY - timedelta(days=newest_days_ago))
    assert ("garmin_di_spo2_stale" in _codes(db_session)) is loud


def test_no_epoch_night_at_all_for_a_DI_user_is_red_and_a_user_without_DI_is_not_asked(db_session):
    _user(db_session, 1)
    _user(db_session, 2)
    _di(db_session, 1)
    assert _codes(db_session, 1) == {"garmin_di_spo2_none": "red"}
    assert _codes(db_session, 2) == {}


def test_alerts_are_per_user_and_red_sorts_before_amber(db_session):
    _user(db_session, 1)
    _user(db_session, 4)
    _personal(db_session, TODAY + timedelta(days=20), uid=1)
    _di(db_session, 1)
    _night(db_session, TODAY, uid=1)
    garmin_raw.record_lane(db_session, 1, "personal_token", "auth_failed")
    a = fr.garmin_alerts(db_session, 1, NOW)
    assert [x["severity"] for x in a] == ["red", "amber"]
    assert fr.garmin_alerts(db_session, 4, NOW) == []


def test_the_alerts_ride_in_the_freshness_read_and_the_snapshot_lines(db_session):
    _user(db_session)
    _di(db_session)
    f = fr.freshness(db_session, 1, now=NOW)
    assert f["garmin_alerts"] and f["garmin_alerts"][0]["code"] == "garmin_di_spo2_none"
    lines = fr.freshness_snapshot_lines(f)
    assert any(l.startswith("  GARMIN RED:") for l in lines)
    clean = fr.freshness_snapshot_lines({**f, "garmin_alerts": []})
    assert not any("GARMIN" in l.upper() and "ALERT" in l.upper() for l in clean)
