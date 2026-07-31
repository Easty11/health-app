"""`axis_verdict.text` carries the invariant per-group frame (#154).

`#154` reduced `axis_verdict` to `{text}` and states the field "emits the invariant per-group
floor sentence in the interim, which satisfies `#151`'s producer-complete requirement against the
reduced contract and unblocks 1b delivery immediately." These tests assert that emission.

The frame renders on EVERY group on EVERY panel — not only where relations are unevaluable — so
it is the whole group-level descriptor for as long as the branch-condition lane takes. Asserting
that explicitly, rather than only asserting the field exists, is the point: a frame that appeared
solely in a degenerate case would be a different contract.
"""
import json
import pathlib

from interpretation.producer import _MARKER_GROUPS, _axis_verdict

_ASSET = pathlib.Path(__file__).resolve().parent.parent / "reference" / "marker_groups.json"
_GROUPS = {g["group_key"]: g for g in _MARKER_GROUPS["groups"]}


def test_every_authored_group_carries_a_frame():
    """No group may ship without one. A group-level descriptor that is present for some groups
    and absent for others reads as a rendering fault, not as an authoring gap."""
    missing = [k for k, g in _GROUPS.items() if not g.get("axis_frame")]
    assert missing == [], f"groups with no authored axis_frame: {missing}"


def test_the_frame_is_projected_verbatim():
    """The `relations_rendered[].reads` precedent — projected, never rewritten. A producer that
    reformatted the string would make the asset stop being the source of the text."""
    for key, group_def in _GROUPS.items():
        assert _axis_verdict(group_def) == {"text": group_def["axis_frame"]}, key


def test_a_group_with_no_frame_emits_None_not_an_empty_sentence():
    """Absence is visible. `{"text": ""}` would render as a blank descriptor and read as a
    styling bug; None lets the view omit the block."""
    assert _axis_verdict({"group_key": "x"}) is None
    assert _axis_verdict({"group_key": "x", "axis_frame": ""}) is None


def test_the_frame_states_composition_and_never_recommends():
    """`#47` — the frame may explain why these markers are one group; it may not characterise
    the reader's results or point at an action. Asserted mechanically on the authored strings so
    a later edit cannot quietly cross the line."""
    banned = ("you ", "your ", "should ", "recommend", "consider ", "try ", "increase your",
              "reduce your", "we suggest", "advise")
    for key, group_def in _GROUPS.items():
        text = group_def["axis_frame"].lower()
        hits = [b for b in banned if b in text]
        assert hits == [], f"{key} frame uses second-person/recommendation language: {hits}"


def test_the_asset_stays_pure_ascii_with_no_literal_em_dash():
    """`#98`'s reference-JSON edit guard, asserted rather than trusted — the failure mode is
    silent in the direction that writes bad bytes, so only the assertion catches it."""
    raw = _ASSET.read_bytes()
    assert raw.isascii(), "marker_groups.json must be pure ASCII"
    assert raw.decode().count(chr(0x2014)) == 0, "literal em dash written into the asset"
    assert json.loads(raw.decode())


def test_frames_are_distinct_per_group():
    """A copy-paste that gave two groups the same frame would pass every test above."""
    frames = [g["axis_frame"] for g in _GROUPS.values()]
    assert len(set(frames)) == len(frames)
