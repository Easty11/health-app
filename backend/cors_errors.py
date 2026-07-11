"""Global 500 CORS-header guarantee (DECISIONS_LOG #66).

An unhandled exception is caught by Starlette's ServerErrorMiddleware, which sits
*outside* CORSMiddleware — so the resulting 500 skips CORS and the browser reports
a fake "No Access-Control-Allow-Origin" in place of the real error. Registering a
bare Exception handler that echoes the allowed Origin makes the frontend see the
true status. This is the safety net for the whole class; connector HTTP errors are
already remapped upstream (routers/integrations.py) and never reach here.

Kept DB-free and app-agnostic so it is unit-testable without importing main (which
would run create_all against the live DATABASE_URL).
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def add_cors_error_handler(app: FastAPI, allowed_origins: list[str]) -> None:
    @app.exception_handler(Exception)
    async def _unhandled_exception_cors(request: Request, exc: Exception) -> JSONResponse:
        headers: dict[str, str] = {}
        origin = request.headers.get("origin")
        if origin in allowed_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=headers,
        )
