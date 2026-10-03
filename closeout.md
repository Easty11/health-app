# Close-out — Polar sport ids mapped from Polar's own list (#366); the H10-vs-Hevy facts filed (Q205, Q206); Q204 closed

## Real commits this session

Range: `b447ed4` (master when the session opened; the merge of PR #299) to this close-out. Two concern-named branches, approved by the operator (3 Oct 2026) in place of the harness-assigned `claude/vigilant-wozniak-ompbx9`:

- `polar-sport-map`: `f4ef81e fix(polar): SPORT_NAMES is the Polar Flow sport-id list; add report-first relabel script`. Merged by Code on green as PR #300, merge commit `7087026`; the remote ref was already gone when I went to delete it after the merge, and the local branch is deleted.
- `gov-polar-sport-map`: one `gov(polar-sport-map): ...` commit carrying DECISIONS #366, OPEN_QUESTIONS (Q204 closed, a Q201 update, new Q205 and Q206), the CLAUDE.md `load_window` note fix and Recent-landings pointer, one ROADMAP NOW row plus an edit to the Source-hierarchy row, the BRANCHES rows, and this file. Its hash is on the branch; a file cannot name its own commit. The brief asked for a single gov commit at close-out, so the close-out artifacts ride in it.

`claude/vigilant-wozniak-ompbx9` (the harness name) was never committed to: local and remote both sit at `b447ed4` and `git cherry origin/master` is empty. It is rowed in `BRANCHES.md` as DONE with no work, and the remote ref was left in place because the harness created it.

No schema migration, no prod data write, no `refresh_load` run, no backfill run.

## Pending-queue reconciliation

No `PENDING` items were carried in: the input was a chat brief and its rulings, not a `;cc` queue. Where each landed:

- **Ruling 3 (full-table rename, ids 1-142, gaps NULL, names verbatim, no per-row exceptions):** PR #300 (`import_polar.py`), recorded as DECISIONS #366. Both transports use the one table (the v4 parser calls `_parse_session`).
- **Ruling 1 (backfill covers `polar_v4` and `polar_flow_export`):** `scripts/polar_sport_backfill.py` in PR #300. Report by default, `--apply` the single write. Not run.
- **Ruling 4 (tie-break dropped, `_win_key` untouched, record as a Q201 note):** the Q201 update. Nothing was built for it.
- **Q204 closed with the brief's evidence:** moved below `## CLOSED` as `DONE → #366`.
- **New OQs:** Q205 (verify the table against `/v4/data/sports/list`) and Q206 (the S7 findings, framed as input to the input-layer design).
- **CLAUDE.md `load_window` note:** corrected; the migration `1341a2cf6938` and the column rename were verified in the migration file before the edit. This closes the "found, not fixed" item the previous close-out carried.
- **Decision added beyond the brief's list:** DECISIONS #366. Q204 needs a `DONE → #N`, and the rename is a data-meaning default, so it is recorded as a decision; its content is only what the operator ruled.
- **Flagged for Luke (a tension in the rulings, not resolved by Code):** ruling 3 says verify against `/v4/data/sports/list` at the next re-auth and not to add `sports:read`. That endpoint needs the scope, and `connectors/polar.py:39` does not request it. Q205 records this; the check can run only if the scope is requested at a re-auth on purpose.
- **Source caveat, in #366 and Q205:** the id list is a secondary copy (Polar Flow's sports settings page as reproduced on the bipolar wiki). `polar.com` is egress-blocked from the build environment, so Polar's own page was not read. Two live datapoints (id 4 "Jogging", id 55 "Cross-trainer") match it.
- **Test-guard change in PR #300:** `test_no_second_list_anywhere` tripped on the new table (it quotes Yoga, Pilates and Stretching as names), so it gained a reasoned `NAME_TABLES` allow-list entry with a stale-entry check; the read-door drift guard registers the new script.
- **Operator-reported, not read by Code:** the prod facts for rows 93 and 95, the load row (source_ref 95, load 81.85), the grouped `sport_id` result, the slot query (phase 8 declares `["Pilates"]` only) and `user_hrmax` (173, observed, H10, 2026-03-01). All are recorded as the operator's statement.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One new row from this session: **Polar sport-id relabel, and the H10-vs-Hevy facts (#366, Q205, Q206), OWED (operator).** The Source-hierarchy row was rewritten: the live case is read, Q204 is closed, and Q201-Q203 are Luke's to rule (Q201 with the pending input-layer design). Unchanged by this session and still in NOW: HC zones (#364) deploy/seed/verify steps, injury clearance via the #340 sweep, aerobic ingest automated check (#353), session fidelity G6.

**State.** PR #300 is merged. The gov branch is a governance-only change (no code, no migration), so it self-merges on green under CLAUDE.md § Merge disposition. Numbers #366, Q205 and Q206 were resolved at master max #365 / Q204 (`7087026`); re-read master's max and re-resolve if it advances before the merge.

**Single clearest next action.** The operator runs the backfill report from `backend/`: `railway run python -m scripts.polar_sport_backfill`. Read the rows marked `[class flips]` (they change what the psychological window and the CBT-I training-end read), then `--apply`, then `railway run python -m scripts.refresh_load --user 1`. The new map labels only NEW rows until the backfill runs, so new and old sessions carry different names for the same id in the meantime.

**Operator actions owed.** (1) Backfill report, then `--apply`, then `refresh_load` (above). (2) The Q206 queries: (a) Polar rows against Hevy overlap (detail and counts), (c) the Hevy payload key inventory, and the gap-distribution query. All four were syntax-checked with a Postgres parser and none was run. (3) Q205 at the next Polar re-auth.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 114 OPEN, 5 OWED (Q78, Q176, Q178, Q181, Q205). New this session: Q205 (OWED), Q206 (OPEN). Closed this session: Q204. Q201 got an update and stays OPEN with the dedup live case read.

**What was NOT touched (named so absence does not read as finished).**
- **The hierarchy tie-break and any arbitration change.** Dropped by ruling and not built; `_win_key`, the source ranks and the Edwards formula are unchanged. The source-agnostic input-layer design that replaces it is a pending chat design with no repo artifact yet.
- **Q202, Q203 and Q189** (an RPE floor, an expected-but-absent signal) have not moved, and neither has Q198 (re-zoning Polar from raw HR) or Q124 (Catapult SPT3 ingest). Q206 adds facts to the same cluster and decides nothing.
- **Know / the plan:** plan-conformance adjudication (Q197) is still a chat proposal; Q27 and the Rule 1 vote counter are unchanged.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move. The backfill can change the CBT-I training-end read for rows that cross the non-training line, but that happens only when the operator applies it.
- **Loop / Fitness UI:** no frontend work.
- **Pattern to say out loud:** this is another session on load and ingest plumbing (a mapping table, a relabel script, the inventory of what HR the app keeps). The plan-versus-log judgement (Q197) and the Walk-in surfaces the plumbing feeds have now gone untouched for several sessions. The queue after the backfill is rulings (Q201-Q203, the input-layer design), not more instrument work.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Polar sport-id relabel and the H10-vs-Hevy facts (#366, OWED): **Know** (a session carries the name Polar shows) and **See** (a gym-session HR trace is visible as one).
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
