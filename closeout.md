# Close-out — the sRPE-floor brief verified and halted: #326 stands, nothing built, per-session sRPE capture filed (Q209); the Garmin self-evaluation probe landed (PR #307)

## Real commits this session

Range: `53f5925` (master when the session opened) to this close-out. Two concern-named branches, on the operator's 4 Oct ruling, in place of the harness-assigned `claude/stoic-goodall-t1qyw5` (never used; rowed in `BRANCHES.md`).

- `28b5af0 feat(garmin): read-only activity self-evaluation probe (Q209)`. PR #307, merge `aa9eb8e` (merge commit, self-merged on green: guard, vitest and pytest all passed on `28b5af0`). `scripts/garmin_selfeval_probe.py`, `tests/test_garmin_selfeval_probe.py`, its own `BRANCHES.md` row. The remote branch was auto-deleted on merge.
- This close-out: one `gov(srpe-floor): ...` commit on `gov/srpe-floor-q202`: new Q209; the Q202 findings, rulings and S1 result; a Q189 note and a Q159 note; the ROADMAP row 37 item (3) edit; the BRANCHES rows; the CLAUDE.md pointer; and this file. Its hash is on the branch; a file cannot name its own commit. It is the only gov commit of the session.
- No migration. No prod data write. No DECISIONS_LOG entry: the operator listed none, so the rulings below are recorded on Q202 and the fork is a note on Q209 and Q159. Nothing was run against prod from this session: the S1 result (n = 2) is the operator's own query read. Code did read the Railway deploy list (read-only).
- Deploy of `aa9eb8e`: `health-app-frontend` reached SUCCESS; `health-app-backend` deployment `56d3d547` was still DEPLOYING at the last read (01:41:48Z, an unrefreshed `updatedAt`). The probe is not live until the backend reaches SUCCESS (#116, #121), so that is unconfirmed here.

## Pending-queue reconciliation

The operator's 4 Oct paste carried seven rulings and a gov list. Each landed, or is named as not landed.

1. **#326 stands; Case B dropped; Q169's rejection not superseded** — landed as a Q202 note (this close-out's gov commit). No DECISIONS entry (none requested).
2. **Rollup wiring: option (a) when the floor is built; nothing now** — landed as a Q202 note. Nothing built.
3. **No migration this session** — held. None written.
4. **S1: n = 2 pair-days (2026-06-17, 2026-09-09); report and gov only** — landed in Q202 (operator-reported). Nothing built.
5. **Concern-named branches** — done: `feat/garmin-selfeval-probe` (merged) and `gov/srpe-floor-q202`; the harness branch is rowed as unused.
6. **Garmin probe approved** — landed: PR #307, merge `aa9eb8e`. The operator's run is OWED.
7. **The 1 Oct "no client built" position reopened, scoped to a read-only activity read; a note, not a decision** — landed as notes on Q209 and Q159.
- **Gov list:** Q202 notes (landed); new Q209 as drafted, with the operator context and the probe status (landed); Q189 Case A lean (landed); Q159 lag-bypass note (landed).
- **Not landed:** the operator's count query result (days with a `session_rpe`). It has not been pasted. The query is in Q202 (read-only, one statement, parse-checked, not executed) and the result is OWED.
- **One flag for the operator:** rulings 1 and 2 gate future code (a dropped case, a rollup shape) but have no DECISIONS entry. If they should be decisions, say so and a later session records them. Q202 and Q189 stay OPEN, so the brief's "resolved by the landing decision" step did not happen: there was no landing.

Provisional until merged: everything in the gov commit.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Unchanged except row 37 (HC sync reliability), item (3): the "Q202 brief to follow" sentence now records the halt. No new NOW lane. The floor itself (the brief's A and C) is not in NOW: it has no inputs until Q209 is ruled.

**State.** The gov PR is governance-only (no code, no migration): it self-merges on green under CLAUDE.md § Merge disposition. Q209 was resolved at master max Q208 (`aa9eb8e`); re-read master's max and re-resolve if it advances before the merge. No decision number was minted.

**Single clearest next action.** The operator runs the probe on a RATED activity (the only run that can answer). In order: (1) rate one recent activity in Garmin Connect (perceived effort and feel) and note its activity id; (2) open the app's Garmin card (it refreshes and saves the token, #361); (3) confirm the backend deploy is live: `railway deployment list --service health-app-backend` (PowerShell), the top row SUCCESS for `aa9eb8e` or later; (4) `railway ssh --service health-app-backend`, then in the container `cd /app` and `/opt/venv/bin/python -m scripts.garmin_selfeval_probe --user-id 1 --activity-id <id>`; (5) paste the output. It prints only keys matching `rpe|feel|eval` as `path = value`, plus an activity id, date and type. A hit on the known rating gives the key and the scale; a miss on an unrated activity proves nothing. An expiring token exits 2 with the workaround; nothing is sent in that case.

**Operator actions owed.** (1) The probe run above. (2) The capture-rate query (Q202), one statement, from `railway connect health-app-DB` in PowerShell; paste the result. (3) Rule whether the Garmin activity read is built, after the probe (Q209, with Q159). (4) From the earlier close-outs, still open: the overlapping-sync live proof for #371; which build the phone runs; periodic manual 30-day syncs until P1 (#370) lands; the Polar backfill report, `--apply` and `refresh_load`; Q205 at the next Polar re-auth with `sports:read`; a maximal-effort HRmax test (Q199).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 116 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This session: new Q209; Q202, Q189 and Q159 carry notes; none closed or moved.

**What was NOT touched (named so absence does not read as finished).**
- **The sRPE floor itself.** Nothing built: no kappa, no floor event, no marker, no rollup change. It cannot be fitted (n = 2) and has no capture surface. The queue is a ruling (Q209), not more floor work.
- **The phone code and P1 (#370).** Nothing in `health-connect-app` changed; the scheduled sync still reads nothing until P1 lands. This is the larger gap behind the missing in-activity HR, and it stood still.
- **The sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the input-layer design.** Unmoved.
- **Garmin direct, beyond the probe.** No client, no HR pull, no storage; the fork is reopened as a note only.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Loop / Fitness UI:** no frontend work.
- **Pattern to say out loud:** a third session in a row on load and ingest plumbing, and this one ended with a probe and a question rather than a feature. The Walk-in surfaces and the plan-versus-log judgement have gone untouched for several sessions. The next load-side step is gated on a ruling and an operator action, so the next Code session should not be more load work unless one of those lands.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC sync reliability (#369-#371, Q159, Q202, Q208, OWED): **See** (a session's HR and load are not silently zero) and **Loop** (the scheduled sync is how the app learns anything). Q209 now sits behind it.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**. Q159's reopening is a live gap in it.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
