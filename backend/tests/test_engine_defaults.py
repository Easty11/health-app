"""Engine-tier default proposals — "Engine blocks are rows" (Q182, GH#539), PR1.

What is pinned here:
  * every in-code map key seeds its regions, as PROPOSALS, one row per (injury, region key), in the
    D1 shape that `validate_constraint` accepts unchanged;
  * side: a sided injury → sided rows, a bilateral one → sideless rows;
  * D3: `pes anserine` reaches the knee set (Q102 entry 30); a cervical neural entry seeds NOTHING
    from the lumbar-shaped radicular set; an empty body part typed neural seeds it; RA-flare by
    flag or by restriction token;
  * the SUPERSET property — the seeded set never covers less than the live arms block, the one
    divergence being the documented cervical-spine case — which is what lets PR2 retire the arms;
  * idempotency across an active and a resolved twin, and across the operator's own rows;
  * the injury write path (chat and api) proposes, and only on a create or a change to
    body_part / side / signal_type / ra_flare; a failure to propose never loses the injury;
  * a proposal changes `is_contraindicated` and `compute_probe_queue` in nothing (G3), and a
    confirmed one does — so the test can see a leak;
  * V3: a declined proposal is stored with its resolution block and leaves /proposals.
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from engine import engine_defaults as ed
from engine import selection, taxonomy
from load_metrics import _local_day
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry, validate_constraint

REVIEW = date(2026, 12, 14)


def _inj(body_part, side="bilateral", signal_type="mechanical", ra_flare=False, restrictions=None):
    v = {"body_part": body_part, "side": side, "signal_type": signal_type}
    if ra_flare:
        v["ra_flare"] = True
    if restrictions is not None:
        v["restrictions"] = restrictions
    return v


def _regions(value):
    return {c["region_key"] for c in ed.candidate_regions(value)}


# ── every map key seeds its regions ───────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(selection._ACUTE_TISSUE_BLOCKS))
def test_every_acute_map_key_seeds_exactly_its_regions(key):
    assert _regions(_inj(key)) == set(selection._ACUTE_TISSUE_BLOCKS[key])


def test_radicular_and_ra_flare_seed_their_sets():
    assert _regions(_inj("lumbar", signal_type="neural")) == set(selection._RADICULAR_BLOCKS)
    assert _regions(_inj("lumbar", signal_type="radicular")) == set(selection._RADICULAR_BLOCKS)
    assert _regions(_inj("hand", ra_flare=True)) == set(selection._RA_FLARE_BLOCKS)


def test_ra_flare_by_restriction_token_is_the_same_as_the_flag():
    assert _regions(_inj("hand", restrictions=["ra_flare"])) == set(selection._RA_FLARE_BLOCKS)


def test_a_mechanical_lumbar_entry_seeds_nothing():
    """Ledger id 94, as stored (typed `mechanical` to route around the blocker, Q102): no arm fires
    for it today, and the honest default set is empty too — the type stops being load-bearing."""
    assert ed.candidate_regions(_inj("lumbar", signal_type="mechanical")) == []


def test_a_region_two_maps_imply_is_one_row_naming_both():
    cands = ed.candidate_regions(_inj("knee", ra_flare=True))
    by = {c["region_key"]: c["maps"] for c in cands}
    assert len([c for c in cands if c["region_key"] == "single_leg_hop"]) == 1
    assert by["single_leg_hop"] == ["RA-flare", "acute-tissue (knee)"]
    assert by["grip_strength"] == ["RA-flare"]


def test_candidates_are_in_taxonomy_order_and_all_real_regions():
    order = [r.key for r in taxonomy.all_regions()]
    keys = [c["region_key"] for c in ed.candidate_regions(_inj("lumbar", signal_type="neural", ra_flare=True))]
    assert keys == sorted(keys, key=order.index)
    assert all(taxonomy.by_key(k) is not None for k in keys)


# ── side ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("side", ["left", "right"])
def test_a_sided_injury_seeds_sided_rows(side):
    cands = ed.candidate_regions(_inj("shoulder", side=side))
    assert cands and {c["side"] for c in cands} == {side}
    value = ed.default_row_value("injury_x", cands[0], REVIEW)
    assert value["scope"]["side"] == side


@pytest.mark.parametrize("side", ["bilateral", "both", "", "l", "BILATERAL"])
def test_a_bilateral_or_unrecognised_side_seeds_sideless_rows(side):
    """Absent == bilateral. An unrecognised side degrades to the broader block, never a narrower one."""
    cands = ed.candidate_regions(_inj("shoulder", side=side))
    assert {c["side"] for c in cands} == {None}
    assert "side" not in ed.default_row_value("injury_x", cands[0], REVIEW)["scope"]


def test_a_missing_side_is_bilateral():
    assert {c["side"] for c in ed.candidate_regions({"body_part": "knee"})} == {None}


# ── D3: aliases, cervical, unknown ────────────────────────────────────────────

def test_pes_anserine_seeds_the_knee_set_which_the_live_arm_never_reached():
    """Ledger entry 30 (Q102): `"pes anserine"` contains no `knee`, so the bare substring match
    never fires. The declared alias does — the seeded default is broader than the arm, on purpose."""
    assert _regions(_inj("pes anserine", side="left")) == set(selection._ACUTE_TISSUE_BLOCKS["knee"])
    region = taxonomy.by_key("single_leg_hop")
    assert selection.is_contraindicated(region, "left", profile_hard_stops=None,
                                        active_injuries=[_norm_inj("pes anserine", "left")])[0] is False


@pytest.mark.parametrize("part,key", [
    ("patellar tendon", "knee"), ("patella", "knee"),
    ("rotator cuff", "shoulder"), ("labrum", "shoulder"), ("AC joint", "shoulder"),
    ("semimembranosus", "hamstring"),   # #340's BODY_PART_ALIASES, read not copied
])
def test_declared_aliases_reach_their_map_key(part, key):
    assert _regions(_inj(part)) == set(selection._ACUTE_TISSUE_BLOCKS[key])


def test_an_alias_is_not_a_license_for_an_unrelated_part():
    assert ed.candidate_regions(_inj("biceps")) == []   # "biceps femoris" is the alias, not "biceps"


@pytest.mark.parametrize("part", ["neck", "cervical spine", "cervical", "C5-C6", "c7 root"])
@pytest.mark.parametrize("signal", ["neural", "radicular"])
def test_a_cervical_neural_entry_seeds_nothing_from_the_lumbar_shaped_set(part, signal):
    assert ed.candidate_regions(_inj(part, signal_type=signal)) == []


def test_the_cervical_exclusion_is_what_stops_cervical_spine():
    """Control: `cervical spine` IS spinal by the live `_SPINAL_PARTS` (via "spine"), so without the
    exclusion it would seed the lumbar set — the live arm does fire there."""
    assert selection._is_spinal("cervical spine") is True
    assert ed.is_cervical("cervical spine") is True
    assert selection._is_spinal("neck") is False        # why the ledger's `neck` row fires no arm today


def test_an_empty_body_part_typed_neural_seeds_the_radicular_set():
    """Unknown degrades to the broader caution, never to permission (`_is_spinal`)."""
    assert _regions(_inj("", signal_type="radicular")) == set(selection._RADICULAR_BLOCKS)
    assert _regions({"signal_type": "neural"}) == set(selection._RADICULAR_BLOCKS)


def test_a_peripheral_neural_entry_seeds_no_radicular_set():
    assert ed.candidate_regions(_inj("elbow", signal_type="neural")) == []


# ── the O1 ledger (operator-reported, 2 Nov 2026) ────────────────────────────

O1 = {   # id: (key, value)
    77: ("injury_finger_left", _inj("finger", "left")),
    94: ("injury_lumbar_spine", _inj("lumbar", "bilateral")),
    101: ("injury_thumb_left", _inj("thumb", "left")),
    118: ("injury_shoulder_right", _inj("shoulder", "right")),
    119: ("injury_knee_left", _inj("knee", "left")),
    120: ("injury_cervical_spine", _inj("neck", "bilateral", "neural")),
}


def test_the_o1_ledger_seeds_five_proposals_and_nothing_else():
    got = {}
    for id_, (key, value) in O1.items():
        got[id_] = sorted((c["region_key"], c["side"]) for c in ed.candidate_regions(value))
    assert got[118] == [("horizontal_push", "right"), ("vertical_push", "right")]
    assert got[119] == [("change_of_direction", "left"), ("deceleration_landing", "left"),
                        ("single_leg_hop", "left")]
    assert [id_ for id_, rows in got.items() if not rows] == [77, 94, 101, 120]
    assert sum(len(r) for r in got.values()) == 5


# ── D1 row shape ──────────────────────────────────────────────────────────────

def test_a_default_row_is_the_d1_shape_and_passes_the_validator_unchanged():
    cand = ed.candidate_regions(_inj("shoulder", "right"))[0]
    value = ed.default_row_value("injury_shoulder_right", cand, REVIEW)
    assert validate_constraint(value) is value
    label = taxonomy.by_key(cand["region_key"]).label
    assert value == {
        "scope": {"tier": "engine", "region_keys": [cand["region_key"]], "side": "right",
                  "text": f"acute-tissue (shoulder): shoulder → {label} (engine default)"},
        "kind": "block", "parent_key": "injury_shoulder_right", "exit": {"with_parent": True},
        "review_by": "2026-12-14", "status": "proposed", "asserted_by": None,
    }
    assert ed.default_key("injury_shoulder_right", "vertical_push") == \
        "constraint_engine_injury_shoulder_right_vertical_push"


# ── the superset property (what lets PR2 retire the arms) ────────────────────

def _norm_inj(body_part, side="bilateral", signal_type="mechanical", ra_flare=False):
    return {"body_part": body_part.lower(), "side": side, "signal_type": signal_type,
            "ra_flare": ra_flare, "restrictions": [], "raw": {}}


EQUIV_FIXTURES = {
    "hamstring_r": _norm_inj("hamstring", "right"), "shoulder_l": _norm_inj("shoulder", "left"),
    "calf": _norm_inj("calf"), "ankle_r": _norm_inj("right ankle", "right"),
    "knee_bilateral": _norm_inj("knee"), "knee_alias": _norm_inj("patellar tendon", "left"),
    "lumbar_neural": _norm_inj("lumbar spine", signal_type="neural"),
    "back_radicular_l": _norm_inj("lower back", "left", "radicular"),
    "unknown_neural": _norm_inj("", signal_type="radicular"),
    "ra_flare": _norm_inj("hand", ra_flare=True),
    "ra_and_knee": _norm_inj("knee", "right", ra_flare=True),
    "peripheral_neural": _norm_inj("elbow", signal_type="neural"),
    "neck_neural": _norm_inj("neck", signal_type="neural"),
    "mechanical_lumbar": _norm_inj("lumbar"),
}
# The ONE documented divergence from the live arm: a cervical entry whose body part also contains
# "spine" fires the lumbar-shaped set today; the default deliberately does not (D3).
KNOWN_DIVERGENCE = {"cervical_spine_neural"}
EQUIV_FIXTURES["cervical_spine_neural"] = _norm_inj("cervical spine", signal_type="neural")


def _seeded_cells(inj):
    cells = set()
    for c in ed.candidate_regions(inj):
        region = taxonomy.by_key(c["region_key"])
        row_side = c["side"] or "bilateral"
        for s in region.sides():
            if selection._side_conflict(row_side, s):
                cells.add((region.key, s))
    return cells


def _arm_cells(inj):
    return {
        (r.key, s)
        for r in taxonomy.all_regions() for s in r.sides()
        if selection.is_contraindicated(r, s, profile_hard_stops=None, active_injuries=[inj])[0]
    }


@pytest.mark.parametrize("name", sorted(EQUIV_FIXTURES))
def test_the_seeded_set_covers_every_cell_the_live_arms_block(name):
    inj = EQUIV_FIXTURES[name]
    arm, seeded = _arm_cells(inj), _seeded_cells(inj)
    if name in KNOWN_DIVERGENCE:
        assert arm and not seeded      # pin the divergence itself: the arm fires, the default does not
    else:
        assert arm <= seeded, sorted(arm - seeded)


def test_the_equivalence_check_can_fail():
    """Negative control: drop one region from the seeded cells and the subset test would catch it."""
    inj = EQUIV_FIXTURES["knee_bilateral"]
    assert not (_arm_cells(inj) <= (_seeded_cells(inj) - {("single_leg_hop", "left")}))


# ── DB: idempotency ───────────────────────────────────────────────────────────

def _user(db, email="engdef@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _injury_row(db, user_id, key, value, active=True):
    row = models.UserKnowledgeEntry(user_id=user_id, type="injury", key=key, value=value,
                                    source="api", added_at=date.today(), active=active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _plan(db, user, key="injury_shoulder_right", value=None):
    return ed.plan_engine_defaults(db, user.id, key, value or _inj("shoulder", "right"), REVIEW)


def _write_default(db, user, region, key="injury_shoulder_right", **over):
    cand = next(c for c in ed.candidate_regions(O1_BY_KEY[key]) if c["region_key"] == region)
    value = ed.default_row_value(key, cand, REVIEW)
    value.update(over)
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(
        type="constraint", key=ed.default_key(key, region), value=value, source="system"), db)


O1_BY_KEY = {k: v for k, v in O1.values()}


def test_a_fresh_injury_plans_all_its_regions(db_session):
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    plan = _plan(db_session, u)
    assert [p["region_key"] for p in plan["planned"]] == ["horizontal_push", "vertical_push"]
    assert plan["skipped"] == [] and plan["conflicts"] == []


def test_an_active_proposal_is_not_proposed_again(db_session):
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    _write_default(db_session, u, "vertical_push")
    plan = _plan(db_session, u)
    assert [p["region_key"] for p in plan["planned"]] == ["horizontal_push"]
    assert "already covered" in plan["skipped"][0]["why"] and "active" in plan["skipped"][0]["why"]


def test_a_resolved_twin_is_never_re_proposed(db_session):
    """The #340 seed-resurrection lesson: a declined default stays declined."""
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    row = _write_default(db_session, u, "vertical_push")
    knowledge_router._resolve_entry(row.id, knowledge_router.ResolutionIn(
        basis="clinician aware; intent is to rebuild overhead strength", resolved_by="user"),
        "constraint", u.id, db_session)
    plan = _plan(db_session, u)
    assert [p["region_key"] for p in plan["planned"]] == ["horizontal_push"]
    assert "resolved" in plan["skipped"][0]["why"]


def test_an_operators_own_engine_row_on_the_same_parent_and_region_counts(db_session):
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    upsert_knowledge_entry(u.id, KnowledgeEntryIn(type="constraint", key="my_own_vpush", value={
        "scope": {"tier": "engine", "region_keys": ["vertical_push"], "side": "right"}, "kind": "block",
        "parent_key": "injury_shoulder_right", "exit": {"with_parent": True},
        "review_by": "2026-12-01", "status": "confirmed", "asserted_by": "user"}, source="api"), db_session)
    plan = _plan(db_session, u)
    assert [p["region_key"] for p in plan["planned"]] == ["horizontal_push"]
    assert "my_own_vpush" in plan["skipped"][0]["why"]


def test_a_confirmed_cover_with_another_side_is_skipped_and_says_so(db_session):
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    row = _write_default(db_session, u, "vertical_push")
    _client(db_session, u).post(f"/knowledge/constraints/{row.id}/confirm", json={"asserted_by": "user"})
    plan = _plan(db_session, u, value=_inj("shoulder", "left"))
    skipped = [s for s in plan["skipped"] if s["region_key"] == "vertical_push"]
    assert skipped and "its side is right, the injury now implies left" in skipped[0]["why"]
    assert skipped[0]["side_mismatch"] is True
    assert "vertical_push" not in [p["region_key"] for p in plan["planned"]]


def test_an_unconfirmed_default_with_another_side_is_replaced_not_skipped(db_session):
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    row = _write_default(db_session, u, "vertical_push")
    plan = _plan(db_session, u, value=_inj("shoulder", "left"))
    planned = {p["region_key"]: p for p in plan["planned"]}
    assert planned["vertical_push"]["replaces"] == row.id
    assert planned["vertical_push"]["value"]["scope"]["side"] == "left"
    assert planned["horizontal_push"]["replaces"] is None
    assert not any(s["region_key"] == "vertical_push" for s in plan["skipped"])


def test_a_hand_authored_proposal_with_another_side_is_never_replaced(db_session):
    """Only a default OF OURS (our key shape) is superseded; anything else is the operator's."""
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    upsert_knowledge_entry(u.id, KnowledgeEntryIn(type="constraint", key="my_proposal", value={
        "scope": {"tier": "engine", "region_keys": ["vertical_push"], "side": "right"}, "kind": "block",
        "parent_key": "injury_shoulder_right", "exit": {"with_parent": True},
        "review_by": "2026-12-01", "status": "proposed", "asserted_by": None}, source="api"), db_session)
    plan = _plan(db_session, u, value=_inj("shoulder", "left"))
    assert "vertical_push" not in [p["region_key"] for p in plan["planned"]]


def test_another_users_rows_do_not_cover(db_session):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    for u in (a, b):
        _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    _write_default(db_session, a, "vertical_push")
    assert len(_plan(db_session, b)["planned"]) == 2


def test_a_key_held_by_another_shape_is_a_conflict_not_a_write(db_session):
    u = _user(db_session)
    _injury_row(db_session, u.id, "injury_shoulder_right", _inj("shoulder", "right"))
    upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="constraint", key=ed.default_key("injury_shoulder_right", "vertical_push"),
        value={"scope": {"tier": "advisory", "text": "squatter"}, "kind": "block",
               "exit": {"on_condition": "cleared"}, "review_by": "2026-12-01",
               "status": "confirmed", "asserted_by": "user"}, source="api"), db_session)
    plan = _plan(db_session, u)
    assert [c["region_key"] for c in plan["conflicts"]] == ["vertical_push"]
    assert [p["region_key"] for p in plan["planned"]] == ["horizontal_push"]


# ── the injury write path (S2) ────────────────────────────────────────────────

def _put_injury(db, user, key, value, source="api"):
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(type="injury", key=key, value=value,
                                                            source=source), db)


def _defaults(db, user, *, active=None):
    q = db.query(models.UserKnowledgeEntry).filter_by(user_id=user.id, type="constraint")
    rows = [r for r in q.all() if r.key.startswith(ed.DEFAULT_KEY_PREFIX)]
    return [r for r in rows if active is None or r.active == active]


@pytest.mark.parametrize("source", ["api", "chat"])
def test_an_injury_write_proposes_its_defaults_whatever_the_channel(db_session, source):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_shoulder_right", _inj("shoulder", "right"), source=source)
    rows = _defaults(db_session, u)
    assert sorted(r.key for r in rows) == [
        "constraint_engine_injury_shoulder_right_horizontal_push",
        "constraint_engine_injury_shoulder_right_vertical_push"]
    for r in rows:
        v = r.value
        assert (v["status"], v["asserted_by"], v["kind"], v["parent_key"]) == \
            ("proposed", None, "block", "injury_shoulder_right")
        assert r.source == "system" and r.active


def test_the_hook_review_by_is_creation_day_plus_28(db_session):
    from datetime import timedelta
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    assert {r.value["review_by"] for r in _defaults(db_session, u)} == \
        {(_local_day() + timedelta(days=28)).isoformat()}


def test_the_o1_ledger_through_the_write_path_proposes_five(db_session):
    u = _user(db_session)
    for _, (key, value) in O1.items():
        _put_injury(db_session, u, key, value)
    assert len(_defaults(db_session, u)) == 5
    assert {r.value["parent_key"] for r in _defaults(db_session, u)} == \
        {"injury_shoulder_right", "injury_knee_left"}


def test_a_chat_proposal_cannot_be_promoted_by_the_chat_channel(db_session):
    """The chat-channel rule holds by construction: these are proposals, and chat still cannot
    confirm one or retire it."""
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"), source="chat")
    row = _defaults(db_session, u)[0]
    with pytest.raises(ValueError, match="confirmed|PROPOSAL"):
        upsert_knowledge_entry(u.id, KnowledgeEntryIn(
            type="constraint", key=row.key, value={**row.value, "status": "confirmed",
                                                   "asserted_by": "user"}, source="chat"), db_session)


def test_a_rewrite_that_changes_none_of_the_four_fields_proposes_nothing(db_session):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    # Delete one proposal outright: if the rewrite re-ran the planner it would come back (idempotency
    # would not hide it, because no row covers the pair any more).
    gone = _defaults(db_session, u)[0]
    gone_key = gone.key
    db_session.delete(gone)
    db_session.commit()
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left", restrictions=["no deep flexion"]))
    keys = {r.key for r in _defaults(db_session, u)}
    assert len(keys) == 2 and gone_key not in keys


@pytest.mark.parametrize("change", [
    {"signal_type": "neural", "body_part": "lumbar", "side": "left"},   # body_part + signal_type
    {"ra_flare": True},
])
def test_a_rewrite_that_changes_a_trigger_field_proposes_the_new_regions(db_session, change):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_x", _inj("knee", "left"))
    before = {r.key for r in _defaults(db_session, u)}
    _put_injury(db_session, u, "injury_x", {**_inj("knee", "left"), **change})
    after = {r.key for r in _defaults(db_session, u)}
    assert after > before


def test_a_re_sided_injury_supersedes_its_stale_unconfirmed_defaults(db_session):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    old = {r.key: r.id for r in _defaults(db_session, u)}
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "right"))
    active = _defaults(db_session, u, active=True)
    assert {r.key for r in active} == set(old)                      # same keys, same three regions
    assert {r.value["scope"]["side"] for r in active} == {"right"}
    assert {r.id for r in active}.isdisjoint(old.values())          # new rows ...
    assert all(r.superseded_by for r in _defaults(db_session, u, active=False))   # ... superseding the old
    assert len(active) == 3                                          # and no stale left-sided row survives


def test_a_re_sided_injury_never_touches_a_confirmed_default(db_session, caplog):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    row = next(r for r in _defaults(db_session, u) if r.key.endswith("single_leg_hop"))
    _client(db_session, u).post(f"/knowledge/constraints/{row.id}/confirm", json={"asserted_by": "user"})
    with caplog.at_level("WARNING"):
        _put_injury(db_session, u, "injury_knee_left", _inj("knee", "right"))
    db_session.refresh(row)
    assert row.active and row.value["status"] == "confirmed" and row.value["scope"]["side"] == "left"
    assert "its side is left, the injury now implies right" in caplog.text
    others = [r for r in _defaults(db_session, u, active=True) if r.id != row.id]
    assert {r.value["scope"]["side"] for r in others} == {"right"}


def test_a_retype_to_neural_proposes_the_radicular_set(db_session):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_lumbar_spine", _inj("lumbar"))
    assert _defaults(db_session, u) == []
    _put_injury(db_session, u, "injury_lumbar_spine", _inj("lumbar", signal_type="neural"))
    assert {r.value["scope"]["region_keys"][0] for r in _defaults(db_session, u)} == \
        set(selection._RADICULAR_BLOCKS)


def test_a_declined_default_survives_a_retype_that_still_implies_it(db_session):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    hop = next(r for r in _defaults(db_session, u) if r.key.endswith("single_leg_hop"))
    knowledge_router._resolve_entry(hop.id, knowledge_router.ResolutionIn(basis="declined", resolved_by="user"),
                                    "constraint", u.id, db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left", ra_flare=True))
    hops = [r for r in _defaults(db_session, u) if r.key.endswith("single_leg_hop")]
    assert [r.active for r in hops] == [False]


def test_a_refused_injury_write_leaves_no_proposals(db_session):
    u = _user(db_session)
    upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="constraint", key="injury_knee_left", value={
            "scope": {"tier": "advisory", "text": "x"}, "kind": "block", "exit": {"on_condition": "c"},
            "review_by": "2026-12-01", "status": "confirmed", "asserted_by": "user"}, source="api"), db_session)
    with pytest.raises(ValueError, match="key_collision|held by an active"):
        _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    assert _defaults(db_session, u) == []


def test_a_planning_fault_never_loses_the_injury(db_session, monkeypatch):
    u = _user(db_session)

    def boom(*a, **k):
        raise RuntimeError("planner fault")
    monkeypatch.setattr(ed, "plan_engine_defaults", boom)
    row = _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    assert row.active and _defaults(db_session, u) == []


def test_a_refused_proposal_is_skipped_and_the_injury_is_kept(db_session, monkeypatch):
    u = _user(db_session)
    real = ed.default_row_value

    def bad(*a, **k):
        v = real(*a, **k)
        v["kind"] = "nonsense"
        return v
    monkeypatch.setattr(ed, "default_row_value", bad)
    row = _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    assert row.active and _defaults(db_session, u) == []


# ── G3: a proposal reaches nothing; a confirmed row does ──────────────────────

def _queue(db, user):
    return selection.compute_probe_queue(db, user.id, profile=None, loaded_region_keys=set())


def test_proposals_change_neither_the_verdicts_nor_the_probe_queue(db_session):
    u = _user(db_session)
    for _, (key, value) in O1.items():     # direct ORM: the hook does not run
        _injury_row(db_session, u.id, key, value)
    before = _queue(db_session, u)
    injuries = selection.gather_active_injuries(db_session, u.id)
    verdicts = {(r.key, s): selection.is_contraindicated(r, s, profile_hard_stops=None, active_injuries=injuries)
                for r in taxonomy.all_regions() for s in r.sides()}

    # now the proposals are written for the same ledger (the directly-written rows never passed the hook)
    for key, value in O1.values():
        for p in ed.plan_engine_defaults(db_session, u.id, key, value, REVIEW)["planned"]:
            upsert_knowledge_entry(u.id, KnowledgeEntryIn(
                type="constraint", key=p["key"], value=p["value"], source="system"), db_session)
    proposals = [r for r in _defaults(db_session, u) if r.active]
    assert len(proposals) == 5 and all(r.value["status"] == "proposed" for r in proposals)

    assert selection.gather_active_constraints(db_session, u.id) == []
    assert _queue(db_session, u) == before
    injuries = selection.gather_active_injuries(db_session, u.id)
    assert verdicts == {(r.key, s): selection.is_contraindicated(
        r, s, profile_hard_stops=None, active_injuries=injuries, active_constraints=[])
        for r in taxonomy.all_regions() for s in r.sides()}


def test_a_confirmed_default_does_reach_the_engine(db_session):
    """Control for the test above: the harness can see a leak. Confirming one row blocks exactly that
    region on that side — through the real confirm route."""
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    # silence the arm so the constraint arm's effect is visible in isolation
    inj = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, type="injury").one()
    inj.value = {**inj.value, "body_part": "finger"}
    db_session.commit()
    assert selection.gather_active_constraints(db_session, u.id) == []
    row = next(r for r in _defaults(db_session, u) if r.key.endswith("deceleration_landing"))
    _client(db_session, u).post(f"/knowledge/constraints/{row.id}/confirm", json={"asserted_by": "user"})
    got = selection.gather_active_constraints(db_session, u.id)
    assert [(c["region_keys"], c["side"]) for c in got] == [(["deceleration_landing"], "left")]
    assert ("deceleration_landing", "left") not in {(c["region_key"], c["side"]) for c in _queue(db_session, u)}


# ── V3: decline ───────────────────────────────────────────────────────────────

def _client(db, user):
    app = FastAPI()
    app.include_router(knowledge_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_declining_a_proposal_stores_the_resolution_and_removes_it_from_the_proposals_list(db_session):
    u = _user(db_session)
    _put_injury(db_session, u, "injury_shoulder_right", _inj("shoulder", "right"))
    c = _client(db_session, u)
    proposals = c.get("/knowledge/proposals").json()
    assert len(proposals) == 2
    target = proposals[0]
    r = c.post(f"/knowledge/constraints/{target['id']}/resolve",
               json={"basis": "clinician aware; intent is to rebuild overhead strength", "resolved_by": "user"})
    assert r.status_code == 200, r.text
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=target["id"]).one()
    assert not fresh.active and fresh.superseded_by is None
    assert fresh.value["resolution"]["basis"].startswith("clinician aware")
    assert fresh.value["resolution"]["resolved_by"] == "user"
    assert [p["id"] for p in c.get("/knowledge/proposals").json()] == [proposals[1]["id"]]
    # a blank basis is refused: a decline states its grounds
    assert c.post(f"/knowledge/constraints/{proposals[1]['id']}/resolve",
                  json={"basis": " ", "resolved_by": "user"}).status_code == 422


def test_an_injury_resolve_leaves_its_defaults_to_surface_as_exit_due_not_retire(db_session):
    """V4: surfacing, not retirement. The child stays active; the sweep (test_review_due) lists it."""
    import typed_entries
    u = _user(db_session)
    _put_injury(db_session, u, "injury_knee_left", _inj("knee", "left"))
    inj = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, type="injury", active=True).one()
    knowledge_router._resolve_entry(inj.id, knowledge_router.ResolutionIn(basis="healed", resolved_by="user"),
                                    "injury", u.id, db_session)
    children = _defaults(db_session, u, active=True)
    assert len(children) == 3
    live = typed_entries.active_keys(db_session.query(models.UserKnowledgeEntry).filter_by(active=True).all())
    assert all(typed_entries.constraint_due_tags(c.value, live, _local_day()) == ["exit due"] for c in children)
