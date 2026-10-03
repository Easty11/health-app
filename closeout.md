# Close-out — Q206 read and ruled (#367); `sports:read` at the next Polar re-auth (#368); Q207 filed; the harness-ref wording fixed

## Real commits this session

Range: `5b3363b` (master when the session opened; the merge of PR #301) to this close-out. One branch, the harness-assigned `claude/epic-carson-xsmx2a`, kept per the harness instruction (it is rowed in `BRANCHES.md`).

- `claude/epic-carson-xsmx2a`: one `gov(srpe-floor): ...` commit carrying DECISIONS #367 and #368, OPEN_QUESTIONS (the Q206 results and OWED State, new Q207, a ruling note and new State line on Q205, a HRmax-provenance note on Q199), the BRANCHES edits, one ROADMAP row edit, the CLAUDE.md Recent-landings pointer, and this file. Its hash is on the branch; a file cannot name its own commit. The standing rule is one gov commit per session, so the close-out artifacts ride in it.
- No code commit, no migration, no data write. Nothing was run against prod: every prod fact below is the operator's own query read, recorded as operator-reported.

## Pending-queue reconciliation

The pasted block "GOV CARRY (Q206 results, operator, 3 Oct)" carried six items. Each landed in the commit above, or is named below as not landed.

1. **Q206 (a) overlap, (c) Hevy payload keys, (d) gap distribution** — landed as a "Results" block in Q206, tagged operator-reported.
2. **Q206 (b) ruling** — landed as DECISIONS #367. The deposit stays as it is. The required fix (expose `concurrent_strength` in `get_training_sessions` and the readiness summary) is filed OWED as Q206's State, with the loop-close named. It is not built; this was a governance session.
3. **New OQ: which writer owns sessions 68, 69, 71, 80-85 and 92, and why Garmin wrote no activity HR for them** — landed as Q207, OPEN, report-only, with one parser-checked read query for the operator. Not run.
4. **HRmax note** — landed as an Update on Q199, not a new question: Q199 already is the HRmax benchmark test, and a second entry would split it. Operator-reported: the observed 173 came from Polar rows 35 and 47, both short conditioning segments; only three field sessions were recorded through Polar all season (31, 67, 90).
5. **Q205 ruling** — landed as DECISIONS #368 and a Ruling note on Q205, whose State stays OWED with the loop-close restated. One derived point is flagged, not ruled: the scope is `SCOPES` at `connectors/polar.py:39`, so the one-line change has to be made before the re-auth's authorise URL is built. #368 records this as mechanics that follow from the ruling. If "nothing before" meant something else, #368 and Q205 are the two places to correct.
6. **Nit: "was left in place" versus pruned** — landed in the `BRANCHES.md` row for `claude/vigilant-wozniak-ompbx9`, after checking it: `git ls-remote --heads origin claude/vigilant-wozniak-ompbx9` returns nothing and there is no local ref. The prior `closeout.md` carried the same sentence; this file replaces it.

Housekeeping that rode along: the two `BRANCHES.md` cells that read "SHA resolved at next close-out" now carry the merges (`gov-polar-sport-map` = PR #301, `5b3363b`; `ccr-e19d34fa-k09fxb` = PR #299, `b447ed4`), both checked against `git log` and `git ls-remote` (both remote refs are gone). The stale "Operator: Q206 (a), (c) and the gap query" sentence on the `gov-polar-sport-map` row was replaced.

Provisional until merged: everything above. Nothing decided in the paste was left uncommitted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One row was edited this session: **Polar sport-id relabel, and the H10-vs-Hevy facts (#366, #367, #368, Q205-Q207).** Its step (4), the Q206 queries, is done and recorded. Its remaining steps are the backfill report and `--apply` plus `refresh_load` (unchanged, operator), the marker-exposure build (new, Luke briefs and Code builds), Q205 at the next Polar re-auth, the Q207 read (operator), and the max test (Q199). Unchanged and still in NOW: Source hierarchy (#365), HC zones (#364) deploy/seed/verify steps, injury clearance via the #340 sweep, aerobic ingest automated check (#353), session fidelity G6.

**State.** The PR is governance-only (no code, no migration), so it self-merges on green under CLAUDE.md § Merge disposition. Numbers #367, #368 and Q207 were resolved at master max #366 / Q206 (`5b3363b`); re-read master's max and re-resolve if it advances before the merge.

**Single clearest next action.** Luke writes the brief for the marker exposure (Q206 / #367): `concurrent_strength` into `get_training_sessions` (`mcp_server.py:547-572`) and the readiness summary's session count (`:738-758`), display and counting only. It is the one ruled item with no open design question, and it removes the only place the app currently tells two stories about a gym-overlapping Polar row. The operator-side queue, in order: the backfill report (`railway run python -m scripts.polar_sport_backfill`, read the `[class flips]` rows, then `--apply`, then `railway run python -m scripts.refresh_load --user 1`), then the Q207 read.

**Operator actions owed.** (1) The backfill report, `--apply`, and `refresh_load` (see above; the 3 Oct paste does not say whether this has run, so it is carried as not done). (2) The Q207 query in `railway connect`. (3) Q205 at the next Polar re-auth, with `sports:read` requested then (#368). (4) A maximal-effort HRmax test (Q199), unscheduled.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 114 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). New this session: Q207 (OPEN). Q206 moved from OPEN to OWED with its results recorded. Q199 got a note and stays OPEN. Closed this session: none.

**What was NOT touched (named so absence does not read as finished).**
- **The input-layer design and any arbitration change.** Q201 is still waiting on a chat design with no repo artifact. `_win_key`, the source ranks and the Edwards formula are unchanged. #367 adds one constraint for that design: HR recorded over a gym session must still deposit.
- **Q202, Q203 and Q189** (an RPE floor, an expected-but-absent signal) did not move, and neither did Q198 (re-zoning Polar from raw HR) or Q124 (Catapult SPT3 ingest). The session name carries "SRPE floor", but this carry did not touch the floor: the paste held Q206 results, not an sRPE decision. Q206 (d) adds one fact to that cluster: sessions 68, 69, 71, 80-85 and 92 deposit nothing because they have no same-writer HR, which is the same shape as the Q202 gap (a session with no usable HR deposits nothing), though whether they are watch-owned runs is not known (Q207 asks why they have none).
- **The marker exposure is not built.** It is filed, ruled and unstarted.
- **Know / the plan:** plan-conformance adjudication (Q197) is still a chat proposal; Q27 and the Rule 1 vote counter are unchanged.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Loop / Fitness UI:** no frontend work.
- **Pattern to say out loud:** this is another session on load and ingest plumbing and its evidence (a mapping table, a relabel script, an inventory of what HR the app keeps, now the results of the queries that inventory asked for). The plan-versus-log judgement (Q197) and the Walk-in surfaces the plumbing feeds have gone untouched for several sessions. The queue after the backfill and the marker build is rulings (Q201-Q203, the input-layer design), not more instrument work.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** (a session carries the name Polar shows) and **See** (a gym-session HR trace is visible as one, in the MCP as in the chat context).
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
