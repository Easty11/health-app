"""Q6 gate 3 — the load_metrics reconciliation oracle.

The gate-2 discipline (DECISIONS_LOG #244): a hand-computed ARITHMETIC oracle over a
small dated series, asserting the Banister stocks and the ΔLoad ratio to the cent on
named days — an oracle the code cannot satisfy by implementing the wrong spec. The series
includes a rest gap and one session near local midnight (2026-06-05T16:00:00Z =
2026-06-06T02:00 AEST) that exercises the S1 day-boundary rule.

ORACLE (mechanical window; τ_fit=42 → df=e^(-1/42)=0.976471687; τ_fat=10 → dfat=e^(-1/10)=0.904837418):

  daily_load by user-local (AEST) day: 06-01=100, 06-03=100, 06-06=100, 06-09=1400; rest days=0.
  fitness(d) = fitness(d-1)*df   + load(d)        seed fitness(06-01 -1)=0
  fatigue(d) = fatigue(d-1)*dfat + load(d)        seed fatigue(06-01 -1)=0
  form(d)    = fitness(d) - fatigue(d)            (k=1)

    06-01: fit=100,                       fat=100,                       form=0
    06-02: fit=100*df=97.647169,          fat=100*dfat=90.483742,        form=7.163427     (rest, decays)
    06-03: fit=97.647169*df+100=195.349695, fat=90.483742*dfat+100=181.873075, form=13.47662
    06-04: fit=190.753447,                fat=164.565564,                form=26.187883    (rest)
    06-05: fit=186.26534,                 fat=148.90508,                 form=37.36026     (rest)
    06-06: fit=186.26534*df+100=281.88283, fat=148.90508*dfat+100=234.734888, form=47.147942
           (the 06-05T16:00Z session lands HERE, not on 06-05 — boundary proof)
    06-07: fit=275.250603,                fat=212.39691,                 form=62.853693    (rest)
    06-08: fit=268.77442,                 fat=192.184672,                form=76.589749    (rest)
    06-09: fit=268.77442*df+1400=1662.450612, fat=192.184672*dfat+1400=1573.895882, form=88.55473

  ΔLoad (#33): acute=mean(last 7 daily_loads), chronic=mean(all days, ≤28); rest days count 0.
    06-08: acute=[0,100,0,0,100,0,0]/7=28.571429; chronic=[100,0,100,0,0,100,0,0]/8=37.5;   ratio=0.761905
    06-09: acute=[100,0,0,100,0,0,1400]/7=228.571429; chronic=1700/9=188.888889;             ratio=1.210084
"""
from datetime import date, datetime, timezone

import pytest

import models
from load_metrics import compute_load_metrics


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _le(db, ref, occurred_iso, load):
    db.add(models.LoadEvent(
        user_id=1, source="hevy", source_ref=ref, load_window="mechanical",
        occurred_at=_utc(occurred_iso), load=load, unit="kg_reps", formula_version="tier0-v1",
    ))
    db.commit()


# expected (fitness, fatigue, form) per local day, to the cent (transform rounds to 6dp)
_ORACLE = {
    "2026-06-01": (100.0, 100.0, 0.0),
    "2026-06-02": (97.647169, 90.483742, 7.163427),
    "2026-06-03": (195.349695, 181.873075, 13.47662),
    "2026-06-06": (281.88283, 234.734888, 47.147942),
    "2026-06-09": (1662.450612, 1573.895882, 88.55473),
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
