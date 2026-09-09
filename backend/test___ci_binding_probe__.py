# THROWAWAY — CI test-lane binding probe (#273 OWED verification). NOT a real test.
# Deliberately fails so `backend tests (pytest)` reports RED (frontend + guard green).
# If pytest is a REQUIRED check, mergeable_state becomes "blocked"; if reported-not-
# required, "unstable". This PR is closed unmerged once read.
def test_ci_binding_probe():
    assert False, "INTENTIONAL FAILURE — proves the pytest context gates the merge"
