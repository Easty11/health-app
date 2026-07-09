# METRICS.md — per-page metric catalogue

A reference map of every metric each frontend page displays and where it comes
from, at **display-label → code field → backend endpoint → backend field/column**
depth. Purpose: a drift baseline. If a field is renamed, a column is dropped, or
a value silently changes shape (as HC sleep-date did in OPEN_QUESTIONS Q4), this
doc is what you diff the change against.

_Scope note (chosen depth): this catalogue stops at the backend response
field / DB column. It catches **frontend↔backend** contract drift but not
upstream Health-Connect / device / wire-field changes — that deeper layer would
add a `source wire-field` column without restructuring these tables._

_Not repo-canonical (yet). This is a hand-verified snapshot as of commit
`4d6a381` (2026-07-09). It is not auto-generated and carries no lockstep rule;
promoting it to canonical (update-in-step-with-UI) would be a DECISIONS_LOG
entry. Verify against code before trusting for a gating decision._

## Legend — source tables

| Source | Meaning |
|--------|---------|
| `samsung_hrv_readings` | Samsung Health accessibility-scrape (the "scraper"). **Not** Health Connect. |
| `health_connect_syncs` | Health Connect ingest, one row per user per date. |
| `aerobic_sessions` | Polar AccessLink v4 cardio sessions. |
| `daily_records` | v2 check-in store (CheckInAM + NightlyCloseOut). |
| `daily_checkins` | Legacy check-in store (CheckIn.jsx). |
| Hevy API | Live third-party passthrough — fields are Hevy's JSON, not a local column. |
| computed | Derived in code (client or server); not a stored column. |

## Cross-cutting notes (read first)

- **Two parallel sleep/HRV sources coexist.** The Recovery card (HealthPanel)
  renders sleep + HRV from `samsung_hrv_readings`. The AM check-in passive card
  mixes HRV from `samsung_hrv_readings` with sleep from `health_connect_syncs`.
  Same "HRV"/"Sleep" labels, different columns — do not assume one source.
- **`health_connect_syncs` sleep reaches the UI in exactly one place:** the AM
  check-in passive "Sleep" tile (`/checkin-v2/prefill` → `sleep_min`, from
  `health_connect_syncs.sleep_duration_minutes`, newest row with `date ≤ today`).
  This is the field OPEN_QUESTIONS Q4 mis-dated; the #64 wake-date fix corrects
  precisely this surface.
- **Most `health_connect_syncs` columns are ingested but never rendered:**
  `steps`, `resting_heart_rate`, `hrv_rmssd`, `sleep_score`, `deep/rem/light_
  sleep_minutes`, `active_calories`, `distance_meters`, `oxygen_saturation`,
  `respiratory_rate`. They feed context/MCP/chat, not any page in this catalogue.
- **Two check-in systems coexist.** Legacy `daily_checkins` (CheckIn.jsx,
  `readiness_score`) vs v2 `daily_records` (CheckInAM/NightlyCloseOut,
  `naive_baseline`). The two scores use different formulas and scales.

---

## Dashboard — `frontend/src/pages/Dashboard.jsx`

Shell only; composes HealthPanel + WorkoutPanel + ChatPanel. Own data surface:

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| AM check-in done badge | `record.am_timestamp` | `GET /checkin-v2/today` | `daily_records.am_timestamp` |
| PM check-in done badge | `record.pm_timestamp` | `GET /checkin-v2/today` | `daily_records.pm_timestamp` |

## Recovery card — `frontend/src/components/HealthPanel.jsx`

`GET /health/summary` → `latest` is the newest `SamsungHRVReading` (context ≠
'session'), serialized by `_serialize_reading`. **All sleep/HRV here is the
scraper, not Health Connect.**

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Date captured | `latest.captured_at` | `/health/summary` | `samsung_hrv_readings.captured_at` |
| HRV (ms) | `latest.hrv_ms` | `/health/summary` | `samsung_hrv_readings.hrv_ms` |
| HRV vs baseline | `vs_baseline` | `/health/summary` | computed: `latest.hrv_ms − baseline_hrv` |
| 7-day avg HRV | `baseline_hrv` | `/health/summary` | computed: mean of last 7 `hrv_ms` |
| Reading count | `trend.length` | `/health/summary` | length of `trend[]` (last 7 rows) |
| Sleep duration | `latest.total_sleep_time_minutes` ?? `actual_sleep_time_minutes` | `/health/summary` | `samsung_hrv_readings.total_sleep_time_minutes` / `.actual_sleep_time_minutes` |
| Sleep efficiency | `latest.sleep_efficiency_pct` | `/health/summary` | `samsung_hrv_readings.sleep_efficiency_pct` |
| Deep (min) | `latest.deep_minutes` | `/health/summary` | `samsung_hrv_readings.deep_minutes` |
| REM (min) | `latest.rem_minutes` | `/health/summary` | `samsung_hrv_readings.rem_minutes` |
| Light (min) | `latest.light_minutes` | `/health/summary` | `samsung_hrv_readings.light_minutes` |
| Awake (min) | `latest.awake_minutes` | `/health/summary` | `samsung_hrv_readings.awake_minutes` |
| Resp rate | `latest.respiratory_rate` | `/health/summary` | `samsung_hrv_readings.respiratory_rate` |
| Sleep HR | `latest.sleep_hr_bpm` | `/health/summary` | `samsung_hrv_readings.sleep_hr_bpm` |
| SpO2 (%) | `latest.spo2_average_pct` | `/health/summary` | `samsung_hrv_readings.spo2_average_pct` |
| Bedtime | `latest.bedtime` | `/health/summary` | `samsung_hrv_readings.bedtime` |
| Wake time | `latest.wake_time` | `/health/summary` | `samsung_hrv_readings.wake_time` |

_`_serialize_reading` also returns `sleep_duration_home_tile`, `*_pct`,
`extraction_method`, `context` — fetched but not rendered here._

## Training Data — `frontend/src/components/WorkoutPanel.jsx`

### Hevy (live API passthrough)

`GET /integrations/hevy/workout-count`, `GET /integrations/hevy/workouts` — fields
are Hevy's own JSON via `HevyClient`, not local columns.

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Total workouts | `workout_count` / `count` | `/integrations/hevy/workout-count` | Hevy API |
| Workout title | `workout.title` / `.name` | `/integrations/hevy/workouts` | Hevy API `title` |
| Workout date | `workout.start_time` / `.created_at` | `/integrations/hevy/workouts` | Hevy API `start_time` |
| Duration | computed from `start_time`,`end_time` | `/integrations/hevy/workouts` | computed |
| Exercise names | `exercises[].title` / `.exercise_template_id` | `/integrations/hevy/workouts` | Hevy API |
| Set type/weight/reps/dur | `set.type/.weight_kg/.reps/.duration_seconds` | `/integrations/hevy/workouts` | Hevy API |
| Est 1RM | `epley1RM(weight_kg,reps)` | (client) | computed (Epley) |
| Working sets / Volume | computed sums | (client) | computed |

### Hevy session analysis

`GET /health/session-analysis/{id}`, `GET /health/latest-session-analysis`;
written by `POST /health/analyse-session`. Stored as `UserKnowledgeEntry`
(type `session_analysis`); `readiness_context` joined from `SamsungHRVReading` at
workout date.

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Volume (kg) | `analysis.total_volume_kg` | `/health/session-analysis/{id}` | computed `_compute_workout_stats` |
| Total sets | `total_sets` | same | computed |
| Muscle groups | `muscle_groups` | same | computed |
| Top 1RM per lift | `analysis.top_1rm{}` | same | computed (Epley max) |
| HRV at session | `analysis.readiness_context.hrv_ms` | same | `samsung_hrv_readings.hrv_ms` (workout-date row) |
| Last analysis title/date | `latestAnalysis.workout_title/.workout_date` | `/health/latest-session-analysis` | knowledge entry value |

### Polar aerobic

`GET /integrations/polar/aerobic-sessions` → `AerobicSessionOut[]`; client
`normalizePolar` renames fields (shown as `code ← backend`).

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Sport | `sport` ← `sport_name` | `/integrations/polar/aerobic-sessions` | `aerobic_sessions.sport_name` |
| Date/start | `start_time` | same | `aerobic_sessions.start_time` / `.session_date` |
| Duration | `duration_seconds` ← `duration_minutes`×60 | same | `aerobic_sessions.duration_minutes` |
| Avg HR | `avg_hr` ← `hr_avg` | same | `aerobic_sessions.hr_avg` |
| Max HR | `max_hr` ← `hr_max` | same | `aerobic_sessions.hr_max` |
| Calories | `calories` | same | `aerobic_sessions.calories` |
| Cardio load | `cardio_load` | same | `aerobic_sessions.cardio_load` |
| Recovery (h) | `recovery_hours` | same | `aerobic_sessions.recovery_hours` |
| HR zones Z1–Z5 (sec) | `hr_zones.z1..z5_seconds` | same | `aerobic_sessions.z1_seconds..z5_seconds` |

_`AerobicSessionOut` also returns `muscle_load`, `sport_id`, `stop_time`,
`source`, `source_session_id` — not rendered._

## Lab reports — `frontend/src/pages/Metrics.jsx`

Upload → extract → confirm. `GET /labs/canonical-map`, `POST /labs/extract`,
`POST /labs/confirm`. Table rows are `results[]` from the extraction response
(`ExtractionResult`), persisted to `lab_reports`/`lab_results` only on confirm.

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Marker | `r.marker_name_raw` | `/labs/extract` | → `lab_results.marker_name_raw` |
| Value | `r.value_num` / `value_operator` / `value_qualitative` | `/labs/extract` | → `lab_results.value_num` etc |
| Unit | `r.unit_canonical` / `r.unit_raw` | `/labs/extract` | → `lab_results.unit_canonical` |
| Ref range | `r.ref_low/ref_high/*_exclusive` | `/labs/extract` | → `lab_results.ref_low/ref_high/...` |
| Lab flag | `r.lab_flag` | `/labs/extract` | → `lab_results.lab_flag` |
| Computed flag | `r.computed_flag` | `/labs/extract` | → `lab_results.computed_flag` |
| Confidence % | `r.field_confidence{...}` | `/labs/extract` | → `lab_results.confidence` (min) |
| Flag agreement | `r.flag_agreement` | `/labs/extract` | model output |
| Canonical mapping check | `canonicalMap[marker_name_raw]` | `/labs/canonical-map` | `reference/marker_canonical.json` |
| Report lab/panel | `report.lab_name` / `.panel_name_raw` | `/labs/extract` | → `lab_reports.lab_name/panel_name_raw` |
| Collected date | `report.dates.collected` | `/labs/extract` | → `lab_reports.collected_date` |
| Referrer | `report.referrer.name_raw` | `/labs/extract` | → `lab_reports.referrer_name_raw` |
| Source completeness | `report.source_completeness` | `/labs/extract` | → `lab_reports.source_completeness` |
| Report comments | `report.report_comments[]` | `/labs/extract` | → `lab_reports.report_comments` |

## Legacy morning check-in — `frontend/src/pages/CheckIn.jsx`

`GET /checkin/today`, `GET /checkin/prefill`, `POST /checkin` → `daily_checkins`.

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Sleep quality (1–10) | `sleep_quality` | `POST /checkin`; `GET /checkin/today` | `daily_checkins.sleep_quality` |
| Fatigue (1–10) | `fatigue` | same | `daily_checkins.fatigue` |
| Shoulder pain (0–10) | `shoulder_pain` | same | `daily_checkins.shoulder_pain` |
| Motivation (1–10) | `motivation` | same | `daily_checkins.motivation` |
| Readiness score | `readiness_score` / `liveScore` | `GET /checkin/today`; client re-computes | computed `_calc_readiness` → `daily_checkins.readiness_score` |
| Rugby session yesterday | `rugby_session_yesterday` | `/checkin`; prefill | `daily_checkins.rugby_session_yesterday` |
| Notes | `notes` | same | `daily_checkins.notes` |
| Rugby session title (prefill) | `rugby_session_title` | `GET /checkin/prefill` | Hevy API title (RUGBY_KEYWORDS) |
| Last session title/date (prefill) | `last_session_title/last_session_date` | `GET /checkin/prefill` | Hevy API latest workout |

## v2 morning — `frontend/src/pages/CheckInAM.jsx`

`GET /checkin-v2/prefill`, `POST /checkin-v2/am` → `daily_records`.

### Passive card (read-only sensor data)

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Ring HRV (ms) | `prefill.hrv_ms` | `GET /checkin-v2/prefill` | `samsung_hrv_readings.hrv_ms` (latest ≤ today) |
| HRV vs 7d mean | `prefill.hrv_vs_baseline` | same | computed vs 7-day SamsungHRV mean |
| Sleep (h m) | `prefill.sleep_min` | same | **`health_connect_syncs.sleep_duration_minutes`** (newest, `date ≤ today`) — Q4/#64 surface |

### Form inputs (→ `daily_records`)

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| Morning readiness (1–5) | `morning_readiness` | `POST /checkin-v2/am` | `daily_records.morning_readiness` |
| Sleep quality (1–5) | `sleep_quality` | same | `daily_records.sleep_quality` |
| Fatigue (0–10) | `fatigue` | same | `daily_records.fatigue` |
| Motivation (0–10) | `motivation` | same | `daily_records.motivation` |
| Life/work load (1–5) | `life_load` | same | `daily_records.life_load` |
| Soreness {shoulder,hamstring} | `soreness` | same | `daily_records.soreness` (JSON) |
| Drank last night | `drank_last_night` | same | gate; not stored directly |
| Alcohol units | `alcohol_units` | same | `daily_records.alcohol_units` |
| Alcohol finish time | `alcohol_finish_time` | same | `daily_records.alcohol_finish_time` |
| Readiness baseline (result) | `result.naive_baseline` | `POST /checkin-v2/am` response | computed `calc_naive_baseline` → `daily_records.naive_baseline` |

_`DailyRecordOut` also exposes `model_forecast`, `model_confidence`,
`passive_hrv_ms`, `passive_sleep_min`, `mindfulness_occurred/_duration_min` —
returned but this page renders only `naive_baseline`._

## v2 nightly — `frontend/src/pages/NightlyCloseOut.jsx`

`GET /checkin-v2/today`, `POST /checkin-v2/pm` → `daily_records`.

| Display | Code field | Endpoint | Backend field/column |
|---------|-----------|----------|----------------------|
| How did today land (1–5) | `today_rating` | `POST /checkin-v2/pm`; `GET /checkin-v2/today` | `daily_records.today_rating` |
| Trained today | `trained_today` | same | gate; drives session fields |
| Session quality (1–5) | `session_quality` | same | `daily_records.session_quality` |
| Session RPE (0–10) | `session_rpe` | same | `daily_records.session_rpe` |
| PM done flag | `pm_timestamp` | `GET /checkin-v2/today` | `daily_records.pm_timestamp` |

_Mindfulness ("read from Health Connect automatically") maps to
`daily_records.mindfulness_occurred/_duration_min`, backfilled by the HC sync,
not captured on this form._

## Settings — `frontend/src/pages/Settings.jsx`

No health metrics. Config only: `GET /integrations` (`{provider, connected}`),
`POST/DELETE /integrations/{provider}`, `GET /integrations/polar/auth-url`,
knowledge CRUD `GET/POST/PUT/DELETE /knowledge` (`{id, category, content}`).

## Pages with no metrics

`Login`, `Register`, `ForgotPassword`, `ResetPassword` (auth); `ChatPanel`
(LLM conversation).

---

_Routers not reached by any page above: `recovery.py`, `engine.py`,
`samsung_hrv.py`, `health_connect.py`, `chat.py` — these serve the companion
ingest / MCP tools / chat context, not the React pages. Out of scope for a
per-page catalogue; a "metrics consumed by chat/context" map would be a separate
section if wanted._
