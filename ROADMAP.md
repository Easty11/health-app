# ROADMAP

Last updated: June 2026

---

## NOW — active sprint

| Item | Notes |
|------|-------|
| Fix Health Connect permissions | Companion app returning errors for record types 38, 35, 11, 37. Partially resolved via adb pm grant; proper in-app dialog fix still needed. |
| Samsung Health package name correction | Re-run Health Connect diagnostic with `com.sec.android.app.shealth` filter (not `com.samsung.health`). Verify via Railway Postgres query, not on-device UI. |
| Morning check-in screen | Hooper Index pattern (fatigue, sleep quality, stress, soreness). Primary daily touchpoint. Mutable post-submission with audit trail. See Ideas file for DOMS/soreness split design. |
| Persistent conversation history | Currently clears on browser refresh. Needs backend storage + frontend state management. |
| Session cards not clickable | UI bug — session cards in workout view not responding to click |
| Dual-panel scroll layout issue | UI bug — scroll behaviour broken in dual-panel view |
| Run `seed_engine.py` against Railway Postgres | DECISIONS_LOG #42's device/injury migration only ran against local SQLite this session (no Railway credentials in-session). Luke's chat/MCP context is still hardcode-free but reading empty structured entries in production until this runs. Verify via Postgres query, not on-device UI. |
| `mcp_server.get_hevy_workouts` references unimported `Session` type | Pre-existing bug, found (not introduced) during #42's MCP work — `db: Session = SessionLocal()` with no `Session` import; will raise `NameError` at call time. Out of scope for #42 (Hevy endpoints explicitly not touched); needs a one-line import fix. |

---

## NEXT — queued

| Item | Notes |
|------|-------|
| Scraper canary + honest score degradation | Detect null/stale/implausible scraper output. Surface degraded state to user when HRV unavailable — never silently score without it. |
| Basic readiness score | Formally suppressed until HRV data path is confirmed end-to-end with 7+ days of readings (scraper path confirmed; pending 7-day sample). Once confirmed: Banister fitness-fatigue model (Form = Fitness − Fatigue, dual EWMA) integrated with RMSSD baseline deviation, sleep architecture, and RHR trend. ACWR rejected — see Decisions Log. |
| Manual cardio entry | Unconnected sessions (Rogue Echo bike, gym machines) must be loggable to prevent ACWR silently under-reading load. |
| CLAUDE.md files for both repos | Deferred to laptop. Backend repo and health-connect-app repo both need CLAUDE.md. Drafts exist from June 2026 session. |
| Deploy companion app to wife's phone | Garmin → Health Connect path. Verify data flowing before deploy. |
| Lab upload pipeline | PDF/photo → Vision extraction → confirmation screen with outlier flagging → stored. First stage of the medical spine. Consumer hero-feature dependency. |
| Interpretation layer build | Design complete, build pending. Consumes stored labs → evidence-ranked levers. Education pathway (explain mechanisms, list/filter levers), NOT clinical advice — regulatory boundary. |
| Appointment brief | Hero consumer feature — "Never waste a medical appointment again." Pre-appointment synthesis across modules. Depends on lab pipeline + interpretation layer. |
| user_health_state materialised view | Protocol + injury + flags + baselines as queryable current state, updated on event write. Blocks Decision Support layer + chat context injection. Gated on the event-spine fork (OPEN_QUESTIONS). |

---

## LATER — planned

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
