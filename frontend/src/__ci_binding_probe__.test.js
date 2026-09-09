// THROWAWAY — CI test-lane binding probe (#273 OWED verification). NOT a real test.
// Deliberately fails so `frontend tests (vitest)` reports RED. If this context is a
// REQUIRED check on ruleset master-pr-gated, the PR's mergeable_state becomes "blocked";
// if it is merely reported-not-required, it becomes "unstable" (still mergeable).
// This PR is never merged — it is closed unmerged once the state is read.
import { test, expect } from 'vitest'
test('INTENTIONAL FAILURE — proves the vitest context gates the merge', () => {
  expect(true).toBe(false)
})
