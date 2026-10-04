# Close-out — Q210 is ruled (a): sport groups are counted with activity slots, one metabolic slot takes the remainder, and load accrues for every device session (#376); the phase form's placement trap, history read and kind hints are fixed

## Real commits this session

Range: `7bfdb0a` (master at the start of this half of the session) to this close-out, read with `git log --format="%h %ad %s" --date=short 7bfdb0a..origin/master`. All on 4 Oct 2026. Fresh-clone settings (`core.hooksPath`, the local `land` alias) were set at open. Maxima at open: decisions 374, questions 209. Maxima now: decisions 376 (on this branch), questions 210.

Code branches, each concern-named, each self-merged on green (guard, vitest, pytest) with a merge commit and the branch deleted:
- `fix/phase-form-save-order`: `5422bcb fix(phase-form): validate the whole save before creating a Hevy folder; slot keys become pickers`. PR #311, merge `c6bae6c`.
- `fix/phase-placement-relink-on-change`: `d0b0b45 fix(phase-form): a slot picked on a Keep placement switches it to Relink`. PR #313, merge `bfa58f1`.
- `fix/phase-history-shape`: `bed4e57 fix(phase-history): read the server's {history: [...]} envelope`. PR #314, merge `f38ec24`.
- `fix/phase-form-load-hints`: `5a576fb fix(phase-form): the quota-kind hints say a slot claims sessions to count them, and load still accrues`, then `0583d8b`, master merged in once when the branch fell behind. PR #315, merge `0574072`.
- `test/slot-claim-vs-load`: `b5d7d35 test(slots): pin that a slot claims sessions to count them and load accrues regardless`. PR #316, merge `c6b5c89`. Tests only.

Governance:
- `gov/phase-form-save-order`: `8522894 gov(phase-form-save-order): #375 save validates before the Hevy folder create; Q210 filed`. PR #312, merge `f2eea43`.
- `gov/q210-ruled-phase-form-fixes` (this PR): DECISIONS #376, Q210 closed, the ROADMAP row, the BRANCHES rows, the CLAUDE.md pointer, this file. A file cannot name its own commit; the hash is on the branch.

**Disclosure: two `gov(...)` commits this session.** CLAUDE.md allows at most one per session, at close-out. #312 landed earlier (it carried #375 and Q210's filing); this is the second, which the operator directed ("fold the Q210 ruling, the placement-trap fix and the hint correction into the next governance commit"). It is stated here rather than rewritten. The earlier half of the session (the Garmin self-evaluation read) landed its own governance in PR #310 (`7bfdb0a`, #372-#374 and Q209 closed), outside this range.

- Migration: none in this range. No prod data write; Code has no database access. Deploy facts below were read by Code from Railway.
- Deploys (Railway, read by Code): #313 backend `f721d506` / frontend `8b39863c`; #314 backend `492f210f` / frontend `9983dc7d`; #315 backend `6ce7f5ae` / frontend `20985025`: all SUCCESS. #316 backend `d255b741` / frontend `48d799cf` were still BUILDING at the last read; the change is tests only, so it alters nothing served. Re-read them before relying on that.
- **Not run:** the served-bundle probe (#121). The session's egress proxy denies the frontend host and it was not worked around. The PowerShell line is in the ROADMAP row (string to grep: `Kept as on file`).
- Verification run by Code: backend suite on the earlier half, 2,800 passed, 1 skipped, 1 failed (`test_context_builder_output_unchanged_pre_post_refactor`, the shallow-clone `git show 3360ed5` artifact, green on CI). New tests this range: 4 backend (`test_slot_claim_vs_load.py`, 3 mutations each caught), frontend tests for the Keep-to-Relink switch, the history shape (reverting the one-line fix fails 5 of 6) and the two hint wordings. Every PR merged only after the head SHA's three required checks were read as success.

## Pending-queue reconciliation

Every item the operator sent this half of the session, with its outcome.

1. **Phase-form save order (the 4 Oct bug note).** Landed in #311 (see the previous close-out's item list, now superseded by this file): validate the whole write before the Hevy folder; capacity and load_window slot names are pickers. Recorded as #375.
2. **"Save already succeeded; the wizard revised in place; history empty; verify revise vs close+open and propose a route."** Verified: every transition, Continue or Move, is close+insert. The week counter resets because `entered_on` is today, and the label is locked on Continue. The history was empty because `PhaseHistory.jsx` read the response as a bare array while the server returns `{history: [...]}`: fixed in #314. Route proposed, not executed: re-run the wizard with "Move to a new phase" and the label `aerobic base` (a same-day change is allowed, #317). No ledger edit. **Not landed / not seen:** the decompression rows in the ledger are Likely there, not read; the operator's SQL is owed.
3. **"Q210 input: does the activity slot's 'never deposits load' hold; does load deposit regardless of quota kind; can one session satisfy both."** Verified by reading and by a scratch run, since turned into #316: load deposits for every session with usable zones whatever the slot; a session is claimed by at most one slot, in order (activity first, then load_window). So (a) works, with one effect Q210's first text missed (the aggregate slot counts only the remainder). Corrected in Q210's text.
4. **"Placement tally reads UNPLACED."** Verified: the tally was correct; Keep retains the stored link and ignores the dropdown. UX trap fixed in #313 (a differing pick on a Keep row switches it to Relink; clearing is a Relink to none).
5. **"Q210: rule (a) ... fix the activity hint ... fold into the next governance commit."** Ruled and recorded: #376; Q210 closed. Hint fixed in #315; claim-versus-load pinned in #316.
- **Not landed:** a live save and the ledger read (owed, operator); the #121 bundle probe; the duplicate Hevy folders (no delete in the API); reuse of a same-named folder (not built, not ruled); and the amber warning on a Garmin/Samsung `load_window` slot ("deposits no load until Health Connect stage 2 (Q159)"), which may be stale since stage 2 landed (#364), left unchanged because it was not asked and needs reading against the HC pipeline.
- **Candidate FEEDBACK rules, NOT minted** (governance batching, and no decision has ratified them): (i) a mutation check must run with `PYTHONDONTWRITEBYTECODE=1` and cleared `__pycache__`, since a same-size, same-second mutate-and-restore left a stale `.pyc` and produced two false results; (ii) a chained `expect(a).toBe(x) && expect(b)...` never evaluates its right side (three such dead assertions were found and split in #313). Raise at the next FEEDBACK pass.

Provisional until merged: everything in the gov PR. The code is landed.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Row 39 rewritten: **Phase-change form: save order, placements and slot pickers** (#375, #376; Q210 closed), OWED (operator). The Garmin self-evaluation row (the stored-rows read) is unchanged and still owed. No other row changed.

**State.** #311, #313, #314, #315, #316 merged. The gov PR self-merges on green; #376 resolved at master max #375, re-read before the merge.

**Single clearest next action.** The operator reads the ledger (PowerShell, `railway connect` to `health-app-DB`): `SELECT id, label, entered_on, closed_on, close_reason FROM training_phases WHERE user_id = 1 ORDER BY entered_on, id;`, then opens the Phase card's history and confirms it shows the same rows. Then the bundle probe (expect `True`), then name the phase `aerobic base` before Mon 5 Oct via "Move to a new phase".

**Operator actions owed.** (1) The above, plus the duplicate Aerobic Base Phase folders in the Hevy app. (2) Still open from earlier close-outs: the read of `garmin_activity_selfevals`; the capture-rate query (Q202); the overlapping-sync live proof for #371; which build the phone runs; periodic manual 30-day syncs until P1 (#370) lands; the Polar backfill report, `--apply` and `refresh_load`; Q205 at the next Polar re-auth.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 115 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This half of the session: Q210 closed (`DONE → #376`); none opened.

**What was NOT touched (named so absence does not read as finished).**
- **Several metabolic slots (b).** Not built; the ruling is (a). If a TOTAL conditioning quota across sport groups is ever needed, #376 says to reopen: it would touch the validator, the resolver, `satisfies`, `consistency_rows`, the form and the coach write-shape docs.
- **Folder handling beyond ordering.** No reuse of a same-named folder, and nothing about routines being un-movable between folders.
- **The stale-looking stage-2 warning** on the load_window slot (above).
- **The sRPE floor, the Garmin in-activity HR read (Q159), the phone code and P1 (#370), the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206).** Unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move; the phase form is the plan's input surface, not its judgement.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** this was the second session in a row spent on the plan's input form and the Garmin read, both real-use fixes. Walk in and the plan-versus-log judgement are where they were. The 5 Oct check-in is the first real test of the Know lane and rests on the operator's phase rename.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form: save order, placements and slot pickers (#375, #376, OWED): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED, the stored-rows read): **Know** and **Loop**.
- HC sync reliability (#369-#371, Q159, Q202, Q208, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
