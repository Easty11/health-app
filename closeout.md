# Close-out — 25 Oct 2026: CBT-I titration direction from the mean-SE band (#445) and the operator's refusal path (#446), landed, deployed and verified; governance recorded

## Real commits this session

`git log --format="%h %ad %s" --date=short d660842..HEAD` (session opened at master `d660842`, the merge of PR #431; maxima at open: `DECISIONS_LOG` #444, `OPEN_QUESTIONS` Q238; the brief named #433 and Q233, so it was stale and was re-read, not trusted. Maxima at close: #446 and Q238; master did not advance between the open and the merge, so #445 and #446 held):

- `29b673a` 2026-10-25 feat(cbti): titration direction from the mean-SE band, not TST + buffer (R1, #445)
- `d743a68` 2026-10-25 feat(cbti): operator refusal path - POST /cbti/evaluation/hold (R2, #446)
- `bc7c47d` 2026-10-25 Merge pull request #432 from Easty11/feat/cbti-se-band (all three checks green; opened ready-for-review and self-merged; no schema, both rulings operator-ratified)
- `7654588` 2026-10-25 gov(cbti-se-band): #445 titration direction from the mean-SE band, supersedes #107's rule
- `448b0fc` 2026-10-25 gov(cbti-operator-hold): #446 operator refusal path, extends #118
- the commit of the ROADMAP row, the BRANCHES rows, the CLAUDE.md Recent-landings pointer and this file (`chore: session close-out`), on `gov/cbti-se-band-rulings`, which carries this file

The code PR was cut from `origin/master` in the worktree `.claude/worktrees/cbti-se-band`, because the shared checkout is on `claude/q27-route-i-rep-ceiling-tagpass` (another session's branch, not touched). The two feature commits were re-split once after the first push (`--force-with-lease` on a branch with no PR yet) so that `#445` and `#446` appear in the code comments as real integers rather than placeholders. The remote branch was deleted on the merge; the local one was deleted after.

Deploy (#116, #121): backend `9a1349f8` SUCCESS and frontend `2e776dd9` SUCCESS (both folders changed); the served bundle `assets/index-CTDiRVqw.js` carries `Hold this window`. The live evaluation was read in the prod container, read-only: `extend`, window 477 to 492, lights out 21:33, mean SE 92.34, TST 428, `move_capped` False, `ruleset_version` `cbti-se-band/2026-10-25.1`.

## Pending-queue reconciliation

Input: one operator brief (CBT-I titration direction from SE bands; operator hold on the close-out), with rulings R1, R2, R3. No `PENDING` items were carried from a chat close-out.

- **R1 (SE-band direction).** Landed in `29b673a`, merged in `bc7c47d`, recorded as `DECISIONS_LOG` #445 (`7654588`).
- **R2 (operator refusal).** Landed in `d743a68`, merged in `bc7c47d`, recorded as #446 (`448b0fc`).
- **R3 (one PR, two feature commits, code only).** Held. No migration file and no `models.py` change in the diff; `git diff origin/master --name-only` was checked for both before the push. The brief's `reason` string is stored in the existing nullable `rationale` column.
- **Gates.** (1) Backend suite green in CI; locally 3720 passed with one failure, `test_clock_pin`, which also fails on the clean tree; the placeholder guard is clean. (2) No migration, no `models.py`. (3) `grep -rnw BUFFER_MIN backend` returns zero hits (the bare substring still matches `NON_SLEEP_BUFFER_MINUTES` in `garmin_spo2.py`, an unrelated constant). (4) Both services SUCCESS and the bundle probed. (5) The live evaluation reads as the brief expected. (6) Numbers minted from master's max immediately before the merge.
- **LOG items the brief asked for.** PR 432; merge `bc7c47d`; commits `29b673a` and `d743a68`. The block-1 replay, old and new, and the tests rewritten because they pinned TST + buffer, are in #445's How-you-know. The live payload is in #445's Status.
- **Guard.** The live cycle was not accepted or held. `centre_estimate`, the dither, `CYCLE_NIGHTS`, `MAX_MOVE_MIN`, `SE_FLOOR_PCT` and the converged logic are unchanged.

Nothing decided in this session is uncommitted. Only this close-out is provisional until its own commit merges.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One NOW row added: "CBT-I: titration direction from the mean-SE band, and the operator's refusal path (#445, #446)", DONE with an operator step owed. `ROADMAP.md` "Last updated" now reads 2026-10-25.

**State.** `DECISIONS_LOG` max is #446; `OPEN_QUESTIONS` max is Q238. Questions above `## CLOSED`: 123 OPEN and 6 OWED, by each `**State:**` line's first word. No question was raised or closed; both forks were resolved by the rulings.

**Single clearest next action.** The operator opens the close-out and either accepts the offered extend (477 to 492, lights out 21:33) or holds the window with a reason. This is the operator's act; Code did neither.

**Things the next reader should know.**
- **The extend already sits above the need estimate.** #107's estimate is ~7h30 (450 min) and the live window is 477. #445's revisit clause is two consecutive extends past that estimate under the 90 threshold, so if the 492 is accepted and the next cycle also extends, the clause is tripped.
- **Two behaviours recorded, not ruled** (#445, How-you-know): the converged check runs before the titrate step, so a TST plateau with SE at or above 90 holds and never extends; and a historical replayed cycle is still labelled with the legacy ruleset while its recommendation now comes from the band (replay-only, nothing persisted).
- **The hold route has not been exercised in prod.** It writes an append-only row, and the live cycle is the operator's. The HTTP-layer tests run against the real router and a real ledger; `rationale` is the only place the operator's reason lives, and it is not rendered anywhere yet.
- **Test environment.** `test_clock_pin` (backend) and `Injuries.test.jsx` (frontend, "ancestor June date") fail locally on a clean tree and passed in CI; both are date-sensitive. The suite needs a real `FERNET_KEY`.
- **Shared-checkout hygiene.** A stale zero-byte `.git/packed-refs.lock` (created 08:54 on 25 Oct, no git process running) prints a warning on every ref update from the worktree; the updates still succeeded. It was not removed, because it is in the shared `.git`. The worktree `.claude/worktrees/cbti-se-band` holds a `node_modules` junction to the main checkout's; remove it with `rmdir`, never `rm -rf`, before removing the worktree.
- **Two brief anchors were stale** and were re-read: master's max decision (#444, not #433) and `RULESET_VERSION` (`cbti-basis/2026-10-21.1`, not `2026-09-23.1`).

**What was NOT touched (named so absence does not read as finished).**
- **CBT-I beyond the titration rule:** Q46 (device-versus-diary basis column), Q48 (settling period), Q55 (the four chosen gate constants, still chosen), Q78 (the frequent-napper stall, OWED → #262). The 90 threshold is itself a CHOSEN constant, standing like those.
- **Feature lanes that stood still:** the appointment brief and its reconcile leg, the Hevy programme and routines, the companion app (`health-connect-app`), the MCP OAuth owed items, the cross-repo propagation rows, the Q231 build, and the lab upload and interpretation layers.
- **The Q27 lane** (another session's branch, `claude/q27-route-i-rep-ceiling-tagpass`, was not touched) and every other question above `## CLOSED`.
- **Pattern to say out loud.** This session went to a product behaviour (what the close-out offers), not to the layer under it; the preceding sessions went to the layer under the product (Q27 taxonomy and norms, the rotation runbook, the Railway incident record).

**v1-triage of the NOW lanes.** The new row serves **Loop** (the window moves on the efficiency it produced) and **Know** (a refusal is recorded beside the engine's rejected decision), and states so in its own "Serves" clause. No other NOW row was edited by this session; the rows other sessions added state their own "Serves" clauses, and I add no demotion candidate.
