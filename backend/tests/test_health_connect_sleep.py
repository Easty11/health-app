"""Sleep wake-date attribution for _aggregate_day (OPEN_QUESTIONS Q4).

Canonical rule: a sleep session is attributed to the LOCAL (AEST) calendar date
of its endTime (wake-date) — matching the scraper (samsung_hrv_readings) — and
to that day only. The former bed-date/startTime clause split one physical night
across two rows; under UTC timestamps it collapsed the whole night onto the day
before the local wake-date, one day earlier than the scraper.
"""
from datetime import date

from routers.health_connect import (
    SleepSession,
    SleepStage,
    SleepStageType,
    SyncPayload,
    _aggregate_day,
    _wake_date,
)


def _night(start: str, end: str) -> SleepSession:
    """A session spanning start→end with a fixed deep/rem/light split.

    Stage segments are anchored to the session window so _stage_minutes parses
    them; their exact placement is irrelevant to attribution.
    """
    return SleepSession(
        startTime=start,
        endTime=end,
        stages=[
            SleepStage(stage=SleepStageType.DEEP, startTime=start, endTime=end),
        ],
    )


# ---------- _wake_date: tz correctness across every payload shape ----------

def test_wake_date_utc_z_converts_to_local_aest_date():
    # 20:30Z == 06:30 AEST next calendar day.
    assert _wake_date("2026-07-08T20:30:00Z") == date(2026, 7, 9)


def test_wake_date_utc_naive_treated_as_utc():
    assert _wake_date("2026-07-08T20:30:00") == date(2026, 7, 9)


def test_wake_date_offset_aware_local_preserved():
    assert _wake_date("2026-07-09T06:30:00+10:00") == date(2026, 7, 9)


def test_wake_date_strips_nanosecond_fraction():
    # Android emits nanosecond fractions fromisoformat cannot parse directly.
    assert _wake_date("2026-07-08T20:30:00.123456789Z") == date(2026, 7, 9)


# ---------- _aggregate_day: wake-date-only attribution ----------

def test_midnight_spanning_night_attributes_to_wake_date_only():
    # Bed 23:00 AEST 08 Jul (13:00Z) → wake 06:30 AEST 09 Jul (20:30Z prev day).
    payload = SyncPayload(sleep=[_night("2026-07-08T13:00:00Z", "2026-07-08T20:30:00Z")])

    woke = _aggregate_day(date(2026, 7, 9), payload)
    bed = _aggregate_day(date(2026, 7, 8), payload)

    # Wake-date row carries the night.
    assert woke.get("sleep_duration_minutes") == 450
    # Bed-date row carries nothing — the old dual-write is gone.
    assert "sleep_duration_minutes" not in bed


def test_same_day_nap_does_not_displace_main_night():
    # Main night wakes 09 Jul; a 40-min afternoon nap also wakes 09 Jul (AEST).
    night = _night("2026-07-08T13:00:00Z", "2026-07-08T20:30:00Z")   # 450 min
    nap = _night("2026-07-09T04:00:00Z", "2026-07-09T04:40:00Z")     # 40 min, wakes 09 Jul AEST
    payload = SyncPayload(sleep=[nap, night])

    woke = _aggregate_day(date(2026, 7, 9), payload)

    # Longest-session tiebreak keeps the main night, not the nap.
    assert woke.get("sleep_duration_minutes") == 450


def test_naive_local_night_still_lands_on_wake_date():
    # Even if HCA were to send local-naive timestamps, a morning wake attributes
    # to its own local date (naive treated as UTC only shifts within the day).
    payload = SyncPayload(sleep=[_night("2026-07-08T23:00:00", "2026-07-09T06:30:00")])

    assert _aggregate_day(date(2026, 7, 9), payload).get("sleep_duration_minutes") == 450
    assert "sleep_duration_minutes" not in _aggregate_day(date(2026, 7, 8), payload)
