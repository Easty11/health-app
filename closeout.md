# Close-out — the phase-change save validates the whole write before it creates a Hevy folder, and step 4's slot names are pickers (#375); the several-metabolic-slots question is filed (Q210)

## Real commits this session

Range: `7bfdb0a` (master when the session opened) to this close-out. Two concern-named branches. The session opened on master with the fresh-clone settings already set (`core.hooksPath` and the local `land` alias verified); maxima at open: decisions 374, questions 209.

On `fix/phase-form-save-order` (PR #311, self-merged on green: guard, vitest and pytest passed on `5422bcb`; the branch auto-deleted):
- `5422bcb fix(phase-form): validate the whole save before creating a Hevy folder; slot keys become pickers`. Merge commit `c6bae6c`. Backend: `routers/training_phase.py`, `engine/training_phase.py`, `tests/test_phase_transition_order.py` (new). Frontend: `PhaseTransitionFlow.jsx`, `phaseTransitionLib.js` and their two test files.

On `gov/phase-form-save-order` (governance only, no code, no schema):
- One `gov(phase-form-save-order): ...` commit: DECISIONS #375; new Q210; one ROADMAP NOW row; the BRANCHES rows, including the correction to the `claude/peaceful-lamport-aqc7xi` row flagged at the last close-out; the CLAUDE.md pointer; this file. Its hash is on the branch; a file cannot name its own commit. It is the only gov commit of the session and self-merges on green under § Merge disposition.

- Migration: none. No prod data write; Code has no database access this session. The deploy facts below were read by Code from Railway.
- Deploys (Railway, read by Code): backend `3c2123ad` and frontend `d71a7781`, both for `c6bae6c`, both SUCCESS on 4 Oct.
- **Not run:** the served-bundle probe (#121). The session's egress proxy denied the frontend host (organization policy), and it was not worked around. The PowerShell line is in the ROADMAP row.
- Verification run by Code: 12 new backend tests that observe ORDER (one log of Hevy calls and commits), 8 mutations each failing a test; 11 new frontend tests, 10 mutations each failing a test (an 11th survived, was unreachable, and the code was removed). Backend suite 2,800 passed, 1 skipped, 1 failed: `test_context_builder_output_unchanged_pre_post_refactor`, the shallow-clone `git show 3360ed5` artifact, green on CI. Frontend 342 passed. eslint reports 6 errors, all in files this work does not touch and identical on master.

## Pending-queue reconciliation

The operator's 4 Oct bug note carried these items. Each landed, or is named as not landed.

1. **Verify the actual save ordering on master before fixing** — done. The hypothesis held, and it was a designed order: #317 recorded "the Hevy folder create ... runs FIRST" as an operator ruling. Hence #375, which supersedes that bullet.
2. **External side effects only after full validation, or compensated** — landed in `5422bcb`: a validate-only pass of the whole transaction before the Hevy call. Compensation was not available: the connector has no folder delete (Likely none in Hevy's API either; Hevy's docs were not read), so validate-first was the only option.
3. **Secondary: the capacity slot name is free text in the UI but enum-validated on save** — landed: a picker fed by the backend's own vocabulary, a key reset on kind change (a stale key was another route in), and step 4 now checks and names the refusals (enum, duplicate, device sport) and blocks Next.
4. **`load_window` slot name is enum-validated, free text in the UI** — landed with item 3 (a picker of `metabolic`).
5. **Open design question: are several metabolic slots with disjoint sport filters a supported shape?** — filed as Q210 with verified facts, not decided. Verified: refused today by the per-sub-cycle duplicate rule; slot identity is `(kind, key)`; the resolver's claim order already assumes several; the `activity` slot is the existing way to count a sport separately. Options (a), (b), (c) are on the question.
6. **The two orphan 'Aerobic Base Phase' folders already in Hevy** — NOT cleaned. The API cannot delete a folder. Owed to the operator: remove the duplicates in the Hevy app; on the retry, pick an existing one at step 7.
- **Not landed:** a live save (owed, after deploy), the #121 bundle probe (above), reuse of a same-named folder (not built and not ruled), and the operator's earlier owed items (below).
- **One flag.** The retry will still create another folder if "new folder" is chosen again with the same name; #375 records that as not changed.

Provisional until merged: everything in the gov commit (the gov PR). The code is landed and deployed.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One new row: **Phase-change form: save order and slot pickers** (OWED, operator). The Garmin self-evaluation row (the stored-rows read) is unchanged and still owed. No other row changed.

**State.** PR #311 is merged and deployed. The gov PR self-merges on green; #375 was resolved at master max #374 and Q210 at max Q209, re-read before the merge.

**Single clearest next action.** The operator runs the served-bundle probe (the PowerShell line in the ROADMAP row, expect `True`), then retries the Aerobic Base Phase save: pick an EXISTING 'Aerobic Base Phase' folder at step 7, the capacity picker at step 4, one metabolic slot only, and activity slots for the other sports until Q210 is ruled. Then remove the duplicate folders in the Hevy app.

**Operator actions owed.** (1) The above. (2) Still open from earlier close-outs: the read of `garmin_activity_selfevals` (the Garmin self-evaluation row); the capture-rate query (Q202); the overlapping-sync live proof for #371; which build the phone runs; periodic manual 30-day syncs until P1 (#370) lands; the Polar backfill report, `--apply` and `refresh_load`; Q205 at the next Polar re-auth.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 116 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This session: new Q210; none closed or moved.

**What was NOT touched (named so absence does not read as finished).**
- **Several metabolic slots (Q210).** Filed, not decided. Whatever the ruling, it touches the validator, the resolver, `satisfies`, `consistency_rows`, the form and the coach write-shape docs, so it is a brief, not a tweak.
- **Folder handling beyond ordering.** No reuse of a same-named folder, no routine creation changes, and nothing about routines being un-movable between folders (the form's step-7 note).
- **The sRPE floor, the Garmin in-activity HR read (Q159), the phone code and P1 (#370), the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206).** Unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move; the phase form is the plan's input surface, not its judgement.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** after four sessions on load and ingest plumbing, this one went to the plan's input form. It was a real-use bug fix rather than new capability, so Walk in and the plan-versus-log judgement are still where they were. The form's first real use (5 Oct check-in) is the best test of the Know lane, and it is blocked on the operator's retry.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form: save order and slot pickers (#375, OWED, new): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED, the stored-rows read): **Know** and **Loop**.
- HC sync reliability (#369-#371, Q159, Q202, Q208, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
