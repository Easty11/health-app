"""The Hevy template sync gets a call site: POST /integrations/hevy/sync + connect-seed.

`sync_exercise_templates` populates `hevy_exercise_templates` — the substrate every
resolver reads (`resolve_exercise`, `catalogue_titles_by_id`, `suggest_candidates`,
`resolve_custom_exercise`) — but was reachable only from the module `__main__` and the
`sync_hevy_templates.py` CLI. FEEDBACK §8 records the consequence: an unpopulated table
in prod, every title->id resolution missing, and a green suite reading as done.

These tests drive the ROUTES over a standalone app rather than calling the handlers
directly (the `_boom_app` precedent in `test_connector_error_policy.py`), because the
defect being fixed is exactly "the function exists and nothing reaches it": a path that
was never registered answers 404, and every assertion below fails. Calling the handler
object would prove the body and skip the wiring — the one thing under test.

The sync itself is faked throughout; no live Hevy call, and no create_all against the
live DATABASE_URL (the app is built standalone, never `import main`).
"""
import models
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth import get_current_user
from connectors.hevy import HevyAuthError
from database import get_db
from routers import integrations


def _client(db, user) -> TestClient:
    """Only the integrations router, with auth + session overridden."""
    app = FastAPI()
    app.include_router(integrations.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(db, email="luke@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _ok_summary(**over) -> dict:
    """The shape a clean single-user run returns (prod-realistic counts)."""
    summary = {
        "users_synced": 1, "users_attempted": 1, "users_succeeded": 1, "users_failed": 0,
        "rows_processed": 494, "defaults_seen": 490, "customs_seen": 4,
        "collision_count": 0, "collisions": [],
        "per_user": [{"user_id": 1, "status": "ok", "rows_processed": 494, "error": None}],
    }
    summary.update(over)
    return summary


def _failed_summary(error: str) -> dict:
    return {
        "users_synced": 0, "users_attempted": 1, "users_succeeded": 0, "users_failed": 1,
        "rows_processed": 0, "defaults_seen": 0, "customs_seen": 0,
        "collision_count": 0, "collisions": [],
        "per_user": [{"user_id": 1, "status": "failed", "rows_processed": 0, "error": error}],
    }


def _keyless_summary() -> dict:
    """What `sync_exercise_templates` returns for an id holding no Hevy key."""
    return {
        "users_synced": 0, "users_attempted": 0, "users_succeeded": 0, "users_failed": 0,
        "rows_processed": 0, "defaults_seen": 0, "customs_seen": 0,
        "collision_count": 0, "collisions": [], "per_user": [],
    }


def _install(monkeypatch, *, returns: dict | None = None, raises: Exception | None = None):
    """Fake the sync and record the kwargs it was called with."""
    calls: list[dict] = []

    async def fake_sync(db, *, only_user_id=None):
        calls.append({"only_user_id": only_user_id})
        if raises is not None:
            raise raises
        return returns

    monkeypatch.setattr(integrations, "sync_exercise_templates", fake_sync)
    return calls


# --------------------------------------------------------------------------- #
# G1 — the endpoint exists, is scoped to the caller, and returns the summary.  #
# --------------------------------------------------------------------------- #

def test_sync_endpoint_returns_summary_verbatim(db_session, monkeypatch):
    user = _user(db_session)
    calls = _install(monkeypatch, returns=_ok_summary())

    r = _client(db_session, user).post("/integrations/hevy/sync")

    assert r.status_code == 200
    assert r.json() == _ok_summary()          # verbatim — counts readable at the call site
    assert calls == [{"only_user_id": user.id}]  # scoped to the caller, never family-wide


def test_sync_endpoint_reports_a_populated_catalogue(db_session, monkeypatch):
    """`defaults_seen` survives to the response — the number the prod gate reads."""
    user = _user(db_session)
    _install(monkeypatch, returns=_ok_summary())

    body = _client(db_session, user).post("/integrations/hevy/sync").json()

    assert body["defaults_seen"] > 0
    assert body["rows_processed"] == 494


# --------------------------------------------------------------------------- #
# G2 — a failed run is never a 200 with a silent zero (FEEDBACK §8).          #
# --------------------------------------------------------------------------- #

def test_sync_endpoint_revoked_key_maps_to_424_not_401(db_session, monkeypatch):
    """The #66 decoupling must survive the round-trip through the summary string.

    `sync_exercise_templates` records the exception as text, so the mapping only lands
    on 424 if `_sync_error_to_http` rehydrates the type. A 401 here would log the user
    out of the app over a dead *connector* key.
    """
    user = _user(db_session)
    _install(monkeypatch, returns=_failed_summary("HevyAuthError: Invalid Hevy API key: 401"))

    r = _client(db_session, user).post("/integrations/hevy/sync")

    assert r.status_code == 424
    assert r.status_code != 401
    assert "Invalid Hevy API key" in r.json()["detail"]


def test_sync_endpoint_unrecognised_error_maps_to_502(db_session, monkeypatch):
    user = _user(db_session)
    _install(monkeypatch, returns=_failed_summary("RuntimeError: socket closed"))

    r = _client(db_session, user).post("/integrations/hevy/sync")

    assert r.status_code == 502
    assert "socket closed" in r.json()["detail"]


def test_sync_endpoint_never_returns_200_on_zero_synced(db_session, monkeypatch):
    """The load-bearing negative: `users_synced == 0` must not read as success."""
    user = _user(db_session)
    _install(monkeypatch, returns=_failed_summary("HevyForbiddenError: plan limit"))

    r = _client(db_session, user).post("/integrations/hevy/sync")

    assert r.status_code == 403
    assert r.status_code != 200


def test_sync_endpoint_keyless_caller_is_404(db_session, monkeypatch):
    """Same body `_require_integration` gives, so every Hevy route reads alike."""
    user = _user(db_session)
    _install(monkeypatch, returns=_keyless_summary())

    r = _client(db_session, user).post("/integrations/hevy/sync")

    assert r.status_code == 404
    assert r.json()["detail"] == "hevy integration not connected"


def test_sync_failure_mapper_passes_a_clean_summary(db_session):
    """Unit-level: a clean summary yields no HTTPException at all."""
    assert integrations._sync_failure(_ok_summary()) is None


# --------------------------------------------------------------------------- #
# G3 — connect-time seed: same path, and the key store survives a bad seed.   #
# --------------------------------------------------------------------------- #

def test_connect_stores_key_and_seeds_the_catalogue(db_session, monkeypatch):
    user = _user(db_session)
    calls = _install(monkeypatch, returns=_ok_summary())

    r = _client(db_session, user).post("/integrations/hevy", json={"api_key": "hk_live"})

    assert r.status_code == 201
    assert r.json()["detail"] == "Hevy integration saved"
    assert r.json()["sync"] == _ok_summary()     # seed result visible, not hidden
    assert calls == [{"only_user_id": user.id}]  # the SAME one path as /hevy/sync
    # The key landed, and it landed BEFORE the seed ran — the commit is what makes it
    # visible to `users_with_hevy_key`.
    row = db_session.query(models.UserIntegration).filter_by(
        user_id=user.id, provider="hevy").one()
    assert row.api_key_encrypted


def test_connect_survives_a_raising_seed_and_reports_it(db_session, monkeypatch):
    """201 stands and the key persists, but the failure is on the wire, not swallowed."""
    user = _user(db_session)
    _install(monkeypatch, raises=HevyAuthError("Invalid Hevy API key: 401"))

    r = _client(db_session, user).post("/integrations/hevy", json={"api_key": "hk_bad"})

    assert r.status_code == 201                       # storing the key is the contract
    assert r.json()["detail"] == "Hevy integration saved"
    assert r.json()["sync"]["status"] == "failed"     # …and NOT swallowed
    assert "HevyAuthError" in r.json()["sync"]["error"]
    assert r.json()["sync"]["users_synced"] == 0
    # The store survives the unhappy seed — prove it by reading the row back.
    assert db_session.query(models.UserIntegration).filter_by(
        user_id=user.id, provider="hevy").count() == 1


def test_connect_reports_a_partial_seed_without_failing_the_store(db_session, monkeypatch):
    """A seed that returns a failure summary (rather than raising) is equally visible."""
    user = _user(db_session)
    _install(monkeypatch, returns=_failed_summary("RuntimeError: socket closed"))

    r = _client(db_session, user).post("/integrations/hevy", json={"api_key": "hk_live"})

    assert r.status_code == 201
    assert r.json()["sync"]["users_failed"] == 1
    assert r.json()["sync"]["rows_processed"] == 0
    assert db_session.query(models.UserIntegration).filter_by(
        user_id=user.id, provider="hevy").count() == 1


def test_connect_replaces_an_existing_key_and_reseeds(db_session, monkeypatch):
    """Re-connect path (row exists) takes the same seed, not a silent skip."""
    user = _user(db_session)
    db_session.add(models.UserIntegration(
        user_id=user.id, provider="hevy", api_key_encrypted="stale"))
    db_session.commit()
    calls = _install(monkeypatch, returns=_ok_summary())

    r = _client(db_session, user).post("/integrations/hevy", json={"api_key": "hk_new"})

    assert r.status_code == 201
    assert calls == [{"only_user_id": user.id}]
    row = db_session.query(models.UserIntegration).filter_by(
        user_id=user.id, provider="hevy").one()
    assert row.api_key_encrypted != "stale"


# --------------------------------------------------------------------------- #
# G4 — the error rehydration registry, directly.                              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("recorded, expected", [
    ("HevyAuthError: revoked", 424),
    ("HevyForbiddenError: plan limit", 403),
    ("httpx.HTTPStatusError: Hevy API error 400", 502),
    ("RuntimeError: boom", 502),
    (None, 502),
])
def test_recorded_error_string_maps_to_the_right_code(recorded, expected):
    assert integrations._sync_error_to_http(recorded).status_code == expected
