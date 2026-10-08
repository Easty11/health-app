# Close-out — ingest-triage: resting HR is now the sleep nadir (#344, #345), Hevy mirrors are suppressed at the read-door (#346), and six decisions and two questions are recorded; the companion RHR capture, the exclusion and reconciliation build, and the HRV re-bucketing are decided and unbuilt

## Real commits this session

Session `ingest-triage`, the operator's briefs of 7 and 8 Oct 2026 (AEST). Range: `7a9114f` (session open) to this close-out. Maxima at open and again immediately before numbering, by anchored script: decisions #394, questions Q216. Numbers minted at the merge step: #395 to #400, Q217 and Q218.

- `0399b96` `fix(labels): call the HC resting_heart_rate column what it is, an all-day median HR`, merged as PR #344 (`c330a1e`).
- `98dc9c4` `feat(hr): derive resting HR as the sleep nadir (DECISIONS_LOG.md:480); bucket the all-day median by AEST day`, merged as PR #345 (`f1cefac`). Carries the migration `a8c4e1f72b93`, released by the operator and applied on deploy.
- `c77f230` `feat(aerobic): suppress Hevy mirrors at the read-door (A3.2); overlaps_workout is one fraction test`, merged as PR #346 (`6b8a482`).
- `4984238` `gov(ingest-triage): #395-#400 ...`, the batched governance commit (this PR).
- A final `chore: session close-out` commit carrying this file and the CLAUDE.md pointer: its hash is on the branch (a file cannot name its own commit).

Deploys: #344, #345 and #346 each reached SUCCESS on Railway (#116). The governance PR changes no code. **Provisional until merged: the governance commit and this file.** The three code PRs are merged and live.

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The operator's close-out brief, item by item:

1. **Q29 premise correction: DONE (#395, and an additive note on Q29).** Q29 itself is unchanged.
2. **fetchMeta capture-only superseded: DONE (#399).** Supersedes #321 on that one sentence.
3. **A3.2 D-a and D-b rulings, A3 closed, the row-111 note: DONE (#397).**
4. **Nadir ratifications, the column home, the alcohol-night constraint: DONE (#395, #396).**
5. **Sweep-scope multi-user gap: DONE as Q217. SCHEMA.md 007 to 013 drift: DONE as Q218** (checked: all seven tables have neither a model nor a migration).
6. **`cbti/replay.py` read-door bypass and the CBT-I closure: DONE (#398).**
7. **Handoff carries, unbuilt: DONE in ROADMAP NEXT ("Ingest-triage carries")** — companion RHR capture (two PRs), reconciliation plus exclusion migration with `title`, HRV re-bucketing, the plausibility parking lot. Garmin `RestingHeartRate` as a secondary in #35's cross-check row is recorded as #400.
8. **"Mint numbers only after merge": met in the form the guard allows.** No integer was claimed until the final re-read of master's max, immediately before this PR's merge; the guard refuses a `#NEXT` heading on master, so the integers are written on the branch at that instant and re-resolved if master advances.
9. **HRV audit, item 3 downgraded: the query is owed to the operator** (ROADMAP, same block).

**Divergences and judgment calls, named.**
- **Q200 is settled but not moved to CLOSED.** Moving it removes lines outside a declared replacement region, which sends the batch to human review (gate (c)); it carries an additive "Settled" note and its State line still reads OPEN. The move, with `DONE → #395`, is owed to the next governance session.
- **#399 leaves the exact use of `fetchMeta` to the build brief.** The ruling superseded "capture-only" without spelling out which fields decide absence; the entry names the fields and does not choose.
- **Q217 and Q218 are filed, not ruled.**

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. NEXT gained one block, "Ingest-triage carries" (UNSTARTED, none briefed).

**State.** Code merged and live: the label fix, the sleep nadir (prod rows read by the operator: 8 Oct 57 bpm, matching the device; 6, 7 and 8 Oct read 57, 53 and 57), and the Hevy-mirror suppression (10 of the 16 Strava rows are mirrors; no load change). The governance PR is open, ready for review, self-merging on green. Nothing on the branch carries `#NEXT` after numbering.

**Single clearest next action.** Pick one of two, by what the operator wants first. (1) Brief the companion RHR capture: PR 1 in this repo is small and additive, but it must first look at ONE real Garmin `RestingHeartRate` record (`time`, `zoneOffset`, `metadata.dataOrigin`) before keying anything. (2) Brief the reconciliation plus exclusion migration (a HOLD at the migration), which also gives row 111 its first exclusion.

**Operator actions owed.** (1) The Garmin HRV freshness read: `SELECT captured_at, rmssd_ms, source, status FROM hrv_readings WHERE user_id = 1 AND source = 'garmin' ORDER BY captured_at DESC LIMIT 1;` Flag it if older than 48 hours. The Samsung gap since 14 Sep is expected (Galaxy Ring on warranty). (2) The CBT-I earlier-prescription check: any `cbti_prescriptions` lights-out before about 20:49. (3) Rule on Q217 (sweep scope) and Q218 (the unbuilt SCHEMA.md sections) when convenient. (4) Carried from the last close-out: the R11 live rollup `as_of`; the #121 bundle check for #393 and #394 (the strings "Leg days", "every listed day", "candidate days", "Not counted toward any quota"); the strip on the phone; the Polar max HR lock at 175 (#388); the Q159 in-activity HR read on or after 9 Oct.

**Code actions owed.** Move Q200 to CLOSED with `DONE → #395` in the next governance session. The #387 shared-block propagation to `health-connect-app` (next HCA session). Carried: the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 120 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). Two opened (Q217, Q218); none changed state; Q29 and Q200 carry additive notes.

**What was NOT touched (named so absence does not read as finished).**
- **The `/metrics` phase-marker build:** nothing in `PhaseMarkers.jsx`, `TimeSeriesChart.jsx` or the four chart components; the R11 item still waits on three small answers (live `as_of`, the token choice, legend placement).
- **The reconcile leg of Walk in (NEXT, #386) and every Loop item** (check-in, readiness, recommendation, close-out): unbuilt or unchanged. This session improved the number the check-in will one day read; it did not build the check-in.
- **No consumer reads the nadir for a baseline or a trend.** #396 sets the constraint any such consumer must meet.
- **Not built, though decided:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV/SpO2/respiratory/distance AEST re-bucketing, and the plausibility layer (a parking lot, nothing decided).
- **Q197, the HC zones lane, Q199, Q216, the Polar re-zoning (Q198), Q213, Q214, Q212, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved. Q216 (HC zoning from heart-rate reserve) now has a resting-HR input it lacked; that is noted here and not ruled.
- **Lab upload pipeline, interpretation layer increments, medical protocol (CBT-I beyond the closure in #398, the injury ledger):** did not move.
- **Known gaps carried:** `verify_series_integrity.py:56` still says `railway run`; `scripts/arbitration_flip_report.py` calls `arbitrate()` directly and is not mirror-aware (a report, not a reader).
- **Pattern to say out loud:** this session was almost entirely on the See and Know data underneath the platform (ingest correctness), after four sessions on the See and Know surfaces. It did not move Walk in's reconcile leg or any Loop item. The next session should take one of the two builds above only if the operator wants the data path finished first; otherwise it should go to the reconcile leg or to a Loop item.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389): **Know** and **Loop**. DONE; a candidate for removal from NOW.
- Know (d), the leg strip and wrap (#390 to #394): **Know**. Built; the test is MET (#392); only #393 and #394's deploy check remains.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**. The nadir's sweep gap for a user without a Hevy key (Q217) sits beside it.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
