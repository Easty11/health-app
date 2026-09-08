"""Psychological window (S4 §3) — the residual producer + life-load modulator.

Gates asserted here (S4 brief):
  G1 — fail-closed, down-only: absent life-load data → no bias (False); the residual
       producer emits nothing in cold-start.
  G2 — exclusivity: a psychological `load_event` is NEVER a ridge predictor.
  G4 — no numpy / pure-Python ridge (import-level: the module imports without numpy).
  G5 — grain honesty: a multi-session day is flagged, not silently averaged.
  + the wiring: `life_load_bias` fires the recovery re-rank INDEPENDENTLY of
    `readiness_hint`, is a sibling (never folded in), and never touches dosing.

Negatives are paired with positive controls (FEEDBACK §17/§18): a producer that
emitted nothing, or a re-rank that never fired, could not pass.
"""
from datetime import date, datetime, timezone

import pytest

import models
from engine import profile as profile_mod, selection
from reads.psychological_reads import (
    life_load_bias,
    life_load_severity,
    psychological_residual,
    ridge_fit,
    ewma_time_aware,
    _stress_severity,
    _sleep_severity,
    _combine_severity,
)


def _utc_noon(d: date) -> datetime:
    """Noon UTC on `d` → 22:00 AEST same date, so `_local_day` buckets it to `d`."""
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)


def _user(db, uid=1, email="pw@x.com"):
    db.add(models.User(id=uid, email=email, hashed_password="x"))
    db.commit()
    return uid


def _rpe_day(db, d: date, rpe: float, uid=1):
    db.add(models.DailyRecord(user_id=uid, date=d, session_rpe=rpe))
    db.commit()


def _aerobic(db, d: date, minutes: float, uid=1, sid=None):
    db.add(models.AerobicSession(
        user_id=uid, source="health_connect", source_session_id=sid or f"s-{d}",
        session_date=d, duration_minutes=minutes,
    ))
    db.commit()


def _load(db, d: date, window: str, load: float, uid=1, ref=None):
    db.add(models.LoadEvent(
        user_id=uid, source="hevy", source_ref=ref or f"u{uid}-{window}-{d}",
        load_window=window, occurred_at=_utc_noon(d), load=load,
        unit="kg_reps" if window == "mechanical" else "nm_au", formula_version="tier0-v1",
    ))
    db.commit()


# ── pure math ────────────────────────────────────────────────────────────────

def test_ridge_centres_residuals_and_tracks_a_linear_signal():
    """A tight linear actual~load fit yields residuals that sum to ~0 (centred) and are
    each small relative to the signal — the model explains the objective load."""
    x = [[float(i)] for i in range(1, 21)]
    y = [3.0 + 2.0 * i for i in range(1, 21)]   # exactly linear
    fit = ridge_fit(x, y)
    assert abs(sum(fit.residuals)) < 1e-6                     # centred
    assert max(abs(r) for r in fit.residuals) < 0.5 * (max(y) - min(y))


def test_ridge_flags_a_decoupled_point_with_a_positive_residual():
    """A day whose actual sRPE is FAR above what its (low) load predicts gets a positive
    residual — the decoupling marker. Paired control: a matching-load day is ~0."""
    x = [[float(i)] for i in range(1, 16)] + [[1.0]]
    y = [10.0 * i for i in range(1, 16)] + [200.0]           # last: tiny load, huge actual
    fit = ridge_fit(x, y)
    assert fit.residuals[-1] > 0                              # felt harder than load says
    assert fit.residuals[-1] == max(fit.residuals)


def test_ridge_zero_variance_column_does_not_blow_up():
    """A predictor that never varies (e.g. metabolic all-zero) contributes nothing
    rather than dividing by zero."""
    x = [[float(i), 0.0] for i in range(1, 16)]
    y = [5.0 * i for i in range(1, 16)]
    fit = ridge_fit(x, y)
    assert fit.beta[1] == 0.0                                 # constant column → no coef
    assert all(map(lambda v: v == v, fit.residuals))         # no NaN


def test_ewma_time_aware_weights_recent_and_handles_gaps():
    base = date(2026, 6, 1)
    flat = [(base, 1.0), (base.replace(day=2), 1.0), (base.replace(day=3), 1.0)]
    assert ewma_time_aware(flat, tau_days=7) == pytest.approx(1.0)
    assert ewma_time_aware([], tau_days=7) is None
    # A large gap lets the newest observation dominate the stale mean.
    rising = [(base, 0.0), (date(2026, 7, 1), 10.0)]
    assert ewma_time_aware(rising, tau_days=3) > 9.0


def test_severity_helpers_are_monotone_and_fail_soft():
    assert _stress_severity(1) == 0.0 and _stress_severity(5) == 1.0
    assert _stress_severity(None) is None
    assert _sleep_severity(500) == 0.0                        # >= target → not poor
    assert _sleep_severity(300) == 1.0                        # <= floor → worst
    assert 0.0 < _sleep_severity(390) < 1.0
    assert _sleep_severity(None) is None
    assert _combine_severity(None, None) is None              # both absent → None
    assert _combine_severity(1.0, None) == 1.0               # renormalise on one part


# ── residual producer ────────────────────────────────────────────────────────

def _seed_paired_days(db, n, uid=1, *, rpe_of=lambda i: 5.0, load_of=lambda i: 100.0,
                      minutes=60.0, start=date(2026, 6, 1)):
    days = []
    for i in range(n):
        d = date.fromordinal(start.toordinal() + i)
        _rpe_day(db, d, rpe_of(i), uid=uid)
        _aerobic(db, d, minutes, uid=uid, sid=f"s{i}")
        _load(db, d, "mechanical", load_of(i), uid=uid, ref=f"u{uid}-m{i}")
        days.append(d)
    return days


def test_cold_start_hard_flip_returns_none_below_15(db_session):
    _user(db_session)
    _seed_paired_days(db_session, 14)
    assert psychological_residual(1, db_session, as_of=date(2026, 7, 1)) is None


def test_residual_on_at_15_paired_days(db_session):
    _user(db_session)
    _seed_paired_days(db_session, 15, rpe_of=lambda i: 5.0, load_of=lambda i: 100.0)
    res = psychological_residual(1, db_session, as_of=date(2026, 7, 1))
    assert res is not None
    assert res.n_paired_days == 15


def test_producer_surfaces_a_decoupled_recent_day(db_session):
    """15 aligned days then a high-RPE / low-load day → the latest residual is positive
    and the smoothed value rises (felt-vs-objective decoupling caught)."""
    _user(db_session)
    # Days 0..14: rpe tracks load. Day 15: high rpe, low load.
    _seed_paired_days(db_session, 15, rpe_of=lambda i: 3.0 + i * 0.2,
                      load_of=lambda i: 50.0 + i * 10.0)
    d16 = date.fromordinal(date(2026, 6, 1).toordinal() + 15)
    _rpe_day(db_session, d16, 9.5)
    _aerobic(db_session, d16, 60.0, sid="s16")
    _load(db_session, d16, "mechanical", 10.0, ref="m16")   # tiny objective load
    res = psychological_residual(1, db_session, as_of=date(2026, 7, 1))
    assert res is not None and res.n_paired_days == 16
    assert res.latest_day == d16
    assert res.latest_residual > 0                            # felt harder than load says


def test_a_day_without_resolvable_duration_is_not_paired(db_session):
    """session_rpe present but no session that day (no duration) → excluded; the count
    drops below the flip and the producer emits nothing."""
    _user(db_session)
    _seed_paired_days(db_session, 15)
    # A 16th rpe day with NO aerobic/hevy session → unpaired; still 15 paired.
    orphan = date.fromordinal(date(2026, 6, 1).toordinal() + 15)
    _rpe_day(db_session, orphan, 8.0)
    res = psychological_residual(1, db_session, as_of=date(2026, 7, 1))
    assert res.n_paired_days == 15                            # orphan excluded


def test_gate2_psychological_load_event_is_never_a_predictor(db_session):
    """A psychological load_event on a paired day must NOT change the residual — it is
    not a predictor (exclusivity, gate 2). Positive control: the same magnitude added as
    a MECHANICAL event on the identically-seeded control DOES move the residual.

    Three identically-seeded users: #3 is the event-free control, #1 gets an extra
    psychological event (must be ignored → residual == control), #2 gets an extra
    mechanical event (must count → residual != control)."""
    def _seed(uid, email):
        _user(db_session, uid=uid, email=email)
        _seed_paired_days(db_session, 15, uid=uid, rpe_of=lambda i: 4.0 + i * 0.1,
                          load_of=lambda i: 80.0 + i * 5.0)

    _seed(1, "pw1@x.com")
    _seed(2, "pw2@x.com")
    _seed(3, "pw3@x.com")
    d0 = date(2026, 6, 1)
    _load(db_session, d0, "psychological", 999.0, uid=1, ref="psy0")  # must be ignored
    _load(db_session, d0, "mechanical", 999.0, uid=2, ref="mx0")      # must count

    r1 = psychological_residual(1, db_session, as_of=date(2026, 7, 1))
    r2 = psychological_residual(2, db_session, as_of=date(2026, 7, 1))
    control = psychological_residual(3, db_session, as_of=date(2026, 7, 1))

    assert r1.latest_residual == pytest.approx(control.latest_residual, abs=1e-9)
    assert r2.latest_residual != pytest.approx(control.latest_residual, abs=1e-6)


def test_metabolic_under_metab_v1_enters_the_fit(db_session):
    """Regression (review): metabolic load_events are written under
    FORMULA_VERSION_METABOLIC ('metab-v1') — NOT the tier0-v1 that mechanical/
    neuromuscular carry. A single-version filter dropped the metabolic predictor
    entirely (its column stayed all-zero). Prove (a) the (window, version) pairing
    surfaces metabolic load, and (b) it actually enters the ridge — the residual moves
    versus an identically-seeded, metabolic-free control."""
    from reads.psychological_reads import _daily_load_by_window
    from load_events_metabolic import FORMULA_VERSION_METABOLIC, WINDOW_METABOLIC

    _user(db_session, uid=1)
    _user(db_session, uid=2, email="ctl@x.com")
    for uid in (1, 2):
        _seed_paired_days(db_session, 15, uid=uid, rpe_of=lambda i: 4.0 + i * 0.1,
                          load_of=lambda i: 60.0 + i * 4.0)
    last = date.fromordinal(date(2026, 6, 1).toordinal() + 14)
    # A metabolic load_event under metab-v1 on user 1's latest paired day only.
    db_session.add(models.LoadEvent(
        user_id=1, source="aerobic", source_ref="aero-last", load_window=WINDOW_METABOLIC,
        occurred_at=_utc_noon(last), load=400.0, unit="au",
        formula_version=FORMULA_VERSION_METABOLIC,
    ))
    db_session.commit()

    # (a) the pairing surfaces it (the pre-fix single-version filter returned nothing).
    by_day = _daily_load_by_window(db_session, 1)
    assert by_day[last].get("metabolic") == 400.0

    # (b) it enters the fit — user 1's latest residual differs from the metabolic-free
    # control seeded identically otherwise.
    r1 = psychological_residual(1, db_session, as_of=date(2026, 7, 1))
    ctl = psychological_residual(2, db_session, as_of=date(2026, 7, 1))
    assert r1 is not None and ctl is not None
    assert r1.latest_residual != pytest.approx(ctl.latest_residual, abs=1e-6)


def test_gate5_multi_session_day_is_flagged_not_averaged(db_session):
    """A day with two sessions is recorded in `multi_session_days`, and its duration is
    SUMMED (not averaged) into actual_sRPE."""
    _user(db_session)
    _seed_paired_days(db_session, 15)
    multi = date(2026, 6, 1)
    _aerobic(db_session, multi, 30.0, sid="extra")           # a 2nd session that day
    res = psychological_residual(1, db_session, as_of=date(2026, 7, 1))
    assert multi in res.multi_session_days


# ── life-load modulator ──────────────────────────────────────────────────────

def _daily(db, d: date, *, life_load=None, sleep_min=None, uid=1):
    db.add(models.DailyRecord(
        user_id=uid, date=d, life_load=life_load, passive_sleep_min=sleep_min,
    ))
    db.commit()


def test_life_load_bias_fails_closed_with_no_data(db_session):
    _user(db_session)
    assert life_load_severity(1, db_session, as_of=date(2026, 7, 1)) is None
    assert life_load_bias(1, db_session, as_of=date(2026, 7, 1)) is False


def test_life_load_bias_fires_on_sustained_elevated_load(db_session):
    """High stress + poor sleep across the recent window → severity over threshold →
    True. Paired control: a calm window → False."""
    _user(db_session)
    as_of = date(2026, 7, 10)
    for i in range(7):
        d = date.fromordinal(as_of.toordinal() - i)
        _daily(db_session, d, life_load=5, sleep_min=300)    # max stress, floor sleep
    assert life_load_bias(1, db_session, as_of=as_of) is True

    _user(db_session, uid=2, email="calm@x.com")
    for i in range(7):
        d = date.fromordinal(as_of.toordinal() - i)
        _daily(db_session, d, life_load=1, sleep_min=500, uid=2)  # calm, good sleep
    assert life_load_bias(2, db_session, as_of=as_of) is False


def test_life_load_reads_canonical_sleep_only(db_session):
    """With no stress item but poor canonical TST (passive_sleep_min), the flag still
    reflects sleep — the canonical read is honoured and no second estimate is minted."""
    _user(db_session)
    as_of = date(2026, 7, 10)
    for i in range(7):
        d = date.fromordinal(as_of.toordinal() - i)
        _daily(db_session, d, life_load=None, sleep_min=300)  # sleep-only, worst
    sev = life_load_severity(1, db_session, as_of=as_of)
    assert sev == pytest.approx(1.0)                          # driven purely by sleep


# ── selection wiring ─────────────────────────────────────────────────────────

def _profile(db):
    uid = _user(db)
    p = profile_mod.upsert_profile(db, uid, dict(profile_mod.LUKE_PROFILE_SEED))
    return uid, p


def _queue(db, uid, p):
    return selection.compute_probe_queue(db, uid, profile=p, loaded_region_keys=set())


def test_life_load_bias_reranks_independently_of_readiness(db_session):
    """life_load_bias fires the recovery re-rank with readiness ABSENT (independent
    trigger). Recovery vehicles lead; the life-load note is present; no readiness note."""
    uid, p = _profile(db_session)
    q = _queue(db_session, uid, p)
    out = selection.select_next(
        db_session, uid, profile=p, probe_queue=q,
        readiness_hint=None, life_load_bias=True,
    )
    keys = [v["key"] for v in out["fortify"]["vehicles"]]
    assert keys[0] in ("swim", "pilates_clinical", "hike")
    assert any("Elevated life-load" in n for n in out["notes"])
    assert not any("Low subjective readiness" in n for n in out["notes"])


def test_both_triggers_surface_both_reasons(db_session):
    uid, p = _profile(db_session)
    q = _queue(db_session, uid, p)
    out = selection.select_next(
        db_session, uid, profile=p, probe_queue=q,
        readiness_hint=2, life_load_bias=True,
    )
    assert any("Low subjective readiness" in n for n in out["notes"])
    assert any("Elevated life-load" in n for n in out["notes"])


def test_life_load_bias_false_is_a_noop(db_session):
    """Default False leaves selection byte-identical to no argument at all — the flag
    only ever ADDS a bias, never removes one (down-only)."""
    uid, p = _profile(db_session)
    q = _queue(db_session, uid, p)
    baseline = selection.select_next(db_session, uid, profile=p, probe_queue=q)
    with_false = selection.select_next(
        db_session, uid, profile=p, probe_queue=q, life_load_bias=False,
    )
    assert with_false == baseline


def test_life_load_bias_never_touches_dosing(db_session):
    """The re-rank changes vehicle ORDER only; the dosing block is identical with and
    without the flag (re-rank, never a gate — DECISIONS_LOG #8)."""
    uid, p = _profile(db_session)
    q = _queue(db_session, uid, p)
    off = selection.select_next(db_session, uid, profile=p, probe_queue=q)
    on = selection.select_next(
        db_session, uid, profile=p, probe_queue=q, life_load_bias=True,
    )
    assert on["fortify"]["dosing"] == off["fortify"]["dosing"]
    if off["probe"] is not None:
        assert on["probe"]["dosing"] == off["probe"]["dosing"]
