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

### 38. Close-out body written to file, not echoed to stdout

**Decision:** `/closeout` writes its full body verbatim to `closeout.md` (the sole sink for the body) and prints **only a terse pointer** to stdout — the `closeout.md` path, the current branch, and the single clearest next action. The prior convention of dumping the close-out body to screen for on-the-fly copy-back is retired; copy-back, when needed, comes from terminal scrollback (expand the write line). Verbatim file content — no Code paraphrase or summary of close-out content — is the replacement guarantee. **Scope is narrow:** no global "echo every file write to stdout" rule existed to retire (S1 grep of project `CLAUDE.md` and `~/.claude/CLAUDE.md` found none); the change is local to `.claude/commands/closeout.md` step 6.

**Named exception — governance-store emission survives.** Step 8's emission of touched governance stores (full current post-commit text, fenced and per-file-labelled `project-copy replacement: <filename>`, curated to only the stores that changed this session) remains the one thing besides the pointer that reaches stdout. It is the pre-merge copy-back bridge for the **branch-blind** claude.ai connector (master-only; cannot read a feature branch), and it is a *packaged, curated block* — not a raw body dump — so terminal scrollback (scattered Edit diffs) is not an equivalent substitute. The CLAUDE.md SHARED-block ritual step 6 and FEEDBACK §2.12 item 2 are therefore **untouched**.

**Rationale:** The print-the-body-to-screen convention solved a non-problem — scrollback already delivers copy-back without polluting the main screen. The real failure it over-corrected was Code *summarising* file content instead of emitting it verbatim; that is addressed directly by requiring a verbatim write to the file, not by echoing every write. Keeping the governance-store emission preserves the clean wholesale-replace block FEEDBACK 2.12 was built to provide.

**Status:** Active. Command-local to health-app (`.claude/commands/closeout.md`). The identical body-echo retirement is owed to `health-connect-app`'s `/closeout` in a separate single-repo session — a **command-only** mirror (the SHARED CLAUDE.md block is unchanged under this narrow scope, so no shared-rule propagation is required). This entry is the **junior** of the two unmerged branches appending `DECISIONS_LOG.md` (`feat/sync-writer-identity` reserves #36–#37); it yields on number — when it merges second it cannot `--ff-only`, so this single entry is rebased and renumbered then; #36–#37 are fixed and untouched.

**How you know:** `.claude/commands/closeout.md` step 6 now routes the body to the file with pointer-only stdout, and step 8 is annotated as the named exception — both committed this session (command edit `7441196`). The "no global rule" finding is from an S1 grep across `CLAUDE.md`, `~/.claude/CLAUDE.md`, `.claude/commands/`, and the governance stores: the only carrier of stdout emission is the closeout-local step 8 / ritual step 6 / FEEDBACK §2.12, all governance-store-scoped — none "every file write."

**Do not revisit unless:** terminal scrollback copy-back proves unreliable; close-out content needs a channel other than the file to reach chat; or the governance-store exception is itself later retired (then update step 8 + CLAUDE.md SHARED ritual step 6 + FEEDBACK §2.12 in lockstep and mirror to HCA).

---

### 39. Close-out governance-store emission retired — #38's named exception reversed

**Decision:** The **named exception** in Decision 38 — step 8's emission of each touched governance store's full current text to stdout for wholesale project-copy replacement — is **retired**. `/closeout` stdout is now **pointer-only, with no exception**: the `closeout.md` path, current branch, single clearest next action, and the **filenames** of governance stores changed this session (names only, never their contents). Pre-merge copy-back is done by `cat`/opening the named store file on disk and replacing the project copy wholesale from it. **#38's file/pointer core stands** (body written verbatim to `closeout.md`; stdout reduced to a terse pointer); this entry supersedes **only** #38's named-exception clause. Propagated in lockstep to `.claude/commands/closeout.md` step 8, the CLAUDE.md SHARED-block `/closeout` ritual step 6, and FEEDBACK §2.12 item 2 — the last two of which #38 had deliberately left untouched.

**Rationale:** #38 kept the emission as a packaged copy-back bridge for the **branch-blind** claude.ai connector (master-only; cannot read a feature branch pre-merge). But a changed store file on disk *is* the exact wholesale-replacement text, so `cat`/open of that file is an equivalent, screen-clean pre-merge copy-back that needs no bespoke stdout emission. One rule (pointer-only; names, not contents) is simpler than a rule-plus-exception and removes the last raw-text dump from close-out stdout — the "go broad" direction. #38's own revisit clause anticipated this retirement and named the three files to change in lockstep.

**Status:** Active. Command + SHARED CLAUDE.md ritual step 6 + FEEDBACK §2.12 item 2 edited on `chore/closeout-emit-retire`, cut from master after #38 landed (`0a8a779`). Concern-split per #27: command/SHARED/FEEDBACK in the feature commit, this entry in the governance commit. The identical emission retirement is owed to `health-connect-app` in a separate single-repo session — a **two-file** mirror (its `/closeout` command **and** the SHARED CLAUDE.md loop block, since this change touches the shared ritual, not just the command; broader than #38's command-only mirror note).

**How you know:** `.claude/commands/closeout.md` step 8 now states copy-back is `cat`/open on disk with no store-text emission, and step 6's pointer lists changed-store filenames; the CLAUDE.md SHARED ritual step 6 and FEEDBACK §2.12 item 2 match — all committed this branch. #38's step-6 file/pointer core is unchanged, confirming the supersede is scoped to the named-exception clause only.

**Do not revisit unless:** `cat`/open copy-back from disk proves unreliable — e.g. the connector genuinely cannot reach a changed store even for a human paste — in which case a packaged stdout block returns (restore emission at step 8 + CLAUDE.md SHARED ritual step 6 + FEEDBACK §2.12 in lockstep and re-mirror to HCA).

---

### 40. Branch & session lifecycle protocol adopted

**Decision:** Branches and sessions reach an enforced terminal state, killing the merged-but-uncleaned sprawl. Five rules: (1) single merge path per repo + delete-on-merge — already live via GitHub repo settings (both repos, 2 Jul 2026); (2) merge/pending disposition by patch-id (`git cherry`), never SHA ancestry — `merge-base`/`rev-list` lie under rebase/squash; standing aliases `stale`/`land`; (3) terminal-state gate in `/closeout` + a `BRANCHES.md` ledger — no branch ends a session in undefined limbo; (4) DECISIONS_LOG numbers are `#NEXT` on-branch, claimed at merge — eliminates the #N collision and the renumber-on-`--ff` dance (#38 incurred exactly this); (5) concern-named branches, one per concern, reused across sessions — `claude/<session-hash>` auto-names banned for in-flight work (they spawned the `b9k5qf`/`yg1xx6` twins).

**Rationale:** Root cause addressed: `/closeout` previously proved a session documented, not a branch terminal. A session could end with its stores reconciled and its close-out committed while the branch it worked on sat merged-but-undeleted or unmerged-and-unlisted — invisible to the next session, which then re-cut a duplicate. The five rules close that loop at its enforcement points: disposition must be decidable under rebase/squash history (patch-id, not ancestry), the decision must be forced at session end (the `/closeout` gate), parked work must be legible (the ledger), and the two branch-spawned governance failures already incurred — the #N number collision and the auto-name twins — get structural fixes rather than vigilance.

**Status:** SHARED block + `.claude/commands/closeout.md` + `BRANCHES.md` on `chore/branch-lifecycle-protocol` (health-app). Mirror owed to health-connect-app: SHARED block verbatim + its own `/closeout` command gate + `BRANCHES.md` + its own DECISIONS_LOG claim (next canon = #16, since #34 voided the phantom #16). Rule 1 live via settings; Rules 2–5 land here.

**How you know:** Rule 2 exercised live in the adopting session: `git cherry origin/master <b>` on the four stale remotes showed zero `+` lines (three empty = ancestry-merged; `chore/closeout-emit-retire` two `-` lines = patch-upstream under a rebase merge, exactly the case ancestry checks get wrong), all four then deleted; `git ls-remote --heads origin` shows master only. The `/closeout` gate landed as step 4 with steps renumbered 1→9, verified free of duplicate/missing numbers and with internal cross-references updated. Rule 4's cost is documented precedent, not conjecture: #38's Status field records the yield-on-number / renumber-at-merge dance this rule retires.

**Do not revisit unless:** patch-id disposition yields a false "merged" in practice (a real multi-commit squash shows `+` = pending, so `git cherry` errs toward keeping work — a false "pending" is the safe failure); the `BRANCHES.md` ledger rots into stale entries the close-out gate fails to keep honest; or GitHub delete-on-merge (Rule 1) is switched off and manual pruning silently returns.

---

### 41. Terminal-state gate extended to local branches

**Decision:** #40's terminal-state gate, `stale`, and `land` key on `refs/remotes/origin`; local-only branches with unpushed commits escape the disposition net — undefined limbo one layer beneath where #40 looks. Discovered live: HCA `fix/scraper-sh-relayout` carried 3 unpushed local `+` commits invisible to every remote-based check. The `/closeout` terminal-state gate now enumerates local branches (`git branch`) alongside remotes: a local branch with `+` vs `origin/master` must be pushed, parked in `BRANCHES.md`, or discarded before close. #40's remote handling, patch-id rule, number-at-merge, and naming rules are unchanged.

**Supersedes:** #40's gate-scope clause only (remotes-only → remotes + local). #40 otherwise stands.

**Status:** SHARED block + `.claude/commands/closeout.md` on health-app. Verbatim gate re-mirror owed to `health-connect-app` — now a copy, not a hand-merge (per HCA #16's block establishment). Rule 5 note: `chore/governance-consolidation` carries two concern-split commit-groups (store-currency + gate) in one branch by explicit consolidation.

**How you know:** gate text in SHARED block and command confirmed lockstep-identical on local+remote enumeration; #NEXT claimed #41 at merge with master max verified #40 at that instant.

---

### 42. Per-user context isolation: `user_knowledge_entries` is the canonical structured-profile store; MCP tokens bind to a real user

**Decision:** Two multi-user leaks fixed, both landing as concern-split branches on top of master #41: (1) `context_builder._section_user_profile` no longer hardcodes Luke's identity/devices/injuries into every user's system prompt — it now reads a `type="preference", key="device_profile"` entry from `user_knowledge_entries`, falling back to a neutral line when absent; empty-profile users get a new onboarding-interview section that elicits scope then profile facts via the *existing* `knowledge_update` mechanism, the same write path ongoing chat updates already use (`fix/chat-context-per-user`). (2) `oauth_provider.PersonalOAuthProvider.authorize()` no longer auto-approves — it parks the request behind a ticket and redirects to a new `/mcp/login` form that re-checks email/password against the same `users` table `backend/auth.py` authenticates against; only then is an `AuthorizationCode` minted and bound to that `user_id`, carried through to the access/refresh token. Every `mcp_server.py` tool had its `user_id: int = 1` default removed entirely — no override param — and now resolves the caller via `_current_user_id()`, which reads the bearer token FastMCP already populates (`AuthContextMiddleware`, confirmed pre-wired by the installed SDK — no new middleware needed) and raises rather than falling back to any default (`fix/mcp-oauth-identity`).

**Supersedes:** The hardcoded-`_section_user_profile` approach and the `user_id: int = 1` MCP default. `has_structured_profile` (previously gating off `fortification_profiles`) is retired from `_section_user_profile` entirely — that table remains in use elsewhere (`_section_fortification`/`_section_probe`), untouched.

**Rationale:** Verify-first before design (standing rule, provoked by the HRV pipeline failure) found the original brief's premise wrong: `has_structured_profile` gated off `fortification_profiles` (a separate, manually-seeded table) while `knowledge_update` chat writes landed in `user_knowledge_entries` — genuinely disjoint stores, so an interview could never suppress the hardcode. Reading further showed the actual leak was narrower than assumed: `_section_identity` already renders `user.full_name or user.email` dynamically, and `_section_schedule` already renders `type="injury"` entries per-user — only the device/method mapping was truly orphaned. On the MCP side, `oauth_provider.py`'s `AccessToken` carried no subject field at all; the `user_id=1` default wasn't a lazy shortcut around an existing auth mechanism, there was no user-identity mechanism to hook into until this session added one.

**Status:** `fix/chat-context-per-user` (P1, chat context) and `fix/mcp-oauth-identity` (P2, MCP auth) both complete and verified locally, not yet merged. Luke's device/method facts and three injuries seeded into `user_knowledge_entries` via an extension to `seed_engine.py`'s existing idempotent seeding (not a new migration script) — run once locally; owed against Railway Postgres per the "verify on Railway" standing rule before this entry's G4 counts as satisfied in production.

**How you know:** Direct code reads this session confirmed the disjoint-store finding (`context_builder.py:886` computed `has_structured_profile` from `fortification_profile is not None`; `routers/chat.py`'s `_process_knowledge_updates` → `routers/knowledge.py`'s `upsert_knowledge_entry` write only `user_knowledge_entries`) and the MCP no-subject finding (`oauth_provider.py`'s `AccessToken(token, client_id, scopes, expires_at)` — no `sub`/user field; `PersonalOAuthProvider.authorize()`'s docstring literally read "Auto-approves all authorization requests — no login screen"). All four gates exercised against a real (non-mocked) local SQLite DB with real code paths, not assumption: G1 (`grep -i luke` on an empty-profile user's assembled prompt — empty) and G4 (Luke's seeded device/injury facts render from the structured store) both scripted against `context_builder.build_system_prompt`; G2 scripted a real `<knowledge_update>` block through `_process_knowledge_updates` and confirmed next-turn rendering; G3 drove the full OAuth `authorize()` → `/mcp/login` ticket → `complete_login()` → `exchange_authorization_code()` sequence end-to-end and confirmed the issued token resolves to the logged-in user's real `user_id` (not 1), and that an unbound/garbage token resolves to `None` rather than silently defaulting.

**Do not revisit unless:** a second structured-profile store is introduced without an explicit unification decision (the disjoint-store failure mode that provoked this entry); or MCP needs multi-tenant session concurrency beyond the current in-memory token maps (out of scope here — matches the existing "personal use... reset on server restart" posture of `oauth_provider.py`, not changed by this entry).

---

### 43. Event-spine fork (Q8) resolved — overlay wins for Decision Support; `health_events` narrowed to a deferred projection

**Decision:** Q8 resolves to organic + overlay, not the `health_events` primary-store spine. `user_health_state` is not a new materialised object — it is a compute-on-read `current_state` read model over existing stores: active `user_knowledge_entries` (declared protocol/injury/preference/schedule/load_context; the canonical structured-profile store per #42), `fortification_profiles`, and `capability_state`, plus baselines computed on read (v1: the 7-day HRV rolling baseline already computed inline in `context_builder`). `context_builder` is refactored to consume this read model as a formatter, so declared state has one read layer, not two. `health_events` is deferred; if later adopted it is adopted **only as an additive projection** (a denormalised read-index over the typed systems-of-record) scoped to the medical timeline — labs/imaging/appointments/protocol-change chronology — never as the SCHEMA.md primary store the organic tables collapse into. The projection call is timed to the lab-upload pipeline, its first consumer whose primitive is chronology rather than current state. `capability_state`'s existing fold-in clause (#21) is unchanged.

**Rationale:** Verify-first against master this session found the fork's framing stale. Master already contains a working current-state layer (`user_knowledge_entries` typed/`active`-flagged/`superseded_by`/source-tagged, plus `fortification_profiles` and `capability_state`), and `context_builder` already assembles all of it into the chat prompt including a rolling HRV baseline — so `user_health_state`'s function is largely built. What is missing is not a spine but a *reusable* read model (the state exists only as prompt text, unqueryable by Decision Support or the appointment brief) and, later, baseline persistence. The AEE decision already ratified "don't block on `health_events`; build a dedicated typed table now, fold in if it lands"; overlay continues that stance rather than opening a new bet. A primary-store spine now would duplicate the declared-state semantics `user_knowledge_entries` already carries and lossy-collapse the typed signal tables into JSON. The one force pulling toward a spine — the appointment brief's cross-domain "what changed since last visit" chronology — is served by a projection (every relevant row is already timestamped in the typed tables), not by making `health_events` primary, and that need has real design inputs only at the lab pipeline.

**Do not revisit unless:** the lab-upload pipeline is specced (make the projection call then, with the brief's chronology requirements in hand); a second declared-state store is introduced without unification (the #42 disjoint-store failure mode); or a non-chat consumer needs current-state at a latency compute-on-read can't meet (then materialise the read model or its baselines — without reopening the spine).

---

### 44. Legacy `user_knowledge` retained alongside `user_knowledge_entries` — #43's "one read layer" scoped to structured declared state

**Decision:** The legacy `user_knowledge` table (free-text `category`/`content`, its own router `routers/knowledge.py`, written at `chat.py:232` and `knowledge.py:156`, read at `chat.py:322` into `build_system_prompt`'s `knowledge_entries` param) is **retained as a distinct store**, coexisting deliberately with the structured `user_knowledge_entries` that `current_state` (#43) owns. #43's "declared state has one read layer, not two" is hereby **scoped to structured declared state** — the typed protocol/injury/preference/schedule/load_context/fortification/capability set. The free-text KB is intentionally outside `current_state` and reaches `context_builder` via the parallel `knowledge_entries` param. This entry records intent; no code changes.

**Rationale:** Post-#43 verification against master found `user_knowledge` still live — read, written, and served by its own API router — fed to `context_builder` outside `current_state`. Free-text category/content is a different shape from typed key/value declared state; folding it in now is premature and likely a worse fit. The hazard was never the coexistence but its silence: #43's canonical wording reads as if consolidation is complete, ambushing a future reader with the live parallel store. Documenting the coexistence as deliberate removes that drift-seed; the consolidation question is parked (Q9), not answered.

**Do not revisit unless:** the consolidation review (Q9) is undertaken — fold `user_knowledge` into `user_knowledge_entries` as a note type, retire `routers/knowledge.py`'s legacy write path and `context_builder`'s `knowledge_entries` param, making `context_builder` a true single-source formatter over `current_state` — or a *third* knowledge/declared-state store appears (the #42 disjoint-store failure mode).

---

### 45. `### Current sprint` block retired for a capped, pointer-only `### Recent landings`

**Decision:** CLAUDE.md's repo-specific `### Current sprint` block — a per-close-out-accreting detailed changelog (decision sub-bullets, commit SHAs, test detail) — is retired and replaced by `### Recent landings`: pointer-only, capped at the 3 most recent landings, one line each, referencing the canonical home (`#N` DECISIONS_LOG, `closeout.md`) and never re-narrating decision or feature content. "Current sprint" is freed to mean unambiguously ROADMAP `## NOW` per the store-index, removing the two-directional name collision (a forward sprint table and a backward changelog both titled "Current sprint"). The `/closeout` step that wrote the old block is amended to the pointer-only cap; verified against CLAUDE.md's own SHARED "Session rituals" text and HCA's CLAUDE.md/closeout.md, both the block and the step are repo-specific to health-app only — no HCA propagation required.

**Rationale:** The old block was a derived label over an independently-authored artifact — longer and more detailed than the ROADMAP/ptb-tasks it claimed to derive from — re-narrating DECISIONS_LOG content that won't track supersession (supersede #43 and the block keeps asserting the old conclusion, unreferenced). It fattened every close-out (+31 lines in one session), trending toward a second decisions-log inside the rules file: the same volatile-content-in-a-stable-file failure mode as the PLATFORM drift. A capped pointer preserves cold-open orientation while removing the drift surface — the detail already lives canonically in DECISIONS_LOG (history) and closeout.md (latest handoff). The block's 3 still-open action items (Supersede #3, HCA writer-identity forwarding, backend F1 filter) were not landings and were migrated to `ROADMAP.md` NOW/NEXT rather than dropped.

**Do not revisit unless:** the pointer-only cap proves too thin for cold-resume (then improve closeout.md, don't re-fatten the block); or close-out maintenance drifts back toward re-narration (tighten the `/closeout` step, don't relocate the block).

---

### 46. Polar AccessLink per-second exercise-HR pathway — precise scope + citation

**Decision:** Per-second exercise HR is available via (a) the v3 REST exercise-samples endpoint (per-sample-type `recording-rate`; =1 → 1Hz), and (b) TCX/CSV/FIT export (second-by-second HR; RR in the .txt/FIT). It is NOT available via v4 REST `training-sessions/list` (summary only, per #17) or v4 continuous-samples (24/7 `TRIGGER_TIMED_247`, coarse). For the direct solo/gym upload lane, PSL remains primary and higher-fidelity (1Hz HR + per-beat RR + 203Hz ACC + 130Hz ECG); AccessLink is redundant there. No AccessLink ingest is built in this session.

**Refines:** #35 — adds endpoint precision and methodology to its previously uncited claim ("per-second... available only via AccessLink v4 / ZIP path"). Corrects "v4 / ZIP" to the specific surfaces above; the surface is v3-REST or TCX-export, not v4-REST. #35's HC-lane dependency stands.

**Consistent with:** #17 (v4 REST list = summary; zone/load via ZIP export).

**Out of scope** (separate, still-open decision, motivated by #35): whether to build AccessLink per-second ingest for the Metabolic-load window in the HC/companion lane. Not decided here.

**Inputs/methodology:** official Polar v4 API doc (endpoint surfaces + scopes); validated v3 client `StuMason/polar-flow` (`models/exercise.py` → `ExerciseSample.recording_rate`); Polar export docs (CSV "second by second... heart rate"); corroborating aggregators (Terra, Open Wearables, vitalera).

**Confidence:** pathway existence/scoping — Certain; v3 longevity — Guessing (deprecation risk); applicability to Luke's specific sessions (device recording rate; cloud-sync collision with "never save the Polar session") — Likely.

**Status:** Recorded as a decision input / prior-art finding. No ingest built; no supersede — this refines #35's uncited passing claim with methodology and precise scoping.

---

### 47. Regulatory framing — education, not clinical decision support

**Decision:** The platform provides health education, never clinical decision support. It explains
mechanisms, lists evidence-ranked levers, and filters for relevance; it never connects a lever to a
personalised recommended action. Line: "levers that influence oestradiol" = education; "given your
dose, adjust X" = prescription; evidence-ranked lists = education; filtering already-addressed levers
= curation; personalised prioritisation to the individual = prescription.

**Rationale:** Keeps the product outside TGA Software-as-a-Medical-Device classification; the user is
always the decision-maker. Enforced at the prompt layer AND structurally — no interpretation-output
field expresses a personalised action.

**Consistent with:** #21 — the Adaptive Exposure Engine already drew this same education/practitioner
line for capability state ("engine probes and surfaces; interpreting a formal screen stays the
practitioner's line"). #47 generalises that precedent into a named, repo-wide constraint rather than
an incidental phrase local to one module.

**Status:** Locked. Non-negotiable constraint on the AI output layer.

**Provenance:** Originally decided 2026-06-15 (chat); recorded here to close a chat↔repo drift —
absent from this log until now.

**Do not revisit unless:** regulatory advice changes the classification analysis.

---

### 48. Lab input UX — file-first, no forms, chat for edge cases

**Decision:** Primary lab input is file attach (PDF/photo) → AI extraction → confirmation screen
(outlier flagging) → stored. No manual-entry forms. Chat handles single verbal metrics → inline
confirmation → stored `source: verbal`. Metrics screen has one action: attach file.

**Rationale:** Forms require health literacy; file upload requires none. Chat absorbs the verbal edge
case without new UI. Source-tagged for confidence tracking.

**Status:** Locked.

**Provenance:** Originally 2026-06-15 (chat); backfilled to close drift.

**Do not revisit unless:** extraction proves unreliable enough to need a structured-entry fallback.

---

### 49. Interpretation layer design — delta-first, three sections, filtered levers

**Decision:** Lab interpretation is delta-first (trend is the story, absolute is supporting),
mechanism-based, protocol-aware. Three sections: What Moved (delta vs prior panel + mechanism in
protocol context); Stable (explicit nothing-to-flag — chronically-flagged-but-flat markers belong
here, not in What Moved); Mechanisms Worth Understanding (filtered lever list per moving marker).
Levers already addressed are shown transparently as "already in play," never silently dropped. Each
lever taps into a chat pre-seeded with marker + mechanism + why-surfaced. Consumes `current_state`
(#43) directly. Emitted shape lives in the interpretation output contract (knowledge-file, orientation).

**Rationale:** Delta-first suppresses noise (a persistent Gilbert's-pattern H is not news);
protocol-awareness makes mechanisms correct in stack context; transparent filtering stays curation,
not prescription (#47).

**Status:** Locked (design). Build pending — depends on the lab store (OPEN) and the lever dictionary (#51).

**Provenance:** Originally 2026-06-15 (chat); backfilled — this is the entry ROADMAP called "design
complete" while it was absent here.

**Do not revisit unless:** the three-section model fails a real panel.

---

### 50. Marker canonicalisation — internal dict, confirmation-populated, unit-guarded, dormant LOINC

**Decision:** Canonical marker identity uses an internal dictionary — confirmation-populated (exact
known name auto-maps; novel name → null → surfaces once for manual bind/declare; no fuzzy
auto-guessing) and unit-guarded (keyed on name+unit; write-time guard flags a mapped result whose unit
differs from its series' established unit). Each entry carries a dormant nullable `loinc`, deferred to B2B.

**Rationale:** The dangerous failure is over-collapse (two analytes silently merged — total-T nmol/L
vs free-T pmol/L both "Testosterone"). Confirmation-population + unit-guard make silent over-collapse
structurally hard. LOINC-from-day-one front-loads interop not needed in proof phase; the internal dict
is its substrate.

**Status:** Locked (drafted PENDING in LAB_EXTRACTION_SCHEMA §7). ~~Not implemented.~~ Superseded by #220: fully implemented. The unit-guard landed earlier at confirm (this status line had gone stale against it); the confirmation-populated half landed at #220, where the map became a table and gained a guarded runtime bind. `loinc` remains a carried, dormant column.

**Provenance:** Drafted in chat, marked "carry to Code," never landed. Folded into this pass as
adjacent drift — logged here rather than separately since both surfaced in the same drift review.

**Do not revisit unless:** LOINC is brought forward, or a categorical/qualitative result forces the schema.

---

### 51. Lever dictionary — GRADE tiering, in-repo direct-read asset, per-(marker,lever) grading

**Decision:** The marker→lever reference asset (Section 3 of the interpretation contract) is built,
not bought (no ingestable source; Examine is a paywalled analogue + B2B licensing candidate only). It
is a versioned, direct-read, in-code asset mirroring `engine/taxonomy.py` — never seeded to a table;
only user data is tabled. Evidence certainty uses GRADE (high/moderate/low/very_low), graded per
(marker, lever) pair by a mechanical rubric (start-level by study design → downgrade/upgrade by named
GRADE domains). GRADE over Examine-style A–F because A–F leaks a recommendation verdict; GRADE states
evidence certainty only — consistent with #47. `ai_draft` entries are excluded from user-facing
Section 3 until `human_verified`; a marker ships Section 3 only when its lever set is complete.
Authoring via the connected evidence tools (Consensus/PubMed/Scholar Gateway/Scite).

**Rationale:** In-repo direct-read matches the taxonomy precedent (git diff is the audit trail; no
seed/migration to expand). GRADE keeps grades defensible as education, not product scores. Per-pair
because the same lever grades differently for different markers.

**Status:** Decided, not implemented. Consequence: the interpretation output contract needs a v0.2
(tier enum → GRADE; evidence_rank derived-not-stored; add grade_rationale/evidence_refs +
lever_dictionary_version) — a knowledge-file/UI edit, not this pass.

**Provenance:** Decided this session (2026-07-05, chat).

**Do not revisit unless:** a curated evidence source becomes licensable, or GRADE proves too coarse.

### 52. Lab store — `lab_report` + `lab_result` table pair (Q-store resolved)

**Decision:** Observed labs live in a concrete two-table pair — not
`user_knowledge_entries type="lab"`, not the deferred generic `health_events` spine.
- `lab_report` (envelope, one row per collection event): `user_id` (FK, index),
  `lab_name`, `lab_provider_group?`, `panel_name_raw`, `accreditation_no?`,
  `referrer_name_raw?`/`referrer_ref?`, `collected_date` (index — timeline anchor),
  `received_at?`/`reported_at?`/`document_created_at?`/`requested_date?`,
  `report_comments?` (JSON), `source_completeness`
  ('sonic_dx_extract'|'full_report'|'unknown'|'verbal'), `source`
  ('file_extraction'|'verbal'), `source_doc_filename?`/`page_count?`,
  `overall_confidence` (float), `extracted_at?`, `created_at`.
  Index(user_id, collected_date).
- `lab_result` (one row per marker): `lab_report_id` (FK, index), `marker`
  (canonical id from #50, index), `value_num?` (float), `value_operator?`
  ('<'|'>'), `value_qualitative?`, `unit_canonical?`, `ref_low?`/`ref_high?`,
  `ref_*_exclusive` (bool), `lab_flag?`/`computed_flag?`, `confidence` (float),
  `created_at`. Unique(lab_report_id, marker); Index(marker).
`current_state` reads latest `lab_result` per marker via join to `lab_report`
(compute-on-read, #43 overlay).

**Rationale:** (a) repo grain — every observational series here is a typed table;
`user_knowledge_entries` holds declared facts only. (b) #51's line "only user data
is tabled" puts labs on the table side. (c) the report envelope is real provenance
the extractor emits (LAB_EXTRACTION_SCHEMA §2); a `report_ref` string has nowhere to
store it — a parent table does. (d) source/confidence house rule → typed columns.
(e) modeling honesty — one row = one observation true at its draw date, not a
supersede. (f) delta-first (#49) reads newest+prior per marker via Index(marker) +
join. Not a reopen of #43/Q8: `lab_report` is a concrete domain table, not the
generic `health_events` spine #43 deferred — #43 timed this projection's call to the
lab pipeline; this is it.

**How you know:** master `backend/models.py` tablename enumeration this turn (13
tables, none `lab*`/`health_event*`) = greenfield; `backend/main.py:21` =
`Base.metadata.create_all(bind=engine)` → new model classes auto-create on deploy,
no migration authored (`alembic.ini` exists but boot uses `create_all`).

**Status:** Decided, not implemented. Unblocks the #49 build + #48 write path.

**Provenance:** Q-store raised prior chat, never filed (see Q11); resolved
2026-07-05. Report-envelope gap caught while reconciling LAB_EXTRACTION_SCHEMA §1/§2.

**Do not revisit unless:** a qualitative-heavy panel breaks the numeric `value_num`
assumption, or multi-tenant scale changes the shape.

### 53. Per-marker minimum meaningful delta — reference asset, not a table column (Q-threshold resolved)

**Decision:** `min_meaningful_delta` is a per-marker static-reference attribute in an
in-repo direct-read asset of the #51 family (versioned, git-diff audit trail, never
tabled), keyed on the #50 canonical id. NOT a field on #50's confirmation-populated
identity dict; NOT a `lab_result` column; never global. The #49 delta-gate suppresses
a marker from "What Moved" when `|value(current) − value(prior)| < min_meaningful_delta`.

**Rationale:** #51's dividing line — authored reference data lives in-repo, not a
table. It is static (a fixed property of the analyte), so it does not belong on #50,
which is confirmation-*populated* runtime identity state; mixing static reference into
runtime bindings is the smell #50/#51 already separate. Per-marker not global because
a 2-unit move is noise for one analyte and signal for another.

**How you know:** #50 read this turn — its dict is "confirmation-populated" and
"unit-guarded (keyed on name+unit)," i.e. identity state, not a value store; #51
establishes the in-repo direct-read reference asset this attribute joins.

**Status:** Decided (placement). Threshold values are content-authoring alongside the
#51 lever dictionary, not a fork.

**Provenance:** Q-threshold raised prior chat, never filed (see Q12); resolved this
session. Placement corrected after reading #50.

**Do not revisit unless:** a marker needs a context-dependent (e.g. protocol-phase)
delta rather than a single static one.

### 54. Correction to #52's "How you know" — real boot mechanism is `alembic upgrade head`, not `create_all`; Postgres boolean defaults need `text('true')`/`text('false')`

**Decision:** #52's "How you know" line asserted new model classes auto-create on
deploy via `Base.metadata.create_all` (`backend/main.py:21`), with no migration
authored. That is wrong: `backend/railway.toml` / `backend/Procfile` set
`startCommand = "alembic upgrade head && uvicorn ..."` — Alembic, not `create_all`,
is what actually runs against Railway Postgres on every deploy (`main.py`'s
`create_all` call is dead code for that path; it only matters for
`conftest.py`'s SQLite test fixture). Landing `LabReport`/`LabResult` for real
required authoring migration `8e5c0954c4b5` the same way as the repo's other 17
migrations. Separately, that migration's first version
(`ref_low_exclusive`/`ref_high_exclusive` `server_default=text("0")`) failed twice
in deploy (`sqlalchemy.exc.ProgrammingError: DatatypeMismatch — column is of type
boolean but default expression is of type integer`) — `sa.text()` emits its
argument as literal, untranslated SQL; Postgres DDL does not accept a bare
integer literal as a `BOOLEAN` column's `DEFAULT`. Migration `f4e9d2c1b3a7`
already established the working convention (`server_default=sa.text('true')`);
`text('0')`/`text('1')` — as `UserKnowledgeEntry.active` still uses in
`models.py:84` — is latent-broken should its table ever need a fresh migration.

**Rationale:** Both errors are "assumed, not verified" — the founding failure mode
this repo's rules exist to catch (CLAUDE.md "Verify before design";
DECISIONS_LOG discipline's "How you know" requirement). Logging the correction
rather than silently editing #52 in place keeps the append-only history honest
about what was actually checked when, per CLAUDE.md's DECISIONS_LOG discipline.

**How you know:** `backend/railway.toml`/`backend/Procfile` startCommand read this
session; two live Railway deploy failures (`9e92709a`, `39c503db`) with full
tracebacks via `railway logs --deployment <id>`; migration `8e5c0954c4b5` applied
directly against Railway Postgres after the `text('false')` fix, confirmed via
`psql \d lab_reports`/`\d lab_results` and a clean third deploy (`d0eeed98`,
`SUCCESS`) whose `alembic upgrade head` no-opped against the already-applied
revision.

**Status:** Decided and applied. `lab_reports`/`lab_results` live on Railway
Postgres, both empty, `alembic_version` at `8e5c0954c4b5`.

**Provenance:** Corrected this session (2026-07-05) while landing #52/#53.

**Do not revisit unless:** the deploy pipeline's startCommand changes, or
`UserKnowledgeEntry.active`'s latent `text("1")` default is ever exercised by a
fresh migration (fix to `text('true')` at that point, not before — no functional
bug today since its table already exists with that default already applied).

---

### 55. Boolean server_default convention — standing rule

**Decision:** All Boolean columns in SQLAlchemy models use
`server_default=text('true')` or `server_default=text('false')`.
Never integer literals (`text("1")`, `text("0")`) — these are
invalid Postgres BOOLEAN DDL and silently fail at migration time.

**Rationale:** `text("1")` cost two failed Railway deploys during #52.
The convention already exists implicitly in migrations f4e9d2c1b3a7
and 8e5c0954c4b5; this files it as an explicit referenceable rule.

**Status:** Standing convention.

**Do not revisit unless:** SQLAlchemy ORM changes its DDL generation
in a way that makes this form obsolete.

---

### 56. `railway run` on a local machine cannot resolve Railway's internal `DATABASE_URL` — public proxy override required

**Decision:** When running a local script against Railway production Postgres
via `railway run`, the injected `DATABASE_URL` uses the private-network hostname
(`postgres-28pk.railway.internal`), which only resolves inside Railway's own
network — not from a laptop. `railway run` also takes precedence over any
locally pre-exported `DATABASE_URL`, so the override must happen inside the
same invocation, downstream of Railway's injection (e.g.
`railway run bash -c 'DATABASE_URL="<DATABASE_PUBLIC_URL value>" venv-python script.py'`),
using the Postgres service's own `DATABASE_PUBLIC_URL` value (`railway variables
--service <postgres-service>`) as the override target. The backend service's own
variable set does not expose `DATABASE_PUBLIC_URL` — it must be read from the
Postgres service directly. Separately, the local backend venv
(`backend/.venv`) — not the system Python on `PATH` — is what has
`sqlalchemy`/`psycopg2` installed; `railway run python ...` alone resolves to
the system interpreter and fails with `ModuleNotFoundError`.

**Rationale:** This is the concrete mechanism behind #42's "no Railway
credentials in-session" gap — `railway run` alone is necessary but not
sufficient for a Postgres-hitting local script; without the public-proxy
override it fails closed (connection error), not silently (unlike the SQLite
fallback #42 originally guarded against), but it still blocks the intended
verification-only task from completing with the literal one-line command.
Recording this so the next local-script-against-production run doesn't
re-discover it from scratch.

**How you know:** `railway run python backend/seed_engine.py` failed with
`ModuleNotFoundError: No module named 'sqlalchemy'` (system Python). Re-run with
the venv Python failed with `psycopg2.OperationalError: could not translate
host name "postgres-28pk.railway.internal"`. Confirmed precedence empirically —
a locally-exported `DATABASE_URL` was silently overwritten back to the internal
hostname by `railway run`. Retrieved `DATABASE_PUBLIC_URL` via `railway
variables --service health-app-DB --kv`; overriding inline inside the `railway
run bash -c '...'` invocation connected successfully and `seed_engine.py` ran
to completion against production, confirmed via direct `psql` query against
`zephyr.proxy.rlwy.net:57857/railway` (users, fortification_profiles,
capability_state, user_knowledge_entries all returned expected rows for
user 1).

**Status:** Decided and applied this session (2026-07-06). `seed_engine.py`
run against Railway production Postgres; ROADMAP.md's corresponding NOW-list
line removed.

**Do not revisit unless:** Railway changes `railway run`'s variable-injection
precedence, or exposes public-proxy variables to dependent services by
default.

---

### 57. Canonical marker vocabulary is single-source; interpretation assets bind to it

**Decision:** `marker_canonical.json` is the single source of canonical marker
ids. `lever_dictionary.json` (#51) and `marker_groups.json` bind to its ids;
they do not mint their own. Reconciliation is bidirectional — asset ids conform
down to marker_canonical's strings, and marker_canonical expands up to cover
every markered/levered analyte or the binding dangles. This pass adds the four
hormone-axis markers (`testosterone_total`, `shbg`, `testosterone_free_calculated`,
`oestradiol`) required by the HPG lever/group work; broader expansion (CBC, iron,
lipid sub-markers, homocysteine, PSA, HbA1c, ACR) is deferred. CK is not
pre-added — it populates on first appearance per #50.

**Rationale:** Three assets keying on canonical id (identity #50, levers #51,
relations) were being evolved in isolation across two build lanes; divergence
means levers don't bind and relations don't resolve. Single-source + bidirectional
reconciliation kills the drift.

**Status:** Decided and applied this session.

**How you know:** `backend/reference/marker_canonical.json` read and confirmed
prior state (27 entries, version 0.1, schema `{marker_name_raw, marker_canonical,
unit_established, loinc}`); `backend/routers/labs.py:33` confirmed the loader
keys on `marker_name_raw`, and the over-collapse unit-guard at line 398. `git
branch -a` confirmed no parallel branch mid-edit on this file (master only,
local and remote). Four entries added, version bumped to 0.2; reloaded and
verified programmatically: 31 entries, no duplicate raw names or canonicals,
`testosterone_total` (nmol/L) and `testosterone_free_calculated` (pmol/L)
resolve to distinct canonicals with distinct units — the #50 over-collapse case
this decision exists to prevent.

**Provenance:** Cross-lane coordination review, 2026-07-06 (chat).

**Do not revisit unless:** a second canonicalisation authority is introduced.

---

### 58. Option B: split raw marker name from canonical id; add is_derived

**Decision:** `lab_results` stores `marker_name_raw` (String(100), NOT NULL) and
`marker_canonical` (String(100), nullable) as distinct columns; the per-report
unique key repoints to `(lab_report_id, marker_name_raw)`. Canonicalisation is
the result of mapping `marker_name_raw` against `marker_canonical.json`
(#50/#57), not a value forced into a single NOT NULL column. Adds `is_derived`
(Boolean, NOT NULL, `server_default` false) recording the extraction observation
that a report labelled a value derived/Calculated. `derived_from` is
deliberately NOT a column: it is a type-level canonical dependency edge
(eGFR←creatinine), which belongs in `marker_groups.json`, not duplicated
per-row.

**Rationale:** The prior single NOT NULL `marker` column forced a raw-name
placeholder for unmapped markers — a canonical id that was silently a raw
string, an over-collapse risk #50 exists to prevent. Splitting the columns
removes the placeholder and makes canonical nullable (unmapped = null, visible
as an interpretation-layer skip). `is_derived` on the row is observable even
for unmapped markers; `derived_from` is not (no canonical id to name a source),
and putting it on the row would duplicate a `marker_groups` edge — two sources
of truth, drift-prone.

**Migration:** `backend/migrations/versions/217dce22fbc5_option_b_marker_split_plus_is_derived.py`,
chained onto head `8e5c0954c4b5`. `op.batch_alter_table` throughout for SQLite
portability, split into four sequential batches rather than one — combining the
column rename (`marker` → `marker_canonical`) with index drop/create in a single
batch tripped an Alembic SQLite batch-mode bug in index carry-forward across
renames (`KeyError: 'marker_canonical'` in `_gather_indexes_from_both_tables`);
isolating the rename into its own batch avoided it. `marker_name_raw` backfilled
= old `marker` (raw was never historically stored — lossy but the only
recoverable value; safe on the 24 local rows and empty-of-labs Railway).
Downgrade coalesces `marker := coalesce(marker_canonical, marker_name_raw)`
before restoring NOT NULL. `is_derived` server_default is `text('false')`,
matching the `ref_low_exclusive`/`ref_high_exclusive` convention (#55) — never
`text("1")`/`text("0")`.

**Consumer fix (same commit):** `routers/labs.py`'s `confirm_lab_report` write
path constructed `LabResult(marker=canonical or r.marker_name_raw, ...)` — the
exact placeholder pattern this decision removes, and a direct break the moment
`marker` stopped existing as a kwarg. Updated to
`marker_name_raw=r.marker_name_raw, marker_canonical=canonical` (no fallback;
`unmapped` in the response remains the actual "needs a human bind" signal, not
column nullness).

**Status:** Decided and applied this session. `alembic upgrade head` /
`downgrade -1` / re-`upgrade head` all verified on local SQLite: single head
(`217dce22fbc5`) after, post-migration schema matches spec exactly (`marker_canonical`
nullable, `marker_name_raw` NOT NULL + indexed, `is_derived` present with correct
boolean default, `uq_lab_result_report_marker_raw` live, old constraint/index
gone), all 24 local rows survived with `marker_name_raw` backfilled = old
`marker`, zero NOT NULL violations, downgrade round-trip restored the original
schema and data faithfully.

**How you know:** Pre-state verified against live `master`
(`backend/models.py` + the `8e5c0954c4b5` migration file + a direct SQLite
schema read) — `marker` NOT NULL, `uq_lab_result_report_marker` on
`(lab_report_id, marker)`, no `marker_name_raw`/`marker_canonical`/`is_derived`;
24 rows. `alembic heads` returned exactly one revision before and after. Local
dev DB's `alembic_version` was found stamped stale (`b7c3e1a9f2d4`) against an
already-at-head actual schema (pre-existing drift, unrelated to this session) —
corrected via `alembic stamp 8e5c0954c4b5` (stamp only, no DDL) before testing,
so the reported upgrade/downgrade results are against a verified-accurate
baseline.

**Provenance:** Cross-lane coordination review, 2026-07-06 (chat).

**Do not revisit unless:** raw-name provenance beyond the single stored raw
string is required, or `derived_from`'s home changes.

---

### 59. Lab reads cut against final #58 schema; context_builder feeds the general chat lab GENERALITY only — value relays on-ask, interpretation gates to #49

**Decision:** Two lab reads share one query helper
(`backend/reads/labs_reads.py::latest_lab_results`), a `ROW_NUMBER() OVER
(PARTITION BY COALESCE(marker_canonical, marker_name_raw) ORDER BY
collected_date DESC, id DESC)` joined through `lab_reports` and filtered on
`lab_reports.user_id` — one row per real-world marker, latest report wins.
`current_state.CurrentState.labs` (Read 1) consumes it. Read 2
(`GET /labs/results`) was scoped in the brief but not built — checked
`frontend/src/pages/Metrics.jsx` and found no consumer for a results-GET yet
(only `/labs/canonical-map`, `/labs/extract`, `/labs/confirm`); building it now
would be unused code, deferred until a consumer exists. The read intentionally
never re-resolves raw→canonical itself (would duplicate canonicalisation and
drift from stored state) — canonicalisation is fixed at `/labs/confirm` write
time (#58) plus the backfill rider below.

**Render-policy gate (revised after first-pass review):** `context_builder`'s
`_section_labs` feeds the general-chat standing prompt lab GENERALITY only, per
measured marker: `marker_canonical` + `lab_flag` (the lab's own H/L/critical
assertion, labelled lab-asserted) + availability metadata (collected-date,
derived-staleness tag) + a route pointer. It does NOT feed `value_num`,
`ref_low`/`ref_high`, `unit_canonical`, `computed_flag`, deltas, axis-verdicts,
mechanisms, or levers into standing context. Unmapped markers
(`marker_canonical IS NULL`) render as availability-only.

An initial pass over-rendered `value`/`unit`/ref bounds directly into the
standing feed — caught in review before commit. Corrected: the numeric value +
reference bounds relay only on an EXPLICIT single-marker ask, via
`reads.labs_reads.find_marker` (word-boundary match against the report's raw
name or canonical id, over the already-fetched `state.labs` — no second query)
wired in `chat.py`, and `context_builder.render_asked_lab_value`, which appends
a request-scoped block to the system prompt for that turn only (never merged
into the standing render, never persisted to a later turn). The rationale for
making this structural rather than behavioural: a value sitting in the standing
prompt is reasoning substrate whether or not it was asked for, so the control
is "value absent from standing context, fetched on demand" — not a "don't
mention it" instruction laid over data that's already present, which leaks
under long context or clever prompting. Even the on-ask value response ends in
the route pointer — the number answers the literal question; the route is
where meaning lives, per #49.

**Route pointer is a temporary placeholder, not a real destination.** #49's
dedicated lab-interpretation view has not been built in the frontend yet — the
only route in `App.jsx` is `/metrics`, and `Metrics.jsx` currently only does
attach→extract→confirm, no persisted read-back. Both render functions point at
`"Metrics page"` via a single `_LAB_INTERPRETATION_VIEW_LABEL` constant in
`context_builder.py`, flagged in a code comment as a stand-in to be swapped the
moment #49 ships a real UI. Recorded here so it isn't mistaken for a permanent
architectural choice.

**Backfill rider — generalised, not hardcoded to #57's four.** First pass
hardcoded `backend/backfill_marker_canonical.py` to the four raw names #57
added (`Testosterone`, `SHBG`, `Calculated Free Testosterone`, `Oestradiol`),
but flagged in review as unable to serve the next vocab bump (a pending 7-id
addition) without a code change — the coalesce-partition would silently
double-count those newly-mapped markers too. Corrected: the script now reads
`marker_canonical.json` directly and backfills every raw→canonical mapping in
it wherever `marker_canonical IS NULL`, so it's a genuine standing rider, not a
one-off. Dry-run (default) prints counts; `--apply` writes and commits. Run
dry-run against Railway production twice this session (once per version) via
the #56 public-proxy pattern: `lab_results` has **0 rows** in production
(Metrics page landed this cycle but no report has been confirmed yet), so the
backfill is a correct no-op today — nothing to apply, but the script is now the
actual standing remedy for every future vocab dict expansion, not just #57's.

**Standing rule:** A canonical-dict expansion (`marker_canonical.json` version
bump) requires running this backfill on `lab_results`, else the
`COALESCE(marker_canonical, marker_name_raw)` partition double-counts the
newly-mapped marker as two series. Sibling to #55's boolean-default rule —
filed here so the next dict expansion doesn't rediscover it from scratch.

**Status:** Decided and applied this session. `backend/reads/labs_reads.py`
(`latest_lab_results`, `find_marker`), `current_state.py` (`labs` field),
`context_builder.py` (`_section_labs`, `render_asked_lab_value`), `chat.py`
(on-ask wiring), and `backend/backfill_marker_canonical.py` (generalised) all
landed. Tests: `backend/tests/test_labs_reads.py` (15 cases — coalesced-key
partition, cross-user isolation, derived-staleness flag both ways, standing
render withholds `computed_flag`/value/unit/ref entirely, unmapped shows
availability-only, the double-count failure mode with its backfill fix
demonstrated directly, `find_marker` matching, and the on-ask relay withholding
interpretation). Full suite: 15/15 passed, including
`test_context_builder_output_unchanged_pre_post_refactor` — this was found
failing pre-existing (confirmed via `git stash` against clean `master`, unrelated
to this work) and separately fixed this session: the test compared against
`master:backend/context_builder.py` for a "pre-refactor" snapshot, but `master`
had moved past the refactor commit (`bda4327`) itself, making old-vs-new
actually old-vs-old. Repinned to `PRE_REFACTOR_SHA = "3360ed5"` (`bda4327`'s
parent, verified via `git rev-parse bda4327^`).

**Concurrent-session note:** the test fix above was drafted in a separate
background worktree session (`claude/hopeful-raman-df98df`) spawned mid-session
from this one. Reconciled by hand into this working tree before commit — diff
verified identical, worktree deregistered (`git worktree remove`) and its
branch deleted (`git branch -d`, no unique commits once merged) so this lands
as a single commit rather than two divergent ones.

**How you know:** Migration head confirmed unchanged
(`alembic heads` → `217dce22fbc5`, single head) — these reads add no schema.
`grep` over `_section_labs` and `render_asked_lab_value` confirms zero
`computed_flag`/delta/axis text reaches rendered output (only docstring hits
describing what's withheld). Dry-run backfill executed against Railway
production Postgres via the #56 public-proxy override, both before and after
generalising; connection verified live (not a silent SQLite fallback) by a
direct `SELECT COUNT(*) FROM lab_results` returning `0` both times (31 known
mappings checked post-generalisation, up from the 4 hardcoded originally).

**Do not revisit unless:** a `derived_from` source-link column is added to
`lab_results` (removes the recency-flag's role as a staleness proxy), Read 2
gets a real frontend consumer, or #49's interpretation view ships (swap
`_LAB_INTERPRETATION_VIEW_LABEL` for the real route/label at that point).

---

### 60. Hevy exercise-template resolver: default wins on title collision

**Decision:** `resolve_exercise(db, title, user_id)` (in
`backend/hevy_templates.py`) resolves a canonical exercise title to a Hevy
`exercise_template_id` against the synced store (#61), exact-title match only.
When a title exists as both a Hevy default and a user custom, the resolver
returns the default id (`ORDER BY is_custom ASC LIMIT 1`, filtered to
`is_custom = false OR owner_user_id = :user_id`). Otherwise the requesting
user's own custom; never another user's custom.

**Rationale:** Default ids are global/stable; custom ids are account-scoped.
Default-preference yields a portable, account-independent exercise vocabulary
suited to multi-tenant (B2B) use. Trade-off accepted: `exercise_history` may
split across ids for any title trained under a shadowing custom — surfaced by
the sync collision report (report-only, `_collision_report`), handled
case-by-case, not by the resolver. Fuzzy/normalised matching is an explicit
non-goal; loose-name provisioning is a separate decision if it ever arises.

**Status:** Landed on `feat/hevy-exercise-template-resolver`. Wired into the
`chat.py` `<hevy_create_routine>` path as an OPT-IN fallback: only exercises
missing a non-empty id but carrying a `title` are resolved; id-bearing
exercises pass through untouched (the path already receives ids). Activating
the AI to emit titles (a `context_builder` prompt change) is deliberately
deferred — it trips the context-builder byte-parity guard and is the separate
loose-name decision above.

**How you know:** Live recon against `GET /v1/exercise_templates` confirmed
default ids are 8-char UPPERCASE hex and custom ids are lowercase UUIDs, no id
reuse across the two spaces (493 templates, 451 default / 42 custom for the
recon account). 4 resolver unit tests green (collision→default, custom-only→
custom, other-user-custom→None, unknown→None) + 3 end-to-end provisioning tests
(title→id, id-passthrough, unresolvable-skip). Full suite 22 passed.

**Do not revisit unless:** Hevy changes id allocation such that a default and a
custom can share an id, or product decides shadowing customs (not defaults)
should win — in which case flip the `ORDER BY` and record why.

---

### 61. Hevy exercise templates persisted in a synced table (`hevy_exercise_templates`)

**Decision:** Exercise templates (defaults + per-user customs) are persisted in
a new `hevy_exercise_templates` table (migration `3497ab483935`, down_revision
`217dce22fbc5`) so the provisioning path never sources ids live. Keyed on the
Hevy `id` alone (`String(64)` — absorbs 8-hex defaults and UUID customs, no
composite key needed since ids don't reuse across the two spaces).
`owner_user_id` = app `users.id` (NULL for defaults); the Hevy template object
carries no owner field (confirmed live), so ownership is assigned at sync time
from the key's user for `is_custom` rows. Sync
(`sync_exercise_templates`) is per-user by stored Hevy key, upsert-only, keyed
on id; no delete reconciliation (the Hevy API cannot delete templates). Supersedes
the chat proposal that stored the Hevy account id as owner.

**Rationale:** A local store makes resolution (#60) deterministic and
offline-of-Hevy, decoupling provisioning from live API availability/rate limits.
`owner_user_id` on the app user (not the Hevy account id) is the identity the
resolver and multi-tenant model actually key on.

**Status:** Landed. Schema commit isolated from the sync/resolver feature
commits. NOTE: not yet applied to Railway — the migration was verified on a
SQLite copy stamped at the prior head; the prod-stamp check (Railway alembic
head == `217dce22fbc5`) must pass before this migration is pushed/deployed
(local-vs-Railway drift hazard; autogenerate surfaced unrelated drift that was
stripped from the migration).

**How you know:** `alembic upgrade`/`downgrade` clean on a DB copy at the prior
head; table schema verified (PK, FK CASCADE, both indexes). One full live sync
run: 493 rows written (451 default / 42 custom), owner assignment correct
(0 misassigned either direction), re-run idempotent (distinct rows stayed 493).

**Do not revisit unless:** Hevy adds a template-delete capability (then a
reconciliation/soft-delete pass is needed), or the store needs fields beyond
the synced set (`equipment` is available on the API object but intentionally
not stored yet).

---

### 62. SCHEMA.md promoted to repo-canonical; manual project-knowledge copy retired

**Decision:** `SCHEMA.md` is promoted to repo-canonical at the health-app root;
the manual project-knowledge copy is retired. `PLATFORM.md` was gated on public
commercial positioning and is **skipped this round** — it stays project-knowledge
only, and the prior non-mirrored-refresh rule applies to it alone (its ~8-line
stability makes manual refresh negligible).

**Rationale:** Repo-derived orientation that fell stale silently and couldn't be
edited in place, forcing manual download/swap. As a repo file it auto-mirrors into
project knowledge via Projects sync; Code maintains it at the point of change.
SCHEMA is kept in lockstep with `backend/migrations/` — the CLAUDE.md convention
(Repo-specific → Conventions) records the same-commit-or-immediately-paired rule.

**Status:** Landed at merge. `PLATFORM.md` deferred (not created).

**How you know:** `SCHEMA.md` present at master root; CLAUDE.md convention bullet
records the lockstep and sits below `END SHARED LOOP RULES` (shared-block diff vs
origin/master empty, so no cross-repo propagation); the manual project-knowledge
copy is deleted with no duplicate surfacing (Luke's step 6 — closes the loop).

**Do not revisit unless:** Projects sync stops auto-mirroring repo files, a doc must
diverge between repo and project knowledge, or PLATFORM.md's public-exposure gate
later clears (promote it then under its own entry).

---

### 63. Interpretation Output Contract v0.4 (group-primary) + two reference assets land as `ai_draft`

**Decision:** The interpretation layer's emitted shape is promoted to **group-primary**
(supersedes the marker-primary v0.3 shape). The interpretation unit is the **axis/group**;
a lone marker is a **group-of-one**. `#49` iterates groups. Flat top-level
`moved[]`/`stable[]` is replaced by `groups[]`, each carrying an **axis-verdict**, member
markers with per-member gates, group-level **relations** rendered on member lines
(author-group / present-marker), and **shared levers** with per-member effects.

The **two-gate safety model** is adopted as the structural `#47` resolution for
interpretation output: **gate 1 (is-this-news)** is delta-based and may consult
relations + axis-verdict; **gate 2 (is-this-out-of-range)** is absolute and
**non-suppressible** — no relation, axis-verdict, or phase-precondition may hide a breach,
at most annotate it as expected-by-phase or benign (`stable_rationale`). No directive
field anywhere; every lever carries `grade` + `grade_rationale` + non-empty `evidence_refs`.

Two composed reference assets land under `backend/reference/`, flagged `ai_draft`:
- `lever_dictionary.json` — GRADE-tiered lever **nodes** (group-agnostic) + per-marker
  read-constants (`min_meaningful_delta` with a `mode` amendment to `#53`).
- `marker_groups.json` — purely **relational**: membership/roles, the five relation kinds
  (ratio, co_movement, discriminator, feedback, context), `group_levers` with
  `member_effects`, and structural `derived_from` edges.

Both bind to `marker_canonical.json` v0.2 (`#57`, 31 ids). Markers not yet canonical
(`calcium`, `ck`, `hdl_cholesterol`, `non_hdl`) are parked under `_deferred` with their
exact blocking ids — nothing dangles — pending the 7-id vocab bump (0.2 → 0.3, separate
landing). The contract remains a **UI knowledge-file (orientation)**, not repo-canonical;
the canonical record is this entry and, when built, the code.

**Rationale:** `#49` fixed the conceptual design (delta-first, three sections, lever
filtering/tap); this fixes the emitted *shape* and closes the group-primary-vs-marker-primary
fork in favour of group-primary — a member line is self-explanatory (relations/lever
effects rendered against each marker) without the reader holding the whole axis in their
head, while relations and levers are authored once at group level. The two-gate split is
what stops the group model from becoming a channel that reasons a breach away: coherence
reads and range surfacing are orthogonal. Landing the assets as `ai_draft` unblocks the
interpretation module build while keeping the clinical-review gate explicit.

**Status:** Landed at merge (`feat/interpretation-base`, ff to master). Assets are
`ai_draft` — not clinically reviewed. `_deferred` groups/relations/edges stay parked on
the vocab bump. Contract v0.4 replaced UI-side (refs `#63`); Code never writes it.

**How you know:** Both JSONs parse (`python -m json.tool`); bindings gate green — 70 live
marker refs all resolve to the canonical 31, `bilirubin_total` (not bare `bilirubin`), all
4 orphans confined to `_deferred`, every `group_lever` has a node in `lever_dictionary.levers`;
I1 gate green — all 5 live levers carry non-empty `evidence_refs`. Pre: DECISIONS max 62,
both assets 404. Post: `backend/reference/{lever_dictionary,marker_groups}.json` present on
master, DECISIONS max 63. No migration in this landing (JSON + doc only).

**Do not revisit unless:** the marker-primary shape is reinstated, the `#47` education
boundary changes, the two-gate model needs a third gate, or the vocab bump promotes a
`_deferred` group/relation/edge (each under its own entry, keyed to the new canonical id).

---

### 64. Q4 resolved — canonical HC sleep-date is the LOCAL wake-date (`endTime`), aligning to the scraper

**Decision:** A Health Connect sleep session is attributed to the **local
(AEST / Australia/Brisbane) calendar date of its `endTime`** — the wake-date — and to that
day only. This matches the scraper (`samsung_hrv_readings`), which already keys the
wake-date; the scraper is unchanged. `_aggregate_day`'s former filter (`endTime==day OR
startTime==day`, longest-overlap) becomes a wake-date-only filter; the date-collection loop
enumerates the wake-date only; the `/sync` window upper bound is widened to AEST-today so
last night is not dropped as "future". Existing sleep values are nulled across all
`health_connect_syncs` rows by a data migration and repopulated by a post-deploy HCA
re-sync.

**Rationale:** The same physical night landed one calendar day earlier than the scraper —
`health_connect_syncs[date] ≈ samsung_hrv_readings[date+1]`, 0 same-date matches (Q4). Root
cause: bed-date attribution, compounded under UTC timestamps where a naive `[:10]` slice
collapses the whole night onto the day before the local wake. The fix converts to
Australia/Brisbane before taking the date via a new `_wake_date()` — correct whether the
`endTime` string is UTC-`Z`, UTC-naive, offset-aware, or local-naive (mirrors the
normalisation `context_builder` already applies), so it settles Q4's tz fork regardless of
the payload's actual shape. The `/sync` upsert only writes non-null values and so can never
clear the stale date-1 rows itself; the migration clears them. Blast radius = sleep only;
no other `_aggregate_day` field or upsert semantic touched. Backend-only.

**Status:** Landed at merge (`fix/hc-sleep-wake-date-attribution`, ff to master). Backfill
migration `f4e1a2b3c6d7` co-lands and auto-applies on Railway deploy; the operational
re-sync (Luke, post-deploy) repopulates correct wake-dates. G4 (same-date sleep⇄scraper
verification) is **deferred to the live re-sync** — Railway was unreachable this session, so
Q4 is marked `verifying`, not `resolved`, until G4 passes on live data.

**How you know:** 7 new unit tests green (`tests/test_health_connect_sleep.py`) — a
midnight-spanning UTC night attributes to the wake-date and NOT the bed-date; a same-day nap
does not displace the main night; `_wake_date` returns the correct AEST date for UTC-`Z`,
UTC-naive, offset-aware, nanosecond-fraction, and local-naive strings. Full backend suite
29/29 green. Migration upgrades + downgrades (no-op) cleanly on a DB copy; alembic reports a
single head (`f4e1a2b3c6d7`). Pre: DECISIONS max 63. Gate-0 (UTC-vs-local) was **not**
settled by a live Railway query — no creds this session, local sqlite holds no sleep rows —
so the fix is deliberately made tz-shape-agnostic to be correct under either fork; the Q4
signature (consistent, exceptionless date-1 shift, 0 same-date) and the dual-write code
collapsing to a single date-1 row both point to UTC timestamps.

**Do not revisit unless:** the scraper's date convention changes, HCA begins sending a
timestamp tz shape the AEST conversion mis-dates (re-check with a real payload), the
platform serves a non-AEST user (`Australia/Brisbane` is hard-coded, matching
`context_builder`), or the G4 post-re-sync check still shows a date offset.

---

### 65. Hevy create-loop resolves app-originated customs via list-back-always

**Decision:** App-originated custom-exercise creation resolves the new template's
canonical id by re-pull-and-match (list-back) — create → sync → resolve within the
custom subset — never by trusting the POST /v1/exercise_templates response body. The
create response's id representation (int vs UUID, Q14) does not gate the build; it is
at most a deferred micro-optimisation (skip the re-pull) and is out of scope here.

**Rationale:** hevy_exercise_templates already keys rows on the canonical Hevy id and
is kept fresh by a full-catalogue sync (#61); a create-loop is therefore create → sync
→ resolve, and the re-pull that reads the canonical id from GET happens regardless of
what POST returns, because the store is refreshed anyway. That makes Q14's int-vs-UUID
fork moot for the build. List-back must match within the custom subset (is_custom=True
AND owner_user_id=user_id): a bare-title match against a same-named default would return
the default's id under #60 default-wins, not the new custom's — the one representational
hazard that survives. No schema change; existing HevyExerciseTemplate columns suffice.

**Status:** Landed at merge (`feat/hevy-create-loop`, ff to master). Resolves Q14 →
this entry (list-back-always; POST-response representation deferred, not a How-you-know
blocker). No migration; SCHEMA.md untouched. Q14's empirical fork is settled from the
live OpenAPI spec, not a throwaway live create: the spec types the POST response
`{"id": <integer>}` while GET/ExerciseTemplate types `id` as a string UUID — so POST
cannot carry the canonical id, and the re-pull is load-bearing, not optional.

**How you know:** Request-body shape read from the live spec's
`CreateCustomExerciseRequestBody` (inlined `swaggerDoc`, `api.hevyapp.com/docs`): the
body is WRAPPED — `{"exercise": {title, exercise_type, equipment_category, muscle_group,
other_muscles[]}}` — NOT the flat fields the brief assumed; the connector was adjusted to
wrap before landing. Unit tests (`tests/test_hevy_create_loop.py`, faked client, no live
API): a pre-existing default and the user's own custom each short-circuit create
(default-wins pre-check); an absent title round-trips create→sync→resolve to the new
custom's canonical UUID; list-back stays within the custom subset and does NOT resolve to
a same-titled default (`SLEDDEF1` vs the new UUID, with bare `resolve_exercise` proven to
return the default); 403 exceeds-custom-exercise-limit and 400 surface as typed
`HevyCustomExerciseLimitError` / `HevyBadRequestError`; a bounded retry (3 attempts,
exp backoff) covers a first-GET-miss-then-hit; created-but-unresolved raises
`HevyCreateUnresolvedError`, never returns None. Full backend suite 38/38 green. Pre:
DECISIONS max 64.

**Do not revisit unless:** Hevy adds a title filter to GET (targeted re-pull replaces
full sync), exposes a delete endpoint (reconciliation becomes possible), or the POST
response is later confirmed to carry the canonical UUID and the re-pull is optimised
away (the deferred Q14 micro-opt).

---

### 66. Connector failures decouple from session auth — downstream 401→424, read handlers never leak raw exceptions

**Decision:** A connector (Hevy/Polar) failure must never surface as a session-auth 401 or
an unhandled 500. `_hevy_error_to_http` remaps `HevyAuthError` 401→424;
`hevy_workout_count`/`hevy_workouts`/`hevy_workouts_all`/`hevy_get_routines` now catch
`httpx.HTTPStatusError` → helper (502); `polar.py` token-refresh failure 401→424. A global
`Exception` handler (`cors_errors.add_cors_error_handler`) guarantees any residual 500 still
carries CORS headers. Frontend `api.js` interceptor unchanged — correct by construction once
no connector path emits 401. Step 4 global 500 CORS guard: **LANDED** on this branch (verified
not fiddly).

**Rationale:** Two symptoms traced to one leak — (a) a revoked Hevy key returned 401 →
`api.js:16` "any 401 → clear token → /login" logged the user out; (b) `page_size=20` exceeded
Hevy's `/workouts` pageSize ceiling → Hevy 400 → `_check` raised `httpx.HTTPStatusError` →
uncaught in the read handler → FastAPI 500 → response bypassed CORSMiddleware → browser reported
"No Access-Control-Allow-Origin". Both are the same leak: a connector failure escaping as a
session/transport error. Fixing at the backend choke point makes the untouched frontend
interceptor correct by construction. The global handler closes the residual-500 class for any
future endpoint, since Starlette's `ServerErrorMiddleware` sits outside `CORSMiddleware`.

**Status:** Landed on `feat/connector-error-policy`. No schema change; SCHEMA.md untouched.

**How you know:** Backend tests (faked client, no live API — `tests/test_connector_error_policy.py`)
assert 424 on `HevyAuthError` and 502 (not an unhandled 500) on `httpx.HTTPStatusError` across
all read handlers including the new `/workouts/all` aggregator; 403 (`HevyForbiddenError`)
unchanged; Polar token-refresh failure returns 424; and a forced unhandled exception returns 500
*carrying* `Access-Control-Allow-Origin` for an allowed origin (none echoed for a disallowed
origin) — proven by unit test and empirically against the real `main.app` via a temporary
raising route inserted ahead of the `/` mount. Session-origin 401s confirmed by grep to live only
in `auth.py`/`routers/auth.py` (`get_current_user`/login) — `connectors/hevy.py:33` is the raw
401→`HevyAuthError` conversion, not an HTTP status — so the remap cannot weaken session auth.
Full backend suite 56 green. Pre: DECISIONS max 65.

**Do not revisit unless:** a connector failure legitimately needs to force session re-auth (then
424 is wrong for that path specifically), or Hevy/Polar change their error-status semantics.

---

### 67. "See all" = genuinely all workouts via a server-side page-loop aggregator

**Decision:** "See all" in Training Data means the full workout history, not one page. New
endpoint `GET /integrations/hevy/workouts/all` (`HevyClient.get_all_workouts`) walks every Hevy
`/workouts` page and concatenates; frontend `openHevyHistory` (`WorkoutPanel.jsx`) calls it
instead of the old single-page request. The briefed top-10 stopgap (`page_size` 20→10) was NOT
taken — the product call (Luke) was true pagination.

**Rationale:** Hevy caps `/workouts` `pageSize` at 10, so the old `page_size=20` request exceeded
the ceiling and produced the fake-CORS 500 of #66; a single page can never be "all". Genuine "all"
requires a server-side loop. The aggregator terminates on `page_count` and, defensively, on an
empty batch, so a missing/short `page_count` cannot hang it.

**Status:** Landed on `feat/connector-error-policy` (same branch as #66). Endpoint registered;
frontend rewired. Open issue #13 updated — the control fires and now returns the full history; the
"dead handler" description is superseded (the handler was wired; the live bug was the pageSize
ceiling masquerading as CORS).

**How you know:** Hevy `/workouts` pageSize ceiling = 10, confirmed authoritatively from the
connected Hevy MCP tool schema (`get-workouts` constrains `pageSize` `maximum: 10`), so
`page_size=20` is over the ceiling. Aggregator unit tests (faked, no live API —
`tests/test_hevy_workouts_aggregator.py`): concatenates a 3-page catalogue in order; a single page
makes exactly one call; an empty batch terminates the loop even when `page_count` over-promises;
no-workouts returns an empty list. The `/workouts/all` handler's error routing (424/502) is covered
with the other read handlers. Frontend `npm run build` green; route registration confirmed. NOT
verified: live end-to-end "See all" against a real Hevy account — the connected Hevy key is
invalid/expired (the exact revoked-key case #66 addresses), so the raw live 400 body could not be
captured this session; the ceiling proof rests on the tool schema, not a live 400. Full backend
suite 56 green. Pre: DECISIONS max 65.

**Do not revisit unless:** Hevy raises the `/workouts` pageSize ceiling (single-call path becomes
viable) or moves to cursor pagination (replace the page loop), or full-history fetch grows too
heavy at scale (add server-side caching or lazy UI paging).

---

### 68. Hevy summary parity — `get_hevy_workouts` restored to the signal context_builder already carries; set-type field bug fixed

**Status:** Landed on `feat/hevy-summary-enrichment`. `get_hevy_workouts` (`mcp_server.py`) now
reads the set-type field as `type` (was `set_type`, a dead no-op that never filtered warmups),
renders warmup sets labelled, and surfaces per-set RPE, multi-line exercise notes, workout
description, and duration/distance-only sets — reaching parity with `context_builder`. e1RM
computed from non-warmup sets only. Set formatting was **extracted to a shared `backend/hevy_format.py`**
(`format_set`/`format_duration`) consumed by both `context_builder._section_hevy` and
`get_hevy_workouts`, so the two can no longer drift on field reading (that duplication is what bred
the `set_type` bug). Per Luke's fork calls: shared-module extraction (not in-place), the discovered
extras included (description + duration/distance sets, not just RPE/notes/warmups), and
`get_hevy_workouts` adopts `context_builder`'s verbose per-set layout (one line per set, not the old
compact one-line-per-exercise). `context_builder._section_hevy` also gained the workout-level
`description` for symmetry (Step 3 top-up). `health.py` unchanged (already correct).

**How you know:** The impoverished summary was traced to `get_hevy_workouts` reading `set_type`
while `context_builder._format_set` and `health.py:71` read `type`. Gate 0 ran a **live raw
`HevyClient.get_workouts()` pull** (snake_case payload) that confirmed the set-type field is `type`
and that `rpe`/`notes`/`duration_seconds`/`distance_meters`/`description` are all present in the raw
object — so the summary was walking past fields sitting in the payload, not fields the API withholds.
(The app-stored Hevy key was invalid/expired, so the raw pull used a throwaway key supplied for the
gate; the `hevy:*` MCP was NOT used to pin names because it renames fields, e.g. `weight_kg`→`weight`.)
The 10 Jul workout made the stakes concrete: right/left RPE+load asymmetry (right Bulgarian Split
Squat hit RPE 10 at 35kg, rep fell to 9, dropped to 30kg while left held 35kg at RPE 8) and three
injury-watch notes (left-knee click, right SL-RDL discomfort, right step-up valgus) lived entirely in
the dropped fields — a live before/after render confirmed all now surface and three whole movements
(Air Bike, Suitcase Carry, Copenhagen Plank) that rendered blank now appear. Faked-payload tests
(`tests/test_hevy_summary_enrichment.py`, 9 tests) cover warmup labelling + e1RM exclusion (heavier
warmup proves the filter), half-point RPE, multi-line notes, duration/distance sets, all-warmup
exercise retention, and description present/absent. Full backend suite 65 green. Pre: DECISIONS max 67.

**Do not revisit unless:** Hevy changes its GET /workouts set-object field names, or the two
summarizers need to diverge in field-reading again (they should not — that divergence is what
this entry closes).

---

### 69. Q16 resolved — Hevy exercise-history path is `/v1/exercise_history/{id}`, not `/exercise_templates/{id}/history`

**Status:** Landed on `fix/hevy-exercise-history-path`. `HevyClient.get_exercise_history`
(`backend/connectors/hevy.py`) now calls `GET /v1/exercise_history/{template_id}`. The `{id}`
segment is still the exercise **template** id — no caller signature change. The prior shape
`/exercise_templates/{id}/history` 404'd since ship. Resolves Q16.

**Rationale:** Canonical Hevy path. The path is the only change; the request stays a plain
authenticated GET keyed by template id, so the fix is a pure endpoint correction with no
payload or signature churn. The `/v1` prefix comes from the `HEVY_BASE` join
(`https://api.hevyapp.com/v1` + `/exercise_history/{id}`) — present once, not doubled, not dropped.

**How you know:** Verified chat-side against official Hevy docs plus **3 independent current
clients** that all use `/exercise_history/{id}`: hevy-api-wrapper 1.0.0, chrisdoc/hevy-mcp, and
an OpenClaw endpoint enumeration. **Pre-merge caller audit:** `git grep '\.get_exercise_history('`
returned **zero call sites** — the method is currently unwired, so correcting a silent-404 into
real history introduces no downstream silent-behaviour-shift (the risk the audit existed to catch).
Full backend suite 65 green post-fix (no test exercises this path — none exists; doc-evidence is
the basis). Live `exercise_history` corroboration was blocked this session (local Hevy MCP hung);
flagged as optional belt-and-braces later, not gating. Pre: DECISIONS max 68.

**Do not revisit unless:** Hevy relocates the exercise-history resource again, or a live pull
against `/v1/exercise_history/{id}` returns non-200 for a valid template id (would reopen Q16 with
an empirical negative, superseding the doc-evidence basis).

---

### 70. Ingest bounds guard for `samsung_hrv_readings` — out-of-range biometrics nulled-and-logged

**Status:** Landed on `fix/hrv-sleep-integrity` (HRV & Sleep Data Integrity brief, Task 3).
`routers/samsung_hrv.py` gained a `model_validator` over a `_BOUNDS` table covering every numeric
field (percentages 0–100, minutes 0–1440, plus HRV / sleep-HR / RR / SpO2 physiological ranges). An
out-of-range value is **nulled and logged** (`logger.warning` with field/value/bounds/date), not
clamped — clamping fabricates a plausible number, nulling is honest that the datum is unusable.
Per-field, so one bad field never drops the night's valid data.

**Rationale:** The canonical trigger was `2026-06-28: Eff=119%` — a hard impossibility that the
pipeline ingested faithfully because nothing bounded it. The brief's "if efficiency is unbounded,
assume other fields are too" is satisfied by bounding the whole schema in one guard rather than
patching efficiency alone. Null-over-clamp chosen because 119%→100% would assert "perfect efficiency"
(itself wrong — the source calc is broken), whereas null says "not trustworthy," consistent with the
source/confidence-tagged schema philosophy.

**How you know:** 7 targeted tests (`tests/test_samsung_hrv_bounds.py`) cover efficiency>100 nulled,
boundary 100 valid, valid value survives, out-of-range field does not drop valid siblings (HRV/RHR
kept), all five percentage fields bounded, negative minutes nulled, absurd HRV/RR nulled. Full backend
suite 74 green (was 65; +7 bounds, +2 readiness). **History sweep NOT run from this session** — the
local `DATABASE_URL` is SQLite (dev), with zero production rows; the sweep must run against Railway
Postgres (SQL supplied in the session report). Pre: DECISIONS max 69.

**Do not revisit unless:** a legitimate reading is found to fall outside a `_BOUNDS` range (widen that
bound, don't drop the guard), or the schema gains a `confidence` column making low-confidence retention
preferable to nulling.

---

### 71. Deep-sleep minutes excluded from daily readiness — Samsung Ring deep/light discrimination is not fit for a daily term

**Status:** Landed on `fix/hrv-sleep-integrity` (HRV & Sleep Data Integrity brief, Task 4). The daily
readiness input to the coaching model is the sleep architecture rendered in `context_builder.py`
(nothing gates on an automated composite — DECISIONS #8). Both sleep sections
(`_section_samsung_hrv`, `_section_health_connect`) now report **combined `Deep+Light`** instead of
standalone Deep and Light. REM, awake, sleep efficiency, total sleep time, and SpO2 are retained
unchanged. Deep alone remains queryable as a long-run trend series via `get_recovery_metrics`
(untouched) — never as a daily term.

**Rationale:** Observed split Deep 3% / Light 70% (typical 15–20% / 50–55%) with the ~15 missing deep
points appearing as the ~15 surplus light points — a **complementary two-class confusion signature**,
not physiology. Deep appears as sub-5-minute spikes dispersed across the night with nothing in the
first cycle, the opposite of homeostatically front-loaded slow-wave sleep. The deep/light *boundary*
is unreliable but their *sum* is robust (the confusion is internal to the pair), so `Deep+Light` is
retained as the trustworthy aggregate.

**How you know:** Physiological confounders excluded at source: OSA fully controlled on CPAP at AHI 0.4
(threshold <5) — below 1 event/hr there is no arousal load to suppress SWS; and active CBT-I sleep
restriction should *elevate* SWS, so the observed flattening is the opposite of what the protocol
predicts. Pipeline faithfulness confirmed independently: MCP reported 16m deep / 91m REM vs the Samsung
app's 16m / 1h31m — exact match, so the number is ingested correctly and simply wrong at source. 2 targeted tests
(`tests/test_readiness_sleep_stages.py`) assert both sections render combined `Deep+Light` with REM/awake
retained and no standalone deep/light term. Full backend suite 74 green. Pre: DECISIONS max 69.

**Do not revisit unless:** Samsung ships a deep/light classifier fix (verify against a night with a
normal 15–20% deep fraction and first-cycle SWS concentration before restoring deep as a daily term),
or the ring is replaced by a device whose stage discrimination is validated.

---

### 72. Restrictions are set at injury onset; the check-in monitors, it does not gate

**Status:** Landed on `feat/constraint-consumption` (constraint-consumption brief, Steps 1–4). AM
check-in soreness items now derive from the active injury ledger (`checkin_v2.derive_soreness_items`),
injury entries may carry a `trajectory` in their JSON `value` (no schema change), and
`injury_trajectory.evaluate()` surfaces two flags in `get_readiness_snapshot` — **divergence**
(observation contradicts the declared shape) and **symptom-gated review** (soreness reaches the exit
condition). `is_contraindicated` is unchanged and stays boolean.

**Rationale:** Rejected mapping daily soreness severity to graded restrictions (a severity→restriction
table, thresholds, or a non-boolean `is_contraindicated`). That would re-derive every morning a
decision already made once — with a mechanism and a plan — at injury onset. The restriction belongs to
the injury entry (`restrictions[]`, enforced by `selection.py`); soreness does not renegotiate it. The
check-in's job is narrower: contradiction detection (observation diverges from the plan's expected
trajectory → surface for revision) and status appraisal against the exit gate (symptom-gated review).
Both surface; neither gates. Consequence: injury entries must carry an expected trajectory — without it
there is nothing to contradict. Step-1 encoding adjudication folded in: the right hamstring is recorded
`signal_type:"mechanical"`, **not** `"neural"` — a `neural` signal fires `selection.py`'s signal-wide
radicular block (hinge/rotation/carry/gait), which would contraindicate the wanted SL-RDL
desensitisation lane, while the actual aggravator (static end-range stretching) is not a taxonomy
region and cannot be engine-gated regardless; the neural finding is surfaced via `detail`. Two distinct
hamstrings confirmed (functional left; structural right proximal semimembranosus) — recorded as
separate entries, not a side-amendment of the left.

**How you know:** Empirical exclusion-set probe over all 30 taxonomy regions — `neural` blocks 9 regions
including `hinge` (reason "radicular sign — provoking pattern"), body-part-agnostic; the `mechanical`
right hamstring blocks only the acute-tissue set and leaves `hinge` open both sides (SL-RDL preserved).
Step-3 evaluator verified against the **real seed trajectory** (not a fixture): review fires at soreness
≤1 sustained 3d, settling-divergence on a rising series, stable-divergence on a +2 move, quiet case
silent (no false positives). 74 backend tests green. Local sqlite read-back only — **live Railway seed +
`get_readiness_snapshot` read-back OWED** (MCP connector invalidated this session; #42 precedent). Pre:
DECISIONS max 71.

**Do not revisit unless:** a graded/continuous contraindication is genuinely needed (a non-boolean
`is_contraindicated` with a severity→restriction mapping) — at which point re-open the "restrictions set
at onset" premise deliberately, not by letting daily soreness quietly re-derive it.

**Withdrawn (never committed):** the prior in-chat draft on additive-checklist regulatory scope is void.
It answered a question that existed only because the app was believed to have prompted contraindicated
hamstring stretching; grep refutes (no such string in the tree) and no user-facing checklist module
exists in this repo. Fabricated premise, no decision required — recorded so the withdrawn draft does not
resurface.

---

### 73. Soreness scoring generalises across body parts; max, not shoulder-only

**Status:** Landed on `feat/constraint-consumption`. `calc_naive_baseline`'s soreness term is now **MAX
across all reported soreness items** (was `soreness["shoulder"]` only), retaining the single 0.20 term,
the (v−1)×2.5 scale, and the 1–10 clamp. Default 3 (neutral) when nothing is reported.

**Rationale:** The readiness baseline was structurally blind to both of the user's active injuries —
hamstring soreness was captured and never scored. Max over mean: mean dilutes (a severe single site
averaged against quiet sites under-reads). The scalar answers "how beat up overall"; movement-specificity
is `restrictions[]`'s job, not the score's. Known limitation: multi-site cumulative load is invisible
(max, not sum).

**How you know:** knee soreness now moves the baseline (7.9 at knee=1 → 5.9 at knee=5; previously zero
effect). Discontinuity characterised old-vs-new on fixed sleep/fatigue/motivation: hamstring 5 / shoulder
1 → **−1.00** (the "captured, never scored" bug fixed), derived-default keys → **+1.00** (old
absent-shoulder default-3 penalty removed), legacy `{shoulder:2,hamstring:1}` and empty `{}` → 0. 74
tests green.

**Discontinuity disposition:** accept-and-annotate, **NOT backfilled** — `naive_baseline` is
frozen-at-capture (recomputing corrupts the `model_forecast`-vs-baseline reference the field exists for);
no backfill without sign-off per the brief. Historical shoulder-only values stand; the changeover is
annotated in code and here.

**Do not revisit unless:** multi-site cumulative load proves to matter (move from max to a saturating
sum), or the frozen-baseline comparison is retired.

---

### 74. Exercise movement-taxonomy is app-owned annotation, stored separately from the Hevy-synced catalogue

**Status:** On branch `feat/exercise-catalogue-taxonomy` (pending land; number claimed from max 73 — no
competing branch carries a pending DECISIONS entry). New table `exercise_region_tags` (keyed on the Hevy
template id, FK CASCADE, many-to-many with explicit `role`, validated against `engine/taxonomy.py`,
versioned to `TAXONOMY_VERSION`) + a `hevy_exercise_templates.laterality` column. `infer_loaded_regions`
rewritten from a substring matcher to a table join; the keyword map is demoted to an INSTRUMENTED
fallback for untagged templates only. Migration `b2f1c9a4d7e8`.

**Rationale:** The system's only exercise→region map was `_LOADED_KEYWORDS` (~30 substring rules, no
break on match, no laterality) and it is materially wrong on live data (see FEEDBACK §7). Tags live in a
SEPARATE table because `hevy_exercise_templates` is upsert-from-Hevy-sync (`_upsert_template`) and
clobber-exposed on every resync — separation also splits Hevy-owned data from app-owned annotation.
Many-to-many is deliberate (Suitcase Carry = carry + anti_lateral_flexion); `role` makes primacy explicit
(the bug was *unintentional* multi-match with no primacy, e.g. Pallof firing both anti_rotation AND
rotation). Plane/capacity are NOT duplicated — `Region` already carries them and region_key derives both.
`laterality` is an exercise-level property NOT derivable from the taxonomy and load-bearing for plan↔log
reconciliation (a unilateral movement logs as two sided Hevy entries). Validation is fail-closed: an
orphan region_key is refused, never stored.

**How you know:** GUARD-1 premise reproduced EMPIRICALLY against the user's last-90d Hevy history (20
workouts, 2026-05-26..07-13): Copenhagen Plank (Short Lever)×9 → `trunk_stability_sagittal` (frontal work
mistagged sagittal); Cable Twist×6 → `[]` (loaded rotation unseen); Single Leg RDL×2 → `hinge` (laterality
lost); and stronger than the brief — Shoulder External/Internal Rotation×22 → false `rotation` (a
`_RADICULAR_BLOCKS` region), and ~41% of distinct titles hit the empty fallback. 12 new tests pin the four
documented failures + the Shoulder-Rotation neutralisation + back-compat + fallback instrumentation +
orphan fail-closed; G5 clobber test proves tags + laterality survive a full `_upsert_template` resync.
Full backend suite green (74 → 86 tests). Signature deviation: a table lookup needs a Session, so
`infer_loaded_regions` gained an optional `db=None` keyword — return type (`set[str]`) and positional
contract unchanged; both call sites (`chat.py`, `engine.py`) already had a Session in scope. Migration
applies clean on a fresh DB; local SQLite chain is pre-broken by an older `ALTER` migration (Postgres-only,
unrelated). **Owed:** Railway `alembic upgrade head` + human-confirmed seed of the active-window tags +
live-resync clobber confirmation.

**Do not revisit unless:** the tags are promoted to a source-agnostic canonical exercise layer (OPEN_QUESTIONS
Q22) or the taxonomy vocabulary changes (bump `TAXONOMY_VERSION`, re-tag).

---

### 75. The Plan layer WRAPS the Adaptive Exposure Engine; it does not supersede it

**Status:** Ratified by Luke in chat this session. Logged, NOT built — this is the governing frame for the
Plan schema work (steps 2–4 of the exercise-catalogue sequence), constraining all of it. Number claimed
from max 73.

**Rationale:** `capability_state` and `fortification_profiles` survive intact, demoted from
session-composer to slot-filler and template-shaper. The Plan owns cycle / slots / cardinality; the engine
still supplies probe/fortify region selection *within* slots. This must be minted before any Plan schema
work so that work does not accidentally re-architect the engine it is meant to wrap.

**How you know:** design decision ratified in chat; no code artifact this session (this brief deliberately
does not build to it — it only records the frame).

**Do not revisit unless:** Plan schema work begins and the wrap boundary proves wrong in practice.

---

### 76. Tag coverage is three-state (tagged / adjudicated-no-pattern / untagged) via `adjudicated_at`

**Status:** On branch `feat/tag-adjudication-three-state` (pending land; number claimed from max 75).
Refines #74's coverage model. New nullable column `hevy_exercise_templates.adjudicated_at` (migration
`c3a2d8e5f109`), set ONLY by the `--confirm` seed. `infer_loaded_regions` gains the third state. Resolves
OPEN_QUESTIONS Q26 as option (b).

**Rationale:** "We looked and it maps to nothing" and "we never looked" are epistemically different and the
system must not collapse them — the same untested-vs-normal discipline already ratified on the labs side
(an untested marker is not a normal marker). Redefining coverage as "zero *wrong* tags" (option (a)) quietly
forfeits the ability to detect a real coverage gap later. So three states:

- **tagged** — ≥1 `exercise_region_tags` row → those regions load.
- **adjudicated no-pattern** — `adjudicated_at` set, zero tag rows → contributes nothing DELIBERATELY (an
  isolation, or a joint-level STRENGTH lift v0 has no axis for).
- **untagged** — `adjudicated_at` NULL → keyword fallback, counted and logged.

G2 stands UNSOFTENED: 100% of active-window templates adjudicated (tags + no_pattern), fallback hit-count 0.
Adjudication is a TIMESTAMP on `hevy_exercise_templates`, NOT a sentinel `region_key` — region_key's
fail-closed validation stays intact (a sentinel would weaken the guard). `adjudicated_at` is stamped only on
`--confirm`, so `adjudicated_at NOT NULL` ⟺ human-confirmed adjudication — that is G2's "human-confirmed"
signal for no-pattern templates, which carry no tag-row `source`.

**REJECT calf raise → ankle_df.** Category error: plantarflexion STRENGTH tagged as dorsiflexion MOBILITY
would mark a live Tier-B screening region as demonstrably loaded on the exact opposite movement AND suppress
probing of ankle DF (same failure class as Shoulder-Rotation → rotation, less frequent). → no-pattern. Four
families are adjudicated no-pattern *interim* — calf (plantarflexion), shoulder ER/IR (ER:IR ratio), Copenhagen
(adductor strength), hip add/abd (adductor:abductor) — all BLOCKED on the v1 strength-ratio axis (Q27), not
judgment calls. Do NOT bump the taxonomy inside a tag confirmation: it is external-authority and versioned so
its breadth does not inherit the user's blind spots; adding a region because the user logs a machine is the
tail wagging the dog. v1 is its own grounded design pass (Q27).

**How you know:** 13 tests in `test_exercise_region_tags.py` — the three-state distinction (adjudicated
no-pattern is covered + silent; untagged is a counted coverage gap), Copenhagen and Shoulder-Rotation now
adjudicated no-pattern (wrong → empty; the false `rotation` on a `_RADICULAR_BLOCKS` region killed), and the
G5 clobber test now also asserts `adjudicated_at` survives a resync. Full backend suite green (86 → 87).
Migration `c3a2d8e5f109` is head; `_upsert_template` never assigns the column (resync-safe, as with laterality).

**Do not revisit unless:** the v1 strength-ratio axis (Q27) lands and the interim no-pattern templates get real
regions, or a genuine accessory-sentinel need emerges that the timestamp cannot express.

---

### 77. Hevy template sync is activated at the OPERATOR (CLI) layer only

**Status:** On branch `fix/hevy-template-sync-activation` (pending land; number claimed from max 76). New
operator CLI `backend/sync_hevy_templates.py` (asyncio wrapper, `--user-id` safety valve, non-zero exit on
empty/partial). `sync_exercise_templates` gains per-user error isolation + a loud empty-user-list signal.
`seed_exercise_region_tags.py` gains an empty-substrate precondition gate. NO HTTP endpoint — the
request-layer wiring stays dormant, unchanged from #60/#61.

**Rationale:** The whole template subsystem (resolver #60/#61, `create_and_resolve` #65, catalogue tagging
#74/#75/#76) sits on `hevy_exercise_templates`, which is populated ONLY by `sync_exercise_templates` — and
that function had ZERO wired call sites. Verified against the tree: no router reference, no `main.py`
lifespan hook (lifespan only runs the MCP sub-app), no scheduler/APScheduler, no Railway cron (Procfile and
`railway.toml` startCommand = `alembic upgrade head && uvicorn` only); the sole runner was the module's own
bare `__main__`. Prod `hevy_exercise_templates` has zero rows, so three landed-green features are
structurally inert and the seeder would resolve 40/40 titles to None and exit 0. Sync must therefore be an
explicit, observable, NON-ZERO-EXITING operator operation, not an implicit request side-effect. Per-user
isolation: a single dead key (`_check` raises `HevyAuthError` on 401 — not swallowed, not returned as `[]`)
previously aborted the whole multi-user loop, and with `sync_one_user`'s per-page commit that left a
partial, committed store and no summary (the exception ate it).

**How you know:** 7 tests in `test_hevy_sync_activation.py` — one-key-raises isolation (users_failed=1, error
captured, loop continues, no exception escapes), empty-list WARNING + `users_synced=0` + CLI exit 1, seeder
refuses on an empty store and writes nothing, `--user-id` syncs exactly one user (no other user's sync runs),
and the exit-code matrix (empty/partial → 1, clean → 0). Full backend suite green (87 → 94). CLI `--help`
verified. GUARDs confirmed: `_check` raises `HevyAuthError` on 401 (does not return `[]`); `_upsert_template`
is field-by-field idempotent; `HevyExerciseTemplate.synced_at` has no downstream consumer so its per-sync
refresh is harmless.

**Do not revisit unless:** a scheduled/automated sync is wanted (a separate request-layer / job decision), or
the request-layer dormancy is deliberately lifted.

---

### 78. MarkItDown adopted as the document→markdown ingestion path — deterministic, with recorded table-structure limits

**Status:** On branch `chore/markitdown-mcp` (pending land; number claimed from max 77). Machine-local tooling only —
no repo code, no migration. `markitdown` MCP registered at **user scope** (`uvx markitdown-mcp` → `~/.claude.json`,
outside the repo); CLI installed as `markitdown[pdf,docx,pptx,xlsx,xls]==0.1.6` (`python -m markitdown`, shim not on
PATH). Claude Desktop `claude_desktop_config.json` entry attempted but **the running Desktop app rewrites that file
from its own in-memory model and drops out-of-band edits** — durable registration there requires the Desktop
Settings → Developer → Edit Config UI + restart (operator step, not landed here). CLAUDE.md repo-canonical Tooling
section documents the two paths, the >~30pp→CLI-to-disk threshold, and the limits below.

**Rationale:** PDFs/Office documents (TGA guidance, AS/NZS standards, council specs, clinical papers) processed
natively by Claude incur vision-token cost and extract tables non-deterministically. MarkItDown converts them to
markdown *deterministically* (two paths verified byte-identical modulo line-endings) at a fraction of the cost —
a 79pp born-digital TGA guidance PDF = 35,545 tokens as clean text (`tiktoken cl100k`). Two paths so the >~30pp
case converts to disk and is read selectively rather than dumped into context. User scope, not project `.mcp.json`:
the tool is cross-project, not a health-app dependency. `[all]` extra rejected — unsatisfiable on Python 3.14 (its
`onnxruntime<=1.20.1` pin, audio-only, has no 3.14 wheel); the document extras carry every PDF/Office converter.

**How you know:** Step-6 gate ran BOTH paths on three real PDFs. (1) 79pp TGA guidance (the target class): `cid=0`,
both paths identical, clean readable text — BUT genuine tables **flatten to linear text**: "Table 1. Prominence of
active ingredients" (2-column Permitted/Not-permitted matrix) rendered as a flat cell list with the column pairing
lost. MarkItDown's PDF path is pdfminer *text* extraction — no table-structure detection. (2) OEM operators manual:
clean text but pdfminer over-segmented prose into spurious multi-column GFM tables (1782 fake rows). (3) OEM parts
manual: broken font encoding (no ToUnicode CMap) → ~118 lines of `(cid:NN)` garbage; text-extraction cannot OCR
what native vision could. Verdict: deterministic + clean + cheap on born-digital prose; NOT faithful on structured
tables or scanned/garbled sources. Adopted as the DEFAULT ingestion path WITH those limits recorded, native-vision
fallback for structure-critical tables and scanned/broken-font PDFs.

**Do not revisit unless:** a table-aware backend is wanted (`az-doc-intel` — Azure Document Intelligence — is the
upgrade path, needs an Azure endpoint/key), or a target-corpus document is found where the flattening loses
information native vision would have kept, at which point the fallback becomes the rule for that class.

---

### 79. Exercise-tag reference titles are keyed to the CURRENT catalogue, never to logged workout titles

**Decision:** `reference/exercise_region_tags_v0.json` is keyed on the title as it exists in the live Hevy
CATALOGUE (`hevy_exercise_templates.title`), never on the title a workout was logged under. Corollary: tag
coverage is measured on `exercise_template_id`, never on title — hence the new read-only
`backend/audit_exercise_tag_coverage.py`. No migration, no schema change.

**Rationale:** the reference is keyed on exercise TITLE, and `resolve_exercise` is an EXACT byte-match against
`hevy_exercise_templates.title` (fuzzy matching is an explicit non-goal, #60). But a Hevy WORKOUT carries a
snapshot of the title as it was when logged, and Hevy renames its default templates. The two title spaces
therefore drift. The reference must track the CATALOGUE, not the workout log. A title-keyed audit would report
coverage that the id-keyed join in `infer_loaded_regions` does not actually deliver, in either direction.
The first prod seed proved the DATA is present; it did not prove the keyword fallback stopped firing — those
are different claims, and only the second is what coverage means.

**How you know:** first prod seed (2026-07-14, user 1, 494-row substrate, alembic head `c3a2d8e5f109`) resolved
55/56 titles; the sole miss was `Bulgarian Split Squat`. The live catalogue holds NO template with that bare
title — only `Bulgarian Split Squat (Barbell)`, `Bulgarian Split Squat (Dumbbell)` (id `B5D3A742`, default,
`length(title)=32`, byte-verified), and `Split Squat (Dumbbell)`. Yet the user's Hevy history logs the movement
as bare `Bulgarian Split Squat` — i.e. the reference had been authored against the WORKOUT title, which matched
nothing in the catalogue. Every other one of the 55 titles byte-matched the catalogue, so the drift is
per-template, not systemic. A title-keyed coverage pass over the 28-day window scored 38/38 — but that number is
unsound precisely because of this drift, which is why the audit shipped here is ID-keyed. The audit's
classification is `selection.classify_coverage`, extracted so the read path and the measurement cannot drift
apart; a fixture pins the BSS case (catalogue `Bulgarian Split Squat (Dumbbell)`, logged `Bulgarian Split
Squat`) resolving as TAGGED with the drift surfaced. 105 backend tests green.

**Do not revisit unless:** the resolver adopts normalised/fuzzy title matching (currently an explicit non-goal,
#60), or Hevy exposes a stable template-id-keyed export that removes the need to key reference data on title at
all.

---

### 80. The context-builder pre-refactor parity guard is NARROWED, not retired — the routine-creation section leaves its scope permanently

**Decision:** `test_context_builder_output_unchanged_pre_post_refactor` keeps its full-string old-vs-new assertion
for every prompt section EXCEPT routine-creation, which is excised from its fixture (`connected_integrations=[]`)
and pinned instead by its own explicit contract test. Test-only change to `tests/test_current_state.py` +
new `tests/test_routine_creation_prompt.py`. No migration.

**Rationale:** the guard asserts full-string equality between the system prompt rendered by `context_builder.py`
at pinned SHA `3360ed5` (the parent of the #43 refactor) and by current HEAD. Its question — "did #43 introduce
behavioural drift?" — is only answerable while the prompt is UNCHANGED by intent. #82 changes the routine-creation
section deliberately, so for that section the question dies: `old == new` can never hold again, and there is no
re-baseline that preserves it. Bumping the SHA is explicitly forbidden by the test's own comment (a later pin makes
the comparison old-vs-old and vacuous). Retiring the whole guard would throw away a live regression net over
identity/readiness/HRV/labs to solve a problem in one section. A golden-file snapshot was REJECTED: "parity vs
approved" re-blesses whatever is current on each update, degrading to a change-detector that ratifies drift — a
false-green instrument of exactly the class named in FEEDBACK §10, and not one to ship in the session that named it.
Graceful decay, not amputation.

**How you know:** the guard is live, not dormant — it passes in isolation at `e626e54` and the pinned SHA is
reachable (`git cat-file -t 3360ed5` → commit). `_section_routine_creation` is appended unconditionally
(`context_builder.py:1036`) and renders whenever `"hevy"` is in `connected_integrations`; the fixture passes exactly
`["hevy"]`, and the "never guess an ID" line rewritten by #82 sits inside it — so #82 breaks equality with
certainty, confirmed empirically (the guard failed at `test_current_state.py:203` on the #82 edit before narrowing).
The narrowing was measured before it was accepted, not assumed: it keeps **5055 of 6398 chars (79%)** of the
rendered prompt under the old-vs-new assertion, and of the 1343 chars dropped, **1338 are the excised section
itself**. Known and accepted cost: `_section_integrations`' `["hevy"]` branch (56 chars) leaves parity scope,
replaced by its empty-list branch (51 chars). #81 does NOT trip the guard: the join runs upstream in
`routers/chat.py` and `context_builder` stays formatter-only — the invariant the guard protects is preserved, not
circumvented. 123 backend tests green.

**Do not revisit unless:** the surviving assertion is found to be thin (a large share of the remaining prompt turns
out to be integration-gated and vanishes with an empty list), in which case the guard's value is already spent and
retiring it — citing history — becomes the honest call. The 79% measurement above is the check; re-run it if the
prompt's shape changes materially.

---

### 81. Workout history is rendered to the model with CATALOGUE titles, not Hevy's logged snapshot titles

**Decision:** each logged exercise is annotated UPSTREAM (`routers/chat._annotate_canonical_titles`, where a
Session is already in scope) with `canonical_title`, joined `exercise_template_id` → `hevy_exercise_templates.title`
via the new `hevy_templates.catalogue_titles_by_id`. `context_builder` renders that title and stays a pure
formatter. Ids absent from the catalogue are rendered as the logged title, marked `[UNCATALOGUED]`. No migration.

**Rationale:** Hevy stores a snapshot of the exercise title as it was when the workout was logged, and renames its
default templates over time. The context builder rendered that snapshot. The resolver (#60) matches EXACTLY against
the current catalogue. So the model was being shown titles from a title-space the resolver cannot resolve — a
guaranteed miss on any drifted movement, sourced from data we supplied. Rendering the catalogue title collapses the
two title-spaces into one and makes #82's title emission safe by construction. The join is deliberately NOT done
inside `context_builder`: that would have required threading a Session into it, breaking the formatter-only
invariant the #43 parity guard exists to protect — and then hiding the breach from the guard behind an
optional-default parameter. Fixing the guard's fixture to tolerate a violated invariant is not the same as not
violating it. Upstream annotation keeps `context_builder` pure and leaves the guard untouched structurally, not by
the accident of `hevy_data=None` in one fixture.

**How you know:** `Bulgarian Split Squat (Dumbbell)` (id `B5D3A742`, default) is logged in the user's own Hevy
history as bare `Bulgarian Split Squat` — a title present in NO template across the 494-row prod catalogue
(2026-07-14). Confirmed by the id-keyed coverage audit (#79), which reports the movement as TAGGED via the id join
while printing the divergent logged title alongside it. That prod-confirmed pair is the test fixture. The
formatter-only claim is pinned by a test that renders an annotated payload with no DB in sight, and the parity
guard (#80) passes unmodified by this change.

**Do not revisit unless:** Hevy begins returning the current template title on workout reads, making the join
redundant.

---

### 82. Routine provisioning accepts a canonical TITLE where no verified id exists; matching stays EXACT

**Decision:** the provisioning contract now instructs the model to emit `exercise_template_id` when the exercise
appears in the rendered history, otherwise a `title` spelled exactly as shown — never both, never an invented id.
Activates the dormant #60/#61 resolver at `routers/chat.py`. Matching remains EXACT. No migration.

**Rationale:** the contract told the model to emit `exercise_template_id` or else "say so — never guess an ID".
Correct as a hallucination guard, but it meant the model went SILENT rather than naming the movement, so the landed
title→id resolver had no live call path: it fires only for exercises missing an id but carrying a title, and nothing
ever emitted a title. Permitting title emission — against catalogue titles (#81) — ships the capability. Fuzzy/
normalised matching remains the explicit non-goal of #60. Unresolved titles are surfaced, not dropped: the model
naming a movement we cannot resolve is a finding, not a silent omission from the routine.

**How you know:** fuzzy matching would have "helpfully" resolved bare `Bulgarian Split Squat` to one of three real
candidates — `(Barbell)`, `(Dumbbell)`, or `Split Squat (Dumbbell)` — and picked wrong ~2/3 of the time, silently,
on a movement the user actually trains. Exact-match instead returned None, which is what made the drift visible at
all. The BSS case is the argument for exact-only, made in prod. The surfacing half needed no code:
`_process_routine_actions` already appends a warning naming the unresolvable titles and skips `create_routine`
entirely (fail-closed at whole-routine granularity), pinned since #60 by `test_unresolvable_title_skips_routine`
(`assert client.calls == []`) — verified, not assumed. The one path #82 newly opens (model emits id AND title) is
pinned: the id wins and the stray title never reaches Hevy, dropped by `create_routine`'s field allowlist.
123 backend tests green.

**Do not revisit unless:** a title-normalisation layer is built with an explicit ambiguity-refusal rule (multiple
candidates → resolve to None, never guess), at which point #60's non-goal is what is being revisited, not this.

---

### 83. Unresolved titles return ranked CANDIDATES; resolution stays exact, and a unique candidate is still not auto-resolved

**Decision:** on a title that does not resolve, `hevy_templates.suggest_candidates` returns ranked catalogue
candidates and the existing fail-closed warning names them. Resolution stays EXACT and nothing is auto-adopted —
not even a sole candidate. Fail-closed is unchanged: still no `create_routine`, still whole-routine. No migration.

**Rationale:** #82 let the model emit a title where it has no id — its entire purpose being movements OUTSIDE
recent history, which is precisely where #81 cannot hand it a canonical title. So the feature's primary use case is
the one where the model must guess a string it has never seen, against an exact matcher, with whole-routine failure
on a miss. Measured at 25%. Candidates convert a dead end into a one-turn correction while resolution stays exact:
the model is handed the catalogue slice it needs, when it needs it, instead of the whole catalogue on every request.
Injecting all 494 titles into every system prompt was REJECTED — it would drive accuracy to ~100% with no fuzzy code
at all, but pays ~2.5k tokens on every chat request to serve a path most conversations never take.
**Auto-resolving a unique candidate is explicitly REJECTED.** It is tempting — it would have rescued 2 of the 3
probe misses — but candidate cardinality is an artifact of catalogue SIZE, not of genuine unambiguity. `Leg Curl
(Machine)` has one candidate in a 10-row fixture and at least two in prod's 494 (`Lying Leg Curl (Machine)`,
`Seated Leg Curl (Machine)`). A rule firing on uniqueness would silently resolve wrong the moment the catalogue
grew — a silent-wrong failure replacing a loud-miss one. Loud is the design.

**How you know:** live probes against a real model (2026-07-14, `backend/probe_resolver.py`, fake Hevy client,
nothing written). BEFORE: out-of-history titles resolved 1 of 4. Emitted `Bulgarian Split Squat` (catalogue:
`… (Dumbbell)`) — MISS; `Leg Curl (Machine)` (catalogue: `Lying Leg Curl (Machine)`) — MISS; `Single Leg Romanian
Deadlift` (catalogue: `… (Dumbbell)`) — MISS; `Leg Extension (Machine)` — RESOLVED. The model demonstrably KNOWS
Hevy's `(Equipment)` convention (it emitted `(Machine)` twice unprompted); it cannot know whether the catalogue says
`Leg Curl` or `Lying Leg Curl`. That is unguessable, not a prompting deficiency — which is why the fix supplies
information rather than instruction. Failure compounds per-routine, not per-exercise: at 25%, a three-title routine
resolves ~1.6% of the time, and one probe lost a perfectly valid exercise to two near-misses. #82's contract itself
was followed to the letter — ids for in-history movements, a title for the one outside, never both — so the defect
was purely the string.
AFTER, both behaviours confirmed live and they differ correctly by ambiguity: (a) three out-of-history movements
went 1/3 → **3/3 resolved and the routine provisioned** on the turn after the candidate warning; (b) `Bulgarian
Split Squat`, which has THREE candidates, was NOT guessed — the model asked the user *"Which variation … Barbell /
Dumbbell / (Or Split Squat (Dumbbell) …)"*. Refusing to guess under genuine ambiguity while recovering under a clear
one is exactly the intended split, and it is the auto-resolve rejection vindicated in behaviour: a uniqueness rule
would have picked for the user here. The loop closes because actions are appended to the reply (`chat.py:540`),
returned as `ChatResponse.response`, stored as the assistant message (`ChatPanel.jsx:82`) and echoed back as
`conversation_history` (`ChatPanel.jsx:77-80`) — verified by reading the path, not assumed.
`_SUGGEST_MIN_RATIO = 0.5` is measured: `Split Squat (Dumbbell)` scores 0.512 against `Bulgarian Split Squat` while
the best NONSENSE match scores 0.341; the model then used that 0.512 candidate as a genuine alternative offer, which
a 0.6 floor would have silently withheld. 137 backend tests green.

**How you know — SCALE ADDENDUM (2026-07-15, appended; supersedes nothing above):** verified against the live
494-row prod catalogue, real model, real user state. The model emitted `exercise_template_id` for in-history
movements and a bare title (`Calf Raise`) for the out-of-history one — #82's contract followed exactly. Exact match
missed, as designed; `suggest_candidates` returned 5 candidates and **all 5 were genuine, with zero noise**:
`Seated Calf Raise`, `Standing Calf Raise`, `Standing Calf Raise (Smith)`, `Standing Calf Raise (Barbell)`,
`Standing Calf Raise (Machine)`. Fail-closed held — nothing was written until the user disambiguated ("standing
machine"), after which the routine provisioned. So candidate QUALITY survives 494 rows: the noise this entry
predicted (`Leg Press (Machine)` crowding a Leg Curl list on the 10-row slice) did not materialise, and
containment-first ranking is what carried it.
**What this run did NOT answer:** `_SUGGEST_MIN_RATIO = 0.5` remains **UNEXERCISED at scale, not validated**. All
five candidates were token-containment hits, so the ratio tier was never reached — the 0.5 floor decided nothing in
this run and therefore cannot be said to have held. The threshold's only measurement is still the 10-row gap (0.512
real vs 0.341 noise) recorded above. A live miss that resembles the catalogue without containing its tokens — a
typo or a genuinely different phrasing — is what would exercise it, and none has been observed. Absence of a
failure the run could not have produced is not evidence of correctness (FEEDBACK §10).

**How you know — RATIO TIER NOW EXERCISED (2026-07-15, later run; closes the item the addendum above left owed):**
the repaired probe (`probe_resolver.py`, FEEDBACK §11 fixes) reached its subject against the live 494-row catalogue
and forced three guessed titles at once — `Calf Raise`, `Preacher Curl`, `Pullover`. All three missed exact match;
`Preacher Curl` and `Pullover` produced the first non-containment candidates ever observed, so the 0.5 floor
finally decided something:

| miss | candidate | tier |
|---|---|---|
| `Preacher Curl` | `Preacher Curl (Barbell)` / `(Machine)` / `(Dumbbell)` | containment |
| `Preacher Curl` | `Rope Cable Curl` | **ratio 0.643** |
| `Preacher Curl` | `Drag Curl` | **ratio 0.636** |
| `Pullover` | `Pullover (Machine)` / `(Dumbbell)` | containment |
| `Pullover` | `Pull Up` | **ratio 0.533** |

**Verdict: the floor admits noise, and the RANKING — not the threshold — is what makes the feature work.** `Rope
Cable Curl`, `Drag Curl` and `Pull Up` are different exercises, not variants; they are the tail of a list whose head
is correct. Containment-first ordering put every genuine candidate above every ratio-tier one in all three cases, and
`limit=5` bounds the tail. So the reasoning this entry recorded as "reasoning, not measurement" is now measured, and
it held — but the honest reading is that 0.5 is doing no useful work and is tolerable only because ranking dominates
it. `Calf Raise` (5 candidates, all containment, zero noise) is the shape when the tier never fires.
**Do NOT raise the floor on this evidence:** 0.512 (`Split Squat (Dumbbell)`, a real alternative the model used as a
genuine offer) sits BELOW 0.533 (`Pull Up`, noise). Ratio does not separate signal from noise at this scale in
either direction — a floor high enough to exclude `Pull Up` would also exclude a real candidate. Ranking is the
mechanism; the floor is only a cheap bound on list length.

**Do not revisit unless:** full-catalogue injection becomes cheap enough that paying ~2.5k tokens on every request
beats a one-turn correction on the rare miss.

---

### 84. Model-facing contracts are verified by a paid, non-deterministic OPERATOR probe — never by CI

**Decision:** `backend/probe_resolver.py` is a first-class repo instrument: operator-run, excluded from CI, calling
the real Anthropic API with a fake Hevy client. It measures contracts stated in English in the system prompt and
honoured (or not) by a model at runtime. No migration.

**Rationale:** #82 shipped green across 123 tests and was practically dead on arrival — every test faked the model,
and the model was the failing component. A prompt is a contract with no compiler and no type system; the only way to
know whether it holds is to ask a real model and look. But such a test can never gate CI: it costs money per run and
is non-deterministic, so a red run means "the model chose differently today", not "the code broke" — wiring it into
CI would produce exactly the flaky-gate-that-gets-ignored this repo has no use for. The honest shape is a
measurement instrument an operator runs deliberately, whose output is read, not asserted. It is the FEEDBACK §8
(LANDED ≠ LIVE) lesson applied to the model layer: local-green over a faked model is not live.

**How you know:** the instrument found what the suite could not, twice in one session. It produced #83's entire
evidence base — the 25% hit-rate, the emitted strings, the recovery, and the ambiguity split — none of which any
deterministic test could have surfaced, because all of it is model behaviour. It also caught its own fidelity bugs
under use: the first version appended the RAW reply rather than reply+actions, so the model never saw its own
warning and a "recovered" verdict would have been fiction; and the synthetic user lacked a knowledge entry, firing
`_section_onboarding_interview` so the model spent its turns on profile questions instead of the contract under
test. Both are recorded in the harness itself. Safety is structural, not procedural: `FakeHevyClient` cannot write
a routine, `--synthetic` builds a throwaway in-memory catalogue, an empty catalogue is a loud precondition failure
(mirroring #77), and the API key is presence-checked and never materialised into output.

**Do not revisit unless:** a deterministic replay harness (recorded model responses) can carry the same contracts,
at which point the recorded half belongs in CI and only genuinely new probes stay operator-run.

---

### 85. Structured declared-state ledger — continuity-aware protocol / supplement / behavioural + phase derivation

**Decision:** The user's active stack is declared as structured, queryable rows in
user_knowledge_entries under three new types — protocol (pharma), supplement, behavioural —
sharing one continuity-aware value schema {active, continuity, phase, detail, relevant_date},
one entry per factor, mirroring the injury ledger (idempotent skip-if-active-key, source=
"system", notes=detail, no migration — type is a free String(50)). A pure derive_phase()
maps each entry to a phase as_of a date: continuous→steady/titrating, stopped→washout/stopped,
episodic→episodic (EXPLICITLY not assumed present at any given lab draw), behavioural→
re_entering, never/inactive→None. current_state exposes a declared_state structure lifted from
active entries in-memory (zero new queries), carrying derived phases. context_builder prompt
rendering is deliberately NOT touched (separate concern).

**Rationale:** 4a surfaced that no structured protocol exists anywhere — the platform's #1
health-intelligence principle (never read a lab in isolation from the active stack) had no
data backing; the stack lived only in Clinical_Protocol.md, an orientation doc flagged
unreliable (HGH wrongly active; peptides mis-described). The continuity field is load-bearing:
a continuous agent (TRT) is assumable present at every draw, an episodic one (ad-hoc peptides)
is NOT, a stopped one (tirzepatide) is in dated washout — the one distinction that makes a
factor's lab-relevance decidable, which a bare active flag flattens. Blocks 4b's phase-aware
gates (range_gate.expected_by_phase, feedback-relation phase-gating) until it exists.

**Seed provenance — user-confirmed clinical data, not inferred:** corrects Clinical_Protocol.md
(HGH never sourced; CJC-1295/Ipamorelin + IGF-1 LR3 episodic-not-discontinued; GLOW = BPC-157/
TB-500/GHK-Cu, not the mis-recorded KPV). Tirzepatide last-shot 2026-06-22 is triangulated
(HRV step-change date + Monday constraint + recollection), NOT a dosing log — flagged so it is
not counted twice as evidence for the Q17 washout hypothesis it was partly derived from. The
seed is captured with lab-confounders tagged per factor — berberine→glycaemic/lipid panel,
B-complex→B12/active-B12/homocysteine (repletion, not pathology), D3→25-OH vitamin D, the HPG
cluster (boron/zinc/apigenin production-side + prebiotic fibre estrobolome clearance-side)→
free-T/SHBG/E2, creatine+leucine-protein→creatinine/urea/eGFR — because that per-factor
confounder tagging is the specific capability the declaration unlocks for 4b's "already in
play" lever curation (#49). Supersession history preserved (ultra_muscleze_night inactive,
superseded by l_theanine_pm); cumulative Mg (~505mg bedtime + AM, 3 sources) and Zn (2 sources)
totals recorded so a Mg/Zn/Cu read is not misjudged.

**Two senses of "active" — the decision that drove the design (refines the brief):** the brief
said "one entry per factor" with an `active` field, and separately that the seed writes
inactive entries. Resolved by SEPARATING the row's `active` column from `value["active"]`. The
ROW is always active=True — it means "this declaration is current" — while `value["active"]`
means "the user is currently taking this". "HGH — never used" and "tirzepatide — stopped, in
washout" are both currently-true declarations. Collapsing the two (writing the row inactive
when value.active is false, the brief's literal reading) breaks two things at once, both
mutation-proven: current_state loads active=True rows ONLY, so the four untaken factors
(tirzepatide/glow/hgh/ultra_muscleze_night) would vanish from declared_state and their phase
would be underivable — defeating the ledger's whole purpose; and the idempotent skip keys on
(user_id, key, active=True), which never matches an inactive row, so every re-run duplicates
those four (the mutation fails `assert 4 == 0`). derive_phase therefore orders by CONTINUITY,
never by value.active, so a stopped factor still resolves to washout/stopped rather than being
short-circuited to None.

**Status:** Implemented backend (schema/derivation/wiring/seed). NOT LIVE until the Railway seed
runs (operator step, #56 public-proxy) — current_state.declared_state reads empty until then
(§8 precondition named). Sequence: 4a ✓ → this → 4b (verdict/relations/levers, now phase-aware)
→ rephrase → tap → go-live. Follow-on (separate concern): surface declared_state into the
context_builder system prompt so the chat is stack-accurate off structured data, not the doc.

**How you know:** 184 backend tests green (137 pre-existing + 47 new: 25 derivation/lift +
22 seed). The seed writes exactly 23 rows on an unseeded user (6 protocol + 16 supplement +
1 behavioural, asserted by type-count), and is idempotent — a second and third run add 0, the
table stays at 23, and each of the four untaken factors is present exactly once. Every derived
phase was dumped end-to-end through current_state and matches the brief's table:
trt→steady(assumable), tirzepatide→washout(not assumable), cjc_ipamorelin/igf1_lr3→episodic
(both active=True yet assumable_present=False — the not-present-by-default semantics carried
through to the field), glow→stopped (undated, so not washout), hgh→None, cbt_i→re_entering,
ultra_muscleze_night→None (superseded, active=False on value, active=True on row). The
derivation is mutation-proven non-vacuous four ways: making derive_phase echo value["phase"]
fails 6 tests; letting an inactive check preempt continuity (killing tirzepatide's washout)
fails 5; making assumable_present echo active fails 4; and the collapsed-active-column
alternative fails idempotency and the current_state-reach tests. Seed tests run against
_DECLARED_STATE_SEED itself, not a re-typed copy, so a transcription slip fails rather than
being restated; a cross-check asserts each authored `phase` equals its derived phase.
Boundary: `git diff --name-only master` is declared_state.py, current_state.py, seed_engine.py,
the two test modules and governance — no context_builder, no producer/4b code, no frontend, no
migration.

**Incidental finding (not this branch's work):** `backend/gate_test.py` is an untracked stray
(operator PDF-extraction probe) that pytest collects by its `*_test.py` name and which fires a
live paid Anthropic API call at COLLECTION time — it now 400s and breaks a bare `pytest`. The
suite is clean when scoped to `tests/` (184 in ~7s vs ~65s with the stray firing). Not deleted
(untracked, not this session's to remove); flagged for cleanup.

**Do not revisit unless:** a fourth declared-state type is needed, or a factor requires a
draw-specific presence resolution beyond the episodic/continuous/stopped continuity model.

---

### 86. Interpretation producer FOUNDATION (4a) — deterministic newest+prior gates, is_moved, flat ungrouped

**Number caveat (provisional):** claimed at this branch's merge per number-at-merge. #85 is
declared-state (reconciled from its unminted `#NEXT` this session — it was already in master
past #84, so it takes the lowest free number). `feat/feedback-ledger` (#85–88) and
`feat/checkin-injury-probe` (#89–90) are unmerged hardcodes; unmerged numbers do not bind, so
they renumber at their own merges. If either lands before this branch is pushed, it takes #86+
in merge order and this entry renumbers.

**Decision:** The interpretation producer is built foundation-first (4a) as a pure function —
`interpretation.producer.build_foundation(user_id, db, trigger_panel, prior_panel)` — that
consumes ONLY (a) newest+prior per marker (new `labs_reads.marker_series`, the existing
partition widened to `rn<=2`; `latest_lab_results` left byte-unchanged) and (b)
`marker_groups.json` + `lever_dictionary.marker_interpretation`/`_defaults` (never `levers[]`).
It emits `{meta, groups[], ungrouped[]}` with the 4a-owned fields populated and every 4b field
absent. Per member: `current`/`prior`, `delta` (direction/abs/pct/crossed_ref/magnitude/
censored/min_meaningful_delta), raw `news_gate` (gate-1 delta arm only — `is_news` =
magnitude-meaningful OR crossed_ref; basis names only delta/crossed arms, no relation demotion),
`range_gate` (gate 2, driven by `lab_flag`; `computed_flag` withheld, V2). `is_moved` per group
= any member news OR breach, producer-emitted so the frontend reads it. `magnitude` is
mode-aware (relative vs |pct|/100); `crossed_ref` computes from per-report bounds — the one
deliberate asymmetry (the breach is lab-asserted, the transition is bounds-computed, because a
point-in-time flag cannot express "was out, now in").

UNGROUPED markers are emitted FLAT in `ungrouped[]` (tagged, no `axis_verdict`), NOT synthesised
into groups-of-one. This is the deliberate correction of the earlier (discarded, never-merged)
4a design on the same branch, which synthesised a group-of-one per ungrouped marker: authoring
`marker_groups` content is forbidden (GUARD), and pooling stable+in-range ungrouped rows is a
downstream render call. `vitamin_d_25oh`, absent from any authored group, lands in `ungrouped[]`.

PHASE-FREE, relation-free, `current_state`-free: no verdict, relations, levers, mechanism,
phase, `protocol_context_snapshot`, endpoint or frontend.

**Rationale:** Foundation-first splits the mechanical half (gates, series, is_moved — provable
by re-emitting the §2 fixture from seeded rows) from the interpretive half (4b: verdict,
relations, levers, phase, relation-based news demotion). The 4a/4b line is drawn where judgment
enters. The lab_flag-only gate 2 keeps the producer from asserting a breach the lab did not —
`computed_flag` is withheld per contract V2; a computed breach is 4b's to surface with care.

**Status:** 4a implemented and landed (library only — no endpoint, no frontend, no wiring). The
prior groups-of-one design on this branch was reset away (superseded, never merged). Sequence:
4a ✓ → 4b (verdict/relations/levers, phase-aware — now unblocked by #85's declared-state) →
rephrase → tap → go-live. The `feat/interpretation-view-skeleton` render layer (increment 1,
still an unmerged local branch) consumes this producer's shape once wired.

**How you know:** 206 backend tests green (184 pre-existing incl. #85's 47, + 22 new). Oracle:
`build_foundation` re-emits the §2 worked example's 4a-projection from seeded rows —
hpg_axis(T within_noise/not-news/in-range, E2 marginal/not-news/in-range, FSH censored/not-news/
**breach L**) is_moved TRUE on the FSH breach alone (nothing news); hepatocellular(AST
meaningful/crossed into_range/**news**/in-range) is_moved TRUE on AST news alone; vitamin_d_25oh
in `ungrouped[]`, stable. Each gate proven independently load-bearing. Two divergences from the
fixture asserted explicitly: (1) vitamin D flat-ungrouped not a group-of-one (asset authors no
vitamin-D group); (2) testosterone_total min_meaningful_delta 0.30 (asset `_defaults` fallback —
no `testosterone_total` entry) not the fixture's authored 0.20, verdict within_noise either way,
no CVi fabricated. Mutation-tested: G5 (range_gate→computed_flag) fails; G6 (is_moved≡True fails
an all-stable group; mode-blind magnitude fails E2-marginal; crossed_ref ignoring prior fails
AST into_range). Boundary greps (G1/G2): producer imports neither `current_state` nor
`declared_state`; reads `marker_interpretation`/`_defaults`/`_meta` only, never `levers[]`. G4:
`test_labs_reads.py` green, `latest_lab_results` diff purely additive (zero removed lines).

**Oracle provenance caveat:** `INTERPRETATION_OUTPUT_CONTRACT.md` (the corrected §2 object,
UI-maintained knowledge file per #63) is NOT in the repo. The fixture
`backend/tests/fixtures/interpretation_s2.json` is the §2 worked example as transcribed onto
`feat/interpretation-view-skeleton`; its mechanical 4a fields are stable across the 4b
correction (the brief itself states raw-news == final-news for every member here). If the
corrected contract file later diverges on a mechanical field, re-sync the fixture.

**Do not revisit unless:** the contract's group-primary shape changes, `is_out_of_range` is
shown to hide a lab-asserted breach (it cannot — it reads lab_flag unconditionally), or the
flat-ungrouped decision fails against a real panel once 4b's render layer pools them.

---

### 87. Oracle fixture group display_name re-synced — #86's contract-divergence caveat exercised

**Decision:** The §2 fixture's `hepatocellular` group `display_name` is re-synced from
"Hepatocellular enzymes" to "Hepatobiliary enzymes + bilirubin" — the value in
`marker_groups.json` (which the producer emits) and in the corrected
`INTERPRETATION_OUTPUT_CONTRACT.md` §2 (O1(b), line 192). The G3 oracle
(`test_oracle_readings_match_the_fixture`) now asserts group `display_name` against the fixture
for both authored groups. Refines #86's oracle-provenance note; does not amend #86.

**Rationale:** Group `display_name` is producer-emitted from an asset but was asserted nowhere,
so the fixture could diverge from what the producer emits without any test failing — a silent
oracle gap. #86's caveat ("if the corrected contract file later diverges on a mechanical field,
re-sync the fixture") named this risk as theoretical; it has now MATERIALISED once, for this
field, and is resolved by re-sync plus the assertion that closes the gap for good. A field the
producer emits from an asset must be oracle-covered, or the fixture is not a faithful oracle for
it. Not a new documented divergence — the re-sync removes the divergence rather than recording
it (the two standing divergences, vitamin-D-ungrouped and the testosterone_total 0.30 fallback,
are producer-vs-fixture-by-design and stay).

**Status:** Landed. Test-only + governance; no producer, gates, or asset changed (the asset was
already correct — the fixture was the stale side). The G4-scoped test diff is exactly two files.

**How you know:** 206 green, no count change (assertion added, not replaced). Mutation-proven:
reverting the fixture to "Hepatocellular enzymes" turns the new `display_name` assertion red;
restoring it green. G2 held — the 4b non-vacuity test still passes and `_FIXTURE["groups"][0]`
still carries `axis_verdict` / `shared_levers` / member `relations_rendered` / `mechanism`.
Step-1 adjudication against the tree found NO further mechanical drift beyond this one field
(hpg_axis display_name already matched).

**Do not revisit unless:** the producer starts emitting another asset-sourced field the oracle
does not cover, or `INTERPRETATION_OUTPUT_CONTRACT.md` diverges from `marker_groups.json` on a
group name (they must agree — the producer follows the asset).

---

### 88. Interruption-survival governance — unseeable-surface rule, state vocabulary, HANDOFF ledger, close-out commit-log emission

**Decision:** Four governance changes under one concern — a session interrupted mid-crossing must be
resumable from the repo alone, without reconstructing state from chat scrollback. (1) An
**unseeable-surface rule** in the CLAUDE.md shared block: any declarative claim about a surface chat
cannot read (UI-maintained knowledge files, unpushed branches, local disk, Railway/prod state, the
operator container) is an INSTRUCTION TO VERIFY, never a report of fact. (2) A four-state **vocabulary**
— DONE / BLOCKED / OWED / UNSTARTED, exhaustive, no "in progress" — applied to `BRANCHES.md` Status,
`OPEN_QUESTIONS.md`, `ROADMAP.md`, and close-outs. (3) A new append-only `HANDOFF.md` ledger (`health-app`
root, one ledger, newest-first) whose `CHAT→CODE` receipt is written before work begins. (4) `/closeout`
additionally emits `git log --format="%ad %s" --date=short -10`, so the handoff carries the repo's own
immutable commit dates. Concern-split: rules (1, 2) + the generating incident (FEEDBACK §12) are one
concern; the ledger (3, 4) another. Does not amend #86 or #87.

**Rationale:** #87's brief asserted a precondition in the declarative mood; Code reflected it as
operator-attested; the attribution chain terminated in chat's own sentence, and three turns went to
resolving a state nobody had observed (FEEDBACK §12). Generalised: chat can verify only pushed refs, so a
claim's grammar is not its evidence; "in progress" hides whether work is BLOCKED or merely UNSTARTED; and
a session's state that lives only in scrollback makes an interrupted crossing unrecoverable. The four
states are exhaustive by construction (has-a-blocker → BLOCKED; finished-but-loop-open → OWED;
touched-vs-untouched partitions the rest). One ledger, not two, avoids the interleaving a per-lane split
reintroduces. The close-out git-log binds in CLAUDE.md, not `closeout.md`, because that file is
session-local and overwritten each close-out — a rule left only there would not survive.

**Status:** Landed. Governance-only — no backend, frontend, migration, or reference asset touched;
`latest_lab_results`, the interpretation producer, and every gate are byte-unchanged. The CLAUDE.md shared
block was edited in both repos and left byte-identical.

**How you know:** 206 tests green (`backend/.venv` pytest), count unchanged from #86/#87 — a moved count
would prove something non-governance was touched. The two CLAUDE.md shared blocks diff byte-identical
across both repos (147 lines / 9585 bytes each). `git diff --stat` is scoped to `CLAUDE.md` ×2,
`HANDOFF.md`, `FEEDBACK.md`, `BRANCHES.md`, `DECISIONS_LOG.md` — no `backend/`, `frontend/`, or `alembic/`.
The vocabulary was applied to two live `BRANCHES.md` rows as proof it is usable, not aspirational —
`fix/probe-harness-fidelity` → OWED (names the outstanding container run) and `feat/recovery-metrics-rhr`
→ BLOCKED (names the HCA node-dump blocker + owner Luke); neither resisted the four states. `HANDOFF.md`
landed non-vacuous — the #87 land + this brief's receipt — with the receipt committed (`5243dd6`) before
any substantive work, demonstrating the interruption-survival property it defines.

**Do not revisit unless:** a real artifact resists the four states (a row that is none of
DONE/BLOCKED/OWED/UNSTARTED — that is a finding about the vocabulary, not the row), or a second handoff
ledger is ever proposed (the interleaving problem this closed).

---

### 89. HRV step-change resolved as instrumentation — Q17 closes on (A); the RR corroborator was never independent

**Decision:** The 6-Jul step in scraper HRV (pre: mean ≈57 ms, range 24–88, high variance; post: mean
≈96 ms, range 83–117, variance collapsed) is instrumentation, not physiology. Cause is phantom-node
selection, fixed in `health-connect-app` #19 (`1db8833`): `findById` → `findByIdValidBounds` at three
call sites — `last_shrv` (HRV), `last_shr` (sleep HR), `vitality_respiratory_rate_average_title` (RR).
The phantom is a Compose recycling duplicate bearing the PRIOR render's value with negative width;
`.firstOrNull()` returned it. The fix was **authored 26 Jun** on unmerged `fix/scraper-sh-relayout` and
**reached HCA master 11 Jul** (renumbered #16→#19) — no single commit or merge date is the changepoint.
Q17 is resolved on the **(A)** limb.

**Rationale:** *Why stale-value, not metric-change* — Q17 hypothesised RMSSD→SDNN on a ~1.7× ratio;
withdrawn as surplus. A stale prior-render value predicts the statistics directly (scattered low reads
before, locked on-screen truth after) without any analyte changing; the ratio match is coincidence.
*Why (B)'s corroborator was void, not merely outweighed* — Q17 rested (B) on respiratory rate drifting
14.0→13.5 "via a different sensor path — a scraper bug cannot move RR." RR is read from the same Vitality
screen through the same defective selector and was fixed in the same commit; the RR drift is a
*prediction* of (A), not evidence against it. This is the load-bearing correction: an
assumed-independent corroborator that was never independent.

**Status:** Resolved Q17 → this entry, on (A). Governance-only — no `backend/`, `frontend/`, migration,
or test touched. **Not decided:** (B) as *physiology* is unevidenced, not disproven — GLP-1/GIP washout
may still have produced a real HRV change, but the scraper series cannot speak to it. **Consequence:**
the pre-install HRV baseline ≈57 ms is not a baseline; readiness scoring, trend inference, and protocol
attribution built on the 57→96 "rebound" rest on an artifact — trustworthy HRV history is short, not
long. **Historical rows are not reconciled here — Q29** minted for it: the changepoint is an APK-install
event, not a commit (fix authored 26 Jun, not on HCA master until 11 Jul, data step ~6 Jul, HCA Q3
records a stale APK re-emitting phantom 106 on 11 Jul), so phantom-era and valid-era rows interleave and
must be segmented by install history before any correction.

**How you know:** verified against `health-connect-app` master. (1) `1db8833`'s diff shows the three
`findById`→`findByIdValidBounds` conversions verbatim on `HRVAccessibilityService.kt`. (2) HCA
`DECISIONS_LOG.md` #19 states all three reads hit the Vitality/Energy-score screen and the phantom bears
the prior render's value ("a half-landing that fixed only HRV would leave HR/RR reading phantoms").
(3) No HCA scraper commit exists 2026-07-03…2026-07-10 — the data step has no code change behind it.
(4) #19 and tracked `nodedump.txt` cite the phantom `'Average: 106 ms'` (width −84) sorting before real
`'Average: 97 ms'` (width 912), on-screen 97, "Re-confirmed 11 Jul 2026"; HCA Q3 (RESOLVED) independently
records the stale APK `a5d1643` re-emitting phantom 106 on 11 Jul.

**Do not revisit unless:** a captured node dump shows the post-fix selector binding a *different* metric
than pre-fix (it does not — same RMSSD node, phantom deselected), or Health Connect `resting_heart_rate`
(the only uncontaminated path) contradicts the instrumentation reading.

---

### 90. Vocabulary adoption is a sweep, not a definition — and position, completeness and recency are not evidence

**Decision:** every `BRANCHES.md` row and `OPEN_QUESTIONS.md` entry **in health-app** is brought to a valid state;
five outstanding loops adjudicated against artifacts (two closed on evidence, three confirmed genuinely OWED with
named commands and owners); three previously local-only branches pushed and given dedicated rows. Two standing
rules follow:

1. **Defining a vocabulary does not adopt it.** A vocabulary change is not landed until every existing row using
   the superseded labels has been relabelled, in the same session or an immediately following one — or the unswept
   remainder is recorded as OWED with its exact scope.
2. **A claim inherits authority from what attests it, never from where it sits.**

Does not amend #88; completes its adoption. **Scope is health-app only** — `health-connect-app`'s stores are an
unseeable surface from this repo and its sweep is a separate, single-repo session (recorded OWED, below).

**Rationale:** #88 defined the four states and applied them to two `BRANCHES.md` rows as proof of usability, then
landed. The remaining rows kept `LANDED` / `IN FLIGHT` / `PARKED`, and `OPEN_QUESTIONS.md` kept `PENDING` /
`PARKED` — so the store a returning session actually reads still spoke the superseded dialect, and `IN FLIGHT` /
`PARKED` are precisely the "in progress" ambiguity #88 exists to abolish. A vocabulary that coexists with its
predecessor is worse than either alone: the reader must now decide which dialect a row is written in.

The sweep then surfaced the same defect three times in three disguises. **One root: a claim inheriting authority
from where it sits rather than from what attests it.**

- **(a) Position.** `feat/resolver-candidate-suggestions` carried `LOOP CLOSED — verified in prod` in its
  *Unblocks on* column while its *Status* column still read `IN FLIGHT — local-only (never pushed)`. Both were
  written by the same session about the same work; the row had adopted the new labels partially, so the wrong
  field vouched for the row. The branch had in fact merged and been deleted — its ref existed nowhere, which is
  why patch-id (`git cherry`) was unrunnable and adjudication had to go to content on master.
- **(b) Completeness.** `feat/interpretation-view-skeleton` looks complete by merge position while consuming a
  superseded contract: its committed fixture's top-level keys are `['groups','meta']` and `ungrouped` appears
  nowhere in its `frontend/src`, against master's `{meta, groups, ungrouped}` (#86). Merge position vouched for a
  validity it did not have; wiring the view as-is would silently drop every ungrouped marker.
- **(c) Recency.** This sweep's own brief asserted a prod verification — "key was replaced 12 Jul and See-all
  verified live" — drawn from chat scrollback, written in the declarative mood, with no artifact on master or in
  prod. Recency vouched for attestation. The loop stayed OWED.

Position, completeness and recency are not evidence. Only an artifact is.

**Scoping note — `OPEN_QUESTIONS.md` keeps its own vocabulary.** The four states are for WORK items. A question is
not a work item: `resolved → #43` carries which decision closed it, information `DONE` cannot express, and `open`
(undecided) is not `UNSTARTED` (untouched work). `OPEN_QUESTIONS.md` therefore retains `open` / `verifying` /
`resolved → #` per CLAUDE.md's canonical-stores table, and the sweep fixed only the entries valid under *neither*
vocabulary (Q10 `PARKED`, Q29 `PENDING`). This exposes a contradiction inside CLAUDE.md itself — the canonical-stores
row assigns `open`/`verifying`/`resolved` to `OPEN_QUESTIONS.md`, while #88's state-vocabulary section says the four
states apply to it — which is left OPEN for decision rather than resolved unilaterally, because that text sits in the
verbatim-propagated shared block and editing it obligates `health-connect-app`.

**Status:** Landed. Governance-only — no production code path, no schema, no migration, no reference asset.

**How you know:** backend suite **206 passed** (`.venv/Scripts/python.exe -m pytest tests/ -q`), unchanged from
#88's 206 — no non-governance file was touched. `git diff --stat` against the merge-base lists only `BRANCHES.md`,
`OPEN_QUESTIONS.md`, `ROADMAP.md`, `HANDOFF.md`, `DECISIONS_LOG.md`, `FEEDBACK.md`; zero `backend/`, `frontend/`,
`alembic/`. Label sweep verified by two greps: status labels —
`grep -oE "\| \*\*(DONE|OWED|BLOCKED|UNSTARTED)" BRANCHES.md` returns 22 hits over 22 rows (11 DONE / 10 OWED /
1 UNSTARTED); superseded tokens — `grep -oE "\*\*(LANDED|IN FLIGHT|PARKED|RETIRED)[^*]*\*\*" BRANCHES.md`
returns none. `grep -nE "^\*\*Status:\*\*" OPEN_QUESTIONS.md | grep -viE "open|verifying|resolved"` returns
nothing across all 29 questions. One residual `IN FLIGHT` string survives in free prose — a quotation inside the
(a) audit note recording what was corrected — which is the audit trail, not a row label.

**Do not revisit unless:** a real artifact resists the four states (the `OPEN_QUESTIONS` case above is one, and is
handled by scope, not by forcing the vocabulary), or a store is found still carrying superseded labels — that is an
adoption-sweep failure, not a vocabulary failure.

**OWED at landing:** `health-connect-app`'s `BRANCHES.md` (4 rows) and `OPEN_QUESTIONS.md` (Q1/Q2/Q4/Q5 on
`PENDING`) are NOT swept by this entry and remain on superseded labels. Owner: Luke, in an HCA-rooted session.

---

### 91. `OPEN_QUESTIONS` adopts the four states — the three-value set could not express BLOCKED, and was not applied consistently

**Decision:** `CLAUDE.md`'s canonical-stores table no longer assigns `OPEN_QUESTIONS.md` its own
`open` / `verifying` / `resolved → #` vocabulary; that row now points to the **State vocabulary**
section, which is the sole definition. `health-app/OPEN_QUESTIONS.md` is swept to
DONE / BLOCKED / OWED / UNSTARTED, with `DONE → #N` preserving the resolving-decision pointer. Two
clauses are added to the vocabulary itself:

- **BLOCKED** — a trigger for when work becomes *worth* doing is not a blocker on its being
  *possible*; that is UNSTARTED.
- **OWED** — widened from "work finished" to "work **or decision** settled", which the four OWED
  questions require: their decisions are landed and only a named verification is outstanding.

Amends #88's shared block; does not supersede it. **Scope is health-app.** Propagating the block to
`health-connect-app` and sweeping its stores is Phase 2b of this brief — OWED at this landing, not
asserted here.

Also corrects **#90**. #90's exit condition — zero rows in either repo carrying a non-four-state
label — was **not met at close**: `OPEN_QUESTIONS.md` rows remained on `open`/`verifying`/`resolved`
and `health-connect-app` was untouched. #90 did not misreport this — it scoped `OPEN_QUESTIONS` out
explicitly, recorded the CLAUDE.md contradiction as open, and logged HCA as OWED — and the deferral
was *correct*: the rule it would have executed under was self-contradictory, so executing it would
have picked a winner by accident rather than by decision. But the condition stands unmet until this
entry and Phase 2b close it. #90's entry is locked and unedited; this entry carries the correction.

**Rationale:** the shared block sanctioned two vocabularies twelve lines apart, both looking
authoritative — #90's own defect, a claim inheriting authority from where it sits rather than from
what attests it. The tie-break is empirical, not aesthetic. **The three-value set failed twice over.**

1. **It could not express BLOCKED — and the store visibly reached around the gap.** Q29 carried the
   label `open` while its own body read "blocked on install-history segmentation (owner: Luke)" plus a
   hard prohibition on touching the data. The blocker, its owner and its unblock condition were all
   present — written in prose, because the vocabulary had no state to put them in. Q24 and Q25 are the
   same shape (Q25 cannot proceed at all outside an HCA-rooted session). Under the old set all three
   collapse to `open`, indistinguishable from a question nobody has looked at — precisely the
   ambiguity #88 exists to abolish.
2. **It was applied inconsistently to the states it did have.** Q6's status read
   `open, resolves → #28 on Postgres verify` — a settled decision awaiting one verification, i.e. a
   `verifying` row wearing an `open` label. Q13, Q15 and Q18 are the same. So the `open` bucket was
   never one category: of 18 `open` rows, **3 were BLOCKED, 4 were OWED, 11 were UNSTARTED**. A
   vocabulary that is both under-expressive and unevenly applied cannot be repaired by discipline;
   the bucket has to be split.

Two rows also proved that a stated blocker must hold *now*, not when the row was written: Q3's
precondition (HR de-duplication) had landed on HCA master at `36df9a2`, and Q23's (tags human-confirmed
and seeded) completed in prod on 2026-07-14. Carrying their prose forward would have manufactured two
false BLOCKEDs.

**Status:** Landed. Governance-only — no production path, no schema, no migration.

**How you know:**
- **Pre-edit shared block, both repos:** 151 lines, LF-normalised 9799 B, md5
  `9e7959c2c4a17fa95992a80e43dc1538` — **identical**. Raw working-tree md5 differed
  (health-app 9799 B / HCA 9950 B) by exactly 151 bytes over 151 lines = one CR per line;
  `git ls-files --eol CLAUDE.md` reports `i/lf` in **both** repos, so the committed content — the only
  thing that propagates — was already identical. The raw delta is a `core.autocrlf` checkout artifact,
  not divergence, and is logged as Q30.
- **Post-edit health-app block:** 153 lines, LF-normalised 10080 B, md5
  `9436cb223c4b601252152ab4fa6a3547`. Cross-repo byte-identity is Phase 2b's gate, measured on index
  content.
- **The split tally:** 18 `open` → 3 BLOCKED (Q24, Q25, Q29 — each naming blocker + owner from its own
  content) / 4 OWED (Q6, Q13, Q15, Q18) / 11 UNSTARTED. Mechanical: 10 `resolved` → `DONE → #N`,
  1 `verifying` (Q4) → OWED.
- **Zero out-of-vocabulary labels** in health-app:
  `grep -nE "^\*\*Status:\*\*" OPEN_QUESTIONS.md | grep -viE "DONE|BLOCKED|OWED|UNSTARTED"` returns
  nothing across all 31 questions (10 DONE / 3 BLOCKED / 5 OWED / 13 UNSTARTED); and
  `grep -oE "\| \*\*(LANDED|IN FLIGHT|PARKED|RETIRED)" BRANCHES.md` returns none.
- **Test count:** backend suite **206 passed**, unchanged from the merge-base and from #88/#90.

**Do not revisit unless:** a question arises that resists all four states — in which case the failure
is the vocabulary, not this adoption.

**OWED at landing:** `health-connect-app` has NOT received the block and its stores are NOT swept.
Phase 2b: propagate the block wholesale, re-fingerprint on index content, enumerate its actual
branches (local + remote) against `BRANCHES.md`, and sweep its `OPEN_QUESTIONS.md` off `PENDING`.
Owner: Luke, in an HCA-rooted session.

---

### 92. G1 discharged by return mirror — and a paired obligation is not closed until both repos are

**Decision:** the shared loop-rules block is re-mirrored **health-connect-app → health-app**,
discharging the G1 parity breach that the vocabulary-parity session opened (HCA Q8). Two rules follow,
and one scope boundary is fixed.

**1. The paired-obligation protocol (standing rule).** The single-repo rule guarantees that a session
which edits a shared surface *cannot finish the job* — the other repo is unreachable from it. So a
cross-repo edit does not create a task, it creates a **pair**: the editing session must record the
obligation in its own store as OWED, naming the exact action, the repo it must be run from, and the
fingerprints on both sides; the return session discharges it **first, before any other work**, and
closes the pair. Mirror first is not stylistic ordering — a deferred mirror is the one obligation that
*regenerates* drift while it waits, because every subsequent edit in either repo compounds the delta.
HCA Q8 is the worked example: it recorded both fingerprints, named the action, named the repo, and
named the owner, so the return trip was mechanical rather than reconstructive.

**2. The Q9 split — a ritual definition is a governed surface; a transient payload is not.** HCA Q9
found the struck vocabulary surviving in the `/closeout` command definition. It splits:

- **The `BRANCHES.md` column set (`purpose / why-parked / unblocks-on`) IS a violation — struck.** A
  ritual definition that teaches the dead dialect *re-emits it every session*: unlike a stale row,
  which merely persists, a stale rule regenerates. `.claude/commands/closeout.md` step 4 now names the
  four states and what each requires (SHA for DONE, blocker + owner for BLOCKED, the outstanding
  command or check for OWED).
- **The `PENDING`-queue reconciliation is NOT a violation — deliberately unchanged.** The four states
  govern *stored rows*: `BRANCHES.md` Status, `OPEN_QUESTIONS.md`, `ROADMAP.md`, close-outs. The
  pending-commit queue is defined in the same CLAUDE.md table as "Transient … consumed at the next
  Code open, then discarded. **Not a stored repo file.**" Its `PENDING` flag marks a payload *in
  transit*, not the state of a tracked item a future reader must interpret. Striking it would delete a
  working mechanism to satisfy a rule that does not reach it. Vocabulary scope follows the artifact's
  persistence, not its wording.

**Status:** Landed. Governance-only.

**How you know:**
- **G1 before:** health-app `9fa18cc` = 153 lines / 10080 B / md5 `9436cb223c4b601252152ab4fa6a3547`;
  HCA master = 155 / 10232 / md5 `4243c91ce78e0331ddfa5178aa3006b8` — **diverged**, exactly the two
  lines of the barrier-vs-trigger tie-break.
- **G1 after:** both **155 lines / 10232 B / md5 `4243c91ce78e0331ddfa5178aa3006b8`**, measured on
  **committed content** (`git show <ref>:CLAUDE.md`) in both repos — the surface that propagates, per
  #91's gate definition. The block was spliced verbatim from HCA's committed blob, never retyped.
  Working-tree eol differs (`w/mixed` here, `w/crlf` there) and is not a G1 signal — that is Q30.
- **Exit gate, four files across two repos, measured by FIELD not by word:** health-app
  `BRANCHES.md` (22 rows) and `OPEN_QUESTIONS.md` (32 questions — 11 DONE / 2 BLOCKED / 5 OWED /
  14 UNSTARTED) carry zero out-of-vocabulary labels; HCA `BRANCHES.md` status column reads
  `UNSTARTED` / `BLOCKED` / `DONE → 1db8833` / `DONE → db6f50e` / `OWED`, and its `OPEN_QUESTIONS.md`
  headings read 1 BLOCKED / 1 DONE / 3 OWED / 4 UNSTARTED. A word-level grep returns false hits in
  both repos — "Landed" three times in HCA's *notes* column, "pending/blocked/resolved" in health-app's
  ROADMAP *prose* — none of which are labels. See FEEDBACK §14.
- **Test count:** backend suite unchanged from merge-base.

**Do not revisit unless:** a shared surface is edited from the non-canonical repo again without the
paired obligation being recorded — in which case the failure is the protocol not being followed, not
the protocol.

**OWED at landing:** HCA's own `/closeout` definition still carries the struck column set, and the two
ritual definitions have diverged (77 vs 132 lines). Logged as Q32, owner Luke, for an HCA-rooted
session — not swept here, because another repo's ritual definition is outside this brief's fence and
sweeping it unbidden is not Code's call.

---

### 93. Vocabulary adoption completes at the frame, not the values — and sweeps run definition-first

**Decision:** two instances of the superseded vocabulary are struck from this repo:
`.claude/commands/closeout.md:34` (`parked` as a status verb → `rowed`, mirroring HCA) and
`BRANCHES.md:3` (the `Why parked | Unblocks on` column pair → `Detail | Blocker / outstanding (owner)`,
with HCA's four-state preamble ported verbatim above the table). Header and preamble are now
byte-identical to `health-connect-app` at the same line numbers (both `BRANCHES.md:3–9`, header at `:8`).
Q25's stale sub-claim is corrected (both limbs closed); `FEEDBACK` §14 gains occurrence 4 and §15 is
minted. Completes the adoption begun at #88 and swept at #90/#91/#92 and HCA #20/#21.

This entry also **corrects the scoping of #92's brief**, which placed this repo's ritual out of scope as
"already struck." It was not — `parked` was live at line 34. #92 is locked and unedited; this entry
carries the correction, per the append-only discipline.

**One instance is knowingly deferred, not missed.** `CLAUDE.md:128` (health-app) and `CLAUDE.md:116`
(HCA) carry the same `parked` sentence inside the **verbatim-propagated shared block**, fingerprint-gated
at `4243c91ce78e0331ddfa5178aa3006b8` / 155 lines / 10232 B. It is a generator instruction and it does
survive the frame-vs-narration filter — but editing it from a health-app-rooted session re-breaches the
G1 parity that #92 just discharged, and under #92's own paired-obligation protocol a shared-block edit
needs its own brief with a mirror-first plan. Both repos are identical on that line, so nothing has
diverged; the deferral is safe rather than merely tolerated. Tracked as **Q33, UNSTARTED** — because
DECISIONS records what was decided and OPEN_QUESTIONS is what gets actioned, and an obligation living
only in an append-only entry has nothing pointing at it.

**Rationale:** #92 met its exit condition on values and stopped. But a column header tells the next
writer what to put in the column, and a ritual instruction tells the next session what to call a branch
— both regenerate the dialect regardless of how clean the cells are.

The deeper finding is the **ordering**, visible only now that three sessions have stacked: #90/#91 swept
the values and exposed the ritual; HCA #21 swept the ritual and exposed the header; this session swept
the header and exposed the shared block — the document that *defines* the vocabulary it violates. The
layers fell in strict order of increasing authority, each sweep meeting its exit condition honestly and
each followed by a session finding the dialect one layer up. That is not four failures of thoroughness;
it is one failure of ordering. **Sweep from the most authoritative surface downward, not the most visible
upward** — values are visible so they get swept first, definitions are authoritative so they get swept
last, by which point the definition has re-emitted the dead dialect into every layer beneath it.
Recorded as `FEEDBACK` §15.

**Status:** Landed. Governance + `.claude/` only.

**How you know:** the two edits at named line numbers; `diff` of `BRANCHES.md:3–9` against HCA returns
empty (byte-identical, header at `:8` in both); column integrity held at 5 columns × 24 table lines with
the col4/col5 mapping checked across **all 22 rows**, not sampled, so the rename moved no data; Q25's
subject verified gone independently (HCA row at `f15b545`, `git ls-remote --heads origin
claude/hevy-api-workout-query-teulc2` empty); shared block unchanged at `4243c91ce78e0331ddfa5178aa3006b8`
/ 155 / 10232; backend test count unchanged from merge-base; exit greps by **field** returning zero
struck labels across the four stores in both repos, plus zero in any column header or ritual instruction,
with the single shared-block instance named and deferred.

**OWED at landing — paired obligation, HCA-rooted session (owner: Luke).** `health-connect-app`'s
**Q11** ("health-app's `/closeout` still instructs `parked`; ritual divergence ruled", OWED) names
precisely the two items this entry lands: (1) strike `parked` at `.claude/commands/closeout.md:34`;
(2) rename the `BRANCHES.md:3` header pair. **Both are now done** — Q11 should close `DONE → #93`, and
its clause "HCA is authoritative for the ritual's vocabulary and for the header frame in the interim"
lapses, the two repos now being byte-identical on the header and preamble. Cannot be written from here
under the single-repo rule; recorded as OWED per #92's paired-obligation protocol rather than asserted
done. Unaffected and still open: HCA **Q9 item 1** (`ROADMAP.md`'s work queue carrying
`RESOLVED` / `parked` / `Blocked on` — inert debt, carried rather than regenerated) and HCA **Q10**
(the ritual ANCHOR's declarative mood).

Corroboration worth recording: Q11 independently states health-app's status values as
"12 DONE / 9 OWED / 1 UNSTARTED, zero outside the four states", and this session's by-field count,
taken before that text was read, returned the same distribution summing to 22 rows. Two extractions,
two repos, one number.

**Do not revisit unless:** Q33 lands the shared-block strike, at which point the adoption is complete at
every layer and this entry's deferral is discharged.

---

### 94. The consolidated governance view is generated, never hand-assembled

**Decision:** `scripts/gen_governance_view.py` emits `CONSOLIDATED_GOVERNANCE_VIEW.md` from both
repos' four governance stores — `DECISIONS_LOG` / `OPEN_QUESTIONS` / `FEEDBACK` / `ROADMAP` — read at
**master** via `raw.githubusercontent.com`, with a live provenance block recording each repo's
resolved SHA, highest decision number, and generation time. Output goes to `build/` and is gitignored:
derived artifacts are not committed. The hand-assembled predecessor is superseded.

Reading at master rather than the local tree is deliberate on two counts: a working tree may be dirty
or behind, and fetching over HTTPS sidesteps the single-repo rule — the script reads
`health-connect-app` and never writes it.

**Emits a digest, not a verbatim copy.** One line per entry — `#N · title · status` for decisions,
`Qn · title · STATE` for questions, section/date + first line for feedback, section rows for roadmap —
each carrying a line-anchored GitHub URL to the full entry.

**Rationale:** the manual mirror sat at health-app `#34` / HCA `#15` as of 28 Jun while master carried
`#93` / `#21` — 65 decisions and three weeks of drift, with nothing to signal it. Chat read that file
as orientation throughout 2026-07-20 and made repeated assertions master contradicted; the repo-verify
rule caught them each time, but the mirror was the source of the error. A mirror that can silently
disagree with its source is worse than no mirror: it reads as current. Generation makes drift
structurally impossible, and the provenance block makes the read time explicit.

The predecessor was verbatim, which was viable at health-app `#34`. At `#93` the same approach emits
~350 KB — a second copy of the repos rather than orientation, and a copy large enough that nobody
reads it, which is how it drifted unnoticed. The view is a digest with anchors: enough to know what
exists and where, never enough to substitute for master. **Scaling changed the requirement, not the
intent** — the standing rule already says project knowledge holds orientation only, never canonical
state.

**The two repos do not share store schemas, and every divergence is a silent-failure surface.** Four
were found by reading the stores rather than assuming symmetry: decisions are `### 93.` here and
`### #20 — … · active` there; questions are `## Q33.` here and `### Q11 — … · OWED` there; feedback is
numbered `## N.` sections here and dated `### YYYY-MM-DD … [tag]` entries there; roadmaps are
`| Item | Notes |` tables here and bullet lists there, under entirely different section names. Each
mismatch fails *quietly* — a regex that fits one repo returns zero for the other and renders an empty
section that reads as "nothing here". So every parser asserts it matched at least one entry and
raises otherwise, and the roadmap parser emits all sections and both row forms rather than filtering
to hardcoded names. Two such defects were caught during construction, after passing a first run:
FEEDBACK reported 52 entries for a 15-section store (a lenient `#{2,3}` swept in `### 1.1`-style
subsections), and HCA's roadmap reported 4 rows because a table-only parser dropped its entire
bullet-form work queue.

**Status:** Landed. Governance + `scripts/` only.

**How you know:** the eight resolved URLs, all HTTP 200 at pinned SHAs (`9ec0f2b` / `36a8444`); the
fetched health-app `DECISIONS_LOG.md` diffs clean against local master once CRLF-normalised; per-store
entry counts each equal to emitted digest lines, gated in-script (93/33/15/27 and 21/11/12/30); the
decision-count gap check (highest number == entry count) passing silently for both repos; output 334
lines / 63223 bytes / zero CR bytes; banner runs exactly 60 `═` with one blank line before and three
after; eight `─── STORE: ───` separators; test count unchanged; shared block untouched.

**Do not revisit unless:** a store's schema changes, in which case the script fails loudly by design —
fix the parser, do not relax the assertion.

---

### 95. A deferred entry names one of three blockers, not one — and I1 extends to read-constants

**Decision:** `marker_canonical.json` goes to **v0.3** with 34 appended entries (31 → 65), taking the
CBC, iron studies, lipids, B-vitamins, HbA1c and endocrine markers into the vocabulary so reports map
on arrival. `lever_dictionary._meta.binds_to` follows to `v0.3 (#95)`. Two structural rulings land with
it.

**1. `_deferred` blockers are a three-class taxonomy.** The block's note claimed every deferral was
"blocked purely on canonical-vocabulary gaps". That was true of one of its four entries. The classes:

- **(1) vocabulary gap** — the marker is on the report but has no canonical id. Discharged by a vocab
  bump. `erythroid` and `trt_erythrocytosis_watch` were genuinely this, and v0.3 discharges both:
  `blocked_on` cleared, `status: ready_to_promote`.
- **(2) never ordered** — the marker could be canonical but has never been ordered, so no data will
  arrive until it is. A vocab bump does nothing. `ck_muscle_discriminator` moves to a new
  `_blocked_on_order` block, `blocked_on: ["ck — never ordered"]`.
- **(3) lab does not report it** — structurally absent from this provider's output. Neither a bump nor
  an order discharges it; the entry must be re-scoped or retired. `calcium_corrected` is this: SNP
  prints only `Calcium (Corrected)`, so uncorrected calcium never arrives and the correction can never
  be recomputed — re-scoped as **primitive**.

`non_hdl` was a fourth case and none of the three: the lab prints `Non HDLC` directly, so it is a
primitive read that had been mis-filed as derived. Deriving it would recompute a reported number. The
arithmetic is re-filed as a **4b QA identity** — `non_hdl == cholesterol_total − hdl_cholesterol` — a
check on *extraction fidelity*, not a derivation. If it fails, the extraction is wrong, not the maths.

Retired entries are recorded with their reason in `_deferred.retired`, not deleted. The taxonomy
matters because a single-class note makes the block read as one queue awaiting one event, so a reader
expands the vocabulary and expects the whole block to clear.

**2. Invariant I1 extends from levers to read-constants.** I1 today reads: every *surfaced lever*
needs non-empty `evidence_refs`; nodes with `evidence_refs: []` are draft-only and must not surface.
The same standard now applies to any `marker_interpretation` constant that influences a gate: it
requires non-empty `evidence_refs`, or it falls back to `_defaults`. An uncited number that silently
sets a threshold is the same defect as an uncited lever that silently surfaces — the citation
requirement was never really about levers, it was about anything that changes an output.

**Status:** Landed as vocabulary + governance. **I1's extension is recorded canon but NOT enforced —
see How you know.** No migration, no producer change, no ingestion.

**How you know:** version `0.2 → 0.3`, entries `31 → 65`; zero duplicate `marker_name_raw` and zero
duplicate `marker_canonical` across all 65 (`_CANONICAL_MAP` is a plain dict — a dupe silently wins
last); `glucose_fasting` and `glucose_random` both present and distinct; all three JSON files parse;
backend suite **206 passed**, unchanged, and no test asserts entry count or map version;
`lever_dictionary._meta.version` left at `v0` because fixtures pin it; the over-collapse guard
(`backend/routers/labs.py:394`) untouched and structurally unable to fire on a null
`unit_established`, which is what `haematocrit` and `chol_hdl_ratio` carry.

**Two gates this entry does NOT claim.** Recorded rather than glossed:

- **The backfill dry run did not verify what it was meant to.** It returned `0 rows across 65
  mappings`, but `backend/.env` sets `DATABASE_URL` to local SQLite, not Railway — and that local DB
  holds 24 `lab_results` rows with **zero** `marker_canonical IS NULL`. With no NULL rows to match, the
  query cannot return anything but zero, so it is incapable of detecting the raw-label variant it
  exists to catch. The expected answer, produced by a probe that could not have produced any other.
  Re-run against Railway before trusting it (`FEEDBACK` §11, §14).
- **I1's extension has no enforcement and one live violation.**
  `backend/interpretation/gates.py:39-53` falls back only when the entry is absent or `value is None`;
  it explicitly projects `evidence_refs` away, its docstring stating they "are NOT part of a delta".
  Under extended I1, `alt` — `value: 0.45`, `evidence_refs: []`, note "citation pending" — must fall
  back to `_defaults` (0.30) and currently does not. Landing the invariant without the producer change
  leaves canon and code disagreeing; the producer change is owed.

**Do not revisit unless:** the lab's printed labels change, in which case `marker_name_raw` is the
surface that breaks, silently, via exact match.

---

### 96. `erythroid` authored as structure only — constants withheld under I1

**Decision:** the `erythroid` group lands in `marker_groups.json` with members, roles and two
relations. Members: `haemoglobin` and `haematocrit` (role `concentration`), `rbc` (`cell_count`),
`mcv` (`plasma_independent_control`). Relations: `erythroid_co_movement` across the three
concentrations, and `haemoconcentration_discriminator`, which uses `albumin` as the plasma-based
discriminator separating a draw artefact from a true erythron expansion — plasma-based analytes rise
with plasma contraction while MCV, being per-cell, does not.

`albumin` is an operand without being a member. Precedent verified before relying on it:
`bilirubin_isolation` already takes `haemolysis_index` and `ld` as operands, neither of which is a
`hepatocellular` member.

**`group_levers` is empty, deliberately.** The read-constants for `haematocrit` / `haemoglobin`
(RCV-derived) and the `plasma_volume_status` lever are **withheld**: chat identified sources but could
not supply DOIs verbatim, and `evidence_refs` in this file is DOI-shaped. #95's I1 extension forbids an
uncited constant that influences a gate, so fabricating a DOI or landing `evidence_refs: []` would
break the invariant in the same repo that asserted it, one decision later. Structure needs no
citations; constants do. `plasma_volume_status` is recorded in `_deferred_levers` using the existing
three-field shape (`reason` / `target_markers` / `provisional_grade`) — that block carries no
`blocked_on` field, so none was invented.

**Consequence, recorded rather than papered over:** `erythroid` produces no news beyond the default
gates until the follow-up lands, and **the TRT→Hct concern remains uninstrumented.**

**Status:** Landed. Reference content only — no migration, no producer change.

**How you know:** `groups` confirmed a list (not a dict) and the authored-group schema confirmed
against the `hepatocellular` element rather than against the brief; `relation_kinds` still carries
`co_movement` and `discriminator`; all five referenced ids (`haemoglobin`, `haematocrit`, `rbc`, `mcv`,
`albumin`, plus `protein_total`) resolve in `marker_canonical.json` v0.3; diff **30 insertions, 0
deletions**, with every non-`groups` key and both pre-existing groups byte-identical to master; backend
suite **206 passed**.

**The test gate is weak by construction and is reported as such.** This commit adds content no test
reads. `producer.py`'s docstring lists `relations_rendered` and `shared_levers` under "Emits NONE of"
(4b), and greps confirm zero consumption of `relations`, `group_levers`, `precondition_phase` or
`references` anywhere in `backend/interpretation/` — the producer reads membership, roles and display
names only. So 206-green means **unchanged, not verified**: the authored relations are 4b-latent and no
producer output moved, which is the expected result, not evidence of correctness.

**Do not revisit unless:** the follow-up lands captured DOIs, at which point the constants and the
lever promote and this entry's withholding is discharged.

---

### 97. `trt_erythrocytosis_watch` was not ready to promote — and one of its two blockers was not real

**Decision:** #95 set `blocked_on: []` and `status: "ready_to_promote"` on
`_deferred.relations.trt_erythrocytosis_watch`. Its vocabulary blocker had genuinely cleared at v0.3,
but a **contract blocker survived underneath it**. Reclassified:

```
"blocked_on": ["4b contract: cross-group relation references"],
"status": "blocked_on_contract"
```

**One blocker, not two.** The brief proposed a second — `precondition_phase` in a phase-free producer —
and verification killed it. `hpg_gonadotropin_suppression`, an **authored, live relation inside the
promoted `hpg_axis` group**, already carries `precondition_phase: "on_trt"`, alongside a `driver` key.
Authored relations demonstrably hold arbitrary extra keys beyond the base schema, so
`precondition_phase` is precedented and cannot disqualify promotion. Recorded here as **checked and
cleared** so the next reader does not re-open it. `references` has no such precedent: zero occurrences
across the eight authored relations in both groups.

The other half of the proposed rationale — "the 4a producer does not consume it" — was rejected as a
criterion outright. It is equally true of `group_levers` and of every `relations` block, including the
`erythroid` content landed at #96. **A criterion that would disqualify the commit you just authorised
is not a promotion criterion**; 4b-latent content is authored precisely on the understanding that 4a
ignores it.

**Rationale (the general rule):** clearing a vocabulary blocker does not clear a contract blocker.
#95's three-class taxonomy applies **per-blocker, not per-entry** — a single `_deferred` entry can hold
more than one class of block at once, and discharging one says nothing about the others. #95's clearing
of the vocabulary blocker was correct; only the count of what survived beneath it was wrong.

**Status:** Landed. Corrects #95, which is locked and unedited.

**How you know:** `precondition_phase` found on `hpg_gonadotropin_suppression` in the authored
`hpg_axis` group; `references` absent from all eight authored relations; zero hits for either construct
in `backend/interpretation/`; `_deferred` diff confined to the single relation object (4 insertions, 2
deletions); backend suite **206 passed**, unchanged.

**Do not revisit unless:** 4b defines the contract for cross-group relation `references`, which is the
one thing still holding this relation.

---

### 98. Three standing guards, each replacing care with a mechanism

**Decision:** three rules land, each converting a failure that "being careful" was supposed to
prevent into one a mechanism catches.

**1. Reference-JSON edit guard.** `backend/reference/*.json` is hand-aligned and pure ASCII with
non-ASCII as `\uXXXX`. Never construct a `\uXXXX` escape inside heredoc source — the Bash tool's
heredoc consumes one backslash **even when quoted** (`<<'EOF'`), so the escape arrives at Python as a
literal character and is written into the file. Build the backslash via `chr(92) + "u2014"`, or write
the script to a file. After any edit, assert `raw.isascii()` and zero literal em dashes, and that the
file still parses. No `json.dump` round-trips.

The property that makes this worth a gate rather than a note: **the failure is silent in the direction
that writes bad bytes.** It bit twice in one session. The first time the malformed string failed an
assertion — loud, harmless. The second time it *succeeded*, producing a valid, value-identical file
that violated the encoding convention, and was caught only by reading the result. A defect whose safe
mode is loud and whose damaging mode is silent will not survive contact with the next session on care
alone.

**2. Push branches even while holding for review.** A local-only branch is unreadable to chat —
`raw.githubusercontent.com` 404s — so a hold-before-merge gate that chat cannot independently verify
rests on Code's report alone. That is precisely what the loop's evidence rules exist to prevent, and it
recurred this session: the go for #96/#97 was given explicitly on report rather than on bytes. Pushing
is not merging; it costs nothing. Push when work becomes reviewable, not when it lands.

**3. Post-close-out agreements get a receipt at the moment of agreement.** Recorded in `HANDOFF.md`'s
header. An agreement reached after a close-out is written has nowhere to live — not in a brief, not in
the close-out already on disk, and the next brief carries it only if someone remembers. **Q37 is the
worked example:** flagged at #95's close-out, agreed; flagged again before #96's merge, agreed; landed
only at #97's, on the third session. Both parties said yes both times and the mechanism still lost it.
This is the step-0 receipt breach from the opposite end — step 0 protects work in flight, this protects
an *agreement* in flight.

**Rationale:** all three share a shape. Each was already understood by both parties, each was
re-committed to verbally, and each still failed on the next pass, because an understanding held in a
person's head or a chat scrollback is not a control. The general form: **when a lesson has to be
re-learned, the fix is not to learn it harder — it is to find the surface that will enforce it when
nobody is paying attention.** #94 made this argument for derived artifacts; these three apply it to
process.

**Status:** Landed. Governance only.

**How you know:** `feat/interpretation-view-skeleton` verified **present on origin** and readable —
all three raw URL forms (plain, `refs/heads/`, SHA-pinned) return HTTP 200 for
`DECISIONS_LOG.md`, `OPEN_QUESTIONS.md` and both reference JSONs; both reference files verified
`isascii() == True` with zero literal em dashes after this session's edits;
`feat/erythroid-group-authoring` pushed before merge and confirmed readable at 200.

**Correction to the premise that prompted rule 2:** the observed 404 was on
`feat/erythroid-group-authoring`, which was genuinely local-only. It was generalised to
`feat/interpretation-view-skeleton`, which is **pushed and fully readable** — so O3's re-verify is not
blocked by branch visibility and can proceed now. The rule stands on the branch that really was
invisible; the second instance was an inference, not an observation, and testing it took one command.

**Do not revisit unless:** the Bash heredoc's backslash handling changes, which would only widen what
rule 1 permits, never narrow it.

---

### 99. `haematocrit` constant landed at published RCV; `haemoglobin` withheld

**Decision:** `marker_interpretation.haematocrit.min_meaningful_delta` is set to
`{mode: "relative", value: 0.12}`, cited to **Thirup 2003**
(`10.2165/00007256-200333030-00005`), which reports CVi 3% and CVa 3% across 12 studies / 638
adults — giving a ~12% relative change at the 95% level between successive values 1 day to 1–2
months apart. The estimate is stated to hold for athletes.

**`haemoglobin` is deliberately not authored.** The correct source was identified and its DOI
verified (**Buoro 2018**, `10.1515/cclm-2017-0902`, PMID 29303771), but its public abstract reports
only aggregate ranges, not the per-parameter figure. Transferring haematocrit's 0.12 across two
collinear markers would be **inference laundered as a citation** — the citation would point at a
paper that does not state the number. It falls back to `_defaults` 0.30 until the value is actually
read. Withheld under I1.

**Rationale:** this is the citable half of #96's withholding, and only the citable half. The
distinction being enforced is that a DOI attached to a value the paper does not contain is worse
than no citation at all: it converts an unsupported number into an apparently supported one, and
`evidence_refs` is exactly the field a reader trusts to have done that checking.

**Consequence, recorded plainly — this does not instrument the TRT→Hct erythrocytosis watch.** At
0.12 relative, an observed 0.44 → 0.47 (+6.8%) still produces **no news**, and the range gate does
not fire until the lab's upper bound at 0.54. **The 0.50–0.54 action band remains uninstrumented**,
pending `safety_threshold` (Q34). Landing this constant makes the erythroid group *less* silent, not
adequately instrumented.

**Status:** Landed. Reference content only.

**How you know:** `evidence_refs` string matches the source character-for-character;
`haemoglobin` confirmed absent from `marker_interpretation`; both reference files verified pure ASCII
with zero literal em dashes (#98 guard, run against its own session); diff confined to the two
reference files with deletions limited to the `_deferred_levers` entry and the empty `group_levers`
line — no reflow; backend suite **206 passed**.

**The test gate is weak by construction, again.** `marker_interpretation` is read by
`gates.min_meaningful_delta`, but no test covers `haematocrit`, and `group_levers` is not producer-
consumed at all. **206 green means unchanged, not verified.**

**Do not revisit unless:** the Buoro per-parameter figure is read from the full text, at which point
`haemoglobin` lands and this entry's withholding is discharged.

---

### 100. `plasma_volume_status` promoted with verified citations — and `evidence_refs` admits non-DOI identifiers

**Decision:** `plasma_volume_status` moves out of `_deferred_levers` into `levers`, grade **high**,
and `erythroid.group_levers` is populated with it. This discharges the lever half of #96's
withholding. The grade rests on directly measured evidence rather than inference: **Dill & Costill
1974** (`10.1152/jappl.1974.37.2.247`) observed Hb and Hct before and after running to a 4%
body-weight loss and derived the blood/plasma/red-cell volume relations from them, on the explicit
assumption that circulating red cell mass is unchanged; **Matomäki et al. 2018**
(`10.14814/phy2.13749`) revisit the equation, confirm it for plasma and serum biomarkers, and
identify where the constant-red-cell-mass assumption breaks.

`member_effects` carries `haemoglobin`, `haematocrit` and `rbc` as `raises`/high. **MCV is omitted,
and its absence is the signal** — it is the plasma-independent control and does not move. The
`direction` enum was enumerated against the file before writing and holds only `raises` and
`lowers`, so no "no effect" value was invented; the omission mirrors the existing alcohol/`ggt`
de-select precedent. The `de_select_hint` keys to `haemoconcentration_discriminator`.

**`evidence_refs` now admits stable non-DOI identifiers — a convention extension, flagged before
staging rather than slipped in.** `NBK459198` is an NCBI Bookshelf ID; no DOI exists for it.
Verified with a positive control per the paired-control rule: all **13** pre-existing
`evidence_refs` strings across `levers` and `marker_interpretation` are DOIs, zero non-DOI, with the
matcher shown to discriminate on the 13 it accepted. So this is genuinely the first.

This is an **extension, not a loosening of I1**. I1's requirement is a *resolvable citation* — a
reader can reach the source and check the claim. A DOI is the usual instrument for that, not the
requirement itself. Refusing a stable Bookshelf ID would have forced the alternative of either
dropping a real source or attaching a DOI that does not exist, and the second is precisely the
failure #99 refuses for `haemoglobin`.

**`channel` stays two-valued.** `plasma_volume_status` is `behavioural` — correct on the axis
`channel` actually encodes, which is how the actor acts. That this lever moves the *measurement*
rather than the *physiology* is a different axis; it is confined to `mechanism_summary` and logged
as Q39 rather than smuggled in as a third enum value.

**Status:** Landed. Reference content only. `_meta.binds_to` unchanged at v0.3 (#95) — no vocabulary
change.

**How you know:** all three `evidence_refs` strings match character-for-character;
`plasma_volume_status` present in `levers` and absent from `_deferred_levers`, with
`hepatic_steatosis` untouched; `channel` confirmed `behavioural` against a two-valued enum
enumerated from the file; `erythroid.group_levers` carries three `member_effects` and no MCV entry;
backend suite **206 passed**, no fixture or oracle moved (0 changed test files, against a control of
21 tracked test files, proving the check can see them).

**Do not revisit unless:** 4b introduces `effect_locus` (Q39), which would give the
measurement-vs-physiology distinction a real home and make this entry's `channel` reasoning moot.

---

### 101. Four erythroid RCV constants from a single published source — supersedes #99's haematocrit 0.12

**Decision:** `haemoglobin` 0.08, `haematocrit` 0.08, `rbc` 0.08 and `mcv` 0.02 land in
`marker_interpretation`, all cited to **Coşkun et al.** (`10.1515/cclm-2017-1155`, EFLM Working Group
on Biological Variation) — 30 healthy subjects, weekly sampling over 10 weeks, Sysmex XN 3000. The
source **publishes RCV directly** rather than requiring derivation, which is the point: every CVa
assumption chat introduced is removed.

**#99's haematocrit 0.12 is superseded, not corrected in place.** That value came from Thirup 2003,
whose derivation embeds a 2003-era CVA of 3%; this source measures CVA at 0.63%, and that difference
is the entire gap. **Thirup is retained on `haematocrit` as a second ref**, demoted to the source of
the long-interval caveat rather than of the number.

**Chat's earlier hand-derivations are withdrawn** — 0.08 for haemoglobin from an assumed desirable-APS
CVa, and ~0.09 for a re-derived haematocrit. Both happened to land near the published figures, which
is luck, not method. Chat also mis-targeted Buoro 2018 (`10.1515/cclm-2017-0902`) as the source; that
is a different paper, cited by this one as ref 23. Recording the near-miss matters more than the miss:
a derivation that lands close to the right answer by accident is indistinguishable from one that
worked, and #99 withheld `haemoglobin` precisely to avoid banking on that.

**Convention, stated here rather than left implicit: constants are derived two-sided, Z = 1.96**,
because the delta gate is direction-agnostic — it asks "did this move meaningfully", not "did it rise".
EFLM's own calculator defaults to one-sided (Z 1.64); the one-sided statistic belongs with
`safety_threshold` (Q34), which *is* directional. Coşkun's Methods state Z = 1.96, so these four
already conform.

**Arithmetic verification note:** three of the four published RCVs reproduce exactly from the source's
own equation and inputs; `haematocrit` reproduces to 8.01 against a published 8.00. A second
independent identity from the same table (`B_APS = 0.25·(CVI² + CVG²)^½`) also fails on the haematocrit
row alone, by a larger margin, and cannot be reconciled with any published CVG for that measurand
(solving backwards demands ≈4.56 against published 5.46/5.51). The anomaly is confined to one row, is
immaterial at the resolution of the constant landed — 8.00 and 8.01 both give `0.08` — and **no input
was reconstructed to force agreement**. Chat worked from a text extraction of the PDF; the artefact may
originate there rather than in the source.

**Consequences, recorded plainly:**

- **(a)** At 0.08 the August panel needs `haematocrit` ≥ 0.475 to trip the delta gate, against ≥ 0.493
  at 0.12 — moving it from a gate that could not plausibly fire to one that plausibly will, given 0.47
  on an increased dose with a new steady state pending.
- **(b)** `mcv` moves from the 0.30 default to 0.02, a **fifteen-fold tightening**. This is what makes
  "MCV stays flat" in `haemoconcentration_discriminator` a testable claim rather than a tautology: at
  0.30 an MCV could move substantially and still read as flat, so the discriminator would have
  confirmed haemoconcentration almost regardless of the data.
- **(c)** The **0.50–0.54 band remains uninstrumented.** This is still a delta gate; coverage there
  waits on `safety_threshold` (Q34).

**Status:** Landed. Reference content only — `marker_groups.json` untouched, no migration, no producer
change.

**How you know:** the self-check above, run before writing, with a control showing a desirable-APS CVa
gives 9.09% for haemoglobin against a published 7.76 — so the check discriminates and the source's RCV
column does use measured CVA; diff confined to `lever_dictionary.json`, 30 insertions / 3 deletions,
the deletions being only the three superseded haematocrit lines; `_meta.binds_to`, `levers` and
`_deferred_levers` all unchanged; file verified pure ASCII with zero literal em dashes (#98 guard);
no test names `haematocrit` or pins `0.12`, verified with a control confirming the grep reaches test
files; backend suite **206 passed**, zero changed test files against a control of 21 tracked.

**206 green is reported as unchanged, not verified** — `marker_interpretation` is read by
`gates.min_meaningful_delta`, but no test covers any of these four markers.

**Do not revisit unless:** the interval question (Q38) resolves toward interval-banded constants, which
would replace all four scalars.

---

### 102. A merge authorisation is a cross-lane instruction and needs a receipt — #98 rule 3 widened

**Decision:** #98 rule 3 currently sends *agreements* to `HANDOFF.md`. Widened by one word: **any
cross-lane instruction, including a go, is written to `HANDOFF.md` or it did not happen.**

**Rationale:** `feat/erythroid-constants-and-lever` was completed, gated, pushed and held for a go. The
go was given explicitly in chat, with the bytes verified. It never reached Code, because chat has no
channel to the repo and the next relay carried a different brief instead — one written against a master
state that assumed the merge had happened. The branch sat unmerged for a full session, and the
following brief's supersession premise silently failed.

**This is the third instance of one shape.** Q37 was agreed twice and landed on the third session. The
post-close-out citation agreement needed #98 rule 3 to exist before it had a home. Now a *go* — which is
not an agreement but an instruction — had no surface either. Each time the fix was scoped to the exact
form that had just failed, and each time the next failure arrived in a form one step outside it. The
widening is deliberately to the general category rather than to "goes as well as agreements", because
the pattern is that the category keeps being drawn too narrowly.

**Status:** Landed. `HANDOFF.md` header updated.

**How you know:** master sat at `1d49000` with DECISIONS max #98 while `#99`/`#100`/`Q38`/`Q39` existed
only on the unmerged branch — verified at this session's open, and the reason this brief's ANCHOR had
to be replaced.

**Do not revisit unless:** a fourth instance appears in a form outside "cross-lane instruction", which
would mean the category is *still* drawn too narrowly.

---

### 103. Evidence that looks like evidence — the paired-control rule lands, with identity and coupling

**Decision:** the paired-control rule reaches its canonical home as `FEEDBACK` §17, with two additions
earned in the session that landed it, and two `CLAUDE.md` standing lines.

**1. The base rule.** Any negative offered as evidence — a 404, zero rows, an empty grep — must be
paired with a **positive control in the same command**, and the control's output goes in the report.
A bare negative is equally consistent with "the thing is absent", "the probe was aimed wrong", and "the
probe could not have succeeded". Agreed post-close-out at #98 rule 3 and receipted then; this entry is
the landing, which is the distinction that rule exists to make.

**2. Identity, not just function.** The base rule is necessary and not sufficient. A control proves the
*instrument* works — it says nothing about whether the artefact probed is the intended one. After a
rebase, three `curl` probes returned honest 200s **against the pre-rebase branch still on origin**. The
control passed; the bytes were abandoned. So: **where a probe could succeed against the wrong artefact
— stale refs, cached CDN copies, reused branch names — pin to a SHA or assert on content only the
intended version carries.** "Does something exist at this URL" and "is it what I just built" are
different questions; a status code answers only the first.

**3. A check whose failure cannot stop what follows is not a check.** In the same session an assertion
failed loudly and was followed, in the same command, by `git add && git rebase --continue` — so the
rebase completed and committed conflict markers into an append-only ledger. The machinery existed; the
coupling did not. Chaining a verification to an action is a reflex rather than a decision, which is the
precise condition #98 identifies as needing a gate rather than diligence.

**Rationale:** all three are cases of **evidence that looks like evidence**. An unpaired negative looks
like absence; a passing control looks like confirmation; a chained check looks like verification. Each
produces a report that reads correct to someone who was not there — which is the only reader that
matters, since the whole point of the loop is that a later session cannot re-run the moment.

Note the shape of how this arrived. The base rule was proposed after three instances, and then failed
*twice more in the session that implemented it*, in forms one step outside its wording. That is the
same widening #102 had to make for cross-lane instructions, and the same lesson #98 states generally:
when a category keeps being drawn too narrowly, widen the category rather than adding the next
instance to a list.

**Status:** Landed. `FEEDBACK` §17 + two `CLAUDE.md` standing lines, both repo-specific — the shared
block is untouched, so no G1 breach and no paired obligation.

**How you know:** both additions are worked examples from this session with their artefacts named — the
three 200s against a pre-rebase ref, and the conflict markers committed at `fa10b70`'s pre-amend state;
shared block verified at `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232; backend suite **206 passed**,
unchanged.

**Do not revisit unless:** a fourth form appears outside "evidence that looks like evidence", which
would again mean the category is drawn too narrowly.

---

### 104. Safety threshold lands as a third gate; the asset itself is withheld under I1

**Decision:** `backend/reference/safety_thresholds.json` is created, and `gates.safety_gate()`
compares a value to an authored policy constant. **Closes Q34.** The asset carries **no live
entries**: `_deferred.haematocrit` records the intended shape (0.50 / 0.52 / 0.54, `direction: above`,
`contested: true`, `value_plausibility` [0.20, 0.70]) blocked on citation capture. Chat identified the
band values but has no verified DOIs, and landing uncited constants would break the invariant this
repo asserted at #95, one decision after asserting it.

**A safety threshold is a different comparison class from anything the contract could previously
express.** `delta` compares a value to its predecessor; `range_gate` compares it to a bound that
arrived *with the report*. Both answer *has this moved relative to something in the data*. A safety
threshold compares a value to a number from **outside** the data that does not care what preceded it.
It fires on a **level, not a transition**; its value is **contested rather than measured**; and it is
the closest this platform comes to the regulatory line — so it surfaces a band and its sources and
**never names an action**, enforced by schema test rather than by care.

**The withhold-computed rule (contract V2) is not violated.** That rule exists so the platform never
second-guesses the lab on *the lab's own interval*. A safety threshold is a different bound from a
different authority, and never writes to `flag`. **Consequence, stated so it is not read as a bug:**
output will legitimately carry `range_gate.is_out_of_range: false` alongside
`safety_gate.status: in_band`. Both are correct, from two authorities. The renderer must show both
with their sources rather than reconcile them into one verdict.

**Why a separate asset rather than `lever_dictionary.json`.** Its read-constants are *measured*
quantities — CVI/CVA-derived RCVs that do not expire. These are committee judgement about where a
level becomes worth surfacing. That difference earns a `review_due`, which measurement constants do
not carry: guidance is revised, and a threshold that silently outlives its source is worse than none.

**The 4a/4b boundary is enforced negatively, which makes this entry the authorisation.**
`_FOUR_B_MEMBER_FIELDS` is a **denylist** — the test asserts `field not in member`. `safety_gate` is
therefore permitted by *omission*, not by assertion, and nothing in the test suite states that
emitting it is intended. This entry is that statement: `safety_gate` is a 4a field (pure arithmetic,
no phase, no relation), and any future 4a field is authorised by a decision entry and nothing else.

**Status:** Landed. Asset + schema guard at `436111a`, wiring at `262c9ac`.

**How you know:** four pre-write verifications, each with a positive control — asset absent (control:
4 files present); `_is_moved` emitted at `producer.py:114` (contract surface, confirmed); the three
named oracle tests are field-by-field (confirmed by reading them); `_FOUR_B_MEMBER_FIELDS` is a list
of six 4b fields not containing `safety_gate`. The schema validator **raises** on a synthetic band
carrying `recommended_action`, shown alongside a positive control accepting the same band without it.
Asset verified pure ASCII, zero literal em dashes — the #98 guard caught three real em dashes typed
into the prose. **258 passed** (206 → 222 → 258). `interpretation_s2.json` unchanged;
`marker_groups.json`, `lever_dictionary.json` and `marker_canonical.json` untouched.

**Correction to the brief's premise, recorded because it changed the implementation:** the risk was
never the oracle tests. It is **three exact-dict asserts on `news_gate`** (`fsh`, `ast`, `vitamin_d`)
which pin that return shape whole. They constrain how the second arm may be added — see #105.

**Do not revisit unless:** citations land, at which point `_deferred.haematocrit` promotes and the
schema test starts validating something.

---

### 105. Gate 1 gains a second arm, and it is not demotable

**Decision:** `news_gate` becomes `news_gate(delta_obj, safety_gate=None)`. The keyword is optional and
defaults to `None`, so every pre-existing call site and all 206 prior tests behave identically. When a
`safety_gate` is passed and its `band_change` is non-null, `is_news` is forced true and
`safety_band_<change>` is **appended to `basis`** — never added as a sibling key. The return shape
stays exactly `{is_news, basis}` on every path.

`news_gate` was always designed to accept further arms; its own docstring reserved a relation arm for
4b that "may append and demote". **The safety arm differs in one respect that had to be fixed before
4b exists: it is not demotable.** A relation may legitimately demote a delta-driven story — "AST rose
but GGT is normal, so this is muscle" is a good reason not to surface. Nothing may demote a band
change, because explaining *why* a value rose is a different claim from whether it warrants surfacing,
and no mechanistic account makes a haematocrit of 0.52 not worth showing. Recorded in the module
docstring now so demotion logic **inherits** the constraint rather than discovering it.

**Deviation from the brief, deliberate.** The specified resolution table does not enumerate *agreeing
operator, bound below all bands*. Taken literally, first-match-wins would fall through to the plain
comparison and report `not_in_band` for `>0.30` against a band at 0.50 — but the true value is
unbounded above and could sit in any band. That is a **false negative on a safety gate**, the one
direction never to be wrong in. Resolved to `censored_indeterminate`. The brief's own principle —
censoring destroys a magnitude, not necessarily a threshold comparison — is preserved in the other
direction: `>0.55` against a band at 0.54 is decidable whatever the true value is.

**Status:** Landed at `262c9ac`.

**How you know:** 36 new tests, written against a **synthetic** asset because the live one is empty —
a suite pointed only at the live asset would exercise `no_asset` and nothing else while reporting
green. The shape guard was verified by **mutation**: reimplementing the arm as a sibling key fails 6
tests, so the guard fails *today* if the arm is built wrong. The three pre-existing exact-dict asserts
cannot do that work yet — with no live asset, `band_change` is always null and `basis` is never
touched, so they are inert with respect to the thing they would protect.

**Do not revisit unless:** 4b's demotion logic is written, at which point this constraint is the thing
it must not violate.

---

### 106. `is_moved` renamed to `should_surface` — an emitted contract key changes

**Decision:** `_is_moved` becomes `_should_surface`, and the **emitted group key `is_moved` becomes
`should_surface`**. The predicate gains `or m["safety_gate"]["status"] == "in_band"`.

**Rationale:** once safety status feeds the predicate it is no longer testing movement. A persistently
elevated value that has not moved at all must still surface — otherwise it hides inside a quiet group,
which is the exact failure the gate exists to prevent. A key named `is_moved` that reports true for
something that did not move is precisely the drift this repo punishes elsewhere; renaming it costs two
tests, and keeping it costs the meaning of the word.

**Cost, paid knowingly:** this is a contract-surface change. **Three** tests moved, not the two the
brief predicted — the third is `test_all_stable_group_is_not_moved`, the G6 non-vacuity guard that
proves the predicate is not hardwired true, now `test_all_stable_group_does_not_surface`. O3's already-
owed re-verify of `feat/interpretation-view-skeleton` now also covers this rename; that branch was cut
against a pre-#86 shape and already owed a contract reconciliation.

**Status:** Landed at `262c9ac`.

**How you know:** `grep is_moved backend/ --include=*.py` returns 2 hits, both inside the docstring
that explains the rename; `should_surface` returns 10. The G6 non-vacuity guard still asserts `False`
for an all-stable group, so the predicate remains falsifiable.

**Do not revisit unless:** the frontend consumes `is_moved` somewhere not yet reconciled — which is
what O3's re-verify is for.
### 107. CBT-I titration controls on total sleep time, with sleep efficiency as a floor rather than the target

**Decision:** the titration rule computes the prescribed window from rolling mean TST plus a buffer, and
exits on TST plateau with SE held ≥85% — not on SE reaching or stalling at a threshold. SE is the
constraint that keeps the window honest; TST is the outcome the protocol exists to produce.

The completed 2026-03-19 → 2026-05-13 block is the evidence. Mean SE peaked at **0.958** at a 6h30
window and declined monotonically to **0.896** at 7h38, while mean TST rose across the same span to
**7.13h**. An SE-maximising rule terminates at the point of greatest efficiency, which on this data is
roughly 45 minutes short of need. Sleep need is estimated at **~7h30**, from the only week where time in
bed was not the binding constraint (week 7, TIB 8h07 against a 7h38 prescription, TST 7h29, SE 92.2%),
corroborated by the two post-prescription nights at SE 0.925 and 0.989. The workbook's own
`Biological Sleep Need (TST24)` field is **not** used: the FAQ confirms it is TST plus naps, so
restriction lowers it and it reports need falling as a consequence of the intervention. Circular.

**Status:** Rule adopted; engine gated behind schema and import. Phase-1 substrate landed
(`feat/cbti-module`); the engine and its replay against the imported block are phase 2 (brief Steps 5–7).

**How you know:** nine prescription blocks reconstructed from `Rx Bedtime` change-points against a
constant 05:00 anchor and loaded to Railway (block id=1, contiguous effective ranges, `superseded_by`
chained); 53 diary nights loaded, recomputed SE reconciled against the sheet's `Sleep Efficiency`
**0/53 mismatch to ±0.001** (worst residual 0.000047), with a negative control that flags exactly one
injected 0.01 perturbation. The block's exit aggregates as stored — mean TST **428 min (7.13h)**, mean
SE **89.6% (0.896)** over the final window — reproduce this decision's own decline figures. Engine
replay (Gate 5) is **not** yet run.

**Do not revisit unless:** a second unconstrained week contradicts the ~7h30 estimate — it currently
rests on one observation.

---

### 108. The CBT-I module is block-structured, and read-only with respect to readiness

**Decision:** CBT-I is modelled as repeating blocks, not a single arc — this is the third block, two
prior completions. A block opens with `decision='adopt'` carrying the in-flight prescription and closes
at the block level (`closed_on` + exit metrics); the ledger persists permanently after closure and is
the baseline any later block titrates against. Diary fields on `DailyRecord` are sparse by design,
legended by `cbti_prescription.effective_from/to`, and render only while a block is open. No new column
feeds readiness in this phase — a titration artefact must not propagate into training-load decisions
before the module has demonstrated it is calibrated.

Early-morning awakening is instrumented but does not drive compression: wakes cluster at
**04:32 ±21 min** — time-locked, not distributed — so EMA is diagnostic, not a compression signal.

**Status:** Adopted. Schema landed as two append-only ledgers (`cbti_blocks`, `cbti_prescriptions`)
plus nine nullable AM-moment diary columns; append-only is a model+application invariant with the
`decision` domain as the one DB-enforced constraint (`ck_cbti_prescription_decision`).

**How you know:** readiness isolation verified this session — a repo-wide grep confirms no code path
outside the models, the importer, tests, and the migration reads any of the nine diary columns or either
cbti table; readiness code (`context_builder.py`, `engine/selection.py`) reads none. One closed block
loaded and its supersession chain and contiguous effective ranges verified against Railway. The
04:32 cluster figure is inherited from the block's diary and is not re-derived here.

**Do not revisit unless:** a block opens under a materially different wake anchor and the 04:32 cluster
moves with it, which would reclassify it from conditioned arousal to anchor-relative.

---

### 109. A reconciliation is not evidence until its negative control has fired — sibling to #103

**Decision:** a reconciliation offered as proof that imported data matches its source ("all 53 nights
match to ±0.001") must, in the same run, perturb one record and confirm the comparator flags **exactly**
that record. An all-match result is equally consistent with "the data is faithful" and "the comparator
is blind" — a swallowed exception, a misaligned join, or a unit mismatch passes identically. The perturb
→ detect → restore cycle proves the check *can* fail before its *not* failing is allowed to mean
anything. This is #103's paired-control rule (a negative needs a positive control) applied to the
matched case: a clean reconciliation is a negative finding about mismatches, and it needs its own
positive control.

Earned in the CBT-I import (#107): the independent SE recompute caught a real defect — an unconditional
+24h midnight wrap under-read one after-midnight night by **0.445** — which a comparator that could not
see mismatches would have hidden as a clean pass. The negative control (perturb 0.01 → exactly one
night flagged) is what licensed trusting the eventual 0/53.

**Status:** Adopted as method; realised in `import_cbti_block.py` (`reconcile_with_control`) which aborts
the load if the control does not localise its injected mismatch, and in `tests/test_cbti_import.py`.

**How you know:** the importer's own output — `control_ok=True (perturbed 2026-04-14, flagged
['2026-04-14'])` alongside `real_mismatches=0` — and the seven synthetic-data tests (223 passed, was
216). The midnight-wrap defect and its 0.445 residual are the worked example.

**Do not revisit unless:** a reconciliation gate is added that cannot express a negative control (no way
to perturb one record), which would mean the check is structurally unfalsifiable and should be redesigned
rather than trusted.

---

### 110. A null result is not evidence of absence unless the search proves it had scope — and a diagnostic must not require the operator to redact its output

**Decision:** Two clauses, both from one failure chain in this module's closure.

**A search whose negative outcome founds a conclusion must report what it scanned.** File count, not
just match count, and a positive control demonstrating it can return a hit on a known value. The design
chat ran `Select-String -Path $env:USERPROFILE\.claude\**\*.jsonl` to establish that no credential had
reached the session. PowerShell has no globstar; `**` resolves as a single path segment, so the command
enumerated approximately **zero** files. The empty output was read as "no matches" when it meant
"nothing was searched," and a real exposure was declared non-existent on that basis. The corrected
search opened **60** files and found **54** occurrences digest-identical to the reference credential
out of 79 credential-shaped matches, across **7** session transcripts — including six sessions
predating this work, and a second distinct credential digest consistent with an earlier rotation.

The design chat then drafted a canonical entry retracting a valid security recommendation, and it was
refused at execution because the artefact was checked rather than the account accepted. That refusal is
the rule working; the draft is the reason the rule is needed.

**A diagnostic must not require the operator to redact its own output.** The instruction
`Get-Content .\backend\.env | Select-String -Pattern 'DATABASE_URL|PASSWORD|KEY'` matched key *names*
and returned whole lines including values — publishing a live API key and a Fernet key in the course of
establishing that no credential had been published. Any command touching a secrets file returns names,
counts, digests, roles, line numbers, or presence. Never values. `probe_resolver.py:143` already states
it: *presence only — the value is never read into output*. The live instance of this clause is
`railway variables --service <svc> --kv`, which prints values and is the vector recorded at Q44.

The two clauses are one failure: a search that proved nothing and a search that printed everything,
both written to answer the same question.

**Provenance, since it was contested and is the worked example for both clauses.** Record *role* does
not establish origin — `tool_result` blocks persist as `user`-role records by API convention, so a
user-role record carrying a credential is ambiguous. *Content block type* resolves it. The census
across all seven transcripts: `tool_result` ×4 (all `Bash`), `tool_use` ×16, plain-string user content
×3, `queue-operation` ×2, `text` ×1. Both mechanisms are real — four sessions carry the credential only
as tool output, and three carry it as operator-supplied input. The two accounts reconcile rather than
one being wrong; role was function, block type was identity.

**Status:** Adopted. The corrected artefact check is the first application — 60 files scanned reported
alongside 79 matches, positive control passed, and identity established by digest with no value
rendered.

**How you know:** scope proof is the 60-file count against the original's ~0; the positive control
returned a hit on the reference; provenance was reported by content block type, tool name, and line
number with no content; the leak-vector command was reported with its credential-shaped substrings
masked by pattern; `.dbenv` was digested before deletion so identity survived the ops action. No digest
of the un-rotated credential appears in this entry.

**Do not revisit unless:** a search is genuinely unscopeable and the work is blocked by it — which
would mean the rule needs an escape hatch, not an exception.

---

### 111. Secret-rendering commands are prohibited by instruction, not by configuration — the declarative layer does not hold

**Decision:** The prohibition on commands that render secret values lives in `CLAUDE.md`'s shared
block, and **that is the enforcing layer**. `.claude/settings.json` deny rules are added as a second
layer and are explicitly **not** relied upon.

This is not a preference. Claude Code's `permissions.deny` for Bash is documented, but non-enforcement
reports are open and recurring and the standard remedy is a custom `PreToolUse` hook to obtain the
behaviour the configuration already promises. Piped and compound commands are a known bypass. The
layer is therefore a speed bump, and recording it as such prevents a later reader assuming coverage
that does not exist.

**Two structural constraints shaped the deny list.** A deny rule cannot carry an allowlist exception —
a broad pattern blocks every matching call including narrower permitted ones. Separately, a `Read()`
deny blocks the Read tool but not an equivalent Bash invocation, so both forms are listed for
`backend/.env`.

**The brief's narrow pattern was corrected at execution by reading the CLI's own help.** The plan kept
the deny scoped to `railway variables --kv` specifically to preserve `--json` as the sanctioned
substitute. `railway variables --help` states that `--kv` **and** `--json` both print raw values, that
the base command is `variable` with `variables` as an alias, and that `-k` is a short form. That is
four bypasses of a `--kv`-only pattern, and the premise for keeping it narrow was false. Because the
sanctioned substitute was independently changed to `railway run <cmd>` — a different command with no
flag dependency — the pattern could widen to the whole `railway variable(s)` family without blocking
the replacement. Verified in that order: help first, widen second, then run the substitute against the
landed deny list.

**The prohibition is general, not vector-specific.** `railway variables --kv` is the vector Q44 named,
but bare `railway variables`, `printenv`, `env` and `cat` of a `.env` are the same hazard by another
route — the last of which is how a live API key and a Fernet key were rendered *while establishing
that no credential had been rendered*.

**Project-scoped Claude Code configuration is repo-canonical.** `.claude/settings.json` is committed,
deny patterns only, with no path that reveals structure beyond what `.gitignore` already does. This is
less of a first than it looked: `.claude/commands/closeout.md` was already tracked, so the precedent
existed and this extends it. Machine-local files beside it (`settings.local.json`, `launch.json`) stay
untracked, which is why the staging rule is `git add .claude/settings.json` and never the directory.
Under the two-lane model the repo is what Code reads, so a rule that is not in the repo is not a rule
for a fresh clone or a second machine.

A `PreToolUse` hook is the layer that would actually enforce, since hooks run ahead of the permission
system. It is deliberately deferred until instruction and configuration are observed to fail.

**Status:** Adopted. Q44 closed by this entry. Q43 closed alongside it — both keys prod-isolated,
established by a digest comparison run at execution rather than by the brief's assertion that it had
already been run.

**How you know:** the sanctioned names-only substitute was executed **after** the deny list landed and
returned 114 injected variable names with zero values — the only proof that the rules discriminate
rather than blanket-block. `.env.example` was confirmed unmatched by any pattern (0 of 10), and
`railway run` unmatched (0 of 10). The Q43 comparison carried both controls: identical input reported
equal, differing input unequal.

**Do not revisit unless:** a session renders a secret despite both layers — in which case the hook
lands, and this entry records why it was needed rather than being the first thing tried.

---

### 112. Cross-repo propagation debt is recorded in ROADMAP NOW; `closeout.md` may only point at it

**Decision:** Work owed in a second repository — most commonly a shared-block propagation that could not
be reached under the single-repo anchoring rule — is recorded in `ROADMAP.md` under **NOW**.
`closeout.md` may reference it, but never as the store.

Three precedents existed and were used inconsistently: a `BRANCHES.md` outstanding column, an
`OPEN_QUESTIONS` next-action, and a `closeout.md` OWED list. The discriminator is **whether the record
survives the thing that created it.**

`closeout.md` is overwritten at every `/closeout` by design, so anything held only there is destroyed by
the next session — it is a pointer, structurally incapable of being a store. `BRANCHES.md` rows are
branch-scoped and reach a terminal DONE state; debt attached to one is destroyed exactly when
propagation is still owed. `OPEN_QUESTIONS` is for matters genuinely undecided, and a propagation is not
undecided — the content is known and byte-defined, it simply has not been executed. Recording known work
as a question would make that store's own semantics unreliable. `ROADMAP` NOW is the only store whose
entries are neither session-scoped nor branch-scoped and whose semantics already mean *known work, not
yet done*.

**Status:** Adopted. The owed `health-connect-app` shared-block propagation is the first and, as it
turned out, the only entry under it this session.

**Scope correction made at execution.** The brief anticipated a second instance: if Step 3's prod Hevy
round-trip blocked on a missing network route, its owed verification would land in the same store, and
two instances would make a better first application than one. Step 3 did **not** block — `railway ssh`
reaches inside the container, where the internal host resolves and no proxy is required, and the
round-trip returned HTTP 200. So the rule lands with one instance. Recording the anticipated second
instance would have been recording a hypothetical as debt.

**How you know:** the three precedents were located in the stores before the decision was made, not
inferred — `gov/session-closure-sweep`'s `BRANCHES.md` row, Q42's next-action, and `closeout.md`'s
OWED-carried list. `closeout.md`'s overwrite semantics are stated in `CLAUDE.md` under the Code
close-out ritual (steps 6 and 7: *"Overwrites a single `closeout.md`. Never appends narrative"*). The
propagation gap itself was measured rather than assumed: HCA's `CLAUDE.md` carries the shared-block
markers but greps 0 for the secret-rendering rule where health-app greps 1.

**Do not revisit unless:** a second repository's debt needs to survive a ROADMAP reorganisation, which
would argue for a dedicated store rather than a different existing one.

---

### 113. An unanchored audit can certify the condition it is auditing for — match on anchors, read the matches

**Decision:** A search whose result decides whether something is *recorded* must anchor on the form
the thing actually takes — `^### 104\.`, `^## Q45\.`, a whole word — never a bare substring. And the
matches are read, not counted.

Earned in the same breath as the thing it protects. An audit ran to establish whether the CBT-I nap
resolution had a durable home; its check for `nap` in `BRANCHES.md` returned a hit, and the hit was
**`snapshot`**. Counted rather than read, that audit would have certified the decision as recorded
when it existed in no store, no commit message, and no question — leaving a silent-when-wrong field
to be attributed by convention in a later session. The audit would have produced exactly the false
assurance it was run to prevent.

This is #103's second clause — *controls discriminate on identity, not just function* — applied to
search patterns, and the same defect as the bare `s/104/107/` that #111's renumber avoided. A hit
count answers *did the pattern fire*; it never answers *did it fire on the thing you meant*. The
failure is worse in an audit than anywhere else, because an audit's output is trusted precisely when
nobody re-examines it.

**The cheaper half of the rule is the habit, not the pattern.** Anchoring is defeatable — a
sufficiently odd form slips any regex. Reading the matched text is not. Where the two conflict, read
the matches.

**Status:** Adopted as a repo-specific standing rule in `CLAUDE.md` Conventions, beside #103's
identity clause. **Not** placed in the shared block: its siblings are repo-specific, and the shared
block already carries an unpaid propagation debt to `health-connect-app` (ROADMAP NOW) that a second
addition would enlarge without benefit.

**How you know:** the `snapshot` false positive is the worked example, and it was caught in this
session's own audit by reading the match rather than the count — which is why Q45 exists at all.

**Do not revisit unless:** an anchored pattern produces a false *negative* that matters, which would
argue for reading a wider result set rather than for a different pattern.

---

### 114. Regularity is instrumented, not gating — and three other constants are recorded as unvalidated rather than chosen

**Decision:** Lights-out SD and wake-time SD are computed, stored and displayed, but do **not** gate
titration.

The proposal was a HOLD gate on lights-out SD, reasoning that the block's largest single-week efficiency
gain coincided with SD collapsing from **1.21 to 0.23**. That was two adjacent points selected from
eight. Across the full block, lights-out SD against mean weekly SE gives **r = −0.206**. Week 2
contradicts the rule outright: SD *rose* from 0.23 to 0.98 while SE *rose* from 94.59 to 95.44, the
block's highest. A >0.5h gate would have blocked **five of eight weeks, including the two best**
(95.44 and 92.23).

Wake-time SD correlates better at **r = −0.441**, but the wake anchor is fixed at 05:00 by
prescription, so its variance *is* early waking — the same phenomenon #108 instruments as EMA, and
downstream of the outcome rather than an input to it. Gating on it would compress the window in
response to a signal #108 establishes must not drive compression.

**A second adherence arm was proposed, built up, and rejected on evidence.** The gate compares diary
`lights_out` against the prescription and checks nothing at the wake end, so a night that starts on
time and ends late passes while over-running the window — and both of the replay's extensions sat on
over-run. The proposed fix was an `out_of_bed` vs wake-anchor arm at ±30 with the same ≥3-of-7
threshold. Tested against the block, **it fires on nothing**: the worst cycle is 2 of 6 outside
tolerance. Wake-end failures here are few-and-huge (+225, +90, +85, +75, +70 min); the bed-end failures
the existing arm catches are many-and-small. A count-based rule suits the latter and not the former.
Recorded as a negative result so it is not re-proposed from scratch.

**Three constants are unvalidated by this block and left as-is rather than tuned.** Choosing better
numbers from data that cannot test them is fitting the rule to one block:

- `MAX_MOVE_MIN = 30` — bound in **0 of 8** cycles. The block never reached the constraint.
- `PLATEAU_TOL_MIN = 10` — the replay **never plateaued**, so this has no empirical support at all;
  its only coverage is synthetic.
- `MIN_VALID_NIGHTS = 5` — **undeterminable**. The three failing cycles had n = 3, 3, 2. Lowering to 4
  changes nothing; lowering to 3 rescues two and still leaves one. The failures sit far below any
  defensible value, so the block cannot distinguish the options.

**Status:** Adopted. The regularity gate was removed from the engine spec before it was built; the
adherence arm was removed after being tested; the constants ship recorded-as-unvalidated in-source.

**How you know:** eight weekly rows, Pearson on complete cases; the blocked-week count computed
directly against the proposed 0.5h threshold; the endpoint arm's 2-of-6 worst case measured against the
imported block's own `out_of_bed` values; the cap and plateau counts read off the Gate-4 replay.

**Do not revisit unless:** a later block shows regularity varying independently of the fixed anchor —
which would require an anchor change mid-block, currently prohibited — or a block binds `MAX_MOVE_MIN`
or reaches a plateau, at which point those two constants have data behind them for the first time.

---

### 115. The titration buffer is +30 min, recovered from the prior block rather than assumed — and its basis week over-ran

**Decision:** Prescribed window = mean TST over the last 7 valid nights **+ 30 minutes**, floored at
5h00.

The constant is not taken from convention. It is recovered from the completed block by differencing
each prescribed window against the mean TST of the seven nights preceding it: **+36, +45, +36, +27,
+16, +48, +65** — median **+36**, mean +39, range +16 to +65. The instrument that produced those
prescriptions was the VA CBT-I Sleep Diary Calculator, so this is an observed rule, not a
reconstruction of intent.

**+30 is adopted rather than +36** because it sits at the conservative end of the observed range and
coincides with the standard sleep-restriction buffer — two independent supports rather than one. The
spread (+16 to +65, widening late in the block) indicates the source rule carried a second term this
scalar does not model, likely efficiency-dependent. That is a known simplification, recorded as such.

**The over-run acknowledgement, which belongs here rather than in #107.** #107 estimates sleep need at
~7h30 from week 7 — "the only week where time in bed was not the binding constraint" — and that week
ran **TIB 8h07 against a 7h38 prescription: +29 min of over-run**. The estimate is treated as ground
truth *because* it over-ran. That is consistent, but only once stated: it means over-run cannot also be
gated out as contamination, and a TIB-over-run gate was withdrawn partly on that ground (see #114 for
the endpoint arm; the direct TIB gate was withdrawn because SE = TST/TIB and over-run = TIB − window
share TIB **by construction**, so it measures what the SE floor already measures).

The discriminator was never over-run magnitude but **SE at over-run**: week 7 over-ran at SE 92.2% —
slept through the extra time, genuine capacity — while the replay's worst cycles over-ran at SE 85.7%,
lying awake in it. Same TIB behaviour, opposite meaning, separated by the existing SE floor without a
new gate. `basis_tib_over_run_min` is recorded per prescription so a threshold can eventually be set
against a distribution across blocks rather than this one.

**#107 is on master and append-only, so this is a forward reference and not an amendment.** The
estimate stands; only the reasoning is made explicit, because a later reader who noticed the over-run
unaided would reasonably read it as a contradiction.

**Status:** Adopted as a single scalar. Revisit if replay shows systematic divergence attributable to
the buffer.

**How you know:** seven prescription change-points with ≥4 prior nights each, all with n=7; differences
computed against the prescribed window derived from the constant 05:00 anchor. The over-run figures are
direct per-night measurements of `lights_out` → `out_of_bed` across the basis nights of each replay
cycle, not inverted from SE — the derived and measured values agree to within ~3 min, but the
measurement is what is recorded.

**Do not revisit unless:** replay shows the fixed buffer producing divergence a second term would
resolve — in which case the successor models efficiency explicitly rather than widening the scalar.

---

### 116. A check against a system mid-deploy can answer correctly from the outgoing instance — verify after settled, and confirm which instance answered

**Decision:** A verification against a deployed system must be run **after the deployment reports
settled**, and must establish **which instance answered**. A well-formed, confidently-wrong answer from
a draining instance is indistinguishable from a real result on its face.

Earned at the phase-2 merge. Master was merged and pushed; Railway rebuilds and runs
`alembic upgrade head` on deploy. The first `railway ssh` → `alembic current` returned
**`e5f2a9c7b104`** — the pre-merge revision — with only the pre-merge migration file present in the
image. Read alone, that says *the deploy did not take* and sends a reader hunting a failure that does
not exist. `railway deployment list` showed the new deployment SUCCESS and the previous one REMOVING:
the SSH had landed on the instance still draining. The retry after it settled returned
**`c4e8a2019bd7`** with all three migration files present, matching master exactly.

**This is a distinct axis from its neighbours, which is why it earns its own entry rather than a
clause.** #110 clause 1 is **scope** — did the search look at anything. #113 is **pattern** — did the
match mean what it appears to. This is **timing** — was the answer current. All three produce a
well-formed result that reads as authoritative; none of the other two would have caught this one.

**It is a property of the environment, not a one-off.** Railway cycles instances on every deploy, so
this recurs on *every* post-push production verification. `railway ssh` defaults to the first active
instance, which during a cycle may be the outgoing one. The cheap discipline: check
`railway deployment list` for SUCCESS on the new deployment before trusting an in-container answer, and
prefer a check whose result would differ between the two images — the migration-file listing did that
here, where the bare revision string alone would have been ambiguous.

**Status:** Adopted as a repo-specific standing rule in `CLAUDE.md` Conventions, beside #103's
identity/coupling rules and #113's anchored-match rule. **Not** shared-block: `health-connect-app` is an
Expo React Native app with no rolling-deploy model, so the rule has no application there, and the shared
block already carries an unpaid propagation debt (ROADMAP NOW) that a further addition would enlarge.

**How you know:** the two `railway ssh` results are the worked example — same command, same session,
minutes apart, different answers, only the second one true. The deployment list is the artefact that
explained the first.

**Do not revisit unless:** a deployment platform is adopted whose instance cycling is not observable
from the CLI, which would mean the "confirm which instance answered" half is unenforceable and the rule
needs a different mechanism rather than an exception.

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
| 13 | "Training Data → See all" | Frontend + `backend/routers/integrations.py` | **Fixed (#67).** The control was never a dead handler — `openHevyHistory` was wired; the live bug was `page_size=20` over Hevy's `/workouts` pageSize ceiling (10) → Hevy 400 → uncaught → 500 that stripped CORS (fake "No Access-Control-Allow-Origin"). Now fires and returns the full history via `/integrations/hevy/workouts/all` (server-side page loop). |
| 14 | `_capture_record_sources` upsert is non-atomic (check-then-insert) | `backend/routers/health_connect.py` | Tech-debt. Reads existing keys into memory, then inserts — two concurrent `/health-connect/sync` calls for one user could both miss a key and double-insert, hitting `uq_hc_record_source` on commit. Harmless at single-user/family scale (syncs are serial). Replace with an atomic upsert (Postgres `ON CONFLICT DO UPDATE`) **before multi-tenant**. (Finding 5, `feat/sync-writer-identity` review.) |

---

## Things tried and abandoned / not yet attempted

- **Samsung Health → Health Connect for Ring HRV:** Confirmed not possible. Samsung does not write HRV, RHR, sleep stages, or respiratory rate to Health Connect. Closed.
- **Direct Polar API integration:** Not pursued. Polar Flow → Health Connect bridge is sufficient for current use case. **Superseded by #17** — direct Polar AccessLink v4 adopted; Health Connect is no longer the Polar transport. This line predates that decision and no longer reflects the stack.
- **Direct Samsung Ring API:** Does not exist. No third-party API for Ring data.
- **Garmin Body Battery:** Explicitly closed — no API access available regardless of method.
- **Native Kotlin companion app:** Superseded by Expo for cross-platform reasons.
- **Terra unified wearable layer:** Evaluated June 2026. Third-party dependency + cost model doesn't justify itself at personal/family scale. Deferred unless scraper + SDK path proves unworkable.

### 117. The device prefills clock positions and never wakefulness magnitudes

**Decision:** Samsung-derived values prefill `got_into_bed`, `lights_out`, `final_wake` and `out_of_bed`
as **editable** defaults. `sleep_latency_min` and `waso_min` are **never** prefilled and are always
manual entry.

The split is by what consumer sleep tracking is reliably wrong about. Timing — when a sleep period
started and ended — is within actigraphic competence. Magnitude of wakefulness *within* that period is
not: devices systematically score quiet wakefulness as sleep, and the error runs in exactly the
direction that defeats sleep restriction. A prefilled-low WASO produces a diary SE biased high, which
opens the window before the sleep it is opened for exists. Prefilling those two would corrupt the
titration signal while appearing to reduce burden. Anchoring is the mechanism, not just error
propagation: a prefilled value that only needs confirming *is* confirmed, so the burden reduction is
real — which is exactly why it must not apply to the two fields the device biases. In the UI the
difference is made legible rather than incidental: prefilled clock fields carry a "from ring" treatment,
the two manual fields an "your recall — not the ring" one.

**Status:** Adopted and built — prefill in `checkin_v2.get_prefill` (`diary_prefill`), render in
`CheckInAM.jsx`. The 4h sanity gate is its safety catch: a prefill is rejected outright, never degraded
to a raw device value, when it falls more than 4h from the prescription (a 12-hour-clock corruption).

**How you know:** the scraper captures `(\d+:\d+)` from a Samsung content-desc and `parseClockToMinutes`
accepts `10:12` for `10:12 pm`, so a 12-hour phone clock silently stores a 12-hour error — demonstrated
rejected by the gate's negative control (synthetic `10:12`-for-`22:12` suppressed, valid value passes).
The `bedtime -> got_into_bed` mapping is verified bed-entry over 31 real nights (median +35 min remainder).

**Do not revisit unless:** a device is added whose wakefulness scoring is validated against
polysomnography, in which case the split is re-drawn by evidence rather than by category.

---

### 118. Titration is triggered manually and witnessed, not scheduled; block open is manual

**Decision:** The engine evaluates when the operator runs it, and a block **opens** only by a manual,
witnessed act — never on a schedule and never from a data signal. Block **close** remains engine-driven,
since the exit condition is a computation over the ledger rather than an instruction.

A prescription changes what the operator does for the following week. Minting one from a background job
means a behavioural instruction can change without the person it instructs seeing the decision or its
basis, and the ledger's design assumes decisions are auditable at the moment they are made, not
reconstructed afterwards. Manual triggering makes each row an event with a witness. It also fails safe:
a missed evaluation delays a cycle rather than voiding it. Nothing in the data should decide that a
course of treatment *begins*, which is why open is manual even though close is computed.

**Status:** Adopted. The **block-open** half is BUILT and exercised — block 3 was opened by
`open_cbti_block3.py` (dry-run default, `--apply` to write, duplicate-ABORT guard), a manual witnessed
act, writing block id=2 / prescription id=10 to prod. The **PM evaluation-trigger** half (offer
evaluation on PM close-out once >=7 days have elapsed since the current prescription's `effective_from`)
is specified but **not yet built** — deferred with `NightlyCloseOut.jsx` and the PM prescribed-lights-out
display. This entry records the decision; the trigger UI is owed (ROADMAP / next brief).

**How you know:** the replay produced eight decisions across the imported block, of which five were HOLD
— a rate that under scheduling would have written five unread rows for three actionable ones. Block 3's
manual open is the worked instance of the open-is-manual half.

**Do not revisit unless:** adherence to the module itself becomes the binding constraint, which would
argue for prompting rather than for automating the decision.

---

### 119. Waking-cause is instrumented observationally, decomposing the count without gating on it

**Decision:** Three nullable counts on `daily_records` (`wakings_nocturia_n`, `wakings_pain_n`,
`wakings_spontaneous_n`, migration `b2d5f9e04a17`) decompose `night_wakings_n` by cause. They are
**observational only** — the titration engine must not read them (`grep -rn 'wakings_' backend/cbti/`
stays empty) — and carry **no sum constraint** to `night_wakings_n`.

`night_wakings_n` records how many arousals and `waso_min` how long, but nothing recorded *why*. Sleep
restriction addresses conditioned and homeostatic fragmentation; it does not address nocturia. With PVR
229 mL on record and no urology relationship, a titration stalling at the SE floor is ambiguous between
behavioural non-response and a urological constraint, and the two imply opposite next actions. Counts
not timestamps (3am recall does not support timestamps); three columns not JSON (the series is meant to
be trended). No sum constraint because recall is imperfect and enforcement would block submission —
consistency is surfaced, never enforced. Observational isolation from the engine is what makes the
columns safe to land **mid-block** (block 3 is open) without perturbing an in-flight prescription.

**Status:** Adopted and built — migration `b2d5f9e04a17` (off head `c4e8a2019bd7`), AM capture in
`checkin_v2.submit_am`, UI in `CheckInAM.jsx` (toilet / pain / other). Value already evident: block 3's
first night was a single 03:40 nocturia trip against an ISI showing severe maintenance difficulty and
zero onset difficulty. A CPAP mask-off cross-check is filed as an objective instrument (ROADMAP).

**How you know:** the isolation grep is the guarantee — the engine cannot read what it does not
reference. The columns are nullable and additive, so historical rows and non-block nights carry NULL
without perturbation.

**Do not revisit unless:** a causal decomposition is shown to improve a titration decision, which would
move one or more counts from observational into the engine — a change that must re-clear the mid-block
safety argument, since an engine-read column is no longer inert.

---

### 120. The ISI is stored as its seven items, with the tool's total preserved separately and the canonical total derived

**Decision:** Insomnia Severity Index administrations are stored item-level (`cbti_isi.item_1..item_7`,
migration `d3f7a1908c62`). The administering tool's returned total is preserved as `total_reported`, a
fact about the tool; the **canonical total is derived on read** (`sum(item_1..7)`), never stored. Rows
are **block-scoped and nullable** (`block_id` FK to `cbti_blocks`, `ON DELETE SET NULL`): a screening or
between-block administration belongs to no block. One administration per `(block_id, timepoint)`;
`timepoint` domain is DB-enforced (`ck_cbti_isi_timepoint`: baseline|mid|exit).

The ISI is the outcome measure a block is judged by, and a **total cannot be decomposed later**. Storing
only the total would throw away the distinction that matters: item-level separates a **sleep** change
(items 1-3: onset / maintenance / early waking) from a **distress** change (items 6-7: worry / daytime
interference), which are different results and can move in opposite directions under the same total.
Storing both totals would be redundant and invites them to disagree silently; seven integers sum cheaply,
and the reported total is kept only because it is what the instrument said, not because it is authoritative.

Block 3's baseline is the worked case: QxMD returned **16**, the seven items sum to **15** (QxMD anchors
one response differently) — band unchanged (moderate clinical either way), but the discrepancy is visible
precisely because the items are the record and the total is derived, not reconciled away.

**Status:** Adopted and built — table `cbti_isi`, model `CBTIISI.canonical_total`, `backfill_cbti_isi_baseline.py`.
Block 3's baseline (items `[0,3,2,3,2,2,3]`, administered 2026-07-24 19:10 via QxMD, one night into the
block so 13 of 14 recall days are pre-block) is stored. No read endpoint yet — a UI for future
administrations waits for the exit ISI (weeks out), which lands with the evaluation trigger.

**How you know:** the seven items and `total_reported` are distinct columns; `canonical_total` is a
computed property with no backing column, so the 16-vs-15 case is representable rather than lossy. The
`(block_id, timepoint)` unique with a nullable `block_id` admits screenings without collision (NULL != NULL).

**Do not revisit unless:** an instrument is adopted whose subscale structure is not the seven Morin items,
which would need either a second table or an instrument-tagged item schema rather than fixed `item_1..7`.

---

### 121. A deploy check must cover every service that changed, with a per-service discriminating probe

**Decision:** Deployment verification must probe **each service that changed**, using a probe whose
result **differs between the old and new image for that service**. This project runs two Railway
services from one repo — `health-app-backend` and `health-app-frontend`. The backend probe
(`alembic current` / migration-file listing) is **structurally blind to the frontend**: it verifies the
Python image and cannot fail on an undeployed, failed, or mis-rooted frontend build. A green backend
probe therefore reads as "deployed" while a frontend change may be unshipped.

**The frontend probe is a served-bundle content grep**, not a deployment status and not a hash. Fetch
the live site (`curl $FRONTEND_URL/`), read the `assets/index-*.js` name it references, fetch that asset,
and grep for a **string literal only the new code carries** (e.g. `"Tonight's sleep window"`,
`"Sleep diary"`). String literals survive minification; the built content-hash differs by build
environment (local `index-C5_3m34c.js` vs deployed `index-V4WCQMwV.js` for identical source), so the hash
is **not** a reliable probe on its own. To split the three failure modes, `railway service
health-app-frontend` then `railway deployment list`: latest older than the merge → nothing triggered;
FAILED → read the build log; SUCCESS but the grep misses → wrong Root Directory / stale tree.

**Status:** Adopted as a repo-specific standing rule in `CLAUDE.md` Conventions, beside #116. Earned when
two frontend merges (`2f9004e` `CheckInAM.jsx`, `9331c31` `NightlyCloseOut.jsx`) were each reported
"deployed and verified" on a backend-only check. Both had in fact shipped — the frontend service
auto-deploys on push — but that was established only retroactively by the content grep this rule
prescribes; the original "verified" claims rested on a probe that could not have caught the failure they
asserted was absent.

**How you know:** the live bundle `index-V4WCQMwV.js` returned PRESENT for all six probed strings from
both merges; `railway deployment list` on the frontend service showed three deploys matching the night's
three pushes, latest SUCCESS. The gap was in the verification, not the deployment — which is the point:
the check passed for a reason unrelated to the thing it claimed to confirm.

**Do not revisit unless:** the deployment surface collapses to a single artifact (one service, or a
monolithic image serving both API and static assets), at which point one probe can cover both and the
per-service requirement is vacuous rather than wrong.

---

### 122. Naps are captured at PM as 0-not-null, which is what makes the engine's nap exclusion able to fire

**Decision:** The PM close-out captures `naps_min` while a block is open, and a blank field is submitted
as **0** ("asked, no nap"), never null. `null` is reserved for "not asked" — a night with no open block,
or a night predating this capture.

The engine excludes any nap-flagged night (`engine.py`, `naps_min > NAP_EXCLUDE_MIN` with the threshold
at 0 per Q45), but its guard is `naps_min is not None`. A null therefore does not merely fail to exclude
— it makes the night **un-gateable**: an unrecorded nap night is indistinguishable from a no-nap night,
so a real nap silently counts toward the titration window. Before this, PM never captured naps, so every
block-3 night was null and the exclusion was **structurally dead** — present in code, unable to fire.
Capturing 0-or-N at PM is what turns it back on. This matches `import_cbti_block.py:135`'s `or 0`, which
gave block 2's imported nights the same 0-not-null property.

**Status:** Adopted and built — `NightlyCloseOutIn.naps_min`, `submit_pm` storage, `TodayOut` round-trip,
and the `NightlyCloseOut.jsx` field gated on `block_open` with the blank→0 coercion client-side.

**How you know:** tests pin that 0 stores as 0 (not dropped as falsy), null persists as not-asked, and the
engine excludes `naps_min > 0`, keeps `naps_min = 0`, and **silently keeps `naps_min = None`** — the last
asserted explicitly as the failure mode this closes.

**Do not revisit unless:** the VA instrument's nap-day referent is established (Q45), which would allow
attributing a nap to a specific night rather than excluding the night wholesale — at which point the
capture stays but the engine's response to it changes.

**Carried, not a decision:** block 3's already-logged nights (24 Jul onward) keep `naps_min = NULL` and
cannot be nap-gated retrospectively without a memory backfill. Two nights so far — worth a manual note.

---

### 123. ROADMAP priority is anchored to external dates; closed questions leave the scan surface

**Decision:** `ROADMAP.md` NOW holds only work serving a **known external date**, ordered by that date;
undated live work sits in NEXT. `OPEN_QUESTIONS.md` gains a `## CLOSED` foot section holding the 14 DONE
entries **verbatim**, below the live 33. No item is deleted — only moved or re-tiered, every body intact.
The outer NOW / NEXT / LATER vocabulary is unchanged, because other stores bind to it (#112 names
"ROADMAP NOW" as the canonical home for cross-repo debt); priority is implemented *inside* it. The
cross-repo propagation row is therefore **pinned to NOW by #112** even though it is undated — the one
NOW row that is not date-anchored, and it says so.

**Rationale:** NOW had accumulated twelve unrelated rows with no ordering inside it, while the only two
date-bound programmes in the backlog — the CBT-I titration due ~31 Jul and the lab/interpretation spine
due against the early-Aug TRT panel — both sat in NEXT. A readiness-ordered list with no priority axis
cannot answer "what next," so selection defaulted to whatever surfaced in conversation. Dates are the one
ordering input that isn't a matter of taste. Closed questions were 30% of the store and, per #112, are
not scanned for live work — pure noise in a file meant to be scanned.

**Status:** Landed.

**How you know:** pre-edit counts, measured not inherited — 47 question headers (14 DONE / 26 UNSTARTED /
5 OWED / 2 BLOCKED); ROADMAP NOW 12 / NEXT 11 / LATER 6. Post-edit: 33 live questions above the fold, 14
in CLOSED; ROADMAP NOW 6 / NEXT 19 / LATER 6. Content preservation verified independently against HEAD —
46/47 question blocks byte-identical (Q42 gained a re-scope note, no deletion), and every one of the 33
original ROADMAP rows preserved (30 verbatim, 3 prefix-extended, zero lost). Two brief-internal points
were resolved against the file rather than assumed: the 4b package is **Q36–Q41 (six)**, not "Q35–Q41" —
Q35 carries no `Due 4b` tag and none of the six cross-reference it; and Step 5's two stale candidates were
checked against code — the morning check-in screen IS built (full Hooper set in `CheckInAM.jsx`; kept live
only for the audit-trail and DOMS-split gaps), and Q42's scraper parse lives in `health-connect-app`, so
tonight's 4h gate covers prefill only and Q42 stays open, re-scoped.

**Do not revisit unless:** a third dated programme appears, or NOW again exceeds what one session can
hold — in which case the dates are no longer discriminating and the axis needs revisiting, not the rows.

---

### 124. The settling period between prescription changes is instrumented, not gated — the parameter is undeterminable from both available sources

**Decision:** `evaluate_cycle` accepts `nights_since_effective_from` and records it on every verdict,
including all HOLD paths. **Nothing branches on it.** No constant is introduced. This supersedes the
earlier settling-*gate* proposal by recording why the gate is not built, so it is not re-proposed from
first principles a third time.

**Rationale:** A minimum settling period was proposed on a real defect — the basis is the trailing
`CYCLE_NIGHTS`, so a move inside that span is adjudicated partly on nights run under a *superseded*
window, the same objection the adherence comment already raises in another form. It is not implemented
as a gate for three reasons. **(1) The parameter cannot be estimated.** Titration interval has never been
studied as a variable; the SRT literature's named failure mode is *under*-titration (Scott 2022: 45%
reach baseline TST by end of acute treatment, concluding further titration of sleep opportunity may
accelerate gains). Block 2 cannot supply it either — 29 of 53 nights removed by one exclusion,
pharmacologically suppressed sleep contaminating the window estimate, a lumbar investigation spanning the
block (CT 7 Apr). **(2) The observed failure mode is under-firing** — two titrations in eight cycles
against three insufficiency HOLDs; a fourth gate moves against the defect the data actually shows.
**(3)** `MAX_MOVE_MIN` (bound in 0 of 8 cycles) and `PLATEAU_TOL_MIN` (never reached) are already carried
as unvalidated; a third guessed constant enlarges that set while presenting as rigour.

Physiology, recorded so it is not re-derived: with the wake anchor fixed and morning light unmoved,
extension shifts lights-out *earlier* and needs no circadian phase adjustment — the "week to adapt"
figure from jet-lag / shift-work research does not apply. The real term is sleep-efficiency recovery
after an extension: TIB rises immediately, TST rises slowly, SE dips by construction and recovers as TST
fills the window. That duration is state-dependent — fast at large deficit, slow near sleep need — so any
fixed constant is too long early and too short late. The corollary is that a *lengthening* settling time
is itself a plateau signal, which is why this parameter and the exit criterion should be derived from one
curve rather than guessed separately.

Interim control: #118's manual, witnessed trigger already functions as a settling gate — a human
declining to offer an evaluation at three nights is a valid control, and unlike a hard-coded constant,
each decision becomes evidence for what the rule should be. Precedent: the direct TIB gate — proposed,
tested, rejected in favour of `basis_tib_over_run_min`, recorded and not acted on. Same shape.

**Status:** Landed. `evaluate_cycle` accepts `nights_since_effective_from` and records it on every verdict
including all HOLD paths; nothing branches on it; no constant introduced.

**How you know:** `grep -n nights_since_effective_from backend/cbti/engine.py` shows the field in the
dataclass (181), signature (303) and `base` (338) only — never in a conditional. A verdict with the
parameter set is byte-identical to one with it unset (`dataclasses.replace` neutralises the one field and
compares equal), asserted on both a move and a HOLD path. Replay populates it as a by-product: block 2's
nine prescriptions ran for `[3,7,5,6,6,6,7,7,6]` nights (range 3–7, median 6) — recorded, NOT evidence,
because the block is confounded. Suite 401 passed, was 394.

**Do not revisit unless:** block 3 yields enough post-extension SE-recovery observations to estimate the
curve — at which point this becomes a gate proposal with data behind it rather than a guess.

---

### 125. Free-text AM/PM notes on the daily record — captured context that must not become an engine input

**Decision:** Two nullable `Text` columns on `daily_records` — `am_notes`, `pm_notes` (migration
`f1a4c7e29b83`) — captured through the AM and PM check-in surfaces. **Observational: read by no engine
code.** Not gated on an open block — notes are useful with or without a CBT-I block.

**Rationale:** the block generates one-off explanations that belong on the record but must not become
titration inputs — a carnival alarm, an off night. A structured field cannot hold them and the engine
must not read them (the same discipline as the waking-cause columns, #119). **Separate AM/PM columns,
not one:** the two surfaces submit independently, so a shared column's later write would clobber the
earlier — the record already carries separate `am_timestamp` / `pm_timestamp`, and the notes follow that
shape. Both fields round-trip through `DailyRecordOut` / `TodayOut` so the morning's note is visible when
the PM form loads.

**Status:** Landed. Migration chains off the real head `d3f7a1908c62` (the ISI migration superseded the
brief's stated `b2d5f9e04a17` — Step-A VERIFY caught it). Both surfaces capture, both fields round-trip,
a plain textarea on each page.

**How you know:** suite asserts round-trip and null-accepted for both fields, and that a PM submit does
**not** clobber `am_notes` (the two-columns justification, executable). Migration verified up/down/up in
isolation on SQLite (via `create_all` — a bare stamp cannot test `add_column`, no table). Both services
deploy-verified per #121: backend OpenAPI carries `am_notes`/`pm_notes`, frontend bundle carries the
textarea label, each with a negative control. 406 passed, was 401.

**Do not revisit unless:** a structured field is later shown to be the right home for something currently
going into notes — at which point that content is promoted to its own column, and the note stays free-text.

---

### 126

**Decision:** Block 3's opening prescription (id=10, 23:45→05:45, window 360) is superseded by an
operator correction (id=11, 22:30→05:00, window 390, `decision='adopt'`, `effective_from` 2026-07-27)
rather than edited in place, and the `cbti_blocks` row is left unchanged. The write is APPEND +
SUPERSEDE on `cbti_prescriptions` — insert id=11, then set id=10 `effective_to`=2026-07-26 and
`superseded_by`=11, the only permitted UPDATE shape (models.py:278-281). The block's `wake_anchor`
stays 05:45.

**Rationale:** The opening window 360 was operator-set to ≈ the device mean TST (basis_tst_min=349 on
id=10), a mean measured over nights already under self-restriction, and the anchor 05:45 sat above the
measured wake terminus. The correction returns the anchor to 05:00 (the wake terminus, and the anchor
under which the completed block closed at window 458) and the window to 390. `decision='adopt'`, not
`extend`: an operator correction must not enter the titration chain as a move ('adopt' is in the CHECK
set and carries no titration semantics). `basis_*` left NULL: operator-set, not basis-derived, so
id=10's device-derived provenance is not copied forward. The block row is NOT rewritten because
CBTIBlock is append-only (models.py:253-257) and 05:45 is a true fact about how block 3 opened — the
superseding prescription is the artifact that expresses the anchor change, exactly as prescription
supersession expresses a titration.

**Status:** DONE. Applied to prod in-container (`railway ssh` → the seed script's `--apply` path):
inserted id=11, superseded id=10, block id=2 unchanged. Seed script committed
(`backend/correct_cbti_block3_rx.py`) — dry-run-default, resolves the target (the single live rx on the
single open block) at read time, guards against double-apply.

**How you know:** post-write read-back of all three rows, reproduced in the session transcript: id=10 →
`effective_to`=2026-07-26, `superseded_by`=11, every other column frozen (23:45/05:45/360/adopt,
basis_tst 349); id=11 → 22:30/05:00/window 390/adopt, `basis_*` NULL, `superseded_by` NULL; block id=2
→ `wake_anchor` 05:45, unchanged.

**Do not revisit unless:** a further operator correction or a genuine titration move supersedes id=11 in
turn — done the same way, an append + supersede, never an in-place edit. The block-vs-prescription
anchor divergence this entry knowingly accepts is tracked separately as OPEN_QUESTIONS Q49 (the replay
reads the block anchor, not the effective prescription's), which is the blocker on the first evaluation.

---

### 127

**Decision:** CBT-I adherence and diary capture are RECALL-ONLY. (1) The engine's adherence gate
differences the prescribed lights-out against the diary `lights_out` only — the `samsung_bedtime` arm is
removed from `classify_night` (`cbti/engine.py`). (2) The AM diary prefill no longer defaults `lights_out`
from Samsung `got_into_bed` (`routers/checkin_v2.py` `_diary_prefill`): `lights_out` returns None and is
entered from recall with no device value shown. `got_into_bed` prefill (a distinct, verified bed-entry
moment) and the 12h-corruption gate are unchanged.

**Rationale:** Clinical CBT-I is recall-only by design; a device-DETECTED onset is a different construct
from a RECALLED lights-out ("tried to sleep"). Treating the two interchangeably against a ±30 tolerance
let a systematic detection lag flip a borderline night (Q47). Removing the sensor arm ON PRINCIPLE moots
the calibration Q47 deferred — the lag need not be known if the sensor is not consulted. Diary
`lights_out` coverage is complete on the observed block (51/51), so no fallback gap; and the Samsung arm
never executed on a completed block (`samsung_hrv_readings` begins 2026-06-08, after block 2 closed
2026-05-11), so nothing historical is revalued. The prefill is the same intent at capture: a prefilled
`lights_out` invites accepting the device value as recall, defeating recall-only at the point of entry.

**Status:** DONE. `samsung_bedtime` left on the `Night` dataclass and in replay's `_SAMSUNG_SQL` (now dead
as an adherence input — still populated and counted by the `n_with_samsung` diagnostic; removal deferred,
not folded here). `basis_n_samsung` / `AdherenceSource='samsung'` are now structurally 0. Resolves Q47.

**How you know:** full backend suite passes (406) with the engine tests driving (non-)adherence through
diary `lights_out` (Samsung ignored even when present) and the prefill suite asserting `lights_out` is None
post-change with `got_into_bed` still defaulted. S4 (read-only, this session) tried to measure the
sensor−diary lag over 2026-06-08..2026-07-26: only n=2 nights carry BOTH a diary `lights_out` and a
`passive_overnight` bedtime (block 3 had just opened), mean +3.5 min (sensor later) — sign-consistent with
but far too thin to characterize. The export's own `bedtime_detection_delay` (p50 14, p90 19, n=211) is the
real distribution; the in-app join cannot reproduce it, which itself argues against depending on the sensor
for adherence.

**Do not revisit unless:** a future block has incomplete diary `lights_out` coverage AND a validated device
onset-to-lights-out model exists — at which point the sensor could supplement recall for missing-diary
nights only, never in preference to it.

---

### 128

**Decision:** The replay adjudicates each cycle against the EFFECTIVE prescription read from
`cbti_prescriptions`, not a chain regenerated from the engine's own decisions. Cycles anchor to each
prescription's `effective_from` and never span a prescription boundary; the engine's per-cycle decision
is a recorded recommendation, never fed forward. Resolves Q49.

**Rationale:** The prior replay walked fixed 7-day cycles from block-open, seeded from the earliest
prescription, and carried the engine's own output forward as the next window — so a mid-block operator
correction was invisible, and nights run under it read as adherence failures against the superseded
prescription (a false GATE-2 HOLD). Block 3's correction (#126: id=11 supersedes id=10 on the 4th night of
cycle 1) is the live instance. Reading the effective prescription per cycle — window, lights-out, AND wake
anchor — makes block-vs-prescription divergence (incl. the #126 anchor divergence) inert: adherence is
always differenced against the prescription the nights were actually run under. Cycles anchored to
`effective_from` are the same "≥7 nights since the current prescription's effective_from" unit the live
evaluation trigger (#118) will use, so replay and trigger share one model. A plateau "close" is advisory
(recorded for #107's exit-too-early check) and no longer terminates the walk — the operator's ledger, not
the engine, decides when the block ends.

**Status:** DONE. `replay.py` reworked; the prescription SELECT extended to carry `effective_to` +
`wake_anchor`. New `test_cbti_replay.py` (the module had no tests): flagship Q49 regression (a mid-cycle
correction is adjudicated, not false-held) + no-cycle-spans-a-boundary invariant + per-prescription anchor
+ plateau continuity across cycles. Resolves Q49 — it was the blocker on the first block-3 evaluation.

**How you know:** full backend suite passes (412, was 406 — +6 replay tests). Verified READ-ONLY against
prod: block 1 (completed, 9 ledger prescriptions) walks 9 cycles, one per prescription, each adjudicated
against its own ledger lights-out/window/anchor; block 3 shows id=10's 2-night stub (insufficient) and will
adjudicate id=11's nights against 22:30/05:00 (the correction), not the seeded 23:45.

**Do not revisit unless:** the live evaluation trigger (#118) is built to consume something other than the
effective prescription per cycle — it must reuse this same read, or the two paths diverge again.

---

### 129. FEEDBACK.md §19 is an append-only, status-mutable integrity ledger; failures are typed HUMAN / MODEL / COUPLED

**Decision:** analysis-loop failures are recorded as a table in `FEEDBACK.md` §19 — one row per failure, typed
`HUMAN` / `MODEL` / `COUPLED`. `COUPLED` is first-class: a model gap-fill plus a partial/stale record in the same
place is ONE failure, not two. §19 is a section of the existing file, not a new store — §1–§11 keep their remit
(behavioural corrections and standing rules) and the shared canonical-stores row is unchanged, because it still
describes the file correctly. The ledger is documented in CLAUDE.md's repo-specific section, below
`END SHARED LOOP RULES`, so the verbatim-propagated block stays identical and true across repos.

**Rationale:** the 15 Jul calf investigation produced 12 model retractions and 3 human input errors in one session.
A flat two-list ("human errors" / "model errors") misattributed cause: it logged model fabrications as `MODEL` and
record gaps as ambient system properties ("templates are unreliable" — agentless, passive voice), laundering the
coupling into two unrelated lists and pointing the fix at the wrong party. The coupling IS the finding. The most
consequential failure of that session — "the load does not explain the injury, which survived every correction" —
is `COUPLED`: a premise co-signed by Luke that the model never routed the killing data at. Attributing it to either
party alone is false.

**How you know:** seeded with 12 rows from the session (ids 1–15, gaps preserved). The `artefact_vs_source` field
alone accounts for 11 of the 12 model retractions — every one was a record-artefact (drill label, template label,
session aggregate) read as the thing it describes. The coupling links are **pinned, not measured**, and the
distinction matters: `5 → 6,15` · `6 → 15` · `7 → 13` · `8 → 13` were pinned directly (correcting row 8, whose
authored cell read 15 — a transcription error). The remaining edge `15 → 13` is pinned from row 15's authored cell
read as `caused`, corroborated by the §5 note that the 15 Jul tidbits were unknown-unknowns surfaced BY a wrong
model claim — i.e. the retractions caused the ad-hoc intake, not the reverse. On those pins the graph is connected
with id 5 as root: 5 → 6 → 15 → 13, with 7 and 8 also feeding 13. Connectedness is a **consequence of the pins**,
not independent evidence for them; override the `15 → 13` pin and this sentence must be re-derived.

**Do not revisit unless:** `COUPLED` proves unfalsifiable in practice — i.e. every failure gets typed `COUPLED`
because a record gap can always be found somewhere — at which point the enum needs a tighter test for "in exactly
the place the error landed."

---

### 130. Integrity-ledger inclusion test: a row exists only if a procedural change would have prevented the failure

**Decision:** `prevention` is mandatory and non-null. Before any row is written: would a procedural change have
prevented it? Yes → it belongs, fill `prevention`. No → it is not a failure, do not log it. Unpreventable events
are explicitly barred: injury, faulty recall, first-use data lag, fumbling the ball.

**Rationale:** an integrity ledger stuffed with unpreventable events becomes a guilt ledger. A guilt ledger is
abandoned within a fortnight, and then the one document that could catch real coupling is dead. The mandatory
non-null field is the enforcement mechanism, not a documentation nicety: if you can't name the procedure, there
was no failure.

**How you know:** applied at seed time and it bit immediately — the authored row 3 carried
`(verdict correction, not prevention)` in the `prevention` column, which is null under this test. The row survives
only because a real prevention exists (change the label at substitution time, or log the substitution in the set
note). Four candidate rows from the session were barred outright by the test.

**Do not revisit unless:** a class of failure appears that is real, recurring, and worth recording but has no
procedural fix — in which case it needs a home that is not this ledger.

---

### 131. Signed-error rule: an error with a known direction is a BOUND, not a loss

**Decision:** the `signed` field records error direction (`UNSIGNED` / `SIGNED:<direction>`). A dimension is never
written off as "unrecoverable" without first establishing which way the error points.

**Rationale:** a directional error does not destroy the data — it bounds it. Declaring a dimension lost without
asking the direction question discards recoverable information and is itself an integrity failure. The field forces
the question at log time rather than leaving it to whoever reads the row later.

**How you know:** the 15 Jul seated-for-standing mislabel was written off as "gastroc/soleus split UNRECOVERABLE."
False. The substitution runs one way only — machine occupied, so seated was performed and standing was logged; no
scenario produces the reverse. Therefore logged gastroc ≥ true gastroc (upper bound) and logged soleus ≤ true
soleus (lower bound). The data was bounded, in the direction that happened to strengthen the existing read. Ledger
row 3 `STANDS` with the verdict struck and corrected.

**Do not revisit unless:** a signed error is found whose direction is itself uncertain, requiring a third state
between `SIGNED` and `UNSIGNED`.

---

### 132. Ledger retraction mechanism: entries are append-only and never deleted; status is mutable

**Decision:** ledger entries are never deleted. Ids are never reused; a struck entry keeps its id. `status` is
mutable — `STRUCK:<date>:<reason>` when an entry is shown false, or `STANDS` with a dated verdict correction when
the failure was real but its conclusion was not. A struck entry is retained as evidence the ledger self-audits.

**Rationale:** an un-retractable false positive discredits clean data, and distrust is sticky — once a record is
marked corrupt, nobody returns to it and everyone reasons from summaries instead, which is the exact behaviour that
caused every real failure in the seed. A phantom failure entry therefore drives the behaviour that produces real
failures: it is self-amplifying. Retaining the struck row rather than deleting it is the point — that the ledger
accumulates false entries and must be audited is itself the most important thing it records.

**How you know:** the prior list contained a phantom — "a left-knee note filed under the right-leg block," asserted
as data corruption and written into the anti-fabrication section. It did not happen: Luke was doing right-leg BSS,
his LEFT knee clicked, and he logged it correctly under the block he was in. A Hevy note attaches to a container,
not a limb; a model inferred corruption from a label mismatch. It is ledger row 4, `STRUCK: phantom`, retained.

**Do not revisit unless:** struck entries accumulate to the point of drowning live ones, at which point they need a
separate view — not deletion.

---

### 133. The app's injury-return role is educate / probe / never-clear — and never-clear is enforced in code, not prose

**Decision:** The app may EDUCATE (surface general evidence) and PROBE (elicit and date injury-specific markers),
but must not INTERPRET those answers into a clearance, a prescription, or a grade. The boundary is structural, not
prose: probe questions are elicitation-only (tested against prescription verbs and rep/set schemes) and escalation
is referral-only (tested against grades, clearances, severity, and "safe to X" verdicts). No behavioural clearance
logic is added; this entry fixes a boundary. No migration.

**Rationale:** Return-from-injury is the archetypal hard-gated decision: error causes re-injury, and the inputs to
judge readiness (tissue response to progressive load, pain-on-load behaviour over days) cannot be verified by the
app or by self-report. Critically, the pro-loading evidence base (PEACE & LOVE over RICER) does NOT relax this: its
"Load" element is titrated against tissue response — exactly the clinical judgment the app lacks inputs for — so
stronger evidence for early loading SHARPENS the boundary rather than eroding it. Making the boundary structural
means a future edit cannot quietly cross it in prose.

**How you know:** Same directive-vs-defer test used across this platform — defer only where error harms AND the
inputs to judge it are unavailable and unverifiable. Return-to-run readiness fails both. A clean single-leg heel
raise is necessary but not sufficient evidence for clearance; the app records it as data and stops there. The gates
are proven to bite, not merely present: each carries negative controls, and both were mutation-tested against a
poisoned source — the elicitation gate fails on a seeded "Do 3x10 heel raises", the referral gate fails on a seeded
"Grade 2 strain — you are cleared to run in 3 weeks". A gate that cannot fail is a false-green (FEEDBACK §10), so
"the gate exists" was not accepted as evidence that it works.

**Do not revisit unless:** the app gains a verified, objective load-response input (not self-report) that a
practitioner would accept as clearance evidence — at which point the gate's premise, not the gate, is what changes.

---

### 134. Injury-type-specific probe questions are a versioned, provenance-stamped, deliberately-incomplete reference

**Decision:** `backend/injury_probes.py` — a versioned (`PROBE_QUESTIONS_VERSION`), provenance-stamped scaffold for
injury-type-specific probe questions, seeded with exactly ONE worked example (gastroc strain). Unrecognised injury
types fall back to the existing generic soreness item, never a fabricated question set. Cadence is a property of the
injury type (acute soft tissue = every 2 days), counted from the entry's set-date. No migration.

**Rationale:** Injury-driven check-in soreness items ALREADY LANDED 13 Jul 2026 (FEEDBACK 2.6):
`checkin_v2.derive_soreness_items` generates one item per active `UserKnowledgeEntry type='injury'` ledger row,
`/prefill` serves it, and `CheckInAM.jsx` renders it with a "no active injuries" empty state. This entry does NOT
re-do that — it adds the layer above it: injury-TYPE-specific PROBE questions (the markers that track a given
injury's course). Those question sets are a clinical reference with the same provenance obligation as the taxonomy:
a "complete" bank authored from intuition would be a false-green. So the scaffold is versioned, provenance-stamped,
and seeded with one worked example only. Completeness is a standing review obligation, not a shipped claim.

**Keying (a finding, not a preference):** probe sets are keyed on an explicit optional `injury_type` field in the
entry's JSON `value` — alongside `trajectory`, same additive no-migration pattern — and NOT on `body_part`. The
ledger carries `body_part` + `signal_type` and no injury type at all. Keying on `body_part` would mis-serve probes:
the live right-hamstring entry refers S1-pattern symptoms *to the calf*, so a "calf" body_part is positive evidence
of referred neural pain, not of a gastroc strain. A test pins this.

**How you know:** The derivation's prior existence was confirmed against master (`checkin_v2.py:69`,
`CheckInAM.jsx:247`) before this branch — an earlier draft of this entry wrongly claimed that derivation as new work
AND mis-stated its mechanism (it does not route through `gather_active_injuries`; it queries the ledger directly).
Both errors were caught at the STEP 0 tree read. The gastroc seed is the session-specced case — walking-pain trend,
single-leg heel-raise capability, forefoot-load pain — all elicitation, tested against prescription verbs (#133).
Incompleteness is explicit in the provenance string, not a shipped completeness claim.

**Scope limits, recorded rather than glossed:** (1) the seed is UNEXERCISED by live data — there is no calf/gastroc
entry in the injury ledger (`seed_engine.py`), so every currently-active injury takes the fallback path and the
gastroc set has never fired on a real entry; (2) no ledger entry carries an `injury_type` field yet, so the keying
is live-inert until one is authored; (3) probe RESPONSES have no storage — `daily_records.soreness` stores soreness,
not probe answers — so `evaluate_escalation` takes its series as an argument and stays pure. This is LANDED ≠ LIVE
(FEEDBACK §8) declared up front rather than discovered later.

**Do not revisit unless:** a validated clinical question-bank source replaces the authored seeds (provenance shifts
from "authored, unvalidated" to the cited source), or the three parallel ledger readers are consolidated (Q52 —
would change how the scaffold reads injury type).

---

### 135. Lab interpretation view — three-section render of contract v0.4; hybrid weighted-inline levers; colour-as-fact

**Decision:** The lab-interpretation view renders the contract v0.4 (#63) group-primary
object as a three-section screen (What Moved → Stable → Mechanisms). Section placement:
a group is "moved" iff any member is news (gate 1) OR out-of-range (gate 2); moved groups
render whole (axis-verdict + all members), stable groups collapse to the axis-verdict line.
Levers render HYBRID WEIGHTED-INLINE — an in-card shared-levers strip per moved group
(present-marker), plus a thin pooled Mechanisms index at the bottom that is navigation only
(grade-ordered jump-links back to each in-card strip), so a lever is authored once, rendered
in context, and still browsable as a reading mode. COLOUR-AS-FACT: a coloured breach
indicator appears only where range_gate.is_out_of_range (the lab-asserted H/L flag); the
coherence verdict stays monochrome. An expected-by-phase breach stays coloured with its note
shown — the colour marks the fact, the note reframes it, the breach is never suppressed
(#47 gate-2 spine).

**Rationale:** View-first (increment 1 of 5) surfaces contract gaps cheaply before producer
logic, and is pure frontend that doesn't depend on the empty lab store. Hybrid-inline keeps
both #63 present-marker (lever legible beside its marker) and #49's distinct "worth
understanding" reading mode. Colour-as-fact is the #47 boundary made visual: a scannable
coherence traffic-light would be the personalised all-clear #47 forbids, so colour is
reserved for facts the lab asserted, neutral on what the platform infers. The fixture IS the
contract §2 object verbatim, so the view cannot drift from what the future producer emits.

**Status:** Increment 1 (static skeleton against the fixture) implemented. Remaining
increments: 2 = register + LLM rephrase pass (deterministic core, rephrase-not-claims,
base canonical / rephrase disposable, simplify-never-reassures — the #47 danger zone);
3 = lever tap → scoped ephemeral education thread; 4 = producer module emitting real
contract JSON (D3 cache-on-confirm vs compute-on-read decided there); 5 = go-live (confirm
one real panel, promote the two ai_draft assets to human_verified). LANDED ≠ LIVE (§8): this
increment is a fixture render, not a live feature — the AI view-pointer
(context_builder `_LAB_INTERPRETATION_VIEW_LABEL`) is deliberately left at its placeholder
until increment 5 renders real data.

**How you know:** `npm run build` green (98 modules, no new lint errors — the 5 reported are
pre-existing on master in ChatPanel/WorkoutPanel/Settings). Section split exercised against
the committed fixture through the shipped helper: What Moved = `[hpg_axis, hepatocellular]`,
Stable = `[vitamin_d_25oh]`. The gate-2 spine is confirmed by the per-member trace, not
assumed — `hpg_axis` moves on `fsh(news=false, oor=true)` alone, with both other members
`news=false, oor=false`; `hepatocellular` moves on `ast(news=true, oor=false)`. So each gate
is independently load-bearing on this fixture: HPG exercises gate 2 with no news, AST
exercises gate 1 with no breach. Colour-as-fact verified by computed style over EVERY element
on the rendered page, not by inspection: Tailwind v4 emits `oklch`, whose neutral ramp sits at
hue 247–265 and chroma ≤ 0.034; the only chromatic elements on the page are five, all inside
the FSH line — the breach dot (`oklch(0.705 0.213 47.604)`), "Below range" (chroma 0.222),
"· expected for phase", the note text (chroma 0.195) and its `orange-50` chip (hue 73.684).
AST — news but in-range — renders entirely on the neutral ramp, and all three axis_verdict
headers probe monochrome. Present-marker holds: `hpg_t_e2_ratio` renders on BOTH the T line
(`ratio · oestradiol`) and the E2 line (`ratio · testosterone_total`); the GGT discriminator
renders on the AST line alongside De Ritis. Levers: `exercise_muscle` renders labelled
"already in play"; the Mechanisms index lists both `testosterone_substrate_load` and
`exercise_muscle`, and both jump-links were confirmed to RESOLVE to a real in-card anchor in
a different section (`resolves: true`, `targetIsInCardStrip: true`) — a dangling href would
have failed silently. Group-of-one: vitamin D renders in Stable, collapsed to its verdict
line, with no delta glyph or "first observation" text anywhere in the section. Concern
boundary held: `git diff --name-only master` returns frontend paths only, and
`_LAB_INTERPRETATION_VIEW_LABEL` still reads "Metrics page". Zero console errors.

**Not verified:** the view has only ever rendered THIS fixture — one panel, three groups,
two levers, one breach. No empty-state, no multi-breach group, no `is_news` + `is_out_of_range`
on the same member, no group with zero levers in What Moved, and no real producer output has
touched it. The section-placement helper is exercised by a scratch probe, not by a committed
test — the frontend has no test runner (`package.json` has no test script), so nothing guards
the split against regression.

**Do not revisit unless:** the contract v0.4 shape changes (#63's own revisit clause), or the
three-section / hybrid-inline / colour-as-fact model fails against a real panel once the
producer lands.

---

### 136. Block 1 (2026-03-19 → 2026-05-11) is discarded for outcome claims; instrument and parameter evidence survives

**Decision:** Block 1 (`cbti_blocks.id=1`, the clinical "block 2") is DISCARDED for OUTCOME CLAIMS — any
claim about what the prescription produced: TST, SE, titration counts, adherence rates, exclusion loads,
cycle verdicts. Instrument-characterisation and parameter-setting evidence from the same nights survives,
and #107's week 7 survives, each for its own reason (below). This mints a premise a substantial amount of
landed code and comment already leans on (commit `d07b538`, OPEN_QUESTIONS Q55) but which until now
existed only in chat.

**Grounds for the discard.** (1) Prescriptions were extended mid-block for external reasons, so TIB was
not held. (2) The observed TIB SD (~67 min) is statistically indistinguishable from the subsequent
self-restricted hold period — i.e. the restriction was largely not in force. *(This SD figure is from
prior chat analysis; it is NOT verified against the repo or DB, and is recorded here as the operator's
stated basis, not as an attested measurement.)* (3) The ledger and diary spans disagree:
`cbti_blocks.id=1.closed_on = 2026-05-11` (51 nights) against #107 / BRANCHES prose describing the imported
block as 2026-03-19 → 05-13 (53 nights), so two nights (05-12, 05-13) carried no prescription.
`replay.load_nights` bounds on `closed_on`, so a replay sees 51. *(This span discrepancy IS repo/DB-checkable
and was checked: the block-1 replay reports "nights loaded: 51"; the importer loaded 53.)*

**What survives — three classes, each for its own reason.**

- *Instrument characterisation.* The relationship between recalled lights-out and detected sleep onset is a
  property of the SENSOR, not of the prescription; a mid-block prescription change cannot corrupt it. This
  is why lag queries on block-1 data (Q47 / #127) are legitimate.
- *Parameter-setting from unforced periods.* Chronotype and wake-mode determination from periods where the
  schedule was not binding. These are not measurements of the intervention and are not runtime reads.
- *#107's week 7.* TIB 8h07 against a 7h38 prescription, TST 7h29, SE 92.2%. It survives BECAUSE it is the
  over-run: the non-adherence that voids the block's outcome claims is precisely what makes this week
  informative — the only observed period where TIB was not the binding constraint. Applying the discard
  uniformly would delete the project's only sleep-need estimate. #107 stands.

**Consequence.** Any claim citing block-1 outcome measurements as design justification is void, including
where it appears in code comments. Commit `d07b538` neutralised the known sites in `engine.py`; future work
must not reintroduce them.

**Interaction with prior locked decisions (reconciliation deferred, not done here).** This entry does not
amend any append-only decision. Where a prior locked decision cites a block-1 OUTCOME as a support — #115's
buffer "recovered from the prior block" (+36 median) and #114's regularity / second-adherence-arm rejections
(`r = −0.206`, "fires on nothing") — that citation now rests on discarded ground, and `d07b538` already
removed the mirror of it from code, so store and code disagree about the basis. Reconciling each is a
SEPARATE supersession with its own weight, not folded into this discard. (#124 already labels its block-1
figures "recorded, NOT evidence, because the block is confounded", so it needs none.)

**Not covered (a limit, not a discard).** No unrestricted baseline exists in any dataset — every recorded
night is prescribed-restricted or self-restricted. Sleep need is therefore unmeasurable from existing data
by any method, and plateau detection must be self-referential rather than referenced to a need estimate.

**Status:** Minted as the canonical home for a premise already relied on by landed code (`d07b538`) and
OPEN_QUESTIONS Q55. Not an amendment to any existing decision.

**How you know:** the span discrepancy is repo/DB-checkable and was checked (`closed_on` 2026-05-11 vs a
53-night import; the block-1 replay loads 51). The TIB-SD ground and "extended mid-block for external
reasons" are the operator's stated basis from chat analysis, marked as such above and NOT attested at the
repo or DB.

**Do not revisit unless:** an unrestricted-baseline dataset becomes available (which would make sleep need
directly measurable and reopen the "Not covered" clause), or a specific block-1 quantity is shown
prescription-independent by an argument that does not itself rest on a block-1 outcome — in which case it
joins the "survives" classes rather than reopening the discard.

---

### 137. Buffer and rejected-gate bases restated — block-1 derivations retired, values unchanged

**Decision:** Supersedes the recorded BASES of #115 (the +30 titration buffer) and #114 (regularity-not-gating
and the rejected second adherence arm), whose stated evidence is void under #136 (block 1 discarded for
outcome claims). NO constant changes and NO code changes — the code already reads this way after `d07b538`;
this aligns the store to the code, not the reverse. #115 and #114 stand as append-only history; only their
recorded bases are restated here, and #114's constants portion is left untouched.

**Buffer (+30) — one support, not two.** #115 derived the buffer by differencing each prescribed window
against the mean TST of the preceding seven nights (+36, +45, +36, +27, +16, +48, +65; median +36) and
adopted 30 as sitting at the conservative end of that range AND matching the standard sleep-restriction
convention — claiming two independent supports. The derivation is void under #136, and for a sharper reason
than general contamination: it measures the gap between a prescribed window and actual sleep, and where the
window was not run that quantity is not headroom but the distance between a paper figure and reality — the
fourfold spread (+16 to +65) is consistent with that reading. **+30 now stands on the standard
sleep-restriction convention alone — one support.** The value is unchanged; the code (`BUFFER_MIN = 30`,
comment already SRT-only) is already correct.

This parameter is LIVE, not settled. `target = mean_TST + BUFFER_MIN` governs whether titration climbs at
all, and it interacts with a known servo problem: restricting TIB suppresses TST, which lowers the target,
which shrinks the move. Any re-derivation belongs to the pending policy revision, not here. The only observed
period where TIB was not binding shows a ~+38 min gap (TIB 8h07, TST 7h29, SE 92.2% — #115/#107's surviving
week 7) — recorded as context, not adopted.

**Rejected gates — NOT ATTESTED, not refuted.** #114 rejected the regularity gate and the second adherence
arm on block-1 outcome figures (`r = −0.206`, "blocked five of eight weeks"; the arm "fires on nothing",
worst cycle 2 of 6). Those figures are void under #136, so the rejections no longer rest on evidence. This
does NOT reopen them: evidence is required to ADD a gate, not to omit one, so losing the evidence leaves both
unbuilt with no case for building — which is where they already stood. The change is only that the recorded
basis becomes NOT ATTESTED rather than refuted-by-data, correctly leaving room for either to be argued later
on new evidence. #114's constants portion — `MAX_MOVE_MIN` / `PLATEAU_TOL_MIN` / `MIN_VALID_NIGHTS` recorded
as unvalidated — survives untouched: an honest limitation, not a derivation from void data, and the same
carve-out already applied in code.

**Closes the deferred clause in #136** ("Interaction with prior locked decisions … reconciling each is a
SEPARATE supersession"). #124 needed none — it self-labels its block-1 figures "recorded, NOT evidence,
because the block is confounded".

**Status:** Store aligned to code. No constant and no `.py` file touched (governance-only). #115 and #114
stand as history; this entry is the current basis of record for the +30 buffer and the two omitted gates.

**How you know:** `engine.py` post-`d07b538` already states the restated bases — the `BUFFER_MIN` comment
cites the SRT buffer only ("a block-2 derivation once co-supported ~30 but is discarded"); the module
docstring marks the second adherence arm "NOT ATTESTED — prior block discarded" and regularity as an
observational construct; the three constants remain "unvalidated". No comment required editing to match
this entry (Step-3 check confirmed).

**Do not revisit unless:** the pending policy revision re-derives the buffer against a period where TIB was
binding (which #136's "Not covered" clause notes is unmeasurable from existing data), or new evidence is
offered to ADD the regularity gate or a wake-end adherence arm — in which case the argument is made on that
evidence, not by reinstating the void block-1 figures.

---

### 138. Interpretation contract v0.5 — three-gate safety supersedes the two-gate model; ungrouped markers render in their own section

**Decision:** The interpretation output contract moves to v0.5. Two parts, different in kind. The
contract document is UI-maintained and sits outside both repositories; this entry is the canonical,
master-readable record of what it now says, because Code cannot read the document and cannot verify the
producer against it.

**Part 1 — records what the code already does.** v0.4 stated a two-gate safety model as the structural
resolution of the regulatory-framing boundary. The code (`backend/interpretation/gates.py`) has three
independent runtime gates:

- **Gate 1 — news.** Two arms. The delta arm is movement-based (`crossed_ref` set, or magnitude
  `meaningful`) and may be demoted by an in-phase relation. The safety arm fires on a safety-band change
  and forces `is_news` true with **no demotion path** in code.
- **Gate 2 — range.** Absolute value against the lab's per-report reference bounds. Always fires; never
  suppressed.
- **Gate 3 — safety band.** Level against an authored policy band, independent of movement **and** of the
  reference range: an unmoved, in-range value can still sit in a band. (Currently inert — the asset
  carries no live band.)

The contract also lacked three keys the producer emits: `safety_gate` on every member (and `ungrouped`)
row, `should_surface` at group level, and `ungrouped[]` as a top-level array. v0.5 adds all three.
`should_surface` is the classification predicate materialised — it decides where a group renders
(What Moved vs the collapsed Stable line); the axis verdict is the narrative above the member lines once
it does.

**Part 2 — a new ruling.** Markers present in the panel but in no authored group render in their **own
section**, ordered surfacing-first, placed **between What Moved and Stable**. They are not pooled into
Stable and not synthesised into groups-of-one.

**Two new contract invariants.** Content is recorded here as canonical; the ordinal for each is assigned
in the UI-maintained contract and is **not mintable from master** — master establishes the contract's
invariant series only through I1 and I6, so the next-free number cannot be confirmed from the repo and is
deliberately not asserted here.

- **Safety-arm non-demotability.** Gate 1's safety arm may not be demoted; relations may demote the delta
  arm only. Recorded before demotion logic exists so that logic inherits it (the `gates.py` module
  docstring already carries "THE SAFETY ARM IS NOT DEMOTABLE").
- **No present marker is dropped.** Every marker present in the panel renders somewhere.

**Why the ungrouped ruling is a correctness fix, not a layout preference.** The non-suppressible range
gate says nothing may hide an out-of-range value. The producer places every unauthored marker in
`ungrouped[]`; the view renders groups only. So an ungrouped marker breaching its reference range is
silently dropped the moment the view is wired to the producer. Pooling into Stable does not fix it — a
breach rendered under a "Stable" heading is hidden by prominence instead of by suppression. Its own
section, above Stable, is the placement that satisfies the gate rather than its letter.

**The mechanism that produced the drift, and the change that addresses it.** v0.4 carried a hand-authored
worked example; the producer's oracle tests compared output to a committed fixture. Both were
hand-maintained, so they were only ever checked against each other — and the contract fell a full gate
behind the code across several subsequent decisions without anything failing. In v0.5 the worked example
is generated from producer output rather than authored, and the contract defines the shape normatively
instead.

**Left open, deliberately.** The contract is UI-maintained and sits outside both repositories, so Code
cannot read it and cannot verify the producer against it. Two candidate closures — commit the file to the
repo, or accept the generated fixture as the operative contract and treat the document as design
narrative — are **not decided here**.

**Status:** Governance only. No code, asset, or migration touched. The contract document itself is
UI-maintained and unreadable from master; this entry is the canonical record of what it now says.

**How you know:** The three gate functions, the safety arm's unconditional `is_news` force with no
demotion path, `should_surface`, and the producer's top-level `ungrouped[]` emission with `safety_gate`
on every row are all verifiable in `backend/interpretation/gates.py` and `backend/interpretation/producer.py`,
re-confirmed at read time on this branch. The build sequence recorded in `ROADMAP.md` carries the same
three-gate model, established independently.

**Do not revisit unless:** a fourth gate is added; the ungrouped section is re-litigated on evidence that
its placement misleads; or the verification gap is closed, which would change where the contract lives and
therefore what this entry is for.

---

### 139. Haematocrit safety bands promoted with per-band citations — gate 3 fires for the first time

**Decision:** Three haematocrit bands move from `_deferred` into live `thresholds` in
`safety_thresholds.json`, each carrying its own `evidence_refs`: **0.50** the monitoring target
ceiling, **0.52** the observed risk inflection, **0.54** the intervention threshold. Gate 3 previously
resolved undecidable (`no_asset`) for every marker because the asset was empty; it now fires for
haematocrit, and gate 1's safety arm becomes reachable with it.

**Why three bands rather than one.** They rest on different kinds of evidence and license different
readings, so each carries its OWN citation — a shared citation across all three would assert an
evidential unity that does not exist, the laundering I1 exists to prevent. **0.50** is a management
target from contemporary haematology reviews and a relative contraindication in andrology guidance.
**0.52** is an observed outcome inflection — matched cohorts on testosterone therapy, MACE/VTE odds
ratio 1.35 (95% CI 1.13–1.61) — scoped to the FIRST YEAR of therapy, which the band's note records
rather than generalises. **0.54** is a normative action threshold from the Endocrine Society, with a
second guideline body (EAU) independently specifying withdrawal / dose reduction / venesection; EAU is
attested only secondhand here, so it is recorded via resolvable secondary attestations rather than
cited without an identifier.

**Why this marker first.** The reporting lab's own reference interval runs to 0.54, so no value below
the intervention threshold is flagged at all. Gate 3 at 0.50 and 0.52 surfaces before the lab does.
That is the capability; the citations are what let it land under I1.

**Unit convention — verified, load-bearing.** Haematocrit's `unit_established` is null, so `safety_gate`
does NOT normalise: it plausibility-gates on [0.20, 0.70] and compares the raw value directly against
band values. The reporting lab issues haematocrit as a FRACTION (0.47, interval 0.40–0.54), and the
bands are stored as fractions (0.50 / 0.52 / 0.54) to match. A band stored as 50 against a fraction
result would never fire, and would fail SILENTLY — a clean negative, not an error. The fraction
convention is the decision, not an accident.

**Status:** Reference asset plus its schema/gate test. No producer or gate logic changed
(`gates.py` / `producer.py` untouched). The lab store holds zero haematocrit results, so in production
the gate fires on nothing yet — the capability lands ahead of the data.

**How you know:** `safety_thresholds.json` now carries `thresholds.haematocrit` with three cited bands
and `_deferred` emptied; the asset re-verified pure ASCII, zero literal em dashes, and parsing (the
reference-JSON edit guard). `test_safety_thresholds_schema.py` gains live-asset coverage: `validate()`
walks the three bands, a positive `safety_gate(0.53) -> elevated` carrying its own citation, a
`no_asset` negative control on an unbanded marker, and gate 1's safety arm firing on
`first_observation_in_band` where the delta arm cannot. Backend suite **448 passed** (was 445, +3).

**Do not revisit unless:** a band's underlying guidance changes; the first-year scope on 0.52 is found
to generalise or to fail to; or the unit convention changes such that the stored fractions no longer
match reported results.

---

### 140. The interpretation producer is three-pass; `should_surface` is computed after relations, and ungrouped rows are non-demotable by construction

**Decision:** The producer moves from single-pass (4a) to three passes: pass 1 builds each member row
(delta, safety_gate, range_gate, raw news_gate — unchanged 4a arithmetic); pass 2 authors group
relations over the assembled member set, then computes `should_surface`; pass 3 is the interpretive
layer (verdict, levers — held for 4b-ii). `should_surface` moves from pass 1 to pass 2.

**Rationale:** 4a composed each member row in one shot and computed `should_surface` inside `_groups()`.
That order cannot survive 4b: a relation needs the group's fully assembled member set (a `ratio` needs
both operands) and the protocol phase, so a member's final `news_gate` is not knowable while that member
is being built. `_should_surface`'s predicate is unchanged and undoubled; only its call site moved. It
remains `any(news OR out_of_range OR in_band)`, and that OR is what makes demotion safe: demotion can
only ever clear `news`, so a group carrying a range breach or a safety band stays surfaced by
construction rather than by a rule someone has to remember. **Ungrouped rows never enter pass 2.**
Demotion requires a relation; relations are group-authored; an ungrouped marker has none. Its gates are
final at pass 1. The asymmetry is deliberate: ungrouped markers over-surface relative to grouped ones,
which is the safe direction, and I9 exists precisely because the alternative — silent omission — is the
failure mode. Moving `should_surface` is the highest-risk edit in 4b; landing it while it is provably a
no-op makes it reviewable as a refactor, where landing it in the same commit that grants relations
authority over surfacing would make a behaviour change and a structural change indistinguishable in the
diff.

**Status:** Landed on `feat/interpretation-relations` (feature commit, Steps B/C). Behaviour-neutral —
no output changed. Restructure and snapshot rode one commit; relations a second.

**How you know:** `build_foundation` output on the fixture seed is byte-identical pre- and
post-restructure (captured to JSON, `meta.generated_at` stripped, `diff` empty), and
`test_interpretation_producer_foundation.py` passed unmodified at the restructure checkpoint
(`git diff --stat` carried no entry for it before Steps C/E edited it).

**Do not revisit unless:** a fourth pass is needed, or a relation is found that requires cross-*group*
state — which this structure does not provide and which would need its own decision.

---

### 141. Protocol context is snapshotted as of the panel's collection date, not the generation date

**Decision:** `meta.protocol_context_snapshot` is built with
`current_state(..., today=trigger_panel.collected_date)`, not `date.today()`. It carries `key`, `type`,
`phase`, `assumable_present`, `relevant_date` per factor, flattened across the three declared types.

**Rationale:** The phase that interprets a panel is the phase at draw time; a panel from six weeks ago
read against today's stack would attribute the wrong protocol to the wrong numbers. `derive_phase`
currently consumes `as_of` in no rule — deliberately and documented, because every window that would
consume it needs a clinical number the module does not author. So this is **inert today**. It is
recorded now because the failure it prevents is silent: once window logic lands, a producer passing
`today` would be wrong in a way no test would catch and no output would show. The snapshot omits
`detail` (unbounded free text, not an interpretive input) and omits `active` — the ledger holds two
incompatible senses of that word, and `phase` is the one that survives the distinction.

**Status:** Landed on `feat/interpretation-relations` (feature commit, Step C).

**How you know:** a test asserts `as_of == trigger_panel.collected_date` against a fixture whose
collected date (2026-05-30) is not today, so a `today`-based implementation cannot pass it (asserted in
both directions: `== draw date` AND `!= date.today()`, with the control proven live).

**Do not revisit unless:** `derive_phase` gains window arithmetic, at which point this stops being inert
and the test above becomes load-bearing rather than anticipatory.

---

### 142. Relations are emitted before they are given authority — assembly and demotion land separately

**Decision:** This increment (4b-i) emits `relations_rendered` and enables **no** demotion. Gate 1's
delta arm is untouched; `news_gate` still returns exactly `{is_news, basis}` with no demotion basis
string anywhere in the tree. `feedback` relations are emitted with `precondition_status: "unresolvable"`.

**Rationale:** Relation *assembly* and relation *authority over surfacing* are separable, and separating
them is the point. Assembly is verifiable against the fixture right now — do the operands resolve, does
`render_on` place them on the right member lines, does a missing operand degrade rather than fabricate.
Authority over surfacing is not verifiable yet: it depends on relation semantics that are still
contested (the `discriminator` inversion is an open question) and on a phase vocabulary that does not
resolve (Q56). Granting authority to a surface whose correctness is unestablished would
make the first demotion bug indistinguishable from an assembly bug. `feedback` relations are emitted
`unresolvable` rather than silently skipped or silently satisfied: a skipped relation looks like an
absent relation; a satisfied one asserts that LH/FSH suppression is expected. Neither is a claim this
increment can make.

**Status:** Landed on `feat/interpretation-relations` (feature commit, Steps D/E).

**How you know:** a grep proves no basis string containing `demot` exists in the emitted tree; the
`news_gate` two-key shape holds on every member and ungrouped row; every `feedback` relation in the
output carries `unresolvable`; and `on_trt` is hardcoded in no non-test source file (grep clean), so no
code path maps it to a derived phase.

**Do not revisit unless:** the phase-vocabulary and discriminator questions both resolve, at which point
demotion is its own brief and its own entry (4b-ii).

---

### 143. A relation precondition names a factor and a set of admissible phases, not a phase

**Decision:** A `feedback` relation's precondition is
`{ factor_key, admissible_phases[], grade, rationale, evidence_refs[], contested_note }`,
replacing the bare `precondition_phase: "on_trt"`. For `hpg_gonadotropin_suppression`:
`factor_key "trt"`, `admissible_phases ["steady"]`, `grade "moderate"`, five `evidence_refs`,
and a `contested_note`. Content authored and authorised by Luke; transcribed verbatim.

**Rationale:** `on_trt` was a value `derive_phase` can never return, so the relation was
unevaluable from the day it was authored. The fix is not a translation table: `on_trt` was
never a phase, it was a factor and a phase compressed into one string, and the compression is
what made it untranslatable. The pair is load-bearing in both directions — a phase alone
(`steady`) fires identically on steady tirzepatide, and a factor alone ignores that a
washing-out factor does not close the loop. **`admissible_phases` is `["steady"]`, not
`["steady", "re_entering"]`** (an earlier draft's value): `derive_phase` reaches `re_entering`
only for `type == "behavioural"`, and `trt` is seeded `type == "protocol"`, so `re_entering`
is unreachable for this factor and authoring it would assert a possibility that cannot occur.
`washout` is excluded because gonadotropin recovery after cessation runs on a months-to-years
scale, so suppression during washout is recovery-in-progress, and marking it expected would
suppress the signal being watched for — a clinical judgement, authored by Luke, not derived
here. `evidence_refs` is required because a precondition becomes a read-constant under I1's
extension the moment demotion reads it; authored now rather than retrofitted, on the
safety-asset precedent (Q41 stayed open precisely as long as its citations were missing).
`grade "moderate"` and the `contested_note` are load-bearing: suppression on exogenous
testosterone is usual but not universal, so when demotion lands in 4b-ii this relation must
annotate rather than demote hard — an unsuppressed LH/FSH on TRT is a real finding this
relation must not be able to bury.

**Status:** Landed on `feat/relation-preconditions` (asset commit). Resolves Q56.

**How you know:** every value in `admissible_phases` is asserted (programmatically, against
`derive_phase`'s AST-resolved return set) to be a phase the function can return; `["steady"]`
passes, and the test is non-vacuous. The reference-JSON edit guard passed (pure ASCII, 0
literal em/en-dash, parses).

**Do not revisit unless:** a relation needs a precondition over two factors at once, which
this shape does not express and which would need its own decision.

---

### 144. The producer resolves preconditions; `expected_by_phase` is emitted with no authority

**Decision:** `_relations_rendered` resolves a `feedback` relation's precondition against the
declared-state phase map into `precondition_status` (`satisfied` / `not_satisfied` /
`unresolvable`) and emits `expected_by_phase`. `expected_by_phase` touches no gate.

**Rationale:** the producer hardcoded `precondition_status = "unresolvable"` for every
`feedback` relation. That was honest while nothing *could* resolve and became a false
statement the moment an asset carried a resolvable precondition — the code asserted a property
of the world rather than testing it. Status is now computed; `unresolvable` names its reason
(legacy shape, or `factor_key` absent from the ledger). `expected_by_phase` has **no
authority** — demotion stays held for 4b-ii, on the same seam and for the same reason as #142:
resolution is verifiable against the fixture today, authority is not, and a demotion bug and a
resolution bug arriving in one diff would be indistinguishable. The declared state is resolved
**once** per build — the same snapshot `meta.protocol_context_snapshot` uses, at the panel's
`collected_date` — because a second derivation is the shape of bug that reads `date.today()`
and passes every functional test.

**Status:** Landed on `feat/relation-preconditions` (feature commit). Partially resolves the
4b-ii track (resolution + `expected_by_phase`); demotion itself remains held.

**How you know:** `should_surface` and `news_gate` are byte-identical across the change on the
fixture seed (gate projection diffed empty); `news_gate` keeps its two-key shape and no basis
mentions demotion, precondition, or expectation; the three resolution arms have positive and
negative controls; a spy asserts `current_state` is queried once, with `today` == the draw
date != `date.today()`.

**Do not revisit unless:** demotion lands, at which point `expected_by_phase` gains authority
and that is its own decision (4b-ii).

---

### 145. Levers carry `declared_factor_keys`, and an empty list is an assertion

**Decision:** each of the six `lever_dictionary.levers` nodes carries `declared_factor_keys`.
Only `testosterone_substrate_load` is joined, to `["trt"]`; the other five carry `[]`.

**Rationale:** I3 requires filtered levers to be shown with a reason rather than dropped, which
needs a join from a lever to the declared factor representing it. No join existed — lever keys
(`testosterone_substrate_load`, `alcohol`, …) and ledger keys (`trt`, `tirzepatide`, …) are
different namespaces, and the lever node had no connecting field. **Present-and-empty is a
claim** — *no declared factor represents this lever, so I3 renders it unfiltered* — and is
deliberately distinguishable from the field being absent, which is why the key is present on
every node. `alcohol` has no ledger row and **none was created**: a declaration asserts
something true of Luke, and asset plumbing has no standing to make one. The filtering predicate
(4b-ii) will read `is_assumable_present` on a matched factor, which is also what stops an
episodic factor being assumed present at a draw it may not have been present for.

**Status:** Landed on `feat/relation-preconditions` (asset commit). Resolves Q57. The consumer
(`shared_levers` filtering) is held for 4b-ii — the join lands before the consumer.

**How you know:** `build_foundation` output is byte-identical across this change on the fixture
seed (nothing reads lever nodes beyond `min_meaningful_delta`, which reads
`marker_interpretation`, never `levers[]`); `trt` verified as a seeded declared factor; the
reference-JSON edit guard passed.

**Do not revisit unless:** a lever needs to be filtered by something other than a declared
factor.

---

### 146. Extraction confidence is derived at confirm, not reported by the model

**Decision:** `lab_reports.overall_confidence` is derived at confirm as `min(row confidences)`
— the same per-row `min(field_confidence)` values written to each `LabResult` — instead of
being read from the model's extraction output. The field is removed from `ReportExtractionMeta`
and from the extraction prompt's worked example.

**Rationale:** the first real ingestion run produced seven reports whose `overall_confidence`
was either 0.97 or exactly 0.0, never anything between. The three zeroes had per-row confidences
of 0.92–0.99 and values that matched the paper report, so extraction had succeeded and the field
alone was wrong. Two causes compounded: the Pydantic field defaulted to `0.0` when absent, and the
extraction prompt's own worked example contained `"overall_confidence": 0.0`, so the template the
model copies from carried a zero — sometimes it computed a value, sometimes it transcribed the
example. Fixing the example would have been the smaller change and the wrong one: `0.0` is a valid
confidence, so an omitted field and a certain-it-is-wrong field are indistinguishable, and the field
asked the model to invent a number with no grounded basis. `confirm` already derives per-row
confidence deterministically from `field_confidence`; overall is now derived the same way from the
same values. `min` was implemented over `mean` (the fork): it propagates the worst row, is consistent
with the per-row rule, and — because this gates a user-facing confidence statement — a single bad row
must not hide. The derived number is **triage** (direct human attention at rows worth checking), not a
verdict on the data; no human-verification/provenance field was added, because an edited value's
provenance is a different class from extraction confidence and needs its own design (see the
editable-confirm question).

**Status:** Landed on `feat/ingestion-findings` (feature commit). Forward fix + a backfill migration
(`b7f3a1c92e40`) recomputing every existing report's value from stored per-row confidences.

**How you know:** a report whose model output omits the field still scores non-zero (test), with a
low-confidence-row negative control proving the test cannot pass on a constant, and a no-field-confidence
row falling back to 1.0. Backfill proven on a synthetic seven-report reproduction (three 0.0 → 0.92/0.93/
0.94, zero zeros remaining); the real Railway before/after is an operator step post-deploy.

**Do not revisit unless:** a genuine per-report confidence signal appears that is not a function of its
rows.

---

### 147. A draw, not a report, is the interpretation trigger

**Decision:** the interpretation trigger is the newest **`collected_date`** and everything collected on
it; `compared_against` is the next distinct `collected_date` back — not "the newest `lab_report`" and
"the one before it". **No endpoint logic lands with this entry** — the 4b-ii endpoint is its own brief;
this records the resolution so the endpoint inherits it.

**Rationale:** the first ingestion run stored seven `lab_reports` rows sharing
`collected_date = 2026-05-30` — one blood draw, seven printed Sullivan Nicolaides panels. The 4b-ii
endpoint was specced to resolve the trigger as "the newest confirmed `lab_report`" and the comparison as
"the one before it"; against real data that is ambiguous in both halves and would compare a panel against
a sibling from the same draw. The draw is the unit the sample was actually taken in, and it makes
"compared against the prior panel" mean what a reader assumes. The read layer already worked this way and
is the precedent: `marker_series` partitions per marker over `(collected_date DESC, id DESC)`, so it never
carried the report-shaped assumption — only the trigger concept did. The producer is draw-safe already: it
reads only panel identity off the passed object; the fixture's `meta` encodes `collected` dates, not report
ids, so no regeneration is owed here (a producer docstring that called the inputs "report rows" was
corrected to note the draw-shaped trigger — doc only, no logic).

**Status:** Landed on `feat/ingestion-findings` (decision + producer docstring note). Endpoint deferred to
4b-ii.

**How you know:** the seven-report, one-date panel is in the store (first ingestion run) and is the case
that falsifies the report-shaped reading.

**Do not revisit unless:** two genuinely distinct draws land on one date, which a date cannot distinguish
and which would need a draw identifier rather than a date.

---

### 148. Renumber scope follows the branch's own tokens, not a file-type boundary

**Decision:** a merge's renumber resolves every `#NEXT` the branch introduced, wherever it
lives — markdown or source — and leaves every token it did not. The scope is **ownership**,
not file type. The pre-land verification must **classify** residual tokens (branch-own vs
pre-existing debt vs rule-text), not merely count them.

**Rationale:** the first two renumber merges treated `backend/**/*.py` as wholly out of scope,
because every `#NEXT` there was pre-existing debt from earlier branches — "skip source" and
"skip other branches' debt" described the same set. `feat/ingestion-findings` broke that
coincidence by writing decision references at the points the decisions are embodied (a comment
in `labs.py` explaining why `overall_confidence` is derived; a docstring in `producer.py`
recording the draw-shaped trigger) — correct practice, and it put six live placeholders inside
a directory the ritual had learned to ignore. `producer.py` is the case that forces the
distinction: it carries a resolved `#140` from an earlier branch and an unresolved `#NEXT` from
this one in the same file, so neither "skip the file" nor "substitute the file" is right. This
is the fifth instance of a verification scoped more narrowly than the property it was meant to
establish (after `demot` in a tree grep, `on_trt` across history, `^### #NEXT` against a
docstring, and a markdown-only sweep). The pattern is not carelessness: a check is written
against the failure imagined at authoring time, and the next failure is somewhere the check
cannot see. The mitigation is procedural — enumerate the branch's own tokens explicitly in the
merge brief, and require the pre-land verification to classify residuals rather than count them.

**Status:** Applied at this merge (`feat/ingestion-findings`): six source tokens resolved
(`labs.py`/`test_labs_confirm_confidence.py`/backfill migration → #146; `producer.py` draw
docstring → #147), the resolved `#140` and the ten pre-existing ROADMAP-L19 placeholders +
`SCHEMA.md:762` left untouched. Does **not** discharge ROADMAP L19 — that debt still needs a
shared-block edit across both repos; what changes is that the debt stops growing.

**How you know:** `backend/**/*.py` token count falls 16 → 10 across this merge; `producer.py`
carries `#140` and `#147` simultaneously; the eight pre-existing source files appear in no diff.

**Do not revisit unless:** the shared-block extension (ROADMAP L19) lands, at which point the
enumeration becomes a tooling concern rather than a per-brief one and this entry is superseded.

---

### 149. Every dependency is pinned; the MCP SDK stays on 1.x until migration is a deliberate increment

**Decision:** `mcp[cli]` is pinned to `==1.28.1`, closing the last unpinned line in
`requirements.txt` (twenty-one of twenty-two were already `==`). Migrating to the mcp 2.0 API is
explicitly deferred to its own increment; the pin holds 1.x until then.

**Rationale:** `requirements.txt` left `mcp[cli]>=1.0.0` open. On 2026-07-28 the SDK published
2.0.0, the next Railway build resolved to it, and `mcp/server/fastmcp` — removed in that release —
took the application down at import (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`).
Migrations had already run, so the database advanced to `c1e8b4d70f92` while the code could not
start, and the previous container kept serving stale. The failure was invisible to the suite, which
passed 460 against a session venv holding a working SDK — the check ran against an environment that
already had the dependency the deploy lacked. The pin is the fix; the version choice is the
judgement: 1.28.1 (26 June) predates the major by a month, where 1.29.0 shipped the same day as
2.0.0 and is unvalidated here.

Migrating to 2.0 is worth doing and is not this change. The new API is a redesign, not a rename
(`FastMCP` → `MCPServer`, with extensions, tool bindings, a request-state codec, elicitation
primitives); the auth and transport paths survive, so the blast radius is one file. Three things make
it a separate increment: the release was hours old when it broke this, nothing in the project can
verify that the application starts (see the deployability question), and production was stale while
the decision was being made. Restoring service and choosing an SDK architecture are different kinds
of work and must not share a commit.

**Status:** Landed on `fix/pin-mcp-sdk` (fix commit, one line). Deploy-reaches-healthy + `/mcp`
answers are operator verifications post-merge (the migrations already applied, so a green deploy is
the only outstanding proof).

**How you know:** a CLEAN virtualenv built from `requirements.txt` (not the session venv, which
already holds a working SDK) resolves mcp to 1.28.1 and imports all six SDK paths the app reaches —
`mcp.server.fastmcp.FastMCP` and every name in `oauth_provider`'s provider block among them; the
`git diff --stat` for the fix commit names one file and one line; the suite is unchanged at 460.

**Do not revisit unless:** the 2.0 migration lands, which supersedes the version choice but not the
pinning rule.

---

### 150. Navigation model — hub-as-home with persistent chat

**Decision:** `/dashboard` becomes a module hub — a tile grid routing to the app's surfaces, with
chat persistent rather than a destination. Four rules:

1. **Chat is docked, not routed.** A rail on desktop, a sheet/drawer on mobile. Present in every hub
   state, reachable from every module. There is no `/chat` route and chat is never a tile — you do not
   navigate to it.
2. **Header links retire into the hub as it absorbs them.** The current header (AM / PM / Labs /
   History / Settings / Sign-out) is at six and grows one per module; that growth forced the decision.
3. **Tiles may seed chat context, and must do so through existing paths.** A seeded lab entry routes
   through the existing on-ask mechanism (`find_marker` → `render_asked_lab_value`, request-scoped); it
   must not inject values into the standing prompt. Value-absence from standing context was made
   structural (#59) precisely so it could not be undone behaviourally, and a seeding feature is the
   most likely thing to undo it by accident. (Prompt hygiene, not #47 — see Constraint C.)
4. **The two dashboard panels become tiles, executed as a relocation.** `HealthPanel` and
   `WorkoutPanel` leave the dashboard and become two hub tiles — Recovery and Training — each routing
   to a page hosting the existing panel component rendered full-width. A move, not a rewrite: no new
   view is authored, and the hub shell stays a layout job.

**Constraint A — the #47 boundary is personalised action, and nothing wider.** #47 (verbatim) has the
platform "explains mechanisms, lists evidence-ranked levers, and filters for relevance; it never
connects a lever to a personalised recommended action", with the worked line "levers that influence
oestradiol" = education; "given your dose, adjust X" = prescription; "personalised prioritisation to
the individual" = prescription; enforced structurally — "no interpretation-output field expresses a
personalised action". So the gate is *personalised action or personal priority ordering*, not a
general prohibition on computation, richness, or explanation.
  * **Permitted on a tile:** values, lab-asserted flags, computed flags, deltas, trends, counts, dates,
    recency, completion state, mechanism, evidence-ranked lists, section counts — the user's own data
    or education about it.
  * **Forbidden:** any field or phrasing expressing a personalised action or ranking issues *for this
    user* — `recommended_action`, `priority_for_you`, `dose`, "your top three", "needs attention",
    "you should".
  * **The test:** does it tell this user what to do, or order their problems for them? Out. Does it show
    them their data, or explain how something works? In. `"3 markers out of range"` is arithmetic
    against the report's own printed range — in; `"3 markers need attention"` is personalised
    prioritisation, which #47 names as prescription — out. This corrects an earlier draft that read #47
    as forbidding computed flags/deltas/mechanism; that was contradicted by #47's own text.

**Constraint B — a readiness tile may not present the model forecast as authoritative (data integrity,
not regulatory).** NOT the old HRV suppression — that precondition is met and lifted (`95355fa`; the
row must not be re-frozen into this decision). What survives is narrower: `context_builder.
_section_daily_record` keeps the model forecast low-confidence "until it demonstrably beats the naive
baseline on this user's data" (`context_builder.py:368-369`) — a claim about the *model*, not HRV
availability. So a readiness tile is permitted, but must render `naive_baseline` and `model_forecast`
as what they are — the forecast not given authoritative visual weight until it has beaten the baseline.
Nothing here is a #47 matter.

**Constraint C — interpreted synthesis has one home (architectural, not regulatory).** #49 puts
interpreted meaning in the interpretation view. A tile duplicating that synthesis is not forbidden — it
is a coherence problem (two sources of interpretation drift apart). Soft, subordinate to product need,
and distinct from Constraint A; conflating the two produced the earlier draft's over-broad rule.

**Supersedes:** Nothing — no prior navigation/IA-model decision exists on master (verified: only #26,
a chat→repo handoff mechanism, matched). Ratifies, in modified form, the parked `Ideas.md` "chat entry
points as a feature" thesis (rules 1 + 3 keep chat ambient and every tile a doorway into it); rejects
only the strong reading in which no orientation surface exists at all. `Ideas.md` is project-knowledge,
not a repo artifact, so its parked state is not verifiable against master.

**Rationale:** Header-link growth is linear in modules and the app is phone-first for its daily
touchpoints, where six links is already poor. Decided now rather than after the interpretation view
lands — that view is the largest new surface coming (already routed at `/interpretation`, inert), and a
nav model decided after it is a retrofit. Chat-persistent over chat-as-tile because demoting chat to one
destination among six would abandon the stated product thesis silently; if that thesis is to change, it
should change in a decision that says so.

**Status:** Decided (design). **Build deferred behind 4b-ii** — governance-only, no hub shell built
this increment.

**How you know:** verified against master before minting — #47's Constraint-A quotations are verbatim
(`awk` extract of the entry); `Dashboard.jsx` still composes `ChatPanel` + `HealthPanel` +
`WorkoutPanel` (rule 4's relocation premise); `/interpretation` is routed under `RequireAuth` with no
nav link (inert); the on-ask path is `find_marker` → `render_asked_lab_value`, request-scoped and
documented "never part of the standing" prompt (rule 3's premise); no prior nav decision exists.

**Do not revisit unless:** a module needs to be a destination chat cannot serve (re-examine rule 1); or
#47's classification analysis changes on regulatory advice (per #47's own revisit clause), which would
move Constraint A.

---

### 151. Producer completed before the interpretation view is wired — the view is not made absence-tolerant

**Decision:** The interpretation view will not be made tolerant of absent producer fields.
Instead the producer is completed — `mechanism` and `axis_verdict` emitted — before the
committed fixture is regenerated and before the view is wired to a live endpoint. The view's
unconditional reads of `group.axis_verdict.*` and `member.mechanism.text` are therefore
accepted as correct rather than treated as brittleness to be defended against.

**Rationale:** Regenerating the fixture from the producer today would remove exactly the
fields the view hard-reads, breaking a view that currently renders. That forces a choice:
make the view tolerate absence, or complete the producer first. Absence-tolerance was
rejected because it makes a contract field's disappearance render as an empty section rather
than as a failure — the view would stop being able to tell "the producer does not emit this
yet" from "the producer regressed." Completing the producer keeps the view a faithful
consumer of a complete shape, at the cost of ordering one content task and one open question
ahead of all delivery work. That cost was accepted knowingly.

**Consequence for sequencing:** `mechanism` (content authoring) and `axis_verdict` (gated on
the generated-field `#47` question) both precede fixture regeneration, the endpoint, and view
wiring. Delivery is not partially startable ahead of them.

**Status:** Decided (sequencing). No code in this entry.

**Sizing reads that accompanied this decision (2026-07-30, read-only, this session).** Recorded
because they change what "complete the producer" costs, and both findings postdate the brief that
ordered the work:

- **`axis_verdict` is FOUR fields, not "an enum plus prose", and none is derivable today.** The
  object is `{verdict, protocol_phase, text, confidence}` in all six instances across both
  fixtures. `verdict` is `"coherent"` in every one — zero variation, so the fixture cannot reveal
  the vocabulary; no enum set exists anywhere in the repo (searched `backend/interpretation`,
  `backend/reference/*.json`, `backend/tests`, `frontend/src`, for `verdict` and for candidate
  values). The only other value named in the repo is `insufficient_data`, and it appears solely in
  a producer docstring aside. `protocol_phase` is worse than unsourced: its fixture values
  (`on_trt`, `active_training`, `baseline`) intersect `derive_phase`'s actual return set
  (`episodic`, `re_entering`, `steady`, `stopped`, `washout`) at **zero**, and `on_trt` is
  vocabulary a live test (`test_on_trt_vocabulary_is_gone_from_source_and_live_asset`) forbids in
  producer source. `confidence` (`Likely` / `Certain`) has no definition anywhere either. So
  `axis_verdict` needs an authored vocabulary + derivation rule before any part of it is
  emittable — it is not "one prose field behind an easy enum."
- **`mechanism` is three fields — `{text, protocol_factors_referenced, confidence}`** — with
  `text` the literal `…` placeholder in all ten instances. Authoring scope: **15 markers** can
  appear as group members (`hpg_axis` 6, `hepatocellular` 5, `erythroid` 4); **no marker belongs to
  more than one group** (multi-group count 0), so a flat `marker_interpretation[marker].mechanism`
  is a structurally valid home and group-scoping is unnecessary. The testable subset is the 4
  grouped markers the producer test seed carries (`testosterone_total`, `oestradiol`, `fsh`, `ast`;
  `vitamin_d_25oh` is seeded but ungrouped). **I1 does not bind the authored text:** `#95` extends
  I1 to `marker_interpretation` constants that *influence a gate*, `mechanism.text` influences
  none, the existing authored-prose precedent (`bilirubin_total.stable_rationale`) carries no
  citation, and no test enforces citation on that file.

**Do not revisit unless:** the generated-field question resolves in a way that leaves
`axis_verdict.text` permanently unemittable — at which point the view must tolerate its
absence, or the field leaves the contract, and this entry is superseded either way.

---

### 152. `axis_verdict` reduced to `{protocol_phase, text}`; `confidence` removed from the interpretation output entirely

**Decision:** The `axis_verdict` object is amended from four fields to two, and `confidence`
is removed from every interpretation-output field that carried it.

- **`verdict` — removed.** A neutral enum label communicates nothing to a reader, and any
  plain-language rendering of it is either reassurance or prioritisation, both of which `#47`
  places outside the education boundary. The value an axis-level statement carries was never
  the label; it is the explanation of why the members relate as they do. The label goes and
  the explanation stays.
- **`confidence` — removed, from `axis_verdict` and from `mechanism`.** The concept it would
  express is already structurally carried: an axis verdict is less certain exactly when its
  relations could not be fully evaluated, which `operand_status` already records and which an
  `insufficient_data` outcome already expresses. A separate scalar duplicates that in a
  weaker, unfalsifiable form. On `mechanism` there is nothing for it to express at all —
  the text is authored physiology, which is either correct or does not belong in the asset.
- **`protocol_phase` — retained, redefined as a projection.** The concept is sound; the
  fixture's values were not. They intersect `derive_phase`'s return set at zero and include
  `on_trt`, vocabulary a live test forbids in producer source. The field is therefore a
  projection of the per-factor phase already carried in `meta.protocol_context_snapshot`,
  not a separately-authored value.
- **`text` — retained, authored rather than generated.** An axis explanation describes a
  pattern — suppressed gonadotropins with an active TRT factor — not a set of numbers. It is
  therefore authorable once per (group, relation outcome, phase) and projected, following the
  precedent that `relations_rendered[].reads` narrative already lives in `marker_groups.json`
  and is copied verbatim by the producer.

Resulting shapes: `axis_verdict: {protocol_phase, text}` and
`mechanism: {text, protocol_factors_referenced}`. Both fully deterministic asset projections.

**Amends — corrected against master; the draft's premise did not hold.** No DECISIONS entry
ever established the four-field shape, so there is no prior ruling to amend. Verified: the
only occurrence of `protocol_phase` in the whole log is inside `#151`'s own sizing-read block,
which *reports* the fixture rather than establishing canon, and no entry names
`axis_verdict.confidence` or a `verdict` sub-field at all. The entries that record the
axis-verdict's *conceptual* content are `#63` (v0.4 promotes the output to group-primary and
names an "axis-verdict" per group, no sub-fields) and `#138` (v0.5, which states the axis
verdict is "the narrative above the member lines" — consistent with, and closer to, this
entry's `{protocol_phase, text}` than to the four-field object); `#135` records the view that
renders it. So the four-field shape was never canon in master: it existed only in the
UI-maintained contract file, the two hand-authored fixtures, and the view's reads of them.
**This entry is therefore the first master-canonical statement of the shape, and it supersedes
that residue rather than amending a decision.** The interpretation output contract
knowledge-file is stale from this entry forward; it is orientation-only and outside the repo,
so it cannot be corrected by Code.

**Rationale:** The fixture was the only source for all four sub-fields, and it is not a
specification. Four independent defects are now demonstrated in it: `shared_levers[].status`
inverted against the `#145` rule; `protocol_phase` values with zero intersection with
`derive_phase`; an invented `training_load` declared-factor key that exists nowhere in the
repo; and `confidence` values (`Likely`, `Certain`) that are the operator's own conversational
epistemic tags, imported into a data contract by an earlier chat session. A field whose entire
specification is a hand-authored artifact with four proven defects is residue, not requirement
— but the *need* an axis-level statement serves is real, so the field is reduced to the part
that carries value rather than removed outright.

**Consequences:**
- **Q62 has no current consumer.** It asked how `#47` is enforced structurally for a generated
  field; `axis_verdict.text` is now authored, so nothing generated remains in the
  interpretation output. Q62 stays open for any future generated field — it is not answered,
  it is unblocked-around.
- **`mechanism`'s producer projection is unblocked.** `{text, protocol_factors_referenced}` is
  now the complete contract shape, not a partial one, so emitting it is no longer a
  non-contract shape. The content is already authored and landed for all 15 group members.
- **The 1b view-correction list gains two removals** — `axis_verdict.verdict` and
  `.confidence` — alongside the corrections already known (consume `should_surface` rather
  than recompute; add the Ungrouped section; fix the `protocol_context_snapshot` reader).
  Verified complete: the ONLY consumers are `GroupCard.jsx` (lines 15, 17) and
  `GroupCollapsed.jsx` (lines 10, 12), and `.confidence` is read nowhere else in the frontend
  — `mechanism.confidence` has no consumer at all, so removing it costs the view nothing.

**Open gap this entry does not close — the projection needs a source-factor rule.**
`meta.protocol_context_snapshot.factors` is a LIST (one entry per declared factor), while
`axis_verdict.protocol_phase` is a single scalar. With more than one factor declared (trt +
tirzepatide + cbt_i are all real ledger keys) the projection is ambiguous until it names WHICH
factor's phase a given group carries. The mechanism for that already exists — relation
preconditions resolve against a named `factor_key` (`#141`/`#145`) — so the likely answer is a
group-scoped factor reference, but it is not decided here and the field cannot be emitted
until it is.

**Status:** Decided (contract). No code in this entry. Build order unchanged from `#151`:
producer completed before fixture regeneration and view wiring.

**How you know:** verified against master before minting — no entry pins the four-field shape
(grep over `protocol_phase` / `axis_verdict.confidence` / verdict-sub-field across
`DECISIONS_LOG.md`); `_SNAPSHOT_FIELDS` includes `phase` and a seeded steady TRT factor
projects `{"key": "trt", "phase": "steady", "assumable_present": true, ...}`, so
`protocol_phase` has a real source; all 7 rendered `relations_rendered[].reads` in the seeded
build are byte-identical to `marker_groups.json`, so the authored-narrative precedent is live,
not historical; and the view's `.verdict` / `.confidence` consumers are exactly the four lines
named above.

**Do not revisit unless:** the (group × relation-outcome × phase) authoring table proves
combinatorially intractable — at which point generated prose returns as the only practical
option and Q62 binds again. That sizing is not yet done and is the one empirical risk this
entry carries.

---

### 153. Relation-based demotion of gate 1's delta arm — the predicate is `feedback` + satisfied + complete, and never a bound crossing

**Decision:** Relations are granted authority over gate 1's **delta arm only**. A member's
delta-arm news verdict is withdrawn iff **both**:

1. the news did **not** come from a reference-bound crossing (`delta.crossed_ref is None`); and
2. the member carries a `relations_rendered` entry with `kind == "feedback"` **and**
   `precondition_status == "satisfied"` **and** `operand_status == "complete"`.

The demotion names itself in `news_gate.basis` as `relation_demoted_<relation_key>`. The
predicate lives in one named function (`gates.demoting_relations`) rather than inline, because
it is this decision and not an implementation detail.

**Why `feedback` only — the phrase "fully explained away by an in-phase relation" resolves to
one kind, not five.** `feedback` is the only relation kind whose applicability the producer can
*evaluate*: it alone carries a machine-readable `precondition` (`factor_key` +
`admissible_phases`, #141) which `_resolve_precondition` resolves against the panel's declared
state. The other four kinds — `ratio`, `co_movement`, `discriminator`, `context` — carry a
narrative `reads` string and operand lists and **no demotion condition whatsoever** (verified
across all ten authored relations; no `demotes` / `demotes_when` / `condition` / `predicate`
field exists on any). Demoting on one of those would mean asserting an explanation the producer
never checked: for `haemoconcentration_discriminator` it would literally be emitting "this rise
is a draw artefact" without ever looking at albumin. Encoding that arithmetic in code would also
put physiology in the producer, which #63 forbids by making `marker_groups.json` "purely
relational". So widening the predicate is an **asset-vocabulary change, not a code change** —
see OPEN_QUESTIONS Q65. The contract's own wording supports the narrowing: "**in-phase**" is
precisely the feedback precondition holding.

**Why a reference-bound crossing is never demoted — and why this is NOT the I5 clause it looks
like.** I5 needs no help from this predicate: gate 2 fires on a breach independently and
`should_surface` ORs the three gates, so demoting the delta arm on a breaching member cannot
hide it. The case the clause actually protects is the **opposite** transition,
`crossed_ref == "into_range"`. There gate 2 goes **quiet** (the value is back inside the
interval), `_magnitude` returns `meaningful` precisely *because* of the crossing, and an
in-phase relation would swallow "this marker returned to range" — which is real news to a
reader whatever the mechanism explains. `crossed_ref` is bidirectional (`delta()` emits
`into_range` / `out_of_range`), so the clause is live rather than unfalsifiable caution.

**What this deliberately does not demote:** the safety arm (I8), gate 2 (I5), gate 3, a
`not_satisfied` or `unresolvable` precondition (the first is news, the second is never grounds
for silence), a `degraded` relation (it is the case where the producer names what it could not
see, so it cannot also be a full explanation), a first observation (no delta arm exists), and a
delta arm that was already quiet (demotion withdraws a verdict; it never adds a token to a
marker that never moved).

**I8 holds by construction, not by check.** Demotion runs **before** the safety arm, and the
safety arm re-forces `is_news = True` on any `band_change` unconditionally — so no code path
lets a demotion outlive a band change. This is the ordering the gate module's docstring demanded
before the logic existed, and the logic inherited it.

**Status:** Landed on `feat/interp-demotion`. Producer gate 1 is now re-computed in pass 2 once
a member's relations exist — the reason #140 moved surfacing out of pass 1; pass 1's `news_gate`
is explicitly provisional from here.

**How you know:** G1 artifact — both canonical panels are **byte-identical** before and after
(the §2 seed's feedback relation is permanently `degraded`: it seeds `fsh` without `lh`), and on
a panel where the relation resolves satisfied+complete exactly one member leaves What Moved —
`fsh`, attributed to `hpg_gonadotropin_suppression`, carrying `gate2_breach=False`,
`band_change=None`, `crossed_ref=None`. I5 under pressure end-to-end: `fsh` below range on both
draws has gate 1 demoted and still surfaces on the breach. I8 under pressure at gate level,
**paired** — the identical call minus the band change demotes, which is what proves the path was
live rather than unavailable. `gates.py` diff confined to the delta arm: `range_gate`,
`safety_gate`, `delta`, `_magnitude` and `_resolve_band` bodies are absent from it and the
executable safety-arm block is unchanged. Suite 478 to 506.

**One coverage gap, recorded not glossed:** the I8 pressure test is **gate-level, not
end-to-end**, because no marker can currently carry both a safety band and a demotable relation
— the asset bands `haematocrit` alone and the sole `feedback` relation renders on `lh`/`fsh`.
That intersection is **contingent, not structural**: a haematocrit feedback relation or an `lh`
band would close it, at which point the unit-level test would keep passing while covering less.
`test_banded_and_feedback_markers_do_not_yet_intersect` is the tripwire — it asserts the
emptiness, and its docstring instructs the reader to write the end-to-end test and delete the
tripwire when it fires.

**Do not revisit unless:** a relation proves able to explain a movement this predicate refuses
to demote — most likely a `discriminator` whose condition someone can state mechanically (the
normal-GGT / transaminase-rise case is the obvious candidate). That is Q65's first branch, and
it supersedes clause 2 of this predicate rather than this entry as a whole.

---

### 154. Relation conditions become machine-readable and eliminative; the group descriptor states a position only where it is defensible

**Decision:** Q65 resolves toward a declared condition per relation. Relation `reads` prose is
decomposed into a branch set, each branch carrying its own fragment and resolving to
`excluded`, `not_excluded`, or `not_assessed`. The group descriptor reports the surviving set
with the evidence that excluded the others and the operands that were never assessed.

**Governing rules:** (1) the descriptor describes the overall position; (2) it takes a position
only where defensible; (3) where the evidence produces only options it presents the options and
the evidence rather than picking one; (4) it never proposes a solution — levers are presented
separately, information only, ranked by evidence strength and filtered for relevance.

**Defensibility, operationally:** every branch resolved `excluded` except exactly one, and no
branch resolved `not_assessed`. A live unassessed branch means a leading option, not a position.

**Condition shapes** — `ratio_band`, `operand_in_range`, `co_movement`, and the existing
`feedback_precondition`. Authors supply thresholds and operand names to a shape; they do not
author predicates. This is why the vocabulary does not become an expression language, which was
Q65's stated worry. Band sets must tile — an explicit non-discriminating band is required rather
than a gap between bands.

**CORRECTED FROM THE PROPOSAL — shape is declared per relation, not implied by kind.** The
proposal claimed the relation kind fixes the condition's form. Verified false against master:
`haemoconcentration_discriminator` is declared `kind: discriminator` but its condition is a
co-movement test (do albumin/protein rise *with* the red cell line) with MCV as a tiebreak. Kind
and shape therefore diverge in the live asset, so `condition_shape` must be an authored field
per relation and "kind implies shape" is at most a default. Recorded because building the
mapping as a rule would have failed on the first relation that uses it.

**Cross-relation conflict is a first-class output.** Where two relations each resolve cleanly and
point in different directions, the descriptor states that both apply and disagree, with the
evidence for each. It does not adjudicate — that would violate rule 2. This case is invisible at
member level by construction and is the primary justification for a group-level descriptor.

**`#47` boundary:** the descriptor never names a lever; it may state its own coverage (which
declared operands the panel lacked) because that is a statement about the algorithm rather than
about the reader; it must never recommend a test and must never carry "talk to your doctor",
which belongs to chat, asked and in context, per `#59`. Levers are ranked by evidence strength,
never by predicted effect for the individual. **Verified already-built, so rule 4 constrains
rather than adds:** `poolLevers` sorts on `GRADE_ORDER` (evidence grade) and `shared_levers`
already filters to present markers and marks `already_in_play` from declared state (#145).

**Amends:** `#152`, for the `axis_verdict` authoring approach only. `#152` retained
`protocol_phase` and made `text` authored per (group x relation-outcome x phase); this replaces
that with assembly from branch fragments and **drops `protocol_phase`**, which duplicated
`meta.protocol_context_snapshot` and whose scalar-vs-list projection gap `#152` itself recorded
as unresolved. Resulting shape: `axis_verdict: {text}`. No decision pins `reads` as a single
verbatim string (verified — the only mention in this log is `#153`'s observation that relations
carry narrative `reads` and no condition), so nothing else is amended.

**Decomposability, walked over all ten relations (Q65's own gate).** Every string decomposes
structurally, but three findings qualify the work:
- **Two ratios carry no authored thresholds.** `hpg_t_e2_ratio` names no numbers at all and
  `de_ritis_ratio`'s three bands do not tile (a ratio of 1.4 falls in none). Decomposition is
  therefore *new evidence-cited authoring* (I1), not mechanical splitting.
- **`ggt_hepatobiliary_discriminator` states only one branch** (normal GGT). Its complement is
  unauthored and must be written.
- **`shbg_free_fraction` (`context`) does not branch at all** — it is guidance on how to read
  another marker. Confirmed: `context` carries no condition and always renders.
- **The near-counter-example:** `hpg_substrate_co_movement` reads "On stable dosing these track
  the substrate pool together" — a co-movement that is itself PHASE-CONDITIONAL. None of the four
  shapes expresses that; it needs `co_movement` composed with a `feedback_precondition`. The
  four-shape model must admit composition, or this relation is authored wrong.

**Consequence for sequencing:** this is a lane, not a tail on 4b-ii. `axis_verdict` emits the
invariant per-group floor sentence in the interim, which satisfies `#151`'s producer-complete
requirement against the reduced contract and unblocks 1b delivery immediately.

**Status:** Decided (contract + asset vocabulary). No code in this entry. Resolves Q65.

**Do not revisit unless:** a `reads` string is found that cannot be decomposed into branch
fragments without loss of meaning — which would show the conditional structure is not general,
and the model would have to admit non-branching relations as a first-class case rather than only
`context`. (`hpg_substrate_co_movement` is the near miss: decomposable, but only under shape
composition.)

---

### 155. Retain-raw is ratified as intended architecture, not an accident; promotion is two-tier, and the live gap is ingestion, not recognition

**Decision:** Every analyte the extractor observes is stored with its raw label, value, unit,
reference interval, source report and collection date, whether or not it maps to a canonical
marker. Canonicalisation is a **mapping layer over a complete raw store**, never a filter applied
at ingest. Unmapped analytes are surfaced — identified and returned for human binding — never
silently discarded. Because the raw store is complete, **promotion is retroactive**: making a
marker canonical unlocks its entire observed history rather than starting a series at the
promotion date.

**Promotion is two-tier.** A marker becomes *canonical* (key, display name, unit, reference-range
source) cheaply; it is then stored, charted and trend-visible. It becomes *interpretable* (group
membership, `min_meaningful_delta`, `stable_rationale`, `mechanism`, all I1-cited) as a separate
authoring act. Conflating the two makes cheap work wait on expensive work.

**THIS ENTRY RATIFIES; IT DOES NOT INTRODUCE.** Verified against master before minting, and the
proposal's premise was wrong in four ways. Recorded in full because the corrections change what
is owed:

1. **Retain-raw is already built.** `LabResult.marker_canonical` is **nullable** and `#58`
   already rules that "unmapped raw names surface as an interpretation-layer skip, not a
   placeholder canonical id". The confirm path writes every extracted row regardless of mapping
   and returns `unmapped` in `ConfirmResponse` for human binding. So the architecture is present;
   what this entry adds is that it is **intended and constraining** — a future change that
   filters at the door is now a violation of a decision rather than a refactor.
2. **`ld` and `haemolysis_index` are already canonical** (`marker_canonical.json`, 66 entries,
   both exact keys). The proposal's §6 rested on their being unrecognised. They are not.
3. **The canonicalisation work queue is empty.** Every operand and render target declared across
   all ten relations — 17 keys, including `albumin`, `ld`, `haemolysis_index` — is already
   canonical. So coverage-driven prioritisation over *canonicalisation* has nothing to rank
   today. The metric that does have signal is **interpretability**: exactly three declared
   operands are canonical-but-not-interpretable — `albumin`, `ld`, `haemolysis_index`. That is
   the two-tier state, live, and it is the list worth ranking.
4. **The live gap is INGESTION, not recognition.** The store holds 7 reports, all collected
   2026-05-30, 27 results, and **zero unmapped rows**. It contains no `bilirubin_total`, `ggt`,
   `alp`, `ld`, `haemolysis_index`, `ast`, `alt` or `albumin` — the 6 Mar 2026 routine chemistry
   the worked example draws on has never been ingested. Once it is, `bilirubin_isolation`
   resolves fully **with no asset change at all**: a relation operand only needs to be present in
   `marker_series`, which requires the marker to be canonical and ingested — NOT to be
   interpretable or a group member (`albumin` already works this way, as an operand of
   `haemoconcentration_discriminator` while being no member of `erythroid`). The difference
   between an open option set and a defensible position on that panel is one upload.

**Two further corrections, both to worries the proposal raised:**
- **Panels already span reports.** `marker_series` partitions **per marker** across all of a
  user's reports (`partition_by=marker_key`, ordered `collected_date DESC, id DESC`); it never
  scopes to a single report. So a cross-report relation such as albumin-with-haemoglobin resolves
  by construction, and the "unit of interpretation might be a report" risk does not exist. Note
  the actual shape is broader than a collection episode: it is newest-per-marker regardless of
  date, which is why the §2 fixture legitimately mixes a 2025-12-27 vitamin D with a 2026-05-30
  draw.
- **There is no `ai_draft` → `human_verified` gate to reuse.** `ai_draft` appears as a `status` /
  `draft_status` string in the three reference assets; **`human_verified` appears nowhere in the
  repo and no code implements a promotion mechanism.** It is a convention marker, not a gate, so
  a marker-promotion workflow would be building one, not reusing one.

**`#42` applies unchanged** — verified: both `latest_lab_results` and `marker_series` filter
`LabReport.user_id`, so the raw store is per-user on every read.

**Status:** Decided (architecture). Ratifies built behaviour and names the two-tier distinction;
the only new build implied is an interpretability-coverage ranking, and it has exactly three
candidates today.

**Do not revisit unless:** raw retention proves to carry a storage or privacy cost that outweighs
retroactive promotion — in which case the fallback is retention of unmapped analytes only for a
bounded window, which preserves most of the value and should be costed before the decision is
reversed outright.

---

### 156. Series integrity is a precondition of the gate model, and is guarded at ingest rather than assumed

**Decision:** Confirm-time ingest detects that a marker already exists for the user at the same
collection date, keyed `(user_id, marker_canonical, collected_date)`, and surfaces the collision
for resolution rather than silently accepting it. Detection is marker-level only; no
report-level key is added.

**Why this is a decision and not a bug fix:** every invariant the gate model asserts is
conditional on the series being correct, and nothing tested that. `I8` guarantees a
`band_change` cannot be *demoted* — `#153` made that hold by construction. It does not guarantee
a `band_change` is *detected*. A duplicated prior gives `marker_series` two same-draw rows at
`rn=1` and `rn=2`, drops the true earlier prior, resolves both bands identically, and returns
`band_change: None`. The safety arm never fires, and the output reads as a legitimately quiet
marker — `direction: flat`, `magnitude: within_noise` — with nothing recording that a comparison
was lost. The guarantee the model actually carries is "no gate suppresses this," not "this cannot
be missed." Dedupe is the first instance of that class, not a one-off.

**Demonstrated before it was built** (empirically, not argued — the brief rested on one claim
about `marker_series` and that claim was tested first). Haematocrit 0.515 (`watch`) → 0.530
(`elevated`), constructed so the safety arm is the only possible source of news:

| scenario | `band_change` | `is_news` | `should_surface` |
|---|---|---|---|
| clean two episodes | `escalated` | True | True |
| duplicate of the **newest** episode | **None** | **False** (`flat_vs_prior`) | True |
| duplicate of the **older** episode | `escalated` | True | True |
| full band **exit**, clean | `exited` | True | True |
| full band **exit**, duplicate of newest | **None** | **False** | **False** |

Three findings the brief did not have. **(a)** It is the duplicate of the **NEWEST** episode that
masks; duplicating the older one changes nothing, because `rn=1`/`rn=2` must both land on the
same draw. The brief's construction said the opposite while its description of the mechanism was
right. **(b)** While the marker stays *in* a band, `should_surface` survives via gate 3 — the
loss is the transition and the news verdict, not the group. **(c)** When the marker **exits the
bands entirely**, gate 3 goes quiet too and `should_surface` flips to False: the group leaves
What Moved altogether. That last row is the complete-masking case.

**Detection, not enforcement.** A unique constraint would block the corrected-result case, where
the second value for a marker at a collection date is the correct one — the pathology reports
state results "can only be changed with a corrected result." Two panels from one draw may also
legitimately carry a common analyte, which is `#147`'s expected shape. A collision on one marker
never fails the whole upload: `on_duplicate=skip` (default) writes every non-colliding row and
still creates the report, because the document genuinely exists (`#155` retain-raw);
`keep_both` writes the colliding row for a case the operator knows is legitimate.

**`supersede` is deliberately NOT offered.** `LabResult` has no supersede column — `#52` is
explicit that supersession is compute-on-read — so the only available mechanism would be
deleting the earlier row, which contradicts `#155`'s ratification of retain-raw. Superseding
needs a `superseded_at`/`superseded_by` affordance so the original is retained but excluded from
the series. That is a schema change and was not invented here; recording the absence is the
honest outcome.

**Correction versus re-upload — VERIFIED, nothing distinguishes them.** `source_completeness`
separates `sonic_dx_extract` from `full_report`, but that is document provenance, not correction
status, and no other stored field carries it. The resolution is therefore **operator-chosen and
must never be inferred**; no heuristic is implemented. What the platform does instead is return
both the existing and incoming values on the collision, so the operator can distinguish a
byte-identical re-upload from a changed value without a second round trip.

**Null-canonical is GUARDED, not left as a gap.** `marker_canonical` is nullable, so a
canonical-only key would miss unmapped rows — and under `#155`'s retroactive promotion a
duplicated unmapped raw becomes a duplicated series at the moment of promotion, the same failure
surfacing long after its cause. The key therefore falls back to `marker_name_raw` when canonical
is null. The check also catches the same marker twice within one submission, which the
`(lab_report_id, marker_name_raw)` constraint cannot see when two raw labels resolve to one
canonical id.

**Status:** Decided (ingest integrity). Code in this entry. `result_count` now reports rows
**written** rather than submitted, so a skipped collision is visible to the caller. Verified
against live data: zero duplicate `(user, marker, collection date)` groups today.

**Do not revisit unless:** a second series-integrity failure is found that this key does not
cover — at which point the guard belongs at the read layer (`marker_series` asserting its own
inputs) rather than at each write path, and this entry is superseded rather than extended.

---
### 157. The ingest path asserts persistence rather than response success; the zero-row reports were `#156` working, and the loss was one nobody read

**Decision:** The lab ingest path is held to a **persistence standard** — a confirmed result is
proven present in `lab_results` by reading the row back, never inferred from a `201` — and the
confirm outcome is **surfaced to the operator** rather than merely returned. `#156`'s guard is
recorded as correct and load-bearing; the defect was in what happened to its report.

**The reported symptom was not the defect. VERIFIED at Step 2, and the brief's causal hypothesis
is falsified.** The brief proposed that `#156` "cannot fire on a write that produces no rows,"
and that a lab result displayed on the confirm screen was failing to reach the database. Both are
wrong, in the same direction: the guard fired, correctly, and *caused* the zero-row write by
design. All ten zero-result `lab_reports` are re-uploads in which **every** submitted marker
already existed for that user at that collection date, so every row was skipped, `result_count`
returned `0`, and the report envelope was still created per `#155` retain-raw. Nothing was lost.
The values are held on the earlier report. Live database, at investigation: 43 reports, 168
results, **zero** duplicated `(user, marker, collection date)` groups, and 66 distinct canonical
markers against a 66-entry canonical map.

**How the wrong conclusion was reachable, and what actually failed.** `#156` closes by recording
that `result_count` reports rows **written** rather than submitted, *"so a skipped collision is
visible to the caller."* It was visible to the caller. The caller — `Metrics.jsx` — awaited the
POST, discarded the response, and rendered an unconditional `"Report saved"` toast. So a save
that wrote zero rows was indistinguishable from one that wrote twelve, and the read-back rendered
the resulting empty report as column headings above nothing, which reads as a report that had no
results rather than as a fault. Ten of these accumulated across a backfill and were discovered
weeks later by reading a screenshot.

**A field that is returned but not read is not a report.** That is the generalisable finding, and
it is a *different* failure from the one `#156` guarded: `#156` correctly refused to write blind
and correctly told the caller. The loop closed at the API boundary and stopped. An outcome
channel is only load-bearing when something consumes it — the same standard `#146` applied to
`overall_confidence` (a model self-report nobody could distinguish from a genuine zero), one
layer further out.

**A genuine loss WAS found — a different one.** The skip set was keyed by **marker**, and the
write loop tested membership by that key, so a marker appearing twice inside one submission
suppressed **every** row carrying it, including the first, which had nothing to collide with.
That marker reached no row anywhere. This is categorically unlike the database-collision case,
where skipping is correct precisely *because* the value is already stored. Skip is now decided
per **row index**. Today this is latent rather than active — no canonical id in
`marker_canonical.json` currently has more than one raw synonym, so the path fires only on an
identical raw label repeated in one document — but it arms itself the moment a synonym is added,
which is a routine map edit.

**How you know:** the persistence tests confirm a document and then query `lab_results`
**directly**, asserting the row exists with the value submitted; the response object is not the
evidence. Non-vacuity is on the record rather than asserted: against the pre-fix handler the new
file ran **2 failed, 6 passed** — the two intra-batch cases — and **8 passed** after. The six that
passed pre-fix state the standard against a happy path that was never broken, and are reported as
such rather than dressed up as regressions. Full suite 521, from 513.

**Why the empty envelopes exist at all, and the limit of this entry.** `#155` retain-raw means the
report row is created because the document genuinely exists, and `#156` is explicit that detection
is marker-level with **no report-level key**. A full-collision re-upload therefore has nothing to
collide on *at the report layer*, and produces an empty envelope every time. That is the real
structural gap — not the one the brief named — and it is not closed here, because closing it needs
report-level identity the schema does not capture. It is now at least visible: an empty report
renders as a fault.

**Status:** Decided (ingest integrity). Code in this entry. Junk rows reported to the operator and
**not deleted** — `#155` ratified retention and a delete is the operator's call.

**Do not revisit unless:** report-level identity lands — `Document ID` / `Lab ID` from the source
document, currently uncaptured — at which point a re-uploaded document is recognised as the same
document before any row is examined, the empty envelopes stop being created rather than being
explained, and this entry's last two paragraphs are superseded.

---
### 158. "Your Results" carries values; an upload that contributed none is an upload event, not a result

**Decision:** The results list shows reports that contributed marker values. A report whose
markers were all declined as already-stored duplicates is removed from that list and surfaced in
an upload history instead. Collision detection is additionally performed at the confirm screen,
before the write, so the operator learns of a repeat while still deciding rather than afterwards.

**The pre-check does not replace `#156`'s write-time guard.** The guard is the correctness
mechanism and is unchanged; the pre-check is the interface to it. A check that informs a decision
and a check that protects the data are different obligations, and collapsing them would leave the
write unguarded the moment the interface changes. **Proven, not asserted:** both guard regions
hash byte-identical to the pre-change baseline (detection block `fb9e9cbf84a535c5`, write-loop
skip `c478d7313ea5c50f`).

**The pre-check needed no endpoint — verified before building.** `GET /labs/results` already
returns every stored report with its `collected_date`, `marker_canonical` and `marker_name_raw`,
and `GET /labs/canonical-map` resolves an extracted raw label exactly as the server does. Both are
already fetched on mount to render the results table, so the check is client-side computation over
state in hand. Cancelling therefore issues no request at all: **no `LabReport` row, no history
entry** — confirmed by driving the real page and counting requests (zero after cancel).

**Rationale:** `#156` worked exactly as designed and the interface reported it as a permanent
fault — four red cards apologising in the operator's history for a correctly declined re-upload.
The information was right and its placement and persistence were both wrong. A record of the
upload is still owed, which is what the history view is for; it also answers which source
documents have been ingested, which nothing previously could.

**Consequence for `#156`'s junk rows:** the ten zero-result reports listed at `#157`'s close-out
are reclassified rather than deleted. They were never junk — they are upload events with no
contribution, which is what the history view records. `#155`'s retention holds unchanged and no
deletion decision is required.

**Distinguishing declined from unparseable — the store could NOT, and the gap was deeper than a
missing field.** Two findings, both verified against the pre-change handler:

1. Nothing persisted the outcome. The confirm response carried `duplicates`, but no column
   recorded it, so after the fact both cases were simply a report with zero rows.
2. **An unparseable document could not reach the store at all.** A submission carrying no results
   tripped `assert row_confidences`, which raised *before* `db.commit()` — HTTP 500, no row
   written. So the fault case had no representation to be confused with; it had none at all.

Filtering the results list on row count would therefore have hidden faults along with repeats, and
the fault would additionally have been invisible everywhere. `lab_reports.zero_row_reason` is
added: `NULL` when the report contributed rows, `all_markers_declined`, or `no_values_extracted`.
The assert becomes a recorded event — a chart or scan with no results table is a real document the
operator uploaded and is owed a record of. Finding (2) is also what makes the migration's backfill
a **proof** rather than an inference: the fault value was unreachable before this change, so no
legacy zero-row row can carry it and the backfill cannot mislabel one.

**Where the brief was diverged from, and why.** It said not to reword the zero-row red panel, on
the reasoning that once declines left the list the copy would only appear at confirm. But the panel
must remain for faults, and its copy attributed the emptiness to a repeat — *"this usually means
every marker was already recorded ... the upload was a repeat."* Left in place it would tell the
operator that an unreadable chart PDF was a duplicate. That is a misattribution, and worse than the
emptiness it replaced. The decline copy was not polished; it leaves that surface together with the
declines, and the fault is given copy that is true of it.

**Status:** Decided (interface + ingest surfacing). Code in this entry. Suite 527, from 521.

**Do not revisit unless:** the upload history grows past a flat list — at which point it is a
module with its own scope and should be planned as one rather than extended by increments.

---
### 159. The interpretation output is a reading of more than one draw, and says so; provenance is partitioned rather than bounded, scoped away, or composited silently

**Decision:** `Q69` resolves to candidate **(e) — partition the output by provenance**, a candidate
added to the set after the fact. `marker_series` keeps its unbounded newest-per-marker read. What
changes is that the output stops presenting a multi-draw composite as a single panel: every group
carries an as-of date derived from its members, a group whose as-of differs from the trigger draw
is labelled rather than merged, a group whose members span draws says so with each member carrying
its own date, and a relation whose operands come from different draws states that.

**Why the original candidates were amended rather than chosen from.** `Q69`'s (a), (b) and (d) were
drafted before the producer had ever run over real series. The first run (1b Step 0) falsified all
three on one piece of evidence: **the `hepatocellular` group is absent from the newest draw
entirely — every member current at `2026-03-06` against a `2026-05-30` trigger — and it carries all
three out-of-range markers in the dataset** (`ast` 47 H, `alt` 53 H, `bilirubin_total` 28 H).
Verified: the `2026-05-30` draw measured no liver marker at all.

- **(a) recency-bounded operands** — at 85 days the group survives an arbitrary window and vanishes
  at 91. A cliff, not a rule.
- **(b) draw-scoped interpretation** — an interpretation of the `2026-05-30` draw would contain no
  liver markers, because that draw did not measure liver. The raised transaminases and the elevated
  bilirubin disappear until a new liver panel is drawn.
- **(d) hybrid** — inherits (b) for gates and relations, so it hides the same content.

All three suppress the most clinically interesting finding in the data. **(c) surface the age** is
built (`#158`, member-level dates rendered and confirmed) and is the foundation of (e) rather than a
competitor to it.

**The reframe.** `Q69` asked which markers belong in the panel. The answer is all of them — a raised
bilirubin from March is real, and hiding it because a May draw did not repeat the test would be a
defect, not a fix. The answerable question is *what the output is a reading of*, and the honest
answer is: more than one draw.

**Group date coherence is a property of the DATA, not of the code — verified, and rule 2 is already
firing.** `_assemble_members` pulls each member independently from `marker_series` with no date
constraint, so nothing enforces coherence within a group. Two partial-group draws have already
occurred (`hpg_axis`, `2026-01-07` at 3/6 and `2026-04-20` at 3/6), and the **prior** side of
`hpg_axis` already spans three dates today: `testosterone_total`/`shbg`/`testosterone_free_calculated`
against `2026-04-20`, `lh`/`fsh` against `2026-01-07`, `oestradiol` against `2025-12-27`. The
group's current side is coherent only because the May draw happened to measure all six. Rule 2 is
not a hypothetical guard.

**CORRECTED FROM THE PROPOSAL — rule 3 does NOT amend `#154`, and adding a fourth state would be a
category error.** The proposal asked whether `#154`'s eliminative model has room for a fourth
relation state, "evaluated across draws", alongside `excluded` / `not_excluded` / `not_assessed`.
Read against master: those three are **branch** resolutions — each branch of a decomposed condition
answers "did the evidence rule this out?" — not relation states. Operand provenance is not a
resolution of a branch; it is a property of the inputs, and its existing peer is `operand_status`
(`complete` / `degraded`), which already sits outside the branch model. Cross-draw provenance
belongs there, orthogonally: a relation can be both degraded and cross-draw. `#154` is therefore
**not amended** — and its own `#47` clause already licenses the statement, since the descriptor
"may state its own coverage ... because that is a statement about the algorithm rather than about
the reader", which is exactly what naming an operand's draw is.

**What (e) does NOT fix, stated so it cannot be claimed later.** `min_meaningful_delta` remains a
bare percentage with no time dimension. (e) makes the interval visible; it does not make the
threshold sensitive to it. That defect would exist in a perfectly draw-scoped world with irregular
spacing and is recorded as its own question rather than being marked resolved by a decision that
does not touch it.

**Status:** Decided (interpretation input model). **No code in this entry** — the producer and view
changes are the delivery, and the wiring bar below is what gates them.

**Wiring bar (1b Step 5).** Resolution on paper does not discharge a concern about invisibility, so
`Q69`'s block on wiring the view to live data lifts when **both** hold: member-level dates (built,
`#158`) and **group-level as-of rendered**, so a group three months older than the panel header says
so at group level rather than only per member. Relation qualifiers and provenance sectioning — the
rest of (e) — follow without blocking delivery.

**Do not revisit unless:** a group is found whose members span draws so widely that a single
group-level as-of misleads more than it informs — at which case the group-level date is the wrong
unit and the partition belongs at the member level throughout.

---
### 160. A group's as-of date derives from its members' current values, and a group off the trigger draw is labelled rather than merged

**Decision:** A group's as-of date is derived from the collection dates of its members' **current**
values only. Where those agree it is that date; where they differ the group states the span, and
per `#158` each member already carries its own date. A group whose as-of differs from the trigger
draw is labelled in place.

**Why this entry exists:** `#159` rule 1 requires the field and says it is "derived from its
members" without fixing the derivation. Verified against master before implementing — it does not,
so the derivation is decided here rather than chosen silently at the keyboard.

**Why current-only:** the prior side spanning draws is a distinct defect — about comparison
intervals rather than about what the panel contains — and is recorded at `Q71`. Deriving the as-of
from both sides would conflate them and would mark part of `Q71` resolved by a decision that does
not address it. This is concrete, not hypothetical: live `hpg_axis` has a coherent current side at
`2026-05-30` and a prior side spanning `2026-04-20` / `2026-01-07` / `2025-12-27`, so a both-sides
derivation would report that group as spanning when what it *contains* does not. A test pins the
boundary.

**Emitted by the producer, not derived in the view.** A view computing `min(member dates)` itself
would be a second source of truth — the same defect `sections.js` carried when it recomputed
moved-ness from the gates instead of reading `should_surface`.

**"Labelled", verified — not "labelled and separated".** The brief proposing this entry quoted
`#159` as requiring the group be "labelled and separated rather than merged", and framed an
in-place label as the minimum standing in for sectioning. `#159`'s committed text is "is **labelled**
rather than merged". An in-place label is therefore exactly compliant, and no minimum-versus-full
trade-off was made. Provenance sectioning remains part of (e), unstarted and not owed here.

**Two levels, one statement — corrected after reading the live page.** With a member-level date
badge on every stale marker the page carried **forty** "not this panel" labels, five of them
repeating verbatim what the group header had just said. The member badge is therefore suppressed
where the group is coherent, and shown where the group spans — the header states the range, the
members carry the detail, exactly as `#159` rules 1 and 2 divide it. Found by looking, not by a
gate; every automated check passed on the noisy version.

**Status:** Decided (presentation). Code in this entry.

**Do not revisit unless:** provenance sectioning lands as part of (e), at which point the in-place
label is superseded by the section and this entry is absorbed rather than amended.

---

### 161. The wearable-metric invariant scopes to the verdict, not to the measurement — and capability gets a history

**Decision:** `capability_observations` is added: an append-only, per-`(region, side, measure)`
ledger of measured quantities with the date they were measured. `capability_state` is unchanged —
not widened, not read differently, not swapped. The two carry different signals. `status` is the
response-to-load **verdict**, written from adaptation response tags and self-reported through the
education idiom (spec §12). A row in the new table is a **measured quantity**. The invariant that
"nothing introduces a wearable metric" scopes to the first and not the second: `status` remains
self-reported and never device-derived, while an observation **may** carry a device value.

**Why this is a decision and not a code comment:** two places assert the invariant in prose —
`models.CapabilityState`'s docstring and `engine/__init__`'s module docstring. The GPS unit
(Catapult SPT3) is intended to feed max velocity, deceleration counts, and change-of-direction load
into this table, and those are wearable metrics by any reading. The failure mode is widening the
invariant **silently** — letting the docstrings quietly go stale while the behaviour changes under
them. Both were amended in this commit to state the split explicitly, so the narrowing is on the
record rather than inferred from what the code happens to do.

**Why a table and not a wider `capability_state`:** `capability_state` holds one row per
`(user, region, side)` and is overwritten in place by `adaptation.apply_response`. Only today's
label is ever visible; a 4-level ordinal cannot be regressed against dose; and an overwritten row
has no trajectory. Asymmetry direction-of-travel, re-attainment curves after injury, and
dose-response slopes each need history the state table structurally cannot hold. The other half was
already present — `exercise_region_tags` joins templates to regions with primary/secondary roles, so
dose-per-region is computable today. The offseason (season ends ~6 Sep 2026) is the highest-variance
window, and a table added afterwards cannot retroactively observe it.

**Append-only, and `observed_on` is the measurement date.** No `updated_at`, no UPDATE path, and a
test asserts the module exposes no update/delete/upsert function so the discipline cannot lapse
quietly. A correction is a new row; supersession resolves on read by `observed_on`, then
`created_at`, then `id`. The date split matters and is tested: a correction entered today for a
June measurement supersedes June without displacing a real July measurement — the naive
"latest row wins" would silently rewind the series.

**Sidedness is a property of the instrument, not of the region — the brief was wrong here.** The
proposing brief's §8 table assigned `deceleration_landing` and `change_of_direction` the side
`bilateral`. Both are declared `per_side=True` in `taxonomy.py`, so `Region.sides()` returns
`[left, right]` and a bilateral write would have been refused by the very fail-closed guard the
brief asked for — the seed battery would not have loaded. Resolved by moving sidedness onto
`Measure` (`per_side`), bounded by the region's `sides()` as a ceiling: a trunk-mounted GPS unit
records one deceleration figure for the athlete and cannot attribute it to a leg, even though the
region is legitimately readable per-side. This yields exactly the brief's intended table without
misdeclaring the regions.

**`measure_key` is a declared, versioned registry, not free text.** `Region.measures` carries
`Measure(key, unit, higher_is_better, per_side)`, versioned with `TAXONOMY_VERSION` like the rest of
the axis list, and writes validate against it — the same fail-closed guard `adaptation.py` applies
to `region_key`. Free text would have drifted into a synonym pile within weeks. `unit` is taken from
the declaration rather than the caller; a caller may assert a unit, and a mismatch **raises rather
than converting**, because a conversion we invented is a value we made up. Seven of thirty-one
regions are seeded. A region with no declared measure is observation-ineligible — the correct
default for an axis nobody has chosen an instrument for, not a gap.

**The boundary is enforced, not documented.** A numeric capability value sits close to the line
`injury_probes.py` exists to hold. Legal: storing a measured quantity; deriving symmetry, trend, or
dose-response slope for display. Illegal: converting any of it into a clearance, a "safe to return",
a severity grade, or a return-to-sport verdict. `symmetry()` is the sharpest edge — the
return-to-sport literature attaches a >=90% Limb Symmetry Index threshold to exactly this ratio — so
it returns the ratio, both collection dates, and which side is lower, and compares nothing to a
threshold. A regex gate over every observation read path enforces this, with negative controls
proving it bites and a positive control proving the payload was non-empty. The gate is deliberately
NOT applied to the taxonomy reference text, which legitimately quotes the >=90% figure as a
documented expectation FLAG.

**The engine already had an HTTP surface — the brief was wrong here too.** §3 stated "no capability
endpoints exist. The engine currently has no HTTP surface", and §9 accordingly placed the routes in
`main.py`. `backend/routers/engine.py` has existed with seven endpoints under `/engine`, including
`GET /engine/capability-state` and `POST /engine/response`. The two new routes went there,
alongside the verdict surface they are the counterpart to, rather than establishing a second
capability API in `main.py`.

**Status:** Decided and landed. Additive only — `capability_state`, `engine/selection.py`, and the
Probe queue are untouched, and nothing existing reads the new table.

**How you know:**
- 33 new tests in `backend/tests/test_capability_observations.py`; full suite **578 passed**, no
  regressions.
- Migration `b6f3d92a4e17` (on verified head `d7c4b1a90e35`, single head confirmed via
  `ScriptDirectory.get_heads()`) applied and reversed against a scratch SQLite database — table
  created with all three indexes and the CASCADE FK, and absent after downgrade. The full chain does
  NOT run on SQLite (pre-existing `da60d2b93599` uses Postgres-only `ALTER COLUMN ... DROP DEFAULT`),
  so the migration was exercised in isolation from a stamped parent, not via a full replay.
- ORM-model-versus-migration DDL diff run programmatically: it caught a real drift — `created_at`
  NOT NULL on the model, nullable in the migration — which was fixed, and the re-run reports no
  drift. The visual read of the DDL had missed it.
- Every §3 claim in the brief re-verified against `master` before implementing; two were false and
  are corrected above.

**Do not revisit unless:** a second writer of measured values appears (a Catapult ingest path, a
Hevy-derived measure), at which point the `source` vocabulary and the per-measure sidedness rule
are the surfaces to re-read — not the append-only rule, which is the point of the table.

---

### 162. The interpretation hub tile shows structural counts, not a priority ordering (resolves Q63)

**Decision:** Under `#150` Constraint A the interpretation tile carries Q63 candidate (a) — counts,
section structure and recency read from the existing `GET /interpretation` payload. The tile routes
to `/interpretation` and does not reproduce the interpreted synthesis (`#150` Constraint C, `#49`).
The rendered string is:

> `What Moved: 2 · Stable: 5 · collected 30 May`

**Amends the candidate as written.** Q63 (a) and the commissioning brief both said *"generated
<date>"*. That is wrong against master and is not shipped. `meta.generated_at` exists, but
`GET /interpretation` builds the payload on every request — `producer.py:560` stamps
`datetime.now(timezone.utc)` — so the field is always "now". A tile reading "generated 2 Aug" on
2 Aug and "generated 3 Aug" on 3 Aug, over an unchanged lab draw, states nothing about the user's
data and implies a stored artefact with an age. `meta.trigger_panel.collected` is the real recency:
the date of the draw being interpreted, and the date the view itself already labels "collected".
Q63's own example — "last generated 30 May" — *is* that collection date in the committed fixture, so
the candidate conflated the two rather than choosing generation deliberately.

**Rationale:** (a) is permitted and informative; (b) existence-only discards free, already-computed
structure; (c) no-tile removes a doorway the hub exists to provide. A reader inferring salience from
counts is inference from their own data, not the product ordering their problems — the line `#150`
Constraint A draws from `#47`: "3 markers out of range" is arithmetic (in), "3 need attention" is
personalised prioritisation (out).

**Status:** Decided (design + build). Resolves `Q63`. Tile built on `feat/hub-shell`, pushed and
held for review; not on master at time of writing.

**How you know:**
- The copy is a pure function (`interpretationTileCopy`), not a literal buried in JSX, so the `#47`
  boundary has one reviewable site. Evaluated through Vite's own resolver in the browser against
  the committed fixture: `What Moved: 2 · Stable: 0 · collected 30 May`; against a synthetic 2-moved
  / 5-stable payload: `What Moved: 2 · Stable: 5 · collected 30 May`. No priority phrasing in either.
- Counts come from `splitSections`, the same placement function the view uses, which CONSUMES
  `should_surface` rather than recomputing it — no second source of truth (the defect `sections.js`
  was written to close).
- The tile renders four distinct states (loading / empty-404 / error / ready); an error does not
  render as an absent or empty tile.
- **Not** a test assertion. This repo has no frontend test runner — no vitest/jest, no `test`
  script, no spec files anywhere under `frontend/src` (verified). Adding one is tooling adoption,
  not a layout job, so the artefact above is evaluation-plus-inspection and the assertion Q63's
  brief anticipated is recorded as OWED, not claimed.

**Do not revisit unless:** the producer's emitted section shape changes which counts are available
(Q62 / 4b-ii follow-ons); `#47` classification moves (its own revisit clause), which would move
Constraint A; or `/interpretation` gains a cached/stored generation, at which point `generated_at`
becomes a real recency signal and the collected-vs-generated amendment above is worth re-reading.

---
### 163. The Hevy template sync gets a call site: an operator endpoint plus a connect-time seed

**Decision:** `sync_exercise_templates` — the only writer of `hevy_exercise_templates`, the substrate
every resolver reads (`resolve_exercise`, `catalogue_titles_by_id`, `suggest_candidates`,
`resolve_custom_exercise`) — is wired to two call sites in `backend/routers/integrations.py`:

- **`POST /integrations/hevy/sync`** — operator trigger, `get_current_user` auth, scoped to the caller
  via `only_user_id=current_user.id`. Returns the summary verbatim.
- **`connect_hevy` (`POST /integrations/hevy`)** — now `async def`; after the key's `db.commit()` it
  calls the **same** path, so the catalogue is seeded at the moment a key first exists.

**Rationale:** the sync had no call site at all. It was reachable only from the module `__main__` and
the `sync_hevy_templates.py` CLI, both operator-invoked from a shell. `FEEDBACK` §8 (`#77`) records
what that cost: three landed features — the resolver (`#60`/`#61`), `create_and_resolve` (`#65`), and
the taxonomy tagging effort (`#74`–`#76`) — were structurally inert in prod on a zero-row table, all
green locally. The CLI run of 2026-07-14 populated it once by hand; nothing in the *application* has
ever populated it, so a fresh key, a new user, or a wiped table leaves every title→id resolution
missing and would make a future custom-create path mint duplicates against an empty idempotency
check. A sync reachable only from a shell is a sync that runs when someone remembers.

**The connect-time seed is where the substrate stops being optional.** A key and an empty catalogue is
not a half-connected integration — it is a connected integration whose reads all miss. Ordering is
load-bearing: the seed runs **after** the commit, because the committed `UserIntegration` row is what
makes the key visible to `users_with_hevy_key`, which the sync reads. One sync path serves both call
sites, so there are not two sets of sync semantics to reason about.

**A seed failure does not fail the key store, and is not swallowed either.** Storing the key is the
request's contract and still returns 201. But the response body gains `sync`, carrying the summary
(whose `users_failed` / `rows_processed` expose a partial run) or, if the call raised outright, a
failure shape. Swallowing it would reproduce the §8 blind spot precisely: a 201 that reads as a
working integration over an empty catalogue. Additive to the response, so no caller breaks.

**The failure signal is mapped to HTTP, never returned as a 200 with a zero.** `hevy_templates`
documents `users_synced == 0` as a first-class failure signal, and with `only_user_id` set there is
exactly one user in scope, so a zero is *this* user's failure and never a family-wide partial.
`_sync_failure` splits the two shapes: `users_attempted == 0` is a 404 carrying the identical body
`_require_integration` produces (`"hevy integration not connected"`), so a keyless caller reads the
same whichever Hevy route it hits; `users_failed >= 1` routes the recorded error through the existing
`_hevy_error_to_http` choke point.

**The recorded error is a string, so the type is rehydrated.** `sync_exercise_templates` consumes the
exception inside its per-user isolation wrapper and keeps only `f"{type(exc).__name__}: {exc}"`.
Passing that text to `_hevy_error_to_http` as a bare `Exception` would flatten a revoked Hevy key to
502 and quietly undo `#66`'s 401→424 decoupling — the whole point of which is that a dead *connector*
key must not log the user out of the app. `_SYNC_ERROR_TYPES` rehydrates the two types whose mapping
is not the 502 default (`HevyAuthError`, `HevyForbiddenError`); everything else maps to 502 either
way, so the registry stops there rather than growing a case per exception.

**Status:** Decided; code landed on `feat/hevy-template-sync-wiring`, pushed, **not merged**. The prod
population gate is **OWED** and is the reason: the route cannot be exercised in prod until the branch
deploys (see *How you know*). No migration, no schema change. `hevy_templates.py` is untouched — the
summary contract, the per-user isolation, and the CLI all keep their existing behaviour. The routine
contract, `context_builder`, and `chat.py`'s block parser are out of scope and unedited; custom-
exercise creation (`<hevy_create_exercise>`) is a separate step that depends on this one.

**How you know:**
- 16 new tests in `backend/tests/test_hevy_sync_wiring.py`; full backend suite **594 passed** (baseline
  on `master` before the branch: **578**).
- The tests drive the **routes** over a standalone `FastAPI` app with `get_db` / `get_current_user`
  overridden — not the handler objects — because the defect being fixed is exactly "the function
  exists and nothing reaches it". A handler-object call would prove the body and skip the wiring.
- **Paired negative controls** (`FEEDBACK` §17, `#103`): renaming the route to `/hevy/sync-UNWIRED`
  fails 6 of 16 and passes the 10 that do not touch that path; replacing the connect-time seed call
  with a literal fails the 4 connect tests and passes the other 12. Each control fails exactly the
  half it should, so neither half is being carried by the other. The 404 assertion checks the
  **detail string**, not just the code, so an unregistered route (which also 404s) cannot pass it.
- Prod population gate, paired against the Railway database — **BEFORE recorded, AFTER owed.**
  `hevy_exercise_templates` = **494** rows (451 default, 43 custom), `max(synced_at)` =
  **2026-07-14 12:09:06+00** — i.e. still the one-off CLI run of that date; three `user_integrations`
  rows carry `provider='hevy'`. Queried via `railway run --service health-app-DB` over
  `DATABASE_PUBLIC_URL` (`#56`), printing counts only, never a credential (`#111`).
  The AFTER half cannot be taken this session: the deployed backend's `openapi.json` lists five
  `/integrations/hevy*` paths and **not** `/integrations/hevy/sync`, so the route does not exist in
  prod until this branch merges and Railway redeploys. Verified by probe, not assumed. Per the brief
  the gate is therefore **not claimed**.
- **The delta is not the signal on an already-populated table** — worth recording, because a naive
  read of the paired control would call a zero delta a failure. The sync is upsert-only (`#77`: the
  Hevy API cannot delete templates), so on a healthy prod the after-count is expected to *equal* 494,
  not exceed it. The load-bearing after-signals are `defaults_seen > 0` in the returned summary and
  `max(synced_at)` advancing off 2026-07-14. A rising count would mean new templates existed
  upstream; an unchanged count with a fresh `synced_at` is the success case.

**Amendment 2026-08-03 — the prod population gate is CLOSED.** *(Appended, not rewritten: the two
bullets above record what was true at authoring and stay as written. The entry is locked; this
extends its evidence, it does not revise the decision.)* The branch ff-merged at `9c8176a`; the
`health-app-backend` deploy `34cda96f` reported SUCCESS (`#116`, timing); the live `openapi.json`
gained `/integrations/hevy/sync`, six `/integrations/hevy*` paths where there were five (`#121`,
coverage); unauthenticated `POST /integrations/hevy/sync` returned **401** against **404** for a
nonexistent sibling path — a control discriminating on identity, so the 401 proves registered-and-
gated rather than absent. Luke then ran the authenticated POST.

AFTER: **499 rows (451 default / 48 custom)**, `max(synced_at)` **2026-08-02 21:59:50+00** — which
is 07:59 on 2026-08-03 AEST; the column is UTC, so the date reads a day behind local and is not
stale. The prediction above held exactly: the default count did **not** move (upsert-only), and the
+5 delta is five real customs added in the Hevy client since July.

`defaults_seen > 0` was confirmed in **durable DB form** rather than read off the response body:
`synced_at` is stamped per row on upsert, so a run that had read only customs would leave the
default rows carrying the July timestamp. **451 default rows carry the new timestamp and ZERO rows
remain stale.** This is the stronger artifact — it does not depend on anyone having captured the
summary at the moment of the call, and it distinguishes "the sync ran and read the whole catalogue"
from "the sync ran" in a way the row count alone cannot.

**Do not revisit unless:** a recurring/scheduled sync is built (`Q75` — cron vs. staleness-on-read
vs. sync-on-workout-fetch), at which point the shared path this decision establishes is the surface
to hang it on rather than a third call site; or `sync_exercise_templates` changes its summary contract,
which is what `_sync_failure` and `_SYNC_ERROR_TYPES` read.

---

### 164. Custom-exercise creation is an explicit, separately-confirmed block — never a repair for a resolve miss

**Decision:** `create_and_resolve` (`#65`) gets a model-facing call site. `chat.py` parses a new
`<hevy_create_exercise>` block via `_process_exercise_actions`, and `context_builder` gains
`_section_exercise_creation` — the contract, gated on a connected Hevy. Creation stays a **separate,
separately-confirmed act**: `_resolve_missing_ids` is unchanged and still only refuses on a miss.

**Rationale — the asymmetry that shapes everything here is permanence.** Hevy has no API to delete
or edit an exercise template. A routine created wrongly is deleted in the app in two taps; a custom
exercise created wrongly is in the user's picker forever, and so is a typo in its title. Every
design call below falls out of that.

**Auto-create on a resolve miss is the tempting fix and is rejected.** `_resolve_missing_ids`
already knows the title did not resolve, and minting it there would close the loop in one turn with
no new idiom. It would also turn **every typo into a permanent record** — `Bulgairan Split Squat`
becomes a real template the moment the model misspells it. A resolve miss is far more often a
naming mismatch against an exercise Hevy already has (which is why `#83` returns ranked candidates)
than a genuine absence. The one-turn saving is not worth trading a recoverable miss for an
unrecoverable write, so the miss stays loud and the create stays explicit. Guarded by test, not
just by intent: `test_resolve_miss_refuses_and_creates_nothing`.

**Ordering at the call site is load-bearing, not stylistic.** Exercise blocks are processed **before**
routine blocks. The model cannot cite a server-minted UUID it has never seen, so a same-turn routine
must reference the new exercise by TITLE — and `_resolve_missing_ids` finds it only if the create
and its list-back sync have already run. Reverse the two and a same-turn create-then-use fails an
unresolved-title miss on an exercise created seconds earlier in the same reply.

**Idempotency is re-checked in the processor, not left to the orchestrator.** `create_and_resolve`
short-circuits an existing title by returning its id — which is indistinguishable at the chat layer
from a fresh create. Reporting `✓ … created in Hevy` for something that already existed would be a
false confirmation about an irreversible act, so the processor resolves first and reports
`already in the exercise catalogue — nothing created`. The orchestrator's own pre-check remains as
defence; this one exists so the *confirmation can tell the truth*.

**`HevyCreateUnresolvedError` forbids a retry rather than merely reporting.** That error means the
POST may well have succeeded and only the list-back failed. The naive next move — try again — is
exactly how a delete-less API ends up with two identically-named permanent templates. The message
says so explicitly.

**Status:** Decided and landed on `feat/hevy-create-exercise-block`. `hevy_templates.py` and
`connectors/hevy.py` are untouched — the orchestrator and connector already existed and were tested
(`#65`). The routine idiom's resolution logic is unchanged. No migration.

**How you know:**

*The enum artifact.* The repo has no enum authority — the connector passes strings through and a
bad one returns 400 — so the contract's values are quoted from **Hevy's live OpenAPI spec**, read
2026-08-03. The spec is not served at `/openapi.json` (404), and `/docs/*` returns the Swagger UI
HTML for **any** path, including invented ones: `/docs/spec.json` and `/docs/v1/openapi.json` both
answer 200 with HTML, so a status-code check alone would have "found" a spec that does not exist.
The document is embedded in `api.hevyapp.com/docs/swagger-ui-init.js` as `swaggerDoc`
(`openapi 3.0.0`, `Hevy API Docs`, 28 schemas), and `CreateCustomExerciseRequestBody` confirms the
wrapped `{"exercise": {…}}` body `#65` recorded. Captured verbatim:

- **`CustomExerciseType` (8):** `weight_reps`, `reps_only`, `bodyweight_reps`,
  `bodyweight_assisted_reps`, `duration`, `weight_duration`, `distance_duration`,
  `short_distance_weight`
- **`EquipmentCategory` (9):** `none`, `barbell`, `dumbbell`, `kettlebell`, `machine`, `plate`,
  `resistance_band`, `suspension`, `other`
- **`MuscleGroup` (20):** `abdominals`, `shoulders`, `biceps`, `triceps`, `forearms`, `quadriceps`,
  `hamstrings`, `calves`, `glutes`, `abductors`, `adductors`, `lats`, `upper_back`, `traps`,
  `lower_back`, `chest`, `cardio`, `neck`, `full_body`, `other`

*The cross-check, which found a real trap.* The brief asked for `hevy exercises --json`; that CLI is
not on this machine, so the cross-check ran against the **synced catalogue itself** — 499 rows of
the same account's real data, refreshed by `#163`'s sync hours earlier. `MuscleGroup` matches
perfectly in both directions: all 20 spec values occur in `primary_muscle_group`, and nothing occurs
that the spec lacks. `CustomExerciseType` **does not**, vindicating `#65`'s warning that the create
enums differ from the values seen elsewhere:

- Present in the live catalogue's `type` but **invalid for creation**: `bodyweight_assisted`,
  `bodyweight_weighted`, `floors_duration`, `steps_duration`
- Valid for creation but never observed: `bodyweight_assisted_reps`, `bodyweight_reps`,
  `weight_duration`

The dangerous pair is `bodyweight_assisted` (GET) versus `bodyweight_assisted_reps` (CREATE) — near
enough that copying a type off the workout history reads as correct and returns a 400. The spec
confirms the divergence is structural rather than an artifact of this account:
`ExerciseTemplate.type` is typed as a bare `string` with no enum, while creation constrains it to
`CustomExerciseType`. Both schemas *do* share `EquipmentCategory`, which is also why that one field
could not be cross-checked against the catalogue — the sync does not persist `equipment_category`.
It is recorded as spec-only, uncross-checked. The contract names the four GET-only values as
invalid, and a test pins each.

*Tests.* 61 new in `backend/tests/test_hevy_create_exercise_block.py`; full suite **655 passed**
(baseline **594** at `#163`).

- The ordering gate drives the **real call-site sequence**, not the processors in isolation, and is
  paired with a control (`test_reversed_order_would_fail_to_resolve`) pinning what reversing them
  would cost — so the requirement is held by a passing test, not only by a comment.
- **Paired mutation control:** renaming the block tag to `<hevy_MUTATED_tag>` fails **13 of 61**,
  and the 13 are exactly the tests that drive a block through the processor. The 48 that survive are
  the contract-text tests, the non-goal guards (routine path), the no-block no-op, and the
  reversed-order control — none of which parse an exercise block. Read as names, not counted
  (`#113`).
- A **regression the mutation run surfaced**: adding the section broke
  `test_context_builder_output_unchanged_pre_post_refactor`. That guard compares against a frozen
  pre-`#43` builder with `connected_integrations=[]`, where the new section correctly renders `""` —
  but the extra list separator alone shifted the whitespace. Fixed by giving both Hevy authoring
  contracts **one** section slot that collapses to `""` when Hevy is absent, so the list is
  byte-identical when the guard runs. The guard itself was neither touched nor narrowed.

*What is NOT proven.* No live create was performed this session — the deferral and its watch-point
are recorded as an open question below.

**Do not revisit unless:** Hevy ships a delete or edit endpoint for exercise templates, which
removes the permanence premise every call above rests on and would make auto-create-on-miss worth
re-arguing; or the enum lists drift (`Q76`).

---

### 165. Titration becomes a perpetual 4-night hunting search; the block no longer auto-closes; the dither centre is the sleep-need estimate

**Decision:** The titration cadence drops to a 4-night cycle with 15-minute steps; the plateau `close`
is removed — a converged cycle HOLDs and the block stays open indefinitely, accumulating while the
operator still logs, so a later drift is visible with its cause rather than a silent reset. The
reported sleep-need estimate is the running centre (mean of the last `CENTRE_CYCLES` prescribed
windows), not any single cycle's window. Constants: `CYCLE_NIGHTS` 4, `MIN_VALID_NIGHTS` 3,
`MAX_MOVE_MIN` 15, `ADHERENCE_FAIL_N` 2, `CENTRE_CYCLES` 4 — all operator-chosen, CHOSEN-not-derived
(Q55).

**Rationale:** The SRT literature has never studied titration interval as a variable (Q48 — its named
failure mode is *under*-titration), so a fast small-step dither finds the setpoint empirically while
staying usable, and the small step makes 4-night noise inconsequential (±15 cannot move the window
far; the centre averages it out). Compress-on-fragmentation is already inherent
(`window = mean_tst + buffer`: broken sleep → lower TST → lower target → compress), so no new logic is
added for it. Adopted engagement-first: a weekly cadence the operator ignores has zero value (#118's
own "revisit if adherence becomes the binding constraint").

`MIN_VALID_NIGHTS` is the one constant that is **forced, not chosen**: a sufficiency threshold of 5
cannot be met inside a 4-night cycle, so leaving it would make GATE 1 unsatisfiable and the engine
would HOLD forever — a stall that reads as "titration is broken", not as a bad constant. The invariant
`MIN_VALID_NIGHTS < CYCLE_NIGHTS` is now asserted at import rather than left to review.

**Evidence context (honest):** no source supports 4 nights specifically; it is a pragmatic operator
choice, not a validated constant. The dither generates exactly the SE-recovery data Q48's curve-fit
would need, so it advances Q48 rather than pre-empting it. CBT-I/SRT consolidates sleep and reduces
fragmentation; it does not manufacture total sleep time (van Straten 2017: TST the smallest effect,
g≈0.16, against SE 0.71; Scott 2022) — the surface therefore frames titration as one deep-sleep lever
among five, evidence-ranked and identical for every reader, never connected to a personalised action
(#47, #150 Constraint A).

**Correction to the brief — there was no engine-close to remove.** The brief framed this as removing
the engine-driven block close that #118 established. Enumerated against master before editing: nothing
writes `cbti_blocks.closed_on` from an engine decision. The only `closed_on` writers are
`import_cbti_block.py` (the historical block-1 import) and a read in `correct_cbti_block3_rx.py`; the
engine's `close` was consumed **only** by `replay.py`'s advisory #107 exit-too-early report and by
tests. So #118's "close is engine-driven" half was specified and never built, and what this decision
actually removes is a *recommendation*, not a mechanism. `close` is retained in the `Decision`
vocabulary and the DB CHECK constraint — block 1 was imported carrying it and the ledger is
append-only, so retiring the value would invalidate history. The engine simply never emits it again.

**Status:** Decided (design + build). Supersedes `#107`'s weekly cadence and its plateau exit; retunes
`#118`/`#128`. Advances Q48 (cadence adopted pragmatically). Q55's cadence constants now carry a
recorded rationale (still chosen-not-derived). Q45 unchanged — exclude-all stands, over-exclusion is
now surfaced rather than silent.

**How you know:**
- Backend suite **674 passed** (655 baseline **+19**); `test_cbti_replay.py` green, with every changed
  replay decision traced to an intended constant: the 3-night stub moves `insufficient hold → extend`
  (`MIN_VALID_NIGHTS` 5→3), a 7-night span splits 1→2 cycles (`CYCLE_NIGHTS` 7→4), moves cap at 15,
  and the plateau becomes a converged HOLD. Nothing flipped for another reason.
- The block stays open past a plateau: on 28 flat nights the walk yields 7 cycles, cycles 3–7 all
  `hold`/`converged`, and no cycle anywhere emits `close` (asserted parametrically across five
  `prior_basis_tst` shapes and four TST/SE combinations).
- Worked centre: windows `[405, 420, 435, 420]` → **420 min**; a pure ±15 dither
  `[405, 435, 405, 435]` → **420** while the latest window reads 435 — probe and estimate are
  demonstrably different numbers.
- Nap guard on a synthetic 4-night cycle with 2 nap nights:
  `insufficient_nights: 2 valid of 4, need 3 (2 excluded: nap x2)`.
- Frontend `npm run build` clean, eslint at the 5-error master baseline. **No frontend test runner
  exists**, so the lever content and centre copy are extracted to pure modules
  (`leverContent.js`, `centreCopy.js`) and evaluated in node; the assertions are recorded OWED, not
  faked.
- **NOT verified against prod, and not deployed** — the branch is held for review. Both `#121` deploy
  probes are owed.

**Do not revisit unless:** block-3 data or a clinician establishes a derived cadence/threshold (Q48's
curve); or the dither fails to converge — a wandering centre means the extend/compress boundary is
biased, first suspects being the Q45 nap exclusion (SE reads high) or the `SE_FLOOR_PCT` threshold.

---

### 166. The create-response body is not load-bearing — a 2xx must never abort before list-back (patches `#65`/`#164`)

**Decision:** `HevyClient.create_exercise_template` no longer raises on an unparseable
**success** body. On a 2xx it attempts `.json()`, and on `json.JSONDecodeError` it logs the
status and the raw bytes and returns `{}`. The typed pre-checks (403 limit, 400 bad body)
and `_check`'s 401/4xx/5xx raises are untouched — this changes the success path only, and is
deliberately **not** generalised to the other `.json()` call sites, where the body *is* the
payload and tolerating a bad parse would convert a real failure into silent empty data.

**Rationale — the throw was destructive, not cosmetic.** The old line was
`return self._check(r).json()`. By the time it runs, the status is necessarily 2xx: 401 and
every `is_error` status die inside `_check`, and the 403/400 branches pre-empt it above. So
**Hevy has already created the template** when the parse fails. `json.JSONDecodeError` is
not one of the typed connector errors, so it unwound out of `create_and_resolve` before
steps 4–5 (sync + list-back) ever ran, and surfaced through `_process_exercise_actions`'s
catch-all as `⚠️ Failed to create custom exercise`.

The resulting state was the worst available combination: the template **live in Hevy**,
**absent from `hevy_exercise_templates`**, and the user told it had failed. Against an API
with no delete, a user who believes that message and retries mints a permanent duplicate.
The only reason no duplicate exists is that Luke checked Hevy and declined to retry.

**The body was never needed.** `create_and_resolve` discards the return of
`create_exercise_template` entirely and reads the canonical id by list-back — precisely
because `#65` established that the POST returns an integer id distinct from the canonical
string UUID. So the parse that broke the flow was decoding a value nothing consumes. That
asymmetry is the whole decision: a value no caller reads must not be able to abort a
sequence that has already had an irreversible side effect.

**Why `#164`'s 61 tests passed over a live-broken path.** Every one of them fakes either
the client or the orchestrator, so each fake returned clean JSON and the real parse never
executed. A fake installed one layer *above* a defect cannot see it. The new tests fake the
**transport** (`httpx.AsyncClient.post`) and drive the genuine `HevyClient`, so the parse
runs. That is the structural lesson, and it generalises past this bug.

**Status:** Decided and landed on `fix/hevy-create-response-parse`. One-function change plus
tests; no migration, no schema change. `create_and_resolve` needed **no new control flow** —
with the connector no longer throwing, the "a 2xx always reaches list-back" invariant holds
automatically, so it is pinned by test rather than defended by a second guard. The trace was
re-verified against master before changing anything; no other abort point exists between the
POST and the sync.

**How you know:**

- **The prod failure is identity-level, not inferred.** A live attempt created
  `Copenhagen Adductor Plank Hip Lift` (Custom · None · Adductors · Glutes) in Luke's Hevy
  account — visible in-app, screenshotted — while chat returned the failure message. The
  raised error was `json.JSONDecodeError: Extra data: line 1 column 4 (char 3)`.
- **What that error string constrains, stated as inference rather than fact:** the body's
  first three characters form a *complete* JSON document and are followed by further
  non-whitespace content. It is therefore neither the spec's `{"id": <int>}` (which parses
  cleanly) nor a bare integer (likewise). **The exact bytes are OWED** — see below.
- **Trace verified against master**, not taken from the brief: `connectors/hevy.py`
  `create_exercise_template` ended at `return self._check(r).json()`; `_check` raises on 401
  and on `response.is_error` and otherwise returns the response, with `.json()` called
  *outside* it; `create_and_resolve` wraps the POST in no handler; `chat.py`'s catch-all
  produces the observed message.
- **16 new tests** in `backend/tests/test_hevy_create_response_tolerance.py`; full suite
  **690 passed** (master baseline **674** — note this is *not* the brief's 655, which
  predates `#165`).
- **Paired negative control:** reverting the connector to `return self._check(r).json()`
  fails **11 of 16**. The 5 survivors are exactly the tests that must pass either way — the
  403/400/500/401 typed-error paths and the well-formed-body positive control — so the
  control discriminates the tolerance from the error handling rather than merely proving the
  file is reachable.
- The regression is asserted on the **real captured error shape** (`'123{"id":123}'`,
  constructed to raise the identical `Extra data: line 1 column 4 (char 3)`), and separately
  across five other unparseable bodies, so the fix is not keyed to one byte sequence in an
  endpoint whose true shape is still unknown.

**OWED, not claimed:**

1. **The live response bytes.** The `logger.warning` added here captures `status_code` and
   the raw body on the next real create; a test asserts the bytes reach the log. Capturing
   them requires a genuine create, which mints a permanent template — Luke's call, and it
   needs a *fresh* movement name, since re-attempting the orphan's title now correctly
   short-circuits to "already in the catalogue" and would prove nothing.
2. **Prod recovery of the existing orphan.** Confirmed absent from the catalogue
   (`hevy_exercise_templates` = 499 rows, `max(synced_at)` still 2026-08-02 21:59:50+00; a
   title search matches only the pre-existing `Copenhagen Plank (Short Lever)`). One
   `POST /integrations/hevy/sync` upserts it in — no delete, no re-create. Code cannot run
   it: the endpoint needs a session token, and `railway ssh` (the in-container alternative)
   is blocked by this environment's permission policy. Expect 499 → 500 and customs 48 → 49.
3. **`Q77` therefore stays OWED rather than resolved** — see its entry. This decision fixes
   the defect the watch-point exposed; it does not prove the round-trip.

**Do not revisit unless:** Hevy's create endpoint starts returning a documented, stable body
that a caller actually needs, at which point the tolerance should be narrowed to the specific
shape rather than left permissive; or `create_and_resolve` begins consuming the create
response, which would make the body load-bearing and invalidate the premise above.

---

### 167. Number-at-merge is enforced by a pre-push ref guard, not by remembering

**Decision:** `scripts/check_governance_placeholders.py` refuses any push to `master` whose
`DECISIONS_LOG.md` still carries `^### #NEXT` or whose `OPEN_QUESTIONS.md` still carries
`^## Q#NEXT`, wired as a repo-versioned `.githooks/pre-push` hook (`git config core.hooksPath
.githooks`, once per clone, alongside the existing `land`/`stale` aliases). Branch pushes are
untouched. The rule is added to the shared loop block, so it propagates verbatim to
`health-connect-app`.

**Rationale:** number-at-merge specified when the integer is claimed and nothing enforced it. The
placeholder reached master and stayed: `feat/hub-shell` fast-forwarded with its heading still
reading `#NEXT`, `#163` and `#164` were minted on top, and `#162` became a hole in the canonical
store. It survived three sessions because the fix kept being written on branches that did not merge
— the defect and its cure were never on master at the same time. A rule that depends on the person
merging remembering it has now failed three times; the correct response is to move it out of memory.

**The guard is on the REF, not on `git land`.** This is the load-bearing design choice and it was
settled by evidence, not preference: the merge that finally healed `#162` was done by hand —
`git checkout master && git merge --ff-only && git push` — so a guard living inside the `land` alias
would not have fired for it. The placeholder reaches master by whichever path is convenient that
day, so the check belongs where master actually changes.

**Anchored on the heading, never a substring (`#113`).** `CLAUDE.md`'s own rule text, `#148`'s
entry, and every corrected entry legitimately quote the token — a substring match would fire on the
files that define the convention, get bypassed out of habit, and protect nothing. A guard that cries
wolf is worse than no guard, because it manufactures the habit that defeats it.

**Fails loud in all three states.** Clean → 0. Placeholder present → 1, printing every offending
file and line so the matches are read rather than counted. Cannot run (missing file, bad ref) → 2:
a check that could not run must never be indistinguishable from a check that passed.

**Status:** Decided and built on `gov/next-resolution-guard`. **Shared-block change** — the
`health-connect-app` copy must be updated byte-identically; recorded as cross-repo debt in `ROADMAP`
NOW, and it cannot be written from a health-app-rooted session.

**How you know:**
- 10 tests (`test_governance_placeholder_guard.py`), full suite green.
- **Positive control is the real defect, not a fixture:** run against `001df4c` — the actual
  `feat/hub-shell` merge commit that put a live `### #NEXT` on master — the guard exits 1 and names
  `DECISIONS_LOG.md:5833`. Against `4b247f4` it catches both arms (`### #NEXT` and `## Q#NEXT`).
- **Negative control:** current `origin/master` exits 0, and the false-positive cases are asserted
  explicitly — the `CLAUDE.md` rule line that contains the literal token, a correction quoting the
  superseded token, and a mid-line occurrence all fail to match.
- **Cannot-run control:** an invalid ref exits 2 with `cannot read`, never 0.
- End-to-end through the hook itself with crafted stdin: a `refs/heads/master` push of a placeholder
  ref is refused; the same ref pushed to a branch ref is allowed.

**Do not revisit unless:** the placeholder tokens themselves change form (then the patterns move
with them), or a second enforcement point is wanted for the `@claude` GitHub Action path — which
pushes without a local hook and is therefore **not** covered by this guard. That gap is known and
recorded rather than papered over: the Action is not currently a merge-to-master path, and closing
it would mean a CI check, not a hook.

---

### 168. The model is shown the whole exercise catalogue — the capability shipped in `#61`, it was simply never surfaced

**Decision:** `build_system_prompt` gains an `exercise_catalogue` parameter rendered by
`_section_exercise_catalogue`, listing every catalogue title visible to the user — all Hevy
built-ins plus their own customs, each flagged. `hevy_templates.catalogue_titles` is the
read. Both authoring contracts (`_section_routine_creation`,
`_section_exercise_creation`) are corrected to state that resolution covers the whole
catalogue and not merely logged history.

**No new backend capability.** The catalogue has been synced since `#61` and
`resolve_exercise` / `suggest_candidates` have always run over all of it. This exposes what
existed.

**Rationale — the model was reasoning from the only exercise data it could see.** Asked in
prod whether Nordics were in the Hevy catalogue, it answered that it could confirm only
exercises appearing in the workout history, that it could not see Hevy's built-in
catalogue, and offered to fix this by "pulling the Hevy exercise catalogue endpoint" —
i.e. by building `#61`, live since July over 500 rows. Both claims were false about the
system, and neither was the model's fault: the prompt handed it ten recent workouts and
nothing else, so ten workouts is what it reasoned from. A capability the model cannot see
is, from the user's side, a capability that does not exist — and worse than absent, because
the app then volunteers to rebuild it.

**The full list, not a lookup block.** A `<hevy_lookup_exercise>` block would have cost a
round trip per question and needed its own processor and contract; a same-turn inject
mirroring the on-ask lab relay would have needed exercise-phrase detection in free text —
a fuzzy matcher whose misses are silent. The whole catalogue is ~11,400 characters
(**measured**, not estimated: 2,839 tokens by the chars/4 rule, 500 rows) rebuilt every turn, so
it is never stale and there is no invalidation to reason about. For a single-user build
that is the cheap end of the trade, and it removes the error class at the root rather than
adding a mechanism the model must remember to invoke.

**Where the read lives is not a style question — the brief's design would have broken an
invariant.** The brief specified `_section_exercise_catalogue(db, user_id, connected)`.
`context_builder` is a **pure formatter**: it takes no `Session` and performs no queries,
which is the invariant the `#43` parity guard exists to protect and which
`_annotate_canonical_titles` documents in `chat.py` as the reason IT runs upstream. Passing
a `Session` in would have put a query inside the one module contracted to hold none. So the
read happens in `chat.py` beside the other Hevy context gathering, and the section receives
already-read rows — the same shape as `hevy_data`, `knowledge_entries` and every other
section. A test asserts the signature takes `catalogue` and nothing else, and a second
greps the module for `sqlalchemy` / `db.query(` / `db.execute(` / `SessionLocal`, so the
invariant is guarded at module level rather than by memory.

**Scope of the list is `_visible_to`, the resolver's own predicate.** Not a fresh query with
similar intent — the same one `resolve_exercise` and `suggest_candidates` use. A catalogue
shown to the model that differed from the catalogue the resolver resolves over would invite
it to emit a title the resolver then refuses: the instrument disagreeing with the behaviour
it serves (`FEEDBACK` §10). One rule, now shared three ways.

**Status:** Decided and landed on `feat/chat-catalogue-visibility`. Chat-layer only. The
sync (`#61`), `resolve_exercise` / `suggest_candidates` / `catalogue_titles_by_id`, the
create path (`#164`/`#166`) and the `hevy_exercise_templates` schema are untouched. No
migration.

**How you know:**

- **The live catalogue answers the question that prompted this.** Queried against Railway:
  `Nordic Hamstrings Curls` is present as a **default**. Note the exact title — *Hamstrings*
  and *Curls*, both plural — which is not what anyone would type from memory, and is
  precisely why the list is injected rather than left to recall. `Glute Ham Raise` is also a
  default; `Prone Hamstring Curl` is one of the user's customs. So the honest answer to
  "are nordics in the hevy catalogue?" is *yes, as a built-in*, and the app can now say so.
- **Payload measured, not estimated:** 500 visible rows (451 default / 49 custom) render to
  11,356 characters ≈ 2,839 tokens per turn.
- **14 of the 500 live titles are non-ASCII** — the U+2011 non-breaking hyphen family
  (`Single‑Leg RDL`, `B‑Stance RDL`). They look ordinary and fail a byte-exact resolve if
  retyped, so the section instructs the model to copy from the list rather than type from
  memory, and a test pins that a non-ASCII title renders verbatim rather than normalised.
- **19 new tests** in `backend/tests/test_chat_catalogue_visibility.py`; full suite
  **719 passed** (baseline **700**).
- **Mutation control:** unwiring the section from `build_system_prompt` fails exactly **2 of
  19** — the two end-to-end prompt assertions — while the 17 that call the section directly
  still pass. The control discriminates the *wiring* from the *rendering*, which is the half
  that was broken here: the renderer never existed, but the failure mode being fixed is
  "the data never reaches the model".
- **Parity guard untouched.** The section is appended conditionally, so with no catalogue
  nothing is added at all and the section list stays byte-identical under
  `test_context_builder_output_unchanged_pre_post_refactor` — no empty-string-plus-separator
  and no narrowing of the guard.

**Do not revisit unless:** the catalogue grows past the point where a few thousand tokens a
turn is no longer trivial (a multi-user build, or Hevy expanding the default set several
fold), at which point the model-initiated lookup block described above becomes the live option; or a
second consumer needs the same list, which would make `catalogue_titles`' scope predicate
worth asserting rather than merely shared.

---

### 169. The `#167` guard was written for one repo's heading grammar; generalised before propagation, not after

**Decision:** the placeholder patterns in `scripts/check_governance_placeholders.py` tolerate the
heading **level** (`^#{2,3}`) while still pinning the heading **form**, and the shared-block
session-open sweep becomes `^### #?[0-9]+` — sigil-agnostic as well as period-agnostic. Both changes
land in `health-app` **before** anything is copied to `health-connect-app`, because the script is one
implementation of one rule and fixing it in the copy would mint a second master one layer beneath the
shared block. Extends `#167`; supersedes nothing.

**The defect, stated exactly.** Two arms, both verified against both trees on 2026-08-04:

- **Session-open sweep — a false max, reported as fact.** The shared block instructs Code to count
  `^### [0-9]+`. `health-app` heads an entry `### 166.`; `health-connect-app` heads it
  `### #21 — …  ·  active`. `grep -cE '^### [0-9]+' DECISIONS_LOG.md` returns **168** in `health-app`
  and **0** in `health-connect-app`. A shared-block rule that reports a max of zero in one of the two
  repos it governs is not a stale number — it is an instrument that reads empty and says so
  confidently, at the exact moment of the session whose whole purpose is to establish canon.
- **Guard question arm — a false green.** `CHECKS` pinned `^## Q#NEXT`. `health-app` heads a question
  `## Q77.`; `health-connect-app` heads it `### Q8 — …  ·  OWED`. Copied unchanged, the question arm
  can never fire in `health-connect-app`: installed, green, and blind. The decision arm was already
  safe — both repos head a decision `### `, and the placeholder token is `### #NEXT` in both — so
  exactly one of the two arms was broken, which is the shape most likely to be missed.
- **Session-open question arm — absent, and filled in by analogy.** Caught on challenge before the ff.
  The ritual named the `DECISIONS_LOG` max and **no question max at all**, so anyone reporting one
  reached for the shape of the arm that was there and produced `^## Q[0-9]+` — **78** in `health-app`,
  **0** in `health-connect-app`. Nothing was broken here; something was *missing*, and a missing arm
  in a rule that has a sibling arm is not neutral — it is a template. The bullet now names both arms
  explicitly, with `^#{2,3} Q[0-9]+`. The generalisable part is that the two prior arms were found by
  looking for a pinned pattern; this one was only found by asking *what does the rule not say*.

**The trap was real; its location was not where the brief put it.** The chat brief predicted the
break in the guard's *integer* anchor, reasoning that `^### [0-9]+` would not match `### #16 —`. The
guard has no integer anchor — it matches the literal placeholder token and never computes a max. The
`^### [0-9]+` the brief was reaching for is in the **session-open ritual**, a different bullet of the
same shared block, and there the prediction is correct and worse than predicted: not a guard that
fails to fire but a count that returns zero. Recorded because the near-miss is the lesson — a
correctly-reasoned failure mode aimed at the wrong artefact still has to be re-derived against the
tree before it can be believed or dismissed, and dismissing it on "the brief was wrong about the
script" would have shipped the propagation with the real hole intact.

**Tolerate the level, never the form.** `{2,3}` is not a loosening toward substring matching — the
token must still open a heading, so `#113`'s false-positive shapes (the rule text quoting the token,
a correction quoting what it superseded, a mid-line occurrence) remain non-matches and are still
asserted. The decision arm is generalised alongside the question arm despite not needing it today, so
the two cannot drift into disagreeing about what a heading is.

**How you know:**
- **Positive control, the real defect and not a fixture** — `001df4c`, the `feat/hub-shell` merge that
  put a live `### #NEXT` on master, still exits **1** and names the line post-change; `4b247f4` still
  catches **both** arms. A widened pattern that lost the original control would be a regression, not a
  generalisation.
- **Negative controls** — clean working tree **0**, `master` **0**, unreadable ref **2** (never 0).
- **Cross-repo cases pinned in tests** — a `### Q#NEXT — …  ·  OPEN` question heading and a
  `### #NEXT — …  ·  active` decision heading both fire; the resolved `health-connect-app` forms
  (`### #21 — …`, `### Q8 — …`) do not. **3 new tests**; suite **722 passed**.
- **Hook end-to-end, crafted stdin, all four paths** — master push carrying the placeholder
  **REFUSED (1)**; the same ref pushed to a branch **ALLOWED (0)**; clean master **ALLOWED (0)**;
  zero-sha deletion **ALLOWED (0)**.
- **The counts are file evidence, not inference** — `168` / `0` under the old anchor and `168` / `21`
  under the new one, read off both `DECISIONS_LOG.md` files on disk.

**Status:** Decided and built on `gov/placeholder-guard-cross-repo`. **Shared-block change** — the
`health-connect-app` copy must be updated byte-identically. The propagation itself (`.githooks/` +
script copy, install, HCA `DECISIONS_LOG` / `OPEN_QUESTIONS` / `BRANCHES` rows) is **not** done here
and cannot be: this session is `health-app`-rooted, and loop work in a second repo requires an
HCA-rooted session. Carried in `ROADMAP` NOW as cross-repo debt, now with the generalisation as its
precondition rather than its follow-up.

**Propagation is not unconditionally safe in the source→destination direction, and that is a hole in
`#16`'s founding mechanism.** `health-connect-app`'s wording of the session-open rule — *"matching the
file's actual `###` heading format"* — is **generic and correct**. `health-app`'s was pinned to
`health-app`'s own grammar and returns zero against HCA's file. Verbatim propagation would therefore
have **replaced a correct line with a defective one**, at full fidelity, with a `diff` of empty as its
evidence of success. Copy-not-hand-merge kills drift by making the source authoritative; it silently
assumes the source is the better copy, and here it was not. The shared-block preamble now carries the
missing clause: **verify the source's rule against the destination's actual shape before copying** —
run the regex, count the store, check the paths exist — and if the source is wrong, fix it here first
and copy after. Never fix it in the copy; never hand-merge. This is a precondition of propagation,
not a review of it, and it is itself a shared-block edit that propagates.

**Also recorded:** `FEEDBACK` **§24** — chat cannot make verbatim claims about file content. The brief
that prompted this work stated both `CLAUDE.md` files were "read whole from master" and quoted a regex
the guard does not contain; the fetch surface had returned a paraphrase shaped like verbatim, welding
two bullets into one sentence. Truncation announces itself, paraphrase does not, and the confidence tag
is generated from the same surface as the claim. The operative half for Code is in that row: a misaimed
finding is not a false one — re-derive it against the tree before acting on it **or dismissing it**.

**Also minted here:** `OPEN_QUESTIONS` `Q79`, for the `@claude` Action's unguarded push path.
`#167` recorded that gap knowingly, but only in its own entry and a `BRANCHES` row — append-only
history and a row that dies at merge, neither of them a tracked item. So a reader of the store whose
job is *what is undecided* saw a fully-enforced guard, and the propagation brief's instruction to
mint an HCA row "mirroring health-app's" had nothing to mirror. Same shape as the defect above: an
instrument reading green over a surface it cannot observe.

**Do not revisit unless:** a third repo joins the project with a heading grammar outside `##`/`###`,
at which point the honest fix is to derive the pattern from a per-repo declaration rather than widen
it again; or the `@claude` Action's uncovered push path is closed (`Q79`), which needs a CI check
and not a hook, and would make the hook the second of two implementations rather than the only one.

---

### 170. The placeholder guard gains a CI surface — and with it the first POSIX control surface either repo has ever had

**Decision:** `.github/workflows/governance-guard.yml` runs the placeholder guard on `ubuntu-latest`, on
`pull_request` targeting master and on `push` to master, asserting in order: **(2a)** `.githooks/pre-push`
tracked mode is `100755`, **(2b)** the hook *executes* as git would execute it, fed crafted pre-push stdin
against a known-clean ref, **(2c)** the guard runs against the ref that would land. Extends `#167`'s
ref-level enforcement to a surface a client-side hook cannot reach. Supersedes nothing. Resolves `Q79`.

**The gap `Q79` named is real. The agent it named is not.** `Q79` said the `@claude` GitHub Action pushes
from a checkout that never ran `git config core.hooksPath`. health-app has **no `.github` directory in any
commit on any ref** — the Action has never been wired to this repo, so that push path does not exist and
never did. The question was minted on `#167`'s prose plus the shared block's claim that *"Code — and the
`@claude` GitHub Action — is the only writer"*, and nobody checked whether the Action was installed. That is
`FEEDBACK` §12 committed by Code rather than chat: a declarative about an unseeable surface (GitHub-side app
installation) carried as fact.

**The real uncovered path was in this repo's own history the whole time.** Five merges on master carry
committer `GitHub <noreply@github.com>` — `e62f89f`, `0aa0200`, `f4b538f`, `cb1b58f`, `9f9437c` — github.com
web-UI merges, i.e. **server-side ref updates**. `core.hooksPath` is per-clone and client-side; it can bind
neither a runner nor a merge button. So the hole is demonstrated, not hypothesised, and its positive control
needed no construction. The correction is worth more than the close: a gap recorded against the wrong agent
would have been "closed" by covering a path that does not exist, and the merge button would have stayed open
behind a green check.

**PREVENTION vs DETECTION — the distinction outcome D forces, and the reason this entry does not claim more
than it has.** `#167`'s claim is *prevention*. A `push: [master]` job fires **after** the ref has moved: by
the time it runs, the hole is on master. Against the merge button that is **detection**, not prevention, and
shipping it as though it were prevention would quietly weaken `#167` while appearing to strengthen it.
Prevention on this path needs two pieces and only one is a file:

- **`pull_request` targeting master** — runs before the merge button is live. In the tree, versioned, done.
- **Branch protection requiring the check** — disables the merge button until it passes. **GitHub-side repo
  config, not committable.** Code cannot land it; it is Luke's action. Until it is set, the PR arm reports
  and does not block.

`push: [master]` ships anyway as the backstop for anything reaching master outside a PR. The workflow header
states which arm is which, so a green run cannot be read as more than it is.

**The enforcement now spans three layers and only one is versioned.** `core.hooksPath` is per clone, branch
protection is per repo, and the workflow file is the only piece with a diff. A fresh clone or a settings
change removes enforcement with nothing in the history to show for it — the same unseeable-surface problem
in a new costume. Recorded here rather than rediscovered.

**Why `ubuntu-latest` is load-bearing and not an implementation detail.** `#23` — the propagated hook landing
non-executable in `health-connect-app` — was **not a coverage failure**. Every control in both repos runs on
Windows with `core.filemode=false`, and Git for Windows honours a script's shebang regardless of its mode
bit, so the substrate cannot express the defect. More Windows controls could not have caught it at any
count. A Linux runner is the first surface in either repo on which the mode-and-permission class is
observable at all, so siting the enforcement there buys the observability free. That coincidence is the
reason to build this now rather than when the backlog reaches it.

**Also corrected here, named rather than numbered:** `scripts/check_governance_placeholders.py`'s docstring
claimed *"the alias calls the same script."* It never did — the `land` alias body is
`checkout && merge --ff-only && push && branch -d && push --delete`, with no call to anything in `scripts/`
(read from `git config --global --get alias.land`, 2026-08-04). The docstring is a claim about **which
surfaces enforce the rule**, and this decision changes that set, so rewriting it to name the true two — the
hook and CI — is part of the change, not a rider on it. Not a separate decision.

**How you know — four real runs, and the evidence quoted is the failing output, not the passing:**

- **Negative control** — PR `#11`, clean branch, run `30881982823`: **success**.
- **Positive control, placeholder arm** — PR `#12`, synthetic `### #NEXT` + `## Q#NEXT`, run `30882006064`:
  **failure at 2c**, naming both offences against the merge commit `91aeccc` (the tree that would land, not
  the branch tip):
  `REFUSED: unresolved governance placeholder in HEAD.` /
  `DECISIONS_LOG.md:6513  ### #NEXT. CONTROL ONLY …` / `OPEN_QUESTIONS.md:2259  ## Q#NEXT. CONTROL ONLY …`
- **Positive control, mode arm** — PR `#13`, `.githooks/pre-push` at `100644`, run `30882020463`: **failure
  at 2a** — `tracked mode: 100644  (100644 8cd1001… .githooks/pre-push)`. `#23` reproduced deliberately on a
  surface that can see it, for the first time.
- **Positive control, execution arm** — PR `#14`, run `30882100017`. **Minted because the mode control did
  not prove what it appeared to:** 2a fires first and short-circuits the job, so 2b never ran against the
  non-executable hook and its behaviour was *argued, not shown*. This branch removed 2a only, keeping mode
  `100644`, and 2b failed on its own:
  `./.githooks/pre-push: Permission denied` — **exit 126**. That is the execution proof; without it the
  workflow header carried a claim in the exact style this project exists to refuse.
- **Scratch refs torn down** — PRs `#12`/`#13`/`#14` closed, all three remote branches deleted, local
  branches gone, `git branch -r` back to `master` + `feat/cbti-eval-trigger` + this branch.

**Unverified and recorded as such:** whether a GitHub App holds push rights on this repo. That is GitHub-side
config, not in the tree, and not readable from Code. Reported as unknown rather than assumed in either
direction — the mistake `Q79` made in the first place.

**Do not revisit unless:** branch protection is set, at which point the PR arm becomes prevention and this
entry's prevention/detection caveat should be superseded by a new entry recording it; an `@claude` Action or
any other automated pusher is installed, which reopens the credential question the original brief posed
(a default `GITHUB_TOKEN` push does not fire `on: push`, so the trigger would need re-planning); the guard
gains a third enforcement surface, at which point the docstring's surface list needs updating again; or a
non-Windows dev clone appears, which would make the mode class locally visible and reduce CI's unique value
to the enforcement half.

---

### 171. The pull request becomes the sole route to master; `land` rewritten around `gh`

**Decision:** master is reachable only by pull request, gated by the `placeholder guard (POSIX)` required
status check. Ruleset `master-pr-gated` (id `20414758`) requires a PR, requires that check under a strict
up-to-date policy, forbids non-fast-forward, and carries **no bypass actors**. The `land` alias is
**rewritten, not retired** — `git push -u origin <branch>` then `gh pr create --fill --base master` then
`gh pr merge --merge --delete-branch` — so the whole motion stays in the terminal and in Code's hands; no
part of it moves to a browser or to a second operator. `--auto` and `--admin` are both excluded by name.
`stale` is unchanged and stays global; `land` becomes **repo-local** (`git config --local`), because its
body now differs between repos and a `--global` alias cannot hold two.

**Rationale:** a required status check gates a merge, not a push, so prevention requires that the merge be
the only route. Two bypasses sit in this repo's own history: five github.com web-UI merges (`#170`'s
motivating evidence) and `a9d52d3`, a direct push to master on 2026-08-04 with no associated PR. Both are
outside `core.hooksPath`, which is per-clone and client-side.

This corrects a false claim in canon rather than adding a new constraint. `#40` rule 1 has asserted "single
merge path per repo — already live via GitHub repo settings" since it landed; the setting live was
delete-on-merge, and the single path never existed — `a9d52d3` and PR #11 sit on the same log. Enabling the
ruleset makes rule 1 true. Had it been declined, the honest alternative was amending rule 1 to say the path
is single by convention, not enforcement.

Secondary effect, recorded as effect and not intent: `--delete-branch` removes the branch server-side, so
`branch -d`'s ancestry check — a `#40` rule 2 violation living inside `#40`'s own tooling — no longer runs
at all.

**Supersedes:** `#40` rule 1's enforcement claim (now true rather than asserted) and its merge-motion
description; `#170`'s prevention/detection caveat, which that entry's **Do not revisit unless** explicitly
nominated for supersession once branch protection was set. Disposition (`#40` rule 2), naming (rule 5) and
the terminal-state gate (`#41`) are unchanged — `#41`'s gate was re-read this session and holds unmodified.

**Status:** Landed on `chore/merge-path-pr-migration`. The ruleset was created by Code, not Luke — the brief
assigned it to Luke, written before he directed that Code hold the whole path; it is reversible with
`gh api -X DELETE repos/Easty11/health-app/rulesets/20414758`. **OWED to Luke, and NOT closed by this
commit:** the alias body itself. Git aliases live in unversioned config; the old body is still in
`~/.gitconfig` and must be removed there and re-added with `git config --local` in this clone. A committed
doc is not a rewritten alias.

**How you know:** the refusals are quoted, not the successes. Direct push to master, exit 1:

    remote: error: GH013: Repository rule violations found for refs/heads/master.
    remote: - Changes must be made through a pull request.
    remote: - Required status check "placeholder guard (POSIX)" is expected.
     ! [remote rejected] master -> master (push declined due to repository rule violations)

Scratch branch carrying `### #NEXT` opened as PR #15; guard concluded `FAILURE`, `mergeStateStatus:
BLOCKED`, and `gh pr merge --merge --delete-branch` exited 1 with "not mergeable: the base branch policy
prohibits the merge". **The `--admin` escape that `gh`'s own refusal advertises was tested, because one that
worked would have made this theatre** — it is also refused, and its refusal is the only one that names the
check: `GraphQL: Repository rule violations found / Required status check "placeholder guard (POSIX)" is
failing. (mergePullRequest)`. `--auto` was confirmed to queue rather than bypass: exit 0, auto-merge armed,
PR stayed OPEN, master unmoved at `a9d52d3`. Scratch ref torn down. `rules/branches/master` returns the
three rules; `current_user_can_bypass` is `never`. `gh` 2.93.0.

**Recorded as NOT verified:** whether `gh pr merge --delete-branch` deletes the *local* branch. `gh pr close
--delete-branch` demonstrably does — it reported "Deleted branch scratch/ruleset-probe and switched to
branch master", and a following `git branch -D` errored `branch not found` — but close is not merge, and the
merge path was never exercised to completion here because nothing was permitted to merge. The brief asserted
the opposite (remote-only); that assertion is unproven in both directions, and `#41`'s gate is written to be
correct either way.

**RESOLVED 2026-08-05 — this note postdates the locked entry and closes a recorded unknown; it changes no
decision.** This entry's own landing supplied the evidence. `gh pr merge 16 --merge --delete-branch` was run
against PR #16, the PR carrying this entry; immediately afterwards `git branch --show-current` returned
`master` and `chore/merge-path-pr-migration` was absent from `git branch`. So `--delete-branch` deletes the
**local** branch and switches to the default branch on the merge path exactly as it does on the close path —
the brief's remote-only claim is disproven for both. Stated to its actual scope: this is `gh` 2.93.0 run from
a working copy checked out on the branch being merged; it says nothing about a merge invoked from elsewhere.
`#41`'s gate needs no change and got none — it was re-read this session and its local arm remains correct,
because a branch abandoned without a PR still never reaches this path at all.

**Do not revisit unless:** the ruleset is disabled, deleted, or gains a bypass actor — enforcement is
unversioned and leaves no diff, so this entry is the only in-tree record that it is expected; the job name at
`jobs.guard.name` changes, which silently unbinds the required context (a context that never reports reads
as pending, not failed); a merge queue is adopted, which moves the merge instant again; `gh`'s merge
semantics change; or `health-connect-app` gains a CI check, which reopens whether the merge path can return
to the shared block.

---

### 172. Merge-path mechanics leave the shared block — the boundary criterion for verbatim propagation

**Decision:** a rule belongs in the CLAUDE.md shared block only if its correctness is independent of any
surface outside the tree. Invariants qualify and stay: number-at-merge, terminal-state disposition, patch-id
over ancestry, concern-named branches, single-writer. **Mechanics that depend on unversioned config do not**,
and move below `END SHARED LOOP RULES` in the repo whose config they describe. Applied here: how a branch
*reaches* master is now repo-local (health-app PR-gated; `health-connect-app` unchanged), while disposition,
the ledger, the terminal-state gate and number-at-merge remain shared. `stale` stays a global alias; `land`
becomes repo-local.

**Rationale:** `#171` made health-app's merge path depend on a ruleset `health-connect-app` does not have. A
verbatim copy would have either imposed a PR-gated path on a repo with nothing to enforce it, or told HCA
its only working merge route had changed. This is the counter-case `#169`'s verify-before-copy clause
anticipated in principle and now has in fact — the first shared-block change that legitimately must not
propagate.

**The rejected alternative is the load-bearing part.** A shared rule *conditioned* on whether the repo has a
required check was considered and refused, because the condition is itself invisible from the tree: a reader
in either repo could not tell which branch of the rule applied to them by reading the repo. That is exactly
the defect that produced `Q79`, `#40` rule 1 and `#171` — a claim about an unversioned enforcement surface
entering canon unchecked — promoted into the governance text itself. A rule that reads differently in each
repo is a divergent rule wearing a shared rule's clothes, and worse than an honest split, because the
empty-`diff` propagation check would still pass.

**Finding, recorded because its absence is the point:** health-app has **no numbered entry** establishing the
verbatim shared-block model. `#22` draws the global-philosophy vs repo-canonical line, `#25` the
source-of-truth model, `#169` added verify-before-copy; the "edit here, copy verbatim" mechanism itself lives
only in CLAUDE.md prose. The brief cited "`#16`'s propagation model", which is `health-connect-app`'s
numbering — health-app's `#16` is about metric verification. The model this whole section depends on was
never numbered in this repo, which is how a rule about propagation could be drafted three times against the
wrong entry.

**Supersedes:** nothing outright. Amends the shared-block preamble (adds the boundary criterion), restates
number-at-merge against *landing* rather than fast-forward, and amends the disposition bullet. Extends
`#169`'s precondition from "is the source correct for the destination" to "does this belong in the shared
block at all". `#22` and `#25` stand.

**Status:** Landed on `chore/merge-path-pr-migration`. **Propagation to `health-connect-app` is OWED** and
must run in an HCA-rooted session per the single-repo rule: HCA takes the amended shared block verbatim (its
own merge path is unaffected and its `land` stays as it is) and gains nothing from health-app's new
repo-local section.

**How you know:** HCA's asymmetry was verified by direct inspection this session rather than assumed —
`rules/branches/master` returned `[]`, `rulesets` returned `[]`, `branches/master/protection` returned
`404 Branch not protected`, `contents/.github/workflows` returned `404 Not Found`, and check-runs on HEAD
`18841b78` returned `total_count: 0`. So the "HCA migrates too" resolution was not one CI wiring away — it
required a workflow authored from nothing, which is why it was not chosen.

**Do not revisit unless:** `health-connect-app` gains a CI check and a ruleset, at which point the merge path
could return to the shared block and this criterion should be re-applied rather than assumed; or a third repo
joins the project with a different enforcement posture, which tests whether "repo-local" scales or wants a
per-repo mechanics file.

---

### 173. Deep-confidence and Banister inherit `#71` — device deep-sleep is not a readiness input

**Decision:** Extends `#71` (deep-sleep minutes excluded from the daily readiness term; Samsung Ring
deep/light discrimination not fit for purpose) to two mechanisms `#71` did not address: the
`runDeepConfidence` module (`health-connect-app/src/deepSleepConfidence.js`) and Banister load.
Device-reported deep-sleep is **not** a first-class input to readiness or to Banister.
`deepSleepConfidence.js` is retained **diagnostic-only** — it surfaces deep-stage artifact
fragmentation; its tunables (`DELTA_ARTIFACT`, `SPREAD_SPIKE`, `SHORT_MS`, `HR_NADIR_PCT`,
`MARGIN_MS`) stay uncalibrated **by design** and feed no score, and `runDeepConfidence` is not wired
into readiness or Banister. No new rationale beyond `#71` — the same unfitness finding, applied to the
module and to Banister.

**Rationale:** Ring-validation literature generalises `#71`'s finding from one device to the sensing
class. PPG+accelerometer deep/N3 classification tops ~50–58% per-epoch with large individual-night
error and proportional under-reporting of deep on high-deep nights; group averages mask per-night
error. The confidence module can only **subtract** false deep (artifact slivers) — it can never
recover **under-reported** deep, so it cannot rehabilitate the signal for scoring even in principle.
That asymmetry, not the accuracy number, is what makes calibration pointless.

**Status:** Landed on `gov/open-questions-sweep` — governance only, no code change. Nothing to
implement: the decision is that two mechanisms stay unwired, and both are unwired today.
`deepSleepConfidence.js` lives in `health-connect-app` and is untouched by this entry.

**How you know:** `#71`'s own evidence (complementary two-class confusion signature; MCP/Samsung-app
exact match proving faithful ingest of a wrong-at-source number) plus Luke's records — low deep
despite refreshed waking, and ~26 of 30 deep segments under 3 minutes at Gate 2. Literature supplied
by the 2026-08-03 chat session: Herberger 2025 (Sci Rep); Kainec 2024 (Sensors); Robbins 2024
(Sensors); de Zambotti 2017 (Behav Sleep Med) — **cited as supplied and not independently retrieved
from this tree.** Q3's original "precondition cleared, re-run Gate 3" was **falsified** in the same
session: `collapseSleepSessions()` de-dups sleep **sessions** only, while the HR array
(`fetchHeartRateData` → `heartRateMapper` → `.flat()`) is never de-duped, so a re-run would likely
reproduce `hrMedianGapSec: 0`. **That falsification is a `health-connect-app` claim and is not
verifiable from this tree** (single-repo rule); it is recorded as reported, and it weakens rather
than carries the decision — the decision stands on `#71` alone.

**Resolves:** Q3 (supersedes its Gate 3 re-run requirement), `Q81`.

**Do not revisit unless:** a validated deep sensor enters the pipeline (EEG headband), or Samsung
ships a validated N3 algorithm with published per-epoch performance — the same trigger as `#71`,
deliberately, because this entry adds no independent trigger of its own.

---

### 174. The `/health-connect/sync` field contract is single-named on HCA's mapped names, pinned by a contract test rather than codegen

**Decision:** The `/health-connect/sync` payload is single-named on the mapped JS field names HCA
emits: `bpm` (HeartRate), `rmssd` (HRV), `date` (Steps), `type` (Exercise), and payload key
`workouts`. The dual-acceptance `.get_*()` reconcilers and their duplicate fields collapse to these;
the dead raw-library branches are deleted — `HeartRateRecord.beatsPerMinute`,
`HRVRecord.heartRateVariabilityMillis`, `StepsRecord.startTime`, `ExerciseRecord.exerciseType`,
`SyncPayload.exercise`. The stalled workouts→exercise rename is **abandoned**: `workouts` is live and
stays, `exercise` was never adopted by the client and goes. `.get_kg()` / `.get_meters()` are **out of
scope** — they unwrap Health Connect's nested `{inKilograms}` / `{inMeters}` shape, which is
forward-compatibility for record types HCA does not post, not a dual-name contract.

**Rationale:** The tolerance exists only because the contract was never single-sourced, and it costs
more than it buys: two accepted names for one value means no reader can tell which one production
sends, and a client-side rename fails silently rather than loudly.

**Not codegen — and that is the deliberate departure from `#24`/`#29`.** The sleep-stage enum is
generated from the backend spec. This payload is not, and should not be: there is exactly one
fully-controlled client, and once the dual acceptance is gone a rename 422s in test rather than
degrading in production. A contract test asserting each backend model's accepted field equals the
name HCA's mapper emits buys the same guarantee for a fraction of the machinery.

**Status:** **OWED** — the decision is settled, the code is not written. Outstanding: delete the five
dead branches in `backend/routers/health_connect.py` and add the field-name contract test. Landed on
`gov/open-questions-sweep` as governance only. `Q5` moves to `DONE → #174` when that lands, not
before. **SUPERSEDED by #234** (2026-08-24): the collapse is six branches not five (`dataOrigin`/
`.get_source_package()` in scope), and the loudness this entry claimed for the deletion — "a rename
422s in test rather than degrading in production" — was assumed, not built (extra-`ignore` +
`Optional`-`None` defaults would have discarded a raw name silently). `#234` supersedes the grounds;
`#235` builds the loudness. Q5 resolved `DONE → #234`, not `#174`.

**How you know:** The backend half was re-read against master this session: the five branches are
present and exactly as described — `beatsPerMinute` at `health_connect.py:79`, `.get_bpm()` at `:82`,
`heartRateVariabilityMillis` at `:98`, `.get_rmssd()` at `:101`, `StepsRecord.startTime`/`date` at
`:87`/`:89`, `exerciseType`/`type` at `:132`/`:133`, and `SyncPayload.exercise` at `:200` feeding
`all_exercises()` at `:208`. The client half — that HCA's `src/healthConnect.js` mappers rename
raw→mapped in the map expression and React Native serializes verbatim, so no build emits raw names —
was read by the 2026-08-03 chat session and **is not verifiable from this tree** (single-repo rule).
It is the load-bearing half: if it is wrong, deleting the raw branches breaks production silently on
the next sync. **The contract test is what converts it from an assumption into an assertion, which is
why the test is not optional and the deletion must not land without it.** Q5's "capture one real
on-device sync" precondition is struck as a red herring — source is the contract, not a capture.

**Resolves:** Q5, on the collapse landing.

**Do not revisit unless:** a second `/health-connect/sync` client appears — at which point one
controlled client no longer holds and codegen becomes the cheaper answer — or HCA changes an emitted
field name, which is what the contract test fires on.

### 175. Source *admission* replaces source *priority* for HC sleep — an allow-list, not a ranking (narrows `#35`/`#36`/`#37`)

**Decision:** `_aggregate_day` admits sleep **only** from an explicit allow-list of **registered
measuring sources** — Samsung `com.sec.android.app.shealth` today. Any other writer is **excluded by
default, not ranked**. This narrows `#35`/`#36`/`#37` from source **priority** to source **admission**:
those decisions rank all comers and let the top-ranked *present* source win; admission means an
unlisted writer never competes at all.

**Rationale:** The two mechanisms are indistinguishable on a night the canonical source is present, and
that is what made priority look sufficient. **They separate exactly where it matters: on a night
Samsung is absent and a mirror or unknown writer is present, priority lets the mirror win on duration
— silently — while admission excludes it.** The Withings Health-Mate mirror (`Q83`, attested
2026-08-05) is that case, made real. Priority fails *silent*; admission fails *safe*. For a source
feeding readiness, fail-safe is the correct default — and this is the same class of silent-edge-case
defect the surrounding sweep kept turning up (`#173`'s uncalibratable constants, `#174`'s
silently-breaking deletion).

**The trade, named so it is a chosen property and not a future surprise:** a genuinely new, legitimate
device — an Oura ring, a Polar watch — writing sleep to Health Connect **contributes nothing until it
is deliberately admitted**. That is the cost, accepted. Device-agnostic (the project-wide rule) means
**any device can be admitted, not that any writer is auto-trusted**; the admission step is precisely
where a new source gets characterised — provenance, units, whether it measures or mirrors — which is
work that was previously never done at all. The failure mode this creates is *loud and local* ("my new
ring's sleep is missing") against the one it removes, which is silent and downstream (readiness quietly
computed from an echo).

**Status:** **OWED** — decided, not implemented. No code is written; `_aggregate_day` still selects by
max-duration across all writers. Ordering is unchanged from `Q83`: admission runs **before** `Q82`'s
fragment-merge, because merging across a measuring source and its own mirror would double-count the
night.

**PRECONDITION ON THE IMPLEMENTATION — an allow-list is only safe if writer identity actually
arrives.** Read against master this session and unresolved: `WriterIdentity`
(`backend/routers/health_connect.py:56`) documents itself *"Optional/nullable everywhere: current HCA
builds send no dataOrigin, so a required field would 422 every live sync (#36). Capture only — no
filtering."*, and `_capture_record_sources` coalesces a missing identity to the literal `'unknown'`
before insert. **If identity arrives as `'unknown'` in practice, an allow-list admits nothing and the
night's sleep vanishes — a fail-closed-on-everything that is worse than the fail-silent it replaces.**
Against that, `Q83`'s own evidence shows `health_connect_record_sources` carrying real package names
(`com.sec.android.app.shealth`, `com.withings.wiscale2`) on 2026-08-03, which the docstring — dated to
the `c9b8a7d6e5f4` migration, 2026-06-29 — predates. The two cannot both be current. **Resolve which
before writing the filter, and make an `'unknown'` admission decision explicitly rather than by
default.** This does not gate the decision; it gates the code.

*(**Rider, added post-landing on `gov/175-precondition-narrowed` — it narrows the precondition above,
it does not revise the decision, and the original text is left standing because the history is the
point.** The contradiction resolved **in the safe direction the same day**: identity **does** arrive,
and the docstring is the stale artifact. Two facts settle it, both from surfaces this repo cannot read
and both attested by Luke 2026-08-05 from an HCA-rooted read plus prod data: HCA master's sleep mapper
and `heartRateMapper` thread `sourcePackage: r.metadata?.dataOrigin ?? null`, so current builds do post
it; and the live `health_connect_record_sources` rows carry real packages. The docstring predates the
mapper change that added `sourcePackage`. **So "an allow-list admits nothing" is what WOULD have
happened had the docstring been true, and it is not** — the fail-closed-on-everything scenario is
withdrawn. **What survives, narrowed:** the allow-list must not silently drop the `'unknown'` that
legitimately exists — historical rows written before HCA threaded `dataOrigin`, any record type HCA
does not tag, and a future build regression all produce it. So `'unknown'` must be a **decided value,
not a default that means exclude**: admit-with-flag, or fall back to pre-`#175` max-pick for
unidentified records, or log-and-count coverage per the `#74` fallback-hit-rate pattern. Live detail,
including the two moves that discharge it, is at `Q83`.)*

**How you know:** The code half was re-read against master this session and is cited by line:
`_aggregate_day` selects `best = max(day_sleep, key=...duration())` with no reference to any writer
field; `health_connect_record_sources` is **written** by `_capture_record_sources`
(`health_connect.py:314`, called at `:499`) and **never read back** — the grep returns the capture path
and the endpoint, nothing in the aggregation. Migration `c9b8a7d6e5f4`'s docstring states the table's
purpose verbatim: *"Backend enabler for source-priority dedup (DECISIONS_LOG #35 F1 / #36 / #37)."* So
the enabler has been populated and ignored since 2026-06-29. The mirror finding itself is **attested by
Luke 2026-08-05 and not independently verified from this tree** — the Railway CLI was non-functional in
the recording session, and Health Connect writer permissions are a device surface neither Code nor chat
can read.

**Resolves:** the `Q83` OWED note (the entry that the reframe needed in order to bind). `Q83` itself
moves to `DONE → #175` when the code lands.

**Do not revisit unless:** the allow-list becomes a real maintenance burden across genuinely many
legitimate measuring devices — at which point admission-plus-characterisation may want to become a
registry rather than a literal list — or Health Connect gains a native provenance guarantee that
distinguishes a measuring writer from a mirroring one, which would make the allow-list redundant rather
than merely narrower.

### 176. Governance edits bank to one batched PR per checkpoint; gate by diff shape, not file class (extends `#171`/`#172`)

**Decision:** Governance/docs-only changes (`DECISIONS_LOG`, `OPEN_QUESTIONS`, `BRANCHES`,
`ROADMAP`, `CLAUDE.md`, `FEEDBACK`, `closeout.md` — no code, no migrations) accumulate on a single
branch and land as **one PR per checkpoint**; individual items are not taken to their own PR.
Invariants: **(a)** an entry does not land until its design has settled — unresolved preconditions
keep it on the open branch, not master; **(b)** housekeeping (terminal `BRANCHES` row,
Recent-landings pointer) rides the originating branch, resolved at merge; **(c)** a batch is
guard-gated only if every removed line is inside an explicitly-declared replacement region — any
removal outside forces human review. Emergent findings append to the open branch. Code/schema always
take full human review. Extends `#171` (PR sole route to master) and `#172` (merge-path mechanics
health-app-local); neither is revised.

**Rationale:** The 2026-08-05 `OPEN_QUESTIONS` sweep landed as six sequential PRs (#21–#26) where one
or two would have sufficed; deciding and landing were interleaved when they should be two phases.
`#23` existed only to unwind a lying self-row `#22` introduced; `#26` only to reframe a precondition
`#25` shipped before it was reconciled. The naive form of invariant **(c)** — "governance-only →
guard-gated" — was falsified in the same session: a `#NEXT` blanket substring-replace corrupted 55
lines in `BRANCHES.md` and 104 in `DECISIONS_LOG.md` while `check_governance_placeholders.py`
returned exit 0 throughout, because it anchors on unresolved placeholder headings and cannot see
content corruption. `Q80` records the neighbouring hole (the guard checks the placeholder symptom,
not the uniqueness-and-gapless invariant, so a wrong-but-resolved integer also passes green). So the
gate is scoped to diff shape, not the guard's word.

**Status:** Landed on `gov/175-precondition-narrowed`, batched with the `Q83`/`#175` identity
reframe — the rule shipping inside the batch that motivated it. In force from this commit, since
`CLAUDE.md` carries the prose in the same change. **Invariant (c) is a MANUAL check today**, not an
enforced one: no script asserts "no removed line outside a declared replacement region". That is the
honest reading of its own rationale — the gate exists precisely because the guard cannot see this
class — and it is what the revisit trigger below is pointed at.

**How you know:** Observed directly — six PRs, most prose-only, ~$100, zero behaviour shipped; `#22`
→ `#23` and `#25` → `#26` the two self-inflicted loops; the `#NEXT` corruption and `Q80`'s
symptom-not-invariant note the two demonstrations that guard-green ≠ correct for governance. The
corruption figures are from the working tree before it was reverted (no commit was made): a blanket
`#NEXT` → `#175` replace, against a diff whose surgical redo touches `BRANCHES.md` +1/−0 and
`DECISIONS_LOG.md` +64/−0.

**Do not revisit unless:** the guard gains content-integrity coverage — `Q80`'s uniqueness-and-gapless
arm **plus** a removed-lines-outside-declared-region check — at which point invariant (c) can widen
from manual to guard-enforced and the batch can land unattended; or a governance edit is genuinely
time-critical (a live-wrong canonical row that will mislead an in-flight session), in which case a
single hotfix PR is justified and stated as such.

---

### 177. The lab-ingest banner discarded list-form 422 `detail`; both catch blocks now render the refused field (Move 1 of 2 — the contract question is held at `Q85`)

**Decision:** Both lab-ingest catch blocks in `frontend/src/pages/Metrics.jsx` — `/labs/extract`
and `/labs/confirm` — render a **list-form** FastAPI validation `detail` through one shared pure
helper, `frontend/src/lib/apiError.js`. The constant fallback string ("Failed to read/save report")
is now reserved for the case where `detail` is genuinely absent, which is the transport case and
the only one it can honestly describe. This is **Move 1 of two**: the instrument. The contract
question it was built to answer — whether `FieldConfidence` should tolerate a null `ref` — is
**NOT decided here** and is held at `Q85` until the live 422 names its field.

**Rationale:** A genuine urine-ACR report (SNP Albumin/Creat Ratio, collected 2026-08-04) could
not be saved, and the banner said only "Failed to save report". The catch block read
`typeof detail === 'string' ? detail : detail?.error`, which matches neither arm of a Pydantic
request-validation rejection: that `detail` is an **array** of `{loc, msg, type}`,
`typeof [] === 'object'`, and an array has no `.error`, so the whole structured rejection
collapsed to the one string that names nothing. The failure is diagnostically total rather than
destructive — the confirm write is transactional, so nothing partial persisted — but the user
could not self-serve, and **every** extraction failure of every shape presented identically.

The reusable shape is in `FEEDBACK` §25: a fail-closed request contract and a fail-opaque error
handler are each survivable alone and compound into an undiagnosable defect. Fixing the banner is
therefore not preliminary to the real fix; it is the only move that can be made **before** the
evidence exists, and it is what produces that evidence.

**Status:** **Move 1 landed. Move 2 HELD, and the live capture is OWED — nobody has yet re-uploaded
the reproducer.** The offending field is a **hypothesis, not a finding**: `FieldConfidence`
(`backend/routers/labs.py:41`) requires all four of `name/value/unit/ref` as bare `float`, while a
ref-less row (`R U-Creatinine`, printed `—`, sited above the results table) gives a model asked for
a per-field `ref` confidence nothing to be confident about — so it plausibly omits the key or emits
`null`. It is equally possible the model invented a `ref` and broke instead on
`report.source_completeness` or `report.panel_name_raw`, both required `str`. Those are different
defects with different fixes (contract loosening vs an extraction-prompt gap) and the captured
`loc` discriminates them in one read. **No contract change ships without the live field that
justifies it.**

**How you know:** Three artifacts, and note what each does *not* establish.

1. *The 422 is a request-validation rejection, by elimination — verified against the tree, not
   inferred.* `confirm_lab_report` has exactly two `raise HTTPException` sites of its own
   (`labs.py:514` collected-date, `labs.py:533` over-collapse), both with a **string** `detail`,
   which would have rendered. Both are independently excluded by the screenshot: the UI shows
   `Collected: 2026-08-04`, so `dates.collected` parsed; and all three markers are unmapped, so
   the over-collapse guard — which fires only on a *mapped* marker with a unit mismatch —
   structurally cannot fire. `grep` confirms no `RequestValidationError` handler anywhere in
   `backend/`, so FastAPI's default list-form body applies. Unmapped is a response signal (`#58`),
   never a failure. Only this one report of seven fails, which rules out flaky transport.
2. *The old code returns exactly the generic banner on the exact payload* — a positive control per
   `#103`, run rather than reasoned: feeding the G1 fixture to the pre-fix expression in `node`
   printed `"Failed to save report"`, with `typeof detail` `object` and `detail.error` `undefined`.
   Without this the new tests would pass without proving they discriminate the fix.
3. *Ten `vitest` cases pass* (`frontend/src/lib/apiError.test.js`), covering the list form, the
   multi-entry join, honest truncation, a non-`body` `loc` prefix, and the three previously-handled
   shapes as anti-regression. Backend suite **722 passed, unchanged from baseline** — this change
   touches no backend file. Frontend lint is unchanged at 5 pre-existing errors, all in
   `ChatPanel`/`WorkoutPanel`/`Settings`, none in a file this change touches (measured by stashing).

**What this explicitly does NOT establish:** that the banner renders correctly *in a browser*, and
that the hypothesised field is the real one. The assertion boundary is the helper plus a
source-level check that both call sites route through it — the repo had **no** frontend test runner
before this change (`vitest` is added here, node environment, no jsdom), so a rendered-DOM assertion
would have meant adding `jsdom` + a component harness to carry one string. The wiring test is the
substitute and is named as such. The live capture closes both gaps at once and is the gate on Move 2.

**Do not revisit unless:** the captured `loc` lands — at which point Move 2 is scoped by it, not by
this entry's hypothesis (a `field_confidence.*` hit means `float | None` sub-fields **and** fixing
the `min()` over a `None`-bearing list at `labs.py:603`, which would raise `TypeError`; anything
else means an extraction-prompt gap and no contract change). Or: a second consumer needs this
helper, at which point the truncation cap (5) and the `body`-stripping convention become shared
policy rather than one banner's formatting and should move behind a named contract.

---

### 178. A ref-less row nulls a non-Optional exclusivity bool; the contract coerces `null → False` on both flags (cures the `#177` fault, resolves `Q85`)

**Decision:** `ResultItem.ref_low_exclusive` and `ref_high_exclusive` gain a Pydantic
`mode="before"` field validator mapping `None → False`. The declared type stays strictly `bool`.
The extraction prompt's normalisation block gains the absent-ref case explicitly — empty/blank ref
sets both flags `false`, and the flags are always booleans, never null. **No migration**, no schema
change, and `field_confidence` is deliberately untouched.

**Rationale:** **Coerce, do not loosen.** `False` is the semantically correct value, not a
placeholder: with no bound there is nothing to be exclusive about. It is also exactly what the
column already wants — `models.py:622-623` is `Boolean, nullable=False, server_default=text("false")`
— so keeping the Pydantic type `bool` means nothing downstream ever sees `None` and no migration
follows. Loosening to `bool | None` would have propagated a null into a non-nullable column and
bought a migration for no gain.

**Both flags, though the capture named only one.** Which side the model nulls is nondeterministic:
this report nulled the ceiling flag on an absent-ref row, but a `>x` floor-only row leaves the
ceiling absent and a `<x` ceiling row the floor. Fixing only `ref_high_exclusive` would have
re-opened the identical fault on the next report shape — a fix scoped to the observed instance
rather than the class.

**The coercion is behaviourally inert on exactly the rows it touches**, which is why it is safe
rather than merely convenient: every consumer reads the flag only inside a bound-is-not-None branch
— `interpretation/gates.py:108,114` and `context_builder.py:965-966` both guard on
`ref_low is not None` / `ref_high is not None`. A row whose bound is null never consults its flag.

The prompt arm is secondary and is not the guard. `labs.py:254-258` enumerated `a-b`, `<x`, `>x`
and, for empty/blank, named only `ref_low`/`ref_high` — saying nothing about the exclusivity flags,
so the model was left to invent and emitted null. Stating the case cuts recurrence at source, but
the model is nondeterministic, so the contract coercion is the actual guard. Both ship.

**Status:** Landed. `Q85` resolved by this entry. The original fault — the SNP Albumin/Creat Ratio
report, collected 2026-08-04, un-ingestible since — now saves.

**Scope, and one correction to the brief that carried this work.** The brief stated that fixing the
pair "closes the null-on-sparse-row class completely". Audited rather than assumed, that is true of
`ResultItem` and not of the request contract as a whole. Enumerating every non-Optional scalar in
the confirm path: on `ResultItem` the only survivor is `marker_name_raw`, which is always present on
a row that exists at all — so the per-row surface a sparse document actually hits IS closed, and
`test_no_other_resultitem_field_can_be_nulled_into_a_422` asserts it so a future bare-scalar field
trips in the suite rather than in production. But **`FieldConfidence` still declares four
non-Optional floats** (`name`/`value`/`unit`/`ref`), nested inside `ResultItem`. They validated on
this report — which is why they are untouched here, per `#177`'s own lesson about not shipping a
guess — but they are the remaining members of the class, not absent from it. Recorded so the next
sparse shape does not find them cold.

**How you know:** Four artifacts.

1. *The captured `loc`, which is the whole reason this entry is scoped the way it is.*
   `results.0.ref_high_exclusive: Input should be a valid boolean`, read off the deployed `#177`
   banner (screenshot, SNP Albumin/Creat Ratio, collected 2026-08-04). **Neither predicted branch
   was right** — `#177`'s brief guessed `field_confidence.ref`; `Q85` offered `field_confidence.*`
   or `source_completeness`/`panel_name_raw`. All wrong. The live extraction adjudicated what no
   amount of chat-side tracing could.
2. *The end-to-end test reproduces the original 422 byte-for-byte against unfixed code.* Reverting
   `labs.py` to master and re-running yields
   `{"type":"bool_type","loc":["body","results",0,"ref_high_exclusive"],"msg":"Input should be a
   valid boolean","input":null}` — the captured banner's field and message exactly. With the fix,
   201, three rows written, all `unmapped`. It drives the **route**, not the handler: the 422 was
   raised by Pydantic before `confirm_lab_report`, so a test calling the handler object would
   construct `ResultItem` in Python, skip request validation, and pass against the broken code
   (`FEEDBACK` §23, fake below the defect).
3. *Positive control per `#103`.* Against master's `labs.py`, 4 of the 10 contract tests fail and 5
   of the 5 end-to-end tests fail; the 6 anti-regression contract cases pass both before and after.
   The split is the evidence the suite discriminates the fix rather than passing incidentally.
4. *Suite.* Backend **737 passed** against a 722 baseline (+15: 10 contract, 5 end-to-end).
   Frontend **10 passed**, unchanged — this change touches no frontend file.

**Do not revisit unless:** a sparse row nulls something inside `FieldConfidence` — the residual
named under Scope above, which this entry deliberately does not pre-empt; the fix would be the same
coercion, and the evidence should again be a captured `loc`, not a prediction. Or: a genuine
semantic need arises for a *null* exclusivity flag, meaning "unknown whether the bound is
exclusive", distinct from `False` meaning "inclusive" — at which point the column's `nullable=False`
is the thing to revisit first, and this entry's inertness argument no longer holds because consumers
would need a third branch.

---

### 179. `FieldConfidence` sub-fields made Optional; the null-on-sparse-row class is closed for row-level fields (last instance of the `#177`/`#178` family)

**Decision:** `FieldConfidence.name/value/unit/ref` become `float | None = None`. Four arms ship
together, because loosening the contract alone relocates the failure rather than removing it:
(1) the contract, so a ref-less row's `{"ref": null}` validates; (2) the confirm derivation
(`labs.py`) drops `None` before `min()`, or a null converts the removed 422 into a 500;
(3) the frontend `isSuspect` and `confidencePct` (now `frontend/src/pages/labRowClassification.js`)
guard `null`, or JS coerces it to 0 and reports a clean extraction as suspect / understates its
confidence; (4) the extraction prompt states the not-applicable case. `field_confidence` as a whole
was already Optional; this is about its sub-fields when the object is present.

**Rationale:** **LOOSEN, do not coerce — the opposite call from `#178`, and the difference is the
point.** `#178`'s exclusivity bools had a correct default (`False`: an absent bound has nothing to
be exclusive about), so coercion was honest. A confidence has *no* safe default: `1.0` asserts high
confidence in a field never read (hides a suspect row), `0.0` marks suspect a field that legitimately
does not exist. Both are directional lies. `None` = "not expressed" is the only honest type, which
forces every consumer to treat it as **absent**, not as a number — and three of them would coerce it
to 0 if left unguarded, which is why arms 2 and 3 are not optional extras but the same fix finishing
its own consequences.

Arm 2 preserves the existing semantics exactly: an all-`None` object (or an absent object) filters
to empty and falls to `1.0`, the same as today's absent-object branch, so it does not resurrect
`#146`'s silent-zero ambiguity. Non-empty stays min-over-expressed — §6's rule that overall
propagates the worst *expressed* row confidence. Arm 4 is secondary and not the guard; the model is
nondeterministic, the contract is not.

**Shipped pre-capture, deliberately, and this is the one governance-worthy difference from
`#177`/`#178`.** Those two fixed a 422 that had actually happened. This one has **not** yet fired in
production: on the `R U-Creatinine` upload the extractor happened to emit a real `ref` confidence
rather than null. But whether it scores a `ref` it never read is nondeterministic, the trigger row
demonstrably exists in the corpus, and the root-cause pattern is the one already proven twice. This
is closing the *last known instance of an identified class*, which is what the thread's minimalism
rule licenses — distinct from speculative hardening of a pattern never observed. The distinction is
recorded because "we fixed it before it broke" is exactly the shape a scope-creep rationalisation
also takes, and the difference (proven pattern + real trigger shape vs. imagined one) is the test.

**Status:** Landed. `Q86` opened as the residual watch-point (report-level required scalars, left
fail-closed by design). The row-level null-on-sparse-row class is now closed and asserted closed.

**Scope — enumerated, not asserted.** After this, no row-level non-Optional scalar can be nulled into
a 422 except `marker_name_raw`, which is always present on a row that exists.
`test_no_remaining_row_level_scalar_fails_closed_on_null` walks `FieldConfidence.model_fields` and
`ResultItem.model_fields`, probes each with `None`, and asserts the survivor sets are exactly
`{}` and `{marker_name_raw}` — so a future bare-scalar field added to either trips in the suite, not
in production. **This is claimed of row-level fields ONLY.** The report-level required scalars
(`ReportEnvelope.lab_name`, `panel_name_raw`, `source_completeness`) stay non-Optional **on purpose**:
a report genuinely missing its lab name or panel identity is an extraction fault to surface — now
with a readable banner (`#177`) — not a legitimate sparse row to tolerate. Different class, correctly
left alone; `Q86` is its watch-point.

**How you know:** Four arms, each with a discriminating control per `#103`.

1. *Contract + derivation, against master's `labs.py`:* the null-`ref` cases raise
   `ValidationError` (`Input should be a valid number [float_type, input=None]`) and the derivation
   cases fail — the 422 and the latent 500 both reproduced. With the fix: route returns **201**, the
   stored row confidence is the min over expressed fields (`0.97`, not `0` and not the poisoned
   mean), and an all-null object scores `1.0` identically to an absent one.
2. *Frontend, against master's classification logic (exports added but bodies unchanged):* 5 of 10
   cases fail — the null-suspect cases and, tellingly, `confidencePct` returning **74%** where the
   guarded version returns **98%** (the mean-poisoning arm, the one easy to miss). The 5
   genuine-signal cases pass both sides, proving the guard did not flatten the real signal.
3. *Suite.* Backend **749 passed** vs a 737 baseline (+12); frontend **20 passed** vs 10 (+10). The
   classification helpers moved to `labRowClassification.js` — a component file may only export
   components (`react-refresh`), the same split as `lib/apiError.js`; frontend lint is unchanged at
   the 5 pre-existing errors.

**Do not revisit unless:** a report-level required scalar is nulled by a real extraction — that is
`Q86`, and the answer would be to fix extraction, not to loosen the contract. Or: a genuine need
arises to distinguish "confidence not expressed" (`None`) from "expressed as low" (`0.1`) in the
stored data rather than only at derivation — at which point `overall_confidence`'s all-None→`1.0`
fold is the thing to revisit, because it deliberately erases that distinction today.

---

### 180. Canonical map gains the three urine-ACR markers; analyte-first specimen-suffix is the standing key convention (completes part of `#57`'s deferred list)

**Decision:** `backend/reference/marker_canonical.json` gains three entries —
`R U-Creatinine` → `creatinine_urine` (mmol/L), `R U-Albumin` → `albumin_urine` (mg/L),
`R U-Albumin/Creat` → `albumin_creatinine_ratio_urine` (mg/mmol), all `loinc: null`. This is a
**data addition**; no confirm/read code changed. It sets the map's **first specimen-typed markers**,
and with them the convention every future urine/serum split inherits: **analyte-first, qualifier-
suffixed** (`creatinine_urine`, not `urine_creatinine`) — matching the existing `calcium_corrected`
shape and sorting an analyte's variants adjacently. `#57` deferred "ACR" explicitly; this lands it.

**Rationale:** The three markers were stored raw-and-unmapped from the SNP Albumin/Creat Ratio
upload; unmapped they never trend (`LAB_EXTRACTION_SCHEMA §7`). They walk directly onto §7's
over-collapse landmine — each shares an analyte token with a serum marker already in the map
(`Creatinine`→`creatinine` umol/L, `Albumin`→`albumin` g/L) — and two mechanisms hold them apart,
both asserted in tests, not assumed: **exact-string keying** (`R U-Creatinine` is a different key
from `Creatinine`; no fuzzy match exists) and the **§6 unit guard** (a urine row carrying a serum
unit is refused, not merged). The specimen-first alternative (`urine_creatinine`) reads more
naturally but scatters an analyte's variants; nothing downstream depends on the string beyond
exact-match, so the choice is free now and expensive later — hence recording it as the standing
convention rather than an ad-hoc key.

**Status:** **Map landed. The expansion is NOT YET COMPLETE — the mandatory backfill is OWED against
prod and has not run.** The `#55`-sibling standing rule (documented in
`backend/backfill_marker_canonical.py`'s own header) is explicit: a canonical-dict expansion that
skips the backfill lets the `COALESCE(marker_canonical, marker_name_raw)` reads partition
double-count the newly-mapped marker — the pre-bump raw-keyed stored row and a post-bump
canonical-keyed upload read as two series. The three rows are stored with `marker_canonical` NULL
right now. **This session cannot reach prod** (the Railway CLI has no TTY here, and data
verification is a Railway Postgres query per `CLAUDE.md`), so the dry-run, the `--apply`, and the
backend redeploy that reloads `_CANONICAL_MAP` are all handed to the operator. Recording the rule as
*honoured* would be false; it is honoured only when the backfill lands in prod.

**Two assumptions stated, both with loud failure modes (not silent):**
1. *Units.* `unit_established` is set to the clinically-standard SNP ASCII forms (mmol/L, mg/L,
   mg/mmol), consistent with the file's convention (serum `umol/L`, `ug/L`). The brief's precision
   check — that these byte-match the `unit_canonical` actually stored on the three rows — is **OWED**;
   it needs the stored rows, which are in prod. If a live extraction's normalised unit differs in
   byte form, the §6 guard trips on the *next* upload with a message that names both units
   (`#177` made that banner legible) — a loud, self-diagnosing 422, never silent corruption. Safe to
   land under the assumption for exactly that reason.
2. *Backfill row count.* The script is generalised — it binds every raw name in the map with
   NULL-canonical rows, not only these three — so the "dry-run reports exactly three" gate assumes
   prod holds no other unmapped-but-mappable rows. A wider count is a signal to investigate before
   `--apply`, which is what the dry-run-first sequence is for.

**How you know:** Local evidence only; prod verification is owed.
- `_load_canonical_map` returns 69 entries, all three urine markers keyed by raw name at the tabled
  canonical/unit; no duplicate `marker_name_raw`; the serum homographs are untouched
  (`creatinine`/umol/L, `albumin`/g/L). File stays pure ASCII with zero em-dashes, hand-edited per
  the `#98` reference-JSON guard (no `json.dump` reflow — the diff is +18 lines, one comma changed).
- Route-level §6 discrimination: a fresh `R U-Creatinine` at `mmol/L` returns 201 and stores
  `creatinine_urine`; the same marker at serum `umol/L` returns 422 naming the over-collapse guard,
  both established and mismatched units. This is §7's protection doing real work on real data, not
  in design — the `FEEDBACK` note records it as the first live exercise.
- Control per `#103`: all six new tests fail against master's map and pass with the addition. Backend
  **755 passed** vs a 749 baseline (+6 new; one Move-2 e2e assertion updated in place from
  "all_unmapped" to mapped, since this change is precisely what makes those rows resolve). Frontend
  **20**, unchanged — no frontend file touched.

**Do not revisit unless:** the OWED backfill's dry-run reports other than the expected rows (a
raw-name collision to investigate), or a real upload trips the §6 guard on a byte-form unit mismatch
(the precision check coming due the loud way) — in either case the fix is a one-line map or a bounded
data correction, not a convention change. The analyte-first convention itself is revisited only if a
future specimen split cannot be expressed as `analyte_specimen` (none foreseen: blood/serum/plasma,
urine, saliva all suffix cleanly).

---

### 181. The `get_lab_results` MCP tool reuses `routers.labs.get_lab_results` (#59/#47 surface), so the interpretation withhold is inherited, not re-implemented

**Decision:** A seventh MCP tool, `get_lab_results(marker, limit) -> str`, surfaces stored lab
results to the chat model as a thin text formatter over the **existing** REST read-back
`routers.labs.get_lab_results` (the #59 consumer, projected to the #47 raw-fields-only
`StoredResultOut`). It does **not** read `labs_reads.latest_lab_results` or `marker_series`.
`marker` filters to one analyte and `limit` keeps the most-recent N reports, both applied in the
tool over the returned Pydantic snapshots — no second query.

**Rationale:** The #47 boundary (raw values / ranges / lab-asserted flags only — no
`computed_flag`, `confidence`, `is_derived`, deltas, mechanisms, or levers) is enforced at the
projection in `routers.labs.get_lab_results`. Reusing that function inherits the boundary for free;
re-querying `LabResult` in the tool would re-implement — and eventually drift from — the withhold.
`latest_lab_results` (one-row-per-marker-latest) and `marker_series` (trend) are the seams the 4b
interpretation producer (#49) owns; a raw read-back tool must not reach for either, or it starts
computing latest/trend, which is interpretation wearing a read-back's clothes. The tool's docstring
tells the consuming model the same thing in-band ("Not interpreted — no deltas, mechanisms, or
judgements"), so it does not diagnose off a raw surface.

**One clarification against the brief — the marker matcher.** The brief said to reuse
`labs_reads.find_marker`'s rule and "don't invent a second matcher; import/mirror that one." Its
RULE is mirrored exactly — word-boundary, case-insensitive, matched against the raw name or the
canonical id with underscores read as spaces. But `find_marker` is **directional**: it searches a
row-name *within a user message* (mention-detection over a sentence), whereas a `marker=` filter
needs the query searched *within* each row's names. Reusing `find_marker` literally would treat the
query as the message, return first-match-only, and miss every marker whose name is longer than the
query — `marker="creatinine"` would not match `R U-Creatinine`. So `_marker_matches` mirrors the
rule in the filter direction; it does not call `find_marker`. This is a same-rule/opposite-subject
mirror, which is what "mirror that one" asks for, not a second matching rule.

**Status:** Landed. Seven `@mcp.tool()`s now; the tool is registered and the module imports clean
(no circular import from the new `routers.labs` dependency — verified).

**How you know:** `tests/test_mcp_lab_results.py`, 10 cases, all green; backend suite **765 passed**
vs a 755 baseline (+10), frontend untouched (no frontend file changed). The formatting/filter logic
is extracted to a pure `_format_lab_results` and tested over the **real** read's output
(seed → `routers.labs.get_lab_results` → format), so the projection is genuinely exercised rather
than stubbed; the `@mcp.tool()` wrapper adds only `_current_user_id()` + a session, which need a live
bearer token and are not the logic under test. The #47 withhold has a **string-level** guard on top
of the projection guarantee (test c): a row stored with `computed_flag="H"` and `confidence=0.40`
renders byte-identically to a clean row, and neither the field names nor the leaked values (`[H]`,
`0.4`) appear. Control per `#103`: the suite cannot even import against master (the helper does not
exist there) — the feature is net-new, so an import-level failure is the honest discrimination.

**Do not revisit unless:** the tool needs latest-per-marker or trend — at which point it is no longer
a raw read-back and the work belongs to the 4b producer (#49), reading `latest_lab_results` /
`marker_series`, not this tool widening. Or the REST projection `StoredResultOut` changes shape, in
which case this tool follows it automatically (that is the point of reusing it) and only the
formatter's field references need review.

---

### 182. Writer identity is repo-local evidence; the shared block asserted it as an invariant

**Decision:** The shared block's writer line — "Code — and the `@claude` GitHub Action — is the only
writer" — is reduced to "Code is the only writer." The `@claude` Action clause is struck from the
verbatim-propagated block. It named a per-repo surface, not an invariant, and a rule earns a place in
the shared block only if its correctness is independent of any surface outside the tree. Any Action
wiring is stated below `END SHARED LOOP RULES`, in the repo-specific section of the repo that has it;
health-app has none to state.

**Rationale:** The clause was carried into both repos as though it were an invariant. It is not one —
and the specific finding is stronger than "the surface differs per repo": no `@claude` Action exists
on any ref of health-app. `git ls-tree -r --name-only HEAD -- .github` lists only
`governance-guard.yml`, a `permissions: contents: read` CI check that cannot write to the repo, and
`git grep -niE '@claude|anthropic|uses:.*claude' HEAD -- .github` returns a single hit sitting inside
that file's own prose comment — no `uses:` action reference anywhere. So the claim was false in
health-app just as in HCA, naming a writer that has never existed in either tree; the server-side
merges this repo does have were made by the web-UI merge button (`GitHub <noreply@github.com>`), not
by any agent. HCA's stores recorded the same consequence independently — HCA's `Q12` logged the claim
used as fact about a push path that never existed there (`git log --all -- .github` empty until HCA's
`#24`), and HCA's `#170` made the identical correction to HCA's `Q79`. Same class as HCA's `#24`
header finding: the rule is the invariant, the writer roster is evidence, and evidence does not
propagate. Resolved by the block's own boundary criterion — the shared line now states only that Code
is the only writer.

**Status:** Landed. One-line strike to `CLAUDE.md:55`; no repo-specific writer line added, because
there is no Action wired here to name.

**How you know:** `git ls-tree -r --name-only HEAD -- .github` →
`.github/workflows/governance-guard.yml` only, which declares `permissions: contents: read`.
`git grep -niE '@claude|anthropic|uses:.*claude' HEAD -- .github` → one hit, inside a prose comment,
no action reference. The block was re-measured against its baseline before the edit
(259 / 18757 / `20722eee1462769531d54d2b28ec2f64`, git LF blob, lines 20–278, trailing newline
excluded — the surface named per §14) and is re-measured after the edit; the post-merge triple is
emitted for the HCA re-mirror (Brief B) so it mirrors against a hash, not a description.

**Do not revisit unless:** an `@claude` Action — or any other automated writer — is actually wired
into health-app. At that point its writer status is stated below `END SHARED LOOP RULES` in the
repo-specific section, never restored to the shared block; the shared line stays "Code is the only
writer" regardless, because it is the invariant and the roster is not.

---

### 183. The placeholder guard could report clean on a store it never read

**Decision:** `read()` in `scripts/check_governance_placeholders.py` now captures the store as
**bytes** and decodes it explicitly, and every path that yields no checkable content routes to
**exit 2** — non-zero `git show`, a `UnicodeDecodeError`, and empty/whitespace-only content — on
both the `--ref` arm and the working-tree arm. This is conformance to the exit contract the
docstring already states ("Exit 2 = the check itself could not run … never silently pass, because a
check that cannot run is not a check that passed"), not new policy.

**Rationale:** `read()` returned `r.stdout` after checking only `r.returncode`. Under `text=True`,
git's blob is decoded inside a subprocess reader thread; a `UnicodeDecodeError` there kills the
thread, leaves `returncode` at `0`, and yields a non-string — invisible to a `returncode` check.
`re.finditer(None)` then raised `TypeError`, exiting via an uncaught traceback with code `1` — the
SAME code as a genuine `REFUSED`, and indistinguishable from one to CI, where the contract reserves
`2` for a check that could not run. An empty blob reached a quieter silent end: `git show` exits `0`,
`stdout` is `""`, the `returncode != 0` arm never fires, and `finditer("")` matches nothing → the
guard returns **exit 0 on a governance store with no content**. The loud path fails closed today only
because `re.finditer` type-checks its argument — an accident of the regex API, not a property of this
guard. Fifth member of the class *a check that runs over nothing and returns the expected answer*:
locally, `FEEDBACK` §14 occurrence 4 and the close-out's own header gate; the same class recorded in
HCA as `#24` (header evidence), and — per Brief D — `#25` (CRLF) and `#26` (stale figure).

**Status:** Landed. `read()` rewritten (fix commit); the docstring's contract is unchanged because it
already stated the rule (the docs commit strikes only the two cross-repo sentences — see the next
entry).

**How you know:** Reproduced against the UNFIXED script on scratch refs (#170). A CP1252 byte (`0x97`)
committed into `DECISIONS_LOG.md` produced `UnicodeDecodeError` in `Thread-1 (_readerthread)` then
`TypeError: expected string or bytes-like object, got 'NoneType'` at `finditer`, exit `1`. An empty
`DECISIONS_LOG.md` blob produced **exit 0** — the demonstrated silent false PASS (step 3 was run, not
inferred). After the fix, four controls with exit codes asserted and real output read: clean ref → `0`
(no output); unresolved placeholder → `1` (`REFUSED`, naming `DECISIONS_LOG.md:<line>`); non-UTF-8
byte → `2` (names path + ref, no traceback); empty blob → `2`. Scratch refs torn down;
`git ls-remote origin` confirmed none leaked.

**Do not revisit unless:** the exit contract itself changes, or a governance store legitimately
becomes empty/whitespace-only — which it never should, since both `CHECKS` paths are known non-empty.

---

### 184. A file cannot hold evidence about a repo it cannot see

**Decision:** Two docstring sentences in `scripts/check_governance_placeholders.py` are **struck, not
corrected**: the exclusivity parenthetical on the ruleset (`, health-app only`) and the sentence
asserting HCA's enforcement state (`` `health-connect-app` has the hook only — no workflow, no
ruleset ``). The ruleset id is kept. Cross-repo enforcement state belongs in the command that reads it
live (`gh api`), not in a file that cannot keep it current.

**Rationale:** Both were true when written and have since gone stale — HCA has wired its own
governance workflow and a `master-pr-gated` ruleset (recorded in HCA's own stores, per HCA `#24` /
Brief D; not verifiable from this tree, which is the point). They sat four lines below this file's own
warning that a green run is never evidence the layers are installed and that they must be checked
directly. The deeper justification does not depend on the claims' current truth value: **a file has
no means to keep a claim about another repo current, and no surface here would ever contradict it, so
it should not originate one** — true or false. HCA `#24` ruled that evidence does not propagate
between repos; this extends it to origination. The second sentence would have survived a strike aimed
only at the first, so the strike list came from a grep of the whole docstring, not the one sentence
first noticed — the transferable point. Same class as `#182` (writer identity is repo-local evidence,
not a shared invariant).

**Status:** Landed. Docstring-only strike (docs commit); no behaviour change. The `VERIFY` grep of the
full docstring returned exactly these two cross-repo assertions and no third. Two further HCA
references remain in the `CHECKS` code-comment — they justify the `{2,3}` heading-level in the regex
the code actually runs (a rationale that co-varies with the pattern, not a dangling enforcement claim)
— and are deliberately left.

**How you know:** `ast.get_docstring` + a regex over the docstring returned two matches: the
`, health-app only` parenthetical (docstring line 29) and the `health-connect-app has the hook only`
sentence (line 41). Post-strike assertions: `health-app only` absent; exactly one `health-connect-app`
remains (the code-comment); the module parses (`ast.parse`); pure CRLF preserved.

**Do not revisit unless:** health-app wires its own automated writer or changes its own ruleset in a
way worth restating — in which case it is stated below `END SHARED LOOP RULES` and checked live, never
re-entered as a claim about another repo.

---

### 185. The rule against cross-repo claims was applied to one file, not to the repo

**Decision:** `CLAUDE.md`'s repo-specific merge-path section carried a third instance of the defect
`#184` struck — a present-tense sentence asserting `health-connect-app`'s enforcement state ("has no
ruleset, no branch protection, and no `.github/workflows` directory at all") as the justification for
why the section is repo-specific. It is **struck and replaced with the structural justification**: a
merge path depends on enforcement configuration, which lives outside the tree and is set per repo, so
by the shared-block boundary criterion it cannot be a shared rule — no claim about what HCA currently
has, which would only reset the clock. The same session runs `#184`'s test **repo-wide** rather than
file-locally: every tracked `*.md` and `*.py` is swept for cross-repo references and each is classified.

**Rationale:** `#184` ruled that a file may not originate evidence about another repo — it has no means
to keep the claim current and no local surface would ever contradict it — but the grep behind it was
scoped to the one file where the defect was first seen. A rule enforced only where it was discovered is
not enforced. The `CLAUDE.md:293` sentence proved it: three false clauses in one sentence, one of them
("no `.github/workflows` directory at all") **already false when `#184` landed** — the rule was four
commits old and its violation sat two hundred lines away in the same repo. All three clauses were
verified false at merge via `gh api` (ruleset `20573455` active; `.github/workflows/governance-guard.yml`
present) — verified only to justify the strike, never written into the file.

**Status:** Landed. Governance/docs strike plus a new `.gitattributes`. The sweep — 9 tracked `*.md`
(236 matching lines) and 8 `*.py` (27), 263 lines across 17 files — returned **exactly one** in-scope
live state claim: the struck sentence. One further live-but-stale claim, `backend/models.py:224`
("current HCA builds send no dataOrigin"), is a wire-contract claim in a code file, already
`Q83`/`#175`'s territory with its sibling docstring (`routers/health_connect.py`) already corrected;
**held for separate human review**, not swept into this governance batch. Every other reference
classified as append-only history (`DECISIONS_LOG` ×133, `FEEDBACK`, immutable migrations),
structural/grammatical (the checker's `{2,3}` note `#184` itself kept, `gen_governance_view.py`'s parser
grammar for reading both repos, heading-form refs), a dated past-tense narration (`CLAUDE.md:48`
"Earned … had no CI workflow", `HANDOFF`'s event log), or a cross-repo task-pointer / debt row / open
divergence question (`BRANCHES`, `ROADMAP` §NOW per `#112`, `OPEN_QUESTIONS` Q30/Q32/Q33/Q87) — none
struck.

**How you know:** `git grep -Eic 'health-connect-app|\bHCA\b'` over tracked `*.md`/`*.py` enumerated
every reference (263 lines / 17 files); each classified against the three bins. Post-strike,
`CLAUDE.md:293` asserts nothing about HCA's state; `git diff --cached` showed 6 insertions / 3 deletions
on `CLAUDE.md` — the strike only, no whole-file EOL churn (`#176(c)` / Brief D signature) — plus a new
`.gitattributes`. `.gitattributes` verification: `git ls-files --eol BRANCHES.md` now reads
`i/lf w/crlf`, so the `-text` heuristic no longer trips after `dc023a1`'s heal — `*.md text` is
**preventive** (forecloses re-tripping on a future long-line edit), not a live fix; `git add
--renormalize .` staged no `.md` content, confirming every blob was already LF.

**Do not revisit unless:** a fourth cross-repo state claim is written into a non-historical surface —
struck the same way — or `Q87`'s artefact-parity register is built, at which point the checker /
`closeout.md` parity drift this sweep re-touched gains a named governing rule instead of ad hoc handling.

---

### 186. Governance contract pruned — the contract's job shifts from auditing to shipping

**Decision:** The session-start governance surface is cut to invariants and live principles.
`CLAUDE.md`'s shared block is compressed from ~258 lines of rules-plus-provenance to 97 lines
of invariants only (whole file 453→249, 5,375→2,311 words); the intro essays, number-at-merge
narratives, and every "Earned…" retelling move **verbatim** into `FEEDBACK_ARCHIVE.md` — nothing
deleted. `FEEDBACK.md` is rebuilt (1,328→73 lines, 15,950→1,005 words): the 22 verification-rule
essays (§§7–28) collapse to a one-line index under a new §7; the accreted behavioural corrections
and preferences (§§1–3) move **verbatim** to the archive; §4 survives as **§1 Project principles**
(retitled) and six design-relevant items from old §2 survive as **§2 Design principles**
one-liners (2.1, 2.4, 2.5, 2.6, 2.10, 2.13). §3.5 (Samsung Health package name) is lifted to
`CLAUDE.md` Tooling as one line. **§5 (injury snapshot)** is removed from the live file and
archived under a **SUPERSEDED / stale-as-of-Aug-2026 tombstone**: injury truth is the Postgres
declared-state ledger (`type='injury'`), and its maintained text mirror is project-knowledge
`Athlete_Profile` (chat-maintained) — the archived copy is a record of what once lived there, not
consultable state. **§6 (CPAP context)** is removed entirely (near-duplicate of §1.1's CPAP
specifics, which are preserved in the archive); the canonical clinical facts fold into
project-knowledge `Clinical_Protocol` per the kill-rule (clinical data never lives in the repo).
Two new standing rules enter the shared block — a **severity gate on review** and **governance
batching** (≤1 `gov(...)` commit per session) — and a **moratorium**: no new governance rules,
hooks, or mechanisms until three product items land from — lab-confirm Brief A, lab-confirm
Brief B, interpretation producer 4b, Polar wired into the chat handler. Interim defects get one
condensed `FEEDBACK` line — no essay, no mechanism.

**Rationale:** the session-start read load was ~21,000 words dominated by defect-hunting
epistemology and accreted behavioural corrections — priming every session toward auditing over
shipping; governance had become the product. Provenance is not lost, only relocated to a file
consulted when a rule's origin is disputed. The contract now states the invariants and live
principles and gets out of the way.

**Status:** Landed on `chore/governance-prune` via the PR-gated path. Gates — **G1**: shared block
97 (≤150), whole file 249 (≤250). **G2**: `FEEDBACK.md` **73 lines** (≤200, extended target); the
archive carries all 22 §7–§28 headings verbatim and its §§1–3 (21,689 B) and §§7–28 (75,166 B)
bodies are **byte-identical** to the 4bd99cc original. **G3**: all 18 shared invariants carried
(secrets-rule command-form enumeration restored per keep-longer-form). **G4**: the placeholder
hook fires on `### #NEXT` (exit 1) in both repos, clears when resolved (exit 0). **G5**: the
extracted shared block is byte-identical across both repos (6,135 B, sha256 `622ae8559e81`).
**G6**: decision entries in both repos, moratorium verbatim. **Read-load, measured post-delta**:
`CLAUDE.md` + `FEEDBACK.md`, both read at open, = 2,311 + 1,005 = **3,316 words**, down from
5,375 + 15,950 = **21,325** (an 84% cut). §§1–6 were condensed under an explicit operator
disposition after the first pass measured §§1–3 as the dominant remaining load.

**How you know:** `wc -l`/`wc -w` pre/post recorded above; archive↔original byte-equality proven
by comparing the §§1–3 and §§7–28 slices normalised to LF (21,689 B and 75,166 B, `in`-equal);
the §7–§28 heading grep count in `FEEDBACK_ARCHIVE.md` = 22; `check_governance_placeholders.py`
exit codes captured at both the `#NEXT` and resolved states; the extracted BEGIN…END shared block
diffed byte-identical between the two repos; §6 confirmed absent from both live file and archive
(grep = 0).

**Do not revisit unless:** a defect class recurs ≥3 times that an archived essay demonstrably
would have prevented — at which point that essay earns re-promotion to the read-at-open surface,
and the moratorium is reviewed against the product-landing count.

---

### 187. Re-confirm lab shells bounded and de-noised; a flat current-levels read added (lab-confirm Briefs A + B)

**Decision:** Three changes land together (PR #43, one branch, three concern-split commits),
settling lab-confirm Briefs A and B:

- **(A-write) Re-confirm shells are capped at one per identified document.** `confirm_lab_report`
  no longer mints a fresh `all_markers_declined` shell on every re-submission of a document whose
  markers are all already stored at that `collected_date`. On the all-collision path (`written==0`
  and `resolved`), when the source is identifiable by filename, it returns the existing shell for
  `(user, collected_date, source_doc_filename)` instead of creating a second. **NULL-filename
  guard:** a file-less re-confirm is unidentifiable and is NOT deduped — folding two would collapse
  genuinely-distinct un-named uploads. `no_values_extracted` (empty extraction) is a fault, never
  deduped. This **SCOPES #155 retain-raw** — the document event is still recorded once; only its
  unbounded repetition is removed, and #155/#157's decline-history record is preserved.
- **(A-read) The MCP `get_lab_results` read-back suppresses hollow `all_markers_declined` shells**
  in the formatter's filtering block — before header emission and before `limit`. Presentation
  only: the shared REST projection (`StoredReportOut`) and its upload-history feed are untouched,
  nothing is deleted. `no_values_extracted` faults still render their one-line fault.
- **(B) `get_lab_results` gains `latest_only`** — one row per marker (most recent draw), flat,
  reusing `labs_reads.latest_lab_results` so "latest" is defined in one place. The latest path
  re-projects `LabRow`→`StoredResultOut`, a **second #47 withhold enforcement point** (drops
  `computed_flag`/`is_derived`); the withhold test now covers both paths.

**Rationale:** A production diagnostic (user 1, Railway, read-only) found 10 `all_markers_declined`
shells, **all re-confirm duplicates** (0 genuine declines, 0 `no_values_extracted`), two of them a
second shell for the same `PSA.pdf` — the shells accumulate without bound and are pure noise. Chat's
Brief A proposed suppressing on read; the diagnostic plus a read of the confirm handler confirmed the
mechanism, and the operator elected to also bound them at write time via the least-destructive option
(one-shell-per-document dedupe, NULL-filename guarded), **rejecting** the more aggressive "skip
creating entirely" after its blast radius (four ratified tests, the frontend upload-history split,
#155/#157) was surfaced. Brief B answers "what are my current levels" in one flat glance, which the
report-grouped read cannot.

**Status:** Landed on `feat/labs-shell-dedupe-and-mcp-reads` via PR #43 (merge `e208663`), branch
merged + remote-deleted. Commits `3f63fbb` (write dedupe), `2a40e84` (read suppression), `d733b65`
(latest_only). Backend sweep **168 passed**, 0 failures. **These are two of the four product items
#186's moratorium waits on (lab-confirm Brief A, lab-confirm Brief B) — two of the three needed to
lift it.** Backend deploy probe OWED (see `closeout.md`).

**How you know:** Diagnostic run twice against Railway prod (`railway run --service health-app-DB`,
read-only SELECT); the second re-keyed on marker-at-date after the first's filename-keyed twin join
produced a false "NO TWIN" on the two PSA shells — report 1 holds the populated `psa` 0.7 ug/L row
under `src=NULL`, so a filename join missed it. Every shell's panel then confirmed to have a populated
same-date twin. Behaviour changes only on the 2nd+ filenamed re-confirm; all pre-existing
duplicate/zero-row tests unchanged (13 in `test_labs_zero_row_reason.py`, 10 in
`test_labs_confirm_duplicates.py`). New tests: dedupe + NULL-filename non-dedupe (write);
reason-keyed suppression + before-limit ordering (read); newest-per-marker + latest-path withhold (B).
Placeholder guard green on PR #43 (6s).

**Do not revisit unless:** a genuine `all_markers_declined` shell with **no** populated twin appears —
the read-suppression predicate would then hide a real fault and must tighten beyond
`reason == 'all_markers_declined'`; or the two #47 withhold enforcement points (report projection +
latest re-projection) drift — a field added to one and not the other is the failure the shared
withhold test guards.

### 188. Identity in a uniqueness key means a change of identity forks the record

**Decision:** Record the measured Health-Connect identity cutover and correct the three sites that
still reasoned from the world before it (`models.py` docstring, migration `c9b8a7d6e5f4` docstring —
both this session — and, already corrected 2026-08-05, `routers/health_connect.py`). No deletion, no
migration, no production query is performed by this entry: it is the record, and remediation of the
existing duplicate rows is deliberately deferred to a separate dry-run-gated change. `active`.

**Rationale:** `uq_hc_record_source` is `(user_id, record_type, record_start, source_package)`. `#37`
put `source_package` in the key deliberately, so two apps writing the same `(type, timestamp)` persist
as two rows rather than one overwriting the other — the multi-writer signal `F1` needs — and coalesced
missing identity to the literal `'unknown'` so that a real `NULL`, being `UNIQUE`-distinct from itself,
could not duplicate on every re-sync. Both hold: `nulls = 0` across 42,893 rows, and re-syncs are
idempotent.

What neither anticipated is a change in *what identity is reported*. Health Connect began sending
`dataOrigin` at 05:51:53Z on 2026-07-05, eight minutes after the last identity-less write at
05:43:14Z — a clean cutover, nothing unattributed since. The re-sync that carried it re-ingested
records already stored, now bearing real identity, and the key admitted them as new rows. 10,406
heart_rate keys hold both an `'unknown'` row and an identified twin; the identified side is Polar 7,319
/ Samsung 3,094 / healthsync 468, so the pre-cutover block is mostly workout HR arriving unattributed,
not a Samsung artefact. `healthsync`'s 469 rows all land at a single instant during that sync and are
third copies — a one-shot bridge import, not a source. Withings appears ten days later, totals 33 rows,
and is absent from the contamination entirely.

The distortion is confined to heart_rate and is now bounded: 650 groups are genuine multi-writer once
unknowns are excluded — 6% of the 10,406 a naive `COUNT(DISTINCT source_package) > 1` returns — and
3,533 heart_rate unknowns have no identified twin and are permanently unattributable, which is why the
`'unknown'` sentinel stays. `#35` is untouched: its 286 sleep dup-groups were established on distinct
`dedupe_hash` per app, which a single writer's re-sync cannot produce, and only 11 of them are
contaminated. `Q83`'s two-writer sleep premise is falsified by the same figures (premise corrected,
question stays OPEN); the F1 backend-filter gate on `ROADMAP` is discharged.

The rule: an identity column inside a uniqueness key makes every change in identity reporting a fork,
silently and retroactively. The `'unknown'` sentinel guarantees idempotency across re-syncs; it does
not survive an identity change, because the two rows differ in the key by design. This recurs the next
time any writer starts or stops sending `dataOrigin`. Same family as `#184`/`#185`: a claim true when
written, load-bearing on structure, and false without any surface reporting the change.

**Status:** Landed on `gov/hc-identity-cutover` — four concern-split commits (`models.py` + migration
docstrings; `Q83` premise; `ROADMAP` F1 gate; this entry). Remediation of the existing ~10,881
duplicate rows is **not** in this change — it is production health data and needs a dry-run whose
counts match the figures below before any deletion.

**How you know:** Figures from `railway connect health-app-DB`, operator-run 2026-08-08 (attested
input, not re-derived here; this session opened no production connection). Two arithmetic
reconciliations verified against the attested distribution before use: contaminated-group rows
`21,287 = 10,406 + 7,319 + 3,094 + 468`, and unknowns `13,978 = 10,406 + 3,533 + 5 + 4 + 3 + 27` —
both reconcile. The stale `'no dataOrigin'` clause was corrected at `models.py` and migration
`c9b8a7d6e5f4` this session; the backend-wide grep that found the migration site is #185's
repo-wide-enforcement lesson applied (the 2026-08-05 fix had been file-scoped to
`routers/health_connect.py`). Guard green on the PR.

**Do not revisit unless:** a second writer starts or stops sending `dataOrigin` — the same fork
recurs, and the residue/twin counts above go stale; or the deferred remediation runs, at which point
its dry-run counts must match this entry's figures before any deletion, and a superseding entry
records the collapse.

### 189. Aerobic cross-source arbitration is read-time and derived, not a persisted dedup

**Decision:** Health-Connect exercise sessions and Polar sessions coexist as independent rows in
`aerobic_sessions`; where two rows describe the same physical bout, exactly one is marked `canonical`
at READ time by `reads/aerobic_reads.py` — computed per request, never persisted (no column, no
migration). Polar (`polar_v4` = `polar_flow_export`) outranks `health_connect`; same bout = interval
overlap >= `OVERLAP_THRESHOLD` (0.50) of the shorter duration; ties break longest -> earliest ->
lowest-id. A session with no overlapping cross-source counterpart is canonical. HC ingestion is NOT
built here (see Status). `active`.

**Rationale:** Three things, one decision.

(1) *Coexistence is already assumed by the schema.* `uq_aerobic_session_source` is
`(user_id, source, source_session_id)` — `source` is IN the key, so a Polar row and an HC row for one
bout were always going to be two rows, never one overwriting the other. Nothing new is needed to let
them coexist; what was missing is a rule for which one to trust on read.

(2) *Arbitration is read-time because arrival order is unknowable.* Polar sync and HC sync land in
unpredictable order. Write-time suppression makes the winner depend on which arrived first, and forces
retro-suppression when the higher-fidelity source (Polar, carrying `cardio_load` + zone seconds) lands
second — a wrong row already served, then withdrawn. Computing `canonical` at read is order-independent
and reversible: the same rows yield the same verdict regardless of sequence, and re-ranking after a late
Polar sync needs no rewrite. This is the load-bearing reason; a persisted flag is a separate decision,
deferred until a consumer needs to filter in SQL.

(3) *Distinct class from the #35/#36/#37/#175 admission dedup — do not fold.* That mechanism governs
MIRRORS: one writer re-posting another writer's record, where the copy carries no new signal, keyed in
`health_connect_record_sources`. This governs INDEPENDENT CAPTURES: two sensors each recorded one real
event and BOTH carry signal (Polar: load + zones; HC: duration + type), and the question is which row
is richer, not whether one is a copy. Different substrate (`aerobic_sessions`), different key, different
question. `Q83`/F1 admit-or-exclude a mirror; this ranks two originals.

The `exerciseType` mapping ships with it: `ExerciseSessionType` mirrors HC's official enum (61 codes)
and is published with `x-enum-varnames` for the companion contract; an unmapped code persists with
`sport_id` retained and `sport_name` NULL — the wire field stays a lenient int, so a code we do not
recognise never 422-rejects a sync and is never assigned a guessed sport.

**Status:** Landed on `feat/aerobic-arbitration-read`. **Ingestion (brief steps 2-3) is HELD, not
deferred-by-oversight:** an HCA-rooted read on 2026-08-10 confirmed `workoutMapper` forwards six fields
and NO record identifier, so `source_session_id` has no key to carry and the upsert is not written. The
synthetic-key fallback (`{startTime}|{sourcePackage}`) is deliberately NOT invoked — it is licensed for
"identifier proven absent or unstable", a different state from "producer not yet wired"; collapsing the
two would bury the finding. The module therefore runs today over Polar-only rows (every row canonical)
until HC ingestion lands. Consumers: `GET /integrations/polar/aerobic-sessions` is wired through the
module and surfaces `canonical`; the raw-SQL aggregate consumers (`get_training_load` ACWR, readiness
`session_stats`) are not clean drop-ins and are deferred with ingestion — ACWR maths untouched.

**How you know:** `pytest` 785 green (771 prior + 14 new). G2 (Polar + fixture HC overlapping -> exactly
one canonical, the Polar one) proven at the pure, DB, and HTTP layers; G3 (lone + active-recovery HC ->
canonical) at pure + DB; G4 (unmapped code -> NULL, no exception); G5 existing HC sleep/HRV/steps
aggregation byte-identical (`_aggregate_day`, `valid_dates` untouched). Enum contract verified against
`app.openapi()`: `ExerciseSessionType` present with 61 values and index-aligned `x-enum-varnames`,
`SleepStageType` varnames unregressed. Values mirrored from androidx-main `ExerciseSessionRecord.kt`
(61 defined in [0,83], gaps unassigned).

**Do not revisit unless:** HC exercise ingestion lands (step 3) — at which point G1 (an HC row appears,
re-sync idempotent) becomes live and this entry's "Polar-only, all canonical" note goes stale; or a
consumer needs to filter non-canonical in SQL, the trigger to reconsider persisting the flag; or
`OVERLAP_THRESHOLD` is recalibrated against real pairs (`Q88`).

### 190. Status generators gate on extraction, not only on counts

**Decision:** Every governance status generator runs, alongside a crude dialect-agnostic heading/row
count checked against its own parsed count, an EXTRACTION gate: if a state field resolves empty across
all N>0 parsed items of a store, it HALTs and emits nothing. Off-vocabulary state tokens are tallied
per field and reported as drift — never coerced into a neighbouring state, never dropped. Count parity
is necessary but insufficient. `active`.

**Rationale:** `gen_governance_view._status_from_body` matched a question's state as `**Status:**`
while health-app `OPEN_QUESTIONS.md` uses `**State:**`, so every one of the 89 health-app questions
rendered with an empty status. The count and parsed-vs-emitted gates never saw it: heading counts
still matched, so the parse "succeeded" against a field that was never there. A count gate is
structurally blind to a field present in form and empty in fact. The extraction gate is the missing
check.

**Status:** Landed on `status-parser-gate`. Live in `gen_status_model.gate_extraction_nonempty` and in
`gen_governance_view` (the all-empty question check). The `**State:**` bug is fixed in the same session
by centralising the state-line grammar to match `**State:**|**Status:**` (`#191`).

**How you know:** `python scripts/gen_status_model.py --self-check` fires all three gate positives
(count parity, sequence gap, extraction-empty) and confirms off-vocab is tallied not halted. The real
positive: run over the live health-app `OPEN_QUESTIONS.md` with the buggy `**Status:**`-only matcher,
the count gate passes (`crude=89 == parsed=89`) and the extraction gate HALTs (`state extracted EMPTY
for all 89 items`, exit 1). After the fix both generators run clean and every health-app question
carries a state.

**Do not revisit unless:** a store legitimately introduces a stateless item class (then the all-empty
gate needs a per-class exemption, not a loosened threshold), or a new governance generator is added
that does not import the shared gate.

### 191. Store dialect knowledge lives in one module

**Decision:** The heading regexes, state-line labels and state-vocabulary constants for both repos'
governance stores live in exactly one module — `scripts/gov_dialects.py` — which every governance
generator imports. No generator carries its own copy of the grammar. Scope is dialect grammar only:
not fetch, not emit, not gates. `active`.

**Rationale:** The two repos do not share store schemas (health-app `## Q88.` with a `**State:**` body
line vs HCA `### Q11 — … · OWED` inline; `## N.` vs `### #20 —` decision heads), and more than one tool
now parses them — the markdown digest (`gen_governance_view`) and the machine model
(`gen_status_model`). The `**State:**` defect (`#190`) is what independent dialect knowledge looks like
once one copy goes stale: a single tool's private regex drifted from the store and nothing reconciled
it. One import site is the structural fix; keeping the module to grammar only bounds its blast radius.

**Status:** Landed on `status-parser-gate`. Both generators import `gov_dialects`; the shared surface is
the decision/question heading patterns, the `**State:**|**Status:**` line, the vocabulary sets, and the
extractor/classifier over them.

**How you know:** both generators run green against live master importing the one module; the
`**State:**` fix applied once in `gov_dialects.STATE_LINE` corrected the digest with no second edit.

**Do not revisit unless:** a store's grammar diverges so far a shared pattern would have to hedge both
ways — then the module holds two named dialects, still one import site, never a per-tool copy.

### 192. Cross-repo status snapshots live outside both repos; snapshots are derived, not truth

**Decision:** The cross-repo status model writes append-only JSON to `Projects/_status/` — outside both
repos — as `snapshots/<ISO8601>_model.json` plus `latest.json`. Snapshots are DERIVED observations; the
governance stores at each repo's master are canonical. Each snapshot records the master SHA it read per
repo (provenance) and a `baseline` flag for the first snapshot with no predecessor. `active`.

**Rationale:** The cross-repo view cannot live inside one repo without recreating a two-master pattern.
Deleting the store costs ageing history (the diff baseline), never correctness, since the model
regenerates from the stores at any time. Accepted loss, stated rather than left implicit: the directory
is unbacked and single-machine. Baseline flag and per-repo provenance are built in from the first
snapshot because retrofitting either costs a format migration — a baseline-less first diff reads as "no
change" instead of "no comparison available"; a provenance-less snapshot is not reproducible.

**Status:** Landed on `status-parser-gate`. Snapshot #1 seeded 2026-08-10 to
`Projects/_status/snapshots/2026-08-10T115614Z_model.json`, `baseline:true`, provenance
health-app@`fbc86e9` + health-connect-app@`255014a`; `latest.json` byte-identical; a README in the
directory records the accepted loss.

**How you know:** the seed run wrote valid JSON, `latest.json` `cmp`-identical to snapshot #1, the
baseline flag true, both repos' provenance SHAs present, and the one drift finding recorded (HCA
questions carry `UNSTARTED×6`, `Q90`).

**Do not revisit unless:** the ageing history must survive a machine loss (then the directory needs a
backing/sync decision — a new decision, since this one accepts the loss), or a consumer needs the
snapshots inside a repo (re-derive the two-master argument first).

### 193. Status tooling is anchored in health-app; health-connect-app is read-only

**Decision:** Cross-repo status tooling is anchored in health-app, the senior governance store. HCA's
governance stores are read over `raw.githubusercontent.com` at master, never cloned and never written
in a status-tooling session. Single-repo-per-session is preserved because the constraint is on writes.
`active`.

**Rationale:** Cross-repo tooling needs one governance home with a DECISIONS_LOG; health-app is it.
Reading HCA read-only — the same mechanism `gen_governance_view` and the session-open ritual already use
— does not breach single-repo scope, which constrains loop-affecting writes, and those stay health-app
only. The snapshot data still lands outside both repos (`#192`); the code and its decisions live in
health-app.

**Status:** Landed on `status-parser-gate`. `gen_status_model` resolves each repo's master by
`ls-remote` and fetches stores by raw URL; no HCA clone, branch, or commit exists in this session.

**How you know:** the session touched only health-app's working tree; HCA content was fetched read-only
at `255014a`.

**Do not revisit unless:** HCA becomes the senior store (it will not), or a status tool needs to WRITE
an HCA store — at which point it is no longer a status tool and the single-repo rule bites.

### 194. Interpretation go-live: first live run against the 2026-08-04 draw; assets promoted on human verification; #51 status is convention, not code

**Decision:** Interpretation increment 5 (go-live) is landed. The 2026-08-04 draw — 11 reports, 51
markers, canonical binding near-total (only `_ROUTINE CHEMISTRY` at 16/18: `Bilirubin conjugated`,
`CK` unmapped) — is the producer's first real consumer. On Luke's content verification (O2, worksheet
of 36 authored claims, no issues found), the three reference assets' `_meta.status` and the six levers'
`draft_status` are promoted `ai_draft → human_verified`. The stale `_deferred.groups.erythroid` ledger
entry is removed: the group was already promoted into active `groups` (with `mcv` added) and surfaces
live, so the deferral note contradicted the built state. The four go-live items resolve as: **(a)**
real-panel confirm — done pre-session via the #187 dedup path, census-confirmed, not re-done here;
**(b)** asset promotion — done here on O2 verdicts (the erythroid GROUP promotion was already discharged;
the `trt_erythrocytosis_watch` relation stays `blocked_on_contract`, unrelated to O2); **(c)** view-pointer
swap — already discharged at #158 (view reads `GET /interpretation` live); **(d)** fixture⇄asset drift —
none: deterministic regeneration of `interpretationExample.json` is byte-identical.

**Rationale:** Go-live is a promotion event, not new behaviour. Nothing in the producer changed; the
first live run exercises the already-built path against real data, and the promotion records that a
human verified the authored content. Layperson-readability is deliberately NOT addressed here: the
verified base text stays clinically precise, and simplification is increment 2's (rephrase) job — a
presentation layer over the base text with a hard eval that rephrase-may-not-change-claims. Verifying
now and simplifying in increment 2 is the intended split, not a contradiction (see ROADMAP refinement
routing).

**#51 enforcement-locus finding:** No code reads asset `_meta.status` or a lever's `draft_status`. The
producer reads only `_meta["version"]` (`producer.py` `_meta()`), and the frontend has no status gate.
#51's "nothing renders Section 3 until `human_verified`" is a **curation convention enforced NOWHERE in
code**. Recorded here, not mechanised — building an enforcement gate unbidden is exactly what the
moratorium forbids. Opens **Q92** (gate-in-code vs stay-convention).

**Moratorium (3/3):** #186's three-item moratorium set named "interpretation producer 4b"; 4b actually
landed #140–#160 on 1 Aug — pre-moratorium. This increment is the lane's next real product step and
satisfies the third slot in spirit, stated plainly so the count is honest, not gamed.

**Status:** Landed on `feat/interpretation-go-live`. Backend suite **785 passed**. Reference-JSON edit
guard (#98) re-asserted post-edit on all three files: `isascii()` True, zero literal em-dash, still
parses; diff is the status fields plus the declared erythroid `_deferred` removal and nothing else.
Fixture regeneration zero-diff.

**How you know:** First live run captured by mirroring the router (`_panel_for` + `build_foundation`,
compute-on-read, no writes) against the Railway store via the public proxy. Trigger draw 2026-08-04
(panel id 44) vs prior 2026-05-30 (panel id 1); output = 3 groups [`hpg_axis`, `hepatocellular`,
`erythroid`] + 56 ungrouped. Haematocrit 0.50 fires the safety arm at the band boundary by design:
`safety_gate = {status: in_band, band_key: watch, threshold_value: 0.5, direction: above, contested:
true, evidence_refs: [10.1002/ajh.70118, 10.1002/ajh.26920, 10.1111/andr.12770], band_change: entered}`;
`news_gate.basis = [delta_marginal, safety_band_entered]`; `range_gate.is_out_of_range = false`. Rendered
register is education, not urgency: the view shows a neutral `news` pill + mechanism/relation prose, no
`BreachIndicator` (0.50 is within ref 0.40–0.54), and surfaces no action directive (G4). MCP surface
carries no interpretation fields — `mcp_server.py`'s only `interpretation` strings are ACWR; labs are
"Not interpreted" (#47/#181, G5).

**Do not revisit unless:** Q92 decides status should gate rendering in code (then the convention becomes
a mechanism and this promotion's meaning changes), or a future draw shows the producer path behaving
differently on real data than the fixture oracle predicts.

### 195. `discriminator` names the EVIDENCE, and becomes a list (resolves Q36)

**Decision:** In every `marker_groups.json` relation, `discriminator` names the evidence marker(s);
`operands` are the markers being explained. The field is promoted from single string to list.
`bilirubin_isolation` is re-authored to conform (its current field contents are swapped);
`haemoconcentration_discriminator` gains `protein_total` as its second list member, which until now
survived nowhere a renderer could reach.

**Rationale:** 2 of 3 authored relations already read evidence-in-field, and the word's plain meaning is
"the thing that discriminates". The alternative re-authors two relations and renders the haemoconcentration
artefact-vs-expansion call backwards until done. The list promotion is forced by a live relation with two
genuine evidence markers, not by speculation.

**Status:** OWED — decided, not implemented. Implementation: asset edit ×2 + schema/renderer contract
update, own concern-split commit in a product session.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q36; OWED — no implementation artifact yet.

**Do not revisit unless:** the implementing product session lands it (status → landed), or a fourth
relation contradicts evidence-in-field.

### 196. I1's read-constant extension is ENFORCED; `alt` is cited first (resolves Q37)

**Decision:** `gates.py` reads `evidence_refs` at fallback time: a gate-driving constant with empty refs
falls back to `_defaults`. Citations become load-bearing at runtime, as #95's extension intended.
Precondition, Luke-owed per the #98 pattern: pin `alt`'s CVi source to a DOI so 0.45 lands cited and
enforcement is behaviour-neutral on day one. Fallback ruling, stated now so it needs no second decision:
if the DOI cannot be pinned, enforcement proceeds anyway and `alt` drops to `_defaults` 0.30 — the
false-positive direction, which is the safe way to be wrong.

**Rationale:** Narrowing I1 would retroactively make #96's withholding of the haematocrit/haemoglobin
constants stricter than the rule required; enforcing makes the invariant real and vindicates it. Canon
and code stop documenting opposite intents.

**Status:** OWED — decided, not implemented. `alt` DOI capture: owner Luke, receipted.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q37; OWED — no implementation artifact
yet; `alt` DOI is a Luke-owed receipt per the #98 pattern.

**Do not revisit unless:** implementation lands, or the `alt` DOI capture forces the cold-fallback path.

### 197. `min_meaningful_delta` becomes interval-banded (resolves Q38; closes Q71)

**Decision:** Erythroid constants gain a second interval band: gap ≤ ~4 months (one erythrocyte turnover,
per Coşkun's own stated validity bound) → the landed 0.08-family values; gap > 4 months → 0.15 (Thirup
2003, the 6-month figure). Interval = delta of `collected_at` between the two draws in the delta. Two
bands, not a continuous widening factor — the literature anchors exactly two figures, and a function
would invent precision. Other markers stay single-band until interval-resolved data exists for them.

**Rationale:** This repo's draw cadence is months apart crossing seasons — the wide-interval case is the
normal case, and the single tight constant was producing the status quo by default rather than by
decision. Q71 (the same hole, minted independently against gate 1) is answered mechanically by the same
change and closes to this entry.

**Status:** OWED — decided, not implemented. Composes with the rise/fall pair ruling (#199) into ONE
schema change: `min_meaningful_delta` = list of bands, each band a `{rise, fall}` pair; see that entry.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q38 and closing Q71; OWED — no
implementation artifact yet.

**Do not revisit unless:** implementation lands, or interval-resolved data appears for a non-erythroid
marker (then it too gains bands).

### 198. Levers gain `effect_locus` (resolves Q39)

**Decision:** As proposed in Q39, unmodified: `effect_locus: physiology | measurement` on
`lever_dictionary` nodes, default `physiology` so every existing lever is correct without edit;
`plasma_volume_status` is authored `measurement`. The renderer never ranks a measurement-locus lever
alongside physiology-locus ones — distinct labelling or a separate strip, never one ordered list.

**Rationale:** `plasma_volume_status` changes what the number measures, not what it is; un-flagged it
renders as a peer of TRT dose and invites chasing an artefact. `channel` cannot carry this (orthogonal
axis, per #100's explicit decline).

**Status:** OWED — decided, not implemented. Additive; zero edits to existing levers beyond the one
`measurement` authoring.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q39; OWED — no implementation artifact yet.

**Do not revisit unless:** implementation lands, or a lever needs a third locus value.

### 199. `min_meaningful_delta` is a rise/fall PAIR for all markers (resolves Q40)

**Decision:** The scalar is replaced schema-wide by a `{rise, fall}` pair, derived asymmetrically (Fokkema
2006, log-normal, two-sided Z = 1.96 per the Q38 convention) from the same CVA/CVI inputs that produced
each landed scalar. Erythroid pairs will come out near-equal (CVI 0.72–2.82%, inside the convergence
region) — derived anyway, not copied, so the asset is uniform. Markers whose scalar was NOT
derivation-backed carry `{rise: x, fall: x}` from the existing value, flagged as symmetric-legacy pending
derivation. `oestradiol` (CVI ≈14%, the one marker in the divergent region today) gets a genuinely
asymmetric pair. Gate 1's delta arm compares a rise against `rise` and a fall against `fall`; `abs()`
comparison is retired.

**Rationale:** Chat's lean was an oestradiol-only pair; overruled by Luke for the uniform schema — one
shape everywhere beats a special case, and any future high-CV marker (hormonal panel candidates are the
obvious class) lands into a schema that already expresses it. Composed with the interval-band ruling: the
unified shape is `min_meaningful_delta: [ {interval_max_days, rise, fall}, … ]`, single-band equal-pair as
the degenerate case.

**GUARD for the implementing brief:** derive the oestradiol pair from the asset's actual CVA/CVI inputs —
chat's ~+47%/−32% figures were rough and are NOT to be transcribed. If the inputs behind 0.42 cannot be
recovered from the asset or its citations, stop and report rather than reconstruct.

**Status:** OWED — decided, not implemented. One schema change shared with the interval-band entry (#197);
one derivation pass; gate 1 comparison change; I1 applies (pairs are read-constants — citations carry over
from the scalar's refs where derivation-backed).

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q40; OWED — no implementation artifact yet.

**Do not revisit unless:** implementation lands, or the oestradiol CVA/CVI inputs prove unrecoverable
(then the GUARD's stop-and-report fires).

### 200. CBT-I is scoped OUT of the consumer product; verdict surfacing cleared (resolves Q60 Fork 1)

**Decision:** The CBT-I module is a personal/household instrument, permanently outside the consumer-facing
product surface and the commercial path (B2B and consumer). Ruled by Luke 2026-08-10, binding.
Consequence: #47's regulatory rationale (TGA SaMD, supplied product) does not attach to this module, and
the engine's MOVE/HOLD verdict may surface plainly on the user surface — the only reader is the author of
the rules being executed. This is a scope ruling, not a rider on #47: #47 is untouched and continues to
bind every consumer-facing surface.

**What the ruling settles beyond Fork 1:** (1) The engine's divergence from the VA CBT-I document (#165's
hunting search, cadence, gates) is unproblematic — bespoke titration logic surfaced to its own author
needs no external evidence base, only honest labelling. (2) Q55 (four gate constants chosen, not derived)
is confirmed as a tidy-up, never a gate — un-grounded constants driving directives is an exposure only
when the verdict reaches someone who didn't choose them, which this ruling forecloses. Annotate, don't
block. (3) Q78 (multi-user nap attribution) is UNCHANGED — household users are not consumers, so it still
guards a second household block; priority unaffected.

**Boundary, stated so drift is legible:** if the commercial path ever wants sleep features, that is a NEW
product decision made then — not an extension of this module, whose scope this entry fixes.

**Status:** active. Unblocks the interim surface — see Q60's closure for its shape.

**How you know:** Operator ruling (Luke), 2026-08-10, binding; a scope ruling, not a code artifact.

**Do not revisit unless:** the commercial product proposes a sleep feature.

### 201. `computed_flag`/`confidence` stay off the raw labs read-back — rationales corrected (resolves Q61)

**Decision:** Both fields remain omitted from `GET /labs/results`, re-decided on honest grounds replacing
the misapplied #47 label: `computed_flag` is excluded by the #49 raw/interpreted seam — this endpoint's
provenance is the report (values, ranges, the lab's own `lab_flag`); `computed_flag`'s provenance is our
derivation, which belongs to the interpretation surface. `confidence` is excluded as extraction QA, not a
clinical read — its correct audience already has it, at confirm time, on the Brief-B confirm screen;
per-row at-a-glance display misleads. The two rationales are deliberately separate and independently
supersedable.

**Rationale:** Q61 established #47's text does not bound a range comparison out of an education surface.
The omission survives on different merits; the mislabel is retired so no future session inherits "settled
by #47" for a bound #47 never drew.

**Status:** active. Implementation: docstring/comment relabel in `routers/labs.py` only — no behavioural
change.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q61; the omission is unchanged behaviour —
only the recorded rationale changes.

**Do not revisit unless:** either rationale is independently superseded, or a consumer needs
`computed_flag`/`confidence` on this endpoint.

### 202. Generated prose is permitted in REPHRASE FORM ONLY, structurally gated (resolves Q62)

**Decision:** The interpretation layer may generate prose under exactly one form: rephrase of the
templated assembly. Structural properties, all mandatory: (1) the generator's input IS the templated
assembly built from reviewed asset fragments and arithmetic over the user's data — it sees nothing else;
(2) structured fields remain the record; prose is a discardable overlay, never parsed back, never
load-bearing; (3) a mechanical validator gates every output — no named entity or numeral absent from the
input, no directive mood, no priority vocabulary not present in the source; (4) fail-closed to template:
on any rejection the templated assembly renders — the safe artifact exists independently of generation
succeeding. Granularity dial: fragment-wise rephrase (order preserved by construction) for anything gate-
or verdict-adjacent; whole-block rephrase for mechanism/education prose, where emphasis carries no
prioritisation weight. Training wheels: first 2–3 panels route through the existing `ai_draft →
human_verified` promotion gate (#194 precedent: `lever_dictionary`, `marker_groups`), dropped once the
validator earns trust. Prompt-only generation (Q62 option c) is foreclosed permanently — #59 already
established instructed-against is not structural, and behavioural controls are model-version-variant where
structural ones are not.

**Rationale:** Rephrase is the one generation class with a checkable contract ("says what the input says"
is verifiable; "is good and safe" is not), and the one where a reject set stays small, enumerable, and
mechanical rather than a behavioural rule wearing a schema. The three leak modes — additive drift,
modality drift, priority-by-emphasis (#47's own "personalised prioritisation = prescription" line) — are
each addressed structurally: (3) catches the first two; the granularity dial confines the third to where
ordering cannot imply importance.

**Consistent with:** #47 (structural half restored for generated fields), #59 (the precedent this
generalises), #152/#154 (structured fields stay the record).

**Status:** active — binds increment 2 (rephrase pass) before it is built. OWED: validator + dial
implementation land with that increment, not before.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q62; binds increment 2's spec —
validator/dial are OWED with that increment.

**Do not revisit unless:** increment 2's build finds the validator contract unbuildable as specified, or a
non-rephrase generation class is proposed.

### 203. `mechanism` projects onto ungrouped rows; `stable_rationale` stays grouped-only (resolves Q64)

**Decision:** Of the two marker-authored member fields, `mechanism` — which explains what the marker is
and always applies — projects onto `ungrouped[]` rows; `stable_rationale` — gate-adjacent judgement
annotating a persistently-flagged marker — remains scoped to grouped members. Ruled (c) over chat's weak
lean (a): the split keys on function, not authorship — an ungrouped marker deserves its explanation;
whether it also carries not-news judgement stays an open cost until something concrete needs it.
`vitamin_d_25oh` gains its mechanism.

**Status:** OWED — decided, not implemented. Small producer change + Ungrouped-section view touch (the
section shipped at 1b on status quo, so this is a follow-up edit, not a rider). Group-derived fields
(`relations_rendered`, `member_lever_effects`) remain structurally absent from ungrouped rows — by
construction, unchanged.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q64; OWED — no implementation artifact yet.

**Do not revisit unless:** implementation lands, or a concrete need appears for `stable_rationale` on an
ungrouped row.

### 204. Relation condition shapes COMPOSE — `precondition` becomes an optional modifier on any kind (resolves Q67)

**Decision:** Any relation, regardless of `kind`, may carry an authored `precondition`;
`_relations_rendered` resolves it wherever present instead of only on `kind == "feedback"` (retiring the
hardcoded `precondition_status: "not_applicable"` for other kinds). `feedback_precondition` is thereby a
modifier, not a peer shape. `hpg_substrate_co_movement` is authored with its phase condition ("stable
dosing") as the first non-feedback carrier.

**Rationale:** Kind-implies-shape was already falsified by the live asset (`haemoconcentration_discriminator`,
per #154); composition is the honest generalisation and the smallest change that lets the one
phase-conditional relation state its condition machine-readably. Splitting the relation (b) would author
one piece of physiology as two entries; prose-only (c) reintroduces the reader-does-the-branch-work
problem #154 exists to remove.

**Status:** OWED — decided, not implemented. Producer change + one asset authoring; touches the
co-movement shape work Q67 was blocking, which is now unblocked.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q67; OWED — no implementation artifact yet.

**Do not revisit unless:** implementation lands, or a relation needs a condition shape that composition
cannot express.

### 205. Censored deltas stop asserting a comparison that never ran (resolves Q70)

**Decision:** Options (a)+(d). `delta()` on a censored comparison emits a distinct basis token —
`delta_magnitude_unknown_censored` — never `delta_within_min_meaningful`, which asserted a threshold read
the code did not perform. The view renders censored deltas as "magnitude not computable". Surfacing
verdicts are untouched — on the live panel they are correct via the phase relation, and demotion's
predicate is explicitly NOT widened to reach this case (Q65/#154 own that boundary). Option (c), the
bound-aware magnitude floor (`|prior − bound|`), is declined unless a real panel turns on it — the phase
relation answers every live case, and the floor buys precision nobody is currently misled without.

**Rationale:** The invariant was holding by accident — right verdict, wrong route, the #156/#157 shape.
Honesty of the basis tokens is a precondition for ever showing them to a reader or generating prose from
them (which #202-rephrase now sanctions), so the fix lands before either consumer exists.

**Status:** OWED — decided, not implemented. Gate/token change + view string; test asserting censored
pairs never emit the old token.

**How you know:** Operator ruling (Luke), 2026-08-10, resolving Q70; OWED — no implementation artifact yet.

**Do not revisit unless:** implementation lands, or a real panel turns on the declined bound-aware floor
(option c).

### 206. `max_velocity_ms` is homed in a new passively-observed §E region; the engine may read it, never schedule it (resolves Q72)

**Decision:** Resolves Q72. `max_velocity_ms` enters the capability taxonomy as a new top-level §E region
with `per_side=False` (trunk-mounted GPS records one figure and cannot attribute it to a leg — instrument
property, per the per-side-on-Measure correction), `needs_norm=False` (self-referenced against own season
peak; the quantity of interest is re-attainment fraction, not an external standard), and
`queue_eligible=False` (Probe must never initiate a maximal sprint onto two velocity-gated hamstrings;
this flag is what makes the region safe to exist). This creates a new region class — passively-observed:
data arrives only from match/training GPS capture, the engine reads but never initiates. Distinct from
§G's norm-blocked exclusion, where observation is suppressed entirely. Future match-derived measures
(accelerations, collision counts from the same IMU stream) join this class rather than re-deriving it.
Placement over the Locomotion-fold variant is deliberate: the class deserves a visible home, not a flag
buried in an axis.

**Status:** active (ruled 2026-08-11, Doc-8 shape). OWED: taxonomy authoring of the §E region.

**How you know:** Operator ruling (Luke), 2026-08-11, resolving Q72; a ruling, not yet authored into the
taxonomy.

**Do not revisit unless:** a passively-observed measure needs the engine to initiate capture (it must
not), or §E needs a per-side member.

### 207. Unified inline-state reader; per-repo question vocabulary; decisions best-effort, never extraction-gated

**Decision:** Completes `#191`'s centralization. `gen_governance_view` retired its private
`_split_inline_status`/`_status_from_body` and now consumes the shared `gov_dialects` reader: decisions
read via `decision_state` (scan-based lowercase `·` channel + `**Status:**` body), questions via
`entry_state` (caps `·` inline + `**State:**` body). The HCA lowercase decision channel's vocabulary is
enumerated empirically `{active: 34, held: 1}` across all 35 entries; lineage segments
(`clarifies`/`supersedes`/`rider`/`repair`, each carrying a `#N`) are never state and are scanned past.
Question vocabulary is per-repo: HCA `OPEN/OWED/DONE/UNSTARTED`, health-app `OPEN/OWED/DONE`. The shared
`QUESTION_STATES` tuple is unchanged and the `gov_dialects:44` position — an `UNSTARTED` on a health-app
question is drift, not a first-class state — is reaffirmed and asserted in `--self-check` both directions
(G6). Decision state is best-effort: `unstated` where no channel yields state (the 17 health-app decisions
with no `**Status:**` line, stable id set `#35, #43–#45, #79–#84, #129–#134, #170`; optional-by-convention
per the 2026-08 census), never a defect. `gate_extraction_nonempty` scope is untouched (questions + branches
only).

**Rationale:** The two readers had verifiably diverged — the machine model (`gen_status_model`) read HCA
decisions as *missing* (caps-only, `rsplit`-last), while the digest (`gen_governance_view`) rendered lowercase
state with lineage junk (`active · clarifies #6`) on the six multi-`·` headings. That is the drift `#191`'s
single-grammar module exists to prevent, reintroduced because the digest kept a private reader. One reader,
both tools, closes it. Recognising HCA's `UNSTARTED` via *per-repo* vocab — not the shared tuple — recognises
the HCA dialect without silencing health-app's drift signal.

**Status:** Landed on `feat/status-reader-channels` via PR #56 (merge `e4c7dba`), PR-gated path (`#171`);
branch merged + deleted. Three scripts, no store schema change, no migration.

**How you know:** Reader agreement verified at master `c65e604` — 0 disagreements across 241 decisions + 116
questions, both repos; the six multi-`·` HCA decisions (`#8, #11, #14, #19, #23, #25`) render bare `active`.
Census invariants reproduced: 17 `unstated` (id set above, stable across the 193→206 growth), HCA decisions
`{active:34, held:1}`, `UNSTARTED×7` clean, drift `[]`, gapless both repos, crude==parsed every cell.
`--self-check` green including the G6 both-direction drift assertion.

**Do not revisit unless:** the HCA decision inline vocabulary grows beyond `{active, held}` (a new lowercase
token surfaces as `unstated`, prompting re-enumeration, not silent coercion); or a private state reader is
reintroduced into either tool (the divergence this closes recurs); or an `UNSTARTED` is authored on a
health-app question and intended as real state rather than drift (the per-repo split would then be revisited).

### 208. The #186 moratorium is lifted and replaced by a mint filter, not a schedule

**Decision:** #186 was a volume brake, minted after a review found the governance layer had over-corrected —
governance had become the work rather than what enables it. It was reduced and refocused; the brake has
served. Lifting it. In its place, the standing test: a rule mints only where the session's primary objective
was product or tooling, the rule was discovered by that work rather than sought, and it is the minimum that
closes what was found. A session that opens on governance, or that mints beyond the defect it hit, fails the
test. No scheduled governance review — a recurring review generates rules to justify itself, which is the
failure this exists to prevent. Instead, the status report surfaces rules unreferenced since mint, and
pruning happens on that signal at Luke's discretion. #190 and #191, minted while #186 was live, stand under
this test. Supersedes #186.

**Rationale:** A volume brake is a blunt instrument — it slows good mints and bad alike. A filter keyed on
provenance (primary objective, discovered-not-sought, minimum-that-closes) discriminates instead of throttling,
and the unreferenced-since-mint signal turns pruning into evidence-driven housekeeping rather than a scheduled
ritual that must find work to justify its cadence.

**Status:** active. Supersedes #186.

**How you know:** `mint filter` is absent from `DECISIONS_LOG.md` (0 occurrences, verified 2026-08-12 at
master `4c02763`); adjudicated LAND-UNCHANGED in this session's Step 0 — the premise is independent of #207.

**Do not revisit unless:** a scheduled or recurring governance review is proposed again, or the status
report's unreferenced-rule signal proves insufficient to drive pruning in practice.

### 209. The extraction gate covers questions and branches; decisions are governed by sequence

**Decision:** Re-measured 2026-08-12 at master `4c02763` via the post-#207 unified reader
(`gen_status_model --dry-run`): zero missing state across questions and branches in both repos; **17 of 207**
health-app decisions carry no state (`unstated` — best-effort, never a defect, the stable id set named in
#207); and all **35 of 35** HCA decisions carry state in a lowercase inline `·` channel (`{active: 34,
held: 1}`), which #207's unified reader now reads (HCA decisions `unstated=0`) — the earlier "neither
generator reads HCA's inline channel" no longer holds. Decision `**Status:**` is optional by convention and
the two repos' decision dialects differ; extending `gate_extraction_nonempty` to decisions would halt both
stores permanently while catching nothing. Decisions remain covered by the sequence gate. #207 already holds
this scope untouched (questions + branches only); this entry formalises that as the ruling.

**Rationale:** The extraction gate exists to catch a MISSING state where state is mandatory. On decisions,
absence of `**Status:**` is convention (17/207 omit it deliberately, including ledger entries #129–#134), not
omission — a gate there would fire on the convention, not a defect, and would halt permanently while catching
nothing real. Sequence, not extraction, is the right guard for decision integrity.

**Status:** active. Confirms and formalises the scope #207 left untouched.

**How you know:** re-measured via the landed reader at `4c02763` — health-app 17 `unstated` / 207 (gapless),
HCA `unstated=0` (channel now read), `drift []`; adjudicated AMENDED in Step 0 (ruling preserved, premise
figures updated from the pre-#207 `17/193` and the "neither generator reads" claim to the post-#207 ground).

**Do not revisit unless:** the two repos' decision dialects converge so that state is reliably present on
every decision (a gate would then catch omissions rather than convention), or the sequence gate proves
insufficient to catch a genuinely mis-sequenced decision.

### 210. Governance placeholders in code use `#NEXT`, never `#N`

**Decision:** A bulk `#N` → number substitution mangled a docstring where `#N` meant "the highest number."
Caught by inspection, not by a gate, on a class of edit that recurs every session. `#NEXT` is already the
store convention and the placeholder guard already scans for it.

**Rationale:** `#N` is ambiguous — it reads as both a placeholder-to-resolve and a literal token meaning
"some number N" in prose. `#NEXT` is unambiguous, already the convention in the stores, and already gated, so
a bulk resolve pass can never mistake explanatory prose for a placeholder.

**Status:** active.

**How you know:** the `#N`-meaning-"highest number" mangle was caught by inspection, not a gate; `#NEXT` is
the store convention and the placeholder guard scans `^### #NEXT` / `^## Q#NEXT`
(`scripts/check_governance_placeholders.py:75-76`, verified 2026-08-12). LAND-UNCHANGED in Step 0.

**Do not revisit unless:** the placeholder token itself changes, or a gate is added that scans bare `#N`
directly.

### 211. Catalogue freshness is sync-on-workout-fetch, staleness-gated on a per-user marker — Q75 resolved as option (c)

**Decision:** The Hevy template catalogue refreshes by piggybacking a per-user template sync
(`sync_exercise_templates(only_user_id=…)`, which reuses `sync_one_user` under #77 isolation) on the
workout-fetch path (`GET /integrations/hevy/workouts[/all]`), gated on the per-user marker
`user_integrations.templates_synced_at` older than 24h (`_CATALOGUE_STALE_AFTER`, constant). No scheduler
(option a rejected: a new failure surface for drift no read has yet needed); no sync inside pure read
paths that don't already imply a live key and a present user (option b rejected: a network call on a
currently-pure read, so a Hevy outage would degrade reads that today succeed). Sync failure never fails
the fetch (#77 isolation inherited, and the call additionally wrapped so any escape is logged and swallowed).

**The staleness signal is a per-user marker, NOT an aggregate over `hevy_exercise_templates.synced_at`.**
That column is per-row and stamped by every upsert; a full `sync_one_user` re-stamps ALL 451 defaults, so
`MAX(synced_at)` over a user's visible scope reads FRESH the moment ANY user syncs — reporting a current
catalogue while this user's own customs are stale. Wrong now that multi-user is live (4 users in prod,
though only user 1 holds customs today). The marker is stamped by `sync_one_user` on a completed pull —
the one primitive every caller routes through (operator route, connect-seed, create-loop) — so it can
never claim a freshness no code path produced. Migration `e2d5c7a1b9f3`; NULL (never synced) reads as
stale and a first fetch syncs (self-healing, no back-fill).

**Rationale:** The 2026-08-05 incident discriminated the axis empirically: workouts synced while templates
did not (store `max(synced_at)` 2026-08-04, before the incident; two of the three Aug-5 customs absent),
so the exact traffic option (c) piggybacks was present and would have caught the drift. Customs created
in-session at a new venue are Q75's second drift vector occurring as predicted, up to and including the
duplicate-mint offer Q75 warned of.

**Status:** active. Q75 resolved (DONE → #211).

**How you know:** full backend suite green (823) incl. the four Q75 cases (stale/null→sync, fresh→skip,
sync-raise + failure-summary both serve the fetch, incident fixture: three Aug-5 customs land + marker
stamped); G3 local before/after proof — a marker aged 25h drove a fetch-path refresh that pulled the
incident customs and re-stamped the marker fresh. The incident fixture pins the real prod ids read back
after the 2026-08-12 seeder run (user 1 customs 50→55): `iso-lateral front lat pull down`
0dd081f1…, `Iso-lateral Wide Chest Press` 1fe04727…, `Iso-lateral Incline Press` f8dccc5a… — all three
resolve as customs, so the incident was templates lagging workouts, not a built-in mismatch. Live prod
re-confirmation deferred to post-deploy (#116/#121: verify `alembic upgrade head` ran before trusting the
marker; the first post-deploy fetch fires one expected redundant sync per user, markers NULL until then).

**Do not revisit unless:** a custom-exercise create needs freshness ahead of any nearby read — Q75's own
condition. NOTE the write path (`<hevy_create_exercise>`) is ALREADY user-facing via chat
(`routers/chat.py:748`) and its idempotency pre-check reads this store; (c) covers the common case (an
active user's workout fetch refreshes the catalogue in the same session) but does NOT gate the create
path, so a create with no recent fetch can still race a stale catalogue. If that residual bites, option
(a) or a create-time freshness gate re-enters — flagged, out of this branch's scope.

### 212. Create-path catalogue freshness — the stale-catalogue mint window #211 left open is closed by a refresh-before-idempotency gate in the chat create path (Q75 residual)

**Decision:** `_process_exercise_actions` (`routers/chat.py`) calls `refresh_catalogue_if_stale(db, user_id)`
ONCE, after the not-connected early-return and BEFORE the honest-confirmation idempotency pre-check, so a
chat-initiated `<hevy_create_exercise>` with no recent workout fetch resolves its idempotency reads against
a fresh catalogue. Reuses #211's machinery verbatim — same per-user marker `user_integrations.templates_synced_at`,
same `_CATALOGUE_STALE_AFTER` (24h) gate, same non-blocking-on-failure wrapper. No new sync primitive, no scheduler.

**Placement is load-bearing — the chat pre-check, NOT inside `create_and_resolve`.** The create path reads
the local store twice: the honest-confirmation pre-check at `chat.py` (#164 — so the reply can say "created"
vs "already there" truthfully) and `create_and_resolve`'s own idempotency read (#65). A refresh placed only
inside `create_and_resolve` would leave the chat pre-check reading the STALE store: it would miss the upstream
custom, fall through to `create_and_resolve`, which would then refresh, find it, and return its id — and chat
would report "✓ created" for something that already existed, the exact false confirmation the #164 pre-check
exists to prevent. Refreshing before the chat pre-check makes that read honest AND leaves `create_and_resolve`'s
read fresh — one refresh closes both. It runs once per turn (before the block loop), so N blocks consult the gate
once; and it sits after the not-connected / no-block early returns, so the overwhelmingly common no-block chat
turn carries zero gate overhead and a keyless user never triggers a sync.

**Rationale:** #211 resolved Q75 as option (c), but its own "Do not revisit unless" flagged this residual
explicitly: (c) covers an active user's workout fetch refreshing the catalogue in-session, but does NOT gate
the create path, so a create with no recent fetch can still race a stale catalogue and mint a permanent
duplicate against Hevy's delete-less API — the 2026-08-05 incident's mint offer. The gate is ~one line because
#211 already built the staleness-gated per-user sync primitive; option (a)'s scheduler is not needed. No
double-sync on the common path: a recent fetch (#211) or create leaves a fresh marker, so the gate reads one
column and skips the Hevy call.

**Status:** active. Closes the create-path residual flagged in #211; Q75 stays DONE → #211 (NOT reopened).
Lineage: Q75 / #65 (`create_and_resolve`) / #164 (block + honest pre-check) / #211 (fetch-path freshness).

**How you know:** full backend suite green (828 = 823 + 5). New `test_hevy_create_freshness_gate.py` drives the
REAL gate + REAL pre-check with a faked sync transport: a stale (NULL-marker) store missing an upstream custom
refreshes, the pre-check then catches it, and NOTHING mints (`create_and_resolve` never called); a fresh marker
skips the sync entirely while a genuinely-new title still mints; the gate runs once for two blocks and never for
a no-block or not-connected turn. Two pre-existing chat-path fixtures (`test_hevy_create_exercise_block.py`,
`test_hevy_create_response_tolerance.py`) reseeded with a fresh marker — orthogonal to freshness, so the real
gate skips; this also removed swallowed real-network sync attempts the gate would otherwise trigger in those
fixtures (create-block file 18.9s → 2.5s).

**Do not revisit unless:** a create's own list-back needs to survive a marker that goes stale mid-turn (today the
gate refreshes once at turn start, and a create whose `sync_one_user` stamps the marker keeps subsequent same-turn
reads fresh), OR a non-chat caller of `create_and_resolve` appears needing the same gate (chat is the sole caller
today; the gate lives at the chat layer by design, per the placement rationale above).

### 213. The PM evaluation trigger, rebuilt on the 4-night hunting engine — offers on elapsed DAYS, replays the whole block, and carries no block-close path at all

**Decision:** #118's PM half — a read-only OFFER (`GET /checkin-v2/cbti/evaluation`) plus a witnessed
ACCEPT (`POST /checkin-v2/cbti/evaluation/accept`) surfaced in `NightlyCloseOut.jsx` — is built on the
4-night hunting engine (`CYCLE_NIGHTS=4`, `MAX_MOVE_MIN=15`), not the 7-night converge-and-close engine
the original `feat/cbti-eval-trigger` branch was cut against. Both endpoints go through the SAME block
replay the offline script runs (`cbti.replay.evaluate_live_cycle`, #128's revisit clause), extracted from
`replay.main` as `load_ledger_rxs`. Three calls, one reworked from the branch:

1. **Eligibility is CALENDAR DAYS elapsed since `effective_from`, not logged nights.** The gate is
   `days < CYCLE_NIGHTS`. `replay()`'s cycle spans are already calendar-dated (`cycle_start +
   CYCLE_NIGHTS - 1`), so days is the unit both #118 and the code use. Night COUNT still governs the
   DECISION, through the engine's own sufficiency gate (`>= MIN_VALID_NIGHTS = 3` valid), which returns a
   HOLD naming the shortfall rather than withholding the offer. Both quantities are reported.

2. **There is NO block-close path, because the engine emits none.** The hunting engine never returns
   `close` — a TST plateau is a `converged HOLD` that leaves the block open (#107, the 4-night retune
   #165). The original branch built a whole close arm — an `acceptable` flag, a 409 refusal in accept, and
   a dead-control UI arm — to say "a close is surfaced but not actionable". Under the engine that actually
   ships, that arm is UNREACHABLE, so it is DELETED, not ported. Every eligible decision is a prescription
   (extend / compress / hold, including a converged HOLD); accept mints it. Block close stays engine-driven
   and simply has no producer here to refuse.

3. **The trigger runs the FULL block replay, not the live prescription in isolation.** `prior_basis_tst`
   accumulates across every prior cycle, and the engine needs two of them to detect the plateau
   (`converged HOLD`). Evaluating the live cycle alone would start that history empty and the engine could
   never report convergence.

**Rationale:** call 1 is the one with teeth — gating the OFFER on logged nights strands the operator: a
cycle can never reach `CYCLE_NIGHTS` logged nights once one of its calendar days goes unlogged, so a
single missed diary entry withholds the evaluation permanently (the cycle's span is in the past). That
converts a data gap into a silent titration halt — the under-firing failure mode #124 names as the
observed one. Call 2 is the rework's core: the branch's close arm reasoned about a decision the shipped
engine cannot produce, so shipping it would have been dead code masquerading as a safety rail; removing it
is the honest port. This is a FRESH port onto master, not a merge of the stale branch — the branch predated
several master features and its diffs would have DROPPED them: the `centre_minutes` / `centre_cycles_n` /
`dither_minutes` estimate fields on `CBTIContextOut` and its `windows` read, and `DeepSleepLevers` + the
centre estimate in `NightlyCloseOut.jsx`. All preserved; only `EvaluationOffer` was added. The copy module
(`evaluationCopy.js`) claimed "no frontend test runner in this repo" — false on master (vitest ships), so
the OWED copy test is written, not deferred.

**Status:** active. Built on `feat/cbti-eval-trigger-v2`, cut fresh from master (the obsolete
`feat/cbti-eval-trigger @ fec0324` was reference-only, never merged). Resolves and supersedes that branch's
own decision, which was left headed `#NEXT` and never landed (the 7-night-engine version). Reuses #128's ledger
read; preserves #211/#212's create-path work untouched.

**How you know:**
- 10 new backend tests (`test_cbti_eval_trigger.py`); full backend suite **838 = 828 + 10**, no regressions
  (pre/post measured on fresh master via `.venv`, not derived). Every expected number recomputed from the
  4-night engine arithmetic, not pasted: a default night tst=420 against a 390 window targets 450, a +60
  move capped to +15 -> a **405** proposed window; the selected cycle is the last complete 4-night span.
- **G2 (offer/guard parity)** is pinned by a test: a nap night INSIDE the selected 4-night cycle is
  excluded by the engine's GATE-1 nap guard (reason `nap`) and the OFFER surfaces exactly that night in
  `nights_excluded`, with `nights_counted` dropping to 3 — the offer and the guard cannot diverge (Q45/Q78).
- **#128 reuse** is pinned by a test reproducing a mid-block correction superseding the seed: the basis
  reports the correction's lights-out and window, not the seed's.
- **Append-only invariant** asserted by column diff, not inspection — the prior row is re-read after accept
  and the changed-column set is asserted `== {effective_to, superseded_by}`; the block row is untouched.
- **Close-path absence** verified by grep across the live-trigger + endpoint + UI paths (clean of `acceptable`
  and close-decision reasoning; the `close` vocabulary member stays only in `engine.py` and the DB CHECK
  constraint — block-1 history).
- 12 new frontend tests (`evaluationCopy.test.js`, vitest); frontend suite green (32).
- **NOT verified against prod** — no live block-3 read this session; that remains OWED as it was on the branch.

**Do not revisit unless:** a block-close path is built (which would reintroduce a decision the accept
endpoint must then refuse — call 2 is the surface to re-read, not the engine), or the settling-period
question (Q48) resolves into an actual gate, at which point eligibility gains a second condition and call 1
is the surface to re-read, not the engine's sufficiency gate.

### 214. A UI control that performs an irreversible ledger write requires a restating two-step confirm

**Decision:** Any client control whose action mints or mutates an append-only ledger row — a write that
cannot be undone from the UI — must, before it writes: (1) restate the ACTUAL mutation in the user's terms
(what row is appended, what state changes, what it costs), and (2) require a distinct second deliberate
action to commit. The read-only preview/offer that precedes the write carries NO live write control. This is
a cross-cutting UI invariant, not a property of any one screen: it binds `EvaluationOffer`'s accept (#213),
the labs confirm-and-store screen (the next mint surface, #48/#52), and every future control that reaches an
append-only store.

**Rationale:** #166 already requires confirm-before-mint for irreversible writes, but #213's first live run
showed that invariant is satisfiable in FORM while bypassable in FUNCTION. `EvaluationOffer`'s accept is
mechanically distinct from the offer (a separate control, a separate endpoint), so #166 reads as met — yet a
single tap intended to *view* the offer minted `cbti_prescriptions.id`=12, an irreversible ledger append,
with no restatement of the mutation and no second action. The gap is that "distinct control" is not the same
as "deliberate, informed second action": a lone button that writes on first tap passes the structural test
and still fires by accident. Naming the invariant at the level of the WRITE (restate + second action), not
the screen, is what stops the same defect recurring on the labs confirm surface, which mints on confirm and
is being built next. Cheap to state now, load-bearing before the next mint surface ships.

**Status:** active. Minted from #213's first live run (the accept-confirm defect, filed as a ROADMAP NEXT
fix-row). The `EvaluationOffer` fix and the labs confirm screen must both satisfy this. Folds into `Q101`
where the accept-may-not-be-acceptable-at-all fork (an insufficiency-hold) further narrows WHEN the control
should exist.

**How you know:** `cbti_prescriptions.id`=12 exists on block 2 in prod (read-only Railway query, 2026-08-13):
`decision='hold'`, `basis_nights_n=2`, window unchanged 390/22:30, `effective_from`=08-13, superseding rx 11
(`effective_to`=08-12, `superseded_by`=12) — a real irreversible append produced by #213's accept on its
first live exercise, which is the concrete artifact this invariant generalises from.

**Do not revisit unless:** a mint surface has a genuinely different reversibility model (e.g. a soft-delete /
undo window) such that a restating two-step confirm is redundant rather than load-bearing — in which case the
undo path, not the confirm, is the safety mechanism and this invariant is satisfied by other means.

### 215. Railway prod verification 2026-08-16 closes Q13/Q15/Q18 — schema at head, zero bounds violators, HRV absent at source

**Decision:** Three OWED verifications ran against Railway Postgres (dashboard query editor,
single-statement runs) and all three closed with zero prod writes. **Q15:** `alembic_version` =
`e2d5c7a1b9f3` = local head; `exercise_sessions`, `samsung_hrv_readings.context` (varchar) and
`user_integrations.api_key_encrypted` (text) are all present with their intended types — the
`3497ab483935` drift was local-behind-prod, reconciled by `0f1ac6f33c40` / `e1f2a3b4c5d6` /
`a7d4f8e21c93`, not a real un-migrated delta. **Q18:** the full 15-field `_BOUNDS` `NOT BETWEEN`
sweep over all 56 prod rows returned zero violators; the `2026-06-28` trigger row's
`sleep_efficiency_pct` is already NULL, so `fix/hrv-sleep-integrity` Task 3 is satisfied with no
backfill and no writes. **Q13:** `hrv_rmssd` non-null count is 0 all-time, and
`health_connect_record_sources` holds only exercise / heart_rate (47,250 rows) / sleep / steps —
no HRV record type has ever arrived. HRV is absent at source, not unmapped; Q5's unmapped
hypothesis is eliminated for HRV; the scraper is the confirmed sole HRV path and the
single-point-of-failure residual transfers to `health-connect-app` issue #9.

**Rationale:** All three items were blocked on the same surface — production Postgres, unreachable
from the dev SQLite the local `DATABASE_URL` points at — and had aged 34–38 days for that single
reason. Batching them into one operator session cleared the whole surface at once rather than
paying the Railway-access setup cost three times. The 47,250 heart-rate rows matter to Q13's
conclusion specifically: they corroborate that the pipeline does read Samsung-written Health
Connect records, so the HRV gap cannot be explained by a dead ingest path — the absence is
upstream, at Samsung, which is what makes it *absent* rather than *unmapped*.

**Status:** active. Q13, Q15 and Q18 all `DONE → #215`; `BRANCHES.md` `fix/hrv-sleep-integrity`
moves OWED → DONE. The HRV SPOF is not closed by this — it is transferred, not resolved.

**How you know:** query outputs recorded in the 2026-08-16 operator session, read-only against
Railway Postgres via the dashboard query editor. The multi-statement no-op footgun that nearly
produced a false Q18 close — the editor silently returns 0 rows for a multi-statement paste — is
recorded as `FEEDBACK.md` §29.

**Do not revisit unless:** a future migration diverges prod from head again (re-opens Q15's class),
or an HRV-typed record ever appears in `health_connect_record_sources` — which would reopen Q13's
absent-vs-unmapped question and put Q5 back in scope for HRV.

### 216. Contraindication block sets revised per the Q23 audit — G-axis twins added, the PC-length screen blocked under radicular, the neural block scoped to spinal body parts

**Decision:** `_RADICULAR_BLOCKS` gains `hip_flexion_pc_length` and `loaded_carry_capacity_bw`;
`_RA_FLARE_BLOCKS` gains `grip_strength` and `loaded_carry_capacity_bw`; and the radicular/neural
branch of `is_contraindicated` fires only when the injury's `body_part` matches `_SPINAL_PARTS`
(or is empty, which degrades to the broader caution). Non-spine neural signals fall through to the
acute-tissue arm.

**Rationale:** The sets were written against the A–E axis vocabulary and never swept G, and the
omissions are not arbitrary — each one contradicts the set's own stated reason for existing.
`_RA_FLARE_BLOCKS` is documented as "base + grip compromised" yet left the grip region itself
probeable mid-flare; both sets blocked `carry` while leaving `loaded_carry_capacity_bw`, its G-axis
twin, open. A PC-length screen is functionally a straight-leg raise — a neural provocation test — so
probing it under an active radicular sign is the literal case the "don't discover your way into a
flagged nerve" rule exists to forbid. Body-part scoping fixes the opposite error: `_RADICULAR_BLOCKS`
is a lumbar-shaped stand-down (hinge, rotation, carry, gait), so firing it on anything merely typed
`neural` lets a peripheral entrapment block a hinge it has no relationship to. Empty degrades to
firing rather than to permission, because `body_part` is an optional hand-written field and the
absent case is the one most likely to be a real spinal sign nobody typed.

**Status:** active. Protective, not corrective — **neither named set has ever fired in prod**; all
five live injury-ledger entries are typed `mechanical`. The live defects the audit surfaced are not
in these sets but in `restrictions[]` consumption, spawned as `Q102` and deliberately not patched
here.

**How you know:** audit of 2026-08-16 — taxonomy × confirmed tags × sole-consumer verification
(`is_contraindicated` is the only runtime reader of either set; the other three repo hits are a
reference-JSON note and two test docstrings), with the live ledger read read-only from Railway the
same session. All three new keys resolve via `taxonomy.by_key`, as do all nine pre-existing members.
Backed by 22 new tests in `backend/tests/test_contraindication_blocks.py`, shown to DISCRIMINATE
rather than merely pass: against master's `selection.py` the four defect cases return the wrong
answer (neural@hamstring blocks `hinge`; RA flare leaves `grip_strength` and `loaded_carry_capacity_bw`
probeable; radicular leaves `hip_flexion_pc_length` probeable) and both preserved behaviours already
hold — after the change all six are correct. Suite 860 passed, up from an 838 baseline, no regressions.

**Do not revisit unless:** the `restrictions[]` consumption design pass (`Q102`) replaces
set-membership blocking wholesale — at which point these sets become defaults *under* that layer
rather than the mechanism — or a cervical / peripheral neural block set is added, which is the
fall-through this entry deliberately left open.

### 217. Cystatin C mapped to `cystatin_c` and the stored row bound by the standing backfill

**Decision:** `backend/reference/marker_canonical.json` gains one entry — raw `Cystatin C` ->
`cystatin_c`, `unit_established` `mg/L`, `loinc` null (69 -> 70 entries, all keys unique) — and the
`#55`-sibling backfill rider was run against prod, binding the single row stored unmapped from the
SNP draw of 2026-08-04. Data only; no code path changed. `unit_established` is set from the STORED
`unit_canonical`, not the printed form.

**Rationale:** The row sat with `marker_canonical` NULL, which is what raised the app's "not a known
marker" banner. While it stays NULL the reads' `COALESCE(marker_canonical, marker_name_raw)`
partition key treats the raw-keyed row and any future canonical-keyed row for the same analyte as
two distinct series — the double-count the standing rider exists to prevent, which is why the
backfill is mandatory on a dictionary expansion rather than a judgement call.

Taking the unit from the STORED string is the whole point of the precision check. The §6
over-collapse guard is a byte equality (`r.unit_canonical != established_unit`), so a case or form
variant in the map would have refused the NEXT upload of this marker with a 422 — loud rather than
silent, but a self-inflicted outage on a marker that had only just been mapped. No §7 homograph
exists: no other entry shares a token with `Cystatin C`. The `mg/L` shared with `R U-Albumin`
(`albumin_urine`) is a shared UNIT, not a shared key, and is pinned in the tests so it is not later
"fixed".

**Status:** active. Landed `2b2f91d`, merged `c71e497` via PR #72; branch merged+deleted. Prod
backfill applied the same session. Unblocks Brief B (renal derived metrics), whose input marker this
is; B's placement fork was closed by the same session's `is_derived` trace and is recorded in B's
spec, not here.

**How you know:** the precision check ran against prod BEFORE the entry was written — row id 220,
`marker_name_raw` `Cystatin C` at 10 bytes, `unit_canonical` `mg/L`, both byte-exact,
`marker_canonical` NULL, exactly one row; the unique constraint
`uq_lab_result_report_marker_raw (lab_report_id, marker_name_raw)` makes the one-row expectation
constraint-protected rather than merely empirical. Post-deploy (Railway deployment `188c8050`,
status SUCCESS at commit `c71e497`, prior image `REMOVED`), the backfill dry-run inside the
container reported the NAMED line `'Cystatin C' -> 'cystatin_c': 1 row(s) would update` with a
file-wide total of 1 across **70** known mappings — the "70" doubling as the `#116`
image-discriminating probe, since the prior image would report 69 and print no Cystatin C line at
all. `--apply` returned `Committed. 1 row(s) backfilled.`; the same dry-run re-run post-apply
returned 0 rows, so no `Cystatin C` row carries a NULL canonical any longer.

**What this entry does NOT carry:** a direct `SELECT` projection of row 220 post-apply. The written
literal is `cystatin_c` by construction — the UPDATE binds `:canonical` from the same map lookup the
dry-run printed — and the post-apply 0-row read proves the NULL is gone, but the row was not
separately read back. Recorded rather than glossed, per empirical specificity.

Suite 869 passed, up from an 860 baseline (`#216`), on 9 new tests in
`backend/tests/test_canonical_cystatin_c.py` written to discriminate rather than merely pass: the §6
refusal is asserted at three wrong units including the case variant `MG/L`, and a null-unit row is
asserted to PASS — fixing the guard's meaning as unit-CONFLICT, not unit-REQUIRED.
`test_canonical_urine_acr.py`'s whole-file count assertion moved 69 -> 70; it exists to force that
notice on every expansion and did.

**Standing-rule compliance:** the `#55`-sibling backfill rider was honoured in full — dry-run gated
on the named line, then `--apply`, then a post-apply re-read.

**Do not revisit unless:** a future SNP report prints this marker under a different raw label — which
is a NEW entry, never an edit to this one, since exact-string keying means the old label must keep
resolving for the stored history — or the extractor's `unit_canonical` normalisation changes form,
which would trip the §6 guard on this marker and require the map to follow the stored string again.

---

### 218. Q101 resolved — an insufficiency-hold is not an acceptable event; accept gains the #214 restating confirm

**Decision:** The evaluation offer's accept is gated on DECISION CLASS. An insufficiency-hold — the
engine's GATE 1 firing because fewer than `MIN_VALID_NIGHTS` of the cycle's nights are valid — mints
nothing, resets nothing, and renders information-only, enforced SERVER-SIDE (409 on
`POST /checkin-v2/cbti/evaluation/accept`) rather than merely hidden client-side. Selection stays
`complete[-1]`. A converged HOLD remains acceptable — it is a decision-on-merits, and recording it is
the block's memory of its found level. Accept now runs the #214 two-step: a confirmation restating the
actual ledger write, then a second deliberate action; the offer preview carries no live accept control.

The discriminator is STRUCTURAL, not a string match. `CycleDecision.sufficient: bool` is minted at the
sufficiency gate in `cbti/engine.py` — the only path that sets it False — threaded verbatim through
`replay()`'s series dict and surfaced on `CBTIEvaluationOut`. Before this the `insufficient_nights:`
reason PREFIX was the only carrier, which would have made an irreversible write's refusal rest on the
wording of a diagnostic sentence. It mirrors `converged`, the field that already exists for exactly this
job: distinguishing "held because a gate failed" from "held because the window is where it belongs".

That distinction is the whole reason the rule is not the simpler "a HOLD is not acceptable". The engine
returns `decision="hold"` on three unlike grounds — insufficiency (no conclusion), adherence (a
conclusion: the window was not run, so its sleep is not evidence about it), and convergence (a
conclusion, and the one most worth recording, since #107 left the engine with no other block-ending
signal). Only the first is a non-decision. A verb-level rule would be wrong in two cases of three.

**Rationale:** Prescriptions are prescriptive acts; "could not adjudicate" is a finding. Minting one
cost block 2 (`cbti_blocks.id`=2) a buried fully-logged `compress 390->375` plus ~4 days of clock
(`cbti_prescriptions.id`=12, #213's first live run) — and the harm event was itself the #214 defect
firing, a single tap on a live `Accept and prescribe` intended to view the offer. One landing therefore
closes both: the class gate removes the acceptability, the two-step removes the single tap. The
confirmation restates the CLOCK RESET explicitly, because that is the consequence the decision's own
numbers never mention and the one that cannot be undone by prescribing again tomorrow.

Fork (a) — deferring selection to an older sufficient cycle — was REJECTED: it violates the staleness
principle the selection encodes; an unaccepted elapsed decision expires rather than resurrects.
Answering fork (b) makes (a) moot in practice, since with no accept on the non-decision nothing buries
anything. `cbti_prescriptions.id`=12 is let stand: the ledger is append-only and the row faithfully
records what was accepted, so reversing it is an operator matter (a corrective prescription), never a
migration.

The client reads the flag STRICTLY — only an explicit `false` suppresses the accept control — so a
server that predates the field keeps the two-step accept rather than silently going read-only through a
rolling deploy. And the information-only card carries no control at all rather than a disabled one: a
greyed button still reads as an action that could be taken.

**Status:** active. **How you know:** block-2 ledger evidence in Q101 (read-only Railway, rx 12
`hold`/n=2/390/22:30, rx 11 `superseded_by`=12); enforcement tested BOTH directions in
`tests/test_cbti_accept_decision_class.py` — 409 with the ledger asserted untouched (`effective_to`
still None, i.e. the clock did NOT restart) on an insufficiency fixture, 200 on compress and
converged-hold fixtures, discriminator asserted on all four engine paths. Backend 869 -> 877, zero
regressions. Frontend vitest 32 -> 41: the repo's first COMPONENT tests, because #214 was a wiring
defect (a button bound straight to the POST) and no pure-function test can fail when someone rebinds
it — first tap fires no POST, POST only after the confirm, cancel fires nothing, an insufficiency card
renders zero buttons. jsdom + `@testing-library/react` added as devDeps, environment declared per-file
so the existing node suites pay nothing.

**Do not revisit unless:** the engine gains night-pooling across sparse cycles, which changes what
"insufficient" means — a pooled cycle could clear the gate on nights drawn from outside its own span,
and the flag would then have to say WHICH nights it rests on, not merely that it has enough.

### 219. Nap nights attribute to the night they precede — Q45 closed on operator determination, exclusion logic reversed

**Decision:** A recorded nap attributes to the night it **precedes** — the nap logged on day D belongs
to the night terminating on the morning of D+1 — implemented as the `naps_min` date-1 read in
`cbti.replay.load_nights`, and `NAP_EXCLUDE_MIN` rises 0 -> 30 so a sub-30-minute nap no longer
excludes a night. The attribution convention is **operator-set (2026-08-17), not clinically sourced**;
Q45's prior bar — confirm the referent from VA protocol documentation or the administering clinician —
is superseded as the wrong gate for a modelling convention. The previous logic (exclude any
nap-flagged night, because the instrument does not say which day a nap belongs to) is reversed, and
every comment asserting that rationale is rewritten to match.

**Rationale:** Which night a nap belongs to is a modelling choice the operator is entitled to make,
not a fact requiring clinical provenance. The preceding-night attribution is the natural reading of a
PM-captured nap, and it is the reading the app's own instrument already enforces: `_today_aest`
records "naps today" against the nap's own calendar day, so for every night live titration runs on the
referent is fixed by the capture surface rather than inferred from a workbook. A 30-minute floor stops
trivial naps from stalling titration; it is a CHOSEN floor with the same standing as `CYCLE_NIGHTS`
and `ADHERENCE_TOL_MIN`, recorded as chosen rather than dressed as derived. Holding the close hostage
to a VA-protocol citation that may not exist would have stranded a sound convention indefinitely — and
left the store asserting a provenance it never had.

Two things this decision did NOT do, because both would overclaim. It does not answer the question
Q45 originally asked: the workbook's scoped-null search stands, is not re-run, and the VA instrument's
wording still does not settle the referent — this decision says that question no longer *gates* the
engine. And it does not resolve **Q78**, which stays OPEN: two over-threshold nap nights still starve
a 4-night cycle at a one-night margin. Q78 was never blocked on the referent but on that data
consequence, which is why it survives a close that unblocks it.

**Status:** active. **How you know:** reworked onto current master from the orphan branch
`fix/q45-nap-attribution` (`4f77679`, based on `1e6cf0c`), **re-derived rather than replayed** — the
orphan predated #218 and would not fast-forward. Backend suite **877 -> 882**, zero regressions;
frontend **41**, unchanged. #218's accept-confirm suite (`test_cbti_accept_decision_class.py`) was run
in isolation under the change and is green at 8/8, so the decision-class work is undisturbed. The five
attribution assertions were **controlled for non-vacuity**: run against master's `replay.py` with the
reworked tests in place, all five fail — they discriminate the new read, not merely the new threshold.
Coverage pins the attribution positively and negatively (the nap lands on the night it preceded AND
not on its own night, so the old same-row read cannot pass), the floor at 30/31 in both directions,
the read reaching one day OUTSIDE the requested window (the off-by-one that would silently blank the
first night of every cycle), and a nap on a day carrying no diary row still attributing forward.

The corroborating artifact is that `models.DailyRecord.naps_min` has carried the column comment
*"Logged PM on date D; belongs to night terminating D+1. Engine reads from (date-1)"* since the column
was created, while the engine read the nap off the night's own row — a documented contract the code
never honoured, flagged silent-when-wrong in the model itself. This change makes them agree. Seven
stale comment sites were found and rewritten, not the three the orphan carried: #218 had independently
added a fourth Q45 site, and `models.py`, `checkin_v2.py` (x2) and `import_cbti_block.py` were never
in the orphan's diff at all. One user-facing string changed — the PM hint now reads "Naps over 30 min
exclude tonight"; note "tonight" was *wrong* under the old same-row read (the nap excluded the night
that had already ended that morning) and is literal only now.

**Do not revisit unless:** Q78 resolves the frequent-napper exclude-vs-attribute fork in a way that
changes attribution (not merely exclusion cadence or per-user cadence), or a real VA-protocol
statement on nap-day attribution surfaces and contradicts the convention. A different value for
`NAP_EXCLUDE_MIN` is a tuning question inside Q78, not a revisit of this decision — with the standing
caution that raising it to buy a decidable cycle is tuning the instrument to the outcome.


### 220. Canonical marker map is DB-backed and runtime-mutable via a confirmation-screen bind — #50 fully implemented

**Decision:** The canonical marker map moves from a startup-loaded `marker_canonical.json`
dict to a `marker_canonical_entries` table, seeded from that JSON. The confirm path and
`GET /labs/canonical-map` read the table per request; a new `POST /labs/canonical/bind`
writes an entry and backfills that marker's historical unmapped `LabResult` rows. Bind
inherits #50's protections — no fuzzy matching, and an over-collapse unit-guard refusing a
raw->canonical bind (or a historical backfill) whose unit disagrees with the canonical's
established unit. Binding is offered at the confirm screen but optional; an unbound marker
still stores null (retain-raw, #58/#155). The JSON becomes the migration seed. This
implements #50's confirmation-populated half; the over-collapse guard was already live, so
#50 is now fully realised and its "Not implemented" status is superseded.

**Rationale:** #50's "confirmation-populated" was never buildable against a static repo file
— a runtime bind cannot edit a file the app loaded at startup. Making the map a table is the
only architecture that fulfils #50's own word, and it ends the recurring
hand-edit-JSON-plus-backfill chore (PSA, conjugated bilirubin, CK, Cystatin C were each done
that way). Bind-triggers-backfill is what makes a bind worth doing — it promotes history,
not just future uploads (#159). The unit-guard is carried into the bind and the backfill
because that is where over-collapse would newly enter once identity is mutable at runtime.

**Scope correction — the interpretation readers are PHASED, and the brief's reason for
phasing them was wrong.** Two readers outside `labs.py` keep reading the JSON
(`interpretation/gates.py`, `interpretation/rephrase.py`). The brief proposed phasing them on
the hypothesis that interpretation only covers grouped markers, so a freshly-bound-ungrouped
marker could never reach them. That hypothesis is FALSE and was tested rather than assumed:
`producer._ungrouped()` emits every non-grouped panel marker as a flat row and
`presentation.py:237` builds rephrase fragments from them, so a bound-ungrouped marker does
reach `rephrase`. Phasing is still correct, on a different and narrower mechanism — both
readers degrade SAFE, and the migration cost is asymmetric:

- `rephrase._KNOWN_ENTITIES` is a **detector** allowlist, not a permit-list
  (`rephrase_validator.py` iterates the vocabulary and rejects only a word that is IN the set
  and appears in candidate-but-not-source). A marker absent from the stale set is never
  tested, so staleness narrows hallucination coverage — a missed detection — and can never
  cause a false rejection.
- `gates._UNIT_ESTABLISHED` is consulted only inside `_resolve_band`, reachable only when
  `safety_gate` finds the marker authored in `safety_thresholds.json`, which a freshly-bound
  marker is not; and the absent case already falls back to `value_plausibility` — weaker, not
  wrong.
- Migration cost decided the split: `generate_plain` is called from an endpoint already
  holding a `db` and already takes a `known_entities=` injection param, so rephrase could
  migrate almost free. `_resolve_band` sits ~4 levels below `build_foundation` inside the pure
  #86 producer, reached by two paths, with no injection param for the unit map — migrating it
  means threading a session through ~6 signatures in contract-sensitive machinery. Since
  either reader needing that threading disqualifies the cheap path, both stay on JSON and the
  hazard is tracked as Q104, which names the two downstream changes that would end the
  safe degradation.

**Status:** active.

**How you know:** migration seeds the 70 current entries and self-checks the inserted count
against the JSON (verified by replaying it in isolation on a scratch SQLite — the full chain
cannot replay there, an older unrelated migration uses Postgres-only `ALTER ... DROP DEFAULT`);
over-collapse refusal proven at confirm (pre-existing tests, still green) and at bind, both
bind-time and backfill-time, with the refused bind promoting zero rows; a bound marker
resolves at the very next confirm with no restart; an unbound marker still stores null.
Backend 882 -> 890, frontend 41 -> 47.

**Do not revisit unless:** the map needs per-user scoping (it is global by design — canonical
identity is not user-specific), or LOINC leaves dormancy at B2B.

---

### 221. The weekly template carries capacity quotas, never sport or position labels

**Decision:** `fortification_profiles.weekly_template` holds a capacity-quota microcycle —
`{"slots": [{capacity, sessions_per_week, minutes}]}` — where `capacity` is a member of the
`engine.taxonomy.Capacity` enum. There is no `sport` field, no `position` field, and no
exercise names; the shape refuses unknown keys at either level, so adding one is a schema
change rather than a convention drift. Sport-specificity is expressed entirely through fields
that already exist and are already upsertable: `vehicle_bias`, `horizon` and `primary_target`.
Two users with identical templates and different `vehicle_bias` get different programmes. That
is the design, not a gap. `select_next(..., capacity=)` and `GET /engine/next?capacity=`
consume one slot's capacity to constrain the probe candidate set; nothing yet resolves WHICH
slot is due.

**Rationale:** the template answers "how much of which capacity, how often, for how long".
That question is sport-independent — a netball centre and a marathoner both need a number of
stability sessions a week — while the answer to "which regions fill the slot" is not, and the
engine already has the machinery to answer it per-user. A `sport` label would put the same
information in two places with no arbiter between them, and every consumer would then have to
decide which one wins. Worse, it would invite a lookup table of sport -> programme, which is
precisely the hardcoded-string architecture the fortification profile replaced (spec §9): the
engine's whole claim is that it generalises from a profile, not from a taxonomy of sports. The
temptation will recur — it reads as the obvious missing field — so the refusal is recorded here
and enforced by the validator rather than left to reviewer memory.

**Sub-decision — the slot filter is a subset operation, not an ordering.** The brief asked that
contraindication and hard-stop filtering "run first" so the slot filter never overrides a stop.
In this tree those filters do not live in `select_next` at all: `compute_probe_queue` applies
them while building the queue, and `select_next` receives the result already ranked. The slot
filter is therefore implemented as a narrowing of that already-stop-filtered queue, which makes
the guarantee STRUCTURAL rather than a convention about statement order — a function that only
ever removes candidates cannot re-admit one a stop removed. Asserted end-to-end at both the
engine and HTTP layers, and separately as a subset property over every capacity, rather than by
reading the filter order off the source.

**Sub-decision — the Fortify target is not filtered by the slot.** A slot constrains the
SELECTION; the Fortify target is a declared profile field, not a ranked candidate. Dropping it
when its capacity disagrees with the requested slot would be scheduler policy — the lane this
work deliberately defers — and silently serving a mismatched target would be worse. The
response reports `slot.fortify_target_matches_slot` instead, so the disagreement is visible to
whatever eventually resolves it.

**Sub-decision — validated at write, stored verbatim.** Unknown capacity, duplicate capacity
across slots, `sessions_per_week` outside 0-14, `minutes` outside 5-180, non-integer or boolean
counts, missing fields and unknown fields all 422. Validation runs BEFORE the session is
touched, because `upsert_profile` calls `db.add` before its field loop — a mid-loop raise would
leave a pending INSERT for any caller sharing the session. The stored value is NOT
canonicalised: `PUT` then `GET` is byte-identical, so a slot written `"STABILITY"` reads back
`"STABILITY"`. That honours the round-trip contract at the cost of pushing normalisation onto
consumers, which `taxonomy.resolve_capacity` absorbs by accepting the enum name or its value
case-insensitively. The trade is live rather than settled — raised as Q105.

**Status:** active.

**How you know:** 55 tests (`backend/tests/test_weekly_template.py`) covering all six brief
gates at BOTH the engine and HTTP layers — round-trip compared on serialised JSON and on the
raw wire substring `"capacity":"STABILITY"`, not on dict equality, which would pass a silent
re-casing; unknown capacity 422 with `GET /engine/profile` still returning a null profile
afterwards; `GET /engine/next` with no parameter returning the same region as the unconstrained
call AND carrying no `slot` key, so the absent-parameter response shape is unchanged;
`?capacity=STABILITY` returning only stability-tagged regions across every enum member; and the
hard-stop gate proven by before/after — the region a STABILITY slot DOES select, then stopped,
then absent. The refusal battery carries negative controls (four templates the validator must
accept) so a validator that refused everything could not report green. Migration verified by
stamping the prior head and upgrading one step on a scratch SQLite, then downgrading to confirm
the column is removed. The head was `a7c3f19d5e28`, not `e2d5c7a1b9f3`: a first pass chained
onto the wrong revision because the head-detection regex required the annotated
`revision: str =` form while `a7c3f19d5e28` uses bare `revision =` — caught by `alembic heads`
reporting two heads before anything was committed (the #113 lesson — read the matches, do not
trust the pattern). Backend 890 -> 945.

**Do not revisit unless:** the consuming lane needs a slot to carry something a capacity and a
dose cannot express — in which case add a field to the SLOT, not a sport label to the template
— or `minutes` acquires a defined effect on the prescription (Q106).

---

### 222. Resolution and supersession are distinct terminal states; only supersession names a successor

**Decision:** A `user_knowledge_entries` row can reach `active=False` two ways, and they mean
different things. SUPERSESSION means "replaced by a newer statement about the same thing" — it
is written by `upsert_knowledge_entry` when a new entry arrives on the same key, and it sets
`superseded_by` to the successor's id. RESOLUTION means "no longer true" — it is written by
`POST /knowledge/injuries/{id}/resolve`, sets `active=False`, adds a `resolution` block
(`resolved_on`, `basis`, `resolved_by`) to the row's JSON `value`, and leaves `superseded_by`
NULL, because there is no successor. `superseded_by` is now exposed on `KnowledgeEntryOut` so
the distinction survives the trip through the API rather than living only in the table.

**Rationale:** collapsing the two is the obvious simplification — both set one boolean, and a
future reader will see two code paths writing the same field and want to merge them. But
`superseded_by` is the ONLY signal separating a healed hamstring from a re-worded one, and the
two demand opposite treatment: a superseded row's meaning is carried forward by its successor
and reading it in isolation is a mistake, while a resolved row's meaning is complete and its
absence from the active set is the point. Merging them would silently make every resolved
injury indistinguishable from an amended one at exactly the moment someone wants injury
history — which is the reason the ledger is append-only in the first place. Recorded because
the merge will look like tidying, not like data loss.

**Sub-decision — the write is a reassignment, not an in-place mutation.** `value` is a plain
`JSON` column, not a `MutableDict`, so `entry.value["resolution"] = ...` is invisible to the
unit of work and is dropped at commit with no error. The endpoint rebuilds and reassigns the
dict. This is a silent-failure class, so it is tested by re-reading the row from a fresh query
with the identity map expired — asserting on the response body alone passes either way.

**Sub-decision — the route is scoped to the caller AND to `type='injury'`.** A non-injury entry
and another user's entry are both 404, so the resolve route cannot retire a `schedule_item`,
and probing someone else's entry id learns nothing about whether it exists.

**Status:** active.

**How you know:** 35 tests (`backend/tests/test_injury_resolution.py`). The load-bearing gate
names a SPECIFIC region — `single_leg_hop` on the right, suppressed by an active right-hamstring
entry through `_ACUTE_TISSUE_BLOCKS` — and asserts it contraindicated before the resolve and
selectable after, with no other input changed; a second gate re-runs it one layer out through
`compute_probe_queue`, which is what `/engine/next` actually consumes; a third proves the lift
is SCOPED by leaving a second live injury's block standing. Asserting only that the injury list
shrank would have passed even if suppression never lifted. Gates mutation-tested against four
seeded defects, each caught by the intended gate and no other: removing the `active` flip fails
the region gates; mutating `value` in place fails ONLY the persistence gate (the region gate
correctly still passes, since `active=False` still lands); setting `superseded_by` fails the two
distinguishability gates; dropping the user scope fails the cross-user gate. Backend 945 -> 980.

**Do not revisit unless:** a third terminal state is genuinely needed — at which point add it
alongside, and do not express it by overloading `superseded_by`.

---

### 223. Injury resolution is an explicit operator write; `injury_trajectory` stays surfacing-only

**Decision:** Nothing auto-resolves an injury. No date, no soreness threshold, and no
trajectory flag may set `active=False` on its own. `injury_trajectory.evaluate()` remains what
#72 made it — divergence and symptom-gated review flags that SURFACE and change nothing. It
identifies resolution candidates; `POST /knowledge/injuries/{id}/resolve` is where the operator
puts the answer. This restates #72 rather than assuming it carries, because this brief is the
first thing built that could plausibly erode it.

**Rationale:** #72 settled that restrictions are set at injury onset and the check-in monitors
rather than renegotiates. Giving the system a resolution mechanism creates the obvious next
step — the review flag already knows the injury "looks resolved", so why not let it resolve?
Because that inverts #72 with no operator in the loop: an injury constraint that lifts itself
because a `resolve_by` date passed, or because self-reported soreness sat at 1 for three days,
is a safety failure whose whole cost lands on the user. The exit condition is a PROMPT to
revisit, not a verdict — the same asymmetry #133 fixes for clearance, where stronger evidence
for early loading sharpens the boundary rather than eroding it. And this endpoint is not the
app clearing anyone: it interprets nothing, it records an assertion and stamps who made it
(`resolved_by`), which is why `basis` is mandatory — a resolution with no stated grounds is
what later reads as an accident.

**Sub-decision — `expire-stale` is untouched and is not resolution.** It flips only rows whose
`expires_at` was predicted at creation, and it writes no `resolution` block, so an expired row
stays distinguishable from a resolved one. It was one of the three inadequate routes this brief
exists to replace, not a mechanism to extend.

**Status:** active. Restates and reinforces #72; consistent with #133.

**How you know:** three GUARD tests plus a structural one. A trajectory whose `resolve_by`
(2026-08-01) is well past, with a soreness series that keeps the divergence flag firing — exact
message pinned — leaves `active` True and the region still suppressed. A soreness series sitting
at the declared exit condition for the full sustained window raises the review flag, the
strongest "this looks resolved" signal the system produces, and still resolves nothing. Both
flags are pinned EXACTLY for an untouched fixture so a drift in `evaluate()` fails loudly rather
than being absorbed. The structural gate greps `injury_trajectory`'s own source and asserts it
contains no `.active =` assignment at all, so a later edit adding a write fails even if no test
exercises it. One drafting correction is recorded because it proves the pin is tight: the first
version asserted a divergence for a series ending at soreness 1, and the source refused it —
`resolving_by` diverges only while the last reading is >1, so a series at 1 means the injury DID
resolve by its date and only the review arm fires. The expectation was wrong, not the code.

**Do not revisit unless:** the app gains a verified, objective load-response input that a
practitioner would accept as resolution evidence — the same premise-change #133 names, not a
loosening of this rule.

---

### 224. AM soreness prefill carries the last reported value, bounded by a lookback window

**Decision:** `derive_soreness_items` prefills each active injury's soreness item with that
injury key's most recent reported value from `daily_records`, provided it falls within
`_PREFILL_LOOKBACK_DAYS` (7) of today. Beyond the window nothing is carried. The most recent
record CONTAINING the key wins, not the most recent record — a key absent from an intervening
day does not reset the carry. One query resolves every key; a per-key lookup would be an N+1 on
a route in the daily path.

**Rationale:** the previous prefill was a hardcoded `1`, and `1` is the scale FLOOR, so every
morning opened at "asymptomatic" regardless of yesterday. For a genuinely sore injury the
operator had to re-enter the same value daily or the record understated it, and an unedited day
silently reported recovery — the check-in's own capture was biased toward improvement. Carrying
the last stated value makes the common case (unchanged since yesterday) the zero-effort one,
which is the correct default for a daily ritual measured in seconds.

**Why the window is bounded at all:** a carried value is a claim the operator did not make
today. Within a week that is a reasonable inference; beyond it, it is a confident statement
about a body that has had seven days to change, and it arrives pre-agreed — the operator must
notice it to correct it. A stale value is worse than a stated unknown, so the carry expires
rather than persisting indefinitely. Seven days is one training microcycle and is a named
constant, not an inline literal, so moving it is a decision rather than an edit.

**Sub-decision — out-of-range does NOT clamp to the nearest bound.** A stored 9 resolves to the
fallback, not to 5. It is corrupt data, not an emphatic reading, and manufacturing a plausible
number from it is how bad data stops looking bad. `bool` is rejected explicitly, since it is an
`int` subclass and `True` would otherwise read as a valid 1 — the exact value this change exists
to stop arriving unasked. A key present-but-unusable ends that key's search rather than reaching
past it to an older valid value, which would silently substitute a number the operator never
re-stated.

**Status:** active. Prefill only — no change to submit, to the readiness formula, or to
`injury_trajectory`.

**How you know:** 38 tests (`backend/tests/test_soreness_prefill_carry.py`). The window boundary
is asserted at exactly 7 days (carried) and exactly 8 days (not carried) using a carried value
of **2**, deliberately not the fallback 3 — a boundary test whose expected value equals the
fallback cannot distinguish "carried correctly" from "fell through", and would pass a window
that failed open. Query count is asserted as a comparison between a 1-injury and an 8-injury
user rather than against a magic number. Prefill's read-only nature is asserted by a SQLAlchemy
statement spy (no INSERT/UPDATE/DELETE reaches the database) as well as by row-count and stored
payload comparison, including for a user with no `daily_records` row at all. Gates
mutation-tested against four seeded defects, each caught by the intended gate and no other:
widening the window to 8 fails only the boundary and constant gates; discarding a key on the
most recent RECORD rather than the most recent record containing it fails both carry-gap gates;
removing the `bool` guard fails only the `True` case; and a per-key N+1 query fails ONLY the
query-count gate — correctly, since its behaviour is identical. Backend 980 -> 1018.

**Do not revisit unless:** the carry needs to distinguish a reported value from a defaulted one
— see #226, where that was considered and declined.

---

### 225. The soreness prefill's absence fallback is 3, not 1 — aligning it with the readiness scorer

**Decision:** when there is nothing to carry (a new injury, or nothing in the lookback window),
the prefill is `3`, not `1`. `3` is already this module's no-information value: `calc_naive_baseline`
computes `soreness_raw = max(vals) if vals else 3`. The prefill now agrees with the scorer it
feeds instead of contradicting it.

**Rationale:** `1` was doing double duty — it is both the scale floor ("None") and, formerly,
the value that arrived unasked. Those are incompatible jobs. Because the floor arrived by
default, the system could not tell a deliberate "no soreness" from an untouched form, and an
untouched form scored as full recovery. Making the default the neutral midpoint separates the
two: the floor is now reachable only by entering it.

**Recorded consequence, which is the point rather than a side effect:** a `review_when` exit
condition of `soreness <= 1 sustained 3 days` can now only be satisfied by the operator actively
entering `1` on three separate days. Under the old default it could be satisfied by three days
of not touching the form — an injury could clear its own exit condition through inattention.
That flag is surfacing-only (#223), so the old behaviour produced a weakly-earned prompt rather
than a write, but a prompt earned by silence is still noise in the one place the system asks the
operator to think.

**Second recorded consequence:** for a user with a new injury and no history, an untouched
submission now carries `3` where it carried `1`, lowering `naive_baseline` by exactly 1.0 point
(the soreness term is weighted 0.20 over a 0-10 scale, and `(3-1)*2.5 = 5`). That is the intended
effect of a more honest input, not a regression, and it is pinned as an explicit test rather than
left in prose. Historical `naive_baseline` values are frozen at capture and are NOT recomputed,
so no stored score moves.

**Status:** active.

**How you know:** the fallback is asserted against the scorer's own behaviour, not a duplicated
literal — `calc_naive_baseline` with `soreness={}` and with `soreness={key: 3}` return the same
value. The new-injury case is asserted explicitly as a behaviour change from `1`. A carried `1`
is asserted to survive as `1`: the fallback applies to absence, never to a low reading, or the
exit condition above would be unreachable. The 1.0-point cost is asserted as an arithmetic
identity. The formula itself is pinned twice on a fixed payload — once against a literal and
once against the weighting spelled out term by term, so a weighting change cannot be absorbed by
adjusting the literal.

**Do not revisit unless:** the scale itself changes, in which case the no-information value and
`calc_naive_baseline`'s fallback must move together — they are now one decision in two places.

---

### 226. A reported-vs-defaulted flag was considered and declined

**Decision:** the system does not record whether a submitted soreness value was stated by the
operator or arrived as a prefill. No `touched` flag, no per-item provenance, no parallel
structure alongside `daily_records.soreness`.

**Rationale:** the flag's purpose would be to stop an untouched item from being read as a
reported one. The `3` fallback (#225) addresses the same failure more cheaply and at the point
of origin: an untouched item no longer RESEMBLES a recovered one, because the value it carries is
the neutral midpoint rather than the floor. A flag would add a field, a migration, a wire-format
change, and a second thing every reader must consult and can forget to consult — to recover a
distinction the fallback already makes operationally invisible.

**Residual, stated plainly so this reads as a decision later and not an oversight:** the system
still cannot distinguish a deliberate `3` from an untouched `3`. A divergence arm reading a flat
series at `3` is reading defaults, and will describe them as a stable trajectory. This is
contained rather than solved, and what contains it is #223: `injury_trajectory` is
surfacing-only, so a weakly-earned flag yields a prompt to a human, never a write. The
containment is structural, not incidental — if trajectory ever gains authority over state, this
residual becomes load-bearing and the flag must be reconsidered in the same change.

**Status:** active. Declined, not deferred — revisit on the trigger below, not on preference.

**How you know:** no schema change, no migration, and no new field ships with #224/#225; the
carry is computed from `daily_records.soreness` as it already exists.

**Do not revisit unless:** `injury_trajectory` gains the power to change state (which #223
forbids), or a consumer appears that must act on the reported/defaulted distinction rather than
surface it. Preference for completeness is not a trigger.

---

### 227. Assertion provenance lives inside the JSON entry; writes require it, reads tolerate its absence

**Decision:** each entry in `fortification_profiles.hard_stops` and `live_signals` carries a
provenance block as KEYS INSIDE the entry — `asserted_by` (`user` | `engine` | `clinician`),
`asserted_on` (ISO date), `basis` (free text), `review_on` (ISO date or null). Not a side table,
not a parallel list. `upsert_profile` refuses (422) an entry missing `asserted_by` or
`asserted_on`, or carrying an unrecognised tier; `profile_to_dict` backfills entries that lack a
block with `asserted_by: "user"`, `asserted_on: null`, `review_on: null`, and passes entries that
carry one through VERBATIM. No migration.

**Rationale — inside the entry:** an assertion and its attribution are one fact. A side table
makes them two rows that can disagree, and every reader must then join or forget to. Both columns
are already JSON lists of free-form dicts, so keys are addable without a migration, and the
precedent is one tier down: `POST /engine/response` already carries a `source` alongside the
response it describes rather than beside it.

**Rationale — writes require, reads tolerate:** these are the two halves of a change-management
rule, not an inconsistency. Making reads strict would 422 every existing profile, which is a
migration by another name. Making writes lenient would let provenance stay optional forever, so
the store would never actually fill in. Requiring it at the write boundary means a legacy entry
survives untouched and acquires provenance the moment someone next edits it — which is exactly
when the operator knows the answer.

**Recorded consequence, pinned as a test rather than left in prose:** a legacy entry read back
carries `asserted_on: null`, and re-sending that verbatim is refused, so GET -> PUT of a
pre-provenance profile is not a no-op. The refusal message names the fix (state the date rather
than re-sending null). This is the intended friction; recording it stops it being read later as a
bug.

**Sub-decision — only the provenance keys are validated.** Entries stay free-form domain dicts:
`hard_stops` carry `pattern`/`region_key`/`scope`/`side`/`reason`, `live_signals` carry
`signal`/`branch_param`/`status`/`self_triage`, and an unknown key passes. Deliberately unlike
`validate_weekly_template` (#221), whose slots are a closed shape by design — freezing these
shapes is not this brief's business, and doing it by accident would be the kind of scope creep
that only surfaces when someone cannot add a field.

**Sub-decision — `asserted_by` is a new key, not a rename of `source`, and its vocabulary is
aligned deliberately.** The stores already carry `source` (`onboarding | chat | system` on
`user_knowledge_entries`, `probe` on `/engine/response`, `self_report | catapult | hevy | polar`
on `capability_observations`) and `method`, plus a `hard: true|false` on schedule items. Those
answer different questions: `source` is the CHANNEL or INSTRUMENT an entry arrived through,
`method` the capture protocol, `hard` a commitment strength. `asserted_by` is an AUTHORITY tier —
who is making the claim — and it is orthogonal to all of them: an entry can arrive via `chat`
while being asserted by a `clinician`, and today every knowledge row reads `source: "chat"`,
which is precisely why the channel axis carries no authority information. Collapsing them would
lose one axis to record the other. The vocabulary IS aligned where it should be: with #222's
`resolved_by` (`user | clinician`), the other authority field in the tree. The two differ by
exactly one member — `engine` — because an engine can assert (a probe response is an inference
the engine made) but must never resolve (#223: nothing auto-resolves). Both the disjointness from
the channel words and the exact one-member difference from `resolved_by` are asserted as tests, so
a later merge of the vocabularies has to argue with a gate rather than look like tidying.

**Sub-decision — `weekly_template` takes no provenance block.** It is a DECLARATION (a capacity
quota the user is choosing), not an ASSERTION about the world. Provenance answers "who claimed
this is true"; a template has no truth value to attribute. Recorded because `weekly_template`
joined `_UPSERTABLE` and `profile_to_dict` in #221, one commit before this, and its absence from
`_PROVENANCED_FIELDS` will otherwise read as an oversight.

**Status:** active.

**How you know:** 51 tests (`backend/tests/test_assertion_provenance.py`). THE regression gate
runs the same hard stop in BOTH shapes — with and without provenance — through the real
`is_contraindicated` path in one comparison, asserting the same verdict AND the same reason
string; a second runs `compute_probe_queue` -> `select_next` for two users whose profiles differ
only in the presence of provenance keys and asserts identical selection. Running both shapes in
one test is what makes it a comparison rather than an assumption that added keys are inert. The
seed gained provenance this session and its selection is separately pinned. The backfill is
asserted not to write: the stored column keeps the legacy shape after a read. The refusal battery
carries negative controls (all three tiers accepted). Gates mutation-tested against three seeded
defects, each caught by the intended gate: a backfill that clobbers real provenance fails the
verbatim, mixed-profile and round-trip gates; skipping `live_signals` validation fails only the
`live_signals` arm of the parametrised refusals; and treating `review_on` as an expiry fails all
four guard gates (see #228). Two #221 tests were updated — they wrote `hard_stops` without
provenance, which the new write contract refuses. Backend 1018 -> 1069.

**Do not revisit unless:** a second store gains an authority field, in which case it aligns with
these values rather than inventing a third vocabulary — or `asserted_by: "clinician"` is made to
carry identity, which is Q108 and binds both stores at once.

---

### 228. `review_on` is a prompt, never an expiry — nothing auto-retires

**Decision:** `review_on` on a `hard_stop` or `live_signal` means ASK AGAIN on this date. It does
not, and must not, cause `gather_active_injuries`, `is_contraindicated`, or `compute_probe_queue`
to skip the entry. A `review_on` in the past still blocks, exactly as it did the day it was
written. `null` means standing until explicitly retired. Retirement is always an explicit write.

**Rationale:** a hard stop that quietly stops applying because a date passed is a safety failure
with no operator in the loop, and it is the precise inversion of what provenance is for — the
brief exists because stale entries silently constrain, and an auto-expiry would replace that with
stale entries silently UN-constraining, which is worse: an un-applied safety rule fails open. The
asymmetry is deliberate. A stop that outlives its usefulness costs a conservative recommendation
the operator can notice and retire; a stop that expires itself costs a recommendation into a
region the operator still needs protected, and nothing surfaces that it happened.

**This restates #223 in a second store rather than assuming it carries.** #223 settled that
nothing auto-resolves an injury; this settles that nothing auto-expires a profile assertion. They
are the same rule about different objects, and the temptation is identical — the date is right
there, and using it looks like the obvious feature. Both are recorded because the next thing
built near either one will be a review surface, and a review surface that resolves is one
refactor away from a review surface that expires.

**Status:** active. Same rule as #223, different store.

**How you know:** four guard gates, one of them structural. `is_contraindicated` blocks a stop
whose `review_on` is 2020-01-01; `compute_probe_queue` still excludes the region; past, future,
null and absent `review_on` are asserted to produce IDENTICAL verdicts in one comparison, so an
edit that reads the field at all fails; and a source-level gate asserts `engine/selection.py`
contains no reference to `review_on` whatsoever, which catches a future filter even if no
behavioural test covers its shape. Mutation-tested: seeding an expiry check into
`is_contraindicated` fails all four, including the structural one.

**Do not revisit unless:** a retirement mechanism is built — in which case it is an explicit
operator write, like #222's resolve endpoint, and this entry is its constraint rather than its
obstacle.

---

### 229. A FEEDBACK entry proven wrong in scope is amended in place, not superseded by a new §

**Decision:** when a `FEEDBACK.md` entry is found to be wrong in scope, its line is REWRITTEN. A
correcting entry is not appended beneath it and the wrong text is not left standing. This is the
opposite convention to `DECISIONS_LOG`, and the difference is deliberate: a decision is a record of
what was decided and when, so supersession preserves the reasoning trail; FEEDBACK is a live
instruction set, so the trail belongs in `FEEDBACK_ARCHIVE.md` and git history, never in the
instruction itself.

**Rationale:** FEEDBACK is read at session start as a set of standing instructions, not as history.
A superseded entry left in place keeps instructing until the reader reaches its replacement, and a
reader who acts on the first thing they read has already acted. §30 is the case that shows the
cost. It told a reader never to "fix" data that reads fine over HTTP elsewhere — correct for the
read path, and actively suppressing on the write path, where the loss is real and at rest. A wrong
rule sitting above its correction is a rule that still fires.

**Status:** active. Applies to `FEEDBACK.md` only. `DECISIONS_LOG` supersession is unchanged, as is
`OPEN_QUESTIONS`, where a superseded item carries an explicit `**State:**` a reader cannot miss.

**How you know:** the superseded §30 text is recoverable via `git log -p -- FEEDBACK.md`, so
amending in place destroys nothing. The amended line names BOTH directions and the evidence
(em-dashes persisted as hyphens, `POST /knowledge/entry` ids 75-78), so a reader cannot take the
read-half as the whole rule. The convention had no precedent before this entry: across 39 commits
touching `FEEDBACK.md`, no `- §N` line has ever been deleted — `git log -p --follow --
FEEDBACK.md` matched against the anchored form `^-- §[0-9]+` returns nothing, so every deletion in
the store's history is essay prose, a footer metadata line, or the 2026-08-09 prune, never a rule's
text.

**Do not revisit unless:** FEEDBACK stops being read at session start, at which point the
live-instruction argument no longer holds and the store becomes history like the others.

---

### 230. `source` is a channel axis; authority lives in `asserted_by`

**Decision:** `source` on `user_knowledge_entries` answers HOW DID THIS ARRIVE, never who was
behind it. The vocabulary is declared and validated at write — `onboarding | chat | system | api`
— and `api` names a direct operator write against the API. The `"chat"` default is removed, so a
caller must state the channel. `operator` is refused: naming the writer is an authority claim, and
authority already has a field.

**Rationale:** `operator` reads well against rows 75–78 precisely because those rows are an
operator's, and that is the trap. Adding it would make `source` a mixed axis — some members
naming a channel, one naming an author — and duplicate `asserted_by` (#227, `user | engine |
clinician`), the field introduced for exactly this question one store over. Two fields answering
"who", disagreeing eventually, is worse than one field that declines to. The cost is stated rather
than hidden: **`source` will never answer "who"**, and that is the correct shape, not a
limitation to route around later.

**Removing the default is the load-bearing half.** Adding `api` while `"chat"` still filled itself
in would leave the vocabulary complete and the defect untouched: the four rows were not a
validation failure, they were a validation that never ran, and a caller that says nothing would
still be labelled `chat`. The member without the removal is a dictionary nobody has to open.

**Status:** active. Landed with the validator; the four existing rows are untouched.

**How you know:** `SOURCE_VALUES` is asserted as a closed four-member tuple; unknown literals are
refused, and the refusal battery includes `user`, `clinician`, `engine` and `operator` — the
axis-mixing case is a test, not a comment. Two negative controls carry the rest: every declared
member is accepted (a validator refusing everything would otherwise report green), and an omitted
`source` is refused, which is the assertion this entry exists for. Widening
`test_provenance_is_a_different_axis_from_the_capture_source` to include `api` keeps #227's
disjointness claim honest, and that test now carries a comment recording what it does NOT prove:
two disjoint word lists are not a guarantee the axes stay separate — a future `source` member
naming an author would be disjoint from `ASSERTED_BY_VALUES` and still collapse them. Backend
1069 → 1083.

**Rows 75–78 are NOT corrected here.** Relabelling them is a write against live prod data, and it
waits on the member existing. It is the operator's, per §8.

**Do not revisit unless:** a write arrives through a channel none of the four names — in which
case the answer is a fifth channel word, and this entry is the constraint on choosing it.

---

### 231. `resolved_by` and `asserted_by` record a class, not an identity

**Decision:** neither authority field carries an assertor's identity. `resolved_by` (#222) stays
`user | clinician`; `asserted_by` (#227) stays `user | engine | clinician`. Attribution beyond the
class is absorbed by `basis` — mandatory free text — and stays prose.

**Rationale:** #133's reasoning about inputs the app cannot verify applies to the assertor as much
as to the assertion. On a single-operator platform an identity field is a name typed into a box,
self-asserted, with no verification path; a field that LOOKS like provenance and isn't is worse
than honest prose, because a later reader trusts the structured field and reads past the free
text. The evidential asymmetry the identity question was raised to capture — a clinician-resolved
injury versus a self-resolved one — is already captured, by the class.

**The binding half of the question was already settled and is not re-decided here.** #227 aligned
the two vocabularies and pinned the alignment with a test rather than a convention: they differ by
exactly `engine`, which can assert but must never resolve (#223). So "does an answer bind both
stores" is closed — yes, by a gate. What this entry closes is only the identity question itself.

**Status:** active. No code change; this records a declined addition, like #226.

**How you know:** `test_the_authority_vocabulary_agrees_with_the_resolution_store` asserts
`set(RESOLVED_BY_VALUES) < set(ASSERTED_BY_VALUES)` and that the difference is exactly `{engine}`,
so a later edit that adds an identity member to one store and not the other fails loudly instead
of looking like tidying.

**Do not revisit unless:** a second asserting user exists — at which point the change lands on
`resolved_by` (#222) and `asserted_by` (#227) in the same stroke, or it is drift.

---

### 232. Standing views own review and resolve prompts; decision-support carries a pointer, not a control

**Decision:** one convention, two stores. A due `review_on` (#227) and an injury `review` flag
(#222/#223) both surface the same way — as a badge on a row in that store's own standing view:
`GET /engine/profile` for profile assertions, `GET /knowledge/injuries` for injuries. The
decision-support surface carries a COUNT POINTER only — "N items due for review", linking into
those views. It holds no resolve control and no retire control. The AM check-in is unchanged and
stays read-only.

**Rationale:** the standing view is the honest home because the list already exists and already
returns every entry with its block, so the prompt is a rendering rather than a new mechanism. Its
known weakness is real — a flag can sit unseen for weeks — and the answer to that is visibility,
not interruption: the pointer costs a navigation step at a moment the operator is already
reviewing, which is the register the prompt belongs to. Putting a state-changing control in the
check-in is refused on #72's scope: the check-in monitors, it does not renegotiate, and a
due-review prompt is a renegotiation invitation dressed as a data point.

**Answered as one question across two stores, deliberately.** Q107 asked where an injury `review`
flag surfaces; Q110 asked where a profile `review_on` surfaces. Answering them independently
produces two review surfaces with two conventions — the same drift #227's aligned vocabularies
exist to prevent one layer down. One convention, applied twice, is the decision.

**Constraint inherited, not restated:** #223 and #228 are unconditional. No surface named here
resolves or retires anything. Every state change remains an explicit operator write carrying a
`basis`.

**Status:** active as a constraint on future work. **This entry decides WHERE, not WHAT GETS
BUILT** — it authorises no UI work by itself. A later brief that builds the badge or the pointer
cites this entry as its constraint.

**How you know:** the two endpoints exist and already return what a badge needs — `GET
/knowledge/injuries` returns injury rows including resolved ones behind `include_resolved`, and
`GET /engine/profile` returns `hard_stops`/`live_signals` with the provenance block #227 added,
`review_on` included. No new read is required to render either prompt, which is the property that
made the standing view the cheap answer as well as the honest one.

**Do not revisit unless:** a flag is demonstrably missed with the pointer in place — in which case
the fork reopens at the check-in, and #72 is the entry that has to be argued with, not this one.

---

### 233. `schedule_item` is a closed validated shape; `hard` and `expected_load` are two axes; `supersedes` triggers on day overlap alone

**Decision:** `user_knowledge_entries.value` for `type='schedule_item'` is a **closed, validated shape**, enforced at write in `routers/knowledge.py::validate_schedule_item` and applied inside `upsert_knowledge_entry` — the shared write path for `POST /knowledge/entry`, the chat channel and `routers/health.py`. Unknown keys, non-weekday `days` members, truthy-string booleans, `sessions_per_week` outside 1–14, missing required fields and out-of-set `expected_load` / `time_of_day` are all **refused (422), not stored**. Validation runs before the session is touched, so a refused write leaves no row; the value is never canonicalised. Direct ORM construction stays unvalidated by design — that is the backfill's path, and validation is at write.

**The ownership rule:** `schedule_item` owns **WHEN**; `fortification_profiles.weekly_template` (#221) owns **HOW MUCH OF WHAT KIND**. Stores own facts; the resolver composes them. **Any further axis resolves into an existing vocabulary rather than minting a store.** The narrower phrasing considered here — *neither store owns both, the resolver is the join, not a third store* — is correct today but reads as prohibiting any future axis, which would force a supersession within weeks. `sessions_per_week` appears in both stores meaning different things by design: a calendar fact here, a capacity quota there.

**`hard` and `expected_load` are two axes, not one.** `hard` is a **scheduling** fact (immovable in the calendar); `expected_load` is a **cost** fact (`light` | `moderate` | `heavy`). Conflating them was the original error: Saturday rugby and Thursday set piece are both `hard`, and only one wants the day before scaled back. `expected_load` is the cost of a **scheduled commitment**, and any future axis expressing training cost — including a training-goal axis — **resolves into this vocabulary rather than minting a parallel one**. That axis is named here so the rule survives it; it is not in scope, has no store, and has no ruling.

**`expected_load` is required on write and nullable in store.** A caller that does not know the load must ask; a fabricated load entering a load model is worse than a visible gap. Legacy rows carrying null are untouched — validation is at write, so they read back unchanged.

**The `supersedes` trigger keys on DAY OVERLAP ALONE.** A write landing on a day any active row of the same user already holds is refused **409** regardless of `activity`, naming every overlapping row (id, activity, days, time_of_day); the retry must acknowledge **every** named row via `supersedes: <id>` or `distinct_from: [<id>, …]`. `distinct_from` is accepted at write and never stored — an acknowledgement token, not a relationship. An earlier draft additionally required a matching `activity`; that is rejected, because the documented root cause of the live duplicate pairs is that the writer **minted a new key for an existing commitment**, so string equality over generated free text fails the same way one level down and fails **open**. This deliberately refuses more often, including on genuinely distinct same-day commitments: the failure moves from silent to visible and the caller states which it is — the aide posture of #222/#223/#232.

**Expiry precedence — nothing auto-flips `active` (#228).** `season_end` (calendar fact), `duration_weeks` (duration from `added_at`) and `expires_at` (absolute, on overlay rows) are not interchangeable and no validator derives one from another. A passed bound is a **badge and a prompt**, never a state change; where more than one is set, the earliest governs the badge.

**A rejection is surfaced, never swallowed.** The chat writer reports a refused write into `actions_taken` with the reason, and on an overlap states the clash back to the user and asks whether it replaces or coexists — it must not resolve the ambiguity itself, because inventing an answer is what produced the duplicates. A silently dropped fact is worse than the mess this replaces: the user said it out loud, and nothing downstream can distinguish "not said" from "said and lost".

**Rationale:** `schedule_item` was unvalidated free JSON and every fault in the live data traced to that — constraint prose in a documented-boolean field, quota values smuggled into `days[]` (`"flexible"`, `"flexible_third_day"`), a `minimum_days` key invented around a missing field, duplicate rows for one commitment, and rows still `active` months after the commitment ended. A shape that exists only as prose inside a prompt template has no enforcement surface, which is why it drifted.

**Status:** Implemented at write; **the live rows are NOT backfilled.** This session had no route to the production database (no Railway CLI, credentials closed by #111), so the 18 active rows, the five prod assertions and the live-row stop-condition are outstanding and carried in `OPEN_QUESTIONS` Q116. The validator is live and the legacy rows read back unchanged, so the two states coexist without error — which is exactly why the gap needs a question rather than a memory. Granularity of `expected_load` is Q117.

**How you know:** Backend suite 1087 → 1113, zero regressions, both suites green. The validator is proven **by mutation, not by passing** (`FEEDBACK` §18): eight mutations were applied one at a time and every one was caught — notably the v1 activity-matching rule, which fails 4 tests including `test_overlap_is_refused_even_when_activity_differs`, the specific regression it would have shipped. Positive controls are paired with every negative (`FEEDBACK` §17): a conforming write is asserted accepted and stored verbatim, a non-overlapping second row asserted accepted, and cross-user isolation asserted, so the refusals cannot be a validator that refuses everything. The two `context_builder` silent-drop sites were read in the source, not inferred: the day-map loop's `if d_lower in day_map:` with no `else`, and the bare `except (ValueError, IndexError): pass` — both now report into THIS WEEK FLAGS.

**Do not revisit unless:** the overlap refusal proves noisy enough in real use that the operator stops reading it — the failure mode this decision trades for, and the only one that would argue for narrowing the trigger back toward `activity`.

---

### 234. `#174` superseded — the `/health-connect/sync` collapse is six branches, and deletion alone does not make a name break loud

**Decision:** `#174` is superseded on two counts. **(1) Six dual-name branches, not five.**
`WriterIdentity.dataOrigin` / `.get_source_package()` is the same dual-name pattern on a live path and
is in scope (operator ruling, 2026-08-24); `.get_kg()` / `.get_meters()` remain out of scope, because
they unwrap Health Connect's nested `{inKilograms}` / `{inMeters}` shape for record types HCA does not
post — forward-compatibility, a different construction from a dual name. **(2) The deletion `#174`
specified does not deliver the loudness it claims.** `#174`'s rationale states that once dual
acceptance is gone "a rename 422s in test rather than degrading in production." That was false as
specified: no payload model set an extra-field policy (Pydantic v2 defaults to `ignore`) and every
canonical field was `Optional` with a `None` default — so a raw name would have been silently
discarded, the canonical field left null, and the handler would have returned `{"synced": N}` with no
error and no data. The load-bearing property was assumed, not built; `#235` builds it.

**The deletion rule, stated so three untouched dead surfaces do not read as a judgement call:** the
line is *the collapse breaks it*, not *dead code gets deleted*. `all_exercises()` was deleted because
branch 5 removes `SyncPayload.exercise`, which it reads — leaving it would ship a `NameError` in
waiting. `.get_kg()`, `.get_meters()` and `sport_name_for` are equally unreferenced-or-test-only and
are **untouched**, because dead-code cleanup is not this branch's concern. Deletion here is scoped to
references the collapse breaks.

**Why the premise failed rather than the reasoning:** `#174` chose a conformance test over codegen on
the ground of "exactly one fully-controlled client." That was true when written and is no longer — a
second client class (iOS/HealthKit) is a near-term proposition, the exact condition `#174`'s own *Do
not revisit unless* clause named.

**On the codegen ground specifically (a distinct correction, not a disturbance of the grounds above):**
`#174` rejected codegen *for the field-name contract*, but codegen already existed and was in use for
`SleepStageType` (`gen:contract` → `src/contract/sleepStages.generated.js`, `#24`). So the
machinery-cost argument for preferring a conformance test was weaker than it appeared — the field-name
arm would have been an **extension of an existing generator, not new machinery**. This does not disturb
`#234`'s grounds (six branches; absent loudness), which stand independently; it corrects `#174`'s cost
reasoning.

**Status:** Backend half implemented on `feat/hc-sync-contract-collapse` (this entry's branch). The
client-side conformance check (`#174`'s O3) is **deferred** behind the source-neutral contract ruled in
`#236`, so `Q5` closes on the backend golden fixture plus the negative battery — the half that is
hermetic and does not expire.

**How you know:** Suite 1113 → 1137, zero unadjudicated changes, both suites green. Fixture provenance:
**machine-verified against `health-connect-app` `7a63b15f91e33f6e508302d2054d36a760486c1c`**,
transcribed from the `fetchAllData` INLINE mappers (the sync path; the standalone `fetchSleepData` /
`fetchHRVData` copies are content-identical there but off-path — see `#236`). GATE 1, restated because
its own brief wording was falsified in-tree: the fixture populates **four** streams into `DailyRecord`
(steps, heartRate, hrv, sleep) and **five** into `health_connect_record_sources`; `_aggregate_day`
(`backend/routers/health_connect.py`) **never reads `workouts`** — HC exercise ingestion into the daily
row is deliberately held at `#189`, so the gap is held, not overlooked. The branch-4 negative
(`type ← exerciseType`) proves the **validator fires**, not that a live behavioural break was prevented:
there is **zero runtime read of `ExerciseRecord.type`**, a claim that rests on `sport_name_for` being
test-only (stated so it fails loudly if someone later wires it into production). Loudness proof is
`#235`. **Four brief/spec assertions were falsified in-tree this session** — `#174`'s own `:79`-style
line anchors (stale by ~110 lines), GATE 1's "five streams" wording, the "six 422s" claim (it is five;
see `#235`), and GATE 4's requirement, which the diagnostic first met only halfway until its own test
caught a loc-parse bug. Carried as evidence that the working model (chat infers, the tree adjudicates)
is operating as designed, not as a defect count.

**Do not revisit unless:** a second client lands on this endpoint before the source-neutral contract
(`#236`) exists, at which point the required-field coupling in `#235` binds two fleets and needs
re-ruling.

---

### 235. Loudness comes from required canonical fields with `extra="allow"`; the response accounts for what arrived, aggregated, and lost its writer

**Decision:** canonical record fields (`bpm`, `rmssd`, `date`, `type`) and the five envelope lists HCA
always sends (`sleep`, `hrv`, `heartRate`, `steps`, `workouts`) are **required** (lists emptyable, `[]`
valid); payload models set `extra="allow"`; a rejected body is diagnosed by SHAPE, never values.
`extra="forbid"` is **rejected**.

**The loudness table — three directions, three treatments:**
- **Canonical value absent → FATAL (422).** A missing `bpm`/`rmssd`/`date`/`type`, or a renamed envelope
  key (a renamed list defaults to `[]` and would report success, which is why envelope-required is
  needed on top of record-required).
- **Unknown surplus → INERT and RETAINED.** An additive key from a client that shipped ahead of the
  backend is kept in `model_extra`, not dropped and not fatal. `forbid` cannot tell this from a rename;
  required-plus-allow gives exactly that discrimination — absence fatal, surplus inert.
- **Attribution absent → TOLERATED and COUNTED.** The writer-identity branch is the one collapse branch
  whose rename does **not** 422: **five required-field renames 422; the writer-identity rename degrades
  to the documented `'unknown'`.** `sourcePackage` is optional by design (the `WriterIdentity` docstring;
  `#175`/Q83 — identity is not guaranteed, and a required field would 422 every legitimately-untagged
  record). So a `dataOrigin`-instead-of-`sourcePackage` payload parses and its writer coalesces to
  `'unknown'` at capture — silent loss of *attribution*, not of a *value*. It is made observable rather
  than left silent by the `unattributed` count below.

**`type: int`, not `Any` — the asymmetry named:** `bpm`/`rmssd`/`date` are typed (`int`/`float`/`str`)
and reject `null` natively; `type` was `Optional[Any]`, and a required `Any` accepts an explicit `null`.
`int` closes that, and preserves the enum's documented leniency (`ExerciseSessionType` header comment),
which defends unknown **codes**, not non-integer types — `int` admits every unknown code exactly as
`Any` did.

**`aggregated`, not `ingested`.** The per-stream response gains `received` (records as posted),
`aggregated` (records on a date that produced a `DailyRecord` row), and `unattributed` (writers degraded
to `'unknown'`). `aggregated.workouts` is honestly **0** — HC exercise is source-captured, its
`DailyRecord` ingestion held at `#189` — so the map is named `aggregated`: under the brief's `ingested`
the same 0 would have implied a permanent defect on every sync, the GATE 1 misread baked into a response
contract that outlives this session. `received` is counted **before** `_reject_pre2020` mutates the
payload, so the accounting reconciles; `unattributed` is tallied inside `_capture_record_sources`'s
existing pass, so the two counts cannot disagree about what was captured.

**Worked example of "absence becomes fatal":** `_reject_pre2020`'s dateless-steps path went from
*silently discarded* to *rejects the batch at validation* (a steps record with no `date` now 422s before
`_reject_pre2020` runs). Intended, not a regression; no test exercised it, so nothing moved.

**Two rules that live here, not in `FEEDBACK` (consequences of this decision's extra-policy, not
free-standing corrections):**
- **Reject diagnostics log SHAPE, never values.** Health data does not enter logs. The endpoint now
  carries more than one person's data; a rejected payload is a week of someone's heart rate, sleep and
  HRV, and logging the body would put it in Railway logs on every client defect, unbounded and
  unaudited. The diagnostic needs the shape (field paths, error types, key names, counts), never the
  values — a rename is fully diagnosable from names alone.
- **A fixture must not carry metadata in-band once the model under test retains unknown keys.** With
  `extra="allow"`, an in-band `_provenance` key would be retained in `model_extra` and contaminate the
  additive-unknown-key control; the golden fixture keeps provenance in a sibling file so it can stand as
  a clean "no unknown keys present" negative.

**Status:** Implemented on this branch. **LANDED ≠ LIVE:** the counts are emitted and consumed by **no
client** — `SyncScreen.js` discards the sync response at HCA `7a63b15` — so the operator surface is
Railway logs and direct DB inspection until an HCA update reads them. Consuming them is session-2-or-
later work. **OWED — the §8-class prod verification this line points at (owner: Luke, after merge +
Railway deploy):** one real sync from the operator's own device. The golden fixture is a transcription
of what HCA *should* send, not a capture of what the device *does* — and this session made a live
endpoint stricter. Concrete risk: `heartRateMapper` emits `bpm: s.beatsPerMinute`; if any real sample
ever carries `undefined`, JS drops the key and a required `bpm` 422s the whole batch. The SDK types say
it cannot (Likely) — but "the SDK types say" is the exact claim class this session falsified four times.
Whole-batch rejection was accepted here *because it is loud and diagnosable* (the Step-4 shape log names
the field), and the first real sync is what exercises that acceptance. PASS = 200, the three maps
present with sane counts, `unattributed == 0` or explained; FAIL = a 422 whose Step-4 log names the
exact field, which is the system working — followed by a fix informed by real data. Either outcome
closes the loop; only not running it leaves it open.

**DISCHARGED 2026-08-24 (post-deploy, owner Luke — the `§8` prod verification this line owed):** one real
sync ran against the deployed, now-stricter endpoint at `2026-08-24 10:43:37Z`. **PASS** — all eight
in-window dates upserted; the pre-window `synced_at` was left untouched (the upsert is non-destructive, the
property the *Do not revisit* clause below assumes); **no 422 and no `HC sync rejected` shape-log line**; and
`unattributed == 0` on every stream (`exercise` 75 / `sleep` 129 / `steps` 78 / `heart_rate` 49311;
`last_capture` 10:43:37). The `heartRateMapper` `undefined`→dropped-`bpm` risk this line named did not fire
on real data. **Structural finding, carried as a cross-ref, not a new question:** `health_connect_syncs.hrv_rmssd`
has never been populated (`COUNT WHERE NOT NULL = 0` over the table's life) and no `hrv` `record_type` has ever
reached `record_sources` — **Samsung Health does not write HRV to Health Connect**; the scraper path
(`samsung_hrv_readings`) is the sole HRV source. That gap is upstream of this contract and is exactly the
multi-writer HRV-source arbitration `#236`/`Q83` already own — the sync contract is sound, so `Q119` stays
OPEN at its current priority and no repair is owed here.

**How you know:** GATE 3 — fixture parses and populates identically to GATE 1 (value-identical); five
required-field renames 422, the writer-identity rename degrades to `'unknown'`, `type=null` 422s with
`int_type` (distinct from `missing`), additive top-level and record keys retained in `model_extra`.
GATE 3-M — four mutations, each caught by its intended gate and **no other**, including `type:int→Any`
failing **only** the null negative (proving the tightening has independent coverage) and a fifth harness
mutation that was a silent no-op, caught by the battery's own zero-failures check rather than passing as
green. GATE 4 — a raw-name payload yields a 422 and a shape-only log naming the missing canonical key
**and** the unknown key that replaced it; the requirement was first met only halfway (the unknown key
was absent) until the diagnostic's own test caught a loc-parse bug (FastAPI prefixes validation locs with
`body`); a sentinel value on the failing record is asserted **absent** from the log; a validation failure
on an unrelated route is byte-identical to a captured stock 422 (the handler delegates the response to
FastAPI's default on every path, logging only on the sync path); the handler is asserted wired onto the
real app **by identity** (FastAPI ships a default `RequestValidationError` handler, so presence is not
proof — `landed ≠ live`, `§8`). GATE 5 — `received` non-zero for all five streams, `aggregated` for
four with `workouts` 0 by design, an empty stream reads 0 and still 200, `unattributed` > 0 on the
branch-6 payload and 0 on the fully-attributed fixture, and a crafted three-record steps stream
reconciles each count individually (`received` 3, `rejected_pre_2020` 1, `aggregated` 1) rather than
asserting a brittle sum identity.

**Do not revisit unless:** the sync window stops being re-read on every sync (today a break is a
self-healing gap, not corruption, because HCA re-reads a rolling window and the upsert never overwrites
a stored value with null) — at which point a gap stops being self-healing and the required-field
coupling's cost calculus changes.

---

### 236. The wearable ingestion contract is source-neutral and carries metric identity; `/health-connect/sync` is an adapter behind it

**Decision:** the target architecture (E3) is a **source-neutral ingestion contract** that both the
Android/Health Connect client and any future client map into as adapters — not a shared
`/health-connect/sync` (whose name is false, HC being Android-only) and not per-source endpoints
duplicating aggregation, dedup and admission.

**The contract carries metric IDENTITY, not metric-named fields.** HealthKit exposes **SDNN**, not
RMSSD; Health Connect exposes **RMSSD**. They are different quantities and no coefficient converts them
— this repo already convicted that idea once (**Q17**: the RMSSD→SDNN ≈1.7× ratio, withdrawn as
coincidence). A payload field literally named `rmssd` receiving SDNN is the same silent-wrong-data class
this whole thread exists to close.

**Normalise the OUTPUT, never the metric.** Each `(user, source, metric)` stream carries its own
baseline; the recovery output is a position relative to that stream's own baseline, comparable across
metrics precisely because absolute scale cancels. Derivation lives downstream of ingestion so adapters
stay dumb and a fourth source stays cheap. Vendor indices are ingested and surfaced as **labelled
secondary signals**; the headline number is always own-derived, so no user gets a primary metric another
user structurally cannot have.

**Scope:** this branch is E3's **precondition**, not E3. A contract accepting two names per value cannot
be cleanly migrated — the adapter must know which name is real, and today the code said "either."

**Deferral, repriced (the earlier estimate was wrong and is corrected here so session 2 scopes from the
right one):** session 2 is **not** "build a conformance harness in a repo with no test runner." The
generator exists (`#24`), the direction (backend canonical → client conforms) is already right, and the
field-name arm is an extension. The generator **survives E3**; only the generated *content* expires (it
would assert HC-shaped field names against mappers E3 rewrites). Wasted content, not wasted machinery —
a real but smaller cost than first claimed.

**De-duplication is a named precondition of the adapter extraction.** HCA's sleep and HRV mappers exist
**twice** — standalone (`fetchSleepData` / `fetchHRVData`) and inline in `fetchAllData` — content-
identical at `7a63b15` but only the `fetchAllData` copies on the sync path. The E3 adapter extraction
must **de-duplicate, not move**, or the conformance surface binds a copy production does not execute.

**Also unaddressed here, and larger than this branch:** `_aggregate_day` averages HRV across **all**
writers with no source filter and no arbitration, and `#175`'s admission allow-list is referenced in a
docstring but not implemented. A second HRV writer therefore blends two devices — and, post-E3, two
metrics — into one mean. That gates a device switch, not just a second user. **Parked as one design
lane, not three questions:** the baseline specification (window, statistic, minimum sample count), the
confidence-tag composition, and multi-source arbitration are one problem — "take the higher-confidence
source" is circular until the tag is defined, and "if they match" is undefined until baselines exist,
since raw RMSSD and SDNN from the same night never match by construction. Operator ruling stands that a
degraded output ships with an honest confidence tag rather than being withheld.

**Status:** Design ruling; no code here beyond the precondition this branch lands. E3 is a horizon lane.

**How you know:** Design decision, chat-settled 2026-08-24, grounded on the collapse this branch
implements and on HCA source read at `7a63b15`. The metric-identity argument is anchored by Q17's
already-recorded withdrawal of the RMSSD↔SDNN conversion.

**Do not revisit unless:** a second source lands and forces the baseline/arbitration lane before it is
designed — the parked problem becomes blocking rather than horizon.

---

### 237. `/injuries` operator view — the reachable half of the #222/#223 resolution loop

**Decision:** ship a frontend-only `/injuries` surface over the existing #222/#223 endpoints: a
route in `App.jsx` + a hub `Tile` on `Dashboard.jsx`, a single `GET /knowledge/injuries?include_resolved=true`
fetch on load, an active list ordered by chain-earliest `added_at`, a display-only history toggle that
distinguishes **resolved** (`superseded_by` null, `resolution` block shown verbatim) from **superseded**
(names the successor id), and a per-row resolve gated on a human-authored `basis` (≥15-char client floor
over the server's non-empty floor) and a `resolved_by` tier. One row, one basis, one human — no bulk
resolve, no auto-resolve, no canned bases, no staleness heuristic (#223/#228). Cites #232 as its
constraint.

**Rationale — the ledger is write-only, NOT that a stale row corrupts readiness.** Chat (`source='chat'`),
the API (`source='api'`) and onboarding (`source='system'`) all write injury rows and no route retired
any, so the operator could add but not remove. That is the justification. The stale-row-suppresses-readiness
argument is explicitly NOT made: the five live rows for user 1 are all current and cross-referenced (the
finger row reads "Managed, not resolved"), and `is_contraindicated` never reads `restrictions[]` — it
fires only via a `body_part` substring against `_ACUTE_TISSUE_BLOCKS` plus the radicular/ra_flare arms,
so `pes anserine` and `finger` suppress nothing regardless of staleness. Accordingly the effect readout
asserts **no** contraindication (a server-side computation absent from the payload) and labels
`restrictions[]` "surfaced to sessions, not enforced".

**Corrects #232's "no new read required" for the injury store, and defers the badge:** the review flag
is derived by `injury_trajectory.evaluate()`, exposed only through `mcp_server.py`, absent from
`GET /knowledge/injuries` (which returns `value` unmodified) — and moot today, since no active row carries
`review_when`, so zero flags could fire. Re-implementing `_review_message`/`_divergence_message`
client-side is refused (a second copy drifts from the one #222's gates pin). Badge deferred until
`review_when` is populated, which is itself operator work.

**Surfaced, not fixed:** `added_at` was rewritten for ids 75–78 by a `source` backfill routed through
`upsert_knowledge_entry` (supersede-by-key mints a new row); `trajectory.declared_on` carries the same
artefact. The value shape has no onset field, so `/injuries` shows chain-earliest `added_at` as "on
record since" — a record-age floor, a compensation for the absent field, never labelled onset or age.
Logged as **Q120**. Two ROADMAP consequences banked the same session: the injury-ledger backfill-audit
lane is reframed (the active set has never been operator-reviewed against current truth; it is a
human-recall exercise, not a stale-row sweep), and the next injury-ledger build is an **edit-and-supersede
path** ahead of the #232 badge.

**Status:** DONE — landed via PR #100, merge `8098e63` (feature tip `5e31321`); branch merged + deleted.
Frontend suite **57 passed** (10 in `Injuries.test.jsx`); `npm run lint` at the pre-existing 6-error
baseline; `npm run build` clean.

**How you know:** merged to master — the `/injuries` route is present on `master:frontend/src/App.jsx`;
`placeholder guard (POSIX)` completed success on the head; reviewed by the operator ("Verified at
`5e31321`. All three edits landed as specified."). The chain walk is pinned by a scoped test: `injury_finger_left`
(id 77) renders its ancestor's June date and not its own August date.

**Do not revisit unless:** the value shape gains an onset field (Q120 decided), or the edit-and-supersede
path supersedes the resolve-only exit, or `review_when` begins being populated (at which point the #232
badge becomes a live surfacing-only read, not a client-side rule copy).

---

### 238. The human merge gate is removed — Code merges its own PRs on green
**Decision.** Code opens PRs ready-for-review, never draft, and merges its own PR once every
required check is green: no confirmation request, no waiting on the operator, no scheduled
check-in re-reporting a clean `mergeable_state`. A green PR left unmerged is a defect. One
exception — a PR containing a schema migration holds for explicit operator instruction, as does
anything a session was explicitly told to hold. `--merge` only, branch deleted and its
`BRANCHES.md` row flipped to DONE with the merge SHA in the same motion. Number-at-merge is
unchanged and now resolves against the merge Code itself performs.

**Rationale.** The gate never existed in the contract. The Merge path (#171) states the motion as
three acts ending in `gh pr merge --merge --delete-branch`, and `/closeout`'s terminal-state gate
requires every touched branch to end merged+deleted. Sessions nonetheless opened PRs as drafts,
asked whether to merge, then armed check-ins that repeatedly re-reported `mergeable_state: clean`
on PRs that were ready to land — and cited the merge path as the authority for doing so. That
citation was fabricated. The gate protected nothing: the ruleset already requires a PR and a green
`placeholder guard (POSIX)`, with no bypass actors, so the enforcement is server-side and does not
depend on a human clicking merge. What it cost was a round-trip per PR and a monitoring schedule
per PR.

**Status.** Locked. Shared loop rules, propagated verbatim to `health-connect-app`.

**How you know.** `CLAUDE.md` at master was read in full this session and contains no merge gate;
the #171 section constrains only `--auto`, `--admin`, and squash/rebase. Both repos' shared blocks
were confirmed byte-identical by `diff` before the edit. This PR is the rule's first exercise —
opened ready-for-review and merged on green without a confirmation request.

**Do not revisit unless.** A merge lands broken work that a required check should have caught —
in which case the fix is the check, not a human gate. Finding Code self-merging is not evidence
of a defect; it is this decision working.

---

### 239. Hevy strength → four-window load: persistence layer + Tier-0 design (Q6)

**Decision.** Land the persistence substrate the Q6 four-window load lane rests on, and
record the chat-settled Tier-0 design it will be built to (`#28` taxonomy/routing, `#32`
independent per-window τ, `#33` ΔLoad, `#79` key-on-template-id). The transform
(`load_events`) and the daily rollup (`load_metrics` + Banister) are sequenced AFTER, built
to this design. Seven sub-decisions, labelled D-A..D-G:

- **D-A · Window-native units.** Per `#32`'s independent channels, load units need no
  cross-channel commensurability — only internal consistency over time. Mechanical /
  Neuromuscular ship strength-native; Metabolic ships TRIMP-native. The first within-channel
  bridging decision triggers only when a second source enters a channel (Q115 is the expected
  trigger for Neuromuscular). SPEC — no unit code lands this session.
- **D-B · Two-level store.** `load_events` (append-only, per session-window, source refs +
  `formula_version`) → `load_metrics` (daily rollup, derived, recomputable). Coefficient and
  routing corrections are recomputes, never migrations of computed history. `hevy_workouts.raw`
  keeps the untouched payload so any transform version recomputes from source without a
  re-fetch. This removes Q115's stated migration-cost urgency. Store LANDED (`hevy_workouts`,
  `hevy_sets`); `load_events`/`load_metrics` are the next lanes.
- **D-C · Transform v1 (Tier 0, systemic).** Per normal set: Mechanical = weight_kg × reps ×
  mech(band); Neuromuscular = f(RIR)·h(I), RPE-dominant, intensity I = weight/e1RM as a bounded
  modifier (velocity-mandate proxy per `#32` — RPE/RIR is proximity-to-failure, the measurable
  correlate of velocity loss). Bands from (reps, RPE). All coefficients REASONED PRIOR,
  provenance-labelled per `#32`. Warmups excluded from NM, included in Mechanical at reduced
  band weight; failure sets are RIR 0 by definition. SPEC — the transform is a later session.
- **D-D · Non-rep sets are IN at Tier 0** (operator ruling 2026-08-25). Carries/sleds =
  weight × distance; timed holds = load × seconds. One named bridging constant maps kg·m and
  kg·s into the Mechanical kg·reps series — REASONED PRIOR, `formula_version`-tagged,
  recompute-cheap. NM from non-rep work = 0 at Tier 0 (flagged arguable for maximal sled
  efforts). SPEC. The store already persists `distance_meters` / `duration_seconds` for it.
- **D-E · Laterality session rule.** Template tag + paired same-template blocks in one session
  → one movement; halve the system-level double-count. Forward-stream convention (routine-creation
  enforcement via the `#13`/`#14` interception path): unilateral exercises are two blocks,
  sequenced left-then-right, side in note — yielding side identity for the asymmetry instrument.
  BACKFILL uses side-agnostic pairing only. One-block both-limbs entries and alternating
  single-blocks: template tag governs, never note parsing. LANDED as the data mechanism
  (`laterality.detect_session_pairing`): unilateral + ≥2 blocks → paired; untagged + ≥2 blocks →
  indeterminate (surfaced, never guessed); the halving itself is the transform's.
- **D-F · Step detection flags, never auto-corrects.** Within-exercise weight discontinuities
  (venue/machine change) are flagged for operator annotation + recompute, never auto-corrected.
  In-data evidence: Face Pull 2:1 note 21 Jul, Hip Thrust leverage note 10 Aug, Leg Extension
  117→55 (bilateral→unilateral machine — a laterality change presenting as a scale step, which
  is exactly why auto-correction is forbidden). SPEC — detection is a transform-adjacent lane.
- **D-G · Dedup is flag-and-adjudicate.** PK-upsert on the Hevy workout id; same-window
  high-similarity pairs flagged for operator adjudication, NEVER auto-dropped. Adjudicated-out
  workouts leave load via an exclusion mark (`excluded_at`), not deletion. LANDED
  (`hevy_workouts.detect_duplicate_pairs` + `_recompute_dedup`): sync-derived
  `dedup_flag`/`dedup_partner_ids` recomputed each run; `excluded_at`/`exclusion_reason`
  operator-owned and never touched by sync.

**Rationale.** Q6's DONE condition — "a query shows strength volume landing in the load path" —
was unrunnable because nothing persisted Hevy workouts at all (`to_regclass('public.load_metrics')`
NULL; `mcp_server.get_training_load` aerobic-only). The design was fully settled in chat but had
no substrate to be built on or verified against. Persistence-first makes the transform buildable
and its DONE condition a real query. Splitting store from transform follows D-B: computed history
is a recompute, so the expensive, revisable part (coefficients, routing, bridging constants) never
becomes a migration. The two mechanisms that ARE fully determined by the data shape rather than by
tunable priors — laterality pairing (D-E) and dedup (D-G) — land now with the store, because they
are read off block structure and workout identity, not off a coefficient anyone will revise.

**Status.** Store + D-E + D-G LANDED and test-proven (pairing positive/negative/mutation-proofed;
dedup positive/negative/fail-closed; idempotent re-ingest; exclusion mark survives resync).
D-A/D-C/D-D/D-F are SPEC for the sequenced transform lanes. PR HELD for operator per `#238`'s
schema-migration exception (this lane adds `hevy_workouts`/`hevy_sets`).

**How you know.** `backend/tests/test_laterality_pairing.py`,
`test_hevy_workouts_ingestion.py`, `test_laterality_coverage_audit.py` pass (28 tests); the
migration compiles to valid Postgres DDL under the `postgresql` dialect and the models build on
the SQLite test engine via a `JSON().with_variant(JSONB, "postgresql")` column. The prod
assertions (row counts > 0, 180-day span, the two known dedup pairs listed) are the post-deploy
gate the operator runs after landing — "landed ≠ live".

**Do not revisit unless.** A coefficient/routing correction is proposed — that is a recompute
against `load_events`, not a change to this store (D-B). Reopening the store shape (adding an FK
from `hevy_sets.exercise_template_id` to the catalogue, auto-correcting weights, or auto-deleting
duplicates) reintroduces exactly the failure modes D-F/D-G/#79 forbid.

---

### 240. Q6 gate 1 verified live; the FK-ordering ingest defect; the test engine now enforces prod's constraints

**Decision.** Q6 gate 1 (the `#239` persistence layer) is landed AND live-verified, and two
corrections ride with it. (a) The first prod backfill raised a `hevy_sets_workout_id_fkey`
ForeignKeyViolation at `sync_one_user`'s single commit: `SessionLocal` runs `autoflush=False`
and the models carry FK columns but no `relationship()`, so the unit of work emitted the
`hevy_sets` batch before its parent `hevy_workouts` rows. Fixed by an explicit `db.flush()` in
`_upsert_workout` (parent before children; covers first-ingest and the resync delete-then-insert)
— `#104`. (b) The suite never caught it because SQLite ships FK enforcement OFF: the test engine
was FK-blind. **Standing policy: the test engine now runs prod-faithful — `PRAGMA foreign_keys=ON`
AND `autoflush=False` (conftest) — and every fixture seeds its referenced parents** (`#105`, 71
fixtures across 12 files fixed; no constraint relaxed; tests-only). A future session must not
relax the test engine back toward SQLite defaults to make a fixture pass.

**Rationale.** An integrity constraint the test substrate does not enforce is a constraint that
is only tested in production. The FK-ordering bug was invisible to a green suite and cost a
rolled-back first backfill; the cheapest place to catch that class is the test engine matching
what Postgres enforces. The store shape itself (`#239`) was sound — the defect was in the write
ORDER and in the substrate that failed to check it, not the schema.

**Status.** Locked. `#103` (215435f), `#104` (b42e32a), `#105` (d5875a3) merged; backend deploy
`9b6ad5de` SUCCESS on d5875a3; backfill re-run clean.

**How you know.** Prod psql this session: `hevy_workouts` COUNT 56, span 2026-04-05 10:15 →
2026-08-24 17:58, `hevy_sets` COUNT 1710, `dedup_flag` rows exactly 4 (the two known pairs);
operator adjudication excluded the two planned-routine-artifact copies → effective 54/1609. The
FK-ordering regression reproduces the exact IntegrityError on an FK-enforced + autoflush=False
engine pre-fix and passes post-fix; full suite green (1164) but for the pre-existing
`test_context_builder_output_unchanged_pre_post_refactor` shallow-clone artifact.

**Do not revisit unless.** A fixture genuinely needs a row with no real parent (none found this
session) — then model the parent, never drop FK enforcement. Reintroducing an FK-blind or
autoflush=True default reopens exactly the gap `#104` was shipped green through.

---

### 241. Q6 gate 2 — the Tier-0 `load_events` transform (D-C/D-D), `formula_version` 'tier0-v1'

**Decision.** The four-window load transform is built and lands to spec: `hevy_workouts.raw`
(gate 1, source of truth) → `backend/load_events.py` (Tier-0 D-C/D-D) → the new `load_events`
store, one **Mechanical** and one **Neuromuscular** row per non-excluded session, window-native
units (D-A). This is the *derive* half of the two-level store (D-B): `load_events` is
recomputable, so every constant below is a REASONED PRIOR (#32) tagged `formula_version =
'tier0-v1'`, and a correction is a **recompute** (bump the version, re-derive) — never a
migration of computed history, never an edit to the constants recorded here. Metabolic and
Psychological windows are NOT fed by this transform (aerobic / sRPE, separate sources — the
store is source-neutral for them, #236).

Operator inputs (2026-08-25): `EPOCH_RPE_COMPLETE = 2026-05-11`, `BODYWEIGHT_KG = 102`. The
routing, exactly as built:

- **Per normal rep set.** Mechanical = `effective_weight × reps × m(RIR)`; Neuromuscular =
  `f(RIR) · h(I)`, RPE-dominant, `I = effective_weight / e1RM`. Bands m/f from RIR = 10 − RPE.
  `m`: RIR≥4→1.0, 2–3→1.15, 0–1→1.30. `f`: ≥5→0, 4→.25, 3→.5, 2→.75, 1→.9, 0→1.0.
  `h(I) = 0.25 + 0.75·clamp((I−0.40)/0.45, 0, 1)`; **no e1RM fit → h = 0.5**.
- **Missing-RPE rule — PER-SET, date-independent.** A set with an `rpe` bands on (reps, RPE)
  **whatever its date**; a set without one takes the reps-band prior. **No imputation, ever.**
  RPE-absent rep set: Mechanical `m = 1.0`; Neuromuscular = the reps-band prior (reps≤5→0.6,
  6–11→0.35, ≥12→0.15), no h(I). (This supersedes the brief's/ROADMAP's older "pre-epoch RPE
  bands by reps alone" wording — "pre-epoch RPE is not trusted" appears in no decision and is
  removed; the epoch is diagnostic-only, below.)
- **e1RM.** Per-template Epley-with-RIR `w·(1 + (reps + RIR)/30)`, RIR the continuous 10−RPE,
  rolling 60 d, **fitted from ALL RPE-present working sets, ANY date** (failure sets, which carry
  no `rpe`, do not fit it). An RPE-absent set may CONSUME a fit but never UPDATES it; a session's
  own top set may set its own intensity reference (window is `≤ as_of`).
- **Warmups** ×0.5 Mechanical, **excluded from NM**. **Failure type = RIR 0** by definition (a
  set-type fact, needs no `rpe`).
- **Non-rep work (D-D).** Carries/sleds and timed holds bridge into the Mechanical kg·reps
  series: Mechanical `+= effective_weight × distance_m × K_dist` (`K_dist = 0.3`) and
  `+= effective_weight × duration_s × K_time` (`K_time = 0.05`). **NM from non-rep = 0** at Tier 0.
- **Bodyweight.** `effective_weight = weight_kg` when present and > 0, else `BODYWEIGHT_KG` (pure
  bodyweight). Weighted-bodyweight (an added plate) uses the plate alone at Tier 0 — a known
  undercount, **surfaced** (OPEN_QUESTIONS Q121, Tier-0-gaps item), never silently corrected.
- **Laterality — LOAD SUMS SETS AS LOGGED (D-E supersession).** Unilateral work is genuine work
  (3 sets/leg of 40kg×10 = 2400 kg·reps, at parity with the bilateral equivalent), so the D-E
  pairing **NEVER discounts cost** — the halving is narrowed to the movement-count / asymmetry
  instrument. `laterality.detect_session_pairing` is retained for **`provenance` only**:
  `paired_templates` (unilateral in ≥2 blocks) and `indeterminate_laterality` (untagged in ≥2
  blocks) are both surfaced for that instrument, applied to no load sum. (Supersedes `#239` D-E's
  "the halving itself is the transform's" for the load path.)
- **Epoch — DIAGNOSTIC ONLY.** `EPOCH_RPE_COMPLETE` gates no cost and no e1RM path. Its one use:
  a rep-based workout **on/after** it whose working sets carry no RPE at all is a
  planned-vs-performed artifact signature (D-G hardening candidate), flagged `post_epoch_zero_rpe`
  in `provenance`.
- **Dedup respected from day one (D-G).** The transform reads `excluded_at IS NULL` — an
  adjudicated-out artifact never enters load.
- **RIR banding of half-point RPE.** RIR = round-half-up(10 − RPE), clamped ≥ 0 — a deterministic
  Tier-0 choice, flagged for Tier-1 review (OPEN_QUESTIONS Q121).

Gate-2 agenda item 4 rides here: **`hevy_workouts._rpe_coverage` is corrected** — denominator is
now `reps IS NOT NULL` over non-excluded, in-window workouts (DB-queried, `excluded_at`-aware),
replacing `type == 'normal' AND weight_kg IS NOT NULL`, which dropped bodyweight rep sets and
hinged on a frequently-null `type` (both demonstrated by prod 2026-08-25). Keys renamed
`normal_weighted_sets` → `rep_sets`.

**Rationale.** D-B's whole point is that the revisable part of the pipeline (coefficients,
routing, bridging constants) lives in a recompute, not a migration. Persisting per-session-window
events keyed on `(source, source_ref, window, formula_version)` makes a coefficient correction a
delete-and-reinsert of one `formula_version` — landed history for other versions is untouched, and
the daily rollup (gate 3) reads whichever version it is pinned to. Recording the transform's gaps
in `provenance` (RPE- vs reps-banded counts, e1RM fit vs 0.5 fallback, non-rep contribution,
`paired_templates` / `indeterminate_laterality` surfacing, `post_epoch_zero_rpe`) means the
coverage of a computed value travels with it — the "gap recording" the brief names — instead of
being re-derived downstream. Load itself sums sets as logged; laterality and the epoch inform the
asymmetry and dedup instruments, not cost.

**Status.** Built and test-proven; not yet live. **PR HELD for operator per `#238`'s
schema-migration exception** (adds `load_events`, migration `c7d9e2f14a86`). The live recompute
(`python backend/load_events.py --user <id>` after deploy, then per-window row counts and a
provenance spot-check against the 54/1609 gate-1 substrate) is the post-deploy gate — landed ≠ live.
Gate 3 (the `load_metrics` + Banister daily rollup, reading these events) is the next lane.

**How you know.** `backend/tests/test_load_events.py` (37 cases: band tables + every routing branch
mutation-proofed; **RPE-is-per-set-any-date** — a discarded pre-epoch RPE FAILS; **load-sums-as-logged**
— a halved unilateral cost FAILS; e1RM fits pre-epoch RPE too; the `post_epoch_zero_rpe` diagnostic;
`excluded_at` skipped; idempotent per-`formula_version` recompute; provenance gaps) and the two
rewritten `test_hevy_workouts_ingestion.py` coverage cases pass; full backend suite green (1197
passed) but for five failures that reproduce identically on the clean tree pre-change (four
date-sensitive: `test_capability_observations`, three `test_cbti_eval_trigger`; plus the `#240`
`test_context_builder_output_unchanged_pre_post_refactor` shallow-clone artifact).
`load_events` renders valid Postgres DDL under the `postgresql` dialect and builds on the
FK-enforced SQLite test engine via the `_JSONB` variant. Migration `c7d9e2f14a86` chains
`f9a2c1d40b73` → head (the pre-existing second head `e2d5c7a1b9f3` predates this branch on master
and is untouched — a separate governance matter, flagged not fixed).

**Do not revisit unless.** A coefficient, band, or bridging constant is corrected — that is a
**recompute under a new `formula_version`**, not a change to `load_events`' shape and not an edit to
the constants above (supersede by a new entry). Do **not** reinstate epoch-gated RPE or laterality
halving in the load path — both were review-rejected here (`#238`-gate PR): RPE is per-set and
date-independent, load sums sets as logged, and the epoch is diagnostic-only. Reopening the store
shape (a hard FK on `source_ref`, per-window separate tables, or dropping `formula_version` from the
natural key) reintroduces exactly the recompute-as-migration coupling D-B forbids. The known Tier-0
modelling gaps (weighted-bodyweight undercount, non-rep NM = 0, half-point RIR banding) are logged
as OPEN_QUESTIONS Q121 for Tier-1, not a defect in this entry.

---

### 242. Q6 gate 2 verified live; Q6's DONE condition met — strength volume in the per-window load path

**Decision.** Q6 gate 2 (the `#241` `load_events` transform) is landed AND live-verified on prod,
and Q6's standing DONE condition — a real query showing strength volume landing non-zero in
per-window load rows — is **MET for the first time since Q6 was filed**. The merge (`c36825d`, PR
#107) deployed clean: backend deploy SUCCESS, boot log
`Running upgrade f9a2c1d40b73 -> c7d9e2f14a86, add_load_events` then `Application startup complete`;
the dual-head signature (`Multiple head revisions`) did NOT fire.

**How you know.** Prod recompute (`compute_load_events`, `formula_version 'tier0-v1'`): sessions 54,
events_written 108, sessions_with_e1rm_fit 36, sessions_reps_banded 24 (April/early-May, the bounded
pre-RPE-epoch era — as designed), sessions_indeterminate_laterality 0, sessions_artifact_signature 0.
Q6 closing query (prod, per-window `load_events` sums over 54 non-excluded sessions):
**Mechanical 3,056,351.056 `kg_reps`; Neuromuscular 480.818 `nm_au`** — both non-zero, one row per
window per session. The zero indeterminate-laterality and zero artifact-signature counts confirm the
current store needs no laterality adjudication and carries no post-epoch 0-RPE planned-routine
artifact; the 24 reps-banded sessions are the pre-epoch tail banding by reps alone (per-set rule,
not an epoch gate). The rows are in `load_events` (the transform output); the `load_metrics` daily
rollup is gate 3 (unbuilt) — Q6's DONE bar is strength volume demonstrably in the per-window load
path, which these rows satisfy.

**Status.** Q6 DONE. Gate 3 (`load_metrics` + Banister fitness-fatigue per `#32`) is the next lane
(ROADMAP "Banister build" NOW). Two carried notes recorded here so they survive the session:

- **Standing correction (process) — a held PR is held for the RELEASE DECISION only.** On release,
  Code executes the ENTIRE land end-to-end: resolve `#NEXT` at the re-read master max → push →
  confirm the guard green → un-draft → merge (merge commit) → delete branch → verify the Railway
  deploy reaches SUCCESS and the migration applied in the boot logs. The operator's residue is the
  release decision itself, prod-credentialed execution, and data-judgement calls — nothing
  mechanical. Full rule in `FEEDBACK.md` §1. This refines `#238` (which removed the human *merge*
  gate; this clarifies that a `#238` schema-migration hold gates the release decision, not the
  mechanical land that follows it).
- **Container-tooling note.** `psql` is absent from the current `health-app-backend` image;
  `railway connect` (to the `health-app-DB` service) is the operator's psql route for prod queries
  like the closing query above. Recorded so a future session does not assume an in-container `psql`.

**Do not revisit unless.** The recompute numbers above are superseded by a `formula_version` bump
(then re-verify live and supersede by a new entry). The parked pre-existing second alembic head
`e2d5c7a1b9f3` (predates the Q6 lane; `#241`) is a **latent hazard for whoever owns it** — gate-1
and gate-2 deploys both booted clean with both heads present, but a future migration that needs a
single linear head, or an `alembic upgrade head` (singular) path, will trip `Multiple head
revisions`; resolve it with a merge migration when that lane is picked up, not here.

---

### 243. Tier0-v1 defect — the bodyweight COALESCE leaked into the non-rep branch and priced Hevy cardio as mechanical work

**Decision.** Fix a correctness defect in the `#241`/`#242` `load_events` transform, same
`formula_version 'tier0-v1'` (the spec was right; the implementation was wrong — D-B: a correction
is a recompute that replaces same-version rows by natural key, never a version bump). `_effective_weight`'s
bodyweight COALESCE (102 kg) was applied in the **non-rep** branch of `compute_set_load`, but the
brief's bodyweight fallback is **rep-based only**. A weight-NULL non-rep set must score **zero both
windows** — that zero is the mechanism that excludes Hevy cardio (treadmill/bike/row distance- and
duration-only entries carry no `weight_kg`) **without a template denylist**. As built, a 5 km
treadmill entry scored 102 × 5000 × `K_dist` 0.3 = **153,000 `kg_reps`**, so Flush/Recovery and
physio (bodyweight-hold) sessions topped the Mechanical ranking and the top-10 was all April–May.

**Fix.** In the non-rep branch, `weight_kg is None → SetLoad(skip=True)`. Weighted carries / sleds /
timed holds (weight present) bridge exactly as before via `K_dist` / `K_time`. Bodyweight timed
holds (planks, Copenhagens) score zero at Tier 0 — the named, accepted D-D limitation. No schema
change → merged on green per `#238`.

**Rationale.** The zero-for-bodyweight-non-rep rule is not an omission but a load-bearing exclusion:
it is *how* the systemic Mechanical channel keeps aerobic/cardio work out of a strength-volume series
that has no commensurability with it (D-A window-native units), with no per-template denylist to
maintain. Pricing cardio distance at bodyweight silently routed the largest-magnitude non-strength
entries into the channel and inverted the ranking.

**Status.** Locked. Fixed + test-proven; `formula_version` unchanged.

**Defect window.** Prod `load_events` (tier0-v1) written by the `#242` post-`#107` recompute carried
the inflated Mechanical for weight-NULL non-rep entries until the post-`#243` recompute. Because the
recompute replaces the same `(source, source_ref, window, formula_version)` rows, the operator's
post-deploy rerun overwrites them cleanly — **the `#242` closing number (Mechanical 3,056,351.056
`kg_reps`) is defect-affected and superseded by that rerun**; Neuromuscular (480.818 `nm_au`) is
unaffected (non-rep NM was already 0). Q6 stays DONE — strength volume is in the per-window path;
only the Mechanical magnitude was wrong.

**How you know.** `backend/tests/test_load_events.py`: `test_non_rep_weight_null_distance_skips`
(mutation-proof — a bodyweight-priced 5 km cardio set FAILS) and `test_non_rep_weight_null_timed_hold_skips`
assert skip; `test_non_rep_weighted_distance_bridged_nm_zero` / `test_non_rep_weighted_timed_hold_bridged`
assert weighted non-rep still bridges. 39 transform cases pass; full suite green but for the `#240`
`test_context_builder_output_unchanged_pre_post_refactor` shallow-clone artifact.

**Do not revisit unless.** Tier 1 gives bodyweight timed holds / bodyweight cardio a real load model
(then a `formula_version` bump, not a re-COALESCE in the non-rep branch — reintroducing
`_effective_weight` there is exactly this defect). The weighted-bodyweight-rep undercount and non-rep
NM=0 remain the `Q121` Tier-0 gaps.

**Closing figures (operator recompute 2026-08-27, deploy `9583a992`, in-container
`/opt/venv/bin/python load_events.py`).** User 1, `tier0-v1`, 54 non-excluded sessions — shape
identical to `#242` (sessions 54 / events 108 / e1rm_fit 36 / reps_banded 24 / indeterminate 0 /
artifact 0):

- **Mechanical 924,082.523 `kg_reps`** (was the defect-affected 3,056,351.056). The headline drop is
  this entry's cardio exclusion; `#244`'s floor also nudges the mechanical band up for RPE-8.5 and
  RPE-6.5 boundary sets (`m` 1.15→1.30 / 1.0→1.15), and `#245` contributes exactly 0 (all
  `bw_fraction` NULL, below), so this figure is `#243`+`#244`, not `#243` alone.
- **Neuromuscular 522.480 `nm_au`** (the `#242` number was 480.818).
- **Ranking pass.** Mechanical top-10 is strength sessions Apr–Aug, no Flush/Recovery or physio,
  no April–May cluster — the inversion this entry fixed is gone.

**The NM movement is real, and it is NOT this entry's.** The "Neuromuscular (480.818 `nm_au`) is
unaffected" claim above is correct **as scoped to `#243`** — but the operator's single recompute at
`9583a992` carries `#243`+`#244`+`#245` together, so its closing NM is 522.480, not 480.818. The
+41.66 `nm_au` is caused by **`#244`** (the `floor(10 − RPE)` RIR convention), the only NM-path change
in the recompute window that raises NM. Traced against the brief's candidate order (a)→(b)→(c); (b)
accounts for it:

- **(a) — the non-rep skip shifting the per-template e1RM fit — is impossible, not merely absent.**
  `e1rm_samples` filters `rpe is None or reps is None or weight is None or weight <= 0`, so a
  weight-NULL **non-rep** set (reps None, weight None) was NEVER in the e1RM fit, before or after this
  entry; and `2dc23e1` touched only the non-rep **mechanical** branch (which already returned
  `neuromuscular=0.0`). `#243` moves NM by exactly 0.
- **(b) — `#244`'s RIR floor — is the cause.** The diff window is `git diff c36825d..ec02436 --
  backend/load_events.py` (`c36825d` = `#242`'s merge, the 480.818 baseline; `ec02436` = current
  master), and it holds only `#243`/`#244`/`#245`. Of those three: `#243` is NM-neutral (above);
  `#245` `bw_fraction` contributes **exactly 0** to this recompute: every template's `bw_fraction` was
  still NULL (≡ ×1.0; operator-confirmed, the tagging pass is pending — so the ×1.0 bodyweight overcount
  `#245` exists to remove is still live in prod, and these figures pre-date the tagging). So `#244`'s
  floor **owns the entire +41.66 outright**, not "net of two effects". (Once templates are tagged,
  `bw_fraction ≤ 1.0` — push-up ~0.65 … chin/dip 1.0 — could only *lower* `h(I)=eff_w/e1RM` and thus NM,
  and would be inert wherever a bodyweight-class template with no weighted set hits the `h=0.5` fallback;
  that is the direction of the next recompute, not this one.) Mechanism confirmed on the pure functions:
  floor lowers the banded RIR by 1 for every half-integer `10 − RPE`, raising `f(RIR)` by +0.10…+0.25
  (×`h`) per half-point-RPE working set (e.g. RPE 8.5 → RIR 1.5 → band 1 not 2 → `f` 0.9 not 0.75), and
  leaves every whole-number-RPE set exactly unchanged (`floor(x)=floor(x+0.5)` for integer `x`).
- **(c) — a `hevy_workouts.raw` re-sync with revised RPEs — is ruled out by the recompute's own
  diagnostic shape.** The ANCHOR reports counts identical to `#242` (54 / 108 / 36 / 24 / 0 / 0); a
  re-sync that changed RPEs or session/set composition would move `reps_banded` / `e1rm_fit` /
  `sessions`. Not needed to explain an increase the code change already forces.

No code defect exposed — `#244`'s floor is a deliberate convention, working as designed — so this stays
a governance-only recording, not a concern-split fix.

**How you know.** `git diff c36825d..ec02436 -- backend/load_events.py` = `#243`/`#244`/`#245` only;
`git show 2dc23e1 -- backend/load_events.py` touches only the non-rep mechanical branch; `e1rm_samples`
carries the `reps/weight` filter that makes candidate (a) impossible; the `_rir_from_rpe` half-up→floor
grid over `_f_rir` shows a strictly non-negative per-set NM delta (positive only on half-point RPEs,
zero on whole RPEs); `#245`'s NM delta was exactly 0 in this recompute (every `bw_fraction` NULL,
operator-confirmed; `≤ 0` in general since `bw_fraction ≤ 1.0`); the ANCHOR's identical diagnostic shape
closes (c).

**Open item — RESOLVED by operator (2026-08-27).** `window` is a Postgres reserved word and the
`load_events.window` column already needs quoting in hand queries. The fork was: **rename the column**
(a schema migration — holds for explicit operator instruction per `#238`/CLAUDE.md merge-disposition)
**vs. live with quoting** every reference. **Operator's call: rename now**, to `load_window` (keeping the
D-A window vocabulary), while `load_events` is the sole 108-row table carrying the name and the rename is
trivially reversible — before Gate 3's `load_metrics` inherits it and the name is two tables plus every
rollup query. Executed as its own concern-split migration PR, **held for the operator's release decision**
per `#238`; the decision and its migration are recorded in that PR's DECISIONS_LOG entry, not here.

---

### 244. The "fourth defect" was not one — the mechanical formula is spec-correct; RIR banding is pinned to `floor`

**Decision.** A reported fourth transform defect — "mechanical priced off the Epley factor, e1RM leaked
into the mech path" — was **investigated at the line and disconfirmed**. The mechanical path is
`eff_w × reps × m(RIR)` in **every committed version** (`dd7193c` gate 2, `2dc23e1` `#243`); `epley_with_rir`
is called **only** inside `e1rm_samples`, which feeds the Neuromuscular `h(I)` — never the mechanical
sum. A runtime probe confirmed the code computes `eff_w × reps × m` even when a non-null `e1rm` is
passed (an Epley leak would have used it). No code defect exists in the mechanical formula.

**Reconciliation of the anomaly.** The operator's 13 Jul Upper-A stored Mechanical (35,367.5125) exceeded
a hand oracle (22,790.575) by ~55%. The gap is **two committed conventions**, not a bug:
- **0-falsy `_effective_weight`** — two sets logged at `weight_kg = 0` (a logging dead-bug) fall through
  the `weight > 0` test to `BODYWEIGHT_KG` (102). **Deliberate and correct**: a 0/NULL-weight rep set is a
  bodyweight movement. Kept.
- **RIR banding convention** — the hand oracle used fractional RIR; the code banded RIR to an integer
  before the `m()`/`f()` tables. The banding rule was **unspecified at gate 2** and `round()`/half-up
  filled it silently (RPE 8.5 → RIR 1.5 → 2 → m 1.15).

**Minted convention.** RIR = **`floor(10 − RPE)`**, clamped ≥ 0 (RPE 8.5 → RIR 1 → m 1.30). A half point
that is "not quite N reps in reserve" bands to the harder (N−1) tier, never rounds up to the easier one.
This is a **convention choice, not a defect fix** — it changes only half-point-RPE sets. `formula_version`
stays **`tier0-v1`** (the spec was never wrong; an unspecified corner is now specified); the recompute
replaces same-version rows by natural key (D-B), so the operator reruns recompute + rankings after deploy.

**The regression fixture is the class-closer.** A single-session reconciliation test over the real 13 Jul
workout (56 sets embedded) asserts the session's Mechanical **and** Neuromuscular totals to the cent
against a **hand-computed arithmetic oracle in comments** under the live convention (`floor` RIR; 0-falsy
bodyweight; warmup ×0.5 after `m`). The oracle is arithmetic, not code — it cannot pass by implementing the
wrong spec, which is how defects 1, 2, `#243`, and this convention gap all survived a green suite. The
third and fourth findings came from **external reconciliation, not the suite**; this fixture is what
changes that. "Looks sane" is retired as evidence — NM had looked sane twice while Mechanical looked sane
once.

**Status.** Convention change + reconciliation fixture landed together. The 13 Jul fixture
(`test_load_events_reconciliation.py`, 56 sets embedded, hevy_id `6d8b2f4d…`) reconciles both windows
**three ways in exact agreement**: Mechanical **36,458.575 `kg_reps`** (operator hand derivation =
fraction-exact hand derivation = code) and Neuromuscular **14557/720 ≈ 20.218056 `nm_au`** under an
embedded e1RM map (`SHP → 60`, h computed; rest → `H_NO_E1RM` 0.5). Prior recompute rankings are
**void** pending the post-`#244` recompute. No schema change → merge-on-green per `#238`.

**How you know.** `git show dd7193c:backend/load_events.py` and `2dc23e1:…` both carry
`mech = eff_w * float(reps) * m`; `epley_with_rir` appears only at the `e1rm_samples` call site. Runtime
probe: `compute_set_load({w:100,reps:8,rpe:8}, e1rm=133.33).mechanical == 100*8*1.15` (919.99), not the
Epley-leak 1226.67. `test_rir_from_rpe_floor_and_clamped` pins 8.5→1 / 7.5→2 (mutation-proof vs half-up);
the 13 Jul reconciliation fixture asserts both window totals to the cent.

**Do not revisit unless.** Tier 1 replaces integer RIR banding with f/m interpolation across the half
(OPEN_QUESTIONS Q121) — a `formula_version` bump, not an edit here. Reintroducing `round()`/half-up, or
reading an `e1rm`-derived quantity into the mechanical path, is exactly what this entry and the fixture
forbid.

---

### 245. `bw_fraction` — the per-template bodyweight fraction, promoted build-now ahead of gate 3

**Decision.** Promote the flat-bodyweight-fraction gap (OPEN_QUESTIONS Q121 gap 4) from Tier-1 to
**build-now**, landing it **before** gate 3 so the ×1.0-bodyweight distortion never enters the EWMA
history the Banister engine builds on. New operator-owned column
`hevy_exercise_templates.bw_fraction FLOAT NULL` (migration `d4a1f8c609e2`); the Tier-0 transform
reads it ONLY for rep-based sets with `weight_kg` NULL or 0:
`eff_w = BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0)`. **A logged `weight_kg > 0` is never scaled by
it** — `bw_fraction` touches no real load. `NULL` fraction ≡ the prior ×1.0 behaviour, so the change
is opt-in per template and an untagged catalogue is unchanged. `formula_version` stays **`tier0-v1`**
(a modelling refinement inside the frozen convention set, applied by recompute — D-B; not a version
bump). The weighted-bodyweight ADDITIVE case (bodyweight + plate) stays the parked Tier-1 limitation,
unchanged.

**Fraction semantics.** `bw_fraction` is the fraction of bodyweight moved per rep for a
bodyweight-CLASS movement — no separate leverage axis (Hevy already splits elevated/decline/ring
variants into distinct templates). REASONED-PRIOR priors, **guidance not gospel** (biomechanics
literature ballpark; the operator assigns the live values in the tagging pass): chin/pull-up ~1.0,
dip ~1.0, push-up ~0.65, BW squat/lunge ~0.85, Nordic ~0.9, dead bug ~0.25; plank-class is N/A
(non-rep, already zero by D-D). Operator-owned like `laterality`: `_upsert_template` never assigns
it, so a Hevy resync preserves it. The tagging surface is `audit_bodyweight_templates.py` — every
in-use template that has ever logged a 0/NULL-weight rep-based set, with usage counts (catalogued vs
uncatalogued); nothing else needs a tag.

**Validation carried.** Retrospective **face-validity passed 5/5** on the post-`#244` rankings
(operator, 2026-08-26). With that, the **`tier0-v1` constants are frozen under the `#244`
conventions** (floor RIR, 0-falsy bodyweight, load-sums-as-logged, non-rep skip, `formula_version`
recompute-not-migrate) — `bw_fraction` is a per-template data annotation on top, not a constant change.

**Status.** Built + test-proven. **PR HELD for operator per `#238`'s schema-migration exception**
(adds the `bw_fraction` column). On release, Code executes the full land; then the operator runs the
tagging pass + recompute + ranking re-read, and gate 3 (`load_metrics` + Banister) follows.
**Q121 gap 4 → RESOLVED** by this entry (the flat-fraction gap is closed; the additive
weighted-bodyweight case remains, noted in Q121).

**How you know.** `test_load_events.py`: NULL fraction ≡ ×1.0, a fractional template scales only
0/NULL-weight sets, and a logged-weight set is provably untouched (mutation-proof); DB test drives
`bw_fraction` off the templates table on the FK-enforced substrate. The 13 Jul reconciliation fixture
updated **in the same commit** per its standing rule: with Weighted Dead Bug tagged `0.25`, its two
0 kg sets reprice 102→25.5 → Mechanical **26,207.575** (untagged stays **36,458.575**; delta −10,251
is exactly those two sets), NM unchanged (WDB has no e1RM). `audit_bodyweight_templates.py` tests
surface catalogued-untagged vs uncatalogued and exclude weighted/non-rep/excluded. Migration
`d4a1f8c609e2` adds one nullable FLOAT and chains `c7d9e2f14a86` → head (the pre-existing second head
`e2d5c7a1b9f3` untouched). Full suite green but for the `#240` shallow-clone artifact.

**Do not revisit unless.** The additive weighted-bodyweight case (bodyweight + plate) is modelled —
that is the remaining Q121 item and needs the e1RM fit to read the same coalesced load (a
`formula_version` consideration), not a second column. Never let `bw_fraction` scale a logged
`weight_kg > 0` — that is exactly the "never scales a real load" invariant the mutation-proof test
guards.

---

### 246. `load_events.window` renamed to `load_window` — `window` is a Postgres reserved word

**Decision.** Rename the `load_events` window column from `window` to `load_window` (migration
`1341a2cf6938`, chained on the single head `d4a1f8c609e2`), keeping the D-A "window" vocabulary.
Column-rename only; no data change — a rename preserves every row and the natural key.

**Rationale.** `window` is a Postgres reserved word: every hand query against the store already had to
quote `"window"` (recorded in the `#243` closing-figures append and the CLAUDE.md prod-tooling block), and
gate 3's `load_metrics` rollup was about to inherit that quoting into every EWMA query. Renaming now —
while `load_events` is the sole 108-row table carrying the name and the rename is trivially reversible —
costs one `ALTER TABLE ... RENAME COLUMN`; renaming after gate 3 is two tables plus every rollup query.
This resolves the `#243` open item, adjudicated by the operator 2026-08-27 (rename, not live-with-quoting).

**Scope kept minimal.** The unique constraint `uq_load_event_session_window_version` and the index
`ix_load_events_user_window` keep their names — Postgres `RENAME COLUMN` rewrites their *definitions* to
reference `load_window` automatically, and the names never appear in a query, so renaming them would add
drop/recreate risk on a constraint over live data for zero query-surface benefit.

**Status.** LANDED + live-verified. Held for the `#238` schema-migration gate, then released by explicit
operator instruction (2026-08-27) and landed end-to-end per `#242`'s standing correction: merged via PR
#116 (merge commit `7bed138`, `--merge`, branch deleted), `#246` re-read against master max `#245` at the
merge instant (no advance). Backend deploy `7fa6a32e` reached **SUCCESS** and the boot log carries
`INFO [alembic.runtime.migration] Running upgrade d4a1f8c609e2 -> 1341a2cf6938, rename
load_events.window to load_window` followed by `Application startup complete` — the migration applied on a
single head (no `Multiple head revisions`). No recompute run (structural rename, not a `formula_version`
change — rows and natural key untouched); the full pytest suite was not run in the authoring sandbox
(sqlalchemy absent) and was owed on the next local/CI pass. **Suite discharged (operator, 2026-08-28, on
`8c6b04e`): `test_load_events.py` 43 passed; full backend suite 1216 passed, 0 failed** — the rename is
green, owed line closed.

**How you know.** After the rename a tree-wide grep for a `LoadEvent` `window` attribute
(`backend`/`frontend`) returns zero — the model attribute, the `load_events.py` insert kwarg, all six
`test_load_events.py` sites, and the SCHEMA.md DDL read `load_window`; the migration is a pure
`op.alter_column(new_column_name=…)` with a symmetric downgrade. Tests build the schema from the model via
`Base.metadata.create_all` (`conftest.py`), so the model rename is what the suite exercises (the suite was
not run in the authoring sandbox — sqlalchemy absent — so it is validated statically here and by the
operator on land). The single migration head is `d4a1f8c609e2` (the `#242`-era parked second head
`e2d5c7a1b9f3` has since been linearized into the main chain), so this migration adds no new head.

**Do not revisit unless.** Another load column later collides with a reserved word (same fix, its own
migration). Reintroducing a bare `window` identifier on any load table is exactly this defect.

---

### 247. Correction to `#243`'s closing figures — `bw_fraction` was live at the 27 Aug recompute, so `#245` is NOT zero

**Decision.** Supersede the claim in `#243`'s closing-figures block that "`#245` contributes exactly 0
(all `bw_fraction` NULL at recompute time)". It is **wrong**. The 17-template `bw_fraction` tagging pass was
already live at the 27 Aug recompute (`audit_bodyweight_templates.py --strict` exit 0 — 0 templates need a
tag), so **both closing figures — Mechanical 924,082.5234 `kg_reps` and Neuromuscular 522.480 `nm_au` —
reflect `#243`+`#244`+`#245`**, not `#243`+`#244` with `#245`=0. Per the DECISIONS supersede-not-amend rule
this appends; `#243`'s block is left as-landed and corrected here. The two figures themselves are unchanged —
only their attribution is.

**What changes.**
- **Mechanical** is `#243` (cardio exclusion) + `#244` (floor band at RPE 8.5/6.5) + **`#245`**
  (bodyweight-class scaling) — not "`#243` alone" and not "`#243`+`#244`". `#245`'s Mechanical effect is
  measured, not argued: nulling Push Up (`392887AA`) and recomputing **raised** Mechanical
  924,082.5234 → 924,903.6234 (**+821.1**); restoring the tag returned it exactly — a reversible prod
  experiment (operator, 2026-08-28).
- **Neuromuscular** attribution to `#244` **stands directionally** (the floor is still the only NM-*raising*
  change in the `c36825d..ec02436` window), but its **magnitude is net of `#245`'s effect through
  `I = eff_w/e1RM`** on mixed-logging templates: a `bw_fraction < 1` lowers `eff_w`, hence `I`, hence
  `h(I)`, hence NM — but only where a bodyweight set consumes a fitted e1RM from the same template's
  weighted sets; a pure-bodyweight template hits the `h=0.5` fallback and is unaffected. `#245`'s NM
  contribution is therefore ≤ 0, so record the movement as **"≥ +41.66 `nm_au` from `#244`"**, not
  "exactly +41.66" — `#244`'s gross contribution is at least the observed net.

**Rationale (the process failure).** The "all `bw_fraction` NULL" claim was **inferred from `#245`'s
closeout** ("tagging pass not yet done") **without a prod read** — an adjacent attestation stood in for a
measurement. This is exactly `FEEDBACK` **§18** (*state inferred from an adjacent attestation is not
measured state*): the adjacent fact was genuinely written, which is what made the inference feel safe, but
only a prod read (`audit --strict`, or the Push Up experiment) could measure it — and it said the opposite.
The tagging pass had gone live between `#245`'s closeout and the 27 Aug recompute; the closeout was true
when written and stale by the time it was cited.

**Status.** Locked. Corrects `#243`'s closing-figures block (its Mechanical bullet, the (b) NM bullet, and
the how-you-know's "`#245`'s NM delta was exactly 0" line) and the CLAUDE.md Recent-landings pointer
(updated to reference this entry). The `#243`/`#242` figures (924,082.5234 / 522.480) are unchanged.

**How you know.** Operator's reversible prod experiment (2026-08-28): `bw_fraction` set NULL on Push Up
(`392887AA`) → recompute → Mechanical 924,082.5234 → 924,903.6234 (+821.1); restore → exact return.
`audit_bodyweight_templates.py --strict` exit 0 (0 templates need a tag) confirms the 17-template pass was
live at the 27 Aug recompute. `#245`'s NM direction (≤ 0) follows from `_effective_weight`'s
`bw_fraction ≤ 1.0` lowering `I` into the monotone `h(I)`.

**Do not revisit unless.** A `formula_version` bump re-derives the figures (then supersede with the new
recompute). The general rule this instance is filed under — never attest a prod figure or state from a
closeout or adjacent doc; measure it (a prod read) — is `FEEDBACK` §18.

---

### 248. Gate 3 — load_metrics daily rollup: per-window Banister Fitness/Fatigue/Form

**Decision:** Gate 3 materialises `load_metrics`, a per-(user, day, load_window, formula_version,
metrics_version) daily rollup of `load_events`. `daily_load` is the sum of that window's events on
that day; `fitness` (τ=42d, all windows) and `fatigue` (τ per #32: mechanical 10, neuromuscular 6,
metabolic 4) are discrete EWMAs over a continuous daily series (rest days decay, seed 0) to `as_of`
(default today; tail rows past the last session are pure decay); `form = fitness − k·fatigue`, k=1,
applied at write and re-derivable from the stored stocks alone — a k change is a form-column refresh,
never a stock recompute or a metrics_version bump. Windows are computed only where load_events supply
rows (today: mechanical, neuromuscular); the machinery is window-generic, so Metabolic/Psychological
light up when fed, no re-architecting. Units are window-native (kg_reps, nm_au) and never crossed.

Day grain buckets by user-local Australia/Brisbane (UTC+10, no DST) date from occurred_at. The concrete
conversion is `_local_day = astimezone(Australia/Brisbane).date()` (mirroring `health_connect._wake_date`,
which treats an ingested health timestamp as UTC and converts). **S1 CONFIRMED (operator, 2026-08-28):**
raw `start_time` carries an explicit `+00:00` offset with plausible AEST session times (12:40 / 18:17 /
17:38); a naive-local reading would put one session at 02:40, ruled out against the 5:45 am wake anchor —
so Hevy emits true UTC instants and `_local_day = astimezone` is correct as built (no flip, oracle
unchanged). UTC-date bucketing was rejected either way — it misplaces early-morning AEST sessions onto the
prior training day.

Maturity flag per row (annotate-never-suppress, #10/#28): 'low' until ≥42d continuous history for the
window, else 'ok'. Undated load_events (occurred_at NULL) are excluded from the curve, mirroring the
e1RM undated-skip. Extends D-B (recompute, never migrate) with a second axis, metrics_version, pinning
the τ-set that governs the stored stocks: a τ tune is a metrics_version bump + delete-and-reinsert per
(user, formula_version, metrics_version), not an edit. Implements #28/#32 gate 3.

**Status.** RELEASED by the operator (2026-08-28) after S1 confirmed; landed via PR #121, migration
`334526269006` (`load_metrics`) chained on the single head `1341a2cf6938`. Gates discharged with real
execution (deps installed in a venv): full backend suite **1225 passed / 1 skipped** (the sole failure is
the pre-existing `3360ed5` shallow-clone artifact, unrelated); the `load_metrics` tests incl. the
reconciliation oracle **54 passed**; the alembic scratch **upgrade `1341a2cf6938 → 334526269006` +
downgrade** ran clean with `load_window` present and no bare `window` column. **Live-verified:** merged via
PR #121 (merge commit `e289c12`); backend deploy `bfc1a5e2` reached SUCCESS and the boot log carries
`INFO [alembic.runtime.migration] Running upgrade 1341a2cf6938 -> 334526269006, add_load_metrics` then
`Application startup complete` — single head applied, clean boot. The `load_metrics` **rollup** itself
(populating rows) is operator-run post-deploy in-container (`railway ssh --service health-app-backend` →
`cd /app` → `/opt/venv/bin/python load_metrics.py`), then face-validity the curves. Standing operator
sequence after any `bw_fraction` or template change: BOTH recomputes in order — `load_events` first, then
`load_metrics` — because the rollup reads a derived store, not raw.

**How you know.** `backend/load_metrics.py` reads `models.LoadEvent` only (no `hevy_workouts.raw` access
— grep-clean); `test_load_metrics_reconciliation.py` asserts fitness/fatigue/form and the ΔLoad ratio to
the cent on named days over a dated series with a rest gap and a near-midnight boundary session;
`test_load_metrics.py` pins fail-closed psychological (no metric row), metabolic-provisioned, the undated
skip, idempotent recompute, the AEST boundary, unit isolation, and formula_version scope.

**Do not revisit unless.** A τ tune (metrics_version bump + recompute). The S1 day-rule is settled
(true UTC → astimezone); revisit only if Hevy's timestamp contract changes. A k change is a form-column
refresh, not this.

---

### 249. ΔLoad instantiated (#33) — per-window acute:chronic over daily_load

**Decision:** #33's ΔLoad primitive is instantiated on the load_metrics daily row as a per-window
acute:chronic ratio over daily_load — acute = trailing-7d mean, chronic = trailing-28d mean (rest days
count as 0), load_ratio = acute/chronic — carried as acute_load/chronic_load/load_ratio columns. It is
distinct from Form (#33: Form is readiness, ΔLoad is spike/injury-risk; they do not collapse). The 7:28
shape mirrors the ACWR it succeeds; EWMA-ACWR weighting is a Tier-3 refinement.

This does NOT retire ACWR (#8/#28): ACWR is aerobic-only and this ΔLoad covers only strength windows
(mechanical, neuromuscular). ACWR stays live until a Metabolic→load_events transform feeds the metabolic
window, or aerobic acute-spike detection is lost. Retirement is downstream of that transform, not gate 3.

**Status.** RELEASED + landed with the gate-3 rollup (`#248`, same PR #121). `load_ratio` is NULL while
chronic is 0 (mutation-proof in the reconciliation oracle: divergent ratios 0.761905 and 1.210084 on
named days, both asserted green in the executed suite).

**How you know.** The reconciliation oracle asserts acute/chronic/ratio to the cent; `load_ratio` NULL
on a zero-chronic day is asserted by construction (the ratio column is nullable and set only when
chronic > 0).

**Do not revisit unless.** A Metabolic→load_events transform lands (then reassess ACWR retirement) or the
7:28 shape moves to EWMA-ACWR (Tier 3).

---

### 250. SessionStart tooling install — grep→manifest, fail-loud, on-demand full stack via venv

**Decision.** Three concern-adjacent hardenings to `.claude/hooks/session-start.sh`, the web-session
SessionStart hook that installs the DB tooling into the ephemeral container (established #122). (a) **grep→manifest
(C):** the hook no longer greps the five tooling pins out of `backend/requirements.txt` at run time; it installs
`-r .claude/requirements-tooling.txt`, a committed, reviewable manifest (`sqlalchemy`, `alembic`, `psycopg2-binary`,
`python-dotenv`, `pytest`). `scripts/check_tooling_pins.py` keeps the manifest in lockstep with
`backend/requirements.txt` — the *source of truth for pin values* — closing BOTH drift modes: **version** (a pin bumped
on one side only) and **membership** (a canonical tooling package dropped from, or a non-tooling package added to, the
manifest). The canonical tooling name-set is named in the check (it was the hook's old grep alternation), so a dropped
package fails the check rather than resurfacing as a mid-session `ModuleNotFoundError`. Without this check C only swaps
grep-fragility for silent drift, so the check is part of the change, not polish. (b) **fail-loud (D):** `set -euo
pipefail` retained, and the silent-skip escape hatches removed — a missing manifest now `exit 1` (was `exit 0` on a
missing `requirements.txt`), and the empty-grep / `grep || true` skips are gone; a failed `pip` line propagates
non-zero under `set -e`. A half-install aborts session start visibly instead of surfacing later as a mid-task
`ModuleNotFoundError`. The `CLAUDE_CODE_REMOTE` guard and its no-op-when-unset behaviour are unchanged. (c) **on-demand
full stack (B):** `.claude/scripts/install-full-stack.sh` builds a throwaway venv (`.venv`, gitignored) and installs
the full `backend/requirements.txt` into it. A fresh venv is isolated from the distro site-packages, so the
python-jose→PyJWT conflict that blocked a full *system* install in #122 does not arise. Design call: tooling
fast-and-always in system Python; full stack **on request**, isolated — NOT wired into SessionStart, so it never taxes
cold start.

**Status.** LANDED. Feature via **PR #125** (merge commit `7dadb2e`; `--merge`, branch deleted). Governance (this entry
+ BRANCHES rows + closeout + Recent-landings) rides `gov/250-hook-install-hardening` per #176(b). `.claude/`-only plus
the manifest/check under `scripts/`; no backend, migration, or app code; `settings.json permissions.deny`
byte-identical.

**How you know.** Gates run for real in a web container (`CLAUDE_CODE_REMOTE=true`): remote mode installs the five
pins clean; `CLAUDE_CODE_REMOTE` unset → clean no-op (exit 0, no output). Fail-loud both paths: missing manifest →
exit 1; an injected bogus pin → pip errors, hook exits non-zero. Consistency check passes on the tree; a hand-desynced
`sqlalchemy` pin (2.0.50→2.0.49) makes it fail with a named message, restore → passes; `scripts/tests/test_tooling_pins.py`
6/6 (live lockstep + injected version/membership drift both bite). `install-full-stack.sh` runs clean (~22s); afterward
`jose` (python-jose) and `jwt` (PyJWT) coexist and the previously-#122-blocked pytz/app-stack tests collect and run —
`test_canonical_title_render.py` 9 passed, the sole failure across the broader run being the known `3360ed5`
shallow-clone git artifact (unrelated to packaging). `alembic heads` resolves a single head (`334526269006`).

**Do not revisit unless.** The tooling set changes (add the package to BOTH `CANONICAL_TOOLING` in
`scripts/check_tooling_pins.py` and the manifest, in one change — the check enforces this). If a future session wants
the full stack at session start, weigh the cold-start tax the #122/#250 split deliberately avoided; the venv path exists
precisely so it need not be.

---

### 251. Metabolic window derivation — Edwards zone-weighted TRIMP (`metab-v1`, `trimp_edw_au`)

**Decision:** The Metabolic window of the four-window `load_events` store is derived from
`aerobic_sessions` by a NEW sibling transform (`backend/load_events_metabolic.py`), one Metabolic
row per qualifying session, in Edwards (1993) zone-weighted TRIMP:
`trimp = Σ_z (zone_z_seconds / 60) × weight_z`, weights `{z1:1, z2:2, z3:3, z4:4, z5:5}` — a reasoned
prior (#32), literature-standard, needing no individual physiological constant. `formula_version =
"metab-v1"`, `unit = "trimp_edw_au"`, `load_window = "metabolic"` (lowercase — the `load_metrics`
fatigue-τ allowlist already provisions `metabolic` τ=4, so the daily rollup lights up unchanged).
Source linkage is source-neutral: `source = "aerobic_sessions"`, `source_ref = str(id)` (the stable
internal id — `source_session_id` is nullable and untrustworthy as a key). `occurred_at` prefers
`start_time`, else UTC-midnight of the always-present `session_date` (the rollup drops NULL-`occurred_at`
rows). Recompute is delete-and-reinsert scoped to `(user, "metab-v1")` ONLY — the strength transform's
`tier0-v1` rows are never touched — and idempotent on the natural key.

Three sub-rulings: **(a) fail-closed coverage (INV-7).** A session with no usable zone data — every
`z*_seconds` NULL, or a zero zone-sum — emits NO row and is counted in `sessions_skipped_no_zones`; no
imputation. **(b) no fallback formula (INV-2 unit-lock).** There is NO Banister-TRIMP (HR-based) fallback
in v1 — mixing formulas inside one window's series would break within-window comparability. Zone-less
sessions wait for a v2 ruling (Q123), they are not silently HR-mapped. **(c) `cardio_load` excluded as a
load input.** Polar's proprietary `cardio_load` is device-locked and non-recomputable (violates #32
provenance discipline); it appears only as a convergent-sanity TRIMP-vs-`cardio_load` correlation in the
transform summary, never as magnitude. Windows are orthogonal: a session captured by both Hevy
(→ Mechanical / Neuromuscular) and Polar (→ Metabolic) deposits into DIFFERENT windows by design — not
double-counting.

**Rationale.** Closes the §3.1 ledger gap: the Governor (S2) was blind to the dominant in-season
chronic-tax vector because the Metabolic window was schema-present but compute-absent. This transform is
the trigger #249 named for reassessing the legacy aerobic acute-spike ratio's retirement (#8/#28) — that
reassessment is downstream governance, NOT part of this change.

**Status.** BUILT + test-proven; PR open, held for human review (code change — CLAUDE.md merge
disposition: code changes always take full human review; not self-merged). No schema migration — the
`load_window`/`unit`/`formula_version` columns already accept these string values, so SCHEMA.md does not
move.

**How you know.** `backend/tests/test_load_events_metabolic.py` runs green (19 tests): G1 exact Edwards
sum, mutation-proofed against a flat unweighted sum (600s z1 + 300s z2 + 120s z5 → 10+10+10 = 30, not
17); G2 fail-closed (all-NULL and all-zero → zero rows, skip counted); G3 idempotency (double-run →
identical row set); G4 isolation (a landed `tier0-v1` row survives byte-identical). Full `test_load_events.py`
strength suite stays green (62 passed together). No `metabolic` load-event writer existed before this
(grep-confirmed — the token appeared only as rollup provisioning and docstrings).

**Do not revisit unless.** Zone-less aerobic sessions must be scored rather than skipped (Q123 — a
`formula_version` bump to a calibrated HR-based v2), a non-Polar zone source with a different zone model
is ingested into `aerobic_sessions` (Q124), or the Edwards weights are recalibrated (a `metab-v1`→`v2`
recompute, never an edit of landed rows).

---

### 252. Aerobic ingest is recompute-triggering — Flow-export upload endpoint + one per-user metabolic cascade + zone-coverage flag (Polar Ingest Automation, Phase 1)

**Decision:** Every Polar aerobic ingest cascades the per-user metabolic recompute AUTOMATICALLY — recompute-on-ingest, not a button. **(a) One named cascade callable.** `run_metabolic_cascade(db, user_id)` (`backend/metabolic_cascade.py`) runs the metabolic transform (`metab-v1`, `compute_metabolic_load_events`) then the `load_metrics` rollup for `metab-v1` (`compute_load_metrics(..., formula_version="metab-v1")`) — both per-user, both idempotent delete-and-reinsert scoped to their own `(user, formula_version)`, so the strength `tier0-v1` series is never touched. It is invoked by BOTH aerobic routes — the new upload endpoint and the existing `POST /integrations/polar/sync` — with no route-inline duplication, because the Phase-3 webhook handler is anticipated as its third caller. Synchronous in-request (delete-and-reinsert per user is cheap at current scale); a framework background task is deferred until a measured response-time concern appears. **(b) Flow-export upload moves in-app.** `POST /integrations/polar/import-export` (authenticated user, never an email parameter; multipart ZIP) replaces the operator's local `import_polar.py` runbook for routine refreshes. The script's parsing/sport-map/dedup core is extracted to a shared `import_flow_export(db, user_id, zip_source, *, dry_run)`; `_parse_session` is used verbatim (byte-identical parse). The CLI is retained as an ops/backfill wrapper — `--email` resolution stays CLI-only. Input hygiene is fail-closed: a non-ZIP is rejected 400 (on the archive magic, not content-type), only `training-session_*.json` members are parsed, and member-count / per-member-size / total-size caps (10 000 / 5 000 / 10 MiB / 200 MiB) reject an oversized archive 400 before any decompression. **(c) Zone-coverage flag.** `zone_coverage(user_id, db)` / `coverage_notice(coverage)` (`backend/reads/aerobic_reads.py`) count zone-carrying vs zoneless sessions (by source), using the SAME qualifying predicate as the transform's INV-7 fail-closed rule, and derive `stale_zoneless` = zoneless `polar_v4` sessions older than `ZONELESS_STALE_DAYS = 7` (a reasoned prior, tunable). Both ingest responses surface the coverage plus a `"N sessions awaiting zone data — refresh export"` notice when `stale_zoneless > 0`. No schema migration — existing tables/columns only, so SCHEMA.md does not move.

**Rationale.** Collapses the operator's seven-step Polar refresh ritual into one in-app action and makes the metabolic recompute automatic on every ingest, so a fresh export can never again land without its `load_events`/`load_metrics` following. The coverage flag makes transport-starved sessions visible instead of silent — the failure mode that hid 17 zoneless `polar_v4` sessions for two months. The cascade is a single callable (not route-inlined) so the Phase-3 webhook becomes a third caller, nothing more. The cascade on a v4 sync is harmless today — v4 list rows carry no HR-zone split, so they fail-closed skip the transform (INV-7) and contribute nothing — and becomes correct unchanged after Phase 2 enriches v4 sessions with per-exercise zones. Phase 2 (v4 zone-enrichment) is out of scope, gated by **Q123** (zone-less session handling); the retirement brief's arbitration OQ is not yet in master, so there is no such number to reference or renumber here.

**Status.** BUILT + test-proven; PR open. The web-task harness's draft / no-self-merge constraint (the Q125 lane) governs the merge in this environment — the operator merges; this session does not self-merge. No migration.

**How you know.** `backend/tests/test_polar_import_export.py` runs green (11 tests): endpoint happy-path (`found=3/inserted=3`, rows scoped to the user, cascade + coverage in the response) and dedup (second upload inserts 0); non-ZIP rejected 400; member-count and total-size cap breaches rejected 400; **G3 full path** — upload → `aerobic_sessions` rows → two `metab-v1` `load_events` (`metabolic` window) → `metabolic` `load_metrics` rows, all scoped to the uploading user while a second user's prior cascade output stays byte-identical; the `/sync` route fires the cascade (zoneless v4 rows fail-closed skip → 0 events) and surfaces the stale notice; coverage counts + `stale_zoneless` + `by_source`; **G2 CLI-equivalence** — `import_flow_export` dry-run and write produce identical substance and dry-run writes nothing, with `_parse_session` byte-identical in the diff. Full backend suite **1255 passed** (1244 baseline + 11), one pre-existing environment-only failure (`test_current_state` `git show 3360ed5:` shallow-clone artifact, unrelated). No `mcp_server.py` diff (grep-clean — the retirement PR owns that file). `placeholder guard (POSIX)` exit 0.

**Do not revisit unless.** A measured response-time concern forces the cascade to a framework background task (default is synchronous in-request); Phase 2 lands zone-enrichment of v4 sessions (the sync cascade is harmless-today / correct-after by design, gated by Q123); or the Phase-3 Polar webhook wires `run_metabolic_cascade` as its third caller. `ZONELESS_STALE_DAYS` and the upload caps are tunable constants, not re-decisions.

---

### 253. Alcohol reclassed DISQUALIFYING → EXCUSABLE in `classify_night` — an excused night stays in the basis, capped one per cycle with a widened action margin

**Decision.** In `backend/cbti/engine.py:classify_night`, a RECORDED non-zero alcohol night (`alcohol_units is not None and > 0`, engine.py:279-280) reclasses from DISQUALIFYING (`NightVerdict(night, False, "alcohol")`, dropped from the basis) to EXCUSABLE: the night stays VALID and counts toward the basis, tagged as excused — a flag on `NightVerdict` alongside the existing `alcohol_unknown`, NOT a re-use of the exclusion `reason` string. This ratifies the PENDING POLICY the code itself marked at engine.py:275-278 (*"a policy revision would reclass this exclusion as EXCUSABLE rather than DISQUALIFYING… the revision is not ratified, so this stays a plain exclusion"*) — those classes may now exist in code. Two guards are PART of the decision, not options: **(a) cap excused nights at one per cycle** — a second recorded-alcohol night in the same `CYCLE_NIGHTS` window stays a plain exclusion, so a cycle can never be built predominantly on compromised nights; **(b) widen the action margin when the basis contains an excused night** — a single excused night may not by itself drive a window change (extend/compress). The exact form is the implementation's to specify and test (e.g. the decision must also hold on the clean-only subset, or a larger delta is required to act), but the guard is not optional. Scope is `classify_night` and the GATE-1 sufficiency count ONLY: it does not touch the naps / travel_or_match / training_constrained / incomplete exclusions, and it does not change `MIN_VALID_NIGHTS` (3) or `CYCLE_NIGHTS` (4).

**Rationale.** The titration keys on sleep efficiency (SE). Low-dose alcohol that clears well before lights-out moves SE very little — it shifts REM proportion and second-half WASO, neither of which GATE 1 nor the window logic reads. Against that small, mostly-unmeasured distortion sits the cost the exclusion actually imposes: with `MIN_VALID_NIGHTS` 3 against a `CYCLE_NIGHTS` 4 window the margin is a single night (engine.py:86-87, :98, :144), so one recorded-alcohol night drops `len(valid)` to 3 and a second trips GATE 1 to a `sufficient=False` HOLD — no decision at all. The observed case: 2026-08-22, 2 units at 19:30 against lights-out 22:15 — a >2.5 h clearance, excluded outright. The rule as written trades a barely-measurable bias for a dead cycle, repeatedly, and that starves the basis calibration cannot proceed without. Excusing-not-excluding keeps the cycle evaluable; the two guards stop the reclass from becoming a free pass — a compromised night can be admitted, but not stacked, and not left to move the window on its own.

**Status.** RATIFIED (policy); implementation OWED, not built. This entry exists so the engine change is built against a ratified spec rather than the unratified one engine.py:275-278 correctly refused. The build — the `NightVerdict` excused flag, the per-cycle cap, the widened action margin, the render split, and their tests — lands under the re-anchored Brief B against `health-app` (`engine.py` + `routers/checkin_v2.py` persistence + the React `frontend/`). It is schema-touching: `excluded_nights` is a persisted JSON column (`migration e5f2a9c7b104`), and an excused night moves out of that map into the basis while still needing its excused state carried — so the implementation PR **HOLDS for explicit operator instruction** under the schema-migration rule. No code or schema moves in this commit.

**How you know.** The exclusion and its pending-policy marker are read directly at `backend/cbti/engine.py:279-280` and `:275-278`; the one-night margin at `:86-87`, `:98`, `:144`; the `sufficient=False` single-path HOLD at `:453-465` (the same collapse Brief B step 5 names — `decision="hold"` carries both a merits HOLD and this no-decision). The failure case (2u @ 19:30, 2026-08-22) is the operator's own recorded night. The SE-blindness mechanism (alcohol moves REM/WASO, not the SE the gate reads) is the physiological ground the operator ruled on; this entry records that ruling and adds no empirical claim beyond it. No test is asserted green because no code changed — the How-you-know for the behaviour lands with the implementation.

**Do not revisit unless.** The titration's control quantity changes from SE to a recall/architecture measure that DOES read alcohol's REM/WASO shift (the pending SE-retirement noted at engine.py:256-260) — then alcohol may re-qualify as disqualifying on the new gate; or the one-per-cycle cap or the widened-margin guard is shown in replay to admit a window change a clean-only basis would not have made (tighten the guard, never drop it); or `MIN_VALID_NIGHTS` / `CYCLE_NIGHTS` change such that the one-night margin this reclass exists to protect no longer binds.

---

### 254. Sleep day-aggregation re-spec'd: UNION of asleep stage-intervals, not longest session (supersedes #35's F3a)

**Decision.** `_aggregate_day`'s sleep block (`backend/routers/health_connect.py`) now computes `sleep_duration_minutes` as the **union of asleep (LIGHT/DEEP/REM) stage-intervals** over the wake-date's session set, replacing the longest-single-session selector. This **supersedes the original F3a spec in #35** ("sum duration + stage-minutes over the night session set") — a plain sum double-counts overlapping sessions; the union collapses overlaps to true total sleep time (TST). Mechanics: flatten every wake-dated session to stage segments (a stageless session → its whole span as one best-effort LIGHT segment); cluster segments into periods by coverage continuity (a gap > `SLEEP_PERIOD_GAP_MINUTES = 120` opens a new period, so a same-wake-date daytime nap stays its own period and never merges into the night — the one thing longest-session got right, preserved); main period = the one with the largest asleep-union; TST = its asleep union; deep/rem/light = per-stage unions. TST is computed from **stage segments, never `session.duration()`** (self-reported and overlapping on a fragmented night). AWAKE is excluded from every asleep total — TST is now true sleep time, not time-in-bed. Wake-date-only grouping is unchanged (Q4); `_sleep_score` and the CBT-I engine are untouched (diary-sourced, insulated).

**Two operator rulings (Luke), recorded as part of the decision.** **(1) Multi-source main period → dominant-source breakdown + flag [option (a)].** The union TST is safe across sources (overlaps collapse), so the total spans all sources; the deep/rem/light breakdown ships from the single source with the most asleep-minutes in the main period, flagged via an INFO log (`HC sleep F3a multi-source night …`) — **no schema column, no persisted marker**. Full cross-source stage resolution defers to F1. Single-source total **and** breakdown ship now, ahead of F1. **(2) Series discontinuity accepted with a documented cutover date; no marker column.** Pre-fix rows are longest-session, post-fix are union-TST; raw sessions are discarded so no clean historical backfill exists. P1 (below) means the discontinuity is a ~7-day seam, not a wall: the companion re-sends a rolling 7-day window every sync and the backend upserts, so the recent tail re-aggregates under union on its own within ~a day of deploy; only rows older than ~7 days before cutover stay on the old (already-under-counting) method. A `sleep_agg_method` marker column would cost a migration and forfeit the migration-free self-merge property for no reader benefit. **Cutover date = the deploy date, captured at close-out from the actual event** (not picked here). Optional operator step: open the companion and sync once post-deploy to heal the last 7 days immediately.

**P1 (HARD GATE) cleared.** The union runs at ingestion on `payload.sleep`; raw sessions are not persisted, so it is only correct if the companion sends the **full night per sync, not deltas**. Verified in `Easty11/health-connect-app@12844925` (`src/healthConnect.js`): `fetchAllData(days = 7)` reads `SleepSession` with a `between` `timeRangeFilter` from `daysAgo(7)` to now — a rolling 7-day window re-sent in full each sync. No `changesToken` / `getChanges` / cursor / delta anywhere in `src/`. Gate satisfied → build proceeded.

**Rationale.** Verified failing night, wake-date 2026-08-30, single-source Samsung, 4 overlapping sessions: the longest-session selector stored `sleep_duration_minutes = 305` (one fragment's self-reported duration), while the union of the night's asleep intervals is ~402 — a ~97-min under-count on a fragmented night. `session.duration()` is untrustworthy here: the stored 305 exceeds the largest inter-start gap (221 min), so the retained record overlaps its neighbours. Computing from stage segments and unioning fixes both faults (fragment loss and self-report/overlap) at once. The stage enum mapping (LIGHT=4/DEEP=5/REM=6/AWAKE=1) was **confirmed correct** — the disrupted-night `rem=151` is Samsung's staging, not a code bug, and was not "fixed."

**Status.** BUILT + test-proven; PR open **draft** — this is a harness-originated feature PR, so it merges under the **Q125 lane** (draft, operator-merged; this session does not self-merge). **No schema migration** (value-fix only) → not schema-held; the migration-free property is deliberate (ruling 2). Downstream readers audited (see How-you-know): all four just display the number, none breaks. The MCP field `actual_sleep_time_minutes` becomes accurate for the first time — no rename.

**How you know.** New `backend/tests/test_health_connect_sleep_union.py` (5 tests, green): the pinned failing-night fixture asserts `sleep_duration_minutes == 402` and explicitly `!= 305`; overlapping same-source sessions union (180) not sum (240); a same-wake-date afternoon nap (gap > 120) stays a separate period and is excluded (night 480 only); single-source per-stage breakdown excludes a mid-night AWAKE (deep 60 / rem 90 / light 315 / TST 465, score 9); multi-source total is the full-source union (420) while the breakdown is the dominant source only (light 240, not the 330 an all-source union would give) and the flag is logged. The canonical-fixture contract assertion (`test_hc_sync_contract.py`) moves `495 → 480`: the old longest-session span counted a 15-min mid-night AWAKE (05:10–05:25) the union correctly excludes; deep 95 / rem 75 / score 10 unchanged, light now 310. Reader audit (grep, non-test): `mcp_server.py`, `routers/recovery.py`, `routers/checkin_v2.py`, `context_builder.py` each only display/format `sleep_duration_minutes` (and deep/rem/light); the CBT-I engine does not read it. Full backend suite green (`test_health_connect_sleep*`, `test_hc_sync_*`, `test_readiness_sleep_stages` = 38 passed together; whole suite 1273 passed, 1 skipped), one pre-existing environment-only failure (`test_current_state` `git show 3360ed5:` shallow-clone artifact, unrelated — fails identically on master). `placeholder guard (POSIX)` clean.

**Do not revisit unless.** F1 (cross-source stage resolution) lands — then the multi-source breakdown moves from dominant-source-derived to a real cross-source resolution and the INFO flag can retire; or a tiny-night-plus-long-nap case is shown in practice to invert main-period selection often enough to matter (the diary is authoritative today, so it is noted not guarded); or a total-sleep-adequacy / awakening term is added to `_sleep_score` (Q126), which reads the same TST this entry made accurate. `SLEEP_PERIOD_GAP_MINUTES` (120) is a tunable constant, not a re-decision. The stageless-session → LIGHT fallback is best-effort; a real stage-source for such sessions would supersede it.

**Close-out (2026-08-31).** Landed on master at merge `99440b8` (PR #133; feature `9bf5ad2`, governance `de64156`), operator-authorised merge under the Q125 draft/operator-merged lane. **Series-discontinuity cutover date = 2026-08-31**, confirmed (not assumed): the merge-triggered Railway deploy of `health-app-backend` — deployment `c152b31a`, commit `99440b8` — reached `SUCCESS` (02:18→02:19 UTC) and the prior image (`d67f8f7`/#132) is `REMOVED`, so the union-method code is the live serving instance (#116 identity check; backend-only change, so no frontend probe needed per #121). Deploy went live 02:19 UTC = 12:19 AEST, same calendar date as the merge, so cutover = deploy date = merge date here. **Recent-tail heal: left to organic rolling-window re-aggregation** — no manual heal was performed, because the heal requires a device-side companion sync (HCA POSTs to the backend; there is no server-side re-pull), which this session cannot trigger. Consequence: for rows in the ~7-day window before the first post-deploy sync, a longest-session value may persist until an organic sync re-aggregates it under union; the operator can force this to immediate by opening the companion and syncing once. The seam is therefore method-artifact, not a data gap, and self-closes on the rolling window.

---

### 255. Legacy aerobic acute:chronic ratio (ACWR) retired — `get_training_load` serves the metabolic Banister lane

**Decision.** The legacy aerobic ACWR readout (#8's interim "Hevy ACWR"; #28's named tech-debt "the ACWR compute path is now tech-debt — retire when Banister Tier 0 lands") is retired per **#249's own trigger** — its stated precondition, a Metabolic→`load_events` transform, has landed and validated (#251, `metab-v1`, Edwards zone-weighted TRIMP; operator-reported r=0.974 vs Polar `cardio_load`, n=46; rollup live). `get_training_load` (MCP Tool 6, `backend/mcp_server.py`) no longer computes acute:chronic from `aerobic_sessions` via the `duration_min × avg_hr` TRIMP proxy, nor emits the 0.8/1.3/1.5 sweet-spot banding and injury-risk verdicts. It now reads the metabolic lane of `load_metrics` (`formula_version='metab-v1'`, `metrics_version='banister-v1'`, `load_window='metabolic'`) and serves the Banister fitness/fatigue/form curves plus the acute/chronic **trace values** in window-native Edwards TRIMP — **no ratio, no band verdict**. **This closes the #18 readout≠dosing boundary at the readout:** dosing never used ACWR (INV-6; `engine/selection.py:440/455`, `engine/__init__.py:22`), and the readout no longer does — the boundary closes with the readout gone, not with a "readout ≠ dosing" caption (the `load-governor-trajectory-design.md` §11 candidate "or retiring the readout" is the branch taken). **Scope guard.** Only the aerobic ACWR readout. #249's own strength-window ΔLoad (`acute_load`/`chronic_load`/`load_ratio` over `daily_load`, `load_metrics`/`load_events`, #33) is a distinct live primitive — untouched; `injury_probes.py`'s acute-soft-tissue cadence usage is unrelated — untouched.

**Rationale.** #28 named the ACWR compute path tech-debt; #249 parked its retirement specifically behind the Metabolic→`load_events` transform ("ACWR stays live until a Metabolic→load_events transform feeds the metabolic window … retirement is downstream of that transform, not gate 3"). That transform is now landed and validated, so the readout's only remaining justification — being the sole aerobic-load surface — is gone. The old proxy also violated the metabolic transform's INV-2 unit-lock: a `duration × avg_HR` number is not commensurable with zone-weighted Edwards TRIMP. Serving the real metabolic lane removes the mixed-unit readout entirely rather than captioning it.

**Q123 closed in the same motion (transport-gap ruling).** The zone-less skips were a **transport gap**, not a scoring gap: the Polar **v4 `/training-sessions/list` endpoint omits `trainingLoadReport`/zones** (verified in code, `backend/connectors/polar.py:196` docstring — `z*_seconds` come back null on live-sync; zones "remain ZIP-only"), so the fail-closed metabolic transform (INV-7) correctly skips those rows. Resolved not by a fallback formula but by the **Flow (ZIP) export refresh, which carries the zone split** (operator-run 2026-08-29; operator-reported `load_events` 30→47 after 18 sessions imported, residual skips = v4 twins of ZIP rows + 2 no-HR one-offs + 1 trivial blip — device-side counts this session cannot verify against Railway, recorded as operator-reported per the unseeable-surface rule). **No fallback formula, permanently:** a `duration × avg_HR` Banister-TRIMP row mixed into one window's series breaks within-window comparability (INV-2 unit-lock). Any future zone-less scoring is a `formula_version` bump (`metab-v1`→`v2`), never an in-place fallback — that fork is what stays open as Q123's data-prerequisite note, now folded into the closure.

**Status.** BUILT + test-proven; PR open **draft** — harness-originated feature PR, so it merges under the **Q125 lane** (draft, operator-merged; this session does not self-merge). **No schema migration** (code + governance only) → not schema-held. Consumers audited: `get_training_load` has **zero internal readers** (no frontend call, no Python caller, no test referencing it by name); the only consumer is the MCP tool surface itself, name unchanged — reshaping the payload breaks nothing.

**How you know.** New `backend/tests/test_mcp_training_load.py` (4 tests, green) over the pure `_format_training_load` formatter: latest-day render shows window-native TRIMP + acute/chronic trace; an executable assertion proves no `acwr`/`sweet spot`/`injury risk`/`ratio:` language survives (G3-as-test); latest-only selection; empty-lane no-data readout. Post-retirement grep of the surface: no ratio computation or band verdict remains in `mcp_server.py` — only docstrings that name the retirement (#113 quote-the-superseded is expected). Full backend suite **1277 passed, 1 skipped** under the isolated `.venv`; the sole failure (`test_current_state` `git show 3360ed5:` ) is the pre-existing shallow-clone artifact — unrelated, touches none of these files, fails identically on master (#254 close-out). `placeholder guard (POSIX)` clean.

**Do not revisit unless.** The ACWR readout is reintroduced (it must not be — acute safety lives in dosing's ramp-rate/monotony guards, the readout serves the Banister metabolic lane); or the metabolic lane's `formula_version`/`metrics_version` identity changes (then the tool's pinned `metab-v1`/`banister-v1` filter follows the bump); or Q123's `v2` zone-less-mapping fork is later adopted (that changes what the lane contains, not that the readout serves it).

---
