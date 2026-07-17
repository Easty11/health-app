"""Foundation producer (4a) — the group-primary skeleton with 4a fields only.

build_foundation(user_id, db, trigger_panel, prior_panel) -> {meta, groups[], ungrouped[]}

Consumes ONLY:
  * newest+prior per marker (labs_reads.marker_series)
  * marker_groups.json (membership, roles, group display names)
  * lever_dictionary.marker_interpretation[*].min_meaningful_delta + _defaults
    (via gates.min_meaningful_delta — never levers[])

Emits NONE of: axis_verdict, relations_rendered, shared_levers,
member_lever_effects, mechanism, stable_rationale, protocol_context_snapshot,
expected_by_phase, note. Those are 4b. The producer reads neither current_state
nor declared_state, and applies no relation-based news demotion (raw gate 1).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from reads.labs_reads import LabRow, MarkerPair, marker_series

from .gates import _LEVER_DICTIONARY
from .gates import delta as build_delta
from .gates import news_gate as build_news_gate
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
    return {
        "marker_canonical": pair.current.marker_canonical,
        "display_name": pair.current.marker_name_raw,  # provisional; polished names are 4b
        "is_derived": pair.current.is_derived,
        "current": _reading(pair.current),
        "prior": _reading(pair.prior),
        "delta": delta_obj,
        "news_gate": build_news_gate(delta_obj),
        "range_gate": build_range_gate(pair.current),
    }


def _member(pair: MarkerPair, role: str | None) -> dict:
    return {**_foundation_row(pair), "role": role}


def _is_moved(members: list[dict]) -> bool:
    """A group is moved iff ANY member is news (gate 1) OR out of range (gate 2).
    Producer-emitted so the frontend reads it, never derives it."""
    return any(m["news_gate"]["is_news"] or m["range_gate"]["is_out_of_range"] for m in members)


def _groups(series: dict[str, MarkerPair]) -> tuple[list[dict], set[str]]:
    """Authored groups from marker_groups.json, members restricted to markers
    present in this panel. A group with no present members is omitted (an empty
    shell carries nothing; an `insufficient_data` verdict is 4b). Returns the
    groups and the set of marker keys they claimed."""
    groups: list[dict] = []
    claimed: set[str] = set()

    for group_def in _MARKER_GROUPS["groups"]:
        members = []
        for member_def in group_def["members"]:
            key = member_def["marker_canonical"]
            claimed.add(key)
            pair = series.get(key)
            if pair is not None:
                members.append(_member(pair, member_def.get("role")))

        if not members:
            continue

        groups.append({
            "group_key": group_def["group_key"],
            "display_name": group_def["display_name"],
            "is_group_of_one": group_def.get("is_group_of_one", False),
            "members": members,
            "is_moved": _is_moved(members),
        })

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


def _meta(trigger_panel, prior_panel) -> dict:
    """The 4a meta subset. No protocol_context_snapshot — that carries phase (4b).
    first_ever_panel is derived from the absence of a prior panel (the caller
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
    }


def build_foundation(user_id: int, db: Session, trigger_panel, prior_panel) -> dict:
    """The 4a entry point. `trigger_panel` / `prior_panel` are the report rows
    the caller already resolved (LabReport, or None for prior); the producer
    reads panel identity off them and the marker series off the DB."""
    series = marker_series(user_id, db)
    groups, claimed = _groups(series)
    return {
        "meta": _meta(trigger_panel, prior_panel),
        "groups": groups,
        "ungrouped": _ungrouped(series, claimed),
    }
