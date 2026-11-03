"""The injury row has a closed shape (DECISIONS_LOG "The injury row has a closed shape"; PR-A of the
injury-lifecycle-in-app brief).

`type="injury"` was the one typed entry with no validator. Now: closed keys; `side` / `signal_type`
enums; `ra_flare` a strict boolean; `body_part` in the vocabulary declared beside the engine-defaults
alias table (a same-key rewrite may keep an existing off-vocabulary part byte-for-byte: user 9's
`foot/hip`); `restrictions` refused on a new row and carried only byte-identical on a rewrite; seven
OPTIONAL injury-model fields (design 0009) admitted and enum- or existence-checked only, read by
nothing. Every channel (api, chat) passes the validator; the chat refusal names the valid set so the
#344 bounded retry recovers it. The frontend's mirrored vocabulary is pinned against the Python tuple.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import models
import typed_entries
from auth import get_current_user
from database import get_db
from engine import engine_defaults as ed
from engine import selection, taxonomy
from load_metrics import _local_day
from routers import chat as chat_router
from routers import knowledge as kn
from routers.knowledge import (
    INJURY_ENUMS, INJURY_FIELDS, INJURY_OPTIONAL_FIELDS, KnowledgeEntryIn, TypedEntryRefused,
    upsert_knowledge_entry, validate_injury,
)

REVIEW = date(2026, 12, 14)
BARE = {"body_part": "knee", "side": "left", "signal_type": "mechanical"}
FULL_OPTIONAL = {
    "onset_on": "2026-10-20", "course": "acute", "mechanism": "contact", "tissue": "medial meniscus",
    "diagnosis_status": "suspected",
}
FOOT_HIP = {"body_part": "foot/hip", "side": "left", "signal_type": "mechanical"}   # user 9, id 163
LEGACY_RESTRICTED = {"body_part": "lumbar", "side": "bilateral", "signal_type": "mechanical",
                     "restrictions": ["heavy hinge at end of range", "end-range lumbar flexion combined with twisting"]}


def _user(db, email="shape@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _orm_injury(db, user_id, key, value, *, active=True, id_=None):
    """Straight to the ORM, as prod holds a legacy row (the validator never ran on it)."""
    row = models.UserKnowledgeEntry(user_id=user_id, type="injury", key=key, value=value, source="api",
                                    added_at=date(2026, 7, 1), active=active, **({"id": id_} if id_ else {}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _put(db, user, key, value, source="api"):
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(type="injury", key=key, value=value, source=source), db)


# ── A2: the vocabulary ───────────────────────────────────────────────────────

@pytest.mark.parametrize("part", ed.INJURY_BODY_PARTS)
def test_every_vocabulary_entry_plans_without_raising(db_session, part):
    u = _user(db_session)
    plan = ed.plan_engine_defaults(db_session, u.id, f"injury_{part}_left",
                                   {"body_part": part, "side": "left", "signal_type": "mechanical"}, REVIEW)
    assert set(plan) == {"planned", "skipped", "conflicts"}
    for p in plan["planned"]:
        kn.validate_constraint(p["value"])          # a planned default is itself a valid row


def test_every_alias_table_key_is_in_the_vocabulary():
    """The planner keys on `body_part`: a map key missing from the vocabulary could never be written."""
    assert set(ed._ACUTE_TISSUE_BLOCKS) <= set(ed.INJURY_BODY_PARTS)
    assert len(set(ed.INJURY_BODY_PARTS)) == len(ed.INJURY_BODY_PARTS)
    assert all(p == p.lower() == p.strip() for p in ed.INJURY_BODY_PARTS)


@pytest.mark.parametrize("raw,expected", [
    ("pes anserine", "knee"), ("Pes Anserine ", "knee"), ("rotator cuff", "shoulder"),
    ("left hamstring", "hamstring"), ("lumbar spine", "lumbar"), ("cervical_spine", "neck"),
    ("foot/hip", "foot"), ("semimembranosus", "hamstring"), ("Knee", "knee"), ("", None), ("spleen", None),
])
def test_suggest_body_part_names_the_entry_meant(raw, expected):
    assert ed.suggest_body_part(raw) == expected


def _js_list(name: str) -> list[str]:
    src = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "injuryVocabulary.js").read_text()
    m = re.search(rf"export const {name} = \[(.*?)\]", src, re.S)
    assert m, f"{name} missing from the frontend mirror"
    return re.findall(r"'([^']+)'", m.group(1))


@pytest.mark.parametrize("js_name,py_values", [
    ("INJURY_BODY_PARTS", ed.INJURY_BODY_PARTS),
    ("INJURY_SIDES", kn.INJURY_SIDES),
    ("INJURY_SIGNAL_TYPES", kn.INJURY_SIGNAL_TYPES),
    ("INJURY_COURSES", kn.INJURY_COURSES),
    ("INJURY_DIAGNOSIS_STATUSES", kn.INJURY_DIAGNOSIS_STATUSES),
])
def test_the_frontend_mirror_equals_the_validator(js_name, py_values):
    """No route serves the vocabulary; the card's selects read a mirrored constant, pinned here."""
    assert _js_list(js_name) == list(py_values)


# ── A1 / A6: refusals ────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad,needle", [
    ({**BARE, "colour": "red"}, "unknown field(s) ['colour']"),
    ({**BARE, "side": "both"}, "injury.side: 'both' is not one of ['left', 'right', 'bilateral']"),
    ({**BARE, "signal_type": "nervy"}, "injury.signal_type: 'nervy' is not one of"),
    ({**BARE, "body_part": "pes anserine"}, "injury.body_part: 'pes anserine' is not in the injury body-part vocabulary -- use 'knee'; valid: ['hamstring'"),
    ({**BARE, "body_part": "spleen"}, "'spleen' is not in the injury body-part vocabulary; valid:"),
    ({**BARE, "body_part": " "}, "injury.body_part must be a non-empty string"),
    ({"side": "left"}, "missing required field(s) ['body_part']"),
    ({**BARE, "restrictions": ["no heel raises"]}, "injury.restrictions is not written on a new injury"),
    ({**BARE, "ra_flare": "yes"}, "injury.ra_flare must be a strict boolean"),
    ({**BARE, "detail": 3}, "injury.detail must be a string or null"),
    ({**BARE, "course": "sudden"}, "injury.course: 'sudden' is not one of ['acute', 'gradual', 'chronic', 'niggle']"),
    ({**BARE, "mechanism": "fall"}, "injury.mechanism: 'fall' is not one of ['contact', 'velocity', 'load', 'insidious', 'unknown']"),
    ({**BARE, "diagnosis_status": "confirmed"}, "injury.diagnosis_status: 'confirmed' is not one of ['suspected', 'imaged', 'clinician_confirmed']"),
    ({**BARE, "onset_on": "20 Oct"}, "injury.onset_on"),
    ({**BARE, "tissue": "  "}, "injury.tissue"),
    ({**BARE, "trajectory": "settling"}, "injury.trajectory must be an object or null"),
    ({**BARE, "resolution": {"basis": "x"}}, "stamped by its route"),
])
def test_shape_refusals_name_the_rule(bad, needle):
    with pytest.raises(ValueError) as exc:
        validate_injury(bad, existing=None)
    assert needle in str(exc.value)


def test_restrictions_grown_on_a_rewrite_is_refused():
    with pytest.raises(ValueError, match="only be carried unchanged"):
        validate_injury({**LEGACY_RESTRICTED, "restrictions": [*LEGACY_RESTRICTED["restrictions"], "new one"]},
                        existing=LEGACY_RESTRICTED)
    with pytest.raises(ValueError, match="only be carried unchanged"):   # reordered is not identical
        validate_injury({**LEGACY_RESTRICTED, "restrictions": list(reversed(LEGACY_RESTRICTED["restrictions"]))},
                        existing=LEGACY_RESTRICTED)
    with pytest.raises(ValueError, match="only be carried unchanged"):   # a key the row never had
        validate_injury({**BARE, "restrictions": []}, existing=BARE)


def test_a_legacy_body_part_may_be_kept_but_not_changed_to_another_off_vocabulary_part(db_session):
    u = _user(db_session)
    _orm_injury(db_session, u.id, "injury_pigeon_foot_left", FOOT_HIP, id_=163)
    kept = _put(db_session, u, "injury_pigeon_foot_left", {**FOOT_HIP, "detail": "re-worded"})
    assert kept.value["body_part"] == "foot/hip"                       # byte-for-byte, never rewritten
    with pytest.raises(ValueError, match="'foot/ hip' is not in the injury body-part vocabulary -- use 'foot'"):
        _put(db_session, u, "injury_pigeon_foot_left", {**FOOT_HIP, "body_part": "foot/ hip"})
    moved = _put(db_session, u, "injury_pigeon_foot_left", {**FOOT_HIP, "body_part": "foot"})
    assert moved.value["body_part"] == "foot"                          # a vocabulary part is always accepted


def test_dangling_problem_key_and_unknown_recurrence_of_are_refused(db_session):
    u = _user(db_session)
    _orm_injury(db_session, u.id, "injury_knee_left_old", BARE, active=False)
    with pytest.raises(TypedEntryRefused, match="problem_key 'injury_lumbar_spine' names no active injury row") as exc:
        _put(db_session, u, "injury_knee_left", {**BARE, "problem_key": "injury_lumbar_spine"})
    assert exc.value.code == "invalid_parent"
    with pytest.raises(TypedEntryRefused, match="problem_key 'injury_knee_left_old' names no active injury row"):
        _put(db_session, u, "injury_knee_left", {**BARE, "problem_key": "injury_knee_left_old"})   # resolved: not a problem
    with pytest.raises(TypedEntryRefused, match="recurrence_of 'injury_nothing' names no injury row"):
        _put(db_session, u, "injury_knee_left", {**BARE, "recurrence_of": "injury_nothing"})
    with pytest.raises(TypedEntryRefused, match="must not name the entry itself"):
        _put(db_session, u, "injury_knee_left", {**BARE, "recurrence_of": "injury_knee_left"})
    assert db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).count() == 0


def test_another_users_injury_is_not_a_valid_problem_or_recurrence(db_session):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    _orm_injury(db_session, a.id, "injury_lumbar_spine", {"body_part": "lumbar"})
    with pytest.raises(TypedEntryRefused, match="invalid_parent|names no"):
        _put(db_session, b, "injury_knee_left", {**BARE, "problem_key": "injury_lumbar_spine"})


# ── acceptances ──────────────────────────────────────────────────────────────

def test_legacy_restrictions_are_carried_byte_identical_on_a_rewrite(db_session):
    u = _user(db_session)
    _orm_injury(db_session, u.id, "injury_lumbar_spine", LEGACY_RESTRICTED, id_=94)
    row = _put(db_session, u, "injury_lumbar_spine", {**LEGACY_RESTRICTED, "detail": "re-worded"})
    assert row.value["restrictions"] == LEGACY_RESTRICTED["restrictions"]
    dropped = _put(db_session, u, "injury_lumbar_spine", {k: v for k, v in LEGACY_RESTRICTED.items() if k != "restrictions"})
    assert "restrictions" not in dropped.value                           # shrinking is not growing


def test_every_optional_field_absent_and_every_optional_field_present(db_session):
    u = _user(db_session)
    _orm_injury(db_session, u.id, "injury_lumbar_spine", {"body_part": "lumbar", "side": "bilateral"})
    _orm_injury(db_session, u.id, "injury_knee_left_2025", {"body_part": "knee", "side": "left"}, active=False)
    bare = _put(db_session, u, "injury_knee_left", BARE)
    assert bare.value == BARE
    full_value = {**BARE, **FULL_OPTIONAL, "problem_key": "injury_lumbar_spine", "recurrence_of": "injury_knee_left_2025",
                  "ra_flare": False, "detail": "x", "trajectory": {"shape": "settling", "declared_on": "2026-10-21"}}
    assert set(INJURY_OPTIONAL_FIELDS) <= set(full_value)
    full = _put(db_session, u, "injury_knee_left", full_value)
    assert full.value == full_value                                      # stored as written, nothing canonicalised
    assert set(full.value) <= set(INJURY_FIELDS)


def test_a_row_carrying_every_optional_field_changes_the_engine_and_the_renderers_in_nothing(db_session):
    """The seven fields are admitted and read by nothing: `is_contraindicated`, `compute_probe_queue`, the
    engine-defaults planner and `## Constraints` are identical for the bare row and the full one."""
    u = _user(db_session)
    _orm_injury(db_session, u.id, "injury_lumbar_spine", {"body_part": "lumbar", "side": "bilateral"})
    _orm_injury(db_session, u.id, "injury_knee_left_2025", {"body_part": "knee", "side": "left"}, active=False)
    full_value = {**BARE, **FULL_OPTIONAL, "problem_key": "injury_lumbar_spine", "recurrence_of": "injury_knee_left_2025"}

    def observe(value):
        _put(db_session, u, "injury_knee_left", value)
        rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).all()
        active = selection.gather_active_constraints(db_session, u.id)
        verdicts = [selection.is_contraindicated(r, s, profile_hard_stops=None, active_constraints=active)
                    for r in taxonomy.all_regions() for s in (taxonomy.SIDE_LEFT, taxonomy.SIDE_RIGHT)]
        queue = selection.compute_probe_queue(db_session, u.id, profile=None, loaded_region_keys=set())
        plan = ed.plan_engine_defaults(db_session, u.id, "injury_knee_left", value, REVIEW)
        section = context_builder._section_constraints(
            typed_entries.lift_constraints(rows), typed_entries.active_keys(rows), _local_day())
        return verdicts, queue, plan, section

    bare = observe(BARE)
    full = observe(full_value)
    assert full == bare
    # And the planner proposed the knee defaults once (the rewrite's signature is unchanged → no second set).
    assert [p["region_key"] for p in bare[2]["planned"]] == []           # already covered by the first write
    assert db_session.query(models.UserKnowledgeEntry).filter(
        models.UserKnowledgeEntry.key.like("constraint_engine_injury_knee_left_%")).count() == 3


# ── A3: every channel ────────────────────────────────────────────────────────

def _client(db, user):
    app = FastAPI()
    app.include_router(kn.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_the_api_channel_refuses_with_422_naming_the_valid_set(db_session):
    u = _user(db_session)
    r = _client(db_session, u).post("/knowledge/entry", json={
        "type": "injury", "key": "injury_knee_left", "source": "api", "value": {**BARE, "body_part": "patella"}})
    assert r.status_code == 422
    assert "use 'knee'" in r.json()["detail"] and "'rib'" in r.json()["detail"]
    assert db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id).count() == 0


def test_the_api_channel_accepts_the_cards_rewrite(db_session):
    """What the Injuries card's Edit posts: a same-key rewrite with `source: "api"`, carrying the row's
    restrictions unchanged; a side change re-proposes the engine defaults (#487)."""
    u = _user(db_session)
    _orm_injury(db_session, u.id, "injury_knee_left", {**BARE, "restrictions": ["deep loaded knee flexion"]}, id_=119)
    client = _client(db_session, u)
    r = client.post("/knowledge/entry", json={
        "type": "injury", "key": "injury_knee_left", "source": "api",
        "value": {**BARE, "side": "right", "restrictions": ["deep loaded knee flexion"], "course": "chronic"}})
    assert r.status_code == 201, r.text
    proposals = client.get("/knowledge/proposals").json()
    assert {p["value"]["scope"]["side"] for p in proposals} == {"right"}
    assert len(proposals) == 3


class _FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0) if self.replies else "Draft."
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _kb(value, key="injury_knee_left"):
    return "<knowledge_update>" + json.dumps({"type": "injury", "key": key, "value": value}) + "</knowledge_update>"


def test_the_chat_channel_refusal_is_retried_once_with_the_valid_set_and_the_fix_saves(db_session, monkeypatch):
    """End to end through `/chat`, the model faked at the transport layer (#344's bounded retry)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = _user(db_session, "retry-injury@example.com")
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    fake = SimpleNamespace(messages=_FakeMessages(["Noting it.\n" + _kb({**BARE, "body_part": "pes anserine"}),
                                                   _kb(BARE)]))
    monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
    r = TestClient(app).post("/chat", json={"message": "my pes anserine is sore", "conversation_history": []})
    assert r.status_code == 200, r.text
    calls = fake.messages.calls
    assert len(calls) == 2                                               # draft + ONE retry, no pass-2
    retry_msg = calls[1]["messages"][-1]["content"]
    assert "use 'knee'" in retry_msg and "valid: ['hamstring'" in retry_msg
    wr = r.json()["write_results"][0]
    assert wr["saved"] is True and wr["retried"] is True
    (row,) = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, type="injury").all()
    assert row.value == BARE and row.source == "chat"


# ── A5: the prompt ───────────────────────────────────────────────────────────

SECTION = context_builder._section_knowledge_update()
SHAPE = context_builder._injury_write_shape()


def test_the_injury_shape_is_generated_into_the_section():
    assert SHAPE in SECTION
    words = set(re.findall(r"[a-z_/]+", SHAPE))
    for name in (*INJURY_FIELDS, *(v for vals in INJURY_ENUMS.values() for v in vals), *ed.INJURY_BODY_PARTS):
        assert name in words, name
    assert "Never send restrictions, trajectory" in SHAPE
    assert 'propose a `type="constraint"` parented to that injury' in SECTION


def test_the_prompt_example_carries_course_and_onset_and_no_restrictions():
    block = SECTION[SECTION.index('<knowledge_update>\n{"type": "injury"'):]
    example = json.loads(block[len("<knowledge_update>\n"):block.index("\n</knowledge_update>")])
    assert set(example["value"]) == {"body_part", "side", "signal_type", "course", "onset_on"}
    validate_injury(example["value"], existing=None)


def test_the_onboarding_interview_no_longer_teaches_restrictions():
    text = context_builder._section_onboarding_interview()
    assert '"restrictions": [...]' not in text and "never `restrictions`" in text
