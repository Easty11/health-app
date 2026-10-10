# Close-out — pm-catchup: a missed nightly close-out is completed from the next morning's AM check-in and lands on the previous day's record (#407; Q226 and Q227 opened); operator check owed

## Real commits this session

`git log --format="%h %ad %s" --date=short 0939eaf..HEAD` (session opened at master `0939eaf`, the brief's design anchor; maxima at open: `DECISIONS_LOG` #404, `OPEN_QUESTIONS` Q223):

- `314fa9a` 2026-10-09 feat(checkin): missed-PM catch-up from the AM check-in (pm-catchup)
- `7cb0f62` 2026-10-09 gov(pm-catchup): record the missed-PM catch-up (#405), open Q224 and Q225, close out
- the merge commit of master into the branch, which resolved the numbering collision and carries this file

PR #357 (ready for review, not draft: `CLAUDE.md` § Merge disposition overrides the harness default). No schema change and no migration, so no hold applies; the PR self-merges on green (`placeholder guard (POSIX)`, `backend tests (pytest)`, and `frontend tests (vitest)`).

**Renumbered at merge.** The branch was cut at `0939eaf` and claimed #405, Q224 and Q225. While PR #357's checks ran, another session landed PRs #358 to #362, which claimed #405 and #406 and Q224 and Q225 for the snapshot-sleep and freshness work. Master was merged into the branch (a merge commit, no rebase) and this session's entries were re-resolved from master's new maxima, **#406 and Q225**, to **#407, Q226 and Q227**. The commit messages `7cb0f62` and `314fa9a` still carry the old numbers and are not rewritten; the stores, `ROADMAP`, `CLAUDE.md` and this file carry the new ones. The renumber touched only this session's own regions; the other session's #405, #406, Q224 and Q225 are unedited.

## Pending-queue reconciliation

No `PENDING` items were carried in; the chat brief was the only input. Its LOG block is written: `DECISIONS_LOG` #407 (window is yesterday only, lateness derived, skip leaves the row null, the route refuses to overwrite yesterday's PM) and `OPEN_QUESTIONS` Q226 (the `DailyRecord` docstring says PM fields are append-only but same-day `submit_pm` overwrites; logged, same-day behaviour unchanged). Q227 is a second question the brief did not ask for; it records the `block_open` gap below. All three are in the PR, so they are committed once the PR merges; until then they are provisional.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One row added: Missed-PM catch-up (#407), built and landed via PR #357, operator check owed. Serves **Loop**. No other row changed.

**State.** Backend (`checkin_v2.py`): `NightlyCloseOutIn.for_date`, `/prefill.missed_pm`, `DailyRecordOut.pm_late`. Frontend: `components/MissedPMCard.jsx` on `CheckInAM`, a "late" marker on `CheckInHistory`. All VERIFY items in the brief matched master `0939eaf` before work began; the later master changes (freshness, snapshot sleep, the load card) touch none of the files this PR changes, so the merge conflicted only in governance files. Full backend suite 3106 passed, 3 skipped, and frontend 407 passed on the pre-merge head; both are re-run by CI on the merged head. The mutation check was run on the real source (`submit_pm` ignoring `for_date` fails 14 tests, both attribution tests among them) and the source restored. Nothing is verified in production.

**Single clearest next action.** The operator check (Luke, after the deploy): skip one evening's close-out; next morning the card appears on the AM screen; submit it; confirm `/checkin-history` shows yesterday's PM with the late marker, today's AM is unaffected, and that evening's `/nightly` is open as normal. Also grep the served frontend bundle for `Close out yesterday` (#121; two services deploy from this repo).

**Operator actions owed.** The check above; and a ruling on Q227 only if a block opens or closes within a day of a missed close-out (otherwise it is inert).

**Things the next reader should know.**
- **One departure from the brief, stated plainly.** The brief wanted a test that `cbti_block_open` "tracks yesterday's block, not today's". `_cbti_context(...).block_open` is `closed_on IS NULL` and never reads its date argument, so today and yesterday always return the same flag. The formula was used as briefed (ratified); the test pins that the context is asked about yesterday and records the equivalence. A block closed this morning hides the nap field for a day that was inside it; a block opened this morning asks for a nap on a day before it. Q227 holds the data-meaning fork; it was not resolved here.
- **`pm_late` compares Brisbane dates, not UTC.** The brief's "late-evening AEST submit that is after midnight UTC" cannot occur at UTC+10 (23:59 AEST is 13:59Z, the same UTC date); the real trap is the other side (00:01 AEST is 14:01Z the day before, so a UTC comparison calls it on time). Tests cover 23:59 AEST false, 00:01 AEST true, and both sides of midnight UTC.
- **A refused request mints no row**: the 409 check runs before `_get_or_create`.
- **Fresh-container test setup.** The suite needs an ephemeral `FERNET_KEY`, `SECRET_KEY` and `ALGORITHM` (as CI sets them) and a non-shallow clone (`git fetch --unshallow`); without the clone `tests/test_constraint_engine_arm.py` fails at collection reading an old SHA.
- The catch-up card is also shown on the "Morning check-in saved" view, because the prefill is loaded either way; the brief placed it on the AM screen without saying which state.
- **Two sessions numbered from the same master.** Both branches were cut at `0939eaf` and the other landed first. Number-at-merge worked as designed (re-read master's max, re-resolve) but cost a conflict resolution across five governance files; the code merged without a conflict.

**Carried forward from the previous close-out (`freshness-load-card`, landed 10 Oct as #405/#406; this file overwrites that one, so its owed items are restated here and its full text is in git history).** None was touched this session.
- The **amber** "Last background sync" paint on the companion: no action now; it shows on its own at the next real silence. The cause of the 8-9 Oct background silence (companion Q25) is still unknown.
- The companion's registration-once logcat check, bearing on Q25's lost-chain candidate.
- A decision on whether to open the egress policy to the app's own frontend domain, so Code can run the #121 grep itself in a future session.
- **Owed by Code:** fold the one-line fix to the companion `closeout.md` (its bullet saying health-app's ROADMAP row and `closeout.md` "still list this repo's earlier device gate as owed", which health-app never did) into the NEXT companion governance commit; no standalone PR.
- The Samsung scraper (companion Q24) is not fixed; its silence is an amber `STALE` line and the re-verification when the ring returns is still owed.
- Named by the operator as open and not Code's: the brief for the schedule tool and the merged recent-sessions tool, the unattributed-steps follow-up, removing the 65 PDFs from the project, and the repo-visibility decision.
- Q224 (per-writer nightly sleep aggregates) and Q225 (the on-device deep-sleep confidence verdict reaching the backend) are the other session's questions and are OPEN.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's other open legs:** the reconcile leg of Walk in (NEXT, #386) and every other Loop item. This session built one Loop habit gap (a missed close-out); it did not touch the readiness, recommendation or log legs.
- **The CBT-I engine, replay and prescriptions** (guarded out by the brief), and **same-day PM behaviour** (Q226).
- **The medical-protocol and fitness lanes:** the ingest and dedupe lane, the marker exposure (#367, Q206), Source hierarchy (Q201, Q203), the Polar re-zoning (Q198), HC sync reliability (Q159, Q208, Q214), the Garmin self-evaluation read, the clinical-documents follow-ups (Q220, Q221), and the MCP OAuth owed items (G4 and G5 from #404; Q222, Q223).
- **Decided and unbuilt from earlier sessions:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV, SpO2, respiratory and distance AEST re-bucketing.
- **Pattern to say out loud:** this is the first session in a while that went to a Loop habit rather than to infrastructure around the product, and it is small; the previous three went to infrastructure (the document store, connector persistence, data-age visibility). The next session should go to the Walk in reconcile leg or another Loop item, not to more capture-side polish, unless the operator wants more here.

**Open questions by status.** 127 OPEN and 7 OWED above `## CLOSED` (two OPEN are new from this session: Q226, the append-only docstring versus same-day overwrite; Q227, `block_open` ignoring its date; the other session added Q224 and Q225).

**v1-triage of the NOW lanes.**
- Missed-PM catch-up (#407): **Loop** (the daily check-in habit survives a missed evening without corrupting a day's record).
- Data freshness, Garmin-primary snapshot sleep and the load card (#405, #406): **See** and **Loop**, per the previous close-out.
- The other NOW rows are unchanged and keep the tests the previous close-outs named: Source hierarchy **See** and **Know**; Polar sport-id relabel **Know** and **See**; HC sync reliability **See** and **Loop**; Garmin self-evaluation read **Know** and **Loop**; Aerobic ingest automated **See** and **Loop**.
- Candidates for removal from NOW, as the previous close-outs named them: the phase-change form (#389, DONE), HC zones (#364, #385, #388), Know (d) (#390-#394). Carrying no v1 test: the CBT-I items, the injury sweep, the typed-constraints seed; the operator should rule on whether any of them belongs in NOW.
