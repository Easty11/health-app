"""Laterality session-pairing rule (DECISIONS_LOG #74/#76; brief D-E).

The DATA mechanism behind D-E, separated from the load formula it will feed (the
transform is a later session — brief step 5). A unilateral movement is logged in
Hevy as two sided blocks under the same exercise template within one session, so
its system-level load double-counts. This module identifies that in-data
signature — "paired same-template blocks in one session" — so the transform can
halve it. It computes NO load; it only classifies block structure against the
template's laterality tag.

The rule, exactly per D-E, template tag governing (never note parsing):

  * unilateral + the template appears in >= 2 blocks in the session
        → PAIRED: one movement logged as two sides, halve at system level.
        Side-agnostic — backfill does not resolve which block is which limb.
  * unilateral + exactly one block
        → NOT paired. Both limbs were logged in one block (the "L 63.5/R 55"
        shape); block structure carries no double-count, and we do not parse the
        note to infer otherwise.
  * alternating (both limbs within a block by definition), OR bilateral
        → NOT paired, at any block count. Two bilateral blocks of the same
        movement are legitimate separate volume, not a laterality artefact.
  * untagged (laterality NULL) + >= 2 same-template blocks
        → INDETERMINATE, never silently paired OR unpaired. The transform must
        not guess laterality; these route to the coverage audit
        (`audit_laterality_coverage`) to be tagged. Fail-closed: an unknown tag
        is surfaced, not assumed.

Keyed on `exercise_template_id` (#79), never title.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


UNILATERAL = "unilateral"
BILATERAL = "bilateral"
ALTERNATING = "alternating"


@dataclass(frozen=True)
class SessionPairing:
    """The pairing classification for one session.

    `paired`        — template_id → the block indices (>=2) that are the two sides
                      of one unilateral movement; the transform halves these.
    `indeterminate` — template_id → block indices for an UNTAGGED template appearing
                      in >=2 blocks; cannot be decided until the template is tagged.
    """
    paired: dict[str, list[int]] = field(default_factory=dict)
    indeterminate: dict[str, list[int]] = field(default_factory=dict)


def detect_session_pairing(
    blocks: list[tuple[int, str]],
    laterality_by_template: dict[str, str | None],
) -> SessionPairing:
    """Classify one session's blocks under the D-E pairing rule.

    `blocks` is the session's (block_index, exercise_template_id) list — one entry
    per exercise block, in log order. `laterality_by_template` maps a template id to
    its tag (`unilateral`/`bilateral`/`alternating`) or None/absent when untagged.
    A missing key is treated as untagged (fail-closed), never as bilateral.

    Pure and deterministic: no I/O, no clock. Block indices in the output preserve
    input order.
    """
    by_template: dict[str, list[int]] = defaultdict(list)
    for block_index, template_id in blocks:
        by_template[template_id].append(block_index)

    paired: dict[str, list[int]] = {}
    indeterminate: dict[str, list[int]] = {}
    for template_id, block_indices in by_template.items():
        if len(block_indices) < 2:
            continue  # a single block is never a same-session pair
        tag = laterality_by_template.get(template_id)
        if tag == UNILATERAL:
            paired[template_id] = sorted(block_indices)
        elif tag is None:
            # Untagged with repeated blocks — the transform cannot decide. Surface it.
            indeterminate[template_id] = sorted(block_indices)
        # bilateral / alternating with repeated blocks → deliberately NOT paired.
    return SessionPairing(paired=paired, indeterminate=indeterminate)


def blocks_from_workout(raw_workout: dict) -> list[tuple[int, str]]:
    """(block_index, exercise_template_id) for each block of a raw Hevy workout, in
    log order. Blocks without a template id are skipped (#79 — nothing to key on)."""
    out: list[tuple[int, str]] = []
    for block_index, ex in enumerate(raw_workout.get("exercises", []) or []):
        tid = ex.get("exercise_template_id")
        if tid:
            out.append((block_index, tid))
    return out
