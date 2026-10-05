# Close-out — Q215 is ruled (#379: keep appending, a derived same-day flag, a wizard review skip, a tests-only pin; one shared brief with #378) and the #371 overlap proof now waits on a natural overlap or a debug control (#380); nothing built

## Real commits this session

Session `phase-ledger-same-day-rows` (the previous session, `phase-open-path-and-carried-items`, had closed out and merged at `1dc8bed`). Range: `1dc8bed` (master at open) to this close-out. Fresh-clone settings verified set at open (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open: decisions 378, questions 214. Maxima now: decisions 380 (#379, #380), questions 215.

- **No code commit, no code PR.** One scratch test (the 4 Oct sequence, run against the repo's own helpers) was run and **deleted; it is not committed**.
- **#324** `gov/phase-ledger-same-day-rows` (merge `4be42db`, self-merged on green: guard, vitest and pytest read as success on the pinned head): Q215 filed, ROADMAP row 39, the CLAUDE.md pointer. Governance only.
- **This PR** `gov/q215-ruled-371-method`: one governance commit (the hash is on the branch; a file cannot name its own commit): DECISIONS #379 and #380, Q215 closed, ROADMAP rows 37 and 39 and the shared NEXT brief, the BRANCHES rows, the CLAUDE.md pointer, this file.

**Disclosure: two `gov(...)` commits this session** (#324 and this one). CLAUDE.md allows one. The second records the operator's ruling, which arrived after #324 landed. Each was a single commit on its own branch. Stated here, not hidden.

- Migration: none. No prod write. Code has no database access; the ledger rows are operator-reported and reproduced from the code, not read from prod. The HTTP-log facts below were read by Code from Railway.

## Pending-queue reconciliation

The operator's 5 Oct ruling, item by item.
1. **Q215 ruled: adopt the lean — recorded as #379; Q215 closed.** Same-day correction keeps appending (#317 stands); a derived flag on the history route for zero-length rows (`closed_on == entered_on`), which the card collapses or labels (no schema, no migration, no deletion); the wizard skips the "did the block do its job" review when the open row was entered today and names the row the save will close; a tests-only pin of the zero-length exclusion in `phase_at` and the open-phase readers. **Build not scheduled;** ROADMAP NEXT now carries one shared brief with #378 (same wizard and route surface), with the pin able to ship first on its own. Left for the brief: the flag's name and shape, collapse versus label, and what close reason a skipped review leaves.
2. **#371 overlap proof — method dropped; recorded as #380.** "Manual sync during a scheduled one" is dropped (a sync takes about 8 s; the worker's start drifts by minutes). #371 stays OWED until a natural overlap shows in the Railway HTTP log or a debug control fires two syncs back to back. **Checked by Code, not just recorded:** none of the four POSTs since #371's deploy (23:12Z on 3 Oct) through 00:09:50Z on 5 Oct overlap (computed from log time minus duration); the start-to-start gaps are 6 h 0 m 30 s, 6 h 4 m 31 s and 6 h 0 m 20 s, so the drift is 0 to 4.5 minutes. The debug control is not built: it is a companion change, and the two sync buttons are disabled while a sync runs (`SyncScreen.js:284,294`).
- **Cross-repo debt, not edited from here:** the companion's `ROADMAP.md:127`, `closeout.md:53` and its locked DECISIONS #48 still name the dropped method; its next close-out should drop them.
- **No longer an operator step:** #371's proof. Any session can read the HTTP log for an overlap.

Provisional until merged: everything in this PR.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Row 37 carries the new #371 method (#380); row 39's state is "the build is in NEXT, one shared brief (#378, #379)". NEXT holds the shared brief, UNSTARTED. No other row changed.

**State.** This PR self-merges on green. #379 and #380 resolved at master max #378. Open: Q212 OWED to the 16 Nov review; Q213 and Q214 OPEN with Luke.

**Single clearest next action.** Nothing blocks. When the operator schedules it, the shared brief starts by reading #378's three open points, then ships the tests-only pin first (it needs no further ruling). Until then the next dated item is the Q159 in-activity HR read on or after 9 Oct.

**Operator actions owed.** (1) The Q159 in-activity HR read (query on Q159) on or after 9 Oct; sessions 69, 85 and 92 can be tested now. (2) The instrument datasheets brief's scope. (3) Still open from earlier: the capture-rate query (Q202); the Polar backfill report, `--apply` and `refresh_load` (from the container); Q205 at the next Polar re-auth; the `concurrent_strength` marker build (Q206). (#371's proof is no longer an operator step; see #380.)

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 117 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This session: Q215 opened and closed (`DONE → #379`).

**What was NOT touched (named so absence does not read as finished).**
- **The shared build (#378 and #379):** not scheduled, nothing built; the wizard, `PhaseCard`, `PhaseHistory`, the history route and the ledger are as they were. The pin is not written.
- **The #371 debug control:** not built; a companion change.
- **Q212** (deferred to 16 Nov), **Q214** (`client.trigger` still dropped by the server; a column is a migration and a hold), **the Q159 read, the datasheets scope, Q213:** as the previous close-out left them.
- **The next date-bomb candidates:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` without pinning today; whether any assertion flips on the 15th was not checked.
- **`verify_series_integrity.py:56`:** its runtime message still says `railway run`.
- **The stale-looking amber warning** on a Garmin or Samsung `load_window` slot: left.
- **The sRPE floor, the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206):** unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** the sixth session in a row on the plan's input form and the phase ledger, and the first to end with two rulings recorded and still nothing built; the queue of unbuilt phase-form work (#378, #379) now outweighs what shipped this week. Walk in is where it was.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form (#375, #376, #378, #379; Q211 and Q215 closed, Q212 deferred; the build in NEXT): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED, first live read reported 4 Oct): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED; #370 DONE, #371's overlap proof waits on a natural overlap or a debug control, the Q159 read owed): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- The shared phase-entry and ledger build (NEXT), HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **Loop** for the phase build.
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
