from fastapi import FastAPI
from database import Base, engine
from routers import auth as auth_router
from routers import integrations as integrations_router
from routers import chat as chat_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Health & Performance API")

app.include_router(auth_router.router)
app.include_router(integrations_router.router)
app.include_router(chat_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
