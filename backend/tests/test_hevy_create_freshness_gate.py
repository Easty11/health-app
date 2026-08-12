"""The chat create path refreshes a stale catalogue BEFORE the idempotency check (#212).

Follow-up to Q75 / #211. #211 keeps the catalogue fresh by piggybacking a staleness-gated
sync on the workout-FETCH path. But custom-exercise creation via `<hevy_create_exercise>`
is also user-facing, and it reads the local store TWICE — the honest-confirmation pre-check
in `_process_exercise_actions` and `create_and_resolve`'s own idempotency read. A chat create
with no recent fetch races a stale catalogue: an upstream custom minted since the last sync is
invisible to both reads, so a duplicate mints against a delete-less API — the 2026-08-05
incident's mint offer.

The gate closes the window by refreshing (staleness-gated) before the pre-check. Placed there,
not inside `create_and_resolve`: the confirmation's honesty depends on the pre-check reading a
fresh store, and a fresh read there leaves `create_and_resolve`'s read fresh too — one refresh
closes both.

Sync is faked throughout — the window-closer fakes `sync_exercise_templates` (the transport)
and exercises the REAL gate + REAL pre-check; the placement/cost tests fake the gate itself to
count calls. No live Hevy call.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import hevy_templates
import models
from encryption import encrypt
from routers import chat


def _run(coro):
    return asyncio.run(coro)


def _integration(db, *, marker, user_id=1):
    """A stored (decryptable) Hevy key with a chosen freshness marker."""
    db.add(models.UserIntegration(
        user_id=user_id, provider="hevy",
        api_key_encrypted=encrypt("hk_test"), templates_synced_at=marker))
    db.commit()


def _block(title="Copenhagen Plank") -> str:
    body = {
        "title": title, "exercise_type": "duration",
        "equipment_category": "none", "muscle_group": "adductors",
        "other_muscles": ["abdominals"],
    }
    return f"<hevy_create_exercise>\n{json.dumps(body)}\n</hevy_create_exercise>"


def _install_create(monkeypatch):
    """Fake `create_and_resolve`; record whether (and with what) it was reached."""
    calls: list[str] = []

    async def fake(db, user_id, title, **kw):
        calls.append(title)
        return "NEW-UUID"

    monkeypatch.setattr(chat, "create_and_resolve", fake)
    return calls


def _count_refresh(monkeypatch):
    """Fake the gate itself; record each (user_id) it is called with — placement probe."""
    calls: list[int] = []

    async def fake(db, user_id):
        calls.append(user_id)
        return None

    monkeypatch.setattr(chat, "refresh_catalogue_if_stale", fake)
    return calls


# --------------------------------------------------------------------------- #
# The window-closer — real gate, real pre-check, faked transport               #
# --------------------------------------------------------------------------- #

def test_stale_catalogue_refreshes_before_idempotency_check(db_session, monkeypatch):
    """A stale store missing an upstream custom: the refresh pulls it in, the pre-check
    then catches it, and NOTHING is minted — the duplicate window is closed."""
    _integration(db_session, marker=None)                    # NULL marker == stale
    create_calls = _install_create(monkeypatch)              # would mint if reached
    assert hevy_templates.resolve_exercise(db_session, "Copenhagen Plank", 1) is None

    async def fake_sync(db, *, only_user_id=None):
        # Simulate the sync surfacing the previously-invisible upstream custom + stamping.
        db.add(models.HevyExerciseTemplate(
            id="UPSTREAM-UUID", title="Copenhagen Plank",
            is_custom=True, owner_user_id=only_user_id))
        db.query(models.UserIntegration).filter_by(
            user_id=only_user_id, provider="hevy").update(
            {"templates_synced_at": datetime.now(timezone.utc)})
        db.commit()
        return {"users_synced": 1, "users_failed": 0}

    monkeypatch.setattr(hevy_templates, "sync_exercise_templates", fake_sync)

    cleaned, actions = _run(chat._process_exercise_actions("ok\n" + _block(), 1, db_session))

    assert create_calls == []                                # never minted
    assert actions == [
        "✓ 'Copenhagen Plank' is already in the exercise catalogue — nothing created"]
    assert "<hevy_create_exercise>" not in cleaned


# --------------------------------------------------------------------------- #
# No double-sync on the common (fresh) path                                    #
# --------------------------------------------------------------------------- #

def test_fresh_marker_skips_the_sync_and_create_proceeds(db_session, monkeypatch):
    """A recent fetch/create leaves a fresh marker: the gate consults it (one column) and
    skips the Hevy call, then the genuinely-new create proceeds and mints."""
    _integration(db_session, marker=datetime.now(timezone.utc) - timedelta(hours=1))
    create_calls = _install_create(monkeypatch)

    synced: list = []

    async def fake_sync(db, *, only_user_id=None):
        synced.append(only_user_id)
        return {"users_synced": 1, "users_failed": 0}

    monkeypatch.setattr(hevy_templates, "sync_exercise_templates", fake_sync)

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    assert synced == []                                      # fresh -> no Hevy sync
    assert create_calls == ["Copenhagen Plank"]              # brand-new title still mints
    assert actions == ["✓ Custom exercise 'Copenhagen Plank' created in Hevy"]


# --------------------------------------------------------------------------- #
# Placement / cost — refresh runs once per turn, and only when there is work   #
# --------------------------------------------------------------------------- #

def test_refresh_runs_once_per_turn_regardless_of_block_count(db_session, monkeypatch):
    """The gate sits before the loop, so two blocks in one reply consult it exactly once."""
    _integration(db_session, marker=None)
    _install_create(monkeypatch)
    refreshes = _count_refresh(monkeypatch)

    _run(chat._process_exercise_actions(
        _block() + "\n" + _block(title="Jefferson Curl"), 1, db_session))

    assert refreshes == [1]                                  # once, not once-per-block


def test_no_block_turn_never_refreshes(db_session, monkeypatch):
    """The overwhelmingly common chat turn carries no block — zero gate overhead."""
    refreshes = _count_refresh(monkeypatch)
    _run(chat._process_exercise_actions("just talking", 1, db_session))
    assert refreshes == []


def test_not_connected_never_refreshes(db_session, monkeypatch):
    """No stored key: the not-connected early return precedes the gate — never sync keyless."""
    refreshes = _count_refresh(monkeypatch)
    _run(chat._process_exercise_actions(_block(), 1, db_session))  # no UserIntegration row
    assert refreshes == []
