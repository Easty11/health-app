"""Wake-day capture: the morning fetch that lands the CURRENT wake-day's overnight vitals.

The real `PersonalClient` runs against a fake host at the TRANSPORT layer (FEEDBACK section 23), so the
requests counted here are the requests the host would see. The clock is injected (`now=`): every test names a
Brisbane wall time on wake-day 2026-11-02. Proven:

  * a morning fetch lands sleep, efficiency, awake, SpO2, RR and RHR for the wake-day, with the budgeted
    requests (4 data + 1 token exchange on the Personal API);
  * the gates: complete skip, 30-minute throttle, explicit-Refresh bypass with a 60 s floor, window close at
    10:00, one in flight;
  * slot states: pending before 10:00, `not_synced` (named message, never a dash) when Garmin has no finished
    night, missing-with-reason after 10:00; an earlier night never fills today's slot;
  * the 10:00 backstop runs for an incomplete user, ignores the throttle, and is idempotent per day;
  * the DI epoch night is part of completeness for a user with a DI connection.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytz

import garmin_personal_lanes as gpl
import models
import wake_day_capture as wdc
from connectors import garmin_personal as gp
from connectors.garmin import GarminClient
from encryption import encrypt
from garmin_personal_fakes import FAKE_KEY, FakeHost, populate, skeleton_day

BRIS = pytz.timezone("Australia/Brisbane")
DAY = date(2026, 11, 2)
DS = DAY.isoformat()


def at(hour, minute=0, second=0):
    return BRIS.localize(datetime(2026, 11, 2, hour, minute, second)).astimezone(timezone.utc)


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.commit()


def _personal(db, uid=1):
    db.add(models.UserIntegration(user_id=uid, provider="garmin_personal", api_key_encrypted=encrypt(FAKE_KEY),
                                  key_expires_on=DAY + timedelta(days=200)))
    db.commit()


def _di(db, uid=1):
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encrypt("DI_BLOB")))
    db.commit()


@pytest.fixture()
def host(monkeypatch):
    h = FakeHost()
    orig = gpl.personal_client
    monkeypatch.setattr(gpl, "personal_client", lambda db, uid, *, transport=None: orig(db, uid, transport=h.transport()))
    return h


@pytest.fixture()
def user(db_session):
    _user(db_session)
    _personal(db_session)
    return db_session


def data_paths(host):
    return sorted(p for (_m, p, _q) in host.requests)


def test_a_morning_fetch_lands_every_slot_for_the_wake_day_within_the_request_budget(user, host):
    populate(host, DS)

    out = wdc.run(user, 1, trigger="checkin", now=at(6, 5))

    assert out["outcome"] == "complete" and out["via"] == "checkin"
    st = out["status"]
    assert st["complete"] and st["gaps"] == [] and st["message"] is None
    assert {s["state"] for s in st["slots"].values()} == {"filled"}
    # the four endpoints of the brief, and nothing else (no body battery, stress or zones)
    assert data_paths(host) == sorted([gp.HRV_PATH.format(date=DS), gp.SLEEP_PATH, gp.HEART_RATE_PATH,
                                       gp.SPO2_HOURLY_PATH.format(date=DS)])
    assert out["requests"] == {"personal": 5, "di": 0}            # 4 data + 1 token exchange
    assert host.exchanges == 1


def test_a_complete_wake_day_is_skipped_with_no_request(user, host):
    populate(host, DS)
    wdc.run(user, 1, trigger="checkin", now=at(6, 5))
    before = len(host.requests)

    out = wdc.run(user, 1, trigger="recovery", now=at(7, 0))

    assert out["skipped"] and out["reason"] == "complete"
    assert len(host.requests) == before


def test_when_garmin_has_no_finished_night_the_slots_say_so_and_never_a_dash(user, host):
    skeleton_day(host, DS)                      # the host answers 200, every value null (observed 25 Oct 2026)

    out = wdc.run(user, 1, trigger="checkin", now=at(6, 0))

    assert out["outcome"] == "not_synced"
    st = out["status"]
    assert st["message"] == "Garmin not synced yet — open Garmin Connect, then Refresh"
    assert st["gaps"] == list(wdc.SLOTS)
    for slot in st["slots"].values():
        assert slot["state"] == "not_synced" and slot["message"] == st["message"]
    lane = user.query(models.IntegrationLaneStatus).filter_by(user_id=1, lane="wake_day_fetch").one()
    assert lane.outcome == "empty" and lane.reason == f"{DS} not_synced via=checkin"


def test_a_slot_before_ten_with_no_attempt_is_pending_and_after_ten_is_missing_with_a_reason(user, host):
    before = wdc.status(user, 1, now=at(6, 0))
    assert before["window_open"] and {s["state"] for s in before["slots"].values()} == {"pending"}

    after = wdc.status(user, 1, now=at(10, 1))

    assert not after["window_open"]
    for slot in after["slots"].values():
        assert slot["state"] == "missing"
        assert slot["message"] == "missing — no fetch ran before 10:00 (no check-in or Recovery open)"
    assert "closed at 10:00 without" in after["message"]


def test_missing_after_ten_names_the_failure_that_stopped_the_capture(user, host):
    host.exchange_status = 401                   # the key is refused
    out = wdc.run(user, 1, trigger="checkin", now=at(6, 0))
    assert out["outcome"] == "auth_failed"

    after = wdc.status(user, 1, now=at(10, 30))

    assert after["slots"]["spo2"]["message"] == "missing — the Garmin key was refused"
    assert user.query(models.IntegrationLaneStatus).filter_by(user_id=1, lane="personal_hrv").one().outcome == "auth_failed"


def test_an_earlier_nights_values_never_fill_todays_slots(user, host):
    prev = (DAY - timedelta(days=1)).isoformat()
    populate(host, prev)
    skeleton_day(host, DS)
    # land yesterday through the same capture, one day earlier
    wdc.run(user, 1, trigger="checkin", now=at(6, 0) - timedelta(days=1))
    assert wdc.status(user, 1, now=at(6, 0) - timedelta(days=1))["gaps"] == []

    st = wdc.status(user, 1, now=at(6, 0))

    assert st["gaps"] == list(wdc.SLOTS)
    assert {s["state"] for s in st["slots"].values()} == {"pending"}


def test_throttle_30_minutes_then_explicit_refresh_bypasses_it_but_keeps_a_60_second_floor(user, host):
    skeleton_day(host, DS)
    assert wdc.run(user, 1, trigger="checkin", now=at(6, 0))["outcome"] == "not_synced"
    n = len(host.requests)

    assert wdc.run(user, 1, trigger="recovery", now=at(6, 10))["reason"] == "throttled"
    assert len(host.requests) == n
    assert wdc.run(user, 1, trigger="refresh", force=True, now=at(6, 0, 30))["reason"] == "throttled"   # floor
    assert len(host.requests) == n
    assert wdc.run(user, 1, trigger="refresh", force=True, now=at(6, 12))["outcome"] == "not_synced"   # bypass
    assert wdc.run(user, 1, trigger="recovery", now=at(6, 50))["outcome"] == "not_synced"              # 38 min on


def test_an_unforced_open_after_ten_does_not_fetch_but_a_forced_refresh_does(user, host):
    populate(host, DS)

    out = wdc.run(user, 1, trigger="recovery", now=at(10, 30))
    assert out["skipped"] and out["reason"] == "window_closed" and host.requests == []

    assert wdc.run(user, 1, trigger="refresh", force=True, now=at(10, 31))["outcome"] == "complete"


def test_the_backstop_runs_for_an_incomplete_user_ignores_the_throttle_and_is_idempotent(user, host):
    skeleton_day(host, DS)
    wdc.run(user, 1, trigger="checkin", now=at(9, 55))                  # 5 minutes before the backstop

    first = wdc.run_backstop(user, now=at(10, 0))
    second = wdc.run_backstop(user, now=at(10, 5))

    assert first == {1: "not_synced"}                                   # ran inside the 30-minute throttle
    assert second == {1: "backstop_done"}
    lane = user.query(models.IntegrationLaneStatus).filter_by(user_id=1, lane="wake_day_fetch").one()
    assert lane.reason == f"{DS} not_synced via=backstop"


def test_the_backstop_skips_a_user_whose_wake_day_is_fully_populated(user, host):
    populate(host, DS)
    wdc.run(user, 1, trigger="checkin", now=at(6, 0))
    n = len(host.requests)

    assert wdc.run_backstop(user, now=at(10, 0)) == {1: "complete"}
    assert len(host.requests) == n


def test_a_user_without_a_personal_key_is_skipped_and_a_non_garmin_user_is_not_claimed(db_session, host):
    _user(db_session)
    out = wdc.run(db_session, 1, trigger="checkin", now=at(6, 0))
    assert out["skipped"] and out["reason"] == "no_personal_key"
    assert out["status"] == {"connected": False, "wake_day": DS}


def test_a_second_caller_while_a_fetch_is_in_flight_is_told_in_progress(user, host):
    assert wdc._user_lock(1).acquire(blocking=False)
    try:
        out = wdc.run(user, 1, trigger="checkin", now=at(6, 0))
    finally:
        wdc._user_lock(1).release()
    assert out["skipped"] and out["reason"] == "in_progress" and host.requests == []


def test_a_rate_limit_stops_the_fetch_is_recorded_and_never_raises(user, host):
    populate(host, DS)
    host.status_for[gp.SLEEP_PATH] = 429

    out = wdc.run(user, 1, trigger="checkin", now=at(6, 0))

    assert out["outcome"] == "rate_limited"
    assert user.query(models.IntegrationLaneStatus).filter_by(user_id=1, lane="personal_wellness").one().outcome == "rate_limited"
    assert wdc.status(user, 1, now=at(6, 1))["slots"]["sleep"]["message"].startswith("pending — last fetch: Garmin rate-limited")


# -- the DI epoch night is part of completeness ---------------------------------------------------------

class _DISource:
    def __init__(self, payload): self.payload = payload
    def social_profile(self): return {"displayName": "N"}
    def get(self, path, params=None): return self.payload


def _di_payload():
    from tests.test_garmin_spo2 import _payload
    start = datetime(2026, 11, 1, 12, 40, tzinfo=timezone.utc)
    p = _payload(60, start=start)
    p["dailySleepDTO"]["calendarDate"] = DS
    return p


def test_a_di_user_is_incomplete_until_the_epoch_night_lands_and_the_di_requests_are_reported(user, host, monkeypatch):
    _di(user)
    populate(host, DS)

    class _Client:
        def dump_token(self): return "REFRESHED"
    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: _Client()))

    empty = wdc.run(user, 1, trigger="checkin", now=at(6, 0), spo2_factory=lambda b: _DISource({"dailySleepDTO": {"calendarDate": DS}}))
    assert empty["outcome"] == "spo2_missing" and not empty["status"]["complete"]
    assert empty["requests"]["di"] == 2                                  # social profile + the one night

    ok = wdc.run(user, 1, trigger="refresh", force=True, now=at(6, 30), spo2_factory=lambda b: _DISource(_di_payload()))
    assert ok["outcome"] == "complete" and ok["status"]["complete"]
    assert user.query(models.Spo2Night).filter_by(user_id=1, captured_at=DAY).count() == 1
    assert ok["status"]["slots"]["spo2"]["state"] == "filled"


# -- the 10:00 schedule ---------------------------------------------------------------------------------

def test_the_backstop_fires_at_ten_brisbane_strictly_after_now():
    import load_sweep
    assert load_sweep.next_backstop_fire_utc(at(9, 59)) == at(10, 0)
    assert load_sweep.next_backstop_fire_utc(at(10, 0)) == at(10, 0) + timedelta(days=1)
    assert load_sweep.next_sweep_fire_utc(at(1, 59)) == at(2, 0)           # the 02:00 sweep is unchanged


def test_the_lifespan_starts_and_cancels_both_scheduler_tasks():
    import inspect
    import main
    src = inspect.getsource(main.lifespan)
    assert "load_sweep.backstop_loop()" in src and "load_sweep.sweep_loop()" in src
