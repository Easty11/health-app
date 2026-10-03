"""Chat context must survive a Hevy exercise whose `notes` is JSON null.

Prod, 3 Oct 2026: every POST /chat returned 500 (`AttributeError: 'NoneType' object has no
attribute 'strip'`, `context_builder.render_workout`) because the ten most recent workouts are
fetched live from Hevy and one exercise carried `"notes": null`. `ex.get("notes", "")` returns
the default only when the KEY is absent, so a present-but-null value went on to `.strip()`.

Every existing fixture wrote `"notes": ""`, which Hevy does not send for an exercise with no note
(FEEDBACK §48: the failures live in the state the author did not type). These tests use the shape
Hevy actually sends, and one fakes Hevy at the TRANSPORT layer so the real client parses the real
JSON (`null` -> None) before the real renderer sees it (#166 companion rule).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

import connectors.hevy as hevy_connector
from connectors.hevy import HevyClient
from context_builder import _section_hevy, render_workout

NOW = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)


def _workout(notes_values):
    return {
        "title": "Back-Safe Full Body",
        "description": None,
        "start_time": "2026-10-02T07:40:00+00:00",
        "end_time": "2026-10-02T09:59:00+00:00",
        "exercises": [
            {
                "index": i,
                "title": f"Exercise {i}",
                "exercise_template_id": f"TPL{i}",
                "superset_id": None,
                "notes": notes,
                "sets": [{"index": 0, "type": "normal", "weight_kg": 40, "reps": 8,
                          "rpe": None, "custom_metric": None}],
            }
            for i, notes in enumerate(notes_values)
        ],
    }


def _exercise_lines(lines):
    """The numbered exercise header lines ('   1. Title [ID: ...] ...'), in order."""
    return [ln for ln in lines if ln.lstrip()[:1].isdigit() and ". " in ln[:8]]


def test_null_exercise_notes_render_without_a_note():
    lines = render_workout(_workout([None]), NOW)
    (header,) = _exercise_lines(lines)
    assert "Exercise 0" in header
    # The line ends at the catalogue marker: no dangling " — " note separator, no literal "None".
    assert header.endswith("may not resolve]")
    assert "None" not in "\n".join(lines)


def test_absent_blank_and_real_notes_still_render_as_before():
    # Null, absent key, empty string, whitespace-only, and a real note in one workout.
    w = _workout([None, None, "", "   ", "Left side felt tight"])
    del w["exercises"][1]["notes"]                    # key absent entirely
    headers = _exercise_lines(render_workout(w, NOW))
    assert len(headers) == 5
    for h in headers[:4]:
        assert h.endswith("may not resolve]"), h      # no note appended for any of the four
    assert headers[4].endswith("— Left side felt tight")


def test_null_notes_through_the_real_client_and_section(monkeypatch):
    """Hevy faked at the transport: raw JSON with `null` -> HevyClient -> _section_hevy."""
    payload = {"page": 1, "page_count": 1,
               "workouts": [_workout([None, "Brace", None])]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/workouts")
        return httpx.Response(200, content=json.dumps(payload),
                              headers={"content-type": "application/json"})

    real_client = httpx.AsyncClient

    def faked_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(hevy_connector.httpx, "AsyncClient", faked_client)

    import asyncio
    data = asyncio.run(HevyClient("test-key").get_workouts())
    assert data["workouts"][0]["exercises"][0]["notes"] is None   # the shape under test

    section = _section_hevy(1, data["workouts"], NOW)
    assert "Back-Safe Full Body" in section
    assert "Exercise 0" in section and "Exercise 2" in section
    assert "— Brace" in section
