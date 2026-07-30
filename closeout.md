# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-07-30 (second session that day; the prior close-out is `bb29c0a`).

## 1. Real commits this session

Session-open ref: `bb29c0a` (prior `chore: session close-out`). Eight commits, all on master
and pushed. `git log --oneline bb29c0a..HEAD`:

```
d8af288 governance: #153 demotion predicate (feedback + satisfied + complete) + Q65 asset-vocabulary gap
45d36fb feat(interpretation): §4 — an in-phase relation may demote gate 1's delta arm
4ceb48f test(interpretation): seed a haematocrit band crossing — first band_change through build_foundation
4157784 governance(open-questions): Q64 — do marker-authored member fields belong on ungrouped rows?
33001a1 feat(interpretation): emit member mechanism — every member field in the contract is now emitted
182ce19 governance: #152 — axis_verdict reduced to {protocol_phase, text}; confidence removed
bd08ac9 content(interpretation): author mechanism for all 15 group members + coverage guard
3dc425b governance: #151 — complete the producer before wiring the view (not absence-tolerant)
```

Immutable dated log (`git log --format="%ad %s" --date=short`):

```
2026-07-30 governance: #153 demotion predicate (feedback + satisfied + complete) + Q65 asset-vocabulary gap
2026-07-30 feat(interpretation): §4 — an in-phase relation may demote gate 1's delta arm
2026-07-30 test(interpretation): seed a haematocrit band crossing — first band_change through build_foundation
2026-07-30 governance(open-questions): Q64 — do marker-authored member fields belong on ungrouped rows?
2026-07-30 feat(interpretation): emit member mechanism — every member field in the contract is now emitted
2026-07-30 governance: #152 — axis_verdict reduced to {protocol_phase, text}; confidence removed
2026-07-30 content(interpretation): author mechanism for all 15 group members + coverage guard
2026-07-30 governance: #151 — complete the producer before wiring the view (not absence-tolerant)
2026-07-30 chore: session close-out
2026-07-30 governance: mint #150 navigation model (hub-as-home, persistent chat) + Q63 (interp tile)
```

Files touched (`bb29c0a..HEAD`): `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`,
`backend/interpretation/gates.py`, `backend/interpretation/producer.py`,
`backend/reference/lever_dictionary.json`,
`backend/tests/test_interpretation_producer_foundation.py`,
`backend/tests/test_lever_dictionary_mechanism.py` (new),
`backend/tests/test_relation_demotion.py` (new) — plus `ROADMAP.md`, `CLAUDE.md` and this file
from the close-out ritual.

### What each commit did

- **3dc425b — #151.** Records the sequencing choice: complete the producer before regenerating
  the fixture or wiring the view; the view's unconditional reads are accepted as correct rather
  than defended against with absence-tolerance. Carries the two sizing reads that motivated it —
  `axis_verdict` is FOUR fields with no vocabulary anywhere in the repo (and a `protocol_phase`
  whose fixture values intersect `derive_phase`'s real return set at ZERO, including
  test-forbidden `on_trt`); `mechanism` is three fields over 15 authorable markers, no marker is
  in two groups, and I1 does not bind the prose (#95 covers gate-influencing constants only).
- **bd08ac9 — mechanism content.** `marker_interpretation[*].mechanism` authored for all 15
  possible group members (8 entries extended, 7 created). `confidence` deliberately NOT authored.
  `#98` guard honoured: surgical text insertion, escapes via `chr(92)`, asserted pure-ASCII /
  zero literal em dashes / parses / only `mechanism` keys added. New guard
  `test_lever_dictionary_mechanism.py` (9 tests) with a synthetic violation per rule — including
  one that catches the fixture's invented `training_load` factor key.
- **182ce19 — #152.** `axis_verdict` reduced to `{protocol_phase, text}`; `confidence` removed
  from both `axis_verdict` and `mechanism`. Draft's `Amends:` premise corrected against master —
  NO entry had ever established the four-field shape, so this is the FIRST master-canonical
  statement of it and supersedes fixture/contract-file residue. Records the open gap the draft
  glossed: `protocol_context_snapshot.factors` is a LIST while `protocol_phase` is a scalar.
- **33001a1 — mechanism emitted.** The real state change: `_HELD_MEMBER_FIELDS` no longer holds
  a genuine hold (what remains are the group-field boundary checks), so EVERY member field in the
  contract is emitted and group-level `axis_verdict` is the sole producer hold.
- **4157784 — Q64.** Marker-authored member fields (`stable_rationale`, `mechanism`) could
  project onto `ungrouped[]` but do not; `vitamin_d_25oh` is seeded, ungrouped, and renders with
  no explanation. Recorded, not decided — belongs with 1b, which must build that section anyway.
- **4ceb48f — haematocrit seed.** First `band_change` propagated through `build_foundation`
  (previously only ever driven at gate-unit level with an injected asset). Escalates
  `watch`→`elevated` with gate 2 AND the delta arm asserted quiet, so `is_news` can only come
  from the safety arm. Commit message states explicitly it is NOT demotion's control.
- **45d36fb — §4 demotion.** In-phase relation demotes gate 1's delta arm. Producer re-computes
  gate 1 in pass 2 once relations exist (the reason #140 moved surfacing out of pass 1).
- **d8af288 — #153 + Q65.** The predicate as a named decision, plus the asset-vocabulary gap
  with both candidate futures stated.

## 2. Pending-commit-queue reconciliation

No chat `;cc` queue was carried in; work arrived as four briefs (the `axis_verdict`/`mechanism`
sizing brief, the mechanism CONTENT brief, the shape-amendment DECISION brief, and the demotion
brief with three amendments). Everything decided landed; nothing is provisional.

- Sizing reads → **3dc425b** (recorded inside #151, since they postdate the brief that ordered
  the work).
- Mechanism content + slot → **bd08ac9**; producer projection → **33001a1**.
- Shape amendment → **182ce19** (#152), with the `Amends:` line corrected against master.
- Demotion, all three amendments applied → **4ceb48f / 45d36fb / d8af288**: (A) emptiness
  tripwire added, (B) clause 1 re-justified on the `into_range` transition after verifying
  `crossed_ref` is bidirectional, (C) Q65 carries both candidate resolutions.
- **Deliberately NOT built:** `axis_verdict` (two named blockers), the `verdict`-enum
  derivability read (deferred by the CORRECTION), fixture regeneration, view, endpoint.

## 3. Cold-resume handoff

### State
- Branch `master`, clean, synced with `origin/master` (0/0). No other local or remote branch —
  every branch this session was ff-merged and deleted. `BRANCHES.md` unchanged (nothing to row).
- Suite **506 passed** (was 476 at session open; +9 mechanism asset guard, +1 mechanism emission,
  +1 band-crossing, +24 gate-level demotion, +4 end-to-end demotion, minus none).
- DECISIONS max **#153**; OPEN_QUESTIONS max **Q65**.

### Interpretation layer — 4b-ii is one item from producer-complete
**Emitted:** all member fields — `relations_rendered` (4b-i), `stable_rationale`,
`member_lever_effects`, `mechanism` — plus group `shared_levers`, plus **relation-based demotion
of gate 1's delta arm** (#153).

**The one remaining producer item is `axis_verdict`**, reduced by #152 to `{protocol_phase, text}`,
blocked on exactly two things:
1. **A source-factor rule.** `meta.protocol_context_snapshot.factors` is a LIST (one per declared
   factor); `protocol_phase` is a scalar. With `trt` + `tirzepatide` + `cbt_i` all real ledger
   keys the projection is ambiguous. Relation preconditions' named `factor_key` (#141/#145) is the
   likely mechanism — not decided.
2. **The authoring table**, keyed on **evaluability, not truth** (9 of 10 relations carry no
   machine-readable condition, so "did the relation hold" is not computable): which relations
   rendered, `operand_status` per relation, and `precondition_status` for
   `hpg_gonadotropin_suppression` alone. Chat is drafting the table and the coarse-keying decision
   (~10 authored strings). Q62 has no current consumer — `text` is authored, not generated.

**Then 1b (delivery), per #151 after the producer:** regenerate the fixture from the producer
(fixes missing `ungrouped[]` and the `protocol_context_snapshot` shape by construction) → correct
the view (consume `should_surface` instead of recomputing gate 1∨2; add the Ungrouped section; fix
the `protocol_context_snapshot` reader; drop the `.verdict` / `.confidence` reads at
`GroupCard.jsx` 15/17 and `GroupCollapsed.jsx` 10/12) → endpoint (draw-triggered, #147) → wire.

**Known and accepted:** demotion is **inert on the canonical panel** — `_seed_fixture` omits `lh`,
so `hpg_gonadotropin_suppression` is permanently `degraded` there. The regenerated fixture will
therefore ship with the demotion path unexercised in the view. Deliberate: adding `lh` to that
seed would break the `fsh` oracle tests. The `lh` absence is now **load-bearing**, and
`test_news_gate_shape_and_no_unearned_demotion_on_the_s2_panel` pins the reason so it fails loudly
if someone adds `lh` casually.

**Also open on this lane:** the I8-under-pressure test is gate-level, not end-to-end, because
banded markers ∩ feedback-rendered markers = ∅ (`haematocrit` vs `lh`/`fsh`). That is
**contingent**, and `test_banded_and_feedback_markers_do_not_yet_intersect` is the tripwire that
fires when it closes, instructing its own deletion.

### Sprint (ROADMAP NOW)
Two dated CBT-I items: **Q45 nap day-attribution** (contaminating capture now — the engine reads
`naps_min` from `date − 1` on an unverified attribution) and the **~31 Jul manual evaluation
trigger** (#118's PM-offer half). Cross-repo shared-block propagation to `health-connect-app`
remains **OWED** and needs an HCA-rooted session. Banister build still owed (readiness suppression
lifted `95355fa`).

### Open questions (by status)
- **Blocked by 4b-ii:** Q63 (interpretation-tile content), Q60 (CBT-I user surface — gating fork
  is #47 verdict-as-directive).
- **Design/policy, not blocking:** Q65 (no `demotes_when` on four relation kinds — also gates the
  `axis_verdict` table's keying, so resolving it on demotion's merits alone would invalidate the
  verdict content), Q64 (marker-authored fields on ungrouped rows — resolve with 1b), Q62 (#47 for
  a generated field — no current consumer), Q61 (labs projection `computed_flag`/`confidence`).
- **Infra:** Q59 (nothing verifies the deployable artifact — no CI, no boot check).
- **Live sprint blocker:** Q45 (nap day-attribution), on the CBT-I lane.

### Single clearest next action
Mint the **`axis_verdict` authoring table + coarse-keying decision** (chat is drafting it) and
decide the **source-factor rule** for `protocol_phase`. Those two close the producer; only then
does 1b start, per #151. Nothing else on this lane is startable ahead of them.
