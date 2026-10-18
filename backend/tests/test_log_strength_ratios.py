"""Route (i) and (ii) for ratios (Q27 v1): log-derived strength per side, same-day pairing, baseline /
current / change, and the observed ratio. Everything here is a READ.

Fixtures reuse the See-test helpers (`test_series_exercise`) so route (i) is shown to read the SAME
sets the per-exercise series reads: same Epley, same rep cap, same working-set rule.
"""
import json
from datetime import timedelta

import pytest
from fastapi import HTTPException

import mcp_server
import models
from engine import log_strength, ratios
from engine import observations as obs
from reads import strength_reads
from routers import series
from routers.engine import get_log_strength, get_ratio, get_ratios

from test_capability_observations import _FORBIDDEN_VERDICT
from test_series_exercise import _today, _user, _template, _workout, _ws

# Template ids
ER_L, ER_R, ER_B = "er-left", "er-right", "er-bilat"
IR_L, IR_R = "ir-left", "ir-right"
ADD_M, ABD_M, COP_L, COP_R = "add-machine", "abd-machine", "cop-left", "cop-right"


def _tag(db, tid, region, side=None, role="primary"):
    if db.get(models.HevyExerciseTemplate, tid) is None:
        _template(db, tid, tid)
    db.add(models.ExerciseRegionTag(hevy_exercise_template_id=tid, region_key=region,
                                    role=role, side=side))
    db.commit()


def _log(db, uid, offset, tid, sets):
    """One workout `offset` days ago holding one block."""
    _workout(db, user_id=uid, day=_today() + timedelta(days=offset), blocks=[(tid, sets)],
             hevy_id=f"w-{uid}-{tid}-{offset}")


def _one_rep(weight):
    """A 1-rep set: Epley factor (1 + 1/30) is the same on both halves, so ratios cancel exactly."""
    return [_ws(weight, 1)]


def _shoulder_setup(db):
    u = _user(db, "ls@example.com")
    for tid, region, side in ((ER_L, "shoulder_er", "left"), (ER_R, "shoulder_er", "right"),
                              (IR_L, "shoulder_ir", "left"), (IR_R, "shoulder_ir", "right")):
        _tag(db, tid, region, side)
    return u


# ── one helper, not a copy (FEEDBACK 39) ─────────────────────────────────────

def test_the_strength_primitives_are_one_shared_helper():
    assert series._aggregate_session is strength_reads.aggregate_session
    assert series._epley_e1rm is strength_reads.epley_e1rm
    assert series._is_working_set is strength_reads.is_working_set
    assert series._session_days_by_template is strength_reads.session_days_by_template
    assert series._title_map is strength_reads.title_map
    assert series._EPLEY_REP_CAP == strength_reads.EPLEY_REP_CAP == 10
    assert log_strength.strength_reads is strength_reads         # route (i) reaches them through it


# ── e1rm_by_side ─────────────────────────────────────────────────────────────

def test_sides_come_from_the_declared_column_and_null_reads_as_bilateral(db_session):
    u = _user(db_session, "sides@example.com")
    _tag(db_session, ER_L, "shoulder_er", "left")
    _tag(db_session, ER_R, "shoulder_er", "right")
    _tag(db_session, ER_B, "shoulder_er", None)
    for tid, w in ((ER_L, 10), (ER_R, 20), (ER_B, 30)):
        _log(db_session, u.id, -3, tid, _one_rep(w))
    out = log_strength.e1rm_by_side(db_session, u.id, "shoulder_er")
    assert set(out) == {"left", "right", "bilateral"}
    assert out["left"][0]["e1rm_kg"] == pytest.approx(10 * (1 + 1 / 30))
    assert out["right"][0]["template_id"] == ER_R
    assert out["bilateral"][0]["e1rm_kg"] == pytest.approx(30 * (1 + 1 / 30))


def test_the_title_is_never_used_to_infer_a_side(db_session):
    """A template titled '... L' with no declared side is bilateral: no title stripping."""
    u = _user(db_session, "title@example.com")
    _template(db_session, "named-l", "Shoulder External Rotation L")
    _tag(db_session, "named-l", "shoulder_er", None)
    _log(db_session, u.id, -2, "named-l", _one_rep(10))
    assert set(log_strength.e1rm_by_side(db_session, u.id, "shoulder_er")) == {"bilateral"}


def test_only_primary_tags_count(db_session):
    u = _user(db_session, "primary@example.com")
    _tag(db_session, ER_L, "shoulder_er", "left", role="secondary")
    _log(db_session, u.id, -2, ER_L, _one_rep(10))
    assert log_strength.e1rm_by_side(db_session, u.id, "shoulder_er") == {}


def test_a_session_day_takes_the_best_template_for_that_side(db_session):
    u = _user(db_session, "best@example.com")
    _tag(db_session, "er-a", "shoulder_er", "left")
    _tag(db_session, "er-b", "shoulder_er", "left")
    _workout(db_session, user_id=u.id, day=_today() - timedelta(days=4),
             blocks=[("er-a", _one_rep(10)), ("er-b", _one_rep(15))], hevy_id="w-best")
    pts = log_strength.e1rm_by_side(db_session, u.id, "shoulder_er")["left"]
    assert len(pts) == 1 and pts[0]["template_id"] == "er-b"


def test_warmups_and_reps_over_the_cap_are_excluded_exactly_as_the_series_excludes_them(db_session):
    u = _user(db_session, "rules@example.com")
    _tag(db_session, ER_L, "shoulder_er", "left")
    _log(db_session, u.id, -9, ER_L, [_ws(100, 3, "warmup")])                  # warm-up only -> no point
    _log(db_session, u.id, -8, ER_L, [_ws(50, 12)])                           # reps > 10 -> no e1RM
    _log(db_session, u.id, -7, ER_L, [_ws(100, 5, "warmup"), _ws(20, 5)])     # warm-up ignored
    pts = log_strength.e1rm_by_side(db_session, u.id, "shoulder_er")["left"]
    assert [p["day"] for p in pts] == [_today() - timedelta(days=7)]
    assert pts[0]["e1rm_kg"] == pytest.approx(20 * (1 + 5 / 30))
    assert pts[0]["top_set"] == {"weight_kg": 20.0, "reps": 5}
    # and it is the series' own number for the same sets
    agg = series._aggregate_session([_ws(100, 5, "warmup"), _ws(20, 5)])
    assert agg["e1rm_kg"] == pytest.approx(pts[0]["e1rm_kg"])


def test_symmetry_per_day_is_a_ratio_and_a_lower_side_only(db_session):
    u = _shoulder_setup(db_session)
    _log(db_session, u.id, -5, ER_L, _one_rep(20))
    _log(db_session, u.id, -5, ER_R, _one_rep(25))
    _log(db_session, u.id, -3, ER_L, _one_rep(22))                  # no right that day
    sym = log_strength.symmetry_by_day(log_strength.e1rm_by_side(db_session, u.id, "shoulder_er"))
    assert len(sym) == 1
    assert sym[0]["index_pct"] == 80.0 and sym[0]["lower_side"] == "left"
    assert set(sym[0]) == {"day", "left_e1rm_kg", "right_e1rm_kg", "index_pct", "lower_side"}


# ── route (i) ratios ─────────────────────────────────────────────────────────

def _pair_days(db, uid, offsets, er_weights, ir_weight=20):
    for off, w in zip(offsets, er_weights):
        _log(db, uid, off, ER_L, _one_rep(w))
        _log(db, uid, off, IR_L, _one_rep(ir_weight))


def test_pairing_is_same_day_only_and_unpaired_days_are_counted(db_session):
    u = _shoulder_setup(db_session)
    for off in (-10, -8, -6):
        _log(db_session, u.id, off, ER_L, _one_rep(15))
    for off in (-10, -8, -4):
        _log(db_session, u.id, off, IR_L, _one_rep(20))
    left = ratios.log_derived(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["n_pairs"] == 2 and left["unpaired_days"] == 2           # -6 (ER only), -4 (IR only)
    assert [p["day"] for p in left["pairs"]] == [str(_today() + timedelta(days=d)) for d in (-10, -8)]
    assert left["pairs"][0]["ratio"] == pytest.approx(0.75)


def test_baseline_current_and_change_are_the_briefed_arithmetic(db_session):
    u = _shoulder_setup(db_session)
    _pair_days(db_session, u.id, (-30, -25, -20, -15, -10, -5), (10, 12, 15, 20, 24, 30))
    left = ratios.log_derived(db_session, u.id, "er_ir")["sides"]["left"]
    assert [round(p["ratio"], 6) for p in left["pairs"]] == [0.5, 0.6, 0.75, 1.0, 1.2, 1.5]
    assert left["baseline"] == pytest.approx(0.6)       # median of the first three: 0.5, 0.6, 0.75
    assert left["current"] == pytest.approx(1.2)        # median of the last three: 1.0, 1.2, 1.5
    assert left["delta_pct"] == pytest.approx(100.0)
    assert left["reference"] == {"governing": "internal",
                                 "reason": "log-derived (cable/machine); no norm shares the instrument"}
    assert set(left) == {"pairs", "n_pairs", "unpaired_days", "baseline", "baseline_days", "current",
                         "current_days", "delta_pct", "reference"}       # no label, band or threshold


def test_under_three_pairs_has_no_baseline_no_current_no_change(db_session):
    u = _shoulder_setup(db_session)
    _pair_days(db_session, u.id, (-9, -4), (10, 12))
    left = ratios.log_derived(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["n_pairs"] == 2
    assert left["baseline"] is None and left["current"] is None and left["delta_pct"] is None


def test_current_is_null_when_fewer_than_three_pairs_are_within_42_days(db_session):
    u = _shoulder_setup(db_session)
    _pair_days(db_session, u.id, (-100, -90, -80, -43), (10, 12, 15, 20))        # all older than 42 days
    left = ratios.log_derived(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["baseline"] == pytest.approx(0.6) and left["current"] is None and left["delta_pct"] is None
    # two recent pairs are still not three
    _pair_days(db_session, u.id, (-10, -5), (24, 30))
    left = ratios.log_derived(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["current"] is None
    # the 42-day edge is inclusive: a pair exactly 42 days old is current
    _pair_days(db_session, u.id, (-42,), (24,))
    left = ratios.log_derived(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["current"] is not None and str(_today() - timedelta(days=42)) in left["current_days"]


def test_bilateral_machines_pair_as_bilateral_and_a_sided_exposure_is_not_mixed_in(db_session):
    u = _user(db_session, "hip@example.com")
    _tag(db_session, ADD_M, "hip_adduction", None)
    _tag(db_session, ABD_M, "hip_abduction", None)
    _tag(db_session, COP_L, "hip_adduction", "left")                  # exposure, side-declared
    _tag(db_session, COP_R, "hip_adduction", "right")
    for off in (-6, -4, -2):
        _log(db_session, u.id, off, ADD_M, _one_rep(30))
        _log(db_session, u.id, off, ABD_M, _one_rep(25))
    _log(db_session, u.id, -2, COP_L, _one_rep(10))
    _log(db_session, u.id, -2, COP_R, _one_rep(10))
    out = ratios.log_derived(db_session, u.id, "add_abd")
    assert set(out["sides"]) == {"bilateral"}
    assert out["sides"]["bilateral"]["n_pairs"] == 3
    assert out["sides"]["bilateral"]["pairs"][0]["ratio"] == pytest.approx(1.2)
    assert out["unmatched_sides"] == {"numerator_only": ["left", "right"], "denominator_only": []}


def test_sides_are_never_mixed(db_session):
    u = _shoulder_setup(db_session)
    _tag(db_session, "ir-bilat", "shoulder_ir", None)
    for off in (-5, -3, -1):
        _log(db_session, u.id, off, ER_L, _one_rep(15))
        _log(db_session, u.id, off, "ir-bilat", _one_rep(20))
    out = ratios.log_derived(db_session, u.id, "er_ir")
    assert out["sides"] == {}
    assert out["unmatched_sides"] == {"numerator_only": ["left"], "denominator_only": ["bilateral"]}


def test_route_i_writes_nothing(db_session):
    u = _shoulder_setup(db_session)
    _pair_days(db_session, u.id, (-9, -6, -3), (10, 12, 15))
    ratios.log_derived(db_session, u.id, "er_ir")
    ratios.all_ratio_overviews(db_session, u.id)
    log_strength.log_strength_as_dict(db_session, u.id, "shoulder_er")
    assert db_session.query(models.CapabilityObservation).count() == 0


# ── route (ii) observed ratio ────────────────────────────────────────────────

P = "hhd_shoulder_rot_seated_neutral_make"
Q = "hhd_shoulder_rot_prone_90_90_make"


def _obs(db, uid, region, value, offset, protocol=P, side="left", prov=True):
    kw = dict(administered_by="ep", instrument="hhd", protocol=protocol) if prov else {}
    return obs.record_observation(
        db, uid, region_key=region, measure_key="hhd_force_n", value=value, side=side,
        observed_on=_today() + timedelta(days=offset), method="manual", source="manual", **kw)


def test_observed_pairs_the_latest_numerator_with_a_same_protocol_denominator_within_14_days(db_session):
    u = _user(db_session, "obsr@example.com")
    _obs(db_session, u.id, "shoulder_er", 100, -60)
    _obs(db_session, u.id, "shoulder_ir", 120, -58)
    _obs(db_session, u.id, "shoulder_er", 130, -5)
    _obs(db_session, u.id, "shoulder_ir", 140, -3)
    left = ratios.observed(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["ratio"] == pytest.approx(130 / 140)
    assert left["days_apart"] == 2 and left["protocol"] == P
    assert left["reference"]["governing"] == "literature"
    assert left["reference"]["band"]["id"] == "riemann2010_er_ir_hhd"


def test_observed_will_not_join_two_clinic_visits_or_two_protocols(db_session):
    u = _user(db_session, "obsr2@example.com")
    _obs(db_session, u.id, "shoulder_er", 130, -40)
    _obs(db_session, u.id, "shoulder_ir", 140, -10)                              # 30 days apart
    assert ratios.observed(db_session, u.id, "er_ir")["sides"] == {}
    v = _user(db_session, "obsr2b@example.com")
    _obs(db_session, v.id, "shoulder_er", 130, -5, protocol=P)
    _obs(db_session, v.id, "shoulder_ir", 140, -4, protocol=Q)                    # different protocol
    assert ratios.observed(db_session, v.id, "er_ir")["sides"] == {}


def test_observed_legacy_rows_still_give_a_ratio_but_it_is_internal(db_session):
    u = _user(db_session, "obsr3@example.com")
    _obs(db_session, u.id, "shoulder_er", 130, -5, prov=False)
    _obs(db_session, u.id, "shoulder_ir", 140, -4, prov=False)
    left = ratios.observed(db_session, u.id, "er_ir")["sides"]["left"]
    assert left["ratio"] == pytest.approx(130 / 140) and left["protocol"] is None
    assert left["reference"]["governing"] == "internal" and left["reference"]["reason"] == "no provenance"


# ── routes ───────────────────────────────────────────────────────────────────

class _Stub:
    def __init__(self, uid):
        self.id = uid


def test_the_routes_return_both_routes_and_refuse_unknown_keys(db_session):
    u = _shoulder_setup(db_session)
    _pair_days(db_session, u.id, (-9, -6, -3), (10, 12, 15))
    allr = get_ratios(current_user=_Stub(u.id), db=db_session)["ratios"]
    assert [r["ratio"]["key"] for r in allr] == ["er_ir", "add_abd"]
    one = get_ratio("er_ir", current_user=_Stub(u.id), db=db_session)
    assert set(one) == {"ratio", "log_derived", "observed"}
    assert one["log_derived"]["sides"]["left"]["n_pairs"] == 3
    ls = get_log_strength(region_key="shoulder_er", since=None, current_user=_Stub(u.id), db=db_session)
    assert set(ls["sides"]) == {"left"} and len(ls["sides"]["left"]) == 3
    for call in (lambda: get_ratio("h_q", current_user=_Stub(u.id), db=db_session),
                 lambda: get_log_strength(region_key="nope", since=None,
                                          current_user=_Stub(u.id), db=db_session)):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 422


# ── MCP ──────────────────────────────────────────────────────────────────────

def test_the_mcp_tool_renders_both_routes_and_no_verdict(db_session, monkeypatch):
    u = _shoulder_setup(db_session)
    _pair_days(db_session, u.id, (-30, -25, -20, -15, -10, -5), (10, 12, 15, 20, 24, 30))
    _obs(db_session, u.id, "shoulder_er", 130, -5)
    _obs(db_session, u.id, "shoulder_ir", 140, -4)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    out = mcp_server.get_capability_ratios()
    # positive controls: both routes, the arithmetic, the reference and the band all rendered
    for token in ("Shoulder ER:IR", "Route (i)", "Route (ii)", "baseline 0.600", "current 1.200",
                  "+100.0%", "reference: internal - log-derived", "reference: literature",
                  "0.86 to 0.99", "PMID 20850997", "Hip adductor:abductor"):
        assert token in out, token
    hit = _FORBIDDEN_VERDICT.search(out)
    assert hit is None, hit.group(0)
    low = out.lower()
    for word in ("deficit", "pass", "fail", "cleared", "grade ", "within normal", "abnormal"):
        assert word not in low.replace("no verdicts", ""), word


def test_the_mcp_tool_takes_no_parameters():
    import asyncio
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert tools["get_capability_ratios"].inputSchema["properties"] == {}
