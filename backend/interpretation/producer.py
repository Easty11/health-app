"""Interpretation producer — group-primary, three-pass.

build_foundation(user_id, db, trigger_panel, prior_panel) -> {meta, groups[], ungrouped[]}

Three passes (4b-i restructure over 4a's single pass):
  Pass 1  per member  — delta, safety_gate, range_gate, raw news_gate (unchanged 4a).
  Pass 2  per group   — relations over the assembled member set, THEN should_surface.
  Pass 3  per group   — interpretive layer (verdict, levers — held for 4b-ii).

Consumes:
  * newest+prior per marker (labs_reads.marker_series)
  * marker_groups.json (membership, roles, display names, relations)
  * safety_thresholds.json (via gates.safety_gate - gate 3, level vs policy constant)
  * lever_dictionary.marker_interpretation[*].min_meaningful_delta + _defaults
    (via gates.min_meaningful_delta — never levers[])
  * current_state(...).declared_state — for meta.protocol_context_snapshot only,
    dated to the panel's draw (never date.today()).

Emits, over 4a: meta.protocol_context_snapshot, member relations_rendered[].
Still HELD for 4b-ii (demotion + interpretive half): axis_verdict, shared_levers,
member_lever_effects, mechanism, stable_rationale, expected_by_phase. No
relation-based news demotion — gate 1 is still raw.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from current_state import current_state
from reads.labs_reads import LabRow, MarkerPair, marker_series

from .gates import _LEVER_DICTIONARY
from .gates import delta as build_delta
from .gates import news_gate as build_news_gate
from .gates import safety_gate as build_safety_gate
from .gates import range_gate as build_range_gate

_MARKER_GROUPS_PATH = Path(__file__).resolve().parent.parent / "reference" / "marker_groups.json"

# The contract's regulatory posture for this deployment — a constant, not a
# derivation (no asset carries it, and 4a authors no policy).
_REGULATORY_MODE = "education"


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_MARKER_GROUPS = _load(_MARKER_GROUPS_PATH)


def _reading(row: LabRow | None) -> dict | None:
    """The contract's `current` / `prior` reading object. `flag` is lab_flag —
    the lab-asserted flag; computed_flag is withheld."""
    if row is None:
        return None
    reading = {
        "value_num": row.value_num,
        "value_operator": row.value_operator,
        "value_qualitative": row.value_qualitative,
        "unit_canonical": row.unit_canonical,
        "ref_low": row.ref_low,
        "ref_high": row.ref_high,
        "flag": row.lab_flag,
        "collected": row.collected_date.isoformat(),
    }
    return reading


def _foundation_row(pair: MarkerPair) -> dict:
    """The per-marker 4a fields, shared by grouped members and ungrouped rows."""
    delta_obj = build_delta(pair.current, pair.prior)
    safety_obj = build_safety_gate(pair.current, pair.prior)
    return {
        "marker_canonical": pair.current.marker_canonical,
        "display_name": pair.current.marker_name_raw,  # provisional; polished names are 4b
        "is_derived": pair.current.is_derived,
        "current": _reading(pair.current),
        "prior": _reading(pair.prior),
        "delta": delta_obj,
        "safety_gate": safety_obj,
        "news_gate": build_news_gate(delta_obj, safety_gate=safety_obj),
        "range_gate": build_range_gate(pair.current),
    }


def _member(pair: MarkerPair, role: str | None) -> dict:
    return {**_foundation_row(pair), "role": role}


def _should_surface(members: list[dict]) -> bool:
    """A group surfaces iff ANY member is news (gate 1) OR out of range (gate 2) OR
    sits in a safety band (gate 3). Producer-emitted so the frontend reads it, never
    derives it.

    Renamed from `_is_moved` at #106, and the emitted key with it. Once gate 3 feeds
    this predicate it is no longer testing movement: a persistently elevated value that
    has not moved at all must still surface, or it hides inside a quiet group -- the
    exact failure the safety gate exists to prevent. A key named `is_moved` that is true
    for something that did not move is the drift this repo punishes.
    """
    return any(
        m["news_gate"]["is_news"]
        or m["range_gate"]["is_out_of_range"]
        or m["safety_gate"]["status"] == "in_band"
        for m in members
    )


def _assemble_members(group_def: dict, series: dict[str, MarkerPair], claimed: set[str]) -> list[dict]:
    """Pass 1 — the group's present members, each a full foundation row (delta,
    safety_gate, range_gate, raw news_gate). Records every authored key in
    `claimed`, present or not, so `_ungrouped` never re-surfaces a claimed key.
    Identical per-member work to 4a; only lifted into its own pass so pass 2 has
    the assembled set to reason over."""
    members = []
    for member_def in group_def["members"]:
        key = member_def["marker_canonical"]
        claimed.add(key)
        pair = series.get(key)
        if pair is not None:
            members.append(_member(pair, member_def.get("role")))
    return members


def _relations_rendered(marker_key: str, group_def: dict, present: set[str]) -> list[dict]:
    """The relations authored on this group that render on `marker_key` and have
    at least one operand present in the panel.

    Author-group, present-marker (I7): a relation is authored once on the group
    and rendered on each member named in `render_on`. This NEVER fabricates a
    missing operand — a relation with no operand present is dropped entirely; one
    with some operands present degrades and NAMES what is missing, so the reader
    sees the relation is partial rather than being shown a confident reading built
    on absent data.

    `precondition_status`:
      * `not_applicable` for ratio / co_movement / discriminator / context.
      * `unresolvable` for feedback — the asset's `precondition_phase` (its
        on-TRT value) is not a value `derive_phase` can ever return, and no
        mapping exists in asset or code. That value is echoed straight off the
        asset via `rel.get("precondition_phase")`; it is never written as a
        literal in this module, so a grep for it over non-test source is empty —
        the mechanical proof that nothing here maps it. The raw phase is echoed,
        never guessed: a guessed mapping
        would silently decide whether LH/FSH suppression is expected or is news,
        which is the entire clinical content of that relation. See OPEN_QUESTIONS
        (precondition_phase vs derive_phase vocabulary). `expected_by_phase` is
        NOT emitted this increment; it depends on that resolution.
    """
    rendered = []
    for rel in group_def.get("relations", []):
        if marker_key not in rel.get("render_on", []):
            continue
        operands = rel.get("operands", [])
        missing = [op for op in operands if op not in present]
        if operands and len(missing) == len(operands):
            continue  # no operand present -> not rendered (never fabricate)

        entry = {
            "relation_key": rel["relation_key"],
            "kind": rel["kind"],
            "reads": rel["reads"],
            "operand_status": "degraded" if missing else "complete",
            "operands_missing": missing,
        }
        if rel["kind"] == "feedback":
            entry["precondition_status"] = "unresolvable"
            entry["precondition_phase"] = rel.get("precondition_phase")  # echoed raw, not mapped
        else:
            entry["precondition_status"] = "not_applicable"
        rendered.append(entry)
    return rendered


def _build_group(group_def: dict, members: list[dict], present: set[str]) -> dict:
    """Pass 2 (+ pass 3) — assemble the group over its already-built member set.
    Pass 2 authors `relations_rendered` on each member (over the whole assembled
    set + panel-present operands), THEN computes `should_surface`. The interpretive
    layer (verdict, levers — held for 4b-ii) is pass 3, after. `should_surface` is
    computed here, not in pass 1, precisely so the relation pass (and, in 4b-ii,
    relation-based demotion) can finalise each member's news_gate first. No
    demotion runs this increment, so the value is still identical to 4a's."""
    for member in members:  # pass 2: relations over the assembled set
        member["relations_rendered"] = _relations_rendered(member["marker_canonical"], group_def, present)
    return {
        "group_key": group_def["group_key"],
        "display_name": group_def["display_name"],
        "is_group_of_one": group_def.get("is_group_of_one", False),
        "members": members,
        "should_surface": _should_surface(members),
    }


def _groups(series: dict[str, MarkerPair]) -> tuple[list[dict], set[str]]:
    """Authored groups from marker_groups.json, members restricted to markers
    present in this panel. A group with no present members is omitted (an empty
    shell carries nothing; an `insufficient_data` verdict is 4b). Returns the
    groups and the set of marker keys they claimed.

    Three-pass, additive over 4a's single pass: pass 1 assembles member rows
    (`_assemble_members`), pass 2 builds the group over them (`_build_group`,
    where relations then `should_surface` land). The passes are separated so a
    relation needing the full member set can run between member assembly and
    surfacing — see #140 (three-pass restructure)."""
    groups: list[dict] = []
    claimed: set[str] = set()
    present = set(series)  # every marker in this panel — operands may reference non-members

    for group_def in _MARKER_GROUPS["groups"]:
        members = _assemble_members(group_def, series, claimed)  # pass 1
        if not members:
            continue
        groups.append(_build_group(group_def, members, present))  # pass 2 (+3)

    return groups, claimed


def _ungrouped(series: dict[str, MarkerPair], claimed: set[str]) -> list[dict]:
    """Every panel marker not in an authored group, emitted FLAT — a foundation
    row tagged ungrouped:true, no axis_verdict. 4a does NOT synthesise a
    group-of-one (that would author new marker_groups content, forbidden); nor
    does it pool stable+in-range ungrouped rows — pooling is a downstream render
    call. Rows are emitted flat, ordered by marker key for determinism."""
    rows = []
    for key in sorted(series):
        if key in claimed:
            continue
        rows.append({**_foundation_row(series[key]), "ungrouped": True})
    return rows


def _panel_ref(panel) -> dict | None:
    if panel is None:
        return None
    return {
        "panel_name_raw": panel.panel_name_raw,
        "collected": panel.collected_date.isoformat(),
    }


_SNAPSHOT_FIELDS = ("key", "type", "phase", "assumable_present", "relevant_date")


def _protocol_context_snapshot(user_id: int, db: Session, trigger_panel) -> dict | None:
    """meta.protocol_context_snapshot (4b) — the declared-state factors as-of the
    panel's collection date, projected to the fields that bear on interpretation.

    `as_of` is the trigger panel's `collected_date`, NEVER `date.today()`: the
    phase that interprets a panel is the phase at draw time. `derive_phase`
    consumes `as_of` in no rule today (deliberate, documented), so this is INERT
    now and correct the moment window logic lands. Passing `today` would be
    silently wrong later and invisible in every test.

    Each factor carries only `key`, `type`, `phase`, `assumable_present`,
    `relevant_date`. It omits `detail` (unbounded free text, not an interpretive
    input) and `active` — `declared_state.py` documents two incompatible senses
    of "active"; `phase` is the one that survives the distinction.

    Returns None only if the caller resolved no trigger panel (nothing to date
    against); the normal flow always supplies one."""
    if trigger_panel is None:
        return None
    as_of = trigger_panel.collected_date
    state = current_state(user_id, db, today=as_of)
    factors = [
        {field: factor[field] for field in _SNAPSHOT_FIELDS}
        for type_factors in state.declared_state.values()
        for factor in type_factors
    ]
    return {"as_of": as_of.isoformat(), "factors": factors}


def _meta(user_id: int, db: Session, trigger_panel, prior_panel) -> dict:
    """Meta. `protocol_context_snapshot` is 4b (carries phase) and is dated to the
    panel's draw, not the generation time — see `_protocol_context_snapshot`.
    `first_ever_panel` is derived from the absence of a prior panel (the caller
    supplies None when there is nothing to compare against)."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trigger_panel": _panel_ref(trigger_panel),
        "compared_against": _panel_ref(prior_panel),
        "first_ever_panel": prior_panel is None,
        "regulatory_mode": _REGULATORY_MODE,
        "lever_dictionary_version": _LEVER_DICTIONARY["_meta"]["version"],
        "marker_groups_version": _MARKER_GROUPS["_meta"]["version"],
        "overall_extraction_confidence": getattr(trigger_panel, "overall_confidence", None),
        "protocol_context_snapshot": _protocol_context_snapshot(user_id, db, trigger_panel),
    }


def build_foundation(user_id: int, db: Session, trigger_panel, prior_panel) -> dict:
    """The 4a entry point. `trigger_panel` / `prior_panel` are the report rows
    the caller already resolved (LabReport, or None for prior); the producer
    reads panel identity off them and the marker series off the DB."""
    series = marker_series(user_id, db)
    groups, claimed = _groups(series)
    return {
        "meta": _meta(user_id, db, trigger_panel, prior_panel),
        "groups": groups,
        "ungrouped": _ungrouped(series, claimed),
    }
