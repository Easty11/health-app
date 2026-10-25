"""Raw landing (garmin_raw): scrubbed, hashed, append-only, idempotent; and the lane status writer."""
from datetime import datetime, timedelta, timezone

import models
import garmin_raw as raw


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.commit()


def test_identity_keys_are_scrubbed_at_any_depth_and_other_keys_survive():
    p = {"userProfilePk": 1, "displayName": "N", "a": {"deviceId": 9, "ownerFullName": "X", "keep": 1},
         "rows": [{"userProfileId": 5, "x": 2}], "ownerProfileImageUrlLarge": "u", "activityName": "ok"}
    s = raw.scrub(p)
    assert s == {"a": {"keep": 1}, "rows": [{"x": 2}], "activityName": "ok"}
    assert "userProfilePk" in p                                                  # the input is untouched


def test_the_hash_ignores_key_order_and_identity_only_differences_and_changes_with_content():
    a = raw.payload_sha256(raw.scrub({"b": 1, "a": 2, "userProfilePk": 1}))
    b = raw.payload_sha256(raw.scrub({"a": 2, "b": 1, "userProfilePk": 999}))
    c = raw.payload_sha256(raw.scrub({"a": 2, "b": 3}))
    assert a == b != c and len(a) == 64


def test_land_is_idempotent_on_the_hash_and_appends_when_the_payload_changes(db_session):
    _user(db_session)
    r1 = raw.land(db_session, 1, "sleep", "2026-10-24", {"v": 1})
    r2 = raw.land(db_session, 1, "sleep", "2026-10-24", {"v": 1})
    r3 = raw.land(db_session, 1, "sleep", "2026-10-24", {"v": 2})
    db_session.commit()
    assert (r1.inserted, r2.inserted, r3.inserted) == (True, False, True)
    assert db_session.query(models.GarminRawPayload).count() == 2
    assert raw.latest_payload(db_session, 1, "sleep", "2026-10-24") == {"v": 2}


def test_the_same_payload_on_another_day_or_endpoint_or_user_is_its_own_row(db_session):
    _user(db_session, 1)
    _user(db_session, 4)
    for args in ((1, "sleep", "d1"), (1, "sleep", "d2"), (1, "stress", "d1"), (4, "sleep", "d1")):
        assert raw.land(db_session, *args, {"v": 1}).inserted
    db_session.commit()
    assert db_session.query(models.GarminRawPayload).count() == 4


def test_emoji_in_a_payload_round_trips_and_hashes_as_the_characters(db_session):
    _user(db_session)
    p = {"activityName": "Leg day \U0001F4AA\U0001F525", "n": 1}
    raw.land(db_session, 1, "activity_detail", "24564069469", p)
    db_session.commit()
    db_session.expire_all()
    assert raw.latest_payload(db_session, 1, "activity_detail", "24564069469") == p
    assert raw.payload_sha256(p) == raw.payload_sha256(dict(reversed(list(p.items()))))


def test_the_stored_payload_never_holds_an_identity_key(db_session):
    _user(db_session)
    raw.land(db_session, 1, "hrv", "2026-10-24", {"userProfilePk": 150823854, "hrvSummary": {"lastNightAvg": 50}})
    db_session.commit()
    stored = db_session.query(models.GarminRawPayload).one().payload
    assert "userProfilePk" not in stored and "150823854" not in str(stored)


def test_lane_status_upserts_one_row_and_success_advances_only_on_ok_or_empty(db_session):
    _user(db_session)
    t0 = datetime(2026, 10, 24, tzinfo=timezone.utc)
    raw.record_lane(db_session, 1, "personal_hrv", raw.OK, now=t0)
    raw.record_lane(db_session, 1, "personal_hrv", raw.ERROR, "PersonalTransientError: HTTP 503", now=t0 + timedelta(days=1))
    row = db_session.query(models.IntegrationLaneStatus).one()
    sub = lambda d: d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    assert row.outcome == "error" and "503" in row.reason
    assert sub(row.last_success_at) == t0 and sub(row.last_attempt_at) == t0 + timedelta(days=1)
    raw.record_lane(db_session, 1, "personal_hrv", raw.EMPTY, now=t0 + timedelta(days=2))
    db_session.refresh(row)
    assert row.outcome == "empty" and sub(row.last_success_at) == t0 + timedelta(days=2) and row.reason is None
    assert db_session.query(models.IntegrationLaneStatus).count() == 1


def test_lane_status_reason_is_truncated_and_a_failure_to_record_never_raises(db_session):
    _user(db_session)
    raw.record_lane(db_session, 1, "x", raw.ERROR, "e" * 500)
    assert len(db_session.query(models.IntegrationLaneStatus).one().reason) == 200
    raw.record_lane(db_session, 999, "x", raw.ERROR, "orphan")        # FK violation: swallowed, session usable
    assert db_session.query(models.IntegrationLaneStatus).count() == 1
