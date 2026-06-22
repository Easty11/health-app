import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in origins if o],  # filter empty string when unset
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


_openapi_cache: dict | None = None


def custom_openapi():
    global _openapi_cache
    if _openapi_cache:
        return _openapi_cache
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    sleep_stage = schema.get("components", {}).get("schemas", {}).get("SleepStageType")
    if sleep_stage is not None:
        from routers.health_connect import SleepStageType
        sleep_stage["x-enum-varnames"] = [m.name for m in SleepStageType]
    _openapi_cache = schema
    return schema


app.openapi = custom_openapi


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.mount("/", _mcp_app)
