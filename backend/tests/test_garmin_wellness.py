"""The wellness lane (garmin_wellness): mappers, stores, traps, remap, and the whole lane over a fake host."""
from datetime import date, datetime, timedelta, timezone

import pytest

import garmin_raw
import garmin_wellness as gw
import models
from connectors import garmin_personal as gp
from garmin_personal_fakes import (
    FakeHost, body_battery_payload, heart_rate_payload, hr_zones_payload, populate, sleep_payload,
    spo2_hourly_payload, stress_payload,
)

D = date(2026, 10, 24)
DS = D.isoformat()
NOW = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.commit()


# -- mappers: sleep ----------------------------------------------------------------------------------

def test_sleep_maps_every_named_field_in_gmt_and_derives_efficiency_with_its_formula_tag():
    n = gw.parse_sleep(sleep_payload(DS), D)
    assert n["captured_at"] == D
    assert n["sleep_start"] == datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    assert n["sleep_end"] == datetime(2026, 10, 24, 20, 0, tzinfo=timezone.utc)
    assert (n["sleep_time_s"], n["deep_s"], n["light_s"], n["rem_s"], n["awake_s"]) == (27000, 5400, 16200, 5400, 1800)
    assert (n["respiration_avg"], n["respiration_low"], n["respiration_high"]) == (14.0, 10.0, 19.0)
    assert (n["spo2_avg_pct"], n["spo2_lowest_pct"]) == (95.0, 88.0)
    assert n["sleep_score"] == 81 and "totalDuration" in n["sleep_scores_subs"] and "overall" not in n["sleep_scores_subs"]
    assert (n["awake_count"], n["avg_sleep_stress"]) == (3, 17.5)
    assert n["sleep_need"] == {"baseline": 480, "actual": 470}
    assert n["efficiency_pct"] == 93.8 and n["efficiency_formula"] == gw.EFFICIENCY_FORMULA     # 27000 / 28800


def test_TRAP_averageSpO2HRSleep_is_a_heart_rate_and_is_never_the_spo2():
    p = sleep_payload(DS)
    del p["dailySleepDTO"]["averageSpO2Value"]                                  # only the HR-named field remains
    n = gw.parse_sleep(p, D)
    assert n["spo2_avg_pct"] is None and 51.0 not in n.values()


def test_TRAP_the_profile_timezone_plays_no_part_times_are_the_gmt_instants_sent():
    p = sleep_payload(DS)
    p["dailySleepDTO"]["timeZone"] = "Pacific/Port_Moresby"                     # the trap seen in the probe
    p["timeZone"] = "Pacific/Port_Moresby"
    n = gw.parse_sleep(p, D)
    assert n["sleep_start"].utcoffset() == timedelta(0) and n["sleep_start"].hour == 12


def test_TRAP_calendar_date_is_the_wake_date_and_wins_over_the_asked_date_when_they_differ():
    assert gw.parse_sleep(sleep_payload("2026-10-25"), D)["captured_at"] == date(2026, 10, 25)
    p = sleep_payload(DS)
    del p["dailySleepDTO"]["calendarDate"]
    assert gw.parse_sleep(p, D)["captured_at"] == D


def test_an_efficiency_that_cannot_be_right_is_no_figure_rather_than_a_clamped_one():
    over = gw.parse_sleep(sleep_payload(DS, tst=40000), D)                      # more sleep than the window holds
    assert over["efficiency_pct"] is None and over["efficiency_formula"] is None
    no_window = sleep_payload(DS)
    del no_window["dailySleepDTO"]["sleepEndTimestampGMT"]
    assert gw.parse_sleep(no_window, D)["efficiency_pct"] is None


def test_flat_sleep_payloads_and_empty_ones():
    flat = sleep_payload(DS)["dailySleepDTO"]
    assert gw.parse_sleep(flat, D)["sleep_time_s"] == 27000
    for empty in (None, {}, [], {"dailySleepDTO": {"calendarDate": DS}}):
        assert gw.parse_sleep(empty, D) is None


# -- mappers: the rest ------------------------------------------------------------------------------

def test_TRAP_daily_rhr_comes_from_the_daily_heart_rate_payload_and_null_samples_are_skipped():
    hr = gw.parse_heart_rate(heart_rate_payload(DS, resting=48))
    assert hr["resting"] == 48 and hr["rhr_7d_avg"] == 49
    assert len(hr["samples"]) == 4 and all(b > 0 for _, b in hr["samples"])
    assert hr["samples"][0][0] == datetime.fromtimestamp(1761264000, tz=timezone.utc)
    assert gw.parse_heart_rate({}) is None


def test_hourly_spo2_reads_pairs_and_objects_and_keeps_the_first_of_a_repeated_hour():
    h = gw.parse_spo2_hourly(spo2_hourly_payload(DS))
    assert len(h) == 24 and h == sorted(h)
    objs = gw.parse_spo2_hourly({"spO2HourlyAverages": [{"startGMT": "2026-10-24T01:00:00.0", "value": 96},
                                                        {"startGMT": "2026-10-24T01:00:00.0", "value": 90}]})
    assert objs == [(datetime(2026, 10, 24, 1, tzinfo=timezone.utc), 96.0)]
    assert gw.parse_spo2_hourly(None) == [] and gw.parse_spo2_hourly({"x": 1}) == []


def test_body_battery_stress_and_hr_zones():
    assert gw.parse_body_battery(body_battery_payload(DS)) == {"high": 85, "low": 12, "charged": 60, "drained": 45}
    newer = [{"charged": 1, "bodyBatteryValuesArray": [[1, "MEASURED", 40, 1.0], [2, "MEASURED", 70, 1.0]]}]
    assert gw.parse_body_battery(newer)["high"] == 70
    assert gw.parse_body_battery([]) is None
    assert gw.parse_stress(stress_payload(DS), D) == {"avg": 29, "max": 91}
    assert gw.parse_stress({"values": [{"calendarDate": "2026-10-01", "values": {"overallStressLevel": 1}},
                                       {"calendarDate": "2026-10-02", "values": {"overallStressLevel": 2}}]}, D) is None
    z = gw.parse_hr_zones(hr_zones_payload())
    assert z == {"max_hr": 190, "lthr": 168, "rhr_7d_auto": 49, "method": "HR_RESERVE"}
    assert gw.parse_hr_zones([{"sport": "RUNNING", "maxHeartRate": 1}, {"sport": "DEFAULT", "maxHeartRate": 190}])["max_hr"] == 190
    assert gw.parse_hr_zones({"unrelated": 1}) is None


# -- stores -----------------------------------------------------------------------------------------

def test_sleep_upserts_on_the_wake_date_and_stamps_source_and_transport(db_session):
    _user(db_session)
    n = gw.parse_sleep(sleep_payload(DS), D)
    assert gw.store_sleep(db_session, 1, n) == "inserted"
    n2 = dict(n, awake_count=9)
    assert gw.store_sleep(db_session, 1, n2) == "updated"
    db_session.commit()
    row = db_session.query(models.SleepNight).one()
    assert (row.source, row.transport, row.awake_count) == ("garmin", "personal_api", 9)


def test_daily_physiology_merges_the_three_endpoints_into_one_row_and_never_nulls_a_value(db_session):
    _user(db_session)
    gw.store_daily_physiology(db_session, 1, D, resting_hr_bpm=48)
    gw.store_daily_physiology(db_session, 1, D, stress_avg=29, stress_max=91)
    gw.store_daily_physiology(db_session, 1, D, body_battery_high=85, resting_hr_bpm=None)
    db_session.commit()
    row = db_session.query(models.DailyPhysiology).one()
    assert (row.resting_hr_bpm, row.stress_avg, row.body_battery_high) == (48, 29, 85)


def test_hr_samples_land_as_garmin_personal_api_and_a_replay_inserts_nothing(db_session):
    _user(db_session)
    s = gw.parse_heart_rate(heart_rate_payload(DS))["samples"]
    assert gw.store_hr_samples(db_session, 1, s) == 4
    db_session.commit()
    assert gw.store_hr_samples(db_session, 1, s) == 0
    rows = db_session.query(models.HrSample).all()
    assert {(r.source, r.source_package) for r in rows} == {("garmin", "personal_api")}


def test_hr_zone_snapshot_appends_only_on_change_and_never_touches_user_hrmax(db_session):
    _user(db_session)
    z = gw.parse_hr_zones(hr_zones_payload(190))
    assert gw.store_hr_zone_snapshot(db_session, 1, z, "h1", now=NOW) is True
    assert gw.store_hr_zone_snapshot(db_session, 1, z, "h2", now=NOW + timedelta(days=1)) is False
    assert gw.store_hr_zone_snapshot(db_session, 1, gw.parse_hr_zones(hr_zones_payload(188)), "h3",
                                     now=NOW + timedelta(days=2)) is True
    db_session.commit()
    rows = db_session.query(models.HrZoneConfigSnapshot).order_by(models.HrZoneConfigSnapshot.id).all()
    assert [r.max_hr_bpm for r in rows] == [190, 188] and rows[0].rhr_7d_auto_bpm == 49
    assert db_session.query(models.UserHrmax).count() == 0


def test_spo2_hourly_is_an_upsert(db_session):
    _user(db_session)
    h = gw.parse_spo2_hourly(spo2_hourly_payload(DS))
    assert gw.store_spo2_hourly(db_session, 1, h) == 24
    assert gw.store_spo2_hourly(db_session, 1, h) == 0
    db_session.commit()
    assert db_session.query(models.Spo2Hourly).count() == 24


# -- the lane, over a fake host ----------------------------------------------------------------------

def _client(host):
    return gp.PersonalClient(host.key, transport=host.transport(), now=lambda: NOW)


def test_the_lane_lands_raw_then_maps_every_endpoint_and_a_second_run_changes_nothing(db_session):
    _user(db_session)
    host = FakeHost(now=NOW)
    populate(host, DS)
    with _client(host) as c:
        first = gw.sync_user(db_session, 1, c, start=D, end=D, now=NOW)
        second = gw.sync_user(db_session, 1, c, start=D, end=D, now=NOW)
    assert first["payloads_landed"] == 6 and first["sleep_inserted"] == 1 and first["hr_samples"] == 4
    assert first["spo2_hours"] == 24 and first["hr_zone_snapshots"] == 1 and first["unmapped"] == 0
    assert second["payloads_landed"] == 0 and second["payloads_unchanged"] == 6
    assert second["sleep_inserted"] == 0 and second["hr_samples"] == 0 and second["hr_zone_snapshots"] == 0
    assert db_session.query(models.GarminRawPayload).count() == 6
    phys = db_session.query(models.DailyPhysiology).one()
    assert (phys.resting_hr_bpm, phys.stress_avg, phys.body_battery_high) == (48, 29, 85)
    assert "userProfilePK" not in str([r.payload for r in db_session.query(models.GarminRawPayload)])


def test_days_garmin_has_nothing_for_are_counted_empty_not_errors(db_session):
    _user(db_session)
    host = FakeHost(now=NOW)                                    # no routes: every GET is a 404
    with _client(host) as c:
        counts = gw.sync_user(db_session, 1, c, start=D, end=D, with_zones=False, now=NOW)
    assert counts["empty"] == 5 and counts["payloads_landed"] == 0


def test_the_lane_stops_at_the_first_failure_with_the_counts_so_far_attached(db_session):
    _user(db_session)
    host = FakeHost(now=NOW)
    for d in ("2026-10-23", "2026-10-24"):
        populate(host, d)
    host.status_for[gp.HEART_RATE_PATH] = 429                    # heart rate is the 2nd endpoint of each day
    with _client(host) as c, pytest.raises(gp.PersonalRateLimited) as err:
        gw.sync_user(db_session, 1, c, start=date(2026, 10, 23), end=D, now=NOW)
    assert err.value.counts["payloads_landed"] == 1              # day 1's sleep was landed; nothing after the 429
    assert not any(p == gp.SLEEP_PATH and prm["date"] == "2026-10-24" for _, p, prm in host.requests)


def test_a_payload_the_mapper_cannot_read_is_landed_and_counted_unmapped_not_lost(db_session):
    _user(db_session)
    host = FakeHost(now=NOW)
    host.set(gp.STRESS_PATH.format(start=DS, end=DS), {"somethingNew": [1, 2]})
    with _client(host) as c:
        counts = gw.sync_user(db_session, 1, c, start=D, end=D, with_zones=False, now=NOW)
    assert counts["payloads_landed"] == 1 and counts["unmapped"] == 1
    assert db_session.query(models.DailyPhysiology).count() == 0


def test_remap_rebuilds_the_canonical_rows_from_the_landed_payloads_with_no_network(db_session):
    _user(db_session)
    host = FakeHost(now=NOW)
    populate(host, DS)
    with _client(host) as c:
        gw.sync_user(db_session, 1, c, start=D, end=D, with_zones=False, now=NOW)
    db_session.query(models.SleepNight).delete()
    db_session.query(models.DailyPhysiology).delete()
    db_session.commit()
    counts = gw.remap_user(db_session, 1, start=D, end=D, now=NOW)
    assert counts["sleep_inserted"] == 1
    assert db_session.query(models.SleepNight).count() == 1 and db_session.query(models.DailyPhysiology).count() == 1


# -- a day with no data: the real host answers 200 with every value null (25 Oct 2026) ----------------

def test_a_null_skeleton_is_empty_and_anything_with_a_real_value_or_an_unknown_shape_is_not():
    skel = {"userProfilePK": 1, "calendarDate": DS, "restingHeartRate": None, "heartRateValues": None}
    assert gw._is_empty(skel)
    assert gw._is_empty([{"date": DS, "charged": None, "bodyBatteryValuesArray": [[1, None], [2, None]]}])
    assert gw._is_empty(None) and gw._is_empty({}) and gw._is_empty([])
    assert not gw._is_empty({"calendarDate": DS, "restingHeartRate": 48})
    assert not gw._is_empty({"calendarDate": DS, "heartRateValues": [[1, 55]]})
    assert not gw._is_empty({"somethingNew": [1, 2]})                         # unknown shape: kept, not dropped
    assert not gw._is_empty({"value": 0})                                     # zero is a value


def test_skeleton_days_are_counted_empty_and_land_nothing(db_session):
    from garmin_personal_fakes import skeleton_day
    _user(db_session)
    host = FakeHost(now=NOW)
    skeleton_day(host, DS)
    with _client(host) as c:
        counts = gw.sync_user(db_session, 1, c, start=D, end=D, with_zones=False, now=NOW)
    assert counts["empty"] == 5 and counts["payloads_landed"] == 0 and counts["unmapped"] == 0
    assert db_session.query(models.GarminRawPayload).count() == 0


def test_the_real_payload_shapes_probed_in_prod_map_as_written():
    """Shapes read from the live host (keys and types, 25 Oct 2026): sleep is FLAT with epoch-ms GMT times,
    hourly SpO2 rows are [ts, level, extra], body battery rows are [ts, level], stress is a list of
    {calendarDate, values}, and the HR-zone endpoint returns one object per sport."""
    sleep = {"calendarDate": DS, "sleepTimeSeconds": 25000, "sleepStartTimestampGMT": 1792764000000,
             "sleepEndTimestampGMT": 1792792800000, "averageSpO2Value": 95.0, "lowestSpO2Value": 88,
             "averageSpO2HRSleep": 51.0, "awakeCount": 2, "avgSleepStress": 14.5,
             "sleepScores": {"overall": {"value": 70, "qualifierKey": "FAIR"}, "stress": {"qualifierKey": "FAIR"}},
             "sleepNeed": {"baseline": 470, "actual": 510}}
    n = gw.parse_sleep(sleep, D)
    assert n["sleep_start"].tzinfo is not None and n["sleep_score"] == 70 and n["spo2_avg_pct"] == 95.0
    hours = gw.parse_spo2_hourly({"spO2HourlyAverages": [[1792764000000, 97, 15.6], [1792767600000, 98, 15.6]]})
    assert [h[1] for h in hours] == [97.0, 98.0]
    assert gw.parse_body_battery([{"charged": 5, "drained": 3, "bodyBatteryValuesArray": [[1, 29], [2, 90]]}])["high"] == 90
    assert gw.parse_stress([{"calendarDate": DS, "values": {"overallStressLevel": 33}}], D) == {"avg": 33, "max": None}
    zones = [{"sport": "RUNNING", "maxHeartRateUsed": 1}, {"sport": "DEFAULT", "trainingMethod": "HR_RESERVE",
             "restingHeartRateUsed": 52, "lactateThresholdHeartRateUsed": 157, "maxHeartRateUsed": 177}]
    assert gw.parse_hr_zones(zones) == {"max_hr": 177, "lthr": 157, "rhr_7d_auto": 52, "method": "HR_RESERVE"}
