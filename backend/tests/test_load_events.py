"""Tier-0 strength load transform — D-C/D-D formulas + gap recording (Q6 gate 2).

Three layers, each MUTATION-PROOFED (FEEDBACK §17/§18 — a test that would pass under a
broken coefficient/routing is worthless):

  * per-set load (`compute_set_load`): every routing branch (RPE-usable, RPE-absent
    reps-band, warmup, failure=RIR 0, non-rep bridging, bodyweight) with a coefficient
    the test would catch if it changed;
  * e1RM fit (`epley_with_rir` / `rolling_e1rm`): RPE-usable only, rolling window, max;
  * session + orchestrator: D-E laterality halving vs indeterminate-surfaced, epoch
    gating, `excluded_at` skipped, idempotent per-`formula_version` recompute, and the
    provenance gap fields.
"""
from datetime import datetime, timezone

import pytest

import models
import load_events as le
from load_events import (
    BODYWEIGHT_KG,
    FORMULA_VERSION,
    compute_load_events,
    compute_set_load,
    epley_with_rir,
    rolling_e1rm,
    E1rmSample,
    Session_,
    compute_session_events,
)
from datetime import date


APPROX = 1e-6


# ── Band tables (mutation-proofed: each RIR must map to its own value) ──────────

@pytest.mark.parametrize("rir,m", [(5, 1.0), (4, 1.0), (3, 1.15), (2, 1.15), (1, 1.30), (0, 1.30)])
def test_mech_mult_table(rir, m):
    assert le._mech_mult(rir) == m


@pytest.mark.parametrize("rir,f", [(5, 0.0), (4, 0.25), (3, 0.5), (2, 0.75), (1, 0.9), (0, 1.0)])
def test_f_rir_table(rir, f):
    assert le._f_rir(rir) == f


def test_rir_from_rpe_half_up_and_clamped():
    assert le._rir_from_rpe(8.0) == 2
    assert le._rir_from_rpe(10.0) == 0
    assert le._rir_from_rpe(8.5) == 2      # RIR 1.5 → half-up → 2
    assert le._rir_from_rpe(11.0) == 0     # clamp >= 0


def test_h_intensity_bounds_and_ramp():
    assert le._h_intensity(0.40) == pytest.approx(0.25)   # floor of the ramp
    assert le._h_intensity(0.85) == pytest.approx(1.0)    # top of the ramp
    assert le._h_intensity(0.20) == pytest.approx(0.25)   # below → clamped
    assert le._h_intensity(1.5) == pytest.approx(1.0)     # above → clamped
    assert le._h_intensity(0.625) == pytest.approx(0.625)  # midpoint → 0.625


# ── Per-set load: routing branches ─────────────────────────────────────────────

def test_normal_set_with_rpe():
    """weight 100 × reps 5, RPE 8 (RIR 2), e1RM 125 (I=0.8)."""
    sl = compute_set_load({"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0},
                          e1rm=125.0)
    assert sl.mechanical == pytest.approx(575.0)          # 100*5*1.15
    assert sl.neuromuscular == pytest.approx(0.75 * 0.916666, abs=1e-4)  # f(2)*h(0.8)
    assert sl.rpe_used and sl.e1rm_used is True


def test_rpe_present_no_e1rm_uses_half():
    sl = compute_set_load({"weight_kg": 100.0, "reps": 5, "rpe": 8.0}, e1rm=None)
    assert sl.neuromuscular == pytest.approx(0.75 * 0.5)  # f(2)*0.5
    assert sl.e1rm_used is False


def test_rpe_absent_rep_set_bands_by_reps():
    """No RPE → Mechanical m=1.0, NM from the reps-band prior (no h(I))."""
    sl = compute_set_load({"weight_kg": 100.0, "reps": 5}, e1rm=125.0)
    assert sl.mechanical == pytest.approx(500.0)          # 100*5*1.0
    assert sl.neuromuscular == pytest.approx(0.6)         # reps<=5 prior
    assert sl.reps_banded and not sl.rpe_used


def test_reps_band_prior_tiers():
    assert compute_set_load({"weight_kg": 50.0, "reps": 5}, e1rm=None).neuromuscular == pytest.approx(0.6)
    assert compute_set_load({"weight_kg": 50.0, "reps": 8}, e1rm=None).neuromuscular == pytest.approx(0.35)
    assert compute_set_load({"weight_kg": 50.0, "reps": 12}, e1rm=None).neuromuscular == pytest.approx(0.15)


def test_warmup_half_mechanical_zero_nm():
    sl = compute_set_load({"type": "warmup", "weight_kg": 60.0, "reps": 5, "rpe": 5.0},
                          e1rm=100.0)
    assert sl.mechanical == pytest.approx(150.0)          # 60*5*1.0*0.5 (RIR5 → m=1.0)
    assert sl.neuromuscular == 0.0                        # excluded from NM
    assert sl.is_warmup


def test_failure_is_rir_zero_without_rpe():
    """Failure type = RIR 0 by definition (no rpe needed, epoch-independent)."""
    sl = compute_set_load({"type": "failure", "weight_kg": 100.0, "reps": 3},
                          e1rm=None)
    assert sl.mechanical == pytest.approx(390.0)          # 100*3*1.30 (m at RIR0)
    assert sl.neuromuscular == pytest.approx(1.0 * 0.5)   # f(0)*0.5
    assert sl.is_failure and not sl.reps_banded


def test_non_rep_distance_bridged_nm_zero():
    sl = compute_set_load({"weight_kg": 40.0, "distance_meters": 20.0}, e1rm=None)
    assert sl.mechanical == pytest.approx(40.0 * 20.0 * 0.3)  # 240
    assert sl.neuromuscular == 0.0
    assert sl.is_non_rep


def test_non_rep_timed_hold_bodyweight():
    sl = compute_set_load({"duration_seconds": 60}, e1rm=None)
    assert sl.mechanical == pytest.approx(BODYWEIGHT_KG * 60 * 0.05)  # 306
    assert sl.is_non_rep and sl.neuromuscular == 0.0


def test_bodyweight_rep_set_uses_operator_weight():
    sl = compute_set_load({"reps": 10, "rpe": 9.0}, e1rm=None)
    assert sl.mechanical == pytest.approx(BODYWEIGHT_KG * 10 * 1.30)  # RIR1 → m=1.30
    assert sl.neuromuscular == pytest.approx(0.9 * 0.5)               # f(1)*0.5


def test_empty_set_skipped():
    assert compute_set_load({"type": "normal"}, e1rm=None).skip is True


# ── e1RM fit ────────────────────────────────────────────────────────────────

def test_epley_with_rir():
    assert epley_with_rir(100.0, 5, 2.0) == pytest.approx(100 * (1 + 7 / 30))  # 123.333


def test_rolling_e1rm_max_in_window_none_outside():
    s = [
        E1rmSample("A", date(2026, 6, 1), 120.0),
        E1rmSample("A", date(2026, 6, 20), 130.0),   # in-window, higher
        E1rmSample("A", date(2026, 3, 1), 200.0),    # far outside 60d → ignored
        E1rmSample("B", date(2026, 6, 20), 999.0),   # other template
    ]
    assert rolling_e1rm(s, "A", date(2026, 6, 25)) == pytest.approx(130.0)
    assert rolling_e1rm(s, "A", date(2026, 3, 15)) == pytest.approx(200.0)  # only the March sample in window
    assert rolling_e1rm(s, "C", date(2026, 6, 25)) is None
    assert rolling_e1rm(s, "A", None) is None


def test_e1rm_samples_include_all_dates():
    """e1RM fits from ALL RPE-present working sets, ANY date. MUTATION-PROOF: a
    PRE-epoch RPE set MUST produce a sample — an epoch cutoff on the fit would drop it
    and this fails. Failure sets (no rpe) and non-rep sets produce none."""
    pre = _sess(date(2026, 4, 1), [(0, "A", {"weight_kg": 100.0, "reps": 5, "rpe": 8.0})])
    post = _sess(date(2026, 6, 1), [(0, "A", {"weight_kg": 110.0, "reps": 3, "rpe": 9.0})])
    fail_only = _sess(date(2026, 6, 2), [(0, "A", {"type": "failure", "weight_kg": 120.0, "reps": 2})])
    samples = le.e1rm_samples([pre, post, fail_only])
    dates = sorted(s.when for s in samples)
    assert dates == [date(2026, 4, 1), date(2026, 6, 1)]      # pre-epoch INCLUDED; failure excluded


# ── Session-level: per-set RPE + laterality (mutation-proofed) ─────────────────

def _sess(when, sets):
    """sets: list of (block_index, template_id, raw_set)."""
    return Session_(hevy_id="s", when=when, occurred_at=None, sets=sets)


def test_rpe_is_per_set_any_date():
    """MUTATION-PROOF against re-introducing epoch gating: an RPE-carrying set bands on
    (reps, RPE) whatever its date. A PRE-epoch RPE set MUST band identically to a
    post-epoch one — if pre-epoch RPE were discarded (→ m=1.0, load 500) this fails."""
    st = {"weight_kg": 100.0, "reps": 5, "rpe": 8.0}
    post = compute_session_events(_sess(date(2026, 6, 1), [(0, "T", st)]),
                                  laterality_by_template={}, e1rm_by_template={"T": None})
    pre = compute_session_events(_sess(date(2026, 4, 1), [(0, "T", st)]),
                                 laterality_by_template={}, e1rm_by_template={"T": None})
    assert post["mechanical"]["load"] == pytest.approx(575.0)   # m(RIR2)=1.15
    assert pre["mechanical"]["load"] == pytest.approx(575.0)    # SAME — RPE is per-set, date-agnostic
    assert post["neuromuscular"]["provenance"]["rpe_sets"] == 1
    assert pre["neuromuscular"]["provenance"]["rpe_sets"] == 1  # NOT reps_banded


def test_unilateral_pair_not_discounted_in_load():
    """MUTATION-PROOF: load SUMS SETS AS LOGGED — a `unilateral` pair is NOT halved.
    A halved cost (500 / 0.35) would FAIL here. Pairing is surfaced in provenance only."""
    st = {"weight_kg": 50.0, "reps": 10}
    sets = [(0, "UNI", st), (1, "UNI", st)]
    ev = compute_session_events(_sess(date(2026, 6, 1), sets),
                                laterality_by_template={"UNI": "unilateral"},
                                e1rm_by_template={"UNI": None})
    # two blocks of 50*10*1.0=500 each → 1000, summed as logged (NOT halved)
    assert ev["mechanical"]["load"] == pytest.approx(1000.0)
    assert ev["neuromuscular"]["load"] == pytest.approx(0.70)   # 0.35 + 0.35, not averaged
    assert ev["mechanical"]["provenance"]["paired_templates"] == ["UNI"]   # surfaced for asymmetry
    assert ev["neuromuscular"]["provenance"]["paired_templates"] == ["UNI"]


def test_untagged_pair_indeterminate_surfaced_not_costed():
    """Untagged repeated template → surfaced as indeterminate, load unchanged (summed)."""
    st = {"weight_kg": 50.0, "reps": 10}
    sets = [(0, "UNT", st), (1, "UNT", st)]
    ev = compute_session_events(_sess(date(2026, 6, 1), sets),
                                laterality_by_template={},        # untagged
                                e1rm_by_template={"UNT": None})
    assert ev["mechanical"]["load"] == pytest.approx(1000.0)     # summed as logged
    assert ev["neuromuscular"]["provenance"]["indeterminate_laterality"] == ["UNT"]
    assert ev["mechanical"]["provenance"]["paired_templates"] == []


def test_bilateral_pair_summed_no_flags():
    st = {"weight_kg": 50.0, "reps": 10}
    sets = [(0, "BI", st), (1, "BI", st)]
    ev = compute_session_events(_sess(date(2026, 6, 1), sets),
                                laterality_by_template={"BI": "bilateral"},
                                e1rm_by_template={"BI": None})
    assert ev["mechanical"]["load"] == pytest.approx(1000.0)
    assert ev["mechanical"]["provenance"]["paired_templates"] == []
    assert ev["neuromuscular"]["provenance"]["indeterminate_laterality"] == []


def test_post_epoch_zero_rpe_artifact_signature():
    """Epoch's ONLY use: diagnostic. A post-epoch rep workout with no RPE → flagged.
    Same workout WITH an rpe, or the same zero-RPE workout PRE-epoch → NOT flagged
    (mutation-proof: the flag must key on both the epoch AND the RPE absence)."""
    zero = [(0, "T", {"weight_kg": 100.0, "reps": 5})]
    withrpe = [(0, "T", {"weight_kg": 100.0, "reps": 5, "rpe": 8.0})]

    post_zero = compute_session_events(_sess(date(2026, 6, 1), zero),
                                       laterality_by_template={}, e1rm_by_template={"T": None})
    post_rpe = compute_session_events(_sess(date(2026, 6, 1), withrpe),
                                      laterality_by_template={}, e1rm_by_template={"T": None})
    pre_zero = compute_session_events(_sess(date(2026, 4, 1), zero),
                                      laterality_by_template={}, e1rm_by_template={"T": None})
    assert post_zero["mechanical"]["provenance"]["post_epoch_zero_rpe"] is True
    assert post_rpe["mechanical"]["provenance"]["post_epoch_zero_rpe"] is False
    assert pre_zero["mechanical"]["provenance"]["post_epoch_zero_rpe"] is False
    # and the diagnostic changes no load
    assert post_zero["mechanical"]["load"] == pytest.approx(500.0)


# ── Orchestrator (DB) ─────────────────────────────────────────────────────────

def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _workout(db, hevy_id, uid, start_iso, exercises, excluded=False):
    dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if start_iso else None
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=dt,
        title="W", raw={"id": hevy_id, "exercises": exercises},
        excluded_at=datetime(2026, 8, 25, tzinfo=timezone.utc) if excluded else None,
    ))
    db.commit()


def _ex(tid, sets):
    return {"exercise_template_id": tid, "sets": sets}


def test_compute_writes_two_windows_per_session(db_session):
    _user(db_session)
    _workout(db_session, "w1", 1, "2026-06-01T10:00:00Z",
             [_ex("BENCH", [{"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0}])])
    summary = compute_load_events(db_session, 1)

    assert summary["sessions"] == 1 and summary["events_written"] == 2
    rows = db_session.query(models.LoadEvent).order_by(models.LoadEvent.window).all()
    windows = {r.window: r for r in rows}
    assert set(windows) == {"mechanical", "neuromuscular"}
    assert windows["mechanical"].load == pytest.approx(575.0)
    assert windows["mechanical"].formula_version == FORMULA_VERSION
    assert windows["mechanical"].source == "hevy" and windows["mechanical"].source_ref == "w1"
    # its own post-epoch top set fits the e1RM → h(I) used a real fit
    assert windows["neuromuscular"].provenance["e1rm_fit_templates"] == ["BENCH"]
    assert summary["sessions_with_e1rm_fit"] == 1


def test_excluded_workout_yields_no_events(db_session):
    _user(db_session)
    _workout(db_session, "keep", 1, "2026-06-01T10:00:00Z",
             [_ex("BENCH", [{"weight_kg": 100.0, "reps": 5}])])
    _workout(db_session, "drop", 1, "2026-06-02T10:00:00Z",
             [_ex("BENCH", [{"weight_kg": 100.0, "reps": 5}])], excluded=True)
    compute_load_events(db_session, 1)
    refs = {r.source_ref for r in db_session.query(models.LoadEvent).all()}
    assert refs == {"keep"}                     # excluded (D-G) never enters load


def test_recompute_is_idempotent(db_session):
    _user(db_session)
    _workout(db_session, "w1", 1, "2026-06-01T10:00:00Z",
             [_ex("BENCH", [{"weight_kg": 100.0, "reps": 5, "rpe": 8.0}])])
    compute_load_events(db_session, 1)
    first = {(r.window, r.load) for r in db_session.query(models.LoadEvent).all()}
    compute_load_events(db_session, 1)          # re-run
    second_rows = db_session.query(models.LoadEvent).all()
    assert len(second_rows) == 2                # not appended
    assert {(r.window, r.load) for r in second_rows} == first


def test_other_formula_version_coexists(db_session):
    _user(db_session)
    _workout(db_session, "w1", 1, "2026-06-01T10:00:00Z",
             [_ex("BENCH", [{"weight_kg": 100.0, "reps": 5}])])
    # a landed row from a different (older) formula version
    db_session.add(models.LoadEvent(
        user_id=1, source="hevy", source_ref="w1", window="mechanical",
        occurred_at=None, load=1.0, unit="kg_reps", formula_version="tier0-v0",
    ))
    db_session.commit()
    compute_load_events(db_session, 1)          # recompute tier0-v1 only
    v0 = db_session.query(models.LoadEvent).filter_by(formula_version="tier0-v0").all()
    assert len(v0) == 1 and v0[0].load == 1.0   # untouched


def test_indeterminate_laterality_surfaced_in_summary(db_session):
    _user(db_session)
    _workout(db_session, "w1", 1, "2026-06-01T10:00:00Z", [
        _ex("UNT", [{"weight_kg": 50.0, "reps": 10}]),
        _ex("UNT", [{"weight_kg": 50.0, "reps": 10}]),   # untagged, 2 blocks
    ])
    summary = compute_load_events(db_session, 1)
    assert summary["sessions_indeterminate_laterality"] == 1
    mech = db_session.query(models.LoadEvent).filter_by(window="mechanical").one()
    assert mech.load == pytest.approx(1000.0)            # not halved
    assert mech.provenance["indeterminate_laterality"] == ["UNT"]
