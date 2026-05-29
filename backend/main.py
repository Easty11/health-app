from fastapi import FastAPI
from database import Base, engine
from routers import auth as auth_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Health & Performance API")

app.include_router(auth_router.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
