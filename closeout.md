# Close-out — hevy-garmin-dedupe: the Hevy-to-Strava mirror chain leaves no residual, Hevy has no metabolic value of its own, and the zone-attachment question is parked (#402, Q219); nothing built

## Real commits this session

Session `hevy-garmin-dedupe`, the operator's brief of 8 Oct 2026 (AEST) and its four amendments. The brief named master `7a9114f`; by the first read, master was `6b8a482`, and it moved twice more (to `02e9fa2`) from other sessions' merges. The working branch was restarted from `02e9fa2` for the governance commit. Maxima at open and again immediately before numbering, by anchored script: decisions #401, questions Q218 at `02e9fa2`. Numbers minted at the merge step: #402 and Q219.

- No commit existed on this session's branch before the close-out (`git cherry origin/master` on it was empty). Nothing was built, so no code PR exists.
- `a3a8192` `gov(hevy-garmin-dedupe): #402 Hevy has no metabolic value of its own, zones supersede only where attachable, H10 wins outright; Q219 zone attachment parked; Strava chain leaves no residual`, merged as PR #350 (`60b3762`, merge commit; checks green; branch deleted). It carries the decision entry #402, the question Q219, the BRANCHES row, the CLAUDE.md Recent-landings pointer and the first version of this file.
- A follow-up `gov(...)` commit (hash on its branch; a file cannot name its own commit) adds an additive status addendum to #402, discharging its OWED items from the operator's query of 8 Oct, and updates the lines of this file that called them open. No new decision number.

Deploys: none; no code changed. **Landed: #350. Provisional until merged: the follow-up commit and this file's current text.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The operator's brief and amendments, item by item:

1. **VERIFY (halt on mismatch): the third check failed and the session halted.** "No existing rule anywhere relates `aerobic_sessions` rows to `hevy_workouts`" was false on master: A3.2 (PR #346) had landed after `7a9114f`. Code reported it and made no census; the operator re-aimed. The first two checks passed (S1a precedes S1b, S1b drops only identical starts from a strictly lower writer class; the Garmin package is in `WEARABLE_NATIVE`).
2. **Step 1, the consumer trace: DONE in the session report.** Every load and readiness consumer takes canonical rows through `arbitrated_sessions`; a mirror is non-canonical and contributes nothing; a canonical zoneless row adds nothing (INV-7); `engine/week_plan.py` is not a load consumer.
3. **Steps 2, 3 and 6b, the prod census: NOT RUN by Code (no database access: the Railway CLI is unauthorized in this environment).** Closed on other evidence instead, named in #402: the operator's #397 impact query (ten mirrors, none zoned, no Garmin-package row affected), the operator's originals query (rows 112, 115, 118, 119 and 122 each have a `polar_v4` original at 1.00), and Code's read plus a 24-case run of the real `arbitrate()`. 6b is zero zoned mirror rows on that evidence.
4. **Step 4, the title or notes check: DONE as far as the repo goes.** `ExerciseRecord.title` is accepted and dropped at ingest; there is no `notes` field. Whether a Garmin or Strava Health Connect record carries the Hevy workout name is a property of the sending app and no payload was read.
5. **Step 6a and 6c: DONE, recorded in Q219.** 6a: a Hevy session contributes no metabolic load on master, and no store ever recorded a fixed or "minor" value. 6c: the readers named there.
6. **The fork on where the rule lives: moot.** Option B (read-time arbitration) was already built (#397, #401).
7. **The enrichment ruling (i): DONE in #402.** Zones supersede where attachable; no zones means 0; no fixed Hevy value. The H10 precedence ruling is in #402 too.
8. **The zone-attachment question, parked: DONE as Q219, State OPEN.** The vocabulary has no PARKED state (`CLAUDE.md`: OPEN, OWED, DONE); the entry says parked and names the trigger.
9. **Strava's Health Connect write revoked 8 Oct 2026: DONE as a dated context line in #402, referencing #397.** #397 is locked text and is not edited; it already states the revocation, undated.
10. **The growth flag: DONE, no violation (operator query, 8 Oct 2026; status addendum on #402).** 16 `com.strava` rows; 0 with `created_at` or `start_time` on or after 2026-10-08; latest `start_time` 2026-10-07 08:22:37Z. The revocation is holding. Code did not run it (no database access).

**Divergences and judgment calls, named.**
- **Type 81, not 70.** The brief and Code's first census SQL filtered Health Connect type 70 (STRENGTH_TRAINING). The Strava rows are type 81 (WEIGHTLIFTING), so that filter would have returned none of them. Every later query keyed on `source_package` instead.
- **The row counts reconcile (operator, 8 Oct 2026; #402 addendum).** #397's 16 = 10 counted mirrors + row 111 + 5 Polar-original rows; by sport the same 16 = 13 Weightlifting + 2 Running + 1 Biking, and the "13 and 3" was the Weightlifting-only cut. The same query exposed a wording error in #402 (it called all 16 Weightlifting, and generalised the relabel from rows 112 and 115 to all five); the addendum corrects it.
- **"Adjudicated as minor" has no record.** The 8 Oct ruling cited an earlier adjudication that no store holds; #402 is now the record, and it chose no fixed value.
- **Q-state.** See item 8.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed and ROADMAP was not touched.

**State.** The Hevy-to-Garmin-to-Strava-to-Health-Connect chain is closed on the read side: ten rows are mirrors (#397), row 111 is a mirror of an excluded Hevy bout (#401), five rows are Polar sessions Strava relabelled Weightlifting and are arbitrated (not Hevy copies), and the write is revoked. Nothing about metabolic load changed: a Hevy session still adds 0 to the metabolic window, a canonical Polar H10 row on a bout deposits as before (#367), and zone attachment is parked until a package with same-writer HR samples records a strength session inside a Hevy bout.

**Single clearest next action.** Take a build that moves a v1 test: the Walk in reconcile leg (NEXT, #386) or a Loop item. This lane (mirror ingest) needs no further Code work; its OWED items are discharged.

**Operator actions owed.** (1) None new from this lane (the growth query is discharged). (2) Carried from the ingest-triage close-out, not confirmed in this session: the #348 post-deploy check (row 111 reads `hevy_mirror = true` and `canonical = false`, no other row changes); rule on Q217 (sweep scope) and Q218 (the unbuilt SCHEMA.md sections); the R11 live rollup `as_of`; the #121 bundle check for #393 and #394 (the strings "Leg days", "every listed day", "candidate days", "Not counted toward any quota"); the strip on the phone; the Polar max HR lock at 175 (#388); the Q159 in-activity HR read on or after 9 Oct.

**Code actions owed.** Move Q200 to CLOSED with `DONE → #395` in the next governance session. The #387 shared-block propagation to `health-connect-app` (next HCA session). Carried: the single-row HC bout deposit read (low priority). Nothing new from this session.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script before the new entry): 120 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). One opened (Q219, OPEN, parked); none changed state.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's open leg:** the reconcile leg of Walk in (NEXT, #386) and every Loop item (check-in, readiness, recommendation, close-out). This session finished a data-correctness question; it built nothing.
- **The `/metrics` phase-marker build (R11):** still waiting on its three small answers.
- **The marker exposure (#367, Q206), the Source hierarchy (Q201, Q203), the Polar re-zoning (Q198), the HC sync reliability lane (Q159, Q208, Q214), the Garmin self-evaluation read, Q216 (HC zoning from heart-rate reserve), Q217, Q218:** unmoved.
- **Decided and unbuilt from earlier sessions:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV/SpO2/respiratory/distance AEST re-bucketing.
- **Lab upload pipeline, interpretation layer increments, medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gaps carried:** `verify_series_integrity.py:56` still says `railway run`; `scripts/arbitration_flip_report.py` calls `arbitrate()` directly and is not mirror-aware (a report, not a reader).
- **Pattern to say out loud:** this is the second session in a row spent on the ingest and dedupe data under See and Know, after four on the See and Know surfaces. It moved no Walk in or Loop item. The next session should go to the reconcile leg or a Loop item unless the operator wants more ingest work.

**v1-triage of the NOW lanes** (which test each serves; unchanged this session):
- Phase-change form (#375, #376, #378, #379, #389): **Know** and **Loop**. DONE; a candidate for removal from NOW.
- Know (d), the leg strip and wrap (#390 to #394): **Know**. Built; the test is MET (#392); only #393 and #394's deploy check remains.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**. #402's H10 precedence ruling rests on #367.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
