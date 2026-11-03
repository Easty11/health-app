"""Engine-tier default constraints — what the three in-code injury block maps encode, as rows.

`selection.is_contraindicated` blocks regions from three hard-coded maps keyed on an injury row's
`body_part` / `signal_type` / `ra_flare`: `_ACUTE_TISSUE_BLOCKS`, `_RADICULAR_BLOCKS`,
`_RA_FLARE_BLOCKS`. They have no exit, no review date, no authority and no render (Q182, GH#539).
This module turns what they encode into PROPOSED engine-tier `block` constraint rows, one per
(injury, region key), that the operator confirms or declines on the Injuries page (#346). A
proposal blocks nothing (#342): until a row is confirmed the engine reads exactly what it read
before, so landing this changes no verdict (DECISIONS_LOG "Engine blocks are rows").

THE MAPS ARE NO LONGER READ BY `is_contraindicated`. They were retired in the second PR, once every
proposal was confirmed or declined (G4), and now live in this module as reference data: the seed
source for the proposals, read by nothing at selection time.

SHAPE (D1). Per (injury, region key):
    type "constraint"; key `constraint_engine_<injury key>_<region key>`; source "system"
    scope  {tier: "engine", region_keys: [<one key>], side: <the injury's side; absent = bilateral>,
            text: "<map name>: <body part> → <region label> (engine default)"}
    kind "block"; parent_key <injury key>; exit {with_parent: true}; review_by <given>;
    status "proposed"; asserted_by null
One region per row, so the operator can keep "deceleration landing" and decline "change of
direction" with the confirm-only card. Decline is `POST /knowledge/constraints/{id}/resolve`.

WHICH MAPS SEED WHAT (D3). The seeded set is a SUPERSET of what the live arms block for the same
injury — a default never seeds less than the arm enforces, so retiring the arm cannot open a hole
that G4 would not see.
  * acute-tissue — by map key, as today (a substring of the body part), PLUS a declared alias list
    per key (`ENGINE_BODY_PART_ALIASES`), so `pes anserine` reaches the knee set (Q102, ledger
    entry 30) where the bare substring never did.
  * radicular   — an entry typed `neural` / `radicular` whose body part is spinal by
    `selection._SPINAL_PARTS`, or EMPTY (unknown degrades to the broader caution, never to
    permission) — EXCEPT a cervical entry (`_CERVICAL_PARTS`). `_RADICULAR_BLOCKS` is a LUMBAR-shaped
    stand-down (hinge, rotation, carry, gait); firing it on a neck entry is the substring defect the
    code comment at `_SPINAL_PARTS` already names. A cervical neural entry's rules live as advisory
    rows. This is a deliberate difference from the live arm, which fires on `cervical spine` via the
    substring `spine`: it is why the equivalence gate in the retirement PR runs per user.
  * RA-flare    — `ra_flare: true` or the `"ra_flare"` restriction, exactly `gather_active_injuries`.
No new clinical block set is invented here: every region comes from one of the three maps.

IDEMPOTENT on (parent_key, region key) across ACTIVE and RESOLVED constraint rows, whatever their
key or side: a declined default (a resolved proposal) is never re-proposed for the same injury, and
a region the operator already covers with their own engine row is not proposed again. Pure
functions over the injury value, plus one read of the user's constraint rows; nothing here writes.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import injury_sweep
import models
from . import taxonomy
from .taxonomy import SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT

MAP_ACUTE = "acute-tissue"
MAP_RADICULAR = "radicular"
MAP_RA_FLARE = "RA-flare"

DEFAULT_KEY_PREFIX = "constraint_engine_"
# Operator ruling (D1): a default proposed by the injury write path is due for review four weeks
# after the injury row is written. The operator script takes an explicit `--review-by` instead.
DEFAULT_REVIEW_DAYS = 28

# --------------------------------------------------------------------------- #
# Reference data — the SEED SOURCE. No longer read at selection time.         #
# --------------------------------------------------------------------------- #
#
# These three maps used to be read by `selection.is_contraindicated`, keyed on an injury row. They
# were retired ("Engine blocks are rows", DECISIONS_LOG #486) once every proposal they seeded was
# confirmed or declined (user 1: five proposals, all declined; user 9: none). They are kept here
# because they are what the engine-default proposals are made FROM, and because the retirement's
# pinned-SHA equivalence tests compare against the engine as it was. Editing a map changes what
# FUTURE injuries are offered as proposals; it changes no verdict anywhere.

# Seed heuristic maps (spec §8). Provoking signal → regions to hard-stop. These
# are intentionally explicit and reviewable, not learned.
_RADICULAR_BLOCKS = frozenset({
    "hinge", "rotation", "carry", "deceleration_landing",
    "change_of_direction", "single_leg_hop", "gait_load_carriage",
    # A PC-length screen is functionally a straight-leg raise — a neural
    # provocation test — so probing it under an active radicular sign is the
    # literal case "don't discover your way into a flagged nerve" forbids.
    # `loaded_carry_capacity_bw` is the G-axis twin of `carry`, which was
    # already blocked here; the sets were swept for A–E only and never G.
    "hip_flexion_pc_length", "loaded_carry_capacity_bw",
})
# RA flare = both-ends stand-down (base + grip compromised).
_RA_FLARE_BLOCKS = frozenset({
    "carry", "anti_lateral_flexion", "gait_load_carriage", "terrain_perturbation",
    "single_leg_hop", "change_of_direction", "deceleration_landing",
    # This set's own rationale says grip is compromised, yet it left the grip
    # region itself probeable mid-flare. Same G-axis omission as above for the
    # carry twin.
    "grip_strength", "loaded_carry_capacity_bw",
})
# Acute tissue → time-limited exclusion of the provoking range, by body part.
_ACUTE_TISSUE_BLOCKS: dict[str, frozenset[str]] = {
    "hamstring": frozenset({
        "lunge_single_leg", "single_leg_hop", "change_of_direction",
        "deceleration_landing", "terrain_perturbation",
    }),
    "shoulder": frozenset({"vertical_push", "horizontal_push"}),
    "calf": frozenset({"single_leg_hop", "change_of_direction", "deceleration_landing"}),
    "ankle": frozenset({"single_leg_hop", "change_of_direction", "terrain_perturbation"}),
    "knee": frozenset({"single_leg_hop", "change_of_direction", "deceleration_landing"}),
}
# Body parts whose neural/radicular signal implicates the spine. `_RADICULAR_BLOCKS`
# is a lumbar-shaped stand-down — hinge, rotation, carry, gait — so firing it on any
# entry merely typed "neural" makes a peripheral entrapment (cubital tunnel, say)
# block a hinge it has nothing to do with. Non-spine neural signals fall through to
# the acute-tissue arm below; dedicated cervical / peripheral block sets are Q102
# territory, not this change.
_SPINAL_PARTS = (
    "spine", "back", "lumbar", "sacral", "sciatic", "si joint",
    "l4", "l5", "s1",
)


def _is_spinal(body_part: str) -> bool:
    """Does this body part implicate the spine, for `_RADICULAR_BLOCKS` scoping?

    An EMPTY body part returns True: unknown degrades to the broader caution, never
    to permission. Ledger entries are hand-written and `body_part` is optional, so
    the absent case is the one most likely to be a real spinal sign nobody typed.
    """
    if not body_part:
        return True
    return any(part in body_part for part in _SPINAL_PARTS)


# Aliases for the ACUTE-TISSUE map keys. Sources: `injury_sweep.BODY_PART_ALIASES` (#340 — the
# hamstring constituents, one definition, read not copied) plus the knee and shoulder aliases named
# by D3 of the engine-tier brief. Lower-case; matched as substrings of the lower-cased body part,
# like the map keys themselves. Extend per body part only by ruling and only from the ledger's own
# body parts: the stored parts on 2 Nov 2026 were the bare map keys (shoulder, knee, lumbar) plus
# finger, thumb and neck, so nothing beyond D3's list is evidenced.
ENGINE_BODY_PART_ALIASES: dict[str, tuple[str, ...]] = {
    **injury_sweep.BODY_PART_ALIASES,
    "knee": ("pes anserine", "patella", "patellar"),
    "shoulder": ("rotator cuff", "labrum", "ac joint"),
}

# Body parts excluded from the lumbar-shaped radicular set (D3). Substrings, like `_SPINAL_PARTS`.
_CERVICAL_PARTS = ("cervical", "neck", "c5", "c6", "c7")


# --------------------------------------------------------------------------- #
# Pure: what an injury value implies                                           #
# --------------------------------------------------------------------------- #

def _norm(value: dict[str, Any]) -> dict[str, Any]:
    """The injury value as `selection.gather_active_injuries` normalises it — one definition of
    how the arms read a row, so the seeded set cannot drift from the enforced one."""
    return {
        "body_part": str(value.get("body_part", "")).lower(),
        "side": str(value.get("side", SIDE_BILATERAL)).lower(),
        "signal_type": str(value.get("signal_type", "mechanical")).lower(),
        "ra_flare": bool(value.get("ra_flare", False)) or "ra_flare" in (value.get("restrictions") or []),
    }


def default_signature(value: dict[str, Any]) -> tuple[str, str, str, bool]:
    """The four fields whose change re-triggers proposing: (body_part, side, signal_type, ra_flare),
    normalised. A rewrite that leaves them alone proposes nothing."""
    n = _norm(value or {})
    return n["body_part"], n["side"], n["signal_type"], n["ra_flare"]


def row_side(side: str) -> str | None:
    """The scope `side` for an injury side: left / right as stored, absent (None) for bilateral.
    An unrecognised side degrades to bilateral — the broader block, never a narrower one."""
    return side if side in (SIDE_LEFT, SIDE_RIGHT) else None


def is_cervical(body_part: str) -> bool:
    return any(part in body_part for part in _CERVICAL_PARTS)


def acute_keys_matching(body_part: str) -> list[str]:
    """Which `_ACUTE_TISSUE_BLOCKS` keys this body part reaches: the key itself or a declared alias."""
    out = []
    for key in _ACUTE_TISSUE_BLOCKS:
        terms = (key, *ENGINE_BODY_PART_ALIASES.get(key, ()))
        if any(t in body_part for t in terms):
            out.append(key)
    return out


def candidate_regions(value: dict[str, Any]) -> list[dict[str, Any]]:
    """The (region, maps) pairs an injury value implies, in taxonomy order. Pure.

    A region implied by more than one map is ONE candidate carrying every map name — the arms would
    each block it, a row blocks it once.
    """
    n = _norm(value or {})
    bp = n["body_part"]
    by_region: dict[str, list[str]] = {}

    def add(map_name: str, keys) -> None:
        for k in keys:
            names = by_region.setdefault(k, [])
            if map_name not in names:
                names.append(map_name)

    if n["signal_type"] in ("radicular", "neural") and _is_spinal(bp) and not is_cervical(bp):
        add(MAP_RADICULAR, _RADICULAR_BLOCKS)
    if n["ra_flare"]:
        add(MAP_RA_FLARE, _RA_FLARE_BLOCKS)
    for key in acute_keys_matching(bp):
        add(f"{MAP_ACUTE} ({key})", _ACUTE_TISSUE_BLOCKS[key])

    order = {r.key: i for i, r in enumerate(taxonomy.all_regions())}
    return [
        {"region_key": k, "maps": by_region[k], "side": row_side(n["side"]), "body_part": bp}
        for k in sorted(by_region, key=lambda k: order.get(k, len(order)))
    ]


def default_row_value(injury_key: str, cand: dict[str, Any], review_by: date) -> dict[str, Any]:
    """The D1 constraint value for one candidate. Passes `validate_constraint` unchanged."""
    region = taxonomy.by_key(cand["region_key"])
    label = region.label if region is not None else cand["region_key"]
    scope: dict[str, Any] = {"tier": "engine", "region_keys": [cand["region_key"]]}
    if cand["side"] is not None:
        scope["side"] = cand["side"]
    scope["text"] = (
        f"{' + '.join(cand['maps'])}: {cand['body_part'] or 'unspecified body part'} "
        f"→ {label} (engine default)"
    )
    return {
        "scope": scope,
        "kind": "block",
        "parent_key": injury_key,
        "exit": {"with_parent": True},
        "review_by": review_by.isoformat(),
        "status": "proposed",
        "asserted_by": None,
    }


def default_key(injury_key: str, region_key: str) -> str:
    return f"{DEFAULT_KEY_PREFIX}{injury_key}_{region_key}"


# --------------------------------------------------------------------------- #
# DB: idempotency against what already exists                                  #
# --------------------------------------------------------------------------- #

def _existing_engine_cover(db: Session, user_id: int) -> dict[tuple[str, str], dict[str, Any]]:
    """(parent_key, region key) → the constraint row already covering it, active or not.

    Every constraint row counts, in any state: a resolved row is a declined or ended default and
    must not come back (the #340 seed-resurrection lesson). When several rows cover the same pair
    the ACTIVE one is reported — it is the one that explains a skip.
    """
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint").all()
    cover: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        v = r.value or {}
        scope = v.get("scope") or {}
        parent = v.get("parent_key")
        if scope.get("tier") != "engine" or not parent:
            continue
        for rk in scope.get("region_keys") or []:
            info = {
                "id": r.id, "key": r.key, "active": bool(r.active),
                "status": v.get("status"), "side": scope.get("side") or SIDE_BILATERAL,
            }
            prev = cover.get((parent, rk))
            if prev is None or (info["active"] and not prev["active"]):
                cover[(parent, rk)] = info
    return cover


def _active_keys(db: Session, user_id: int) -> dict[str, int]:
    return {
        r.key: r.id
        for r in db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, active=True).all()
    }


def plan_engine_defaults(
    db: Session,
    user_id: int,
    injury_key: str,
    injury_value: dict[str, Any],
    review_by: date,
    *,
    cover: dict[tuple[str, str], dict[str, Any]] | None = None,
    active_keys: dict[str, int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """The proposals this injury implies, split into what would be written and why not.

        planned    — [{key, parent_key, region_key, side, maps, value, replaces}]   `replaces` is the id
                     of a stale-sided, still-unconfirmed default of ours this row supersedes (else None)
        skipped    — [{parent_key, region_key, why, side_mismatch}]   an existing row already covers
                     the pair; `side_mismatch` marks a cover whose side differs from the injury's
        conflicts  — [{key, held_by, parent_key, region_key}]   the key is held by an active row of
                     another shape; never written

    Writes nothing. `cover` / `active_keys` may be passed to share one read across many injuries.
    Not called by `probe_resolver._synthetic_db`, on purpose: it is an in-memory measurement harness whose pinned injuries never reach a prod row or the engine (operator ruling, 3 Nov 2026).
    """
    cover = _existing_engine_cover(db, user_id) if cover is None else cover
    active_keys = _active_keys(db, user_id) if active_keys is None else active_keys
    planned, skipped, conflicts = [], [], []
    for cand in candidate_regions(injury_value):
        rk = cand["region_key"]
        hit = cover.get((injury_key, rk))
        key = default_key(injury_key, rk)
        want = cand["side"] or SIDE_BILATERAL
        replaces = None
        if hit is not None:
            mismatch = hit["side"] != want
            if mismatch and hit["active"] and hit["status"] == "proposed" and hit["key"] == key:
                # Our own, still-unconfirmed default carries a stale side (the injury was re-sided).
                # Proposing again under the same key supersedes it, so the operator is never offered
                # the wrong side to confirm. A CONFIRMED or hand-authored row is never touched.
                replaces = hit["id"]
            else:
                state = "active" if hit["active"] else "resolved/superseded"
                why = f"already covered by {hit['key']} (id {hit['id']}, {state}, {hit['status']})"
                if mismatch:
                    why += f"; its side is {hit['side']}, the injury now implies {want}"
                skipped.append({"parent_key": injury_key, "region_key": rk, "why": why,
                                "side_mismatch": mismatch})
                continue
        if replaces is None and key in active_keys:
            conflicts.append({"key": key, "held_by": active_keys[key],
                              "parent_key": injury_key, "region_key": rk})
            continue
        planned.append({
            "key": key, "parent_key": injury_key, "region_key": rk, "side": cand["side"],
            "maps": cand["maps"], "value": default_row_value(injury_key, cand, review_by),
            "replaces": replaces,
        })
    return {"planned": planned, "skipped": skipped, "conflicts": conflicts}


def propose_engine_defaults(
    db: Session, injury_row: models.UserKnowledgeEntry, review_by: date,
) -> list[dict[str, Any]]:
    """The proposed rows for one injury row (S1): `plan_engine_defaults(...)["planned"]`. Unwritten —
    the caller stages them through `routers.knowledge._stage_upsert_entry`."""
    return plan_engine_defaults(
        db, injury_row.user_id, injury_row.key, injury_row.value or {}, review_by,
    )["planned"]


def is_engine_default_key(key: str) -> bool:
    return key.startswith(DEFAULT_KEY_PREFIX)


__all__ = [
    "ENGINE_BODY_PART_ALIASES", "DEFAULT_REVIEW_DAYS", "candidate_regions", "default_key",
    "default_row_value", "default_signature", "plan_engine_defaults", "propose_engine_defaults",
    "is_cervical", "is_engine_default_key",
]
