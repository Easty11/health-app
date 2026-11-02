"""G4 — the equivalence gate for retiring the injury-keyed block maps ("Engine blocks are rows", #486).

THE GATE. For each user with an active injury, every (region, side) the retired arms would block for that
user's active injuries must be EITHER blocked by a confirmed engine-tier row OR covered by a DECLINED
proposal (an engine-default proposal the operator resolved with a basis). A cell in neither set is
under-protection the retirement would silently introduce: the gate halts there and names it.

THE ORACLE is the engine as PR1 merged it (`pr1_oracle`), read through its own `gather_active_injuries`
on the same rows, never a re-typed copy of the maps.

THE FIXTURES are the operator's recorded outcome (O4, 2 Nov 2026, operator-reported; Code cannot read
prod): user 1's six active injuries produced five proposals (ids 168 to 172), all DECLINED, none
confirmed, pending 0; user 9's two active injuries produced none. The rows are rebuilt here through the
real write path (the planner, then the real resolve function), not hand-written.

The gate is also shown to FAIL: nothing proposed, proposals left pending, one proposal left pending, a
declined row on the wrong side, and a declined row that was never an engine proposal each leave a named
gap. Without those a green gate would only mean the harness looks at nothing.
"""
from datetime import date

import pytest

import models
from engine import engine_defaults as ed
from engine import selection, taxonomy
from pr1_oracle import PR1
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

REVIEW = date(2026, 12, 14)

# O1 / O4 — user 1 (ids as reported)
USER_1 = [
    (77, "injury_finger_left", {"body_part": "finger", "side": "left", "signal_type": "mechanical"}),
    (94, "injury_lumbar_spine", {"body_part": "lumbar", "side": "bilateral", "signal_type": "mechanical"}),
    (101, "injury_thumb_left", {"body_part": "thumb", "side": "left", "signal_type": "mechanical"}),
    (118, "injury_shoulder_right", {"body_part": "shoulder", "side": "right", "signal_type": "mechanical"}),
    (119, "injury_knee_left", {"body_part": "knee", "side": "left", "signal_type": "mechanical"}),
    (120, "injury_cervical_spine", {"body_part": "neck", "side": "bilateral", "signal_type": "neural"}),
]
# O4 — user 9: two active injuries, dry-run planned nothing
USER_9 = [
    (162, "injury_pelvic_tilt", {"body_part": "pelvis", "side": "bilateral", "signal_type": "mechanical"}),
    (163, "injury_pigeon_foot_left", {"body_part": "foot/hip", "side": "left", "signal_type": "mechanical"}),
]

DECLINE_BASIS = "not an active restriction; clinician aware; running plan has lateral and plyometric work"


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _ledger(db, user, rows):
    """Injuries straight to the ORM, as prod holds them (the write-path hook does not run)."""
    for id_, key, value in rows:
        db.add(models.UserKnowledgeEntry(id=id_, user_id=user.id, type="injury", key=key, value=value,
                                         source="api", added_at=date(2026, 7, 1), active=True))
    db.commit()


def _propose_all(db, user):
    """What `scripts/seed_engine_defaults.py --confirm` wrote: every planned proposal."""
    rows = []
    injuries = (db.query(models.UserKnowledgeEntry)
                .filter_by(user_id=user.id, type="injury", active=True)
                .order_by(models.UserKnowledgeEntry.id).all())
    for inj in injuries:
        for p in ed.plan_engine_defaults(db, user.id, inj.key, inj.value, REVIEW)["planned"]:
            rows.append(upsert_knowledge_entry(user.id, KnowledgeEntryIn(
                type="constraint", key=p["key"], value=p["value"], source="system"), db))
    return rows


def _decline(db, user, row, basis=DECLINE_BASIS):
    knowledge_router._resolve_entry(row.id, knowledge_router.ResolutionIn(basis=basis, resolved_by="user"),
                                    "constraint", user.id, db)


def _confirm(db, user, row):
    knowledge_router._confirm_entry(row.id, knowledge_router.ConfirmIn(asserted_by="user"),
                                    "constraint", user.id, db)


# ── the gate ──────────────────────────────────────────────────────────────────

def arm_cells(db, user):
    """(region, side) cells the PR1 arms block for this user's active injuries, from the same rows."""
    injuries = PR1.gather_active_injuries(db, user.id)
    return {
        (r.key, s)
        for r in taxonomy.all_regions() for s in r.sides()
        if PR1.is_contraindicated(r, s, profile_hard_stops=None, active_injuries=injuries)[0]
    }


def covered_cells(db, user):
    """Cells covered by a confirmed engine row, or by a DECLINED engine proposal (resolved while still
    `proposed`, with a stated basis). A pending proposal covers nothing."""
    covering = []
    for c in selection.gather_active_constraints(db, user.id):          # confirmed, active, engine
        covering.append((c["region_keys"], c["side"]))
    for r in db.query(models.UserKnowledgeEntry).filter_by(user_id=user.id, type="constraint").all():
        v = r.value or {}
        scope = v.get("scope") or {}
        if (not r.active and scope.get("tier") == "engine" and v.get("status") == "proposed"
                and str((v.get("resolution") or {}).get("basis") or "").strip()):
            covering.append((scope.get("region_keys") or [], str(scope.get("side") or "bilateral").lower()))
    cells = set()
    for keys, side in covering:
        for k in keys:
            region = taxonomy.by_key(k)
            for s in region.sides():
                if selection._side_conflict(side, s):
                    cells.add((k, s))
    return cells


def gap(db, user):
    """The halt condition: cells the retired arms block that nothing decided."""
    return sorted(arm_cells(db, user) - covered_cells(db, user))


# ── user 1: the recorded outcome passes ──────────────────────────────────────

@pytest.fixture
def user1(db_session):
    u = _user(db_session, "u1@example.com")
    _ledger(db_session, u, USER_1)
    return u


@pytest.fixture
def user9(db_session):
    u = _user(db_session, "u9@example.com")
    _ledger(db_session, u, USER_9)
    return u


def test_the_gate_is_not_vacuous_for_user_1(db_session, user1):
    cells = arm_cells(db_session, user1)
    # the shoulder regions are scored bilaterally, so the right shoulder's arm hits their one cell
    assert {("vertical_push", "bilateral"), ("horizontal_push", "bilateral")} <= cells
    # the knee regions are per-side: the left knee blocks the LEFT cell only
    assert {("single_leg_hop", "left"), ("change_of_direction", "left"), ("deceleration_landing", "left")} <= cells
    assert not any(k in ("single_leg_hop", "change_of_direction", "deceleration_landing") and s == "right"
                   for k, s in cells)
    # and nothing the lumbar / cervical / finger / thumb rows would have blocked: they fired no arm
    assert {k for k, _ in cells} == {"vertical_push", "horizontal_push", "single_leg_hop",
                                     "change_of_direction", "deceleration_landing"}


def test_g4_passes_for_user_1_when_all_five_proposals_are_declined(db_session, user1):
    rows = _propose_all(db_session, user1)
    assert len(rows) == 5
    for r in rows:
        _decline(db_session, user1, r)
    assert gap(db_session, user1) == []
    assert selection.gather_active_constraints(db_session, user1.id) == []      # all declined: nothing enforced


def test_g4_passes_when_confirmed_rows_cover_instead(db_session, user1):
    for r in _propose_all(db_session, user1):
        _confirm(db_session, user1, r)
    assert gap(db_session, user1) == []


def test_g4_passes_for_a_mix_of_confirmed_and_declined(db_session, user1):
    rows = _propose_all(db_session, user1)
    for i, r in enumerate(rows):
        (_confirm if i % 2 else _decline)(db_session, user1, r)
    assert gap(db_session, user1) == []


# ── user 9: nothing to decide ────────────────────────────────────────────────

def test_user_9_has_nothing_the_arms_would_block_and_nothing_proposed(db_session, user9):
    assert arm_cells(db_session, user9) == set()
    assert _propose_all(db_session, user9) == []
    assert gap(db_session, user9) == []


# ── the gate can fail ────────────────────────────────────────────────────────

def test_g4_halts_when_nothing_was_proposed(db_session, user1):
    assert gap(db_session, user1) == sorted(arm_cells(db_session, user1))


def test_g4_halts_when_the_proposals_are_still_pending(db_session, user1):
    """A proposal blocks nothing and decides nothing: pending covers no cell."""
    _propose_all(db_session, user1)
    assert gap(db_session, user1) == sorted(arm_cells(db_session, user1))


def test_g4_halts_naming_the_one_proposal_left_pending(db_session, user1):
    rows = _propose_all(db_session, user1)
    left = next(r for r in rows if r.key.endswith("deceleration_landing"))
    for r in rows:
        if r.id != left.id:
            _decline(db_session, user1, r)
    got = gap(db_session, user1)
    assert got and {k for k, _ in got} == {"deceleration_landing"}
    assert ("deceleration_landing", "left") in got


def test_g4_halts_on_a_declined_row_for_the_other_side(db_session, user1):
    """A right-sided decline decides nothing about the left knee."""
    _propose_all(db_session, user1)
    wrong = upsert_knowledge_entry(user1.id, KnowledgeEntryIn(
        type="constraint", key="wrong_side_hop", source="api", value={
            "scope": {"tier": "engine", "region_keys": ["single_leg_hop"], "side": "right"}, "kind": "block",
            "parent_key": "injury_knee_left", "exit": {"with_parent": True}, "review_by": "2026-12-14",
            "status": "proposed", "asserted_by": None}), db_session)
    _decline(db_session, user1, wrong)
    assert ("single_leg_hop", "left") in gap(db_session, user1)


def test_g4_does_not_count_a_row_that_was_confirmed_and_later_resolved(db_session, user1):
    """Only a DECLINED proposal is a decision about the default. A row confirmed and then retired lifted
    the ROW, but the arm kept blocking that cell the whole time: retiring the arm would lift it silently,
    with the operator never having been asked about the arm. The gate must halt there."""
    rows = _propose_all(db_session, user1)
    target = next(r for r in rows if r.key.endswith("single_leg_hop"))
    for r in rows:
        if r.id == target.id:
            _confirm(db_session, user1, r)
            _decline(db_session, user1, r, basis="exit fired; the injury healed")      # retired, not declined
        else:
            _decline(db_session, user1, r)
    got = gap(db_session, user1)
    assert ("single_leg_hop", "left") in got and {k for k, _ in got} == {"single_leg_hop"}


def test_g4_does_not_count_a_resolved_row_that_was_never_an_engine_proposal(db_session, user1):
    _propose_all(db_session, user1)
    adv = upsert_knowledge_entry(user1.id, KnowledgeEntryIn(
        type="constraint", key="advisory_note", source="api", value={
            "scope": {"tier": "advisory", "text": "knee: avoid deep loaded flexion"}, "kind": "block",
            "parent_key": "injury_knee_left", "exit": {"with_parent": True}, "review_by": "2026-12-14",
            "status": "proposed", "asserted_by": None}), db_session)
    _decline(db_session, user1, adv)
    assert gap(db_session, user1) == sorted(arm_cells(db_session, user1))


# ── the retirement itself ────────────────────────────────────────────────────

def test_the_maps_are_gone_from_selection_and_kept_as_reference_data():
    for name in ("_ACUTE_TISSUE_BLOCKS", "_RADICULAR_BLOCKS", "_RA_FLARE_BLOCKS", "_SPINAL_PARTS", "_is_spinal"):
        assert not hasattr(selection, name), name
        assert hasattr(ed, name), name
    assert hasattr(PR1, "_ACUTE_TISSUE_BLOCKS")                 # and the oracle still has the old arms


def test_the_reference_data_is_what_the_pr1_engine_enforced():
    """The seed source did not drift in the move."""
    assert ed._ACUTE_TISSUE_BLOCKS == PR1._ACUTE_TISSUE_BLOCKS
    assert ed._RADICULAR_BLOCKS == PR1._RADICULAR_BLOCKS
    assert ed._RA_FLARE_BLOCKS == PR1._RA_FLARE_BLOCKS
    assert ed._SPINAL_PARTS == PR1._SPINAL_PARTS
    for body in ("", "lumbar", "neck", "cervical spine", "back", "s1"):
        assert ed._is_spinal(body) == PR1._is_spinal(body)


def test_an_injury_alone_now_blocks_no_cell_the_gate_is_what_stood_in_for_it(db_session, user1):
    """After the retirement the engine blocks none of the cells the old arms blocked, unless an
    operator-confirmed row says so — which is exactly what the gate accounted for."""
    now = {
        (r.key, s) for r in taxonomy.all_regions() for s in r.sides()
        if selection.is_contraindicated(
            r, s, profile_hard_stops=None,
            active_constraints=selection.gather_active_constraints(db_session, user1.id))[0]
    }
    assert arm_cells(db_session, user1) and now == set()
