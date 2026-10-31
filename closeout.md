# Close-out — 31 Oct 2026: question layer, Phase B (`DECISIONS_LOG` #468, #469); the questions move to issues and docs, `OPEN_QUESTIONS.md` is deleted

## Real commits this session

Session opened at health-app master `0b9790e` (the merge of PR 473). Maxima at open: `DECISIONS_LOG` #467, `OPEN_QUESTIONS` Q248, 110 headings above `## CLOSED`, the eight Phase A labels present. `git log --first-parent --format="%h %ad %s" --date=short 0b9790e..origin/master` on master:

```
bf571b6 2026-10-31 Merge pull request #563 from Easty11/claude/fervent-dirac-dp2xil
aa636d2 2026-10-31 Merge pull request #474 from Easty11/claude/fervent-dirac-dp2xil
```

and the commits those two merges carry (`--no-merges`):

```
13e6106 2026-10-31 gov(question-layer): migrate questions to issues and docs, delete OPEN_QUESTIONS.md, #468 #469
dcc9c79 2026-10-31 chore(question-layer): build label, closeout sweep, runbook section
7f3cd52 2026-10-31 fix(question-layer): do-now resolutions (Q28 Q52 Q136 Q140 Q147 Q171)
```

GitHub-side and not in any commit: the `build` label (colour `0052CC`), and 87 issues, GH#476 to GH#562, created by a one-off script kept in the session scratchpad and not committed (43 `stamp`, 12 `build`, 6 `verify`, 8 `design` pointers, 18 closed `not_planned` with `abandoned`). A REST read after the run found exactly those, no `fork` issue, 69 open and 18 closed.

Both PRs opened ready-for-review and merged with the head SHA pinned. PR 474 (`7f3cd52`, the six code fixes) was green on all three checks; backend deploy `SUCCESS`, frontend `SKIPPED` on `aa636d2`. PR 563 was green on all three; master's decisions max was re-read at 467 immediately before the merge, so #468 and #469 stood. Deploy (#433) for `bf571b6`: frontend `SKIPPED`; backend `SUCCESS`, not `SKIPPED`, because the guard's updated tests sit in `backend/tests/` inside the `/backend/**` watch path. No application code changed in that merge. Both matched on `commitHash`.

This close-out is a third PR (this branch, restarted from master `bf571b6`): `closeout.md` and `BRANCHES.md` only.

## Pending-queue reconciliation

No `PENDING` item was carried in: the session ran from one chat-ratified brief and its triage table, not a `;cc` queue. Nothing decided is uncommitted. The ratification (operator, 31 Oct 2026: every triage row unchanged, including the six fork leans) is recorded in #468 and #469.

## Cold-resume handoff

**Next action.** Question layer Phase C, a separate brief from an HCA-rooted session: propagate the shared-rule edits (the Phase A edits 4a to 4g, plus this phase's Filing-a-question bullets for `build` and the `GH#N` citation form, the folded Holds bullet, and the Open and `;cc` wording) verbatim to `health-connect-app`'s `CLAUDE.md`, freeze and migrate HCA's `OPEN_QUESTIONS.md`, and carry Q87's parity declaration. Two health-app facts Phase C must respect: (1) `scripts/check_governance_placeholders.py` here has lost its question arm, so HCA's copy differs until HCA's file goes, and `.github/workflows/governance-guard.yml` needs no edit (it never named the file); (2) `scripts/gov_dialects.py` carries `QUESTIONS_RETIRED = {"health-app"}`: add HCA to it when its file is deleted, and the remaining `OPEN_QUESTIONS` names in `gen_governance_view.py`, `gen_status_model.py` and `status_diff.py` can then go.

**Open `fork` issues.** None (REST read, 31 Oct 2026). All 87 issues are `stamp`, `build`, `verify`, `design` or closed `abandoned`.

**Design docs not in a terminal state.** Eight, none committed: `0001` ideation, `0002` discussion, `0003` discussion, `0004` ideation, `0005` ideation, `0006` ideation, `0007` ideation, `0008` discussion (`grep -l "State:\*\* \(ideation\|discussion\)" docs/design/*.md` also matches `0000-template.md`, whose State line is the placeholder). Their Proposal sections read "none yet" except `0002`, which carries Q197's proposal verbatim.

**The stale action will close real work on 30 Dec 2026 unless someone acts.** Every issue was created on 31 Oct, so the 53-day label lands about 23 Dec and the 7-day close about 30 Dec, for any issue not touched, not `pinned` and not `design`. That covers all 43 `stamp` issues (by design: a stamp is acted on by the next PR touching the area), but also eight `build` issues that hold ratified rulings and carry no `pinned` label because the triage table gave them none: Q58, Q66, Q118 and Q170 (the one-way-door rulings awaiting a migration PR) and Q135, Q139, Q181 and Q191. Two `verify` issues are likewise unpinned: Q100 (the table says stale-close is fine) and Q244. The labels are as ratified and were not changed; deciding whether the eight `build` rulings should be `pinned` is an operator call before then. Nothing is lost if one does close: the ruling and the original entry are in the body and the issue can be reopened.

**Operator items, surfaced and not acted on.**
- Q191 (GH#529): the six constraints that share `review_by` 2026-10-26 are past it. MCP `get_findings` does not serve constraints (it returned two injury findings), so the check is a read of the active `type='constraint'` rows in `user_knowledge_entries` whose `value.review_by` is on or before today (the date `typed_entries` compares against at `backend/typed_entries.py:109`).
- Q109 (GH#490): the "row 30" read that settles the reported instance of `review_when.metric`. `get_findings` returned no row 30 either; it needs the prod `findings` table read, which this session could not make.

**Not verified.** The stale action's first scheduled run against these issues; whether the mapping table in #468 is read correctly by whoever next cites a `Qn` (a closed entry resolves through git at `d340104`, #468 item 6, not through the table); the gap in the triage table that gave `build` (except the four former forks), `verify` and `design` rows no Door, so those issue bodies say "not classified" rather than carry a guess. Q135 drops a column, which `CLAUDE.md` calls a one-way door, yet its issue says "not classified"; classify it before its trigger fires.

**Two things a later session should know.**
- Two sentences of the brief's gate list could not hold, and the PR said so: `grep -rn OPEN_QUESTIONS` is not clean in `scripts/` (the HCA-facing tools still name it), in `ROADMAP.md`, `HANDOFF.md` and `METRICS.md` (historical rows), in code comments citing `OPEN_QUESTIONS Qn`, and once in `CLAUDE.md` (the #467 Recent-landings pointer, which clears at the next landing's trim). `.github/` and `.espanso/` are clean.
- PR 475 (`gov(final-wake)`, another session, `claude/quirky-cerf-tzmikx-wake`) was open and `dirty` when checked, before this phase's merge. It amends #466 in place and adds a `BRANCHES.md` row, so it conflicts with this phase's new top rows. It is that session's to rebase; nothing here blocks it.

### What was NOT touched

Phase B is governance plus six defect fixes, and it was queued as more governance (Phase C next). Product work stood still beyond those six fixes.

- **Stamp, build and verify issues were created, not executed.** Q189's capture UX, Q195's sync-ownership fix, Q96, Q103, Q174, Q178, Q214 and Q241 (the migrations), Q58, Q66, Q118 and Q170 (the one-way releases): none was started.
- **v1 tests.** See / Know / Walk in / Loop: no lane moved. The six fixes touch Know-adjacent reads (AEST day keys on the MCP session windows, the load transform's non-finite guard) and nothing was promoted in NOW.
- **The CBT-I side.** No change to the engine, titration or the I1 firewall; the only CBT-I touch is two `BRANCHES.md` rows flipped to DONE.
- **`health-connect-app`** was not edited (Phase C).
- **Consecutive-session pattern.** Several recent sessions have gone to the instrument (the question layer, the sweeps, the close-outs, the `;cc`/`;sc` snippets) rather than the thing instrumented. This one added the migration of the question store itself. The next governance session is Phase C; the last product landing before this was PR 469 (#466, 29 Oct).
- **Operator-owed items from earlier rows** are unchanged and not re-verified: the `.espanso/cc.yml` copy to `%APPDATA%\espanso\match\` (this phase rewrote its `;cc` text, so the installed copy is now stale), the `.espanso/sc.yml` copy and `;sc` deletion (#463), the `CONSOLIDATED_GOVERNANCE_VIEW.md` deletion from project knowledge, and the NOW rows reading OWED (operator). `feat/srpe-source-neutral-store` is landed (`5d13046`) and stays OWED for its post-deploy reads.

### v1-triage of NOW

`ROADMAP.md` NOW was not edited this session and was not re-read for the v1 test each lane serves; the 31 Oct Phase A close-out's triage stands (`git show 0b9790e:closeout.md`). The only `ROADMAP.md` changes were the Phase B row leaving NEXT and two LATER rows (Q148, Q221), neither of which serves a v1 test. **Honest limit:** this is a pointer, not a re-derivation.
