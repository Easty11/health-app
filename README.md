# Health & Performance Platform

A multi-user health and performance platform that aggregates data from multiple sources and surfaces insights via a Claude AI layer.

## Integrations

| Source | Data |
|---|---|
| **Hevy** | Strength training workouts, exercise history, routines |
| **Health Connect** | Steps, sleep, heart rate, body metrics (Android) |
| **MyFitnessPal** | Nutrition, calorie tracking, macros |
| **GameTraka** | Sports performance, match and training session data |

## Architecture

```
health-app/
├── backend/        FastAPI — REST API, data ingestion, Claude AI layer
├── frontend/       React — user dashboard and insights UI
└── connectors/     Integration adapters for each data source
```

## Stack

- **Backend**: Python, FastAPI, uvicorn
- **Frontend**: React
- **AI**: Claude (Anthropic) for natural-language health insights

## Getting started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Health check: `GET http://localhost:8000/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```
