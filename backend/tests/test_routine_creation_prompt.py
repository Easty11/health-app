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


# --------------------------------------------------------------------------- #
# The Q144 contract: supersets can be expressed, and the fragile conventions   #
# are baked in so the model gets them right the first time.                    #
# --------------------------------------------------------------------------- #

def test_superset_id_is_documented():
    """The activation (d): without this the model cannot express a superset, and
    the plumbing that carries superset_id end-to-end stays dormant."""
    s = _section()
    assert "superset_id" in s
    assert "same" in s.lower() and "group" in s.lower()


def test_unilateral_pairing_is_the_highlighted_example():
    """Easty's stated priority — the model must be shown HOW to pair the two sides
    of a unilateral movement, not just told supersets exist."""
    s = _section()
    assert "unilateral" in s.lower()


def test_falsy_zero_superset_is_distinguished_from_null():
    """0 is a real group id; treating it as 'no group' is the classic falsy bug the
    prompt must not invite."""
    s = _section()
    assert '"superset_id": 0' in s or "superset_id\": 0" in s
    assert "null" in s.lower()


def test_rpe_is_forbidden_on_routine_sets():
    """The prompt half of the deterministic strip — the connector is the hard floor,
    but the model should not emit rpe to begin with."""
    s = _section()
    assert "rpe" in s.lower()
    assert "do not put" in s.lower() or "not put" in s.lower()


def test_no_at_sign_in_notes_convention():
    s = _section()
    assert '"@"' in s and "notes" in s.lower()


def test_snake_case_and_at_least_one_set_conventions():
    s = _section()
    assert "snake_case" in s.lower()
    assert "at least one set" in s.lower()


def test_missing_weight_is_omit_not_zero():
    """0 is a real load; the prompt must say omit rather than send zero."""
    s = _section()
    assert "weight_kg" in s
    assert "0 is a real load" in s or "not \"unweighted\"" in s or "unweighted" in s.lower()


# --------------------------------------------------------------------------- #
# The routine-id contract (11 Oct 2026): ids come from the routine line too.   #
# --------------------------------------------------------------------------- #

def _flat() -> str:
    """The section with whitespace collapsed, so a pin survives a re-wrap of the prose."""
    return " ".join(_section().split())


def test_ids_may_be_copied_from_the_routines_section_or_the_history():
    """The 11 Oct Session B incident: the routines section rendered titles only, so the only ids
    in view were history ids and the model reused (L)'s for (R). The rule must name BOTH sources."""
    s = _flat()
    assert "on its line in the `## Hevy routines` section, or in the workout history above" in s
    assert "NEITHER place above" in s


def test_an_update_uses_the_id_on_the_existing_routine_line():
    s = _flat()
    assert "When UPDATING a routine, an exercise that is already in that routine MUST use " \
           "the ID shown on its own line in that routine" in s
    assert "never an ID from the workout history for a same-named or sibling movement" in s
    assert "separate exercises with separate IDs" in s


def test_update_block_notes_say_where_the_existing_ids_come_from():
    s = _flat()
    assert "Copy each existing exercise's `exercise_template_id` from its `[ID: ...]` on that routine line" in s


def test_never_invent_survives_and_now_names_both_sources():
    """The guard is unchanged in force; only the list of places an id may be read from grew."""
    s = _flat()
    assert "NEVER invent or guess an exercise_template_id" in s
    assert "An ID you did not read from the `## Hevy routines` section or the history above is always wrong" in s


def test_one_of_two_fields_rule_is_unchanged():
    assert "never both" in _flat().lower()


def test_an_unmatched_title_report_is_stamped_as_not_in_the_catalogue_this_turn():
    """The model narrated catalogue facts it could not see ("it is there", "L and R share the same
    template ID") after write failures. A miss is a statement about the catalogue as synced this
    turn, nothing more."""
    s = _flat()
    assert "not in the catalogue as synced this turn" in s
    assert "Do not assert that the exercise exists" in s
    assert "do not speculate about shared or sibling IDs" in s


def test_pass2_narration_carries_the_same_stamp():
    """Pass-2 is where the post-failure narration is generated, so the stamp has to reach it too."""
    from routers.chat import _PASS2_SYSTEM
    flat = " ".join(_PASS2_SYSTEM.split())
    assert "unresolved_exercise" in flat
    assert "not in the catalogue as synced this turn" in flat
    assert "do not speculate about shared or sibling exercise IDs" in flat
