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

**Status:** BLOCKED — blocker: cannot be actioned from a health-app-rooted session; disposing of an HCA
remote branch requires a `health-connect-app`-rooted session (single-repo scope rule). Owner: Luke.
Unblocks on: any HCA-rooted session.

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

_Gate summary (2026-06-22, on-device, SM-S921B): GATE 1 PASS → DECISIONS_LOG #20.
GATE 2 PASS (deep slivers survive the HC write at 30s resolution; deep is heavily
fragmented — ~26 of 30 deep segments are <3 min slivers). GATE 3 INCONCLUSIVE → Q3._
