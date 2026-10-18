# Close-out — 19 Oct 2026: Q27's five remainders built and landed (PR 400, #427 to #430, Q27 closed), the migration released and applied, the seeder run in prod, and the post-land record written

## Real commits this session

`git log --format="%h %ad %s" --date=short 5d13046..HEAD` (session opened at master `5d13046`, the merge of PR #393; maxima at open: `DECISIONS_LOG` #424 and #426 after the first fetch, `OPEN_QUESTIONS` Q233; at close: #430 and Q233, four decisions minted by this session, no question opened). Dates are as git prints them (UTC).

This session's work, in order:

- `ae3400a` 2026-10-19 refactor(series): move the strength-read primitives to reads/strength_reads.py, no behaviour change
- `e894c59` 2026-10-19 feat(schema): provenance on capability observations and side on exercise region tags (migration 705a17c84d9a, HELD)
- `2ba656e` 2026-10-19 feat(engine): protocols, norms and the reference gate; route (i) log-derived ratios; knee_flexion measures
- `b457b5a` 2026-10-19 Merge master into feat/q27-v1-remainders (master `06f807e`, the Garmin SpO2 session's PR #399; one OPEN_QUESTIONS line, no conflict)
- `1ec4f88` 2026-10-19 gov(q27-v1-remainders): #427 to #430 (provenance, route (i), norms and knee_flexion, Q27 closed); Q27 to CLOSED; ROADMAP, BRANCHES, capability-taxonomy-v1
- `08010aa` 2026-10-19 gov(q27-v1-remainders): record the operator's release of migration 705a17c84d9a (19 Oct 2026)
- `b3e9150` 2026-10-19 Merge pull request #400 from Easty11/feat/q27-v1-remainders (all three checks green on `08010aa`; self-merge withheld until the operator wrote "released")
- the commit of the post-land record and this close-out (`gov(q27-postland-record)`), on `gov/q27-postland-record` cut from `b3e9150`, which carries this file

**Other landings since the 16 Oct close-out, from `git log --first-parent d460e51..5d13046` plus `5d13046..06f807e` (other sessions' work; named here, not this session's).** The sRPE source-neutral store (#393, `5d13046`, #424) and the Garmin SpO2 capture and its governance (#392, #394 to #399, `06f807e`, #425, #426).

The code PR carried a schema migration, so it was held under hold (a) and merged only after the operator released it. It opened ready-for-review, not draft. The remote deleted the branch on the merge. The post-land record is governance only, no schema, no new decision number.

## Pending-queue reconciliation

Input: two operator briefs. (1) `q27-closeout-v1-remainders`, the five remainders. (2) `q27-postland-record`, a status record after the land. The second block's first line names a session other than the first brief's; `list_sessions` showed this as the only live session ("No other sessions found"), so it was acted on, and the divergence is named here. No pasted `PENDING` block was carried in.

- **Brief 1, steps 1 to 9 and the GATES.** Landed in `ae3400a`, `e894c59`, `2ba656e`, `1ec4f88` and `08010aa`, merged in `b3e9150`. Gate 4 (the migration PR is not self-merged) held until the release. Gate 6 (decision numbers minted from master's max, not from the brief): they were resolved at #427 to #430 against master's max #426 (re-read twice, unchanged) because the placeholder guard refuses `#NEXT` in a PR.
- **Post-land record, item 1 (deploy and migration).** Recorded on #427's Status, in this commit.
- **Item 2 (the seeder run).** Recorded on #427's Status: the dry-run counts, the twelve side updates by template and region, the confirm counts, and the two parents resolved (`68CE0B9B` to `hinge`, `2EE45F81` to `vertical_pull`).
- **Item 3 (operator ratifications).** (a) Westrick as a dimensionless fraction and the inference on "neutral": #429's Status. (b) and (c): #427's Status, with the downgrade cost stated. (d): #428's Status. (e): #429's Status, no value changed.
- **Item 4 (deferred).** Side on the remaining L/R pairs and the `--confirm` side-count tooling fix: #427's Status. The Hebert-Losier regression equation: #428's Status. The NordBord / eccentric measure: #429's Status. Restated in the handoff below.
- **Item 5 (edits).** #427 Status; the BRANCHES row for `feat/q27-v1-remainders` (DONE `b3e9150`, outstanding none); the CLAUDE.md Recent-landings pointer (the #423 (ii) pointer trimmed to hold the cap of three); this file. #428 and #429 Status lines also carry their ratified items, as item 3 says "as applicable".

The operator-pasted output in items 1 and 2 was not independently verified: Code had no prod route, and the figures are recorded as the operator's.

Nothing decided in this session is uncommitted. Only this close-out is provisional until its own commit merges.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row added or removed by this session. The Q27 row (the "Adaptive programming lane ... taxonomy v1 (Q27)" row) records (b) DONE with #420 to #422 and #427 to #430. `ROADMAP.md` "Last updated" still reads 2026-10-16.

**State.** `DECISIONS_LOG` max is #430; `OPEN_QUESTIONS` max is Q233. Questions: 121 OPEN and 6 OWED above `## CLOSED` (127 headings, by each `**State:**` line's first word), 105 closed; Q27 moved below `## CLOSED` as `DONE → #430`. Q27's capability layer is in prod: provenance on observations, `side` on twelve tag rows, ten protocols, nine cited norms, the gate, route (i) and route (ii) ratios, `GET /engine/ratios`, `GET /engine/ratios/{key}`, `GET /engine/log-strength`, and the MCP tool `get_capability_ratios`. Every `literature` declaration has a cited norm and no `internal` one has any, pinned both ways.

**Single clearest next action.** Unchanged from the 16 Oct handoff, because nothing this session moved it: the **Walk in reconcile leg** (ROADMAP NEXT, `UNSTARTED; needs a build brief`, #345/#386), which needs the operator's brief. The nearest owed Q27 step is the operator's, not Code's: put the EP questions to the EP (below).

**Operator actions owed.** The EP ask list, open and non-leading: which shoulder rotation test position and protocol they use (so the matching `protocol` key is recorded; a standing-neutral test is a NEW protocol key); whether they test hip adduction and abduction eccentrically in side-lying; whether they can test eccentric hamstring strength (NordBord or isokinetic) and what, if anything, they would use instead. The cuff purchase stays the operator's call; the ceiling evidence is on the record (about 300 mmHg; Toohey 2017). The other OWED NOW rows are as the 16 Oct close-out left them (Q231 rating of Garmin activities, Q205 at the next Polar re-auth, the Q199 HRmax test, the #412 check, the new post-deploy reads for #424).

**Things the next reader should know.**
- **No value was ever observed through the new surfaces.** The prod `capability_observations` table has no provenanced row, so `GET /engine/ratios` route (ii) is empty and the gate has never returned `literature` in prod. Route (i) reads the Hevy log and needs sided tags; the twelve tagged entries are all the sides there are. Nothing in the product the operator uses changed in the way he would see until the EP records a reading or a sided template is logged on both sides.
- **Three of the ratified calls are rules in code that a later session can trip:** a protocol must produce the observed (region, measure); the migration's downgrade refuses while any observation carries provenance (a rollback first needs those rows exported or deleted by hand); `current` is null unless three pairs fall inside 42 days.
- **Abstract-only norms.** Riemann, Mosler and Delahunt were read from the abstract. The Thorborg attribution for Mosler and whether Delahunt analysed the best or the mean of three are unconfirmed, and say so in the protocol descriptions and the norm records (`verified_against`).
- **Two nits, batched (severity gate).** The ROADMAP Q27 row still says the seeder run "is recorded here when it happens", though it is recorded on #427; the brief's edit list excluded ROADMAP, so it was left. Three L/R pairs in the reference (Dumbbell Step Up, Suitcase Carry, Weighted Lateral Flexion/Ext) carry no `side`, so they read as bilateral in route (i) until the next tag pass.
- **Test environment.** `test_clock_pin` fails in a local run on a clean tree as it did before this work; it passed in CI on `08010aa`. The suite needs a real `FERNET_KEY` (generate a throwaway key); `FERNET_KEY=x` only works for files that never import `encryption`.

**What was NOT touched (named so absence does not read as finished).**
- **The deferred Q27 items:** side on the three remaining L/R pairs; the Hebert-Losier regression equation as an age-appropriate heel-rise comparator (only the median is stored; revisit when `sl_heel_raise_reps` has observations); the NordBord / eccentric `knee_flexion` measure (pending the EP's instrument); the `--confirm` seeder summary, which does not report the side updates it wrote (the dry-run does).
- **Feature lanes that stood still:** the appointment brief and its reconcile leg, CBT-I, the Hevy programme and routines, the companion app (`health-connect-app`), the MCP OAuth owed items (G4, G5), the cross-repo propagation rows, the Q231 build, and the lab and interpretation lanes (LATER since 12 Oct). #423 (ii) is still UNSTARTED.
- **Questions gating them, unchanged:** Q231 (the 10-pair gate), Q203, Q189, Q124, Q198, Q159, Q208 and Q214, Q205, Q224 and Q225, Q226 and Q227, Q228, Q232.
- **Pattern to say out loud.** The last Code sessions have gone to the layer under the product: the 11 Oct load-model records, the 12 Oct Q27 taxonomy and rulings sweep, the 16 Oct roadmap row, the 18 Oct sRPE store and SpO2 capture, and this session, which finished Q27's measurement layer with no reading in it yet. The operator-facing product has not changed in that time. The next session should take the Walk in reconcile leg, or another Loop item, rather than another instrument.

**v1-triage of the NOW lanes.** Carried unchanged from the 16 Oct close-out; no NOW row was edited by this session, and the rows other sessions added (#424, #425) state their own "Serves" clauses. The Q27 row is not a NOW row and names no v1 test, and I add none. Candidates for removal from NOW (DONE, kept for owed checks) and the cross-repo rows' standing reason to sit in NOW (#112) are as the 16 Oct file listed them.
