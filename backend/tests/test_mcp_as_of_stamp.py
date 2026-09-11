"""Every MCP tool output carries a visible `as_of` anchor (WS3 / #281).

An MCP thread can persist across calendar days. The data each tool returns is already
emit-time fresh (every query resolves `CURRENT_DATE` server-side per call), but nothing
told the client WHICH day that was, so a resumed thread could reason off a stale cached
"today". `_stamp` prepends a tz-aware Brisbane (no-DST) `as_of` line so the anchor is
visible and a re-run on a later day is legible as later.

These target the pure helpers `_as_of` / `_stamp` and the `_stamped` decorator — the
`@mcp.tool()` bodies need a live bearer token and a DB, which are not the anchoring logic
under test. Mirrors `test_mcp_training_load`'s formatter-level approach.
"""
import asyncio
from datetime import datetime, timezone

from mcp_server import _as_of, _stamp, _stamped


def test_stamp_prepends_a_brisbane_as_of_line():
    # 2026-09-11 03:00 UTC = 13:00 Australia/Brisbane (UTC+10, no DST).
    now = datetime(2026, 9, 11, 3, 0, 0, tzinfo=timezone.utc)
    out = _stamp("BODY", now)
    first = out.splitlines()[0]
    assert first == "as_of: 2026-09-11T13:00:00+10:00 (Australia/Brisbane)"
    assert out.endswith("BODY")


def test_a_later_call_returns_a_later_as_of():
    """The acceptance criterion: re-run on a later date returns a later `as_of`."""
    earlier = datetime(2026, 9, 11, 3, 0, 0, tzinfo=timezone.utc)
    later = datetime(2026, 9, 12, 3, 0, 0, tzinfo=timezone.utc)
    assert _as_of(earlier) < _as_of(later)
    assert _as_of(earlier).startswith("2026-09-11")
    assert _as_of(later).startswith("2026-09-12")


def test_a_utc_evening_instant_anchors_to_the_next_brisbane_day():
    """The exact skew WS3 exists to close: 15:00 UTC is already the next calendar day in
    Brisbane (01:00), so the stamp must read the later day, not the UTC one."""
    now = datetime(2026, 9, 11, 15, 0, 0, tzinfo=timezone.utc)
    assert _as_of(now).startswith("2026-09-12T01:00")


def test_stamped_decorator_wraps_a_sync_tool_output():
    @_stamped
    def tool() -> str:
        return "PAYLOAD"

    out = tool()
    assert out.splitlines()[0].startswith("as_of: ")
    assert out.endswith("PAYLOAD")


def test_stamped_decorator_wraps_an_async_tool_output():
    @_stamped
    async def tool() -> str:
        return "ASYNC-PAYLOAD"

    out = asyncio.new_event_loop().run_until_complete(tool())
    assert out.splitlines()[0].startswith("as_of: ")
    assert out.endswith("ASYNC-PAYLOAD")


def test_stamped_preserves_name_and_docstring_for_tool_introspection():
    """FastMCP builds the tool schema from the function it decorates; `functools.wraps`
    must keep the name and docstring the client sees."""
    @_stamped
    def get_something(days: int = 7) -> str:
        """A tool docstring the client should still see."""
        return "x"

    assert get_something.__name__ == "get_something"
    assert "A tool docstring" in get_something.__doc__
