import os
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


from fastapi.responses import JSONResponse
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
