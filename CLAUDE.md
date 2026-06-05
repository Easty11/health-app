# Health App — CLAUDE.md

## Bash commands
# Backend
cd backend && .venv\Scripts\uvicorn main:app --reload

# Run migrations
cd backend && .venv\Scripts\alembic upgrade head

# Migrations (after model changes)
cd backend && .venv\Scripts\alembic revision --autogenerate -m "description"

# Frontend
cd frontend && npm run dev

# Companion app
cd ..\health-connect-app && npx expo run:android

## Stack
Backend: Python/FastAPI · PostgreSQL · Alembic · Railway
Frontend: React (Vite) + Tailwind
Mobile: Expo React Native (health-connect-app repo)

## Live URLs
Backend: https://health-app-backend-production-760e.up.railway.app
Frontend: https://health-app-production-e0ff.up.railway.app

## Known quirks (do not change without reason)
- bcrypt pinned to 4.0.1 — passlib 1.7.4 incompatible with 5.x
- POST /auth/login uses OAuth2PasswordRequestForm (form data, NOT JSON)
- Health Connect schema is flexible — see routers/health_connect.py
- Railway env var syntax: ${{Postgres.DATABASE_URL}}
- CORS origins include "null" and "https://claude.ai" for dev access

## Workflow
- All schema changes: alembic revision --autogenerate, commit migration, push
- Railway auto-runs migrations on deploy via Procfile
- VITE_API_URL in frontend/.env controls API target (.env is gitignored)
- Commit and push after each meaningful change

## Open issues
1. ~~Health Connect companion app permissions — fixed: switched handleGrantPermissions to use requestPermission() API (PermissionController contract) instead of wrong native intent~~
2. ~~create_routine 400 error — fixed: missing index fields on exercises/sets in connectors/hevy.py~~
3. ~~Conversation history clears on refresh — fixed: localStorage keyed by user email from JWT~~