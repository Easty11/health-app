# Close-out — Q215 filed: same-day phase corrections leave zero-length ledger rows and misplace close reasons; the ledger is verified append-only and the phase-aware readers exclude the rows; nothing built

## Real commits this session

Session `phase-ledger-same-day-rows` (the previous session, `phase-open-path-and-carried-items`, had closed out and merged at `1dc8bed`). Range: `1dc8bed` (master at open) to this close-out. Fresh-clone settings verified set at open (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open: decisions 378, questions 214. Maxima now: decisions 378 (nothing ruled), questions 215.

- **No code commit, no code PR.** One scratch test (the 4 Oct sequence, run against the repo's own helpers) was run and **deleted; it is not committed** (`git status` clean afterwards).
- **One governance commit**, on `gov/phase-ledger-same-day-rows`, self-merging on green (the hash is on the branch; a file cannot name its own commit): Q215, ROADMAP row 39, the BRANCHES rows, the CLAUDE.md pointer, this file. It is the only `gov(...)` commit of this session.
- Migration: none. No prod write. Code has no database access; the ledger rows below are operator-reported and reproduced from the code, not read from prod.

## Pending-queue reconciliation

The operator's 5 Oct brief, item by item.
1. **"Verify on master: is the ledger append-only?" — Yes, by model and application invariant, not by the database.** `models.TrainingPhase` says the only UPDATE is `closed_on` and `close_reason` at closure ("model+application invariant, no DB trigger"). The write sites are three (the closure and the insert in `_apply_open_phase`, `engine/training_phase.py:428-437`; `close_phase`, `:464-465`); no DELETE of a phase row exists outside tests and migrations; `test_closure_updates_only_closure_columns` pins it.
2. **"Propose a void/superseded marker rather than deletion" — proposed, on Q215.** (a) leave them; (b) a derived marker, no schema (`closed_on == entered_on` returned as a computed flag, the card collapses or labels it); (c) a stored `superseded_by` or `voided_on` (a migration, HOLD, a second permitted UPDATE); (d) delete, ruled out. Code's lean, not a ruling: (b).
3. **"Confirm phase-aware analytics exclude them" — confirmed, with two caveats.** The open-phase readers (the engine, resolver, `current_state`, the MCP read, the wizard draft) never see a closed row. `phase_at` (half-open) cannot return a zero-length row. **Reproduced, not inferred:** the 4 Oct sequence in a scratch test gave exactly the operator's ledger, `phase_at` for the day before returned the 09-21 row and for today the open row. **Caveats:** (i) no test pins the zero-length case (the existing test pins the boundary); (ii) `phase_at` has no non-test caller, so nothing phase-aware reads history yet. The chart overlay reads every row but collapses boundaries that snap to one category, so a zero-length row adds no line; the history card is the only surface that shows them.
4. **"Design question: should a same-day correction (#317) supersede the same-day row instead of appending?" — filed on Q215, no build.** Options (i) append (today), (ii) supersede in place (breaks "never edited after authorship except closure"; the weakest), (iii) append plus a marker. The zero-length rows are #317's ruled behaviour ("closes the just-opened phase same-day and opens the corrected one"), so the ledger worked as ruled.
5. **The close-reason placement — explained, and one useful finding.** The wizard asks about "the block you are closing" but the save writes the note onto the row open at save time. On 4 Oct the open row was a direct-open artefact, so the note about decompression landed on it. **#378 (removing the direct open) would have halved the artefacts and fixed this case:** revise then Move gives one zero-length row and the note lands on it correctly.
- The operator's confirmation that the history renders (#314) closes the "history check" that was owed; ROADMAP row 39 says so.
- **Not landed:** the pinning test and any marker; both wait on the ruling.

Provisional until merged: everything in this PR.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Row 39: the phase-change form lane is now OWED to Luke for Q215 only; the #378 build stays in NEXT, UNSTARTED. No other row changed.

**State.** The gov PR self-merges on green. Q215 is OPEN with Luke. Q212 is OWED to the 16 Nov review; Q213 and Q214 are OPEN.

**Single clearest next action.** Luke rules Q215: the lean is to keep appending, mark same-day rows with the derived flag (no schema), and skip the block-verdict review when the open row was entered today. If (b) is ruled, the build is a history-route flag plus a card label, with a tests-only pin of the zero-length exclusion.

**Operator actions owed.** (1) The Q159 in-activity HR read (query on Q159) on or after 9 Oct; sessions 69, 85 and 92 can be tested now. (2) #371's overlap proof: a manual sync during a scheduled one, both 200. (3) The instrument datasheets brief's scope. (4) Still open from earlier: the capture-rate query (Q202); the Polar backfill report, `--apply` and `refresh_load` (from the container); Q205 at the next Polar re-auth; the `concurrent_strength` marker build (Q206).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This session: Q215 opened; none closed or moved.

**What was NOT touched (named so absence does not read as finished).**
- **Any marker, supersede or reason change:** nothing is built; the ledger, `PhaseHistory.jsx` and the wizard are as they were.
- **The pinning test for the zero-length exclusion:** not written (a code change, and the ruling may change what it pins).
- **The #378 build** (not scheduled), **Q212** (deferred to 16 Nov), **Q214** (`client.trigger` still dropped; a column is a migration and a hold), **#371's overlap proof, the Q159 read, the datasheets scope, Q213:** as the previous close-out left them.
- **The next date-bomb candidates:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` without pinning today; whether any assertion flips on the 15th was not checked.
- **`verify_series_integrity.py:56`:** its runtime message still says `railway run`.
- **The stale-looking amber warning** on a Garmin or Samsung `load_window` slot: left.
- **The sRPE floor, the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206):** unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** the sixth session in a row on the plan's input form and the phase ledger, and the first that ended with no build and no ruling needed from Code. The finding worth carrying is that the artefacts are the cost of #317 and #378 halves them; the rest is a design choice for the operator. Walk in is where it was.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form (#375, #376, #378; Q211 closed, Q212 deferred, Q215 filed; OWED to Luke): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED, first live read reported 4 Oct): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, Q159, Q202, Q208, Q214, OWED; #370 DONE, #371's overlap proof and the Q159 read owed): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- The #378 build (NEXT), HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **Loop** for the #378 build.
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
