"""Narrate-after-write gate (Q143a / WS4, builds on #283's `WriteResult`).

The `/chat` reply is generated in ONE pass BEFORE any write executes, so a "saved" the
model writes into that prose precedes the outcome. These gates pin the close: an all-saved
turn keeps the prose and fires no second call; any failed write discards the prose and runs
a bounded pass-2; a deterministic footer is the floor under both.

The model is faked at the TRANSPORT layer (#166 companion rule) — `_CountingClient` mimics
the one attribute the pass touches, `client.messages.create(...).content[0].text`, and
records every call so the "+1 call on failure only" cost profile is assertable. What a real
model would write is not under test here; the WIRING (when pass-2 fires, what context it is
given, what the deterministic floor says) is.
"""
from routers.chat import (
    WriteResult,
    _compose_response,
    _narrate_after_write,
    _pass2_user_content,
    _render_write_footer,
    _write_affordance,
    _PASS2_FALLBACK,
    _PASS2_SYSTEM,
)


class _Resp:
    def __init__(self, text):
        self.content = [type("Block", (), {"text": text})()]


class _CountingClient:
    """Fake Anthropic client. Records each `create` call; returns `fn(system, messages)`
    (default a fixed truthful regen), or raises `raise_exc` to simulate a transport error."""

    def __init__(self, fn=None, raise_exc=None):
        self.messages = self
        self.calls = []
        self._fn = fn or (lambda system, messages: "Regenerated truthful reply.")
        self._raise = raise_exc

    def create(self, *, model, max_tokens, system, messages):
        self.calls.append(
            {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        )
        if self._raise is not None:
            raise self._raise
        return _Resp(self._fn(system, messages))


def _saved(key):
    return WriteResult(saved=True, reason_code="saved", reason=f"✓ Schedule entry saved: {key}", key=key)


def _clash(key):
    return WriteResult(
        saved=False, reason_code="day_time_clash",
        reason=f"✗ Schedule entry NOT saved: {key} — it lands on a day already held by: id 7", key=key,
    )


def _unknown_field(key):
    return WriteResult(
        saved=False, reason_code="unknown_field",
        reason=f"✗ Schedule entry NOT saved: {key} — unknown field 'active' inside value", key=key,
    )


def _compose(client, reply, write_results, *, actions=None, user_message="hi"):
    return _compose_response(
        client=client,
        model="claude-test",
        user_message=user_message,
        reply=reply,
        all_actions=actions if actions is not None else [r.reason for r in write_results],
        write_results=write_results,
    )


# ---------- GATE: all-saved turn — prose unchanged, no second call ----------

def test_all_saved_turn_keeps_prose_and_fires_no_second_call():
    client = _CountingClient()
    reply = "Great, your Tuesday physio is on the calendar and here's the week impact."
    results = [_saved("physio_2026_09"), _saved("gym_2026_09"), _saved("swim_2026_09")]

    out, second = _compose(client, reply, results)

    assert client.calls == [], "an all-saved turn must not fire a second LLM call"
    assert second is False
    # Conversational prose survives verbatim; only the footer is added (always-on fork).
    assert out.startswith(reply)
    assert out.endswith("✓ 3 saved")


def test_no_write_results_means_no_footer_and_no_call():
    client = _CountingClient()
    reply = "Here's your readiness read for today."
    out, second = _compose(client, reply, [], actions=[])
    assert client.calls == []
    assert second is False
    assert out == reply  # a non-write turn is entirely untouched


# ---------- GATE: single failure (day_time_clash) — regen fires, truth, resolve path ----------

def test_single_day_time_clash_regenerates_with_one_call_and_truthful_floor():
    client = _CountingClient()
    # The pre-write prose falsely claims the save — it must NOT survive.
    reply = "Done — I've saved your Thursday gym session."
    results = [_clash("gym_2026_09")]

    out, second = _compose(client, reply, results)

    assert len(client.calls) == 1, "a failed write must fire exactly one second call"
    assert second is True
    assert "I've saved your Thursday gym session." not in out, "false pre-write prose survived"
    assert out.endswith("⚠ 0 saved, 1 failed — day/time clash")

    # The pass-2 was handed the resolve affordance and the clash reason so a real model
    # can offer supersedes/distinct_from.
    sent = client.calls[0]["messages"][0]["content"]
    assert "user_resolvable" in sent
    assert "day_time_clash" in sent
    assert _PASS2_SYSTEM == client.calls[0]["system"]
    assert client.calls[0]["max_tokens"] == 1024


# ---------- GATE: mixed batch — per-item truth, no roll-up, conversational content preserved ----------

def test_mixed_batch_reports_per_item_not_a_rollup():
    client = _CountingClient()
    reply = "I've updated everything and here's what your training week now looks like."
    results = [
        _saved("physio_2026_09"), _saved("gym_2026_09"),
        _clash("swim_2026_09"), _unknown_field("rugby_2026_09"), _clash("run_2026_09"),
    ]

    out, second = _compose(client, reply, results)

    assert len(client.calls) == 1 and second is True
    # Footer: distinct reasons, real counts, no batch gloss.
    assert out.endswith("⚠ 2 saved, 3 failed — day/time clash, unknown field")

    sent = client.calls[0]["messages"][0]["content"]
    # One line per result — five keys named individually, never collapsed to a tally.
    for key in ("physio_2026_09", "gym_2026_09", "swim_2026_09", "rugby_2026_09", "run_2026_09"):
        assert f"key={key}" in sent
    # The turn's conversational content is handed to pass-2 to preserve.
    assert reply in sent


# ---------- GATE: bug-code — never tell the user to fix it ----------

def test_bug_code_is_a_system_issue_not_a_user_fix():
    assert _write_affordance("unknown_field") == "system_issue"
    assert _write_affordance("invalid_shape") == "system_issue"
    assert _write_affordance("invalid_json") == "system_issue"
    assert _write_affordance("error") == "system_issue"
    # The pass-2 system prompt forbids handing a bug code back to the user.
    assert "NEVER tell the user to fix" in _PASS2_SYSTEM

    client = _CountingClient()
    out, _ = _compose(client, "Saved your rugby change.", [_unknown_field("rugby_2026_09")])
    sent = client.calls[0]["messages"][0]["content"]
    assert "system_issue" in sent
    # The floor names the failure without any "fix your field/format" instruction.
    assert out.endswith("⚠ 0 saved, 1 failed — unknown field")


# ---------- GATE: origin replay — rugby retire (mis-nested `active`) + gym/swim writes ----------

def test_origin_replay_tells_the_truth():
    """The transcript scenario: a rugby retirement whose `active:false` was mis-nested inside
    `value` (refused → unknown_field), alongside two valid weekday writes that saved. The
    pre-write prose narrated the retirement as done; the composed response must not."""
    client = _CountingClient(
        fn=lambda system, messages: "I've set up your gym and swim days. I couldn't retire "
        "rugby though — that didn't record, I'll sort it out."
    )
    pre_write = (
        "You're all set — I've retired rugby and added your gym and swim sessions."
    )
    results = [
        _unknown_field("rugby_2026_09"),
        _saved("gym_2026_09"),
        _saved("swim_2026_09"),
    ]

    out, second = _compose(client, pre_write, results, user_message="I've stopped rugby; add gym Tue and swim Thu")

    assert second is True
    assert "I've retired rugby" not in out, "the false retirement claim survived the regen"
    assert out.endswith("⚠ 2 saved, 1 failed — unknown field")


# ---------- pass-2 transport error → deterministic floor, never the false draft ----------

def test_pass2_transport_error_falls_back_to_floor():
    client = _CountingClient(raise_exc=RuntimeError("network"))
    pre_write = "Done — I've saved all of that."
    results = [_clash("gym_2026_09")]

    out, second = _compose(client, pre_write, results)

    assert len(client.calls) == 1 and second is True
    assert "I've saved all of that." not in out, "false draft prose survived a pass-2 failure"
    assert _PASS2_FALLBACK in out
    assert out.endswith("⚠ 0 saved, 1 failed — day/time clash")


# ---------- footer unit coverage ----------

def test_footer_empty_when_no_writes():
    assert _render_write_footer([]) == ""


def test_footer_all_saved_counts_saves():
    assert _render_write_footer([_saved("a"), _saved("b"), _saved("c")]) == "✓ 3 saved"


def test_footer_mixed_dedupes_reason_phrases_in_first_seen_order():
    results = [_saved("a"), _clash("b"), _unknown_field("c"), _clash("d")]
    assert _render_write_footer(results) == "⚠ 1 saved, 3 failed — day/time clash, unknown field"


def test_footer_unknown_code_falls_back_to_the_raw_code():
    r = WriteResult(saved=False, reason_code="brand_new_code", reason="x", key="k")
    assert _render_write_footer([r]) == "⚠ 0 saved, 1 failed — brand_new_code"


def test_not_found_is_informational_not_a_bug_or_a_clash():
    assert _write_affordance("not_found") == "informational"
    r = WriteResult(saved=False, reason_code="not_found", reason="ℹ️ No active entry for key: k", key="k")
    # not_found is a failed write (nothing saved) so it still fires pass-2 and shows in the floor.
    client = _CountingClient()
    out, second = _compose(client, "Removed it.", [r])
    assert second is True
    assert out.endswith("⚠ 0 saved, 1 failed — no matching entry")


def test_pass2_user_content_carries_ask_draft_and_per_row_outcomes():
    content = _pass2_user_content(
        "stop rugby, add gym Tue",
        "You're retired from rugby and gym is added.",
        [_unknown_field("rugby"), _saved("gym")],
    )
    assert "stop rugby, add gym Tue" in content
    assert "You're retired from rugby and gym is added." in content
    assert "[NOT SAVED · system_issue] key=rugby (unknown_field)" in content
    assert "[SAVED · saved] key=gym (saved)" in content
