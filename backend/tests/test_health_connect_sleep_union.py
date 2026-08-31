"""F3a — sleep aggregated as the UNION of asleep stage-intervals over the
wake-date's session set (DECISIONS_LOG #254), not the longest single session.

Canonical rule: total sleep time = union of LIGHT/DEEP/REM stage-intervals across
every session that wakes on this local (AEST) date, clustered into periods so a
same-wake-date daytime nap stays its own period and never merges into the night.
The union is computed from stage segments — never from session.duration(), which
is self-reported and overlaps its neighbours on a fragmented night.

Timestamps carry an explicit +10:00 (AEST) offset so wake-date is unambiguous.
"""
from datetime import date, datetime

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


# ---------- multi-source breakdown: precedence-resolved across sources, no dominant pick ----------

def test_multi_source_breakdown_resolves_by_precedence_not_dominant():
    """A main period stitched from two sources: the union TST spans BOTH sources
    (overlaps collapse), and the deep/rem/light breakdown is now resolved by stage
    precedence (DEEP > REM > LIGHT) across ALL segments regardless of source —
    #254's dominant-source pick is retired (#256). Garmin's LIGHT (23:30-02:00)
    overlaps Samsung's REM (23:00-01:00) and Samsung's own LIGHT (01:00-05:00):
    the 23:30-01:00 slice resolves to REM (higher precedence), the 01:00-02:00
    slice is already Samsung LIGHT — so Garmin's LIGHT inflates nothing, and the
    breakdown partitions the 420-min union exactly."""
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

    row = _aggregate_day(_DAY, _payload(samsung, garmin))

    # Total = union across BOTH sources (Samsung already covers 22:00-05:00).
    assert row["sleep_duration_minutes"] == 420
    # Precedence resolution: DEEP 60, REM 120, LIGHT 240. Garmin's 150-min LIGHT
    # is absorbed by higher-precedence REM (23:30-01:00) and existing LIGHT
    # (01:00-02:00) — it adds nothing (an independent union would have given 330).
    assert row["deep_sleep_minutes"] == 60
    assert row["rem_sleep_minutes"] == 120
    assert row["light_sleep_minutes"] == 240
    # Coherence: the breakdown partitions the union exactly.
    assert (
        row["deep_sleep_minutes"]
        + row["rem_sleep_minutes"]
        + row["light_sleep_minutes"]
        == row["sleep_duration_minutes"]
    )


# ---------- coherence: breakdown partitions the union; contested minute resolves by precedence ----------

def test_conflicting_overlap_breakdown_sums_to_tst_and_resolves_by_precedence():
    """Two sessions label the overlap 01:30-02:00 differently: LIGHT 01:00-02:00 in
    one, REM 01:30-02:30 in the other. The old independent per-stage unions counted
    that contested half-hour in BOTH light and rem, so deep+rem+light exceeded TST.
    Precedence resolution assigns each minute once: REM (precedence over LIGHT) wins
    01:30-02:00, so REM = 01:30-02:30 = 60, LIGHT = 01:00-01:30 = 30, union TST =
    01:00-02:30 = 90, and the parts sum to the whole."""
    a = _sess(
        "2026-08-30T01:00:00+10:00", "2026-08-30T02:00:00+10:00",
        stages=[_stage(SleepStageType.LIGHT, "2026-08-30T01:00:00+10:00", "2026-08-30T02:00:00+10:00")],
    )
    b = _sess(
        "2026-08-30T01:30:00+10:00", "2026-08-30T02:30:00+10:00",
        stages=[_stage(SleepStageType.REM, "2026-08-30T01:30:00+10:00", "2026-08-30T02:30:00+10:00")],
    )

    row = _aggregate_day(_DAY, _payload(a, b))

    assert row["sleep_duration_minutes"] == 90        # union 01:00-02:30
    assert row["rem_sleep_minutes"] == 60             # 01:30-02:30, wins the contest
    assert row["light_sleep_minutes"] == 30           # 01:00-01:30 only
    assert row["deep_sleep_minutes"] == 0
    # Coherence — the whole point of #256:
    assert (
        row["deep_sleep_minutes"]
        + row["rem_sleep_minutes"]
        + row["light_sleep_minutes"]
        == row["sleep_duration_minutes"]
    )


# ---------- total-invariant: the fix does not move TST ----------

def test_breakdown_fix_is_total_invariant():
    """The precedence resolution touches the breakdown only — TST stays exactly the
    asleep union it was under #254. Uses the conflicting-overlap night: whatever the
    breakdown, the stored total equals the independent asleep union of the segments."""
    from routers.health_connect import (
        SLEEP_STAGE_LIGHT, SLEEP_STAGE_REM, _asleep_union_minutes,
    )
    from datetime import datetime

    def dt(s):
        return datetime.fromisoformat(s)

    # Same night as the coherence test, expressed as segment tuples for the union.
    main = [
        (dt("2026-08-30T01:00:00+10:00"), dt("2026-08-30T02:00:00+10:00"), int(SLEEP_STAGE_LIGHT), _SAMSUNG),
        (dt("2026-08-30T01:30:00+10:00"), dt("2026-08-30T02:30:00+10:00"), int(SLEEP_STAGE_REM), _SAMSUNG),
    ]
    a = _sess(
        "2026-08-30T01:00:00+10:00", "2026-08-30T02:00:00+10:00",
        stages=[_stage(SleepStageType.LIGHT, "2026-08-30T01:00:00+10:00", "2026-08-30T02:00:00+10:00")],
    )
    b = _sess(
        "2026-08-30T01:30:00+10:00", "2026-08-30T02:30:00+10:00",
        stages=[_stage(SleepStageType.REM, "2026-08-30T01:30:00+10:00", "2026-08-30T02:30:00+10:00")],
    )

    row = _aggregate_day(_DAY, _payload(a, b))

    assert row["sleep_duration_minutes"] == _asleep_union_minutes(main)


# ---------- clean night (no conflict): each stage unchanged, still sums exactly ----------

def test_clean_night_no_conflict_stages_unchanged_and_coherent():
    """A single non-overlapping stage sequence (the #254 clean-control shape): no
    contested minutes, so every stage equals its own span and the breakdown already
    summed to TST. Precedence resolution must leave each stage exactly as an
    independent union would — deep 27, rem 60, light 247, TST 334."""
    sess = _sess(
        "2026-08-29T23:00:00+10:00", "2026-08-30T04:34:00+10:00",
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-29T23:00:00+10:00", "2026-08-30T01:00:00+10:00"),  # 120
            _stage(SleepStageType.DEEP,  "2026-08-30T01:00:00+10:00", "2026-08-30T01:27:00+10:00"),  # 27
            _stage(SleepStageType.REM,   "2026-08-30T01:27:00+10:00", "2026-08-30T02:27:00+10:00"),  # 60
            _stage(SleepStageType.LIGHT, "2026-08-30T02:27:00+10:00", "2026-08-30T04:34:00+10:00"),  # 127
        ],
    )

    row = _aggregate_day(_DAY, _payload(sess))

    assert row["deep_sleep_minutes"] == 27
    assert row["rem_sleep_minutes"] == 60
    assert row["light_sleep_minutes"] == 247          # 120 + 127
    assert row["sleep_duration_minutes"] == 334
    assert (
        row["deep_sleep_minutes"]
        + row["rem_sleep_minutes"]
        + row["light_sleep_minutes"]
        == row["sleep_duration_minutes"]
    )


# ---------- the failing night: single-source Samsung self-overlap inflated LIGHT ----------

def test_single_source_self_overlap_no_longer_inflates_breakdown():
    """Reproduces the 2026-08-30 fault shape: one source (Samsung) writes multiple
    overlapping records whose stage labels disagree at the seams. The old
    independent per-stage unions double-booked the contested minutes, pushing
    deep+rem+light ABOVE TST and inflating LIGHT most. Three overlapping records
    below; assert the new breakdown partitions the union exactly and that LIGHT is
    strictly below what an independent per-stage union would have reported."""
    from routers.health_connect import _union_minutes, SLEEP_STAGE_LIGHT as _L

    r1 = _sess(
        "2026-08-29T22:00:00+10:00", "2026-08-30T02:00:00+10:00",
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-29T22:00:00+10:00", "2026-08-29T22:45:00+10:00"),
            _stage(SleepStageType.DEEP,  "2026-08-29T22:45:00+10:00", "2026-08-29T23:03:00+10:00"),  # 18-min deep sliver
            _stage(SleepStageType.REM,   "2026-08-29T23:03:00+10:00", "2026-08-30T00:30:00+10:00"),
            _stage(SleepStageType.LIGHT, "2026-08-30T00:30:00+10:00", "2026-08-30T02:00:00+10:00"),
        ],
    )
    r2 = _sess(  # overlaps r1; labels the same wall-clock minutes differently
        "2026-08-29T23:30:00+10:00", "2026-08-30T03:15:00+10:00",
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-29T23:30:00+10:00", "2026-08-30T01:15:00+10:00"),  # overlaps r1's REM
            _stage(SleepStageType.REM,   "2026-08-30T01:15:00+10:00", "2026-08-30T02:00:00+10:00"),
            _stage(SleepStageType.LIGHT, "2026-08-30T02:00:00+10:00", "2026-08-30T03:15:00+10:00"),
        ],
    )
    r3 = _sess(
        "2026-08-30T01:00:00+10:00", "2026-08-30T03:45:00+10:00",
        stages=[
            _stage(SleepStageType.LIGHT, "2026-08-30T01:00:00+10:00", "2026-08-30T03:00:00+10:00"),  # overlaps r2's REM
            _stage(SleepStageType.REM,   "2026-08-30T03:00:00+10:00", "2026-08-30T03:45:00+10:00"),
        ],
    )

    row = _aggregate_day(_DAY, _payload(r1, r2, r3))
    deep, rem, light = (
        row["deep_sleep_minutes"], row["rem_sleep_minutes"], row["light_sleep_minutes"]
    )
    tst = row["sleep_duration_minutes"]

    # Coherence: parts sum to the whole (the 120%-of-the-night bug is gone).
    assert deep + rem + light == tst

    # LIGHT no longer double-books contested minutes: the resolved LIGHT is strictly
    # below the old independent per-stage LIGHT union over the same segments.
    all_segs = []
    for s in (r1, r2, r3):
        for st in s.stages:
            all_segs.append((st.startTime, st.endTime, int(st.stage)))
    old_light = _union_minutes(
        (datetime.fromisoformat(a), datetime.fromisoformat(b))
        for (a, b, stg) in all_segs if stg == int(_L)
    )
    assert light < old_light
