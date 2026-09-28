"""The coach's constraint / finding write shape is GENERATED from the validators (prod bug, 28 Sep 2026).

Three chat constraint writes in a row were refused for shape — `side` on an advisory scope,
`tier: "engine-enforced"`, `text` at the top level — because the guidance was prose + one example and
the model rebuilt the shape from memory. The #313 remedy: every name in the section is interpolated
from `routers.knowledge` / `engine.taxonomy`. These tests fail if the section drifts from the
validators, if an example it teaches would be refused, or if the pass-2 narrator promises a retry.
"""
import json
import re

import pytest

import context_builder
import models
from engine.taxonomy import all_regions
from routers import chat as chat_mod
from routers.chat import _process_knowledge_updates
from routers.knowledge import (
    CONSTRAINT_EXIT_FIELDS, CONSTRAINT_FIELDS, CONSTRAINT_KINDS, CONSTRAINT_SCOPE_FIELDS,
    CONSTRAINT_SIDES, CONSTRAINT_TIERS, FINDING_DOMAINS, FINDING_EVIDENCE_DOORS, FINDING_FIELDS,
    MARKER_STATUS_VALUES, TYPED_CHAT_OMITTED_FIELDS, TYPED_STAMPED_FIELDS, validate_constraint,
)

SECTION = context_builder._section_knowledge_update()
SHAPE = context_builder._typed_entry_write_shape()


def _words(text):
    return set(re.findall(r"[a-z_]+", text))


@pytest.mark.parametrize("vocab", [
    [f for f in CONSTRAINT_FIELDS if f not in TYPED_CHAT_OMITTED_FIELDS],
    [f for f in FINDING_FIELDS if f not in TYPED_CHAT_OMITTED_FIELDS],
    CONSTRAINT_SCOPE_FIELDS, CONSTRAINT_TIERS, CONSTRAINT_KINDS, CONSTRAINT_SIDES,
    CONSTRAINT_EXIT_FIELDS, FINDING_DOMAINS, FINDING_EVIDENCE_DOORS, MARKER_STATUS_VALUES,
    [r.key for r in all_regions()],
])
def test_every_validator_name_is_in_the_section(vocab):
    missing = [v for v in vocab if v not in _words(SHAPE)]
    assert missing == []


def test_the_section_is_the_generated_block():
    assert SHAPE in SECTION


def test_the_hand_maps_cover_exactly_the_validator_tuples():
    assert set(context_builder._EXIT_MEANING) == set(CONSTRAINT_EXIT_FIELDS)
    assert set(context_builder._ADVISORY_SCOPE_KEYS) < set(CONSTRAINT_SCOPE_FIELDS)


def test_never_send_names_every_channel_and_route_stamped_field():
    line = next(ln for ln in SHAPE.splitlines() if ln.startswith("Never send"))
    for f in (*TYPED_CHAT_OMITTED_FIELDS, *TYPED_STAMPED_FIELDS):
        assert f in line


@pytest.mark.parametrize("bad,rule", [
    ({"scope": {"tier": "advisory", "text": "x", "side": "right"}}, "no region_keys or side"),
    ({"scope": {"tier": "engine-enforced", "region_keys": ["hinge"]}}, "no other spelling"),
    ({"scope": {"tier": "advisory"}, "text": "x"}, "never at the top level"),
])
def test_each_prod_refusal_shape_is_refused_and_named_as_a_rule(bad, rule):
    """The three 28 Sep refusals: still refused by the validator, and each is now a stated rule."""
    value = {"kind": "block", "exit": {"on_condition": "x"}, "review_by": "2026-10-15",
             "status": "proposed", "asserted_by": None, **bad}
    with pytest.raises(ValueError):
        validate_constraint(value)
    assert rule in SHAPE


def _blocks(text):
    return re.findall(r"<knowledge_update>\n(\{.*?\})\n</knowledge_update>", text)


def test_every_example_in_the_shape_writes_as_a_proposal(db_session):
    examples = [json.loads(b) for b in _blocks(SHAPE)]
    assert {e["type"] for e in examples} == {"constraint", "finding"}
    assert any(e["value"]["scope"]["tier"] == "engine" for e in examples if e["type"] == "constraint")
    u = models.User(email="shape@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    for e in examples:
        block = f"<knowledge_update>\n{json.dumps(e)}\n</knowledge_update>"
        _, _, results = _process_knowledge_updates(block, u.id, db_session)
        assert results[0].saved is True, results[0].reason
        row = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, key=e["key"]).one()
        assert row.value["status"] == "proposed" and row.value["asserted_by"] is None


def test_pass2_never_promises_a_retry():
    """The 'I'll sort that out and retry' reply was our own pass-2 instruction; nothing retries."""
    assert "you'll sort it out" not in chat_mod._PASS2_SYSTEM
    assert "Do NOT promise to retry" in chat_mod._PASS2_SYSTEM
    assert "never promise a retry" in SHAPE
