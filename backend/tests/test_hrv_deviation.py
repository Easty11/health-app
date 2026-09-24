"""#292 — per-source-normalised HRV deviation + cross-source confidence reader.

Exercises `reads.recovery_reads.hrv_deviation` / `representative_source` against the
in-memory SQLite `db_session` fixture (no network). Covers the brief's mandated cases:
new-source-doesn't-swamp, flat-is-confident, settling caps, conflicted, immature-single,
and the 5 dual-wear DELOAD nights as real divergent data — plus the confidence tiers, the
representative-number rule, and that the deviation reader shares canonical_hrv's row
plumbing without touching arbitration.

Governing principle under test: two devices measuring the same night are two instruments,
not two candidates for one truth — never blend raw ms; normalise each source to its OWN
baseline, combine deviations by weight, surface disagreement as confidence.
"""
from __future__ import annotations

from datetime import date, timedelta

import models
from reads.recovery_reads import (
    MIN_BASELINE_N,
    canonical_hrv,
    hrv_deviation,
    representative_source,
)

_FOR_DATE = date(2026, 6, 30)


def _user(db, uid=7):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _seed(db, user_id, source, start_offset, count, rmssd):
    """`count` consecutive nightly rows for `source`, the oldest at
    `_FOR_DATE - start_offset`. `rmssd` is a scalar (constant) or a per-night list."""
    for i in range(count):
        d = _FOR_DATE - timedelta(days=start_offset - i)
        v = rmssd[i] if isinstance(rmssd, (list, tuple)) else rmssd
        db.add(models.HrvReading(user_id=user_id, captured_at=d, source=source, rmssd_ms=v))
    db.commit()


def _src(result, name):
    return next((s for s in result["sources"] if s["source"] == name), None)


# ── new-source-doesn't-swamp ─────────────────────────────────────────────────────
def test_new_source_does_not_swamp_established(db_session):
    """Thin-baseline Garmin + mature Samsung → combined tracks Samsung, and the fresh
    source contributes at a strictly lower weight until it matures. This is what stops a
    just-connected Garmin flipping the metric on day one."""
    user = _user(db_session)
    # Mature Samsung, sitting FLAT: 25 baseline nights @50, today also @50 → z = 0.
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=_FOR_DATE,
                                     source="samsung", rmssd_ms=50.0))
    # Thin (just-connected) Garmin swinging hard: 3 baseline nights @40, today +9 → z ≈ +3.
    _seed(db_session, user.id, "garmin", start_offset=3, count=3, rmssd=40.0)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=_FOR_DATE,
                                     source="garmin", rmssd_ms=49.0))
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    s, g = _src(res, "samsung"), _src(res, "garmin")

    assert g["weight"] < s["weight"]          # fresh source down-weighted
    assert s["mature"] and not g["mature"]
    assert abs(g["z"]) >= 1.0                  # Garmin really is swinging
    # Combined tracks the established source: Garmin's day-one swing does NOT flip the
    # metric — combined stays near Samsung's flat (well inside the dead-zone), not Garmin's.
    assert res["direction"] == "flat"
    assert abs(res["combined_z"]) < 0.5
    assert abs(res["combined_z"] - s["z"]) < abs(res["combined_z"] - g["z"])
    # The single ms scalar a scalar-consumer would take is Samsung's, not Garmin's.
    assert representative_source(res)["source"] == "samsung"


# ── flat is CONFIDENT-neutral, not low ───────────────────────────────────────────
def test_flat_is_confident_not_very_low(db_session):
    """All sources inside the dead-zone → direction=flat with a CONFIDENT state.
    "Nothing's happening" is not "we don't know": never very_low, never low."""
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    _seed(db_session, user.id, "garmin", start_offset=25, count=25, rmssd=40.0)
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="samsung", rmssd_ms=51.0),
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="garmin", rmssd_ms=41.0),
    ])
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert all(abs(s["z"]) < 0.5 for s in res["sources"])
    assert res["direction"] == "flat"
    assert res["confidence"] == "flat"
    assert res["confidence"] not in {"very_low", "low"}


# ── settling caps confidence at low, keeps the deviation ──────────────────────────
def test_settling_caps_confidence_but_keeps_deviation(db_session):
    """A recent phase change makes the baseline unsettled: an otherwise-high verdict is
    capped at low, the deviation is still emitted, and baseline_state flags settling."""
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    _seed(db_session, user.id, "garmin", start_offset=25, count=25, rmssd=40.0)
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="samsung", rmssd_ms=56.0),
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="garmin", rmssd_ms=46.0),
    ])
    db_session.commit()

    # Without settling this is two mature sources, same direction, zero gap → high.
    baseline = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert baseline["confidence"] == "high"

    res = hrv_deviation(
        user.id, db_session, for_date=_FOR_DATE,
        phase_change_date=_FOR_DATE - timedelta(days=3),
    )
    assert res["baseline_state"] == "settling"
    assert res["confidence"] == "low"           # capped
    assert res["direction"] == "up"             # deviation still present
    assert res["combined_z"] >= 0.5


# ── conflicted: opposite signs outside the dead-zone, no verdict ──────────────────
def test_conflicted_opposite_signs(db_session):
    """Two sources moving opposite ways outside the dead-zone → conflicted: surface both,
    no directional verdict."""
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    _seed(db_session, user.id, "garmin", start_offset=25, count=25, rmssd=40.0)
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="samsung", rmssd_ms=56.0),  # up
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="garmin", rmssd_ms=34.0),    # down
    ])
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["confidence"] == "conflicted"
    assert res["direction"] == "flat"           # no single verdict
    assert res["n_contributing"] == 2
    assert {s["source"] for s in res["sources"]} == {"samsung", "garmin"}
    assert _src(res, "samsung")["z"] > 0 and _src(res, "garmin")["z"] < 0


# ── immature single source → very_low / building ─────────────────────────────────
def test_immature_single_source_very_low_building(db_session):
    user = _user(db_session)
    _seed(db_session, user.id, "garmin", start_offset=3, count=3, rmssd=40.0)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=_FOR_DATE,
                                     source="garmin", rmssd_ms=49.0))  # active (z ≈ +3)
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["n_contributing"] == 1
    assert res["confidence"] == "very_low"
    assert res["baseline_state"] == "building"
    assert not res["sources"][0]["mature"]


# ── single MATURE source → medium_low ────────────────────────────────────────────
def test_single_mature_source_medium_low(db_session):
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=_FOR_DATE,
                                     source="samsung", rmssd_ms=58.0))  # active
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["n_contributing"] == 1
    assert res["sources"][0]["mature"]
    assert res["confidence"] == "medium_low"
    assert res["baseline_state"] == "normal"


# ── confidence tiers: gap drives high vs medium ──────────────────────────────────
def test_two_mature_same_direction_medium_when_gap_wide(db_session):
    """Both mature, same direction, but the magnitudes differ enough that the gap lands in
    (AGREEMENT_HIGH, AGREEMENT_MED] → medium ("agree on direction, differ on magnitude")."""
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    _seed(db_session, user.id, "garmin", start_offset=25, count=25, rmssd=40.0)
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="samsung", rmssd_ms=53.0),  # z=1.0
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="garmin", rmssd_ms=48.5),    # z≈2.5
    ])
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["direction"] == "up"
    assert 1.0 < res["agreement_gap"] <= 2.0
    assert res["confidence"] == "medium"


# ── the 5 dual-wear DELOAD nights: real divergent data ───────────────────────────
def test_five_dual_wear_deload_nights(db_session):
    """Reuse the 5 dual-wear nights (tagged DELOAD) as a fixture: two instruments on the
    same nights with a NON-CONSTANT offset (2..26 ms here). Assert the model combines
    each source's own-baseline deviation — never a raw-ms blend — and that a thin (n=4)
    baseline yields no false high/medium."""
    user = _user(db_session)
    samsung = [48.0, 52.0, 55.0, 60.0, 62.0]
    garmin = [50.0, 53.0, 60.0, 72.0, 88.0]     # offsets 2,1,5,12,26 — non-constant
    for i in range(5):
        d = _FOR_DATE - timedelta(days=4 - i)
        db_session.add(models.HrvReading(user_id=user.id, captured_at=d, source="samsung", rmssd_ms=samsung[i]))
        db_session.add(models.HrvReading(user_id=user.id, captured_at=d, source="garmin", rmssd_ms=garmin[i]))
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    s, g = _src(res, "samsung"), _src(res, "garmin")

    assert res["n_contributing"] == 2
    assert s["baseline_n"] == 4 and g["baseline_n"] == 4        # thin — one week of overlap
    assert not s["mature"] and not g["mature"]
    assert res["baseline_state"] == "building"
    # Each source z'd against ITS OWN baseline mean, not a shared/blended raw value.
    assert s["rmssd"] == 62.0 and g["rmssd"] == 88.0
    assert s["baseline_mean"] != g["baseline_mean"]
    # Equal maturity → equal weight → combined is the mean of the two z's.
    assert abs(res["combined_z"] - (s["z"] + g["z"]) / 2) < 1e-9
    # Thin baselines can never manufacture a mature-tier verdict.
    assert res["confidence"] not in {"high", "medium"}


# ── the deviation reader shares plumbing, never touches arbitration ──────────────
def test_shares_row_plumbing_without_arbitration(db_session):
    """hrv_deviation reads ALL source rows for a night (no `.canonical` selection); the
    superseded canonical_hrv still arbitrates over the same rows independently."""
    user = _user(db_session)
    db_session.add_all([
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="samsung", rmssd_ms=50.0),
        models.HrvReading(user_id=user.id, captured_at=_FOR_DATE, source="garmin", rmssd_ms=42.0),
    ])
    db_session.commit()

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["n_contributing"] == 2                          # both sources, none dropped

    rows = canonical_hrv(user.id, db_session, as_of=_FOR_DATE)  # arbitration still callable
    assert sum(1 for r in rows if r.canonical) == 1            # exactly one winner


def test_no_data_is_very_low_building(db_session):
    user = _user(db_session)
    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["n_contributing"] == 0
    assert res["confidence"] == "very_low"
    assert res["baseline_state"] == "building"
    assert res["direction"] == "flat"
    assert representative_source(res) is None


def test_thresholds_are_parameterised(db_session):
    """Thresholds are keyword args, not hard-coded: widening the dead-zone turns an
    otherwise-directional night flat, proving the constant is honoured at the call site."""
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=25, count=25, rmssd=50.0)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=_FOR_DATE,
                                     source="samsung", rmssd_ms=53.0))  # z≈1.0
    db_session.commit()

    assert hrv_deviation(user.id, db_session, for_date=_FOR_DATE)["direction"] == "up"
    widened = hrv_deviation(user.id, db_session, for_date=_FOR_DATE, flat_threshold=5.0)
    assert widened["direction"] == "flat"
    assert MIN_BASELINE_N == 21     # the mature-at constant the maturity factor reads


# ── recency gate (#327): same wake-day or it does not contribute ────────────────
def test_g1_dead_mature_source_loses_to_fresh_source(db_session):
    """G1: a DEAD source (last reading D-20, mature 28-night baseline) + a FRESH source
    reading on D → the fresh source is representative; the dead one is excluded from
    weighting/combined_z/confidence and listed in stale_sources with its last date. Before
    the gate the dead source's frozen mature baseline out-weighed the fresh source and its
    20-day-old rmssd was reported as today's."""
    user = _user(db_session)
    # Dead Samsung: 28 mature nights ending D-20, sitting high @113.
    _seed(db_session, user.id, "samsung", start_offset=47, count=28, rmssd=113.0)
    # Fresh, thin Garmin: 5 nights ending ON D.
    _seed(db_session, user.id, "garmin", start_offset=4, count=5, rmssd=[60.0, 62.0, 61.0, 63.0, 64.0])

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)

    assert [s["source"] for s in res["sources"]] == ["garmin"]
    assert res["n_contributing"] == 1
    assert representative_source(res)["source"] == "garmin"
    assert representative_source(res)["rmssd"] == 64.0
    assert res["stale_sources"] == [
        {"source": "samsung", "last_captured_at": _FOR_DATE - timedelta(days=20)}
    ]
    # Dead source's maturity no longer manufactures confidence: one immature source.
    assert res["confidence"] == "very_low"
    assert res["baseline_state"] == "building"


def test_g2_only_dead_source_contributes_nothing(db_session):
    """G2 (model layer): only a dead source → sources[] empty, representative None, and the
    dead source surfaced in stale_sources so 'absent today' ≠ 'never any'."""
    user = _user(db_session)
    _seed(db_session, user.id, "samsung", start_offset=47, count=28, rmssd=113.0)

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)

    assert res["sources"] == []
    assert res["n_contributing"] == 0
    assert representative_source(res) is None
    assert res["confidence"] == "very_low" and res["direction"] == "flat"
    assert res["combined_z"] == 0.0
    assert res["stale_sources"] == [
        {"source": "samsung", "last_captured_at": _FOR_DATE - timedelta(days=20)}
    ]


def test_gate_is_one_day_strict_yesterday_is_stale(db_session):
    """Yesterday is not today: a D-1 reading is stale for for_date=D (no grace window)."""
    user = _user(db_session)
    _seed(db_session, user.id, "garmin", start_offset=25, count=25, rmssd=55.0)  # ends D-1

    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)

    assert res["sources"] == []
    assert res["stale_sources"][0]["last_captured_at"] == _FOR_DATE - timedelta(days=1)


def test_never_any_data_has_empty_stale_sources(db_session):
    """'Never any' is distinguishable from 'stale': no rows at all → stale_sources empty."""
    user = _user(db_session)
    res = hrv_deviation(user.id, db_session, for_date=_FOR_DATE)
    assert res["sources"] == [] and res["stale_sources"] == []


def test_gate_leaves_contributing_baseline_math_unchanged(db_session):
    """A contributing source's baseline is computed exactly as before the gate: the 28-day
    window before its D reading, including nights on which the OTHER source was dead."""
    user = _user(db_session)
    _seed(db_session, user.id, "garmin", start_offset=25, count=25, rmssd=50.0)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=_FOR_DATE,
                                     source="garmin", rmssd_ms=56.0))
    db_session.commit()

    g = _src(hrv_deviation(user.id, db_session, for_date=_FOR_DATE), "garmin")
    assert g["baseline_n"] == 25 and g["baseline_mean"] == 50.0 and g["mature"]
    assert g["z"] == (56.0 - 50.0) / 3.0     # SD floor
