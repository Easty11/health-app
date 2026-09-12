"""Routine-create numeric floor + folder name→id resolution (Q144 follow-up).

Concern A of the arc: the `Expected number, received nan` 400. Root cause (verified,
NOT the chat's folder guess): `json.loads` accepts a literal `NaN` token, the builder
passed it through (`NaN is not None`), and httpx serialized it (`allow_nan=True`) to the
wire. The fix is a deterministic numeric floor — no non-number reaches a numeric field —
plus folder name→id resolution (the `folder` name was silently dropped before).

Connector tests fake the TRANSPORT and drive the real HevyClient (the layer the floor
lives in). The numeric floor runs BEFORE any network call, so a bad value raises without
a GET/POST.
"""
import asyncio

import httpx
import pytest

import models
from connectors.hevy import HevyClient, RoutineNumericError, _is_finite_number
from encryption import encrypt


def _run(coro):
    return asyncio.run(coro)


def _patch_transport(monkeypatch, routines=None, folders=None):
    sent = {"gets": [], "posts": []}

    async def fake_get(self, url, params=None, **kw):
        sent["gets"].append(url)
        if "routine_folders" in url:
            return httpx.Response(200, request=httpx.Request("GET", url),
                                  json={"routine_folders": folders or [], "page_count": 1})
        return httpx.Response(200, request=httpx.Request("GET", url),
                              json={"routines": routines or [], "page_count": 1})

    async def fake_post(self, url, content=None, **kw):
        sent["posts"].append({"url": url, "content": content})
        return httpx.Response(201, request=httpx.Request("POST", url), json={"routine": {"id": "x"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return sent


def _ex(sets, template_id="AAAA1111", **extra):
    e = {"exercise_template_id": template_id, "sets": sets}
    e.update(extra)
    return e


# --------------------------------------------------------------------------- #
# Numeric floor — no non-number reaches a numeric field, caught before the POST #
# --------------------------------------------------------------------------- #

def test_nan_weight_raises_named_before_any_network_call(monkeypatch):
    sent = _patch_transport(monkeypatch)
    with pytest.raises(RoutineNumericError) as ei:
        _run(HevyClient("k").create_routine(
            title="MON",
            exercises=[_ex([{"type": "normal", "reps": 8, "weight_kg": float("nan")}])],
        ))
    msg = str(ei.value)
    assert "weight_kg" in msg and "set 1" in msg and "AAAA1111" in msg   # named
    assert ei.value.code == "invalid_number"
    assert sent["gets"] == [] and sent["posts"] == []                    # nothing sent


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan"), "60", True])
def test_any_nonnumber_in_a_numeric_field_raises(monkeypatch, bad):
    sent = _patch_transport(monkeypatch)
    with pytest.raises(RoutineNumericError):
        _run(HevyClient("k").create_routine(
            title="X", exercises=[_ex([{"type": "normal", "reps": 5, "weight_kg": bad}])]))
    assert sent["posts"] == []


def test_nan_rest_seconds_and_superset_id_raise(monkeypatch):
    _patch_transport(monkeypatch)
    with pytest.raises(RoutineNumericError):
        _run(HevyClient("k").create_routine(
            title="X", exercises=[_ex([{"type": "normal", "reps": 5}], rest_seconds=float("nan"))]))
    with pytest.raises(RoutineNumericError):
        _run(HevyClient("k").create_routine(
            title="X", exercises=[_ex([{"type": "normal", "reps": 5}], superset_id=float("inf"))]))


def test_finite_values_create_normally(monkeypatch):
    """Positive control: real finite numbers pass the floor and reach the wire."""
    sent = _patch_transport(monkeypatch)
    _run(HevyClient("k").create_routine(
        title="X", exercises=[_ex([{"type": "normal", "reps": 8, "weight_kg": 60.0}])]))
    assert len(sent["posts"]) == 1
    assert b"NaN" not in sent["posts"][0]["content"]                     # no NaN token on the wire


def test_zero_is_a_valid_finite_number(monkeypatch):
    """0 is finite — the floor must not reject it (distinct from the omit-weight-not-zero
    prompt guidance; 0 is a real load)."""
    _patch_transport(monkeypatch)
    _run(HevyClient("k").create_routine(
        title="X", exercises=[_ex([{"type": "normal", "reps": 5, "weight_kg": 0}])]))


def test_is_finite_number_helper():
    assert _is_finite_number(0) and _is_finite_number(60.5) and _is_finite_number(-5)
    assert not _is_finite_number(float("nan"))
    assert not _is_finite_number(float("inf"))
    assert not _is_finite_number(True)          # bool excluded
    assert not _is_finite_number("60")          # string excluded
    assert not _is_finite_number(None)


# --------------------------------------------------------------------------- #
# Folder list endpoint                                                          #
# --------------------------------------------------------------------------- #

def test_get_routine_folders_tolerates_envelope_and_bare_list(monkeypatch):
    _patch_transport(monkeypatch, folders=[{"id": 5, "title": "Decompression"}])
    out = _run(HevyClient("k").get_routine_folders())
    assert out == [{"id": 5, "title": "Decompression"}]

    # Bare-list shape (defensive tolerance).
    async def fake_get_bare(self, url, params=None, **kw):
        return httpx.Response(200, request=httpx.Request("GET", url),
                              json=[{"id": 9, "title": "Other"}])
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get_bare)
    out2 = _run(HevyClient("k").get_routine_folders())
    assert out2 == [{"id": 9, "title": "Other"}]


# --------------------------------------------------------------------------- #
# Chat lane — folder resolution + numeric error folded to WriteResult          #
# --------------------------------------------------------------------------- #

from routers import chat as chat_mod  # noqa: E402


class _FakeClient:
    def __init__(self, folders=None, raise_exc=None):
        self._folders = folders or []
        self._raise = raise_exc
        self.calls = []

    async def get_routine_folders(self):
        return self._folders

    async def create_routine(self, title, exercises, folder_id=None):
        self.calls.append({"title": title, "folder_id": folder_id})
        if self._raise is not None:
            raise self._raise
        return {"routine": {"id": "fake"}}


def _routine_block(inner):
    return ("Sure!\n<hevy_create_routine>\n" + inner + "\n</hevy_create_routine>")


def test_chat_folder_name_resolves_to_id(db_session):
    client = _FakeClient(folders=[{"id": 5, "title": "2026 Post Season Decompression"}])
    block = _routine_block(
        '{"title":"MON","folder":"2026 post season decompression",'
        '"exercises":[{"exercise_template_id":"AAAA1111","sets":[{"type":"normal","reps":8}]}]}')
    _cleaned, _actions, wr = asyncio.run(
        chat_mod._process_routine_actions(block, client, 1, db_session))
    assert client.calls[0]["folder_id"] == 5          # name → id, case-insensitive
    assert wr[0].reason_code == "created"


def test_chat_folder_miss_creates_unfoldered(db_session):
    client = _FakeClient(folders=[{"id": 5, "title": "Some Other Folder"}])
    block = _routine_block(
        '{"title":"MON","folder":"2026 Post Season Decompression",'
        '"exercises":[{"exercise_template_id":"AAAA1111","sets":[{"type":"normal","reps":8}]}]}')
    _cleaned, actions, wr = asyncio.run(
        chat_mod._process_routine_actions(block, client, 1, db_session))
    assert client.calls[0]["folder_id"] is None        # unfoldered, never NaN
    assert wr[0].saved is True                          # routine DID create — no retry
    assert wr[0].reason_code == "created_unfoldered"
    assert "not found" in wr[0].reason


def test_chat_numeric_error_is_invalid_number(db_session):
    client = _FakeClient(raise_exc=RoutineNumericError(
        "weight_kg on set 1 of exercise 1 (AAAA1111) is not a valid number (nan)"))
    block = _routine_block(
        '{"title":"MON","exercises":[{"exercise_template_id":"AAAA1111",'
        '"sets":[{"type":"normal","reps":8}]}]}')
    _cleaned, _actions, wr = asyncio.run(
        chat_mod._process_routine_actions(block, client, 1, db_session))
    assert wr[0].saved is False and wr[0].reason_code == "invalid_number"
    assert chat_mod._write_affordance("invalid_number") == "system_issue"


def test_wed_directly_supplied_corrupted_id_is_create_failed_not_unresolved(db_session):
    """VERIFY-don't-patch (WED): a directly-supplied (typo'd) exercise_template_id has an
    id, so _resolve_missing_ids skips it (that resolver only fills TITLE-only entries) —
    it reaches Hevy and fails as `create_failed`, NOT `unresolved_exercise`. This pins the
    honest current behaviour: the corrupted id is surfaced as a failure (never silent, never
    a duplicate), just via the Hevy-rejection path. See OPEN_QUESTIONS finding."""
    client = _FakeClient(raise_exc=RuntimeError("Hevy API error 400: unknown exercise_template_id"))
    corrupted = "b4bab549-a143-4166-9615-249185e5a4a2"   # two digits off the intended id
    block = _routine_block(
        '{"title":"WED","exercises":[{"exercise_template_id":"' + corrupted + '",'
        '"sets":[{"type":"normal","reps":8}]}]}')
    _cleaned, _actions, wr = asyncio.run(
        chat_mod._process_routine_actions(block, client, 1, db_session))
    assert wr[0].saved is False
    assert wr[0].reason_code == "create_failed"          # NOT unresolved_exercise (documented)


# --------------------------------------------------------------------------- #
# REST lane — numeric error → 422                                              #
# --------------------------------------------------------------------------- #

def test_rest_create_routine_nan_maps_to_422(monkeypatch, db_session):
    from fastapi import HTTPException, status
    from routers.integrations import RoutineCreateIn, hevy_create_routine

    user = models.User(id=72, email="nan@test", hashed_password="x")
    db_session.add(user)
    db_session.add(models.UserIntegration(
        user_id=user.id, provider="hevy", api_key_encrypted=encrypt("fake-key")))
    db_session.commit()
    _patch_transport(monkeypatch)

    body = RoutineCreateIn(
        title="MON",
        exercises=[{"exercise_template_id": "0222DB42",
                    "sets": [{"type": "normal", "reps": 8, "weight_kg": float("nan")}]}],
    )
    with pytest.raises(HTTPException) as ei:
        _run(hevy_create_routine(body, current_user=user, db=db_session))
    assert ei.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
