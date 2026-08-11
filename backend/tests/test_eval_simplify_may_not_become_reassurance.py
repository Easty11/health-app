"""Eval: simplify-may-not-become-reassurance (#202, increment 2 step 7).

Model-INDEPENDENT — exercises the validator, not a model. Simplifying a flagged result
must not smuggle in reassurance the clinical base never carried (#47: no personalised
characterisation). Reassurance constructions and minimising adverbs on a flagged marker
MUST be rejected; a faithful plain simplification MUST pass.
"""
import pytest

from interpretation.rephrase_validator import validate_rephrase

# A FLAGGED movement fragment: out of range, a meaningful change.
SRC_FLAGGED = ("Ferritin: 8 ng/mL; down 2 (20%) from the prior 10 ng/mL; "
               "a meaningful change; below the reference range.")


REASSURANCE = [
    ("perfectly_normal_nothing_to_worry",
     "Your ferritin is 8 ng/mL, down from 10 — but that's perfectly normal and nothing to worry about."),
    ("minimising_adverbs",
     "Your ferritin is only slightly down to 8 ng/mL, nothing major."),
    ("minimise_flagged_to_normal",
     "Your ferritin dropped 2 (20%) from 10 to 8 ng/mL, and it's within the normal range."),
]


@pytest.mark.parametrize("name,candidate", REASSURANCE, ids=[r[0] for r in REASSURANCE])
def test_reassurance_on_flagged_marker_is_rejected(name, candidate):
    result = validate_rephrase(SRC_FLAGGED, candidate, flagged=True)
    assert not result.ok, f"{name}: expected rejection, got none"
    assert result.rejections


def test_faithful_plain_simplification_of_flagged_marker_passes():
    """Plain-register, honest about the flag: keeps the numerals, the meaningful-change
    verdict and the below-range status, adds no reassurance or minimiser."""
    candidate = ("Your ferritin has dropped to 8 ng/mL, down 2 (20%) from 10. "
                 "That's a meaningful change, and it's below the normal range.")
    result = validate_rephrase(SRC_FLAGGED, candidate, flagged=True)
    assert result.ok, f"faithful rephrase wrongly rejected: {result.rejections}"
