"""Q247: the diary TST beside the device figure, flagged when the device is 60 min or more
below it. The stored number is never changed; a night with no diary TST gets no note and no flag.

The 29 Oct 2026 night is the anchor: the watch kept only the 01:39 to 06:11 stint (248 min) of a night the
operator went to bed for at 21:30. The numbers here are synthetic stand-ins of that shape.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import models
from reads.recovery_night import PARTIAL_NIGHT_MIN, partial_note, recovery_text
from reads.snapshot_reads import latest_sleep_night, sleep_snapshot_lines
from tests.test_recovery_personal_api import _hc_night

NIGHT = date(2026, 10, 29)
DASH = "–"
# 01:39 to 06:11 AEST on the wake-date, as stored: UTC the evening before.
WIN_START = datetime(2026, 10, 28, 15, 39, tzinfo=timezone.utc)
WIN_END = datetime(2026, 10, 28, 20, 11, tzinfo=timezone.utc)


@pytest.fixture
def user(db_session):
    u = models.User(email="pn@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    return u


WIDE_START = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)      # a 9 h 11 m window, for a long device night


def _api(db, u, night=NIGHT, tst=248, start=WIN_START, end=WIN_END):
    db.add(models.SleepNight(
        user_id=u.id, captured_at=night, source="garmin", transport="personal_api",
        sleep_start=start, sleep_end=end, sleep_time_s=tst * 60, deep_s=18 * 60, rem_s=20 * 60,
        light_s=(tst - 38) * 60, awake_s=24 * 60, sleep_score=50))
    db.commit()


def _diary(db, u, tst, night=NIGHT, lights_out="21:30"):
    db.add(models.DailyRecord(user_id=u.id, date=night, diary_tst_min=tst, lights_out=lights_out))
    db.commit()


def _line(db, u, night=NIGHT):
    text = recovery_text(db, u.id, night - timedelta(days=1), 3)
    return next(ln for ln in text.splitlines() if ln.startswith(f"{night}:"))


# -- the recovery line ---------------------------------------------------------------------------------

def test_a_night_the_device_cut_short_is_flagged_with_the_window_beside_the_diary_lights_out(db_session, user):
    _api(db_session, user)
    _diary(db_session, user, 370)
    line = _line(db_session, user)
    assert ("TST=248 min [garmin/api] (diary 370 min; 122 min below the diary, so the device may have recorded "
            f"only part of the night: device window 01:39{DASH}06:11, diary lights-out 21:30)") in line
    # annotate, never change: the stored figure, its source tag and the score are exactly as before
    assert "Sleep score=50 [garmin/api]" in line and "Deep=18m REM=20m Light=210m Awake=24m [garmin/api]" in line


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


def test_a_health_connect_night_is_flagged_without_a_window(db_session, user):
    _hc_night(db_session, user, NIGHT, tst=250)
    _diary(db_session, user, 400)
    line = _line(db_session, user)
    assert "TST=250 min [garmin/HC] (diary 400 min; 150 min below the diary" in line
    assert "diary lights-out 21:30)" in line and "device window" not in line      # HC's sleep_start is not ruled


# -- the pure rule ---------------------------------------------------------------------------------------

def test_the_note_needs_both_a_device_figure_and_a_diary_figure():
    assert partial_note(None, "garmin_api", {"tst": 400, "lights_out": "21:30"}, None) is None
    assert partial_note(300, "garmin_api", None, None) is None
    n = partial_note(300, "garmin_api", {"tst": 400, "lights_out": None}, None)
    assert n == {"diary_tst": 400, "lights_out": None, "short_min": 100, "window": None}


def test_the_window_rides_only_with_the_personal_api_tst():
    d = {"tst": 400, "lights_out": "21:30"}
    assert partial_note(300, "garmin_api", d, (WIN_START, WIN_END))["window"] == f"01:39{DASH}06:11"
    assert partial_note(300, "garmin_hc", d, (WIN_START, WIN_END))["window"] is None


def test_a_naive_stored_window_is_read_as_utc(db_session):
    naive = (WIN_START.replace(tzinfo=None), WIN_END.replace(tzinfo=None))     # SQLite hands TIMESTAMPTZ back naive
    assert partial_note(300, "garmin_api", {"tst": 400, "lights_out": None}, naive)["window"] == f"01:39{DASH}06:11"


# -- the readiness snapshot and the card ------------------------------------------------------------------

def test_the_snapshot_flags_a_cut_short_night(db_session, user):
    _api(db_session, user)
    _diary(db_session, user, 370)
    sleep = latest_sleep_night(db_session, user.id)
    assert sleep["duration_min"] == 248                       # the stored number is untouched
    assert sleep["diary_note"]["short_min"] == 122 and sleep["diary_note"]["window"] == f"01:39{DASH}06:11"
    lines = sleep_snapshot_lines(sleep)
    assert lines[0] == "  Sleep 4 h 08 m · Garmin (night of 2026-10-29) · diary 6 h 10 m"
    assert lines[1] == ("  Partial night? The device is 2 h 02 m below the diary, so it may have recorded only part "
                        f"of the night (device window 01:39{DASH}06:11, diary lights-out 21:30)")


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
