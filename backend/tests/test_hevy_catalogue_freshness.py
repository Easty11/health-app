"""Q75 option (c): the workout-fetch path refreshes a stale catalogue (DECISIONS_LOG #211).

The 2026-08-05 incident discriminated Q75's axis empirically: Luke's workouts synced while
his templates did not, so three in-session customs were invisible to the resolver and the app
chat offered a duplicate mint. Option (c) piggybacks a per-user, staleness-gated template sync
on `/hevy/workouts` — the exact traffic that would have caught the drift.

Staleness is read off the per-user marker `user_integrations.templates_synced_at`, NOT an
aggregate over `hevy_exercise_templates.synced_at` (that column is per-row and its default
rows are re-stamped by any user's sync — an aggregate reads fresh off another user's run).

The sync is faked throughout (route tests fake `sync_exercise_templates`; the incident-fixture
test fakes the Hevy HTTP client and exercises the REAL upsert path). No live Hevy call.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import hevy_templates
import models
from auth import get_current_user
from database import get_db
from hevy_templates import refresh_catalogue_if_stale, resolve_custom_exercise
from routers import integrations

# The three 2026-08-05 custom templates (byte-exact titles as logged), ids pinned against the
# prod store post-sync (Q75 Step 0 seeder run, 2026-08-12). All three resolve as customs owned
# by user 1 — the incident was templates lagging workouts, not a built-in mismatch.
_FRONT_LAT_ID = "0dd081f1-960e-4bf0-87ca-14cf0ed217ff"   # iso-lateral front lat pull down
_WIDE_CHEST_ID = "1fe04727-cd01-4c66-92ac-86555e511bc8"  # Iso-lateral Wide Chest Press
_INCLINE_ID = "f8dccc5a-61b2-44a1-b162-d585996a0293"     # Iso-lateral Incline Press

_THREE_CUSTOMS = [
    {"id": _FRONT_LAT_ID, "title": "iso-lateral front lat pull down",
     "type": "weight_reps", "is_custom": True, "primary_muscle_group": "lats"},
    {"id": _WIDE_CHEST_ID, "title": "Iso-lateral Wide Chest Press",
     "type": "weight_reps", "is_custom": True, "primary_muscle_group": "chest"},
    {"id": _INCLINE_ID, "title": "Iso-lateral Incline Press",
     "type": "weight_reps", "is_custom": True, "primary_muscle_group": "chest"},
]


# --------------------------------------------------------------------------- #
# Harness                                                                      #
# --------------------------------------------------------------------------- #

def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(integrations.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user_with_hevy(db, *, marker):
    u = models.User(email="luke@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(models.UserIntegration(
        user_id=u.id, provider="hevy", api_key_encrypted="enc",
        templates_synced_at=marker,
    ))
    db.commit()
    return u


class _FakeWorkoutClient:
    """Stands in for the Hevy read client — proves the fetch still serves."""
    async def get_workouts(self, page=1, page_size=10):
        return {"workouts": [{"id": "w1"}], "page": page}

    async def get_all_workouts(self):
        return [{"id": "w1"}]


def _fake_sync(monkeypatch, *, returns=None, raises=None):
    """Fake the sync the gate calls; record the only_user_id it was scoped to."""
    calls: list[int | None] = []

    async def fake(db, *, only_user_id=None):
        calls.append(only_user_id)
        if raises is not None:
            raise raises
        return returns if returns is not None else {"users_synced": 1, "users_failed": 0}

    monkeypatch.setattr(hevy_templates, "sync_exercise_templates", fake)
    monkeypatch.setattr(integrations, "_hevy_client", lambda user, db: _FakeWorkoutClient())
    return calls


# --------------------------------------------------------------------------- #
# (a) stale marker -> sync fires, then the fetch proceeds                      #
# --------------------------------------------------------------------------- #

def test_stale_marker_triggers_sync_then_serves(db_session, monkeypatch):
    u = _user_with_hevy(db_session, marker=datetime.now(timezone.utc) - timedelta(hours=25))
    calls = _fake_sync(monkeypatch)

    r = _client(db_session, u).get("/integrations/hevy/workouts")

    assert r.status_code == 200
    assert r.json()["workouts"] == [{"id": "w1"}]   # fetch served
    assert calls == [u.id]                           # sync fired, scoped to the caller


def test_null_marker_is_stale_and_triggers_sync(db_session, monkeypatch):
    """Never-synced (NULL) is the incident's actual state — it must count as stale."""
    u = _user_with_hevy(db_session, marker=None)
    calls = _fake_sync(monkeypatch)

    r = _client(db_session, u).get("/integrations/hevy/workouts")

    assert r.status_code == 200
    assert calls == [u.id]


# --------------------------------------------------------------------------- #
# (b) fresh marker -> no sync call                                             #
# --------------------------------------------------------------------------- #

def test_fresh_marker_skips_sync(db_session, monkeypatch):
    u = _user_with_hevy(db_session, marker=datetime.now(timezone.utc) - timedelta(hours=1))
    calls = _fake_sync(monkeypatch)

    r = _client(db_session, u).get("/integrations/hevy/workouts")

    assert r.status_code == 200
    assert r.json()["workouts"] == [{"id": "w1"}]   # fetch still served
    assert calls == []                               # read stays pure — no Hevy sync


# --------------------------------------------------------------------------- #
# (c) sync fails -> the fetch still succeeds                                   #
# --------------------------------------------------------------------------- #

def test_sync_raise_never_fails_the_fetch(db_session, monkeypatch, caplog):
    """The outer guard: even if the refresh raises, the workout fetch it rode in on serves."""
    u = _user_with_hevy(db_session, marker=None)
    _fake_sync(monkeypatch, raises=RuntimeError("hevy outage"))

    with caplog.at_level(logging.WARNING):
        r = _client(db_session, u).get("/integrations/hevy/workouts")

    assert r.status_code == 200
    assert r.json()["workouts"] == [{"id": "w1"}]
    assert any("refresh FAILED" in m for m in caplog.messages)


def test_sync_failure_summary_never_fails_the_fetch(db_session, monkeypatch):
    """The realistic #77 shape: sync returns a failure SUMMARY (never raises) — fetch serves."""
    u = _user_with_hevy(db_session, marker=None)
    _fake_sync(monkeypatch, returns={"users_synced": 0, "users_failed": 1})

    r = _client(db_session, u).get("/integrations/hevy/workouts")

    assert r.status_code == 200
    assert r.json()["workouts"] == [{"id": "w1"}]


def test_all_workouts_path_also_gates(db_session, monkeypatch):
    """The 'See all' aggregate fetch carries the same staleness gate."""
    u = _user_with_hevy(db_session, marker=None)
    calls = _fake_sync(monkeypatch)

    r = _client(db_session, u).get("/integrations/hevy/workouts/all")

    assert r.status_code == 200
    assert calls == [u.id]


# --------------------------------------------------------------------------- #
# (d) incident fixture — absent customs land post-sync, and the marker stamps  #
# --------------------------------------------------------------------------- #

def test_incident_customs_land_and_marker_is_stamped(db_session, monkeypatch):
    """Real upsert path over a faked Hevy client: a NULL-marker fetch pulls the three
    2026-08-05 customs into the store and stamps the freshness marker."""
    u = _user_with_hevy(db_session, marker=None)

    class _FakeTemplateClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def get_exercise_templates(self, page=1, page_size=100):
            return {"exercise_templates": _THREE_CUSTOMS, "page_count": 1}

    monkeypatch.setattr(hevy_templates, "HevyClient", _FakeTemplateClient)
    # Route the key list past decrypt (the stored 'enc' is not a real Fernet token).
    monkeypatch.setattr(hevy_templates, "users_with_hevy_key", lambda db: [(u.id, "k1")])

    # BEFORE: the store is absent the three customs (the incident state).
    for c in _THREE_CUSTOMS:
        assert resolve_custom_exercise(db_session, c["title"], u.id) is None

    summary = asyncio.run(refresh_catalogue_if_stale(db_session, u.id))

    # AFTER: all three resolve to their pinned ids…
    assert summary is not None and summary["users_synced"] == 1
    for c in _THREE_CUSTOMS:
        assert resolve_custom_exercise(db_session, c["title"], u.id) == c["id"]
    # …and the per-user freshness marker is now stamped.
    row = db_session.query(models.UserIntegration).filter_by(
        user_id=u.id, provider="hevy").one()
    assert row.templates_synced_at is not None


# --------------------------------------------------------------------------- #
# gate unit — return contract                                                 #
# --------------------------------------------------------------------------- #

def test_gate_returns_none_when_fresh(db_session, monkeypatch):
    u = _user_with_hevy(db_session, marker=datetime.now(timezone.utc) - timedelta(hours=2))

    async def fake(db, *, only_user_id=None):
        raise AssertionError("must not sync when fresh")

    monkeypatch.setattr(hevy_templates, "sync_exercise_templates", fake)
    assert asyncio.run(refresh_catalogue_if_stale(db_session, u.id)) is None
