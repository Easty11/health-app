"""The coach no longer writes injury facts to free-text `user_knowledge` (G3 of the injury
clearance sweep brief; DECISIONS_LOG "Chat no longer writes injury facts to free-text").

The free-text store has no active flag and no resolution and renders unfiltered every turn, so
an injury written there can never be retired. "Injury History" and "Constraints" are removed from
the `<knowledge_update>` free-text categories and the prompt points injury facts at the
structured `type="injury"` ledger. Prompt-only: the manual POST's VALID_CATEGORIES is untouched,
and existing free-text rows are untouched (they are cleared per line via the sweep).
"""
import re

import context_builder
import models
from routers.chat import _process_knowledge_updates
from routers.knowledge import VALID_CATEGORIES

SECTION = context_builder._section_knowledge_update()


def _valid_categories_line() -> str:
    m = re.search(r"^Valid categories: (.*)\.$", SECTION, re.MULTILINE)
    assert m, "the section lost its 'Valid categories:' line"
    return m.group(1)


def test_injury_categories_are_not_offered_as_free_text():
    offered = [c.strip() for c in _valid_categories_line().split(",")]
    assert "Injury History" not in offered
    assert "Constraints" not in offered
    assert offered == list(context_builder.KNOWLEDGE_UPDATE_CATEGORIES)


def test_injury_history_appears_nowhere_in_the_section():
    # Not in the category list, the example block, or the examples: any reappearance fails.
    assert "Injury History" not in SECTION
    assert '"Constraints"' not in SECTION


def test_injury_facts_are_pointed_at_the_structured_ledger():
    assert 'a structured `type="injury"` entry, not free text' in SECTION
    assert "add it to that injury's `restrictions`" in SECTION


def test_the_manual_post_categories_are_untouched():
    """Prompt-only by ruling: VALID_CATEGORIES (the Settings editor's POST) is Q9 territory."""
    assert {"Injury History", "Constraints"} <= VALID_CATEGORIES


def test_the_prompts_injury_example_writes_a_ledger_row(db_session):
    """The example the prompt teaches must actually write — a template the parser refuses would
    push the coach straight back to free text."""
    block = SECTION[SECTION.index('<knowledge_update>\n{"type": "injury"'):]
    block = block[:block.index("</knowledge_update>") + len("</knowledge_update>")]
    u = models.User(email="ku-prompt@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    _process_knowledge_updates(block, u.id, db_session)
    row = db_session.query(models.UserKnowledgeEntry).filter_by(
        user_id=u.id, type="injury", key="injury_calf_left", active=True).one()
    assert row.value["restrictions"] == ["no heel raises for reps"]
    assert db_session.query(models.UserKnowledge).filter_by(user_id=u.id).count() == 0
