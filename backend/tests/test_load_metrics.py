"""Q6 gate 3 — load_metrics daily rollup: structural + fail-closed behaviour.

Mutation-proofed (FEEDBACK §17/§18): every gate asserts a value or a presence/absence a
broken transform would flip, and negatives are paired with a positive control so a
transform that emitted nothing could not pass. The Banister ARITHMETIC oracle lives in
`test_load_metrics_reconciliation.py`; this file pins routing, versioning, fail-closed
windows, the undated skip, idempotency, the day-boundary rule, and unit isolation.
"""
from datetime import datetime, timezone

import pytest

import models
import load_metrics as lm
from load_metrics import compute_load_metrics, compute_window_series, METRICS_VERSION


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _le(db, *, ref, window, load, occurred_at, uid=1, unit=None, fv="tier0-v1"):
    if unit is None:
        unit = "kg_reps" if window == "mechanical" else "nm_au"
    db.add(models.LoadEvent(
        user_id=uid, source="hevy", source_ref=ref, load_window=window,
        occurred_at=occurred_at, load=load, unit=unit, formula_version=fv,
    ))
    db.commit()


def _rows(db, uid=1):
    return db.query(models.LoadMetric).order_by(
        models.LoadMetric.load_window, models.LoadMetric.day
    ).all()


# ── Pure series: EWMA recurrence + form sign (mutation-proof on τ and k) ─────────

def test_window_series_ewma_recurrence_and_form():
    """fitness/fatigue are the NORMALISED Banister EWMAs (#18/banister-v2): the load term
    is weighted by (1 − decay), so day-0 stocks are FRACTIONS of the load, not the load
    itself, and form starts strongly NEGATIVE (fatigue-τ < fitness-τ ⇒ (1 − decay_fat) >
    (1 − decay_fit) ⇒ fatigue outruns fitness). Two days, one load each — a wrong τ, the
    old un-normalised recurrence, or a wrong form sign all fail here."""
    from datetime import date
    import math
    dfit = math.exp(-1 / 42)
    dfat = math.exp(-1 / 10)
    series = compute_window_series(
        {date(2026, 6, 1): 100.0, date(2026, 6, 2): 50.0},
        date(2026, 6, 2),
        tau_fatigue_days=10,
    )
    assert [m.day for m in series] == [date(2026, 6, 1), date(2026, 6, 2)]

    # Day 0 (load 100): stock = (1 − decay)·load, seeded from 0. Normalisation makes these
    # ~2.35 / ~9.52, NOT 100/100 as the old leaky sum produced — and form starts negative.
    exp_fit0 = 100.0 * (1.0 - dfit)      # ≈ 2.352831
    exp_fat0 = 100.0 * (1.0 - dfat)      # ≈ 9.516258
    assert series[0].fitness == pytest.approx(exp_fit0, abs=1e-6)
    assert series[0].fatigue == pytest.approx(exp_fat0, abs=1e-6)
    assert series[0].form == pytest.approx(exp_fit0 - exp_fat0, abs=1e-6)   # ≈ −7.163427
    assert series[0].form < 0                                               # normalised ⇒ day-0 form negative

    # Day 1 (load 50): stock = day0·decay + (1 − decay)·50 for each window.
    exp_fit1 = exp_fit0 * dfit + (1.0 - dfit) * 50.0
    exp_fat1 = exp_fat0 * dfat + (1.0 - dfat) * 50.0
    assert series[1].fitness == pytest.approx(exp_fit1, abs=1e-6)
    assert series[1].fatigue == pytest.approx(exp_fat1, abs=1e-6)
    assert series[1].form == pytest.approx(exp_fit1 - exp_fat1, abs=1e-6)


# ── Normalisation property tests (behaviour, not numbers) — pin "form goes negative" ──
# against a future un-normalising regression (the old leaky sum kept form ≥ 0 forever).

def test_constant_load_converges_to_that_load():
    """Property (a): a constant load L for 300 days drives BOTH stocks to L and form to 0.
    The signature of a normalised EWMA — the un-normalised sum would run away to L/(1−decay)
    (thousands), never converging on L. τ_fit=42 is the slow stock, so 300 days is the bound
    that gets it within 1e-3·L."""
    from datetime import date, timedelta
    L = 100.0
    d0 = date(2026, 1, 1)
    daily = {d0 + timedelta(days=k): L for k in range(300)}
    series = compute_window_series(daily, d0 + timedelta(days=299), tau_fatigue_days=10)
    last = series[-1]
    assert last.fitness == pytest.approx(L, abs=1e-3 * L)
    assert last.fatigue == pytest.approx(L, abs=1e-3 * L)
    assert last.form == pytest.approx(0.0, abs=1e-3 * L)


def test_spike_day_drives_form_negative():
    """Property (b): from steady state, a single day at 2L pushes form NEGATIVE that day —
    fatigue (shorter τ ⇒ larger 1−decay) responds harder to the spike than fitness does."""
    from datetime import date, timedelta
    L = 100.0
    d0 = date(2026, 1, 1)
    daily = {d0 + timedelta(days=k): L for k in range(300)}
    spike = d0 + timedelta(days=300)
    daily[spike] = 2 * L
    series = compute_window_series(daily, spike, tau_fatigue_days=10)
    assert series[-1].form < 0


def test_rest_after_spike_recovers_form_positive():
    """Property (c): after the spike, 14 rest days recover form to POSITIVE — fatigue decays
    faster (τ_fat=10) than fitness (τ_fit=42), so the gap flips sign. The training→rest sign
    change the FormChart caption and #18 both assert."""
    from datetime import date, timedelta
    L = 100.0
    d0 = date(2026, 1, 1)
    daily = {d0 + timedelta(days=k): L for k in range(300)}
    daily[d0 + timedelta(days=300)] = 2 * L
    as_of = d0 + timedelta(days=314)   # 14 rest days after the spike
    series = compute_window_series(daily, as_of, tau_fatigue_days=10)
    assert series[-1].daily_load == 0.0     # confirm the tail is a rest day
    assert series[-1].form > 0


def test_rest_day_is_continuous_and_decays():
    """A gap day appears in the series with daily_load=0 and STRICTLY decayed stocks —
    the continuous-calendar rule. A transform that skipped rest days fails the length."""
    from datetime import date
    series = compute_window_series(
        {date(2026, 6, 1): 100.0, date(2026, 6, 4): 100.0},  # 2-day gap
        date(2026, 6, 4),
        tau_fatigue_days=10,
    )
    assert [m.day.isoformat() for m in series] == [
        "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04",
    ]
    rest = series[1]  # 06-02
    assert rest.daily_load == 0.0
    assert 0.0 < rest.fitness < series[0].fitness   # decayed, not reset, not carried flat
    assert 0.0 < rest.fatigue < series[0].fatigue


def test_maturity_low_until_42_continuous_days():
    """maturity flips 'low'→'ok' at exactly 42 days of continuous history."""
    from datetime import date
    series = compute_window_series(
        {date(2026, 6, 1): 100.0},          # one load; tail decays to as_of
        date(2026, 6, 1) + __import__("datetime").timedelta(days=50),
        tau_fatigue_days=10,
    )
    assert series[40].maturity == "low"     # 41st day
    assert series[41].maturity == "ok"      # 42nd day — the boundary
    assert series[-1].maturity == "ok"


# ── Orchestrator: routing, fail-closed, versioning, undated, idempotency ─────────

def test_fail_closed_psychological_window_never_computed(db_session):
    """A psychological load_event produces NO metric row — the fatigue-τ table has no
    key for it (Q122). Paired positive control: a mechanical event on the same day DOES
    produce rows, so the absence is fail-closed routing, not an empty transform."""
    _user(db_session)
    _le(db_session, ref="p1", window="psychological", load=99.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"), unit="au")
    _le(db_session, ref="m1", window="mechanical", load=100.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"))
    summary = compute_load_metrics(db_session, 1, as_of=__import__("datetime").date(2026, 6, 1))
    windows = {r.load_window for r in _rows(db_session)}
    assert "psychological" not in windows        # fail-closed
    assert "mechanical" in windows               # positive control
    assert "psychological" in summary["windows_skipped_no_tau"]


def test_metabolic_provisioned_computes_when_fed(db_session):
    """metabolic carries a τ (provisioned, #32) → a metabolic load_event DOES light up a
    row, without re-architecting. Contrast with psychological's fail-closed absence."""
    _user(db_session)
    _le(db_session, ref="mtb1", window="metabolic", load=200.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"), unit="trimp")
    compute_load_metrics(db_session, 1, as_of=__import__("datetime").date(2026, 6, 1))
    rows = _rows(db_session)
    assert [r.load_window for r in rows] == ["metabolic"]
    assert rows[0].unit == "trimp"


def test_undated_load_event_excluded(db_session):
    """occurred_at NULL cannot be placed on a day — excluded (mirrors the e1RM skip).
    Positive control: a dated event on the same window IS rolled up."""
    _user(db_session)
    _le(db_session, ref="dated", window="mechanical", load=100.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"))
    _le(db_session, ref="undated", window="mechanical", load=500.0, occurred_at=None)
    compute_load_metrics(db_session, 1, as_of=__import__("datetime").date(2026, 6, 1))
    rows = _rows(db_session)
    assert len(rows) == 1                         # only the dated day
    assert rows[0].daily_load == pytest.approx(100.0)   # 500 undated NOT summed in


def test_recompute_is_idempotent(db_session):
    """delete-and-reinsert per (user, formula_version, metrics_version): a second run is
    byte-identical, not appended."""
    import datetime as _d
    _user(db_session)
    _le(db_session, ref="m1", window="mechanical", load=100.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"))
    _le(db_session, ref="m2", window="mechanical", load=50.0,
        occurred_at=_utc("2026-06-03T00:00:00Z"))
    compute_load_metrics(db_session, 1, as_of=_d.date(2026, 6, 3))
    first = {(r.load_window, r.day, r.fitness, r.fatigue, r.form) for r in _rows(db_session)}
    compute_load_metrics(db_session, 1, as_of=_d.date(2026, 6, 3))
    second = {(r.load_window, r.day, r.fitness, r.fatigue, r.form) for r in _rows(db_session)}
    assert len(_rows(db_session)) == 3            # not 6 — replaced, not appended
    assert first == second


def test_local_day_uses_aest_boundary(db_session):
    """S1 rule: a session at 2026-06-05T16:00:00Z is 2026-06-06T02:00 AEST → local day
    06-06, NOT the UTC date 06-05. Pins `_local_day`'s astimezone(AEST) (a `.date()`
    direct rule would place it on 06-05 — this test would then fail, which is the
    release-gate tripwire)."""
    import datetime as _d
    _user(db_session)
    _le(db_session, ref="near_midnight", window="mechanical", load=100.0,
        occurred_at=_utc("2026-06-05T16:00:00Z"))
    compute_load_metrics(db_session, 1, as_of=_d.date(2026, 6, 6))
    by_day = {r.day.isoformat(): r.daily_load for r in _rows(db_session)}
    # astimezone(AEST): the only load day is 06-06, so the continuous calendar starts there
    # and 06-05 has no row at all. Mutation-proof vs a `.date()` rule, which would place the
    # load on 06-05 (making 06-06 a rest row with load 0) — both assertions would then flip.
    assert by_day == {"2026-06-06": pytest.approx(100.0)}     # landed on the local day, sole row
    assert "2026-06-05" not in by_day                         # NOT the UTC day


def test_units_are_window_native_not_crossed(db_session):
    import datetime as _d
    _user(db_session)
    _le(db_session, ref="m1", window="mechanical", load=100.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"))
    _le(db_session, ref="n1", window="neuromuscular", load=2.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"))
    compute_load_metrics(db_session, 1, as_of=_d.date(2026, 6, 1))
    unit = {r.load_window: r.unit for r in _rows(db_session)}
    assert unit == {"mechanical": "kg_reps", "neuromuscular": "nm_au"}


def test_only_named_formula_version_rolled_up(db_session):
    """A load_event from a different formula_version is not consumed by a tier0-v1 rollup."""
    import datetime as _d
    _user(db_session)
    _le(db_session, ref="cur", window="mechanical", load=100.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"), fv="tier0-v1")
    _le(db_session, ref="old", window="mechanical", load=999.0,
        occurred_at=_utc("2026-06-01T00:00:00Z"), fv="tier0-v0")
    compute_load_metrics(db_session, 1, formula_version="tier0-v1", as_of=_d.date(2026, 6, 1))
    rows = _rows(db_session)
    assert len(rows) == 1
    assert rows[0].daily_load == pytest.approx(100.0)     # 999 (tier0-v0) excluded
    assert rows[0].metrics_version == METRICS_VERSION
