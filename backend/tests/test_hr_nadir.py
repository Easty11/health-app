"""Sleep-nadir resting HR (hr_nadir.py) and the all-day median's move to the AEST calendar day.

DECISIONS_LOG.md:480 calls a derived nadir primary for resting HR; the code stored the median of ALL
the day's HR samples (7 Oct 2026: 118, from a BikeErg session). The nadir is the lowest sustained
window inside the main sleep period, read from `hr_samples` on a 1-minute grid.

Gates: G1 time-weighted (a dense burst cannot weight it) · G2 the method's boundaries (carry-forward,
window presence, coverage floor) · G3 one writer, lexical tie-break, plausibility · G4 the writer sets
NULL as well as a value, idempotently, and reflows late HR · G5 the sync wires it in a savepoint and
the median buckets by the AEST day · G6 the prompt / API / MCP show it and say why when withheld.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import hr_nadir
import models
from context_builder import _section_health_connect
from mcp_server import _format_recovery_metrics
from routers import health_connect as hc
from routers.health_connect import (
    HeartRateRecord, SleepSession, SleepStage, SleepStageType, SyncPayload, _aggregate_day, _local_date, sync,
)
from routers.recovery import get_summary

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"

# A fixed 8 h night, 22:00 -> 06:00 AEST (12:00Z -> 20:00Z), for the pure method tests.
START = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=8)


def _min(i, sec=0):
    return START + timedelta(minutes=i, seconds=sec)


def _every_minute(lo, hi, bpm):
    return [(_min(i), bpm) for i in range(lo, hi)]


# ── G1 / G2: the method ───────────────────────────────────────────────────────────────────

def test_a_dense_burst_cannot_weight_the_nadir():
    """30 min of 1 Hz at 120 bpm beside 1/min at 52: a count-weighted statistic would drift towards
    the burst. The grid gives each minute one vote, so the nadir is the resting 52."""
    samples = _every_minute(0, 480, 52)
    samples += [(_min(100, s), 120) for s in range(60)] + [(_min(100 + m, s), 120) for m in range(1, 30) for s in range(60)]
    r = hr_nadir.nadir_from_samples({GARMIN: samples}, START, END)
    assert r.reason is None and r.bpm == pytest.approx(52.0, abs=0.1)


def test_the_nadir_is_the_lowest_sustained_window_not_a_single_dip():
    samples = _every_minute(0, 480, 60)
    samples = [(t, 47 if 200 <= i < 240 else b) for i, (t, b) in enumerate(samples)]    # a 40-minute low
    samples[300] = (samples[300][0], 30)                                                  # one-minute dip
    r = hr_nadir.nadir_from_samples({GARMIN: samples}, START, END)
    assert r.bpm == pytest.approx(47.0, abs=0.1)                                           # not dragged by the dip
    assert _min(200) <= r.window_start <= _min(210)                                        # inside the low


def test_a_gap_is_carried_for_five_minutes_then_missing():
    # One sample every 6 minutes: observed + 5 carried = every minute present -> a nadir.
    r = hr_nadir.nadir_from_samples({GARMIN: [(_min(i), 55) for i in range(0, 480, 6)]}, START, END)
    assert r.reason is None and r.coverage == 1.0 and r.bpm == pytest.approx(55.0, abs=0.1)
    # One every 8: 6 of 8 present, and a best-aligned 30-minute window holds exactly 24 (6+6+6+6) --
    # the 80% line is inclusive, so that still counts.
    r = hr_nadir.nadir_from_samples({GARMIN: [(_min(i), 55) for i in range(0, 480, 8)]}, START, END)
    assert r.reason is None and r.window_start == START
    # One every 9: 6 of 9 present (67%) -- enough coverage for the floor, but no 30-minute window can
    # hold 24 present minutes (the best alignment holds 21) -- so no window qualifies.
    r = hr_nadir.nadir_from_samples({GARMIN: [(_min(i), 55) for i in range(0, 480, 9)]}, START, END)
    assert r.reason == "no_valid_window" and r.coverage == pytest.approx(0.67, abs=0.01)


def test_a_short_hole_does_not_void_the_night():
    base = _every_minute(0, 480, 60)
    short = [(t, b) for i, (t, b) in enumerate(base) if not 100 <= i < 107]               # 7 min out: 5 carried, 2 missing
    r = hr_nadir.nadir_from_samples({GARMIN: short}, START, END)
    assert r.reason is None and r.bpm == pytest.approx(60.0, abs=0.1)


def test_the_coverage_floor_is_180_minutes_and_half_the_period():
    def at(observed_minutes, period_min):
        end = START + timedelta(minutes=period_min)
        # N observed minutes + 5 carried = N + 5 covered
        return hr_nadir.nadir_from_samples({GARMIN: _every_minute(0, observed_minutes, 55)}, START, end)

    assert at(175, 360).reason is None                    # 180 min = 3 h and exactly 50% of 360: passes
    assert at(174, 360).reason == "insufficient_coverage"  # 179 min
    assert at(195, 480).reason == "insufficient_coverage"  # 200 min >= 3 h but 41.7% of 8 h
    assert at(165, 300).reason == "insufficient_coverage"  # 170 min = 56.7% of 5 h but under 3 h


def test_no_sleep_period_and_no_samples_are_distinct_reasons():
    assert hr_nadir.nadir_from_samples({GARMIN: []}, START, START).reason == "no_sleep_period"
    assert hr_nadir.nadir_from_samples({}, START, END).reason == "no_samples"


# ── G3: one writer, tie-break, plausibility ───────────────────────────────────────────────

def test_the_writer_covering_more_of_the_night_is_used_alone():
    ring = _every_minute(0, 100, 40)                              # sparse and LOWER than the watch
    watch = _every_minute(0, 480, 58)
    r = hr_nadir.nadir_from_samples({SHEALTH: ring, GARMIN: watch}, START, END)
    assert r.package == GARMIN and r.bpm == pytest.approx(58.0, abs=0.1)     # the ring's 40 is never blended in


def test_an_exact_coverage_tie_goes_to_the_lexically_first_package():
    s = _every_minute(0, 480, 55)
    r = hr_nadir.nadir_from_samples({"com.b": list(s), "com.a": list(s)}, START, END)
    assert r.package == "com.a"


def test_implausible_samples_are_dropped():
    r = hr_nadir.nadir_from_samples({GARMIN: _every_minute(0, 480, 20) + _every_minute(0, 480, 250)}, START, END)
    assert r.reason == "no_samples"


# ── G4: the writer ────────────────────────────────────────────────────────────────────────

def _user(db, email="nadir@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _row(db, uid, day, *, start=START, end=END, onset=None):
    r = models.HealthConnectSync(user_id=uid, date=day, sleep_start=start, sleep_end=end, sleep_onset=onset)
    db.add(r)
    db.commit()
    return r


def _store(db, uid, samples, pkg=GARMIN):
    db.add_all([models.HrSample(user_id=uid, sample_time=t, bpm=b, source="health_connect", source_package=pkg)
                for t, b in samples])
    db.commit()


def test_the_writer_stores_all_six_columns(db_session):
    u = _user(db_session)
    row = _row(db_session, u.id, date(2026, 10, 7))
    _store(db_session, u.id, _every_minute(0, 480, 53))
    result, changed = hr_nadir.compute_for_row(db_session, u.id, row)
    assert changed and result.reason is None
    assert (row.hr_nadir_bpm, row.hr_nadir_source_package, row.hr_nadir_reason, row.hr_nadir_formula) == (
        pytest.approx(53.0, abs=0.1), GARMIN, None, hr_nadir.FORMULA)
    assert row.hr_nadir_coverage == 1.0 and row.hr_nadir_window_start is not None


def test_the_writer_is_idempotent(db_session):
    u = _user(db_session)
    row = _row(db_session, u.id, date(2026, 10, 7))
    _store(db_session, u.id, _every_minute(0, 480, 53))
    assert hr_nadir.compute_for_row(db_session, u.id, row)[1] is True
    assert hr_nadir.compute_for_row(db_session, u.id, row)[1] is False


def test_a_night_that_stops_qualifying_is_set_to_null_not_left_stale(db_session):
    """The sync upsert never writes a NULL; the nadir writer must (a stale 53 would outlive the
    samples that justified it)."""
    u = _user(db_session)
    row = _row(db_session, u.id, date(2026, 10, 7))
    _store(db_session, u.id, _every_minute(0, 480, 53))
    hr_nadir.compute_for_row(db_session, u.id, row)
    assert row.hr_nadir_bpm is not None
    db_session.query(models.HrSample).delete()
    db_session.commit()
    result, changed = hr_nadir.compute_for_row(db_session, u.id, row)
    assert changed and row.hr_nadir_bpm is None and row.hr_nadir_reason == "no_samples"
    assert row.hr_nadir_window_start is None and row.hr_nadir_formula == hr_nadir.FORMULA


def test_late_hr_reflows_the_nadir(db_session):
    u = _user(db_session)
    row = _row(db_session, u.id, date(2026, 10, 7))
    _store(db_session, u.id, _every_minute(0, 480, 60))
    hr_nadir.compute_for_row(db_session, u.id, row)
    assert row.hr_nadir_bpm == pytest.approx(60.0, abs=0.1)
    _store(db_session, u.id, [(_min(i, 30), 49) for i in range(250, 290)], pkg=GARMIN)    # a late deep sync
    hr_nadir.compute_for_row(db_session, u.id, row)
    assert row.hr_nadir_bpm < 60.0


def test_a_row_without_clocks_is_no_sleep_period(db_session):
    u = _user(db_session)
    row = models.HealthConnectSync(user_id=u.id, date=date(2026, 10, 7))
    db_session.add(row)
    db_session.commit()
    summary = hr_nadir.compute_for_dates(db_session, u.id, {date(2026, 10, 7)})
    assert row.hr_nadir_reason == "no_sleep_period"
    assert summary["null"] == 1 and set(summary["reasons"]) == set(hr_nadir.REASONS)


def test_onset_is_preferred_over_the_bed_edge(db_session):
    u = _user(db_session)
    row = _row(db_session, u.id, date(2026, 10, 7), onset=_min(60))
    assert hr_nadir.sleep_period(row) == (_min(60), END)


def test_a_recompute_never_moves_synced_at(db_session):
    """`synced_at` is "when the phone last synced" (week_plan's freshness read, /health-connect/status).
    The column carries `onupdate=now()`, so a naive write of the nadir columns by the nightly sweep
    would stamp every touched row as just-synced -- and fake a sync that never happened."""
    u = _user(db_session)
    row = _row(db_session, u.id, date(2026, 10, 7))
    row.synced_at = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    db_session.commit()
    _store(db_session, u.id, _every_minute(0, 480, 53))
    out = hr_nadir.compute_user(db_session, u.id, today=date(2026, 10, 8))
    db_session.refresh(row)
    assert out["changed"] == 1 and row.hr_nadir_bpm is not None
    assert row.synced_at.replace(tzinfo=None) == datetime(2026, 6, 1, 10, 0)


def test_the_sweep_recomputes_only_the_trailing_window(db_session):
    u = _user(db_session)
    recent = _row(db_session, u.id, date(2026, 10, 7))
    old_start = START - timedelta(days=30)
    old = _row(db_session, u.id, date(2026, 9, 7), start=old_start, end=old_start + timedelta(hours=8))
    out = hr_nadir.compute_user(db_session, u.id, today=date(2026, 10, 8))
    assert out["rows"] == 1 and recent.hr_nadir_formula == hr_nadir.FORMULA and old.hr_nadir_formula is None


# ── G5: the sync ──────────────────────────────────────────────────────────────────────────

def _aest_today():
    return hc._now_aest_date()


def _night_payload(day, hr):
    """A Garmin night 22:30 -> 06:00 AEST ending on `day`, with stages, plus HR records."""
    prev = (day - timedelta(days=1)).isoformat()
    cur = day.isoformat()
    stages = [
        SleepStage(stage=SleepStageType.LIGHT, startTime=f"{prev}T22:30:00+10:00", endTime=f"{cur}T01:00:00+10:00"),
        SleepStage(stage=SleepStageType.DEEP, startTime=f"{cur}T01:00:00+10:00", endTime=f"{cur}T03:00:00+10:00"),
        SleepStage(stage=SleepStageType.REM, startTime=f"{cur}T03:00:00+10:00", endTime=f"{cur}T06:00:00+10:00"),
    ]
    sess = SleepSession(startTime=f"{prev}T22:30:00+10:00", endTime=f"{cur}T06:00:00+10:00",
                        sourcePackage=GARMIN, stages=stages)
    return SyncPayload(sleep=[sess], hrv=[], heartRate=hr, steps=[], workouts=[])


def _night_hr(day, bpm=54):
    """1/min across the whole night, as UTC `Z` stamps (what the companion posts)."""
    start = datetime.fromisoformat(f"{(day - timedelta(days=1)).isoformat()}T22:30:00+10:00").astimezone(timezone.utc)
    return [HeartRateRecord(time=(start + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ"), bpm=bpm,
                            sourcePackage=GARMIN) for i in range(450)]


def test_the_sync_computes_the_nadir_on_the_wake_date_row(db_session):
    u = _user(db_session)
    day = _aest_today()
    out = sync(payload=_night_payload(day, _night_hr(day)), current_user=u, db=db_session)
    row = db_session.query(models.HealthConnectSync).filter_by(user_id=u.id, date=day).one()
    assert row.hr_nadir_bpm == pytest.approx(54.0, abs=0.1) and row.hr_nadir_reason is None
    assert out["hr_nadir"]["computed"] >= 1 and "error" not in out["hr_nadir"]


def test_a_nadir_failure_never_fails_the_sync(db_session, monkeypatch):
    u = _user(db_session)
    day = _aest_today()

    def boom(*a, **k):
        raise RuntimeError("nadir broke")

    monkeypatch.setattr(hr_nadir, "compute_for_dates", boom)
    out = sync(payload=_night_payload(day, _night_hr(day)), current_user=u, db=db_session)
    assert out["hr_nadir"] == {"error": "RuntimeError: nadir broke"}
    row = db_session.query(models.HealthConnectSync).filter_by(user_id=u.id, date=day).one()
    assert row.sleep_duration_minutes and row.resting_heart_rate           # the day's aggregates still committed
    assert row.hr_nadir_bpm is None


def test_the_all_day_median_buckets_by_the_aest_calendar_day():
    """13:59Z on the 7th is 23:59 AEST on the 7th; 14:00Z is 00:00 AEST on the 8th. The UTC slice put
    both on the 7th."""
    d7, d8 = date(2026, 10, 7), date(2026, 10, 8)
    p = SyncPayload(sleep=[], hrv=[], steps=[], workouts=[], heartRate=[
        HeartRateRecord(time="2026-10-07T13:59:00Z", bpm=70, sourcePackage=GARMIN),
        HeartRateRecord(time="2026-10-07T14:00:00Z", bpm=90, sourcePackage=GARMIN),
    ])
    assert _aggregate_day(d7, p)["resting_heart_rate"] == 70.0
    assert _aggregate_day(d8, p)["resting_heart_rate"] == 90.0


def test_the_morning_hours_before_ten_belong_to_their_own_aest_day():
    # 20:00Z on the 6th is 06:00 AEST on the 7th: the UTC slice put that sample on the 6th, away
    # from the rest of its morning. Fractions, `Z` and offsets all normalise the same way.
    assert _local_date("2026-10-06T20:00:00Z") == date(2026, 10, 7)
    assert _local_date("2026-10-07T00:30:00.123456789Z") == date(2026, 10, 7)
    assert _local_date("2026-10-07T00:30:00+10:00") == date(2026, 10, 7)


def test_an_unparseable_stamp_keeps_the_legacy_date_slice_instead_of_raising():
    assert _local_date("2026-10-07Tnot-a-time") == date(2026, 10, 7)


# ── G6: presentation ──────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 10, 7, 8, 0, 0)


def test_the_prompt_shows_the_nadir_and_the_median_as_two_labelled_lines():
    out = _section_health_connect(
        [{"date": _NOW.date(), "hr_nadir_bpm": 51.4, "resting_heart_rate": 118.0}], _NOW)
    assert "Resting HR (sleep nadir): 51 bpm" in out
    assert "All-day median HR: 118 bpm" in out
    assert "Resting HR: " not in out                 # the unqualified label is gone for good


def test_a_withheld_nadir_says_why_and_never_shows_a_number():
    out = _section_health_connect(
        [{"date": _NOW.date(), "hr_nadir_bpm": None, "hr_nadir_reason": "insufficient_coverage",
          "resting_heart_rate": 118.0}], _NOW)
    assert "Resting HR (sleep nadir): not available (insufficient overnight HR coverage)" in out
    assert "All-day median HR: 118 bpm" in out       # the median is never promoted into the resting slot


def test_a_row_the_nadir_has_not_reached_prints_no_nadir_line():
    out = _section_health_connect([{"date": _NOW.date(), "resting_heart_rate": 118.0}], _NOW)
    assert "sleep nadir" not in out


def test_the_mcp_fallback_labels_the_nadir_apart_from_rhr():
    row = {"captured_at": "2026-10-07", "source": "health_connect_syncs", "hrv_ms": 50.0,
           "sleep_hr_bpm": None, "all_day_median_hr": 118.0, "hr_nadir": 51.6, "respiratory_rate": None,
           "sleep_efficiency_pct": None, "actual_sleep_time_minutes": None, "deep_minutes": None,
           "rem_minutes": None, "light_minutes": None, "awake_minutes": None, "spo2_average_pct": None}
    line = next(ln for ln in _format_recovery_metrics([row], 7).splitlines() if "[health_connect_syncs]" in ln)
    assert "RHR=— All-day median HR=118 bpm Sleep-nadir HR=52 bpm" in line


def test_the_api_exposes_the_nadir_additively(db_session):
    u = _user(db_session)
    day = hc._now_aest_date()
    db_session.add(models.HealthConnectSync(
        user_id=u.id, date=day, resting_heart_rate=118.0, hr_nadir_bpm=51.4, hr_nadir_reason=None,
        hr_nadir_formula=hr_nadir.FORMULA))
    db_session.commit()
    latest = hc.get_latest(current_user=u, db=db_session)
    assert latest[0].hr_nadir_bpm == 51.4 and latest[0].resting_heart_rate == 118.0
    summary = get_summary(current_user=u, db=db_session)
    assert summary["health_connect"]["hr_nadir_bpm"] == 51.4
    assert summary["health_connect"]["hr_nadir_reason"] is None
    assert summary["health_connect"]["resting_heart_rate"] == 118.0     # key kept for API stability


# ── the nightly chain step ────────────────────────────────────────────────────────────────

def test_the_nightly_step_is_soft_fail(db_session, monkeypatch):
    from scripts import refresh_load

    assert "hr_nadir" in refresh_load.SOFT_STEPS

    def boom(db, uid, **k):
        raise RuntimeError("sweep broke")

    monkeypatch.setattr(refresh_load.hr_nadir, "compute_user", boom)
    assert refresh_load._hr_nadir(db_session, 1) == {"error": "RuntimeError: sweep broke"}
