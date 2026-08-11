"""Rephrase generator — increment 2 step 2 (#202).

Turns the serialiser's base-text fragments into a plain-register presentation, one unit at
a time, gated by the mechanical validator. Structure enforced by construction:

  * #202 clause 1 — the generator is handed ONLY a fragment's own `text` (the templated
    assembly). It never sees the raw payload, the DB, or anything else.
  * #202 clause 3 — every candidate passes `validate_rephrase` before it is used.
  * #202 clause 4 — any rejection, model error, timeout, or missing key falls back to the
    fragment's template text. `generate_plain(..., client=None)` therefore returns exactly
    `render_base_text` — the missing-key path is the template, not an error.

The model client is INJECTED, never constructed here, so a test can fake it at the
transport layer (the #166 companion rule: code interpreting a third party's response is
tested against a faked transport).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .presentation import Fragment
from .rephrase_validator import validate_rephrase

MODEL = "claude-sonnet-4-6"  # matches routers/chat.py
_MAX_TOKENS = 1024
_REF = Path(__file__).resolve().parent.parent / "reference"

_SYSTEM = (
    "You rewrite one clinical sentence or short paragraph into plain, everyday language a "
    "layperson can read. Follow these rules exactly:\n"
    "- Keep every number, unit, date and marker name exactly as given; introduce none.\n"
    "- Keep the same meaning and the same in-range/out-of-range status; never soften or "
    "strengthen it.\n"
    "- No advice, instructions, urgency, ranking, or reassurance. Do not tell the reader to "
    "do anything, and do not say a result is normal, fine, or nothing to worry about.\n"
    "- If a change is described as not computable or censored, do not invent a magnitude or "
    "a direction.\n"
    "Return only the rewritten text, nothing else."
)


def build_known_entities() -> set[str]:
    """The domain vocabulary for the validator's entity check — distinctive words (>= 4
    letters) from every canonical marker name and every lever label. A rephrase that names
    a marker/lever absent from its source fragment is caught against this set."""
    words: set[str] = set()

    def add(text: str | None) -> None:
        for w in re.findall(r"[A-Za-z]{4,}", text or ""):
            words.add(w.lower())

    mc = json.loads((_REF / "marker_canonical.json").read_text(encoding="utf-8"))
    for entry in mc.get("entries", []):
        add(entry.get("marker_name_raw"))
        for tok in (entry.get("marker_canonical") or "").split("_"):
            if len(tok) >= 4:
                words.add(tok.lower())

    ld = json.loads((_REF / "lever_dictionary.json").read_text(encoding="utf-8"))
    for node in (ld.get("levers") or {}).values():
        add(node.get("label"))

    return words


_KNOWN_ENTITIES = build_known_entities()


def _call_model(client, fragment: Fragment, model: str) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM,
        messages=[{"role": "user", "content": fragment.text}],
    )
    return resp.content[0].text.strip()


def rephrase_fragment(fragment: Fragment, *, client, known_entities: set[str] | None = None,
                      model: str = MODEL) -> tuple[str, bool]:
    """Rephrase one unit. Returns (text, was_rephrased). Fails closed to the template text
    on a missing client, any transport error, or a validator rejection."""
    if client is None:
        return fragment.text, False
    known = _KNOWN_ENTITIES if known_entities is None else known_entities
    try:
        candidate = _call_model(client, fragment, model)
    except Exception:
        return fragment.text, False  # #202 clause 4: model error -> template
    result = validate_rephrase(
        fragment.text, candidate,
        censored=fragment.censored, flagged=fragment.flagged, known_entities=known,
    )
    if result.ok and candidate:
        return candidate, True
    return fragment.text, False


def generate_plain(fragments: list[Fragment], *, client, known_entities: set[str] | None = None,
                   model: str = MODEL) -> dict:
    """Assemble the plain-register presentation: rephrase every fragment (fragment-wise /
    whole-block), validate, fall back per unit, join in order.

    Returns {text, any_rephrased, per_fragment:[{addr, rephrased}]}. With client=None the
    result's text is byte-identical to `render_base_text(fragments)` — the fail-closed
    render — so the caller can detect "nothing was actually rephrased" and skip caching."""
    parts: list[str] = []
    per: list[dict] = []
    any_rephrased = False
    for f in fragments:
        text, was = rephrase_fragment(f, client=client, known_entities=known_entities, model=model)
        parts.append(text)
        per.append({"addr": f.addr, "rephrased": was})
        any_rephrased = any_rephrased or was
    return {"text": "\n\n".join(parts), "any_rephrased": any_rephrased, "per_fragment": per}
