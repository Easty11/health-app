# Close-out — date-fragile tests swept: the five hardcoded-`review_by` tests are not date-sensitive, three other tests that were are fixed, and a pin runs the date-sensitive files a year ahead

## Real commits this session

Session `date-fragile-tests`, the operator's brief of 6 Oct 2026 (AEST), two PRs. Range: `a3f52a9` (master at open) to this close-out. Fresh-clone settings were already set and read back (`core.hooksPath` = `.githooks`, local `alias.land` set). Maxima at open, by script: decisions #389, questions Q216. No number minted: the sweep found no pattern that needs a ruling.

PR 1, a time-critical one-test fix, merged:
- `97df534` `test(hc): test_hc_hr_ingest payload dates are relative to the clock, not 28 Sep 2026` - plus its own BRANCHES row.
- `2fc4f6d` `Merge pull request #336 from Easty11/claude/jolly-bardeen-vlksg1` - merged on green at 23:48Z on 5 Oct, twelve minutes before the test would have failed on the real clock.

PR 2, the sweep and the pin, on the same branch name restarted from `2fc4f6d` (the harness instruction and #387):
- `53fe428` `test(dates): test_seed_constraints derives its review date; a pin runs the date-sensitive tests a year ahead` - `tests/test_seed_constraints.py`, `tests/clock_travel.py`, `tests/test_clock_pin.py`, and `time-machine==3.5.1` in `backend/requirements.txt`.
- `53115f4` `gov(date-fragile-tests): the 15 Oct watch row is DONE; the sweep, its findings and the pin recorded` - ROADMAP, BRANCHES, the CLAUDE.md Recent-landings pointer.
- The `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).

No migration, no schema change, no prod read or write. PR 2 self-merges on green (non-schema; the brief ratified it, no new ruling). **Provisional until merged: everything in PR 2.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The brief, item by item:

1. **Confirm the five fail on 15 Oct under a faked clock: DONE, and the answer is that none of them does.** I ran the whole backend suite under a travelled clock (`time-machine`, session-wide, ticking) at 6 Oct 2026 00:00Z, 16 Oct 2026, 31 Dec 2026 14:30Z (the AEST new year) and 6 Oct 2027. `test_constraint_engine_arm`, `test_constraint_entries`, `test_sweep_constraint_rehome`, `test_typed_entries_render` and `test_typed_write_shape_docs` pass at every one. Why: the validator only checks the `review_by` format, and the render test passes its own fixed `today`, so the literal is never compared with the clock. The closeout and ROADMAP both called this "unverified"; it is now verified, and the watch item was a worry rather than a fault.
2. **Fix those: nothing to fix, so none changed.** Moving the literals would have been churn against a passing test. What the run did find, and was fixed by deriving the date from the clock:
   - **`test_hc_hr_ingest::test_an_hr_insert_failure...` (PR 1, `97df534`).** Fixed payload date 28 Sep against a sync that only counts days inside `today - periodDays`; it passed until 00:00Z on 6 Oct and would then have turned `backend tests (pytest)` red on master and every PR. This was the urgent one and is why the work was split.
   - **`test_seed_constraints` (`53fe428`).** A fixed `--review-by 2026-12-01`, which the script refuses as past: four tests fail from 1 Dec 2026 (and the "neither mode" and "both" refusals would have passed for the wrong reason). Now `_local_day() + 60 days`.
3. **Sweep, backend and frontend: DONE.** Beyond the literal grep (83 backend test files hold a 2026/2027 date; 21 of them also read a live clock), the whole-suite run is the stronger test, and after the two fixes it passes at all four dates. Every other file is safe for one of three reasons, listed per file in the PR body: it builds its dates from the clock (`_local_day()`, `datetime.now()`, a `_TODAY` captured at import), it passes an explicit `today` or fixed clock into the code, or its literal is data that is never compared with the clock (a stored draw date, a payload field). The frontend suite, run with `Date` travelled to the same dates, passes (358 tests, no change).
4. **Pin: DONE (`53fe428`).** `tests/test_clock_pin.py` runs every test file that holds a 2026/2027 literal and a live-clock read (23 files today, the sweep's own rule, so a new file with both is covered automatically), plus the five named, in a subprocess a year ahead; about 26 seconds. Mutation-checked: putting the stale `2026-12-01` back fails four tests in the pin while the same tests still pass on today's clock, which is the point.
5. **Governance: DONE (`53115f4`).** BRANCHES rows for both PRs, the ROADMAP watch row struck and replaced by a DONE row, the Recent-landings pointer. No decision entry. The "Known gaps carried" bullet on the 15 Oct time bombs is removed from this handoff.

**Divergences and judgment calls, named.**
- **Split into two PRs** where the brief said one: the HC-sync test was a live fault with a deadline minutes away (found by the sweep at 23:4xZ), so it shipped alone first.
- **A new test dependency,** `time-machine==3.5.1`, in `backend/requirements.txt` beside `pytest` (the same file the production image installs, 3.12 wheels exist). The brief offered freezegun or a monkeypatched `_local_day`; neither works here: `_local_day` is imported by name into many modules, and freezegun swaps `datetime.date` for a fake class (routes registered during a frozen test then fail to build Pydantic models) and freezes the monotonic clock (an asyncio test hung). `time-machine` patches the clock sources and leaves the classes alone. The operator may want it out of the production image; that needs a separate dev requirements file and a workflow edit, not done here.
- **The pin's file set is a heuristic** (a literal plus a clock read in one file). A stale literal in a file whose clock read lives in another module would not be selected; the full-suite run is the check that does not depend on the heuristic, and it is manual.
- **No frontend pin:** the frontend was verified by a one-off run only (a Vitest setup file that fakes `Date`), and I removed those files. Adding a permanent one is small if wanted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. The ROADMAP watch row in LATER is DONE.

**State.** PR 2 is open, checks pending at write time, self-merging on green. No `#NEXT` placeholder exists on the branch and no number is minted.

**Single clearest next action.** After PR 2 merges, the clearest unbuilt work is still the reconcile leg of Walk in (NEXT, #386), which needs a brief first. The #121 served-bundle check for the phase-entry build (#389) is still owed and still blocked on this sandbox's network policy (the Railway frontend host is denied); the operator can run it, or add the host under Allowed domains.

**Operator actions owed.** (1) The #121 bundle check for #389: the live `assets/index-*.js` should contain "End phase", "same-day correction" and "A phase needs at least one quota slot". (2) Confirm Polar Flow's max HR is locked at 175 (#388). (3) The Q159 in-activity HR read on or after 9 Oct. (4) The phone read of B, C and E for the appointment brief. (5) Optional: decide whether `time-machine` should stay in the production image.

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session); the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). No question changed state this session.

**What was NOT touched (named so absence does not read as finished).**
- **The reconcile leg of Walk in** (NEXT, #386): unbuilt and unbriefed.
- **Know and Loop beyond tests:** no change to the due-slot resolver, the daily loop, or readiness. Wrap-vs-plan (Know remainder (d)) is unbuilt.
- **The HC zones lane, Q199's maximal-effort test, Q216, the Polar re-zoning (Q198):** unmoved.
- **Q213, Q214, Q212; the sRPE floor, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Lab upload pipeline and the interpretation layer's remaining increments; medical protocol (CBT-I, the injury ledger):** did not move.
- **One observation, not acted on:** several tests stamp `added_at=date.today()` (the runner's UTC date) where the engine uses `_local_day()` (AEST); the two differ for ten hours of every UTC day (the probe showed 5 Oct against 6 Oct). Nothing fails on it today, and it is the same family as the #335 and #336 faults, so it is the next place to look if a rollover fault recurs.
- **Known gap carried:** `test_context_builder_output_unchanged_pre_post_refactor` fails in a shallow clone (it needs commit `3360ed5`) and passes in CI. `verify_series_integrity.py:56` still says `railway run`.
- **Pattern to say out loud:** this is the third session in a row on instrument, ledger and test hygiene rather than the daily loop. It was warranted (a live CI fault was found and fixed), but the next session should go to Walk in's reconcile leg or a Loop item.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389; only the bundle check OWED): **Know** and **Loop**. Nearly finished; a demotion candidate once the bundle check is read.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
