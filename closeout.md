# Close-out — Q207 closed (#369): Garmin's 7-day HR export lag plus a scheduled sync that never read; the chat outage and the sync race fixed (#371); Q159 reopened

## Real commits this session

Range: `5b3363b` (master when the session opened) to this close-out. One branch name throughout, the harness-assigned `claude/epic-carson-xsmx2a`, kept per the harness instruction; each use was restarted from master after its PR merged, and every use is rowed in `BRANCHES.md`.

- `524266f gov(srpe-floor): Q206 results and ruling (#367), sports:read at next Polar re-auth (#368), Q207, Q199 note`. PR #302, merge `3b275c1`.
- `850d452 gov(srpe-floor): Q207 findings - Pilates HR loss is HC to app via the phone's fixed re-read window; design note, no build`. PR #303, merge `73e58b0`. Its conclusion is superseded by #369.
- `d7f3ab7 fix(chat): a Hevy exercise with null notes no longer 500s every POST /chat`. PR #304, merge `f9c23dd`. A production outage fix; verified live (a `POST /chat` returned 200 on the new deploy).
- `56d593f fix(hc-sync): overlapping syncs no longer race on record_sources or mask the failure as hr_samples`. PR #305, merge `f695591`. Deploy `19a26b44` reached SUCCESS at 23:12Z on 3 Oct; no sync had reached it when this was written.
- This close-out: one more `gov(srpe-floor): ...` commit carrying DECISIONS #369-#371, the Q207 closure, the Q159 reopening, a Q202 scope note, new Q208, FEEDBACK §60-§62, the ROADMAP and BRANCHES edits, the CLAUDE.md pointer, and this file. Its hash is on the branch; a file cannot name its own commit. It is the third gov commit of the session (the rule is one); the operator's rulings of 4 Oct are the request for it.
- No migration. No prod data write. Nothing was run against prod from this session: every prod DB fact is the operator's own query read. Code read Railway deploy logs and the HTTP log, and read the companion repo `health-connect-app` at `0c2f982` (shallow, read-only; nothing pushed to it).

## Pending-queue reconciliation

The pasted block "Q207 results (operator, 4 Oct)" carried five rulings. Each landed, or is named as not landed.

1. **Q207 closed** — landed: #369, Q207 moved below `## CLOSED` as `DONE → #369`. No app-side loss; Garmin exports in-activity HR to Health Connect about 7 days late, and the scheduled sync was failing with "Health Connect client is not initialized".
2. **Q159 reopened with the measured lag** — landed: #369 and a Reopened note on Q159, which moved back above `## CLOSED` with State OPEN. The note says #364's evidence (the freshest passive sample's age) does not cover in-activity lateness.
3. **P1 phone** — the init path and a fix proposal were reported (not built), and the ruling is recorded as #370. The build is OWED: it is in the companion repo, which this session can read but not push to. The brief is to follow.
4. **Server race fix** — landed: PR #305 and #371. One divergence was flagged in the PR and recorded in #371: `record_sources.synced_at` now means first captured, not last re-post.
5. **Q202 case-A scope note** — landed: a note on Q202 and a line in #369. The Q202 brief itself is not written; it follows.

Items from earlier pastes in this session (the Q206 rulings, the Q205 ruling, the Q199 note, the BRANCHES nit) landed in `524266f` and are not repeated here.

Provisional until merged: everything in the third gov commit. Nothing decided in the paste was left uncommitted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** New this session: **HC sync reliability: the scheduled read, the lag window, the race (#369, #370, #371, Q159, Q202, Q208)**, OWED. Edited: the Polar-relabel row (its Q207 step is closed). Unchanged and still in NOW: Source hierarchy (#365), HC zones (#364) deploy/seed/verify steps, injury clearance via the #340 sweep, aerobic ingest automated check (#353), session fidelity G6.

**State.** The third gov PR is governance-only (no code, no migration), so it self-merges on green under CLAUDE.md § Merge disposition. Numbers #369-#371 and Q208 were resolved at master max #368 / Q207 (`f695591`); re-read master's max and re-resolve if it advances before the merge.

**Single clearest next action.** Luke writes the P1 brief (#370). Until it lands, the scheduled sync reads nothing, so HR for a session inside Garmin's 7-day lag only arrives when the operator presses a manual sync, and a 7-day manual sync can miss a lag longer than 7 days. The proposal reported to the operator: init the Health Connect client at the top of `fetchAllData`; make an all-streams-failed fetch return `ok:false` (keep the telemetry POST) so WorkManager retries; then `days: 30` at `backgroundSync.js:52`. Code can build it once it has push access to the companion repo (`add_repo` with push) or the operator applies it.

**Operator actions owed.** (1) After the next sync on the new deploy, confirm an overlapping pair of syncs both return 200 (the live proof for #371; none had reached it). (2) Which build the phone runs: `SELECT git_sha, max(synced_at) FROM health_connect_sync_events GROUP BY git_sha ORDER BY 2 DESC LIMIT 3;` (unrun; the P1 path was read at `0c2f982`). (3) Until P1 lands, a periodic manual 30-day sync keeps sessions inside the lag window from going stale. (4) The backfill report, `--apply`, and `refresh_load` from the earlier close-outs (not known to have run). (5) Q205 at the next Polar re-auth, with `sports:read` requested then (#368). (6) A maximal-effort HRmax test (Q199), unscheduled.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 115 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This session since the last close-out: closed Q207; reopened Q159; new Q208 (overlapping syncs: the sibling race paths and a per-user lock).

**What was NOT touched (named so absence does not read as finished).**
- **The phone code.** Nothing in `health-connect-app` changed. The init failure, the silent `ok:true`, and the 7-day window are all still live.
- **The sibling races.** `_ingest_exercise_sessions` and the per-day `HealthConnectSync` upsert have the same read-then-add shape (Q208). An overlap could still 500 there.
- **Garmin direct.** I offered to file "a Garmin activity-scoped direct pull" as an OPEN question and the operator has not answered. Q207's closure weakens the case (HC delivers, late), and nothing is filed. It is not decided.
- **The marker exposure (#367, Q206)** is filed, ruled and unstarted. The Q202 brief is not written.
- **The input-layer design and any arbitration change.** Q201 waits on a chat design with no repo artifact. #367's constraint stands: HR recorded over a gym session must still deposit.
- **Q203 and Q189** (an expected-but-absent signal, an RPE floor) did not move, though Q159's reopening names the same gap: a session inside the lag window reads as zero load, silently.
- **Know / the plan:** plan-conformance adjudication (Q197) is still a chat proposal; Q27 and the Rule 1 vote counter are unchanged.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Loop / Fitness UI:** no frontend work.
- **Pattern to say out loud:** another session on load and ingest plumbing, now reaching across two repos and a prod outage. The plan-versus-log judgement (Q197) and the Walk-in surfaces the plumbing feeds have gone untouched for several sessions. The queue after P1 is rulings (Q159, Q201-Q203, Q208, the input-layer design), not more instrument work.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC sync reliability (#369-#371, OWED): **See** (a session's HR and load are not silently zero) and **Loop** (the scheduled sync is how the app learns anything).
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**. Q159's reopening is a live gap in it.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
