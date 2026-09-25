"""HC sleep session clocks, persisted source-agnostically (#NEXT, sleep brief PR2).

The night's MAIN period (#254/#256 — the one the duration comes from) now also yields
`sleep_start` / `sleep_end` (earliest / latest segment edge, each tagged with the writer
package of the segment that supplies it) and `sleep_onset` (first ASLEEP stage from a REAL
stage record; a stageless session's synthetic span never counts). The diary's `final_wake`
prefills from today's `sleep_end` whatever the writer, labelled by a package LOOKUP — no
per-device branch. Entry-side fields are never filled from HC (#127; S7 rules later).

Gates: G3 Garmin-only night · G4 Samsung-Health-only night (identical path) · G5 mixed-writer
main period · G6 real-stage onset vs stageless NULL · G7 06:00 AEST → "06:00".
Timestamps carry explicit offsets so wake-date and instants are unambiguous.
"""
from datetime import date, datetime, timezone

import models
from routers.checkin_v2 import _today_aest, get_prefill
from routers.health_connect import (
    SleepSession,
    SleepStage,
    SleepStageType,
    SyncPayload,
    _aggregate_day,
)

_GARMIN = "com.garmin.android.apps.connectmobile"
_SHEALTH = "com.sec.android.app.shealth"


def _iso(day: date, hhmm: str, prev: bool = False) -> str:
    """An AEST (+10:00) ISO instant on `day` (or the evening before, prev=True)."""
    from datetime import timedelta
    d = day - timedelta(days=1) if prev else day
    return f"{d.isoformat()}T{hhmm}:00+10:00"


def _stage(stage, start, end):
    return SleepStage(stage=stage, startTime=start, endTime=end)


def _sess(start, end, source, stages=None):
    return SleepSession(startTime=start, endTime=end, sourcePackage=source, stages=stages or [])


def _payload(*sessions):
    return SyncPayload(sleep=list(sessions), hrv=[], heartRate=[], steps=[], workouts=[])


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def _night(day, source, *, bed="22:30", onset="22:50", wake="06:00"):
    """One writer's night: AWAKE in bed → LIGHT/DEEP/REM → wake at `wake` (AEST)."""
    return _sess(
        _iso(day, bed, prev=True), _iso(day, wake), source,
        stages=[
            _stage(SleepStageType.AWAKE, _iso(day, bed, prev=True), _iso(day, onset, prev=True)),
            _stage(SleepStageType.LIGHT, _iso(day, onset, prev=True), _iso(day, "01:00")),
            _stage(SleepStageType.DEEP, _iso(day, "01:00"), _iso(day, "02:30")),
            _stage(SleepStageType.REM, _iso(day, "02:30"), _iso(day, wake)),
        ],
    )


# ── helpers for the prefill path ─────────────────────────────────────────────────
def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _open_block(db, uid):
    b = models.CBTIBlock(user_id=uid, opened_on=date(2026, 7, 1),
                         wake_anchor="05:00", open_reason="test")
    db.add(b); db.commit(); db.refresh(b)
    db.add(models.CBTIPrescription(block_id=b.id, effective_from=date(2026, 7, 1),
                                   prescribed_lights_out="22:30", wake_anchor="05:00",
                                   window_minutes=390, decision="adopt"))
    db.commit()


def _store(db, uid, day, payload):
    agg = _aggregate_day(day, payload)
    db.add(models.HealthConnectSync(user_id=uid, **agg))
    db.commit()
    return agg


# ── G3 / G4: one writer → identical path, label names that device ────────────────
def _assert_single_writer_night(db_session, source, label, email):
    day = _today_aest()
    u = _user(db_session, email)
    _open_block(db_session, u.id)
    agg = _store(db_session, u.id, day, _payload(_night(day, source)))

    assert agg["sleep_start"] == _utc(_iso(day, "22:30", prev=True))
    assert agg["sleep_end"] == _utc(_iso(day, "06:00"))
    assert agg["sleep_onset"] == _utc(_iso(day, "22:50", prev=True))
    assert agg["sleep_start_source_package"] == source
    assert agg["sleep_end_source_package"] == source

    dp = get_prefill(current_user=u, db=db_session).diary_prefill
    assert dp.final_wake == "06:00"
    assert dp.sources == {"final_wake": label}
    # Entry-side fields are never filled from HC (#127; S7 rules later).
    assert (dp.got_into_bed, dp.lights_out, dp.out_of_bed) == (None, None, None)


def test_g3_garmin_only_night(db_session):
    _assert_single_writer_night(db_session, _GARMIN, "Garmin", "g3@x.io")


def test_g4_samsung_health_only_night_takes_the_identical_path(db_session):
    _assert_single_writer_night(db_session, _SHEALTH, "Samsung Health", "g4@x.io")


# ── G5: mixed-writer main period ────────────────────────────────────────────────
def test_g5_mixed_writer_period_takes_each_edge_from_its_own_writer(db_session):
    """Samsung Health opens the night (22:10), Garmin closes it (06:20); the two overlap
    into ONE main period. Start comes from Samsung Health, end from Garmin, and the diary
    label is the END writer."""
    day = _today_aest()
    u = _user(db_session, "g5@x.io")
    _open_block(db_session, u.id)
    early = _sess(_iso(day, "22:10", prev=True), _iso(day, "03:00"), _SHEALTH, stages=[
        _stage(SleepStageType.LIGHT, _iso(day, "22:10", prev=True), _iso(day, "03:00"))])
    late = _sess(_iso(day, "01:00"), _iso(day, "06:20"), _GARMIN, stages=[
        _stage(SleepStageType.DEEP, _iso(day, "01:00"), _iso(day, "06:20"))])
    agg = _store(db_session, u.id, day, _payload(early, late))

    assert agg["sleep_start"] == _utc(_iso(day, "22:10", prev=True))
    assert agg["sleep_start_source_package"] == _SHEALTH
    assert agg["sleep_end"] == _utc(_iso(day, "06:20"))
    assert agg["sleep_end_source_package"] == _GARMIN

    dp = get_prefill(current_user=u, db=db_session).diary_prefill
    assert dp.final_wake == "06:20" and dp.sources["final_wake"] == "Garmin"


# ── G6: onset is real-stage only ────────────────────────────────────────────────
def test_g6_onset_is_first_real_asleep_stage():
    day = date(2026, 9, 25)
    agg = _aggregate_day(day, _payload(_night(day, _GARMIN, bed="22:00", onset="22:40")))
    assert agg["sleep_onset"] == _utc(_iso(day, "22:40", prev=True))   # AWAKE skipped


def test_g6_stageless_session_has_null_onset_but_keeps_its_clocks():
    day = date(2026, 9, 25)
    agg = _aggregate_day(day, _payload(
        _sess(_iso(day, "23:00", prev=True), _iso(day, "06:30"), _SHEALTH)))
    assert agg["sleep_onset"] is None                           # synthetic span never counts
    assert agg["sleep_start"] == _utc(_iso(day, "23:00", prev=True))
    assert agg["sleep_end"] == _utc(_iso(day, "06:30"))
    assert agg["sleep_duration_minutes"] == 450                 # #254 duration unchanged


# ── G7: timezone ────────────────────────────────────────────────────────────────
def test_g7_session_ending_0600_aest_stores_the_instant_and_prefills_0600(db_session):
    """06:00 AEST == 20:00 UTC the previous calendar day: the stored instant is exact and
    the prefill renders it in local time."""
    day = _today_aest()
    u = _user(db_session, "g7@x.io")
    _open_block(db_session, u.id)
    agg = _store(db_session, u.id, day, _payload(_night(day, _GARMIN, wake="06:00")))
    assert agg["sleep_end"].astimezone(timezone.utc).hour == 20
    assert get_prefill(current_user=u, db=db_session).diary_prefill.final_wake == "06:00"


# ── fallback + same-day ─────────────────────────────────────────────────────────
def test_samsung_scrape_is_the_final_wake_fallback_when_hc_has_no_clock(db_session):
    day = _today_aest()
    u = _user(db_session, "fb@x.io")
    _open_block(db_session, u.id)
    db_session.add(models.SamsungHRVReading(user_id=u.id, captured_at=day, bedtime="22:35",
                                            wake_time="05:05", context="passive_overnight"))
    db_session.commit()
    dp = get_prefill(current_user=u, db=db_session).diary_prefill
    assert dp.final_wake == "05:05" and dp.sources["final_wake"] == "Galaxy Ring"


def test_yesterdays_hc_clock_never_prefills_today(db_session):
    from datetime import timedelta
    day = _today_aest()
    u = _user(db_session, "yday@x.io")
    _open_block(db_session, u.id)
    _store(db_session, u.id, day - timedelta(days=1),
           _payload(_night(day - timedelta(days=1), _GARMIN)))
    dp = get_prefill(current_user=u, db=db_session).diary_prefill
    assert dp.final_wake is None and dp.sources == {}
