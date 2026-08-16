"""Contraindication block sets — membership and radicular body-part scoping (#216).

The Q23 audit found the two named block sets were written against the A–E axis
vocabulary and never swept G, and that the radicular arm fired on *any* neural
signal regardless of body part. These tests pin both corrections.

Pure-function tests: `is_contraindicated` takes plain dicts and a `Region`, so
nothing here needs a database.
"""
import pytest

from engine import taxonomy
from engine.selection import (
    _RA_FLARE_BLOCKS,
    _RADICULAR_BLOCKS,
    _SPINAL_PARTS,
    is_contraindicated,
)
from engine.taxonomy import SIDE_BILATERAL


def _injury(body_part="", *, signal_type="mechanical", ra_flare=False,
            side=SIDE_BILATERAL):
    """A `gather_active_injuries`-shaped row, without touching the ledger."""
    return {
        "body_part": body_part,
        "side": side,
        "signal_type": signal_type,
        "ra_flare": ra_flare,
        "restrictions": [],
        "raw": {},
    }


def _check(region_key, injuries):
    region = taxonomy.by_key(region_key)
    assert region is not None, f"{region_key} does not resolve in the taxonomy"
    return is_contraindicated(
        region, SIDE_BILATERAL,
        profile_hard_stops=None, active_injuries=injuries,
    )


# --------------------------------------------------------------------------- #
# (a) The new members are in the sets, and every member resolves.             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", ["hip_flexion_pc_length", "loaded_carry_capacity_bw"])
def test_radicular_set_gains_g_axis_members(key):
    assert key in _RADICULAR_BLOCKS


@pytest.mark.parametrize("key", ["grip_strength", "loaded_carry_capacity_bw"])
def test_ra_flare_set_gains_grip_and_carry_twin(key):
    assert key in _RA_FLARE_BLOCKS


def test_every_block_set_member_resolves_in_the_taxonomy():
    """Fail-closed spirit of the seeder: a set member that does not resolve is a
    block that can never fire, i.e. silent under-protection."""
    unresolved = sorted(
        k for k in (_RADICULAR_BLOCKS | _RA_FLARE_BLOCKS)
        if taxonomy.by_key(k) is None
    )
    assert unresolved == []


# --------------------------------------------------------------------------- #
# (b)/(c) The radicular arm is scoped by body part.                            #
# --------------------------------------------------------------------------- #

def test_non_spinal_neural_signal_does_not_fire_the_radicular_block():
    """A neural signal at the hamstring must not trigger a lumbar-shaped
    stand-down. `hinge` is chosen deliberately: it is in `_RADICULAR_BLOCKS`
    but NOT in `_ACUTE_TISSUE_BLOCKS["hamstring"]`, so a pass here isolates the
    radicular arm rather than being rescued by the acute-tissue arm."""
    blocked, reason = _check("hinge", [_injury("hamstring", signal_type="neural")])
    assert blocked is False
    assert reason is None


def test_non_spinal_neural_signal_does_not_fire_on_the_new_g_axis_member():
    blocked, _ = _check(
        "hip_flexion_pc_length", [_injury("hamstring", signal_type="neural")]
    )
    assert blocked is False


@pytest.mark.parametrize("body_part", ["lumbar spine", ""])
def test_spinal_and_unknown_body_parts_do_fire_the_radicular_block(body_part):
    """Empty degrades to the broader caution — unknown never becomes permission."""
    blocked, reason = _check("hinge", [_injury(body_part, signal_type="neural")])
    assert blocked is True
    assert "radicular sign" in reason


def test_pc_length_screen_is_blocked_under_a_spinal_radicular_sign():
    """A PC-length screen is functionally an SLR — a neural provocation test."""
    blocked, reason = _check(
        "hip_flexion_pc_length", [_injury("lumbar spine", signal_type="radicular")]
    )
    assert blocked is True
    assert "radicular sign" in reason


@pytest.mark.parametrize("body_part", list(_SPINAL_PARTS))
def test_every_declared_spinal_part_fires(body_part):
    blocked, _ = _check("hinge", [_injury(body_part, signal_type="radicular")])
    assert blocked is True


# --------------------------------------------------------------------------- #
# (d) RA flare reaches the grip region it always claimed to be standing down.  #
# --------------------------------------------------------------------------- #

def test_ra_flare_contraindicates_grip_strength():
    blocked, reason = _check("grip_strength", [_injury("hand", ra_flare=True)])
    assert blocked is True
    assert "RA flare" in reason


def test_ra_flare_contraindicates_the_carry_g_axis_twin():
    blocked, _ = _check("loaded_carry_capacity_bw", [_injury("hand", ra_flare=True)])
    assert blocked is True


def test_ra_flare_is_not_body_part_scoped():
    """Only the radicular arm gained body-part scoping; RA is systemic and its
    stand-down stays global. Pins that the #216 scoping did not leak across."""
    blocked, _ = _check("grip_strength", [_injury("", ra_flare=True)])
    assert blocked is True
