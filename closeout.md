# Close-out — 29 Oct 2026: the open-question sweep (#459) and its three folds (#460), both repos; governance only

## Real commits this session

Session opened at health-app master `6d15a4c` (the merge of PR 453). Maxima at open: `DECISIONS_LOG` #457, `OPEN_QUESTIONS` Q245; the brief named #457 as the next free number, so it was stale and was re-read, not trusted. Maxima at close: #460 and Q246 (Q246 was raised by another session's #458, not here). `git log --format="%h %ad %s" --date=short 6d15a4c..origin/master`, my commits only:

health-app:

- `6d89b07` 2026-10-25 gov(oq-sweep): 19 questions close, 14 re-scoped, Q134 -> Q151/Q135 re-pin (DECISIONS_LOG #459)
- `383de2c` 2026-10-25 Merge origin/master into sweep branch (master had advanced to `896d61f` and taken #458 meanwhile; the branch's #458 became #459 here)
- `c18b307` 2026-10-25 gov(oq-sweep): DECISIONS_LOG #459, BRANCHES row, Recent landings pointer
- `d2a856b` 2026-10-26 Merge pull request #456 from Easty11/claude/youthful-clarke-bpacrn (all three checks green; opened ready-for-review and self-merged; master max re-read at #458 immediately before)
- `41756a5` 2026-10-28 gov(oq-sweep-folds): #460 Q42 closes as transferred, Q83 folds into Q224 (admission fork carried), Q129 folds into Q173
- `5c08f1a` 2026-10-28 Merge pull request #457 from Easty11/claude/youthful-clarke-bpacrn (all three checks green; master max re-read at #459 immediately before)
- the commit of this file, the BRANCHES row and nothing else (`chore: session close-out`), on `claude/youthful-clarke-bpacrn`

health-connect-app (cloned read-write this session; attached with `add_repo`):

- `2961475` 2026-10-25 gov(oq-sweep): Q21 DONE -> #44, Q22 stale state line struck, Q18 re-scoped (health-app DECISIONS_LOG #459)
- `3c2986b` 2026-10-26 Merge pull request #79 from Easty11/claude/youthful-clarke-bpacrn (the guard was its only check; green)

Not mine, landed in the same span: PR 458 (`c7aa6a0`, `bcbaf24`, the Garmin token-invalidation probe, another session). Commit dates are git's author dates; the two PR merges and the folds landed on 26 and 28 Oct. The harness-assigned branch name `claude/youthful-clarke-bpacrn` was used three times (the sweep, the folds, this close-out), each time restarted from master after its PR merged and the remote branch was gone.

Deploys (#433): every merge here changed only governance files, so SKIPPED on both Railway services is the expected result. **Not read by Code**: no `railway deployment list` was run this session. The #433 "no record at all means the trigger did not fire" check is therefore owed to whoever next reads it.

## Pending-queue reconciliation

Inputs: (1) the PENDING block "open-question sweep, ruled 2026-10-26 (Luke, in chat)"; (2) chat's recommendation on three rulings, relayed on 28 Oct and ruled by the operator in session ("ruled — land #460 with both additions"). No other `PENDING` items were carried.

- **Sweep decision (brief item 1).** Landed as `DECISIONS_LOG` #459 (`c18b307`, merged `d2a856b`), not #457: #457 was already the recovery-readers decision, and #458 landed while the branch was open. Every `DONE → #457` in the brief is `#459` in the store.
- **Health-app closures, 19 rows (items 2).** Tier A (Q200, Q82, Q68, Q188, Q190, Q131, Q132), Tier B (Q97, Q98, Q88, Q32, Q90) and the seven superseded (Q10, Q19, Q46, Q99, Q134, Q152, Q186): `6d89b07`, merged `d2a856b`. Each moved below `## CLOSED` in ascending order in the same commit; the old state text is kept verbatim under the new State line.
- **Q134's consequences.** Q151 now solely owns the `recovery.py` disposition; Q135's gate is re-pinned to the actual remaining readers of `samsung_hrv_readings.hrv_ms` (`routers/health.py`, the chat context's Samsung block, `reads/recovery_night.py`, `reads/snapshot_reads.py`, the unmounted `recovery.py`). `6d89b07`.
- **Health-connect-app (item 3).** Q21 `DONE → #44`, Q22's stale in-body OPEN line struck, Q18 re-scoped: `2961475`, merged `3c2986b`. The brief's question whether the stale Q22 line inflated the OPEN count: it did not, because the parser reads the heading's inline state first and the body only when the heading has none.
- **Re-scopes (item 4), 14 health-app rows plus HCA Q18.** Landed in `6d89b07` and `2961475`. Where the heading asked the discharged question it was retitled (Q24, Q55, Q59, Q83, Q102, Q118, Q129), with the original title kept on the row. Q233's "What exists" manifest was rewritten against #449, #450 and #457.
- **Deviation, Q173.** The brief's "now asks" for Q173 (the "Resting HR" mislabel and the unread `spo2_nights`) had already been discharged by #457, which landed after the review snapshot; Q173 was re-scoped against #457's own "Not fixed, reported" list instead. Recorded in #459 item 5(b).
- **Q42, Q83, Q129 (the brief's three "consider" folds).** Not made in the sweep (none was ruled), then ruled and landed: `41756a5`, merged `5c08f1a`, recorded as #460. Q42 closes as transferred to health-connect-app Q19 (read OPEN on 28 Oct); Q83 folds into Q224, whose open design points now carry the admission fork, the Q175 gate and the decided-`'unknown'` precondition; Q129 folds into Q173, with notes on Q173 and Q151. The brief's suggested Q129-into-Q243 fold had no target (Q243 closed at #457).
- **Flags (item 5): no edit ruled, none made.** Q205 (`sports:read` is still absent from `SCOPES` at `backend/connectors/polar.py:39`, read 26 Oct, so #368's revisit trigger may have fired; the 24 Oct re-auth outcome is unrecorded) and Q181 (the free-text `user_knowledge` write and read paths in `routers/chat.py` are live; brief 2 is not cut; the brief's line numbers 1030–1054 and 1537 have drifted, the legacy `{category, content}` write is near line 1088 and the prompt read near 1597 on 26 Oct). Both are carried below.
- **Bookkeeping check (item 6).** Health-app live questions (OPEN + OWED) 134 → 115 at #459 and 115 → 112 at #460, by the repo's own `gov_dialects` parser run locally (the weekly script reads remote master, not run here). The brief's DONE figures (110 → 129) were one low, because Q243 closed at #457 after its snapshot; the parsed figures are DONE 111 → 130 → 133. HCA 14 → 13 live, DONE 11 → 12.

Nothing decided in this session is uncommitted. Only this close-out is provisional until its own PR merges.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Not edited this session; `ROADMAP.md` still reads "Last updated: 2026-10-25". The NOW rows are the CBT-I, Garmin/Polar/HC ingest, source-hierarchy, sRPE and appointment-brief lanes; their own "Serves" clauses stand. Roadmap lines this session's closes make stale and which were left for the operator: row 207 ("HR input layer, per second (Q213)") still says it "waits on Polar per-second ingest (Q10, Q198)", and Q10 closed as superseded at #459 (#364's `hr_samples` serves the HC lane from HC's own raw HR, so AccessLink per-second ingest is optional); whether row 207 still waits on Polar per-second ingest is for the operator, not Code, and Q198 is untouched. The history line 80 ("Q200 ... owes its move to CLOSED") is now true and was left as dated history.

**State.** `DECISIONS_LOG` max is #460; `OPEN_QUESTIONS` max is Q246. Health-app questions above `## CLOSED`: 105 OPEN and 7 OWED (Q78, Q176, Q178, Q181, Q205, Q239, Q242), DONE 133. health-connect-app: 10 OPEN and 3 OWED live, DONE 12. Health-app master is `bcbaf24` (PR 458's merge) at close.

**Single clearest next action.** The operator rules the two flags that gate real work: record the outcome of the 24 Oct Polar re-auth and rule the `sports:read` scope add before the next re-auth (Q205, OWED), and cut the `user_knowledge` retirement brief (brief 2, Q181, OWED, settled GO since 27 Sep). Neither needs Code first.

**Things the next reader should know.**
- **The sweep's counts are the parser's, not the brief's.** Use `scripts/gov_dialects.py` against a store file, or the weekly status run; the brief's 134 → 115 held for health-app, its DONE figures did not.
- **Q173 now carries Q129's remainder.** Its per-reader ruling covers `context_builder._section_health_connect` (unguarded HC sleep duration and the all-day median), the check-in prefill's `passive_sleep_min`, and `routers/recovery.py` (whose adopt-or-delete stays on Q151). Q224 now carries the admission fork; it fires on a second live sleep writer.
- **Q42 has no live row here.** If health-connect-app Q19 closes or is dropped, #460's do-not-revisit clause says the transfer has no target.
- **Cross-references left as history:** Q233's "A ruling touches" line still cites Q129; a few open rows still cite Q42, Q83 and Q129 by number.
- **Unverified by Code:** the HCA Q18 citations to health-app #405, #406 and #449 (carried from the brief, marked as such on the row; health-app's own copies of those decisions were read); that Railway recorded SKIPPED for both merges (not read).
- **Environment:** the backend suite cannot run locally here (dependencies not installed); CI is the only run of it. The first `git push --delete` of the sweep's remote branch failed with "failed to push some refs" (cause not diagnosed); by the next check the remote branch was gone, and the second branch's delete found "remote ref does not exist". health-connect-app's remote branch was also gone by this close-out. Local branches of both clones carry no unique commits (`git cherry` empty).

**What was NOT touched (named so absence does not read as finished).**
- **Every feature lane stood still.** Nothing in `backend/` or `frontend/` changed in this session. The appointment brief's reconcile leg (the unbuilt part of **Walk in**, NEXT), the Q231 RPE-fallback build (OWED, gate not open), the Q239/Q242 Garmin Personal API owed items (M2, PR-B, the user 4 pk check, the payload-shape probe), the Q199 HRmax benchmark test, the Q205 Polar re-auth, the Hevy programme and routines, the companion app's own code, and the `health-connect-app` Q19 12-hour-clock defect all stayed where they were.
- **Pattern to say out loud.** This session was governance only. The previous close-out (25 Oct) went to a product behaviour (#445), but the sessions before it went to the layer under the product (Q27 taxonomy, the rotation runbook, the Railway incident record), and this one went to question hygiene. A sweep that shrinks the live list from 134 to 112 makes the next governance session look cheaper than the next feature one; it is not. The live list is now 112 rows, 7 of them OWED, and the gating items for Know, Walk in and Loop are the operator's OWED rows, not Code's.
- **Questions not re-read this session** (so their text may carry stale premises like the seven just closed): every live question outside the 14 re-scoped, Q151, Q135, Q173, Q224 and the closed set. The sweep reviewed all 148, but only the rows named in the brief were edited.

**v1-triage of the NOW lanes.** The sweep touched no lane, so this is the standing check only. Rows that state their own "Serves" clause (Missed-PM catch-up through Typed constraints, and HC zones) are not repeated here. Rows without one: the exercise-tag seed (#339), CBT-I Q45 nap attribution (#219) and CBT-I manual evaluation trigger (#213), all DONE landings that serve no v1 test on their face and sit in NOW only as landed history, so they are candidates to move out of NOW, not to demote as work; the Appointment brief row, which serves **Walk in** (test 3 MET, #386; reconcile leg unbuilt); and the cross-repo `#NEXT` / number-at-merge extension (FEEDBACK §20), which serves no v1 test and sits in NOW only because #112 pins cross-repo debt there. The struck cross-repo rows serve none and are discharged. No demotion is made here.
