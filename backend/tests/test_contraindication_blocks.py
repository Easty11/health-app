"""Block-set membership and radicular body-part scoping (#216), as they stand after the injury-keyed maps
retired ("Engine blocks are rows", DECISIONS_LOG #486).

The Q23 audit found the two named block sets were written against the A–E axis vocabulary and never swept
G, and that the radicular arm fired on *any* neural signal regardless of body part. These tests pinned both
corrections against `is_contraindicated`. The arms are gone; the maps survive as the SEED SOURCE of the
engine-default proposals (`engine.engine_defaults`), so the same corrections are pinned where they now
act: the sets' membership, and which injuries are OFFERED which set. A map that is wrong now offers a wrong
proposal instead of enforcing a wrong block, but a wrong proposal is still one the operator has to read.

Pure-function tests: `candidate_regions` takes a plain injury value; nothing here needs a database.
"""
import pytest

from engine import engine_defaults as ed
from engine import taxonomy


def _offered(body_part="", *, signal_type="mechanical", ra_flare=False):
    """The regions an injury value would be offered as proposals."""
    return {c["region_key"] for c in ed.candidate_regions({
        "body_part": body_part, "side": "bilateral", "signal_type": signal_type, "ra_flare": ra_flare,
    })}


# --------------------------------------------------------------------------- #
# (a) The new members are in the sets, and every member resolves.             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", ["hip_flexion_pc_length", "loaded_carry_capacity_bw"])
def test_radicular_set_gains_g_axis_members(key):
    assert key in ed._RADICULAR_BLOCKS


@pytest.mark.parametrize("key", ["grip_strength", "loaded_carry_capacity_bw"])
def test_ra_flare_set_gains_grip_and_carry_twin(key):
    assert key in ed._RA_FLARE_BLOCKS


def test_every_block_set_member_resolves_in_the_taxonomy():
    """Fail-closed spirit of the seeder: a set member that does not resolve is a proposal that can never
    validate (`validate_constraint` refuses an unknown region key), i.e. silent under-offering."""
    members = set(ed._RADICULAR_BLOCKS) | set(ed._RA_FLARE_BLOCKS)
    for blocked in ed._ACUTE_TISSUE_BLOCKS.values():
        members |= set(blocked)
    assert sorted(k for k in members if taxonomy.by_key(k) is None) == []


# --------------------------------------------------------------------------- #
# (b)/(c) The radicular set is offered by body part.                           #
# --------------------------------------------------------------------------- #

def test_non_spinal_neural_signal_is_not_offered_the_radicular_set():
    """A neural signal at the hamstring must not be offered a lumbar-shaped stand-down. `hinge` is chosen
    deliberately: it is in `_RADICULAR_BLOCKS` but NOT in `_ACUTE_TISSUE_BLOCKS["hamstring"]`, so a pass
    here isolates the radicular set rather than being rescued by the acute-tissue one."""
    assert "hinge" not in _offered("hamstring", signal_type="neural")


def test_non_spinal_neural_signal_is_not_offered_the_new_g_axis_member():
    assert "hip_flexion_pc_length" not in _offered("hamstring", signal_type="neural")


@pytest.mark.parametrize("body_part", ["lumbar spine", ""])
def test_spinal_and_unknown_body_parts_are_offered_the_radicular_set(body_part):
    """Empty degrades to the broader caution — unknown never becomes permission."""
    assert set(ed._RADICULAR_BLOCKS) <= _offered(body_part, signal_type="neural")


def test_pc_length_screen_is_offered_under_a_spinal_radicular_sign():
    """A PC-length screen is functionally an SLR — a neural provocation test."""
    assert "hip_flexion_pc_length" in _offered("lumbar spine", signal_type="radicular")


@pytest.mark.parametrize("body_part", list(ed._SPINAL_PARTS))
def test_every_declared_spinal_part_is_offered_the_set(body_part):
    assert "hinge" in _offered(body_part, signal_type="radicular")


def test_a_cervical_part_is_not_offered_the_lumbar_shaped_set():
    """The difference from the retired arm, which fired on `cervical spine` via "spine"."""
    assert _offered("cervical spine", signal_type="neural") == set()


# --------------------------------------------------------------------------- #
# (d) RA flare reaches the grip region it always claimed to be standing down.  #
# --------------------------------------------------------------------------- #

def test_ra_flare_is_offered_grip_strength():
    assert "grip_strength" in _offered("hand", ra_flare=True)


def test_ra_flare_is_offered_the_carry_g_axis_twin():
    assert "loaded_carry_capacity_bw" in _offered("hand", ra_flare=True)


def test_ra_flare_is_not_body_part_scoped():
    """Only the radicular set is scoped by body part; RA is systemic and its stand-down stays global.
    Pins that the #216 scoping did not leak across."""
    assert "grip_strength" in _offered("", ra_flare=True)
