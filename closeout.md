# Close-out — 5 Nov 2026: proposal edit and the write receipt (`DECISIONS_LOG` #497, #498; GH#617, GH#612 closed)

## Real commits this session

Session opened at health-app master `64d10b3` (the merge of PR 618, the previous close-out). Maxima at open: `DECISIONS_LOG` #496, three open `fork` issues (GH#608, GH#613, GH#614). At close: master max #498 (both minted by this session), the same three `fork` issues open, GH#617 and GH#612 closed by their PRs. The brief was pasted (`Proposal Edit And Receipts - Aubrey 4 Nov Debrief`), followed by two operator rulings in-turn (V2 accepted; the prompt-byte guard not to be raised); no issue carried it.

The four commits of this session, by the session trailer (`git log --format="%h %ad %s" --date=short 64d10b3..origin/master`, merges excluded):

```
14ef99b 2026-11-04 feat(proposal-edit): Edit on a proposed card writes a superseding proposal through the existing upsert
0ec2203 2026-11-04 gov(proposal-edit): ruling #497; BRANCHES row; ROADMAP lane row PR-A done
f54a8a7 2026-11-04 feat(write-receipt): the coach's reply carries a server-rendered receipt of what it wrote
375eccf 2026-11-04 gov(write-receipt): ruling #498; BRANCHES row; ROADMAP lane row PR-B done, lane done
```

The two merges onto master (`git log --first-parent 64d10b3..origin/master`), each self-merged on green under § Merge disposition, both two-way doors, no migration:

```
864be53 Merge pull request #619 from Easty11/claude/compassionate-heisenberg-h7u362   (PR-A, #497)
7d8a59e Merge pull request #620 from Easty11/claude/compassionate-heisenberg-h7u362   (PR-B, #498)
```

Deploy checks (#491, the `deploy-check` workflow read through the GitHub MCP): `864be53` success (backend and frontend changed). `7d8a59e` success (backend changed; frontend SKIPPED is the expected read, #433).

This close-out's own commit, `chore: session close-out`, follows these on a third use of the harness branch and lands as a docs-only PR; it names no hash here because a commit cannot name itself.

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief and two in-turn operator rulings; each step against where it landed:

| Brief step | Landed in |
|---|---|
| V1 to V4 verified before any write | below, this section; no mismatch that halted the lane |
| A1 backend edit path through `upsert_knowledge_entry`, refusals with reasons | `14ef99b` (`_edit_proposal`, two routes) |
| A2 editable fields, `parent_key` through `invalid_parent` | `14ef99b` (`PROPOSAL_EDITABLE_FIELDS`) |
| A3 Edit on every proposed card, inline form, verbatim refusal, successor shown, never confirms | `14ef99b` (`ProposalEditForm` in the shared `InjuryActions.jsx`, Injuries page and AM saved screen) |
| A4 tests | `14ef99b`: `tests/test_proposal_edit.py` (11), `components/InjuryActions.edit.test.jsx` (5), one assertion in `pages/CheckInAM.pending.test.jsx` |
| B1 server-rendered receipt | `f54a8a7` (`_RECEIPT_HEADER`, `_RECEIPT_ECHO_RE`, the "(re: …)" suffix, `WriteResult.entry_type` / `parent_key`) |
| B2 coach guidance, trimmed per the operator's ruling | `f54a8a7`: one byte-neutral sentence replacing the closing sentence of the knowledge-update section |
| B3 tests, prompt-byte cost noted | `f54a8a7`: `tests/test_chat_write_receipt.py` (6); guard 11707 → 11707 |
| Concern-split commits, one gov commit per landed ruling, PRs ready-for-review, self-merge on green, numbers resolved at merge | the four commits above; PRs 619 and 620; #497 and #498 resolved from master's max re-read before each merge |
| Guard: no ledger row confirmed, declined, edited or resolved; engine-default behaviour unchanged | held: the edit route was built and exercised only in tests; `_propose_engine_defaults` untouched |

**V1 to V4 results.**
- **V1.** Re-confirmed on `64d10b3`: an `api`-source upsert supersedes a `proposed` row under the same key when the successor is also `proposed` (`_typed_supersede_guard` guards chat only; `confirm_via_route` refuses a confirmed status over an unconfirmed row); the predecessor keeps its value, source and notes and gains `superseded_by`. Pinned by `test_edit_supersedes_the_proposal_and_keeps_the_coachs_original`.
- **V2.** `SOURCE_VALUES = ("onboarding", "chat", "system", "api")`, Python-validated on `user_knowledge_entries.source` (no DB CHECK on that table; migration `f4e9d2c1b3a7`). A NEW value would widen the tuple past `training_phases`' frozen CHECK `ck_training_phase_source` (a migration) or split the vocabulary (two tests pin the tuple). Not taken. The existing `api` value is the app's operator channel (the injury card's Edit writes it; confirm, resolve and review are operator routes) and the route is operator-authenticated, so the successor's `source: "api"` plus `notes: "edited in-app from #<id>"` records the editor. **Operator accepted in-turn (5 Nov): no new source value.**
- **V3.** `pages/Injuries.jsx` renders proposals through the shared `ProposalList` (under the parent card, and an "Other proposals" region for orphans) with User / Clinician / Confirm proposal and Decline…; `pages/CheckInAM.jsx` renders the same `ProposalList` in "Needs your call". One Edit in `ProposalItem` therefore covers both surfaces.
- **V4.** `routers/chat.py` `_process_knowledge_updates` executes every typed write (finding, constraint, appointment, injury) through `upsert_knowledge_entry`; success records `✓ <noun> saved: <key>`, a refusal `✗ <noun> NOT saved: <key> — <validator message>` with its code, each as one `WriteResult`; the Q185 in-turn retry replaces a shape refusal's result in place.

**The refusal text the card shows** (verbatim from the validator, through the 422), for the off-vocabulary region the clinician's words suggest:

```
constraint.scope.region_keys: unknown region key(s) ['deep_squat'] -- valid keys: ['hinge', 'squat', 'lunge_single_leg', 'horizontal_push', 'vertical_push', 'horizontal_pull', 'vertical_pull', 'carry', 'rotation', 'anti_rotation', 'trunk_lateral_flexion', 'dip', 'ankle_df', 'hip_flexion_pc_length', 'hip_ir_er', 'tspine_rotation', 'shoulder_mobility', 'trunk_stability_sagittal', 'rotary_stability', 'frontal_single_leg_stability', 'anti_lateral_flexion', 'gait_load_carriage', 'terrain_perturbation', 'aerobic_base', 'repeat_effort', 'single_leg_hop', 'deceleration_landing', 'change_of_direction', 'sit_to_rise', 'gait_speed', 'grip_strength', 'single_leg_balance_eyes_closed', 'loaded_carry_capacity_bw', 'shoulder_er', 'shoulder_ir', 'hip_adduction', 'hip_abduction', 'ankle_plantarflexion', 'knee_flexion']
```

The other refusals the route returns: `Constraint entry is 'confirmed' -- only a proposal is edited; a row past proposed is reviewed (POST /knowledge/constraints/<id>/review) or retired, never rewritten` (409); `Constraint entry is inactive (superseded by a later write) -- only an active proposal can be edited` (409); `Constraint entry: ['status'] cannot be edited on a proposal -- editable: kind, scope, exit, review_by, parent_key, detail` (422); `nothing to edit -- send at least one of: …` (422); the existing `invalid_parent` messages for a missing or self-naming parent (422).

**The prompt-byte delta.** The #43 guard (`tests/test_current_state.py`, `test_context_builder_output_unchanged_pre_post_refactor`) pins the knowledge-update section at 11707 bytes. The first B2 paragraph would have moved it to 12054 (+347) and was dropped on the operator's ruling; the landed guidance is one sentence replacing the section's closing sentence at identical length: **11707 → 11707 (0)**. The one failure in the first local full run came from neither tree: the test runs `git show 3360ed5:backend/context_builder.py` and the session's clone was shallow; it passed on PR-A once the history was fetched, and in CI on both PRs.

Departures from the brief, each reported at its gate:
- **A2 interpretation:** an advisory constraint's scope is its text, so the form edits the instruction where the brief said "scope (regions, side)"; the backend takes `scope` whole and the validator decides. Reported in the PR-A body.
- **A4's brief test:** a proposal never renders in the appointment brief (its hard exclusion), so the re-parent test asserts the edited row is absent until confirmed, confirms it as the test's own step, then asserts it renders under `current_constraints` with its parent through the loader and the MCP tool.
- **B2:** trimmed from a paragraph to one sentence on the operator's ruling; recorded above.

Provisional: nothing decided and uncommitted. Outside the tree and only as durable as its source: GH#612 and GH#617 closed on the tracker; the prod ledger is untouched (no row confirmed, declined, edited or resolved this session).

## Cold-resume handoff

**Next action (the single clearest).** The operator uses the Edit action on the 4 Nov proposals that need it (re-parent #180, #194, #199, #201, #203, #205, #207 onto their injuries; narrow #199 / #207's regions to the clinician's words; collapse the near-duplicate pairs by declining one of each), then confirms or declines; every one of those is an operator act this session did not perform. Then rule GH#613 and GH#614 (forks), and GH#608 still waits. GH#616 (`verify`) closes when read. Code's next lane without a ruling: GH#613's proposed answer (the `parent_key` prompt sentence beside the write shape, #313/§45 pattern) is a one-sentence prompt change that must fit the #43 guard the same way B2 did.

**Current sprint (`ROADMAP.md` NOW).** The "Coach ledger writes" row: lane `Proposal Edit And Receipts` DONE (PR-A → #497, PR-B → #498, both 5 Nov 2026); open from it GH#613, GH#614 (forks), GH#615 (watch), GH#616 (verify). The "Injury lifecycle in-app" lane is DONE (4 Nov); design 0009 at `discussion`, row 1 resolved, nine rows open. The rest of NOW is as the 4 Nov close-outs left it: fifteen DONE rows, and the open ones with owner: Q231 RPE fallback (Code, once the gate opens; January 2027); Source hierarchy (Luke); Polar sport-id relabel (OWED, remaining limbs); HC sync reliability (OWED, the #371 overlap proof); Garmin self-evaluation read (operator); Injury clearance (operator); Aerobic ingest automated (operator); Session fidelity G6 (operator); HC zones single-row read (Code, low priority); the cross-repo `#NEXT` extension (OWED). Operator slots still open from the 4 Nov close-out: O-A (Athlete_Profile's injury section replaced by a pointer) and O-B (the AM saved screen's proposal block seen live, which now also carries Edit).

**Open `fork` issues.** GH#608 (coach proposals from clinical documents, one-way), GH#613 (I2), GH#614 (I3). Open `stamp`: GH#609, GH#593 and the older stamps. Open `design` pointers: GH#537 to GH#544, GH#603. Open `watch`: GH#615. Open `verify`: GH#616. Closed this session: GH#617 (PR 619), GH#612 (PR 620).

**Design docs not in a terminal state.** 0001 canonical exercise layer, 0002 plan-log reconciliation, 0004 load-model routing and gaps, 0005 HR input layer, 0006 sleep writers and admission, 0007 in-app chat architecture (`ideation`); 0008 SpO2 detector and guardrail, 0009 injury model (`discussion`). 0003 is `committed`. Nothing in `docs/design` moved this session.

### What was NOT touched

This session built two small things inside the Fitness module's ledger loop: an edit route plus its form, and a receipt line. Everything below stood still, and a reader should not infer from this file that it is queued or finished.
- **The coach's proposals themselves.** The coach still writes constraint proposals without `parent_key` (GH#613's prompt sentence is not landed), still can write a healed injury as an active row and stage engine defaults for it (GH#614 unruled, `_propose_engine_defaults` untouched), and region blocks still cannot express depth (GH#615, waits on 0009 row 3). The edit route is the operator's correction path for all three; it corrects nothing by itself, and nothing was corrected in prod this session.
- **The 4 Nov ledger.** 13 PENDING constraint proposals and 2 PENDING finding proposals remain as the 5 Nov read found them; two active calf rows (#184 and #206) still read "Resolved." in their detail.
- **The receipt's reach.** The receipt covers the knowledge, schedule, routine and exercise write lanes through `write_results`; the capability lane's lines ride under the header as before but are not write results. The Q187 no-write notice and the check-in notice are unchanged, so a turn that writes nothing and claims a write still gets the old notice, not a receipt.
- **The MCP read doors.** `get_constraints` still hides superseded rows in every status; an edited proposal's kept original is read on the card's history, not through MCP. No MCP tool exposes the chat transcript.
- **Design 0009's model**, **Medical Protocol and Decision Support** (CBT-I, labs, interpretation, appointments, `clinical_documents.py`'s contract pending GH#608), and **the operator-owed lanes in NOW** did not move. Q231's imputed-load consumer did not move; four sessions in a row have now gone to the injury and ledger side rather than to it.

### v1-triage (which v1 test each NOW lane serves)

Read from each row's own "Serves" claim; nothing here is a new ruling.
- **Know:** Coach ledger writes (lane DONE; a proposal the operator corrects is the row they meant, and the reply's receipt is what the turn wrote); Injury lifecycle in-app (DONE); Constraints engine tier (DONE, lane closed); Source-neutral sRPE store and In-app sRPE capture (DONE); Polar relabel (OWED); Garmin self-evaluation read (OWED); Phase posture split (DONE, one read owed); Phase-change form (DONE); Injury clearance (OWED); Garmin account repair (DONE); Typed constraints (DONE, the S6 script now retired).
- **Walk in:** Coach ledger writes (lane DONE; a re-parented constraint reaches the appointment brief once confirmed); Appointment brief (v1 built, test 3 met).
- **Loop:** Injury lifecycle in-app (DONE); Wake-day capture (DONE, gate record owed); Missed-PM catch-up (DONE); CBT-I titration direction (DONE); Session fidelity (built, G6 owed).
- **See:** Data freshness and the home load card (DONE); Plan/schedule and recent-sessions tools (DONE); Garmin overnight SpO2 (DONE); RPE fallback Q231 (OWED); Source hierarchy (OWED); HC sync reliability (OWED); Aerobic ingest automated (OWED); HC zones Q159 stage 2 (OWED).
- **Serves no v1 test:** CBT-I Q45 nap attribution, CBT-I manual evaluation trigger, Training v0.1 exercise tags seed (all DONE, riding NOW because DONE rows are never moved out); the cross-repo shared-block lane (OWED) sits in NOW by #112's stated reason.
- **Demotion candidates:** the DONE rows older than a month (August and September) are the clearest; ROADMAP's "Moved from NOW" precedent covers them. Not moved this session.
