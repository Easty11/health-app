# Close-out — 11 Oct 2026: Q202 closed into Q231 and Q203 (#419), Q231's two-class `k` and lag-window terms, the Q231 build constraint from #374, #418's live read discharged, and the day's landing SHAs resolved

## Real commits this session

`git log --format="%h %ad %s" --date=short 5a3785b..HEAD` (session opened at master `5a3785b`, the merge of PR #382; maxima at open: `DECISIONS_LOG` #418, `OPEN_QUESTIONS` Q231; at close: #419 and Q231, no question opened or renumbered). Dates are as git prints them (UTC); the two merges fall just after midnight UTC.

- `92196fa` 2026-10-12 Merge pull request #385 from Easty11/claude/inspiring-babbage-kvjlot
- `78e0253` 2026-10-11 gov(q231-constraint): Q231 build constraint from #374; Q202 Capture rate discharged as moot
- `c2616d1` 2026-10-12 Merge pull request #384 from Easty11/claude/inspiring-babbage-kvjlot
- `c648d5a` 2026-10-11 gov(q202-close): close Q202 into Q231 and Q203 (#419); #418 live read discharged
- the commit of this close-out (`chore: session close-out`), on the same harness-assigned branch restarted from `92196fa`, which carries this file

Both PRs opened ready-for-review, not draft, and were self-merged with a merge commit once all three required checks were green (`placeholder guard (POSIX)`, `backend tests (pytest)`, `frontend tests (vitest)`), each pinned to its head SHA. Governance only, no schema, so neither held. The branch was deleted by the remote on merge (a `git push --delete` afterwards found no ref).

**The day's other landings, from `git log --first-parent` (other sessions' work; reconciled here, not this session's).** Merge SHA, PR, content:
- `c28f106` #371 (pm-catchup rulings on #407 and the Q227 defer); `e448c78` #372 (the gym-programme 1ms revision, code); `d9054f1` #373 (#412, the catch-up card's resolution); `f1fad21` #374 (#411 and FEEDBACK §64, the Hevy routine ids).
- `dbaa630` #375 (ROADMAP: Polar relabel step (1) discharged, steps (2)-(3) struck as no-ops); `4d56ed8` #376 (#413, HANDOFF.md retired).
- `bd24e53` #377 (#414, the gym-trace marker); `82c0203` #378 (#415, `get_recent_sessions` segments); `17cc0cd` #379 (the HCA HANDOFF row discharged, the #413 pointer).
- `b2d1cde` #380 (#416, the fruit batch); `c8212a3` #381 (#417, the Q201 arbitration rulings); `5a3785b` #382 (#418, the `also_recorded_by` twin surface).

#371 to #374, #377 and #379 were not on the brief's list. They landed the same day and their placeholders map to merges by their head commits, so the ones that left a placeholder (#412, #414, and the #411 BRANCHES row) were resolved with the rest.

## Pending-queue reconciliation

No `PENDING` items were carried in: a search of the four stores finds only the ritual's own descriptions. The input was three operator briefs, all reconciled:

- **Q202 close-into-Q231** (the first brief) landed in `c648d5a` (merge `c2616d1`) as `DECISIONS_LOG` #419: Q202 closed as superseded and moved below `## CLOSED`; Q231's two-class `k` with its first ratified sport-to-class table, and lag-window supersession with the named never-both test; the Q189 note (Case A lean moot for Garmin-watch sessions, OPEN for H10-only); Q203 untouched; and #418's OWED live coach read marked DONE in #418, Q201, ROADMAP and BRANCHES, with `5a3785b` on the #418 BRANCHES row.
- **Part 1 of this brief** landed in `78e0253` (merge `92196fa`): the Q231 build constraint (derived from #374, recorded as a constraint and not a ruling) and the closed Q202's `Capture rate` OWED discharged as moot. By the brief this carries no `DECISIONS_LOG` entry, so its home is `OPEN_QUESTIONS.md` (Q231 and the closed Q202 block), and the CLAUDE.md pointer names this file.
- **Part 2** is this commit: the landing SHAs, resolved from the merge commits and verified against each merge's head commit. `BRANCHES.md`: the rows for #381, #380, #378, #374, #384 and #385 (and a row for this close-out); the #417 row's outstanding cell, which still said (b) was Luke's to rule, now says it was ruled in #418. `DECISIONS_LOG` Status clauses of #412 (`d9054f1`), #414 (`bd24e53`), #415 (`82c0203`), #417 (`c8212a3`), #418 (`5a3785b`, the status line the brief named) and #419 (`c2616d1`). The ROADMAP Q231 row gained the build constraint.

Nothing decided in this session is uncommitted: every ruling is in a merged commit; only this close-out is provisional until its own commit. **Stated plainly:** the 11 Oct live read, the `k` ranges and the zone minutes behind them are operator-reported or chat-computed; Code has no database route and re-ran none of it. The repo carries only the aggregate `k` ranges, tagged Likely, and no per-session values (the repo is public). `HANDOFF.md` is retired (#413) and was not written.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No row added or removed. Changed: the Q231 row (the two-class `k`, lag-window supersession, and the #374-derived build constraint) and the Source-hierarchy row (Q202 closed; Q203 is its only open rule; the #418 read is DONE).

**State.** Nothing was built this session. Q231 is OPEN, ruled in principle (10 Oct) and refined (11 Oct); its build is gated on at least 10 pairs and must be live before January 2027. Read its ruling blocks in order: the 11 Oct block amends the 10 Oct terms for Pilates, Yoga and Stretching (their own class, fail closed, never borrow) and leaves the rugby term, the 10-pair gate and the date untouched. Q202 is closed (#419); the floor is Q231 and the explicit absence is Q203. #326, #373 and #374 stand. DECISIONS max is #419; OPEN_QUESTIONS max is Q231.

**Single clearest next action.** Operator (Luke) and Code are not blocked on each other here, so the clearest action is a choice of lane, not a build: the next Code session should take the **Walk in reconcile leg** (ROADMAP NEXT, `UNSTARTED; needs a build brief`, #345/#386), the only v1 leg with nothing built and no external gate, or another Loop item that changes what the operator does. The Q231 build cannot open until the operator has rated Garmin activities within 7 days and the pair count reaches 10; nothing on the Code side moves it.

**Operator actions owed (unchanged by this session, restated).** Q231: rate every Garmin activity within 7 days (the sweep stops re-checking after 7), and after the next rated unstrapped activity run the one live-check statement in Q231 (verify the user id first) and report the rows or which link failed. The `Capture rate` query on the old Q202 is **no longer owed** (discharged as moot). The other OWED NOW rows are as the previous close-outs left them: Q205 at the next Polar re-auth, the Q199 HRmax test, Polar Flow's locked 175, the #412 opportunistic missed-PM check, the injury-clearance sweep, the aerobic-ingest check, the Garmin self-evaluation first run, the G6 seed checks, and HC sync reliability (#371's overlap proof; Q159, Q208, Q214).

**Things the next reader should know.**
- **The never-both test is load-bearing, and why.** Read at master `5a3785b`: the metabolic transform's delete is scoped to `user_id` and `formula_version == FORMULA_VERSION_METABOLIC` (`load_events_metabolic.py:181-183`, `metab-v1`); the natural key `uq_load_event_session_window_version` includes `formula_version` (`models.py:1434-1435`); the model docstring says a new version's rows coexist beside the old (`models.py:1411-1414`). #374 gives imputed rows their own `formula_version`. So the transform must clear imputed rows in the same pass, or a session imputed in one run and zoned in a later one holds both. Re-verify the line references before building.
- **The closed Q202 entry carries two statements about the `Capture rate` OWED**: the #419 closure paragraph says it is still unrun, and the next paragraph (Part 1) says it is discharged as moot and supersedes that sentence on this point. Read the later one.
- **Two sessions numbered from the same master again, in flight now.** `claude/brave-babbage-5x3kij` (another session, Q27 taxonomy v1: `6730dd9` and `7304699`, two commits not on master, cut from `5a3785b`) carries two `### #NEXT` headings after #418. Master's max is now #419, so those resolve to #420 and #421 at its merge and strict mode will force the branch to update. It is not this session's and was not touched.
- **SHA placeholders left, outside the day's PRs.** Not resolved here: 29 older BRANCHES rows (from 5 to 10 Oct and earlier) and the `DECISIONS_LOG` Status clauses of #382, #391, #393, #394, #403, #404 and #407, plus two ROADMAP clauses. The `plan-sessions-mcp` #410 reference-fix row maps to PR #370 (`71d046f`), and #407 to PR #357 (`129a5d4`), per `git log --first-parent`. One mechanical sweep from the merge history would clear them; it was not in the brief.
- **Container mechanics.** `gh` is present at `/usr/local/bin/gh` but its token failed login here, so PRs and merges used the GitHub MCP tools; the `land` alias (which calls `gh`) was not usable. A fresh clone lacks `core.hooksPath` and the alias; the hook was set and verified at open.
- **The `k` evidence is thin and aggregate.** Conditioning `k` about 0.42-0.77 (median about 0.64), walks about 0.08-0.17, chat-computed from one MCP read with zone minutes rounded. It justifies the split, not a fitted value; no fit is possible until the pairs exist.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's other open legs.** Walk in's reconcile leg is unbuilt; Loop has no new capture, recommendation or log leg. See, Know and Walk in are MET by ruling; Loop is the open test.
- **Feature lanes that stood still:** the appointment brief and its reconcile leg, the lab upload pipeline and interpretation layer (labs left v1 under #345), CBT-I, the Hevy programme and routines, the companion app (`health-connect-app`), the MCP OAuth owed items (G4, G5), and the cross-repo propagation rows.
- **Questions gating them, unchanged:** Q203 (how an expected-but-absent device is represented; Source hierarchy's last open rule), Q189 (the H10-only capture fork), Q124 (field-session ingestion), Q198 (Polar re-zoning from raw HR), Q159, Q208 and Q214 (HC sync), Q205 (Polar sport table), Q224 and Q225 (freshness), Q226 and Q227 (missed-PM), Q228 (zero-minute rows).
- **Pattern to say out loud.** Today's governance (#417, #418, #419, the Q231 terms and constraint) all went to the load model's input layer and its records: which copy of a run deposits, how a suppressed twin shows, what an unrecorded session is worth. The one Loop habit that landed (#407, #412) was earlier. The load model is now specified further than anything the operator can do with it today, and its build is gated on data the operator has not yet produced. The next session should go to a Loop or Walk in item unless the operator says otherwise.

**Open questions by status.** 123 OPEN and 6 OWED above `## CLOSED` (129 headings), 101 closed. This session opened none; Q202 moved below `## CLOSED` as `DONE → #419`.

**v1-triage of the NOW lanes.**
- Q231 RPE fallback: **See** (a load number that counts the sessions actually done, imputed ones shown as such) and **Loop**. Source hierarchy (Q203 left): **See** and **Know**.
- Unchanged and keeping the tests earlier close-outs named: Missed-PM catch-up **Loop**; Data freshness **See** and **Loop**; Plan/schedule and recent-sessions MCP tools **See** and **Loop**; Polar sport-id relabel **Know** and **See**; HC sync reliability **See** and **Loop**; Garmin self-evaluation read **Know** and **Loop**; Aerobic ingest automated **See** and **Loop**; Session fidelity **Loop** and **Know**; Injury clearance **Know** and **Walk in**; HC zones **See**, **Know** and **Loop**.
- Candidates for removal from NOW (DONE, kept for owed checks): the phase-change form (#389), Training tag seed (#339), Garmin account mix-up (#362), the two CBT-I rows (#213, #219), typed constraints (#342; its historic-scoping check is still owed, so it stays until that is read).
- Serving no v1 test, with no reason found to sit in NOW: the **Lab upload pipeline** and **Interpretation layer build** rows (labs left v1 under #345). The operator should rule whether they stay.
