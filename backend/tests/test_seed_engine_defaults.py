"""The operator seed script for engine-default proposals — PR1 of "Engine blocks are rows".

Built against the O1 ledger (operator-reported prod read, user 1, 2 Nov 2026: ids 77, 94, 101, 118,
119, 120) with the verbatim lumbar restrictions from `test_injury_sweep_prod_fixture`. THE FIXTURE
EXPECTATION the operator's dry-run is reviewed against:
  * 118 injury_shoulder_right → vertical_push, horizontal_push, side right;
  * 119 injury_knee_left      → single_leg_hop, change_of_direction, deceleration_landing, side left;
  * 77, 94, 101, 120 seed nothing (94 is typed `mechanical`; 120 is a cervical neural entry);
  => 5 planned, 0 skipped, 0 conflicts. A mismatch on the real ledger is reported, not fixed.

Gates: dry-run writes nothing; --confirm writes the plan as PROPOSALS in one transaction (all or
none); re-running is a no-op; a declined (resolved) default is never re-created; a key clash is a
conflict, not a write; the injury rows are untouched; and an advisory cap on the same injury is
printed beside the rows it may contradict (#344).
"""
import importlib.util
import os
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from engine import selection
from load_metrics import _local_day
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry
from test_injury_sweep_prod_fixture import LUMBAR_94

_SPEC = importlib.util.spec_from_file_location(
    "seed_engine_defaults",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "seed_engine_defaults.py"))
seed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed)

REVIEW = _local_day() + timedelta(days=60)

O1_ROWS = [   # id, key, value — as reported; 94 carries the verbatim prod restrictions
    (77, "injury_finger_left", {"body_part": "finger", "side": "left", "signal_type": "mechanical"}),
    (94, "injury_lumbar_spine", {**LUMBAR_94, "side": "bilateral"}),
    (101, "injury_thumb_left", {"body_part": "thumb", "side": "left", "signal_type": "mechanical"}),
    (118, "injury_shoulder_right", {"body_part": "shoulder", "side": "right", "signal_type": "mechanical"}),
    (119, "injury_knee_left", {"body_part": "knee", "side": "left", "signal_type": "mechanical"}),
    (120, "injury_cervical_spine", {"body_part": "neck", "side": "bilateral", "signal_type": "neural"}),
]


def _client(db, user):
    app = FastAPI()
    app.include_router(knowledge_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _row(db, **kw):
    row = models.UserKnowledgeEntry(type="injury", source="system", added_at=date(2026, 7, 1), **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def ledger(db_session):
    u = models.User(email="seedeng@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    # Resolved in prod (ids 18, 29): inactive, so never iterated
    _row(db_session, id=18, user_id=u.id, key="injury_hamstring_left", active=False,
         value={"body_part": "hamstring", "side": "left", "signal_type": "mechanical"})
    _row(db_session, id=29, user_id=u.id, key="injury_hamstring_right", active=False,
         value={"body_part": "hamstring", "side": "right", "signal_type": "mechanical"})
    for id_, key, value in O1_ROWS:
        _row(db_session, id=id_, user_id=u.id, key=key, active=True, value=value)
    return {"db": db_session, "user": u}


class _NoClose:
    """The test session outlives the script's `finally: db.close()`."""
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


def _run(ledger, *flags, review=str(REVIEW)):
    db = ledger["db"]
    return seed.main([str(ledger["user"].id), "--review-by", review, *flags],
                     db_factory=lambda: _NoClose(db))


def _snapshot(db):
    db.expire_all()
    return [(r.id, r.type, r.key, r.value, r.active) for r in
            db.query(models.UserKnowledgeEntry).order_by(models.UserKnowledgeEntry.id)]


def _constraints(db, uid, active=None):
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, type="constraint").all()
    return [r for r in rows if active is None or r.active == active]


# ── the fixture expectation ───────────────────────────────────────────────────

def test_the_o1_ledger_plan_is_the_expected_five(ledger):
    plan = seed.plan_seed(ledger["db"], ledger["user"].id, REVIEW)
    assert [i["entry_id"] for i in plan["injuries"]] == [77, 94, 101, 118, 119, 120]
    got = sorted((p["parent_key"], p["region_key"], p["side"]) for p in plan["planned"])
    assert got == sorted([
        ("injury_shoulder_right", "vertical_push", "right"),
        ("injury_shoulder_right", "horizontal_push", "right"),
        ("injury_knee_left", "single_leg_hop", "left"),
        ("injury_knee_left", "change_of_direction", "left"),
        ("injury_knee_left", "deceleration_landing", "left"),
    ])
    assert plan["skipped"] == [] and plan["conflicts"] == []
    assert not any(p["parent_key"].startswith("injury_hamstring") for p in plan["planned"])   # ids 18, 29
    per = {i["entry_id"]: i["planned"] for i in plan["injuries"]}
    assert per == {77: 0, 94: 0, 101: 0, 118: 2, 119: 3, 120: 0}


def test_each_planned_value_is_a_proposal_at_the_given_review_date(ledger):
    for p in seed.plan_seed(ledger["db"], ledger["user"].id, REVIEW)["planned"]:
        v = p["value"]
        assert (v["status"], v["asserted_by"], v["kind"], v["exit"]) == ("proposed", None, "block", {"with_parent": True})
        assert v["review_by"] == REVIEW.isoformat() and v["scope"]["tier"] == "engine"
        assert p["key"] == f"constraint_engine_{p['parent_key']}_{p['region_key']}"


# ── dry-run / confirm ─────────────────────────────────────────────────────────

def test_dry_run_writes_nothing_and_prints_the_plan(ledger, capsys):
    before = _snapshot(ledger["db"])
    assert _run(ledger, "--dry-run") == 0
    assert _snapshot(ledger["db"]) == before
    out = capsys.readouterr().out
    assert "PLANNED (5)" in out and "SKIPPED (0)" in out and "CONFLICTS (0)" in out
    assert "DRY RUN — nothing written." in out
    assert "injury_shoulder_right → vertical_push, right" in out
    assert "injury_knee_left → deceleration_landing, left" in out
    assert "#94 injury_lumbar_spine: lumbar / bilateral / mechanical — 0 planned" in out
    assert "#120 injury_cervical_spine: neck / bilateral / neural — 0 planned" in out


def test_confirm_writes_proposals_the_engine_does_not_read(ledger, capsys):
    db, uid = ledger["db"], ledger["user"].id
    injuries_before = [r for r in _snapshot(db) if r[1] == "injury"]
    assert _run(ledger, "--confirm") == 0
    assert "WROTE 5 proposal(s)" in capsys.readouterr().out
    rows = _constraints(db, uid)
    assert len(rows) == 5 and all(r.active and r.source == "system" for r in rows)
    assert all(r.value["status"] == "proposed" and r.value["asserted_by"] is None for r in rows)
    assert all("scripts/seed_engine_defaults.py" in r.notes for r in rows)
    assert selection.gather_active_constraints(db, uid) == []            # a proposal blocks nothing
    assert [r for r in _snapshot(db) if r[1] == "injury"] == injuries_before     # injuries untouched
    assert len(_client(db, ledger["user"]).get("/knowledge/proposals").json()) == 5   # and the card lists them


def test_rerunning_confirm_is_a_no_op(ledger, capsys):
    db, uid = ledger["db"], ledger["user"].id
    _run(ledger, "--confirm")
    capsys.readouterr()
    before = _snapshot(db)
    assert _run(ledger, "--confirm") == 0
    out = capsys.readouterr().out
    assert "WROTE 0 proposal(s)" in out and "PLANNED (0)" in out and "SKIPPED (5)" in out
    assert _snapshot(db) == before


def test_a_declined_default_is_never_re_created(ledger, capsys):
    db, uid = ledger["db"], ledger["user"].id
    _run(ledger, "--confirm")
    target = next(r for r in _constraints(db, uid) if r.key.endswith("injury_knee_left_change_of_direction"))
    knowledge_router._resolve_entry(
        target.id, knowledge_router.ResolutionIn(basis="running plan has cutting from day one", resolved_by="user"),
        "constraint", uid, db)
    capsys.readouterr()
    assert _run(ledger, "--confirm") == 0
    out = capsys.readouterr().out
    assert "WROTE 0 proposal(s)" in out and "resolved/superseded" in out
    assert [r for r in _constraints(db, uid, active=True) if r.key == target.key] == []


def test_the_injury_write_path_and_the_script_agree(ledger, capsys):
    """Rows the write path already proposed are not proposed again by the script; rows the path never
    saw (the directly-written ledger) still are — the coverage gap the script exists for."""
    db, uid = ledger["db"], ledger["user"].id
    upsert_knowledge_entry(uid, KnowledgeEntryIn(
        type="injury", key="injury_ankle_left", source="chat",
        value={"body_part": "ankle", "side": "left", "signal_type": "mechanical"}), db)
    assert len(_constraints(db, uid)) == 3                  # the write path proposed the ankle set
    plan = seed.plan_seed(db, uid, REVIEW)
    assert len(plan["planned"]) == 5 and not any(p["parent_key"] == "injury_ankle_left" for p in plan["planned"])
    assert len(plan["skipped"]) == 3 and all(s["parent_key"] == "injury_ankle_left" for s in plan["skipped"])


def test_a_key_clash_is_reported_not_written(ledger, capsys):
    db, uid = ledger["db"], ledger["user"].id
    clash = "constraint_engine_injury_shoulder_right_vertical_push"
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="constraint", key=clash, value={
        "scope": {"tier": "advisory", "text": "squatting on the key"}, "kind": "block",
        "exit": {"on_condition": "cleared"}, "review_by": "2027-01-01",
        "status": "confirmed", "asserted_by": "user"}, source="api"), db)
    assert _run(ledger, "--confirm") == 0
    out = capsys.readouterr().out
    assert "CONFLICTS (1)" in out and f"{clash} is held by active row" in out and "WROTE 4 proposal(s)" in out


def test_confirm_is_all_or_nothing(ledger, monkeypatch):
    db, uid = ledger["db"], ledger["user"].id
    real = seed._stage_upsert_entry
    calls = []

    def flaky(user_id, entry_in, session):
        calls.append(entry_in.key)
        if len(calls) == 3:
            raise RuntimeError("write fault")
        return real(user_id, entry_in, session)
    monkeypatch.setattr(seed, "_stage_upsert_entry", flaky)
    before = _snapshot(db)
    with pytest.raises(RuntimeError):
        _run(ledger, "--confirm")
    assert len(calls) == 3
    assert _snapshot(db) == before and _constraints(db, uid) == []


def test_an_advisory_cap_on_the_same_injury_is_printed_beside_its_rows(ledger, capsys):
    """#344: a limit on a region still being trained is an advisory cap, never an engine block — if a
    default may contradict one, the dry-run says so beside the row."""
    db, uid = ledger["db"], ledger["user"].id
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="constraint", key="constraint_shoulder_right_er_load_cap", value={
        "scope": {"tier": "advisory", "text": "right shoulder ER capped at 9.5 kg"}, "kind": "cap",
        "parent_key": "injury_shoulder_right", "exit": {"on_condition": "Dr Aubrey reviews posterior shoulder pain"},
        "review_by": "2026-12-14", "status": "confirmed", "asserted_by": "clinician"}, source="api"), db)
    # an unrelated advisory cap (other body part) and a non-cap advisory row must NOT be flagged
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="constraint", key="constraint_lumbar_cap", value={
        "scope": {"tier": "advisory", "text": "lumbar loading capped"}, "kind": "cap",
        "parent_key": "injury_lumbar_spine", "exit": {"with_parent": True},
        "review_by": "2026-12-14", "status": "confirmed", "asserted_by": "user"}, source="api"), db)
    assert _run(ledger, "--dry-run") == 0
    out = capsys.readouterr().out
    shoulder = [l for l in out.splitlines() if "NOTE advisory cap" in l]
    assert len(shoulder) == 2                                               # one per shoulder row
    assert all("constraint_shoulder_right_er_load_cap" in l and "same injury" in l for l in shoulder)
    knee_block = out.split("injury_knee_left → single_leg_hop")[1].split("\n")[1]
    assert "NOTE" not in knee_block                                         # no cross-injury noise


def test_the_overlap_match_is_by_whole_word(ledger):
    db, uid = ledger["db"], ledger["user"].id
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="constraint", key="c_free", value={
        "scope": {"tier": "advisory", "text": "no kneeling hip hinge"}, "kind": "cap",
        "exit": {"on_condition": "reviewed"}, "review_by": "2026-12-14",
        "status": "confirmed", "asserted_by": "user"}, source="api"), db)
    assert seed.advisory_cap_overlaps(db, uid, "injury_knee_left", "knee") == []
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="constraint", key="c_free2", value={
        "scope": {"tier": "advisory", "text": "knee flexion under 90"}, "kind": "cap",
        "exit": {"on_condition": "reviewed"}, "review_by": "2026-12-14",
        "status": "confirmed", "asserted_by": "user"}, source="api"), db)
    assert [o["key"] for o in seed.advisory_cap_overlaps(db, uid, "injury_knee_left", "knee")] == ["c_free2"]


# ── argument handling ─────────────────────────────────────────────────────────

def test_exactly_one_of_dry_run_and_confirm(ledger, capsys):
    assert _run(ledger) == 2
    assert _run(ledger, "--dry-run", "--confirm") == 2
    assert "there is no default write" in capsys.readouterr().out
    assert _constraints(ledger["db"], ledger["user"].id) == []


def test_a_past_or_malformed_review_date_is_refused(ledger, capsys):
    assert _run(ledger, "--confirm", review=(_local_day() - timedelta(days=1)).isoformat()) == 2
    assert _run(ledger, "--confirm", review="soon") == 2
    assert seed.main(["1", "--dry-run"]) == 2
    assert _constraints(ledger["db"], ledger["user"].id) == []


def test_another_users_injuries_are_not_planned(ledger, db_session):
    other = models.User(email="elsewhere@example.com", hashed_password="x")
    db_session.add(other)
    db_session.commit()
    _row(db_session, user_id=other.id, key="injury_shoulder_right", active=True,
         value={"body_part": "shoulder", "side": "left"})
    plan = seed.plan_seed(db_session, ledger["user"].id, REVIEW)
    assert {p["side"] for p in plan["planned"] if p["parent_key"] == "injury_shoulder_right"} == {"right"}
