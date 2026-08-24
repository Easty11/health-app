import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cors_errors import add_cors_error_handler
from hc_sync_diagnostics import add_hc_sync_validation_diagnostics
from routers.health_connect import SyncPayload
from database import Base, engine
from routers import auth as auth_router
from routers import integrations as integrations_router
from routers import chat as chat_router
from routers import password_reset as password_reset_router
from routers import knowledge as knowledge_router
from routers import checkin as checkin_router
from routers import health_connect as health_connect_router
from routers import samsung_hrv as samsung_hrv_router
from routers.health import router as health_router
from routers import checkin_v2 as checkin_v2_router
from routers import polar as polar_router
from routers import engine as engine_router
from routers import mcp_auth as mcp_auth_router
from routers import labs as labs_router
from routers import interpretation as interpretation_router

Base.metadata.create_all(bind=engine)

from mcp_server import mcp

_mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run the MCP sub-app's lifespan so its StreamableHTTPSessionManager
    # initialises its task group before the first request arrives.
    async with _mcp_app.router.lifespan_context(_mcp_app):
        yield


app = FastAPI(title="Health & Performance API", lifespan=lifespan)

# FRONTEND_URL is set in Railway to the deployed frontend URL,
# e.g. https://health-app-frontend.up.railway.app
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "https://health-app-production-e0ff.up.railway.app",
    "https://claude.ai",
    os.getenv("FRONTEND_URL", ""),
]

_allowed_origins = [o for o in origins if o]  # filter empty string when unset

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global 500 guard that carries CORS headers (see cors_errors / #66).
add_cors_error_handler(app, _allowed_origins)

# Shape-only diagnostics for a rejected /health-connect/sync payload (#235). Logs
# key names + counts, NEVER health values; stock 422 body on every other route.
add_hc_sync_validation_diagnostics(app, known_keys=set(SyncPayload.model_fields))

app.include_router(auth_router.router)
app.include_router(password_reset_router.router)
app.include_router(integrations_router.router)
app.include_router(knowledge_router.router)
app.include_router(checkin_router.router)
app.include_router(health_connect_router.router)
app.include_router(samsung_hrv_router.router)
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(checkin_v2_router.router)
app.include_router(polar_router.router)
app.include_router(engine_router.router)
app.include_router(chat_router.router)
app.include_router(mcp_auth_router.router)
app.include_router(labs_router.router)
app.include_router(interpretation_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.mount("/", _mcp_app)

# Inject x-enum-varnames into SleepStageType so orval/openapi-generator emits
# named enum members instead of bare integers. Must run after all routers are
# included so app.openapi() sees the complete route list.
from routers.health_connect import (
    SleepStageType as _SleepStageType,
    ExerciseSessionType as _ExerciseSessionType,
)
_schema = app.openapi()
_st = _schema.get("components", {}).get("schemas", {}).get("SleepStageType")
if _st is not None:
    _st["x-enum-varnames"] = [m.name for m in _SleepStageType]

# ExerciseSessionType is a mapping helper, not a wire field type (the inbound
# exerciseType stays a lenient int), so FastAPI does not auto-emit its schema.
# Publish the full component explicitly — with values AND x-enum-varnames — so
# the companion app can generate a named-constant contract file from the spec.
_schema.setdefault("components", {}).setdefault("schemas", {})["ExerciseSessionType"] = {
    "type": "integer",
    "enum": [m.value for m in _ExerciseSessionType],
    "x-enum-varnames": [m.name for m in _ExerciseSessionType],
    "description": (
        "Health Connect ExerciseSessionRecord.ExerciseType. Mirrored from the "
        "androidx source; unassigned upstream codes are omitted. An exerciseType "
        "not listed here persists with sport_name NULL (never guessed)."
    ),
}
app.openapi_schema = _schema
