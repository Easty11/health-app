"""Education-thread generator — increment 3 steps 2-3 (#47 boundary).

A scoped, ephemeral education thread, architecturally distinct from general chat
(`routers/chat.py`): no action processors, no general-context sweep, no persistent history.
It explains the tapped lever's mechanism in the user's stack context and DEFLECTS any
personalised-action question. Education, never prescription.

Two boundaries carry #47, prompt + guard (Fork B):
  * the system prompt (built here from the #49-locked seed) scopes the thread and forbids
    personalised action;
  * the output guard (`contains_directive`, the shared detector extracted from the rephrase
    validator) is the FAIL-CLOSED backstop: any directive/imperative in the model's text is
    replaced by a fixed deflection, never served. The prompt does the heavy lifting; the
    guard is the structural line, because the boundary is regulatory and must not rest on
    prompt-trust alone.

The model client is INJECTED, never constructed here, so tests fake it at the transport
layer (#166 companion rule). With no client, or on any transport error, the thread fails
closed to the lever's authored `mechanism_summary` — deterministic education, always safe.

LIMITATION (recorded, not fixed): the directive guard was built for a single deterministic
fragment; over a free-form multi-turn thread it is a fail-closed backstop, not a complete
guarantee. Prompt scope + short, mechanism-only answers carry most of the boundary — same
posture as rephrase, looser surface.
"""
from __future__ import annotations

import json

from .rephrase_validator import contains_directive

MODEL = "claude-sonnet-4-6"  # matches routers/chat.py and rephrase.py
_MAX_TOKENS = 512  # short, mechanism-only answers keep the boundary tight

# The fixed deflection served whenever the model's output trips the directive guard, or an
# input asks for personalised action the prompt should already have deflected. Declarative
# throughout (no imperative verb) so the deflection itself never trips the guard it backs.
_DEFLECTION_TEMPLATE = (
    "This is education, not personal advice, so I can't tell you what to do here. "
    "The mechanism is: {mechanism_summary} "
    "Any dosing or action decision belongs with your prescriber."
)

_SYSTEM_FRAME = (
    "You explain the physiological MECHANISM of one health-protocol lever to a layperson. "
    "You are a scoped education surface, NOT a clinician and NOT a general assistant. Follow "
    "these rules exactly:\n"
    "- Explain only the mechanism of the lever named in the seed, and only as it bears on the "
    "one marker in the seed, in the user's declared stack context. Do not roam to other "
    "markers, other levers, or general topics.\n"
    "- Education only. Never tell the user to do anything: no advice, no instructions, no "
    "dosing, no recommendations, no 'you should', no 'consider', no urgency or ranking. "
    "Explaining a mechanism in the user's stack context must never tip into telling them to "
    "change their stack.\n"
    "- If the user asks what to do, what dose to take, whether to change anything, or any "
    "personalised-action question, DEFLECT: say this is education not personal advice and that "
    "dosing/action decisions belong with their prescriber. Do not answer the action question.\n"
    "- Keep answers short and mechanism-only. Do not invent numbers, results, or citations "
    "beyond the seed.\n"
    "Answer in plain language, describing how the mechanism works — never what the reader "
    "should do about it."
)


def render_system_prompt(seed: dict) -> str:
    """The education-only system prompt: the frame + the #49-locked seed as constrained
    context. The seed is the ONLY context the thread gets — no general personal sweep."""
    return _SYSTEM_FRAME + "\n\nSCOPED SEED (the only context for this thread):\n" + json.dumps(
        seed, ensure_ascii=False, indent=2, default=str
    )


def _deflection(seed: dict) -> str:
    return _DEFLECTION_TEMPLATE.format(
        mechanism_summary=seed["mechanism"]["mechanism_summary"]
    )


def _call_model(client, system: str, messages: list[dict], model: str) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=system,
        messages=messages,
    )
    return resp.content[0].text.strip()


def answer_education(seed: dict, messages: list[dict], *, client, model: str = MODEL) -> dict:
    """Answer one turn of the education thread. Stateless (Fork A): `messages` is the full
    client-held turn history, re-sent each call — nothing is persisted server-side, so the
    thread structurally cannot leak into general chat history (gate 2).

    Returns `{text, source, deflected}`:
      * `source="template"` — deterministic authored mechanism (no client, or transport
        error): fail-closed education.
      * `source="deflection"` — the model tripped the directive guard; the fixed deflection
        is served, never the model's directive text (#47 fail-closed backstop).
      * `source="model"` — the model's mechanism explanation passed the guard.
    """
    if client is None:
        return {"text": seed["mechanism"]["mechanism_summary"], "source": "template", "deflected": False}
    system = render_system_prompt(seed)
    try:
        candidate = _call_model(client, system, messages, model)
    except Exception:
        # transport error -> deterministic authored mechanism (fail-closed education)
        return {"text": seed["mechanism"]["mechanism_summary"], "source": "template", "deflected": False}
    if not candidate or contains_directive(candidate):
        return {"text": _deflection(seed), "source": "deflection", "deflected": True}
    return {"text": candidate, "source": "model", "deflected": False}
