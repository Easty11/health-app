"""Routine-create hardening — the connector floor (Q144).

Fakes the TRANSPORT (httpx.AsyncClient.get/post), not the client, so the REAL
`HevyClient.create_routine` runs — the layer where the strip and the guard live.
A fake one layer above (FakeHevyClient) cannot see either, exactly the distinction
`test_hevy_create_response_tolerance` documents.

Gates:
  * `rpe` never reaches Hevy on a routine set (deterministic, not prompt-only).
  * A same-(title, folder) create raises RoutineAlreadyExists and never POSTs.
  * folder discriminates: same title in a different folder is NOT a collision.
  * `superset_id` reaches the payload grouped; a falsy `0` is a real group, not null.
  * The REST lane maps the collision to 409 (mirrors create_entry).
  * The #285 full-render reads a grouped superset back as `[superset N]`.
"""
import asyncio

import httpx
import pytest

import models
from connectors.hevy import HevyClient, RoutineAlreadyExists
from encryption import encrypt


def _run(coro):
    return asyncio.run(coro)


def _patch_transport(monkeypatch, existing_routines, post_status=201):
    """Fake GET /routines (the guard's read) and POST /routines (the create)."""
    sent = {"posts": [], "gets": []}

    async def fake_get(self, url, params=None, **kw):
        sent["gets"].append({"url": url, "params": params})
        return httpx.Response(
            200, request=httpx.Request("GET", url),
            json={"routines": existing_routines, "page": 1, "page_count": 1},
        )

    async def fake_post(self, url, json=None, content=None, **kw):
        # The connector serializes with allow_nan=False and posts via `content=` (bytes),
        # not `json=`; accept either so the capture survives that change.
        import json as _json
        payload = json if json is not None else _json.loads(content)
        sent["posts"].append({"url": url, "json": payload})
        return httpx.Response(
            post_status, request=httpx.Request("POST", url),
            json={"routine": {"id": "new-routine"}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return sent


def _ex(template_id="0222DB42", sets=None, **extra):
    ex = {"exercise_template_id": template_id, "sets": sets or [{"type": "normal", "reps": 8}]}
    ex.update(extra)
    return ex


def _posted_exercises(sent):
    return sent["posts"][0]["json"]["routine"]["exercises"]


# --------------------------------------------------------------------------- #
# rpe strip — the deterministic floor.                                         #
# --------------------------------------------------------------------------- #

def test_rpe_stripped_from_every_routine_set(monkeypatch):
    sent = _patch_transport(monkeypatch, existing_routines=[])
    _run(HevyClient("k").create_routine(
        title="Push Day",
        exercises=[_ex(sets=[
            {"type": "normal", "weight_kg": 60, "reps": 8, "rpe": 8.5},
            {"type": "normal", "weight_kg": 60, "reps": 6, "rpe": 9},
        ])],
    ))
    assert len(sent["posts"]) == 1
    posted_sets = _posted_exercises(sent)[0]["sets"]
    assert all("rpe" not in s for s in posted_sets)        # THE gate
    # Positive control: legitimate fields survive the strip.
    assert posted_sets[0]["weight_kg"] == 60
    assert posted_sets[0]["reps"] == 8


# --------------------------------------------------------------------------- #
# Idempotency guard — refuse a (title, folder) duplicate before the POST.      #
# --------------------------------------------------------------------------- #

def test_same_title_same_folder_refuses_and_never_posts(monkeypatch):
    sent = _patch_transport(
        monkeypatch,
        existing_routines=[{"id": "r1", "title": "Push Day", "folder_id": None}],
    )
    with pytest.raises(RoutineAlreadyExists) as ei:
        _run(HevyClient("k").create_routine(title="Push Day", exercises=[_ex()]))
    assert sent["posts"] == []                              # nothing minted
    assert ei.value.code == "already_exists"
    assert ei.value.existing[0]["id"] == "r1"              # names the collision


def test_collision_is_case_insensitive(monkeypatch):
    sent = _patch_transport(
        monkeypatch,
        existing_routines=[{"id": "r1", "title": "push DAY", "folder_id": None}],
    )
    with pytest.raises(RoutineAlreadyExists):
        _run(HevyClient("k").create_routine(title="Push Day", exercises=[_ex()]))
    assert sent["posts"] == []


def test_same_title_different_folder_is_distinct(monkeypatch):
    """Luke's call: title+folder. A same title in a different folder is a distinct
    routine, so the create proceeds."""
    sent = _patch_transport(
        monkeypatch,
        existing_routines=[{"id": "r1", "title": "Push Day", "folder_id": 5}],
    )
    _run(HevyClient("k").create_routine(title="Push Day", exercises=[_ex()], folder_id=9))
    assert len(sent["posts"]) == 1                          # not a collision → created


def test_same_title_folder_none_vs_set_is_distinct(monkeypatch):
    sent = _patch_transport(
        monkeypatch,
        existing_routines=[{"id": "r1", "title": "Push Day", "folder_id": 5}],
    )
    _run(HevyClient("k").create_routine(title="Push Day", exercises=[_ex()], folder_id=None))
    assert len(sent["posts"]) == 1


def test_different_title_same_folder_is_distinct(monkeypatch):
    sent = _patch_transport(
        monkeypatch,
        existing_routines=[{"id": "r1", "title": "Pull Day", "folder_id": None}],
    )
    _run(HevyClient("k").create_routine(title="Push Day", exercises=[_ex()]))
    assert len(sent["posts"]) == 1


def test_no_existing_routines_creates(monkeypatch):
    sent = _patch_transport(monkeypatch, existing_routines=[])
    _run(HevyClient("k").create_routine(title="Push Day", exercises=[_ex()]))
    assert len(sent["posts"]) == 1


# --------------------------------------------------------------------------- #
# Supersets — grouped to the payload; falsy 0 is a real group, not null.       #
# --------------------------------------------------------------------------- #

def test_shared_superset_id_reaches_payload_grouped(monkeypatch):
    sent = _patch_transport(monkeypatch, existing_routines=[])
    _run(HevyClient("k").create_routine(
        title="Unilateral Day",
        exercises=[
            _ex("AAAA1111", superset_id=1),
            _ex("BBBB2222", superset_id=1),
            _ex("CCCC3333"),  # standalone
        ],
    ))
    posted = _posted_exercises(sent)
    assert posted[0]["superset_id"] == 1
    assert posted[1]["superset_id"] == 1
    assert posted[2]["superset_id"] is None                # omitted → standalone


def test_superset_id_zero_is_not_treated_as_null(monkeypatch):
    """A falsy `0` must survive as a real group id — the classic `x or None` bug."""
    sent = _patch_transport(monkeypatch, existing_routines=[])
    _run(HevyClient("k").create_routine(
        title="Group Zero",
        exercises=[_ex("AAAA1111", superset_id=0), _ex("BBBB2222", superset_id=0)],
    ))
    posted = _posted_exercises(sent)
    assert posted[0]["superset_id"] == 0                   # 0, not None
    assert posted[1]["superset_id"] == 0


def test_grouped_superset_reads_back_grouped(monkeypatch):
    """The #285 read surface renders a grouped write as `[superset N]` — the
    round-trip's read half, driven on the payload the connector builds."""
    import mcp_server

    sent = _patch_transport(monkeypatch, existing_routines=[])
    _run(HevyClient("k").create_routine(
        title="Unilateral Day",
        exercises=[_ex("AAAA1111", superset_id=0), _ex("BBBB2222", superset_id=0)],
    ))
    posted = _posted_exercises(sent)
    routine = {"title": "Unilateral Day", "id": "x", "exercises": posted}
    rendered = "\n".join(mcp_server._format_routine_full(routine, fallback={}))
    assert rendered.count("[superset 0]") == 2             # 0 is grouped, not dropped


# --------------------------------------------------------------------------- #
# REST lane — collision → 409 (mirrors create_entry).                          #
# --------------------------------------------------------------------------- #

def test_rest_create_routine_maps_collision_to_409(monkeypatch, db_session):
    from fastapi import HTTPException, status

    from routers.integrations import RoutineCreateIn, hevy_create_routine

    user = models.User(id=71, email="rest@test", hashed_password="x")
    db_session.add(user)
    db_session.add(models.UserIntegration(
        user_id=user.id, provider="hevy", api_key_encrypted=encrypt("fake-key")))
    db_session.commit()

    _patch_transport(
        monkeypatch,
        existing_routines=[{"id": "r1", "title": "Push Day", "folder_id": None}],
    )
    body = RoutineCreateIn(
        title="Push Day",
        exercises=[{"exercise_template_id": "0222DB42",
                    "sets": [{"type": "normal", "reps": 8}]}],
    )
    with pytest.raises(HTTPException) as ei:
        _run(hevy_create_routine(body, current_user=user, db=db_session))
    assert ei.value.status_code == status.HTTP_409_CONFLICT
