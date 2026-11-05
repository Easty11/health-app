# Close-out — 5 Nov 2026: ledger ruling and resolve (`DECISIONS_LOG` #501; GH#608, GH#622, GH#627 closed; GH#632 filed)

## Real commits this session

Session opened at health-app master `eff62f1` (the merge of PR 630, the previous close-out). Maxima at open: `DECISIONS_LOG` #500, one open `fork` issue (GH#608). At close: master max #501 once this PR lands (one entry, the R1 to R3 ruling), no open `fork` issue (GH#608 closed by this PR), GH#622 closed by PR 631, GH#627 closed by this PR, GH#632 `stamp` filed. The brief was pasted (`Ledger Ruling And Resolve - Aubrey 4 Nov Debrief`); no issue carried it.

Two PRs from the one harness-assigned branch `claude/intelligent-sagan-du9cyu` (restarted from master after PR 631 merged and the remote branch was gone):

| Commit | PR | What |
|---|---|---|
| `db43350` feat(knowledge): GET /knowledge/confirmed lists the rows in force (GH#622) | 631, merge `b132917` | the read: active confirmed constraints and active open/confirmed non-lab findings; `tests/test_confirmed_read.py` (7) |
| `9153cae` feat(injuries): confirmed rows on their card, resolvable at any time (GH#622) | 631 | `ConfirmedList` / `ConfirmedItem` in `InjuryActions.jsx`, the card list and the "Attached to no active injury" section in `Injuries.jsx`, Resolve through the one retire route per type; `Injuries.confirmed.test.jsx` (7) |
| `af1b11e` feat(knowledge): chat may not rewrite or retire an operator-written typed row (GH#608 R3) | this PR | `chat_may_not_rewrite_operator_row`, `OPERATOR_SOURCES = ("api",)`, the guard in `_typed_supersede_guard`, the chat deactivation branch, `operator_route_hint` naming Edit for a proposed typed row; one negative control re-aimed |
| `1cfe4df` feat(coach): typed ledger write guidance, landed by trimming (GH#627; GH#608 R2/R3) | this PR | four sentences beside the write shapes; 11707 → 11702 (−5) re-declared in `test_current_state.py`; `tests/test_coach_ledger_guidance.py` (8) |
| the `docs(clinical_documents)` commit | this PR | the R1 sentence under the module's NO INTERPRETATION contract |
| the `gov(ledger-ruling)` commit | this PR | `DECISIONS_LOG` #501, design 0009 row 10, the ROADMAP rows, the two BRANCHES rows and one flipped loop, the `CLAUDE.md` pointer, this file |

The last two cannot name their own hashes here (a commit cannot name itself); read them with `git log --first-parent -3` on the merge. No migration, no prod write, no ledger row confirmed, declined, edited or resolved (the resolve UI was built, never used: #110 and #102 are the operator's to resolve now that PR 631 is live).

Tracker writes this session (outside the tree, as durable as the tracker): GH#632 `stamp` filed (R3's scope: injury and appointment rows); GH#622 closed by PR 631; GH#608 and GH#627 closed by this PR's `Closes`; a pointer comment on GH#608 after the merge naming the entry number.

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief; each step against where it landed:

| Brief step | Landed in |
|---|---|
| OPERATOR RULING R1 to R3 recorded as one entry, number at merge | `DECISIONS_LOG` #501 (Decision tier: R1 is a cross-module contract) |
| close GH#608 with a pointer | `Closes` in this PR's body; a one-line comment with the entry number after the merge |
| update 0009 row 10 | proposed answer and status (`resolved → #501`), `Last moved` 2026-11-05, the Decisions-landed line |
| V1 to V3 verified before any write | below |
| PR-A A1 to A4 (GH#622) | PR 631 (`db43350`, `9153cae`); A3 held: `/review-due` and `ReviewDue` untouched, pinned by `test_the_sweep_is_unchanged_a_due_row_is_in_both_lists_and_a_future_row_only_here` and the sweep test in `Injuries.confirmed.test.jsx` |
| PR-B B1 (a) to (d) guidance | `1cfe4df`; (c) was already in the shape block ("Never send status, asserted_by, …"), kept as it stood |
| PR-B B2 enforce (c) and (d) | (c) already enforced by `_validate_typed_write` (`proposal_only`), unchanged; (d) built in `af1b11e`; both refusals appear in the receipt (tested) |
| PR-B B3 tests, one per sentence, (d) refused in the receipt | `tests/test_coach_ledger_guidance.py` (8) |
| PR-B B4 byte guard: trim, don't raise; record the delta | 11707 → 11702 (−5), below |
| Gates: no migration, no prod writes, concern-split commits, one gov commit, PRs ready-for-review, self-merge on green, numbers at merge | held (PR 631 self-merged on three green checks; this PR the same) |
| Guard: no ledger row confirmed, declined, edited or resolved | held (reads only: `get_constraints`, `get_injuries`) |

**V1 to V3 results.**
- **V1 (Certain).** No current path pre-sets `asserted_by` or pre-selects an authority for a coach proposal. Backend: the chat channel stamps `asserted_by: null` when absent (`TYPED_CHAT_DEFAULTS`, `routers/chat.py`), and `_validate_typed_write` refuses a chat write carrying any authority with `proposal_only` — "a constraint written from chat is a PROPOSAL: status must be 'proposed' and asserted_by null -- the operator confirms it via POST /knowledge/constraints/{id}/confirm"; `ConfirmIn.asserted_by` has no default and `_confirm_entry` refuses a value outside `user | clinician`. Frontend (`components/InjuryActions.jsx`): `ProposalItem`'s `by` state and `BasisForm`'s start empty on every open, so Confirm, Decline and Resolve all begin with nothing selected. R2 changes no code; it is pinned end to end (the refusal is listed in the receipt as "⚠ 0 saved, 1 failed — proposal_only").
- **V2 (Certain for the code, Likely for the prod rows).** The discriminator is the row's `source`, no migration: `api` is the operator's channel (the in-app proposal Edit writes `source: "api"` with `notes` "edited in-app from #N"; the injury card's Edit writes `api`; the operator's PowerShell writes carry `api`), `chat` is the coach, `system` the engine defaults, `onboarding` the first-run flow. Enforced for constraint and finding rows, proposed or not. Prod rows (MCP reads 2026-11-05 11:56): #167 (`constraint_injury_calf_left_straight_knee_load`, the operator's precise calf record) is listed under resolved as "declined 2026-11-02 by user", never superseded, so on 4 Nov it was already inactive and no write-path refusal could have engaged; the coach's #178 was a fresh write, not a supersede. #166 and #178 are not readable through this session's MCP (#178 is neither a listed constraint nor an injury; the E1 comment describes #166 as the appointment asks, which have no MCP read), so whether R3 would have protected #166 rests on chat's read that it was operator-written and on its type: as an `api`-source constraint or finding, yes; as a planned appointment, no (chat is instructed to rewrite planned appointments whole, and there is no in-app Edit for the refusal to name). Scope not covered, reported here and filed as GH#632 `stamp`: an operator-edited injury row (#215 is `source api`) and an operator-written planned appointment stay rewritable by chat. No HALT: the discriminator exists without a migration.
- **V3 (Certain).** The sweep is `GET /knowledge/review-due` (`routers/knowledge.py` `review_due`): one query of the user's active rows; a confirmed constraint is listed when `constraint_due_tags` is non-empty (`review due`: `review_by` passed; `exit due`: `exit.on_date` passed or a `with_parent` exit whose parent is no longer active), an open/confirmed non-lab finding when its `review_by` has passed; proposals never; lab-derived findings counted as `withheld_labs`. Routes it uses: Resolve is `POST /knowledge/constraints/{id}/resolve` or `POST /knowledge/findings/{id}/retract` (basis required, `resolved_by` in `user | clinician`); Keep is `POST /knowledge/{constraints,findings}/{id}/review` with a future `review_by`, in place. Rendered by `ReviewDue` / `DueItem` (`components/InjuryActions.jsx`) at the top of the Injuries page and under "Needs your call" on the AM check-in's saved screen (`pages/CheckInAM.jsx`). PR-A built beside it, through the same retire routes and `BasisForm`; the sweep is unchanged.

**Refusal texts, quoted.**
- R3 upsert (`_typed_supersede_guard`, code `operator_only`): `constraint 'constraint_knee_left_cap' was written or edited by you in the app, so chat may not rewrite it -- correct it with Edit on its card`. The receipt line: `✗ Constraint entry NOT saved: constraint_knee_left_cap — constraint 'constraint_knee_left_cap' was written or edited by you in the app, so chat may not rewrite it -- correct it with Edit on its card. Only you can do this: edit it yourself with Edit on its card on the Injuries page (/injuries) or the morning check-in's saved screen (POST /knowledge/constraints/{id}/edit).`; tally `⚠ 0 saved, 1 failed — yours to change`.
- R3 deactivation (`routers/chat.py`): `✗ Constraint entry NOT removed: constraint_knee_left_cap — you wrote or edited it in the app, so only you can change it: edit it yourself with Edit on its card on the Injuries page (/injuries) or the morning check-in's saved screen (POST /knowledge/constraints/{id}/edit).`
- R2 (standing, `_validate_typed_write`, code `proposal_only`): `a constraint written from chat is a PROPOSAL: status must be 'proposed' and asserted_by null -- the operator confirms it via POST /knowledge/constraints/{id}/confirm`.

**Byte delta.** `_section_knowledge_update` 11707 → 11702 (−5). Added: the `parent_key` bullet (constraint) and clause (finding), the resolved-event bullet on the injury shape, the never-rewrite sentence. Trimmed: "take the values from the conversation and the data above", the "Shall I record it?" example, "Chat is not where a proposal is confirmed:", "(it leaves the probe queue)", "and leaves any other row out", "(a knee scan does not settle a lumbar constraint)", "a side in the name", the free-text append sentence, the "save proactively" sentence, the tool-wrapper aside. Every pinned phrase (`test_chat_no_silent_turn`, `test_typed_write_shape_docs`, `test_coach_hevy_note_signals`, `test_knowledge_payload`, `test_pocket_ep_write_integrity`, `test_injury_shape`, `test_appointment_entries`) still holds; `test_current_state.py` re-declared.

Departures from the brief: none in scope. One addition: GH#632 filed for R3's uncovered row types (V2 asked for the report; the stamp is the loop's form for it). CI: PR 631 green on `placeholder guard (POSIX)`, `backend tests (pytest)`, `frontend tests (vitest)`; `deploy-check` run 16 on `b132917` SUCCESS. Backend full suite 4449 passed locally with PR-B on top of PR-A; frontend 566 passed.

Provisional: nothing decided and uncommitted. The prod reads are point-in-time (11:56 AEST).

## Cold-resume handoff

**Next action (the single clearest).** The operator resolves #110 (`constraint_shoulder_right_er_load_cap`, duplicated by the confirmed #214 v2 cap) and #102 (`constraint_cervical_contact_return`, overtaken by the confirmed caution #213) on the Injuries page, now that PR 631 is live (the row's Resolve… on its card, basis and authority). Then the next product lane that is not a follow-up of this debrief: Q231's imputed-load consumer (RPE fallback), six sessions in a row having gone to the injury and ledger side.

**Current sprint (`ROADMAP.md` NOW).** "Ledger UX follow-ups": GH#622 and GH#627 DONE this session; open from it GH#623, GH#624, GH#625 (`stamp`, the next card PR), GH#628 (`verify`, operator reads), GH#626 and GH#629 (`watch`). "Coach ledger writes": lane DONE, forks ruled (#499, #500, #501); open GH#615 (`watch`), GH#632 (`stamp`). "Injury lifecycle in-app": DONE; design 0009 at `discussion`, rows 1 and 10 resolved, eight open. The rest of NOW is as the 5 Nov close-outs left it (fifteen DONE rows; the open ones with owner: Q231 RPE fallback (Code, once the gate opens; January 2027); Source hierarchy (Luke); Polar sport-id relabel (OWED); HC sync reliability (OWED); Garmin self-evaluation read, Injury clearance, Aerobic ingest automated, Session fidelity G6 (operator); HC zones single-row read (Code, low priority); the cross-repo `#501` extension (OWED)). Operator slots still open: O-A (Athlete_Profile's injury section replaced by a pointer) and O-B (the AM saved screen's proposal block seen live).

**Open `fork` issues.** None once this PR merges (GH#608 → #501). Open `stamp`: GH#632, GH#623, GH#624, GH#625, GH#609, GH#593 and the older stamps. Open `build`: the older builds (GH#622 and GH#627 closed). Open `watch`: GH#615, GH#626, GH#629. Open `verify`: GH#628. Open `design` pointers: GH#537 to GH#544, GH#603.

**Design docs not in a terminal state.** 0001 canonical exercise layer, 0002 plan-log reconciliation, 0004 load-model routing and gaps, 0005 HR input layer, 0006 sleep writers and admission, 0007 in-app chat architecture, 0008 SpO2 detector and guardrail (`ideation`); 0009 injury model (`discussion`, row 10 resolved this session). 0003 is `committed`.

### What was NOT touched

- **The document-sourced proposal path.** R1 allows it; nothing is built: the coach still proposes from what the operator types or pastes, and `clinical_documents.py` still creates nothing from a document. A build needs its own entry naming the document fields a proposal may cite.
- **Injury and appointment rows under R3.** Chat can still rewrite an operator-edited injury row and an operator-written planned appointment (GH#632). The knee row #215 carries the operator's wording as `source api` today; the next coach rewrite of it would replace that wording, and only the history on the card keeps the original.
- **The three card stamps (GH#623 to GH#625)** — the confirmed row now shows its key, the proposal card still does not; the parent field is still free text; a moved card still gives no notice.
- **The frontend's update path (GH#628)**, **the clearance sweep's word matching (GH#629)**, **the free-text store (GH#626)**, **the engine-default hook** (unchanged by #500) and **design 0009's model** did not move.
- **Medical Protocol and Decision Support** (CBT-I, labs, interpretation, appointments) and **the operator-owed lanes in NOW** did not move. Q231's imputed-load consumer did not move; this is the sixth consecutive session on the injury and ledger side.

### v1-triage (which v1 test each NOW lane serves)

Read from each row's own "Serves" claim; nothing here is a new ruling.
- **Know:** Ledger UX follow-ups (the ledger the operator keeps in the app is the whole ledger: every confirmed row is now visible and resolvable in-app); Coach ledger writes (the coach's proposal is the row the operator meant: parented by guidance, never an operator row rewritten); Injury lifecycle in-app (DONE); Constraints engine tier (DONE); Source-neutral sRPE store and In-app sRPE capture (DONE); Polar relabel (OWED); Garmin self-evaluation read (OWED); Phase posture split (DONE); Phase-change form (DONE); Injury clearance (OWED); Garmin account repair (DONE); Typed constraints (DONE).
- **Loop:** Ledger UX follow-ups (what the operator could not do in-app on 5 Nov is an in-app act since PR 631); Injury lifecycle in-app (DONE); Wake-day capture (DONE); Missed-PM catch-up (DONE); CBT-I titration direction (DONE); Session fidelity (built, G6 owed).
- **Walk in:** Coach ledger writes (a parented proposal reaches the appointment brief once confirmed); Appointment brief (v1 built).
- **See:** Data freshness and the home load card (DONE); Plan/schedule and recent-sessions tools (DONE); Garmin overnight SpO2 (DONE); RPE fallback Q231 (OWED); Source hierarchy (OWED); HC sync reliability (OWED); Aerobic ingest automated (OWED); HC zones Q159 stage 2 (OWED).
- **Serves no v1 test:** CBT-I Q45 nap attribution, CBT-I manual evaluation trigger, Training v0.1 exercise tags seed (all DONE, riding NOW because DONE rows are never moved out); the cross-repo shared-block lane (OWED) sits in NOW by #112's stated reason.
- **Demotion candidates:** the DONE rows older than a month (August and September); ROADMAP's "Moved from NOW" precedent covers them. Not moved this session.
