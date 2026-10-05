# Close-out — the phase-entry build (#389): Review / change phase is the only way a phase is entered, close-to-baseline stays as its own control, and the wizard and history handle same-day corrections

## Real commits this session

Session `phase-entry`, a fresh session on the operator's brief (5 Oct 2026), two PRs. Range: `3f46582` (master at open) to this close-out. Fresh-clone settings were both absent at open (`core.hooksPath` empty, no local `land` alias); both were set and read back (`.githooks`, `!gh pr merge --merge --delete-branch`). Maxima at open, by script: decisions #388, questions Q216.

PR 1, the pin (tests only), merged:
- `c1f6bc1` `test(phase): pin the zero-length exclusion in phase_at and the open-phase readers (#379 item 4)` - `backend/tests/test_phase_zero_length_pin.py` (9 tests) plus its own terminal BRANCHES row.
- `a47b502` `Merge pull request #333 from Easty11/claude/jolly-bardeen-vlksg1` - merged on green (guard, vitest, pytest); the remote branch was deleted at merge.

PR 2, the build, on the same branch name restarted from `a47b502` (the harness instruction and #387):
- `4b32221` `feat(phase): Review / change phase is the only phase-entry route; same-day corrections handled (#378, #379)` - code, tests, `SCHEMA.md` (one phrase).
- `f7860fc` `gov(phase-entry): #389 the phase-entry build settles #378 and #379 (R1-R6)` - DECISIONS (#389; the heading was resolved from `#NEXT` in the close-out commit), ROADMAP, BRANCHES, the CLAUDE.md Recent-landings pointer. One `gov(...)` commit, as #387 allows.
- The `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).

No migration, no schema change, no prod read or write by Code. PR 2 self-merges on green after this commit (non-schema; every ruling in it is the operator's, so no hold applies). **Provisional until merged: everything in PR 2.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The brief, item by item:

**Confirm (a)-(d) first (the brief's STOP condition): all four held, none false.**
- (a) The wizard has no close-to-baseline mode (`continue` / `move` only, always `POST /transition`); `ClosePhaseDialog` was the only baseline route. Confirmed.
- (b) Zero slots build `slots: []`, which `validate_microcycle` refuses ("must be a non-empty list"); there was no client-side block. Confirmed.
- (c) `PhaseForm` and the wizard both write `source='api'`, `asserted_by='user'`; no column says how a row was opened. Confirmed.
- (d) `POST /engine/phase` had one non-test caller (`PhaseForm.jsx:98`); engine `open_phase()` had no other production caller (the transition uses `_apply_open_phase`). Confirmed.

**PR 1, the pin: DONE (`c1f6bc1`, merge `a47b502`).** `phase_at` never returns a zero-length row (with a same-day successor, with none, and swept over a mixed ledger); `current_training_phase` never returns a closed row, including a zero-length one that sorts first. Other open-phase readers found and pinned (all go through `current_training_phase`): `GET /engine/phase`, the transition draft, `/engine/next`, the plan-of-record read, `resolve_window`, `current_state`; `mcp_server.py:728` uses the same call and is not exercised separately. Listed in the PR body. Mutation-checked: `<` to `<=` in `phase_at` fails only the no-successor test (a same-day successor sorts first and masks the bound; stated in the PR); dropping the `closed_on IS NULL` filter fails three.

**PR 2, the build:**
1. **R1, close to baseline stays: DONE (`4b32221`).** "End phase → baseline" is its own control on the Phase card, shown while a phase is open, posting to `/engine/phase/close` with a required reason. The Advanced disclosure and its open path are gone; baseline keeps "Open a phase" to the wizard. Tests: no Advanced or open path in either state; the control closes and refetches; no control at baseline.
2. **R2, the route, `PhaseForm.jsx` (+ test) and the engine `open_phase()` removed: DONE.** `_apply_open_phase` stays. **Divergence, named:** about 33 test call sites used `open_phase()` as a fixture. They now use `tests/phase_fixtures.open_phase`, a test-only wrapper over `_apply_open_phase`, so the production wrapper still goes; the three HTTP tests that posted to the route now use `/transition`. Test: the route answers 405 and the wrapper is absent.
3. **R3, at least one quota slot: DONE.** Step 4 blocks Next with exactly "A phase needs at least one quota slot." Tests: an open phase with its slot removed, and a baseline start. The existing G2 test (which removed the only slot) was changed to swap in an activity slot.
4. **R4, `zero_length` on the history route only; the card labels: DONE.** Computed `closed_on == entered_on`; `phase_to_dict` and the current read are unchanged. The card shows the row muted with a "same-day correction" chip and its close reason; nothing is hidden. Tests on both sides.
5. **R5, same-day skips the verdict: DONE.** Step 1 hides the verdict, relabels the note "What are you correcting? (optional)", an empty note omits `close_prior_reason`, the Then choice stays.
6. **R6, names the row the save closes: DONE.** Label, entered date, "opened today" when same-day, on step 1 and on the step-8 confirm (and "Opens a first phase" when nothing is open). No how-it-was-opened field.
7. **Same-day check, client `todayLocal()` against server `_local_day()`: pinned, with the gap reported.** The check compares the open row's `entered_on` with `todayLocal()`, which is the value the wizard sends as the new row's `entered_on`, so it answers exactly "would this save write a zero-length row". A vitest case with `TZ=Australia/Brisbane` at 14:30Z shows 00:30 on the next AEST date counting as today, and the UTC date not. **The gap:** the draft carries no server "today", so a browser outside the operator's zone near midnight would send an `entered_on` the server may refuse as future-dated. That is existing behaviour, unchanged, and recorded in #389.
8. **Tests and mutation checks: DONE.** Every ruling R1-R6 has at least one test that fails if reverted. Mutation-checked: R3 (block removed: 2 fail), R4 (flag forced false or inverted: 1 backend fails; chip removed: 1 frontend fails), R5 (never same-day: 3 fail). **Divergence, named:** the R5 payload rule (empty note omitted, no verdict prefix) is asserted but cannot fail independently of the hidden verdict control; the UI tests carry the R5 mutation.
9. **Governance: DONE (`f7860fc`).** One DECISIONS entry for R1-R6 (#389, `#NEXT` on the branch), ROADMAP NEXT block to DONE and three phrases on the NOW row, BRANCHES (this row, and the previous row's SHA resolved to `a47b502`), the Recent-landings pointer, `SCHEMA.md` and the `PhaseCard.jsx:15-17` comment removed with the code.
10. **#121 strings for the served-bundle grep: OWED after deploy.** "End phase", "same-day correction", "A phase needs at least one quota slot". Not run by Code; the deploy has not happened.

**Verification run.** Backend 2863 passed, 1 failed locally: `test_context_builder_output_unchanged_pre_post_refactor` runs `git show 3360ed5:...`, a commit absent from this shallow clone; it passed in CI on PR 1. Frontend 358 passed; lint at the 6-error baseline (FEEDBACK §36), none in files touched.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** The Phase-change form row is built (#389); only its post-deploy bundle check is owed. The NEXT block for #378/#379 is now DONE. No other row changed.

**State.** PR 2 is open, green-checks pending at write time, self-merging on green. The `### #NEXT.` heading is resolved to `### 389.` in the close-out commit (master's decision max was #388 when re-read at `a47b502`). If master advances before the merge, re-resolve #389 in the DECISIONS heading and in the integers typed into ROADMAP, BRANCHES and CLAUDE.md (FEEDBACK §37: type the integer into the new text; never a global replace).

**Single clearest next action.** After PR 2 merges and deploys, run the #121 grep on the live frontend bundle for the three strings and the #116 backend check. Then the clearest unbuilt work in NEXT is the reconcile leg of Walk in (#386), which needs a brief first.

**Operator actions owed.** (1) Confirm Polar Flow's max HR is locked at 175 (#388). (2) The Q159 in-activity HR read on or after 9 Oct. (3) The phone read of B, C and E for the appointment brief. (4) Look at the Phase card once deployed: "End phase → baseline" beside "Review / change phase", and the "same-day correction" chip on the two 4 Oct rows (operator-reported rows; Code has not read prod).

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session); the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). No question changed state this session; Q211 and Q215 were already closed (#378, #379).

**What was NOT touched (named so absence does not read as finished).**
- **The reconcile leg of Walk in** (NEXT, #386): unbuilt and unbriefed; this session did not move it.
- **The v1 tests Know and Loop beyond the phase form:** no change to the due-slot resolver, the daily loop, or the readiness path. This session was phase-entry and ledger hygiene.
- **The HC zones lane, Q199's maximal-effort test, Q216, the Polar re-zoning (Q198):** unmoved (finished as far as a session can finish it).
- **Q213, Q214, Q212; the sRPE floor, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Lab upload pipeline and the interpretation layer's remaining increments; medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gaps carried:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` and have not been checked for flipping on the 15th. `verify_series_integrity.py:56` still says `railway run`. The sandbox clone is shallow, so `test_context_builder_output_unchanged_pre_post_refactor` fails locally and passes in CI.
- **Not verified:** callers of `POST /engine/phase` outside the tree (the operator confirmed none, R2); the live deploy.
- **Pattern to say out loud:** this is a second consecutive run of sessions on instrument and ledger rather than the daily loop; the phase form is now closed out, so the next session should go to Walk in's reconcile leg or a Loop item, not to more phase-ledger work.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389; only the bundle check OWED): **Know** and **Loop**. Nearly finished; a demotion candidate once the bundle check is read.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
