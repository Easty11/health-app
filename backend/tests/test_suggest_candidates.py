"""Ranked candidate suggestions for unresolved titles (DECISIONS_LOG #83).

The catalogue slice below is PROD-REALISTIC, not convenient: every title is real
in the 494-row prod catalogue (2026-07-14). That matters for
test_leg_curl_has_at_least_two_candidates — the anti-auto-resolve evidence. A
10-row fixture would have made `Leg Curl (Machine)` look unique and the
uniqueness shortcut look safe.
"""
import models
from hevy_templates import _tokens, resolve_exercise, suggest_candidates

USER = 7
OTHER_USER = 8

# Real prod titles. The Leg Curl pair and the three Bulgarian/Split candidates
# are the load-bearing ones.
CATALOGUE = [
    ("B5D3A742", "Bulgarian Split Squat (Dumbbell)"),
    ("A1B2C3D4", "Bulgarian Split Squat (Barbell)"),
    ("E5F6A7B8", "Split Squat (Dumbbell)"),
    ("B8127AD1", "Lying Leg Curl (Machine)"),
    ("B8127AD2", "Seated Leg Curl (Machine)"),
    ("75A4F6C4", "Leg Extension (Machine)"),
    ("937292AB", "Single Leg Romanian Deadlift (Dumbbell)"),
    ("C7973E0E", "Leg Press (Machine)"),
    ("B923B230", "Deadlift (Trap bar)"),
    ("68CE0B9B", "Hip Thrust (Machine)"),
]


def _seed(db, is_custom=False, owner=None):
    for tid, title in CATALOGUE:
        db.add(models.HevyExerciseTemplate(
            id=tid, title=title, type="weight_reps",
            is_custom=is_custom, owner_user_id=owner,
        ))
    db.commit()


def _titles(cands):
    return [t for _, t in cands]


# --------------------------------------------------------------------------- #
# Tokenisation                                                                 #
# --------------------------------------------------------------------------- #

def test_tokens_strips_punctuation_and_cases():
    assert _tokens("Leg Curl (Machine)") == frozenset({"leg", "curl", "machine"})
    assert _tokens("") == frozenset()


# --------------------------------------------------------------------------- #
# The anti-auto-resolve evidence (#83)                                         #
# --------------------------------------------------------------------------- #

def test_leg_curl_has_at_least_two_candidates(db_session):
    """THE reason a unique candidate is never auto-resolved. `Leg Curl (Machine)`
    looked unique in the 10-row probe fixture; against the real catalogue it is
    ambiguous between Lying and Seated. Uniqueness is an artifact of catalogue
    size, so a rule firing on it would resolve wrong as the catalogue grew."""
    _seed(db_session)
    cands = suggest_candidates(db_session, "Leg Curl (Machine)", USER)
    titles = _titles(cands)

    assert len(titles) >= 2
    assert "Lying Leg Curl (Machine)" in titles
    assert "Seated Leg Curl (Machine)" in titles
    # And it still does not resolve — suggestion never becomes resolution.
    assert resolve_exercise(db_session, "Leg Curl (Machine)", USER) is None


def test_suggest_never_resolves(db_session):
    """suggest_candidates returns candidates; it must not mutate or resolve."""
    _seed(db_session)
    for probe_title in ("Bulgarian Split Squat", "Leg Curl (Machine)",
                        "Single Leg Romanian Deadlift"):
        assert resolve_exercise(db_session, probe_title, USER) is None
        assert suggest_candidates(db_session, probe_title, USER)
    assert not db_session.new and not db_session.dirty and not db_session.deleted


# --------------------------------------------------------------------------- #
# The three live probe misses (2026-07-14) — all containment                   #
# --------------------------------------------------------------------------- #

def test_bulgarian_split_squat_offers_all_three_real_candidates(db_session):
    _seed(db_session)
    titles = _titles(suggest_candidates(db_session, "Bulgarian Split Squat", USER))

    # Both containment hits rank ahead of the non-containment near-miss.
    assert titles[:2] == ["Bulgarian Split Squat (Barbell)",
                          "Bulgarian Split Squat (Dumbbell)"]
    assert "Split Squat (Dumbbell)" in titles


def test_single_leg_rdl_offers_the_dumbbell_variant(db_session):
    _seed(db_session)
    titles = _titles(suggest_candidates(db_session, "Single Leg Romanian Deadlift", USER))
    assert titles[0] == "Single Leg Romanian Deadlift (Dumbbell)"


def test_resolving_title_is_not_a_miss(db_session):
    """`Leg Extension (Machine)` resolved live — sanity that the probe's one hit
    is still an exact hit, so candidates are never consulted for it."""
    _seed(db_session)
    assert resolve_exercise(db_session, "Leg Extension (Machine)", USER) == "75A4F6C4"


# --------------------------------------------------------------------------- #
# Noise control + scope                                                        #
# --------------------------------------------------------------------------- #

def test_nonsense_title_returns_no_candidates(db_session):
    """A suggestion list nobody can act on is noise. Probe 2's movement.

    Scoped claim: against THIS slice. Its best ratio is 0.341 (vs `Leg Press
    (Machine)`), under the 0.5 floor. Against prod's 494 rows a real Zercher
    movement could clear it — which would be a useful suggestion, not a failure
    of this rule.
    """
    _seed(db_session)
    assert suggest_candidates(db_session, "Zercher Moonwalk Press", USER) == []


def test_empty_title_returns_no_candidates(db_session):
    _seed(db_session)
    assert suggest_candidates(db_session, "", USER) == []


def test_limit_is_honoured(db_session):
    _seed(db_session)
    assert len(suggest_candidates(db_session, "Leg", USER, limit=2)) <= 2


def test_scope_matches_the_resolver_never_another_users_custom(db_session):
    """Scope parity (#83): a candidate the resolver could never return would be
    the instrument disagreeing with the behaviour it serves."""
    _seed(db_session, is_custom=True, owner=OTHER_USER)
    assert suggest_candidates(db_session, "Bulgarian Split Squat", USER) == []
    assert resolve_exercise(db_session, "Bulgarian Split Squat (Dumbbell)", USER) is None
    # The owner still sees them.
    assert suggest_candidates(db_session, "Bulgarian Split Squat", OTHER_USER)


def test_deterministic_across_calls(db_session):
    _seed(db_session)
    a = suggest_candidates(db_session, "Bulgarian Split Squat", USER)
    b = suggest_candidates(db_session, "Bulgarian Split Squat", USER)
    assert a == b
