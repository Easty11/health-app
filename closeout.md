# Close-out — 31 Oct 2026: question layer, Phase A (`DECISIONS_LOG` #467); governance and workflow only

## Real commits this session

Session opened at health-app master `2a1ec18` (the merge of PR 471). Maxima at open: `DECISIONS_LOG` #466, `OPEN_QUESTIONS` Q248 (the brief expected #461 and Q246; time had moved both). `git log --format="%h %ad %s" --date=short 2a1ec18..HEAD` on master:

```
d340104 2026-10-31 Merge pull request #472 from Easty11/claude/fervent-pasteur-67jbo6
1f400cd 2026-10-31 gov(question-layer): door-class merge disposition, Filing-a-question, freeze OPEN_QUESTIONS, #467
d1008cd 2026-10-31 chore(question-layer): labels, stale workflow, design-doc store
```

Before the branch, GitHub-side and not in any commit: the eight labels (`fork`, `stamp`, `verify`, `watch`, `design`, `pinned`, `stale`, `abandoned`), created through `gh api` (17 labels now: the eight plus the nine defaults).

Landed through PR 472 (ready-for-review, never draft), merged as `d340104` with the head SHA pinned, after `placeholder guard (POSIX)`, `backend tests (pytest)` and `frontend tests (vitest)` were green on `1f400cd`. Master's decisions max was re-read at 466 immediately before the merge, so #467 stood. Deploy (#433): both services recorded SKIPPED for `d340104`, matched on `commitHash` (service ids `27695d21` and `8a3e506f`); no record missing. Post-merge: `stale` is an active workflow; `docs/design/` holds the README and `0000-template.md`; the `OPEN_QUESTIONS.md` diff is exactly the three banner lines; no heading-anchored `#NEXT` survives in either store; nothing under `backend/`, `frontend/` or `backend/migrations/` changed. Every removed line fell inside a region the change declared (#176 (c)).

This close-out is a second PR (this branch, restarted from master `d340104`): `closeout.md` and its `BRANCHES.md` row only.

## Pending-queue reconciliation

No `PENDING` item was carried in: the session ran from one chat-ratified brief, not a `;cc` queue. Nothing decided is uncommitted. The ratification (operator, 31 Oct 2026: "I like it", on the proposal #467 implements) is recorded in #467 itself.

## Cold-resume handoff

**Next action.** Question layer Phase B: chat produces the triage table for the live `OPEN_QUESTIONS.md` entries (110 above `## CLOSED` on 31 Oct 2026: 105 OPEN, 5 OWED), and a Code session migrates them to issues (`fork` / `stamp` / `verify` / `watch`) and `docs/design` docs, then deletes the file. Phase C (propagate the shared-rule edits 4a to 4g verbatim to `health-connect-app`, plus its own freeze and Phase B) follows as a separate brief from an HCA-rooted session. Both are in `ROADMAP.md` NEXT, UNSTARTED. Until Phase B lands, `OPEN_QUESTIONS.md` is read-only and holds the whole live question queue.

**Open `fork` issues.** None. No issue of any kind exists yet (zero non-PR issues, checked by REST on 31 Oct 2026). The #467 retirement trigger (more than about 15 open `fork` issues at two consecutive session opens) cannot fire before Phase B.

**Design docs not in a terminal state.** None in substance. `grep -l "State:\*\* \(ideation\|discussion\)" docs/design/*.md` matches only `0000-template.md`, whose State line is the placeholder `ideation | discussion | committed | abandoned`. The existing `docs/*design*.md` files were not moved (Phase A rule).

**Two things the next session should know about the new rules in a cloud session.**
- GraphQL is blocked there, so the Open ritual's literal command (`gh issue list --label fork --state open`) is refused. The working equivalent is `gh api 'repos/Easty11/health-app/issues?labels=fork&state=open'`; `gh label list` and `gh pr create` fail the same way. The shared rule was not reworded (that is Phase C territory, and it is correct on the operator's machine).
- Not yet exercised: the stale action's first scheduled run (no issue exists for it to touch), and the first real `stale` to `abandoned` transition. `.github/workflows/stale.yml` also carries `workflow_dispatch` and a cron of `17 3 * * *`, both chosen by Code (the brief said only "daily").

**Governance nits, not gates, left for Phase B or C.** `CLAUDE.md`'s `;cc` bullet and `.espanso/cc.yml` still mention `OPEN_QUESTIONS.md` (outside the declared regions). The old Holds bullet (schema migration; anything told to hold) now overlaps the door-class bullet; harmless. `docs/design/README.md` has a short "who moves state" section the brief named but did not word; Code wrote only that Code moves state in the PR, that `committed` is gated by the one rule, and that one-way-door resolutions hold per door class.

### What was NOT touched

This was a governance session, and the next one is queued as more governance (Phases B and C). Product work stood still: no `backend/`, `frontend/` or migration change, and no deploy (both services SKIPPED).

- **v1 tests.** See / Know / Walk in / Loop: no lane moved. Walk in (the appointment brief) is MET (#386) with its reconcile leg unbuilt, in NEXT; Know (weekly resolver) MET (#392). Nothing about either changed.
- **The CBT-I side.** No change to the engine, titration, or the I1 firewall. #466 (30 Oct) closed the partial-night note; the CBT-I diary, titration and the deliberate absence of a device signal there are as #466 left them.
- **Open questions gating product work.** None was read, reworded or closed (the brief forbids it). They are all still in the frozen file; the ones the NOW rows name (Q231 RPE fallback, Q203 source hierarchy, Q205 and the Q199 HRmax test, Q208 and Q214 for HC sync, Q159 stage 2's single-row bout read) stood still.
- **Operator-owed items from earlier rows** are unchanged and not re-verified: the `.espanso/sc.yml` copy and `;sc` deletion (#463), the `cc.yml` copy and the HCA propagation of #461's lines, the `CONSOLIDATED_GOVERNANCE_VIEW.md` deletion from project knowledge, and the NOW rows reading OWED (operator).
- **`health-connect-app`** was not edited (Phase C).
- **Consecutive-session pattern.** Several recent sessions have gone to the instrument (the question layer, the sweep, the close-outs, the `;cc`/`;sc` snippets) rather than to the thing instrumented. The last product landing was PR 469 (#466, read-side, 29 Oct) and before it PR 467 (#465) and PR 461 (#464, PR-B); the Garmin line is quiet and clean. The next two queued briefs (B and C) are also governance. Say so rather than letting B and C ride by momentum: Phase B has a payoff (it deletes a 6,800-line file and makes closure cheap) but it is not a v1 test.

### v1-triage of NOW

The rows below state which test they serve; the ones that state none are listed after.
- **Serve See:** Data freshness (#405, #406), Plan/schedule MCP tools, RPE fallback (Q231), Source hierarchy (#365), HC sync reliability, Garmin overnight SpO2 capture (raw, no consumer), Aerobic ingest automated.
- **Serve Know:** Polar sport-id relabel, Garmin self-evaluation read, Source-neutral sRPE store, Phase posture split, Phase-change form, Injury clearance, Garmin account mix-up repair, Typed constraints G6, Session fidelity.
- **Serve Loop:** Missed-PM catch-up, CBT-I titration direction (#445, #446), Session fidelity (with Know), HC sync reliability (with See).
- **State no v1 test, and are candidates to move out of NOW by momentum, not by merit:** the DONE rows `Training: seed the v0.1 exercise tags` (#339), `CBT-I: Q45 nap day-attribution` (#219) and `CBT-I: manual witnessed evaluation trigger` (#213); the struck DISCHARGED `Cross-repo` rows (seven of them, each struck and marked DISCHARGED); and the one live cross-repo row (the `#NEXT` rule extension, OWED, re-scoped 17 Aug) which is shared-loop debt, serving no v1 test, and is pinned in NOW by #112, not by a v1 reason. Check each DONE row for an owed limb before moving it. The `Appointment brief` row is the Walk in lane (MET, #386; reconcile leg in NEXT).
- **Honest limit.** The "serves" reading above is from each row's own text (first cell and its "Serves" sentence); I did not re-read every row's full body or re-verify any OWED limb against prod.
