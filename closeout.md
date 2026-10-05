# Close-out — the direct-open path is ruled out (#378, build not scheduled), Q212 is deferred to the aerobic base review, the HC phone fix is device-confirmed (#377), and the in-activity HR read is owed from about 9 Oct

## Real commits this session

Session `phase-open-path-and-carried-items` (the `phase-form-save-order` session had closed out and merged at `21839a4`). Range: `21839a4` (master at open) to this close-out. Fresh-clone settings verified set at open (`core.hooksPath` = `.githooks`, local `land` alias). Maxima at open: decisions 376, questions 210. Maxima now: decisions 378 (#377, #378), questions 214.

Six PRs, each self-merged on green (guard, vitest, pytest read as success on the pinned head) with a merge commit and the branch deleted:
- **#318** `gov/phase-open-path-and-carried-items` (merge `9fc2973`): Q211-Q213, the first Q159 notes, ROADMAP rows 37-39, the CLAUDE.md operator-scripts note. Governance only.
- **#319** `fix/phase-test-review-date-not-hardcoded`: `276ca7a test(phase): give the HTTP open test a review date relative to today` (merge `0c04611`). Tests only, not in the brief: `test_http_open_get_history_and_close` asserted against the shared helper's fixed `review_on` of 2026-10-05, which became today at 00:00Z on 5 Oct and turned the backend check red for every PR.
- **#320** `docs/operator-script-container-recipe`: `998d63c docs(scripts): point operator-script docstrings at the container recipe, not railway run` (merge `27e601e`). Docstrings only.
- **#321** `gov/hc-trigger-and-phase-question-corrections` (merge `461dfff`): Q214 (the phone stamps `client.trigger`, the server drops it), the corrections to my first notes, the Q211 and Q212 additions.
- **#322** `gov/hc-sync-device-confirmation` (merge `a0c9376`): DECISIONS #377, the #370 device confirmation.
- **This PR** `gov/q211-ruled-q212-deferred`: one governance commit (the hash is on the branch; a file cannot name its own commit): DECISIONS #378, Q211 closed, Q212 evidence and deferral, the owed Q159 read, ROADMAP rows 37 and 39 and a NEXT block, the BRANCHES rows, the CLAUDE.md pointer, this file.

**Disclosure: four `gov(...)` commits this session** (#318, #321, #322 and this one). CLAUDE.md allows one. Each answered input that arrived after the previous landed (the duplicate session's findings, then the operator's artifact, then the operator's rulings); the operator asked for this last batch as one commit, and it is one. Each was amended on my own unmerged branch to keep one commit per PR. Stated here, not hidden.

- Migration: none. No prod write. Code has no database access; every prod fact is read by Code from Railway or marked operator-reported or operator-owed.
- Deploys: #319 backend `8c6542a2` SUCCESS. The deploys for the governance and docstring merges were not re-read; they alter nothing served.

## Pending-queue reconciliation

This round (the operator's 5 Oct message clearing my "still yours" list and ruling).
1. **`probe_posture` `suppressed` on `aerobic base` is intended** (operator: to stop probes while run, sprint and VO2 all start). No change. Recorded on Q212 as evidence for separating the three behaviours: the operator wants probe-off without the recovery-first ranking.
2. **Served-bundle probe — done by the operator from chat:** the live bundle contains "Kept as on file", so #313 is live. Operator-reported; Code's proxy still blocks the host. Only #313's string was probed; #314 and #315 were not separately.
3. **Duplicate Aerobic Base Phase folders — deleted by the operator** in the Hevy app.
4. **Instrument datasheets brief — scope to follow from the operator;** the LATER row is left as it is.
5. **Q211 ruled: option (d)** — remove the direct-open path; Review / change is the only phase-entry route. Recorded as **#378**; Q211 closed. **Build not scheduled** (ROADMAP NEXT, UNSTARTED). Left for the build brief: the backend route (its only non-test caller in the tree is `PhaseForm.jsx:98`; MCP and chat only read the phase), the direct close path (the ruling names open only), and whether the wizard can express a no-microcycle or review-date-only phase.
6. **Q212 deferred** to the aerobic base review (16 Nov 2026): `suppressed` stays and the recovery-first ranking is accepted for this phase. Q212 is now OWED (loop-close: that review), not OPEN. No DECISIONS entry: a deferral resolves nothing.
7. **Q159 read owed — recorded with its query** (parser-checked with `pglast` 8.5, not run). **One challenge, recorded on Q159:** the read as framed is probably premature. Garmin writes in-activity HR about 7 days after the session (#369), so the 1 Oct run's late write is expected about 8 Oct; a read on 5 Oct should show passive samples only. The receipt counts in rows 66-68 cannot answer it either (the window slides: 29,475, then 29,357, then 29,569). Read it on or after 9 Oct. A test that can run now: sessions 69, 85 and 92 (older than 7 days, no in-activity HR in Q207's first read).
- **Not reported, so still owed:** the Phase card's history check (the card should list the ledger rows). The operator closed the posture question; the history render was not mentioned.

Earlier rounds, as recorded: the phase-history fix is #314 (deployed); Q211-Q214 filed; #370 confirmed on a device (#377, sync events 66-68); #371's overlap proof stays owed; the carried items located or added; the operator-scripts recipe landed with its docstrings (#320).

Provisional until merged: everything in this PR.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Row 39 rewritten: the phase-change form lane is closed except the history check; the posture, bundle probe and folders are closed by the operator; Q211 and Q212 are ruled. Row 37 carries the Q159 read. NEXT carries the #378 build, UNSTARTED. LATER holds the HR input layer (Q213), the datasheets brief (scope to follow) and the `review_by` fixtures watch row.

**State.** This PR self-merges on green. #378 resolved at master max #377. Open: Q212 OWED to the 16 Nov review; Q213, Q214 OPEN with Luke.

**Single clearest next action.** Nothing blocks. When the operator schedules it, the #378 build starts with a brief that reads the three open points first. Until then the next dated item is the Q159 in-activity HR read on or after 9 Oct.

**Operator actions owed.** (1) The Q159 read (query on Q159) on or after 9 Oct, and now the 69 / 85 / 92 variant. (2) The Phase card's history check. (3) #371's overlap proof: a manual sync during a scheduled one, both 200. (4) The datasheets brief's scope. (5) Still open from earlier: the capture-rate query (Q202); the Polar backfill report, `--apply` and `refresh_load` (from the container); Q205 at the next Polar re-auth; the `concurrent_strength` marker build (Q206).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 117 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This round: Q211 closed (`DONE → #378`); Q212 moved from OPEN to OWED. This session: Q211-Q214 opened; Q211 closed.

**What was NOT touched (named so absence does not read as finished).**
- **The #378 build:** not scheduled, nothing built; the phase form, `PhaseCard` and the backend route are as they were.
- **Q212's separation and seeding:** deferred to 16 Nov; no change to the posture machinery.
- **Q214:** `client.trigger` is still dropped by the server; a column is a migration and a hold.
- **The Q159 in-activity HR read and #371's overlap proof:** owed, not run.
- **The datasheets brief and the HR input layer (Q213):** recorded, not drafted.
- **The next date-bomb candidates:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` without pinning today; whether any assertion flips on the 15th was not checked.
- **`verify_series_integrity.py:56`:** its runtime message still says `railway run`.
- **The stale-looking amber warning** on a Garmin or Samsung `load_window` slot ("deposits no load until Health Connect stage 2"): left.
- **The sRPE floor, the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206):** unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** a fifth session in a row on the plan's input form and the sync plumbing, this one mostly rulings and corrections. Two of my own first readings were wrong (the server's trigger, the 00:09Z POST) and were fixed from the companion's stores and a later log read. Walk in is where it was.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form (#375, #376, #378; Q211 closed, Q212 deferred; OWED the history check only): **Know** and **Loop**.
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
