# Close-out — device source hierarchy recorded (#365); four app-behaviour questions verified and filed (Q201-Q204)

## Real commits this session

Range: `054d2d9` (master when the session opened; the merge of PR #298) to the close-out commit, real `git log` of branch `ccr-e19d34fa-k09fxb` (harness-assigned name, kept per the harness instruction):

- one commit, `gov(source-hierarchy): ...`, carrying DECISIONS #365, OPEN_QUESTIONS Q201-Q204 and three cross-reference notes (Q124, Q189, Q190), one ROADMAP NOW row, the BRANCHES row, the CLAUDE.md Recent-landings pointer, and this file. Its hash is on the branch; a file cannot name its own commit. The brief asked for a single `gov(...)` commit at close-out, so the close-out artifacts ride in it rather than in a second `chore: session close-out` commit.

No feature code, no schema migration, no data deletion. The only other artifact is a scratch script (`sim_qa.py`, in the session scratchpad, not committed) that runs the real `reads.aerobic_reads.arbitrate()` on synthetic rows.

## Pending-queue reconciliation

No `PENDING` items were carried in: this session's input was a chat brief, not a `;cc` queue. Everything in the brief landed in the one commit:

- The hierarchy text (running, field work, the explicit-absence principle, the Garmin %HRR note as context only): DECISIONS #365.
- Q-A to Q-D, each with file:line findings and a gap, each filed because master does not already handle it: Q201 (cross-source dedup), Q202 (RPE floor), Q203 (missingness), Q204 (activity type). None was resolved on master's behalf, so none is `DONE`.
- Existing entries Q190, Q189 and Q124 were not closed or edited; each gained an additive cross-reference paragraph. Q190's stale premise (it says the #309 ladder is same-source only) is corrected in that note and in Q201; closing Q190 would be a resolution call chat has not ratified.
- **The brief's HALT condition was not evaluable, and the brief's gate was honoured on that basis.** The condition is "Q-A shows the 1 Oct run already present twice in load". This session had no route to the prod DB (no Railway CLI, no database variables checked by name only, the `Health_app_data` MCP unauthorised), so no row was read. The code reading predicts one deposit if the Polar start is within about 640 s of the Garmin start (both were reported as about 18:49), so the HALT was treated as not triggered, and the live check was filed as owed to the operator (the two queries in Q201). It is **provisional** until those rows are read.
- **Brief statements about unseeable surfaces were recorded as the operator's statement, not as fact:** the hierarchy, the 1 Oct wrist-against-H10 HR figures (145/145, 158/157), and the Garmin and Polar run figures (3.34 km 21:33; 3.36 km 22:05). #365's How-you-know says so.
- **Citation corrections (mine).** The findings were first reported in chat with four off-by-one or off-by-two line cites; the entries carry the corrected ones (`sport_classes.py:27`, `engine/training_phase.py:71`, `reads/psychological_reads.py:363-392`, `mcp_server.py:559`).
- **Found, not fixed (outside the brief):** the CLAUDE.md "Prod psql route" note says `load_events.window` is a Postgres reserved word and must be quoted. The column was renamed to `load_window` by migration `1341a2cf6938` (and the model says so), so following the note would query a column that does not exist. The Q201 queries use `load_window`. The note needs a correction in a later governance commit.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One new row from this session: **Source hierarchy (#365): read the 1 Oct run in prod, then rule Q201-Q204 (OWED, operator then Luke).** Still in NOW and unchanged by this session: HC zones (#364) release/seed/verify steps (OWED, operator; master carries the #298 merge `054d2d9`, but the deploy, the `user_hrmax` seed, the HCA syncs and the G3 report were not checked here), injury clearance via the #340 sweep (OWED, operator), aerobic ingest automated check (#353, OWED, operator), session fidelity G6 (OWED, operator).

**State.** The branch is pushed and the PR is a governance-only change (no migration, no code), so it is not under the migration hold; it self-merges on green under CLAUDE.md § Merge disposition. Numbers #365 and Q201-Q204 were resolved at master max #364 / Q200 (`054d2d9`); re-read master's max and re-resolve if it advances before the merge.

**Single clearest next action.** The operator runs the two queries in Q201 over `railway connect` (user 1, 1 Oct): the two `start_time` values and `sport_id`/`sport_name` for the run, and the metabolic `load_events` rows for it. One deposit means dedup held and the HALT case did not occur. Two means a data defect: report it, rule, and clean nothing without the ruling.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 114 OPEN, 4 OWED (Q78, Q176, Q178, Q181). New this session: Q201, Q202, Q203, Q204 (all OPEN, none blocking). Closed this session: none. The four new ones are the gate on any device-hierarchy implementation: Q201 (does the hierarchy enter arbitration; surface suppression), Q202 with Q189 (an RPE floor for a no-HR watch run), Q203 (an explicit expected-but-absent signal; with Q169/#326 and Q124), Q204 (the trail-run label is lost at Health Connect; persisting `title` would be a schema migration).

**What was NOT touched (named so absence does not read as finished).**
- **Build of any kind.** #365 is recorded, not built: arbitration, the load formula, ingest, the resolver and every consumer are unchanged, and the Q169/#326 coverage marker is still unbuilt (no table, no code on master).
- **Catapult SPT3 ingestion (Q124)** has not moved; no external-load lane (accel/decel, high-speed running, contact) exists in the load model, and the SPT appears nowhere in the code except a `source` tag on capability observations.
- **Know / the plan:** plan-conformance adjudication (Q197) is a chat proposal, not ruled; Q27 vocabulary and the Rule 1 vote counter are unchanged (#363 stays "recorded, not built").
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments, and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 clearance sweep, operator-owed) did not move.
- **Loop / Fitness UI:** nothing user-facing changed; no frontend work.
- **Pattern to say out loud:** this is again a session that went to load and ingest plumbing and its integrity (Polar ingest automation, session fidelity, the Garmin account repair, HC zoning, and now the device hierarchy). The things that plumbing feeds, the plan-versus-log judgement (Q197) and the Walk-in surfaces, have gone untouched for several sessions. Q201-Q204 are rulings for Luke, not build work, so the next Code session should not default to more instrument-side work.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Source hierarchy (#365, OWED): **See** (a run counted once; a suppressed twin or an absent device visible rather than read as rest) and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
