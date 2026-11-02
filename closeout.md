# Close-out — 2 Nov 2026: in-app per-session sRPE (`DECISIONS_LOG` #475)

## Real commits this session

Session opened at health-app master `59ba1c2` (the merge of PR 577). Maxima at open: `DECISIONS_LOG` #474, no open `fork` issue (REST read, empty). At close: master max #485 (#476 to #485 are other sessions' landings; this session's is #475), still no open `fork` issue, and no issue changed during the session. One issue was filed at this close-out: GH#593 (`stamp`, two-way).

The twelve commits of this session, by the session trailer (`git log --reverse --format="%h %ad %s" --date=short --grep=<session> 59ba1c2..origin/master`):

```
60ca035 2026-10-31 feat(srpe): Pilates is a counted session (operator ruling; supersedes #322 S1/S3 for Pilates)
25e5b14 2026-10-31 feat(srpe): in_app signs the store contract; one CR-10 per counted session, window from the server's bout
1469fef 2026-10-31 feat(srpe): retire day_fill; a session no source rated reads unrated (R2)
614242e 2026-10-31 feat(srpe): per-session read and write routes for the cards
06d0034 2026-10-31 feat(mcp): get_recent_sessions renders the door's rating on Hevy workout lines, once per workout
aa4d497 2026-10-31 feat(srpe): repoint the display readers from the whole-day RPE to the door's per-session ratings
b1071be 2026-10-31 feat(srpe): earlier-sessions read for the backfill, and a real-state fixture for the card tests
723b06a 2026-10-31 feat(srpe): the close-out and the AM catch-up rate each session; the day question is gone (R3, R4)
58b8740 2026-11-01 gov(srpe-in-app): ruling #475, in-app per-session sRPE; day fill retired; Pilates counted
6ac215d 2026-11-01 gov(srpe-in-app): terminal state for the merge - the hold is lifted on the operator's instruction
7167f97 2026-11-01 gov(srpe-in-app): deploy check recorded for #475 (PR 578, merge 19d5d33)
114653a 2026-11-02 gov(srpe-in-app): operator check recorded; #475 How-you-know complete, rows DONE
```

The three merges of those branches onto master (`git log --first-parent`):

```
19d5d33 Merge pull request #578 (code and the #475 entry; merged on the operator's explicit instruction)
4049e69 Merge pull request #579 (deploy check recorded)
36781d6 Merge pull request #592 (operator check recorded)
```

Deploys (#433, matched on `commitHash`): `19d5d33` SUCCESS on both services (backend `f29ffaf0`, frontend `3e5e3ccd`); `4049e69` and `36781d6` SKIPPED on both, as a docs-only merge should be. The live bundle carries `Earlier sessions unrated` (an operator-run PowerShell fetch, reported `True`; this session's network policy blocks the host).

This close-out's own commit, `chore: session close-out`, follows these; it names no hash here because a commit cannot name itself.

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by a pasted brief, `In-App sRPE - Queue Consume 472`, whose rulings R1 to R4 are the operator's. Each step of that brief, against the commit that carries it:

| Brief step | Landed in |
|---|---|
| 1 Contract: `in_app` in `SOURCE_SCALES`, window from the server's bout | `25e5b14` |
| 2 Write route keyed by bout, insert-only, refuses a non-counted key | `25e5b14` (writer), `614242e` (route) |
| 3 Read route for the card, built on `session_ratings` | `614242e`; the backfill's `earlier` read in `b1071be` |
| 4 Retire `day_fill`; `srpe_needed`; the residual's `partial` | `1469fef` |
| 5 Cards: close-out, catch-up, collapsed backfill, day question removed | `723b06a` |
| 6 Tests (the six named, and the §48 flow test from the real state) | in each commit; the generated fixture in `b1071be`; the card flow tests in `723b06a` |
| 7 DECISIONS_LOG entry | `58b8740` (#475) |
| 8 BRANCHES row, CLAUDE.md pointer, ROADMAP | `58b8740`; terminal state `6ac215d`, `7167f97`, `114653a` |
| LOG: operator check after deploy | recorded in `114653a` |

Departures from the brief, each reported at the time and none folded into prose:
- **Two VERIFY divergences, ruled by the operator.** Five readers of `daily_records.session_rpe`, not two (repointed in `aa4d497`); and `get_recent_sessions` carried no rating on a Hevy-only line (fixed in `06d0034`).
- **Pilates counted** (`60ca035`), ruled by the operator when the brief's "Hevy plus Pilates yields two asks" could not hold on the counted set. This made the PR a one-way door, so it held for the operator's instruction instead of self-merging.
- **The #475 heading** was resolved at PR open, not left `### #NEXT`, because the placeholder guard fails any PR carrying `#NEXT`.
- **The backfill bound** was my pick: the 14 days before the card's day, never before 2026-10-18.

Provisional: nothing decided and uncommitted at this point. Two things sit outside the tree and are therefore only as durable as their source: the backfill rating of the 31 Oct pair is operator-reported (Code did not observe it, and the backfill no longer lists them), and GH#593 lives on the tracker.

## Cold-resume handoff

**Next action (the single clearest).** The operator rules two small things so Q231 can be built to a settled definition ahead of its January 2027 deadline: (1) confirm GH#593's proposed answer (Pilates stays in Q231's low-intensity class; the conditioning class is defined by its own list, not "except the #322 S3 set"); (2) say whether `in_app` ratings count toward Q231's gate of 10 global pairs, since Q231's ruled entry route is Garmin-only ("no manual path") and #475 added one. Nothing else is queued for Code.

**Current sprint (`ROADMAP.md` NOW).** Twenty-five lanes: fifteen lead with DONE, ten are open. Open, with owner: Q231 RPE fallback (Code, once the gate opens: at least 10 global pairs, live before club preseason, January 2027; nothing built); Source hierarchy (Luke); Polar sport-id relabel (OWED, remaining limbs); HC sync reliability (OWED, the #371 overlap proof); Garmin self-evaluation read, first live run (operator); Injury clearance (operator); Aerobic ingest automated (operator check); Session fidelity G6 (operator, after deploy); the cross-repo shared-block edit (OWED, pinned in NOW by #112); HC zones, Q159 stage 2 (Code, low priority). The in-app sRPE capture lane is DONE → #475.

**Open `fork` issues.** None (REST read at close). Open `stamp`: GH#593, filed at this close-out (proposed answer stands and is acted on by the next PR touching Q231 unless the operator objects).

**Design docs not in a terminal state.** `docs/design/` 0001 canonical exercise layer, 0004 load-model routing and gaps, 0005 HR input layer, 0006 sleep writers and admission, 0007 in-app chat architecture (all `ideation`); 0002 plan-log reconciliation, 0003 constraints engine tier, 0008 SpO2 detector and guardrail (all `discussion`).

### What was NOT touched

This session was one lane, effort capture, inside the Fitness module. Everything below stood still, and a reader should not infer from this file that it is queued or finished.
- **The consumers of what was captured.** `psychological_residual` has no production caller (a grep finds tests only; its block-level consumer is deferred), and Q231's imputed-load fit is unbuilt. This session built the capture and the read door for consumers that do not exist yet. That is the same pattern as an instrument built ahead of the thing it measures, so the next sRPE-adjacent session should be the consumer (Q231), not more capture.
- **Q231 itself**, and the two questions GH#593 and the next-action line put to the operator. The residual's history also changed (days paired only by a whole-day value left the felt series); Code could not measure how many of the operator's days that was, so the size of that change is unknown.
- **Medical Protocol and Decision Support.** CBT-I (block state, titration), labs and the interpretation layer, appointments, and the injury-clearance sweep did not move. The operator-owed lanes in NOW above did not move either.
- **Session-grain gaps this build left by design:** a counted session with no start or duration cannot be rated and keeps `srpe_needed` true; a session older than the 14-day backfill can no longer be rated in the app; `daily_records.session_rpe` stays as a column written and read by nothing, and dropping it is not built.
- **Governance and status-tooling landings are a large share of recent decisions.** By their titles, #471 to #473, #483 and #485 are governance or status-model work; the feature landings in the same span are #474, #475 and the wake-day capture (#477 to #479). None of them advanced the operator-owed lanes above.

### v1-triage (which v1 test each NOW lane serves)

Read from each row's own "Serves" claim; nothing here is a new ruling.
- **See:** Data freshness and the home load card (DONE); Plan/schedule and recent-sessions tools (DONE); Garmin overnight SpO2 (DONE); RPE fallback Q231 (OWED); Source hierarchy (OWED); HC sync reliability (OWED); Aerobic ingest automated (OWED); HC zones Q159 stage 2 (OWED).
- **Know:** Source-neutral sRPE store and In-app sRPE capture (both DONE); Polar relabel (OWED); Garmin self-evaluation read (OWED); Phase posture split (DONE, one operator read owed); Phase-change form (DONE); Injury clearance (OWED); Garmin account repair (DONE); Typed constraints (DONE).
- **Loop:** Wake-day capture (DONE); Missed-PM catch-up (DONE); CBT-I titration direction (DONE); Session fidelity (built, G6 owed).
- **Serves no v1 test:** CBT-I Q45 nap attribution (DONE), CBT-I manual evaluation trigger (DONE), Training v0.1 exercise tags seed (DONE): all three are finished and sit in NOW only because DONE rows are never moved out. The cross-repo shared-block lane (OWED) serves none and sits in NOW because #112 names ROADMAP NOW the canonical home for cross-repo debt, which is a stated reason, not momentum.
- **Demotion candidates:** the fifteen DONE rows are not active work and ride NOW by momentum; the three above that serve no test are the clearest. The August and September ones (#213 and #219 in August, #339 on 27 Sep) are the oldest. ROADMAP has a "Moved from NOW" precedent for exactly this.
