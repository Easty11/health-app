"""Q247 and Q248: the diary TST beside the device TST, flagged when the device is 60 min or more below it, and for
a flagged night which way the device window falls short of the diary night: started late, finished early, or broken
up (the window covers the night and the gap is awake time inside it). The stored number is never changed; a night
with no diary TST gets no note and no flag. Device data is shown beside the diary here; nothing in this module
feeds CBT-I (the I1 firewall is untouched).

The 29 Oct 2026 night is the anchor: the watch kept only the 01:39 to 06:11 stint (248 min) of a night the
operator went to bed for at 21:25. The numbers here are synthetic stand-ins of the shapes seen in prod.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from reads.recovery_night import (
    PARTIAL_NIGHT_MIN, WINDOW_TOLERANCE_MIN, load_device_nights, load_diary, partial_note, recovery_text,
)
from reads.snapshot_reads import latest_sleep_night, sleep_snapshot_lines
from tests.test_recovery_personal_api import _hc_night

NIGHT = date(2026, 10, 29)
DASH = "–"
AEST = timezone(timedelta(hours=10))


def at(day: date, h: int, m: int = 0) -> datetime:
    """A Brisbane wall-clock moment, as the UTC instant the table stores."""
    return datetime(day.year, day.month, day.day, h, m, tzinfo=AEST).astimezone(timezone.utc)


EVE = NIGHT - timedelta(days=1)                       # the evening before the wake-date
WIN_START, WIN_END = at(NIGHT, 1, 39), at(NIGHT, 6, 11)          # the 29 Oct stint
WIDE_START = at(EVE, 20, 0)                                       # a long window, for a long device night


@pytest.fixture
def user(db_session):
    u = models.User(email="pn@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    return u


def _api(db, u, night=NIGHT, tst=248, start=WIN_START, end=WIN_END, awake=24):
    db.add(models.SleepNight(
        user_id=u.id, captured_at=night, source="garmin", transport="personal_api",
        sleep_start=start, sleep_end=end, sleep_time_s=tst * 60, deep_s=18 * 60, rem_s=20 * 60,
        light_s=max(tst - 38, 0) * 60, awake_s=awake * 60, sleep_score=50))
    db.commit()


def _diary(db, u, tst, night=NIGHT, lights_out="21:25", final_wake="06:30"):
    db.add(models.DailyRecord(user_id=u.id, date=night, diary_tst_min=tst, lights_out=lights_out,
                              final_wake=final_wake))
    db.commit()


def _line(db, u, night=NIGHT):
    text = recovery_text(db, u.id, night - timedelta(days=1), 3)
    return next(ln for ln in text.splitlines() if ln.startswith(f"{night}:"))


def _dev(start, end, awake=24):
    return {"start": start, "end": end, "awake_min": awake}


# -- the recovery line: the diary beside the device figure ----------------------------------------------

def test_a_night_that_started_late_says_so_with_the_window_beside_the_lights_out(db_session, user):
    _api(db_session, user)
    _diary(db_session, user, 396)
    line = _line(db_session, user)
    assert ("TST=248 min [garmin/api] (diary 396 min; 148 min below the diary; window started late: the device "
            f"window 01:39{DASH}06:11 starts 4 h 14 m after diary lights-out 21:25)") in line
    assert "finished early" not in line and "broken up" not in line
    # annotate, never change: the stored figure, its source tag and the stages are exactly as before
    assert "Sleep score=50 [garmin/api]" in line and "Deep=18m REM=20m Light=210m Awake=24m [garmin/api]" in line


def test_a_night_that_finished_early_says_so_against_the_diary_final_wake(db_session, user):
    _api(db_session, user, tst=203, start=at(EVE, 22, 42), end=at(NIGHT, 3, 9))
    _diary(db_session, user, 439, lights_out="22:16", final_wake="07:05")
    line = _line(db_session, user)
    assert (f"window finished early: the device window 22:42{DASH}03:09 ends 3 h 56 m before diary final wake 07:05"
            in line)
    assert "started late" not in line


def test_a_night_that_started_late_and_finished_early_says_both(db_session, user):
    _api(db_session, user, tst=100, start=at(NIGHT, 1, 0), end=at(NIGHT, 3, 0))
    _diary(db_session, user, 400, lights_out="22:00", final_wake="06:30")
    assert (f"window started late and finished early: the device window 01:00{DASH}03:00 starts 3 h 00 m after "
            "diary lights-out 22:00 and ends 3 h 30 m before diary final wake 06:30") in _line(db_session, user)


def test_a_window_that_covers_the_night_is_broken_up_and_names_the_awake_minutes(db_session, user):
    """18 Oct: the whole night is inside the window and the device scored 180 min awake against a diary TST of 491."""
    _api(db_session, user, tst=336, start=at(EVE, 21, 52), end=at(NIGHT, 6, 28), awake=180)
    _diary(db_session, user, 491, lights_out="21:41", final_wake="06:35")
    line = _line(db_session, user)
    assert (f"window broken up: the device window 21:52{DASH}06:28 covers the night but scores 180 min awake "
            "inside it") in line
    assert "started late" not in line and "finished early" not in line


def test_a_shift_night_with_a_bedtime_after_midnight_is_dated_on_the_wake_date(db_session, user):
    """20 Sep: lights-out 04:31 is after midnight, so it sits on the wake-date, not the evening before."""
    _api(db_session, user, tst=207, start=at(NIGHT, 5, 38), end=at(NIGHT, 9, 30))
    _diary(db_session, user, 294, lights_out="04:31", final_wake="09:30")
    line = _line(db_session, user)
    assert "window started late: the device window 05:38" in line and "starts 1 h 07 m after diary lights-out 04:31" in line
    assert "finished early" not in line


def test_the_sixty_minute_tolerance_is_inclusive_at_both_ends(db_session, user):
    night = NIGHT
    on_time_end = at(night, 6, 30)
    late60 = partial_note(night, 100, "garmin_api", {"tst": 400, "lights_out": "22:00", "final_wake": "06:30"},
                          _dev(at(EVE, 23, 0), on_time_end))
    late59 = partial_note(night, 100, "garmin_api", {"tst": 400, "lights_out": "22:00", "final_wake": "06:30"},
                          _dev(at(EVE, 22, 59), on_time_end))
    assert late60["kinds"] == ["started_late"] and late59["kinds"] == ["broken_up"]
    early60 = partial_note(night, 100, "garmin_api", {"tst": 400, "lights_out": "22:00", "final_wake": "06:30"},
                           _dev(at(EVE, 22, 0), at(night, 5, 30)))
    early59 = partial_note(night, 100, "garmin_api", {"tst": 400, "lights_out": "22:00", "final_wake": "06:30"},
                           _dev(at(EVE, 22, 0), at(night, 5, 31)))
    assert early60["kinds"] == ["finished_early"] and early59["kinds"] == ["broken_up"]
    assert WINDOW_TOLERANCE_MIN == 60


def test_a_missing_diary_clock_never_invents_a_mechanism(db_session, user):
    d = {"tst": 400, "lights_out": "22:00", "final_wake": None}
    # started late is still known from the lights-out alone
    assert partial_note(NIGHT, 100, "garmin_api", d, _dev(at(NIGHT, 1, 0), at(NIGHT, 6, 30)))["kinds"] == ["started_late"]
    # on time at the start, final wake missing: the end is unknown, so "broken up" is not asserted
    n = partial_note(NIGHT, 100, "garmin_api", d, _dev(at(EVE, 22, 10), at(NIGHT, 6, 30)))
    assert n["kinds"] == []
    # lights-out missing as well: nothing to compare
    assert partial_note(NIGHT, 100, "garmin_api", {"tst": 400, "lights_out": None, "final_wake": None},
                        _dev(at(EVE, 22, 10), at(NIGHT, 6, 30)))["kinds"] == []


def test_an_undeterminable_mechanism_keeps_the_generic_sentence_and_the_evidence(db_session, user):
    _api(db_session, user, tst=100, start=at(EVE, 22, 10), end=at(NIGHT, 6, 30))
    _diary(db_session, user, 400, lights_out="22:00", final_wake=None)
    line = _line(db_session, user)
    assert (f"the device may have recorded only part of the night (device window 22:10{DASH}06:30, "
            "diary lights-out 22:00)") in line


# -- thresholds and absences ----------------------------------------------------------------------------

def test_sixty_minutes_below_flags_and_fifty_nine_does_not(db_session, user):
    assert PARTIAL_NIGHT_MIN == 60
    _api(db_session, user)
    _diary(db_session, user, 248 + 60)
    assert "60 min below the diary" in _line(db_session, user)

    other = models.User(email="pn2@example.com", hashed_password="x")
    db_session.add(other)
    db_session.commit()
    _api(db_session, other)
    _diary(db_session, other, 248 + 59)
    line = _line(db_session, other)
    assert "TST=248 min [garmin/api] (diary 307 min)" in line and "below the diary" not in line


def test_a_device_above_the_diary_shows_the_diary_and_no_flag(db_session, user):
    _api(db_session, user, tst=430, start=WIDE_START)
    _diary(db_session, user, 402)
    line = _line(db_session, user)
    assert "TST=430 min [garmin/api] (diary 402 min)" in line and "below the diary" not in line


def test_no_diary_means_no_note_and_no_flag(db_session, user):
    _api(db_session, user)
    assert "diary" not in _line(db_session, user)


def test_a_diary_row_without_a_tst_means_no_note(db_session, user):
    _api(db_session, user)
    db_session.add(models.DailyRecord(user_id=user.id, date=NIGHT, diary_tst_min=None, lights_out="21:30"))
    db_session.commit()
    assert "diary" not in _line(db_session, user)


def test_another_users_diary_is_never_read(db_session, user):
    _api(db_session, user)
    other = models.User(email="pn3@example.com", hashed_password="x")
    db_session.add(other)
    db_session.commit()
    _diary(db_session, other, 480)
    assert "diary" not in _line(db_session, user)


def test_a_health_connect_night_is_flagged_with_the_generic_sentence_and_no_window(db_session, user):
    _hc_night(db_session, user, NIGHT, tst=250)
    _diary(db_session, user, 400)
    line = _line(db_session, user)
    assert "TST=250 min [garmin/HC] (diary 400 min; 150 min below the diary; the device may have recorded only" in line
    assert "diary lights-out 21:25)" in line and "device window" not in line      # HC's sleep_start is not ruled
    assert "started late" not in line and "broken up" not in line


# -- the loaders and the pure rule -----------------------------------------------------------------------

def test_the_loaders_return_the_diary_clocks_and_the_awake_minutes(db_session, user):
    _api(db_session, user, awake=37)
    _diary(db_session, user, 396)
    assert load_diary(db_session, user.id, NIGHT)[NIGHT] == {"tst": 396, "lights_out": "21:25", "final_wake": "06:30"}
    dev = load_device_nights(db_session, user.id, NIGHT)[NIGHT]
    assert dev["awake_min"] == 37 and dev["start"] is not None and dev["end"] is not None


def test_the_note_needs_both_a_device_figure_and_a_diary_figure():
    d = {"tst": 400, "lights_out": "21:30", "final_wake": "06:00"}
    assert partial_note(NIGHT, None, "garmin_api", d, None) is None
    assert partial_note(NIGHT, 300, "garmin_api", None, None) is None


def test_the_window_rides_only_with_the_personal_api_tst():
    d = {"tst": 400, "lights_out": "21:30", "final_wake": "06:00"}
    dev = _dev(WIN_START, WIN_END)
    assert partial_note(NIGHT, 300, "garmin_api", d, dev)["window"] == f"01:39{DASH}06:11"
    hc = partial_note(NIGHT, 300, "garmin_hc", d, dev)
    assert hc["window"] is None and hc["kinds"] == [] and hc["short_min"] == 100


def test_a_naive_stored_window_is_read_as_utc():
    naive = _dev(WIN_START.replace(tzinfo=None), WIN_END.replace(tzinfo=None))     # SQLite returns TIMESTAMPTZ naive
    n = partial_note(NIGHT, 300, "garmin_api", {"tst": 400, "lights_out": "21:30", "final_wake": "06:00"}, naive)
    assert n["window"] == f"01:39{DASH}06:11" and n["kinds"][0] == "started_late"


def test_an_unreadable_diary_clock_is_treated_as_missing():
    n = partial_note(NIGHT, 100, "garmin_api", {"tst": 400, "lights_out": "late", "final_wake": "6.30"},
                     _dev(WIN_START, WIN_END))
    assert n["kinds"] == [] and n["short_min"] == 300


# -- the readiness snapshot and the card ------------------------------------------------------------------

def test_the_snapshot_names_the_mechanism_on_a_flagged_night(db_session, user):
    _api(db_session, user)
    _diary(db_session, user, 396)
    sleep = latest_sleep_night(db_session, user.id)
    assert sleep["duration_min"] == 248                       # the stored number is untouched
    note = sleep["diary_note"]
    assert note["short_min"] == 148 and note["kinds"] == ["started_late"] and note["late_min"] == 254
    lines = sleep_snapshot_lines(sleep)
    assert lines[0] == "  Sleep 4 h 08 m · Garmin (night of 2026-10-29) · diary 6 h 36 m"
    assert lines[1] == ("  Partial night? The device is 2 h 28 m below the diary; window started late: the device "
                        f"window 01:39{DASH}06:11 starts 4 h 14 m after diary lights-out 21:25")


def test_the_snapshot_says_broken_up_when_the_window_covers_the_night(db_session, user):
    _api(db_session, user, tst=336, start=at(EVE, 21, 52), end=at(NIGHT, 6, 28), awake=180)
    _diary(db_session, user, 491, lights_out="21:41", final_wake="06:35")
    lines = sleep_snapshot_lines(latest_sleep_night(db_session, user.id))
    assert lines[1].startswith("  Partial night? The device is 2 h 35 m below the diary; window broken up:")
    assert "scores 180 min awake inside it" in lines[1]


def test_the_snapshot_shows_the_diary_without_a_flag_when_the_device_is_close(db_session, user):
    _api(db_session, user, tst=365, start=WIDE_START)
    _diary(db_session, user, 402)
    lines = sleep_snapshot_lines(latest_sleep_night(db_session, user.id))
    assert lines[0].endswith("· diary 6 h 42 m") and not any("Partial night" in ln for ln in lines)


def test_the_snapshot_is_unchanged_when_no_diary_is_logged(db_session, user):
    _api(db_session, user)
    sleep = latest_sleep_night(db_session, user.id)
    assert sleep["diary_note"] is None
    lines = sleep_snapshot_lines(sleep)
    assert lines[0] == "  Sleep 4 h 08 m · Garmin (night of 2026-10-29)"
    assert not any("diary" in ln or "Partial night" in ln for ln in lines)
