# Close-out — Know (d): the leg strip on the Phase card and the leg wrap on /metrics are built; a partial leg shows no delta; "Conditioning" is the one label

## Real commits this session

Session `know-d-leg-wrap`, the operator's brief of 6 Oct 2026 (AEST), two PRs. Range: `1006399` (master at open) to this close-out. Fresh-clone settings were not set in this container and were set and read back (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open, by anchored script: decisions #389, questions Q216. Minted: #390 (PR 1) and #391 (PR 2); each resolved against master's max immediately before its merge (#389, then #390).

PR 1, backend, merged:
- `c4a9093` `feat(know-d): GET /engine/legs, an injected window for resolve(), widened week-plan day items` - `engine/resolver.py`, `engine/week_plan.py`, `routers/engine.py`, `tests/test_legs.py`, the #390 entry, its BRANCHES row.
- `82403d1` `gov(know-d): resolve #NEXT -> #390 against master max #389`.
- `97391da` `Merge pull request #338 from Easty11/claude/busy-clarke-f9vzkw` - merged on green (guard, pytest, vitest) with the head SHA pinned.

PR 2, frontend, on the same branch name restarted from `97391da` (the harness instruction and #387):
- `cd71531` `feat(know-d): LegStrip on the Phase card, LegWrap on /metrics, R8 (no delta against a partial leg)` - `LegStrip`, `LegWrap`, `legLabels`, the Phase card, the quota window, `/metrics`, their tests, and `previous_partial` on the leg rows.
- `d2de64f` `gov(know-d): #391 R8 and the frontend build; Know (d) DONE as a code item with the gap against Know's wording named; phase-planning row` - DECISIONS #391, ROADMAP, BRANCHES, the CLAUDE.md Recent-landings pointer.
- A final `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).

No migration, no schema change, no prod read or write. PR 2 self-merges on green (non-schema; R8 is the operator's ruling, no new judgment by Code). **Provisional until merged: everything in PR 2.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The brief, item by item:

**PR 1.**
1. **Widen week-plan: DONE (`c4a9093`).** Hard items add `satisfies`, `time_of_day`, `time_range` when present; flexible items add `time_of_day`, `time_range` when present and `pool` always. Consumers confirmed: `context_builder` reads day items by `.get`, `session_focus` imports only `item_covers`.
2. **Injected window: DONE (`c4a9093`).** `resolve(..., window=None)`; the current path is pinned by a golden literal and by equality with the same window injected.
3. **`GET /engine/legs?n=8`: DONE (`c4a9093`).** n clamped to 1..26. Phase per leg from `phase_at`; bounds from the phase's `entered_on` and `sub_cycle_days`, cut at its close.
4. **Docstring: DONE (`c4a9093`).** `plan_week` lists and does not place.
5. **Tests: DONE.** Prior-phase quota with a `phase_at`-for-`current_training_phase` control that changes the answer; a partial leg; a zero-length row (paired with a one-day row that does produce a leg); template-only history; the byte-identical path; the widened keys with the old keys unchanged. Mutation-checked.

**PR 2.**
1. **LegStrip: DONE (`cd71531`).** Replaces the "Schedule vs quota" lines; the freshness warning and the planning note stay. Columns from the payload's own day list (a Sun-Sat window and a Mon-Sun window are both tested; sorting Monday-first fails four tests). Hard blocks with time, actual marks, soft pools only in the tray, greyed unavailable days, caution note.
2. **LegWrap: DONE (`cd71531`).** Mounted at the top of `/metrics`.
3. **R7: DONE for the three surfaces named.** One helper, `legLabels.keyLabel`, used by the quota window, the strip and the wrap.
4. **Tests per ruling, mutation checks: DONE.** R6 (the pool drawn per day: 1 fails), R7 (label mapping removed: 2), R4 (partial marker removed: 1), R8 (both flags ignored: 4; only `previous_partial` ignored: 3), `previous_partial` always false (1 backend).
5. **#121 strings.** "to place", "Conditioning", and the LegWrap-specific string **"Done vs quota, by leg"** (the wrap's heading). Present in a local `vite build`; **the live bundle is not checked** (Code's egress to the frontend host is denied).
6. **Governance: DONE (`d2de64f`).** One entry, #391 (R8, the divergence, what was built); #390 holds R1-R7 and is not edited. ROADMAP: the Weekly-resolver row's (d) marked DONE as a code item with Know's wording quoted and the gap named (below); the Visuals increment-4 sentence; the new phase-planning row in NEXT, carrying (f) and the never-written `sessions_per_week` as inputs. BRANCHES rows for both PRs.

**R8 and the operator's agreements.** The two agreed calls (walk start today; one leg beyond `n`) are recorded in #391. R8 is built as presentation only.

**Divergences and judgment calls, named.**
- **A backend field added in PR 2, against "the backend stays as built".** Each leg row carries `previous_partial` (`true`, `false`, `null` at the ledger start). R8 needs the predecessor's flag; the oldest returned row's predecessor is the leg counted beyond `n` and not returned, so the page cannot see it. `delta_done` is unchanged. Named in #391 and the PR body.
- **Does Know (d) meet Know's v1 test wording ("Know — what's due, enforced against the plan.")?** Only in part. What is due and its enforcement were met before (#276, #308); (d) adds a history of finished legs against the quota, which does not change what is due now. The wrap compares with the authored quota only (R2), not with placement, so "against the plan" holds at the quota level. The ROADMAP row marks (d) DONE as the code item, **does not claim the Know test MET**, and names placement-level adherence (versioned schedule items) as the gap.
- **Presentation choices the rulings did not spell out** (in #391): the tray row is named by the linked activities with the key label muted beside it; "N over quota" keeps the old MISMATCH signal; an unlinked soft item shows as "no quota".
- **A citation:** `#316` and `week_plan.py` cite "#275's free-order rule"; `#275` has no such text (searched). Recorded in #390; the cites are left (append-only).
- **Out of R7's stated scope, left alone:** the phase-change wizard's slot-key selector and placeholder still show the raw token `metabolic`.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. The ROADMAP Weekly-resolver row's remainder (d) is DONE as a code item; NEXT gains the phase-planning row (UNSTARTED, no brief).

**State.** PR 2 is open, checks pending at write time, self-merging on green. Backend suite on the PR 2 tree: 2884 passed, 3 skipped; frontend: 378 passed; eslint clean on the changed files (the repo's pre-existing lint debt is unchanged); `vite build` succeeds. No `#NEXT` placeholder on the branch (#391 typed directly).

**Single clearest next action.** The operator reads the live Phase card strip and the `/metrics` wrap against the real ledger, after the deploy settles. That is the check Code cannot make (no prod access) and the one the fixtures cannot replace.

**Operator actions owed.** (1) The #116/#121 deploy checks for #390 and #391: backend and frontend SUCCESS; an authenticated `GET /engine/legs` returns 200 with `legs[]`, `excluded` and `previous_partial`; the live `assets/index-*.js` contains "to place", "Conditioning" and "Done vs quota, by leg"; and the #389 strings ("End phase", "same-day correction", "A phase needs at least one quota slot") are still owed from before. (2) Rule whether the Know test is MET, given the quota-level gap. (3) Carried from the last close-out: confirm Polar Flow's max HR is locked at 175 (#388); the Q159 in-activity HR read on or after 9 Oct; the phone read of B, C and E for the appointment brief.

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session); the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). No question changed state this session; Q197 (matching a done session to a planned one) is still open and R6 deliberately does not touch it.

**What was NOT touched (named so absence does not read as finished).**
- **The planning grid itself** (three-kind grid, quota pre-fill, advisory placement): unbuilt and unbriefed; only its row and two inputs are recorded. The phase-change form still cannot author a new recurring hard item, and still never writes `sessions_per_week`.
- **Placement-level adherence for a past leg:** impossible until schedule items are versioned; not started, not briefed.
- **The reconcile leg of Walk in** (NEXT, #386): unbuilt and unbriefed. **Loop** (check-in, readiness, recommendation, close-out): no change.
- **Q197, the HC zones lane, Q199, Q216, the Polar re-zoning (Q198):** unmoved. The same for Q213, Q214, Q212; Source hierarchy (Q201, Q203); the marker exposure (#367, Q206); the sibling sync races (Q208); the Garmin self-evaluation read; #371's proof.
- **The wizard's raw `metabolic` token** in the slot-key selector (above).
- **Lab upload pipeline, interpretation layer increments, medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gap carried:** `test_context_builder_output_unchanged_pre_post_refactor` fails in a shallow clone (it needs commit `3360ed5`) and passes in CI; this container was shallow until `git fetch --unshallow`. `verify_series_integrity.py:56` still says `railway run`.
- **Pattern to say out loud:** unlike the last three sessions, this one was product work on the Know test, not instrument or ledger hygiene. It is still a read-only view of a plan the form cannot fully author; the next session on Know should go to the planning lane (which needs a brief) rather than a fourth view.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389; only the bundle check OWED): **Know** and **Loop**. Nearly finished; a demotion candidate once the bundle check is read.
- Know (d), the leg strip and wrap (#390, #391; the live read OWED): **Know**. Built; the Know test's MET call is the operator's.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
