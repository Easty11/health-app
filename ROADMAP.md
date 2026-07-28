# ROADMAP

Last updated: 2026-07-27

---

## NOW — active sprint

_Date-anchored work, ordered by external date. The one undated row (cross-repo propagation) is pinned here by #112, which names ROADMAP NOW as the canonical home for cross-repo debt._

| Item | Notes |
|------|-------|
| **CBT-I:** resolve Q45 nap day-attribution (validate the `naps_min` date−1 read) | **DATED — contaminating capture now.** PM nap capture shipped tonight (#122): `naps_min` is written at PM, and the engine reads a night's naps from `date − 1`. That read is correct only if the VA instrument's nap item refers to the day preceding the recorded night — the instrument does not say (Q45), and the CBT-I row itself said to confirm this **before** the engine relied on it, which is now live for block 3. Until Q45 resolves, every nap-excluded night rests on an unverified attribution. Close from the VA CBT-I protocol docs or the administering clinician, not the workbook (searched to exhaustion). See OPEN_QUESTIONS Q45. Owner: Luke. |
| **CBT-I:** manual witnessed evaluation trigger (#118's PM-offer half) | **DATED — ~31 Jul, first titration cycle.** The last piece to *close* a titration cycle in-app: PM close-out offers evaluation once ≥7 days have elapsed since the current prescription's `effective_from`; the engine returns the decision and its basis; the row is minted on acceptance (#118). Block 3 opened 24 Jul, so the first evaluation is due ~31 Jul — a dependency, not a deferral (cannot fire before a full cycle of nights exists). #118's block-open half is already built. **Q49 RESOLVED → #128 (gate lifted):** the replay now reads the effective prescription per cycle from `cbti_prescriptions` (window, lights-out, anchor) and anchors cycles to `effective_from`, so a mid-cycle correction is adjudicated against, not false-held. The trigger, when built, must reuse that same read (the shared "≥7 nights since effective_from" model, #118) — it is no longer gated. Cut a fresh branch from master. Owner: Luke. |
| Lab upload pipeline | PDF/photo → Vision extraction → confirmation screen with outlier flagging → stored. First stage of the medical spine. Consumer hero-feature dependency. File-first UX and marker canonicalisation design are Locked — DECISIONS_LOG #48 / #50; neither implemented. |
| Interpretation layer build | Design Locked, build pending — DECISIONS_LOG #49 (delta-first, three sections, filtered levers). Depends on the lab store (row above) and the lever dictionary — DECISIONS_LOG #51 (GRADE-tiered, decided not implemented). Education pathway (explain mechanisms, list/filter levers), NOT clinical advice — regulatory boundary per DECISIONS_LOG #47. **Packages OPEN_QUESTIONS Q36–Q41** (the six 'Due 4b' forks) — grouped there under the 4b package; this row is their single ROADMAP home. Q35 is a related but separate live question, not in the package. Dated: the early-Aug TRT panel is the first real consumer. Execution order, status tags, and the three-runtime-gate model are detailed in the **Interpretation layer — build sequence** block below. |
| Appointment brief | Hero consumer feature — "Never waste a medical appointment again." Pre-appointment synthesis across modules. Depends on lab pipeline + interpretation layer. Can now query `current_state` directly instead of re-deriving it. |
| **Cross-repo:** propagate the CLAUDE.md shared block to `health-connect-app` | **OWED.** The shared block gained #111's secret-rendering prohibition (health-app `CLAUDE.md`, between the `BEGIN/END SHARED LOOP RULES` markers). It must be copied **byte-identically** into `health-connect-app/CLAUDE.md` — a paraphrase is drift, which is the two-master failure the shared block exists to prevent. **Drift verified, not assumed** (read-only check, 2026-07-23): HCA is cloned at `Projects/health-connect-app` and carries the shared block's `BEGIN/END` markers, but greps **0** for the secret-rendering rule where health-app greps 1. Blocked here on three counts: `chore/secrets-residuals` is not cut in HCA, HCA's working tree is not clean, and a canonical-store edit in a second repo is forbidden from a health-app-rooted session. `.claude/settings.json` does **not** propagate (its deny patterns are health-app-specific paths). Owner: Luke, from an HCA-rooted session. Per #112 this is the canonical home for cross-repo debt. |
| **Cross-repo (shared-block edit owed):** extend the `#NEXT` / number-at-merge rule to cover more than DECISIONS entries | **OWED.** FEEDBACK §20 (2026-07-26) records that hardcoded governance numbers on held branches accrue renumber debt (the 5-branch landing session: one `#NEXT`-compliant branch cost one substitution, two hardcoded branches cost four and seven, one leaking into code docstrings). The documented rule (`CLAUDE.md` → *Number-at-merge*, shared block) names DECISIONS `### #NEXT` **only**; the fix is to extend it to placeholder tokens for FEEDBACK / OPEN_QUESTIONS entries **and `#N`/`§N`/`Q N` refs in code comments/docstrings**. That is a **shared-block** change — byte-identical across both repos (G1) — so it cannot be written from this single-repo session; it must land in `health-app`'s shared block then propagate verbatim to `health-connect-app/CLAUDE.md`. Owner: Luke. Per #112, ROADMAP NOW is the canonical home for cross-repo debt. |

### Interpretation layer — build sequence

_Numbering is organic: it began as a five-increment plan, the producer split into 4a/4b, a declared-state increment was inserted before 4b, and the order was resequenced. Original labels retained; rows are listed in **execution order**, not numeric order. This block is the execution-order detail for the **Interpretation layer build** and **Lab upload pipeline** rows above — those are the sprint-level entries, this is their sequence._

| # | Increment | Status |
|---|-----------|--------|
| 1 | **Interpretation view skeleton.** Static render of the contract example — three sections, group cards, present-marker relations, hybrid weighted-inline levers. No LLM, no producer. | **DONE** — merged, routed behind auth, unlinked |
| 4a | **Producer foundation (phase-free).** `marker_series` newest+prior, delta, gates in mechanical form, group-level surfacing. Range breaches surface un-softened. Proven fixture-as-oracle. No verdict, relations, levers, or endpoint. | **DONE** — merged, library only |
| — | **Declared-state ledger.** Inserted before 4b. Three continuity-aware entry types plus phase derivation, surfaced on `current_state`. The prerequisite for phase-aware interpretation. | **DONE** — merged, seeded live |
| 4b-i | **Producer structural half.** Three-pass restructure (`should_surface` computed after relations), `relations_rendered` with operand degradation, `meta.protocol_context_snapshot` dated to the panel. No demotion, no levers, no verdict, no endpoint. | **DONE** — ff-merged to master (#140–#142); backend suite 453. |
| 4b-ii | **Producer interpretive half.** Relation-based demotion of gate 1's delta arm, `shared_levers` with already-in-play filtering, `axis_verdict`, `mechanism` / `stable_rationale`, `expected_by_phase` (emitted; demotion still to gain authority), the endpoint (draw-triggered per #147), and the view wired fixture→live. Two forks decided here: cache-on-confirm vs compute-on-read, and verdict depth. | **UNSTARTED** — unblocked (ingestion exercised, see below); no external precondition remains |
| 2 | **Rephrase pass.** Register setting, backend rephrase endpoint over the deterministic base text, disposable presentation cache, and two evals as pytest: rephrase-may-not-change-claims, simplify-may-not-become-reassurance. | **UNSTARTED** |
| 3 | **Lever tap → scoped education thread.** Structured seed from the tapped lever, opening a scoped ephemeral thread architecturally distinct from general chat. Follow-ups deflect personalised-action questions. | **UNSTARTED** |
| 5 | **Go-live.** Confirm a real panel through extract→confirm, promote the two `ai_draft` asset groups, swap the view-pointer placeholder, reconcile fixture⇄asset drift. First live run against real data. | **UNSTARTED** |

**4b-ii is now UNBLOCKED — every prerequisite is discharged.**

- ~~**Ingestion.** The lab store is empty — `lab_reports` and `lab_results` both hold zero rows.~~ **Exercised end to end (2026-05-30 draw, ingested 2026-07-28).** The lab path ran on real data: 7 Sullivan Nicolaides reports, 27 results, **26 of 27 bound to canonical markers on first contact** (the 27th, Total PSA, bound by `feat/ingestion-findings`). The store is no longer empty and the view-wiring half now has a real panel to verify against. Struck, not deleted.
- ~~**Phase-vocabulary mismatch** and **lever→declared-factor join.**~~ **Discharged by `feat/relation-preconditions` (Q56/Q57).** The precondition object (`factor_key` + `admissible_phases`) replaced `on_trt` and the producer resolves it; `declared_factor_keys` joins levers to the ledger. `expected_by_phase` now emitted (no authority); relation-based **demotion** remains 4b-ii's own work, not a blocker on it.
- **Trigger resolution settled (#147):** the endpoint resolves the trigger as the newest `collected_date` (a draw), not a single report — the seven-reports-one-date panel falsified the report-shaped spec. Recorded so the endpoint inherits it; no endpoint built yet.

**Runtime gates — not build stages.** "Gate" is overloaded in this project. Inside the interpretation, every marker passes three independent runtime gates:

| Gate | Tests | Notes |
|------|-------|-------|
| **1 — news** | Meaningful change vs prior, or crossed a reference bound | **Two arms.** The delta arm may be demoted by an in-phase relation. The **safety arm** fires on a band change and is **non-demotable**. |
| **2 — range** | Out of range vs the lab's own per-report bounds | Always fires, never suppressed. Phase may annotate a breach as expected; it never hides it. |
| **3 — safety band** | Level vs an authored policy band | Independent of movement *and* of the reference range: an unmoved, in-range value can still sit in a band. Live for haematocrit as of #139 (three bands); `no_asset` for every other marker until authored. |

A group surfaces if any member trips any gate, which routes it to What Moved rather than the collapsed Stable line.

---

## NEXT — queued

_Live, undated — no external date orders these; pick by readiness._

| Item | Notes |
|------|-------|
| CBT-I module phase 2 (engine + surfaces + ISI) | Phase-1 substrate landed on `feat/cbti-module` (held for review, DECISIONS_LOG #107/#108/#109): schema + completed-block import (1 block, 9 prescriptions, 53 nights, SE-reconciled). Phase 2 = titration engine (weekly eval; sufficiency/regularity/adherence gates; TST-plateau exit with SE≥85% as a floor; **replay against the imported block = Gate 5**); AM/PM surfaces with the 12h-clock prefill sanity-gate (Q42); ISI 7-item capture. Separate brief. Confirm the VA nap-timing convention before the engine relies on the `naps_min` date−1 read. **LARGELY LANDED (2026-07-25):** engine (#114/#115), capture surfaces + block 3 opened live (#117/#118/#119), and **ISI capture/storage** (table `cbti_isi` migration `d3f7a1908c62`; block 3 baseline backfilled — corrects the earlier stale "ISI not captured" framing: it was captured 24 Jul, the gap was storage, now closed). Still open: PM prescribed-lights-out display and the manual evaluation trigger (#118's unbuilt half). **Remaining piece — the manual evaluation trigger — is promoted to a dated NOW row (~31 Jul); this row is now programme history.** |
| Scraper canary + honest score degradation | Detect null/stale/implausible scraper output. Surface degraded state to user when HRV unavailable — never silently score without it. |
| Basic readiness score | Formally suppressed until HRV data path is confirmed end-to-end with 7+ days of readings (scraper path confirmed; pending 7-day sample). Once confirmed: Banister fitness-fatigue model (Form = Fitness − Fatigue, dual EWMA) integrated with RMSSD baseline deviation, sleep architecture, and RHR trend. ACWR rejected — see Decisions Log. |
| Manual cardio entry | Unconnected sessions (Rogue Echo bike, gym machines) must be loggable to prevent ACWR silently under-reading load. |
| Deploy companion app to wife's phone | Garmin → Health Connect path. Verify data flowing before deploy. |
| Supersede DECISIONS_LOG #3 | Polar not session-only, AccessLink live, SDK R-R as highest-fidelity HRV path. Blocked on a *How you know* artifact (Polar R-R verification). |
| HCA forwards writer identity (HCA session) | Forward `dataOrigin.packageName` + an HC `health_data_category_priority_table` snapshot in the `/health-connect/sync` payload. Producer half of the #36/#37 wire contract; source dedup arbitration now lives backend-side, so `validateNight()` becomes a faithful relay. |
| Backend F1 filter (backend session) | Apply source-priority dedup over `health_connect_record_sources` (built in #37). Gated on HCA forwarding the field (row above). Also unblocks F3a (frozen-session-set aggregation) once landed. |
| **Security:** identify the second credential digest in the transcripts | **OWED — cheap, and it separates a finding from an unknown.** A second credential-shaped digest (`9688f2…`) appears in 4 session transcripts alongside the now-rotated Railway Postgres credential. Co-occurrence test: if it appears **only** in transcripts that also carry the rotated credential, it is almost certainly that credential's predecessor and is dead twice over. If it appears **independently**, it is a distinct credential nobody is tracking and its liveness is unestablished. A few minutes' work, digests and counts only, never values (#111). Until it runs, "open by choice" and "possibly a live credential" are both true of the same item, which is the thing that shouldn't hold. Recorded here rather than in Q44's body — Q44 is `DONE → #111` and closed questions are not scanned for live work (#112). Fold into the next phase-2 session. Owner: Luke. |
| **Guard:** a canonical-surface consistency test — three comparisons, one mechanism | **OWED.** Two canonical surfaces must agree with their source and **nothing enforces it**; both divergences so far were caught by a human-directed VERIFY inside a brief, which is not a mechanism. The never-lag rule says surfaces must not lag and provides nothing that would notice if they did. **(a) SCHEMA.md vs `models.py`** — four columns from migration `c4e8a2019bd7` (`basis_n_samsung`, `basis_n_diary`, `basis_n_alcohol_unknown`, `basis_tib_over_run_min`) sat in `models.py` and absent from SCHEMA.md until a VERIFY happened to look; an omission when the migration was folded in, and folds recur. **(b) CLAUDE.md conventions vs `DECISIONS_LOG` entries** — *presence* is verified (every `(standing, #N)` citation resolves to a real entry; negative control: a fabricated `#999` returns 0) but *content* is not. A convention can say more than the entry it cites, which reads as authoritative and is not. Live instance: the corrected-doc clause at `CLAUDE.md` L247 is marked `POSTDATES #113` — locally truthful, but that annotation pattern permits **unbounded cumulative drift**, since each note is individually visible while the total distance between a convention and its backing entry is visible nowhere. A content comparison is what would surface it. **(c) Samsung-context filter convention vs its call sites** — the CBT-I read allowlists `context == 'passive_overnight'` (`cbti/replay.py`); the two readiness reads in `checkin_v2.py` (lines ~94 and ~204) instead *denylist* `context != 'session'`, which admits `calibration` readings into the passive snapshot and the HRV baseline — non-resting values contaminating a resting baseline. Modest, real, out of the surfaces brief's scope, and found in passing exactly like the `mcp_server.py` `Session` bug (row above). It is the drift the guard exists to catch: an established convention with no mechanism noticing a call site that departs from it. A content comparison (do all Samsung-context reads share one filter?) is what would surface it. Do **not** tighten the denylist inside a feature branch — it changes readiness behaviour; it lands with the guard, or as its own scoped change. **The detector already exists** and was demonstrated on (a) with a negative control — a fabricated column name must report LAG, proving the check detects absence rather than always passing. That control is the part worth preserving; without it the OKs mean nothing. Separate concern from CBT-I surfaces, so not that branch. Owner: Luke. Recorded here per #112. |
| CPAP mask-off events as an objective nocturia instrument | The waking-cause columns (`wakings_nocturia_n`, migration `b2d5f9e04a17`) rest on self-report — 3am recall of *why* one woke. The CPAP (ResMed AirMini) records mask-off events with timestamps, in-app for 30 days via AirView. A mask-off in the night is an objective correlate of a nocturia trip (the mask comes off to get up). Cross-referencing mask-off timestamps against `wakings_nocturia_n` would give the self-reported count an objective check — and, with PVR 229 mL on record and no urology relationship, help distinguish a behavioural titration stall from a urological one (Q47's neighbour on the "why is the window not opening" question) without relying on recall. No integration exists: the AirMini has no SD card and no OSCAR path; data is in-app only. Filed after block 3's first night showed a single 03:40 nocturia trip against an ISI with severe *maintenance* difficulty and zero *onset* difficulty. Owner: Luke. Recorded per #112. |
| Fix Health Connect permissions | Companion app returning errors for record types 38, 35, 11, 37. Partially resolved via adb pm grant; proper in-app dialog fix still needed. |
| Samsung Health package name correction | Re-run Health Connect diagnostic with `com.sec.android.app.shealth` filter (not `com.samsung.health`). Verify via Railway Postgres query, not on-device UI. |
| Morning check-in screen | Hooper Index pattern (fatigue, sleep quality, stress, soreness). Primary daily touchpoint. Mutable post-submission with audit trail. See Ideas file for DOMS/soreness split design. **Step-5 stale check (2026-07-25):** the core screen IS built — `CheckInAM.jsx` carries the full Hooper set (fatigue, sleep quality, `life_load`=stress, soreness from active injuries) and is routed. Gaps that keep it live: mutation is supported (pre-PM re-entry) but there is **no audit trail**, and there is **no DOMS/soreness split** (soreness is per-active-injury). Stays with both gaps named. |
| Persistent conversation history | Currently clears on browser refresh. Needs backend storage + frontend state management. |
| Session cards not clickable | UI bug — session cards in workout view not responding to click |
| Dual-panel scroll layout issue | UI bug — scroll behaviour broken in dual-panel view |
| `mcp_server.get_hevy_workouts` references unimported `Session` type | Pre-existing bug, found (not introduced) during #42's MCP work — `db: Session = SessionLocal()` with no `Session` import; will raise `NameError` at call time. Out of scope for #42 (Hevy endpoints explicitly not touched); needs a one-line import fix. |
| Sleep duration displays `total_sleep_time_minutes`, which is the in-bed span, not sleep | **SEMANTIC error, not cosmetic — classification corrected 2026-07-24.** Three sites read `total_sleep_time_minutes` and fall back to `actual_sleep_time_minutes`: `context_builder.py:601`, `routers/recovery.py:67`, `HealthPanel.jsx:92`. Originally filed as a `total_ ?? actual_` *presentation inconsistency with no behavioural effect* — that judgement predated knowing what the fields mean. The CBT-I Step-3 probe settled it: across 31 real `passive_overnight` nights, `total_sleep_time_minutes` sits at the clock window `(wake − bedtime)` (remainder median 0) while `actual_sleep_time_minutes` is scored sleep (window − actual median +35). So `total_` is **time in bed**, and these three sites display TIB **labelled as sleep duration** — inflated by ~30–45 min. The correct field for "sleep duration" is `actual_sleep_time_minutes`; `total_` is a TIB/SE-denominator quantity. Fix is a field swap at three sites (mind the `??`/`or` fallback direction). Does **not** clear the bar to interrupt the CBT-I build; still ROADMAP. Corroboration it matters: tonight's 6h00 prescription was derived from `actual_` — the correct scale; `total_` would have prescribed nothing. Owner: Luke. Recorded here per #112. |

---

## LATER — planned

_Unchanged from before this triage._

| Item | Notes |
|------|-------|
| Injury object schema in project files | Schema and extraction method drafted in Ideas. Formalise into Decisions Log and API contracts once morning check-in screen is built. |
| Preset readiness models by sport/goal | Rugby vs endurance vs strength — different metric weighting presets |
| User-adjustable metric weighting | Let users tune what matters to their readiness score |
| AI-personalised model | After ~6 weeks of data per user; Claude infers pattern from history |
| GameTraka connector | Rugby performance data for Luke |
| Apple Health (son) | iOS path; requires either Expo iOS build or separate native integration |

---

## User rollout sequence

1. **Luke (Easty)** — primary dev user; Samsung scraper working; Health Connect partial
2. **Wife** — Samsung Galaxy + Garmin; needs companion app deployed and data flow verified
3. **Son** — iOS; future phase

---

## Dependencies and blockers

| Blocker | Blocks |
|---------|--------|
| Health Connect permissions fix | Polar and Garmin session data |
| Conversation history persistence | AI coaching continuity across sessions |
| Wife companion app deploy | Wife onboarding |
