# 0003 — Constraints engine tier
**State:** discussion
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#539. Folded questions: Q102, Q182, Q183. The triage placed this as architecture-scale, discussion.

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q102 | Constraint rows: restriction vocabulary to region keys, `signal_type` refinement, and the `lunge_single_leg` over-block (vocabulary → region keys, `signal_type`, the `lunge_single_leg` over-block) | none yet | none recorded | unclassified | open |
| Q182 | Default constraint templates from `_ACUTE_TISSUE_BLOCKS` / `_RADICULAR_BLOCKS` (engine-tier defaults from the maps) | none yet | none recorded | unclassified | open |
| Q183 | Engine-tier `cap` and `caution` constraints (`cap`/`caution`) | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q102 — Constraint rows: restriction vocabulary to region keys, `signal_type` refinement, and the `lunge_single_leg` over-block</summary>

````
## Q102. Constraint rows: restriction vocabulary to region keys, `signal_type` refinement, and the `lunge_single_leg` over-block

**Re-scoped 2026-10-26 (operator-ruled, `DECISIONS_LOG` #459).** Discharged: `restrictions[]` strings became typed constraint rows with lifecycle, exit and authority (#342 S6), audited by #340. **Now asks:** the restriction-vocabulary → region-key mapping (engine-tier rows were never seeded); `signal_type` refinement and a per-entry override; and the live `lunge_single_leg` over-block (coordinate with Q182/Q183).
Original title: "`restrictions[]` is dead data — `is_contraindicated` cannot express the ledger's clinical language"

_The entry below is kept as minted, for provenance; where it differs from the paragraph above, the paragraph above governs._

`gather_active_injuries` normalises `restrictions` onto every injury row, and `is_contraindicated` reads it
for exactly one thing: the `"ra_flare" in restrictions` alias. Every other restriction string the ledger
carries is inert. Blocking is driven entirely by `signal_type` + set membership + a `body_part` substring
match, and that vocabulary cannot express what the entries actually say. Evidence, from the live ledger
(read-only Railway, 2026-08-16):

- **Entry 29 — the typing is load-bearing and deliberately wrong.** A documented neural sign is typed
  `mechanical` because typing it `neural` would block its own desensitisation lane: the loaded hinge is
  tolerated and *wanted*, and the aggravator is passive end-range tension. The vocabulary forces a choice
  between an honest `signal_type` and a workable plan, and the entry chose the plan. Any audit that trusts
  `signal_type` as clinical truth is reading a field that has been bent to route around the blocker.
- **Entries 18/29 — a live over-block, and no time limit.** `lunge_single_leg` is contraindicated
  bilaterally via `_ACUTE_TISSUE_BLOCKS["hamstring"]` against a region the user is actively training, and
  nothing expires it — despite the map's own docstring promising a "time-limited" exclusion.
- **Entry 30 — the substring match misses.** `"pes anserine"` does not contain `knee`, so it never reaches
  `_ACUTE_TISSUE_BLOCKS`; its restriction `"deep-flexion unilateral"` enforces nothing.
- **Entry 16 — plain dead text.** `"heavy gripping"` restricts nothing at all.

Design pass owed: a restriction-vocabulary → region-key mapping, plus either a `signal_type` refinement or
per-entry overrides, so an entry can say "neural, but this lane is the treatment" without lying about its
type.

**Explicitly NOT patched on `fix/contra-block-sets`:** the live `lunge_single_leg` over-block stays in
place. Removing it ad hoc trades a known over-block for an unknown under-protection, and it originates in
the very entry whose typing this question argues is unreliable — it belongs to the design pass, not to a
one-line set edit.

**State:** OPEN — no blocker; the audit that spawned it is closed. Owner: Luke. Cross-refs `Q23`
(→ #216), `#216`.
````

</details>

<details><summary>Q182 — Default constraint templates from `_ACUTE_TISSUE_BLOCKS` / `_RADICULAR_BLOCKS`</summary>

````
## Q182. Default constraint templates from `_ACUTE_TISSUE_BLOCKS` / `_RADICULAR_BLOCKS`

Raised with #342 (the brief kept both maps unchanged). `engine/selection.py` hard-codes body-part → region
blocks (the acute-tissue and radicular seed heuristics, spec §8). They have no exit, no review date and no
visible authority — the gap #342 closes for everything else. Convert them into default ENGINE-tier `block`
constraints seeded per injury at creation (`asserted_by: "engine"`, `with_parent` exit), so the coach and the
sweep see them as rows.

**To decide:** seeded as proposals (the operator confirms) or confirmed with engine authority; how existing
active injuries migrate; whether the in-code maps then retire; and the byte-identity gate against the current
arms (#342's pinned-SHA pattern).

**State:** OPEN. No blocker.
````

</details>

<details><summary>Q183 — Engine-tier `cap` and `caution` constraints</summary>

````
## Q183. Engine-tier `cap` and `caution` constraints

Raised with #342 (G2 ruling 2): the engine tier accepts `block` only in v1. `cap` means a load ceiling and the
engine has no dose seam to enforce one (Q106 / the Banister dosing wire), so an engine cap would silently become a
block. `caution` through the boolean `is_contraindicated` (#72: it stays boolean) is indistinguishable from a block.
Both remain advisory-tier kinds.

**To decide, when its trigger fires:** engine `cap` when the dose seam lands (what the cap bounds, and how it is
enforced); engine `caution` only if `is_contraindicated` becomes graded.

**State:** OPEN — watch; no action until the dose seam lands or #72's boolean changes.
````

</details>
