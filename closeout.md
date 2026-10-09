# Close-out — pm-catchup: a missed nightly close-out is completed from the next morning's AM check-in and lands on the previous day's record (#405; Q224 and Q225 opened); operator check owed

## Real commits this session

`git log --format="%h %ad %s" --date=short 0939eaf..HEAD` (session opened at master `0939eaf`, the brief's design anchor; maxima at open: `DECISIONS_LOG` #404, `OPEN_QUESTIONS` Q223):

- `314fa9a` 2026-10-09 feat(checkin): missed-PM catch-up from the AM check-in (pm-catchup)
- the close-out commit below this file (`gov(pm-catchup): ...` carrying `DECISIONS_LOG` #405, `OPEN_QUESTIONS` Q224 and Q225, the `ROADMAP` NOW row, the `CLAUDE.md` Recent landings line and this file), on the same PR

PR #357 (ready for review, not draft: `CLAUDE.md` § Merge disposition overrides the harness default). No schema change and no migration, so no hold applies; the PR self-merges on green (`placeholder guard (POSIX)`, `backend tests (pytest)`).

## Pending-queue reconciliation

No `PENDING` items were carried in; the chat brief was the only input. Its LOG block is written: `DECISIONS_LOG` #405 (window is yesterday only, lateness derived, skip leaves the row null, the route refuses to overwrite yesterday's PM) and `OPEN_QUESTIONS` Q224 (the `DailyRecord` docstring says PM fields are append-only but same-day `submit_pm` overwrites; logged, same-day behaviour unchanged). Q225 is a second question the brief did not ask for; it records the `block_open` gap below. Both are in the close-out commit, so they are committed once that commit exists; until then they are provisional.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One row added: Missed-PM catch-up (#405), built and landed via PR #357, operator check owed. Serves **Loop**. No other row changed.

**State.** Backend (`checkin_v2.py`): `NightlyCloseOutIn.for_date`, `/prefill.missed_pm`, `DailyRecordOut.pm_late`. Frontend: `components/MissedPMCard.jsx` on `CheckInAM`, a "late" marker on `CheckInHistory`. All VERIFY items in the brief matched master `0939eaf` before work began. Full backend suite 3106 passed, 3 skipped; frontend 407 passed. The mutation check was run on the real source (`submit_pm` ignoring `for_date` fails 14 tests, both attribution tests among them) and the source restored. Nothing is verified in production.

**Single clearest next action.** The operator check (Luke, after the deploy): skip one evening's close-out; next morning the card appears on the AM screen; submit it; confirm `/checkin-history` shows yesterday's PM with the late marker, today's AM is unaffected, and that evening's `/nightly` is open as normal. Also grep the served frontend bundle for `Close out yesterday` (#121; two services deploy from this repo).

**Operator actions owed.** The check above; and a ruling on Q225 only if a block opens or closes within a day of a missed close-out (otherwise it is inert).

**Things the next reader should know.**
- **One departure from the brief, stated plainly.** The brief wanted a test that `cbti_block_open` "tracks yesterday's block, not today's". `_cbti_context(...).block_open` is `closed_on IS NULL` and never reads its date argument, so today and yesterday always return the same flag. The formula was used as briefed (ratified); the test pins that the context is asked about yesterday and records the equivalence. A block closed this morning hides the nap field for a day that was inside it; a block opened this morning asks for a nap on a day before it. Q225 holds the data-meaning fork; it was not resolved here.
- **`pm_late` compares Brisbane dates, not UTC.** The brief's "late-evening AEST submit that is after midnight UTC" cannot occur at UTC+10 (23:59 AEST is 13:59Z, the same UTC date); the real trap is the other side (00:01 AEST is 14:01Z the day before, so a UTC comparison calls it on time). Tests cover 23:59 AEST false, 00:01 AEST true, and both sides of midnight UTC.
- **A refused request mints no row**: the 409 check runs before `_get_or_create`.
- **Fresh-container test setup.** The suite needs an ephemeral `FERNET_KEY`, `SECRET_KEY` and `ALGORITHM` (as CI sets them) and a non-shallow clone (`git fetch --unshallow`); without the clone `tests/test_constraint_engine_arm.py` fails at collection reading an old SHA.
- The catch-up card is also shown on the "Morning check-in saved" view, because the prefill is loaded either way; the brief placed it on the AM screen without saying which state.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's other open legs:** the reconcile leg of Walk in (NEXT, #386) and every other Loop item. This session built one Loop habit gap (a missed close-out); it did not touch the readiness, recommendation or log legs.
- **The CBT-I engine, replay and prescriptions** (guarded out by the brief), and **same-day PM behaviour** (Q224).
- **The medical-protocol and fitness lanes:** the ingest and dedupe lane, the marker exposure (#367, Q206), Source hierarchy (Q201, Q203), the Polar re-zoning (Q198), HC sync reliability (Q159, Q208, Q214), the Garmin self-evaluation read, the clinical-documents follow-ups (Q220, Q221), and the MCP OAuth owed items (G4 and G5 from #404; Q222, Q223).
- **Decided and unbuilt from earlier sessions:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV, SpO2, respiratory and distance AEST re-bucketing.
- **Pattern to say out loud:** this is the first session in a while that went to a Loop habit rather than to infrastructure around the product, and it is small. The next session should go to the Walk in reconcile leg or another Loop item, not to more capture-side polish, unless the operator wants more here.

**Open questions by status.** 125 OPEN and 7 OWED above `## CLOSED` (two OPEN are new this session: Q224, the append-only docstring versus same-day overwrite; Q225, `block_open` ignoring its date).

**v1-triage of the NOW lanes.**
- Missed-PM catch-up (#405): **Loop** (the daily check-in habit survives a missed evening without corrupting a day's record).
- The other NOW rows are unchanged and keep the tests the previous close-out named: Source hierarchy **See** and **Know**; Polar sport-id relabel **Know** and **See**; HC sync reliability **See** and **Loop**; Garmin self-evaluation read **Know** and **Loop**; Aerobic ingest automated **See** and **Loop**.
- Candidates for removal from NOW, as the previous close-outs named them: the phase-change form (#389, DONE), HC zones (#364, #385, #388), Know (d) (#390-#394). Carrying no v1 test: the CBT-I items, the injury sweep, the typed-constraints seed; the operator should rule on whether any of them belongs in NOW.
