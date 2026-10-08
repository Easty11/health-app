"""Who may rewrite a CONFIRMED finding, and what survives (the clinical-documents F2 re-point).

The question: can a finding's `document` evidence ref be re-pointed to a `doc_key` while it stays
`confirmed` with its authority? Read from the code and pinned here so the answer is a test, not a
recollection:
  * chat cannot: a same-key chat rewrite of a confirmed finding is REFUSED (`operator_only`), and a
    chat write is a proposal only -- it can never replace the confirmed row, let alone demote it;
  * a non-chat write (`source="api"`, the PowerShell channel) can rewrite it at `confirmed`: the old
    row is superseded (`active=False`, status `superseded`) and the new one is active and confirmed;
  * but `confirmed_on` is stamped by `/confirm` only and a write carrying it is refused, so a
    rewrite cannot carry the original stamp -- the new row has none. Nothing reads it for a finding.

SYNTHETIC rows only.
"""
import pytest

import models
from routers.knowledge import (
    ConfirmIn, KnowledgeEntryIn, TypedEntryRefused, _confirm_entry, upsert_knowledge_entry,
)

KEY = "finding_synthetic_a"


def _user(db):
    u = models.User(email="rewrite@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _injury(db, uid):
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="injury", key="injury_part_a", source="api", value={
        "body_part": "part a", "side": "left", "signal_type": "mechanical",
        "restrictions": ["part a movement"], "detail": "synthetic"}), db)


def _value(ref, **over):
    v = {"statement": "Synthetic statement", "domain": "injury", "status": "confirmed",
         "parent_key": "injury_part_a", "as_of": "2026-09-21",
         "basis": {"text": "synthetic basis", "evidence": [{"door": "document", "ref": ref}]},
         "derived_from_labs": False, "asserted_by": "clinician"}
    v.update(over)
    return v


@pytest.fixture
def confirmed(db_session):
    """A finding that reached `confirmed` the only way it can: proposed by chat, confirmed by the route."""
    u = _user(db_session)
    _injury(db_session, u.id)
    proposal = upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="finding", key=KEY, source="chat",
        value=_value("free text ref", status="proposed", asserted_by=None)), db_session)
    row = _confirm_entry(proposal.id, ConfirmIn(asserted_by="clinician"), "finding", u.id, db_session)
    assert row.value["status"] == "confirmed" and row.value["asserted_by"] == "clinician"
    assert row.value["confirmed_on"]                       # the route stamped it
    return u, row


def _active(db, uid):
    return db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, key=KEY, active=True).one()


def test_a_chat_rewrite_of_a_confirmed_finding_is_refused_and_changes_nothing(db_session, confirmed):
    u, row = confirmed
    for value in (_value("doc_key_a", status="proposed", asserted_by=None),   # a proposal over it
                  _value("doc_key_a")):                                       # or a confirmed lookalike
        with pytest.raises(TypedEntryRefused) as exc:
            upsert_knowledge_entry(u.id, KnowledgeEntryIn(type="finding", key=KEY, source="chat", value=value),
                                   db_session)
        assert exc.value.code == "operator_only"
    db_session.rollback()
    after = _active(db_session, u.id)
    assert after.id == row.id and after.value["status"] == "confirmed"
    assert after.value["basis"]["evidence"][0]["ref"] == "free text ref"


def test_a_non_chat_rewrite_supersedes_and_keeps_confirmed_and_authority(db_session, confirmed):
    u, old = confirmed
    new = upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="finding", key=KEY, source="api", value=_value("doc_key_a")), db_session)
    db_session.refresh(old)
    assert new.id != old.id and new.active and not old.active and old.superseded_by == new.id
    assert old.value["status"] == "superseded"             # history reads superseded, not demoted
    assert new.value["status"] == "confirmed" and new.value["asserted_by"] == "clinician"
    assert new.value["basis"]["evidence"][0] == {"door": "document", "ref": "doc_key_a"}
    assert _active(db_session, u.id).id == new.id


def test_a_rewrite_cannot_carry_the_confirmed_on_stamp(db_session, confirmed):
    u, _ = confirmed
    with pytest.raises(ValueError, match="confirmed_on"):
        upsert_knowledge_entry(u.id, KnowledgeEntryIn(
            type="finding", key=KEY, source="api",
            value=_value("doc_key_a", confirmed_on="2026-10-02")), db_session)
    db_session.rollback()
    new = upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="finding", key=KEY, source="api", value=_value("doc_key_a")), db_session)
    assert "confirmed_on" not in new.value                 # the stamp is not carried; the superseded row keeps it
