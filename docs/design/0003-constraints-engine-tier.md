# 0003 — Constraints engine tier
**State:** committed
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-11-02

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#539. Folded questions: Q102, Q182, Q183. The triage placed this as architecture-scale, discussion.

## Proposal

Every engine block is a row. `is_contraindicated` had four arms; three (radicular, RA-flare, acute-tissue) were hard-coded maps keyed on an injury row's `body_part` substring, with no exit, no `review_by`, no authority and no render, while the `## Constraints` section and the MCP snapshot listed every advisory row as "not engine-enforced". The fourth, the #342 engine-tier row, had lifecycle and visibility and zero rows for any user.

1. **The maps become proposals.** What each map encodes is seeded, per active injury, as engine-tier `block` constraint rows in `proposed` status, one row per (injury, region key), that the operator confirms or declines on the Injuries page. A proposal blocks nothing (#342); a confirmed row blocks exactly what it names and renders with its authority, exit and `review_by`. Declined means resolved with a basis, and a resolved default is never re-proposed for the same injury.
2. **Two seeding paths.** An operator-run script (`backend/scripts/seed_engine_defaults.py`, dry-run first, the `seed_constraints.py` pattern) and the injury write path, which proposes the same rows when an injury is created or re-typed (chat and api alike; `review_by` is the write day plus 28). Chat-created injuries therefore seed proposals, and the chat-channel rule (#342 R5) holds by construction.
3. **Which maps seed what.** Acute-tissue: by map key plus a declared alias list (`pes anserine` reaches the knee set). Radicular: an entry typed neural / radicular whose body part is spinal or empty, excluding cervical parts (the set is lumbar-shaped). RA-flare: the flag or the restriction token. The seeded set is a superset of what the live arms block, so retiring an arm cannot open a hole.
4. **The maps stay live until every proposal is resolved.** The first PR adds the seeding, the aliases, the review sweep and the tests, and leaves `is_contraindicated` byte-identical with zero confirmed engine rows. The second PR deletes the three arms, gated on an equivalence test over each user's active injuries and the operator's "pending = 0" read. The write path that changes what the engine enforces is exercised live, on proposals, before the code that depends on it lands (#166).
5. **The review sweep** (Q191, GH#529) is a read plus a page group, surfacing only: `GET /knowledge/review-due`, and a Keep action that re-dates in place through its own route.

## Alternatives considered

- **A restriction-vocabulary to region-key mapper (Q102's original ask).** Struck: a stem mapper is the substring defect at one remove, and #344 records that a limit on a region still being trained is advisory.
- **Seeding the defaults as confirmed rows with engine authority.** Rejected: it would change what the engine enforces at the moment of seeding, with nobody having confirmed it. A proposal changes nothing until the operator acts.
- **Retiring the maps in the same PR as the seeding.** Rejected: nothing would have exercised the proposal path before the code that depends on it.
- **Engine `cap` and `caution` rows.** Out of scope (Q183, GH#595): an engine cap needs a dose seam and an engine caution needs a graded `is_contraindicated`.

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q102 | Constraint rows: restriction vocabulary to region keys, `signal_type` refinement, and the `lunge_single_leg` over-block | Struck: engine scoping stays explicit region keys (operator-authored or proposed by the defaults); free-text restrictions stay advisory; no `signal_type` field, because once blocks are rows the type stops being load-bearing. The `lunge_single_leg` over-block is not live (both hamstring rows resolved in August) | Operator ruling 2 Nov 2026; the ledger as read 2 Nov 2026 | two-way | resolved → #488 |
| Q182 | Default constraint templates from `_ACUTE_TISSUE_BLOCKS` / `_RADICULAR_BLOCKS` (engine-tier defaults from the maps) | Seeded as proposals (the operator confirms or declines), per injury and region key, by the script and by the injury write path; the maps retire in a second PR behind an equivalence gate | `tests/test_engine_defaults.py`, `tests/test_seed_engine_defaults.py`, the pinned-SHA identity test unchanged | two-way | resolved → #486 (maps retired, second PR) |
| Q183 | Engine-tier `cap` and `caution` constraints (`cap`/`caution`) | Out of scope here: an engine `cap` needs the dose seam and an engine `caution` needs a graded `is_contraindicated`; both stay advisory-tier kinds | The dose seam landing (Q106, GH#489), or #72's boolean changing | two-way | struck (out of scope) → GH#595 |

## Decisions landed

- #486 — Engine blocks are rows: the in-code injury block maps seed per-injury engine-tier proposals; the maps retire once every proposal is confirmed or declined (first PR built the seeding; the second retired the maps, 2 Nov 2026).
- #487 — Engine-default proposals are a two-way door; the injury write path dates them four weeks out (ruling).
- #488 — The restriction-vocabulary mapper is struck; engine scoping stays explicit region keys (ruling; resolves Q102).
- #489 — The standing review sweep (GH#529) and Keep as an in-place re-date (ruling).

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
