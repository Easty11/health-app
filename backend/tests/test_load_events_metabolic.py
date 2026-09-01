"""Metabolic (aerobic) load transform — Edwards zone-weighted TRIMP → load_events (S1).

Gate coverage (design authority §10 S1):
  * G1 fixture: known zone seconds → exact Edwards sum (deterministic, mutation-proofed);
  * G2 fail-closed (INV-7): all zones NULL/zero → zero rows, skip counted;
  * G3 idempotency: double-run → identical row set (natural key holds);
  * G4 isolation: recompute leaves `tier0-v1` strength rows byte-identical.
"""
from datetime import date, datetime, timezone

import pytest

import models
import load_events_metabolic as lem
from load_events_metabolic import (
    EDWARDS_WEIGHTS,
    FORMULA_VERSION_METABOLIC,
    UNIT_METABOLIC,
    WINDOW_METABOLIC,
    compute_metabolic_load,
    compute_metabolic_load_events,
    edwards_trimp,
)

APPROX = 1e-6


# ── Edwards weights (mutation-proofed: each zone maps to its own weight) ─────────

@pytest.mark.parametrize("z,w", [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)])
def test_edwards_weights_table(z, w):
    assert EDWARDS_WEIGHTS[z] == w


# ── G1: exact Edwards sum ───────────────────────────────────────────────────────

def test_edwards_trimp_known_zones_exact():
    """z1 600s(=10min×1), z2 300s(=5min×2), z5 120s(=2min×5) → 10 + 10 + 10 = 30.
    Mutation-proof: a flat (unweighted) sum would give 10+5+2 = 17, not 30."""
    trimp = edwards_trimp({1: 600, 2: 300, 3: None, 4: None, 5: 120})
    assert trimp == pytest.approx(30.0, abs=APPROX)


def test_edwards_trimp_single_zone():
    """900s in z3 = 15 min × 3 = 45."""
    assert edwards_trimp({3: 900}) == pytest.approx(45.0, abs=APPROX)


def test_null_zone_contributes_zero_not_imputed():
    assert edwards_trimp({1: 600, 2: None, 3: None, 4: None, 5: None}) == pytest.approx(10.0, abs=APPROX)


def test_compute_metabolic_load_qualifies_and_records_zones():
    ml = compute_metabolic_load({1: 600, 2: 300, 3: None, 4: None, 5: 120})
    assert ml.qualifying is True
    assert ml.trimp == pytest.approx(30.0, abs=APPROX)
    assert ml.zone_seconds == {1: 600, 2: 300, 5: 120}   # only non-NULL zones


# ── G2: fail-closed (INV-7) ─────────────────────────────────────────────────────

def test_all_zones_null_is_non_qualifying():
    ml = compute_metabolic_load({1: None, 2: None, 3: None, 4: None, 5: None})
    assert ml.qualifying is False
    assert ml.trimp == pytest.approx(0.0, abs=APPROX)


def test_all_zones_zero_is_non_qualifying():
    ml = compute_metabolic_load({1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
    assert ml.qualifying is False
    assert ml.trimp == pytest.approx(0.0, abs=APPROX)


# ── Correlation helper (convergent-sanity only) ─────────────────────────────────

def test_pearson_none_below_two_pairs_and_constant_series():
    assert lem._pearson([]) is None
    assert lem._pearson([(1.0, 2.0)]) is None
    assert lem._pearson([(1.0, 5.0), (2.0, 5.0)]) is None   # constant y
    assert lem._pearson([(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]) == pytest.approx(1.0, abs=APPROX)


# ── Orchestrator (DB) ───────────────────────────────────────────────────────────

def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _aerobic(db, uid, sid, session_date, zones, *, source="polar_flow_export",
             start_time=None, stop_time=None, cardio_load=None, sport_name="Running", hr_avg=None):
    z = dict(zip((1, 2, 3, 4, 5), zones))
    db.add(models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, session_date=session_date,
        start_time=start_time, stop_time=stop_time, sport_name=sport_name, hr_avg=hr_avg,
        cardio_load=cardio_load,
        z1_seconds=z[1], z2_seconds=z[2], z3_seconds=z[3], z4_seconds=z[4], z5_seconds=z[5],
    ))
    db.commit()


def test_compute_writes_one_metabolic_row_per_qualifying_session(db_session):
    _user(db_session)
    _aerobic(db_session, 1, "p1", date(2026, 6, 1), (600, 300, None, None, 120),
             start_time=datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc),
             cardio_load=42.0, hr_avg=150)
    summary = compute_metabolic_load_events(db_session, 1)

    assert summary["sessions"] == 1 and summary["events_written"] == 1
    assert summary["sessions_skipped_no_zones"] == 0
    row = db_session.query(models.LoadEvent).one()
    assert row.load_window == WINDOW_METABOLIC
    assert row.load == pytest.approx(30.0, abs=APPROX)
    assert row.unit == UNIT_METABOLIC
    assert row.formula_version == FORMULA_VERSION_METABOLIC
    assert row.source == "aerobic_sessions"
    assert row.source_ref == str(db_session.query(models.AerobicSession).one().id)
    # SQLite round-trips DateTime as naive; assert the wall-clock (start_time passed through).
    assert row.occurred_at.replace(tzinfo=None) == datetime(2026, 6, 1, 6, 0)
    # AerobicSession.z*_seconds default to 0, so unset zones round-trip as 0 (not NULL);
    # they contribute nothing to TRIMP but appear in the diagnostic blob.
    assert row.provenance["zone_seconds"] == {"1": 600, "2": 300, "3": 0, "4": 0, "5": 120}
    assert row.provenance["zone_source"] == "polar_flow_export"
    assert row.provenance["had_hr_avg"] is True
    assert row.provenance["sport_name"] == "Running"


def test_occurred_at_falls_back_to_session_date_midnight_utc(db_session):
    """No start_time → UTC-midnight of session_date (feeds the rollup, which drops NULLs)."""
    _user(db_session)
    _aerobic(db_session, 1, "p1", date(2026, 6, 2), (600, None, None, None, None), start_time=None)
    compute_metabolic_load_events(db_session, 1)
    row = db_session.query(models.LoadEvent).one()
    # SQLite round-trips DateTime as naive; the fallback anchors to UTC-midnight of the day.
    assert row.occurred_at.replace(tzinfo=None) == datetime(2026, 6, 2, 0, 0)


def test_g2_non_qualifying_sessions_emit_no_row_but_are_counted(db_session):
    _user(db_session)
    _aerobic(db_session, 1, "allnull", date(2026, 6, 1), (None, None, None, None, None))
    _aerobic(db_session, 1, "allzero", date(2026, 6, 2), (0, 0, 0, 0, 0))
    _aerobic(db_session, 1, "good", date(2026, 6, 3), (600, None, None, None, None))
    summary = compute_metabolic_load_events(db_session, 1)
    assert summary["events_written"] == 1
    assert summary["sessions_skipped_no_zones"] == 2
    assert db_session.query(models.LoadEvent).count() == 1


def test_g3_recompute_is_idempotent(db_session):
    _user(db_session)
    _aerobic(db_session, 1, "p1", date(2026, 6, 1), (600, 300, None, None, 120))
    _aerobic(db_session, 1, "p2", date(2026, 6, 2), (None, None, 900, None, None))
    compute_metabolic_load_events(db_session, 1)
    first = {(r.source_ref, r.load) for r in db_session.query(models.LoadEvent).all()}
    compute_metabolic_load_events(db_session, 1)              # re-run
    rows = db_session.query(models.LoadEvent).all()
    assert len(rows) == 2                                     # not appended
    assert {(r.source_ref, r.load) for r in rows} == first


def test_g4_recompute_leaves_tier0_strength_rows_untouched(db_session):
    """Isolation: a landed strength (`tier0-v1`) row survives a Metabolic recompute
    byte-identical — delete-and-reinsert is scoped to `metab-v1` only."""
    _user(db_session)
    db_session.add(models.LoadEvent(
        user_id=1, source="hevy", source_ref="w1", load_window="mechanical",
        occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc), load=575.0,
        unit="kg_reps", formula_version="tier0-v1",
    ))
    db_session.commit()
    _aerobic(db_session, 1, "p1", date(2026, 6, 1), (600, None, None, None, None))
    compute_metabolic_load_events(db_session, 1)

    strength = db_session.query(models.LoadEvent).filter_by(formula_version="tier0-v1").all()
    assert len(strength) == 1
    assert strength[0].load == 575.0 and strength[0].load_window == "mechanical"
    assert strength[0].source == "hevy" and strength[0].source_ref == "w1"
    # and the Metabolic row landed alongside it
    assert db_session.query(models.LoadEvent).filter_by(
        formula_version=FORMULA_VERSION_METABOLIC).count() == 1


def test_correlation_pairs_collected_only_where_cardio_load_present(db_session):
    _user(db_session)
    _aerobic(db_session, 1, "p1", date(2026, 6, 1), (600, None, None, None, None), cardio_load=10.0)
    _aerobic(db_session, 1, "p2", date(2026, 6, 2), (1200, None, None, None, None), cardio_load=20.0)
    _aerobic(db_session, 1, "p3", date(2026, 6, 3), (1800, None, None, None, None), cardio_load=None)
    summary = compute_metabolic_load_events(db_session, 1)
    assert summary["events_written"] == 3
    assert summary["cardio_load_pairs"] == 2
    assert summary["trimp_cardio_load_pearson_r"] == pytest.approx(1.0, abs=APPROX)


# ── Arbitration routing (#260/Q127): emit only the canonical row per bout ────────

def test_v4_flow_export_twin_is_noop_zoned_row_emits(db_session):
    """The v4/flow_export twin case is a no-op on output: the zoneless v4 row
    self-skips today (INV-7) and is non-canonical tomorrow (flow_export outranks
    it); the SAME zoned flow_export row emits either way. Exactly one row, from the
    flow_export twin. v4 is inserted first so it holds the LOWER id — the ingest
    order that, under the old equal-rank tie, made the zoneless v4 canonical and
    dropped the bout."""
    _user(db_session)
    start = datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc)
    stop = datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc)
    # v4 twin: zoneless (list endpoint omits zones), lower id (synced first).
    _aerobic(db_session, 1, "bout1", date(2026, 6, 1), (None, None, None, None, None),
             source="polar_v4", start_time=start, stop_time=stop)
    # flow_export twin: same bout, carries zones.
    _aerobic(db_session, 1, "bout1", date(2026, 6, 1), (600, 300, None, None, 120),
             source="polar_flow_export", start_time=start, stop_time=stop)

    summary = compute_metabolic_load_events(db_session, 1)

    assert summary["sessions"] == 2
    assert summary["events_written"] == 1
    assert summary["sessions_skipped_non_canonical"] == 1   # the zoneless v4 twin
    assert summary["sessions_skipped_no_zones"] == 0        # never reached for v4
    row = db_session.query(models.LoadEvent).one()
    assert row.provenance["zone_source"] == "polar_flow_export"
    assert row.load == pytest.approx(30.0, abs=APPROX)


def test_zoned_cross_source_overlap_collapses_to_one_emission(db_session):
    """The one intended output change: two ZONED cross-source rows for the same
    bout (synthetic Polar-vs-HC, both carrying zones) collapse from two emissions
    to one — a correction. Arbitration keeps the higher-rank flow_export row
    canonical; the HC twin is skipped as non-canonical. Before arbitration routing
    both qualified and both emitted (a double-count in every window the bout
    touched)."""
    _user(db_session)
    start = datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc)
    stop = datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc)
    _aerobic(db_session, 1, "hc1", date(2026, 6, 1), (600, 300, None, None, 120),
             source="health_connect", start_time=start, stop_time=stop)
    _aerobic(db_session, 1, "fe1", date(2026, 6, 1), (600, 300, None, None, 120),
             source="polar_flow_export", start_time=start, stop_time=stop)

    summary = compute_metabolic_load_events(db_session, 1)

    assert summary["sessions"] == 2
    assert summary["events_written"] == 1
    assert summary["sessions_skipped_non_canonical"] == 1
    row = db_session.query(models.LoadEvent).one()
    assert row.provenance["zone_source"] == "polar_flow_export"


def test_non_overlapping_zoned_sessions_both_emit(db_session):
    """Guard the correction's blast radius: two zoned sessions that do NOT overlap
    (different bouts) are both canonical and both emit — arbitration only collapses
    genuine same-bout clusters, never distinct sessions on the same day."""
    _user(db_session)
    _aerobic(db_session, 1, "am", date(2026, 6, 1), (600, None, None, None, None),
             source="polar_flow_export",
             start_time=datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc),
             stop_time=datetime(2026, 6, 1, 7, 0, tzinfo=timezone.utc))
    _aerobic(db_session, 1, "pm", date(2026, 6, 1), (900, None, None, None, None),
             source="health_connect",
             start_time=datetime(2026, 6, 1, 17, 0, tzinfo=timezone.utc),
             stop_time=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc))

    summary = compute_metabolic_load_events(db_session, 1)

    assert summary["events_written"] == 2
    assert summary["sessions_skipped_non_canonical"] == 0


def test_only_this_users_sessions_are_transformed(db_session):
    _user(db_session, 1)
    _user(db_session, 2)
    _aerobic(db_session, 1, "p1", date(2026, 6, 1), (600, None, None, None, None))
    _aerobic(db_session, 2, "p2", date(2026, 6, 1), (600, None, None, None, None))
    compute_metabolic_load_events(db_session, 1)
    rows = db_session.query(models.LoadEvent).all()
    assert len(rows) == 1 and rows[0].user_id == 1
