# Close-out — Q207 located: the Pilates HR loss is HC to app, through the phone's fixed re-read window; findings and a design note recorded, nothing built

## Real commits this session

Range: `5b3363b` (master when the session opened) to this close-out. Branch: the harness-assigned `claude/epic-carson-xsmx2a`, kept per the harness instruction and rowed in `BRANCHES.md`. Its first use merged; this is its second use, restarted from master `3b275c1`.

- `524266f gov(srpe-floor): Q206 results and ruling (#367), sports:read at next Polar re-auth (#368), Q207, Q199 note`. Merged by Code on green as PR #302, merge commit `3b275c1`. Carried DECISIONS #367 and #368, the Q206 results, Q207 filed, the Q205 and Q199 notes, and the BRANCHES wording fix.
- This follow-up: one more `gov(srpe-floor): ...` commit carrying the Q207 findings (OPEN_QUESTIONS), one ROADMAP step edit, the BRANCHES rows, and this file. Its hash is on the branch; a file cannot name its own commit. The standing rule is one gov commit per session; this is the second, at the operator's request (the paste asked for Q207 to stay OPEN with these findings).
- No code commit, no migration, no data write. Nothing was run against prod: every prod fact is the operator's own query read, recorded as operator-reported. The companion repo `health-connect-app` was read at `0c2f982` (24 Sep, shallow, read-only); nothing was pushed to it.

## Pending-queue reconciliation

The pasted block "Q207 update (operator, 3 Oct)" asked for three reports and for Q207 to stay OPEN. Each landed in the commit above, or is named as not landed.

1. **Whether the sync re-reads HR for past windows** — landed in Q207 (1). Yes, to a fixed depth, not once at arrival: the phone reads the whole `days` window on every sync with no cursor (`src/healthConnect.js:418-444`), 7 days in the background task and the manual button, 30 days on the second manual button (`src/backgroundSync.js:52`, `src/SyncScreen.js:268,278`). The server stores any sample time and recomputes every HC row's zones from stored samples on every chain run. The lead hypothesis is half right: late HR is re-read, but only for 7 days (30 by hand).
2. **Whether a back-window re-sync can recover 69, 85 and 92** — landed in Q207 (2), as "probably, if within 30 days; untested". The dates of those rows were not read here. The deciding test is named for the operator: press the 30-day sync and re-run Q207's first read.
3. **A design note for the fix** — landed in Q207 (3), with three options (A: widen the scheduled window; B: a targeted re-read keyed on unzoned sessions; C: measure the lateness first), Code's lean (C, then A if the lag is bounded), and no build.
4. **Q207 stays OPEN with these findings** — done, with a restated State line.

Two things in the findings the paste did not ask for, flagged here so they are not buried:
- **#364's dismissal of the Q159 lag blocker does not hold up as evidence.** It rested on "the newest HR sample is 0.0-7.6 h old at each POST", which measures the freshest sample of the stream (passive sampling refreshes it constantly) and cannot see how late in-activity HR is. Q159 had recorded in-activity HR arriving about 6 days behind the workout, one day inside the 7-day window. No decision changes (#364 is append-only); the note is in Q207 and its State line.
- **The located case does not cover all of Q207's rows.** It covers the Pilates rows (Q198 names 69, 85 and 92). Q198 already attributes 68 and 84 to Samsung rows with no same-writer HR, and rows 71 and 80-83 are not accounted for. Q207 stays OPEN for them.

Provisional until merged: everything above.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One row was edited: **Polar sport-id relabel, and the H10-vs-Hevy facts (#366, #367, #368, Q205-Q207).** Its step (6), Q207, now carries the findings. Its remaining steps: the backfill report, `--apply` and `refresh_load` (operator, unchanged and not known to have run); the marker-exposure build (Luke briefs, Code builds; #367); Q205 at the next Polar re-auth (#368); the Q207 tests (operator) and the choice among its options (Luke); the HRmax test (Q199). Unchanged and still in NOW: Source hierarchy (#365), HC zones (#364) deploy/seed/verify steps, injury clearance via the #340 sweep, aerobic ingest automated check (#353), session fidelity G6.

**State.** The PR is governance-only (no code, no migration), so it self-merges on green under CLAUDE.md § Merge disposition. No new decision numbers were minted; master's max is #368 and Q207.

**Single clearest next action.** The operator presses the 30-day sync on the phone, then re-runs Q207's first read for rows 69, 85 and 92 (and 71, 80-83). It costs one button and it tells two causes apart: in-activity samples appearing means Garmin wrote them to HC after the 7-day window had passed (the fix is a deeper or targeted re-read, options A and B); samples still absent while HC holds them means the phone's read path is at fault (the next read is `health_connect_sync_events.fetch_meta -> 'heartRate'` for the POSTs after the session). Nothing in Q207's design note should be built before that result.

**Operator actions owed.** (1) The 30-day sync and the Q207 first read again (above). (2) The Q207 second read on the next non-GPS Garmin session, since `hr_samples.created_at` only measures lateness for sessions recorded after the #364 deploy. (3) The `start_time` of rows 69, 85 and 92, to know whether any is beyond a 30-day window (the first read can print it by adding `s.st` to its SELECT and GROUP BY, or query the table directly). (4) The backfill report, `--apply`, and `refresh_load` (carried from the last close-out). (5) Q205 at the next Polar re-auth, with `sports:read` requested then (#368). (6) A maximal-effort HRmax test (Q199), unscheduled. (7) Which build the phone runs: `SELECT git_sha, max(synced_at) FROM health_connect_sync_events GROUP BY git_sha ORDER BY 2 DESC LIMIT 3;` (unrun; the columns are as `models.py:375-410` declares them). The code findings are for `0c2f982`, and a different installed build would change them.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 114 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). No question was added or closed in this follow-up; Q207 is still OPEN, now with findings.

**What was NOT touched (named so absence does not read as finished).**
- **Nothing in the HC pipeline was changed.** No sync window, no fetch, no server code. Options A, B and C in Q207 are unbuilt and unruled.
- **The input-layer design and any arbitration change.** Q201 is still waiting on a chat design with no repo artifact. #367's constraint for it stands: HR recorded over a gym session must still deposit.
- **The marker exposure (#367) is filed, ruled and unstarted.**
- **Q202, Q203 and Q189** (an RPE floor, an expected-but-absent signal) did not move, though Q207's finding is a live instance of their gap: a starved HC row deposits nothing and says nothing. The session name carries "SRPE floor", but no sRPE decision has been put to this session.
- **Know / the plan:** plan-conformance adjudication (Q197) is still a chat proposal; Q27 and the Rule 1 vote counter are unchanged.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Loop / Fitness UI:** no frontend work.
- **Pattern to say out loud:** another session on load and ingest plumbing, now reaching across two repos. The plan-versus-log judgement (Q197) and the Walk-in surfaces the plumbing feeds have gone untouched for several sessions. The queue after the 30-day sync test is rulings (Q207's options, Q201-Q203, the input-layer design) and one cross-repo build, not more instrument work.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, Q207, OWED): **Know** (a session carries the name Polar shows, and a Pilates session's load is not silently zero) and **See** (a gym-session HR trace is visible as one, in the MCP as in the chat context).
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**. Q207 is a live gap in it: HR that reaches HC late never reaches a zoned row.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
