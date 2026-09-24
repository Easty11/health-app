"""HRV staleness (#NEXT) — no surface presents a prior-day HRV as today's.

Root: `hrv_deviation` had no age bound, so a dead source's last reading + frozen mature
baseline was reported as current (model-layer gates G1/G2 live in test_hrv_deviation; the
check-in prefill G2/G3 halves in test_hrv_consumption; G4 there too). This file pins the
COACH CONTEXT (G2/G3 context halves, G5), the historical readers' canonical-first /
denorm-fallback read, and `wakeday_hrv_by_date`'s selector-consistent headline.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

import context_builder
import current_state as current_state_mod
import models
from reads.recovery_reads import wakeday_hrv_by_date
from routers.series import get_readiness_series

_AEST = pytz.timezone("Australia/Brisbane")
_TODAY = date(2026, 9, 24)


def _user(db, email="stale@example.com"):
    u = models.User(email=email, hashed_password="x", full_name="Stale User")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _hrv(db, user_id, day, source, ms):
    db.add(models.HrvReading(user_id=user_id, captured_at=day, source=source, rmssd_ms=ms))


def _am_record(db, user_id, day, passive_hrv_ms=None):
    rec = models.DailyRecord(
        user_id=user_id, date=day, am_timestamp=datetime(2026, 9, 23, 21, 0),
        morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3,
        passive_hrv_ms=passive_hrv_ms,
    )
    db.add(rec)
    db.commit()
    return rec


def _prompt(db, user, record, monkeypatch):
    monkeypatch.setattr(context_builder, "_now_aest",
                        lambda: _AEST.localize(datetime(2026, 9, 24, 7, 0)))
    state = current_state_mod.current_state(user.id, db, today=_TODAY)
    return state, context_builder.build_system_prompt(
        user=user, connected_integrations=[], state=state, daily_record=record,
        samsung_hrv=[],   # chat's 7-day samsung_hrv_readings window: empty for a dead ring
    )


# ── G2 (coach context half) ─────────────────────────────────────────────────────
def test_g2_only_dead_source_coach_context_has_no_hrv_number(db_session, monkeypatch):
    """Only a dead source (last reading D-20, mature baseline) and a daily record whose
    frozen passive_hrv_ms is a forward-carried 113 → the context says "no current-day HRV"
    and carries no HRV number at all (neither the denorm nor a baseline)."""
    u = _user(db_session)
    for i in range(20, 48):
        _hrv(db_session, u.id, _TODAY - timedelta(days=i), "samsung", 113.0)
    db_session.commit()
    rec = _am_record(db_session, u.id, _TODAY, passive_hrv_ms=113.0)

    state, out = _prompt(db_session, u, rec, monkeypatch)

    assert state.hrv_today.state == "stale_withheld"
    assert state.hrv_baseline is None                  # dead source contributes nothing
    assert "no current-day HRV" in out
    assert "113" not in out
    assert not re.search(r"HRV[^\n]*\d+\s*ms", out)


# ── G3 (coach context half) ─────────────────────────────────────────────────────
def test_g3_pair_same_wake_day_garmin_primary_both_in_context(db_session, monkeypatch):
    u = _user(db_session)
    _hrv(db_session, u.id, _TODAY, "samsung", 70.0)
    _hrv(db_session, u.id, _TODAY, "garmin", 62.0)
    db_session.commit()
    rec = _am_record(db_session, u.id, _TODAY)

    state, out = _prompt(db_session, u, rec, monkeypatch)

    assert state.hrv_today.state == "pair"
    line = next(l for l in out.splitlines() if l.startswith("HRV (RMSSD) for"))
    assert line.index("62 ms — garmin (primary)") < line.index("70 ms — samsung")
    assert "2026-09-24" in line and "Δ -8 ms" in line


def test_single_current_day_value_carries_source_and_date(db_session, monkeypatch):
    u = _user(db_session)
    _hrv(db_session, u.id, _TODAY, "garmin", 58.4)
    db_session.commit()
    _, out = _prompt(db_session, u, _am_record(db_session, u.id, _TODAY), monkeypatch)
    assert "HRV (RMSSD) for 2026-09-24: 58 ms — garmin" in out


# ── G5 ──────────────────────────────────────────────────────────────────────────
def test_g5_no_ring_hrv_prompt_string_in_context_builder():
    src = (Path(context_builder.__file__)).read_text(encoding="utf-8")
    assert "Ring HRV" not in src
    assert "HRV" in context_builder.HRV_GUIDANCE_LINE and "Ring" not in context_builder.HRV_GUIDANCE_LINE


# ── historical readers: canonical row first, denorm only as fallback ─────────────
def test_series_canonical_row_overrides_a_forward_carried_denorm(db_session):
    """A day with an hrv_readings row reads that row even if its frozen passive_hrv_ms is a
    forward carry; a day with NO canonical row falls back to the retained denorm."""
    u = _user(db_session)
    today = datetime.now(_AEST).date()
    d1, d2 = today - timedelta(days=2), today - timedelta(days=1)
    _hrv(db_session, u.id, d1, "samsung", 64.0)      # canonical row for d1
    db_session.add_all([
        models.DailyRecord(user_id=u.id, date=d1, morning_readiness=3, passive_hrv_ms=113.0),
        models.DailyRecord(user_id=u.id, date=d2, morning_readiness=3, passive_hrv_ms=55.0),
    ])
    db_session.commit()

    out = get_readiness_series(days=90, current_user=u, db=db_session)
    assert [(p.date, p.passive_hrv_ms) for p in out.points] == [
        (d1.isoformat(), 64.0), (d2.isoformat(), 55.0)]


def test_wakeday_hrv_by_date_headline_matches_selector_rules(db_session):
    u = _user(db_session)
    d = _TODAY
    _hrv(db_session, u.id, d, "samsung", 70.0)
    _hrv(db_session, u.id, d, "garmin", 62.0)                    # pair → garmin
    _hrv(db_session, u.id, d - timedelta(days=1), "samsung", 66.0)
    for src in ("garmin", "samsung", "polar"):                   # >2 → config_error
        _hrv(db_session, u.id, d - timedelta(days=2), src, 50.0)
    db_session.commit()

    got = wakeday_hrv_by_date(db_session, u.id, since=d - timedelta(days=5))
    assert got[d] == {"source": "garmin", "rmssd_ms": 62.0}
    assert got[d - timedelta(days=1)] == {"source": "samsung", "rmssd_ms": 66.0}
    assert got[d - timedelta(days=2)] == {"source": None, "rmssd_ms": None}
    assert d - timedelta(days=3) not in got                      # never neighbour-filled
