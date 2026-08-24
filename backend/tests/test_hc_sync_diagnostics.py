"""GATE 4 — a rejected /health-connect/sync payload is diagnosable from its SHAPE, and
health values never enter the log (#235).

Two apps are built with the REAL SyncPayload as the route body — one with the handler,
one stock (FastAPI's default RequestValidationError handler) — so "byte-identical on
every other route" is asserted against a captured stock 422, not against what the
handler "should" produce.
"""
import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hc_sync_diagnostics import add_hc_sync_validation_diagnostics, HC_SYNC_PATH
from routers.health_connect import SyncPayload

_FIXTURE = Path(__file__).parent / "fixtures" / "hc_sync_payload_canonical.json"
_KNOWN = set(SyncPayload.model_fields)
_OTHER_PATH = "/some/other/route"


def _build(with_handler: bool) -> TestClient:
    app = FastAPI()

    @app.post(HC_SYNC_PATH)
    def _sync(p: SyncPayload):            # noqa: ANN202
        return {"ok": True}

    @app.post(_OTHER_PATH)
    def _other(p: SyncPayload):           # noqa: ANN202
        return {"ok": True}

    if with_handler:
        add_hc_sync_validation_diagnostics(app, known_keys=_KNOWN)
    return TestClient(app, raise_server_exceptions=False)


def _rename_payload() -> dict:
    """A raw-name rename that 422s: heartRate sends `beatsPerMinute` (unknown) with a
    SENTINEL value, and no `bpm` (missing canonical). The sentinel proves values stay
    out of the log even for the failing record."""
    d = json.loads(_FIXTURE.read_text())
    hr = d["heartRate"][0]
    hr.pop("bpm")
    hr["beatsPerMinute"] = 918273645          # sentinel — must never appear in logs
    return d


# ---------- the reject IS diagnosable: missing canonical key + unknown key, by name ----------

def test_a_rename_logs_the_missing_and_the_unknown_key_by_name(caplog):
    client = _build(with_handler=True)
    with caplog.at_level(logging.WARNING, logger="hc_sync_diagnostics"):
        r = client.post(HC_SYNC_PATH, json=_rename_payload())
    assert r.status_code == 422

    logged = "\n".join(rec.getMessage() for rec in caplog.records
                       if rec.name == "hc_sync_diagnostics")
    assert logged, "no diagnostic log line emitted for a sync-path rejection"
    # The missing canonical key (a validation error field-path) and the unknown key
    # that replaced it (a key of the first failing record) — both NAMES, both present.
    assert "bpm" in logged
    assert "beatsPerMinute" in logged


def test_the_log_names_no_health_value_even_from_the_failing_record(caplog):
    """The sentinel sits ON the failing heartRate record. The shape extractor reads that
    record's KEY NAMES, never its values, so the sentinel must be absent."""
    client = _build(with_handler=True)
    with caplog.at_level(logging.WARNING, logger="hc_sync_diagnostics"):
        client.post(HC_SYNC_PATH, json=_rename_payload())
    logged = "\n".join(rec.getMessage() for rec in caplog.records
                       if rec.name == "hc_sync_diagnostics")
    assert logged
    assert "918273645" not in logged, "a health value reached the log — #235 violated"


# ---------- other routes: byte-identical to stock, and NO diagnostic log ----------

def test_other_route_422_is_byte_identical_to_stock(caplog):
    handler = _build(with_handler=True)
    stock = _build(with_handler=False)

    with caplog.at_level(logging.WARNING, logger="hc_sync_diagnostics"):
        r_handler = handler.post(_OTHER_PATH, json=_rename_payload())
    r_stock = stock.post(_OTHER_PATH, json=_rename_payload())

    assert r_handler.status_code == r_stock.status_code == 422
    assert r_handler.json() == r_stock.json(), "handler changed a non-sync route's 422 body"
    # No diagnostic for a route that is not the sync path.
    assert not [rec for rec in caplog.records if rec.name == "hc_sync_diagnostics"]


def test_sync_route_422_body_is_also_byte_identical_to_stock():
    """The diagnostic is a log SIDE-EFFECT: the sync path's 422 body must equal stock
    too — the handler delegates the response to stock on every path."""
    handler = _build(with_handler=True)
    stock = _build(with_handler=False)
    r_handler = handler.post(HC_SYNC_PATH, json=_rename_payload())
    r_stock = stock.post(HC_SYNC_PATH, json=_rename_payload())
    assert r_handler.status_code == r_stock.status_code == 422
    assert r_handler.json() == r_stock.json()


# ---------- the handler is actually wired onto the real app (landed != live, §8) ----------

def test_the_real_app_registers_this_handler_not_the_default():
    """FastAPI ships a default RequestValidationError handler, so presence is not proof.
    Assert the live handler is OURS by identity — otherwise the diagnostic is dead code."""
    import main
    from fastapi.exceptions import RequestValidationError
    handler = main.app.exception_handlers.get(RequestValidationError)
    assert handler is not None
    assert getattr(handler, "__name__", "") == "_hc_sync_validation_diagnostics"
