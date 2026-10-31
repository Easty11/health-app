# 0001 — Canonical exercise layer
**State:** ideation
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#537. Folded questions: Q22. The triage placed this as architecture-scale, ideation (trigger: a second exercise source).

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q22 | Promote exercise-region tags to a source-agnostic canonical exercise layer | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q22 — Promote exercise-region tags to a source-agnostic canonical exercise layer</summary>

````
## Q22. Promote exercise-region tags to a source-agnostic canonical exercise layer

Tags are currently keyed on the **Hevy** template id (`exercise_region_tags.hevy_exercise_template_id`),
in tension with the device-agnostic-from-day-one principle. The labs module already solved the analogous
problem (`marker_canonical`). Deferred deliberately for the tagging brief — 493 rows are cheap to re-key,
and movement-identity-across-sources is a real design exercise that should not be rushed inside a tagging
task.

**State:** OPEN — deliberately deferred, not abandoned (#74). **Not BLOCKED**: 493 rows are cheap to
re-key, so nothing prevents it. Revisit when a second exercise source appears or the canonical-exercise
layer is designed.
````

</details>
