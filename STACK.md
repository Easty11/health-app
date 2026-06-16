# STACK OVERVIEW & DEPLOYMENT STATE

## Project identity

Personal and family health intelligence platform. Users connect wearables and
training apps; an AI layer provides coaching and readiness analysis grounded in
real data. Built by Easty (Luke) — personal/family use only at this stage.
Commercial path (freemium, family plan, B2B sports teams) is a future
consideration — do not over-engineer for it now.

---

## Tech stack

| Layer | Tech |
|-------|------|
| Backend | Python / FastAPI · PostgreSQL · Alembic · Railway |
| Frontend | React (Vite) + Tailwind · Railway |
| Mobile companion | Expo React Native (Android-first, iOS planned) |
| AI | Claude API — `claude-sonnet-4-20250514` |

---

## Repository layout (Windows local)

```
C:\Users\lukee\Projects\health-app\
  /backend        FastAPI app
  /frontend       React / Vite
C:\Users\lukee\Projects\health-connect-app\
                  Expo React Native companion
```

---

## Live URLs (Railway production)

| Service | URL |
|---------|-----|
| Backend | `https://health-app-backend-production-760e.up.railway.app` |
| Frontend | `https://health-app-production-e0ff.up.railway.app` |

---

## Local dev commands

```powershell
# Backend
cd C:\Users\lukee\Projects\health-app\backend
.venv\Scripts\uvicorn main:app --reload

# Frontend
cd C:\Users\lukee\Projects\health-app\frontend
npm run dev

# Companion app
cd C:\Users\lukee\Projects\health-connect-app
npx expo run:android
```

---

## Railway deployment notes

- Postgres connection string env var uses Railway interpolation syntax: `${{Postgres.DATABASE_URL}}`
- Procfile runs migrations then starts server: `alembic upgrade head && uvicorn ...`
- Alembic migrations are auto-applied on every deploy — commit migration files before pushing
- Frontend API base URL controlled by `VITE_API_URL` env var — `.env` is gitignored

---

## Auth

- JWT, 7-day expiry (`ACCESS_TOKEN_EXPIRE_MINUTES=10080`)
- Login endpoint uses `OAuth2PasswordRequestForm` — **form-encoded, not JSON**
- `bcrypt` pinned to `4.0.1` — `passlib 1.7.4` is incompatible with `bcrypt 5.x`; **do not upgrade bcrypt**

---

## Database

- Tables: `users`, `user_integrations`
- Health data columns: `heart_rate`, `steps`, `hrv`, `sleep`, `exercise`, `oxygen_saturation`, `respiratory_rate`, `weight`, `distance`
- Schema changes: run `alembic revision --autogenerate -m "description"` locally, commit the file, push → Railway auto-runs on deploy

---

## Key backend routes

```
POST   /auth/register
POST   /auth/login              ← form-encoded
GET    /integrations
POST   /integrations/hevy
DELETE /integrations/hevy
GET    /integrations/hevy/workouts
GET    /integrations/hevy/workout-count
POST   /chat
POST   /health-connect/sync
POST   /samsung-hrv/sync        ← Samsung Health Accessibility Scraper posts here
GET    /integrations/polar/auth-url    ← v4 OAuth (auth.polar.com), frontend redirects to {url}
GET    /integrations/polar/callback    ← v4 token exchange (browser GET, no bearer)
POST   /integrations/polar/sync        ← pulls v4 training-sessions → aerobic_sessions
GET    /integrations/polar/aerobic-sessions  ← ZIP + v4 sessions, one table
```

Polar history backfill (one-time): `python import_polar.py --zip <export.zip> --email <user>`
loads a Polar Flow ZIP export into `aerobic_sessions` (source=`polar_flow_export`,
carries cardio_load + HR zones). v4 and ZIP dedup by shared `identifier.id`.

---

## Users (family)

| User | Devices | Data sources |
|------|---------|--------------|
| Easty (Luke) | Samsung Galaxy S24 + Galaxy Ring + Polar H10 | Hevy (strength), Samsung Health Accessibility Scraper (Ring HRV/sleep), Health Connect (steps, SpO2), Polar AccessLink v4 API (aerobic sessions — H10 recorded via Polar Flow app) |
| Wife | Samsung Galaxy + Garmin watch | Garmin Connect → Health Connect |
| Son | Apple iPhone | Future — Apple Health |

---

## Data source status (as of June 2026)

| Source | Status | Notes |
|--------|--------|-------|
| Hevy | ✅ Working | Direct API. Routine creation via XML block pattern. create_workout pattern also works and is preferred for custom exercises. |
| Samsung Health Accessibility Scraper | ✅ Working | Confirmed full overnight extraction: HRV (RMSSD), sleep stages, respiratory rate, sleep efficiency, SpO2. Primary HRV path. Fragility risk — requires canary + honest score degradation on failure. |
| Health Connect (Android) | 🔧 Partial | Steps and sleep duration confirmed. Samsung Health confirmed NOT writing HRV, RHR, sleep stages, or respiratory rate to Health Connect. Permission issues (record types 38, 35, 11, 37) partially resolved via adb pm grant. |
| Samsung Health Data SDK | 📋 Planned | Migration target for metrics it can serve reliably (sleep stages, SpO2, skin temperature). Live SDK read with positive control is the agreed next action. If HRV returns real values, scraper scope shrinks. |
| Polar H10 (aerobic sessions) | ✅ Working | **Direct Polar AccessLink v4 Dynamic API** (`auth.polar.com` OAuth, `GET /v4/data/training-sessions/list`). NOT via Health Connect. v3 was abandoned — its exercise-transactions silently exclude Polar-Flow-app-recorded sessions (which is how this user records H10 via phone), returning 204. v4's date-range endpoint returns them. Stored in `aerobic_sessions` (source=`polar_v4`). v4 list omits cardio_load/HR-zones (those come only from ZIP export, source=`polar_flow_export`). Session-only; no resting HRV from H10. See Decision 17. |
| Garmin (wife) | ⏳ Pending | Garmin Connect → Health Connect. Not verified on-device. |
| GameTraka | 📋 Planned | Rugby performance data (GPS, player load, collisions) |
| Apple Health | 🔮 Future | For son (iOS) |

---

## Working conventions

- **All code changes go through Claude Code (CLI)** — not pasted into chat
- **All shell commands must be PowerShell-compatible** — Windows environment; no Linux syntax, no backslash line continuation
- Commit and push after every meaningful change; include commit hash in handoff summaries
- When handing off between sessions: paste a summary of what was done + current state
- **Data path verification before algorithm design** — before any metric enters the algorithm, record how you know it works: confirmed test, verified search, or official documentation. "The API has a field for it" is insufficient.
- **exercise_template_id values must come from real workout data** — never fabricate or guess them
- Verify data questions by querying Railway Postgres directly, not by browsing on-device UI
