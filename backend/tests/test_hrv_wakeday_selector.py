"""Wake-day HRV selector — standalone read helper (`reads.recovery_reads.select_wakeday_hrv`).

Pure-function tests against the in-memory SQLite `db_session` fixture (no network, no
prod). The helper answers "what HRV do I show for (user, wake_day), honestly?" with an
explicit current-day gate, source labelling, a same-wake-day-only delta, and hard guards
on the two silent-wrong modes (tz-misaligned pairs, >2 sources).

The safety property under test, above all: with `require_current_day=True`, the helper
NEVER returns a reading whose `captured_at != wake_day` — no upper-bound, no newest-ever,
no fallback to yesterday. That is the seam this helper exists to close (the check-in's
current read uses `hrv_deviation` with `for_date` as an upper bound and leaks a stale
prior-day value).
"""
from __future__ import annotations

from datetime import date, timedelta

import models
from reads.recovery_reads import MIN_BASELINE_N, HrvSelection, select_wakeday_hrv

_TODAY = date(2026, 9, 16)


def _user(db, uid=11):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _row(db, user_id, source, day, rmssd):
    db.add(models.HrvReading(user_id=user_id, captured_at=day, source=source, rmssd_ms=rmssd))
    db.commit()


def _baseline(db, user_id, source, *, up_to, count, rmssd):
    """`count` consecutive nightly rows for `source`, newest at `up_to - 1`, oldest
    earlier — a rolling baseline BEFORE `up_to` (which the caller seeds separately)."""
    for i in range(1, count + 1):
        db.add(models.HrvReading(
            user_id=user_id, captured_at=up_to - timedelta(days=i),
            source=source, rmssd_ms=rmssd,
        ))
    db.commit()


# ── single source → "value" ──────────────────────────────────────────────────────
def test_single_source_is_value_labelled_no_delta(db_session):
    user = _user(db_session)
    _row(db_session, user.id, "garmin", _TODAY, 62.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert isinstance(sel, HrvSelection)
    assert sel.state == "value"
    assert sel.primary == {"source": "garmin", "rmssd_ms": 62.0, "captured_at": _TODAY}
    assert sel.secondary is None
    assert sel.delta_ms is None
    assert sel.sources_seen == ["garmin"]
    assert sel.possible_tz_split is False


# ── two sources SAME wake_day → "pair" (delta valid, primary = garmin) ────────────
def test_same_day_pair_surfaces_both_delta_primary_garmin(db_session):
    user = _user(db_session)
    _row(db_session, user.id, "samsung", _TODAY, 55.0)
    _row(db_session, user.id, "garmin", _TODAY, 62.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "pair"
    assert sel.primary == {"source": "garmin", "rmssd_ms": 62.0, "captured_at": _TODAY}
    assert sel.secondary == {"source": "samsung", "rmssd_ms": 55.0, "captured_at": _TODAY}
    assert sel.delta_ms == 7          # primary − secondary, garmin − samsung
    assert sel.sources_seen == ["garmin", "samsung"]
    assert sel.possible_tz_split is False


# ── no current-day row but earlier one exists → "stale_withheld" (never yesterday) ─
def test_no_today_row_with_earlier_is_stale_withheld_not_yesterday(db_session):
    user = _user(db_session)
    # The 14 Sept Samsung value that must NOT leak as "today". Ring dead since; today empty.
    _row(db_session, user.id, "samsung", _TODAY - timedelta(days=2), 113.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "stale_withheld"
    assert sel.primary is None          # the stale 113 is WITHHELD, not returned
    assert sel.secondary is None
    assert sel.delta_ms is None
    assert sel.sources_seen == []


# ── no reading ever → "absent" ────────────────────────────────────────────────────
def test_no_reading_ever_is_absent(db_session):
    user = _user(db_session)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "absent"
    assert sel.primary is None
    assert sel.sources_seen == []
    assert sel.possible_tz_split is False


# ── require_current_day=False (card) → newest reading WITH its date ───────────────
def test_card_mode_returns_newest_with_date(db_session):
    user = _user(db_session)
    _row(db_session, user.id, "samsung", _TODAY - timedelta(days=3), 50.0)
    _row(db_session, user.id, "garmin", _TODAY - timedelta(days=1), 60.0)   # newest

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=False, today=_TODAY)

    assert sel.state == "value"
    assert sel.primary == {
        "source": "garmin", "rmssd_ms": 60.0, "captured_at": _TODAY - timedelta(days=1),
    }
    # Card headlines the newest day even though it is not `_TODAY` — with the date carried
    # so the caller can label it. This is the ONLY mode that returns a non-current value.


def test_current_day_mode_never_returns_the_newest_when_it_is_not_today(db_session):
    """Contrast to the card: the same seed under require_current_day withholds the
    yesterday value instead of headlining it."""
    user = _user(db_session)
    _row(db_session, user.id, "garmin", _TODAY - timedelta(days=1), 60.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "stale_withheld"
    assert sel.primary is None


# ── two sources on ADJACENT days (not same) → possible_tz_split, not silent single ─
def test_adjacent_day_sources_flag_tz_split_without_merging(db_session):
    user = _user(db_session)
    _row(db_session, user.id, "garmin", _TODAY, 62.0)
    _row(db_session, user.id, "samsung", _TODAY - timedelta(days=1), 58.0)  # adjacent, not same

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "value"                 # still single-source — NOT merged into a pair
    assert sel.primary == {"source": "garmin", "rmssd_ms": 62.0, "captured_at": _TODAY}
    assert sel.secondary is None
    assert sel.delta_ms is None                 # no cross-night delta
    assert sel.possible_tz_split is True        # but the possible split IS flagged
    assert sel.sources_seen == ["garmin"]


# ── >2 distinct sources same wake_day → "config_error", never a silent 2-of-3 ─────
def test_three_sources_same_day_is_config_error(db_session):
    user = _user(db_session)
    _row(db_session, user.id, "garmin", _TODAY, 62.0)
    _row(db_session, user.id, "samsung", _TODAY, 55.0)
    _row(db_session, user.id, "whoop", _TODAY, 70.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "config_error"
    assert sel.primary is None                  # never picks 2-of-3
    assert sel.secondary is None
    assert sel.delta_ms is None
    assert sel.sources_seen == ["garmin", "samsung", "whoop"]


# ── baseline_state passes through (baselined vs building) WITHOUT gating the value ─
def test_baseline_state_baselined_does_not_gate_value(db_session):
    user = _user(db_session)
    _baseline(db_session, user.id, "garmin", up_to=_TODAY, count=MIN_BASELINE_N + 3, rmssd=60.0)
    _row(db_session, user.id, "garmin", _TODAY, 62.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "value"
    assert sel.primary["rmssd_ms"] == 62.0      # value present regardless
    assert sel.baseline_state == "baselined"    # mature source surfaced honestly


def test_baseline_state_building_does_not_gate_value(db_session):
    user = _user(db_session)
    _baseline(db_session, user.id, "garmin", up_to=_TODAY, count=3, rmssd=60.0)   # thin
    _row(db_session, user.id, "garmin", _TODAY, 62.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "value"
    assert sel.primary["rmssd_ms"] == 62.0      # immature baseline does NOT suppress the value
    assert sel.baseline_state == "building"


def test_pair_delta_shows_regardless_of_baseline_maturity(db_session):
    """Ratified: the delta shows on a same-wake-day pair even when neither source is
    mature. Baseline maturity is advisory, never a gate."""
    user = _user(db_session)
    _row(db_session, user.id, "garmin", _TODAY, 62.0)      # no baseline history at all
    _row(db_session, user.id, "samsung", _TODAY, 55.0)

    sel = select_wakeday_hrv(db_session, user.id, _TODAY, require_current_day=True, today=_TODAY)

    assert sel.state == "pair"
    assert sel.delta_ms == 7                     # delta present despite thin baselines
    assert sel.baseline_state == "building"      # primary (garmin) not mature — surfaced, not gating
