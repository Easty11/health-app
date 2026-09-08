"""Education-thread seed builder — increment 3 step 1 (#49 lock).

A lever node in the interpretation view is tappable; tapping opens a scoped, ephemeral
education thread. This module assembles the seed that scopes that thread, and NOTHING more:
the #49 lock is `marker + mechanism + why-surfaced + current_state`, so the seed carries
exactly those four things and no wider personal context (GUARD: no full-context sweep).

The seed is READ from the already-built producer payload (`build_foundation`), never
recomputed — the delta/gate that put the marker in "What Moved" and the per-member lever
effect are the producer's own fields (#49: "read from the producer, do not recompute").
Protocol context is `meta.protocol_context_snapshot`, which the producer already resolved
via a single `current_state(user_id, db, today=panel_date)` query dated to the panel (#43).

Tappability is structural, not cosmetic. A lever is a valid tap target only if ALL hold:
  * it is I1-cited — `_citable_lever(lever_key)` resolves (grade + grade_rationale +
    non-empty evidence_refs). An uncited/absent lever is NOT tappable.
  * the marker sits in a group that surfaces (`should_surface`) — a lever shown under a
    quiet group was never displayed.
  * the lever is in that group's `shared_levers` AND its `member_lever_effects` name this
    marker — i.e. the lever actually acts on the marker it was tapped under (the
    why-surfaced join).
Any miss returns a STRUCTURAL REFUSAL, never a bare thread (the endpoint maps it to a 4xx).
"""
from __future__ import annotations

from dataclasses import dataclass

from .producer import _citable_lever

# The locked top-level seed keys (#49). The `seed-is-scoped` eval asserts this EXACT set —
# adding a key here without amending the lock is the leak the eval exists to catch.
SEED_KEYS = frozenset({"lever_key", "marker", "mechanism", "why_surfaced", "protocol_context"})


@dataclass
class SeedResult:
    """A built seed, or a structural refusal. `ok` discriminates; the endpoint maps a
    refusal to a 4xx and NEVER opens a thread on one."""
    ok: bool
    seed: dict | None = None
    refusal: str | None = None


def _find_member(payload: dict, marker_canonical: str) -> tuple[dict | None, dict | None]:
    """The (group, member) the marker belongs to, or (None, None). A marker is claimed by
    exactly one group, so the first hit is definitive."""
    for group in payload.get("groups", []):
        for member in group.get("members", []):
            if member.get("marker_canonical") == marker_canonical:
                return group, member
    return None, None


def build_education_seed(payload: dict, lever_key: str, marker_canonical: str) -> SeedResult:
    """Assemble the #49-locked seed for a lever tapped under `marker_canonical`, from the
    built producer `payload`. Returns a `SeedResult` — a scoped seed, or a structural refusal.

    The seed is deliberately narrow: the tapped marker's identity, the lever's authored
    mechanism (I1 asset projection), the producer's own why-surfaced gates for THIS marker,
    and the declared-state snapshot dated to the panel. No other marker, no lab-value sweep,
    no general personal context ever enters it.
    """
    group, member = _find_member(payload, marker_canonical)
    if member is None:
        return SeedResult(False, refusal=f"marker {marker_canonical!r} is not in the interpretation")
    if not group.get("should_surface"):
        return SeedResult(False, refusal=f"marker {marker_canonical!r} sits in a group that did not surface")

    node = _citable_lever(lever_key)  # I1 gate — uncited/absent lever is not tappable
    if node is None:
        return SeedResult(False, refusal=f"lever {lever_key!r} is not I1-cited and cannot seed a thread")

    surfaced_keys = {sl["lever_key"] for sl in group.get("shared_levers", [])}
    if lever_key not in surfaced_keys:
        return SeedResult(False, refusal=f"lever {lever_key!r} was not surfaced under this marker's group")

    effect = next((e for e in member.get("member_lever_effects", []) if e["lever_key"] == lever_key), None)
    if effect is None:
        return SeedResult(False, refusal=f"lever {lever_key!r} does not act on marker {marker_canonical!r}")

    seed = {
        "lever_key": lever_key,
        # marker — identity only, no result value beyond the gates below (#49 lock)
        "marker": {
            "marker_canonical": marker_canonical,
            "display_name": member.get("display_name"),
        },
        # mechanism — the lever's authored physiology (I1 asset projection, explains the
        # LEVER, never this user's dose); citations are the evidence_refs behind it
        "mechanism": {
            "label": node["label"],
            "mechanism_summary": node["mechanism_summary"],
            "grade": node["grade"],
            "grade_rationale": node["grade_rationale"],
            "citations": list(node["evidence_refs"]),
        },
        # why-surfaced — the producer's own delta/gates for THIS marker that put it in
        # "What Moved", plus the per-member lever effect (the surfacing join). Read, not
        # recomputed. Scoped to this one marker.
        "why_surfaced": {
            "delta": member.get("delta"),
            "news_gate": member.get("news_gate"),
            "range_gate": member.get("range_gate"),
            "safety_gate": member.get("safety_gate"),
            "lever_effect": {
                "lever_key": lever_key,
                "direction": effect["direction"],
                "grade": effect["grade"],
            },
        },
        # protocol context — current_state (#43) dated to the panel, so the mechanism is
        # stack-aware. Declared factors only (key/type/phase/assumable/date) — no lab sweep.
        "protocol_context": payload.get("meta", {}).get("protocol_context_snapshot"),
    }
    assert set(seed) == SEED_KEYS  # the lock, enforced at construction
    return SeedResult(True, seed=seed)
