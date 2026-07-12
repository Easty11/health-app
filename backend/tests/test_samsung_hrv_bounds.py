"""Ingest bounds guard for samsung_hrv_readings (HRV & Sleep Data Integrity, Task 3).

A value outside physiological/definitional range is corrupt at source — the
canonical trigger was 2026-06-28 sleep efficiency = 119%, a hard impossibility.
The guard nulls the offending field and keeps the rest of the night's data;
it never drops the whole reading or fabricates a clamped value.
"""
from datetime import date

from routers.samsung_hrv import HRVReadingIn


def test_efficiency_over_100_is_nulled():
    r = HRVReadingIn(captured_at=date(2026, 6, 28), sleep_efficiency_pct=119)
    assert r.sleep_efficiency_pct is None


def test_valid_efficiency_survives():
    r = HRVReadingIn(captured_at=date(2026, 6, 28), sleep_efficiency_pct=92)
    assert r.sleep_efficiency_pct == 92


def test_boundary_100_is_valid():
    r = HRVReadingIn(captured_at=date(2026, 6, 28), sleep_efficiency_pct=100)
    assert r.sleep_efficiency_pct == 100


def test_out_of_range_field_does_not_drop_valid_siblings():
    # Efficiency is impossible; HRV and RHR on the same night are fine and kept.
    r = HRVReadingIn(
        captured_at=date(2026, 6, 28),
        sleep_efficiency_pct=119,
        hrv_ms=57.0,
        sleep_hr_bpm=56,
    )
    assert r.sleep_efficiency_pct is None
    assert r.hrv_ms == 57.0
    assert r.sleep_hr_bpm == 56


def test_all_percentage_fields_bounded():
    r = HRVReadingIn(
        captured_at=date(2026, 6, 28),
        awake_pct=120,
        rem_pct=101,
        light_pct=200,
        deep_pct=150,
        spo2_average_pct=105.0,
    )
    assert r.awake_pct is None
    assert r.rem_pct is None
    assert r.light_pct is None
    assert r.deep_pct is None
    assert r.spo2_average_pct is None


def test_negative_minutes_nulled():
    r = HRVReadingIn(captured_at=date(2026, 6, 28), deep_minutes=-5)
    assert r.deep_minutes is None


def test_absurd_hrv_and_rr_nulled():
    r = HRVReadingIn(captured_at=date(2026, 6, 28), hrv_ms=9999.0, respiratory_rate=0.0)
    assert r.hrv_ms is None
    assert r.respiratory_rate is None
