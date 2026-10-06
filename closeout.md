# Close-out — the operator's R11 (phase bands plus a legend replacing the marker lines) is recorded on the ROADMAP phase-marker item with Code's checks for the brief; nothing is built and no decision is minted

## Real commits this session

Session `metrics-markers-r11`, the operator's brief of 6 Oct 2026 (AEST), one governance-only PR. Range: `f289d67` (master at open) to this close-out. Fresh-clone settings were already set and read back. Maxima at open, by anchored script: decisions #394, questions Q216. No number minted: R11 is recorded as a decision entry when it is built, as the brief said.

- `0c96417` `gov(metrics-markers-r11): record the operator's R11 (phase bands plus a legend) on the ROADMAP phase-marker item, with Code's checks for the brief` - the ROADMAP amendment, the BRANCHES row and the CLAUDE.md pointer (oldest dropped, cap of 3).
- A final `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).

No code, no migration, no schema change, no prod read or write. The PR self-merges on green (governance only; no new judgment by Code). **Provisional until merged: everything above.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The brief, item by item:

1. **R11 recorded on the item logged in #342: DONE.** Span, colour per phase name, the same-name revision as a thin dashed line with no label, a phase after the last data day listed as "no data yet" and never dropped, low-opacity bands with light and dark tokens and no in-chart text, and bands from dates with no snap on Exercise and Readiness. The item's heading says it was amended the same day.
2. **The pinned tests: said so, as the brief asked.** R11 replaces the drop-after-the-last-category and snap-to-next-day behaviour; the item says the `PhaseMarkers.test.jsx` tests that pin them are updated in the build, and that the build says so.
3. **The live rollup `as_of`: still owed by the operator,** recorded as such on the item.
4. **"Record as #NEXT when built, not now": honoured.** No decision entry, no number.

**What I checked before recording, and what it found.** R11's "light and dark tokens" assumes a token layer; the app has none (no `dark:` classes, no `prefers-color-scheme` rules and no theme config in `frontend/src`; chart colours are hex literals). That is recorded as an open choice for the brief (CSS variables with a dark override now, or light only), not decided.

**Notes recorded for the brief, none a ruling** (all on the ROADMAP item):
- R11 supersedes the earlier "bands to today": the band ends at the series end and a later phase shows in the legend only, so the axis need not extend to today.
- "Bands from dates, no snap" on Exercise and Readiness needs `xType="time"`, which changes their spacing from even-per-data-day to proportional; R11 implies it without stating it.
- Legend placement (per chart or per page) is unspecified.
- Assumptions to confirm: "same name" is an exact match on `label`; consecutive same-name rows are one band with dashed lines at the handoffs; a name entered again after another phase is a second band in the same colour; a zero-length row (#379) draws nothing.
- Bands go before the series so bars draw on top, as direct children of the Recharts chart.

**Divergences and judgment calls, named.**
- **None built, so nothing narrowed.** The recorded notes are questions, not decisions; the item does not resolve any of them.
- **The earlier fix direction was amended in place, not struck:** its heading clause and lead-in say it is superseded in part by R11, and the text it supersedes is kept.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. NEXT's phase-marker item is amended (UNSTARTED, no brief).

**State.** The PR is open, checks pending at write time, self-merging on green. No `#NEXT` placeholder on the branch. No code changed, so no suite was re-run beyond CI.

**Single clearest next action.** Brief the marker build from the ROADMAP item. It needs three answers first: the live rollup `as_of` (operator), the token choice (variables with a dark override, or light only), and the legend placement (per chart or per page). Everything else in the item is either ruled (R11) or an assumption the brief can confirm in one line.

**Operator actions owed.** (1) The live rollup `as_of`, read off the chart, for the marker brief. (2) The #121 bundle check for #393 and #394 (the strings "Leg days", "every listed day", "candidate days", "Not counted toward any quota"), the strip on the phone, and the 28 Sep to 3 Oct leg on `/metrics`, carried from earlier close-outs. (3) Carried: confirm Polar Flow's max HR is locked at 175 (#388); the Q159 in-activity HR read on or after 9 Oct; the phone read of B, C and E for the appointment brief.

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session); the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). No question changed state this session.

**What was NOT touched (named so absence does not read as finished).**
- **The marker fix itself:** nothing in `PhaseMarkers.jsx`, `TimeSeriesChart.jsx` or the four chart components changed; the misreading is still live, and so is the silent drop of a phase that starts after the last data day.
- **The planning grid, the reconcile leg of Walk in (NEXT, #386), Loop (check-in, readiness, recommendation, close-out):** unbuilt or unchanged.
- **Q197, the HC zones lane, Q199, Q216, the Polar re-zoning (Q198), Q213, Q214, Q212, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Lab upload pipeline, interpretation layer increments, medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gap carried:** `verify_series_integrity.py:56` still says `railway run`.
- **Pattern to say out loud:** this is the fourth session in a row on the See and Know surfaces, and the second in a row that only edited the log for the marker item. Both were warranted (a ruling to record, a premise to check), but none moves Walk in's reconcile leg or a Loop item, and the marker build now waits on three small answers rather than on work. The next session should either take the marker build once those are in, or go to the reconcile leg.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389): **Know** and **Loop**. DONE; a candidate for removal from NOW.
- Know (d), the leg strip and wrap (#390 to #394): **Know**. Built; the test is MET (#392); only #393 and #394's deploy check remains.
- The `/metrics` phase-marker item (NEXT, R11): **See**. Ruled, unbriefed.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
