from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from routers import auth as auth_router
from routers import integrations as integrations_router
from routers import chat as chat_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Health & Performance API")

# For Railway deployment, add the production frontend URL to this list,
# e.g. "https://health-app.up.railway.app"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(integrations_router.router)
app.include_router(chat_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
