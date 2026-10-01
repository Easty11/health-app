# Close-out — HC ingest stage 2: source-neutral HR zoning for health_connect sessions (#364, closes Q159); PR #298 HELD at the migration

## Real commits this session

Range: `94ba73c` (master when the session opened, PR #297) to the close-out commit, real `git log` of branch `hc-zones-ingest` (pushed; PR #298, ready-for-review, held for the operator):

- `c1415df` 2026-10-01 feat(hc-zones): source-neutral HR zoning for health_connect sessions (Q159 stage 2, S1-S3)
- `dde8b16` 2026-10-01 docs(schema): SCHEMA.md section 041 for hr_samples and user_hrmax; strengthen two mutant-killing tests
- `8d37127` 2026-10-01 gov(hc-zones): DECISIONS 364, Q159 closed, Q198-Q200, ROADMAP item 6 discharged, BRANCHES row, Recent landings
- the `chore: session close-out` commit that carries this file (its hash is on the branch; a file cannot name its own commit)

The S0 probe ran earlier in the session and wrote nothing. The harness-assigned branch `claude/relaxed-clarke-9q9qyy` carries no commits of its own (`git cherry origin/master` empty; identical to master `94ba73c`).

## Pending-queue reconciliation

No `PENDING` items were carried in: this session's input was a chat brief plus two rounds of operator G0 rulings, not a `;cc` queue. Every ruling was committed, in `8d37127` unless stated:

- R1-R4, data-meaning calls 1-6, constants (60 s / 0.6 / 30-240), the closed reasons, the soft-fail distinction from #357, #322 S2 reaffirmed, #353's "belongs to brief B" note VOID: DECISIONS #364.
- Q159 closed (`DONE → #364`); Q198 (source-neutral re-zoning, S0(e) inventory table verbatim, Garmin direct kept "untested"), Q199 (Echo Bike HRmax benchmark), Q200 (the "Resting HR" label): OPEN_QUESTIONS.
- ROADMAP item 6 discharged and a NOW row for the operator's owed steps; the BRANCHES row; the Recent-landings pointer.
- The HRmax seed (user 1, 173, `observed`) is decided but NOT written to any store: it is a prod write the operator runs after the migration (`scripts/set_hrmax.py`; command in the ROADMAP NOW row). Provisional until then.
- **Not landed here, by design:** the HCA question (6-hourly POSTs returning `heartRate received=0, truncated=true`, ids 27-31, 38-44, 48; hypothesis, Likely and unverified: background HC reads refused for HR; bears on HCA #44 G2). `health-connect-app` is not in this tree. It is recorded in #364's How-you-know and the ROADMAP NOW row, but the HCA register has no entry until a session in that repo writes it. Provisional.
- A defect in my own gov commit, fixed in this close-out commit: the ROADMAP NOW row was first inserted after the lab-flag table instead of the main NOW table.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One active row is this work: **HC zones (#364): release, seed, verify (OWED, operator).** Others still in NOW: injury clearance via the #340 sweep (OWED, operator), aerobic ingest automated check (#353, OWED, operator), session fidelity G6 (#354-#357, OWED, operator), and two cross-repo shared-block propagation rows (OWED).

**State of PR #298.** Built, tested and pushed. It holds for the operator because it carries migration `b4d6f8a1c3e5` (CLAUDE.md § Merge disposition, hold (a)); it is not self-merged. Numbers #364 and Q198-Q200 were resolved at master max #363 / Q197 (`94ba73c`): **re-read master's max and re-resolve if it advances before landing.** Backend suite on Python 3.12 with full requirements: 2650 passed, 1 skipped, 1 failed (`test_context_builder_output_unchanged_pre_post_refactor`, the shallow-clone artifact, identical on master). CI on the PR has not been read yet in this session.

**Single clearest next action.** The operator releases and merges PR #298, confirms the deploy reaches SUCCESS with the migration applied, then runs the ROADMAP NOW row's steps in order: seed user 1 with `set_hrmax` (`--dry-run` first), one HCA sync then a 30-day deep sync, one chain run, the G3 report, and the Polar-parity comparison for the 28 Sep bout (HC row 88 vs Polar row 91, per band) **by 4 Oct** (inside the 7-day HR re-post window, otherwise a 30-day sync). A divergence from Polar is the operator's ruling (bands/HRmax change plus a recompute), never an edit.

**Optional pre-merge read (operator).** The timestamps-only G2 projection gives exact coverage and reason per HC row before the migration exists: export `aerobic_sessions` and the HR timestamps over `railway connect`, then `python -m scripts.arbitration_flip_report --hc-zones --csv ... --record-sources-csv ... --hrmax 1=173@2026-06-01`; read the rows marked NEAR (within ±0.05 of 0.6). Zones cannot be projected before merge: no bpm exists in any prod table until deploy plus an HCA re-post. Also owed, no longer a gate: `s0_polar_read.py --mode zones`, then `--mode samples` (untracked script, saved by the operator in `backend\`).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`): 110 OPEN, 4 OWED (Q78, Q176, Q178, Q181). New this session: Q198, Q199, Q200 (all OPEN, none blocking). Closed this session: Q159. The ones that gate product work are named in the next section.

**What was NOT touched (named so absence does not read as finished).**
- **Know / the plan:** plan-conformance adjudication (Q197) is a chat proposal, not ruled, and the Hevy `routine_id` check is still owed before its design relies on it; Q27 vocabulary and the Rule 1 vote counter are unchanged (#363 stays "recorded, not built").
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments, and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 clearance sweep, operator-owed) did not move.
- **Loop / Fitness UI:** nothing user-facing changed. The zoned HC rows will appear in the session list and the metabolic trend only after the operator's steps above; no frontend work was done, and the served-bundle checks of earlier PRs (#121 pattern) remain owed where noted in their rows.
- **Pattern to say out loud:** the last several sessions (Polar ingest automation, session fidelity, the Garmin account repair, and now HC zoning) all went to load/ingest plumbing and its integrity. The things that plumbing feeds, the plan-vs-log judgement (Q197) and the pre-appointment brief, have had no session.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC zones (#364, OWED): **See** (a Garmin/Samsung/Polar-Flow session deposits metabolic load, so the trend stops under-reading), **Know**, and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted this session).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
