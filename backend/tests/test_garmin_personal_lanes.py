"""S2/S4/S5: HRV and self-evaluation on the Personal API host, the DI SpO2 lane kept alive on its own, and the
lane status. The real client runs against a fake host at the transport layer; the DI side is faked as in the
existing sweep tests."""
from datetime import date, datetime, timedelta, timezone

import pytest

import garmin_personal_lanes as gpl
import garmin_raw
import models
from connectors import garmin_personal as gp
from connectors.garmin import (
    GarminClient, GarminPersonalKeyError, GarminReconnectError, normalize_hrv_day,
)
from encryption import decrypt, encrypt
from garmin_personal_fakes import FAKE_KEY, FakeHost, hrv_payload, populate
from reads import recovery_reads
from routers import garmin as garmin_router
from scripts import garmin_sync

TODAY = garmin_router.garmin_wake_day()
TS = TODAY.isoformat()


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.commit()


def _personal_row(db, uid=1, key=FAKE_KEY):
    db.add(models.UserIntegration(user_id=uid, provider="garmin_personal", api_key_encrypted=encrypt(key),
                                  key_expires_on=TODAY + timedelta(days=200)))
    db.commit()


def _di_row(db, uid=1, blob="DI_BLOB"):
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encrypt(blob)))
    db.commit()


@pytest.fixture()
def host(monkeypatch):
    h = FakeHost()
    orig = gpl.personal_client
    monkeypatch.setattr(gpl, "personal_client", lambda db, uid, *, transport=None: orig(db, uid, transport=h.transport()))
    return h


def _lane(db, uid, lane):
    return db.query(models.IntegrationLaneStatus).filter_by(user_id=uid, lane=lane).first()


class NoDI:
    """Any DI login in a personal-only flow is a defect."""
    def __init__(self):
        self.calls = 0

    def from_token(self, blob):
        self.calls += 1
        raise AssertionError("the DI lane must not be touched")


# -- HRV --------------------------------------------------------------------------------------------

def test_hrv_comes_from_the_personal_host_with_source_garmin_transport_personal_api_and_no_DI_login(
        db_session, host, monkeypatch):
    _user(db_session)
    _personal_row(db_session)
    host.set(gp.HRV_PATH.format(date=TS), hrv_payload(TS, 61.0))
    no_di = NoDI()
    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: no_di.from_token(blob)))

    out = garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)

    assert out["days_with_data"] == 1 and out["readings_upserted"] == 1 and out["samples_upserted"] == 3
    r = db_session.query(models.HrvReading).one()
    assert (r.source, r.transport, r.rmssd_ms, r.status) == ("garmin", "personal_api", 61.0, "BALANCED")
    assert db_session.query(models.HrvSample).count() == 3 and no_di.calls == 0
    assert _lane(db_session, 1, "personal_hrv").outcome == "ok" and _lane(db_session, 1, "personal_token").outcome == "ok"


def test_the_personal_mapper_is_the_DI_mapper_so_a_payload_gives_the_same_stored_fields(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    payload = hrv_payload(TS, 47.5)
    host.set(gp.HRV_PATH.format(date=TS), payload)
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    expected = normalize_hrv_day(payload, TS)["reading"]
    r = db_session.query(models.HrvReading).one()
    assert {k: getattr(r, k) for k in expected} == expected


def test_source_stays_garmin_so_no_rank_changes_and_an_unknown_source_would_not_(db_session, host):
    assert recovery_reads._WAKEDAY_SOURCE_RANK == {"garmin": 2, "samsung": 1}
    assert recovery_reads._SOURCE_RANK["garmin"] == 2
    _user(db_session)
    _personal_row(db_session)
    host.set(gp.HRV_PATH.format(date=TS), hrv_payload(TS))
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    src = db_session.query(models.HrvReading.source).one()[0]
    assert recovery_reads._WAKEDAY_SOURCE_RANK.get(src, 0) == 2


def test_raw_hrv_is_landed_without_the_profile_pk(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    host.set(gp.HRV_PATH.format(date=TS), hrv_payload(TS))
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    row = db_session.query(models.GarminRawPayload).one()
    assert (row.endpoint, row.ref) == ("hrv", TS) and "userProfilePk" not in row.payload


def test_a_night_first_written_by_DI_is_overwritten_field_by_field_but_never_nulled_or_unsampled(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    night = date.fromisoformat(TS)
    r = models.HrvReading(user_id=1, captured_at=night, source="garmin", rmssd_ms=50.0, status="LOW",
                          baseline_low=38.0, baseline_high=66.0, weekly_avg=60.0, transport="di")
    db_session.add(r)
    db_session.flush()
    db_session.add(models.HrvSample(hrv_reading_id=r.id, reading_time=datetime(2026, 10, 24, 1, tzinfo=timezone.utc), rmssd_ms=49.0))
    db_session.commit()
    thin = {"hrvSummary": {"calendarDate": TS, "lastNightAvg": 58.0}}            # no status/baseline/weekly/readings
    host.set(gp.HRV_PATH.format(date=TS), thin)

    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)

    r = db_session.query(models.HrvReading).one()
    assert r.rmssd_ms == 58.0 and r.transport == "personal_api"                    # overwritten, transport flipped
    assert (r.status, r.baseline_low, r.baseline_high, r.weekly_avg) == ("LOW", 38.0, 66.0, 60.0)   # kept
    assert db_session.query(models.HrvSample).count() == 1                          # series kept


def test_a_refused_key_is_a_personal_key_error_a_424_reconnect_state_and_both_lanes_record_it(db_session, host):
    _user(db_session)
    _personal_row(db_session, key="a-revoked-key")
    with pytest.raises(GarminPersonalKeyError) as e:
        garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    assert isinstance(e.value, GarminReconnectError) and "a-revoked-key" not in str(e.value)
    assert _lane(db_session, 1, "personal_hrv").outcome == "auth_failed"
    assert _lane(db_session, 1, "personal_token").outcome == "auth_failed"
    assert "garmin_personal_attach" in garmin_router._reconnect_http(e.value).detail
    assert "garmin_login" in garmin_router._reconnect_http(GarminReconnectError("x")).detail


def test_a_rate_limit_propagates_typed_and_is_recorded_as_such(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    host.status_for[gp.HRV_PATH.format(date=TS)] = 429
    with pytest.raises(gp.PersonalRateLimited):
        garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    assert _lane(db_session, 1, "personal_hrv").outcome == "rate_limited"
    assert _lane(db_session, 1, "personal_token") is None                          # the key was never refused


def test_the_token_is_cached_encrypted_on_the_row_and_reused_by_the_next_run(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    host.set(gp.HRV_PATH.format(date=TS), hrv_payload(TS))
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    row = gpl.get_row(db_session, 1)
    assert row.access_token_encrypted and decrypt(row.access_token_encrypted) in host.issued
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    assert host.exchanges == 1


def test_a_cached_token_that_no_longer_decrypts_is_a_cache_miss_not_an_error(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    row = gpl.get_row(db_session, 1)
    row.access_token_encrypted = "not-a-fernet-token"
    row.access_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=20)
    db_session.commit()
    host.set(gp.HRV_PATH.format(date=TS), hrv_payload(TS))
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    assert host.exchanges == 1 and db_session.query(models.HrvReading).count() == 1


def test_a_user_with_no_personal_key_still_takes_the_DI_path(db_session, monkeypatch):
    _user(db_session)
    _di_row(db_session)

    class FakeDI:
        def dump_token(self): return "BLOB2"
        def get_hrv_range(self, s, e): return [normalize_hrv_day(hrv_payload(TS, 44.0), TS)]
        def profile_id(self): return "p"

    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: FakeDI()))
    garmin_router.sync_hrv_for_user(db_session, 1, TODAY, TODAY)
    r = db_session.query(models.HrvReading).one()
    assert (r.rmssd_ms, r.transport) == (44.0, "di")


# -- the sweep --------------------------------------------------------------------------------------

class DISpo2Source:
    """A DI SpO2 source whose reads record the order of events."""
    def __init__(self, log): self.log = log
    def social_profile(self): return {"displayName": "N"}
    def get(self, path, params=None):
        self.log.append("spo2_read")
        return {"dailySleepDTO": {"calendarDate": params["date"]}}


class NoActivities:
    def get(self, path, params=None): return []


def _sweep(db, host, log, **kw):
    return garmin_sync.sweep_garmin_hrv(
        db, days=1, selfeval_factory=lambda b: NoActivities(), spo2_factory=lambda b: DISpo2Source(log),
        personal_transport=host.transport(), **kw)


def _activity_routes(host, rpe=60):
    host.set(gp.ACTIVITY_LIST_PATH, [{"activityId": 777, "startTimeGMT": f"{TS} 01:30:00", "duration": 3600,
                                       "activityType": {"typeKey": "running"}}])
    host.set(f"{gp.ACTIVITY_PATH}/777", {"activityName": "Run \U0001F3C3",
                                         "summaryDTO": {"directWorkoutRpe": rpe, "directWorkoutFeel": 50}})


def test_sweep_serves_a_personal_user_from_the_official_host_and_keeps_DI_for_spo2_only(db_session, host, monkeypatch):
    _user(db_session)
    _personal_row(db_session)
    _di_row(db_session)
    populate(host, TS)
    _activity_routes(host)
    log = []

    class FakeDI:
        def dump_token(self): log.append("keepalive_dump"); return "REFRESHED_DI_BLOB"

    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: log.append("keepalive_login") or FakeDI()))

    out = _sweep(db_session, host, log)

    u = out["per_user"][1]
    assert u["status"] == "succeeded" and u["readings_upserted"] == 1
    # self-evaluation: source stays 'garmin' (SOURCE_SCALES / hierarchy key on it), transport is audit detail
    rpe = db_session.query(models.SessionRpeObservation).one()
    assert (rpe.source, rpe.source_activity_ref, rpe.rpe_cr10) == ("garmin", "777", 6.0)
    assert rpe.provenance["transport"] == "personal_api" and rpe.provenance["garmin_type"] == "running"
    assert u["selfeval"]["rated"] == 1
    # wellness landed and mapped
    assert u["wellness"]["sleep_inserted"] == 1 and db_session.query(models.SleepNight).count() == 1
    assert db_session.query(models.DailyPhysiology).count() == 1
    # the DI lane did ONE job, after its own keepalive, and the keepalive wrote the refreshed blob back
    assert log == ["keepalive_login", "keepalive_dump", "spo2_read", "spo2_read"]
    assert decrypt(db_session.query(models.UserIntegration).filter_by(provider="garmin").one().api_key_encrypted) \
        == "REFRESHED_DI_BLOB"
    for lane in ("personal_hrv", "personal_selfeval", "personal_wellness", "di_spo2", "personal_token"):
        assert _lane(db_session, 1, lane).outcome in ("ok", "empty"), lane


def test_sweep_includes_a_personal_only_user_who_has_no_DI_row_at_all(db_session, host, monkeypatch):
    _user(db_session)
    _personal_row(db_session)
    populate(host, TS)
    no_di = NoDI()
    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: no_di.from_token(blob)))
    out = _sweep(db_session, host, [])
    assert out["users_attempted"] == 1 and out["per_user"][1]["status"] == "succeeded"
    assert "spo2" not in out["per_user"][1] and no_di.calls == 0
    assert out["wellness"]["sleep_inserted"] == 1


def test_a_dead_DI_token_is_recorded_loudly_and_never_blocks_the_personal_lanes(db_session, host, monkeypatch):
    _user(db_session)
    _personal_row(db_session)
    _di_row(db_session)
    populate(host, TS)
    log = []

    def dead(cls, blob):
        raise GarminReconnectError("DI token dead")

    monkeypatch.setattr(GarminClient, "from_token", classmethod(dead))
    out = _sweep(db_session, host, log)
    assert out["per_user"][1]["status"] == "succeeded" and out["per_user"][1]["wellness"]["sleep_inserted"] == 1
    assert "spo2_read" not in log                                                  # no read with a token known dead
    assert "error" in out["per_user"][1]["spo2"]
    r = _lane(db_session, 1, "di_spo2")
    assert r.outcome == "auth_failed" and r.last_success_at is None


def test_a_dead_personal_key_skips_the_personal_lanes_but_the_DI_spo2_lane_still_runs(db_session, host, monkeypatch):
    _user(db_session)
    _personal_row(db_session, key="revoked")
    _di_row(db_session)
    log = []

    class FakeDI:
        def dump_token(self): return "B"

    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: FakeDI()))
    out = _sweep(db_session, host, log)
    u = out["per_user"][1]
    assert u["status"] == "reconnect_required" and "selfeval" not in u and "wellness" not in u
    assert "spo2_read" in log and _lane(db_session, 1, "di_spo2").outcome == "ok"
    assert _lane(db_session, 1, "personal_token").outcome == "auth_failed"


def test_a_legacy_DI_only_user_is_unchanged_no_extra_login_and_the_lane_is_recorded(db_session, monkeypatch):
    _user(db_session)
    _di_row(db_session)
    log = []

    class FakeDI:
        def dump_token(self): return "B"
        def get_hrv_range(self, s, e): return []
        def profile_id(self): return "p"

    logins = []
    monkeypatch.setattr(GarminClient, "from_token", classmethod(lambda cls, blob: logins.append(1) or FakeDI()))
    out = garmin_sync.sweep_garmin_hrv(db_session, days=1, selfeval_factory=lambda b: NoActivities(),
                                       spo2_factory=lambda b: DISpo2Source(log))
    assert out["per_user"][1]["status"] == "succeeded" and len(logins) == 1       # the HRV step's login only
    assert _lane(db_session, 1, "di_spo2").outcome == "ok"


def test_a_failing_wellness_endpoint_is_a_recorded_lane_failure_not_a_crashed_sweep(db_session, host, monkeypatch):
    _user(db_session)
    _personal_row(db_session)
    populate(host, TS)
    host.status_for[gp.SLEEP_PATH] = 503
    out = _sweep(db_session, host, [])
    assert out["per_user"][1]["status"] == "succeeded" and "error" in out["per_user"][1]["wellness"]
    r = _lane(db_session, 1, "personal_wellness")
    assert r.outcome == "error" and "503" in r.reason and out["wellness"]["errors"] == 1


def test_wellness_window_on_the_nightly_sweep_is_the_last_few_days_and_an_explicit_window_is_honoured(db_session, host):
    _user(db_session)
    _personal_row(db_session)
    garmin_sync.sweep_garmin_hrv(db_session, days=7, selfeval_factory=lambda b: NoActivities(),
                                 personal_transport=host.transport())
    sleep_dates = sorted({p["date"] for m, path, p in host.requests if path == gp.SLEEP_PATH})
    assert len(sleep_dates) == garmin_sync.WELLNESS_SWEEP_DAYS + 1 and sleep_dates[-1] == TS
    host.requests.clear()
    garmin_sync.sweep_garmin_hrv(db_session, start=TODAY - timedelta(days=6), end=TODAY,
                                 selfeval_factory=lambda b: NoActivities(), personal_transport=host.transport())
    assert len({p["date"] for m, path, p in host.requests if path == gp.SLEEP_PATH}) == 7


def test_no_personal_key_means_run_lane_skips_without_touching_the_network(db_session):
    _user(db_session)
    out = gpl.run_lane(db_session, 1, "personal_wellness", lambda c: {"x": 1})
    assert out == {"skipped": "no_personal_key"} and _lane(db_session, 1, "personal_wellness") is None
