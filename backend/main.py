import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

logger = logging.getLogger("mcp.oauth")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Health & Performance API")

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
app.include_router(chat_router.router)


# ---------------------------------------------------------------------------
# Override FastMCP's hardcoded OAuth metadata to add "none" as a supported
# token_endpoint_auth_method. FastMCP advertises only client_secret_post and
# client_secret_basic; claude.ai requires "none" (PKCE public client) to be
# listed before it will attempt dynamic client registration.
#
# This route must be added to app.routes BEFORE app.mount("/mcp", ...) so
# that Starlette's router checks it first (first-match wins on prefix paths).
# ---------------------------------------------------------------------------
_OAUTH_METADATA = {
    "issuer": "https://health-app-backend-production-760e.up.railway.app/mcp",
    "authorization_endpoint": "https://health-app-backend-production-760e.up.railway.app/mcp/authorize",
    "token_endpoint": "https://health-app-backend-production-760e.up.railway.app/mcp/token",
    "registration_endpoint": "https://health-app-backend-production-760e.up.railway.app/mcp/register",
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
    "code_challenge_methods_supported": ["S256"],
}

# RFC 8414: issuer "https://server/mcp" → metadata at /.well-known/oauth-authorization-server/mcp
# This is what claude.ai fetches. FastMCP wrongly serves it at /mcp/.well-known/... instead.
@app.get("/.well-known/oauth-authorization-server/mcp", include_in_schema=False)
async def mcp_oauth_metadata_root(request: Request):
    logger.info("OAuth AS metadata (root) from %s", request.headers.get("user-agent", "unknown"))
    return JSONResponse(_OAUTH_METADATA)

# Also serve at the path FastMCP uses internally, in case other clients follow that convention.
@app.get("/mcp/.well-known/oauth-authorization-server", include_in_schema=False)
async def mcp_oauth_metadata_subpath(request: Request):
    logger.info("OAuth AS metadata (subpath) from %s", request.headers.get("user-agent", "unknown"))
    return JSONResponse(_OAUTH_METADATA)


from mcp_server import mcp
app.mount("/mcp", mcp.streamable_http_app())


# OAuth protected-resource metadata must be discoverable at the domain root.
# WWW-Authenticate points here; the actual metadata lives in the /mcp sub-app.
@app.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
async def oauth_protected_resource():
    return JSONResponse({
        "resource": "https://health-app-backend-production-760e.up.railway.app/mcp",
        "authorization_servers": ["https://health-app-backend-production-760e.up.railway.app/mcp"],
        "bearer_methods_supported": ["header"],
    })


@app.get("/health")
def health_check():
    return {"status": "ok"}
