# Close-out — #364 (HC zones) is verified in prod after the seed (17 of 29 HC rows zoned, the 28 Sep elliptical deposits once); the Polar band-edge divergence is reported, and the operator's HRmax rulings are recorded as #383 (restatement versus dated change) and #384 (HRmax changes to 177 as a retroactive restatement, bands unchanged; the design is owed as its own proposal); Q216 (HC zoning on heart-rate reserve) is filed; nothing built

## Real commits this session

Session `hc-zones-verify`. Range: `b81cebd` (master at open) to this close-out. Fresh-clone settings were unset at open and were set and verified (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open: decisions 382, questions 215. Maxima now: decisions 384 (#383, #384), questions 216 (Q216).

- `4ff652d` `gov(hc-zones-verify): #364 verified in prod after the seed; Polar-parity divergence reported for the operator` — ROADMAP HC zones row, BRANCHES (the `hc-zones-ingest` row resolved to DONE `054d2d9`, plus this branch's row), a Q199 update, the CLAUDE.md Recent-landings pointer. Governance only. Landed with `861b392` (`chore: session close-out`) as merge `2236cd4` (PR #328); the branch was deleted from the remote.
- **Second round** (branch restarted from master `2236cd4`; `b828373` and `402827b`, merged as `3785666`, PR #329): the operator's amendment of 5 Oct 2026 as DECISIONS #383, and Q216.
- **Third round** (branch restarted from master `3785666`): one `gov(...)` commit and one close-out commit, hashes on the branch (a file cannot name its own commit). It records the operator's full ruling as DECISIONS #384, notes on Q198 and Q199, and the ROADMAP row, the BRANCHES rows, the Recent-landings pointer and this file.
- **Disclosure: three `gov(...)` commits this session** (`4ff652d`, `b828373` and the third round). CLAUDE.md allows one. Each later one records an operator ruling that arrived after the previous PR had landed; each was a single commit on its own branch. Stated here, not hidden.
- **Code and schema: none.** No migration, no code change. The six #364 test files (102 tests) were run on master `b81cebd` and passed (Python 3.11, installed without `garminconnect`; not the full suite). A scratch Postgres 16 built from `models.py` validated the operator's queries and the `--hc-zones` command; it was dropped and stopped.
- **No prod write by Code.** The DB reads and the container report were run by the operator and pasted; Code read the Railway deploy list and logs (read-only).
- Disclosure: one `gov(...)` commit, as CLAUDE.md allows. The branch name `claude/nice-mccarthy-jd2yw8` is the harness's, kept per the harness instruction (recorded in BRANCHES).

## Pending-queue reconciliation

The brief's four items and the correction, one by one. Nothing here came from the chat `;cc` queue as a PENDING item.

1. **G3 report: done, with scope.**
   - **Zoned rows:** 29 HC rows, 17 zoned; the stored zones equal the in-memory projection (canonical flips 0, TRIMP delta 0). `over_ceiling` 0, `no_hrmax` 0, no row within 0.05 of the 0.6 floor.
   - **The 12 unzoned:** 3 `sparse` (69, 85, 92), 2 `no_same_writer_hr` #364 ruled (68, 84), and 7 `no_same_writer_hr` it did not name (72-78, 25-30 Aug). Those seven have zero same-writer HR samples because they predate the oldest stored HR for their writer (Samsung 2026-08-31, Polar Flow 2026-09-20); the 30-day re-post cannot reach them (Likely, not tested). Rows 72, 77 and 78 have no twin, so they never deposit.
   - **Canonical row per multi-row bout (by deposit):** 67 (27 Aug), 90 (20 Sep), 91 (28 Sep), 95 (1 Oct), 97 (2 Oct), one deposit each. The 15 Sep and 22 Sep Pilates pairs have no zoned row and no deposit. **Not read:** whether the single-row HC bouts (79-83, 70, 86, 87, 94, 101) deposit.
   - **28 Sep elliptical deposits once:** one `metabolic` event (id 48849, 115.97, `metab-v1`, zone source `polar_v4`) across rows 88, 89, 91. Verified.
   - **`no_hrmax` count and user 4: the premise failed.** The brief expected user 4 to read `no_hrmax`. User 4 has no `aerobic_sessions` row of any source (the count query shows user 1 only; the chain log read `hc_zoned=0/0` for her on every run since 1 Oct). Her `no_hrmax` is untested, not demonstrated. The count is 0 because nothing was evaluated.
2. **Polar parity: done, reported, nothing edited.** HC 88 and Polar 91 are the same H10 stream and agree on `hr_avg` 137 and `hr_max` 167. Minutes z1..z5: HC 0.60/3.58/10.82/8.60/8.65, Polar 0.32/3.47/11.32/8.98/7.77 (HC minus Polar +0.28/+0.11/-0.50/-0.38/+0.88), Edwards about +1.9 AU (+1.6%). In all seven HC-with-Polar-twin bouts HC z5 is at or above Polar's and HC z3 and z4 at or below (1 Oct running: Polar z5 0.0, HC 1.15 and 2.25 at `hr_max` 157-158); z1 is mixed. That is the direction a Polar HRmax above 173 would give (Likely, not shown). **Ruled afterwards (items 6 and 7, #383 and #384):** HRmax changes to 177 as a retroactive restatement, bands unchanged; not yet applied. Home: the ROADMAP HC zones row and Q199.
3. **`s0_polar_read.py --mode zones`, then `--mode samples`: not run; RETIRED as owed by the operator's full ruling (#384; see item 7).** The file is not on `origin/master`, the branch, any ref, or in the Code container; the stores name it only as an operator-local read. Not guessed at. It would print Polar's zone limits and the implied HRmax, which settles item 2's hypothesis.
4. **ROADMAP NOW and BRANCHES for #364: updated in `4ff652d`.** The `hc-zones-ingest` BRANCHES row is DONE `054d2d9` (PR #298, merged 1 Oct 2026, remote branch deleted). The ROADMAP row keeps OWED for exactly the ruling and the local read.
5. **The seed correction: recorded; no longer OWED.** `user_hrmax` id 1: user 1, effective 2026-03-01 (equal to user 1's earliest `aerobic_sessions` date, read), 173 bpm, `observed`, the #364 note verbatim. `created_at` 2026-10-01 07:49:05.495922Z (17:49 AEST), 17 minutes after the migration ran (07:31:52Z) and before the first stored HR arrived (08:14:35Z). Who: the operator, with `scripts/set_hrmax` (the only writer; a test asserts nothing else touches the table). The table has no author column, so the actor is inferred from the code path, not read. The 5 Oct re-seed was refused by the append-only guard and wrote nothing.
- **Cross-checks that corroborate, from the Railway logs (Certain):** the migration line, the first chain line `no_hrmax=23` (07:32:21Z) and the first `no_hrmax=0` (16:00:24Z), bracketing `created_at`. The 4 Oct 12:08:48Z POST took 237 s against about 8 s normally, so it is probably a deep sync (Likely, not confirmed); the zoned count did not move across it.

6. **The operator's amendment to item 2 (5 Oct 2026, addressed to this session): recorded as #383; the new question filed as Q216.** (a) A `user_hrmax` correction from better evidence is a restatement: retroactive, prior value and reason kept. (b) A value that genuinely changes with fitness is a dated change, forward only. (c) The corrective path (the operator's 2b) must tell the two apart: owed as a design, not built, and no HRmax value changed. **Code's findings on master `2236cd4`, not rulings:** a restatement cannot be appended at the seed's own date (`uq_user_hrmax_effective`, `set_hrmax`), nothing on a row marks it as a restatement, so a marker is likely a schema change and a hold, and a restatement reflows HC rows only (Polar keeps its own zones, Q198). (d) **Q216, OPEN:** should HC zoning move to heart-rate reserve? Its first finding: the app has no resting-HR input today, because `resting_heart_rate` is the day's median of every sample (Q200).
- **Not visible to Code:** the text of the operator's "item 2" and "2b" beyond the amendment. The amendment is recorded as given. Whether the value or bands change at all is not in it, so that stays OWED.

7. **The operator's full ruling (5 Oct 2026; the item 2 / 2b text that #383 amends): recorded as #384.** (a) **Value:** HRmax changes to a target of 177 (173 is a modality-limited lower bound, every observation on an Echo bike), applied as a #383 restatement from 2026-03-01 with 173 and the reason kept; bands unchanged. **Nothing is applied: 173 stands, no row written, nothing recomputed.** (b) **Design, owed as a proposal for operator release, not merged before the ruling on it:** an `adjusted` provenance (base observation and rationale required, distinct from the banned `estimated`); the restatement path at the seed's own date; and the 28 Sep HC-versus-Polar comparison re-run at 177 as a write-nothing projection. (c) **`s0_polar_read.py` retired as owed**; the operator reads Polar Flow's profile HRmax by hand and reports it as context. (d) **Single-row HC bout deposits: low priority, next pass; user 4 `no_hrmax`: untested, not failed.**
- **Code's findings recorded under #384 (not rulings):** `hrmax_in_force` resolves two entries on one date to the first in input order (strict `>`), so lifting the unique key alone would leave 173 in force and the path needs an explicit rank rule; a third provenance value changes the `ck_user_hrmax_provenance` CHECK (a migration, amending #364 R2's closed set); the 28 Sep projection at 177 must be dated after the seed, `--hrmax 1=177@2026-03-02`, or the tie ignores it.
- **Item 2 of the previous reconciliation is closed by this:** the value-or-bands question is ruled (HRmax changes, bands unchanged); the `s0_polar_read.py` reads are retired.

Provisional until merged: everything in the third PR.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** The HC zones row now reads landed, seeded and verified, OWED for one operator ruling and one local read. No other row changed.

**State.** This PR is governance only and self-merges on green; no `#NEXT` placeholders, no migration. Open: Q212 OWED to the 16 Nov review; Q213 and Q214 OPEN with Luke.

**Single clearest next action.** The corrective-path design session (#384): a proposal for operator release, not merged before the ruling on it, covering (a) the `adjusted` provenance, (b) the restatement path at the seed's own date (a schema change, a hold), and (c) the 28 Sep HC-versus-Polar comparison at 177 as a write-nothing projection. The projection command is in #384 and the ROADMAP row (`--hc-zones --hrmax 1=177@2026-03-02`, run in the container); the operator's manual read of Polar Flow's profile HRmax is its context. Applying 177 follows the release.

**Operator actions owed.** (1) Schedule the corrective-path design session (#384) and, when it is ready, release it; read Polar Flow's profile HRmax setting by hand and report it as context (#384). (2) The Q159 in-activity HR read on or after 9 Oct (the stores carry the query; sessions 69, 85 and 92 are the unzoned `sparse` rows it concerns, and now each has 26-30 samples in `hr_samples`). (3) Still open from earlier: the instrument datasheets brief's scope; the capture-rate query (Q202); the Polar backfill report, `--apply` and `refresh_load`; Q205 at the next Polar re-auth; the `concurrent_strength` marker build (Q206); the #371 overlap proof (a natural overlap or a debug control, #380).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This session: Q216 opened; Q199 gained an update note and stays OPEN.

**What was NOT touched (named so absence does not read as finished).**
- **Single-row HC bout deposits:** whether rows 79-83, 70, 86, 87, 94 and 101 each deposit a metabolic event was not read; only the multi-row bouts and 28 Sep were. Ruled low priority for the next pass (#384).
- **The seven pre-reach unzoned rows (72-78):** recorded, not ruled, no recovery attempted; whether the deposit gap on 72, 77 and 78 matters is the operator's call.
- **User 4's `no_hrmax`:** untested until she has an HC aerobic row; no seed for her, no change.
- **The corrective-path design and build (#383, #384):** not started; the table is as #364 left it, and 177 is not applied. **Q216's resting-HR derivation, the Polar re-zoning (Q198), the HRmax benchmark test (Q199's "to decide"), the "Resting HR" label (Q200):** unmoved.
- **The shared phase-entry and ledger build (#378, #379), Q213, Q214, Q212:** unmoved; the queue of unbuilt phase-form work is where it was.
- **The sRPE floor, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Known gaps carried:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` and have not been checked for flipping on the 15th (from the previous close-out). `verify_series_integrity.py:56` still says `railway run`.
- **Pattern to say out loud:** this was a verification session: it moved a record, not a product. The recent sessions have gone to plumbing, ledgers and verification of them (HC sync, source hierarchy, the phase form, now zones) rather than Walk in; the unbuilt phase-form work (#378, #379) still outweighs what shipped this week.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC zones (#364, OWED for the #384 corrective-path design and then applying 177): **See**, **Know** and **Loop**.
- Phase-change form (#375, #376, #378, #379; the build in NEXT): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- The shared phase-entry and ledger build (NEXT), HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **Loop** for the phase build.
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
