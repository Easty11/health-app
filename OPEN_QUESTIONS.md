# OPEN QUESTIONS

Undecided forks and unverified-at-machine items. One status per item, from the four states
defined in `CLAUDE.md` → **State vocabulary** (the sole definition). `DONE → #N` names the
resolving `DECISIONS_LOG` entry.

---

## Q1. Backend HC stage-constant fix + historical backfill

`routers/health_connect.py` stage constants are confirmed wrong (DECISIONS_LOG #20):
`SLEEP_STAGE_DEEP=4`, `REM=5`, `LIGHT=2`. Correct to the official enum — `LIGHT=4`,
`DEEP=5`, `REM=6`, `AWAKE=1` — and add handling for stage 6 (currently dropped) so
REM is counted. Then decide whether to **backfill** the corrupted `health_connect_syncs`
rows or let them age out: the HC path looks dormant (latest row 2026-06-21, all written
in a single backfill at 2026-06-21 19:04Z; live sleep stages currently come from the
scraper). Also re-verify the HC `sleep_score` derivation and the `_section_health_connect`
AI-prompt block, which both consume the mislabelled values.

**Status:** DONE → #20. Fix deployed to Railway (PR #2) and all 31 HC rows
re-synced from device on 2026-06-22 (30-day backfill, range 05-22→06-21). Verified
against Railway Postgres: `light_sleep_minutes` now populated (was 0 on every row),
deep/REM no longer swapped, slivers no longer truncated; corrected values track the
scraper. Surfaced a new date-attribution bug — see Q4.

---

## Q2. Companion `validateNight` returns overlapping/duplicate SleepSession records

`validateNight()` for last night returned `sleepRecords: 4` with the per-stage `durMin`
arrays clearly doubled (totals ≈2× the real night: stage-5 deep 69→~34.5, stage-6 rem
134→67). `runDeepConfidence`/`flagDeepSegments` currently `flatMap` all sessions and will
double-count. Must de-duplicate before `trustedDeepMin` is meaningful — e.g. pick the
longest session per night (as `health_connect.py:_aggregate_day` does), or union by time
range. Until then `runDeepConfidence` output is not trustworthy.

**Status:** DONE — fixed in `health-connect-app` `36df9a2` (confirmed patch-present
on HCA master): `collapseSleepSessions()` de-duplicates the overlapping SleepSession
records before downstream consumers, behaviorally verified 9/9.

---

## Q3. HR sampling cadence during sleep unconfirmed (`hrMedianGapSec = 0`)

Gate 3 returned `hrMedianGapSec: 0` over 802 samples, not the expected ~60s (1/min). Caused
by duplicate HR timestamps from the same record-doubling as Q2. The artifact flagging depends
on real HR density during sleep, so this must be re-measured after HR is de-duped. Gate 3 is
INCONCLUSIVE — do **not** calibrate `DELTA_ARTIFACT` / `SPREAD_SPIKE` / `SHORT_MS` or wire
`runDeepConfidence` into readiness/Banister until resolved.

**Status:** UNSTARTED — re-run the Gate 3 HR-cadence measurement. **The stated precondition has CLEARED**:
Q2's `collapseSleepSessions()` de-dup landed on HCA master (`36df9a2`), so HR is de-duped and the
re-measurement is simply not done. No blocker.

---

## Q4. HC dates each night one day earlier than the scraper

After the Q1 backfill, corrected HC stage minutes match the scraper but under a consistent
one-day shift: `health_connect_syncs[date] ≈ samsung_hrv_readings[date+1]` (3 nights match
all three stages exactly, the rest within 1–2 min; 0 same-date matches). `_aggregate_day`
attributes a session by its bed-date while the scraper keys on the wake-date. This
pre-existed the Q1 fix — it was invisible while the HC values were garbage. It matters
because `_section_health_connect` selects "today/yesterday" and the dashboard joins by
date, so HC and scraper rows for the *same physical night* land on different days. Decide a
single canonical sleep-date convention (likely wake-date, to match the scraper) and align
`_aggregate_day`.

**Status:** OWED — resolved in code at DECISIONS_LOG #64
(`fix/hc-sleep-wake-date-attribution`): canonical sleep-date = **local (AEST) wake-date**
(`endTime`), aligning to the scraper; `_aggregate_day` filter + date-collection loop switched
to wake-date-only via a tz-aware `_wake_date`, and existing sleep values cleared by migration
`f4e1a2b3c6d7` for a post-deploy HCA re-sync. G4 (confirm `health_connect_syncs[date]` sleep
stages match `samsung_hrv_readings[date]` **same-date**, not date+1) is pending the
operational re-sync against live Railway data — this session could not reach Railway. Outstanding check: G4 — confirm `health_connect_syncs[date]` sleep stages match
`samsung_hrv_readings[date]` **same-date** against live Railway data after the operational re-sync.
Owner: Luke. Move to `DONE → #64` once G4 passes.

---

## Q5. Backend `/health-connect/sync` dual-field acceptance — collapse after confirming what mobile posts

`routers/health_connect.py` accepts both the raw Health Connect library field names and the
mapped JS names for the same value — `HeartRateRecord.beatsPerMinute`/`bpm` (`.get_bpm()`),
`HRVRecord.heartRateVariabilityMillis`/`rmssd` (`.get_rmssd()`), `StepsRecord.startTime`/`date`
(`.get_start()`) — the "intentionally flexible" tolerance that exists only because the contract
was not single-sourced. With the sleep-stage enum now single-sourced (DECISIONS_LOG #24), the
same can be done here: capture one real on-device sync, confirm exactly which field names
`health-connect-app` actually posts, pick the canonical name, then collapse the dual acceptance
and delete the `.get_*()` reconcilers (this is "Phase 2" of the contract work). Which name to
keep is unverified until an actual payload is captured.

**Status:** UNSTARTED — capture one real on-device sync payload, confirm which field names HCA actually
posts, pick the canonical name, then collapse the dual acceptance. No blocker: the capture is the first
step of the work, not a precondition on someone else.

---

## Q6. Strength volume-load not yet ingested into daily training load

Decision 28 routes strength volume-load → the Mechanical + Neuromuscular windows as a
named, non-optional daily-TL input. The decision is settled, but it is unverified at the
machine: no Postgres query has confirmed Hevy strength volume actually populating the
per-window `load_metrics` rows. Verify a real query shows strength volume landing in the
load path before the four-window engine — or even Tier 0 with a strength term — can be
trusted. Was tracked as "B2" in an out-of-project session's scheme that never entered the
repo; recorded here under the canonical Q-series.

**Status:** OWED — outstanding check: a Railway Postgres query confirming Hevy strength volume actually
populates the per-window `load_metrics` rows. Resolves → #28 on that verify. Owner: Luke.

---

## Q7. Structured injury ledger (`user_knowledge_entries`) is missing the right proximal semimembranosus tear

DECISIONS_LOG #42 migrated Luke's device/method facts and three injuries (left little
finger, right shoulder, left hamstring) into `user_knowledge_entries` — but reused
`seed_engine.py`'s existing `_INJURY_SEED` verbatim rather than authoring new injury data.
`FEEDBACK.md` §5 ("Easty's Current Injury State") documents a **fourth**, distinct injury —
right proximal semimembranosus, full-thickness partial-width rupture, confirmed ultrasound
Aug 2025 — explicitly called out there as DISTINCT from the left hamstring issue. It has
never been in the structured ledger (`seed_engine.py`'s `_INJURY_SEED` predates this
session and also only carried three). `_section_schedule`'s "THIS WEEK FLAGS" injury
render and `mcp_server.get_readiness_snapshot`'s injury query (both now sourced from
`user_knowledge_entries` as of #42) are therefore both missing this injury today. Also
missing: the richer three-valued provocative/clear/untested detail per injury that
`FEEDBACK.md` §5 carries but the current `_INJURY_SEED` schema (`body_part`, `side`,
`restrictions`, `detail`) does not have a field for.

**Status:** UNSTARTED — author the fourth injury (right proximal semimembranosus) into the structured
ledger, and decide the findings-detail schema jointly with Q20. No blocker named in-row.

---

## Q8. Event-spine schema fork

Adopt `health_events` + `user_health_state` as the canonical spine, OR keep the organic
schema (`aerobic_sessions`, `daily_records`, `daily_check_ins`, `samsung_hrv_readings`)
with `user_health_state` as an overlay view on top? Design-stage; not in master. Blocks
the `user_health_state` build and the Decision Support layer.

Resolution: overlay adopted; `user_health_state` is a compute-on-read `current_state`
read model over existing stores, not a `health_events` spine. `health_events` deferred
and narrowed to an additive projection scoped to the medical timeline; call timed to the
lab pipeline.

**Status:** DONE → #43

---

## Q9. Consolidate legacy free-text `user_knowledge` into `user_knowledge_entries`?

Legacy `user_knowledge` (free-text category/content) coexists with structured
`user_knowledge_entries` per #44. Fold the legacy KB in as a `type="note"` entry and
retire `routers/knowledge.py`'s legacy write path + `context_builder`'s parallel
`knowledge_entries` param — making `context_builder` a true single-source formatter over
`current_state` — or keep them permanently distinct (free-text notes vs typed declared
state)? Deferred by #44; not urgent.

**Status:** UNSTARTED — undecided design fork (fold the legacy KB in as `type="note"` vs keep the two
permanently distinct). Deferred by #44, not urgent. No blocker.

---

## Q10. Build AccessLink per-second ingest for the Metabolic-load window (HC/companion lane)?

#35 established the dependency: HC carries no per-second R-R/HR-zone; only AccessLink
(v3 REST exercise-samples / TCX export) does. #46 specified the exact pathway but it is
not built. PSL covers Luke's direct solo/gym capture, so the need only bites if the
HC/companion lane carries a Polar user requiring per-second — currently none (Deb's
wearable integration deferred, Cooper has no wearable).

**Status:** UNSTARTED — low priority, deliberately deferred. **Not BLOCKED**: #46 already specified the
pathway, so nothing prevents building it; there is simply no consumer yet (Deb's wearable integration
deferred, Cooper has no wearable). Revisit when the Metabolic-load channel is wired to Polar-in-HC data
for a real consumer.

---

## Q11. Lab store — where per-marker observed results live

Fork: `lab_result` typed table vs `user_knowledge_entries type="lab"` vs `health_events`.
Blocked the #49 build, the #48 write path, and lever-dictionary wiring alike.

**Status:** DONE → #52 (`lab_report` + `lab_result` table pair).

---

## Q12. Per-marker minimum meaningful delta

Where the #49 delta-gate threshold lives; global vs per-marker.

**Status:** DONE → #53 (per-marker `min_meaningful_delta`, in-repo #51-family reference asset).

---

## Q13. HRV is scraper-only — Health Connect `hrv_rmssd` structurally empty; single point of failure pending scraper canary (#9)

Both HRV surfaces in the app — the Recovery card and the v2 AM check-in passive tile — read
`samsung_hrv_readings.hrv_ms` (the Samsung Health accessibility-scrape). The parallel Health
Connect column `health_connect_syncs.hrv_rmssd` comes back **always NULL**. The ingest does
attempt to fill it: `_aggregate_day` averages `payload.hrv` via `get_rmssd()` (which accepts
both `rmssd` and `heartRateVariabilityMillis`), so an empty node means the inbound payload
carries **no HRV records at all**. Root cause is the confirmed, closed platform finding —
*Samsung does not write Ring HRV (nor RHR, sleep stages, respiratory rate) to Health Connect*
(DECISIONS_LOG "things tried and abandoned"). HRV therefore has exactly one delivery path (the
scraper); there is no HC fallback and no HC-side ingest change can recover it. That makes the
scraper a **single point of failure for HRV**, fragile to any Samsung Health UI change — the
motivation for the scraper canary (issue #9) and a per-Samsung-screen metric catalogue
(`health-connect-app` work; distinct from the frontend-page catalogue in `METRICS.md`).

Not-yet-verified-at-machine: "empty because HRV is absent from the payload" is **inferred**
from the closed finding + ingest logic, not re-confirmed against a live captured sync. The
competing (less likely) explanation is that HCA posts HRV under a field name neither
`get_rmssd()` branch maps — the open **Q5** territory. One captured real payload's `hrv[]`
(or a Railway sync/`health_connect_record_sources` check) disambiguates absent-vs-unmapped.

**Status:** OWED — root cause is a closed platform finding; what remains is confirmatory. Outstanding
check: capture one real HC sync payload and confirm `payload.hrv` is empty (absent, not unmapped per Q5).
Owner: Luke. If absent-confirmed, the residual is the HRV single-point-of-failure risk, tracked to issue #9
(`health-connect-app` scraper canary). Cross-refs Q5, issue #9.

---

## Q14. Hevy create-loop id contract

Does `POST /v1/exercise_templates` return the canonical string id (UUID/hex) or a bare
integer (the spec example shows an int)? This decides the create loop's shape:
create→single-row-upsert (if the create response carries the canonical id) vs
create→list-back (if it does not). Resolve empirically: one throwaway live create + a
list-match against `get_exercise_templates`. **How-you-know** artifact required before
any build.

**Status:** DONE → #65 — the live OpenAPI spec types the `POST
/v1/exercise_templates` response as `{"id": <integer>}`, distinct from the canonical
string UUID `GET` returns; the create loop adopts create→list-back (create → sync →
resolve within the custom subset), so the POST-response representation never gates the
build. The deferred micro-opt (skip the re-pull if the POST is later confirmed to carry
the canonical UUID) is out of scope.

---

## Q15. `3497ab483935` prod-drift reconciliation

Autogenerate surfaced (and Code stripped) three divergences between local and prod at
revision `3497ab483935`: an `exercise_sessions` drop, `samsung_hrv_readings.context`, and
`api_key_encrypted` `VARCHAR`→`TEXT`. Confirm each is an intended local/prod difference or
a real un-migrated delta. Resolve against Railway Postgres, not local.

**Status:** OWED — outstanding check: confirm each of the three divergences against **Railway Postgres**
(not local) as either an intended local/prod difference or a real un-migrated delta. Owner: Luke.

---

## Q16. `hevy.py` `get_exercise_history` path

The connector calls `/exercise_templates/{id}/history`; community docs show
`/exercise_history/{id}`. Verify against the live API and fix the connector path if it is
wrong.

**Status:** DONE → #69. Path corrected to `/v1/exercise_history/{id}` (template id unchanged)
on `fix/hevy-exercise-history-path`; basis is official docs + 3 independent current clients.
Live corroboration remains optional belt-and-braces (local Hevy MCP hung this session).

---

## Q17. HRV step-change from 6 Jul — (A) instrumentation vs (B) physiology

`get_recovery_metrics(days=30)` surfaced a step (not ramp) in scraper HRV: pre-6-Jul (13 Jun–4 Jul,
22 nights) mean ≈57 ms, range 24–88, high variance; post-6-Jul (7 nights) mean ≈96 ms, range 83–117,
variance collapsed. No row exists for 5 Jul — the discontinuity sits in that gap. The 57 ms pre-period
mean matches the established operative baseline exactly, so old data was valid and the break is new.
Two hypotheses, possibly both true: **(A) instrumentation** — the phantom-node fix changed which node
the scraper binds, now reading a different metric (RMSSD→SDNN ≈ the observed 1.7× ratio); **(B)
physiology** — tirzepatide ceased 2+ weeks ago (~3 half-lives), GLP-1/GIP washout produces a genuine
HRV rebound, ~~corroborated by respiratory rate drifting ~14.0→~13.5 br/min over the same window via a
*different sensor path* (a scraper bug cannot move RR). The 68% rise exceeds published GLP-1 HRV
effects alone.~~ **[struck — resolved → #89 on (A): RR is NOT a different sensor path. It is
`vitality_respiratory_rate_average_title`, read from the same Vitality screen through the same
phantom-affected selector, fixed in the same HCA commit as HRV (`1db8833`/#19). The RR drift is a
*prediction* of (A); the "68% rise" is an artifact of stale reads, not a real rebound.]**

**Decision gate = Task 1 node dump** (branch `feat/hrv-node-dump` in **`health-connect-app`**, a
separate repo — not reachable from a health-app-rooted session). Dump the `HRVAccessibilityService`
node tree; identify the bound node's field/metric identity and whether a sibling node carries the
pre-6-Jul metric. Different node/metric → (A): correct the binding, then reconcile. Same node/metric →
(B): rebound is real. **Historical row reconciliation must NOT run until this gate resolves** —
reconciling against a moving metric definition bakes the error in permanently. Confirmatory input held
ready: `feat/recovery-metrics-rhr` (Task 2, RHR series in `get_recovery_metrics`) — but note the primary
`samsung_hrv_readings` RHR is the scraper's `sleep_hr_bpm`, same device family as HRV; the truly
independent discriminator is Health Connect `resting_heart_rate` (query `health_connect_syncs` directly).

**Resolution (→ #89 · 2026-07-19).** Closed on **(A) instrumentation**, verified against
`health-connect-app` master (`1db8833`/#19):
1. **(A) confirmed — mechanism is stale-phantom *selection*, not a metric change.** #19 routes all
   three Energy-score reads through `findByIdValidBounds` instead of `findById(...).firstOrNull()`; the
   phantom is a Compose view-recycling duplicate bearing the *prior* render's value with negative width,
   which `.firstOrNull()` returned. Same node, same metric (RMSSD) throughout — the scraper simply
   stopped binding the stale duplicate. (Authored 26 Jun on unmerged `fix/scraper-sh-relayout`; reached
   HCA master 11 Jul, renumbered #16→#19 — the gate's binary "different node→A / same node→B" missed
   this third case: same node, but the old reads were the phantom.)
2. **RMSSD→SDNN withdrawn as surplus.** The 1.7× ratio is coincidence. A stale prior-render value
   predicts the statistics directly — pre (mean 57, range 24–88, high variance) = scattered stale reads;
   post (mean 96, range 83–117, variance collapsed) = locked to on-screen truth — with no analyte change
   required.
3. **(B)'s corroborator is void — never independent.** RR shares the exact read path (see the struck
   clause above), so the 14.0→13.5 drift is a *prediction* of (A), not evidence against it.

(B) as *physiology* is **unevidenced, not disproven** — washout may still have moved HRV, but this
series cannot speak to it. The pre-install baseline ≈57 ms is not a baseline; trustworthy HRV history is
short, not long. **Historical rows are NOT reconciled here — see Q29** (install-history segmentation is
the prerequisite; the changepoint is an APK-install event, not a commit).

**Status:** DONE → #89 (instrumentation limb; (A) confirmed vs HCA master). Cross-refs Q13, Q18,
Q29, issue #9, `BRANCHES.md` `feat/recovery-metrics-rhr`, HCA #19 / Q3.

---

## Q18. `samsung_hrv_readings` historical out-of-range sweep

DECISIONS_LOG #70 added an ingest bounds guard that nulls-and-logs out-of-range biometrics going
forward (trigger: `2026-06-28 Eff=119%`), but **existing rows are unswept** — the sweep could not run
this session because the local `DATABASE_URL` is dev SQLite with zero production rows. Run the
full-schema `NOT BETWEEN` sweep (mirrors `_BOUNDS` in `routers/samsung_hrv.py`) against **Railway
Postgres**; for any historical violator, null/clamp the offending field (the guard only protects new
writes). If efficiency was unbounded, assume other fields were too — the sweep covers the whole
numeric schema, not just efficiency.

**Status:** OWED — outstanding check: run the full-schema `NOT BETWEEN` sweep against Railway Postgres and
null/clamp any historical violator. Owner: Luke. Independent of Q17. Same loop as `BRANCHES.md`
`fix/hrv-sleep-integrity` Task 3.

---

## Q19. Desktop workout-detail exercise scroller starved to ~36px — right-column space allocation

Desktop full-width, a workout opened in `WorkoutDetail` (`frontend/src/components/WorkoutPanel.jsx`
lines 190–244): reported symptom, verbatim — "no scroll ability for the full column, only the
exercise section, which is small." Live DevTools measurement on the authenticated app (Chromium,
~779 px-tall viewport) confirms the exercise list at `WorkoutPanel.jsx:224`
(`flex-1 overflow-y-auto px-4 py-4 space-y-5`) computes `clientHeight 36` / `scrollHeight 1977`,
`overflow-y: auto` — scrollable, but squeezed to a 36 px window. **Nothing is stranded/unreachable**;
the fixed chrome above simply consumes the panel. Cause is **space allocation, not a
min-height/overflow CSS defect**: the right column (727 px) splits 50/50 between HealthPanel and
WorkoutPanel (both `flex-1 min-h-0`, `Dashboard.jsx:99/102`), so WorkoutPanel gets ~363 px; the two
`flex-none` blocks above the list — header (`:192`) and the stats-grid + session-analysis + "Get AI
Feedback" button block (`:197–223`) — consume ~327 px, leaving the `flex-1` exercise list ~36 px.

Falsified prior hypothesis: the `md:min-h-0`-on-four-scrollers fix (drafted as "#70", **withdrawn** —
the real #70/#71 are the HRV work) was disproven by measurement; all four targets are self
scroll-containers whose flexbox automatic-minimum is already 0, so `min-h-0` is inert (pre-fix sim
scrolled identically, 274 vs 3144). The Dashboard column chain is measurement-confirmed bounded
(LEFT/Chat scroller 573→112029 and HealthPanel 363→511 both scroll correctly); the LEFT-column prime
suspect was exonerated (clientH == scrollH == 727).

Fork (undecided): (a) let the whole detail view scroll as one unit — move the scroll boundary to the
panel root so the stats/analysis chrome scrolls with the exercise list rather than being pinned;
(b) rebalance the right-column 50/50 split so the expanded/active panel gets priority, or size to
content; (c) cap the chrome height so the list keeps a usable minimum. Frontend-only; no connector,
contract, or schema impact.

Not-yet-characterised: measured only at ~779 px viewport height — taller viewports give WorkoutPanel
more room and may not exhibit it. A faithful isolated repro (real compiled CSS, verbatim classes) did
**not** reproduce it; the trigger is specifically the detail-view chrome height vs the ~363 px
half-column, which the repro did not stage.

**Status:** UNSTARTED — frontend layout fork: decide direction (a) / (b) / (c), then implement. Branch
`fix/desktop-column-scroll` was cut then discarded (zero commits; deleted). No DECISIONS_LOG entry.
No blocker — the decision is Luke's to make at will, nothing external gates it.

---

## Q20. Clinical findings vs restrictions — `user_knowledge_entries.value` conflates them

Restrictions are structured (`restrictions[]`, enforced by `selection.py`); **findings are not**.
Positive right slump, S1-pattern referral, frontal-plane deficit have no first-class home in the injury
`value` JSON — they ride as `signal_type` + free-text `detail`. The constraint-consumption brief added a
`trajectory` key to `value` but deliberately did **not** model findings. Note the split surfaces
elsewhere too: FEEDBACK §5 documents these findings clinically, but the structured ledger the engine and
snapshot read does not carry them. Q7 territory.

**Status:** UNSTARTED — resolve jointly with Q7 (injury-ledger completeness), not piecemeal. This is a
sequencing coupling, **not** a blocker: Q7 is itself UNSTARTED and startable, so nothing prevents doing
both together.

---

## Q21. Does the lab-side expectation contract (#63 / SPEC_64) generalise to injury trajectories?

**Status:** DONE (this session; no DECISIONS entry — logged conclusion only) — they **rhyme, they do not share code.** Both follow declare
expectation → surface divergence → never suppress (lab gate-2 "annotate, don't hide" ≡ injury "surface,
don't gate"). But the lab contract is bound to marker/delta semantics (`marker_groups.json`,
`min_meaningful_delta`, two-gate axis-verdicts) while injury trajectory is a soreness series vs a
declared shape (`injury_trajectory.py`). Kept as separate mechanisms deliberately — forcing a shared
abstraction over two things that merely share a shape is how you get a bad one. Logged per the
constraint-consumption brief; no further action unless a third expectation-gated surface appears and the
rhyme becomes a rule worth abstracting.

---

## Q22. Promote exercise-region tags to a source-agnostic canonical exercise layer

Tags are currently keyed on the **Hevy** template id (`exercise_region_tags.hevy_exercise_template_id`),
in tension with the device-agnostic-from-day-one principle. The labs module already solved the analogous
problem (`marker_canonical`). Deferred deliberately for the tagging brief — 493 rows are cheap to re-key,
and movement-identity-across-sources is a real design exercise that should not be rushed inside a tagging
task.

**Status:** UNSTARTED — deliberately deferred, not abandoned (#74). **Not BLOCKED**: 493 rows are cheap to
re-key, so nothing prevents it. Revisit when a second exercise source appears or the canonical-exercise
layer is designed.

---

## Q23. Do `_RADICULAR_BLOCKS` / `_RA_FLARE_BLOCKS` need revision now that region attribution is accurate?

Correctly tagging Pallof as `anti_rotation`-only (and Shoulder Rotation as NOT `rotation`) is what makes
the radicular rotation-block behave correctly for this user. Other blocks in `selection.py` may have been
tuned against wrong keyword inputs and never noticed — the block sets and the (now-fixed) loaded-region
inference were never independently validated.

**Status:** UNSTARTED — **the stated precondition has CLEARED**: active-window tags were human-confirmed
and seeded in prod on 2026-07-14 (`seed_exercise_region_tags.py 1 --confirm` → 37 tag rows, 56/56 titles
resolved; see `BRANCHES.md` `fix/exercise-tag-coverage`). The audit of `_RADICULAR_BLOCKS` /
`_RA_FLARE_BLOCKS` has simply not been run. No blocker.

---

## Q24. Does anything besides reconciliation consume `laterality`? Is there a `capability_state.side` join that should exist?

`capability_state` already carries a `side` column (left / right / bilateral). `hevy_exercise_templates.laterality`
now records whether a movement is unilateral. A unilateral logged exercise plausibly should feed a per-side
`capability_state` row, but no such join exists today. `laterality` is currently written and consumed only
by (future) plan↔log reconciliation.

**Status:** BLOCKED — blocker: the plan↔log reconciliation is not built, and it is `laterality`'s ONLY
consumer, so whether a `capability_state.side` join *should* exist cannot be settled until that consumer
exists. Owner: Luke. Unblocks on: reconciliation being designed/built.

---

## Q25. (cross-repo, health-connect-app) Disposition of remote branch `claude/hevy-api-workout-query-teulc2`

Remote branch `claude/hevy-api-workout-query-teulc2` (`4dfccbe`) is on `origin` for **health-connect-app**,
unmerged, and is NOT in that repo's `BRANCHES.md` — whose own header states "every branch not master lives
here until merged+deleted." The store is violating its own rule. Needs a disposition: govern it (add to
BRANCHES.md) or kill it. Not this repo's / this brief's job — logged only.

**Status:** DONE → #91 — the branch now carries a dedicated row in `health-connect-app`'s `BRANCHES.md`
(added at HCA `f15b545`, "row the unrowed branch"). This question asked whether the branch was **governed or
killed**; governing it discharges the question.

**Both limbs now closed (verified 2026-07-20, #93).** The disposition this entry left OWED in HCA's store has
since completed: the operator deleted the remote ref, HCA's row reads `DONE → discarded 2026-07-20`, and
`git ls-remote --heads origin claude/hevy-api-workout-query-teulc2` returns empty — verified from an
HCA read during the #93 session. Both the omission this question recorded and its subject are gone.
The row remains HCA's to hold; tracking it here too would be the duplication defect Q31 records.

---

## Q26. Taxonomy has no home for isolation / adductor-abductor work — G2 "zero fallback" vs benign empties

`Capability_Taxonomy_v0` is a movement-PATTERN + capacity vocabulary. A large share of the user's logged
work has no clean region: **Hip Adduction / Hip Abduction (Machine)** (frontal-hip strength — pes-anserine-
relevant, the injury the tagging brief itself cares about), knee isolations (leg extension / leg curl), and
arm/shoulder isolations (curls, raises, delt flies, triceps). These are left UNTAGGED in the v0 proposal —
the keyword fallback returns `[]` for all of them (benign: no wrong region, just a logged coverage-gap hit).
This puts G2 ("100% of active-window templates tagged, fallback hit-count 0") in tension with reality:
forcing a tag would pollute the region signal.

Three resolutions for Luke: (a) accept benign empties and redefine the coverage metric as "zero *wrong*
tags" rather than "zero fallback"; (b) add an accessory/no-pattern sentinel so isolations are "tagged" (bypass
the keyword path) but contribute no region — needs a mechanism, since region_key validates fail-closed
against the taxonomy; (c) extend the taxonomy (e.g. a frontal-hip adductor/abductor strength region) — a
`TAXONOMY_VERSION` bump. The adductor gap is the load-bearing one given the active pes anserine injury.

**Status:** DONE → **DECISIONS_LOG #76**, option **(b)** with a correction. Not two states but THREE —
`tagged` / `adjudicated no-pattern` / `untagged` — via a `hevy_exercise_templates.adjudicated_at` timestamp,
NOT a sentinel region_key (which would weaken fail-closed validation). G2 stands UNSOFTENED (option (a) was
rejected: redefining coverage as "zero wrong tags" forfeits the ability to detect a real gap later). Option
(c) — the taxonomy bump — is deliberately NOT done inside a tag confirmation (the log must not shape the
screen); it is spun out to Q27 as a grounded v1 design pass. Interim: calf / shoulder ER-IR / Copenhagen /
hip add-abd are adjudicated no-pattern.

---

## Q27. Capability_Taxonomy v0 has no axis-type for joint-level STRENGTH RATIOS — grounded v1 family

Four independent instances in one user's last-90d log point at one structural hole: v0 is a movement-PATTERN
and screening vocabulary with no axis-type for **joint-level strength / strength-ratio** reads.

| Movement | v0 offers | Why it fails |
|----------|-----------|--------------|
| Copenhagen Plank | nothing | Adductor strength; `frontal_single_leg_stability` is closed-chain balance, `anti_lateral_flexion` is trunk — a side-lying adduction load demonstrates neither |
| Shoulder ER / IR | `shoulder_mobility` | Cable ER at load is STRENGTH; shoulder_mobility is a mobility screen — wrong capacity |
| Hip Add / Abd (machine) | nothing | Open-chain frontal-hip strength; not `frontal_single_leg_stability` (closed-chain stability) |
| Calf raise | `ankle_df` — REJECT | Plantarflexion STRENGTH ≠ dorsiflexion MOBILITY (category error, #76) |

This is a family, externally grounded, carrying some of the best-evidenced return-to-sport metrics there are:
**adductor:abductor** and the adductor squeeze (groin injury in field sport, HAGOS), **shoulder ER:IR** ratio
(overhead athlete / rotator cuff, isokinetic literature), **plantarflexion** strength. Four hits from one log
is what makes it structural, not anecdotal.

**Live impact:** the user's ER:IR ≈ 6.25 : 11.25 = **0.56** against a ~0.66–0.75 reference — a quantified,
flagged deficit he is actively fortifying, and the platform currently has no axis to represent it.
`capability_state` is already per-region-per-side, so ratio reads are natively supported once the vocabulary
exists — the schema is ready, the vocabulary is not.

**Status:** UNSTARTED — the v1 taxonomy bump is its own design pass: externally grounded (HAGOS / adductor
squeeze; ER:IR isokinetic references; return-to-sport LSI), with adductor:abductor and ER:IR as first-class
reads. NOT a bolt-on from a tag file (the taxonomy is external-authority so its breadth does not inherit the
user's blind spots — #76). No blocker — the external references are named and nothing gates starting it.
Unblocks the interim no-pattern verdicts on the four families above.

---

## Q28. `Pullover` is not a constraint-neutral probe subject — the resolver probe passes by luck

`backend/probe_resolver.py` `_RESOLVER_PROBE` labels its subjects "out-of-history AND constraint-neutral",
which is what stops an injury refusal from silently suppressing the resolver measurement (the whole reason
B3 swapped the subjects off BSS / single-leg RDL). `Calf Raise` and `Preacher Curl` hold. **`Pullover` does
not.**

**How you know:** the live container run (2026-07-15, 494-row catalogue, real model) opened with the model
flagging it unprompted — *"Pullovers involve shoulder movement… You've got an active shoulder injury with a
flag on horizontal adduction and overhead work. Pullovers can load the shoulder in a similar pattern."* It
proceeded after confirmation, so the probe still reached its subject and reported `[OK]`. That is the
problem: **the probe currently passes for a reason it does not state**, and it will stop passing if the
shoulder flag tightens or the model gets more conservative — a false-green waiting on someone else's
check-in (FEEDBACK §11).

**The fix is one line, but the candidate set is narrower than it looks.** A replacement must satisfy BOTH
constraints simultaneously, and the two suggested in passing each fail one:
- **Reverse Fly** — fails *out-of-history*. `Rear Delt Reverse Fly (Cable)` / `(Dumbbell)` / `Single Arm
  Rear Delt Cable Fly` are all in the user's 28-day window (they appear in the 2026-07-15 ID-keyed audit's
  ADJUDICATED NO-PATTERN list), so the model has ids for them and would never emit a title — the probe would
  measure nothing and, post-`5c5b43f`, correctly fail loudly. [Certain — from the audit output]
- **Cable Crossover** — likely fails *constraint-neutral*: horizontal adduction is the exact pattern the
  shoulder flag names. [Reasoning, not measured]

**Simplest resolution — probably no replacement at all:** drop `Pullover` and keep `Calf Raise` +
`Preacher Curl`. Both are prod-confirmed to force a guessed title and return genuine candidates, and two
subjects already exercise the ratio tier (`Preacher Curl` → `Rope Cable Curl` 0.643 / `Drag Curl` 0.636).
The third subject adds coverage, not capability.

**Status:** UNSTARTED — the resolution is already identified (drop `Pullover`, keep `Calf Raise` +
`Preacher Curl`); deferred to the next harness-open, not a branch. Test-instrument only; no production code
path is involved. No blocker. Ref: live probe run 2026-07-15; DECISIONS_LOG #83/#84; FEEDBACK §11.

---

## Q29. Historical HRV phantom-stale row reconciliation (`samsung_hrv_readings`)

Spawned by Q17's resolution on **(A)** (→ #89). Pre-fix `samsung_hrv_readings` HRV rows are
phantom-stale — each carries a *prior render's* value, not the night's, because the scraper's
`findById(...).firstOrNull()` bound a Compose recycling duplicate (HCA #19). The pre-install baseline
≈57 ms is an artifact, so any downstream trend / readiness / protocol attribution built on the 57→96
"rebound" rests on bad rows.

**Why no reconciliation runs yet — the changepoint is an APK-install event, not a commit.** The fix was
authored 26 Jun (unmerged `fix/scraper-sh-relayout`) and reached HCA master 11 Jul; the data step is
~6 Jul; HCA Q3 (RESOLVED) records a stale APK (`a5d1643`) still emitting the phantom `106` on 11 Jul. So
no single commit or merge date partitions the series — phantom-era and valid-era rows interleave by
*which build was installed when*. **Prerequisite: segment the series by APK-install history first.**
Reconciling against an unsegmented series bakes the error in permanently.

Distinct from **Q18** (out-of-range bounds sweep — those rows are wrong-*magnitude*; these are
stale-but-plausible) and from **Q17** (now resolved). The RHR discriminator is likewise contaminated:
`last_shr`/`sleep_hr_bpm` was phantom-affected too (fixed in the same HCA commit — see `BRANCHES.md`
`feat/recovery-metrics-rhr`), so Health Connect `resting_heart_rate` (`health_connect_syncs`) is the
only clean independent path.

**Status:** BLOCKED — blocker: the series must be segmented by APK-install history first (the changepoint
is an install event, not a commit). Owner: Luke. **Do NOT reconcile, backfill, or delete a
single `samsung_hrv_readings` row until segmented.** Cross-refs Q17, Q18, issue #9, HCA #19 / Q3.

---

## Q30. Neither repo has a `.gitattributes` — `core.autocrlf` decides bytes per-machine

`health-app` and `health-connect-app` both lack `.gitattributes`, so with `core.autocrlf=true` the
line endings of a working-tree checkout are decided per-machine rather than by the repo. Measured
during the #91 sweep: the CLAUDE.md shared block is `i/lf w/lf` in health-app but `i/lf w/crlf` in
health-connect-app — identical in the index (the thing that propagates), 151 CR bytes apart in the
working tree.

**Why it matters beyond cosmetics:** any cross-repo verification that reads the *working tree* will
keep producing false divergence, and the G1 byte-identity guarantee becomes machine-dependent unless
every check is made through git. A raw `md5sum` of the two working trees says "diverged" while the
committed content is identical — the exact false verdict #91's gate had to be redefined to avoid.

**Action (named, not taken today):** add `* text=auto eol=lf` as `.gitattributes` in both repos.
Deliberately NOT done in the #91 brief: it changes working-tree checkouts on the next checkout in
both repos — a behavioural change beyond a governance brief's bounds.

**Status:** UNSTARTED — blocker-free, action named above. Owner: Luke.

---

## Q31. `DECISIONS_LOG.md`'s trailing Known-issues table is a fourth vocabulary — and may duplicate `OPEN_QUESTIONS`

`DECISIONS_LOG.md` carries a trailing "Known open issues" table whose Status column uses
`Open` / `Fixed` / `Tech-debt` — a fourth vocabulary, outside #88's stated scope
(`BRANCHES.md` / `OPEN_QUESTIONS.md` / `ROADMAP.md` / close-outs) and therefore untouched by both the
#90 and #91 sweeps. Whether it should adopt the four states, or is legitimately a different artifact
class (as `OPEN_QUESTIONS` was argued to be, then overturned by #91), is undecided.

**Second, independent defect — recorded, not investigated:** those rows resemble `OPEN_QUESTIONS`
content in kind. If the same issue is tracked in both files, that is a duplication defect independent
of vocabulary — two stores that can disagree about the same fact. Verify whether the sets overlap
before deciding either question; a vocabulary sweep over a duplicated store would entrench the
duplication rather than expose it.

**Status:** UNSTARTED — no blocker. Owner: Luke.

---

## Q32. The `/closeout` ritual definitions have diverged between repos — 77 vs 132 lines

`health-app/.claude/commands/closeout.md` is **77 lines**; `health-connect-app`'s is **132**. Both
define the same ritual, and both were carrying the struck `purpose / why-parked / unblocks-on`
column set (HCA Q9 item 2). health-app's copy is fixed at #92; **HCA's still teaches the dead
dialect**, and a ritual definition that does so re-emits it every session — the drift regenerates
itself rather than merely persisting.

Two undecided questions, deliberately left open rather than answered unilaterally (sweeping another
repo's ritual definition is out of this brief's scope, and doing it unbidden is not Code's call):

1. **Does HCA's copy need the same strike?** Almost certainly yes — HCA Q9 records it as the higher
   priority of its two items.
2. **Is the 77-vs-132 divergence intentional?** The shared loop-rules block is propagated verbatim
   and fingerprint-gated; the ritual definition is neither. If the ritual is meant to be shared, it
   needs the same treatment (markers + a parity gate). If it is meant to be per-repo — HCA's is a
   different app with different close-out needs — that should be *stated*, so the divergence stops
   reading as drift. Right now nothing distinguishes "intentionally different" from "quietly
   drifted", which is the same ambiguity the vocabulary sweeps existed to remove.

**Status:** UNSTARTED — no blocker; both questions are answerable at will. Owner: Luke.

---

## Q33. The shared loop-rules block still says `parked` — the definition outlasted every sweep

`CLAUDE.md:128` (health-app) and `CLAUDE.md:116` (health-connect-app) carry the same sentence:

> `branch with `+` commits vs `origin/master` must be pushed, parked in `BRANCHES.md`,`

This is a **generator instruction**, not narration — it tells the next session what to call a branch,
so it re-emits the struck vocabulary every time it is read. It survives the frame-vs-narration filter
that correctly exempts `retired` (prose) and the OAuth `parks the request` (different word-sense).

Knowingly deferred at #93, not missed. Two reasons, both structural:

1. It sits inside the **verbatim-propagated shared block**, fingerprint-gated at
   `4243c91ce78e0331ddfa5178aa3006b8` / 155 lines / 10232 B. Editing it from a health-app-rooted
   session re-breaches G1 — the exact obligation #92 discharged.
2. Under the paired-obligation protocol (#92), a shared-block edit creates a **pair**: the editing
   session records it OWED, the return session discharges it. It therefore needs its own brief and a
   mirror-first plan, not a drive-by fix at the end of an unrelated sweep.

The two repos are **identical** on this line, so nothing has diverged — the deferral is safe, not
merely tolerable. What is *not* safe is leaving it untracked: after #93 both rituals say `rowed`
while the document that defines the vocabulary says `parked`.

**Status:** UNSTARTED — no blocker; needs a shared-block brief with a mirror-first plan and a G1
re-fingerprint on both sides. Owner: Luke.

---

## Q34. Is `safety_threshold` a third class of read-constant, alongside delta and stable_rationale?

`lever_dictionary.marker_interpretation[*]` currently carries two kinds of authored constant:
`min_meaningful_delta` (is this change news?) and `stable_rationale` (is this persistent flag benign?).
Both answer *interpretive* questions — they shape how a reading is narrated.

Neither answers a **safety** question: is this value dangerous *now*, regardless of whether it moved or
whether it is constitutionally normal for this person? Haematocrit on TRT is the live case that
prompted this — `trt_erythrocytosis_watch` (now `ready_to_promote` at #95) is a context relation, and
context is not a threshold. A rising-but-in-range Hct and an Hct at 0.54 are different claims, and only
the second is a safety statement.

The open fork: does `safety_threshold` belong as a third key on `marker_interpretation`, or is it a
distinct asset that should not share a home with interpretive constants — on the grounds that mixing a
"this is interesting" constant with a "this is dangerous" constant in one dict invites a producer bug
that treats them interchangeably?

Whatever the shape, extended I1 (#95) applies: a safety threshold with empty `evidence_refs` must not
gate anything. That is more load-bearing here than for a delta, because the failure direction is
asymmetric — an uncited delta produces a boring narration, an uncited safety threshold produces a
false reassurance or a false alarm.

**Status:** DONE → #104 — `safety_threshold` is a third class, and a third *gate*, not a third
read-constant. It lives in its own asset (`backend/reference/safety_thresholds.json`) rather than in
`lever_dictionary.marker_interpretation`, because the two existing constants are **measured**
(CVI/CVA-derived, non-expiring) while a safety threshold is **policy** — committee judgement carrying a
`review_due`. `gates.safety_gate()` compares a level to it, and the mechanism is complete and tested.

**The asset is empty and that is the remaining work — tracked as Q41, not here.** The question asked
what shape the thing should take; that is answered. Whether haematocrit's bands can be cited is a
different question with a different owner.

---

## Q35. The over-collapse guard is unit-only and cannot see same-unit semantic collapse

`backend/routers/labs.py:394` refuses a write when a raw label maps to a canonical whose
`unit_established` disagrees with the incoming `unit_canonical`. That catches a collapse where two
markers differ *dimensionally* — mapping something in `g/L` onto a canonical established in `mmol/L`.

It cannot catch a collapse where both markers share a unit. `glucose_fasting` and `glucose_random` are
the live example, canonical as of v0.3: both `mmol/L`, both plausibly labelled "Glucose" by a lab that
varies its wording. If a raw label were ever mapped to the wrong one of the pair, every value would be
dimensionally valid, the guard would stay silent, and the two series would merge into one — the exact
double-counting the COALESCE partition rule exists to prevent, arriving through the door the guard does
not watch. `hba1c_ngsp` (%) and `hba1c_ifcc` (mmol/mol) are safe by contrast: different units, so the
guard does cover that pair.

Note the guard is also inert wherever `unit_established` is null (`egfr`, `haemolysis_index`,
`haematocrit`, `chol_hdl_ratio`) — by design, but it means the null-unit markers have no protection of
either kind.

The fork: is a semantic-collapse guard worth building (e.g. asserting that a raw label maps to exactly
one canonical across the whole map, plus a same-unit sibling registry), or is exact-match on
`marker_name_raw` considered sufficient defence given the labels are verbatim from the report? The
`Saturation` entry is the argument for the former — it is a bare generic label, safe only because no
other panel has yet printed that word.

**Status:** UNSTARTED — no blocker. Owner: Luke.

---

## Q36. `discriminator` field semantics are inverted between two authored relations

Both authored `discriminator` relations use the field to mean the opposite thing:

- **`ggt_hepatobiliary_discriminator`** — `discriminator: "ggt"` is the **evidence marker**;
  `operands: ["ast", "alt"]` are the markers being explained.
- **`bilirubin_isolation`** — `discriminator: "bilirubin_total"` is the **marker being explained**;
  `operands: ["ggt", "alp", "haemolysis_index", "ld"]` are the evidence.

Both are authored, both read coherently in prose, and 4b's renderer will need exactly one meaning.

**#96 took a side, which is why this is now urgent rather than tidy.**
`haemoconcentration_discriminator` follows the `ggt` reading — `discriminator: "albumin"` is the
evidence, `operands` are the red cell markers being explained. That makes it **2-to-1** for
evidence-in-`discriminator`. A renderer built on the `bilirubin_isolation` reading would render the new
relation **backwards**: it would announce albumin as the thing being explained by a red cell rise,
inverting the artefact-vs-expansion call that is the relation's entire purpose. That is the concrete
cost of leaving the ambiguity open, and it should be settled by decision rather than discovered at 4b.

**Secondary, and unresolved by picking a side:** `discriminator` is a single string, but
`haemoconcentration_discriminator` genuinely has **two** evidence markers — `albumin` *and*
`protein_total`. Only `albumin` fits the field. `protein_total` survives in the `reads` prose and in
`plasma_volume_status.target_markers`, i.e. nowhere a renderer can reach it. Should `discriminator`
become a list?

**Status:** UNSTARTED — no blocker. Due **4b**, with Q34 (`safety_threshold`), Q37 (I1 enforcement),
D3 and PV1. Owner: Luke.

---

## Q37. Does `gates.py` carry citation payload into the output? — I1's extension has no enforcement

#95 extended invariant I1 from levers to read-constants: any `marker_interpretation` constant that
influences a gate requires non-empty `evidence_refs`, or it falls back to `_defaults`. **Nothing
enforces this, and there is one live violation.**

`backend/interpretation/gates.py:39-53` falls back only when the entry is absent or its `value` is
`None`. It explicitly projects `evidence_refs` away, the docstring stating they "are asset citation
payload and are NOT part of a delta". Under extended I1, `alt` — `value: 0.45`, `evidence_refs: []`,
note "citation pending — CVi source not yet pinned to a DOI" — must fall back to `_defaults` (0.30).
It does not; it uses 0.45 today.

So canon and code disagree **by design**, each documenting the opposite intent. The fork: does
`gates.py` start reading citation payload to decide fallback — making `evidence_refs` load-bearing at
runtime rather than documentation — or does I1's extension get narrowed to something the producer can
honour without inspecting citations?

**This is the parent question to #96's withholding.** The `haematocrit`/`haemoglobin` read-constants
and `plasma_volume_status` were held back precisely because I1 forbids uncited constants. If I1's
extension is narrowed rather than enforced, that withholding was stricter than the invariant actually
requires — and if it is enforced, `alt` must move at the same time.

Recorded here because it lived only in #95's body and this file is what gets actioned; an obligation
in an append-only entry has nothing pointing at it. Flagged at #95's close-out and again before #96's
merge, unminted both times.

**Status:** UNSTARTED — no blocker. Due **4b**, with Q34, Q36, D3 and PV1. Owner: Luke.

---

## Q38. `min_meaningful_delta` has no interval awareness, but RCV is interval-dependent by construction

Thirup 2003 gives **~12%** for haematocrit between successive values 1 day to 1–2 months apart, and
**~15%** for intervals up to 6 months — the widening coming from warm-weather haemodilution, with the
population mean running ~3% lower in summer. Same marker, same paper, two different answers keyed to
the gap between draws.

`min_meaningful_delta` holds **one scalar**. So whichever value lands is wrong for roughly half of a
real draw series, and this repo's series are months apart and cross seasons — the condition that
selects the wider figure is the normal case here, not the edge case. #99 landed **0.12**, the tighter
of the two, deliberately: it produces false positives (news that is really seasonal drift) rather than
false negatives (a real change called noise), which is the safer direction to be wrong in for a marker
whose failure mode is erythrocytosis.

Options: interval-banded constants; a widening factor derived from `collected_at` deltas; or accept
the tighter value and absorb the seasonal false positives, annotating them. The third is the status
quo by default rather than by decision, which is the thing to fix.

**Update at #101 — the interval-dependence now has a citable basis, not chat's assertion.** Coşkun et
al. sampled **weekly over 10 weeks** and state this is **less than one erythrocyte turnover period
(~4 months)**, offering that as the reason erythrocyte CVI came out lower than for other parameters.
So the four constants landed at #101 are valid for roughly the interval this repo's recent draws span
(~10–12 weeks) and **understate variation beyond it**; Thirup's ~15% at 6 months is the widened
figure. The two sources are not in conflict — they measure different intervals, which is the whole
point of the question.

Note this reverses the direction of the concern as originally written. Q38 was minted against #99's
0.12, worrying it was *over*-sensitive for long intervals. At #101's 0.08 the constant is tighter
still, so the same argument now bites harder: the shortfall at long intervals is larger, not smaller.

**Convention, settled at #101 and recorded here because this is where a reader reasoning about
constants will look:** constants are derived **two-sided, Z = 1.96**, because the delta gate is
direction-agnostic. EFLM's calculator defaults to one-sided (Z 1.64); the one-sided statistic belongs
with `safety_threshold` (Q34), which is directional. Not an open fork — stated so it is not
re-derived differently next time.

**Status:** UNSTARTED — no blocker. Due **4b**, with Q34 (`safety_threshold`), Q36, Q37, Q39 and Q40.
Owner: Luke.

---

## Q39. Levers have no `effect_locus` — `plasma_volume_status` moves the reading, not the biology

Every lever authored before #100 changes the underlying physiology: a TRT dose really does raise
testosterone, alcohol really does raise GGT. `plasma_volume_status` does not. It leaves red cell mass
untouched and changes the denominator — which is *precisely why* the Dill & Costill derivation works,
since that equation depends on circulating red cell mass being constant across the two draws.

Surfacing it un-flagged means a UI offering "hydration" and "TRT dose" as comparable handles on
haematocrit. They are not comparable: one changes what the number *is*, the other changes what the
number *measures*. Acting on the second as though it were the first means chasing an artefact.

`channel` cannot carry this. It encodes **how the actor acts** — `pharmacologic` | `behavioural` — and
`plasma_volume_status` is genuinely behavioural on that axis. Adding a third value would conflate two
orthogonal dimensions in one field, and #100 explicitly declined to do so.

Proposal: an `effect_locus` field, `physiology` | `measurement`, defaulting to `physiology` so every
existing lever is correct without edit. The renderer can then refuse to rank a measurement-locus lever
alongside physiology-locus ones, or label it distinctly.

**Status:** UNSTARTED — no blocker. Due **4b**. Owner: Luke.

---

## Q40. RCV is asymmetrical for a rise and a fall, but `min_meaningful_delta` holds one scalar

EFLM's calculator and **Fokkema** (Clin Chem 2006;52:1602–3) give **different RCVs for a rise and for a
fall** — the log-normal distribution of most analytes means a 30% increase and a 30% decrease are not
equally improbable. `min_meaningful_delta` holds **one value**, applied to `abs()` of the change.

Symmetric and asymmetric forms **converge below roughly 5–10% CV**, so all four erythroid constants
landed at #101 are unaffected — CVI runs 0.72–2.82% across them. **`oestradiol` is not**: at 0.42 from
CVI ≈14%, it sits well inside the divergent region, so the single scalar is meaningfully wrong in one
direction. Which direction, and by how much, is the thing to determine.

This interacts with Q34 rather than duplicating it. `safety_threshold` is directional *by design* — it
asks "is this dangerous now", which has a side. The delta gate is direction-agnostic by design. So the
asymmetry question is whether a direction-agnostic gate can honestly use a statistic that isn't, or
whether the asymmetric form forces `min_meaningful_delta` to become a pair.

**Status:** UNSTARTED — no blocker. Due **4b**, with Q34, Q36, Q37, Q38 and Q39. Owner: Luke.

---

## Q41. `safety_thresholds.json` citation capture for haematocrit — the last thing before the band

The mechanism landed at #104/#105/#106 and is fully tested. **The asset has no live entries**, so
`safety_gate` returns `no_asset` for every marker and the 0.50–0.54 band is still dark.

Bands identified but **uncited**: **0.50** from cohort definitions, **0.52** from AUA / Endocrine
Society guidance, **0.54** from Canadian guidance. Also uncited: the two positions that make
`contested: true` honest — that cutoffs across guidelines appear arbitrarily chosen, and that the
evidence for benefit of intervention is thin in *both* directions.

None has a verified DOI. Under I1 as extended at #95, landing them would be exactly the failure #99
refused for `haemoglobin`: a citation pointing at a source that does not state the number, which makes
an unsupported value look supported. So `_deferred.haematocrit` holds the shape and nothing is live.

**This is the last item between the repo and the clinical concern that opened the erythroid fork.**
Everything else on the 4b list — Q36 (discriminator semantics), Q37 (I1 enforcement), Q38
(interval-banding), Q39 (`effect_locus`), Q40 (asymmetrical RCV) — is correctness. This one is
coverage: until it lands, a haematocrit of 0.52 produces no safety signal at all.

Note the contested flag is not a hedge to be resolved away. If the cutoffs really are arbitrary, that
belongs in the output next to the band, which is why `contested` and `contested_note` are asset fields
rather than commentary.

**Status:** UNSTARTED — no blocker; the capture is the first step of the work, not a precondition on
someone else. Owner: Luke.
## Q42. The 12-hour-clock scrape failure in `parseSleepTimingContentDesc` is silent and cross-cutting — owned by `health-connect-app`

`HRVDataModel.parseSleepTimingContentDesc` captures `(\d+:\d+)` from a Samsung content-desc, and
`parseClockToMinutes` accepts it without a meridiem. If the phone clock is ever set to 12-hour, `10:12 pm`
is stored as `10:12` — a 12-hour error that reads as a valid time. It is silent, and it affects **every**
consumer of `bedtime`/`wake_time`, not just CBT-I (surfaced while designing the CBT-I diary prefill,
which now sanity-gates prefills against the prescribed window as a local defence — brief Step 6).

This is a scraper defect in the companion app's store, not health-app's. Raised here so it is not lost;
the fix and its canonical question belong in `health-connect-app`'s `OPEN_QUESTIONS`, not this repo.

**Status:** UNSTARTED — no blocker. Owner: Luke. **Next action:** carry to `health-connect-app`'s
`OPEN_QUESTIONS` (cross-repo; not editable from a health-app-rooted session).

---

## Q43. Does production share `FERNET_KEY` (and `SECRET_KEY`) with the local development `.env`?

`mcp_server.py:288` decrypts `api_key_encrypted` for stored third-party credentials, so a shared Fernet
key makes every stored credential recoverable by anyone holding the dev value. The question is only
whether the two environments hold the same key, not what either key is.

Resolve by comparing **SHA-256 digests** local vs Railway — digests only, never values, per #110's
second clause. If they match, rotation is not a variable swap: every `api_key_encrypted` row was
encrypted under the old key and must be re-encrypted, so the fix carries a data migration.

**Status:** DONE → #111. **Both keys are prod-isolated — the digests differ on both.** No shared key,
therefore no re-encryption migration over `api_key_encrypted` and no prod rotation on this account.

**Method, which matters as much as the outcome.** A single script run under
`railway run --service health-app-backend` held both sides at once: Railway's values arrived as
injected `os.environ`, the dev values were parsed from `backend/.env` on disk, and each was reduced to
`sha256(value)[:12]` *inside* the comparison. No value was printed, logged, or returned, and the
digests themselves are deliberately not recorded here — this repo is public and a digest of a live
secret is still identifying. The comparator carried both controls: identical input reported equal,
differing input reported unequal, so "differs" cannot be a broken comparison silently passing.

This entry supersedes an earlier assertion that the comparison had already been performed. It had been
reported in chat but never attested against an artefact — the third instance in this sequence of a
claim about an unreadable surface being carried as fact (see #110). The result happened to be correct;
the basis was not, until this run.

---

## Q44. `railway variables --kv` prints secret values into session transcripts — the fix is the command, not the operator

Established while settling #110's provenance question. Four of seven transcripts carry the Railway
Postgres credential **only** as `tool_result` output, never as operator input, and every one of those
originates from the same command shape:

```
railway variables --service <service> --kv
```

`--kv` returns name=value pairs, so any invocation persists live secrets into the transcript — and the
grep-for-a-name variants used alongside it (`| grep -i DATABASE_URL`) narrow the lines returned without
removing the values. This is #110 clause 2 as a live case rather than a retrospective one: the operator
did nothing wrong, the diagnostic did.

The credential-free substitute already exists and is proven on this machine: `railway run <cmd>` injects
`DATABASE_URL` into the child process without printing it (used for the phase-1 production reconcile).
For presence or equality checks, a digest comparison as in [[Q43]] — never `--kv`.

Open: whether to ban `--kv` outright in the loop rules or require it be piped through a masking filter;
and whether the seven existing transcripts are purged or retained after rotation, since they remain the
exposure surface once the credential is dead only if it is in fact dead.

**Status:** DONE → #111. Resolved by a two-layer prohibition: the standing rule in `CLAUDE.md`'s
shared block (the enforcing layer) plus `.claude/settings.json` deny patterns (a speed bump, explicitly
not relied upon — see #111 for why).

**The rule is general, not vector-specific**, because the CLI's own `--help` showed the narrow reading
was wrong: `--kv` *and* `--json` both state they print raw values, the base command is `variable` with
`variables` as an alias, and `-k` is a short form — four bypasses of a `--kv`-only pattern. Since the
sanctioned substitute is `railway run` (a different command entirely, no flag dependency), the deny
patterns widened to the whole `railway variable(s)` family without blocking the replacement. Proven by
running the substitute after the deny list landed: 114 injected variables, names only, zero values.

**Residual — NOT immaterial, contrary to the initial framing, and verified rather than assumed.**
Presence-only search across 60 transcript files (positive control fired on a known-present string):
the dev `FERNET_KEY` appears in 2 files, `SECRET_KEY` in 2, and the `ANTHROPIC_API_KEY` value currently
in `backend/.env` in 1 file, 24 times. The local dev DB (`health-app.db`) is **not** fixtures — it holds
one `user_integrations` row, `provider='hevy'`, encrypted under that exposed dev Fernet key (the row was
never decrypted; only its existence was read). So a **local** rotation is owed: the Hevy credential
itself, then the dev `FERNET_KEY`, then re-encrypt or drop that row. Prod is unaffected (Q43).

**Still open, deliberately out of scope here:** whether the second Postgres digest seen across four
transcripts is a retired credential or a second live one — a cheap co-occurrence test, but a finding
rather than a fix. And whether the transcripts are purged or retained once the credentials in them are
dead.

---

## Q45. The VA CBT-I diary does not say which day a recorded nap belongs to — so the engine excludes nap nights rather than attributing them

`daily_records.naps_min` is silent when wrong. The titration engine reads naps for the night
terminating on wake-date W from `date = W-1`, which is only correct if the instrument's nap item refers
to the day *preceding* the recorded night. **The instrument does not say.**

**This search was run, and it was scoped.** Every text cell across all five sheets of the VA CBT-I
Sleep Diary Calculator export was matched against both a nap pattern and a temporal pattern
(`yesterday|today|last night|previous day|during the day|...`). Every nap reference is bare:
`Naps (minutes)`, `Naps`, `Biological Need for Sleep (TST + Naps)`. The FAQ mentions naps only for the
TST24 definition and for scheduled-nap timing advice — neither states which day a diary row's nap
covers.

**Positive control — this is what makes it a scoped null and not a failed search.** The temporal
pattern *did* fire elsewhere in the same workbook, on `"Did you eat before bed? How long before bed?"`.
The detector demonstrably finds temporal qualifiers in this instrument and found none attached to the
nap item. Per #110 clause 1, that is the difference between "the wording does not settle it" and
"nobody looked". **Do not re-run this search.**

**Resolution, adopted:** the engine **excludes nap-flagged nights entirely**, recording them in
`cbti_prescriptions.excluded_nights` with reason `nap`, rather than attributing them to a date. Two of
the imported block's 53 nights carry naps, so exclusion costs almost nothing while a wrong attribution
is silent. This is the standing behaviour until the question is answered, not a placeholder.

**Status:** UNSTARTED — no blocker; the engine's exclusion path is the interim answer. Owner: Luke.
**Next action to close it:** establish the nap item's referent from the VA CBT-I protocol
documentation or by asking the clinician who administered the block — not from the workbook, which has
already been searched to exhaustion.

---

_Gate summary (2026-06-22, on-device, SM-S921B): GATE 1 PASS → DECISIONS_LOG #20.
GATE 2 PASS (deep slivers survive the HC write at 30s resolution; deep is heavily
fragmented — ~26 of 30 deep segments are <3 min slivers). GATE 3 INCONCLUSIVE → Q3._
