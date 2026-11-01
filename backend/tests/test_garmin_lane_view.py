"""S3: the lane/key view behind Settings -> Integrations. Thresholds are `garmin_alerts`' own, so Settings, the
load card and the snapshot agree: amber at <= 30 days, red at <= 7, when expired, and when the token exchange
is refused. Synthetic gate: a key 20 days from expiry is amber."""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytz

import garmin_raw
import models
from encryption import encrypt
from reads.freshness_reads import garmin_lane_view, garmin_alerts

BRIS = pytz.timezone("Australia/Brisbane")
NOW = BRIS.localize(datetime(2026, 11, 2, 12, 0)).astimezone(timezone.utc)
TODAY = date(2026, 11, 2)


def _setup(db, *, expires=TODAY + timedelta(days=200), di=False):
    db.add(models.User(id=1, email="u1@example.com", hashed_password="x"))
    db.commit()
    db.add(models.UserIntegration(user_id=1, provider="garmin_personal", api_key_encrypted=encrypt("k"),
                                  key_expires_on=expires))
    if di:
        db.add(models.UserIntegration(user_id=1, provider="garmin", api_key_encrypted=encrypt("d")))
    db.commit()


@pytest.mark.parametrize("days,severity", [(200, "ok"), (31, "ok"), (30, "amber"), (20, "amber"), (8, "amber"),
                                           (7, "red"), (1, "red"), (0, "red"), (-3, "red")])
def test_key_expiry_thresholds_match_the_alerts(db_session, days, severity):
    _setup(db_session, expires=TODAY + timedelta(days=days))

    key = garmin_lane_view(db_session, 1, NOW)["key"]

    assert key["days_to_expiry"] == days and key["severity"] == severity
    # the load card / snapshot alert and Settings agree on whether it is a problem at all
    has_alert = bool([a for a in garmin_alerts(db_session, 1, NOW) if a["code"].startswith("garmin_key_exp")])
    assert has_alert == (severity != "ok")


def test_a_key_twenty_days_from_expiry_is_amber_with_its_wording(db_session):
    _setup(db_session, expires=TODAY + timedelta(days=20))
    key = garmin_lane_view(db_session, 1, NOW)["key"]
    assert key["severity"] == "amber" and key["message"] == "Expires in 20 days"


def test_an_expired_key_and_a_refused_token_exchange_are_red(db_session):
    _setup(db_session, expires=TODAY - timedelta(days=2))
    assert garmin_lane_view(db_session, 1, NOW)["key"]["message"] == "Key EXPIRED 2 day(s) ago: attach a new key"

    row = db_session.query(models.UserIntegration).one()
    row.key_expires_on = TODAY + timedelta(days=200)
    db_session.commit()
    garmin_raw.record_lane(db_session, 1, garmin_raw.LANE_PERSONAL_TOKEN, garmin_raw.AUTH_FAILED, "PersonalAuthError", now=NOW)
    key = garmin_lane_view(db_session, 1, NOW)["key"]
    assert key["severity"] == "red" and key["token_refused"] is True


def test_no_recorded_expiry_is_amber_not_silent(db_session):
    _setup(db_session, expires=None)
    key = garmin_lane_view(db_session, 1, NOW)["key"]
    assert key["severity"] == "amber" and key["days_to_expiry"] is None


def test_lanes_list_only_what_the_connections_can_run_with_success_age_and_outcome(db_session):
    _setup(db_session)
    garmin_raw.record_lane(db_session, 1, garmin_raw.LANE_PERSONAL_HRV, garmin_raw.OK, now=NOW - timedelta(hours=3))
    garmin_raw.record_lane(db_session, 1, garmin_raw.LANE_PERSONAL_WELLNESS, garmin_raw.ERROR, "RuntimeError",
                           now=NOW - timedelta(hours=1))

    v = garmin_lane_view(db_session, 1, NOW)
    by = {l["lane"]: l for l in v["lanes"]}

    assert "di_spo2" not in by                                       # personal-only user: no DI lane
    assert by["personal_hrv"]["outcome"] == "ok" and by["personal_hrv"]["success_age_hours"] == 3.0
    assert by["personal_wellness"]["severity"] == "amber" and by["personal_wellness"]["reason"] == "RuntimeError"
    assert by["personal_wellness"]["success_age_hours"] is None      # never succeeded
    assert by["personal_selfeval"]["outcome"] is None and by["personal_selfeval"]["severity"] == "none"


def test_the_di_lane_is_listed_for_a_di_user_and_a_failure_is_red(db_session):
    _setup(db_session, di=True)
    garmin_raw.record_lane(db_session, 1, garmin_raw.LANE_DI_SPO2, garmin_raw.AUTH_FAILED, "GarminReconnectError", now=NOW)
    by = {l["lane"]: l for l in garmin_lane_view(db_session, 1, NOW)["lanes"]}
    assert by["di_spo2"]["severity"] == "red" and by["di_spo2"]["outcome"] == "auth_failed"


def test_a_user_with_no_garmin_connection_has_nothing_to_show(db_session):
    db_session.add(models.User(id=1, email="u1@example.com", hashed_password="x"))
    db_session.commit()
    v = garmin_lane_view(db_session, 1, NOW)
    assert v["connected"] is False and v["key"] is None and v["lanes"] == []


def test_the_route_serves_the_view(db_session):
    from routers.garmin import garmin_lanes
    _setup(db_session, expires=TODAY + timedelta(days=20))
    user = db_session.get(models.User, 1)
    out = garmin_lanes(current_user=user, db=db_session)
    assert out["connected"] and out["key"]["severity"] in ("amber", "red", "ok") and out["personal_api"] is True
