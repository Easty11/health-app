# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

## 1. Real commits this session

Session-open ref: `31997d7` (prior session's `#NEXT -> #140/#141/#142` merge governance).
`git log --oneline 31997d7..HEAD`:

```
cd35786 asset: record precondition-authoring prerequisite on trt_erythrocytosis_watch
524cc60 governance(Q56/Q57): record precondition-shape + lever-join resolution across the stores
0404c64 feat(interpretation): resolve feedback preconditions; expected_by_phase with no authority (Q56)
778a3c1 asset(Q56): precondition shape on hpg_gonadotropin_suppression (factor_key + admissible_phases)
fce128a asset(Q57): add declared_factor_keys join to lever nodes
eb024b5 governance: resolve carried #NEXT docstring token -> #140 in producer.py
```

Date-stamped (`git log --format="%ad %s" --date=short`, immutable):

```
2026-07-28 asset: record precondition-authoring prerequisite on trt_erythrocytosis_watch
2026-07-28 governance(Q56/Q57): record precondition-shape + lever-join resolution across the stores
2026-07-28 feat(interpretation): resolve feedback preconditions; expected_by_phase with no authority (Q56)
2026-07-28 asset(Q56): precondition shape on hpg_gonadotropin_suppression (factor_key + admissible_phases)
2026-07-28 asset(Q57): add declared_factor_keys join to lever nodes
2026-07-28 governance: resolve carried #NEXT docstring token -> #140 in producer.py
```

All six are on `feat/relation-preconditions`, pushed to origin (0 ahead / 0 behind), all `+`
under `git cherry origin/master` (real work, unmerged). A seventh `chore: session close-out`
commit carries this file + the CLAUDE.md Recent-landings update.

The branch resolves **Q56** and **Q57** for the relation-preconditions increment: lever->declared-factor
join (`declared_factor_keys`), the precondition object shape (`factor_key` + `admissible_phases`,
authored by Luke, replacing `on_trt`), producer resolution (`precondition_status` satisfied /
not_satisfied / unresolvable) and `expected_by_phase` emitted **with no authority**. Plus Step 0
(carried `#NEXT` docstring -> `#140`) and a promotion-note on the `_deferred` `trt_erythrocytosis_watch`.

Backend suite **457 passed** (baseline 453 per the prior branch, **+4**). Gates G1-G10 all reported
green in session (Q57 output-neutral; admissible_phases a real derive_phase subset; resolution
draw-dated + `current_state` queried once; three resolution arms with pos/neg controls; should_surface
+ news_gate byte-identical across the producer change; `on_trt` gone from producer source + live asset;
held-4b-ii fields still absent; Q56/Q57 both `DONE`).

## 2. Pending-commit queue reconciliation

**No `;cc` pending-commit queue was carried into this session.** The session was driven by the
chat-authored relation-preconditions brief (a proposal, not a pending-queue paste), so there are no
`PENDING` items to reconcile. The brief WAS the payload; every step (0, A-E, governance) plus the
reviewer-surfaced promotion-note landed in the six commits above. Nothing decided this session remains
uncommitted **on the branch** — but the whole branch is provisional against master until it ff-merges:
DECISIONS `#NEXT`x3 are unminted and Q56/Q57 read `DONE -> #NEXT`.

## 3. Cold-resume handoff

**Where things stand.** The relation-preconditions increment is complete, tested, pushed, and **held
for review** on `feat/relation-preconditions` — not merged. Feedback-relation preconditions now resolve
(`factor_key` "trt" + `admissible_phases` ["steady"] on `hpg_gonadotropin_suppression`, authored by
Luke), the producer emits `precondition_status` + `expected_by_phase` (no authority, demotion still
held), lever nodes carry `declared_factor_keys`, and the dead `on_trt` vocabulary is gone from the live
producer surface.

**Single clearest next action:** review `feat/relation-preconditions`; on acceptance, ff-merge to master
(`git checkout master; git merge --ff-only feat/relation-preconditions; git push origin master;
git branch -d feat/relation-preconditions; git push origin --delete feat/relation-preconditions`). At
that merge: resolve the three `### #NEXT` DECISIONS headings to **#143/#144/#145** (file order), resolve
Q56/Q57 `DONE -> #NEXT` to those numbers, and flip the BRANCHES row OWED -> DONE(SHA). BRANCHES.md
carries the row with the full merge checklist.

**Open questions by status (this session's changes):**
- **DONE this session:** Q56 (precondition vocabulary — resolved by the precondition-object shape) and
  Q57 (lever->declared-factor join — resolved by `declared_factor_keys`). Both `DONE -> #NEXT`; numbers
  resolve at merge.

**4b-ii's blocker — ingestion is now the ONLY one.** The two asset-content blockers (phase-vocabulary
mismatch, lever join) are discharged. The lab store is still empty (`lab_reports` / `lab_results` zero
rows, unverified-from-session); the ~30 May TRT panel is the natural first input. Relation-based
**demotion** remains 4b-ii's own work (its own brief), not a blocker on it.

**Known follow-on, recorded not lost:** `_deferred.relations.trt_erythrocytosis_watch` still carries the
legacy `precondition_phase: "on_trt"` and is `ready_to_promote`. A `promotion_note` on the entry (commit
`cd35786`) records that promoting it requires converting to the precondition-object shape and authoring
its clinical content (Luke) first — else it emits `unresolvable` on arrival. Chat-only finding, now
durable on the asset where the promoter will look.

**Convention set this session:** gate-label namespacing in the interpretation test file is now
`<increment>-G<n>` (`4a-G*`, `4b-i-G*`, `4b-ii-G*`), resolving the two-G5 / two-G6 collision.

**Loop discipline:** single-repo (health-app only) throughout; no `frontend/`, no `health-connect-app`,
no shared-CLAUDE.md-block edits. `INTERPRETATION_OUTPUT_CONTRACT.md` (UI-maintained) not written;
`precondition_status` / `expected_by_phase` semantics changed here — report the divergence from v0.5
rather than reconciling the contract file.
