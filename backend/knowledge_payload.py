"""Reading a knowledge-update payload the model wrote (pure: no session, no clock).

Prod, 1 Nov 2026: a Pocket EP knowledge update was refused with
`Extra data: line 1 column 3918 (char 3917)` -- `json.loads` handed ONE valid JSON value followed
by more content (a second object, or prose). The whole block was dropped, and the user was told to
mention it again. Two fixes live here:

  * `parse_knowledge_payload` -- the tolerant reader for the `<knowledge_update>` text block.
    It decodes values one after another with `JSONDecoder.raw_decode`, so concatenated objects are
    ALL read, and it strips code fences and leading/trailing prose. It is tolerant of FORMAT, never
    of CONTENT: every value it returns still goes through the same per-type validators, and text
    that begins like JSON but does not decode is returned as `error`, never skipped (a second
    object that is malformed must not vanish while the first one saves).
  * `RECORD_KNOWLEDGE_TOOL` -- the structured channel. Tool input arrives already parsed by the
    API as `{"updates": [..]}`, so a concatenation or trailing-prose failure cannot be produced on
    that path at all. The schema guarantees well-formed JSON and an array of objects; the per-type
    shapes stay with the server-side validators (`routers.knowledge`), which refuse with a message
    the bounded retry feeds back.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

RECORD_KNOWLEDGE_TOOL_NAME = "record_knowledge_updates"

RECORD_KNOWLEDGE_TOOL: dict[str, Any] = {
    "name": RECORD_KNOWLEDGE_TOOL_NAME,
    "description": (
        "Save new information about the user to their knowledge base. `updates` is an ARRAY: one "
        "object per update, each exactly the JSON object shape in your instructions (a legacy "
        "{category, content} note, or a typed {type, key, value, ...} entry; `active: false` at "
        "the top level of an object retires that key). Put several updates in ONE call as several "
        "items. Calling this REQUESTS the writes; the system performs them and reports each "
        "outcome."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "updates": {
                "type": "array",
                "minItems": 1,
                "description": "One object per knowledge update.",
                "items": {
                    "type": "object",
                    "description": "A single knowledge update, in the shape your instructions give.",
                    "properties": {
                        "type": {"type": "string"},
                        "key": {"type": "string"},
                        "value": {"type": "object"},
                        "active": {"type": "boolean"},
                        "expires_at": {"type": "string"},
                        "category": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    # Per-type fields live inside `value` and are validated server-side.
                    "additionalProperties": True,
                },
            },
        },
        "required": ["updates"],
    },
}


@dataclass
class ParsedPayload:
    """What `parse_knowledge_payload` found in one block.

    `values` -- every JSON value decoded, in order (an array is flattened one level, so a model
    that wrote `[{..},{..}]` is read the same as two objects).
    `trailing` -- prose after the last decoded value ('' when none); never acted on.
    `error` -- set when text that began like JSON did not decode, or when nothing decoded at all.
    The values before the error are still returned: they are intact writes.
    """

    values: list[Any] = field(default_factory=list)
    trailing: str = ""
    error: str | None = None


# A whole line that is only a code-fence marker (```, ```json ...).
_FENCE_LINE_RE = re.compile(r"(?m)^[ \t]*```[A-Za-z0-9_-]*[ \t]*$")
# An inline fence hugging the payload: "```json {..} ```".
_FENCE_EDGE_RE = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*|[ \t]*```\s*$")
# Where a payload can begin: an object, or an array of objects.
_START_RE = re.compile(r"\{|\[\s*\{")


def strip_code_fences(text: str) -> str:
    """Remove markdown code-fence markers, keeping what is inside them."""
    text = _FENCE_LINE_RE.sub("", text)
    return _FENCE_EDGE_RE.sub("", text).strip()


def _describe(exc: json.JSONDecodeError, text: str) -> str:
    return f"{exc.msg}: line {exc.lineno} column {exc.colno} (char {exc.pos} of {len(text)})"


def parse_knowledge_payload(raw: str) -> ParsedPayload:
    """Decode every JSON value in `raw`; see the module docstring for the contract."""
    text = strip_code_fences(raw or "")
    out = ParsedPayload()
    start = _START_RE.search(text)
    if start is None:
        out.error = "no JSON object found in the block"
        out.trailing = ""
        return out

    decoder = json.JSONDecoder()
    n = len(text)
    i = start.start()
    while i < n:
        try:
            value, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError as exc:
            out.error = _describe(exc, text)
            return out
        if isinstance(value, list):
            out.values.extend(value)
        else:
            out.values.append(value)
        i = end
        # Between values: whitespace, and at most one comma (`{..},{..}`).
        while i < n and text[i].isspace():
            i += 1
        if i < n and text[i] == ",":
            i += 1
            while i < n and text[i].isspace():
                i += 1
        # Another value only if it LOOKS like one; anything else is trailing prose.
        if i >= n or _START_RE.match(text, i) is None:
            break
    out.trailing = text[i:].strip()
    return out


def updates_from_tool_input(tool_input: Any) -> tuple[list[Any], str | None]:
    """The `updates` array from a `record_knowledge_updates` call, as (items, error).

    The API parses tool input, so the normal case is a dict holding a list. A model that passes
    `updates` as a JSON STRING (it happens) is read through the tolerant parser rather than
    refused; anything else is a loud error, never a silent no-op.
    """
    if not isinstance(tool_input, dict):
        return [], f"tool input was {type(tool_input).__name__}, not an object with `updates`"
    updates = tool_input.get("updates")
    if isinstance(updates, list):
        return list(updates), None
    if isinstance(updates, str):
        parsed = parse_knowledge_payload(updates)
        return parsed.values, parsed.error
    if updates is None:
        return [], "tool input had no `updates` array"
    return [], f"`updates` was {type(updates).__name__}, not an array"


def extract_tool_updates(content: Any) -> tuple[list[Any], list[str]]:
    """Every `record_knowledge_updates` call in a response's content blocks -> (items, errors).

    Duck-typed (`type` / `name` / `input`) so a transport-layer fake needs only those attributes.
    """
    items: list[Any] = []
    errors: list[str] = []
    for block in content or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != RECORD_KNOWLEDGE_TOOL_NAME:
            continue
        got, err = updates_from_tool_input(getattr(block, "input", None))
        items.extend(got)
        if err:
            errors.append(err)
    return items, errors


def render_updates_as_blocks(updates: list[Any]) -> str:
    """The updates as `<knowledge_update>` text, for replaying a tool-call draft to the model as
    an assistant turn (history is text-only; it never carries tool_use blocks)."""
    return "\n".join(f"<knowledge_update>{json.dumps(u)}</knowledge_update>" for u in updates)
