"""Read-time cross-source aerobic arbitration + exerciseType mapping.

Gates (brief):
  G2 — real Polar + fixture HC overlapping the same bout -> exactly one
       canonical, and it is the Polar row.
  G3 — an HC session with no overlapping Polar counterpart -> canonical true.
       (The load-bearing requirement: active-recovery HC bouts must survive.)
  G4 — an unmapped exerciseType -> sport_name None, no exception.
"""
from datetime import date, datetime, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from routers import polar
from routers.health_connect import ExerciseSessionType, sport_name_for
from reads.aerobic_reads import OVERLAP_THRESHOLD, arbitrate, arbitrated_sessions


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _session(source, start, stop, *, sid=None, day=None):
    """An unattached AerobicSession — enough for the pure arbitrate() path."""
    return models.AerobicSession(
        id=sid,
        user_id=1,
        source=source,
        session_date=day or start.date(),
        start_time=start,
        stop_time=stop,
    )


# ---------- G4 + enum contract: exerciseType mapping ----------

def test_exercise_session_type_contract_pins_known_codes():
    # Lock the wire contract against accidental edits (values feed HCA's
    # generated constants). Spot-check anchors + the exact defined count.
    assert ExerciseSessionType.OTHER_WORKOUT == 0
    assert ExerciseSessionType.RUNNING == 56
    assert ExerciseSessionType.STRENGTH_TRAINING == 70
    assert ExerciseSessionType.YOGA == 83
    assert len(ExerciseSessionType) == 61
    # Gaps are unassigned upstream and MUST stay unassigned.
    defined = {m.value for m in ExerciseSessionType}
    for gap in (1, 3, 6, 7, 12, 15, 30, 45, 49, 67, 77):
        assert gap not in defined


def test_sport_name_for_maps_known_codes():
    assert sport_name_for(56) == "Running"
    assert sport_name_for(57) == "Running Treadmill"
    assert sport_name_for(0) == "Other Workout"
    assert sport_name_for(36) == "High Intensity Interval Training"


def test_sport_name_for_unmapped_is_none_no_exception():  # G4
    assert sport_name_for(999) is None      # beyond the defined range
    assert sport_name_for(1) is None        # an unassigned gap
    assert sport_name_for(None) is None     # missing exerciseType


# ---------- G2: Polar + HC same bout -> one canonical, the Polar one ----------

def test_g2_polar_and_hc_overlap_exactly_one_canonical_polar():
    polar = _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), sid=1)
    hc = _session("health_connect", _utc(2026, 8, 1, 6, 5), _utc(2026, 8, 1, 6, 55), sid=2)
    arbitrate([polar, hc])
    canonical = [s for s in (polar, hc) if s.canonical]
    assert len(canonical) == 1
    assert canonical[0] is polar
    assert hc.canonical is False


def test_g2_holds_via_db_read(db_session):
    db_session.add_all([
        _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0)),
        _session("health_connect", _utc(2026, 8, 1, 6, 5), _utc(2026, 8, 1, 6, 55)),
    ])
    db_session.commit()
    rows = arbitrated_sessions(1, db_session)
    canonical = [r for r in rows if r.canonical]
    assert len(canonical) == 1
    assert canonical[0].source == "polar_v4"


# ---------- G3: HC with no overlapping Polar counterpart is canonical ----------

def test_g3_lone_hc_session_is_canonical():
    hc = _session("health_connect", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 6, 30), sid=1)
    arbitrate([hc])
    assert hc.canonical is True


def test_g3_hc_active_recovery_survives_alongside_unrelated_polar():
    # HC morning walk; Polar evening run same day but non-overlapping. Both real.
    hc = _session("health_connect", _utc(2026, 8, 1, 7, 0), _utc(2026, 8, 1, 7, 40), sid=1)
    polar = _session("polar_v4", _utc(2026, 8, 1, 17, 0), _utc(2026, 8, 1, 18, 0), sid=2)
    arbitrate([hc, polar])
    assert hc.canonical is True
    assert polar.canonical is True


def test_g3_holds_via_db_read(db_session):
    db_session.add(_session("health_connect", _utc(2026, 8, 2, 6, 0), _utc(2026, 8, 2, 6, 30)))
    db_session.commit()
    rows = arbitrated_sessions(1, db_session)
    assert len(rows) == 1
    assert rows[0].canonical is True


# ---------- overlap threshold ----------

def test_below_threshold_is_not_same_bout_both_canonical():
    # 60-min sessions overlapping only 10 min: 10/60 = 0.167 < 0.50.
    polar = _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), sid=1)
    hc = _session("health_connect", _utc(2026, 8, 1, 6, 50), _utc(2026, 8, 1, 7, 50), sid=2)
    arbitrate([polar, hc])
    assert polar.canonical is True
    assert hc.canonical is True


def test_at_threshold_is_same_bout_hc_suppressed():
    # Overlap exactly 30 of 60 min = 0.50 (>= threshold).
    assert OVERLAP_THRESHOLD == 0.50
    polar = _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), sid=1)
    hc = _session("health_connect", _utc(2026, 8, 1, 6, 30), _utc(2026, 8, 1, 7, 30), sid=2)
    arbitrate([polar, hc])
    assert polar.canonical is True
    assert hc.canonical is False


# ---------- tie-breaks (equal rank: the two Polar transports) ----------

def test_tie_same_rank_longest_duration_wins():
    short = _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 6, 40), sid=1)
    long = _session("polar_flow_export", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), sid=2)
    arbitrate([short, long])
    assert long.canonical is True
    assert short.canonical is False


def test_tie_equal_duration_earliest_start_wins():
    early = _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), sid=1)
    late = _session("polar_flow_export", _utc(2026, 8, 1, 6, 10), _utc(2026, 8, 1, 7, 10), sid=2)
    arbitrate([early, late])
    assert early.canonical is True
    assert late.canonical is False


# ---------- degenerate rows ----------

# ---------- HTTP layer: canonical round-trips through the response model ----------

def test_aerobic_sessions_endpoint_serializes_canonical(db_session):
    """Drive the route so AerobicSessionOut serializes the derived (non-mapped)
    `canonical` attribute — the one seam the pure/DB tests above don't cover."""
    user = models.User(email="luke@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add_all([
        _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), day=date(2026, 8, 1)),
        _session("health_connect", _utc(2026, 8, 1, 6, 5), _utc(2026, 8, 1, 6, 55), day=date(2026, 8, 1)),
    ])
    for row in db_session.query(models.AerobicSession).all():
        row.user_id = user.id
    db_session.commit()

    app = FastAPI()
    app.include_router(polar.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    resp = TestClient(app).get("/integrations/polar/aerobic-sessions")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    by_source = {r["source"]: r["canonical"] for r in body}
    assert by_source["polar_v4"] is True
    assert by_source["health_connect"] is False


def test_session_missing_interval_is_canonical():
    # A row with no start/stop cannot be paired -> canonical by default.
    partial = models.AerobicSession(
        id=1, user_id=1, source="health_connect",
        session_date=date(2026, 8, 1), start_time=None, stop_time=None,
    )
    polar = _session("polar_v4", _utc(2026, 8, 1, 6, 0), _utc(2026, 8, 1, 7, 0), sid=2)
    arbitrate([partial, polar])
    assert partial.canonical is True
    assert polar.canonical is True
