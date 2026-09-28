"""The engine reads engine-tier constraints — S3 of the typed-entries brief (#342).

G3's gates:
  * ZERO ROWS → BYTE-IDENTICAL. With no constraint rows, `is_contraindicated` returns exactly what
    the pre-change engine returned — same bool, same reason string — for every one of the 36
    taxonomy regions × its sides, under each #72-probe injury fixture (the #72 probe enumerated
    30 regions; the taxonomy has 36 since v0.1). `compute_probe_queue` is identical end to end.
    The comparison runs against the engine AS IT WAS, loaded from the pinned SHA, never against
    a re-typed copy. No existing test is re-baselined.
  * one confirmed engine `block` on `hinge` blocks `hinge` and NOTHING else;
  * the same row `proposed` blocks nothing; an `advisory` row blocks nothing; a resolved row
    blocks nothing;
  * `side` (G2 ruling 1): a right-sided row blocks the right side only (plus bilateral-scored
    regions, per the engine's own `_side_conflict`).
"""
import os
import subprocess
import types
from datetime import date

import pytest

import models
from engine import selection, taxonomy
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

# The master this branch was cut from — the engine before the constraint arm existed. Pinned to
# a SHA, never "master": master moves past this change, which would make the comparison new-vs-new.
PRE_CONSTRAINT_SHA = "8324a28"


def _load_pre_constraint_selection():
    src = subprocess.check_output(
        ["git", "show", f"{PRE_CONSTRAINT_SHA}:backend/engine/selection.py"],
        cwd=os.path.dirname(__file__), encoding="utf-8",
    )
    module = types.ModuleType("engine._selection_pre_constraint")
    module.__package__ = "engine"          # its `from . import taxonomy` resolves against the live package
    exec(compile(src, "selection_pre_constraint.py", "exec"), module.__dict__)
    return module


OLD = _load_pre_constraint_selection()


def _inj(body_part, side="bilateral", signal_type="mechanical", ra_flare=False):
    return {"body_part": body_part, "side": side, "signal_type": signal_type,
            "ra_flare": ra_flare, "restrictions": [], "raw": {}}


# The #72 exclusion-set probe's shapes, plus the other arms, so every existing branch is exercised.
INJURY_FIXTURES = {
    "none": [],
    "neural_lumbar": [_inj("lumbar spine", signal_type="neural")],
    "neural_unknown": [_inj("", signal_type="radicular")],
    "neural_peripheral": [_inj("elbow", signal_type="neural")],
    "hamstring_right_mechanical": [_inj("hamstring", side="right")],
    "ra_flare": [_inj("hand", ra_flare=True)],
    "shoulder_left": [_inj("shoulder", side="left")],
    "stacked": [_inj("calf", side="left"), _inj("knee", side="right"), _inj("ankle")],
}
HARD_STOPS = {"none": None, "squat_left": [{"region_key": "squat", "side": "left", "reason": "hs"}]}

ALL_CELLS = [(r, s) for r in taxonomy.all_regions() for s in r.sides()]


def test_the_matrix_covers_all_36_regions():
    assert len(taxonomy.all_regions()) == 36
    assert len({r.key for r, _ in ALL_CELLS}) == 36


@pytest.mark.parametrize("hs", list(HARD_STOPS))
@pytest.mark.parametrize("fixture", list(INJURY_FIXTURES))
def test_zero_constraints_is_byte_identical_to_the_pre_change_engine(fixture, hs):
    injuries, stops = INJURY_FIXTURES[fixture], HARD_STOPS[hs]
    for region, side in ALL_CELLS:
        old = OLD.is_contraindicated(region, side, profile_hard_stops=stops, active_injuries=injuries)
        assert selection.is_contraindicated(
            region, side, profile_hard_stops=stops, active_injuries=injuries) == old
        assert selection.is_contraindicated(
            region, side, profile_hard_stops=stops, active_injuries=injuries, active_constraints=[]) == old


HINGE_BLOCK = [{"key": "c_hinge", "region_keys": ["hinge"], "side": "bilateral", "kind": "block"}]


@pytest.mark.parametrize("fixture", list(INJURY_FIXTURES))
def test_a_hinge_block_blocks_hinge_and_nothing_else(fixture):
    injuries = INJURY_FIXTURES[fixture]
    changed = []
    for region, side in ALL_CELLS:
        old = OLD.is_contraindicated(region, side, profile_hard_stops=None, active_injuries=injuries)
        new = selection.is_contraindicated(region, side, profile_hard_stops=None,
                                           active_injuries=injuries, active_constraints=HINGE_BLOCK)
        if new != old:
            changed.append((region.key, side, new))
    already_blocked = OLD.is_contraindicated(
        taxonomy.by_key("hinge"), "left", profile_hard_stops=None, active_injuries=injuries)[0]
    if already_blocked:
        # An existing arm already blocks hinge (the radicular set): it keeps its own reason —
        # the constraint arm runs last and changes no existing verdict or reason.
        assert changed == []
    else:
        assert changed == [("hinge", s, (True, "constraint c_hinge — block"))
                           for s in taxonomy.by_key("hinge").sides()]


def test_a_right_sided_block_leaves_the_left_side_open():
    region = taxonomy.by_key("shoulder_er_ir")
    assert region.per_side
    c = [{"key": "c_r_shoulder", "region_keys": ["shoulder_er_ir"], "side": "right", "kind": "block"}]
    kw = dict(profile_hard_stops=None, active_injuries=[], active_constraints=c)
    assert selection.is_contraindicated(region, "right", **kw) == (True, "constraint c_r_shoulder — block")
    assert selection.is_contraindicated(region, "left", **kw) == (False, None)


def test_a_sided_block_on_a_bilateral_scored_region_blocks_it():
    """`_side_conflict`'s own rule: a region scored bilaterally is hit by a sided restriction."""
    region = next(r for r in taxonomy.all_regions() if not r.per_side)
    c = [{"key": "c", "region_keys": [region.key], "side": "right", "kind": "block"}]
    assert selection.is_contraindicated(region, "bilateral", profile_hard_stops=None,
                                        active_injuries=[], active_constraints=c)[0] is True


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


def _queue(module, db, user_id):
    return module.compute_probe_queue(db, user_id, profile=None, loaded_region_keys=set())


def _hinge_in(queue):
    return {c["side"] for c in queue if c["region_key"] == "hinge"}


def test_probe_queue_is_identical_with_no_constraint_rows(db_session):
    u = _user(db_session)
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key="hamstring_right", source="api", added_at=date.today(),
        active=True, value={"body_part": "hamstring", "side": "right", "signal_type": "mechanical"},
    ))
    db_session.commit()
    assert _queue(selection, db_session, u.id) == _queue(OLD, db_session, u.id)


@pytest.mark.parametrize("case", ["proposed", "advisory", "resolved"])
def test_rows_the_engine_must_not_read_block_nothing(db_session, case):
    u = _user(db_session)
    if case == "proposed":
        _constraint(db_session, u.id, status="proposed")
    elif case == "advisory":
        _constraint(db_session, u.id, tier="advisory")
    else:
        row = _constraint(db_session, u.id)
        row.active = False
        db_session.commit()
    assert selection.gather_active_constraints(db_session, u.id) == []
    assert _queue(selection, db_session, u.id) == _queue(OLD, db_session, u.id)


def test_a_confirmed_engine_row_removes_hinge_from_the_probe_queue(db_session):
    u = _user(db_session)
    assert _hinge_in(_queue(selection, db_session, u.id))           # precondition: hinge probeable
    _constraint(db_session, u.id)
    new, old = _queue(selection, db_session, u.id), _queue(OLD, db_session, u.id)
    assert _hinge_in(new) == set()
    assert [c for c in old if c["region_key"] != "hinge"] == new     # and nothing else moved


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
