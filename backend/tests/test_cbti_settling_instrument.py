"""#124 — nights_since_effective_from is instrumented, not gated.

Two properties: the field is recorded on EVERY verdict path (both HOLDs included), and
setting it changes NOTHING about the verdict. The second is the one that matters — it is
the executable form of "nothing branches on it".
"""
import dataclasses
from datetime import date

from cbti.engine import CycleDecision, Night, evaluate_cycle

RX = "23:45"
ANCHOR = "05:45"
WINDOW = 360


def night(d, tst, se, *, bedtime="23:45", lo="23:45", fw="05:45", oob="05:45", naps=0, alc=0):
    return Night(date=date(2026, 7, d), tst_min=tst, se_pct=se, lights_out=lo, final_wake=fw,
                 out_of_bed=oob, samsung_bedtime=bedtime, naps_min=naps, alcohol_units=alc)


def _eval(nights, **kw):
    return evaluate_cycle(nights, WINDOW, RX, ANCHOR, **kw)


# ── the field lands on all four verdict paths ─────────────────────────────────────

def test_sufficiency_hold_carries_the_field():
    d = _eval([night(i, 380, 90) for i in (1, 2, 3)], nights_since_effective_from=7)
    assert d.decision == "hold" and "insufficient" in d.reason
    assert d.nights_since_effective_from == 7


def test_adherence_hold_carries_the_field():
    nights = [night(i, 380, 90, lo="22:00") for i in (1, 2, 3)] + [night(i, 380, 90) for i in (4, 5)]
    d = _eval(nights, nights_since_effective_from=7)
    assert d.decision == "hold" and "adherence" in d.reason
    assert d.nights_since_effective_from == 7


def test_plateau_close_carries_the_field():
    d = _eval([night(i, 382, 90) for i in range(1, 6)],
              prior_basis_tst=[375, 380], nights_since_effective_from=7)
    assert d.decision == "close" and "plateau" in d.reason
    assert d.nights_since_effective_from == 7


def test_titrate_carries_the_field():
    d = _eval([night(i, 400, 90) for i in range(1, 6)], nights_since_effective_from=7)
    assert d.decision == "extend"
    assert d.nights_since_effective_from == 7


# ── the negative control that matters: setting it changes nothing else ────────────

def test_verdict_is_identical_set_vs_unset_on_a_move():
    nights = [night(i, 400, 90) for i in range(1, 6)]
    d_set = _eval(nights, nights_since_effective_from=5)
    d_unset = _eval(nights)
    assert d_set.nights_since_effective_from == 5
    assert d_unset.nights_since_effective_from is None
    # everything else byte-identical — proven by neutralising the one field and comparing
    assert dataclasses.replace(d_set, nights_since_effective_from=None) == d_unset


def test_verdict_is_identical_set_vs_unset_on_a_hold():
    """The HOLD path is where the value matters, so pin invariance there too."""
    nights = [night(i, 380, 90) for i in (1, 2, 3)]      # insufficient -> hold
    d_set = _eval(nights, nights_since_effective_from=3)
    d_unset = _eval(nights)
    assert d_set.nights_since_effective_from == 3 and d_unset.nights_since_effective_from is None
    assert dataclasses.replace(d_set, nights_since_effective_from=None) == d_unset


def test_default_is_none_when_caller_gives_no_context():
    d = _eval([night(i, 400, 90) for i in range(1, 6)])
    assert d.nights_since_effective_from is None      # correct, and must stay inert
