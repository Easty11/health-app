"""Diagnose a rejected /health-connect/sync payload — SHAPE, never values (#235).

A raw-name payload now 422s at validation (#234), before the route handler runs, so
`model_extra` is unreachable on failure. This records WHAT was wrong on the wire so a
rename is diagnosable once remote users are on the endpoint — without which a silent
sync gap can only be debugged by asking the user what their device sent.

HEALTH DATA DOES NOT ENTER LOGS. The endpoint now carries more than one person's
data; a rejected payload is a week of someone's heart rate, sleep and HRV. Logging the
raw body would put that in Railway logs on every client defect — retained outside the
database, outside any schema, in a surface nobody audits — and unbounded (a retrying
client rewrites it each time). The diagnostic need never required the values; it
requires the shape. So this logs only:

  * validation error field-paths and error types (`missing`, `int_type`)
  * top-level key names present, unknown ones flagged
  * per-stream record counts
  * the first failing record's KEY NAMES and index — never its values

A rename is fully diagnosable from that: the missing canonical key is a field-path in
the errors, and the unknown key that replaced it is a flagged top-level key or a key
of the first failing record — both are names.

Registering a RequestValidationError handler REPLACES FastAPI's default globally, so
this delegates to the stock handler for the RESPONSE on every path (byte-identical
behaviour everywhere, including the sync path — the diagnostic is a log side-effect,
not a body change) and emits the log line only when the path matches. Kept DB-free and
app-agnostic (known-keys passed in) so it is unit-testable without importing main.
"""
import json
import logging
from typing import Any, Iterable, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

logger = logging.getLogger(__name__)

HC_SYNC_PATH = "/health-connect/sync"


def _shape_only(exc: RequestValidationError, known_keys: set[str]) -> dict[str, Any]:
    """Extract the diagnosable SHAPE of a rejected body. Never returns a stored value."""
    errors = [
        {"loc": ".".join(str(p) for p in e.get("loc", ())), "type": e.get("type")}
        for e in exc.errors()
    ]

    body = exc.body
    is_map = isinstance(body, dict)
    top_keys = sorted(body.keys()) if is_map else None
    unknown_top_keys = (
        [k for k in top_keys if k not in known_keys] if top_keys is not None else []
    )
    # Per-stream counts only — len(), never the elements.
    counts = (
        {k: len(v) for k, v in body.items() if isinstance(v, list)} if is_map else {}
    )

    # First failing record: the first error whose loc contains a list index. FastAPI
    # prefixes locs with "body", so the shape is ("body", <stream>, <index>, <field>) —
    # find the first int and take the element before it as the stream, prefix-agnostic.
    first_failing: Optional[dict[str, Any]] = None
    if is_map:
        for e in exc.errors():
            loc = e.get("loc", ())
            pos = next((i for i, p in enumerate(loc) if isinstance(p, int) and i >= 1), None)
            if pos is None:
                continue
            stream, idx = loc[pos - 1], loc[pos]
            seq = body.get(stream)
            if isinstance(seq, list) and 0 <= idx < len(seq) and isinstance(seq[idx], dict):
                # KEY NAMES ONLY — the values on this record are never read.
                first_failing = {"stream": stream, "index": idx,
                                 "keys": sorted(seq[idx].keys())}
            break

    return {
        "errors": errors,
        "top_keys": top_keys,
        "unknown_top_keys": unknown_top_keys,
        "counts": counts,
        "first_failing_record": first_failing,
    }


def add_hc_sync_validation_diagnostics(
    app: FastAPI,
    known_keys: Iterable[str],
    path: str = HC_SYNC_PATH,
) -> None:
    """Register a RequestValidationError handler that logs SHAPE for `path` rejections
    and reproduces stock behaviour byte-identically on every other path."""
    known = set(known_keys)

    @app.exception_handler(RequestValidationError)
    async def _hc_sync_validation_diagnostics(request: Request, exc: RequestValidationError):
        if request.url.path == path:
            # json.dumps of a shape-only dict — asserted value-free by the sentinel test.
            logger.warning("HC sync rejected (shape only): %s",
                           json.dumps(_shape_only(exc, known), sort_keys=True))
        # Response is ALWAYS the stock 422 — byte-identical on every path.
        return await request_validation_exception_handler(request, exc)
