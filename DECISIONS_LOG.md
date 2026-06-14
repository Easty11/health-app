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

**Decision:** Polar H10 data is captured via Polar Flow → Health Connect bridge. Only aerobic session data is captured. No resting HRV is attempted from Polar. H10 is the re-validation instrument for Ring HRV coherence — not a correction factor source.

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

**Status:** Active. Immediate next action: live SDK read with a known-populated metric as positive control + HRV query. Record result as a "how you know" artifact.

**Do not revisit unless:** Samsung removes developer mode access.

---

### 8. Composite readiness score formally suppressed until HRV data path confirmed

**Decision:** The composite readiness score must not be displayed until a confirmed RMSSD data path exists and has produced at least 7 days of readings.

**Rationale:** RMSSD is 30% of the readiness score and the primary recovery gate. Without it the score is not physiologically meaningful. Displaying a partial score is misleading.

**In the interim:** Surface training load (Hevy ACWR), sleep duration, and subjective check-in as separate indicators — not aggregated into a composite score.

**Status:** Active constraint until HRV path confirmed end-to-end.

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

## Known open issues (as of June 2026)

| # | Issue | Location | Status |
|---|-------|----------|--------|
| 1 | Health Connect permission errors for record types 38, 35, 11, 37 | Companion app | Partially resolved via `adb pm grant`; in-app dialog incomplete |
| 2 | Polar Flow / Garmin Connect not confirmed writing to Health Connect | Device | Verify by querying Railway Postgres for source IDs — not by browsing Health Connect app UI |
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
