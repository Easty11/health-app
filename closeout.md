# Close-out — three phase-machinery questions and the trigger-drop question are filed (Q211-Q214); the HC phone fix (#370) is device-confirmed (#377); the 4-5 Oct evidence and the corrections to my own first notes are recorded

## Real commits this session

Session `phase-open-path-and-carried-items` (the `phase-form-save-order` session had closed out and merged at `21839a4`). Range: `21839a4` (master at open) to this close-out. Fresh-clone settings verified set at open (`core.hooksPath` = `.githooks`, local `land` alias). Maxima at open: decisions 376, questions 210. Maxima now: decisions 377 (#377, a confirmation), questions 214.

Five PRs, each self-merged on green (guard, vitest, pytest read as success on the pinned head) with a merge commit and the branch deleted:
- **#318** `gov/phase-open-path-and-carried-items` (merge `9fc2973`): Q211, Q212, Q213, two dated notes on Q159, ROADMAP rows 37-39 and two LATER rows, the CLAUDE.md operator-scripts note. Governance only.
- **#319** `fix/phase-test-review-date-not-hardcoded`: `276ca7a test(phase): give the HTTP open test a review date relative to today` (merge `0c04611`). Tests only, not in the brief. `test_http_open_get_history_and_close` asserted `review_due is False` against the shared helper's fixed `review_on` of 2026-10-05, which became today at 00:00Z on 5 Oct, so the backend check went red on #318 and would have on every PR. Reproduced locally, fixed in the test only; a review date of yesterday fails it.
- **#320** `docs/operator-script-container-recipe`: `998d63c docs(scripts): point operator-script docstrings at the container recipe, not railway run` (merge `27e601e`). Docstrings only; the four files compile and their two test files pass (22).
- **#321** `gov/hc-trigger-and-phase-question-corrections` (merge `461dfff`): Q214, the Q159 and ROADMAP row 37 corrections, the Q211 and Q212 additions, ROADMAP rows 36 and 56, the BRANCHES rows, the CLAUDE.md pointer, a whole-session `closeout.md`. Governance only.
- **This PR** `gov/hc-sync-device-confirmation`: one governance commit (the hash is on the branch; a file cannot name its own commit): DECISIONS #377, the Q159 and ROADMAP row 37 text it supersedes, the BRANCHES rows, the CLAUDE.md pointer, this file.

**Disclosure: three `gov(...)` commits this session** (#318, #321 and this one). CLAUDE.md allows one. The second answered the duplicate session's findings and the third records the operator's artifact; each arrived after the previous landed. Each was amended on my own unmerged branch to keep one commit per PR. Stated here, not hidden.

- Migration: none. No prod write. Code has no database access; every prod fact is read by Code from Railway or marked operator-owed. The companion repo (`health-connect-app`) was read-only, cloned shallow for this round.
- Deploys: #319 backend `8c6542a2` SUCCESS. The deploys for #318, #320 and this PR were not re-read; all three touch only governance files or docstrings, so nothing served changes.

## Pending-queue reconciliation

**Round 1, the 5 Oct brief** (landed in #318; see the Q211-Q213 and Q159 entries): the phase-history fix was already #314 (deployed; the ledger read and the card check are owed); Q211 filed; the "recovery vehicles" source reported and filed as Q212; the scheduled-sync evidence recorded on Q159 and ROADMAP row 37 (it does not confirm #370); the carried items located or added (Q213, the datasheets LATER row with no scope stated); the PENDING notes landed (CLAUDE.md recipe, the first live self-evaluation read).

**Round 2, the duplicate session's findings.** Each verified against the code before landing.
1. **`client.trigger` — the real gap is server-side. Filed as Q214.** The phone stamps it (companion `syncRunner.js:93`, `backgroundSync.js:57`, `SyncScreen.js:177`; its comment calls persisting it "the owed health-app follow-up (OPEN_QUESTIONS)", and the companion holds it as its Q23). The server accepts it (`ClientInfo` `extra="allow"`) and drops it (`routers/health_connect.py:1152-1159`; no column in `models.py:393-414`). A column is a migration: HOLD. **My round-1 text was wrong on this:** I wrote that the server "records no trigger" and suggested a label "for the P1 brief". Corrected on Q159 and ROADMAP row 37.
2. **`railway run` in the stores and docstrings — fixed.** ROADMAP rows 36 and 56 and the four docstrings (set_hrmax, polar_sport_backfill, garmin_sync, arbitration_flip_report) now give the container recipe; `verify_series_integrity.py` already documented why. **Stray, not changed:** its runtime message at `:56` still says "run via `railway run`".
3. **Q212 — added.** One `probe_posture` value drives three behaviours (budget 0 and fortify at `selection.py:574-581`, probe block withheld at `:733-737`, the recovery-first re-rank at `:646-650`), and the re-rank fires on `probe_suppressed` alone. Options to separate them are on Q212. **Verified, not copied:** a third posture value is a migration, because `training_phases` has a database `CHECK` on `probe_posture IN ('suppressed','held')` (`models.py:1107`).
4. **#370 "device confirmation" — DONE → #377.** The operator supplied the artifact after #321 landed: sync events 66-68 (build `52f9d4d`, `period_days` 30, no error on any stream, heart rate 29.4-29.6k received, `hrv` 0 as expected), the GitHub compare `ahead`, and the app's "Last background sync 04:09:31" line. Verified by Code against the Railway HTTP log (the three row times fall inside their requests; a fourth POST at 00:09:50Z), a clone of the companion (`e3e2333` is an ancestor of `52f9d4d`; the stamp is written only by a background run). The acceptance criterion is amended to "a build containing `e3e2333`" (operator). **One correction of mine:** the first reading said no POST followed the 18:09Z one; the 00:09Z POST existed and the log had not caught up. **#371's overlap proof stays owed.**
5. **`PhaseCard.jsx:15-17` — added to Q211.** The direct path is kept "until the 8-step flow has completed one real transition in prod", to be removed once confirmed. By the operator's 4 Oct report that condition is met, so option (d) is the removal the code already plans. Not a ruling.

- **Not landed:** the ledger read, the served-bundle probe, the phase posture check; the duplicate Hevy folders; whether the phase was renamed `aerobic base` before Mon 5 Oct.

Provisional until merged: everything in this PR.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Rows 36 and 56 give the container recipe; row 37 now says P1 is DONE → #377 and carries Q214; rows 38 and 39 are as #318 left them. LATER holds the HR input layer (Q213), the datasheets brief (no scope stated) and the `review_by: 2026-10-15` test fixtures watch row.

**State.** This PR self-merges on green. Q211-Q214 are OPEN with Luke. #377 records a confirmation, not a ruling.

**Single clearest next action.** The operator runs the ledger query and reads `probe_posture` on the open `aerobic base` row first: if it is `suppressed` and that was not intended, re-run Review / change and set `held` (a same-day correction is allowed, #317). Until then the coach output is recovery-first with the probe off.

**Operator actions owed.** (1) The ledger query (`SELECT id, label, probe_posture, entered_on, closed_on, close_reason, (microcycle IS NOT NULL) AS has_microcycle, source FROM training_phases WHERE user_id = 1 ORDER BY entered_on, id;`, `PGCLIENTENCODING=UTF8` set first) and the Phase card's history check. (2) The served-bundle probe (the line in ROADMAP row 39). (3) The duplicate Aerobic Base Phase folders in the Hevy app. (4) Still open from earlier: the capture-rate query (Q202); the overlapping-sync live proof for #371; the Polar backfill report, `--apply` and `refresh_load` (now from the container); Q205 at the next Polar re-auth; the `concurrent_strength` marker build (Q206).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 119 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This session: Q211, Q212, Q213, Q214 opened; none closed or moved.

**What was NOT touched (named so absence does not read as finished).**
- **Any fix for Q211, Q212 or Q214.** All three are filed with options; Q214's column is a migration and a hold.
- **The companion repo.** Read only; the `client.trigger` stamping and the P1 build are its, and landed.
- **The HR input layer (Q213) and the instrument datasheets brief:** recorded, not drafted; the datasheets scope was not stated.
- **The next date-bomb candidates:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` without pinning today, and `typed_entries.py:110` tags `review due` once it passes. Whether any assertion flips on the 15th was not checked.
- **`verify_series_integrity.py:56`:** the runtime `railway run` message.
- **The stale-looking amber warning** on a Garmin or Samsung `load_window` slot ("deposits no load until Health Connect stage 2"): left, as before.
- **The sRPE floor, the Garmin in-activity HR read (Q159), the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206):** unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** a fourth session in a row on the plan's input form and the sync plumbing, and this round was mostly correcting my own first notes against the companion's stores. Two of the three corrections (the trigger, the P1 state) came from a store this repo does not hold. Walk in is where it was.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form: save order, placements and slot pickers (#375, #376; Q211, Q212, OWED): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED, first live read reported 4 Oct): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, Q159, Q202, Q208, Q214, OWED; #370 DONE, #371's overlap proof owed): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **See** if built, off the v1 path.
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
