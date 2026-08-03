"""The chat model can see the whole Hevy catalogue (#NEXT).

Observed in prod 2026-08-03: asked "are nordics in the hevy catalogue?", the model replied
it could only confirm exercises appearing in the workout history, said it could not see
Hevy's built-in catalogue, and offered to "pull the Hevy exercise catalogue endpoint" — i.e.
to build `#61`, which shipped and is live with 500 rows.

Both claims were false about the system. `hevy_exercise_templates` holds the full catalogue
and `resolve_exercise` / `suggest_candidates` already run over all of it. The only gap was
that `build_system_prompt` never surfaced it, so the model reasoned from the ten recent
workouts it was handed. This adds no capability — it exposes one.

**The reader is called upstream in `chat.py`, never in `context_builder`.** That module is a
pure formatter and gets no `Session` (the `#43` parity-guard invariant), so the section takes
already-read rows. `test_section_takes_data_not_a_session` pins that, because the brief
originally specified `_section_exercise_catalogue(db, user_id, connected)` and following it
literally would have broken the guard.
"""
import inspect

import context_builder
import models
from context_builder import (
    _section_exercise_catalogue,
    _section_exercise_creation,
    _section_routine_creation,
    build_system_prompt,
)
from hevy_templates import catalogue_titles


def _tmpl(db, tid, title, *, is_custom=False, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=is_custom, owner_user_id=owner))
    db.commit()


def _seed(db, user_id=1):
    _tmpl(db, "D1", "Nordic Hamstrings Curls")
    _tmpl(db, "D2", "Bench Press (Barbell)")
    _tmpl(db, "D3", "Glute Ham Raise")
    _tmpl(db, "C1", "Prone Hamstring Curl", is_custom=True, owner=user_id)
    _tmpl(db, "C2", "Copenhagen Plank (Short Lever)", is_custom=True, owner=user_id)
    _tmpl(db, "X1", "Someone Else's Lift", is_custom=True, owner=999)


# --------------------------------------------------------------------------- #
# G1 — the reader: same scope as the resolver, stable order.                   #
# --------------------------------------------------------------------------- #

def test_catalogue_titles_returns_defaults_and_own_customs(db_session):
    _seed(db_session)
    rows = catalogue_titles(db_session, 1)
    titles = [t for t, _ in rows]
    assert "Nordic Hamstrings Curls" in titles
    assert "Prone Hamstring Curl" in titles


def test_catalogue_excludes_another_users_custom(db_session):
    """Scope must equal `_visible_to` — the SAME predicate the resolver uses. Showing a
    title the resolver would refuse is the instrument disagreeing with the behaviour."""
    _seed(db_session)
    titles = [t for t, _ in catalogue_titles(db_session, 1)]
    assert "Someone Else's Lift" not in titles


def test_catalogue_flags_custom_vs_default(db_session):
    _seed(db_session)
    by_title = dict(catalogue_titles(db_session, 1))
    assert by_title["Nordic Hamstrings Curls"] is False
    assert by_title["Prone Hamstring Curl"] is True


def test_catalogue_order_is_defaults_first_then_title(db_session):
    """Stable across turns, so the prompt does not churn between requests."""
    _seed(db_session)
    rows = catalogue_titles(db_session, 1)
    flags = [c for _, c in rows]
    assert flags == sorted(flags)                      # defaults (False) first
    defaults = [t for t, c in rows if not c]
    assert defaults == sorted(defaults)


def test_empty_catalogue_returns_empty_list(db_session):
    assert catalogue_titles(db_session, 1) == []


# --------------------------------------------------------------------------- #
# G2 — the section renders, and is absent without a catalogue.                 #
# --------------------------------------------------------------------------- #

def test_section_lists_titles_split_by_custom_and_default():
    s = _section_exercise_catalogue([
        ("Nordic Hamstrings Curls", False), ("Bench Press (Barbell)", False),
        ("Prone Hamstring Curl", True),
    ])
    assert "Nordic Hamstrings Curls" in s
    assert "Prone Hamstring Curl" in s
    assert "### The user's custom exercises (1)" in s
    assert "### Hevy built-in exercises (2)" in s


def test_section_absent_when_no_catalogue():
    assert _section_exercise_catalogue([]) == ""
    assert _section_exercise_catalogue(None) == ""


def test_section_renders_with_no_customs():
    s = _section_exercise_catalogue([("Bench Press (Barbell)", False)])
    assert "- (none)" in s
    assert "### Hevy built-in exercises (1)" in s


def test_section_takes_data_not_a_session():
    """`context_builder` is a pure formatter — the #43 parity-guard invariant.

    The brief specified `_section_exercise_catalogue(db, user_id, connected)`. Following
    that literally would have put a Session and a query inside the module whose whole
    contract is that it performs neither. This asserts the corrected signature.
    """
    params = list(inspect.signature(_section_exercise_catalogue).parameters)
    assert params == ["catalogue"]
    assert "db" not in params and "user_id" not in params


def test_context_builder_module_performs_no_db_queries():
    """Guards the invariant at module level, not just this one function."""
    src = inspect.getsource(context_builder)
    for forbidden in ("sqlalchemy", "db.query(", "db.execute(", "SessionLocal"):
        assert forbidden not in src, f"context_builder must not reference {forbidden}"


# --------------------------------------------------------------------------- #
# G3 — the section kills the two false claims, by assertion not by hope.       #
# --------------------------------------------------------------------------- #

def test_section_states_it_is_the_full_catalogue_not_history():
    s = _flat(_section_exercise_catalogue([("Bench Press (Barbell)", False)]))
    assert "FULL catalogue" in s
    assert "not read from workout history" in s
    assert "Do NOT say you can only see exercises that appear in the workout history" in s


def test_section_forbids_offering_to_build_the_integration():
    """The prod reply offered to 'pull the Hevy exercise catalogue endpoint' — i.e. to
    build #61, already live. That offer must have no basis left in the prompt."""
    s = _flat(_section_exercise_catalogue([("Bench Press (Barbell)", False)]))
    assert "Do NOT offer to build, pull, or extend a catalogue integration" in s


def test_section_warns_titles_must_be_copied_exactly():
    """14 of the 500 live titles carry non-ASCII characters (U+2011 non-breaking hyphen).
    They render normally and fail a byte-exact resolve if retyped."""
    s = _section_exercise_catalogue([("Single‑Leg RDL", True)])
    assert "copied EXACTLY" in s
    assert "non-breaking hyphen" in s
    assert "Single‑Leg RDL" in s                   # rendered verbatim, not normalised


# --------------------------------------------------------------------------- #
# G4 — the contracts no longer assert history-only visibility.                 #
# --------------------------------------------------------------------------- #

def _flat(text: str) -> str:
    """Whitespace-normalised, so a prose assertion is not defeated by a line wrap."""
    return " ".join(text.split())


def test_routine_contract_states_full_catalogue_visibility():
    s = _flat(_section_routine_creation(["hevy"]))
    assert "NOT just exercises that appear in the workout history" in s
    assert "Never say you can only confirm exercises from the workout history" in s
    assert "Never offer to build, pull, or extend a Hevy catalogue integration" in s


def test_exercise_contract_points_at_the_catalogue_before_creating():
    s = _flat(_section_exercise_creation(["hevy"]))
    assert "CHECK THE CATALOGUE LIST ABOVE BEFORE EMITTING THIS BLOCK" in s
    assert "permanent and cannot be undone" in s


def test_contracts_still_absent_when_hevy_not_connected():
    assert _section_routine_creation([]) == ""
    assert _section_exercise_creation([]) == ""


# --------------------------------------------------------------------------- #
# G5 — end to end through build_system_prompt.                                 #
# --------------------------------------------------------------------------- #

def _prompt(catalogue, **kw):
    from current_state import CurrentState
    user = models.User(email="a@b.c", hashed_password="x")
    state = CurrentState(
        device_profile=None, knowledge_entries=[], fortification_profile=None,
        labs=[], hrv_baseline_7d=None,
    )
    return build_system_prompt(
        user=user, connected_integrations=["hevy"], state=state,
        exercise_catalogue=catalogue, **kw,
    )


def test_prompt_contains_the_catalogue_when_supplied():
    p = _prompt([("Nordic Hamstrings Curls", False), ("Prone Hamstring Curl", True)])
    assert "Hevy Exercise Catalogue (complete, synced server-side)" in p
    assert "Nordic Hamstrings Curls" in p


def test_prompt_omits_the_section_entirely_without_a_catalogue():
    p = _prompt(None)
    assert "Hevy Exercise Catalogue" not in p


def test_the_reported_prod_question_is_now_answerable_from_the_prompt():
    """The concrete case: 'are nordics in the hevy catalogue?'

    With the real default title present in the prompt, the model has the fact in front of
    it. Note the actual Hevy title is `Nordic Hamstrings Curls` — both words plural — which
    is precisely why the list is injected rather than left to recall.
    """
    p = _flat(_prompt([("Nordic Hamstrings Curls", False)]))
    assert "Nordic Hamstrings Curls" in p
    assert "Do NOT say you can only see exercises that appear in the workout history" in p
