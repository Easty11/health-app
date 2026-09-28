"""The appointment brief (#345) — assembly, modules, surfaces.

Gates, each with its boundary or negative control:
  * each derived-ask rule fires and does not fire at its boundary (review_by exactly +30d / +31d;
    only-condition exit vs dated / with_parent; open provocative/untested vs clear / confirmed);
  * a derived ask on a row an authored ask resolves is FOLDED into it, not repeated;
  * proposed rows, lab-derived findings (not even a count) and out-of-scope rows never render;
  * an appointment with no asks still renders every section coherently;
  * each kind's default list; add/drop; options only as authored; request only with its block;
  * background never reads free-text `user_knowledge`;
  * ONE assembly function feeds the route and the MCP (same object).

SYNTHETIC fixtures only: placeholder parts, conditions and statements (the repo is public).
"""
import copy
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

import appointment_brief as ab
import mcp_server
import models
from auth import get_current_user
from database import get_db
from routers import appointments as appointments_router
from routers.knowledge import (
    APPOINTMENT_DEFAULT_SECTIONS, KnowledgeEntryIn, ResolutionIn, _resolve_entry,
    upsert_knowledge_entry,
)

AT = "2026-01-15T13:00"          # appointment date 2026-01-15 → review horizon 2026-02-14
SINCE = "2025-12-01"
IN = "injury_part_a_left"        # in scope
OUT = "injury_part_b_right"      # active, NOT in scope
GONE = "injury_part_c_left"      # resolved since `since`, in scope


def _user(db, email="brief@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _put(db, uid, type_, key, value, added_at=date(2025, 11, 1)):
    row = upsert_knowledge_entry(uid, KnowledgeEntryIn(type=type_, key=key, value=value, source="api"), db)
    row.added_at = added_at
    db.commit()
    return row


def _injury(db, uid, key, part, side="left", **kw):
    return _put(db, uid, "injury", key, {"body_part": part, "side": side, "signal_type": "mechanical",
                                         "restrictions": [f"{part} movement"], "detail": f"{part} detail"}, **kw)


def _constraint(parent=IN, review_by="2026-03-01", exit_=None, status="confirmed", **over):
    v = {"scope": {"tier": "advisory", "text": "cap on movement A"}, "kind": "cap",
         "parent_key": parent, "exit": exit_ or {"on_date": "2026-04-01"},
         "review_by": review_by, "status": status,
         "asserted_by": "user" if status == "confirmed" else None}
    v.update(over)
    return v


def _finding(parent=IN, status="open", marker=None, as_of="2025-12-10", labs=False, **over):
    v = {"statement": "Synthetic finding", "domain": "injury", "status": status, "parent_key": parent,
         "as_of": as_of, "basis": {"text": "synthetic basis"}, "derived_from_labs": labs,
         "asserted_by": None if status == "proposed" else "user"}
    if marker:
        v["marker_status"] = marker
    v.update(over)
    return v


def _appt(**over):
    v = {"clinician": "Clinician A", "practice": "Practice A", "at": AT, "kind": "follow_up",
         "since": SINCE, "scope": {"parent_keys": [IN, GONE]},
         "asks": [], "logistics": ["Bring report A"], "status": "planned"}
    v.update(over)
    return v


@pytest.fixture
def world(db_session):
    """One user: injury IN (active, in scope), OUT (active, out of scope), GONE (resolved since)."""
    u = _user(db_session)
    _injury(db_session, u.id, IN, "part a")
    _injury(db_session, u.id, OUT, "part b", side="right")
    gone = _injury(db_session, u.id, GONE, "part c")
    _resolve_entry(gone.id, ResolutionIn(basis="synthetic clearance", resolved_by="clinician",
                                         resolved_on="2025-12-20"), "injury", u.id, db_session)
    return u


def _brief(db, uid, key="appt_a", **over):
    _put(db, uid, "appointment", key, _appt(**over))
    return ab.load_appointment_brief(db, uid, key)


def _section(brief, module):
    return next((s for s in brief["sections"] if s["module"] == module), None)


def _derived(brief):
    return _section(brief, "asks")["derived"]


# ── derived asks: each rule at its boundary ───────────────────────────────────

def test_review_due_fires_at_plus_30_and_not_at_plus_31(db_session, world):
    _put(db_session, world.id, "constraint", "c_30", _constraint(review_by="2026-02-14"))
    _put(db_session, world.id, "constraint", "c_31", _constraint(review_by="2026-02-15"))
    _put(db_session, world.id, "constraint", "c_past", _constraint(review_by="2025-12-31"))
    _put(db_session, world.id, "finding", "f_30", _finding(review_by="2026-02-14"))
    _put(db_session, world.id, "finding", "f_31", _finding(review_by="2026-02-15"))
    due = {(d["rule"], d["entry_key"]) for d in _derived(_brief(db_session, world.id))}
    assert ("review_due", "c_30") in due and ("review_due", "c_past") in due and ("review_due", "f_30") in due
    assert ("review_due", "c_31") not in due and ("review_due", "f_31") not in due


def test_undated_exit_fires_only_when_the_condition_is_the_only_exit(db_session, world):
    _put(db_session, world.id, "constraint", "c_cond", _constraint(exit_={"on_condition": "condition A"}))
    _put(db_session, world.id, "constraint", "c_cond_dated",
         _constraint(exit_={"on_condition": "condition B", "on_date": "2026-05-01"}))
    _put(db_session, world.id, "constraint", "c_cond_parent",
         _constraint(exit_={"on_condition": "condition C", "with_parent": True}))
    d = [x for x in _derived(_brief(db_session, world.id)) if x["rule"] == "undated_exit"]
    assert [x["entry_key"] for x in d] == ["c_cond"]
    assert d[0]["text"] == "Confirm or date the exit condition: condition A" and d[0]["source"] == "ledger"


def test_unsettled_marker_fires_for_open_provocative_and_untested_only(db_session, world):
    _put(db_session, world.id, "finding", "f_prov", _finding(marker="provocative"))
    _put(db_session, world.id, "finding", "f_untested", _finding(marker="untested"))
    _put(db_session, world.id, "finding", "f_clear", _finding(marker="clear"))
    _put(db_session, world.id, "finding", "f_conf", _finding(status="confirmed", marker="provocative"))
    keys = {x["entry_key"] for x in _derived(_brief(db_session, world.id)) if x["rule"] == "unsettled_marker"}
    assert keys == {"f_prov", "f_untested"}


def test_a_derived_ask_on_an_authored_asks_row_is_folded_not_repeated(db_session, world):
    _put(db_session, world.id, "constraint", "c_cond", _constraint(exit_={"on_condition": "condition A"}))
    _put(db_session, world.id, "finding", "f_prov", _finding(marker="provocative"))
    b = _brief(db_session, world.id, asks=[
        {"id": "a1", "text": "Settle the cap", "priority": 1,
         "resolves": {"entry_key": "c_cond", "note": "note A"}}])
    asks = _section(b, "asks")
    a1 = asks["authored"][0]
    assert [d["entry_key"] for d in a1["folded"]] == ["c_cond"]
    assert a1["resolves"]["row"]["key"] == "c_cond" and "condition A" in a1["resolves"]["row"]["exit"]
    assert a1["resolves"]["row"]["review_by"] == "2026-03-01"
    assert [d["entry_key"] for d in asks["derived"]] == ["f_prov"]


def test_resolves_row_outside_scope_is_not_shown(db_session, world):
    _put(db_session, world.id, "constraint", "c_out", _constraint(parent=OUT))
    b = _brief(db_session, world.id, asks=[
        {"id": "a1", "text": "Ask", "priority": 1, "resolves": {"entry_key": "c_out", "note": None}}])
    assert _section(b, "asks")["authored"][0]["resolves"]["row"] is None
    assert "cap on movement A" not in json.dumps(b)


# ── hard exclusions ───────────────────────────────────────────────────────────

def test_proposed_rows_never_render(db_session, world):
    _put(db_session, world.id, "constraint", "c_prop", _constraint(status="proposed", review_by="2026-01-20",
                                                                    exit_={"on_condition": "x"}))
    _put(db_session, world.id, "finding", "f_prop", _finding(status="proposed", marker="provocative",
                                                              statement="PROPOSAL TEXT"))
    dump = json.dumps(_brief(db_session, world.id))
    assert "c_prop" not in dump and "f_prop" not in dump and "PROPOSAL TEXT" not in dump


def test_lab_derived_findings_never_render_not_even_as_a_count(db_session, world):
    _put(db_session, world.id, "finding", "f_lab", _finding(labs=True, marker="provocative", statement="LAB TEXT"))
    b = _brief(db_session, world.id)
    dump = json.dumps(b)
    assert "f_lab" not in dump and "LAB TEXT" not in dump and "withheld" not in dump


def test_nothing_outside_scope_renders(db_session, world):
    _put(db_session, world.id, "constraint", "c_out", _constraint(parent=OUT, exit_={"on_condition": "x"}))
    _put(db_session, world.id, "finding", "f_out", _finding(parent=OUT, marker="provocative"))
    b = _brief(db_session, world.id, sections={"add": ["background", "imaging_timeline"]})
    dump = json.dumps(b)
    assert OUT not in dump
    assert "c_out" not in dump and "f_out" not in dump and "part b" not in dump


def test_grandchildren_are_not_read(db_session, world):
    _put(db_session, world.id, "constraint", "c_child", _constraint())
    _put(db_session, world.id, "finding", "f_grandchild", _finding(parent="c_child", marker="provocative"))
    assert "f_grandchild" not in json.dumps(_brief(db_session, world.id))


# ── coherence ─────────────────────────────────────────────────────────────────

def test_an_empty_asks_follow_up_still_renders_every_section(db_session, world):
    b = _brief(db_session, world.id)
    assert [s["module"] for s in b["sections"]] == [
        m for m in APPOINTMENT_DEFAULT_SECTIONS["follow_up"] if m != "options_prep"]
    assert _section(b, "header")["clinician"] == "Clinician A" and _section(b, "header")["time"] == "13:00"
    assert _section(b, "leave_with") == {"module": "leave_with", "items": [], "total": 0}
    assert _section(b, "asks") == {"module": "asks", "authored": [], "derived": []}
    assert _section(b, "current_constraints")["items"] == []
    assert _section(b, "logistics")["items"] == ["Bring report A"]
    assert b["audience"] == "operator" and b["scope"]["hops"] == 1


def test_leave_with_is_the_first_five_by_priority(db_session, world):
    asks = [{"id": f"a{p}", "text": f"Ask {p}", "priority": p} for p in (7, 3, 1, 6, 2, 5, 4)]
    b = _brief(db_session, world.id, asks=asks)
    lw = _section(b, "leave_with")
    assert [i["priority"] for i in lw["items"]] == [1, 2, 3, 4, 5] and lw["total"] == 7
    assert [a["priority"] for a in _section(b, "asks")["authored"]] == [1, 2, 3, 4, 5, 6, 7]


def test_since_and_changes_vs_history(db_session, world):
    # A finding rewritten since the last visit, over an open predecessor and a chat proposal.
    _put(db_session, world.id, "finding", "f_chain", _finding(statement="Statement v1", as_of="2025-11-01"))
    _put(db_session, world.id, "finding", "f_chain", _finding(statement="Statement v2", as_of="2025-12-05"))
    _put(db_session, world.id, "finding", "f_old", _finding(statement="Old statement", as_of="2025-11-15"))
    _put(db_session, world.id, "constraint", "c_new", _constraint(), added_at=date(2025, 12, 3))
    _put(db_session, world.id, "constraint", "c_before", _constraint(), added_at=date(2025, 11, 3))
    gone_c = _put(db_session, world.id, "constraint", "c_gone", _constraint(parent=IN))
    _resolve_entry(gone_c.id, ResolutionIn(basis="lifted", resolved_by="user", resolved_on="2025-12-12"),
                   "constraint", world.id, db_session)
    b = _brief(db_session, world.id)

    since = _section(b, "since")
    assert since["since"] == SINCE
    assert [(i["key"], i["change"], i["on"]) for i in since["injuries"]] == [(GONE, "resolved", "2025-12-20")]
    assert [f["key"] for f in since["findings"]] == ["f_chain"]
    assert {(c["key"], c["change"]) for c in since["constraints"]} == {("c_new", "confirmed"), ("c_gone", "resolved")}

    chv = _section(b, "changes_vs_history")
    assert [(f["key"], f["text"], [p["statement"] for p in f["previous"]]) for f in chv["findings"]] == [
        ("f_chain", "Statement v2", ["Statement v1"])]
    assert [(i["key"], i["before"], i["after"]) for i in chv["injuries"]] == [(GONE, "active", "resolved 2025-12-20")]


def test_a_superseded_proposal_is_not_history(db_session, world):
    _put(db_session, world.id, "finding", "f_chain", _finding(status="proposed", statement="PROPOSED V1"))
    _put(db_session, world.id, "finding", "f_chain", _finding(statement="Statement v2"))
    chv = _section(_brief(db_session, world.id), "changes_vs_history")
    assert chv["findings"][0]["previous"] == []


def test_an_injury_rewritten_since_shows_before_and_after(db_session, world):
    _put(db_session, world.id, "injury", IN, {"body_part": "part a", "side": "left", "signal_type": "mechanical",
                                               "restrictions": [], "detail": "part a detail v2"},
         added_at=date(2025, 12, 8))
    chv = _section(_brief(db_session, world.id), "changes_vs_history")
    assert (IN, "part a detail", "part a detail v2") in [(i["key"], i["before"], i["after"]) for i in chv["injuries"]]


def test_current_constraints_are_confirmed_in_scope_with_tier_exit_review(db_session, world):
    _put(db_session, world.id, "constraint", "c1", _constraint(exit_={"on_condition": "condition A"}))
    _put(db_session, world.id, "constraint", "c_prop", _constraint(status="proposed"))
    items = _section(_brief(db_session, world.id), "current_constraints")["items"]
    assert [(c["key"], c["tier"], c["kind"], c["exit"], c["review_by"]) for c in items] == [
        ("c1", "advisory", "cap", "when condition A", "2026-03-01")]


# ── kinds and overrides ───────────────────────────────────────────────────────

@pytest.mark.parametrize("kind,extra,audience", [
    ("follow_up", {}, "operator"),
    ("intro", {}, "clinician"),
    ("request", {"request": {"ask": "Referral A", "justification": "Reason A"}}, "operator"),
])
def test_each_kind_renders_its_default_list(db_session, world, kind, extra, audience):
    asks = [{"id": "a1", "text": "Ask", "priority": 1, "options": [{"option": "If A", "implication": "Then B"}]}]
    b = _brief(db_session, world.id, kind=kind, asks=asks, **extra)
    assert [s["module"] for s in b["sections"]] == list(APPOINTMENT_DEFAULT_SECTIONS[kind])
    assert b["audience"] == audience and b["kind"] == kind


def test_add_and_drop_override_the_default_list(db_session, world):
    b = _brief(db_session, world.id, sections={"add": ["background"], "drop": ["since", "logistics"]})
    assert [s["module"] for s in b["sections"]] == [
        "header", "leave_with", "changes_vs_history", "asks", "current_constraints", "background"]


def test_audience_override(db_session, world):
    assert _brief(db_session, world.id, audience="clinician")["audience"] == "clinician"


def test_options_render_only_as_authored(db_session, world):
    b = _brief(db_session, world.id, asks=[
        {"id": "a1", "text": "Ask one", "priority": 2},
        {"id": "a2", "text": "Ask two", "priority": 1,
         "options": [{"option": "Answer X", "implication": "Meaning Y"}]}])
    assert _section(b, "options_prep") == {"module": "options_prep", "items": [
        {"ask_id": "a2", "text": "Ask two", "options": [{"option": "Answer X", "implication": "Meaning Y"}]}]}
    assert _section(_brief(db_session, world.id, key="appt_b"), "options_prep") is None


def test_request_module_renders_its_block(db_session, world):
    b = _brief(db_session, world.id, kind="request", request={
        "ask": "Referral A", "justification": "Reason A",
        "evidence": [{"door": "document", "ref": "doc-a"}], "alternatives": ["Option B"]})
    assert _section(b, "request") == {"module": "request", "ask": "Referral A", "justification": "Reason A",
                                      "evidence": [{"door": "document", "ref": "doc-a"}],
                                      "alternatives": ["Option B"]}


def test_imaging_timeline_lists_document_refs_in_date_order(db_session, world):
    _put(db_session, world.id, "finding", "f_late", _finding(as_of="2025-12-20", basis={"evidence": [
        {"door": "document", "ref": "doc-late"}, {"door": "counted_workouts", "ref": "2025-12-19"}]}))
    _put(db_session, world.id, "finding", "f_early", _finding(as_of="2025-10-01", basis={"evidence": [
        {"door": "document", "ref": "doc-early"}]}))
    items = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert [i["ref"] for i in items] == ["doc-early", "doc-late"]


def test_background_is_the_ledger_and_confirmed_findings_only(db_session, world):
    _put(db_session, world.id, "finding", "f_conf", _finding(status="confirmed", statement="Confirmed A"))
    _put(db_session, world.id, "finding", "f_open", _finding(statement="Open A"))
    bg = _section(_brief(db_session, world.id, kind="intro"), "background")
    assert [i["key"] for i in bg["injuries"]] == [IN, GONE]
    assert [(i["status"], i["resolved_on"]) for i in bg["injuries"]] == [("active", None), ("resolved", "2025-12-20")]
    assert [f["key"] for f in bg["findings"]] == ["f_conf"]


def test_the_brief_never_reads_free_text_user_knowledge(db_session, world):
    db_session.add(models.UserKnowledge(user_id=world.id, category="Other", content="FREE TEXT SENTINEL"))
    db_session.commit()
    _put(db_session, world.id, "appointment", "appt_i", _appt(kind="intro", sections={"add": ["background"]}))
    uid = world.id   # read before capture: an expired `world` would refresh through `users`
    statements = []
    engine = db_session.get_bind()

    def _capture(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        b = ab.load_appointment_brief(db_session, uid, "appt_i")
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    assert statements, "the capture saw no query — the negative below would pass vacuously"
    assert not any("user_knowledge " in s or "user_knowledge\n" in s or s.rstrip().endswith("user_knowledge")
                   for s in statements)
    assert all("user_knowledge_entries" in s for s in statements)
    assert "FREE TEXT SENTINEL" not in json.dumps(b)


def test_modules_are_pure_over_the_context(db_session, world):
    """Each module is callable alone over one `BriefContext` (no session in reach)."""
    _put(db_session, world.id, "constraint", "c1", _constraint())
    rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=world.id).all()
    from current_state import CurrentState
    import typed_entries
    active = [r for r in rows if r.active]
    state = CurrentState(constraints=typed_entries.lift_constraints(active),
                         findings=typed_entries.lift_findings(active))
    ctx = ab.scope_context({"key": "k", "value": _appt()}, state, rows)
    for name, fn in ab.MODULES.items():
        out = fn(ctx)
        assert out is None or isinstance(out, dict), name
    assert ab.module_current_constraints(ctx)["items"][0]["key"] == "c1"


# ── surfaces: one assembly for the route and the MCP ─────────────────────────

def _client(db, user):
    app = FastAPI()
    app.include_router(appointments_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_route_and_mcp_return_the_same_object(db_session, world, monkeypatch):
    _put(db_session, world.id, "constraint", "c_cond", _constraint(exit_={"on_condition": "condition A"}))
    _put(db_session, world.id, "appointment", "appt_a", _appt(asks=[{"id": "a1", "text": "Ask", "priority": 1}]))
    route = _client(db_session, world).get("/appointments/appt_a/brief")
    assert route.status_code == 200
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: world.id)
    out = mcp_server.get_appointment_brief("appt_a")
    assert out.startswith("as_of: ")
    mcp_obj = json.loads(out.split("\n\n", 1)[1])
    assert mcp_obj == route.json() == ab.load_appointment_brief(db_session, world.id, "appt_a")


def test_one_assembly_function_behind_both_surfaces(db_session, world, monkeypatch):
    calls = []
    real = ab.build_appointment_brief
    monkeypatch.setattr(ab, "build_appointment_brief", lambda *a: calls.append(1) or real(*a))
    _put(db_session, world.id, "appointment", "appt_a", _appt())
    _client(db_session, world).get("/appointments/appt_a/brief")
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: world.id)
    mcp_server.get_appointment_brief("appt_a")
    assert len(calls) == 2


def test_unknown_or_inactive_key_is_404(db_session, world, monkeypatch):
    c = _client(db_session, world)
    assert c.get("/appointments/nope/brief").status_code == 404
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: world.id)
    assert "No active appointment" in mcp_server.get_appointment_brief("nope")


def test_another_users_appointment_is_404(db_session, world):
    _put(db_session, world.id, "appointment", "appt_a", _appt())
    other = _user(db_session, "other@example.com")
    assert _client(db_session, other).get("/appointments/appt_a/brief").status_code == 404


def test_list_filters_by_status_soonest_first(db_session, world):
    _put(db_session, world.id, "appointment", "appt_late", _appt(at="2026-02-01T09:00"))
    _put(db_session, world.id, "appointment", "appt_soon", _appt(at="2026-01-10T09:00"))
    _put(db_session, world.id, "appointment", "appt_done", _appt(status="closed"))
    c = _client(db_session, world)
    assert [a["key"] for a in c.get("/appointments", params={"status": "planned"}).json()] == [
        "appt_soon", "appt_late"]
    assert len(c.get("/appointments").json()) == 3
    assert c.get("/appointments", params={"status": "maybe"}).status_code == 422
