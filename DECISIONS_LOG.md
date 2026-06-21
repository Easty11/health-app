# DECISIONS LOG

Format: Decision · Rationale · Status · Do not revisit unless…

---

## Architecture decisions

### 1. Health Connect requires Expo companion app as bridge

**Decision:** Health Connect data is read by an Expo React Native companion app (`health-connect-app`), which POSTs to the backend. The web backend does not call Health Connect directly.

**Rationale:** Health Connect is an Android on-device API. It cannot be accessed remotely. A native (or near-native) on-device app is required to read from it and relay data to the backend.

**Status:** Locked. This is a platform constraint, not a design choice.

**Do not revisit unless:** A server-side Health Connect API is released (currently does not exist).

---

### 2. Expo over native Kotlin for companion app

**Decision:** Companion app built with Expo React Native using `.android.js` / `.ios.js` platform file convention.

**Rationale:** Faster cross-platform path — Android now, iOS later. Avoids maintaining two separate codebases. Luke has existing React/JS familiarity.

**Status:** Active. Android build working (permission issues notwithstanding).

**Do not revisit unless:** Health Connect integration requires capabilities only accessible via native Kotlin, or iOS becomes a priority and Expo limitations become blocking.

---

### 3. Polar H10 is session-only; role is re-validation instrument, not calibration layer

**Decision:** Only aerobic session data is captured from Polar; no resting HRV is attempted from H10. H10 is the re-validation instrument for Ring HRV coherence — not a correction factor source. (Transport superseded: aerobic sessions now come via the Polar AccessLink v4 API directly, not the Polar Flow → Health Connect bridge — see Decision 17. The role described here is unchanged.)

**Rationale:** Polar H10 is a chest strap designed for session-only aerobic monitoring. Ring and H10 measure in different physiological windows (nocturnal averaged vs morning supine). No correction factor can be computed between them. H10 validates that the Ring remains internally coherent and trend-faithful, not that it is accurate in absolute terms. Polar is primary for aerobic session data; Samsung Health is connected to Polar, not the other way around.

**Status:** Locked.

**Do not revisit unless:** A different Polar device (e.g. Polar Vantage) is introduced for a user.

---

### 4. Garmin Body Battery — explicitly not pursuable

**Decision:** Garmin Body Battery metric is not integrated and will not be attempted.

**Rationale:** Garmin does not expose Body Battery via any third-party API regardless of approach. This is a documented limitation and a deliberate business restriction by Garmin.

**Status:** Closed. Do not attempt.

---

### 5. Samsung Health → Health Connect does NOT write Ring HRV or key recovery metrics

**Decision:** Samsung Ring metrics cannot be accessed via the Samsung Health → Health Connect pipeline for the following: HRV (RMSSD), resting heart rate, respiratory rate, sleep stages. Only sleep duration, steps, and SpO2 are potentially available via Health Connect from Samsung sources.

**Rationale:** Confirmed June 2026 via web search (Samsung community threads) and on-device diagnostic. Samsung Health does not write these metrics to Health Connect regardless of permissions. This is a platform constraint, not a permissions issue.

**Status:** Closed. Do not attempt to pull these metrics via Health Connect from Samsung sources.

**Do not revisit unless:** Samsung explicitly adds these types to Health Connect sync and it is verified on-device with a Postgres query.

---

### 6. Samsung Health Accessibility Scraper is the current Ring HRV path

**Decision:** Nightly HRV (RMSSD), sleep stages, respiratory rate, sleep efficiency, and SpO2 are extracted from the Samsung Health UI via an Android AccessibilityService (`HRVAccessibilityService.kt`). Data posts to `/samsung-hrv/sync`. This is the production HRV pipeline as of June 2026.

**Rationale:** No official API exposes Ring HRV to third parties. Accessibility scraping is fragile but confirmed working with full overnight extraction. It is the only viable path until the Samsung Health Data SDK is confirmed to cover these metrics.

**Status:** Active. Confirmed working June 2026. Recognised as the highest fragility component in the system.

**Fragility requirements:** Canary mechanism required (null, stale/frozen, implausible value detection). Honest score degradation must be surfaced to the user when HRV is unavailable — never silently score without it.

**Do not revisit unless:** Samsung Health Data SDK confirms it can return HRV, in which case migrate and retire the scraper for that metric.

---

### 7. Samsung Health Data SDK is the migration target

**Decision:** The Samsung Health Data SDK is the correct migration target for metrics it can reliably serve (sleep stages, SpO2, skin temperature, potentially HRV). Migrating any metric from the scraper to the SDK shrinks the scraper's blast radius.

**Rationale:** The SDK is an official channel with lower fragility than UI scraping. Developer mode (tap Samsung Health version number 10 times) allows reads without formal partnership approval — sufficient for personal/family use. Formal Samsung partnership only required for commercial distribution.

**Status:** Active (non-HRV metrics only). HRV via scraper confirmed as permanent path — SDK HRV investigation closed. Remaining scope: SDK migration for sleep stages, SpO2, skin temperature when priority warrants.

**Do not revisit unless:** Samsung removes developer mode access.

---

### 8. Composite readiness score formally suppressed until HRV data path confirmed

**Decision:** The composite readiness score must not be displayed until a confirmed RMSSD data path exists and has produced at least 7 days of readings.

**Rationale:** RMSSD is 30% of the readiness score and the primary recovery gate. Without it the score is not physiologically meaningful. Displaying a partial score is misleading.

**In the interim:** Surface training load (Hevy ACWR), sleep duration, and subjective check-in as separate indicators — not aggregated into a composite score.

**Status:** Active constraint. Scraper path confirmed working; pending 7+ consecutive days of readings before composite score is unblocked.

---

### 9. Passivity priority for HRV — Galaxy Ring primary, H10 secondary

**Decision:** Galaxy Ring is the primary HRV source. Passivity is explicitly prioritised over measurement precision — no morning protocol, no deliberate measurement required.

**Rationale:** Ease of collection beats marginal precision gains. The Ring captures HRV passively overnight. The H10 requires active participation. Sustainable passive collection is more valuable than sporadic high-precision reads for long-term trend analysis.

**Status:** Locked.

---

### 10. Annotate confounds, don't discount scores

**Decision:** When a known confound (alcohol, illness, travel, disrupted sleep environment) suppresses a metric, tag the cause and preserve the score. Do not adjust, exclude, or discount the measurement.

**Rationale:** The readiness state was real — the metric accurately captured a genuine suppression. Discarding the reading corrupts baseline trending. Tagging the cause lets the trend engine distinguish chronic overreaching from acute, benign suppressions. Both the accurate physiological read and the cause are preserved.

**Status:** Active. Apply to all confound detection and annotation logic.

---

### 11. bcrypt pinned to 4.0.1

**Decision:** `bcrypt==4.0.1` is pinned in requirements. `passlib==1.7.4` is incompatible with `bcrypt 5.x`.

**Rationale:** Upgrading bcrypt breaks the passlib authentication layer. Passlib 1.7.4 is the last release and is not being maintained.

**Status:** Locked. Do not upgrade bcrypt.

**Do not revisit unless:** passlib is replaced entirely with a maintained alternative (e.g. `bcrypt` library used directly, or `argon2-cffi`).

---

### 12. JWT 7-day expiry

**Decision:** `ACCESS_TOKEN_EXPIRE_MINUTES=10080` (7 days).

**Rationale:** Personal/family app — friction of re-login on mobile is not acceptable for primary users. Security tradeoff is acceptable at this scale.

**Status:** Active. Revisit if multi-tenant commercial launch.

---

### 13. Hevy routine creation — XML block interception pattern

**Decision:** Claude includes a `<hevy_create_routine>` or `<hevy_create_workout>` XML block in its response, which the backend strips, acts on, and replaces with a confirmation message — invisible to the user.

**Rationale:** Keeps the AI interaction natural while allowing structured actions to be triggered from conversation. Avoids a separate "confirm and submit" UI flow.

**Status:** Active and fully working as of June 2026. See HEVY_PATTERN.md for full schema.

---

### 14. Hevy routine creation — exercise type field rules

**Decision:** Set payloads must only include metric fields that belong to the exercise type. Null fields must be omitted entirely, not sent as null. `index` field must be stripped from POST payloads. For routines containing custom exercise UUIDs, prefer the `create_workout` path — custom UUIDs do not resolve correctly via `create_routine`.

**Rationale:** Hevy rejects sets with unexpected field combinations even when those fields are null. `index` is returned in GET responses but rejected on POST. Custom exercise UUIDs confirmed not resolvable via `create_routine` — `create_workout` is the correct path for those cases. A workout record with a timestamp is valid training log data, not pollution.

**Status:** Locked. Enforced at the Pydantic model layer (`RoutineSetIn` model_validator) and in `HevyClient.create_routine()`.

**How you know:** Live workout pull from "Exercise format schema" workout confirmed field patterns per type. Routine creation confirmed working end-to-end after fix (June 2026, commits 70d0aca, 5a01ac8, b3c8dee).

**Do not revisit unless:** Hevy changes their API contract.

---

### 15. Frontend SPA routing — Railway static fallback

**Decision:** `frontend/railway.toml` configured with SPA catch-all so all unmatched routes serve `index.html`, allowing React Router to handle client-side navigation.

**Rationale:** Without this, direct navigation to `/login`, `/dashboard` etc. returns 404 because Railway serves static files and has no knowledge of React Router routes.

**Status:** Fixed June 2026 (commit 5a01ac8).

---

### 16. Verification required before any metric enters algorithm design

**Decision:** Before any data source metric enters algorithm design, record how you know it works. Confirmed test, verified search result, or official documentation. "The API has a field for it" is not sufficient.

**Rationale:** Multiple metrics were designed against before ground truth was checked — HRV, sleep stages, resting HR, respiratory rate via Samsung Health → Health Connect. A five-minute search would have found the Samsung community threads. This failure mode must be closed at the design phase, not the build phase.

**Status:** Standing principle. Applied to all future metric additions.

---

### 17. Polar aerobic data via AccessLink v4 Dynamic API — not v3, not Health Connect

**Decision:** Polar H10 aerobic sessions are pulled through the **Polar AccessLink v4 Dynamic API** (`auth.polar.com` OAuth, `GET /v4/data/training-sessions/list`), stored in `aerobic_sessions` (source=`polar_v4`). Health Connect is no longer the Polar transport. Historical backfill is a one-time ZIP-export import (`import_polar.py`, source=`polar_flow_export`).

**Rationale:** v3 AccessLink (`exercise-transactions`) only exposes sessions recorded *on a Polar device*. This user records H10 via the Polar Flow phone app — every session is tagged `product.modelName="Polar Flow app"` (proven from the export JSON), which v3 silently excludes (transactions return 204 even for post-registration sessions). Diagnostic proof: v3 `physical-information-transactions` returned 201 through the identical mechanism while `exercise-transactions` returned 204 — so token/code were correct; Polar simply had no device-recorded exercises queued. v4's schema separates `productReference` from `applicationReference` and its date-range endpoint returns app-recorded sessions. v4 `identifier.id` matches the ZIP `source_session_id` exactly, so v4 and ZIP dedup cleanly across sources.

**Implementation facts (hard-won, keep):**
- v4 tokens: 12h access + refresh_token; auto-refresh implemented. (v3 tokens were long-lived.)
- v4 needs NO user registration (v3 required `POST /v3/users`).
- Date params must be ISO datetime **without** timezone — trailing `Z` → 400.
- Query window capped at ~a quarter (108d → 400, 90d ok) — sync chunks into 90-day windows.
- v4 `training-sessions/list` returns summary only (HR avg/max, calories, duration, recovery, sport). It does **not** return `cardioLoad`, `muscleLoad`, or HR-zone distribution — those come only from the ZIP export. Current summary data is sufficient for workload implications.
- v4 session schema == ZIP session schema, so `import_polar._parse_session` is reused for both.
- `user_integrations.api_key_encrypted` widened varchar(512) → TEXT — v4 token payload exceeds 512 chars encrypted.

**Status:** Working in production. Sync is manual (button); a scheduled v4 sync is the agreed automation path (NOT scheduled ZIP download — Polar has no export API and download links expire).

**Do not revisit unless:** Polar exposes cardio_load/zones via a v4 endpoint (flagged follow-up — find the `features` syntax or per-session sub-resource), or the user starts recording on a Polar *watch* (which would also make v3-style data available).

---

### 18. Readiness algorithm: ACWR rejected — Banister fitness-fatigue model adopted

**Decision:** The readiness algorithm uses the Banister fitness-fatigue impulse-response model (Form = Fitness − Fatigue). ACWR (Acute:Chronic Workload Ratio) is explicitly rejected.

**Rationale:** ACWR has documented statistical limitations: mathematical coupling between numerator and denominator, sensitivity to arbitrary time-window boundaries, and no representation of physiological adaptation. The Banister model applies dual EWMAs to a daily training load signal with separate time constants, producing a Fitness term (long-term adaptation, τ ≈ 42 days) and a Fatigue term (short-term stress, τ ≈ 7 days). Form = Fitness − Fatigue represents readiness — positive Form means more adapted than fatigued.

**Architecture:**
- Daily Training Load = session RPE × duration for cardio + volume-load proxy for strength
- Fitness = EWMA(TL, τ ≈ 42 days)
- Fatigue = EWMA(TL, τ ≈ 7 days)
- Form = Fitness − Fatigue
- Form integrated with RMSSD baseline deviation, sleep architecture score, and RHR trend into composite readiness score

**Status:** Architecture decided. Not yet implemented. Composite score remains suppressed pending 7+ days of confirmed HRV readings (see Decision 8).

**Do not revisit unless:** Calibration data over ≥6 weeks shows consistent divergence between model-predicted Form and user-reported readiness — in which case time constants are the first tuning lever before reconsidering the model family.

---

### 19. exercise_sessions table retained as future ingestion surface; ORM model removed

**Decision:** The `exercise_sessions` DB table is kept (not dropped). The `ExerciseSession` SQLAlchemy model is removed from `models.py` because nothing currently writes to this table. All live aerobic data (Polar v4, ZIP import) lands in `aerobic_sessions`. `exercise_sessions` is reserved for future non-Polar sources (Garmin direct API, manual entry) where a simpler schema without cardio_load/HR-zone columns is sufficient. All four MCP tool queries that previously targeted `exercise_sessions` are re-pointed at `aerobic_sessions` with column remapping (`sport_name`, `stop_time`, `duration_minutes*60`, `hr_avg`, `hr_max`, `z1–z5_seconds` for HR zones).

**Rationale:** Dropping the table would require a migration and leaves no obvious home for future Garmin data. The simpler `exercise_sessions` schema (duration_seconds, avg_hr — no Polar-specific cardio_load or zone columns) is a better fit for devices that report only summary metrics. ORM model deleted because no writer exists; re-add when the first non-Polar ingestion path is implemented.

**Status:** Active. Table exists, empty, no ORM model.

**Do not revisit unless:** A second aerobic source (Garmin, manual) is ready to ingest — at that point evaluate whether to populate `exercise_sessions` or extend `aerobic_sessions` with a nullable source-type discriminator.

---

### 20. Health Connect sleep-stage enum confirmed (official StageType); backend ingestion constants are wrong

**Decision:** Samsung Health (`com.sec.android.app.shealth`) writes a full sleep-stage hypnogram to Health Connect using the **official `SleepSessionRecord.StageType` enum** — `AWAKE=1, LIGHT=4, DEEP=5, REM=6` (2/3/7 not emitted). The companion `deepSleepConfidence.js` constant `DEEP=5` is therefore correct. The backend ingestion constants in `routers/health_connect.py` (`SLEEP_STAGE_DEEP=4`, `REM=5`, `LIGHT=2`) are **wrong** and mislabel every HC-sourced night: stage 4 (LIGHT) is counted as deep, stage 5 (DEEP) is counted as REM, stage 6 (REM) is dropped entirely, and `light_sleep_minutes` is always 0 (stage 2 is never emitted). This corrupts `health_connect_syncs.deep/rem/light_sleep_minutes`, the HC `sleep_score` derived from them, and the `_section_health_connect` block in the AI system prompt. The **dashboard readiness summary is unaffected** because it reads sleep stages from the scraper path (`samsung_hrv_readings`), not HC — which is why the bug went unnoticed.

This **supersedes the "sleep stages" claim in Decision 5**: Samsung *does* write sleep stages (full hypnogram, 30-second resolution) to Health Connect. Decision 5 remains valid for HRV (RMSSD), resting HR, and respiratory rate.

**How you know:** On-device raw read 2026-06-22 via the companion `validateNight()` harness on SM-S921B (Galaxy S24). `distinctStageValues = [1,4,5,6]`; per-stage minutes identify stage 5 as the ~34-min deep block and stage 6 as the ~67-min REM block — an exact match to the in-app Samsung Health figures and the scraper row (`samsung_hrv_readings` 2026-06-22 = deep 34 / rem 67 / light 245 / awake 19). Cross-checked against `health_connect_syncs` (Railway Postgres, read-only): HC "deep" runs 55–250 min (light-magnitude, physiologically impossible as deep) and HC "light" is 0 every night — consistent only with the LIGHT↔DEEP swap above. Gate 2 also confirmed the deep slivers survive the HC write at 30s resolution (HC does not flatten the hypnogram), so the flagging approach is viable.

**Status:** Enum fact locked. Backend fix + historical backfill tracked in `OPEN_QUESTIONS.md` (Q1). `runDeepConfidence` in the companion app remains exposed but NOT wired into readiness/Banister pending Q2/Q3.

**Do not revisit unless:** Samsung changes the enum it writes to Health Connect (re-confirm via `validateNight()` on-device).

---

## Known open issues (as of June 2026)

| # | Issue | Location | Status |
|---|-------|----------|--------|
| 1 | Health Connect permission errors for record types 38, 35, 11, 37 | Companion app | Partially resolved via `adb pm grant`; in-app dialog incomplete |
| 2 | Garmin Connect (wife) not confirmed writing to Health Connect | Device | Verify by querying Railway Postgres for source IDs — not by browsing Health Connect app UI. (Polar no longer relevant here — moved to direct v4 API, see Decision 17.) |
| 10 | Polar cardio_load / HR-zone distribution not available via v4 list endpoint | `backend/connectors/polar.py` | Flagged follow-up. v4 list omits load/zones; ZIP export has them. Investigate `features` param syntax or per-session sub-resource. Current summary data sufficient for now. |
| 11 | Polar sport-ID → name map incomplete | `backend/import_polar.py` `SPORT_NAMES` | Low priority. e.g. id 55 shows "Fitness" where Polar Flow displays "Cross-trainer". |
| 12 | Polar v4 sync is manual (button) | `backend/routers/polar.py` | Scheduled nightly v4 sync agreed as automation path but not built. APScheduler in-backend preferred over external cron. |
| 3 | `create_routine` 400 error | `backend/routers/integrations.py` + `backend/connectors/hevy.py` | **Fixed June 2026** — RoutineSetIn model_validator enforces exercise-type field combos; index stripped from exercise and set payloads; rpe gated on reps-based types; null metric fields omitted (commits 70d0aca, 5a01ac8, b3c8dee) |
| 4 | Conversation history clears on browser refresh | Frontend / backend | No persistence built yet |
| 5 | SPA routing 404 on direct navigation | Frontend / Railway | **Fixed June 2026** — railway.toml SPA fallback added (commit 5a01ac8) |
| 6 | Session cards not clickable | Frontend | Open |
| 7 | Dual-panel scroll layout issue | Frontend | Open |
| 8 | Samsung Health package name filter incorrect | Companion app diagnostic | Use `com.sec.android.app.shealth` not `com.samsung.health` |
| 9 | Scraper canary mechanism not implemented | health-connect-app | Required before scraper is considered production-hardened |

---

## Things tried and abandoned / not yet attempted

- **Samsung Health → Health Connect for Ring HRV:** Confirmed not possible. Samsung does not write HRV, RHR, sleep stages, or respiratory rate to Health Connect. Closed.
- **Direct Polar API integration:** Not pursued. Polar Flow → Health Connect bridge is sufficient for current use case.
- **Direct Samsung Ring API:** Does not exist. No third-party API for Ring data.
- **Garmin Body Battery:** Explicitly closed — no API access available regardless of method.
- **Native Kotlin companion app:** Superseded by Expo for cross-platform reasons.
- **Terra unified wearable layer:** Evaluated June 2026. Third-party dependency + cost model doesn't justify itself at personal/family scale. Deferred unless scraper + SDK path proves unworkable.
