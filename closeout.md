# Close-out — 5 Nov 2026: ledger UX follow-ups (`DECISIONS_LOG` #499, #500; GH#622 to GH#629 filed; GH#613, GH#614, GH#616 closed)

## Real commits this session

Session opened at health-app master `4d36ccb` (the merge of PR 621, the previous close-out). Maxima at open: `DECISIONS_LOG` #498, three open `fork` issues (GH#608, GH#613, GH#614). At close: master max #500 (both minted by this session as operator rulings), one open `fork` issue (GH#608), GH#613 and GH#614 closed by this PR, GH#616 closed by comment. The brief was pasted (`Ledger UX Followups - Aubrey 4 Nov Debrief`, with Amendment 1 carrying rulings R1 to R3); no issue carried it.

This session made ONE commit, this close-out's own `gov(ledger-ux-followups)` commit, which lands as a docs-only PR; it names no hash here because a commit cannot name itself. Commits before it on the branch: none (`git log --oneline 4d36ccb..HEAD` was empty before the governance commit). No code, no migration, no prod write, no ledger row confirmed, declined, edited or resolved.

Tracker writes this session (outside the tree, as durable as the tracker):

| Write | Where |
|---|---|
| N1 `build`: confirmed constraints cannot be seen or resolved in-app before their review date | GH#622 |
| N3 `stamp`: proposal and constraint cards show no ledger key or id | GH#623 |
| N4 `stamp`: the edit form's parent injury key is free text | GH#624 |
| N5 `stamp`: an edit that sets a parent moves the card with no notice | GH#625 |
| N8 `watch`: free-text knowledge entries have no lifecycle (15 Jul line in context on 5 Nov) | GH#626 |
| N9 `build`: coach guidance for `parent_key` and resolved events (R3) | GH#627 |
| N6 `verify`: stale frontend after a deploy, V3 reported, fix proposed | GH#628 |
| N7 `watch`: the clearance sweep over-matches by word | GH#629 |
| N2: NOT filed — V2 shows `detail` editable on the injury card's Edit, and the operator used it (#215 is `source api` with the corrected onset wording) | — |
| E1: a coach rewrite erased a precise operator record (#166 / #167 → #178) | GH#608, comment `6643367910` |
| E2: the coach reused a resolved episode's key and wrote a duplicate; the operator recorded a finding and resolved both | GH#614, comment `6643370366` |
| E3: first live use of the depth gap (the knee block edited down to hop, landing, change of direction) | GH#615, comment `6643372526` |
| GH#616 closed as resolved, with a comment pointing at GH#613 and GH#617 | GH#616, comment `6643364728` |
| R1 ruling recorded; GH#613 closed by this PR | `DECISIONS_LOG` #499 |
| R2 ruling recorded; GH#614 closed by this PR | `DECISIONS_LOG` #500 |

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief and its amendment; each step against where it landed:

| Brief step | Landed in |
|---|---|
| V1 to V3 verified before any write | below, this section |
| N1 to N9 filed, four fields each, labels as given (N2 conditional on V2, not filed) | GH#622 to GH#629 |
| E1 to E3 evidence comments | GH#608, GH#614, GH#615 |
| GH#616 closed | by comment, state completed |
| R1, R2 recorded in `DECISIONS_LOG`, numbers resolved at merge | #499, #500 (master max #498 re-read before each resolve) |
| R3: close GH#613 and GH#614 with a pointer to their entries | `Closes` in this PR's body; a one-line comment with the entry number after the merge |
| R3: update 0009's row table if either issue is listed there | not listed (rows 1 to 10 name GH#608 only); unchanged |
| R3: file N9 | GH#627 |
| One ROADMAP row, one `gov(...)` commit | the NOW row "Ledger UX follow-ups"; this commit (which also carries the close-out ritual's `closeout.md`, `CLAUDE.md` pointer and `BRANCHES.md` row) |
| Gates: no code, no migrations, no prod writes; no issue filed bare | held |
| Guard: no ledger row confirmed, declined, edited or resolved | held (reads only: `get_constraints`, `get_injuries`) |

**V1 to V3 results.**
- **V1.** Confirmed (Code, from `pages/Injuries.jsx`): the page reads `/knowledge/injuries`, `/knowledge/proposals` and `/knowledge/review-due` only; a card lists its PROPOSED rows (`ProposalList`); a CONFIRMED constraint surfaces only through `ReviewDue` (`components/InjuryActions.jsx`), fed by `GET /knowledge/review-due`, once it is past `review_by` or `exit.on_date` or its parent injury is resolved; the same component renders on the AM check-in's saved screen under "Needs your call", and Resolve and Keep live on that due row. Prod read 2026-11-05 08:06: #110 (the old ER cap, now duplicated by the confirmed #214) and #102 (the contact-return block, overtaken by the confirmed caution #213) are confirmed with `review_by` 2026-11-16, invisible and unresolvable in-app until then. Filed as GH#622.
- **V2.** `detail` IS editable: `InjuryEditForm` (`pages/Injuries.jsx`, the `detail` textarea) writes it through the same-key rewrite with `source: "api"`. N2 not filed. The knee row #215 now carries the operator's corrected wording ("Tear onset unknown, no recalled event; clean-line tear (per Aubrey)") as `source api`.
- **V3.** No cache headers configured: `npx serve -s dist` (`frontend/railway.toml`), `serve-handler` sends `Last-Modified` and no `Cache-Control`. A service worker exists: `vite-plugin-pwa`, app shell precached (`index.html` and the hashed bundle), `autoUpdate`, `skipWaiting` and `clientsClaim`, no runtime caching; `src/pwa.js` registers immediately, checks hourly and on `visibilitychange`; the plugin reloads the page when an updated worker activates. `version.json` carries the served commit and nothing in the client compares it. The stale case is a window already open and visible across the deploy (no navigation, no visibility change, next check in an hour); a page opened mid-build is the other. Reported with the fix proposed as GH#628.

Departures from the brief: none. N2's omission is the brief's own condition. Design 0009's row table was not touched because R3's condition (either issue listed there) was not met.

Provisional: nothing decided and uncommitted. The prod reads are point-in-time; the ledger moved between the 06:06 read of the previous session and the 08:06 read of this one (the operator worked the debrief through Edit: 13 proposals and 2 finding proposals cleared, four confirmed, two calf rows resolved, the knee block narrowed and confirmed).

## Cold-resume handoff

**Next action (the single clearest).** GH#622 (confirmed constraints visible and resolvable on their card before they are due) is the one defect that still keeps a ledger fact outside the app: #110 and #102 stay confirmed until 2026-11-16 unless it lands first. It is two-way, UI plus one read, and the next Code lane. GH#627 (the coach guidance, within the #43 guard) follows; its two sentences must be landed byte-neutral or by trimming, as #498's was. GH#608 is the only open fork.

**Current sprint (`ROADMAP.md` NOW).** Two rows from this debrief: "Ledger UX follow-ups" (filed, nothing built; GH#622 and GH#627 owned by Code at capacity, three stamps for the next card PR, GH#628 for the operator to read, two watches) and "Coach ledger writes" (lane `Proposal Edit And Receipts` DONE → #497, #498; its forks now ruled → #499, #500; GH#615 watch open). The "Injury lifecycle in-app" lane is DONE; design 0009 at `discussion`, row 1 resolved, nine rows open. The rest of NOW is as the earlier 5 Nov close-out left it (fifteen DONE rows; the open ones with owner: Q231 RPE fallback (Code, once the gate opens; January 2027); Source hierarchy (Luke); Polar sport-id relabel (OWED); HC sync reliability (OWED); Garmin self-evaluation read, Injury clearance, Aerobic ingest automated, Session fidelity G6 (operator); HC zones single-row read (Code, low priority); the cross-repo `#NEXT` extension (OWED)). Operator slots still open: O-A (Athlete_Profile's injury section replaced by a pointer) and O-B (the AM saved screen's proposal block seen live).

**Open `fork` issues.** GH#608 (coach proposals from clinical documents, one-way). Closed this session: GH#613 (→ #499), GH#614 (→ #500), GH#616 (resolved by comment). Open `stamp`: GH#623, GH#624, GH#625, GH#609, GH#593 and the older stamps. Open `build`: GH#622, GH#627 and the older builds. Open `watch`: GH#615, GH#626, GH#629. Open `verify`: GH#628. Open `design` pointers: GH#537 to GH#544, GH#603.

**Design docs not in a terminal state.** 0001 canonical exercise layer, 0002 plan-log reconciliation, 0004 load-model routing and gaps, 0005 HR input layer, 0006 sleep writers and admission, 0007 in-app chat architecture (`ideation`); 0008 SpO2 detector and guardrail, 0009 injury model (`discussion`). 0003 is `committed`. Nothing in `docs/design` moved this session; 0009 row 2 now has #500 pointing at it from the log and GH#614's evidence, and row 3 has GH#615's E3.

### What was NOT touched

This session was governance: reads, eight issues, four comments, two ruling entries. Nothing in the product moved, and a reader should not infer from this file that any of the eight issues is under way.
- **The Injuries page.** Confirmed constraints are still invisible until due (GH#622); the proposal card still shows no key (GH#623), takes the parent as free text (GH#624) and moves without notice (GH#625). The operator's workaround on 5 Nov was text matching and waiting.
- **The coach.** Still sends no `parent_key` and still can write a healed event as an active row; #499 and #500 rule what the right behaviour is, GH#627 names the guidance, nothing is in the prompt yet. The receipt (#498) now shows each turn's writes, so the next debrief's defects will at least be visible in the reply.
- **The frontend's update path.** Hourly and on visibility change only; a window open across a deploy stays stale until the operator refreshes (GH#628).
- **The sweep, the free-text store and the engine.** The clearance sweep reports as before (GH#629); the free-text store still renders unfiltered (GH#626, resolved by GH#528 when it lands); `_propose_engine_defaults` is unchanged by ruling.
- **Design 0009's model**, **Medical Protocol and Decision Support** (CBT-I, labs, interpretation, appointments, `clinical_documents.py`'s contract pending GH#608), and **the operator-owed lanes in NOW** did not move. Q231's imputed-load consumer did not move; five sessions in a row have now gone to the injury and ledger side rather than to it, and the next product lane that is not a follow-up of this debrief is still that one.

### v1-triage (which v1 test each NOW lane serves)

Read from each row's own "Serves" claim; nothing here is a new ruling.
- **Know:** Ledger UX follow-ups (filed; the ledger the operator keeps in the app is the whole ledger); Coach ledger writes (lane DONE; forks ruled); Injury lifecycle in-app (DONE); Constraints engine tier (DONE, lane closed); Source-neutral sRPE store and In-app sRPE capture (DONE); Polar relabel (OWED); Garmin self-evaluation read (OWED); Phase posture split (DONE, one read owed); Phase-change form (DONE); Injury clearance (OWED); Garmin account repair (DONE); Typed constraints (DONE, the S6 script now retired).
- **Loop:** Ledger UX follow-ups (filed; what the operator could not do in-app becomes an in-app act); Injury lifecycle in-app (DONE); Wake-day capture (DONE, gate record owed); Missed-PM catch-up (DONE); CBT-I titration direction (DONE); Session fidelity (built, G6 owed).
- **Walk in:** Coach ledger writes (lane DONE; a re-parented constraint reaches the appointment brief once confirmed); Appointment brief (v1 built, test 3 met).
- **See:** Data freshness and the home load card (DONE); Plan/schedule and recent-sessions tools (DONE); Garmin overnight SpO2 (DONE); RPE fallback Q231 (OWED); Source hierarchy (OWED); HC sync reliability (OWED); Aerobic ingest automated (OWED); HC zones Q159 stage 2 (OWED).
- **Serves no v1 test:** CBT-I Q45 nap attribution, CBT-I manual evaluation trigger, Training v0.1 exercise tags seed (all DONE, riding NOW because DONE rows are never moved out); the cross-repo shared-block lane (OWED) sits in NOW by #112's stated reason.
- **Demotion candidates:** the DONE rows older than a month (August and September) are the clearest; ROADMAP's "Moved from NOW" precedent covers them. Not moved this session.
