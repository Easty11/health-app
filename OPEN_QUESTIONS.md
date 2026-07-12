# OPEN QUESTIONS

Undecided forks and unverified-at-machine items. One status per item:
`open` / `verifying` / `resolved → #` (where `#` is the resolving DECISIONS_LOG entry).

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

**Status:** resolved → #20. Fix deployed to Railway (PR #2) and all 31 HC rows
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

**Status:** resolved — fixed in `health-connect-app` `36df9a2` (confirmed patch-present
on HCA master): `collapseSleepSessions()` de-duplicates the overlapping SleepSession
records before downstream consumers, behaviorally verified 9/9.

---

## Q3. HR sampling cadence during sleep unconfirmed (`hrMedianGapSec = 0`)

Gate 3 returned `hrMedianGapSec: 0` over 802 samples, not the expected ~60s (1/min). Caused
by duplicate HR timestamps from the same record-doubling as Q2. The artifact flagging depends
on real HR density during sleep, so this must be re-measured after HR is de-duped. Gate 3 is
INCONCLUSIVE — do **not** calibrate `DELTA_ARTIFACT` / `SPREAD_SPIKE` / `SHORT_MS` or wire
`runDeepConfidence` into readiness/Banister until resolved.

**Status:** open

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

**Status:** verifying — resolved in code at DECISIONS_LOG #64
(`fix/hc-sleep-wake-date-attribution`): canonical sleep-date = **local (AEST) wake-date**
(`endTime`), aligning to the scraper; `_aggregate_day` filter + date-collection loop switched
to wake-date-only via a tz-aware `_wake_date`, and existing sleep values cleared by migration
`f4e1a2b3c6d7` for a post-deploy HCA re-sync. G4 (confirm `health_connect_syncs[date]` sleep
stages match `samsung_hrv_readings[date]` **same-date**, not date+1) is pending the
operational re-sync against live Railway data — this session could not reach Railway. Move to
`resolved → #64` once G4 passes.

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

**Status:** open

---

## Q6. Strength volume-load not yet ingested into daily training load

Decision 28 routes strength volume-load → the Mechanical + Neuromuscular windows as a
named, non-optional daily-TL input. The decision is settled, but it is unverified at the
machine: no Postgres query has confirmed Hevy strength volume actually populating the
per-window `load_metrics` rows. Verify a real query shows strength volume landing in the
load path before the four-window engine — or even Tier 0 with a strength term — can be
trusted. Was tracked as "B2" in an out-of-project session's scheme that never entered the
repo; recorded here under the canonical Q-series.

**Status:** open, resolves → #28 on Postgres verify.

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

**Status:** open

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

**Status:** resolved → #43

---

## Q9. Consolidate legacy free-text `user_knowledge` into `user_knowledge_entries`?

Legacy `user_knowledge` (free-text category/content) coexists with structured
`user_knowledge_entries` per #44. Fold the legacy KB in as a `type="note"` entry and
retire `routers/knowledge.py`'s legacy write path + `context_builder`'s parallel
`knowledge_entries` param — making `context_builder` a true single-source formatter over
`current_state` — or keep them permanently distinct (free-text notes vs typed declared
state)? Deferred by #44; not urgent.

**Status:** open

---

## Q10. Build AccessLink per-second ingest for the Metabolic-load window (HC/companion lane)?

#35 established the dependency: HC carries no per-second R-R/HR-zone; only AccessLink
(v3 REST exercise-samples / TCX export) does. #46 specified the exact pathway but it is
not built. PSL covers Luke's direct solo/gym capture, so the need only bites if the
HC/companion lane carries a Polar user requiring per-second — currently none (Deb's
wearable integration deferred, Cooper has no wearable).

**Status:** PARKED, low priority. Revisit when the Metabolic-load channel is wired to
Polar-in-HC data for a real consumer.

---

## Q11. Lab store — where per-marker observed results live

Fork: `lab_result` typed table vs `user_knowledge_entries type="lab"` vs `health_events`.
Blocked the #49 build, the #48 write path, and lever-dictionary wiring alike.

**Status:** resolved → #52 (`lab_report` + `lab_result` table pair).

---

## Q12. Per-marker minimum meaningful delta

Where the #49 delta-gate threshold lives; global vs per-marker.

**Status:** resolved → #53 (per-marker `min_meaningful_delta`, in-repo #51-family reference asset).

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

**Status:** open — verify a captured payload shows `payload.hrv` empty (absent, not unmapped
per Q5); if absent-confirmed, the residual is the HRV single-point-of-failure risk, tracked to
issue #9 (`health-connect-app` scraper canary). Cross-refs Q5, issue #9.

---

## Q14. Hevy create-loop id contract

Does `POST /v1/exercise_templates` return the canonical string id (UUID/hex) or a bare
integer (the spec example shows an int)? This decides the create loop's shape:
create→single-row-upsert (if the create response carries the canonical id) vs
create→list-back (if it does not). Resolve empirically: one throwaway live create + a
list-match against `get_exercise_templates`. **How-you-know** artifact required before
any build.

**Status:** resolved → #65 — the live OpenAPI spec types the `POST
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

**Status:** open

---

## Q16. `hevy.py` `get_exercise_history` path

The connector calls `/exercise_templates/{id}/history`; community docs show
`/exercise_history/{id}`. Verify against the live API and fix the connector path if it is
wrong.

**Status:** resolved → #69. Path corrected to `/v1/exercise_history/{id}` (template id unchanged)
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
HRV rebound, corroborated by respiratory rate drifting ~14.0→~13.5 br/min over the same window via a
*different sensor path* (a scraper bug cannot move RR). The 68% rise exceeds published GLP-1 HRV
effects alone.

**Decision gate = Task 1 node dump** (branch `feat/hrv-node-dump` in **`health-connect-app`**, a
separate repo — not reachable from a health-app-rooted session). Dump the `HRVAccessibilityService`
node tree; identify the bound node's field/metric identity and whether a sibling node carries the
pre-6-Jul metric. Different node/metric → (A): correct the binding, then reconcile. Same node/metric →
(B): rebound is real. **Historical row reconciliation must NOT run until this gate resolves** —
reconciling against a moving metric definition bakes the error in permanently. Confirmatory input held
ready: `feat/recovery-metrics-rhr` (Task 2, RHR series in `get_recovery_metrics`) — but note the primary
`samsung_hrv_readings` RHR is the scraper's `sleep_hr_bpm`, same device family as HRV; the truly
independent discriminator is Health Connect `resting_heart_rate` (query `health_connect_syncs` directly).

**Status:** open — blocked on Task 1 node dump (`health-connect-app`). Cross-refs Q13, issue #9,
`BRANCHES.md` `feat/recovery-metrics-rhr`.

---

## Q18. `samsung_hrv_readings` historical out-of-range sweep

DECISIONS_LOG #70 added an ingest bounds guard that nulls-and-logs out-of-range biometrics going
forward (trigger: `2026-06-28 Eff=119%`), but **existing rows are unswept** — the sweep could not run
this session because the local `DATABASE_URL` is dev SQLite with zero production rows. Run the
full-schema `NOT BETWEEN` sweep (mirrors `_BOUNDS` in `routers/samsung_hrv.py`) against **Railway
Postgres**; for any historical violator, null/clamp the offending field (the guard only protects new
writes). If efficiency was unbounded, assume other fields were too — the sweep covers the whole
numeric schema, not just efficiency.

**Status:** open — verify-at-machine (Railway Postgres). Independent of Q17.

---

_Gate summary (2026-06-22, on-device, SM-S921B): GATE 1 PASS → DECISIONS_LOG #20.
GATE 2 PASS (deep slivers survive the HC write at 30s resolution; deep is heavily
fragmented — ~26 of 30 deep segments are <3 min slivers). GATE 3 INCONCLUSIVE → Q3._
