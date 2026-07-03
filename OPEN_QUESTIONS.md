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

**Status:** open

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

**Status:** open

---

_Gate summary (2026-06-22, on-device, SM-S921B): GATE 1 PASS → DECISIONS_LOG #20.
GATE 2 PASS (deep slivers survive the HC write at 30s resolution; deep is heavily
fragmented — ~26 of 30 deep segments are <3 min slivers). GATE 3 INCONCLUSIVE → Q3._
