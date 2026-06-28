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

### 21. Adaptive Exposure Engine — capability-first Decision Support; standalone capability_state table

**Decision:** Built the Adaptive Exposure Engine (Decision Support module) from the v2 spec: a capability taxonomy (`engine/taxonomy.py`, versioned `v0`), a Fortify/Probe explore-exploit selector (`engine/selection.py`), an adaptation-loop response apply (`engine/adaptation.py`), a per-user fortification-target profile (§9) that replaces the hardcoded injury string in `context_builder.py`, surfacing into the chat system prompt, and an `/engine/*` API. Capability state ("map contents") lives in a **standalone `capability_state` table**, not in `health_events`.

**Rationale:** The spec ties capability-state to a `health_events` table that does not yet exist (still under design). Rather than block the engine on that schema, capability-state gets a dedicated table now (region × side × status untested/pass/deficient, source/confidence-tagged per the device-agnostic rule). It folds into `health_events` when that lands. The axis list is external-authority and versioned so Probe's coverage does not inherit the user's blind spots; the map self-builds one probe per session (clean attribution). Dosing references the **Banister Form** seam (Decision 18), never ACWR. Nothing gates on the suppressed readiness composite (Decision 8) — a low-readiness hint only re-ranks vehicles. No new wearable metric is introduced: capability state is self-reported through the education idiom (engine probes and surfaces; interpreting a formal screen stays the practitioner's line).

**Status:** Implemented and merged to master via PR #4 (2026-06-22). Migration `d8e1f2a3b4c5` (tables `capability_state`, `fortification_profiles`). Seed: `seed_engine.py` (Luke / back-resilience, §10). First instance not yet seeded against Railway.

**How you know:** Logic smoke-test passed end-to-end on a temp sqlite — probe-queue ranks the comfort-cluster blind spot (E-group) first, the adaptation loop drops exactly the revealed cell, a radicular sign removes right-side spinal-load regions from the queue, and the system prompt renders the fortification + probe sections with the hardcoded injury block suppressed. Migration `d8e1f2a3b4c5` applied and reverted cleanly in isolation; full app imports with all six `/engine` routes registered.

**Do not revisit unless:** `health_events` schema lands (migrate `capability_state` into it), or the four-window Banister load model is implemented (replace the dosing seam's named-windows annotation with real Form-based dosing).

---

### 22. Loop governance lives per-repo (committed CLAUDE.md), not in a parent directory

**Decision:** The Chat→code→Git loop's binding contract is carried by each repo's own committed `CLAUDE.md` (plus `FEEDBACK.md`, `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`). There is no `Projects/CLAUDE.md` enforcing the system across sub-projects. The portable *philosophy* (source-of-truth model, "Code is the only writer," the closeout ritual) belongs in a user-global `~/.claude/CLAUDE.md`; the *binding contract* stays repo-canonical and committed.

**Rationale:** `C:\Users\lukee\Projects` is not a git repo, so a CLAUDE.md placed there would be an orphan — uncommitted, absent from any clone, invisible in a PR, and silently effective only on this one machine (CLAUDE.md discovery walks up the tree). That is exactly the "project-only, not repo-canonical" anti-pattern the FEEDBACK.md correction removed. A parent file would also couple two independent repos (separate remotes `Easty11/health-app`, `Easty11/health-connect-app`) through local filesystem layout neither repo records. "Enforcement" in the blocking sense is hooks / pre-commit, which are inherently repo-local anyway.

**Status:** Locked. Global `~/.claude/CLAUDE.md` philosophy layer not yet authored.

**Do not revisit unless:** `Projects/` (or a dedicated workspace repo) is converted into a real monorepo — see Decision 23 — at which point a top-level CLAUDE.md becomes legitimately repo-canonical.

---

### 23. Not a monorepo — single-source the wire contract instead

**Decision:** `health-app` and `health-connect-app` stay as separate repos. Their only coupling — the `/health-connect/sync` payload plus the Health Connect sleep-stage enum — is single-sourced via the backend's OpenAPI spec rather than merged into a monorepo.

**Rationale:** The shared surface is one wire contract, not shared code. The repos have heterogeneous toolchains (FastAPI/Alembic/Railway vs Expo/Gradle/Kotlin), separate deploy targets, and independent histories/remotes; a merge would impose path-scoped CI, split deploy config, and a history migration for little gain. Single-sourcing the contract fixes the actual recurring failure (enum drift — see #20, #24) at roughly a tenth of a monorepo's disruption and stays reversible.

**Status:** Locked for now.

**Do not revisit unless:** the shared surface grows past the wire contract into shared *code* (validation logic, business rules, types), or the two repos require constant lockstep changes — then a monorepo with path-scoped CI/deploy earns the migration cost.

---

### 24. Backend OpenAPI spec is the contract source of truth; mobile vendors a generated client

**Decision:** The backend (`/openapi.json`) is the single source of truth for the `/health-connect/sync` contract. The sleep-stage enum is defined once as the backend `SleepStageType` IntEnum (full official StageType, 0–7) and published into the spec with `x-enum-varnames`; the mobile app vendors a generated copy (`src/contract/sleepStages.generated.js` via `npm run gen:contract`) instead of maintaining its own enum.

**Rationale:** The DEEP=4-vs-DEEP=5 drift (#20) happened because the name→value mapping was defined independently in both repos. Generating mobile's enum from the backend spec makes that drift structurally impossible — exactly one definition exists. `x-enum-varnames` is injected via an eager `app.openapi_schema` patch in `main.py` (the Pydantic `__get_pydantic_json_schema__` hook and the `app.openapi` override both failed to fire, likely due to the MCP app mounted at `/` plus schema caching). The full enum (0–7, not just 1/4/5/6) keeps the strict-enum field from 422-ing otherwise-valid records.

**Status:** Implemented. Backend Phase 0/0.5 live (commits `5ea5319`, `13860b9`); mobile Phase 1 generates and consumes the enum. Backend "intentionally flexible" dual-field acceptance (`bpm`/`beatsPerMinute`, `rmssd`/`heartRateVariabilityMillis`) not yet collapsed (Phase 2 pending).

**How you know:** Independently verified against the live spec — the vendored `sleepStages.generated.js` is an *exact* name→value match with `components.schemas.SleepStageType` (`x-enum-varnames` + `enum`), DEEP→5, and `deepSleepConfidence.js` imports it with no local enum remaining. Mobile sleep calc unchanged (DEEP was already 5 on that side).

**Do not revisit unless:** the contract grows to need full payload validation (adopt orval + zod — Phase 1b), or Phase 2 collapses the dual-field acceptance.

---

### 25. Repo-canonical source-of-truth model

**Decision:** The repo is the single source of truth for all volatile project state — decisions, open questions, roadmap, behavioural corrections, task pointers. Code (and the `@claude` GitHub Action) is the only writer; chat proposes but never commits; the commit is the only sync point. Volatile state is **never** saved into claude.ai project knowledge (kill-rule) — project knowledge holds stable orientation docs only.

**Rationale:** This is the foundational model the entire loop enforces, adopted to kill the two-master drift that occurred when decisions lived in claude.ai project knowledge and diverged from the repo. Recording it as a numbered decision (not only as CLAUDE.md prose) gives the model an explicit, supersedable entry in the decision history.

**Status:** Locked. Implemented across the loop scaffolding: CLAUDE.md "Shared loop rules", FEEDBACK.md (corrected from a project-only copy to repo-canonical, commit `f9bccef`), and the canonical stores.

**How you know:** CLAUDE.md "The loop (source-of-truth model)" and "Canonical stores" sections encode the rule; FEEDBACK.md was moved from a project-only copy to a committed repo file (`f9bccef`); the kill-rule (no volatile state in project knowledge) is stated in CLAUDE.md.

**Do not revisit unless:** the claude.ai connector gains repo write access, or a different store becomes authoritative.

---

### 26. Chat→repo handoff: paste now, `@claude` GitHub Action as the automated writer path

**Decision:** The chat→repo handoff (the pending-commit queue) has two carriers, both honouring "Code is the only writer": (a) human paste of the queue into a Code session, and (b) materialising the queue as a GitHub issue that the `@claude` Action consumes and commits. The Action is Code-equivalent; chat still never commits directly.

**Rationale:** The source-of-truth model (#25) forbids chat from writing to the repo (the claude.ai connector is read/attach only), so the pending-commit queue needs a writer-side carrier. Paste is the manual path; the `@claude` Action is the automated path for when chat output is filed as an issue. Both preserve the invariant that truth changes only at a commit authored by Code or the Action.

**Status:** Model locked; automated path **not yet wired** — `.github/` does not exist, so paste is the live transport today.

**How you know:** CLAUDE.md "The loop" names "Code — and the `@claude` GitHub Action — is the only writer" and the pending-commit-queue row names the GitHub-issue carrier. Verified `.github/` is absent in the tree (`find .github` → none), so the Action path is recorded as future work, not claimed as live.

**Do not revisit unless:** the `@claude` Action is wired (update status with the workflow path), or the claude.ai connector gains write access (which would void the "chat never commits" invariant).

---

### 27. Session rituals: `;cc` chat close-out + `/closeout` Code close-out

**Decision:** The loop's two close-out rituals are committed and bound to the CLAUDE.md "Session rituals" payload. `;cc` (espanso) emits the pending-commit queue from chat; `/closeout` (Claude Code command) reads the stores, reports the **real** commits made that session, reconciles the PENDING queue, regenerates the cold-resume handoff, and overwrites a single `closeout.md`. `/compact` is mid-session compression, never a close-out.

**Rationale:** The rituals are the trigger mechanism that keeps the loop running — chat proposes (`;cc` emits PENDING entries), Code disposes (`/closeout` reconciles and the commit lands truth). Spec-bound, committed ritual bodies stop the close-outs drifting from the payload definition. The guarded failure mode is health-connect-app's misfired `closeout.MD`, which claimed "docs only" while ~1000 lines sat uncommitted.

**Status:** Implemented — `.claude/commands/closeout.md` + `.espanso/cc.yml` committed (`11c82f1`). espanso snippet requires manual install into the user's match dir. Not yet exercised end-to-end (that is loop Step 5).

**How you know:** Both files committed and present; the `/closeout` body enumerates the five CLAUDE.md steps, and `.espanso/cc.yml`'s replace body matches the pending-commit-queue payload. Conformance verified by inspection against CLAUDE.md; a live run is still pending (Step 5).

**Do not revisit unless:** the CLAUDE.md "Session rituals" payload changes (update both bodies in lockstep), or the chat→Code transport changes (e.g. the `@claude` issue path of #26 goes live).

---

### 28. Banister load model is four-window; single-signal is Tier 0

**Decision:** The Banister fitness-fatigue engine (Decision 18) is computed per the four-window load taxonomy — Neuromuscular, Mechanical, Metabolic, Psychological — producing a Fitness/Fatigue/Form triplet per window, not a single global Form. Single-signal Banister (#18's one daily TL of RPE×duration + strength volume-load proxy) is **Tier 0** of this same engine — the graceful-degradation floor when only summary load is available — not a separate model. Routing: strength volume-load → Mechanical + Neuromuscular; HR/zone-derived load → Metabolic; sRPE / subjective-vs-objective divergence → Psychological. Form carries a low-confidence band until ~4–6 weeks of continuous load history (especially Fitness, τ≈42d); annotate, never suppress (Decision 10). Partially supersedes #18's architecture block (the single daily-TL formulation); #18's core (Banister adopted, ACWR rejected) stands. This entry is the first definition of the four-window taxonomy — no earlier decision establishes it.

**Rationale:** A single Form collapses the information that drives prescription (high neuromuscular + acceptable mechanical ≠ all-windows-elevated). One engine across all tiers preserves the Tier 0–3 graceful-degradation design. Resolves OPEN_QUESTIONS Q6 — strength volume is a named Mechanical/Neuromuscular input, not optional.

**Status:** Decided, not implemented. Engine still at #18 single-signal; deployed metric still interim ACWR (#8). The ACWR compute path is now tech-debt — retire when Banister Tier 0 lands. Gated on: per-window `load_metrics` at ingestion · Hevy strength ingestion (Q6) · Polar zone retrieval (#10) for Metabolic. The Form confidence-gate is part of this implementation. **Architecture block superseded by #32** (independent per-window τ pairs, no global fatigue term, recovery ordering, provenance-labelled τ); #28's taxonomy, routing, and Tier-0 graceful-degradation core stand.

**How you know:** Design decision, chat-settled 23 Jun 2026. No code asserts four-window yet — target architecture, not implemented state.

**Do not revisit unless:** ≥6 weeks calibration shows window separation adds no prescriptive value over single Form — then Tier 0 becomes the permanent model.

---

### 29. Morning Check-in: unified 0–4 subjective wellness schema

**Decision:** All subjective wellness items use a single 0–4 button-group with a hard floor of 0, dual-anchor labels, and number/descriptor agreement (0 = literal absence). Items: Sleep quality (0 Poor→4 Great), Fatigue (0 Fresh→4 Exhausted — replaces the prior "feel right now" item), Stress (0 None→4 Very high), Motivation (0 None→4 High), Shoulder soreness (0 None→4 Very sore), Hamstring soreness (0 None→4 Very sore). Polarity is **not** normalised in the UI — the scoring layer owns inversion; dual anchors make per-item direction explicit. The conditional alcohol block is retained: "Drank last night?" toggle → units (stepper 0–15, default 0 — a count, not a slider) → last-drink time-select. Soreness items are hardcoded for now. Full field spec: `docs/checkin-schema.md`.

**Rationale:** A 0-floor with agreeing number+descriptor removes the ambiguity of the prior mixed scales; dual anchors keep per-item direction explicit without forcing UI-side polarity normalisation (Decision 10 logic applied to UX — annotate direction, let scoring invert). Collapsing "feel right now" into Fatigue removes a redundant item. Stepper (not slider) for alcohol because units are a discrete count.

**Status:** Decided, not implemented. Schema spec lives in `docs/checkin-schema.md`; the UI build is a backlog code item. Soreness items hardcoded pending injury-list / movement-pattern indexing (FEEDBACK 2.6).

**How you know:** Design decision, chat-settled 23 Jun 2026. No check-in UI asserts this schema yet — target spec, not implemented state.

**Do not revisit unless:** the scoring layer's polarity-inversion contract changes, or soreness items move to injury-list-driven (FEEDBACK 2.6) — then update `docs/checkin-schema.md` in lockstep.

---

### 30. Global `~/.claude/CLAUDE.md` authored; loop work is single-repo-scoped; `;raw` protocol

**Decision:** The #22-reserved global philosophy layer (`~/.claude/CLAUDE.md`) is authored. It carries two portable rules binding in every Claude Code session regardless of repo: (a) loop work (commits, canonical-store edits, `/closeout`) requires a single-repo-rooted session, verified by `pwd` — multi-repo sessions are reserved for the shared wire-contract surface (#23/#24); (b) the `;raw` protocol — chat emits `;raw <command>`, Code pastes its output verbatim; canonical/action claims rest on raw bytes, not summaries.

**Rationale:** Sessions launched outside a single repo (parent dir, dead-zone sibling, multi-repo workspace) load no single repo's binding contract, silently breaking the loop (#25/#26/#27) — the cause of the `/closeout` "unknown command" failure and a contributor to canonical drift. #22 reserved `~/.claude/CLAUDE.md` for this but left it unauthored. `pwd`-verification is mandatory because the desktop picker is unreliable — observed directly (selected "Claude Code", session opened in hevy-client), matching reported desktop bugs. `;raw` codifies evidence discipline after repeated paraphrase-of-available-bytes failures touched canonical (#10/#11).

**Status:** Global layer authored. Enforcement is advisory (objects and redirects; does not hard-block a mis-scoped commit).

**How you know:** Load-verified — sentinel test 2026-06-24, a unique codeword placed only in `~/.claude/CLAUDE.md` returned immediately by a fresh hevy-client session with no file read. Both rules are present verbatim in the global layer.

**Do not revisit unless:** the desktop app gains a reliable default-working-directory setting (picker becomes trustworthy, `pwd`-verify relaxes), or `~/.claude/CLAUDE.md` stops auto-loading (re-run the sentinel).

---

### 31. Samsung HRV scraper one-day scalar misdate — backend data reconciled (24–26 Jun)

**Decision:** The pre-fix accessibility scraper's three numeric tile reads (`hrv_ms`, `sleep_hr_bpm`, `respiratory_rate`) read the **prior night's** tiles and welded them onto the **current** night's correct sleep architecture — a one-day shift confined to those three scalar fields. In `samsung_hrv_readings` (Railway Postgres) this corrupted the 24–26 Jun window. Reconciled against Samsung's own retained history:

- **06-25 (id 28):** three scalars corrected `83 / 57 / 13.3` → **`62 / 65 / 13.9`** (the 25th's genuine reading). The row's architecture, bed/wake times (22:12–05:57), SpO2 (96) and stage percentages were already an exact match to Samsung's 25 Jun record — so only the three scalars were rewritten; no relabel.
- **06-24:** a full row was **inserted** (was a missed sync, not a corruption): `hrv 83 / hr 57 / rr 13.3`, SpO2 98, eff 92, deep 24 / rem 89 / light 223 / awake 26, total 362 / actual 336, 23:00–05:02.
- **06-23 (id 27)** and **06-26 (id 33)** were already correct (06-26 = the Phase-1 live S5 read) — untouched.

The `62 / 65 / 13.9` triple that Phase 1 named "the phantom" is **not garbage — it is the 25th's real Samsung measurement**, which surfaced misdated during the scraper bug. It is therefore **restored to the 25th, not purged**. This does not contradict the companion-repo scraper fix (`health-connect-app` DECISIONS_LOG #16, `findByIdValidBounds`): #16 fixed the read mechanism (Phase 1); this entry is the backend data cleanup it authorised (Phase 2). The diagnostic test-POST litter (ids 26, 29–32) had already been deleted from production before this session — no DELETE was needed.

**Rationale:** Verify-before-write. Each night's correct values were derived from Samsung's retained history (the in-app HRV/HR trend charts plus the per-night sleep-detail screens for 23–26 Jun), **not** from the observed "phantom = prior day" pattern — re-deriving from that pattern would have re-committed the same stacked-inference error the defect is made of. The fix was both localised and disambiguated by evidence: on id 28, all non-scalar fields matched Samsung's 25th *exactly* while the three scalars matched the 24th, proving the defect is exactly three fields wide and that id 28 is genuinely the 25th's row (Option A, not a whole-row relabel). Thematically adjacent to Q4 (HC vs scraper bed-/wake-date attribution) but a distinct mechanism: a scalar-tile staleness, not a session-date convention mismatch.

**Status:** Reconciled and committed to production Postgres (single transaction, row-count guarded: UPDATE=1, INSERT=1). Companion-side recurrence prevention is already live via the Phase-1 fix build. One field left NULL-then-filled by sign-off: 06-24 `sleep_efficiency_pct` = 92 (supplied from Samsung Health; the scraper's stored efficiency formula does not reproduce from actual/total, so it was not fabricated).

**How you know:** Post-write readback of `samsung_hrv_readings` for 2026-06-23→26 (Railway Postgres, read-only) returns all four nights matching Samsung's retained history on HRV/HR/RR and sleep architecture: 06-23 `80/61/13.2`, 06-24 `83/57/13.3` (SpO2 98), 06-25 `62/65/13.9` (SpO2 96, deep 5/rem 66/light 312/awake 49), 06-26 `42/72/14.7`. 06-26 independently cross-checks against the Phase-1 live S5 device walk (HRV 42 / HR 72 / RR 14.7).

**Do not revisit unless:** a further back-window emerges where the pre-fix scraper POSTed (pre-06-23), in which case apply the same Samsung-derived reconciliation; or Samsung's retained history is later found to disagree with these four nights (it is the source of truth here).

---

### 32. Four-window Banister implementation canon — independent per-window τ pairs; recovery ordering; provenance-labelled

**Decision:** The four-window Banister engine (Decision 28) is implemented as **four independent Fitness/Fatigue channels, each with its own τ pair** — there is **no global/aggregate fatigue term layered beneath the windows**. This supersedes Decision 28's architecture block (the Fitness/Fatigue/Form-per-window sketch); #28's core — the four-window taxonomy, Tier 0–3 graceful degradation, and load routing — stands.

**Recovery ordering (the substantive correction — no prior decision states it):** **Mechanical** (structural tissue damage) is the **slowest-recovering** window. **Neuromuscular** = CNS / velocity / rate-of-force readiness, **fast-recovering**. The windows are mutually exclusive: structural damage → Mechanical; velocity/recruitment → Neuromuscular. The intuitive "neuromuscular is slowest" is a **CMJ measurement artifact** — countermovement-jump *height* stays suppressed for days because it is contaminated by muscle damage; probed instead by velocity / RFD / power, the CNS signal recovers in minutes-to-hours. Provenance: the ordering is literature-supported (EIMD force deficits persist 24–72h+ vs CNS fatigue resolving minutes-to-hours).

**τ, provenance-labelled:**
- Fitness (global adaptation) **≈ 42 d** — literature-anchored (**SOURCED**).
- Mechanical fatigue τ — set within the **7–15 d** band the classic global fatigue τ occupies (that band *is* the muscle-damage timescale). **Default 10 d; 8 d retained as acceptable floor.** Provenance: literature-anchored via that identification (**SOURCED [Likely]**).
- Neuromuscular fatigue τ **≈ 6 d** — **REASONED PRIOR** (ordering literature-supported; magnitude is for Tier-3 validation).
- Metabolic fatigue τ **≈ 4 d** — **REASONED PRIOR**, same status.

**Measurement rule:** the Neuromuscular window **MUST** be fed by velocity / RFD / power, **never raw CMJ jump height** — otherwise it re-absorbs mechanical damage and the window separation collapses.

**Data-maturity gate:** Form is low-confidence until ~4–6 weeks of continuous load fills the chronic window (especially Fitness, τ≈42d) — flag low-confidence and annotate, **do NOT suppress** (Decision 10).

**Measure type:** passive priors run Tiers 0–2 from day one; per-athlete κ/λ calibration is required **only** at instrumented Tier 3.

**Status:** Decided, not implemented. No Banister/four-window load code exists yet — confirmed this session: the only load computation is `get_training_load()` (ACWR) in `backend/mcp_server.py`. This entry is the spec the engine is built to, not a fix to existing code. The no-global-term clause is therefore preventive — it ensures the per-window-τ-shorter-than-global-τ inconsistency is never written in the first place.

**How you know:** Design decision, chat-settled 26 Jun 2026, grounded against verified repo state (DECISIONS_LOG max #31 at decision time; `backend/engine/` is the Adaptive Exposure Engine #21, which only names the windows for capability routing and computes no Fitness/Fatigue). Architecture check this session confirmed no global fatigue term exists to contradict — there is no Banister code at all.

**Do not revisit unless:** Tier-3 calibration shows a per-window τ (the Neuromuscular ≈6d / Metabolic ≈4d REASONED PRIORs, or the 10 d Mechanical default) diverges from measured recovery — τ is the first tuning lever (per #18) before reconsidering the four-window split (#28's own revisit clause governs the split itself).

---

### 33. ΔLoad spike detector is a required primitive — the surviving function of ACWR

**Decision:** ΔLoad — **per-window acute load-spike detection**, an injury-risk signal — is captured as a **required primitive to build**, the **surviving function of ACWR**. When ACWR retires on Banister Tier 0 (#28), ΔLoad must **not** retire with it. Banister Form is a *readiness* signal, not a *spike* signal; the two are distinct and ΔLoad has no home in Form.

**Rationale:** The step-6 check this session confirmed ΔLoad is **not homed anywhere** — the only acute-spike signal in the codebase is ACWR's acute/chronic bands in `get_training_load()` (`backend/mcp_server.py`), which retire with ACWR as tech-debt (#28). Acute spike (injury risk) and Form (adaptation/readiness) are orthogonal; collapsing spike detection into Form would lose the injury-risk channel. ΔLoad is therefore recorded as a primitive the Banister engine must carry forward, per window — not a casualty of ACWR retirement.

**Status:** Decided, not implemented. No ΔLoad primitive exists yet; ACWR (its interim stand-in) is live in `get_training_load()`.

**How you know:** Architecture check 26 Jun 2026 — grep of the readiness/engine path found no per-window spike detector; the sole acute/chronic computation is the ACWR function #28 flags as tech-debt.

**Do not revisit unless:** ΔLoad is implemented (update status with its per-window home), or evidence shows acute spike adds no injury-risk signal beyond Banister Form — then it retires with ACWR after all.

---

### 34. Decision 31's companion-repo causal citation is withdrawn — the data reconciliation stands

**Decision:** The cross-repo citation embedded in Decision 31 — that the backend reconciliation was authorised by a companion-side scraper fix recorded as `health-connect-app` DECISIONS_LOG **#16** (`findByIdValidBounds`) — is **withdrawn as fabricated**. Both the entry number and the identifier are phantom: no `#16` and no `findByIdValidBounds` exist in any `health-connect-app` reference. Decision 31 framed itself as "Phase 2, the backend cleanup that #16's Phase-1 read fix authorised"; that Phase-1↔Phase-2 lineage rests on a citation to a record that does not exist, so the lineage claim is void. **Everything else in #31 stands** — the 24–26 Jun `samsung_hrv_readings` reconciliation, its row-count-guarded single transaction (UPDATE=1, INSERT=1), and its Samsung-history-derived values are unaffected by this withdrawal, because that work was verified by post-write Postgres readback (#31 "How you know"), not by the companion-repo citation. This supersedes **only** the companion-repo causal claim in #31's body (the parenthetical at "does not contradict the companion-repo scraper fix… #16… findByIdValidBounds"); #31's data decision, status, and readback artifact are untouched.

**Rationale:** A *How you know*-bearing entry must not carry, even as supporting colour, a cross-repo citation that cannot be verified — that is exactly the stacked-inference failure mode #31 itself was written to correct, reappearing one level up as a fabricated provenance link. The loop corrects locked entries by superseding, never by editing: #31's text is append-only canon and the fabrication is part of the history that the supersede records. The correction is deliberately narrow — withdrawing a phantom citation must not cast doubt on the independently-verified Postgres write it was wrongly attached to, or the cure would destroy more truth than the defect.

**Status:** Governance-only. No code or data change — the production `samsung_hrv_readings` rows reconciled under #31 remain correct and are not retouched. This entry rewrites the provenance record, not the database.

**How you know:** The companion repo (`health-connect-app`) is not in this tree, so the cited `#16` / `findByIdValidBounds` cannot be confirmed from here; absent any verifiable companion-side artifact, an unverifiable citation in a canon entry is withdrawn rather than left standing (verify-before-write, applied to provenance). #31's surviving claims keep their original artifact: post-write read-only readback of `samsung_hrv_readings` for 2026-06-23→26 against Railway Postgres, cross-checked to Samsung's retained history and the Phase-1 live S5 device walk (06-26 HRV 42 / HR 72 / RR 14.7).

**Do not revisit unless:** a genuine `health-connect-app` decision is later found (or written) that actually records the companion-side scraper read fix — in which case cite it by its real number here, restoring the Phase-1↔Phase-2 lineage on a verifiable basis; or the #31 reconciliation is itself shown wrong on its own readback evidence (a separate matter from this citation withdrawal).

---

### 35. HC ingest selects one authoritative writer per data category (TARGET architecture; backend enforcement blocked)

**Decision (TARGET architecture):** HC ingest selects a **single authoritative source app per data category**, keyed on writer identity (`dataOrigin.packageName`), before any aggregation. Priority read from HC's `health_data_category_priority_table` (the user's stated preference), with documented overrides where stored priority contradicts reality. Non-authoritative writers dropped at ingest.

Authoritative source per category (28 Jun 2026 export):

| Category | Ingest from | Drop | Note |
|----------|-------------|------|------|
| Sleep (session + stages) | `shealth` | wiscale2, cbti, (healthsync removed) | Samsung writes full hypnogram |
| Heart rate | `shealth` | polar, wiscale2 | |
| SpO2 | `shealth` | wiscale2 | |
| Steps | `shealth` | others | |
| Weight | **`wiscale2`** | shealth, hevy | Override: shealth wrote 4d vs Withings 285d |
| Resting HR | `fitness` / `polar` | — | Samsung writes **zero** RHR; cross-check only — derived nadir stays primary |
| Strength | `hevy` | — | |
| VO2max | `wiscale2` / `polar` | — | Sparse; only writers |
| **Exercise session** | **type-route — exception** | — | Multi-modality, NOT source-filtered |

**Exception — `exercise_session` is type-routed, not source-filtered.** Five apps write distinct modalities (Hevy=strength, Polar=aerobic, Samsung=watch). Route by `exercise_type` → preferred source per modality (B-rule). Time-overlap enrichment (C-rule) deferred. Sits above the table split that governs the landing table.

**Polar HC data dropped.** Polar writes session-*summary* to HC, but the Metabolic window requires **per-second R-R / HR-zone** data HC does not carry — available only via AccessLink v4 / ZIP path. HC-Polar is redundant summary. Does not reopen the v4 zone-retrieval gap.

**Rationale:** 28 Jun HC export proved duplication is **multi-writer, not multi-record**: 6 apps, 13–58% inflation by category. Duplicates carry **distinct `dedupe_hash` per app** (286/286 sleep dup-groups span 2+ apps, 0 share a hash) — `dedupe_hash`/GROUP BY cannot collapse them; only source-priority can. This is the concrete enforcement of the **CLAUDE.md device-agnostic schema standing rule** (every event carries source + confidence; normalisation precedes the algorithm/AI layer).

**Health Sync removed (28 Jun 2026).** `nl.appyhapps.healthsync` uninstalled, not filtered. Sole writer for StepsCadence (58d), dominant for active_calories (97/130d), ambient distance (35d) — none load-bearing. Cuts one of three sleep-writers; **Withings (`wiscale2`) remains an independent duplicate writer** for sleep (160d) and SpO2 (102d), so source-priority filtering is **still required** once enforceable — removal did not solve duplication.

**Watch-item:** `active_calories` goes stale/null going forward. Confirm nothing reads it (grep) before trusting. Confirm next sync still shows Samsung writing sleep/HR/SpO2 natively.

**Also at ingest (immediately buildable, backend):**
- **Pre-2020 timestamp reject at record level (counted/logged).** Real gap: epoch-zero `startTime` + valid `endTime` corrupts computed sleep duration. Reject record where `startTime` < 2020-01-01.
- **Day-aggregation over the frozen night session set, not the single longest session** (coverage fix — see Status).

**Status:**
- **F1 (source-priority filter): TARGET architecture — backend enforcement BLOCKED.** The `/health-connect/sync` payload carries **no writer identity** (fork gate verified ABSENT, 28 Jun). This entry ratifies the target; enforcement awaits a wire-contract change (HCA forwards `dataOrigin`, or filters read-side). Cross-repo, separate session.
- **F2 (timestamp reject): buildable now, health-app.**
- **F3a (frozen-session-set day aggregation): buildable now, health-app — CONDITIONAL.** `_aggregate_day` currently takes the single longest session, dropping naps → sleep coverage **under-count**. Fix = sum duration + stage-minutes over the night session set. *Precondition:* the set reaching `_aggregate_day` must already be single-source — else summing re-introduces multi-app duplication (the inflation F1 was to kill, which is blocked). VERIFY before building. Flags a `sleep_duration_minutes` **semantic change (366→462)**; audit downstream readers.
- **F3b (119% efficiency arithmetic): NOT in this file** — lives in the HCA scraper; carries with Q2.

**Do not revisit unless:** a new app legitimately becomes the better source for a category (update override table, not rule); the C-rule is built (exercise graduates to merge); or the wire-contract change lands (then F1 backend enforcement unblocks).

**How you know:** 28 Jun 2026 HC SQLite export (`health_connect_export.db`, 78 tables). Writer inventory, inflation, per-app `dedupe_hash` distinctness, Samsung-writes-zero-HRV/RHR/RespRate, and the 17,653 Samsung sleep-stage rows all computed directly from it. Fork gate (payload writer-identity ABSENT) verified against the live sync schema (`backend/routers/health_connect.py`, this session).

**Carry to HCA (separate ratify, health-connect-app):**
- **Q2 `validateNight()`** = cross-app **source** dedup, not time-overlap dedup.
- **F3b** — the 119% efficiency arithmetic is the HCA scraper computation.
- **Wire-contract** — writer identity (`dataOrigin.packageName`) must survive HCA→backend for any backend F1 enforcement.

---

### 36. Source-priority enforcement is backend (F1); HCA forwards writer identity
**Decision:** Source-priority deduplication (#35 F1) is enforced backend-side, not on-device. The backend is the only layer where all ingestion paths converge — HC sync, the Samsung scraper (`/samsung-hrv/sync`), Polar AccessLink v4 (direct, never transits HCA, #17), and Hevy-direct — so cross-source dedup can only run there. HCA is reduced to a faithful relay: forward `dataOrigin.packageName` (plus an HC `health_data_category_priority_table` snapshot as policy input) in the `/health-connect/sync` payload; it performs no source arbitration. `validateNight()` retains quality validation (#20 enum harness, F3b efficiency catch) but loses source dedup. Override policy (e.g. weight→`wiscale2`) lives backend, mutable without an APK rebuild. Resolves #35's open F1 fork and supersedes its "or filters read-side" horn as a false fork — both horns require writer identity in the payload; backend wins once identity is present.
**Rationale:** HCA sees only Health Connect and structurally cannot reconcile against Polar v4 or the scraper, which never reach it (#35 already drops HC-Polar for v4-direct — a cross-path call HCA can't make). Two arbiters reintroduce the #20/#24 two-master drift the loop exists to kill. The override table is offline-derived from the one-time HC export, not computed per-night, so the device needs no live cross-night visibility at runtime. Backend policy mutates by deploy; device policy by app rebuild + redistribution. The CLAUDE.md device-agnostic rule already places normalisation before the algorithm/AI layer — backend.
**Status:** Architecture decided (chat-settled 29 Jun 2026). Backend enabler — per-record writer-identity capture in `/health-connect/sync` — built this session in `health-app` (optional/nullable field + migration + OpenAPI publish). The F1 filter itself remains gated on HCA forwarding the field (separate backend session); HCA forwarding is a separate `health-connect-app` session. Keystone reframed: the wire-contract change (identity in the payload), not on-device `validateNight()` dedup.
**How you know:** Chat resolution 29 Jun 2026, grounded on #35's own fork statement and the verified-ABSENT payload writer-identity gate (#35, 28 Jun). Polar-v4-never-transits-HCA confirmed against #17.
**Do not revisit unless:** a thin on-device pre-filter is later justified by payload size at scale (not in evidence at personal/family scale), or the ingestion topology changes such that a different layer sees all sources.

### 37. Per-record writer identity is captured in a dedicated staging table, populated pre-aggregation
**Decision:** The #36 backend enabler stores writer identity in a new per-record table `health_connect_record_sources` (one row per inbound HC record: `user_id`, `record_type`, `record_start`, nullable `source_package`, `synced_at`), written by `_capture_record_sources()` in `/health-connect/sync` BEFORE `_aggregate_day` runs. The existing `health_connect_syncs` table — one aggregated row per `(user, date)` — is unchanged; no column was added to it. Inbound record models gain an optional `dataOrigin.packageName` (raw HC shape) plus a flat `sourcePackage` mapped alias, per the #24 dual-field house pattern, via a shared `WriterIdentity` mixin. `source_package` is nullable end-to-end (current HCA builds send no `dataOrigin`; a required field would 422 every live sync). Re-syncs are idempotent via `uq_hc_record_source (user_id, record_type, record_start)` — a seen record's source is refreshed, not duplicated.
**Rationale:** `health_connect_syncs` collapses a night to a single daily row (longest-session selector, median HR, mean HRV), but a night spans multiple writers (#35 — 286 sleep dup-groups span 2+ apps). A column on the aggregated row would attach identity to the post-collapse winner and destroy exactly the multi-writer signal F1 needs. So capture must precede aggregation and persist at record granularity. A dedicated typed table (vs a JSON blob) keeps the signal queryable for the F1 dedup pass. The natural-key upsert is dialect-agnostic (SQLite local, Postgres prod) — no `ON CONFLICT`, one read + in-memory merge, bounded at personal/family scale.
**Status:** Built this session in `health-app` on `feat/sync-writer-identity` — model, capture function, Alembic migration `c9b8a7d6e5f4` (up→down→up verified clean in isolation, #21 bar), OpenAPI publish confirmed, round-trip (with-field stored / without-field null, both 200) and idempotency verified. The F1 dedup pass that consumes the table is a separate backend session, gated on HCA actually forwarding the field.
**How you know:** Step-gated verification this session: ingest read confirmed Case (b) (aggregates immediately; writer identity ABSENT — grep zero matches); migration up→down→up clean on isolated SQLite; `dataOrigin`/`sourcePackage` present in `/openapi.json`; TestClient round-trip stored `com.sec.android.app.shealth` (nested) and `com.withings.wiscale2` (flat alias) per-record, null for the no-identity POST, both 200; re-POST `sources_captured: 0`, row count flat.
**Do not revisit unless:** evidence shows truly-simultaneous same-`(type, timestamp)` writes from two apps (the natural key collapses them — include `source_package` in the key then); or staging-table volume becomes a concern at scale (heart_rate is per-sample); or the F1 pass needs a richer key (e.g. record end-time or a stable HC uid) than `(type, start)`.

---

## Known open issues (as of June 2026)

| # | Issue | Location | Status |
|---|-------|----------|--------|
| 1 | Health Connect permission errors for record types 38, 35, 11, 37 | Companion app | Partially resolved via `adb pm grant`; in-app dialog incomplete |
| 2 | Garmin Connect (wife) not confirmed writing to Health Connect | Device | Verify by querying Railway Postgres for source IDs — not by browsing Health Connect app UI. (Polar no longer relevant here — moved to direct v4 API, see Decision 17.) |
| 10 | Polar cardio_load / HR-zone distribution not available via v4 list endpoint | `backend/connectors/polar.py` | Flagged follow-up. v4 list omits load/zones; ZIP export has them. Investigate `features` param syntax or per-session sub-resource. **Elevated June 2026:** zones now **required** for the Metabolic window (Decision 28), no longer "sufficient for now". Absorbs D2 — the Jun-10 session on the retired ZIP/Flow path carries zones; v4 sessions don't, so the gap is real until v4 zone retrieval lands. |
| 11 | Polar sport-ID → name map incomplete | `backend/import_polar.py` `SPORT_NAMES` | Low priority. e.g. id 55 shows "Fitness" where Polar Flow displays "Cross-trainer". |
| 12 | Polar v4 sync is manual (button) | `backend/routers/polar.py` | Scheduled nightly v4 sync agreed as automation path but not built. APScheduler in-backend preferred over external cron. |
| 3 | `create_routine` 400 error | `backend/routers/integrations.py` + `backend/connectors/hevy.py` | **Fixed June 2026** — RoutineSetIn model_validator enforces exercise-type field combos; index stripped from exercise and set payloads; rpe gated on reps-based types; null metric fields omitted (commits 70d0aca, 5a01ac8, b3c8dee) |
| 4 | Conversation history clears on browser refresh | Frontend / backend | No persistence built yet |
| 5 | SPA routing 404 on direct navigation | Frontend / Railway | **Fixed June 2026** — railway.toml SPA fallback added (commit 5a01ac8) |
| 6 | Session cards not clickable | Frontend | Open |
| 7 | Dual-panel scroll layout issue | Frontend | Open |
| 8 | Samsung Health package name filter incorrect | Companion app diagnostic | Use `com.sec.android.app.shealth` not `com.samsung.health` |
| 9 | Scraper canary mechanism not implemented | health-connect-app | Required before scraper is considered production-hardened |
| 13 | "Training Data → See all" control is dead (no destination/handler) | Frontend | Open — inspect the element first (div/span ⇒ missing handler; empty Link/anchor ⇒ no destination), then wire it. |

---

## Things tried and abandoned / not yet attempted

- **Samsung Health → Health Connect for Ring HRV:** Confirmed not possible. Samsung does not write HRV, RHR, sleep stages, or respiratory rate to Health Connect. Closed.
- **Direct Polar API integration:** Not pursued. Polar Flow → Health Connect bridge is sufficient for current use case.
- **Direct Samsung Ring API:** Does not exist. No third-party API for Ring data.
- **Garmin Body Battery:** Explicitly closed — no API access available regardless of method.
- **Native Kotlin companion app:** Superseded by Expo for cross-platform reasons.
- **Terra unified wearable layer:** Evaluated June 2026. Third-party dependency + cost model doesn't justify itself at personal/family scale. Deferred unless scraper + SDK path proves unworkable.
