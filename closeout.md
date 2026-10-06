# Close-out — the /metrics phase-marker misreading is logged on ROADMAP NEXT with the check of its cause; nothing is built and no decision is minted

## Real commits this session

Session `metrics-markers-log`, the operator's brief of 6 Oct 2026 (AEST), one governance-only PR. Range: `cf5102d` (master at open) to this close-out. Fresh-clone settings were already set and read back. Maxima at open, by anchored script: decisions #394, questions Q216. No number minted: the brief asked for a log, not a ruling.

- `e93eebc` `gov(metrics-markers): log the /metrics phase-marker misreading on ROADMAP NEXT, with the check of its cause` - the ROADMAP NEXT item, the BRANCHES row, the CLAUDE.md Recent-landings pointer (oldest dropped, cap of 3).
- A final `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).

No code, no migration, no schema change, no prod read or write. The PR self-merges on green (governance only; no new judgment by Code). **Provisional until merged: everything above.**

## Pending-queue reconciliation

Nothing came from a chat `;cc` queue as a PENDING item. The brief, item by item:

1. **Log on ROADMAP, no build: DONE (`e93eebc`).** A new small NEXT item rather than a Visuals-row edit, so the Visuals row stays history.
2. **"Chat's hypothesis (verify)": verified, and half of it does not hold.** Checked by reading the code and by a throwaway render (jsdom, then real Chromium) of the shared chart with the ledger the report implies; nothing from the render is committed.
   - **Holds: one fix in the shared piece.** All four chart components pass `markers` through `TimeSeriesChart` to `referenceLinesFor`; the three load charts share one `LoadChart` data array and marker list.
   - **Does not hold: "a categorical axis of only days with load".** The rollup writes a continuous daily calendar per window to `as_of`, rest days included, so the load charts' axis has a slot per calendar day.
   - **Does not hold: "bands".** The markers are dashed vertical lines; no training chart draws a band.
   - **The likely cause of what the operator saw:** each marker's label is drawn to the LEFT of its line, over the preceding phase's bars. "Aerobic base" appears above the 28 Sep to 3 Oct bars although its line is correctly just right of the 3 Oct bar.
   - **A second defect, reproduced:** a boundary after the last category is dropped silently, so a phase that starts after the series ends leaves no mark. `PhaseMarkers.test.jsx` pins that drop and the snap-to-next-day rule as design, so the fix changes pinned behaviour.
   - **A third, by code only:** on the sparse axes (Exercise, Readiness) a boundary snaps to the next data day.
3. **Fix direction and test, as given: recorded verbatim in the item,** with three notes for the brief that picks it up (the load charts need the band, an in-band label and an axis to today more than a time scale; the time scale matters for Exercise and Readiness; the pinned behaviours change).

**Divergences and judgment calls, named.**
- **The brief's premise was partly wrong and the log says so** rather than recording the hypothesis as fact (the unseeable-surface rule: a brief statement about a surface chat cannot read is an instruction to verify).
- **Not read:** the operator's real ledger, the live rollup `as_of`, the live bundle (no prod or frontend-host access). The render used the dates from the report, so it shows what the code does with that shape, not what the live page shows.
- **A process note:** the first real-browser attempt failed on a wait for a bare `<g>` to be "visible"; I changed the wait to "attached" and re-ran. The throwaway harness and the dev server were removed, and `git status` is clean of them.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. NEXT gains the `/metrics` phase-marker item (UNSTARTED, no brief).

**State.** The PR is open, checks pending at write time, self-merging on green. No `#NEXT` placeholder on the branch. No code changed, so no suite was re-run beyond CI.

**Single clearest next action.** Brief the marker fix. The operator's direction (bands clipped to [`entered_on`, `closed_on` or today], an axis to today, a test per chart that a phase entered after the last data day renders as a band with no bars) stands, with the three notes in the ROADMAP item. The one open fact it needs: the live rollup `as_of`, which the operator or a prod read can give.

**Operator actions owed.** (1) The #121 bundle check for #393 and #394 (the strings "Leg days", "every listed day", "candidate days", "Not counted toward any quota"), the strip on the phone, and the 28 Sep to 3 Oct leg on `/metrics`, all carried from the last close-out. (2) Carried: confirm Polar Flow's max HR is locked at 175 (#388); the Q159 in-activity HR read on or after 9 Oct; the phone read of B, C and E for the appointment brief.

**Code actions owed.** The #387 shared-block propagation to `health-connect-app` (next HCA session); the single-row HC bout deposit read (low priority).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). No question changed state this session.

**What was NOT touched (named so absence does not read as finished).**
- **The marker fix itself:** nothing in `PhaseMarkers.jsx`, `TimeSeriesChart.jsx` or the four chart components changed; the misreading is still live.
- **The planning grid, the reconcile leg of Walk in (NEXT, #386), Loop (check-in, readiness, recommendation, close-out):** unbuilt or unchanged, as in the last close-out.
- **Q197, the HC zones lane, Q199, Q216, the Polar re-zoning (Q198), Q213, Q214, Q212, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Lab upload pipeline, interpretation layer increments, medical protocol (CBT-I, the injury ledger):** did not move.
- **Known gap carried:** `verify_series_integrity.py:56` still says `railway run`.
- **Pattern to say out loud:** this is the third session in a row on the See and Know surfaces (the strip, the wrap, now the chart markers). All are small and operator-driven; none moves Walk in's reconcile leg or a Loop item. The next session should go there unless the marker fix is the operator's priority.

**v1-triage of the NOW lanes** (which test each serves):
- Phase-change form (#375, #376, #378, #379, #389): **Know** and **Loop**. DONE; a candidate for removal from NOW.
- Know (d), the leg strip and wrap (#390 to #394): **Know**. Built; the test is MET (#392); only #393 and #394's deploy check remains.
- The `/metrics` phase-marker item (NEXT): **See**. Unbriefed.
- HC zones (#364, #385, #388, OWED for a lock confirmation and a low-priority read): **See**, **Know** and **Loop**. No real work left; a demotion candidate.
- Appointment brief: **Walk in**, met (#386); the reconcile leg (NEXT) serves the same test.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Lanes carrying no v1 test: the `Training` tag seed (#339, DONE), the CBT-I items, the injury sweep and the typed-constraints seed serve the medical-protocol module rather than a v1 test; they sit in NOW by operator ownership, not by a v1 reason, and are demotion candidates the operator should rule on.
