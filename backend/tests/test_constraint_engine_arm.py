"""The engine reads engine-tier constraints — S3 of the typed-entries brief (#342), as it stands after the
injury-keyed block maps retired ("Engine blocks are rows", DECISIONS_LOG #486).

`is_contraindicated` now has TWO arms, both explicit rows: the profile hard-stop arm and the confirmed
engine-tier constraint arm. G3's gates, restated for that engine:
  * IDENTITY. For every one of the taxonomy's regions × its sides, under each profile-hard-stop fixture and
    each constraint set, the two remaining arms return exactly what they returned at the PR1 merge (same
    bool, same reason string). The comparison runs against the engine AS PR1 MERGED IT, loaded from the
    pinned SHA (`pr1_oracle`), never against a re-typed copy. The retired injury arms are NOT part of this
    identity — their retirement is gated separately, per user, in `test_engine_block_retirement`.
  * one confirmed engine `block` on `hinge` blocks `hinge` and NOTHING else;
  * the same row `proposed` blocks nothing; an `advisory` row blocks nothing; a resolved row blocks nothing;
  * `side` (G2 ruling 1): a right-sided row blocks the right side only (plus bilateral-scored regions, per
    the engine's own `_side_conflict`);
  * an INJURY row blocks nothing by itself: the probe queue is the same with it as without it.
"""
from datetime import date

import pytest

import models
from engine import selection, taxonomy
from pr1_oracle import PR1 as OLD
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

HARD_STOPS = {"none": None, "squat_left": [{"region_key": "squat", "side": "left", "reason": "hs"}]}

HINGE_BLOCK = [{"key": "c_hinge", "region_keys": ["hinge"], "side": "bilateral", "kind": "block"}]
SIDED_BLOCKS = [
    {"key": "c_r_er", "region_keys": ["shoulder_er"], "side": "right", "kind": "block"},
    {"key": "c_l_hop", "region_keys": ["single_leg_hop", "deceleration_landing"], "side": "left", "kind": "block"},
]
CONSTRAINT_SETS = {"none": None, "empty": [], "hinge": HINGE_BLOCK, "sided": SIDED_BLOCKS,
                   "all": HINGE_BLOCK + SIDED_BLOCKS}

ALL_CELLS = [(r, s) for r in taxonomy.all_regions() for s in r.sides()]


def test_the_matrix_covers_every_region_in_the_taxonomy():
    assert len(ALL_CELLS) == sum(len(r.sides()) for r in taxonomy.all_regions())
    assert len({r.key for r, _ in ALL_CELLS}) == len(taxonomy.all_regions()) == 39


@pytest.mark.parametrize("cs", list(CONSTRAINT_SETS))
@pytest.mark.parametrize("hs", list(HARD_STOPS))
def test_the_two_remaining_arms_are_identical_to_the_pr1_engine(hs, cs):
    stops, constraints = HARD_STOPS[hs], CONSTRAINT_SETS[cs]
    for region, side in ALL_CELLS:
        old = OLD.is_contraindicated(
            region, side, profile_hard_stops=stops, active_injuries=[], active_constraints=constraints)
        assert selection.is_contraindicated(
            region, side, profile_hard_stops=stops, active_constraints=constraints) == old


def test_is_contraindicated_takes_no_injuries():
    """A parameter that is accepted and ignored is how a retired gate keeps looking alive."""
    import inspect
    assert "active_injuries" not in inspect.signature(selection.is_contraindicated).parameters
    assert "active_injuries" not in inspect.signature(selection.compute_probe_queue).parameters
    with pytest.raises(TypeError):
        selection.is_contraindicated(taxonomy.by_key("hinge"), "bilateral",
                                     profile_hard_stops=None, active_injuries=[])


@pytest.mark.parametrize("hs", list(HARD_STOPS))
def test_a_hinge_block_blocks_hinge_and_nothing_else(hs):
    changed = []
    for region, side in ALL_CELLS:
        base = selection.is_contraindicated(region, side, profile_hard_stops=HARD_STOPS[hs])
        new = selection.is_contraindicated(region, side, profile_hard_stops=HARD_STOPS[hs],
                                           active_constraints=HINGE_BLOCK)
        if new != base:
            changed.append((region.key, side, new))
    assert changed == [("hinge", s, (True, "constraint c_hinge — block"))
                       for s in taxonomy.by_key("hinge").sides()]


def test_a_right_sided_block_leaves_the_left_side_open():
    region = taxonomy.by_key("shoulder_er")
    assert region.per_side
    c = [{"key": "c_r_shoulder", "region_keys": ["shoulder_er"], "side": "right", "kind": "block"}]
    kw = dict(profile_hard_stops=None, active_constraints=c)
    assert selection.is_contraindicated(region, "right", **kw) == (True, "constraint c_r_shoulder — block")
    assert selection.is_contraindicated(region, "left", **kw) == (False, None)


def test_a_sided_block_on_a_bilateral_scored_region_blocks_it():
    """`_side_conflict`'s own rule: a region scored bilaterally is hit by a sided restriction."""
    region = next(r for r in taxonomy.all_regions() if not r.per_side)
    c = [{"key": "c", "region_keys": [region.key], "side": "right", "kind": "block"}]
    assert selection.is_contraindicated(region, "bilateral", profile_hard_stops=None,
                                        active_constraints=c)[0] is True


def test_a_profile_hard_stop_still_outranks_a_constraint_for_the_reason_string():
    """Arm order is part of the contract: the hard-stop arm answers first."""
    c = [{"key": "c_sq", "region_keys": ["squat"], "side": "bilateral", "kind": "block"}]
    got = selection.is_contraindicated(taxonomy.by_key("squat"), "left",
                                       profile_hard_stops=HARD_STOPS["squat_left"], active_constraints=c)
    assert got == (True, "hs")


# ── through the store: which rows the engine reads ───────────────────────────

def _user(db, email="engine-arm@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _constraint(db, user_id, key="c_hinge", *, tier="engine", status="confirmed", side=None):
    scope = ({"tier": "engine", "region_keys": ["hinge"]} if tier == "engine"
             else {"tier": "advisory", "text": "no heavy hinging"})
    if side is not None:
        scope["side"] = side
    return upsert_knowledge_entry(user_id, KnowledgeEntryIn(type="constraint", key=key, value={
        "scope": scope, "kind": "block", "exit": {"on_condition": "cleared by physio"},
        "review_by": "2026-10-15", "status": status,
        "asserted_by": "user" if status == "confirmed" else None,
    }, source="api"), db)


def _queue(db, user_id):
    return selection.compute_probe_queue(db, user_id, profile=None, loaded_region_keys=set())


def _hinge_in(queue):
    return {c["side"] for c in queue if c["region_key"] == "hinge"}


@pytest.mark.parametrize("injury", [
    {"body_part": "hamstring", "side": "right", "signal_type": "mechanical"},
    {"body_part": "shoulder", "side": "left", "signal_type": "mechanical"},
    {"body_part": "knee", "side": "left", "signal_type": "mechanical"},
    {"body_part": "lumbar spine", "side": "bilateral", "signal_type": "neural"},
    {"body_part": "", "side": "bilateral", "signal_type": "radicular"},
    {"body_part": "hand", "side": "bilateral", "signal_type": "mechanical", "ra_flare": True},
])
def test_an_injury_row_alone_changes_the_probe_queue_in_nothing(db_session, injury):
    """The retirement, end to end: the shapes that used to remove regions (acute-tissue, radicular,
    RA-flare) now remove none. Only a confirmed engine row does."""
    u = _user(db_session)
    before = _queue(db_session, u.id)
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key="injury_x", source="api", added_at=date.today(),
        active=True, value=injury,
    ))
    db_session.commit()
    assert selection.gather_active_injuries(db_session, u.id)       # the row IS read by the chat / sweep
    assert _queue(db_session, u.id) == before


@pytest.mark.parametrize("case", ["proposed", "advisory", "resolved"])
def test_rows_the_engine_must_not_read_block_nothing(db_session, case):
    u = _user(db_session)
    before = _queue(db_session, u.id)
    if case == "proposed":
        _constraint(db_session, u.id, status="proposed")
    elif case == "advisory":
        _constraint(db_session, u.id, tier="advisory")
    else:
        row = _constraint(db_session, u.id)
        row.active = False
        db_session.commit()
    assert selection.gather_active_constraints(db_session, u.id) == []
    assert _queue(db_session, u.id) == before


def test_a_confirmed_engine_row_removes_hinge_from_the_probe_queue(db_session):
    u = _user(db_session)
    before = _queue(db_session, u.id)
    assert _hinge_in(before)                                         # precondition: hinge probeable
    _constraint(db_session, u.id)
    after = _queue(db_session, u.id)
    assert _hinge_in(after) == set()
    assert [c for c in before if c["region_key"] != "hinge"] == after   # and nothing else moved


def test_another_users_constraint_is_not_read(db_session):
    _constraint(db_session, _user(db_session, "other@example.com").id)
    u = _user(db_session)
    assert selection.gather_active_constraints(db_session, u.id) == []


def test_gather_normalises_side_default_bilateral(db_session):
    u = _user(db_session)
    _constraint(db_session, u.id, key="a")
    _constraint(db_session, u.id, key="b", side="left")
    got = {c["key"]: c["side"] for c in selection.gather_active_constraints(db_session, u.id)}
    assert got == {"a": "bilateral", "b": "left"}
