"""HevyClient.get_all_workouts — the "See all" page-loop aggregator (DECISIONS_LOG #67).

Hevy caps /workouts pageSize at 10 (the connected Hevy MCP tool schema enforces
`pageSize maximum: 10`), so a single call can never return the full history. The
aggregator walks page 1..page_count and concatenates. Faked — no live Hevy call;
the loop drives a canned multi-page catalogue via a patched get_workouts.
"""
import asyncio

import pytest

from connectors.hevy import HevyClient


def _patch_pages(client, pages: dict):
    async def fake_get_workouts(page=1, page_size=10):
        assert page_size == 10  # /workouts ceiling — never request more per page
        return pages[page]
    client.get_workouts = fake_get_workouts


# ---------- concatenates every page in order ----------
def test_aggregates_all_pages_in_order():
    pages = {
        1: {"page": 1, "page_count": 3, "workouts": [{"id": "w1"}, {"id": "w2"}]},
        2: {"page": 2, "page_count": 3, "workouts": [{"id": "w3"}, {"id": "w4"}]},
        3: {"page": 3, "page_count": 3, "workouts": [{"id": "w5"}]},
    }
    client = HevyClient("fake-key")
    _patch_pages(client, pages)

    result = asyncio.run(client.get_all_workouts())

    assert [w["id"] for w in result["workouts"]] == ["w1", "w2", "w3", "w4", "w5"]
    assert result["page_count"] == 3


# ---------- single page (page_count == 1) makes exactly one call ----------
def test_single_page_makes_one_call():
    calls = {"n": 0}

    async def fake_get_workouts(page=1, page_size=10):
        calls["n"] += 1
        return {"page": 1, "page_count": 1, "workouts": [{"id": "only"}]}

    client = HevyClient("fake-key")
    client.get_workouts = fake_get_workouts

    result = asyncio.run(client.get_all_workouts())

    assert calls["n"] == 1
    assert [w["id"] for w in result["workouts"]] == ["only"]


# ---------- empty batch terminates even if page_count over-promises ----------
def test_empty_batch_terminates_loop():
    pages = {
        1: {"page": 1, "page_count": 5, "workouts": [{"id": "w1"}]},
        2: {"page": 2, "page_count": 5, "workouts": []},  # short/empty — stop here
    }
    client = HevyClient("fake-key")
    _patch_pages(client, pages)

    result = asyncio.run(client.get_all_workouts())

    # Never requests page 3+ despite page_count=5, because page 2 came back empty.
    assert [w["id"] for w in result["workouts"]] == ["w1"]


# ---------- no workouts at all -> empty list, no error ----------
def test_no_workouts_returns_empty():
    async def fake_get_workouts(page=1, page_size=10):
        return {"page": 1, "page_count": 1, "workouts": []}

    client = HevyClient("fake-key")
    client.get_workouts = fake_get_workouts

    result = asyncio.run(client.get_all_workouts())

    assert result["workouts"] == []
