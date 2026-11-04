# Close-out — 5 Nov 2026: coach ledger writes, the 4 Nov clinician debrief (GH#608 evidence; GH#612 to GH#617)

## Real commits this session

Session opened at health-app master `600097e` (the merge of PR 611, the previous close-out). Maxima at open: `DECISIONS_LOG` #496, one open `fork` issue (GH#608). At close: `DECISIONS_LOG` max still #496 (nothing ruled, no integer minted), three open `fork` issues (GH#608, and GH#613 and GH#614 filed by this session), plus GH#612 and GH#617 (`build`), GH#615 (`watch`), GH#616 (`verify`), all filed by this session. The brief was pasted (`Coach Ledger Writes - Aubrey 4 Nov Debrief`, with Amendment 1); no issue carried it.

Commits on the branch before this close-out: none (`git log --oneline 600097e..HEAD` was empty). The brief authorised no feature code, no migration and no prod write, and none was made. This close-out's own commit, `chore: session close-out`, is the branch's only commit and lands as a docs-only PR; it names no hash here because a commit cannot name itself. Files it carries: `ROADMAP.md` (one NOW row), `BRANCHES.md` (one row), `CLAUDE.md` (Recent-landings pointer, cap of 3), `closeout.md` (this file).

Tracker writes this session (outside the tree, as durable as the tracker):

| Write | Where |
|---|---|
| Evidence comment, the debrief as a worked case, no ruling requested | GH#608, comment `6640954877` |
| I1 `build`: the coach claims a write it did not make; receipt-derived summary | GH#612 |
| I2 `fork`: injury-scoped proposals without `parent_key` fall out of brief scope (Amendment 1 wording) | GH#613 |
| I3 `fork`: a healed injury written active fires engine defaults for a healed tissue | GH#614 |
| I4 `watch`: region blocks cannot express depth; 0009 row 3 resolves it | GH#615 |
| I5 `verify`: the parenting gap is the coach never sending `parent_key`; determination in the body | GH#616 |
| I6 `build`: Edit on a proposed card writes a superseding proposal; the VERIFY it asked for is in the body | GH#617 |

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief and its amendment; each step against where it landed:

| Brief step | Landed in |
|---|---|
| V1 to V4 verified before any write (MCP read doors and the tree) | below, this section; no mismatch that undermined the brief |
| Step 1: GH#608 comment, the session as a worked case | GH#608 comment `6640954877` |
| Step 2: I1 to I5 filed, four fields each, labels as given | GH#612, GH#613, GH#614, GH#615, GH#616 |
| Amendment 1: I6 filed; I2's proposed answer replaced by the re-parenting-through-I6 wording | GH#617; GH#613 body |
| Step 3: ROADMAP lane row naming I1 to I6 and GH#608 | `ROADMAP.md` NOW, first row, in this commit |
| LOG: issues filed, V1 to V4 results, mismatches | this file |
| Guard: no confirm, decline or resolve of any ledger row; no integer minted | held: reads only through `get_constraints` and `get_injuries`; `DECISIONS_LOG` untouched |

**V1 to V4 results** (prod read 2026-11-05 06:06 to 06:07 Brisbane, through the MCP read doors):
- **V1, proposals.** #180 proposed with no parent, as stated. #185 to #187 parented to `injury_calf_left_oct2026`, as stated. #182, #183 and #188 are listed under neither `proposed` nor `resolved`; `get_constraints` hides superseded rows in every status, so they were superseded (not declined). Beyond the brief's snapshot: nine newer proposals #194 to #207 exist, of which #196 to #198 are engine defaults parented to `injury_calf_left` and the rest (#194, #199, #201, #203, #205, #207) are coach-authored and unparented. The movement strengthens the brief's premise rather than contradicting it, so the session proceeded and reported it (the brief said the operator might act on rows before the run).
- **V2, injuries.** #184 `injury_calf_left_oct2026` active with detail ending "Resolved.", as stated. #119 → #179 and #118 → #181 superseded, on record 2026-11-04, as stated; the chains continue (#179 → #189 → #200 knee; #181 → #191 → #202 shoulder). Beyond the brief: a second active calf row #206 (`injury_calf_left`, after #195, under the July episode #76's key) also reads "Resolved." Two active rows for one healed tissue.
- **V3.** GH#608 open, label `fork`, body as filed by PR-D. Matches.
- **V4.** `backend/routers/knowledge.py`: `parent_key` optional on constraints (L539 to L541, L1159); `_propose_engine_defaults` (L1606 to L1631) is called from `_stage_upsert_entry` at L1732 and compares only `default_signature` (body part, side, signal type, RA flare), reading nothing the row says about itself. Matches.

Determinations the brief asked for, recorded on the issues rather than ruled here: I5 (GH#616) is answered from the write path (a `parent_key` is a key resolved at read time, an injury rewrite keeps the key, and a constraint's value is stored as sent; every parented proposal is a system-written engine default, every coach-authored one is unparented; no MCP tool exposes the chat transcript and none was needed). I6's VERIFY (GH#617): an `api`-source upsert can supersede a `proposed` row under the same key when the successor is itself `proposed` (`_typed_supersede_guard` guards chat only; `confirm_via_route` refuses a confirmed status over an unconfirmed row); the predecessor keeps its value, `source` and `notes` and gains `superseded_by`; there is no editor field, which is the build's one open choice.

Observed, outside the authorised group and so filed nowhere: decline-and-retry produced near-duplicate keys (#180 / #201, #194 / #205, #199 / #207, and `_v2` on #203), noted as evidence inside GH#617 and the GH#608 comment; the coach's write-shape section lists `parent_key` as allowed with no instruction to set it (GH#613).

Provisional: nothing decided and uncommitted. The prod reads are point-in-time.

## Cold-resume handoff

**Next action (the single clearest).** The operator rules the two forks this session filed, GH#613 (unparented injury-scoped proposals: coach guidance plus Edit, or validator refusal) and GH#614 (a healed event as a finding, or a born-resolved injury write), and GH#608 still waits. The two-way builds need no ruling and are the next Code lane: GH#617 (Edit on a proposed card, superseding proposal through the existing upsert; verify first that the card's history read shows the superseded original, since `get_constraints` hides it) and GH#612 (the closing summary derived from write receipts; extend the Q187 notice to a claimed write type with no receipt of that type). GH#613's proposed answer (the `parent_key` prompt sentence beside the write shape, #313/§45 pattern) can ride GH#617's PR. GH#616 closes when the operator reads it.

**Current sprint (`ROADMAP.md` NOW).** One new row at the top, "Coach ledger writes: the 4 Nov debrief defects", UNSTARTED. The "Injury lifecycle in-app" lane is DONE (4 Nov); design 0009 at `discussion`, row 1 resolved, nine rows open, row 10 pointing at GH#608. The rest of NOW is as the 4 Nov close-out left it: fifteen DONE rows, and the open ones with owner: Q231 RPE fallback (Code, once the gate opens; January 2027); Source hierarchy (Luke); Polar sport-id relabel (OWED, remaining limbs); HC sync reliability (OWED, the #371 overlap proof); Garmin self-evaluation read (operator); Injury clearance (operator); Aerobic ingest automated (operator); Session fidelity G6 (operator); HC zones single-row read (Code, low priority); the cross-repo `#NEXT` extension (OWED). Operator slots still open from the 4 Nov close-out: O-A (Athlete_Profile's injury section replaced by a pointer) and O-B (the AM saved screen's proposal block seen live).

**Open `fork` issues.** GH#608 (coach proposals from clinical documents, one-way), GH#613 (I2), GH#614 (I3). Open `stamp`: GH#609, GH#593 and the older stamps. Open `design` pointers: GH#537 to GH#544, GH#603. New `build`: GH#612, GH#617. New `watch`: GH#615. New `verify`: GH#616.

**Design docs not in a terminal state.** 0001 canonical exercise layer, 0002 plan-log reconciliation, 0004 load-model routing and gaps, 0005 HR input layer, 0006 sleep writers and admission, 0007 in-app chat architecture (`ideation`); 0008 SpO2 detector and guardrail, 0009 injury model (`discussion`). 0003 is `committed`. 0009's open rows are the LATER block "Injury model lanes (design 0009)"; GH#615 names row 3 as its resolver and GH#614 names row 2.

### What was NOT touched

This session was governance: reads, one comment, six issues, one ROADMAP row. Nothing in the product moved, and a reader should not infer from this file that the lane it opened is under way.
- **The coach.** No prompt sentence changed: the coach still writes constraint proposals without `parent_key`, still can write a healed injury as an active row and stage engine defaults for it, and still narrates a write it did not make on a turn that wrote something else. The six issues describe the fixes; none is built.
- **The Injuries page.** No Edit on a proposed card; Confirm and Decline remain the only actions on a proposal (`components/InjuryActions.jsx`). The 13 PENDING constraint proposals and 2 PENDING finding proposals in prod are the operator's to confirm or decline; this session touched none.
- **The engine and the write path.** `_propose_engine_defaults`, `_stage_upsert_entry`, the validators and the appointment brief's one-hop scope are unchanged and were only read.
- **Design 0009's model.** Rows 2 (problem/episode split) and 3 (cap/require behind a dose seam) gained two more pointers at them (GH#614, GH#615) and no work. The next injury session should pick one of GH#617 or GH#612 and build it, not widen the issue set.
- **Medical Protocol and Decision Support.** CBT-I, labs, the interpretation layer, appointments and `clinical_documents.py`'s contract (un-interpreted until GH#608 is ruled) did not move. Q231's imputed-load consumer did not move; three sessions in a row have now gone to the injury and ledger side rather than to it.
- **The operator-owed lanes in NOW** did not move.

### v1-triage (which v1 test each NOW lane serves)

Read from each row's own "Serves" claim; nothing here is a new ruling.
- **Know:** Coach ledger writes (UNSTARTED; a proposal the coach writes is the row the operator meant); Injury lifecycle in-app (DONE); Constraints engine tier (DONE, lane closed); Source-neutral sRPE store and In-app sRPE capture (DONE); Polar relabel (OWED); Garmin self-evaluation read (OWED); Phase posture split (DONE, one read owed); Phase-change form (DONE); Injury clearance (OWED); Garmin account repair (DONE); Typed constraints (DONE, the S6 script now retired).
- **Walk in:** Coach ledger writes (UNSTARTED; an unparented constraint is a row the appointment brief never shows); Appointment brief (v1 built, test 3 met).
- **Loop:** Injury lifecycle in-app (DONE); Wake-day capture (DONE, gate record owed); Missed-PM catch-up (DONE); CBT-I titration direction (DONE); Session fidelity (built, G6 owed).
- **See:** Data freshness and the home load card (DONE); Plan/schedule and recent-sessions tools (DONE); Garmin overnight SpO2 (DONE); RPE fallback Q231 (OWED); Source hierarchy (OWED); HC sync reliability (OWED); Aerobic ingest automated (OWED); HC zones Q159 stage 2 (OWED).
- **Serves no v1 test:** CBT-I Q45 nap attribution, CBT-I manual evaluation trigger, Training v0.1 exercise tags seed (all DONE, riding NOW because DONE rows are never moved out); the cross-repo shared-block lane (OWED) sits in NOW by #112's stated reason.
- **Demotion candidates:** the DONE rows older than a month (August and September) are the clearest; ROADMAP's "Moved from NOW" precedent covers them. Not moved this session.
