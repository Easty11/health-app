# Close-out — 4 Nov 2026: injury lifecycle in-app (`DECISIONS_LOG` #493 to #496; design 0009)

## Real commits this session

Session opened at health-app master `78a620a` (the merge of PR 602). Maxima at open: `DECISIONS_LOG` #492, no open `fork` issue (REST read, empty). At close: master max #496 (all four minted by this session), one open `fork` issue (GH#608, filed by this session), one `stamp` (GH#609, filed by this session), one `design` pointer (GH#603, filed by this session). The brief was pasted (`injury-lifecycle-in-app - Next work nomination`); no issue carried it.

The nine commits of this session, by the session trailer (`git log --format="%h %ad %s" --date=short --grep=session_01MzemEYnbRHrjxn5YXcR76X 78a620a..origin/master`):

```
52113a5 2026-11-03 gov(injury-model-design-doc): design 0009 injury model at discussion; ROADMAP lane row and LATER block; BRANCHES row
652f477 2026-11-03 feat(injury-shape): validate_injury on every channel, the body-part vocabulary, optional injury-model fields, Edit on the card
45f9e1a 2026-11-03 gov(injury-shape): #493 the injury row has a closed shape; design 0009 row 1 resolved; ROADMAP and BRANCHES rows
2959d39 2026-11-03 feat(restrictions-to-proposals): the S6 seed script becomes a card action; restrictions are proposed, never seeded confirmed
126cc6e 2026-11-03 gov(restrictions-to-proposals): ruling #494; ROADMAP lane row PR-B done and the G6 seed row's retirement note; BRANCHES row
b64bcee 2026-11-03 feat(checkin-pending-surfacing): Needs your call on the AM saved screen; the Injuries doorway counts; shared InjuryActions
73ddc8c 2026-11-03 gov(checkin-pending-surfacing): ruling #495; ROADMAP lane row PR-C done; BRANCHES row with O-B owed
fe73848 2026-11-03 feat(coach-hevy-note-signals): a Hevy exercise note reporting pain or a limit is an injury signal the coach proposes from
9b83258 2026-11-03 gov(coach-hevy-note-signals): ruling #496; lane row done; BRANCHES row; CLAUDE.md pointer for the lane; design 0009 row 10 names GH#608
```

The five merges onto master (`git log --first-parent 78a620a..origin/master`), each self-merged on green under § Merge disposition, every one a two-way door, no migration:

```
26c5312 Merge pull request #604 from Easty11/gov/injury-model-design-doc   (PR-0, docs only)
4050066 Merge pull request #605 from Easty11/feat/injury-shape              (PR-A, #493)
9d3bb75 Merge pull request #606 from Easty11/feat/restrictions-to-proposals (PR-B, #494)
e84c92c Merge pull request #607 from Easty11/feat/checkin-pending-surfacing (PR-C, #495)
70fb8a7 Merge pull request #610 from Easty11/feat/coach-hevy-note-signals   (PR-D, #496)
```

Deploy checks (#491, the `deploy-check` workflow read on each merge commit by Code through the GitHub MCP): `26c5312` success (docs only: both services SKIPPED by construction, the check passes because each service still serves a commit containing its folder's last change); `4050066` success (backend and frontend changed); `9d3bb75` success (both changed); `e84c92c` success (frontend changed); `70fb8a7` success (backend changed). Post-deploy read for PR-B (G3), through `get_constraints` at 06:58 Brisbane: 5 confirmed, 0 pending, unchanged from the morning's read, so the route wrote no confirmed row.

This close-out's own commit, `chore: session close-out`, follows these on `gov/closeout-injury-lifecycle` and lands as a docs-only PR; it names no hash here because a commit cannot name itself.

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief; each of its steps, against the commit that carries it:

| Brief step | Landed in |
|---|---|
| PR-0 P1 to P5: design 0009 (Proposal and Exclusions byte-faithful), GH#603 pointer, ROADMAP NOW row and LATER block, BRANCHES row | `52113a5`; GH#603 |
| PR-A A1 to A7: `validate_injury`, the vocabulary, every channel, Edit on the card, the prompt's injury example and INJURY shape, tests, design doc row 1 → #493 | `652f477` (code, tests), `45f9e1a` (#493, doc, rows) |
| PR-B B1 to B5: planner module, `POST /knowledge/injuries/{id}/propose-constraints`, card button and states, script and test deleted, fixture test migrated, SCHEMA/ROADMAP mentions, tests | `2959d39`, `126cc6e` (#494) |
| PR-C C1 to C4: `InjuryActions.jsx` extraction (four Injuries test files zero diff), the saved-screen block, the doorway line, tests | `b64bcee`, `73ddc8c` (#495) |
| PR-D D1 to D5: the paragraph, #43 guard re-declared, the transport-faked test, D4 (not done, slot unfilled), GH#608 filed | `fe73848`, `9b83258` (#496); GH#608 |
| G6 `CLAUDE.md` Recent-landings pointer once at the end of PR-D | `9b83258` |
| LOG entries: #493 (Decision), #494, #495, #496 (rulings), headed `### #NEXT` and resolved at each PR open from master's max, re-read before each merge | the four `gov(...)` commits |

Departures from the brief, each reported at its gate and none folded into prose (FEEDBACK §44):
- **VERIFY mismatch, PR-D (G1):** the second D3 fixture ("a free-text write of the same note is refused by the existing free-text rule — prove the guard") has no code guard to prove: the rule is prompt-only (#340 S3) and `_process_knowledge_updates`'s legacy branch writes any category. Reported, not fixed; filed as GH#609 (`stamp`, two-way, with the proposed chat-channel guard) and pinned as a strict `xfail` in `tests/test_coach_hevy_note_signals.py` that landing the guard must flip.
- **VERIFY scope, PR-A:** user 9's rows (`pelvis`, `foot/hip`) are not readable through this session's MCP connector, which serves the connected user; that half of the body-part read rests on chat's 2026-11-03 read, and the tolerance test uses the `foot/hip` shape from the retirement fixture. User 1's six active parts were read and match chat's read.
- **PR-A fixtures:** nine backend test files wrote synthetic off-vocabulary injuries (`part a`, `left hamstring`) or `restrictions` on new rows through the upsert; repointed to vocabulary parts or to a direct ORM row (the legacy shape they stood for). `hand` was added to the "obvious" vocabulary set (the brief did not name it). The vocabulary is listed in the prompt (19 words), unlike the 36 region keys #344 removed; the cost is declared in the parity guard.
- **PR-B card state:** a restriction's state after the POST lives for the visit; a fresh load shows the button again and asking again creates nothing (idempotent). A read-only plan would need a GET the brief did not ask for (nits, G7).
- **PR-C layout:** the brief's "above any catch-up card" is not met literally; the missed-PM card keeps its place at the top of the saved view (#407) and the block sits below the readiness baseline, above the buttons. Recorded in #495.
- **D4:** operator slot O-A reads neither `done` nor `not done` in the brief as received, so the `injury_sweep` manual checklist was left untouched.
- **Branch names:** the brief's five names were used (`gov/...`, `feat/...`), one branch per concern, rather than the harness-assigned `claude/sweet-cray-4tf2na`, which received no commits and is left local at master.

Provisional: nothing decided and uncommitted. Outside the tree and only as durable as its source: GH#608 and GH#609 on the tracker; the prod reads (`get_injuries`, `get_constraints`) are point-in-time.

## Cold-resume handoff

**Next action (the single clearest).** The operator rules GH#608 (`fork`, one-way: should the coach propose constraints and findings from clinical documents, with clinician authority pre-selected at confirm). Alongside it, two operator slots from the brief: O-A (replace Athlete_Profile's injury section in project knowledge with a pointer to the app, then say `done <date>` so the one-line `injury_sweep` checklist edit can land) and O-B (after this morning's deploys, save the next AM check-in and report whether the Needs your call block appeared; at the 4 Nov read there are zero proposals and zero reviews due, so "no block" is the expected and correct result). For Code, GH#609 (`stamp`) is acted on by the next PR touching the chat write path unless the operator objects.

**Current sprint (`ROADMAP.md` NOW).** The "Injury lifecycle in-app" lane is DONE (all five PRs merged 4 Nov 2026; design 0009 at `discussion` with row 1 resolved and nine rows open). The rest of NOW is as the 2 Nov close-out left it: fifteen DONE rows, and the open ones with owner: Q231 RPE fallback (Code, once the gate opens; January 2027); Source hierarchy (Luke); Polar sport-id relabel (OWED, remaining limbs); HC sync reliability (OWED, the #371 overlap proof); Garmin self-evaluation read, first live run (operator); Injury clearance (operator); Aerobic ingest automated (operator check); Session fidelity G6 (operator, after deploy); the cross-repo shared-block edit (OWED, pinned by #112); HC zones Q159 stage 2 (Code, low priority). The wake-day capture lane still owes its three-morning gate record (mornings 2 and 3) and the Decision-tier record after it.

**Open `fork` issues.** GH#608 (filed this session). Open `stamp`: GH#609 (filed this session) and GH#593 (from the 2 Nov close-out). Open `design` pointers: GH#537 to GH#544 and GH#603.

**Design docs not in a terminal state.** `docs/design/` 0001 canonical exercise layer, 0004 load-model routing and gaps, 0005 HR input layer, 0006 sleep writers and admission, 0007 in-app chat architecture (all `ideation`); 0002 plan-log reconciliation, 0003 constraints engine tier is `committed` (not listed), 0008 SpO2 detector and guardrail, 0009 injury model (all `discussion`). 0009's open rows are the LATER block "Injury model lanes (design 0009)" in ROADMAP: cap/require behind a dose seam (one-way), problem/episode split, tissue-based review defaults, the niggle persistence rule, regional load exposure (needs 0001), the red-flag class (one-way), per-session pain capture (owed to 0002), the OSTRC-style weekly capture, and GH#608.

### What was NOT touched

This session was one lane, the injury lifecycle, inside the Fitness module, and it was built to the brief: validation, a card action, a surface, a prompt paragraph. Everything below stood still, and a reader should not infer from this file that it is queued or finished.
- **Design 0009's model itself.** Nothing here treats an injury differently: no `cap` or `require` kind, no problem/episode split, no tissue table, no red-flag class, no overuse capture, no regional load. The seven optional fields are admitted and read by nothing; a field nobody reads is an affordance, not a feature. The next injury session should pick ONE row of 0009 and build its consumer, not widen the shape again.
- **The engine.** `is_contraindicated`, `compute_probe_queue` and the engine-defaults planner are proven unchanged by this session's rows (the changes-nothing test); no verdict moved. The aerobic-base review on 2026-11-16 that re-opens probes is unaffected.
- **Medical Protocol and Decision Support.** CBT-I, labs and the interpretation layer, appointments, and `clinical_documents.py`'s contract (un-interpreted until GH#608 is ruled) did not move. Q231's imputed-load consumer, named by the 2 Nov close-out as the thing to build next on the sRPE side, did not move either; this session went to the injury lane instead, by the operator's nomination.
- **The operator-owed lanes in NOW** above did not move.
- **Known gaps left by design:** the card's restriction states are per visit (PR-B nits); the free-text category guard is a stamp, not code (GH#609); user 9's ledger is unread by this session; the AM saved screen's block has not been seen live (O-B).

### v1-triage (which v1 test each NOW lane serves)

Read from each row's own "Serves" claim; nothing here is a new ruling.
- **Loop:** Injury lifecycle in-app (DONE; what needs the operator's call appears on the morning screen); Wake-day capture (DONE, gate record owed); Missed-PM catch-up (DONE); CBT-I titration direction (DONE); Session fidelity (built, G6 owed).
- **Know:** Injury lifecycle in-app (DONE; the ledger is the only authority and nothing outside the app is needed to keep it true); Constraints engine tier (DONE, lane closed); Source-neutral sRPE store and In-app sRPE capture (DONE); Polar relabel (OWED); Garmin self-evaluation read (OWED); Phase posture split (DONE, one read owed); Phase-change form (DONE); Injury clearance (OWED); Garmin account repair (DONE); Typed constraints (DONE, the S6 script now retired).
- **See:** Data freshness and the home load card (DONE); Plan/schedule and recent-sessions tools (DONE); Garmin overnight SpO2 (DONE); RPE fallback Q231 (OWED); Source hierarchy (OWED); HC sync reliability (OWED); Aerobic ingest automated (OWED); HC zones Q159 stage 2 (OWED).
- **Serves no v1 test:** CBT-I Q45 nap attribution, CBT-I manual evaluation trigger, Training v0.1 exercise tags seed (all DONE, riding NOW because DONE rows are never moved out); the cross-repo shared-block lane (OWED) sits in NOW by #112's stated reason.
- **Demotion candidates:** the DONE rows older than a month (August and September) are the clearest; ROADMAP's "Moved from NOW" precedent covers them. Not moved this session.
