# Close-out — 31 Oct 2026: question layer, Phase C1 (`DECISIONS_LOG` #470); stale exempts `build`, the shared-block source edits are on master

## Real commits this session

Session opened at health-app master `da5f492` (the merge of PR 564). Maxima at open: `DECISIONS_LOG` #469, 87 issues GH#476 to GH#562, no open `fork` issue. `git log --first-parent --format="%h %ad %s" --date=short da5f492..origin/master` on master:

```
5c3e322 2026-10-31 Merge pull request #566 from Easty11/claude/great-cray-wjh02n
```

and the commits that merge carries (`--no-merges`):

```
9ad4b5b 2026-10-31 gov: question layer Phase C1 - repo-generic Open command, parity artefacts, GH#N citation rule (#470)
2ffb0bd 2026-10-31 chore: stale action exempts build issues (Phase C1)
```

GitHub-side and not in any commit (REST, one throwaway script in the session scratchpad, not committed):

- `pinned` added to eight issues: GH#505 (Q195), GH#516 (Q234), GH#485 (Q96), GH#486 (Q103), GH#501 (Q174), GH#503 (Q178), GH#508 (Q214), GH#518 (Q241). Q100 (GH#533) and Q244 (GH#536) were left on the clock.
- A Door set, with a comment on each, on eight `build` issues: one-way GH#523 (Q135), GH#528 (Q181), GH#530 (Q231); two-way GH#521 (Q78), GH#524 (Q139), GH#525 (Q156), GH#527 (Q176), GH#529 (Q191). Q58, Q66, Q118 and Q170 already read one-way from Phase B and were not touched. A paginated read afterwards found all eight pins and all twelve Door lines set.
- Comments on GH#490 (Q109: row 30 is `active = f`, the stamp stands) and GH#529 (Q191: seven active constraints past `review_by`).
- New issue GH#565, label `stamp`, two-way: the documented `land` alias refuses to run from master or main (from health-connect-app Q16). Its dry-run evidence is in the body.

PR 566 opened ready-for-review and merged with the head SHA pinned, `--merge`. All three checks were green on `9ad4b5b` (`placeholder guard (POSIX)`, `backend tests (pytest)`, `frontend tests (vitest)`); master's decisions max was re-read at 469 immediately before the merge, so #470 stood. Deploy (#433) for `5c3e322`: `SKIPPED` on both services, matched on `commitHash`, a record on each, which is the expected result for a merge that changes neither folder.

Two slips, both corrected in-session: a script typo (a keyword argument passed to a helper that took none) stopped the Door pass after the Q135 body edit and before its comment, so that comment was posted separately and the rest rerun; and the first merge call passed a SHA padded out from a seven-character prefix, which GitHub refused with a 409 and which changed nothing, before the real SHA was read from `git rev-parse` and the merge went through.

The remote branch `claude/great-cray-wjh02n` could not be deleted by hand (the proxy returns 403 on `DELETE git/refs`), but `git ls-remote --heads origin claude/great-cray-wjh02n` later returned nothing: it was gone after the merge. This close-out is a second PR on the same harness-assigned name, restarted from master `5c3e322`: `closeout.md` and `BRANCHES.md` only.

## Pending-queue reconciliation

No `PENDING` item was carried in: the session ran from one chat brief whose triage table the operator left unmarked, which the brief defines as ratified (the Phase B convention). Nothing decided is uncommitted; the two rulings the session made are in #470, and it records them as two-way doors.

**A ritual was skipped and then run late.** This session did not run `/closeout` after landing because the brief did not ask for it. The operator pointed out that a ritual is not brief-optional; this file is the late close-out. If it recurs, the operator has said it is a `FEEDBACK` line, not a brief line. This session wrote nothing to `FEEDBACK.md`.

**One paste arrived that was not this session's.** The C2 paste (first line `Question Layer Phase C2 - Question Layer Redesign`) was delivered here. It is addressed to a session rooted in health-connect-app, so it was reported back and not acted on (Paste addressing).

## Cold-resume handoff

**Next action.** Run C2: open a Code session rooted in `health-connect-app` and paste the C2 block from its first line. Before it starts, the operator should run the Q20 query (the one operator item that can change what C2 writes): a `com.garmin…` row in `health_connect_record_sources` for `record_type = 'hrv'` flips Q20's lean to a one-week stamp. C2 needs three facts from this session: C1 is `5c3e322`, the decisions max is 470, and the `land`-guard stamp is **GH#565**.

**Phase C order, and what each part owes.**
- **C2** (health-connect-app): copies the shared block verbatim from health-app master, adds the labels and the stale workflow, migrates 13 live questions, deletes its `OPEN_QUESTIONS.md`, makes its guard code-identical with this repo's. Its gate hashes the shared-block slice against this repo's.
- **C3** (back here, ten minutes): add `health-connect-app` to `QUESTIONS_RETIRED` in `scripts/gov_dialects.py`, then drop the `OPEN_QUESTIONS` names from the status tools (`gen_governance_view.py`, `gen_status_model.py`, `status_diff.py`) and keep the "no questions section" tests for both repos. Carry one nit with it: the comment block in `scripts/check_governance_placeholders.py` (lines ~75-79) says health-connect-app still has the `OPEN_QUESTIONS.md` arm, and goes stale once C2 lands.

**Open `fork` issues.** None (REST read, 31 Oct 2026).

**Design docs not in a terminal state.** Eight, none committed: `0001` ideation, `0002` discussion, `0003` discussion, `0004` ideation, `0005` ideation, `0006` ideation, `0007` ideation, `0008` discussion (the grep also matches `0000-template.md`, whose State line is the placeholder). Unchanged this session.

**The stale clock, after C1.** The Phase B handoff warned that real work would be closed by the stale action on about 30 Dec 2026. C1 narrowed that: all twelve `build` issues are now exempt by label (`stale.yml` reads `pinned,design,build`), and eight stamps are pinned. What still ages from 31 Oct, label about 23 Dec and close about 30 Dec: 35 unpinned stamps from Phase B, GH#565, and the verifies Q100 and Q244. That is by design for the stamps (acted on by the next PR touching the area), but each is a ruling that a closed issue still holds in its body, and any can be reopened.

**Operator items, surfaced and not acted on.**
- Q20's query (above), before C2.
- The `land` alias on the operator's machine (Phase C operator item 1): `git config --local alias.land` with the `case` guard from GH#565. The documented alias body in `CLAUDE.md` § Fresh-clone setup is deliberately unchanged here; GH#565 changes it with the next PR that touches that section.
- Seven active constraints past `review_by` 2026-10-26: ids 95, 96, 97, 98, 102, 103, 110, all `confirmed` (operator's prod read; the Phase B handoff counted six, so the count moved). Re-date or resolve through the typed write path.
- Carried from Phase B and not re-verified: the `.espanso/cc.yml` copy to `%APPDATA%\espanso\match\` (its `;cc` text was rewritten in Phase B, so the installed copy is stale), the `.espanso/sc.yml` copy and `;sc` deletion (#463), the `CONSOLIDATED_GOVERNANCE_VIEW.md` deletion from project knowledge, and the NOW rows reading OWED (operator).

**`BRANCHES.md` sweep (Q138).** Three open OWED rows checked: `gov/q238-rotation-ledger` (Status DONE, the outstanding cell is operator-owed), `feat/srpe-source-neutral-store` (landed, `5d13046`; stays OWED on purpose for its post-deploy reads, which are not a landing SHA), `claude/determined-curie-khwfp7` (Status DONE `60b3762`, the outstanding cell is the operator's Strava query). All three remote branches are gone from `origin` and none carries unmerged work; no row was landed-but-unflipped, so no row was flipped. This session's own C1 row was flipped from "merged via this PR" to `DONE 5c3e322`, now that the SHA exists.

**Not verified.**
- That `gh api "repos/{owner}/{repo}/..."` substitutes in a health-connect-app clone. It substituted here (`{owner}/{repo}` returned `Easty11/health-app`), where `origin` is a plain GitHub URL. A clone whose remote has another shape is the case this did not test; C2 must run the same one-line probe in its own clone before it trusts the shared block's Open command.
- That the stale action's first scheduled run (about 23 Dec) treats the `build` exemption as intended. `actions/stale@v11` was not run against it; the `exempt-issue-labels` value was read back from master and parsed as YAML.
- FEEDBACK.md was read by heading only for this close-out, not in full.

**Two things a later session should know.**
- GitHub appears to delete a merged PR's head branch on its own in this repo (PR 474's branch and now PR 566's were both gone after a refused manual delete). That is Likely, not confirmed: it is a setting this session could not read. It matters because `land` passes `--delete-branch`, and a session that sees the proxy's 403 on a manual delete should check `git ls-remote` before concluding the branch lingers.
- Four health-app `build` issues carried their pins from Phase B, and four carried their one-way Doors; Phase C1's brief assumed otherwise. The end state is the one the brief wanted, but the brief's premise about those eight was stale.

### What was NOT touched

C1 is governance plus a workflow exemption, the third governance phase running (Phase A, Phase B, C1), with C2 and C3 queued behind it. Product work stood still.

- **No stamp, build or verify issue was executed.** The eight pinned stamps are held for operator release (Q96, Q103, Q174, Q178, Q214, Q241 are migrations or data-meaning) or for a date (Q195, Q234); none was started. The twelve builds got a Door and nothing else: Q58, Q66, Q118, Q135, Q170, Q181, Q231 (one-way) and Q78, Q139, Q156, Q176, Q191 (two-way) are as ruled and unbuilt.
- **v1 tests.** See / Know / Walk in / Loop: no lane moved. Know, Walk in and See are marked MET in `ROADMAP.md`; Loop is the test with open surface-debt work, and none of it was touched.
- **The CBT-I side.** No change to the engine, titration or the I1 firewall. The operator's accept of the live close-out (NOW row for #445, #446) is unchanged.
- **The ring.** Three health-connect-app items (Q18, Q19, Q24) and health-app's Q176 are pinned to its return; none moved.
- **`health-connect-app`** was not edited. Its C2 is the next session.
- **Consecutive-session pattern.** Phase A, Phase B and C1 have all gone to the instrument (the question layer) rather than the thing instrumented, and C2 and C3 are queued behind it. The last code landing is PR 474 (six defect fixes, 31 Oct); the last feature landing recorded in the prior close-out is PR 469 (#466, 29 Oct), not re-derived here. A governance-heavy week is a reasonable cost to retire a store, but the next session after C3 should be product.

### v1-triage of NOW

`ROADMAP.md` was not edited this session (its header still reads "Last updated: 2026-10-25") and NOW was read from the first 430 characters of each row, not in full. By that read every dated NOW row names the v1 test it serves in its own Notes cell (Know, See or Loop; the Appointment brief row is Walk in, MET). The one live undated row, the cross-repo number-at-merge extension, serves no v1 test and sits in NOW because the NOW heading pins cross-repo debt there (#112); it is the only candidate for demotion and is not demoted here, because it is cross-repo debt rather than a lane. **Honest limit:** this is a read of row prefixes, not a re-derivation; the 31 Oct Phase A close-out's triage stands (`git show 0b9790e:closeout.md`).
