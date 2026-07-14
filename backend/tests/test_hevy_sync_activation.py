"""Hevy template sync activation + resilience (DECISIONS_LOG #77).

The template subsystem sat on an unpopulated prod substrate: `sync_exercise_templates`
had no wired call site, and the seeder would resolve every title against an empty
table and exit 0. These tests pin the failure modes made loud.
"""
import asyncio
import logging

import pytest

import models
import hevy_templates
import sync_hevy_templates
import seed_exercise_region_tags as seeder
from connectors.hevy import HevyAuthError


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# G1 — per-user isolation: one dead key must not abort the whole sync.         #
# --------------------------------------------------------------------------- #

def test_one_user_failure_isolated_others_complete(db_session, monkeypatch, caplog):
    monkeypatch.setattr(
        hevy_templates, "users_with_hevy_key",
        lambda db: [(1, "k1"), (2, "bad"), (3, "k3")],
    )

    async def fake_sync_one_user(db, user_id, api_key):
        if user_id == 2:
            raise HevyAuthError("Invalid Hevy API key: 401")
        return {"rows_processed": 493, "defaults_seen": 490, "customs_seen": 3}

    monkeypatch.setattr(hevy_templates, "sync_one_user", fake_sync_one_user)

    with caplog.at_level(logging.WARNING, logger="hevy_templates"):
        summary = _run(hevy_templates.sync_exercise_templates(db_session))

    assert summary["users_attempted"] == 3
    assert summary["users_succeeded"] == 2
    assert summary["users_failed"] == 1
    assert summary["users_synced"] == 2                # == succeeded
    assert summary["rows_processed"] == 986            # only the two OK users
    per = {r["user_id"]: r for r in summary["per_user"]}
    assert per[1]["status"] == "ok" and per[3]["status"] == "ok"
    assert per[2]["status"] == "failed"
    assert "HevyAuthError" in per[2]["error"]           # error captured
    assert any("FAILED for user 2" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------- #
# G2 — empty user list is a loud failure signal, not a silent no-op.          #
# --------------------------------------------------------------------------- #

def test_empty_user_list_warns_and_zero_synced(db_session, monkeypatch, caplog):
    monkeypatch.setattr(hevy_templates, "users_with_hevy_key", lambda db: [])

    with caplog.at_level(logging.WARNING, logger="hevy_templates"):
        summary = _run(hevy_templates.sync_exercise_templates(db_session))

    assert summary["users_synced"] == 0
    assert summary["users_attempted"] == 0
    assert any("NO users with a stored Hevy key" in r.getMessage() for r in caplog.records)
    assert sync_hevy_templates._exit_code(summary) == 1  # CLI exits non-zero


def test_exit_code_matrix():
    assert sync_hevy_templates._exit_code({"users_synced": 0, "users_failed": 0}) == 1  # empty
    assert sync_hevy_templates._exit_code({"users_synced": 3, "users_failed": 1}) == 1  # partial
    assert sync_hevy_templates._exit_code({"users_synced": 3, "users_failed": 0}) == 0  # clean


# --------------------------------------------------------------------------- #
# G3 — seeder refuses on an empty template store (precondition, not data).     #
# --------------------------------------------------------------------------- #

def test_seeder_refuses_on_empty_template_store(db_session):
    proposal = {"_meta": {"source": "llm_proposed"}, "tags": [], "no_pattern": []}
    # hevy_exercise_templates is empty in a fresh in-memory db.
    with pytest.raises(seeder.EmptyTemplateStoreError):
        seeder.seed_tags(db_session, user_id=1, proposal=proposal)
    # Nothing written.
    assert db_session.query(models.ExerciseRegionTag).count() == 0


def test_seeder_proceeds_once_a_template_exists(db_session):
    db_session.add(models.HevyExerciseTemplate(
        id="ABC", title="Goblet Squat", is_custom=False, owner_user_id=None,
    ))
    db_session.commit()
    proposal = {"_meta": {"source": "llm_proposed"},
                "tags": [{"title": "Goblet Squat", "laterality": "bilateral",
                          "regions": [{"key": "squat", "role": "primary"}]}],
                "no_pattern": []}
    summary = seeder.seed_tags(db_session, user_id=1, proposal=proposal)  # must not raise
    assert summary["titles_resolved"] == 1


# --------------------------------------------------------------------------- #
# G5 — --user-id path syncs exactly one user, touches no other.               #
# --------------------------------------------------------------------------- #

def test_only_user_id_syncs_exactly_one_user(db_session, monkeypatch):
    monkeypatch.setattr(
        hevy_templates, "users_with_hevy_key",
        lambda db: [(1, "k1"), (4, "k4"), (5, "k5")],
    )
    called: list[int] = []

    async def fake_sync_one_user(db, user_id, api_key):
        called.append(user_id)
        return {"rows_processed": 10, "defaults_seen": 9, "customs_seen": 1}

    monkeypatch.setattr(hevy_templates, "sync_one_user", fake_sync_one_user)

    summary = _run(hevy_templates.sync_exercise_templates(db_session, only_user_id=4))

    assert called == [4]                       # no other user's sync ran
    assert summary["users_attempted"] == 1
    assert summary["users_succeeded"] == 1
    assert [r["user_id"] for r in summary["per_user"]] == [4]


def test_only_user_id_unknown_is_empty_failure_signal(db_session, monkeypatch):
    monkeypatch.setattr(hevy_templates, "users_with_hevy_key", lambda db: [(1, "k1")])
    summary = _run(hevy_templates.sync_exercise_templates(db_session, only_user_id=999))
    assert summary["users_synced"] == 0
    assert sync_hevy_templates._exit_code(summary) == 1
