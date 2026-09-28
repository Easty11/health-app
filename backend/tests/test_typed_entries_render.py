"""Rendering and reads for typed constraints / findings — S4 of the typed-entries brief (#342/#343).

G4's gates:
  * NO ROWS → BYTE-IDENTICAL. The #43 parity guard (`test_current_state`) passes unchanged except
    for the ONE declared difference (the knowledge-update guidance, re-declared there). Here:
    proposals, advisory-free states and retracted rows add nothing — the prompt is byte-identical
    to the same state with no typed rows at all.
  * WITH ROWS the authority label renders per `asserted_by`; a passed exit / review is TAGGED and
    the constraint still renders (enforced until resolved, #223); the Constraints section is
    unbudgeted; the Findings section holds its 2,000-char budget, caps each statement at 280 with
    "…", NAMES the overflow and never drops it, and a lab-derived finding appears only as a count.
  * THE MCP reads through the same lift as `current_state` (one query, no `current_state()` run).
  * THE GUIDANCE's two examples write as proposals through the real chat channel.
"""
import json
import re
from datetime import date, datetime

import pytest

import context_builder
import current_state as current_state_mod
import mcp_server
import models
import typed_entries
from routers.chat import _process_knowledge_updates
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

TODAY = date(2026, 9, 28)


def _user(db, email="render@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _put(db, user_id, type_, key, value, source="api"):
    return upsert_knowledge_entry(user_id, KnowledgeEntryIn(
        type=type_, key=key, value=value, source=source), db)


def _constraint(**over):
    v = {"scope": {"tier": "advisory", "text": "no striding or sprinting"}, "kind": "block",
         "exit": {"on_condition": "physio clears return to running"}, "review_by": "2026-10-15",
         "status": "confirmed", "asserted_by": "user"}
    v.update(over)
    return v


def _finding(**over):
    v = {"statement": "Right ER painful at 11.25 kg; left clean", "domain": "training",
         "status": "open", "as_of": "2026-09-27", "basis": {"text": "session report"},
         "derived_from_labs": False, "asserted_by": "user"}
    v.update(over)
    return v


def _prompt(db, user, monkeypatch):
    monkeypatch.setattr(context_builder, "_now_aest",
                        lambda: context_builder.AEST.localize(datetime(2026, 9, 28, 9, 0)))
    state = current_state_mod.current_state(user.id, db, today=TODAY)
    return context_builder.build_system_prompt(user, [], state)


def _baseline(db, user_id):
    _put(db, user_id, "preference", "device_profile", {"hrv_source": "galaxy_ring"})
    _put(db, user_id, "injury", "hamstring_right", {"body_part": "hamstring", "side": "right",
                                                    "restrictions": ["no sprinting"]})


# ── no rows → byte-identical ─────────────────────────────────────────────────

def test_unreadable_typed_rows_leave_the_prompt_byte_identical(db_session, monkeypatch):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    _baseline(db_session, a.id)
    _baseline(db_session, b.id)
    # b carries every typed row NOTHING may render: proposals, and a retracted finding.
    _put(db_session, b.id, "constraint", "c_prop", _constraint(status="proposed", asserted_by=None))
    _put(db_session, b.id, "finding", "f_prop", _finding(status="proposed", asserted_by=None))
    gone = _put(db_session, b.id, "finding", "f_gone", _finding())
    gone.active = False
    db_session.commit()
    pa = _prompt(db_session, a, monkeypatch)
    pb = _prompt(db_session, b, monkeypatch).replace("b@example.com", "a@example.com")
    assert "## Constraints" not in pa and "## Findings" not in pa
    assert pa == pb


# ── with rows ────────────────────────────────────────────────────────────────

def _section(prompt, head):
    start = prompt.index(head)
    nxt = prompt.find("\n## ", start + 1)
    return prompt[start: nxt if nxt != -1 else len(prompt)]


def test_authority_label_renders_per_asserted_by(db_session, monkeypatch):
    u = _user(db_session)
    _baseline(db_session, u.id)
    for who in ("user", "clinician", "engine"):
        _put(db_session, u.id, "constraint", f"c_{who}", _constraint(asserted_by=who))
    sec = _section(_prompt(db_session, u, monkeypatch), "## Constraints")
    assert "set by you [c_user]" in sec
    assert "set by your clinician [c_clinician]" in sec
    assert "set by the engine [c_engine]" in sec
    assert sec.count("(advisory — not engine-enforced)") == 3


def test_engine_row_renders_as_enforced_with_its_side(db_session, monkeypatch):
    u = _user(db_session)
    _baseline(db_session, u.id)
    _put(db_session, u.id, "constraint", "c_shoulder", _constraint(
        scope={"tier": "engine", "region_keys": ["shoulder_er_ir"], "side": "right"}))
    sec = _section(_prompt(db_session, u, monkeypatch), "## Constraints")
    assert "BLOCK (engine-enforced) — regions: shoulder_er_ir, right side only" in sec


def test_passed_exit_and_review_are_tagged_and_still_render(db_session, monkeypatch):
    u = _user(db_session)
    _baseline(db_session, u.id)
    _put(db_session, u.id, "constraint", "c_date", _constraint(exit={"on_date": "2026-09-20"}))
    _put(db_session, u.id, "constraint", "c_review", _constraint(review_by="2026-09-28"))
    _put(db_session, u.id, "constraint", "c_parent", _constraint(
        parent_key="hamstring_right", exit={"with_parent": True}))
    _put(db_session, u.id, "constraint", "c_fine", _constraint(
        exit={"on_date": "2026-12-01"}, review_by="2026-10-30"))
    # The parent resolves AFTER confirm: the with_parent exit has fired, the row stays in force.
    inj = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, key="hamstring_right").one()
    inj.active = False
    db_session.commit()
    lines = {re.search(r"\[(c_\w+)\]", ln).group(1): ln
             for ln in _section(_prompt(db_session, u, monkeypatch), "## Constraints").splitlines()
             if ln.startswith("- ")}
    assert set(lines) == {"c_date", "c_review", "c_parent", "c_fine"}          # all still render
    assert lines["c_date"].endswith("[EXIT DUE]")
    assert lines["c_review"].endswith("[REVIEW DUE]")                          # due ON the day
    assert lines["c_parent"].endswith("[EXIT DUE]")
    assert "DUE" not in lines["c_fine"]                                        # control


def test_constraints_section_is_unbudgeted(db_session, monkeypatch):
    u = _user(db_session)
    _baseline(db_session, u.id)
    for i in range(40):
        _put(db_session, u.id, "constraint", f"c_{i:02d}", _constraint(detail="x" * 150))
    sec = _section(_prompt(db_session, u, monkeypatch), "## Constraints")
    assert len(sec) > typed_entries.FINDINGS_CHAR_BUDGET * 3
    assert all(f"[c_{i:02d}]" in sec for i in range(40))


def test_findings_budget_caps_names_overflow_and_never_drops(db_session, monkeypatch):
    u = _user(db_session)
    _baseline(db_session, u.id)
    long_stmt = "L" * 600
    _put(db_session, u.id, "finding", "f_long", _finding(statement=long_stmt, as_of="2026-09-26"))
    for i in range(20):
        _put(db_session, u.id, "finding", f"f_{i:02d}",
             _finding(statement=f"finding number {i:02d} " + "y" * 120, as_of=f"2026-08-{i + 1:02d}"))
    _put(db_session, u.id, "finding", "f_lab", _finding(
        statement="Bilirubin elevated, consistent with Gilbert's", domain="clinical",
        derived_from_labs=True, basis={"evidence": [{"door": "lab_results", "ref": "bilirubin_total"}]}))
    sec = _section(_prompt(db_session, u, monkeypatch), "## Findings")
    body = sec.splitlines()[1:]
    shown = [ln for ln in body if ln.startswith("- [")]
    assert sum(len(ln) + 1 for ln in shown) <= typed_entries.FINDINGS_CHAR_BUDGET
    # Newest first; the 600-char statement is capped at 280 + "…".
    # (the 09-27 finding is the lab-derived one — withheld, so it is not the first line).
    assert shown[0].startswith("- [2026-09-26")
    assert "L" * 280 + "…" in shown[0] and "L" * 281 not in sec
    assert shown[1].startswith("- [2026-08-20")
    overflow = next(ln for ln in body if ln.startswith("Beyond this section's budget"))
    # Never dropped: every one of the 20 older findings is either shown or named.
    for i in range(20):
        assert f"finding number {i:02d}" in sec
    assert "finding number 00" in overflow                                    # the oldest overflowed
    # The lab-derived finding: counted in one pointer line, its statement nowhere.
    assert "Gilbert" not in sec
    assert body[-1] == typed_entries.withheld_labs_line(1, "Labs page")


def test_findings_section_renders_for_withheld_only(db_session, monkeypatch):
    u = _user(db_session)
    _baseline(db_session, u.id)
    _put(db_session, u.id, "finding", "f_lab", _finding(derived_from_labs=True))
    sec = _section(_prompt(db_session, u, monkeypatch), "## Findings")
    assert "Right ER" not in sec and "1 lab-derived finding withheld" in sec


# ── MCP: the same lift, one query ────────────────────────────────────────────

@pytest.fixture
def mcp_user(db_session, monkeypatch):
    u = _user(db_session, "mcp@example.com")
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    return u


def test_mcp_reads_what_current_state_reads(db_session, mcp_user):
    _baseline(db_session, mcp_user.id)
    _put(db_session, mcp_user.id, "constraint", "c1", _constraint())
    _put(db_session, mcp_user.id, "constraint", "c_prop", _constraint(status="proposed", asserted_by=None))
    _put(db_session, mcp_user.id, "finding", "f1", _finding())
    _put(db_session, mcp_user.id, "finding", "f_lab", _finding(derived_from_labs=True))
    state = current_state_mod.current_state(mcp_user.id, db_session, today=TODAY)
    constraints, findings, live = mcp_server._typed_entries_read(mcp_user.id)
    assert constraints == state.constraints and [c["key"] for c in constraints] == ["c1"]
    assert findings == state.findings and live == state.live_keys


def test_readiness_snapshot_carries_confirmed_constraints(db_session, mcp_user, monkeypatch):
    _put(db_session, mcp_user.id, "constraint", "c_shoulder", _constraint(
        scope={"tier": "engine", "region_keys": ["shoulder_er_ir"], "side": "right"}, asserted_by="clinician"))
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [])
    out = mcp_server.get_readiness_snapshot()
    block = out[out.index("Active constraints (confirmed):"):]
    assert "shoulder_er_ir, right side only" in block and "set by your clinician [c_shoulder]" in block


def test_readiness_snapshot_unchanged_without_constraints(db_session, mcp_user, monkeypatch):
    _put(db_session, mcp_user.id, "constraint", "c_prop", _constraint(status="proposed", asserted_by=None))
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [])
    assert "Active constraints (confirmed)" not in mcp_server.get_readiness_snapshot()


def test_get_findings_full_statements_filters_and_withholds(db_session, mcp_user):
    long_stmt = "S" * 500
    _put(db_session, mcp_user.id, "finding", "f_long", _finding(statement=long_stmt, domain="injury"))
    _put(db_session, mcp_user.id, "finding", "f_old", _finding(as_of="2026-07-01"))
    _put(db_session, mcp_user.id, "finding", "f_prop", _finding(status="proposed", asserted_by=None,
                                                                statement="PROPOSAL"))
    _put(db_session, mcp_user.id, "finding", "f_lab", _finding(statement="LABTALK", derived_from_labs=True))
    out = mcp_server.get_findings()
    assert long_stmt in out                              # full, not capped
    assert "PROPOSAL" not in out and "LABTALK" not in out
    assert "1 lab-derived finding withheld" in out
    assert "f_old" in out and "f_long" in out
    assert "f_old" not in mcp_server.get_findings(since="2026-09-01")
    assert "f_long" in mcp_server.get_findings(domain="injury") and "f_old" not in mcp_server.get_findings(domain="injury")
    assert "Unknown domain" in mcp_server.get_findings(domain="medical")
    assert "Unknown status" in mcp_server.get_findings(status="proposed")
    assert "ISO date" in mcp_server.get_findings(since="yesterday")


# ── the guidance: its examples write as proposals ────────────────────────────

SECTION = context_builder._section_knowledge_update()


def test_guidance_states_the_proposal_rules():
    assert "You only ever PROPOSE one" in SECTION
    assert "Never send status, asserted_by" in SECTION
    flat = " ".join(SECTION.split())
    assert "Never confirm, resolve, retract or deactivate a constraint or finding" in flat


@pytest.mark.parametrize("type_", ["constraint", "finding"])
def test_guidance_example_writes_a_proposal(db_session, type_):
    start = SECTION.index('<knowledge_update>\n{"type": "' + type_ + '"')
    block = SECTION[start: SECTION.index("</knowledge_update>", start) + len("</knowledge_update>")]
    payload = json.loads(block[len("<knowledge_update>"): -len("</knowledge_update>")])
    assert "status" not in payload["value"] and "asserted_by" not in payload["value"]
    u = _user(db_session, f"ex-{type_}@example.com")
    _, _, results = _process_knowledge_updates(block, u.id, db_session)
    assert results[0].saved is True, results[0].reason
    row = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, type=type_).one()
    assert row.value["status"] == "proposed" and row.value["asserted_by"] is None
