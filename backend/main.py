import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from routers import auth as auth_router
from routers import integrations as integrations_router
from routers import chat as chat_router
from routers import password_reset as password_reset_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Health & Performance API")

# FRONTEND_URL is set in Railway to the deployed frontend URL,
# e.g. https://health-app-frontend.up.railway.app
origins = [
    "http://localhost:5173",
    "http://localhost:5174",
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
app.include_router(chat_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
