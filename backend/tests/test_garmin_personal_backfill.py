"""The one-shot backfill: dry run by default, stops where Garmin's data stops, idempotent and resumable."""
from datetime import date, datetime, timedelta, timezone

import models
from connectors import garmin_personal as gp
from garmin_personal_fakes import FakeHost, populate
from scripts import garmin_personal_backfill as bf

NEWEST = date(2026, 10, 24)


def _user(db):
    db.add(models.User(id=1, email="u@example.com", hashed_password="x"))
    db.commit()


def _client(host):
    return gp.PersonalClient(host.key, transport=host.transport())


def _host_with_history(days=5):
    host = FakeHost()
    for i in range(days):
        populate(host, (NEWEST - timedelta(days=i)).isoformat())
    return host


def _run(db, host, **kw):
    with _client(host) as c:
        return bf.backfill(db, 1, c, newest=NEWEST, stop_after_empty=kw.pop("stop", 3), confirm=kw.pop("confirm", False),
                           pause=0, sleep=lambda s: None, **kw)


def test_a_dry_run_fetches_and_counts_but_writes_no_data(db_session):
    _user(db_session)
    out = _run(db_session, _host_with_history())
    assert out["days_with_data"] == 5 and out["oldest_with_data"] == "2026-10-20"
    assert out["stopped"] == "empty_streak_3"
    for model in (models.GarminRawPayload, models.SleepNight, models.HrvReading, models.DailyPhysiology,
                  models.HrSample, models.Spo2Hourly, models.HrZoneConfigSnapshot):
        assert db_session.query(model).count() == 0, model.__name__


def test_the_walk_stops_where_the_data_stops_not_at_a_fixed_floor(db_session):
    _user(db_session)
    host = _host_with_history(5)
    out = _run(db_session, host, stop=4)
    assert out["days_walked"] == 5 + 4                      # five days of data, then the empty streak


def test_a_gap_shorter_than_the_streak_does_not_stop_the_walk(db_session):
    _user(db_session)
    host = FakeHost()
    for d in (NEWEST, NEWEST - timedelta(days=1), NEWEST - timedelta(days=4), NEWEST - timedelta(days=5)):
        populate(host, d.isoformat())
    out = _run(db_session, host, stop=3)
    assert out["days_with_data"] == 4 and out["oldest_with_data"] == (NEWEST - timedelta(days=5)).isoformat()


def test_confirm_writes_every_table_and_a_second_run_changes_nothing(db_session):
    _user(db_session)
    host = _host_with_history(3)
    first = _run(db_session, host, confirm=True)
    assert first["hrv_nights"] == 3 and first["payloads_landed"] == 3 * 6
    counts = {m.__name__: db_session.query(m).count() for m in (
        models.GarminRawPayload, models.SleepNight, models.HrvReading, models.DailyPhysiology, models.HrSample,
        models.Spo2Hourly, models.HrZoneConfigSnapshot)}
    assert counts["HrvReading"] == 3 and counts["SleepNight"] == 3 and counts["HrZoneConfigSnapshot"] == 1
    assert db_session.query(models.HrvReading).first().transport == "personal_api"
    second = _run(db_session, host, confirm=True)
    assert second["payloads_landed"] == 0
    assert counts == {m.__name__: db_session.query(m).count() for m in (
        models.GarminRawPayload, models.SleepNight, models.HrvReading, models.DailyPhysiology, models.HrSample,
        models.Spo2Hourly, models.HrZoneConfigSnapshot)}


def test_a_429_mid_walk_raises_and_what_was_written_is_kept_so_a_rerun_resumes(db_session):
    _user(db_session)
    host = _host_with_history(5)
    host.status_for[gp.SLEEP_PATH] = 429
    try:
        _run(db_session, host, confirm=True)
        raise AssertionError("expected PersonalRateLimited")
    except gp.PersonalRateLimited:
        db_session.rollback()
    del host.status_for[gp.SLEEP_PATH]
    out = _run(db_session, host, confirm=True)
    assert out["days_with_data"] == 5 and db_session.query(models.SleepNight).count() == 5
