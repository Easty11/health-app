"""Q6 gate 3 — the load_metrics reconciliation oracle.

The gate-2 discipline (DECISIONS_LOG #244): a hand-computed ARITHMETIC oracle over a
small dated series, asserting the Banister stocks and the ΔLoad ratio to the cent on
named days — an oracle the code cannot satisfy by implementing the wrong spec. The series
includes a rest gap and one session near local midnight (2026-06-05T16:00:00Z =
2026-06-06T02:00 AEST) that exercises the S1 day-boundary rule.

ORACLE (mechanical window; NORMALISED EWMA per #18 with the FIRST-WEEK-MEAN SEED of
banister-v4 — the load term is weighted by (1 − decay). τ_fit=42 → df=e^(-1/42)=0.976471687,
1-df=0.023528313; τ_fat=10 → dfat=e^(-1/10)=0.904837418, 1-dfat=0.095162582):

  daily_load by user-local (AEST) day: 06-01=100, 06-03=100, 06-06=100, 06-09=1400; rest days=0.

  banister-v4 SEED (P1.1): both stocks start at the mean of the first ACUTE_DAYS(7) daily_loads.
  Here the first 7 calendar days are 06-01..06-07 = [100,0,100,0,0,100,0] → seed = 300/7 =
  42.857142857. Day 0 (06-01) IS the seed: fitness(0)=fatigue(0)=42.857143, so form(0)=0 by
  construction. The recurrence runs from day 1:
    fitness(d) = fitness(d-1)*df   + (1-df)*load(d)     (d ≥ 1)
    fatigue(d) = fatigue(d-1)*dfat + (1-dfat)*load(d)   (d ≥ 1)
    form(d)    = fitness(d) - fatigue(d)                (k=1)

  Values re-derived independently under the seed semantics (a standalone re-implementation,
  not the module's own output fed back). Form now CROSSES ZERO — the warm-up artefact is gone,
  so form is 0 at day 0, positive on rest days as the fast fatigue stock decays below the
  seeded fitness, and negative on the 06-09 spike (fatigue outruns fitness):

    06-01: fit=42.857143,  fat=42.857143,   form=0.0          (seed; form(0)=0 by construction)
    06-02: fit=41.848787,  fat=38.778746,   form=3.07004      (rest, decays)
    06-03: fit=43.216987,  fat=44.604719,   form=-1.387733    (load)
    06-04: fit=42.200164,  fat=40.360019,   form=1.840145     (rest)
    06-05: fit=41.207265,  fat=36.519255,   form=4.68801      (rest)
    06-06: fit=42.590559,  fat=42.560247,   form=0.030312
           (the 06-05T16:00Z session lands HERE, not on 06-05 — boundary proof)
    06-07: fit=41.588475,  fat=38.510104,   form=3.078371     (rest)
    06-08: fit=40.609968,  fat=34.845383,   form=5.764585     (rest)
    06-09: fit=72.594123,  fat=164.757021,  form=-92.162898

  ΔLoad (#33): acute=mean(last 7 daily_loads), chronic=mean(all days, ≤28); rest days count 0.
  UNCHANGED by the seed — computed off daily_load, not the stocks.
    06-08: acute=[0,100,0,0,100,0,0]/7=28.571429; chronic=[100,0,100,0,0,100,0,0]/8=37.5;   ratio=0.761905
    06-09: acute=[100,0,0,100,0,0,1400]/7=228.571429; chronic=1700/9=188.888889;             ratio=1.210084
"""
from datetime import date, datetime, timezone

import pytest

import models
from load_events import FORMULA_VERSION as _FV
from load_metrics import compute_load_metrics


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _user(db, uid=1):
    # NULL rpe_complete_from → no P3 truncation, so the full 9-day calendar holds; the stock
    # values below are the banister-v4 first-week-mean seed (P1.1), the daily_load/ΔLoad
    # columns are unchanged by the seed.
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _le(db, ref, occurred_iso, load):
    db.add(models.LoadEvent(
        user_id=1, source="hevy", source_ref=ref, load_window="mechanical",
        occurred_at=_utc(occurred_iso), load=load, unit="kg_reps", formula_version=_FV,
    ))
    db.commit()


# expected (fitness, fatigue, form) per local day, 6dp (transform rounds to 6dp). Derived
# independently under the normalised recurrence with the banister-v4 first-week-mean seed
# (a standalone re-implementation, not the module's own output fed back).
_ORACLE = {
    "2026-06-01": (42.857143, 42.857143, 0.0),          # day 0 = seed → form 0 by construction
    "2026-06-02": (41.848787, 38.778746, 3.07004),
    "2026-06-03": (43.216987, 44.604719, -1.387733),
    "2026-06-06": (42.590559, 42.560247, 0.030312),
    "2026-06-09": (72.594123, 164.757021, -92.162898),
}


def test_reconciliation_mechanical_banister_and_dload(db_session):
    _user(db_session)
    _le(db_session, "s1", "2026-06-01T00:00:00Z", 100.0)      # → AEST 06-01
    _le(db_session, "s2", "2026-06-03T00:00:00Z", 100.0)      # → AEST 06-03
    _le(db_session, "s3", "2026-06-05T16:00:00Z", 100.0)      # → AEST 06-06 02:00 (boundary)
    _le(db_session, "s4", "2026-06-09T00:00:00Z", 1400.0)     # → AEST 06-09

    summary = compute_load_metrics(db_session, 1, as_of=date(2026, 6, 9))

    rows = {r.day.isoformat(): r for r in db_session.query(models.LoadMetric).all()}
    # continuous calendar 06-01..06-09 → 9 rows, one window
    assert len(rows) == 9
    assert summary["rows_written"] == 9 and summary["windows_computed"] == ["mechanical"]

    # Banister stocks + form to the cent on named days
    for day, (fit, fat, form) in _ORACLE.items():
        r = rows[day]
        assert r.fitness == pytest.approx(fit, abs=1e-6), day
        assert r.fatigue == pytest.approx(fat, abs=1e-6), day
        assert r.form == pytest.approx(form, abs=1e-6), day

    # boundary: the near-midnight session is on the LOCAL day 06-06, not the UTC day 06-05
    assert rows["2026-06-06"].daily_load == pytest.approx(100.0)
    assert rows["2026-06-05"].daily_load == pytest.approx(0.0)

    # rest-day decay row carries load 0 and decayed (not reset, not flat)
    assert rows["2026-06-02"].daily_load == 0.0
    assert rows["2026-06-02"].fitness < rows["2026-06-01"].fitness

    # ΔLoad acute:chronic — divergent both directions
    assert rows["2026-06-08"].acute_load == pytest.approx(28.571429, abs=1e-6)
    assert rows["2026-06-08"].chronic_load == pytest.approx(37.5, abs=1e-6)
    assert rows["2026-06-08"].load_ratio == pytest.approx(0.761905, abs=1e-6)
    assert rows["2026-06-09"].acute_load == pytest.approx(228.571429, abs=1e-6)
    assert rows["2026-06-09"].chronic_load == pytest.approx(188.888889, abs=1e-6)
    assert rows["2026-06-09"].load_ratio == pytest.approx(1.210084, abs=1e-6)

    # 9 days < 42 → every row immature; window-native unit
    assert all(r.maturity == "low" for r in rows.values())
    assert all(r.unit == "kg_reps" for r in rows.values())
