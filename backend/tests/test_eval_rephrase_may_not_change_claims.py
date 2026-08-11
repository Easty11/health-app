"""Eval: rephrase-may-not-change-claims (#202, increment 2 step 7).

Model-INDEPENDENT — it exercises the mechanical validator, not a model, so CI never
needs a live key. Each adversarial candidate is a rephrase that changes a claim and MUST
be rejected; a faithful plain-register simplification of the same source MUST pass.

The source strings are shaped like `presentation.py` movement fragments — the exact text
the generator is handed and the validator scores against.
"""
import pytest

from interpretation.rephrase_validator import validate_rephrase

# A normal, in-range, no-news movement fragment.
SRC = ("Testosterone (total): 23.9 nmol/L; unchanged from the prior 22.4 nmol/L; "
       "within the meaningful-change threshold; in range.")

# A censored movement fragment (fsh-shaped).
SRC_CENSORED = "FSH: <0.1 IU/L; no change in the censored bound; below the reference range."

# The domain vocabulary the producer knows — distinctive marker/lever name words. In
# production the endpoint builds this from the asset marker names; here a representative set.
KNOWN = {"testosterone", "cortisol", "ferritin", "fsh", "oestradiol", "shbg", "haematocrit"}


ADVERSARIAL = [
    # (name, source, candidate, kwargs)
    ("added_numeral", SRC,
     "Your total testosterone is 23.9 nmol/L, and about 38% of it is bound to proteins.", {}),
    ("dropped_negation_status_flip", SRC,
     "Your total testosterone is 23.9 nmol/L and is now out of range.", {}),
    ("unit_swap", SRC,
     "Your total testosterone is 23.9 mg/dL, about the same as before.", {}),
    ("censored_to_magnitude", SRC_CENSORED,
     "Your FSH increased by 50% since last time.", {"censored": True}),
    ("entity_substitution", SRC,
     "Cortisol is 23.9 nmol/L, unchanged from the prior 22.4 nmol/L; in range.", {}),
]


@pytest.mark.parametrize("name,source,candidate,kw", ADVERSARIAL, ids=[a[0] for a in ADVERSARIAL])
def test_claim_changing_rephrase_is_rejected(name, source, candidate, kw):
    result = validate_rephrase(source, candidate, known_entities=KNOWN, **kw)
    assert not result.ok, f"{name}: expected rejection, got none"
    assert result.rejections


def test_faithful_simplification_passes():
    """A genuinely faithful plain-register rephrase keeps every numeral, unit and status
    and introduces no new entity, directive, priority or reassurance term."""
    candidate = ("Your total testosterone is 23.9 nmol/L. That's about the same as last "
                 "time (22.4), a change too small to be meaningful, and it sits within the "
                 "normal range.")
    result = validate_rephrase(SRC, candidate, known_entities=KNOWN)
    assert result.ok, f"faithful rephrase wrongly rejected: {result.rejections}"


def test_faithful_censored_simplification_passes():
    """A faithful rephrase of a censored fragment keeps it magnitude-free."""
    candidate = ("Your FSH reads below 0.1 IU/L. Because it's a below-detection value, "
                 "we can't measure how much it changed, and it's below the reference range.")
    result = validate_rephrase(SRC_CENSORED, candidate, censored=True, known_entities=KNOWN)
    assert result.ok, f"faithful censored rephrase wrongly rejected: {result.rejections}"
