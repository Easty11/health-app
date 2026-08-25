"""D-E laterality session-pairing rule (DECISIONS_LOG #74/#76).

Positive, negative, and MUTATION-PROOFED (FEEDBACK §17/§18): the rule must
discriminate on the laterality TAG's identity and on block COUNT — a test that
would pass regardless of the tag is worthless. Each positive is paired with the
same structure under a different tag that flips the outcome, so a rule that
ignored the tag (or the count) fails here.
"""
from laterality import detect_session_pairing, blocks_from_workout

LAT = {"UNI": "unilateral", "BI": "bilateral", "ALT": "alternating", "UNT": None}


# ── Positive ────────────────────────────────────────────────────────────────

def test_unilateral_two_blocks_is_paired():
    """Unilateral template in two blocks of one session → paired (halve)."""
    result = detect_session_pairing([(0, "UNI"), (1, "UNI")], LAT)
    assert result.paired == {"UNI": [0, 1]}
    assert result.indeterminate == {}


def test_unilateral_paired_among_other_work():
    """The pair is isolated from unrelated bilateral blocks in the same session."""
    blocks = [(0, "BI"), (1, "UNI"), (2, "UNI"), (3, "BI")]
    result = detect_session_pairing(blocks, LAT)
    assert result.paired == {"UNI": [1, 2]}


def test_three_unilateral_blocks_all_grouped():
    """More than two blocks of a unilateral template still group as one movement."""
    result = detect_session_pairing([(0, "UNI"), (1, "UNI"), (2, "UNI")], LAT)
    assert result.paired == {"UNI": [0, 1, 2]}


# ── Negative ────────────────────────────────────────────────────────────────

def test_unilateral_single_block_not_paired():
    """One unilateral block = both limbs logged together; no block-level double count."""
    result = detect_session_pairing([(0, "UNI"), (1, "BI")], LAT)
    assert result.paired == {}
    assert result.indeterminate == {}


def test_bilateral_two_blocks_not_paired():
    """Two bilateral blocks of the same movement are separate legitimate volume."""
    result = detect_session_pairing([(0, "BI"), (1, "BI")], LAT)
    assert result.paired == {}


def test_alternating_two_blocks_not_paired():
    """Alternating carries both limbs within a block; repeated blocks are not a pair."""
    result = detect_session_pairing([(0, "ALT"), (1, "ALT")], LAT)
    assert result.paired == {}


def test_untagged_two_blocks_is_indeterminate_not_paired():
    """Untagged repeated blocks are surfaced as indeterminate, never silently paired."""
    result = detect_session_pairing([(0, "UNT"), (1, "UNT")], LAT)
    assert result.paired == {}
    assert result.indeterminate == {"UNT": [0, 1]}


def test_missing_tag_treated_as_untagged_not_bilateral():
    """A template id absent from the tag map fails closed to indeterminate."""
    result = detect_session_pairing([(0, "ZZZ"), (1, "ZZZ")], {})
    assert result.paired == {}
    assert result.indeterminate == {"ZZZ": [0, 1]}


# ── Mutation-proofing: outcome must depend on the tag and the count ──────────

def test_same_structure_flips_with_tag():
    """IDENTICAL block structure, only the tag differs → outcome must differ.

    Kills a mutant that ignores laterality (e.g. pairs any repeated template).
    """
    structure = [(0, "X"), (1, "X")]
    assert detect_session_pairing(structure, {"X": "unilateral"}).paired == {"X": [0, 1]}
    assert detect_session_pairing(structure, {"X": "bilateral"}).paired == {}
    assert detect_session_pairing(structure, {"X": "alternating"}).paired == {}
    assert detect_session_pairing(structure, {"X": None}).paired == {}


def test_pairing_depends_on_block_count():
    """Same unilateral tag, one block vs two → only two pairs.

    Kills a mutant that pairs on tag alone regardless of repetition.
    """
    assert detect_session_pairing([(0, "UNI")], LAT).paired == {}
    assert detect_session_pairing([(0, "UNI"), (1, "UNI")], LAT).paired == {"UNI": [0, 1]}


# ── Adapter ─────────────────────────────────────────────────────────────────

def test_blocks_from_workout_skips_missing_template_ids():
    raw = {"exercises": [
        {"exercise_template_id": "A", "sets": []},
        {"sets": []},                                  # no template id — skipped
        {"exercise_template_id": "B", "sets": []},
    ]}
    assert blocks_from_workout(raw) == [(0, "A"), (2, "B")]
