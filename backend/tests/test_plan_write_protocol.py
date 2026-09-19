"""Write-protocol docs for `training_plan` + `satisfies` (#313, follow-up to #312).

#312's S5(iv) instructs the coach to propose `training_plan` rewrites and to set `satisfies`
on schedule items, but the `<knowledge_update>` schema it works from (the write-shape home,
`context_builder._section_user_profile`) documented neither. This closes that gap and guards it:

  (a) every `TRAINING_PLAN_FIELDS` field and every `_SATISFIES_VALIDATORS` kind appears in the
      rendered protocol text. The docs are GENERATED from those tuples, so this passes by
      construction and drift is impossible — the test is the standing guard against a future
      hand-rewrite that stops generating and silently drops a field/kind.
  (b) a `<knowledge_update>` block in the DOCUMENTED training_plan shape passes
      `_process_knowledge_updates` and lands a current `training_plan` row.
  (c) a `<knowledge_update>` block linking a schedule_item via `satisfies` lands.
"""
import json

import context_builder
import models
from routers.chat import _process_knowledge_updates, _strip_thinking
from routers.knowledge import (
    TRAINING_PLAN_FIELDS,
    TRAINING_PLAN_KEY,
    _SATISFIES_VALIDATORS,
)


def _user(db, email="write-proto@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _block(payload: dict) -> str:
    return f"OK.\n<knowledge_update>{json.dumps(payload)}</knowledge_update>\nDone."


# ---------- (a) the docs are complete, and generated so they cannot drift ----------

def test_protocol_text_documents_every_training_plan_field_and_satisfies_kind():
    txt = context_builder._section_user_profile(None)
    for f in TRAINING_PLAN_FIELDS:
        assert f in txt, f"training_plan field {f!r} is not documented in the write-shape home"
    for kind in _SATISFIES_VALIDATORS:
        assert kind in txt, f"satisfies kind {kind!r} is not documented in the write-shape home"
    # the type and its fixed key are named, and the supersede-not-append rule is stated.
    assert '"type": "training_plan"' in txt
    assert TRAINING_PLAN_KEY in txt
    assert "SUPERSEDES the whole plan" in txt and "NOT appended" in txt


# ---------- (b) e2e: the documented training_plan block lands a current row ----------

def test_documented_training_plan_block_lands_a_current_row(db_session):
    u = _user(db_session)
    payload = {
        "type": "training_plan",
        "key": TRAINING_PLAN_KEY,
        "value": {
            "macro": "## Offseason\nPhase 1 (base): rebuild aerobic base; buffer rule — "
                     "sacrifice conditioning first.",
            "revised_on": "2026-09-19",
            "revised_by": "coach",
        },
    }
    _, actions, results = _process_knowledge_updates(_block(payload), u.id, db_session)
    assert results and results[-1].saved is True, actions
    rows = (db_session.query(models.UserKnowledgeEntry)
            .filter_by(user_id=u.id, type="training_plan", active=True).all())
    assert len(rows) == 1
    assert rows[0].key == TRAINING_PLAN_KEY
    assert rows[0].value["revised_by"] == "coach"
    assert "buffer rule" in rows[0].value["macro"]


def test_documented_training_plan_rewrite_supersedes_by_key(db_session):
    """A second documented block supersedes the first (single-current), predecessor retained."""
    u = _user(db_session)
    first = {"type": "training_plan", "key": TRAINING_PLAN_KEY,
             "value": {"macro": "v1", "revised_on": "2026-09-19", "revised_by": "operator"}}
    second = {"type": "training_plan", "key": TRAINING_PLAN_KEY,
              "value": {"macro": "v2", "revised_on": "2026-09-20", "revised_by": "coach"}}
    _process_knowledge_updates(_block(first), u.id, db_session)
    _process_knowledge_updates(_block(second), u.id, db_session)
    active = (db_session.query(models.UserKnowledgeEntry)
              .filter_by(user_id=u.id, type="training_plan", active=True).all())
    assert len(active) == 1 and active[0].value["macro"] == "v2"
    allrows = (db_session.query(models.UserKnowledgeEntry)
               .filter_by(user_id=u.id, type="training_plan").all())
    assert len(allrows) == 2   # predecessor retained as history


# ---------- (c) e2e: the documented satisfies link lands on a schedule_item ----------

def test_documented_satisfies_link_lands_on_a_schedule_item(db_session):
    u = _user(db_session)
    payload = {
        "type": "schedule_item",
        "key": "gym_2026_09",
        "value": {
            "activity": "gym", "days": ["monday", "wednesday", "friday"],
            "hard": False, "expected_load": "moderate", "time_of_day": "morning",
            "same_day_training": False, "duration_weeks": None, "season_end": None,
            "satisfies": {"capacity": "stability"},
        },
    }
    _, actions, results = _process_knowledge_updates(_block(payload), u.id, db_session)
    assert results and results[-1].saved is True, actions
    row = (db_session.query(models.UserKnowledgeEntry)
           .filter_by(user_id=u.id, type="schedule_item", active=True).one())
    assert row.value["satisfies"] == {"capacity": "stability"}


# ---------- type-aware write-result footer (#313) ----------

def test_write_footer_is_type_aware(db_session):
    """A refusal/confirmation footer names the type — a training_plan is not labelled
    'Schedule entry' (the exact prod mislabel, 19 Sep: a training_plan save under the wrong key
    footered as 'Schedule entry NOT saved')."""
    u = _user(db_session, email="footer@example.com")

    # training_plan FAILURE — wrong key (the real prod key that was refused).
    bad_plan = {"type": "training_plan", "key": "offseason_2026_27",
                "value": {"macro": "x", "revised_on": "2026-09-19", "revised_by": "coach"}}
    _, acts, res = _process_knowledge_updates(_block(bad_plan), u.id, db_session)
    assert res[-1].saved is False and "Plan-of-record entry NOT saved" in acts[-1]

    # training_plan SUCCESS.
    ok_plan = {"type": "training_plan", "key": TRAINING_PLAN_KEY,
               "value": {"macro": "base", "revised_on": "2026-09-19", "revised_by": "coach"}}
    _, acts, res = _process_knowledge_updates(_block(ok_plan), u.id, db_session)
    assert res[-1].saved is True and "Plan-of-record entry saved" in acts[-1]

    # schedule_item FAILURE — bad shape (missing required fields).
    bad_sched = {"type": "schedule_item", "key": "s1", "value": {"activity": "gym"}}
    _, acts, res = _process_knowledge_updates(_block(bad_sched), u.id, db_session)
    assert res[-1].saved is False and "Schedule entry NOT saved" in acts[-1]

    # injury SUCCESS (injury has no validator, so its label is exercised on the success path).
    injury = {"type": "injury", "key": "left_knee",
              "value": {"body_part": "left knee", "restrictions": ["deep squat"]}}
    _, acts, res = _process_knowledge_updates(_block(injury), u.id, db_session)
    assert res[-1].saved is True and "Injury entry saved" in acts[-1]


# ---------- verbatim-macro instruction (behaviour, so assert the text is present) ----------

def test_protocol_text_requires_verbatim_macro():
    """The verbatim-storage rule is a BEHAVIOUR (the coach must not paraphrase the athlete's
    plan) and prompt behaviour is not unit-testable — so this asserts the instruction is
    present in the write-shape home, not that a model obeys it."""
    txt = context_builder._section_user_profile(None)
    assert "store it VERBATIM" in txt
    assert "edit only the affected line" in txt


# ---------- <thinking> is stripped from the displayed reply (#313) ----------

def test_strip_thinking_removes_the_block_keeps_the_reply():
    reply = "Here's your plan.\n<thinking>the athlete wants X so I will…</thinking>\nDone."
    out = _strip_thinking(reply)
    assert "<thinking>" not in out and "the athlete wants X" not in out
    assert "Here's your plan." in out and "Done." in out
    # case-insensitive + multiline, and a reply that is ONLY thinking collapses to empty.
    assert _strip_thinking("<THINKING>\nmulti\nline\n</THINKING>") == ""
