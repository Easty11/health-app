"""MCP read doors for the engine: `get_injuries`, `get_constraints`, `get_probe_queue`.

Prod reads reach Code only as MCP tools added by PR (operator ruling, 2 Nov 2026); these are three. What is
pinned:
  * the probe-queue refactor is output-identical: `compute_probe_queue` returns exactly what it returned
    before `probe_queue_detail` existed (the engine at 4845d40, loaded from git), across profile hard-stops,
    confirmed engine rows, capability states and a loaded set;
  * every (region, side) cell is in the queue XOR in the exclusions, each excluded with the engine's own reason,
    and the checks report in the set expression's order;
  * `get_constraints` carries what the operator needs and Code could not see without psql: the PENDING count,
    proposals, a declined default's basis, due rows; a superseded row is never listed;
  * `get_injuries` lists the ledger as written with the engine rows parented to each injury by state;
  * the tools are read-only, scoped to the token's user, stamped with `as_of`, and registered;
  * the case this door was built to answer: after the maps retired, the five regions an injury used to block
    are probeable for the O1 ledger, and a confirmed row excludes exactly its cell with its key as the reason.
"""
import asyncio
from datetime import date, timedelta

import pytest

import mcp_server
import models
from engine import selection, taxonomy
from load_metrics import _local_day
from pr1_oracle import load_selection_at
from reads import engine_reads
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

# The engine immediately before `probe_queue_detail` existed (the merge of the retirement PR).
BEFORE_DETAIL = load_selection_at("4845d40a85c1be652f41bca1c8caa9ffded3ece2", "engine._selection_before_detail")

TODAY = _local_day()
PAST = (TODAY - timedelta(days=10)).isoformat()
FUTURE = (TODAY + timedelta(days=60)).isoformat()
FIVE = [("vertical_push", "bilateral"), ("horizontal_push", "bilateral"), ("single_leg_hop", "left"),
        ("change_of_direction", "left"), ("deceleration_landing", "left")]
ALL_CELLS = {(r.key, s) for r in taxonomy.all_regions() for s in r.sides()}
HINGE_SIDES = taxonomy.by_key("hinge").sides()      # per-side: the cell names a side, never assume "bilateral"


def _user(db, email="engreads@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _injury(db, user, key, value, active=True):
    row = models.UserKnowledgeEntry(user_id=user.id, type="injury", key=key, value=value, source="api",
                                    added_at=date(2026, 7, 1), active=active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _constraint(db, user, key, *, status="confirmed", region="single_leg_hop", side="left", parent=None,
                tier="engine", review_by=FUTURE, kind="block"):
    scope = ({"tier": "engine", "region_keys": [region], **({"side": side} if side else {})}
             if tier == "engine" else {"tier": "advisory", "text": f"text of {key}"})
    value = {"scope": scope, "kind": kind, "exit": {"with_parent": True} if parent else {"on_condition": "cleared"},
             "review_by": review_by, "status": "proposed", "asserted_by": None, **({"parent_key": parent} if parent else {})}
    row = upsert_knowledge_entry(user.id, KnowledgeEntryIn(type="constraint", key=key, value=value, source="api"), db)
    if status == "confirmed":
        row = knowledge_router._confirm_entry(row.id, knowledge_router.ConfirmIn(asserted_by="clinician"),
                                              "constraint", user.id, db)
    return row


def _resolve(db, user, row, basis="not an active restriction; clinician aware"):
    knowledge_router._resolve_entry(row.id, knowledge_router.ResolutionIn(basis=basis, resolved_by="user"),
                                    "constraint", user.id, db)


@pytest.fixture
def world(db_session, monkeypatch):
    u = _user(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_aest_wake_day", lambda *a, **k: TODAY)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    import routers.engine as engine_router

    async def _no_hevy(db, user_id):
        return set()
    monkeypatch.setattr(engine_router, "_loaded_regions", _no_hevy)
    return u


def _run(coro):
    return asyncio.run(coro)


# ── the refactor is output-identical ──────────────────────────────────────────

def _state(db, user, region, side, status):
    db.add(models.CapabilityState(user_id=user.id, region_key=region, side=side, status=status))
    db.commit()


@pytest.mark.parametrize("scenario", ["empty", "hard_stops", "confirmed_block", "tested", "loaded", "all"])
def test_compute_probe_queue_is_identical_to_the_engine_before_the_detail_existed(db_session, scenario):
    u = _user(db_session)
    hs = loaded = None
    profile = None
    if scenario in ("hard_stops", "all"):
        profile = models.FortificationProfile(user_id=u.id, hard_stops=[
            {"region_key": "squat", "side": "left", "reason": "post-op"}])
        db_session.add(profile)
        db_session.commit()
    if scenario in ("confirmed_block", "all"):
        _constraint(db_session, u, "c_hop", region="single_leg_hop", side="left")
        _constraint(db_session, u, "c_hinge", region="hinge", side=None)
    if scenario in ("tested", "all"):
        _state(db_session, u, "hinge", HINGE_SIDES[0], "clean")
        _state(db_session, u, "single_leg_hop", "right", "managed")
    loaded = {"squat", "carry"} if scenario in ("loaded", "all") else set()
    kw = dict(profile=profile, loaded_region_keys=loaded)
    new = selection.compute_probe_queue(db_session, u.id, **kw)
    assert new == BEFORE_DETAIL.compute_probe_queue(db_session, u.id, **kw)
    assert new == selection.probe_queue_detail(db_session, u.id, **kw)["queue"]


# ── queue XOR exclusions, with the engine's own reason ───────────────────────

def test_every_cell_is_either_probeable_or_excluded_with_a_reason(db_session):
    u = _user(db_session)
    _constraint(db_session, u, "c_hop", region="single_leg_hop", side="left")
    _state(db_session, u, "hinge", HINGE_SIDES[0], "clean")
    d = selection.probe_queue_detail(db_session, u.id, profile=None, loaded_region_keys={"carry"})
    queue_cells = {(c["region_key"], c["side"]) for c in d["queue"]}
    out_cells = [(e["region_key"], e["side"]) for e in d["excluded"]]
    assert len(out_cells) == len(set(out_cells))                     # no cell excluded twice
    assert queue_cells.isdisjoint(out_cells)
    assert queue_cells | set(out_cells) == ALL_CELLS
    assert all(e["reason"] and e["kind"] for e in d["excluded"])


def test_the_exclusion_kinds_and_their_reasons(db_session):
    u = _user(db_session)
    _constraint(db_session, u, "c_hop", region="single_leg_hop", side="left")
    _state(db_session, u, "hinge", HINGE_SIDES[0], "clean")
    d = selection.probe_queue_detail(db_session, u.id, profile=None, loaded_region_keys={"carry"})
    by = {(e["region_key"], e["side"]): e for e in d["excluded"]}
    assert by[("single_leg_hop", "left")]["kind"] == "contraindicated"
    assert by[("single_leg_hop", "left")]["reason"] == "constraint c_hop — block"
    assert by[("hinge", HINGE_SIDES[0])] == {"region_key": "hinge", "label": taxonomy.by_key("hinge").label,
                                             "side": HINGE_SIDES[0], "kind": "already_tested",
                                             "reason": "capability state is 'clean'"}
    assert by[("carry", taxonomy.by_key("carry").sides()[0])]["kind"] == "recently_loaded"
    ungrounded = [r for r in taxonomy.all_regions() if not r.queue_eligible]
    assert ungrounded and all(by[(r.key, r.sides()[0])]["kind"] == "not_queue_eligible" for r in ungrounded)
    # the right-side hop is a different cell: not blocked by a left-sided row
    assert ("single_leg_hop", "right") in {(c["region_key"], c["side"]) for c in d["queue"]}


def test_a_profile_hard_stop_is_reported_with_its_own_reason(db_session):
    u = _user(db_session)
    db_session.add(models.FortificationProfile(user_id=u.id, hard_stops=[
        {"region_key": "squat", "side": "left", "reason": "post-op precaution"}]))
    db_session.commit()
    profile = db_session.query(models.FortificationProfile).filter_by(user_id=u.id).one()
    d = selection.probe_queue_detail(db_session, u.id, profile=profile, loaded_region_keys=set())
    [e] = [e for e in d["excluded"] if (e["region_key"], e["side"]) == ("squat", "left")]
    assert (e["kind"], e["reason"]) == ("contraindicated", "post-op precaution")


def test_the_checks_report_in_the_set_expressions_order(db_session):
    """Already tested is reported before contraindicated: a cell that fails both says the first."""
    u = _user(db_session)
    _constraint(db_session, u, "c_hop", region="single_leg_hop", side="left")
    _state(db_session, u, "single_leg_hop", "left", "managed")
    d = selection.probe_queue_detail(db_session, u.id, profile=None, loaded_region_keys=set())
    [e] = [e for e in d["excluded"] if (e["region_key"], e["side"]) == ("single_leg_hop", "left")]
    assert e["kind"] == "already_tested"


# ── get_injuries ──────────────────────────────────────────────────────────────

def test_injuries_lists_the_ledger_with_engine_rows_by_state(db_session, world):
    inj = _injury(db_session, world, "injury_knee_left",
                  {"body_part": "knee", "side": "left", "signal_type": "mechanical",
                   "restrictions": ["deep loaded knee flexion"], "detail": "post-op"})
    _constraint(db_session, world, "c_confirmed", region="deceleration_landing", parent="injury_knee_left")
    p = _constraint(db_session, world, "c_declined", status="proposed", region="single_leg_hop", parent="injury_knee_left")
    _resolve(db_session, world, p)
    _constraint(db_session, world, "c_pending", status="proposed", region="change_of_direction", parent="injury_knee_left")
    _injury(db_session, world, "injury_old", {"body_part": "ankle", "side": "right", "resolution": {
        "resolved_on": "2026-08-25", "resolved_by": "user", "basis": "healed"}}, active=False)

    out = mcp_server.get_injuries()
    assert out.splitlines()[0].startswith("as_of: ")
    assert f"#{inj.id} injury_knee_left — knee / left / mechanical" in out
    assert "restrictions (chat-rendered, gate nothing): deep loaded knee flexion" in out
    assert "constraint rows parented to it: 1 confirmed, 1 proposed, 1 resolved" in out
    assert "injury_old" not in out                                    # active only by default
    both = mcp_server.get_injuries(include_resolved=True)
    assert "injury_old [resolved]" in both and "resolved 2026-08-25 by user: healed" in both


def test_injuries_with_none_says_so(world):
    assert mcp_server.get_injuries().endswith("No active injuries.")


def test_ra_flare_by_restriction_token_is_shown(db_session, world):
    _injury(db_session, world, "injury_hand", {"body_part": "hand", "signal_type": "mechanical",
                                              "restrictions": ["ra_flare"]})
    assert "/ RA flare" in mcp_server.get_injuries()


# ── get_constraints ───────────────────────────────────────────────────────────

@pytest.fixture
def ledger(db_session, world):
    _injury(db_session, world, "injury_knee_left", {"body_part": "knee", "side": "left", "signal_type": "mechanical"})
    confirmed = _constraint(db_session, world, "c_confirmed", region="deceleration_landing", parent="injury_knee_left")
    due = _constraint(db_session, world, "c_due", tier="advisory", review_by=PAST, parent="injury_knee_left", kind="cap")
    pending = _constraint(db_session, world, "c_pending", status="proposed", region="change_of_direction",
                          parent="injury_knee_left")
    declined = _constraint(db_session, world, "c_declined", status="proposed", region="single_leg_hop",
                           parent="injury_knee_left")
    _resolve(db_session, world, declined, basis="running plan has cutting from day one")
    return dict(confirmed=confirmed, due=due, pending=pending, declined=declined)


def test_constraints_open_with_the_pending_count(ledger, world):
    out = mcp_server.get_constraints()
    assert ("Constraints: 2 confirmed, 1 PENDING proposal(s), 1 resolved, 1 confirmed row(s) due for review/exit."
            in out)
    assert "Finding proposals pending confirmation: 0." in out


def test_the_default_lists_active_rows_only_and_marks_a_proposal_as_blocking_nothing(ledger, world):
    out = mcp_server.get_constraints()
    assert "c_confirmed" in out and "c_pending" in out and "c_due" in out
    assert "c_declined" not in out
    pending_line = next(l for l in out.splitlines() if "c_pending" in l)
    assert "[proposed — PENDING, blocks nothing]" in pending_line
    assert "BLOCK (engine-enforced) — regions: change_of_direction, left side only" in pending_line
    assert "(re: injury_knee_left)" in pending_line


def test_a_confirmed_row_shows_authority_and_the_confirm_date(ledger, world):
    line = next(l for l in mcp_server.get_constraints(status="confirmed").splitlines() if "c_confirmed" in l)
    assert f"[confirmed {TODAY.isoformat()}]" in line and "set by your clinician" in line


def test_a_due_row_is_tagged_and_counted(ledger, world):
    line = next(l for l in mcp_server.get_constraints().splitlines() if "c_due" in l)
    assert line.endswith("[REVIEW DUE]")


def test_resolved_shows_the_declined_proposals_basis(ledger, world):
    out = mcp_server.get_constraints(status="resolved")
    line = next(l for l in out.splitlines() if "c_declined" in l)
    assert f"[declined {TODAY.isoformat()} by user]" in line
    assert "basis: running plan has cutting from day one" in line
    assert "c_pending" not in out and "c_confirmed" not in out


def test_a_retired_block_reads_retired_not_declined(db_session, world):
    row = _constraint(db_session, world, "c_ended", region="hinge", side=None)
    _resolve(db_session, world, row, basis="exit fired; the injury healed")
    line = next(l for l in mcp_server.get_constraints(status="resolved").splitlines() if "c_ended" in l)
    assert "[retired " in line and "declined" not in line


def test_a_superseded_row_is_never_listed(db_session, world):
    _constraint(db_session, world, "c_x", status="proposed", region="hinge", side=None)
    _constraint(db_session, world, "c_x", status="proposed", region="carry", side=None)     # same key: supersedes
    out = mcp_server.get_constraints(status="proposed")
    assert out.count("c_x") == 1 and "regions: carry" in out and "regions: hinge" not in out
    assert "0 resolved" in out
    assert "No resolved constraint rows." in mcp_server.get_constraints(status="resolved")


def test_finding_proposals_are_counted_but_a_lab_derived_one_is_not(db_session, world):
    _injury(db_session, world, "injury_x", {"body_part": "finger", "side": "left", "signal_type": "mechanical"})
    base = {"statement": "s", "domain": "injury", "status": "proposed", "parent_key": "injury_x", "as_of": "2026-09-20",
            "basis": {"text": "b", "evidence": [{"door": "document", "ref": "r"}]}, "asserted_by": None}
    for key, labs in (("f_ok", False), ("f_lab", True)):
        upsert_knowledge_entry(world.id, KnowledgeEntryIn(type="finding", key=key, source="chat",
                                                          value={**base, "derived_from_labs": labs}), db_session)
    assert "Finding proposals pending confirmation: 1." in mcp_server.get_constraints()


def test_an_unknown_status_is_refused_by_name(world):
    assert mcp_server.get_constraints(status="active").endswith("one of confirmed, proposed, resolved.")
    with pytest.raises(ValueError):
        engine_reads.constraints_read(None, 1, status="bogus", today=TODAY)


def test_constraints_with_none_says_so(world):
    out = mcp_server.get_constraints()
    assert "Constraints: 0 confirmed, 0 PENDING proposal(s), 0 resolved" in out
    assert "No active (confirmed and proposed) constraint rows." in out


# ── get_probe_queue, and the case this door was built to answer ──────────────

O1 = [("injury_finger_left", {"body_part": "finger", "side": "left", "signal_type": "mechanical"}),
      ("injury_lumbar_spine", {"body_part": "lumbar", "side": "bilateral", "signal_type": "mechanical"}),
      ("injury_thumb_left", {"body_part": "thumb", "side": "left", "signal_type": "mechanical"}),
      ("injury_shoulder_right", {"body_part": "shoulder", "side": "right", "signal_type": "mechanical"}),
      ("injury_knee_left", {"body_part": "knee", "side": "left", "signal_type": "mechanical"}),
      ("injury_cervical_spine", {"body_part": "neck", "side": "bilateral", "signal_type": "neural"})]


def _probeable(out):
    return {(l.split(". ", 1)[1].split(" (")[0], l.split(" (")[1].split(")")[0])
            for l in out.splitlines() if l[:1].isdigit() and ". " in l.split(" — ")[0]}


def test_the_five_regions_the_injuries_used_to_block_are_probeable_for_the_o1_ledger(db_session, world):
    for key, value in O1:
        _injury(db_session, world, key, value)
    out = _run(mcp_server.get_probe_queue())
    assert out.splitlines()[0].startswith("as_of: ")
    assert set(FIVE) <= _probeable(out)
    assert "- none (no confirmed engine-tier constraint row or profile hard-stop covers an untested region)" in out


def test_a_confirmed_row_excludes_exactly_its_cell_and_names_its_key(db_session, world):
    for key, value in O1:
        _injury(db_session, world, key, value)
    _constraint(db_session, world, "constraint_engine_injury_knee_left_single_leg_hop", region="single_leg_hop",
                side="left", parent="injury_knee_left")
    out = _run(mcp_server.get_probe_queue())
    assert "- single_leg_hop (left) — constraint constraint_engine_injury_knee_left_single_leg_hop — block" in out
    assert ("single_leg_hop", "left") not in _probeable(out)
    assert set(FIVE) - {("single_leg_hop", "left")} <= _probeable(out)
    assert ("single_leg_hop", "right") in _probeable(out)


def test_a_proposal_does_not_exclude_anything(db_session, world):
    _constraint(db_session, world, "c_prop", status="proposed", region="single_leg_hop", side="left")
    assert ("single_leg_hop", "left") in _probeable(_run(mcp_server.get_probe_queue()))


def test_loaded_regions_come_from_the_hevy_read_and_are_named(db_session, world, monkeypatch):
    import routers.engine as engine_router

    async def _loaded(db, user_id):
        return {"carry"}
    monkeypatch.setattr(engine_router, "_loaded_regions", _loaded)
    out = _run(mcp_server.get_probe_queue())
    assert "Loaded in recent Hevy workouts (best-effort; empty when Hevy is not connected or the fetch failed): carry" in out
    assert "Excluded: recently loaded" in out


def test_the_output_says_what_it_is_not(world):
    out = _run(mcp_server.get_probe_queue())
    assert "narrow it, so the first entry here is not necessarily the one it suggests" in out


# ── all three: read-only, scoped, registered ─────────────────────────────────

def _snapshot(db):
    db.expire_all()
    return [(r.id, r.type, r.key, r.value, r.active) for r in
            db.query(models.UserKnowledgeEntry).order_by(models.UserKnowledgeEntry.id)]


def test_the_tools_write_nothing(db_session, ledger, world):
    before = _snapshot(db_session)
    n_caps = db_session.query(models.CapabilityState).count()
    mcp_server.get_injuries(include_resolved=True)
    mcp_server.get_constraints()
    mcp_server.get_constraints(status="resolved")
    _run(mcp_server.get_probe_queue())
    assert _snapshot(db_session) == before and db_session.query(models.CapabilityState).count() == n_caps


def test_the_tools_are_scoped_to_the_tokens_user(db_session, ledger, world):
    other = _user(db_session, "someone-else@example.com")
    _injury(db_session, other, "injury_other_persons_hip", {"body_part": "hip", "side": "right", "signal_type": "mechanical"})
    _constraint(db_session, other, "c_other_persons", region="hinge", side=None)
    seen = "\n".join([mcp_server.get_injuries(include_resolved=True), mcp_server.get_constraints(),
                      mcp_server.get_constraints(status="resolved"), _run(mcp_server.get_probe_queue())])
    assert "other_persons" not in seen and "someone-else" not in seen
    assert {("hinge", s) for s in HINGE_SIDES} <= _probeable(_run(mcp_server.get_probe_queue()))   # their block is not mine


def test_the_tools_are_registered_with_their_contracts():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    for name in ("get_injuries", "get_constraints", "get_probe_queue"):
        assert name in tools, name
        assert "read" in (tools[name].description or "").lower()
    assert "status" in tools["get_constraints"].inputSchema["properties"]
    assert "include_resolved" in tools["get_injuries"].inputSchema["properties"]
    assert tools["get_probe_queue"].inputSchema["properties"] == {}
    assert "Loop recommendation leg" in tools["get_probe_queue"].description
