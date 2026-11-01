# Close-out — 31 Oct 2026: question layer, Phase C3 (`DECISIONS_LOG` #471); the questions store is gone from the status tooling in both repos

## Real commits this session

Session opened at health-app master `b7743c3` (the merge of PR 567). Maxima at open: `DECISIONS_LOG` #470, no open `fork` issue (REST read). `git log --first-parent --format="%h %ad %s" --date=short b7743c3..origin/master` returns one line:

```
4378090 2026-10-31 Merge pull request #569 from Easty11/claude/affectionate-shannon-jgsrtp
```

and the commits that merge carries (`git log --format="%h %s" b7743c3..claude/affectionate-shannon-jgsrtp`, before the branch was restarted):

```
1cc7fe2 gov: question layer Phase C3 - both question stores retired, status tools read issues or nothing (#471)
3e8b7d2 chore: retire the questions store from the status tooling in both repos (Phase C3)
```

This close-out's own commit and merge are not listed: a commit cannot name its own SHA, and the merge is the last act. Read them with `git log --first-parent --grep=session.close-out`.

GitHub side: GH#568 created (`stamp`, two-way): the shared block's Session rituals names `scripts\gen_governance_view.py`, a health-app-only script. No issue closed. `health-connect-app` was not edited.

Gates, all met on PR 569 before the merge: backend suite 3977 passed / 3 skipped (a full-depth clone; a shallow one fails collection on `git show 8324a28`, the reason CI uses `fetch-depth: 0`); `scripts/tests` 15 passed; both `--self-check` runs pass; `gen_governance_view.py` exits 0 against both masters (health-app `b7743c3`, health-connect-app `858a990`), six store sections and no questions section; `grep -rn OPEN_QUESTIONS scripts/ backend/tests/` returns only the guard comment; the guard is AST-identical to HCA's copy modulo docstrings and the one repo-local `main()` advisory string (`CLAUDE.md` declares both repo-local). Deploy (#433), matched on `commitHash` `4378090`: backend `SUCCESS`, frontend `SKIPPED`.

## Pending-queue reconciliation

No `PENDING` item was carried in from a chat close-out: the session's input was the C3 brief, six steps.

| Step | State | Evidence |
|------|-------|----------|
| 1. Status tools lose the questions branch; `QUESTIONS_RETIRED`, `has_questions_store` go | DONE | `3e8b7d2` |
| 2. Guard comment reworded; code identical to HCA's | DONE | `3e8b7d2`; the AST comparison is in the gates above |
| 3. `gen_governance_view.py` run once against master | DONE | exit 0; output under `build/`, gitignored; not run at close-out |
| 4. Shared-block stamp filed | DONE | GH#568 |
| 5. Ruling entry | DONE | `1cc7fe2`, `DECISIONS_LOG` #471 (master max was 470 at the merge) |
| 6. `BRANCHES.md` row, Recent-landings pointer, land, `/closeout` | DONE | row and pointer in `1cc7fe2`; landed as `4378090`; this close-out |

Where the work departed from the brief, so the next reader does not have to find it:

- **`QUESTIONS_RETIRED` was never extended to HCA.** Step 1 says add it, then delete it if nothing else reads it. Nothing did, so the commit deletes it outright. Consequence: #471's Reverse-by cannot say "re-add the repo to the set" as the brief worded it; it says to revert the `chore` commit.
- **More was removed than the three named branches.** The question parsers, `_tally_stateful`, the `status_diff.py` renumber handling (reachable only through the questions identity key) and the `retired` markers went with them. The question grammar in `gov_dialects.py` (`QUESTION_HEADING`, `question_states`, `entry_state`, `split_inline_state`) is left in place and now unread; deleting it is a separate small change, not made here.
- **The grep gate needed five comment edits in `backend/tests/`.** Six files cited `OPEN_QUESTIONS` by name; the guard-test docstring is reworded and five historical citations now read "retired-store question Qn" (comment-only; the Q-number provenance is kept). This is why the backend built.
- **The negative tests avoid the token.** They assert `"questions" not in text.lower()`, so the same grep that gates the tools does not trip on the tests that guard them.
- **The status model no longer emits a `questions` key** (schema_version stays 1). Older snapshots in the out-of-tree `_status` directory keep theirs; nothing reads it.

Nothing decided is uncommitted.

## Cold-resume handoff

**Next action.** The question layer's three phases are complete, so the next session should leave governance. The clearest owed item that is not an operator's alone is the **source-neutral sRPE post-deploy reads**: compare row counts of `session_rpe_observations` and `garmin_activity_selfevals` for user 1, then read the first 02:00 sweep's inserts under source `garmin` (`BRANCHES.md` row `feat/srpe-source-neutral-store`, ROADMAP NOW row; Code or operator, a prod read per the standing rule that data verification is a Postgres query against Railway).

**Open `fork` issues.** None (REST read, 31 Oct 2026).

**Open `stamp` issues touched or carried.** GH#568 (new, shared-block sentence; settled by the next propagation's byte-identity check) and GH#565 (the `land` alias refuses to run from master or main; carried from the C1 hand-off, still open).

**Design docs not in a terminal state.** Eight, none committed: `0001` ideation, `0002` discussion, `0003` discussion, `0004` ideation, `0005` ideation, `0006` ideation, `0007` ideation, `0008` discussion. Unchanged this session.

**Current sprint.** ROADMAP NOW is unchanged by this session. Its open rows, with the v1 test each names (the `Serves` text of the row, read from `ROADMAP.md`):

| NOW lane | v1 test it names |
|----------|------------------|
| Source hierarchy (#365) | See, Know |
| Polar sport-id relabel, H10-vs-Hevy facts | Know, See |
| HC sync reliability | See, Loop |
| Garmin self-evaluation read, first live run | Know, Loop |
| Source-neutral per-session sRPE store (#424) | Know, Loop |
| Injury clearance (operator) | Know, Walk in |
| Aerobic ingest automated (operator check) | See, Loop |
| Session fidelity (Brief A + C.1), G6 owed | Loop, Know |
| HC zones (Q159 stage 2), low priority | See, Know |
| RPE fallback for unrecorded sessions (Q231) | none named in the row's opening text; not asserted here |
| Cross-repo: extend the `#NEXT` rule beyond DECISIONS entries | none; a governance debt pinned in NOW by #112 |

The v1 section tags See, Know and Walk in as MET; **Loop carries no MET tag**, so it is the open v1 test, and five of the nine lanes that name a test list it. Demotion candidate surfaced, not decided: the cross-repo `#NEXT` row serves no v1 test and sits in NOW only because #112 names NOW as the home for cross-repo debt.

**What was NOT touched.** All product work. Nothing under `frontend/`, no migration, no engine, ingestion, CBT-I or brief code; no production path changed (the backend rebuilt only because `backend/tests/` comments changed). Every NOW lane above stood still, and so did the questions that gate them (Q231's gate, Q203, Q205, Q208, Q214, Q199 and the operator-owed checks listed in the NOW rows; the questions themselves are GitHub issues now, reached through the Q-to-destination map recorded with #468). Five consecutive sessions (question layer Phases A, B, C1, C2 and C3) went to the instrument that holds and routes the work, not to the thing it routes. That is finished now, so the risk is the opposite one: a session opening on this hand-off reads a governance queue because governance is what is legible. The product queue is the NOW table above.

**Left unmade, deliberately.** The unread question grammar in `gov_dialects.py` (see the departures list). GH#568's move of one sentence below END SHARED LOOP RULES waits for the next shared-block edit, per its stamp.
