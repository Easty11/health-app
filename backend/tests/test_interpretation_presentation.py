"""Deterministic serialiser (increment 2, #202) — conformance against the live panel.

The live-panel fixture (`frontend/src/fixtures/interpretationExample.json`, generated
from `build_foundation`) is the oracle. These tests pin the properties #202 makes the
generator and validator depend on:

  * PURE / DETERMINISTIC — same payload -> byte-identical fragments (no model, no clock).
  * PASS-THROUGH FIDELITY — every reviewed asset prose string (frame, mechanism) appears
    verbatim in exactly one block, so a rephrase simplifies the asset text and nothing else.
  * CENSORED HONESTY (#205/#Q70) — a censored comparison's movement fragment is flagged
    and carries no computed magnitude, only direction.
  * ADDRESS STABILITY / UNIQUENESS — every fragment has a unique, payload-derived address.
  * FAIL-CLOSED RENDER — render_base_text is the ordered join (the #202 clause-4 fallback).
"""
import json
from pathlib import Path

from interpretation.presentation import (
    BLOCK,
    FRAGMENT,
    presentation_hash,
    render_base_text,
    serialize,
)

_FIXTURE = (Path(__file__).resolve().parent.parent.parent
            / "frontend" / "src" / "fixtures" / "interpretationExample.json")


def _payload() -> dict:
    with open(_FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_serialize_is_deterministic():
    p = _payload()
    a = serialize(p)
    b = serialize(p)
    assert [(f.addr, f.text, f.granularity, f.censored) for f in a] \
        == [(f.addr, f.text, f.granularity, f.censored) for f in b]
    assert a  # non-vacuous


def test_addresses_unique_and_kind_matches_granularity():
    frags = serialize(_payload())
    addrs = [f.addr for f in frags]
    assert len(addrs) == len(set(addrs)), "fragment addresses must be unique"
    # The #202 dial: mechanism/education prose is BLOCK; everything gate/verdict-adjacent
    # (and the header/lever) is FRAGMENT.
    for f in frags:
        if f.kind in ("frame", "mechanism"):
            assert f.granularity == BLOCK, f"{f.addr} should be a block"
        else:
            assert f.granularity == FRAGMENT, f"{f.addr} should be a fragment"


def test_prose_blocks_are_verbatim_passthrough():
    """Every axis_verdict.text and mechanism.text in the payload appears, unaltered,
    as a block. The serialiser authors no prose — it passes the reviewed asset through."""
    p = _payload()
    frag_by_addr = {f.addr: f for f in serialize(p)}

    for g in p["groups"]:
        av = (g.get("axis_verdict") or {}).get("text")
        if av:
            f = frag_by_addr[f"groups.{g['group_key']}.frame"]
            assert f.text == av and f.granularity == BLOCK
        for m in g["members"]:
            mech = (m.get("mechanism") or {}).get("text")
            if mech:
                addr = f"groups.{g['group_key']}.members.{m['marker_canonical']}.mechanism"
                assert frag_by_addr[addr].text == mech


def test_flat_censored_member_carries_no_magnitude():
    """fsh is censored AND flat in the live fixture (both draws `<0.1`): the movement
    fragment is flagged censored and fabricates neither magnitude nor direction (#205)."""
    frags = {f.addr: f for f in serialize(_payload())}
    fsh = next(f for a, f in frags.items() if a.endswith("fsh.movement"))
    assert fsh.censored is True
    assert "censored" in fsh.text.lower()
    # abs_change/pct_change are None on a censored comparison, so no "(...%)" magnitude leaks.
    assert "%)" not in fsh.text


def test_directional_censored_says_magnitude_not_computable():
    """A censored comparison with a direction (crossed bound) reports direction only and
    states the magnitude is not computable — never an invented abs/pct (#205)."""
    payload = {
        "meta": {"trigger_panel": {"collected": "2026-05-30"}, "compared_against": None},
        "groups": [],
        "ungrouped": [{
            "marker_canonical": "ferritin",
            "display_name": "Ferritin",
            "current": {"value_num": 10, "value_operator": ">", "unit_canonical": "ng/mL"},
            "prior": {"value_num": 8, "unit_canonical": "ng/mL"},
            "delta": {"direction": "up", "abs_change": None, "pct_change": None,
                      "crossed_ref": None, "magnitude": "within_noise", "censored": True},
            "range_gate": {"is_out_of_range": False, "flag": None},
            "safety_gate": {"status": None},
        }],
    }
    f = next(fr for fr in serialize(payload) if fr.addr.endswith("ferritin.movement"))
    assert f.censored is True
    assert "not computable" in f.text.lower()
    assert "moved up" in f.text.lower()
    assert "%)" not in f.text  # no fabricated pct


def test_first_observation_reads_as_such():
    """vitamin_d_25oh has no prior in the live fixture."""
    frags = {f.addr: f for f in serialize(_payload())}
    vd = next(f for a, f in frags.items() if a.endswith("vitamin_d_25oh.movement"))
    assert "first observation" in vd.text.lower()
    assert vd.censored is False


def test_movement_fragment_contains_name_and_value():
    """A normal member's movement sentence carries its display name and current reading —
    the entities/numerals the validator will treat as this fragment's allowed set."""
    p = _payload()
    frags = {f.addr: f for f in serialize(p)}
    g = p["groups"][0]
    m = g["members"][0]
    f = frags[f"groups.{g['group_key']}.members.{m['marker_canonical']}.movement"]
    assert m["display_name"] in f.text
    assert str(int(m["current"]["value_num"])) in f.text or str(m["current"]["value_num"]) in f.text


def test_render_base_text_is_the_ordered_join():
    frags = serialize(_payload())
    assert render_base_text(frags) == "\n\n".join(f.text for f in frags)


def test_flagged_tracks_gate_state():
    """fsh is below the reference range -> flagged; a normal in-range member is not."""
    frags = {f.addr: f for f in serialize(_payload())}
    fsh = next(f for a, f in frags.items() if a.endswith("fsh.movement"))
    assert fsh.flagged is True
    normal = next(f for a, f in frags.items()
                  if a.endswith("testosterone_total.movement"))
    assert normal.flagged is False


def test_presentation_hash_is_stable_and_content_sensitive():
    p = _payload()
    h1 = presentation_hash(serialize(p))
    assert h1 == presentation_hash(serialize(p))          # stable across runs
    assert len(h1) == 64                                   # sha256 hex
    # meta.generated_at is NOT hashed: mutating it does not change the hash.
    p2 = json.loads(json.dumps(p))
    p2["meta"]["generated_at"] = "1999-01-01T00:00:00+00:00"
    assert presentation_hash(serialize(p2)) == h1
    # A change to an actual reading DOES change the hash.
    p2["groups"][0]["members"][0]["current"]["value_num"] = 999.9
    assert presentation_hash(serialize(p2)) != h1
