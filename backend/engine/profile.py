"""
Fortification-target profile (spec §9) — load, serialise, upsert, and seed.

The profile is the structured object that replaces the hardcoded injury string in
context_builder. `probe_queue` is computed at request time (selection.py), never
stored, so it does not live on this object.

The seed encodes the first instance — Luke / back-resilience (spec §10) — which
exists to prove the engine generalises from a real profile rather than a
hardcoded one.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import models
from . import taxonomy


def get_profile(db: Session, user_id: int) -> models.FortificationProfile | None:
    return (
        db.query(models.FortificationProfile)
        .filter_by(user_id=user_id)
        .first()
    )


def profile_to_dict(p: models.FortificationProfile | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {
        "floor": p.floor,
        "ceiling": p.ceiling,
        "horizon": p.horizon,
        "horizon_date": str(p.horizon_date) if p.horizon_date else None,
        "primary_target": p.primary_target,
        "primary_target_note": p.primary_target_note,
        # Provenance-backfilled on READ only (#227): entries written before
        # provenance existed surface the legacy default rather than 422-ing, and
        # entries that carry a block are passed through VERBATIM — no summarising,
        # no computed "is stale" boolean. Presentation decides staleness, not the
        # store. The stored column is untouched; this builds new dicts.
        "live_signals": with_provenance(p.live_signals),
        "hard_stops": with_provenance(p.hard_stops),
        "vehicle_bias": p.vehicle_bias or [],
        # Returned VERBATIM, not normalised — the round-trip is byte-identical by
        # contract, and None stays None ("no template" is distinct from an empty one).
        "weekly_template": p.weekly_template,
        "probe_budget": p.probe_budget,
        "notes": p.notes,
    }


_UPSERTABLE = (
    "floor", "ceiling", "horizon", "horizon_date", "primary_target",
    "primary_target_note", "live_signals", "hard_stops", "vehicle_bias",
    "weekly_template", "probe_budget", "notes",
)


# --------------------------------------------------------------------------- #
# Assertion provenance on profile entries (DECISIONS_LOG #227/#228).           #
# --------------------------------------------------------------------------- #

# Who asserted an entry. Three tiers, not free text: "the user stated this" and
# "the engine inferred it from a probe response" are different facts with different
# weight, and they previously occupied the same JSON key by occupying none.
# Mirrors the `source` field `POST /engine/response` already carries one tier down.
ASSERTED_BY_VALUES = ("user", "engine", "clinician")

# Lists whose entries carry provenance. Both are JSON lists of free-form domain
# dicts, so provenance is added as KEYS INSIDE an entry — assertion and attribution
# stay atomic in one object, and no migration is needed.
_PROVENANCED_FIELDS = ("hard_stops", "live_signals")

# What an entry written before provenance existed reads as. `asserted_on` is None
# rather than a guessed date: nobody knows when those were asserted, and inventing
# a plausible timestamp is how unknown provenance stops looking unknown.
_LEGACY_ASSERTED_BY = "user"


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_assertions(entries: Any, field: str) -> Any:
    """Validate the provenance block on every entry of `hard_stops`/`live_signals`.

    Only the PROVENANCE keys are checked. The rest of an entry is a free-form domain
    dict — `hard_stops` carry `pattern`/`region_key`/`scope`/`side`/`reason`,
    `live_signals` carry `signal`/`branch_param`/`status`/`self_triage` — and
    rejecting unknown keys here would freeze shapes this brief has no business
    freezing. (Deliberately unlike `validate_weekly_template`, whose slots are a
    closed shape by design.)

    WRITES REQUIRE PROVENANCE; READS TOLERATE ITS ABSENCE. That asymmetry is the
    whole point: a legacy profile keeps working, but the next time anyone touches an
    entry they must say who asserted it and when. See `with_provenance` for the read
    half, and #227 for the consequence — a legacy entry round-tripped GET -> PUT must
    have its `asserted_on` filled in, because the read surfaces None and None is not
    a date.
    """
    if entries is None:
        return entries
    if not isinstance(entries, list):
        raise ValueError(f"{field} must be a list")

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{field}[{i}] must be an object")

        asserted_by = entry.get("asserted_by")
        if asserted_by is None:
            raise ValueError(
                f"{field}[{i}]: asserted_by is required — one of "
                f"{list(ASSERTED_BY_VALUES)}"
            )
        if asserted_by not in ASSERTED_BY_VALUES:
            raise ValueError(
                f"{field}[{i}].asserted_by: unknown value {asserted_by!r} — one of "
                f"{list(ASSERTED_BY_VALUES)}"
            )

        if "asserted_on" not in entry or entry["asserted_on"] is None:
            raise ValueError(
                f"{field}[{i}]: asserted_on is required (ISO YYYY-MM-DD). An entry "
                f"read back from a pre-provenance profile carries null here — state "
                f"the date it was asserted rather than re-sending null."
            )
        if _parse_iso_date(entry["asserted_on"]) is None:
            raise ValueError(
                f"{field}[{i}].asserted_on must be an ISO date (YYYY-MM-DD), got "
                f"{entry['asserted_on']!r}"
            )

        # `review_on` is OPTIONAL and may be null — null means standing until
        # retired. A date means ASK AGAIN, never expire (#228).
        review_on = entry.get("review_on")
        if review_on is not None and _parse_iso_date(review_on) is None:
            raise ValueError(
                f"{field}[{i}].review_on must be an ISO date (YYYY-MM-DD) or null, "
                f"got {review_on!r}"
            )

        basis = entry.get("basis")
        if basis is not None and not isinstance(basis, str):
            raise ValueError(f"{field}[{i}].basis must be a string or null")

    return entries


def with_provenance(entries: list | None) -> list:
    """Read-side backfill. Entries carrying provenance pass through UNCHANGED; an
    entry with no `asserted_by` gains the legacy default so an existing profile
    reads without error.

    Builds new dicts — the stored column is never mutated by a read.
    """
    out: list = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        if "asserted_by" in entry:
            out.append(entry)                     # verbatim — round-trip contract
            continue
        out.append({
            **entry,
            "asserted_by": _LEGACY_ASSERTED_BY,
            "asserted_on": None,
            "review_on": None,
        })
    return out


# --------------------------------------------------------------------------- #
# Weekly template — the capacity-quota microcycle (DECISIONS_LOG #221).        #
# --------------------------------------------------------------------------- #

# Bounds. `sessions_per_week` allows 0 (a declared-but-dormant slot, distinct from
# an absent one) and tops out at twice-daily. `minutes` is a session length, not a
# weekly total: below 5 nothing useful is dosed, above 180 it is not one session.
_MAX_SESSIONS_PER_WEEK = 14
_MIN_SLOT_MINUTES = 5
_MAX_SLOT_MINUTES = 180

_SLOT_FIELDS = ("capacity", "sessions_per_week", "minutes")


def _slot_int(slot: dict[str, Any], field: str, lo: int, hi: int, i: int) -> None:
    """Range-check one integer slot field. `bool` is rejected explicitly: it is an
    `int` subclass, so `True` would otherwise pass as `sessions_per_week=1`."""
    if field not in slot:
        raise ValueError(f"weekly_template.slots[{i}]: missing required field {field!r}")
    v = slot[field]
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(
            f"weekly_template.slots[{i}].{field} must be an integer, got {type(v).__name__}"
        )
    if not (lo <= v <= hi):
        raise ValueError(f"weekly_template.slots[{i}].{field} must be {lo}-{hi}, got {v}")


def validate_weekly_template(value: Any) -> dict[str, Any]:
    """Validate a weekly template, raising ValueError with a field-located message.

    Fail-closed on unknown capacity strings rather than storing them: the template
    is read by `select_next` to constrain a candidate set, and a capacity nothing
    matches would silently select nothing — a wrong-but-quiet programme rather than
    a loud refusal. Same reasoning as the `measure_key` registry (#161): declaring
    the set and validating at write is what stops a synonym pile forming.

    The value is returned UNCHANGED, never canonicalised. `PUT`-then-`GET` is
    byte-identical by contract, so a template written as "STABILITY" reads back as
    "STABILITY". Consumers resolve through `taxonomy.resolve_capacity`, which
    accepts either spelling — see Q105 for whether that stays the right trade.
    """
    if not isinstance(value, dict):
        raise ValueError("weekly_template must be an object with a 'slots' list")
    extra = sorted(set(value) - {"slots"})
    if extra:
        raise ValueError(f"weekly_template: unknown field(s) {extra}")
    slots = value.get("slots")
    if not isinstance(slots, list):
        raise ValueError("weekly_template.slots must be a list")

    seen: dict[taxonomy.Capacity, int] = {}
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise ValueError(f"weekly_template.slots[{i}] must be an object")
        extra = sorted(set(slot) - set(_SLOT_FIELDS))
        if extra:
            raise ValueError(f"weekly_template.slots[{i}]: unknown field(s) {extra}")
        cap = taxonomy.resolve_capacity(slot.get("capacity"))
        if cap is None:
            raise ValueError(
                f"weekly_template.slots[{i}].capacity: unknown capacity "
                f"{slot.get('capacity')!r} — one of {taxonomy.capacity_tokens()}"
            )
        if cap in seen:
            raise ValueError(
                f"weekly_template.slots[{i}].capacity: duplicate capacity "
                f"{cap.name} (already declared at slots[{seen[cap]}])"
            )
        seen[cap] = i
        _slot_int(slot, "sessions_per_week", 0, _MAX_SESSIONS_PER_WEEK, i)
        _slot_int(slot, "minutes", _MIN_SLOT_MINUTES, _MAX_SLOT_MINUTES, i)

    return value


def upsert_profile(db: Session, user_id: int, data: dict[str, Any]) -> models.FortificationProfile:
    # Validate BEFORE touching the session. A refused template must leave no row
    # behind, and `db.add` below runs before the field loop — so a mid-loop raise
    # would leave a pending INSERT for a caller that shares the session.
    if data.get("weekly_template") is not None:
        validate_weekly_template(data["weekly_template"])
    for field in _PROVENANCED_FIELDS:
        if data.get(field) is not None:
            validate_assertions(data[field], field)

    p = get_profile(db, user_id)
    if p is None:
        p = models.FortificationProfile(user_id=user_id)
        db.add(p)
    for field in _UPSERTABLE:
        if field in data and data[field] is not None:
            setattr(p, field, data[field])
    db.commit()
    db.refresh(p)
    return p


# --------------------------------------------------------------------------- #
# Seed — first instance, Luke / back-resilience (spec §10).                    #
# --------------------------------------------------------------------------- #

LUKE_PROFILE_SEED: dict[str, Any] = {
    "floor": {
        "demonstrated": "trap-bar 120 kg, grade-level scrum",
        "tag": "managed",  # clean-but-managing — what you already survive, not Phase 1
    },
    "ceiling": "breadth",          # not scrum-peak; scrum demotes to a time-boxed stress-test
    "horizon": "life",             # functional durability
    "primary_target": "anti_lateral_flexion",
    "primary_target_note": (
        "Frontal/transverse trunk control as the right-side asymmetry corrective — "
        "the limiter the bar named (oblique/QL/glute-med/erector tension at 120, legs "
        "in reserve = control cap, not strength cap). Same object as the longevity "
        "priority and the 30-year right-side through-line."
    ),
    # Provenance is carried GOING FORWARD (#227). The seed's entries are stated by
    # the user at first-instance authoring; the pre-existing rows in any live
    # profile are NOT retro-written — the read path backfills them instead.
    "live_signals": [{
        "signal": "flank tension",
        "side": "right",
        "branch_param": "stabiliser_ceiling_vs_guard",
        "status": "unresolved",   # default branch: train it (mechanical-dominant, no travelling pain at 120)
        "self_triage": "warms-up-and-clears → train it; stays-and-sharpens → assess first",
        "asserted_by": "user",
        "asserted_on": "2026-08-19",
        "basis": "Standing right-flank signal at the 120 kg trap-bar ceiling — the "
                 "spec §10 first-instance authoring, not a new observation.",
        # Unresolved branch parameter: worth asking again in a training block.
        "review_on": "2026-11-19",
    }],
    "hard_stops": [
        {"pattern": "radicular", "scope": "provoking pattern", "side": "right",
         "reason": "radicular signs = stop the provoking pattern; Probe never samples that region",
         "asserted_by": "user",
         "asserted_on": "2026-08-19",
         "basis": "Standing safety rule, not an episode — do not discover your way "
                  "into a flagged nerve (spec §8).",
         # null = standing until explicitly retired. This one does not expire.
         "review_on": None},
        {"pattern": "ra_flare", "scope": "both-ends",
         "reason": "RA flare = base + grip compromised",
         "asserted_by": "user",
         "asserted_on": "2026-08-19",
         "basis": "Standing safety rule tied to a diagnosed condition, not to a "
                  "transient flare.",
         "review_on": None},
    ],
    "vehicle_bias": [
        "pilates_clinical", "offset_carry", "unilateral_lifting",
        "swim", "hike", "barbell_floor_hold",
    ],
    "probe_budget": 0.25,
    "notes": "First-instance profile (spec §10). Proves the engine runs off a profile, not a hardcoded string.",
}

# Capability-state seed: the demonstrated sagittal-strength floor is already
# well-sampled (needs loading, not probing) → pass/history. The primary-target
# region is the active Fortify focus → fortifying. Everything else stays untested
# (no row) so the map self-builds via Probe (§2.1).
_FLOOR_PASS_REGIONS = ("hinge", "squat", "horizontal_push", "vertical_pull", "horizontal_pull")
_FORTIFYING_REGIONS = ("anti_lateral_flexion", "frontal_single_leg_stability", "anti_rotation")


def seed_capability_state(db: Session, user_id: int) -> int:
    """Idempotent seed of the demonstrated floor + active fortify target. Returns
    the number of rows written. Leaves all other regions untested by design."""
    written = 0

    def _ensure(region_key: str, side: str, status: str, source: str) -> None:
        nonlocal written
        existing = (
            db.query(models.CapabilityState)
            .filter_by(user_id=user_id, region_key=region_key, side=side)
            .first()
        )
        if existing is not None:
            return
        db.add(models.CapabilityState(
            user_id=user_id, region_key=region_key, side=side,
            status=status, source=source, taxonomy_version=taxonomy.TAXONOMY_VERSION,
            detail={"seeded": True},
        ))
        written += 1

    for key in _FLOOR_PASS_REGIONS:
        region = taxonomy.by_key(key)
        if region is None:
            continue
        for side in region.sides():
            _ensure(key, side, "pass", "history")

    for key in _FORTIFYING_REGIONS:
        region = taxonomy.by_key(key)
        if region is None:
            continue
        for side in region.sides():
            _ensure(key, side, "fortifying", "fortify")

    db.commit()
    return written
