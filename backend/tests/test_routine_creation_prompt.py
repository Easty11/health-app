"""The routine-creation prompt section — its own explicit guard (#80/#82).

This section left the pre-refactor parity guard's scope permanently (#80): #82
changes it by intent, so `old == new` against PRE_REFACTOR_SHA can never hold
again and the SHA cannot move without going vacuous. The parity guard now
excludes it via `connected_integrations=[]`; these tests are what replaces that
coverage, pinning the CONTRACT the section states rather than its exact bytes.

Pinning behaviour, not bytes, is deliberate: a byte-snapshot of current output
would re-bless whatever is current on every update — a change-detector that
ratifies drift (FEEDBACK §10, false-green instruments).
"""
import context_builder


def _section() -> str:
    return context_builder._section_routine_creation(["hevy"])


def test_section_absent_without_hevy():
    assert context_builder._section_routine_creation([]) == ""
    assert context_builder._section_routine_creation(["polar"]) == ""


# --------------------------------------------------------------------------- #
# The #82 contract: id XOR title, never a guessed id.                          #
# --------------------------------------------------------------------------- #

def test_title_emission_is_permitted():
    """The activation itself (#82). The old text told the model to 'say so' when
    it had no id, which kept the landed #60/#61 resolver dormant — the resolver
    fires only for an exercise missing an id but carrying a title, and nothing
    ever emitted a title."""
    s = _section()
    assert '"title"' in s
    assert "never emit" not in s.lower() or "title" in s
    # The dormancy-causing instruction must be gone.
    assert "If you don't know the template ID for an exercise, say so" not in s


def test_guessing_an_id_is_still_forbidden():
    """Permitting titles must not weaken the hallucination guard — that guard is
    why the rule existed. Titles are the escape hatch, not invented ids."""
    s = _section()
    assert "NEVER invent or guess an exercise_template_id" in s


def test_id_is_preferred_when_the_exercise_is_in_history():
    s = _section()
    assert "exercise_template_id" in s
    assert "workout history above" in s


def test_exactly_one_identifying_field():
    s = _section()
    assert "never both" in s.lower()


def test_titles_are_stated_to_match_exactly_and_be_reported_back():
    """#82 keeps matching EXACT (fuzzy remains #60's explicit non-goal) and
    surfaces misses. The model must be told BOTH, or it will either expect fuzzy
    forgiveness or assume a miss is silently dropped."""
    s = _section()
    assert "matched exactly" in s.lower()
    assert "reported back" in s.lower()
    assert "not created" in s.lower()


def test_uncatalogued_marker_is_explained():
    """The renderer marks drifted/uncatalogued movements (#81); the prompt must
    say what that marker means, or it is noise the model cannot act on."""
    s = _section()
    assert "[UNCATALOGUED]" in s


def test_confirm_before_creating_survives():
    """Pre-existing contract, unchanged by #82 — pinned so the rewrite cannot
    quietly drop it."""
    s = _section()
    assert "ALWAYS confirm with the user before creating a routine" in s


def test_set_type_and_field_placement_survive():
    s = _section()
    assert '"normal", "warmup", "dropset", "failure"' in s
    assert "rest_seconds sits on the exercise, not the set" in s
