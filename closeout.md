# Close-out — Know is MET by operator ruling; the leg strip draws a soft item whose days equal its pool, stacks a row per day on a phone, lists tray days once and Monday first; each leg row says how many sessions it could not count and why

## Real commits this session

Session `know-met-leg-followups`, the operator's brief of 6 Oct 2026 (AEST), two PRs: Part A (governance) then Part B (code). Range: `2073d68` (master at open) to this close-out. Fresh-clone settings were already set and read back. Maxima at open, by anchored script: decisions #391, questions Q216. Minted: #392 (PR 1), #393 and #394 (PR 2); each resolved against master's max immediately before its merge (#391, then #392).

PR 1, governance only, merged:
- `71ec64c` `gov(know-met): #392 Know (v1 test 2) is MET by operator ruling; the #389, #390 and #391 bundle checks recorded as met; previous_partial accepted` - DECISIONS #392, ROADMAP (v1 Know line, the Weekly-resolver row, the Phase-change form row, the NEXT block, one input on the planning row), BRANCHES, the CLAUDE.md pointer.
- `ad972e1` `Merge pull request #340 from Easty11/claude/busy-clarke-f9vzkw` - merged on green (guard, pytest, vitest) with the head SHA pinned.

PR 2, code, on the same branch name restarted from `ad972e1` (the harness instruction and #387):
- `65f80e8` `feat(know-d): leg strip follow-ups (R9, mobile rows, tray order) and uncounted on each leg (R10)` - `LegStrip`, `LegWrap`, `legLabels`, `engine/resolver.py`, and their tests.
- `b5bb9f9` `gov(know-d-followups): #393 R9 and the strip follow-ups, #394 R10` - DECISIONS #393 and #394, BRANCHES, the CLAUDE.md pointer.
- A final `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).

No migration, no schema change, no prod read or write. PR 2 self-merges on green (non-schema; R9 and R10 are the operator's rulings, no new judgment by Code). **Provisional until merged: everything in PR 2.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The brief, item by item:

**Part A (governance record) — DONE, `71ec64c`, merged.**
1. **#389's #121 check** recorded as met by the operator's grep (the three strings present, the two removed ones absent), in #392 and ROADMAP; the Phase-change form row flips to DONE.
2. **#390/#391's #121 check** recorded as met (`index-Bh2Xn4H_.js`), with the operator's read of the live strip (desktop and phone) and the `/metrics` wrap. Operator-reported; Code did not re-check (egress to the frontend host is denied).
3. **`previous_partial`: ACCEPTED**, recorded in #392.
4. **Know (v1 test 2) is MET**, recorded in #392 with the operator's reading quoted; the ROADMAP v1 Know line flipped.
5. **The wizard's raw `metabolic`** added as an input on the phase-planning row.
- **A choice, named:** #389, #390 and #391's own Status and deploy-check lines are locked, so #392 carries the records instead of editing them (the brief said "status line only"; I read that as the kind of record, and the append-only rule decides how it is written). ROADMAP and three BRANCHES cells (mutable) were updated.

**Part B (code) — DONE, `65f80e8`, pending merge.**
1. **Mobile layout: DONE.** Below 640px the strip is one row per day; a block's text truncates with its full text in `title`. Tested at 380px **in a real browser** (Chromium via Playwright, throwaway harness, not committed): at 380px and 639px each day is its own row, no horizontal page scroll, each hard block's name a single line with nothing clipped; at 640px and 1024px seven columns, the long name ("Work — Instrument calibration") truncates to one line. Screenshots read. Vitest asserts the layout classes.
2. **R9: DONE.** A soft item whose candidate days equal its pool is drawn on its days as an outlined block; a larger pool stays tray-only; done renders only where it happened.
3. **Tray days: DONE.** De-duplicated, Monday first.
4. **R10: DONE.** **The stop condition was checked first and did not trigger:** `resolve()` lists a Hevy workout with no matching capacity slot (`off_plan`, with its capacity) and an untagged one (`untagged`); reproduced on a stability-only phase with three strength sessions and one untagged. Each `/engine/legs` row carries `uncounted {count, reasons}` from the same pass as `done`; LegWrap shows "N uncounted" with the reasons.
5. **Tests per item, mutation checks: DONE.** R9 (every pool fixed: 5 fail; none fixed: 2), the order (1), the dedupe (1, after a first mutation proved too blunt and was redone), the layout (1 each for no truncate, no single column, no row layout), R10 backend (3 variants, 2 each) and frontend (3 variants, 2 each).
6. **#121 strings, one per item:** "Leg days" (the phone layout), "every listed day" (R9), "candidate days" (the tray days), "Not counted toward any quota" (R10). All four are in a local `vite build`; the live bundle is not checked.

**Divergences and judgment calls, named.**
- **A nuance in R10, not changed:** `resolve()` evaluates aerobic sessions only when the window declares an aerobic slot, so in a leg with none an aerobic session is neither counted nor listed. `uncounted` is complete for Hevy workouts and for aerobic sessions only where the leg could have counted them. Recorded in #394.
- **R9's "candidate-day count" is derived on the page** (distinct weekdays the item appears on in the window), equal to `len(days)` for a 7-day leg. A leg shorter than 7 days would read as not fixed and stay tray-only; a server field is the fix if one ever appears. Recorded in #393.
- **Presentation choices the rulings did not spell out** (in #393 and #394): an item drawn on its days is not also listed by day in the tray; a missing `pool` never reads as fixed; `uncounted` is counts by reason, not the item list, shown in words with an amber line.
- **The 380px check is desktop Chromium at that width, not the phone.** The operator reads the strip on the device.
- **A process slip, mine:** a `pkill -f` matched its own shell command line and killed the step (exit 144); nothing it protected had run, and I re-ran the work without it.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed except the Phase-change form row (DONE). The v1 **Know** test is MET (#392); See and Know are met, Walk in is met with its reconcile leg unbuilt, Loop is not claimed.

**State.** PR 2 is open, checks pending at write time, self-merging on green. Backend suite on the PR 2 tree: 2886 passed, 3 skipped. Frontend: 387 passed; eslint clean on the changed files; `vite build` succeeds. No `#NEXT` placeholder on the branch (#393 and #394 typed directly).

**Single clearest next action.** The operator reads the live strip on the phone and the 28 Sep to 3 Oct leg on `/metrics` after the deploy settles, and confirms the four #121 strings in the live bundle. After that, the clearest unbuilt work is the reconcile leg of Walk in (NEXT, #386), which needs a brief first.

**Operator actions owed.** (1) The #121 bundle check for #393 and #394: the live `assets/index-*.js` contains "Leg days", "every listed day", "candidate days" and "Not counted toward any quota"; and a look at the strip on the phone and the 28 Sep to 3 Oct leg (it should now read "N uncounted"). (2) Carried from the last close-out: confirm Polar Flow's max HR is locked at 175 (#388); the Q159 in-activity HR read on or after 9 Oct; the phone read of B, C and E for the appointment brief.

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session); the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). No question changed state this session; Q197 (matching a done session to a planned one) is still open and R9 deliberately does not touch it.

**What was NOT touched (named so absence does not read as finished).**
- **The planning grid** (three-kind grid, quota pre-fill, advisory placement): unbuilt and unbriefed; its row carries three inputs now (the form cannot author a new recurring hard item, it never writes `sessions_per_week`, and the wizard still shows the raw `metabolic` token). Placement-level adherence is ruled out of Know's scope and would need versioned schedule items.
- **Listing which sessions were uncounted on a past leg:** only counts by reason are on the row. Aerobic sessions in a leg with no aerobic slot are still unlisted.
- **The reconcile leg of Walk in** (NEXT, #386): unbuilt and unbriefed. **Loop** (check-in, readiness, recommendation, close-out): no change.
- **Q197, the HC zones lane, Q199, Q216, the Polar re-zoning (Q198):** unmoved. The same for Q213, Q214, Q212; Source hierarchy (Q201, Q203); the marker exposure (#367, Q206); the sibling sync races (Q208); the Garmin self-evaluation read; #371's proof.
- **Lab upload pipeline, interpretation layer increments, medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gap carried:** `test_context_builder_output_unchanged_pre_post_refactor` fails in a shallow clone (it needs commit `3360ed5`) and passes in CI; this container is now unshallowed. `verify_series_integrity.py:56` still says `railway run`.
- **Pattern to say out loud:** this is the second session in a row on the Know test's own surfaces. Know is now MET and the strip, wrap and uncounted line are polished against the operator's live reading; a third session here would be polish on a met test. The next session should go to Walk in's reconcile leg or a Loop item.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389): **Know** and **Loop**. DONE (the bundle check met); a demotion candidate for removal from NOW.
- Know (d), the leg strip and wrap (#390 to #394): **Know**. Built and live-read; the test is MET (#392). Nothing left in NOW except #393 and #394's own deploy check.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
