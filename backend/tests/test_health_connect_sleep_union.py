"""F3a — sleep aggregated as the UNION of asleep stage-intervals over the
wake-date's session set (DECISIONS_LOG #254), not the longest single session.

Canonical rule: total sleep time = union of LIGHT/DEEP/REM stage-intervals across
every session that wakes on this local (AEST) date, clustered into periods so a
same-wake-date daytime nap stays its own period and never merges into the night.
The union is computed from stage segments — never from session.duration(), which
is self-reported and overlaps its neighbours on a fragmented night.

Timestamps carry an explicit +10:00 (AEST) offset so wake-date is unambiguous.
"""
import logging
from datetime import date

from routers.health_connect import (
    SleepSession,
    SleepStage,
    SleepStageType,
    SyncPayload,
    _aggregate_day,
)

_SAMSUNG = "com.sec.android.app.shealth"
_GARMIN = "com.garmin.android.apps.connectmobile"
_DAY = date(2026, 8, 30)


def _stage(stage: SleepStageType, start: str, end: str) -> SleepStage:
    return SleepStage(stage=stage, startTime=start, endTime=end)


def _sess(start, end, stages=None, source=_SAMSUNG, dur=None) -> SleepSession:
    return SleepSession(
        startTime=start,
        endTime=end,
        durationMinutes=dur,
        sourcePackage=source,
        stages=stages or [],
    )


def _payload(*sessions) -> SyncPayload:
    return SyncPayload(
        sleep=list(sessions), hrv=[], heartRate=[], steps=[], workouts=[]
    )


# ---------- the pinned failing night: 4 overlapping single-source sessions ----------

def test_fragmented_night_reports_union_tst_not_longest_fragment():
    """Reproduces wake-date 2026-08-30 (single-source Samsung, 4 overlapping
    sessions): the old longest-session selector stored 305 (one fragment's
    self-reported duration); the union of the night's asleep stage-intervals is
    the true ~402-min total. Every stage here is asleep, so the asleep-union
    equals the contiguous coverage 22:00 -> 04:42 = 402 min."""
    s1 = _sess(
        "2026-08-29T22:00:00+10:00", "2026-08-30T01:00:00+10:00", dur=180,
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-29T22:00:00+10:00", "2026-08-29T23:00:00+10:00"),
            _stage(SleepStageType.DEEP,  "2026-08-29T23:00:00+10:00", "2026-08-29T23:45:00+10:00"),
            _stage(SleepStageType.REM,   "2026-08-29T23:45:00+10:00", "2026-08-30T00:30:00+10:00"),
            _stage(SleepStageType.LIGHT, "2026-08-30T00:30:00+10:00", "2026-08-30T01:00:00+10:00"),
        ],
    )
    s2 = _sess(  # longest single session by self-reported duration -> old picked this
        "2026-08-29T23:00:00+10:00", "2026-08-30T04:05:00+10:00", dur=305,
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-29T23:00:00+10:00", "2026-08-30T00:00:00+10:00"),
            _stage(SleepStageType.DEEP,  "2026-08-30T00:00:00+10:00", "2026-08-30T01:00:00+10:00"),
            _stage(SleepStageType.REM,   "2026-08-30T01:00:00+10:00", "2026-08-30T02:00:00+10:00"),
            _stage(SleepStageType.LIGHT, "2026-08-30T02:00:00+10:00", "2026-08-30T03:00:00+10:00"),
            _stage(SleepStageType.REM,   "2026-08-30T03:00:00+10:00", "2026-08-30T04:05:00+10:00"),
        ],
    )
    s3 = _sess(
        "2026-08-30T00:30:00+10:00", "2026-08-30T03:00:00+10:00", dur=150,
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-30T00:30:00+10:00", "2026-08-30T01:30:00+10:00"),
            _stage(SleepStageType.DEEP,  "2026-08-30T01:30:00+10:00", "2026-08-30T02:15:00+10:00"),
            _stage(SleepStageType.REM,   "2026-08-30T02:15:00+10:00", "2026-08-30T03:00:00+10:00"),
        ],
    )
    s4 = _sess(
        "2026-08-30T02:30:00+10:00", "2026-08-30T04:42:00+10:00", dur=132,
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-30T02:30:00+10:00", "2026-08-30T03:30:00+10:00"),
            _stage(SleepStageType.DEEP,  "2026-08-30T03:30:00+10:00", "2026-08-30T04:00:00+10:00"),
            _stage(SleepStageType.REM,   "2026-08-30T04:00:00+10:00", "2026-08-30T04:42:00+10:00"),
        ],
    )

    row = _aggregate_day(_DAY, _payload(s1, s2, s3, s4))

    assert row["sleep_duration_minutes"] == 402       # union of the night's asleep intervals
    assert row["sleep_duration_minutes"] != 305       # not the longest single fragment
    assert row["sleep_score"] is not None


# ---------- overlap: union, never sum ----------

def test_overlapping_same_source_sessions_union_not_sum():
    """Two overlapping same-source sessions (no stages -> each span is one
    best-effort LIGHT segment). 22:00-00:00 and 23:00-01:00 overlap; their union
    is 22:00-01:00 = 180, not the 240-min sum."""
    a = _sess("2026-08-29T22:00:00+10:00", "2026-08-30T00:00:00+10:00")
    b = _sess("2026-08-29T23:00:00+10:00", "2026-08-30T01:00:00+10:00")

    row = _aggregate_day(_DAY, _payload(a, b))

    assert row["sleep_duration_minutes"] == 180       # union
    assert row["sleep_duration_minutes"] != 240       # not the sum
    assert row["light_sleep_minutes"] == 180          # stageless span -> LIGHT


# ---------- nap exclusion: a same-wake-date nap is a separate period ----------

def test_daytime_nap_stays_separate_period_and_is_excluded():
    """A night (480 min) and a 60-min afternoon nap both wake on 30 Aug AEST.
    The 8-hour gap between night-end (06:00) and nap-start (14:00) exceeds
    SLEEP_PERIOD_GAP_MINUTES, so they cluster into separate periods; the main
    period is the night and the nap is excluded from the reported total."""
    night = _sess("2026-08-29T22:00:00+10:00", "2026-08-30T06:00:00+10:00")
    nap = _sess("2026-08-30T14:00:00+10:00", "2026-08-30T15:00:00+10:00")

    row = _aggregate_day(_DAY, _payload(night, nap))

    assert row["sleep_duration_minutes"] == 480       # night only; nap excluded


# ---------- single-source breakdown: per-stage union, AWAKE excluded ----------

def test_single_source_breakdown_is_per_stage_union_excluding_awake():
    """One Samsung session with an explicit stage sequence including a 15-min
    mid-night AWAKE. TST and the deep/rem/light breakdown are per-stage unions;
    the AWAKE interval is excluded from every asleep total."""
    sess = _sess(
        "2026-08-29T22:00:00+10:00", "2026-08-30T06:00:00+10:00",
        stages=[
            _stage(SleepStageType.DEEP,  "2026-08-29T22:00:00+10:00", "2026-08-29T23:00:00+10:00"),  # 60
            _stage(SleepStageType.REM,   "2026-08-29T23:00:00+10:00", "2026-08-30T00:30:00+10:00"),  # 90
            _stage(SleepStageType.LIGHT, "2026-08-30T00:30:00+10:00", "2026-08-30T05:30:00+10:00"),  # 300
            _stage(SleepStageType.AWAKE, "2026-08-30T05:30:00+10:00", "2026-08-30T05:45:00+10:00"),  # 15 (excluded)
            _stage(SleepStageType.LIGHT, "2026-08-30T05:45:00+10:00", "2026-08-30T06:00:00+10:00"),  # 15
        ],
    )

    row = _aggregate_day(_DAY, _payload(sess))

    assert row["deep_sleep_minutes"] == 60
    assert row["rem_sleep_minutes"] == 90
    assert row["light_sleep_minutes"] == 315          # 300 + 15
    assert row["sleep_duration_minutes"] == 465       # 480 span - 15 AWAKE
    assert row["sleep_score"] == 9


# ---------- multi-source breakdown: union total, dominant-source breakdown + flag ----------

def test_multi_source_total_is_full_union_breakdown_is_dominant_source():
    """A main period stitched from two sources: the union TST spans BOTH sources
    (overlaps collapse), but the deep/rem/light breakdown is taken from the
    dominant source by asleep-minutes (Samsung, 420 > Garmin's 150) and a flag is
    logged. Garmin's overlapping LIGHT does NOT inflate the LIGHT breakdown."""
    samsung = _sess(
        "2026-08-29T22:00:00+10:00", "2026-08-30T05:00:00+10:00", source=_SAMSUNG,
        stages=[
            _stage(SleepStageType.DEEP,  "2026-08-29T22:00:00+10:00", "2026-08-29T23:00:00+10:00"),  # 60
            _stage(SleepStageType.REM,   "2026-08-29T23:00:00+10:00", "2026-08-30T01:00:00+10:00"),  # 120
            _stage(SleepStageType.LIGHT, "2026-08-30T01:00:00+10:00", "2026-08-30T05:00:00+10:00"),  # 240
        ],
    )
    garmin = _sess(
        "2026-08-29T23:30:00+10:00", "2026-08-30T02:00:00+10:00", source=_GARMIN,
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-29T23:30:00+10:00", "2026-08-30T02:00:00+10:00"),  # 150
        ],
    )

    handler_records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            handler_records.append(record.getMessage())

    logger = logging.getLogger("routers.health_connect")
    h = _Capture()
    logger.addHandler(h)
    prev_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        row = _aggregate_day(_DAY, _payload(samsung, garmin))
    finally:
        logger.removeHandler(h)
        logger.setLevel(prev_level)

    # Total = union across BOTH sources (Samsung already covers 22:00-05:00).
    assert row["sleep_duration_minutes"] == 420
    # Breakdown from the dominant source (Samsung) only — Garmin's 150-min LIGHT
    # is NOT unioned in (that would give 330).
    assert row["deep_sleep_minutes"] == 60
    assert row["rem_sleep_minutes"] == 120
    assert row["light_sleep_minutes"] == 240
    # Flag: a multi-source night is logged for F1 follow-up.
    assert any("multi-source night" in m for m in handler_records)
