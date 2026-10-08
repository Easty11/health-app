"""The appointment brief (#345) — assembly, modules, surfaces.

Gates, each with its boundary or negative control:
  * each derived-ask rule fires and does not fire at its boundary (review_by exactly +30d / +31d;
    only-condition exit vs dated / with_parent; open provocative/untested vs clear / confirmed);
  * a derived ask on a row an authored ask resolves is FOLDED into it, not repeated;
  * proposed rows, lab-derived findings (not even a count) and out-of-scope rows never render;
  * an appointment with no asks still renders every section coherently;
  * each row renders ONCE (#348): Leave with is a pointer list (first sentence, no full text);
    `since` yields findings and injury status changes to `changes_vs_history`, drops a constraint a
    derived ask already names, and renders nothing when empty — but keeps them when the owning
    module is not in the brief;
  * statements render in full (no 280-char cap); injury labels are human words;
  * an authored ask whose `resolves` row cannot be shown is flagged `unresolved`, not dropped;
  * neutral framing (#349): derived asks are open questions, never a presumed gate or instruction,
    and every constraint/finding row carries its `asserted_by` authority;
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
    assert d[0]["text"] == "Does this condition still apply? condition A" and d[0]["source"] == "ledger"


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
    # options_prep: no options authored. since: its only row (GONE resolved) belongs to
    # changes_vs_history, so it renders nothing.
    assert [s["module"] for s in b["sections"]] == [
        m for m in APPOINTMENT_DEFAULT_SECTIONS["follow_up"] if m not in ("options_prep", "since")]
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


def test_leave_with_is_a_pointer_list_not_a_second_copy(db_session, world):
    long_first = ("Ask whether the synthetic movement A progression can continue at the current load "
                  "while condition B is still being monitored weekly")
    b = _brief(db_session, world.id, asks=[
        {"id": "a1", "text": "Short ask one. Second sentence with detail A.", "priority": 1},
        {"id": "a2", "text": long_first + ". Then more.", "priority": 2},
        {"id": "a3", "text": "Ask about e.g. the synthetic thing without a break", "priority": 3}])
    items = _section(b, "leave_with")["items"]
    assert [i["id"] for i in items] == ["a1", "a2", "a3"]
    assert all("text" not in i for i in items), "Leave with must not carry the full ask text"
    assert items[0]["short"] == "Short ask one."
    assert items[1]["short"].endswith("…") and len(items[1]["short"]) <= ab.LEAVE_WITH_SHORT_CHARS + 1
    assert long_first.startswith(items[1]["short"][:-1])
    assert items[2]["short"] == "Ask about e.g. the synthetic thing without a break"
    # The full text is under Asks, once.
    assert _section(b, "asks")["authored"][0]["text"] == "Short ask one. Second sentence with detail A."


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
    _injury(db_session, world.id, "injury_part_d_right", "part d", side="right", added_at=date(2025, 12, 4))
    b = _brief(db_session, world.id, scope={"parent_keys": [IN, GONE, "injury_part_d_right"]})

    # changes_vs_history owns the findings and the injury status changes...
    chv = _section(b, "changes_vs_history")
    assert [(f["key"], f["text"], [p["statement"] for p in f["previous"]]) for f in chv["findings"]] == [
        ("f_chain", "Statement v2", ["Statement v1"])]
    assert [(i["key"], i["change"], i["before"], i["after"]) for i in chv["injuries"]] == [
        (GONE, "resolved", "active", "resolved 2025-12-20")]
    # ...so since keeps only what it does not carry: constraints confirmed / resolved, new injuries.
    since = _section(b, "since")
    assert since["since"] == SINCE
    assert [(i["key"], i["change"]) for i in since["injuries"]] == [("injury_part_d_right", "recorded")]
    assert since["findings"] == []
    assert {(c["key"], c["change"]) for c in since["constraints"]} == {("c_new", "confirmed"), ("c_gone", "resolved")}
    # Each row once across the two modules.
    since_keys = {i["key"] for i in since["injuries"]} | {c["key"] for c in since["constraints"]}
    chv_keys = {i["key"] for i in chv["injuries"]} | {f["key"] for f in chv["findings"]}
    assert not since_keys & chv_keys


def test_since_keeps_findings_and_status_changes_when_changes_vs_history_is_dropped(db_session, world):
    # Negative control for the dedup: with the owning module absent, since is the most specific home.
    _put(db_session, world.id, "finding", "f_new", _finding(as_of="2025-12-05"))
    since = _section(_brief(db_session, world.id, sections={"drop": ["changes_vs_history"]}), "since")
    assert [f["key"] for f in since["findings"]] == ["f_new"]
    assert [(i["key"], i["change"]) for i in since["injuries"]] == [(GONE, "resolved")]


def test_a_constraint_already_asked_about_is_not_repeated_as_confirmed(db_session, world):
    _put(db_session, world.id, "constraint", "c_asked", _constraint(exit_={"on_condition": "condition A"}),
         added_at=date(2025, 12, 3))
    _put(db_session, world.id, "constraint", "c_plain", _constraint(), added_at=date(2025, 12, 3))
    b = _brief(db_session, world.id)
    assert [d["entry_key"] for d in _derived(b)] == ["c_asked"]
    assert [c["key"] for c in _section(b, "since")["constraints"]] == ["c_plain"]
    # Current constraints is still its home.
    assert {c["key"] for c in _section(b, "current_constraints")["items"]} == {"c_asked", "c_plain"}


def test_an_empty_since_renders_nothing(db_session, world):
    _put(db_session, world.id, "constraint", "c_asked", _constraint(exit_={"on_condition": "condition A"}),
         added_at=date(2025, 12, 3))
    b = _brief(db_session, world.id, scope={"parent_keys": [IN]})
    assert _section(b, "since") is None
    assert _section(b, "changes_vs_history") is not None


def test_statements_render_in_full_everywhere(db_session, world):
    long_v1 = "Earlier synthetic statement " + "x" * 300 + " END-V1"
    long_v2 = "Synthetic statement about a possible lesion " + "y" * 300 + " END-V2"
    _put(db_session, world.id, "finding", "f_long", _finding(statement=long_v1, as_of="2025-11-01"))
    _put(db_session, world.id, "finding", "f_long", _finding(statement=long_v2, as_of="2025-12-05",
                                                             marker="provocative", status="open"))
    _put(db_session, world.id, "finding", "f_conf", _finding(statement=long_v2 + " C", status="confirmed"))
    b = _brief(db_session, world.id, sections={"add": ["background"]})
    chv = _section(b, "changes_vs_history")["findings"]
    f = next(x for x in chv if x["key"] == "f_long")
    assert f["text"] == long_v2 and f["previous"][0]["statement"] == long_v1
    assert next(d for d in _derived(b) if d["entry_key"] == "f_long")["text"] == f"What does this mean? {long_v2}"
    assert _section(b, "background")["findings"][0]["text"] == long_v2 + " C"
    assert "…" not in json.dumps(b, ensure_ascii=False)


def test_injury_labels_are_human_words_everywhere(db_session, world):
    _put(db_session, world.id, "injury", "injury_cervical_spine", {
        "body_part": "cervical_spine", "side": "bilateral", "signal_type": "mechanical",
        "restrictions": [], "detail": "d"}, added_at=date(2025, 12, 4))
    b = _brief(db_session, world.id, scope={"parent_keys": [IN, GONE, "injury_cervical_spine"]},
               sections={"add": ["background"]})
    since = _section(b, "since")
    assert [(i["key"], i["text"]) for i in since["injuries"]] == [("injury_cervical_spine", "cervical spine")]
    assert [i["text"] for i in _section(b, "background")["injuries"]] == [
        "left part a", "left part c", "cervical spine"]

    def texts(o):
        if isinstance(o, dict):
            yield from ([o["text"]] if isinstance(o.get("text"), str) else [])
            for v in o.values():
                yield from texts(v)
        elif isinstance(o, list):
            for v in o:
                yield from texts(v)
    assert not [t for t in texts(b["sections"]) if "_" in t], "a raw token reached a rendered label"


def test_an_ask_whose_resolves_row_is_not_found_is_flagged_not_dropped(db_session, world):
    _put(db_session, world.id, "constraint", "c_prop", _constraint(status="proposed"))
    gone_c = _put(db_session, world.id, "constraint", "c_inactive", _constraint())
    _resolve_entry(gone_c.id, ResolutionIn(basis="lifted", resolved_by="user", resolved_on="2025-12-12"),
                   "constraint", world.id, db_session)
    _put(db_session, world.id, "constraint", "c_ok", _constraint())
    b = _brief(db_session, world.id, asks=[
        {"id": "a1", "text": "Missing", "priority": 1, "resolves": {"entry_key": "c_nowhere", "note": None}},
        {"id": "a2", "text": "Proposed", "priority": 2, "resolves": {"entry_key": "c_prop", "note": None}},
        {"id": "a3", "text": "Inactive", "priority": 3, "resolves": {"entry_key": "c_inactive", "note": None}},
        {"id": "a4", "text": "Found", "priority": 4, "resolves": {"entry_key": "c_ok", "note": None}},
        {"id": "a5", "text": "Unlinked", "priority": 5}])
    got = [(a["id"], a["resolves"]["entry_key"], a["resolves"]["row"] is None, a["resolves"]["unresolved"])
           for a in _section(b, "asks")["authored"]]
    assert got == [("a1", "c_nowhere", True, True), ("a2", "c_prop", True, True),
                   ("a3", "c_inactive", True, True), ("a4", "c_ok", False, False), ("a5", None, True, False)]


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
    assert (IN, "updated", "part a detail", "part a detail v2") in [
        (i["key"], i["change"], i["before"], i["after"]) for i in chv["injuries"]]


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
    # A constraint confirmed since the last visit, asked about by nothing, so `since` has a row.
    _put(db_session, world.id, "constraint", "c_new", _constraint(), added_at=date(2025, 12, 3))
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
    # The ledger query, plus one read of the user's `full_name` (the print subtitle, #350) — nothing else.
    others = [s for s in statements if "user_knowledge_entries" not in s]
    assert len(others) == 1 and "users.full_name" in others[0] and "FROM users" in others[0], others
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


# ── neutral framing (#349) ────────────────────────────────────────────────────

def test_derived_asks_are_open_questions_never_presumed_instructions(db_session, world):
    _put(db_session, world.id, "constraint", "c_due", _constraint(review_by="2026-01-20"))
    _put(db_session, world.id, "constraint", "c_cond", _constraint(exit_={"on_condition": "condition A"}))
    _put(db_session, world.id, "finding", "f_due", _finding(review_by="2026-01-20", statement="Finding D"))
    _put(db_session, world.id, "finding", "f_prov", _finding(marker="provocative", statement="Finding P"))
    texts = {(d["rule"], d["entry_key"]): d["text"] for d in _derived(_brief(db_session, world.id))}
    assert texts == {
        ("review_due", "c_due"): "Is this still appropriate? CAP (advisory — not engine-enforced) — cap on movement A",
        ("undated_exit", "c_cond"): "Does this condition still apply? condition A",
        ("review_due", "f_due"): "Is this still appropriate? Finding D",
        ("unsettled_marker", "f_prov"): "What does this mean? Finding P",
    }
    for t in texts.values():
        head = t.split("?")[0]
        assert t.split(" ", 1)[0] in ("Is", "Does", "What"), t
        assert not any(w in head.lower() for w in ("set ", "confirm", "rule on", "date ", "must", "clear")), t


def test_every_constraint_and_finding_row_carries_its_authority(db_session, world):
    _put(db_session, world.id, "constraint", "c_mine", _constraint(exit_={"on_condition": "condition A"}),
         added_at=date(2025, 12, 3))
    _put(db_session, world.id, "constraint", "c_clin", _constraint(asserted_by="clinician"))
    _put(db_session, world.id, "finding", "f_chain", _finding(statement="v1", as_of="2025-11-01"))
    _put(db_session, world.id, "finding", "f_chain", _finding(statement="v2", as_of="2025-12-05",
                                                              marker="provocative", asserted_by="clinician"))
    b = _brief(db_session, world.id, asks=[
        {"id": "a1", "text": "Ask", "priority": 1, "resolves": {"entry_key": "c_mine", "note": None}}])
    a1 = _section(b, "asks")["authored"][0]
    assert (a1["resolves"]["row"]["asserted_by"], a1["resolves"]["row"]["authority"]) == ("user", "set by you")
    assert a1["folded"][0]["row"]["asserted_by"] == "user"
    by_key = {c["key"]: (c["asserted_by"], c["authority"]) for c in _section(b, "current_constraints")["items"]}
    assert by_key == {"c_mine": ("user", "set by you"), "c_clin": ("clinician", "set by your clinician")}
    f = _section(b, "changes_vs_history")["findings"][0]
    assert (f["asserted_by"], f["authority"]) == ("clinician", "set by your clinician")
    assert (f["previous"][0]["asserted_by"], f["previous"][0]["authority"]) == ("user", "set by you")
    assert next(d for d in _derived(b) if d["entry_key"] == "f_chain")["row"]["asserted_by"] == "clinician"


# ── print-document fields (#350): plain words beside the chat phrasing ──────

def _no_token(s):
    return s is None or "_" not in s


def test_a_finding_carries_its_parent_key_and_label(db_session, world):
    _put(db_session, world.id, "finding", "f_a", _finding(as_of="2025-12-05", marker="provocative"))
    b = _brief(db_session, world.id, sections={"add": ["background"]})
    f = _section(b, "changes_vs_history")["findings"][0]
    assert (f["parent_key"], f["parent_label"]) == (IN, "left part a")
    assert next(d for d in _derived(b) if d["entry_key"] == "f_a")["row"]["parent_label"] == "left part a"
    assert _no_token(f["parent_label"])


def test_parent_label_falls_back_to_the_key_in_words(db_session, world):
    s = ab._finding_summary({"key": "f_x", "statement": "S", "parent_key": "injury_part_z_left"}, {})
    assert s["parent_label"] == "injury part z left" and _no_token(s["parent_label"])
    assert ab._finding_summary({"key": "f_y", "statement": "S"}, {})["parent_label"] is None


def test_an_advisory_restriction_is_its_own_text(db_session, world):
    _put(db_session, world.id, "constraint", "c_adv", _constraint(exit_={"with_parent": True, "on_date": "2026-04-01"}))
    c = _section(_brief(db_session, world.id), "current_constraints")["items"][0]
    assert c["restriction"] == "cap on movement A"
    assert "engine-enforced" not in c["restriction"]
    # exit_label names the parent injury in words; exit and text stay the chat phrasing.
    assert c["exit_label"] == "on 2026-04-01 or when left part a is resolved"
    assert c["exit"] == f"on 2026-04-01 or when {IN} is resolved"
    assert c["text"] == "CAP (advisory — not engine-enforced) — cap on movement A"
    assert (c["parent_key"], c["parent_label"]) == (IN, "left part a")
    assert _no_token(c["restriction"]) and _no_token(c["exit_label"])


def test_an_engine_restriction_is_kind_regions_and_side_in_words(db_session, world):
    _put(db_session, world.id, "constraint", "c_eng", _constraint(
        kind="block", scope={"tier": "engine", "region_keys": ["shoulder_er_ir", "vertical_push"], "side": "right"}))
    _put(db_session, world.id, "constraint", "c_bi", _constraint(
        kind="block", scope={"tier": "engine", "region_keys": ["hinge"]}))
    items = {c["key"]: c for c in _section(_brief(db_session, world.id), "current_constraints")["items"]}
    assert items["c_eng"]["restriction"] == "Block: Shoulder ER / IR (rotator cuff), Vertical push, right side only"
    assert items["c_bi"]["restriction"] == "Block: Hinge (hip-dominant)"
    for c in items.values():
        assert "engine-enforced" not in c["restriction"] and _no_token(c["restriction"])
        assert "engine-enforced" in c["text"]      # the chat phrasing is unchanged


def test_a_derived_ask_carries_its_question_alone(db_session, world):
    _put(db_session, world.id, "constraint", "c_due", _constraint(review_by="2026-01-20"))
    _put(db_session, world.id, "constraint", "c_cond", _constraint(exit_={"on_condition": "condition A"}))
    _put(db_session, world.id, "finding", "f_prov", _finding(marker="provocative", statement="Finding P"))
    got = {(d["rule"], d["entry_key"]): (d["question"], d["text"]) for d in _derived(_brief(db_session, world.id))}
    assert got[("review_due", "c_due")][0] == "Is this still appropriate?"
    assert got[("undated_exit", "c_cond")] == ("Does this condition still apply?",
                                               "Does this condition still apply? condition A")
    assert got[("unsettled_marker", "f_prov")] == ("What does this mean?", "What does this mean? Finding P")
    assert all(_no_token(q) for q, _ in got.values())


def test_patient_name_is_the_users_full_name_or_null(db_session, world):
    assert _brief(db_session, world.id)["patient"] == {"name": None}
    world.full_name = "Person A"
    db_session.commit()
    b = ab.load_appointment_brief(db_session, world.id, "appt_a")
    assert b["patient"] == {"name": "Person A"}


# ── imaging_timeline: the `document` door resolves against stored clinical documents ──────────────
#
# A `document` ref that byte-matches one of the user's clinical-document `doc_key`s gains the
# record's date, title and verbatim conclusion and sorts by `service_date`; any other ref renders
# exactly as it always did. SYNTHETIC documents only.

DOC_VERBATIM = "Appearances  as written – query ?  [sic]\r\nLine two \n"


def _doc(db, uid, key, service="2026-01-05", **over):
    vals = dict(user_id=uid, doc_key=key, doc_type="imaging", modality="MRI", study=f"Study {key}",
                service_date=date.fromisoformat(service), source_doc_filenames=["f.pdf"],
                conclusion_verbatim=DOC_VERBATIM, source="file_extraction",
                schema_version="clinical_documents v0.1")
    vals.update(over)
    db.add(models.ClinicalDocument(**vals))
    db.commit()


def _cite(db, uid, fkey, as_of, *refs):
    _put(db, uid, "finding", fkey, _finding(as_of=as_of, basis={"evidence": [
        {"door": "document", "ref": r} for r in refs]}))


def test_a_matched_document_ref_gains_date_title_and_the_verbatim_conclusion(db_session, world):
    _doc(db_session, world.id, "doc-a", service="2026-01-05")
    _cite(db_session, world.id, "f_a", "2025-12-10", "doc-a")
    items = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert items == [{"ref": "doc-a", "finding_key": "f_a", "as_of": "2025-12-10",
                      "service_date": "2026-01-05", "title": "Study doc-a",
                      "conclusion_verbatim": DOC_VERBATIM}]
    assert items[0]["conclusion_verbatim"].encode() == DOC_VERBATIM.encode()


def test_an_unmatched_ref_renders_exactly_as_before(db_session, world):
    _doc(db_session, world.id, "doc-a")
    _cite(db_session, world.id, "f_a", "2025-12-10", "doc-a", "Free text ref, no such key")
    items = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    free = next(i for i in items if i["ref"] == "Free text ref, no such key")
    assert free == {"ref": "Free text ref, no such key", "finding_key": "f_a", "as_of": "2025-12-10"}


def test_a_ref_must_match_the_doc_key_byte_for_byte(db_session, world):
    _doc(db_session, world.id, "doc-a")
    _cite(db_session, world.id, "f_a", "2025-12-10", "DOC-A", "doc-a ", " doc-a")
    items = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert all(set(i) == {"ref", "finding_key", "as_of"} for i in items) and len(items) == 3


def test_resolved_items_sort_by_service_date_not_by_the_citing_findings_as_of(db_session, world):
    _doc(db_session, world.id, "doc-late", service="2026-01-20")
    _doc(db_session, world.id, "doc-early", service="2025-09-01")
    # cited in the opposite order, and by findings whose as_of order is also the opposite
    _cite(db_session, world.id, "f_1", "2025-10-01", "doc-late")
    _cite(db_session, world.id, "f_2", "2025-12-01", "doc-early")
    items = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert [i["ref"] for i in items] == ["doc-early", "doc-late"]


def test_an_unresolved_ref_keeps_its_place_among_resolved_ones(db_session, world):
    _doc(db_session, world.id, "doc-a", service="2026-01-05")
    _cite(db_session, world.id, "f_free", "2025-11-01", "free text ref")      # sorts on as_of 2025-11-01
    _cite(db_session, world.id, "f_doc", "2025-12-15", "doc-a")                # sorts on service 2026-01-05
    items = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert [i["ref"] for i in items] == ["free text ref", "doc-a"]


def test_a_document_with_no_conclusion_resolves_with_a_null_one(db_session, world):
    _doc(db_session, world.id, "doc-letter", doc_type="correspondence", modality=None, study=None,
         subtype="specialist letter", conclusion_verbatim=None)
    _cite(db_session, world.id, "f_a", "2025-12-10", "doc-letter")
    (item,) = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert item["title"] == "specialist letter" and item["conclusion_verbatim"] is None


def test_another_users_doc_key_does_not_resolve(db_session, world):
    other = _user(db_session, "other-brief@example.com")
    _doc(db_session, other.id, "doc-a")
    _cite(db_session, world.id, "f_a", "2025-12-10", "doc-a")
    (item,) = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["items"]
    assert set(item) == {"ref", "finding_key", "as_of"}


def test_the_note_no_longer_says_the_door_resolves_to_nothing(db_session, world):
    note = _section(_brief(db_session, world.id, kind="intro"), "imaging_timeline")["note"]
    assert "do not resolve" not in note and "yet" not in note
    assert "matches a stored clinical document" in note


def test_no_document_query_is_made_when_no_finding_cites_one(db_session, world):
    _put(db_session, world.id, "appointment", "appt_i", _appt(kind="intro"))
    uid = world.id
    statements = []
    engine = db_session.get_bind()

    def _capture(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        ab.load_appointment_brief(db_session, uid, "appt_i")
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    assert statements and not any("clinical_documents" in s for s in statements)


def test_the_pure_core_resolves_from_the_documents_it_is_given(db_session, world):
    import typed_entries
    from current_state import CurrentState
    _cite(db_session, world.id, "f_a", "2025-12-10", "doc-a")
    _put(db_session, world.id, "appointment", "appt_i", _appt(kind="intro"))
    rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=world.id).all()
    active = [r for r in rows if r.active]
    state = CurrentState(knowledge_entries=active, constraints=typed_entries.lift_constraints(active),
                         findings=typed_entries.lift_findings(active), live_keys=typed_entries.active_keys(active))
    appt = {"key": "appt_i", "value": _appt(kind="intro")}
    docs = {"doc-a": {"service_date": "2026-01-05", "title": "T", "conclusion_verbatim": "C"}}
    resolved = ab.build_appointment_brief(appt, state, rows, None, docs)
    plain = ab.build_appointment_brief(appt, state, rows, None)
    assert _section(resolved, "imaging_timeline")["items"][0]["title"] == "T"
    assert set(_section(plain, "imaging_timeline")["items"][0]) == {"ref", "finding_key", "as_of"}


def test_the_pure_core_matches_a_ref_to_its_doc_key_byte_for_byte():
    """The loader's exact `IN` already keeps a near-miss from being fetched; the core must not
    resolve one either, whatever it is handed."""
    ctx = ab.BriefContext(key="k", value={}, kind="intro", audience="operator",
                          at=ab.datetime(2026, 1, 15, 13, 0), since=None, parent_keys=[],
                          documents={"doc-a": {"service_date": "2026-01-05", "title": "T",
                                               "conclusion_verbatim": None}})
    ctx.findings = [{"key": "f", "as_of": "2025-12-10", "basis": {"evidence": [
        {"door": "document", "ref": r} for r in ("DOC-A", "doc-a ", " doc-a", "doc-a")]}}]
    items = ab.module_imaging_timeline(ctx)["items"]
    assert [("title" in i) for i in items] == [False, False, False, True]

