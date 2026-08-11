"""Deterministic serialiser — interpretation payload -> fragment-addressed base text.

Increment 2's foundation (DECISIONS_LOG #202). The output of `serialize()` is BOTH:

  * the ONLY thing the rephrase generator is ever shown (#202 clause 1 — it sees
    the templated assembly built from reviewed asset fragments and arithmetic over
    the user's data, nothing else), and
  * the fail-closed render (#202 clause 4 — when a rephrase is rejected by the
    validator, errors, or is unavailable, THIS text is what the view shows).

Because it is both, it is a pure function: same payload in -> byte-identical
fragments out. No model, no randomness, no I/O, no clock. Ordering is the payload's
own deterministic order (groups and members are already ordered by the producer).

Two fragment kinds, matching the #202 granularity dial:

  * GATE / VERDICT-ADJACENT -> `granularity="fragment"`. The composed "how this
    marker moved" sentence (arithmetic over the user's readings) and the
    gate-adjacent `stable_rationale` judgement. Order is preserved by construction
    so a rephrase cannot reorder a verdict into a different emphasis.
  * MECHANISM / EDUCATION -> `granularity="block"`. Reviewed asset prose that
    explains physiology and never characterises THIS user's result — the group
    frame (`axis_verdict.text`), each marker's `mechanism.text`, and each shared
    lever's summary. Emphasis here carries no prioritisation weight, so a whole-block
    rephrase is safe.

For the prose blocks the base text IS the reviewed asset string, verbatim — the
serialiser passes it through, it does not author. Only the movement fragment is
COMPOSED, and only from structured fields, so every numeral and entity it contains
is present in the payload by construction. That is what lets the validator (#202
clause 3) treat each fragment's own `text` as the exact allowed-input set.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Granularity constants — the #202 dial.
FRAGMENT = "fragment"  # gate/verdict-adjacent; order preserved
BLOCK = "block"        # mechanism/education prose; whole-block


@dataclass(frozen=True)
class Fragment:
    """One addressable unit of the base text.

    `addr`   — stable, unique, payload-derived address (e.g.
               "groups.hpg_axis.members.testosterone_total.movement"). Stable across
               runs so a presentation cache and the promotion gate can key on it.
    `text`   — the register-neutral base render. The generator's sole input for this
               unit AND the fail-closed fallback. The validator derives this unit's
               allowed numerals/entities from this string.
    `granularity` — FRAGMENT or BLOCK (the #202 dial).
    `censored` — True only on a movement fragment whose delta is censored (#205/#Q70:
               magnitude is not computable). The validator forbids a rephrase of a
               censored fragment from acquiring magnitude or direction language.
    """
    addr: str
    text: str
    granularity: str
    censored: bool = False
    kind: str = ""  # coarse tag for callers/tests: "header"|"frame"|"movement"|"mechanism"|"stable_rationale"|"lever"


# --------------------------------------------------------------------------- #
# Value / movement composition — the only COMPOSED (non-pass-through) text.
# Pure arithmetic and formatting over the payload's structured reading fields.
# --------------------------------------------------------------------------- #

def _num(x) -> str:
    """Render a number without trailing-zero noise, deterministically."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _reading_text(reading: dict | None) -> str | None:
    """A reading -> "op value unit" / a qualitative string, or None if absent."""
    if not reading:
        return None
    if reading.get("value_qualitative"):
        return str(reading["value_qualitative"])
    if reading.get("value_num") is None:
        return None
    op = reading.get("value_operator") or ""
    unit = reading.get("unit_canonical") or ""
    return f"{op}{_num(reading['value_num'])} {unit}".strip()


def _range_clause(row: dict) -> str | None:
    """Range status from range_gate + the lab flag. None when in range and unflagged."""
    rg = row.get("range_gate") or {}
    if not rg.get("is_out_of_range"):
        return None
    flag = (rg.get("flag") or "").upper()
    if flag.startswith("H"):
        return "above the reference range"
    if flag.startswith("L"):
        return "below the reference range"
    return "outside the reference range"


def _movement_text(row: dict) -> str:
    """The composed gate/verdict-adjacent sentence for one marker.

    Deterministic clinical base — terse by design; the rephrase pass is what makes
    it plain (go-live O2: "most people would need an interpreter"). Every numeral and
    entity here comes from the payload, so the fragment's own text is its allowed-set.
    """
    name = row.get("display_name") or row.get("marker_canonical") or "This marker"
    cur = _reading_text(row.get("current"))
    head = f"{name}: {cur}." if cur else f"{name}."

    clauses: list[str] = []
    delta = row.get("delta")
    if delta is None:
        clauses.append("first observation, no prior to compare")
    else:
        direction = delta.get("direction") or "flat"
        if delta.get("censored"):
            # #205/#Q70: magnitude is not computable on a censored comparison.
            if direction == "flat":
                clauses.append("no change in the censored bound")
            else:
                clauses.append(f"moved {direction}; magnitude not computable (censored value)")
        else:
            prior = _reading_text(row.get("prior"))
            absc, pct = delta.get("abs_change"), delta.get("pct_change")
            if direction == "flat" or absc is None:
                clauses.append("no change from prior" if prior is None
                               else f"unchanged from the prior {prior}")
            else:
                bits = f"{direction} {_num(abs(absc))}"
                if pct is not None:
                    bits += f" ({_num(abs(pct))}%)"
                if prior is not None:
                    bits += f" from the prior {prior}"
                clauses.append(bits)
            mag = delta.get("magnitude")
            if mag == "within_noise":
                clauses.append("within the meaningful-change threshold")
            elif mag == "meaningful":
                clauses.append("a meaningful change")
            if delta.get("crossed_ref") == "into_range":
                clauses.append("moved into range")
            elif delta.get("crossed_ref") == "out_of_range":
                clauses.append("moved out of range")

    rng = _range_clause(row)
    if rng:
        clauses.append(rng)
    elif row.get("delta") is not None and not (row.get("range_gate") or {}).get("is_out_of_range"):
        clauses.append("in range")

    if (row.get("safety_gate") or {}).get("status") == "in_band":
        clauses.append("in a safety-monitoring band")

    body = "; ".join(clauses)
    return f"{head} {body}." if body else head


# --------------------------------------------------------------------------- #
# The walk — deterministic, payload-ordered.
# --------------------------------------------------------------------------- #

def _member_fragments(base_addr: str, row: dict) -> list[Fragment]:
    """Movement (fragment) + mechanism (block) + stable_rationale (fragment) for one
    grouped member. Prose fields are passed through verbatim; absent ones are skipped
    so a missing string is visibly absent rather than an empty unit."""
    out = [Fragment(
        addr=f"{base_addr}.movement",
        text=_movement_text(row),
        granularity=FRAGMENT,
        censored=bool((row.get("delta") or {}).get("censored")),
        kind="movement",
    )]
    mech = row.get("mechanism")
    if mech and mech.get("text"):
        out.append(Fragment(f"{base_addr}.mechanism", mech["text"], BLOCK, kind="mechanism"))
    sr = row.get("stable_rationale")
    if sr:
        out.append(Fragment(f"{base_addr}.stable_rationale", str(sr), FRAGMENT, kind="stable_rationale"))
    return out


def _lever_text(lever: dict) -> str:
    """A shared lever -> one education sentence. Pass-through of the reviewed label
    and mechanism summary; grade is evidence strength, not urgency."""
    label = lever.get("label") or lever.get("lever_key") or "Lever"
    summary = (lever.get("mechanism_summary") or "").strip()
    grade = lever.get("grade")
    tail = f" (evidence grade {grade})" if grade else ""
    return f"{label}: {summary}{tail}".strip()


def serialize(payload: dict) -> list[Fragment]:
    """interpretation payload -> ordered fragments. Pure and deterministic."""
    frags: list[Fragment] = []

    meta = payload.get("meta") or {}
    trig = meta.get("trigger_panel") or {}
    cmp_ = meta.get("compared_against")
    if trig.get("collected"):
        if cmp_ and cmp_.get("collected"):
            head = (f"Results from the {trig['collected']} draw, "
                    f"compared against the {cmp_['collected']} draw.")
        else:
            head = f"Results from the {trig['collected']} draw (first draw on record)."
        frags.append(Fragment("meta.header", head, FRAGMENT, kind="header"))

    for group in payload.get("groups") or []:
        gk = group.get("group_key") or "group"
        gbase = f"groups.{gk}"
        av = group.get("axis_verdict")
        if av and av.get("text"):
            frags.append(Fragment(f"{gbase}.frame", av["text"], BLOCK, kind="frame"))
        for member in group.get("members") or []:
            mk = member.get("marker_canonical") or "marker"
            frags.extend(_member_fragments(f"{gbase}.members.{mk}", member))
        for lever in group.get("shared_levers") or []:
            lk = lever.get("lever_key") or "lever"
            frags.append(Fragment(f"{gbase}.levers.{lk}", _lever_text(lever), FRAGMENT, kind="lever"))

    for row in payload.get("ungrouped") or []:
        mk = row.get("marker_canonical") or "marker"
        # Ungrouped rows carry no mechanism/stable_rationale (#203) — movement only.
        frags.append(Fragment(
            addr=f"ungrouped.{mk}.movement",
            text=_movement_text(row),
            granularity=FRAGMENT,
            censored=bool((row.get("delta") or {}).get("censored")),
            kind="movement",
        ))

    return frags


def render_base_text(fragments: list[Fragment]) -> str:
    """The fail-closed full render — fragments joined in order. This is what the view
    shows when the plain register is off or every rephrase failed (#202 clause 4)."""
    return "\n\n".join(f.text for f in fragments)
