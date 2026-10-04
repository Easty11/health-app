# Close-out — the Garmin per-activity self-evaluation read is built, read-only and insert-only inside the Garmin sweep (#372); migration held in PR #309; the srpe-floor rulings recorded (#373, #374); Q209 closed

## Real commits this session

Range: `dc5aa90` (master when the session opened) to this close-out. Two concern-named branches, on the operator's brief, in place of the harness-assigned `claude/peaceful-lamport-aqc7xi` (never used; local deleted, rowed in `BRANCHES.md`).

On `feat/garmin-selfeval-read` (PR #309, ready for review, HELD for the migration; not merged):
- `15ec3d5 feat(garmin): garmin_activity_selfevals table (Q209 path a, migration; HELD)`. `models.py`, migration `c5e7a9b1d3f2`, `SCHEMA.md` §042 (same commit, per the SCHEMA rule), `tests/test_garmin_selfeval_schema.py` (the model-versus-migration parity test; a mutated FK was caught).
- `dcee435 feat(garmin): read per-activity self-evaluation inside the Garmin sweep (Q209 path a)`. `garmin_selfeval.py`, `scripts/garmin_sync.py` (the step and the summary counts), `load_sweep.py` (the nightly brief), `mcp_server.py` and `aerobic_format.py` (the readout), `tests/test_garmin_selfeval.py`.

On `gov/garmin-selfeval-read` (governance only, no code, no schema):
- One `gov(garmin-selfeval-read): ...` commit: DECISIONS #372-#374; Q209 closed and moved below `## CLOSED`; Q159, Q189 and Q202 notes; one ROADMAP NOW row; the BRANCHES rows; the CLAUDE.md pointer; this file. Its hash is on the branch; a file cannot name its own commit. It is the only gov commit of the session, and it self-merges on green under § Merge disposition.

- Migration: yes, `c5e7a9b1d3f2`, held for the operator (hold (a)). No prod data write. Code has no Railway or Garmin access this session beyond the repo; every prod fact below is operator-reported.
- Verification run by Code: 64 new tests; 17 mutations, each failing at least one test (two were first reported "caught" in error: a stale `.pyc` from a same-size, same-second mutate-and-restore. Re-run with bytecode caching off, two survived, and two tests were added); full backend suite 2,788 passed, 1 skipped, 1 failed. The one failure, `test_context_builder_output_unchanged_pre_post_refactor`, needs `git show 3360ed5` and fails identically on a pristine tree in this shallow clone.
- Deploys: none. Nothing is live.

## Pending-queue reconciliation

The operator's brief and its follow-up carried these items. Each landed, or is named as not landed.

1. **VERIFY (halt on mismatch): #361 and the no-refresh seam, the probe's GET pattern and the pin, the HC rows' package and interval** — verified and reported in chat before building (no mismatch). Not a commit.
2. **S1 store (migration, held)** — landed in `15ec3d5`, with the three forks as ratified: marker rows for unrated sightings, a DB-only relink pass inserting a linked row, FK `ON DELETE SET NULL`. HELD for release.
3. **S2 read** — landed in `dcee435`. Bounded list (14 days, one day before the last captured start), one detail GET per new activity, unrated re-check about daily for 7 days, then stop.
4. **S3 link** — landed in `dcee435`, through the aerobic read-door (a drift-guard test forced that; no allow-list entry was added).
5. **S4 wire-in: overridden by the operator to run inside `sweep_garmin_hrv`, after its token refresh** — landed in `dcee435`. The placement was clean, so no halt. **One part of the override could not be applied as written:** "report `skipped_needs_refresh` ... so a page-open run that lands on a stale token is visible". The read does not run on a page open (neither `POST /load/refresh` nor the Garmin card's refresh route calls the sweep), so that case does not exist. `skipped_needs_refresh` is counted in the sweep summary and the nightly brief for the sweep's own case. Recorded in #372; say so if you wanted the read on a page-open path too.
6. **S5 readout** — landed in `dcee435`. `get_training_sessions` shows RPE and feel on a linked session; a value on a lost twin moves to the canonical row; the shared renderer is unchanged. No UI.
7. **S6 tests** — landed (above).
8. **S7 gov (single commit)** — landed in the gov commit: the decision superseding the 1 Oct position (#372); Q209 closed (`DONE → #372`; the brief said "RESOLVED", the repo's vocabulary is `DONE → #N`); the Q159 note (the HR read stays separate); the Q202 note (a floor input now exists for watch sessions); srpe-floor ruling 1 (#373) and ruling 2 (#374). A Q189 note was added so Q209's "path (b) stays a note on Q189" is true.
9. **Delete the stale local harness branch** — done (`claude/peaceful-lamport-aqc7xi`, local; it was identical to master). The remote branch is untouched and rowed.
10. **Gates: report VERIFY and the S1 schema in chat before building; migration held for explicit release** — both honoured.
- **Not landed:** the operator's capture-rate query (Q202) result is still not pasted; the probe's own run is recorded from the brief's anchor (operator-reported, not read by Code).
- **Flags for the operator.** (a) A rated activity is read once; a later revision of a rated value on Garmin is NOT captured (#372 says so). (b) Garmin's list payload names (`startTimeGMT`, `duration`) come from the library's typed model, not a captured payload; the first live run is the proof.

Provisional until merged: everything in the gov commit. The feature is provisional until PR #309 is released and merged.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One new row: **Garmin self-evaluation read — release the migration, then the first live run** (OWED, operator). No other row changed.

**State.** PR #309 (the migration and the feature) is open and HELD. The gov PR self-merges on green; #372-#374 were resolved at master max #371 (`dc5aa90`), so re-read master's max and re-resolve if it advances before the merge.

**Single clearest next action.** The operator says "release" on PR #309. Then Code lands it end-to-end (FEEDBACK section 1: resolve, guard, merge with a merge commit, delete the branch, verify the deploy per #116 and #121), and the operator does the first live run from PowerShell: `railway ssh --service health-app-backend`, then `cd /app`, then `/opt/venv/bin/python -m scripts.garmin_sync --user-id 1`, and reads `garmin_activity_selfevals` via `railway connect` (the query is in the ROADMAP row). Activity 24564069469 should read 4.0 and 25.

**Operator actions owed.** (1) Release PR #309, then the first live run above. (2) Still open from earlier close-outs: the capture-rate query (Q202); the overlapping-sync live proof for #371; which build the phone runs; periodic manual 30-day syncs until P1 (#370) lands; the Polar backfill report, `--apply` and `refresh_load`; Q205 at the next Polar re-auth. (3) Optional: delete the remote `claude/peaceful-lamport-aqc7xi`.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 115 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This session: Q209 closed (`DONE → #372`) and moved below `## CLOSED`; Q159, Q189 and Q202 carry notes.

**What was NOT touched (named so absence does not read as finished).**
- **The sRPE floor itself.** Nothing built: no kappa, no floor event, no rollup change (#374 is a ruling for when it is). It still cannot be fitted (n = 2 when read) and the new capture is not live. The next floor step is data, not code.
- **The phone code and P1 (#370).** Nothing in `health-connect-app` changed; the scheduled sync still reads nothing until P1 lands. That is the larger gap behind the missing in-activity HR, and it stood still again.
- **The in-activity HR read from Garmin (Q159).** Not built; the self-evaluation read was deliberately kept to self-evaluation. It is still only a candidate.
- **Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208).** Unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Loop / Fitness UI:** no frontend work; the new readout is MCP-only.
- **Pattern to say out loud:** a fourth session in a row on load and ingest plumbing; this one shipped a capture path rather than a question, which is the first step toward a feature, but nothing in Walk in or the plan-versus-log judgement has moved for several sessions. After the release and the live run, the next Code session should not be more load work unless a ruling or an operator reading lands.
- **A candidate FEEDBACK rule, not minted:** a mutation check that rewrites a file and restores it within one second, to the same byte length, can leave a stale `.pyc` that makes a mutant read as caught or surviving wrongly. Run mutation checks with `PYTHONDONTWRITEBYTECODE=1` and clear `__pycache__` first. It cost this session two false "caught" results.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Garmin self-evaluation read (#372, OWED, new): **Know** (a session carries the effort the athlete rated) and **Loop** (the rating enters at the watch).
- HC sync reliability (#369-#371, Q159, Q202, Q208, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**. Q159's reopening is a live gap in it.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
