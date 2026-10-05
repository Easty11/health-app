# Close-out — #385 is recorded as applied (#388): user 1's HRmax is 175 in prod and HC/Polar parity at 175 is closed, with one residual z2/z3 rounding difference that is not built against

## Real commits this session

Session `hrmax-restatement`, fold-in after #331 landed (merge `28bd699`). Range: `28bd699` (master at open) to this close-out. The branch was restarted from master per the harness instruction, same name, kept and permitted by #387. Fresh-clone settings were already set and re-verified (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open: decisions 387, questions 216. Maxima now: decisions 388 (#388), questions 216 (unchanged).

- `99100be` `gov(hrmax-applied): #388 #385 is applied: user 1's HRmax is 175; HC/Polar parity at 175 is closed, residual z2/z3 rounding difference not built against` - DECISIONS #388, the ROADMAP HC zones row, a Q199 note, BRANCHES (this row, and the previous row's SHA resolved to `28bd699`), the CLAUDE.md Recent-landings pointers.
- The `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).
- **One `gov(...)` commit**, as CLAUDE.md now allows (one per landed ruling, #387). No code, no schema, no migration: governance only, so it self-merges on green.
- **No prod write and no prod read by Code.** Every figure in #388 is the operator's, relayed in chat.

## Pending-queue reconciliation

Nothing came from the chat `;cc` queue as a PENDING item. The operator's fold-in brief (5 Oct 2026), item by item:

1. **Record #385 APPLIED: DONE (`99100be`), as #388.** #385 is merged and append-only, so it is not edited; #388 records the write (user 1, 175, `adjusted`, restating row #1, effective 2026-03-01), the 29 HC rows moved 173 -> 175, `refresh_load` OK (hc_zoned 17/29, changed 15; TRIMP against Polar cardio-load r = 0.974, n = 46), and the four parity rows.
2. **Post-apply parity at 175: recorded, CLOSED by the operator's call.** HC minus Polar, z1..z5 in minutes: 20 Sep #71/#90 [0, 0, 0, 0, 0]; 28 Sep #88/#91 [0, +0.43, -0.45, 0, 0]; 1 Oct #96/#95 [0, +0.06, -0.05, 0, 0]; 2 Oct #100/#97 [0, +3.04, -3.05, 0, 0]. The 28 Sep z5 gap was +0.88 at 173 and -1.04 at 177, so 0.00 at 175. This closes item 4 of the original brief, which I had reported as not done and not doable from a session.
3. **Residual finding, no build: recorded.** Every remaining gap is a z2/z3 swap at 70% of 175 = 122.5 bpm. **What Code added, tagged:** in `band_for` at 175, HC puts 122 bpm in z2 and 123 in z3, and its lower edge at each of the three half-bpm edges (87.5, 122.5, 157.5) is the next whole bpm up. The data (zero gaps at 87.5 and 157.5, a gap only at 122.5) fits Polar rounding half to even (88, 122, 158) and does not fit rounding down. **Likely, not tested;** Polar's convention is not documented here, and a count of `hr_samples` at exactly 122, 87 and 157 bpm in the affected bouts would test it.
4. **Polar Flow's max HR locked at 175 as user-set: the operator's action, "being locked".** Recorded as such; whether it is done is not known to Code, so it stays OWED (a confirmation).
5. **Close the HC zones row's owed items accordingly: DONE, with two left open on purpose.** The apply and the parity report are closed. Still OWED: the Polar lock confirmation (operator) and the single-row HC bout deposit read (#384 item 4, low priority). The row is not marked finished, because those two are real.

**One thing worth saying about "parity closed".** It is the expected result of having chosen 175 to match Polar: it shows HC zoning agrees with Polar's at the same maximum, not that 175 is the true maximum (#385; only Q199's test can say). #388 states this so the closure is not read as a validation of the value.

Provisional until merged: everything on this branch.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** The HC zones row now reads: landed, seeded, verified; 175 applied in prod (#388); HC/Polar parity closed at 175. OWED only: the Polar lock confirmation and the single-row deposit read. No other row changed.

**State.** One governance-only PR, self-merging on green; no `#NEXT` placeholders, no migration. Number resolved at master max #387 / Q216 (`28bd699`); re-read it immediately before the merge. Open: Q212 OWED to the 16 Nov review; Q213 and Q214 OPEN with Luke.

**Single clearest next action.** The corrective-path work is finished, so the next product work is not on the zones record. The clearest unbuilt item in NEXT is the shared phase-entry and ledger build (#378, #379, one brief), or the reconcile leg of Walk in (NEXT, #386, which needs a brief first). Which one is the operator's call; neither has been briefed.

**Operator actions owed.** (1) Confirm Polar Flow's max HR is locked at 175 as user-set (if it reverts to an age estimate in November, the seam reopens: #385). (2) The Q159 in-activity HR read on or after 9 Oct. (3) The phone read of B, C and E against the ledger for the appointment brief, which is not recorded as done. (4) Whether the #121 discharge of the Conditioning grep lifts the block-2 gate (#270). (5) The items in earlier handoffs that this session did not touch.

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session). The single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212, carried from the last count; no question changed state). This session: Q199 gained a dated note (the restatement is applied; the maximal-effort test is still the only route to a measured value) and stays OPEN.

**What was NOT touched (named so absence does not read as finished).**
- **The z2/z3 rounding difference:** recorded, not tested and not built against (the operator's call). Polar's convention is unread.
- **Q199's maximal-effort test:** unmoved. 175 is a corrected floor aligned with Polar, not a measurement.
- **HR-reserve zoning (Q216), the bands, Polar's own zoning, the Polar re-zoning (Q198):** unmoved.
- **Single-row HC bout deposits (rows 79-83, 70, 86, 87, 94, 101), the seven pre-reach unzoned rows (72-78), user 4's `no_hrmax`:** unmoved.
- **The reconcile leg of Walk in** (NEXT, #386): unbuilt and unbriefed. The "Mark attended" route and the answered-state on asks do not exist.
- **The shared phase-entry and ledger build (#378, #379), Q213, Q214, Q212; the sRPE floor, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Lab upload pipeline and the interpretation layer's remaining increments; medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gaps carried:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` and have not been checked for flipping on the 15th. `verify_series_integrity.py:56` still says `railway run`. The sandbox clone is shallow, so `test_context_builder_output_unchanged_pre_post_refactor` fails here and not in CI.
- **Pattern to say out loud:** several sessions running have gone to the HC zones record, and it is now finished as far as a session can finish it; the next session should not be another one on it. Walk in and the phase-entry build are where the queue stands still.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. This lane has no real work left and is a demotion candidate once the lock is confirmed.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Phase-change form (#375, #376, #378, #379; the build in NEXT): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build: **Walk in**, unstarted; labs left v1 under #345, so the lab pipeline's v1 claim is weaker than its row says and it is a demotion candidate.
- The shared phase-entry and ledger build (NEXT), HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **Loop** for the phase build.
- Cross-repo shared-block rows (including the #387 propagation): no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
