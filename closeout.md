# Close-out — the HRmax restatement path is released with three further rulings: #385 (user 1's HRmax is 175; Polar's 175 is age-predicted, so it is alignment and not evidence), #386 (v1 test 3, Walk in, is met and reframed) and #387 (harness branch names accepted; one `gov(...)` commit per landed ruling); nothing is applied in prod

## Real commits this session

Session `hrmax-restatement`, two rounds. Range: `98b8f8b` (master at open) to this close-out. Fresh-clone settings were unset at open and were set and verified (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open: decisions 384, questions 216. Maxima now: decisions 387 (#385, #386, #387), questions 216 (unchanged). Master was still `98b8f8b` at the start of round two, so no number was re-resolved.

- `b718c59` `feat(hrmax-restatement): restatement path and `adjusted` provenance for user_hrmax (#383, #384)` - migration `d6f8b1a3c5e7`, the rank rule in `hr_zones.hrmax_in_force`, `set_hrmax --restate`, both readers, tests, SCHEMA.md section 043, the provenance doc line.
- `874b1b5` `gov(hrmax-restatement): #385 user 1's HRmax is 175 (supersedes #384's 177); restatement path built and held for release` - round one.
- `ff20c8b` `chore: session close-out` - round one's handoff.
- `65abf8b` `gov(hrmax-restatement): #385 corrected in place and ratified: Polar's 175 is age-predicted, so it is alignment and not evidence` - #385, the ROADMAP apply command, the Q199 note.
- `87631e9` `gov(v1-walk-in): #386 v1 test 3 (Walk in) is met and reframed as prepare, prompt, capture, reconcile; reconciliation promoted to NEXT` - #386, the ROADMAP v1 / surfacing / brief / NEXT / LATER rows, the #345 BRANCHES row.
- `d85b4df` `gov(loop-rules): #387 harness branch names are accepted; one gov commit per landed ruling` - #387, the two CLAUDE.md shared-block bullets, a ROADMAP propagation row, the Recent-landings pointer.
- `5b928fd` `gov(served-bundle-greps): discharge the #121 grep half of the owning rows (...)` - the remaining owning rows.
- The `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).
- **Disclosure: five `gov(...)` commits in total (round one's, and four in round two).** CLAUDE.md as it stood at the start of round two allowed one per session; the operator's release brief asked for one per landed ruling and ruled the relaxation (#387), and round two followed it before it landed. Four of the five carry one ruling each; the grep discharge carries none (a recorded fact). Stated here, not hidden.
- **Code and schema: yes; one migration.** The operator released it (5 Oct 2026). Merge, the Railway deploy and the migration in the boot logs are reported in the session, not here: a file cannot know them before it lands.
- **No prod write by Code, and no prod read.** Code's egress to the live frontend is denied here, so the Railway MCP (read-only) was used for deployment state and the bundle greps could not be re-checked.

## Pending-queue reconciliation

Nothing came from the chat `;cc` queue as a PENDING item. The operator's release brief (5 Oct 2026), item by item:

1. **Ratify #385 (a)-(f) as written, including (d): DONE.** #385's Status reads BUILT, RATIFIED and RELEASED, and (d) is unchanged: same user and same date are not database rules; `set_hrmax` and the resolver hold them (`65abf8b`).
2. **Correct #385 and the ROADMAP apply command: DONE (`65abf8b`).**
   - Polar's zoning is removed from the basis and from the `--rationale` string. The basis is the Echo-bike lower bound corrected upward, with alignment to Polar rows' zoning as a second stated reason; the entry records that the alignment target (Polar Flow's 175, a blue ESTIMATE, 220 minus age) is age-predicted and corroborates nothing. An earlier draft that cited Polar as evidence is named as withdrawn.
   - "Polar profile not in the record" is answered. Do-not-revisit gained the lock condition (the operator locks Polar's 175 as user-set; if Polar reverts to an age estimate the seam reopens). The 4x4 figure (about 162 bpm at 90-95%, so roughly 170-180) is recorded as supporting context, not proof.
   - The new `--rationale` string was re-rehearsed in a real shell, extracted from the ROADMAP row itself rather than retyped: it parses, applies, stores in full (314 characters, limit 1000) and a second paste is refused.
3. **Governance fold-ins, checked against master first (master had not moved: none was on it):**
   - **(a) #121 greps: DONE for the grep half of every owning row** (`87631e9` for the two Walk-in rows, `5b928fd` for the rest). Recorded as the operator's read of the live `index-CI1keljv.js`. **Not re-checked by Code:** egress to the live frontend is denied, so the unseeable-surface rule is met by attribution, not by verification. Gate (c) of the Conditioning row (do not open the block-2 phase until the bundle is confirmed) was left exactly as written; whether this discharge lifts it is the operator's call (#270).
   - **(b) v1 test 3: DONE as #386 (`87631e9`).** Reframed as prepare, prompt, capture, reconcile; the reconcile row moved from LATER to NEXT, with a "Mark attended" transition. I checked the code: `routers/appointments.py` has two routes (`GET ""` and `GET /{key}/brief`) and no status route, which agrees with the operator; whether the chat knowledge lane can rewrite a row's `status` was not checked and is flagged in the NEXT row for the build brief.
   - **(c) CLAUDE.md: DONE as #387 (`d85b4df`).** Both bullets are in the shared block, so the verbatim propagation to `health-connect-app` is OWED (a ROADMAP NOW row).
4. **Land #331 end to end: see the session report** (re-resolve if master advanced; deploy SUCCESS and the migration in the boot logs). Provisional until merged: everything on this branch.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** HC zones row: landed, seeded, verified; HRmax 175 ruled (#385); restatement path released; apply owed. Appointment brief row: test 3 met (#386). New NOW row: shared-block propagation owed to `health-connect-app`. New NEXT row: post-visit transcript reconciliation with "Mark attended", UNSTARTED.

**Single clearest next action.** The operator applies 175 after the landing, in the container (`railway ssh --service health-app-backend`, then `cd /app`; one command at a time, read it, then act). The exact commands are in the ROADMAP HC zones row (the dry run, which must say `restates row #1: 173 bpm (observed) effective 2026-03-01` and list every health_connect row of user 1 as `173 -> 175`; then the same without `--dry-run`; then `refresh_load --user 1`; then `arbitration_flip_report --hc-zones --user 1`). Then report the 28 Sep HC-minus-Polar minutes per band at 175 against 173 (+0.28/+0.11/-0.50/-0.38/+0.88) and 177 (z5 -1.04; the other bands were never relayed). **That report is not done and cannot be from a session.**

**Operator actions owed.** (1) The apply and the report above. (2) Lock Polar's 175 as user-set in Polar Flow (#385: if it reverts to an age estimate in November the seam reopens). (3) The Q159 in-activity HR read on or after 9 Oct. (4) The phone read of B, C and E against the ledger for the appointment brief, which is not recorded as done. (5) Whether the #121 discharge of the Conditioning grep lifts the block-2 gate (#270). (6) The items in the previous handoff that this session did not touch.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212, carried from the last count; no question changed state). This session: Q199 gained a corrected dated note and stays OPEN; no question opened.

**What was NOT touched (named so absence does not read as finished).**
- **The reconcile leg of Walk in:** ruled met and promoted to NEXT, but unbuilt and without a brief. Code's own challenge, recorded in #386 and not argued past the operator: marking the test met while a leg of the reframed test is unbuilt is the operator's call. The "Mark attended" route and the answered-state on asks do not exist.
- **The shared-block propagation to `health-connect-app`:** owed, not done; the two repos' shared blocks differ until then.
- **Polar's own zoning, the bands, HR-reserve zoning (Q216), the Polar re-zoning (Q198):** unmoved. The HC/Polar seam is measured after the apply, not corrected. 175 does not come from a measurement of the maximum: Q199's maximal-effort test is still the only route to one.
- **`retire_user` and composite foreign keys; a projected restatement in the flip report:** left as they are (#385).
- **Single-row HC bout deposits (rows 79-83, 70, 86, 87, 94, 101), the seven pre-reach unzoned rows (72-78), user 4's `no_hrmax`:** unmoved.
- **The shared phase-entry and ledger build (#378, #379), Q213, Q214, Q212; the sRPE floor, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Lab upload pipeline and the interpretation layer's remaining increments; medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gaps carried:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` and have not been checked for flipping on the 15th. `verify_series_integrity.py:56` still says `railway run`. The sandbox clone is shallow, so `test_context_builder_output_unchanged_pre_post_refactor` fails here and not in CI.
- **Pattern to say out loud:** this was the fourth session in a row on the HC zones record, and the second round of it was mostly governance (three rulings and a fold-in) rather than product. Walk in moved only by a ruling; no product code for it changed. The unbuilt phase-form work (#378, #379) is where the queue stands still.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC zones (#364, #385, OWED for the apply and the report): **See**, **Know** and **Loop**. After the apply this lane has no remaining work except the per-band report.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Phase-change form (#375, #376, #378, #379; the build in NEXT): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build: **Walk in**, unstarted; labs left v1 under #345, so the lab pipeline's v1 claim is weaker than the row says and is a demotion candidate.
- The shared phase-entry and ledger build (NEXT), HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **Loop** for the phase build.
- Cross-repo shared-block rows (now including the #387 propagation): no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
