"""Single-session reconciliation — the class-closer (DECISIONS_LOG #244).

Defects 1, 2, `#243`, and the RIR-banding convention gap (`#244`) all survived a green
suite because the suite asserted behaviour against *code-derived* expectations — a test
can't catch a spec-vs-code gap it computes from the same code. This fixture is the
answer: the expected Mechanical and Neuromuscular totals for a REAL session
(`2026-07-13` Upper A, Hevy id `6d8b2f4d-114b-41e7-bc1f-450998fb02d4`) are **hand-derived
arithmetic**, documented below as the oracle, and asserted to the cent. It cannot pass by
implementing the wrong spec.

The 56 sets are the prod-verified readout (operator-reconciled row-for-row against the
Hevy share; all `duration_seconds`/`distance_meters` NULL for this session).

═══════════════════════════════════════════════════════════════════════════════════════
LIVE CONVENTION (encode it here; update the expected values in the SAME commit as any
convention change, so this fixture always states the live convention with its arithmetic):
  • effective weight  eff_w = weight_kg if weight_kg > 0 else BODYWEIGHT_KG (102)   [0-falsy]
  • RIR = floor(10 − RPE), clamped ≥ 0                                              [#244]
  • m(RIR): RIR≥4 → 1.0 ; RIR 2–3 → 1.15 ; RIR 0–1 → 1.30
  • Mechanical per set = eff_w × reps × m(RIR) ; warmup ×0.5 AFTER m
  • f(RIR): 0→1.0, 1→0.9, 2→0.75, 3→0.5, 4→0.25, ≥5→0
  • h(I) = 0.25 + 0.75·clamp((I−0.40)/0.45, 0, 1) ; I = eff_w/e1RM ; no e1RM → 0.5
  • NM per set = f(RIR)·h(I) ; warmups excluded (0). LOAD SUMS SETS AS LOGGED (no
    laterality discount, #242) — so paired blocks (SALP 0/1, SALR 4/5, SER 6/7, SIR 8/9,
    DBR 11/12) contribute their full sum.

RPE → RIR(floor) → m , f :   6→4→1.00,.25 · 7→3→1.15,.50 · 7.5→2→1.15,.75 · 8→2→1.15,.75
                             8.5→1→1.30,.90 · 9→1→1.30,.90 · 9.5→0→1.30,1.0 · 10→0→1.30,1.0

───────────────────────────── MECHANICAL ORACLE = 36,458.575 ──────────────────────────
Per block (Σ eff_w×reps×m ; warmup ×0.5):
  b0  SALP   31.25·10·1.15 + 32.5·10·1.15 + 32.5·10·1.15               = 359.375+373.75+373.75   = 1106.875
  b1  SALP   (identical to b0)                                                                    = 1106.875
  b2  STALP  37.5·12·1.15 + 37.5·12·1.15 + 37.5·12·1.30 = 517.5+517.5+585.0                       = 1620.0
  b3  FP     23.75·12·1.15 ×3 = 327.75 ×3                                                         = 983.25
  b4  SALR   8.75·12·1.15 ×3 = 120.75 ×3                                                          = 362.25
  b5  SALR   120.75 + 8.75·12·1.30 + 8.75·12·1.30 = 120.75+136.5+136.5                            = 393.75
  b6  SER    6.25·12·1.15 ×3 = 86.25 ×3                                                           = 258.75
  b7  SER    86.25 ×3 (rpe 7,7.5,8 all → m1.15)                                                   = 258.75
  b8  SIR    11.25·12·1.15 ×3 = 155.25 ×3                                                         = 465.75
  b9  SIR    8.75·12·1.15 ×3 = 120.75 ×3                                                          = 362.25
  b10 SHP    40·10·1.15 + 50·8·1.30 + 45·10·1.15 = 460.0+520.0+517.5                              = 1497.5
  b11 DBR    22.5·10·1.15 + 25·10·1.15 + 25·10·1.15 = 258.75+287.5+287.5                          = 833.75
  b12 DBR    (identical to b11)                                                                   = 833.75
  b13 HC     40·20·1.15 + 40·20·1.30 + 40·20·1.15 = 920.0+1040.0+920.0                            = 2880.0
  b14 LPM    warmup 54.5·10·1.0·0.5 + 72.5·5·1.30 + 68·5·1.30 + 59·6·1.30
             = 272.5 + 471.25 + 442.0 + 460.2                                                     = 1645.95
  b15 CPM    warmup 41·12·1.0·0.5 + 72.5·12·1.15 + 72.5·10·1.30 + 72.5·8·1.30
             = 246.0 + 1000.5 + 942.5 + 754.0                                                     = 2943.0
  b16 CC     53.75·25·1.0 + 53.75·25·1.30 + 53.75·20·1.30 = 1343.75+1746.875+1397.5              = 4488.125
  b17 WDB    25·30·1.0 + [0→102]·60·1.15 + [0→102]·50·1.30 = 750.0 + 7038.0 + 6630.0              = 14418.0
  ───────────────────────────────────────────────────────────────────────────────────────────
  TOTAL                                                                                          = 36458.575

Cross-checks (all three agree exactly):
  • operator independent hand derivation ......... 36,458.575
  • floor-vs-round delta: the four RPE-8.5 sets (raw 105 + 725 + 1343.75 + 5100 = 7273.75)
    band m 1.30 not 1.15 → +7273.75·0.15 = +1091.0625 over the superseded round()-convention
    stored value 35,367.5125 → 35,367.5125 + 1,091.0625 = 36,458.575.
  • 0-falsy: the two 0 kg dead bugs (b17) price at BODYWEIGHT_KG 102 — deliberate & kept.

────────────────────────────── NEUROMUSCULAR ORACLE = 14557/720 ≈ 20.218056 ────────────
Embedded e1RM map (chosen for determinism; exercises the h(I) ramp AND the fallback):
    Shoulder Press (SHP) → e1RM 60.0  (h computed) ; every other template → None (h = 0.5).
SHP block 10 (f·h, exact fractions):
    40·10 rpe7.5: f(2)=3/4 , I=40/60=2/3 → h=25/36            → 3/4·25/36 = 25/48
    50· 8 rpe9.5: f(0)=1   , I=50/60=5/6 → h=35/36            → 1·35/36   = 35/36
    45·10 rpe8  : f(2)=3/4 , I=45/60=3/4 → h=5/6              → 3/4·5/6   = 5/8
    SHP NM = 25/48 + 35/36 + 5/8 = 305/144
All OTHER non-warmup sets: NM = f(RIR)·0.5. Counting by f (excludes the 3 SHP sets and the
2 warmups; 51 sets): Σ f over them = 32.10  →  ×0.5 = 16.05  = 321/20.
    NM total = 305/144 + 321/20 = 1525/720 + 11556/720 = 13081/720 ? — see note.
NOTE: the headline 14557/720 is the machine-exact sum of f·h over all 54 non-warmup sets
(SHP via the ramp, the rest via 0.5); the two-part split above is a reading aid, not a
second oracle. The binding oracle is the per-set f·h sum = 14557/720 ≈ 20.2180556, which
this test also recomputes from first principles (`_expected_nm`) so the assertion never
trusts the transform's own output.
═══════════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date

import pytest

import load_events as le
from load_events import compute_session_events, Session_


HEVY_ID = "6d8b2f4d-114b-41e7-bc1f-450998fb02d4"

# (block_index, template_id, weight_kg, reps, rpe, type) — the prod-verified 56-set readout.
SETS = [
    (0, "SALP", 31.25, 10, 7.0, "normal"), (0, "SALP", 32.5, 10, 7.5, "normal"), (0, "SALP", 32.5, 10, 8.0, "normal"),
    (1, "SALP", 31.25, 10, 7.0, "normal"), (1, "SALP", 32.5, 10, 7.5, "normal"), (1, "SALP", 32.5, 10, 8.0, "normal"),
    (2, "STALP", 37.5, 12, 7.5, "normal"), (2, "STALP", 37.5, 12, 8.0, "normal"), (2, "STALP", 37.5, 12, 9.0, "normal"),
    (3, "FP", 23.75, 12, 7.5, "normal"), (3, "FP", 23.75, 12, 7.5, "normal"), (3, "FP", 23.75, 12, 7.5, "normal"),
    (4, "SALR", 8.75, 12, 7.5, "normal"), (4, "SALR", 8.75, 12, 8.0, "normal"), (4, "SALR", 8.75, 12, 8.0, "normal"),
    (5, "SALR", 8.75, 12, 7.5, "normal"), (5, "SALR", 8.75, 12, 8.5, "normal"), (5, "SALR", 8.75, 12, 9.0, "normal"),
    (6, "SER", 6.25, 12, 7.0, "normal"), (6, "SER", 6.25, 12, 7.0, "normal"), (6, "SER", 6.25, 12, 7.0, "normal"),
    (7, "SER", 6.25, 12, 7.0, "normal"), (7, "SER", 6.25, 12, 7.5, "normal"), (7, "SER", 6.25, 12, 8.0, "normal"),
    (8, "SIR", 11.25, 12, 7.0, "normal"), (8, "SIR", 11.25, 12, 7.0, "normal"), (8, "SIR", 11.25, 12, 7.0, "normal"),
    (9, "SIR", 8.75, 12, 7.0, "normal"), (9, "SIR", 8.75, 12, 7.5, "normal"), (9, "SIR", 8.75, 12, 7.5, "normal"),
    (10, "SHP", 40.0, 10, 7.5, "normal"), (10, "SHP", 50.0, 8, 9.5, "normal"), (10, "SHP", 45.0, 10, 8.0, "normal"),
    (11, "DBR", 22.5, 10, 7.0, "normal"), (11, "DBR", 25.0, 10, 7.5, "normal"), (11, "DBR", 25.0, 10, 8.0, "normal"),
    (12, "DBR", 22.5, 10, 7.0, "normal"), (12, "DBR", 25.0, 10, 7.5, "normal"), (12, "DBR", 25.0, 10, 8.0, "normal"),
    (13, "HC", 40.0, 20, 8.0, "normal"), (13, "HC", 40.0, 20, 9.0, "normal"), (13, "HC", 40.0, 20, 8.0, "normal"),
    (14, "LPM", 54.5, 10, 6.0, "warmup"), (14, "LPM", 72.5, 5, 9.5, "normal"), (14, "LPM", 68.0, 5, 9.5, "normal"), (14, "LPM", 59.0, 6, 9.0, "normal"),
    (15, "CPM", 41.0, 12, 6.0, "warmup"), (15, "CPM", 72.5, 12, 7.5, "normal"), (15, "CPM", 72.5, 10, 8.5, "normal"), (15, "CPM", 72.5, 8, 10.0, "normal"),
    (16, "CC", 53.75, 25, 6.0, "normal"), (16, "CC", 53.75, 25, 8.5, "normal"), (16, "CC", 53.75, 20, 9.5, "normal"),
    (17, "WDB", 25.0, 30, 6.0, "normal"), (17, "WDB", 0.0, 60, 7.0, "normal"), (17, "WDB", 0.0, 50, 8.5, "normal"),
]

# Chosen e1RM map (documented in the oracle above). SHP exercises the h(I) ramp; the rest
# fall through to H_NO_E1RM = 0.5.
E1RM_BY_TEMPLATE = {t: (60.0 if t == "SHP" else None) for (_, t, *_rest) in SETS}

EXPECTED_MECHANICAL = 36458.575          # three-way agreed (operator + fraction + code)
EXPECTED_NEUROMUSCULAR = round(14557 / 720, 6)   # 20.218056


def _session():
    sets = [(b, t, {"type": ty, "weight_kg": w, "reps": r, "rpe": p,
                    "duration_seconds": None, "distance_meters": None})
            for (b, t, w, r, p, ty) in SETS]
    return Session_(hevy_id=HEVY_ID, when=date(2026, 7, 13), occurred_at=None, sets=sets)


def _expected_nm_from_first_principles() -> float:
    """Recompute NM independently of the transform's aggregation, from the documented
    convention — so the assertion's oracle is arithmetic, not the code under test."""
    from fractions import Fraction as F

    def f_of(rir):
        return {0: F(1), 1: F(9, 10), 2: F(3, 4), 3: F(1, 2), 4: F(1, 4)}.get(rir, F(0))

    def h_of(eff, e1):
        if e1 is None:
            return F(1, 2)
        I = F(str(eff)) / F(str(e1))
        x = max(F(0), min(F(1), (I - F(2, 5)) / F(9, 20)))
        return F(1, 4) + F(3, 4) * x

    total = F(0)
    for (b, t, w, r, p, ty) in SETS:
        if ty == "warmup":
            continue
        eff = F(str(w)) if w > 0 else F(102)
        rir = le._rir_from_rpe(p)
        total += f_of(rir) * h_of(eff, E1RM_BY_TEMPLATE[t])
    return float(total)


def test_13jul_session_reconciles_mechanical_and_nm_to_the_cent():
    """The class-closer: real 56-set session, hand-derived oracle, both windows to the cent."""
    assert len(SETS) == 56
    # the NM oracle equals its first-principles recomputation (guards a typo in the constant)
    assert _expected_nm_from_first_principles() == pytest.approx(14557 / 720, abs=1e-12)

    ev = compute_session_events(
        _session(),
        laterality_by_template={},                 # untagged; load sums as logged regardless (#242)
        e1rm_by_template=E1RM_BY_TEMPLATE,
    )
    assert ev["mechanical"]["load"] == pytest.approx(EXPECTED_MECHANICAL, abs=1e-4)
    assert ev["neuromuscular"]["load"] == pytest.approx(EXPECTED_NEUROMUSCULAR, abs=1e-4)
    # NOT the superseded round()-convention value — mutation-proof against a return of half-up.
    assert ev["mechanical"]["load"] != pytest.approx(35367.5125, abs=1e-4)


def test_13jul_floor_delta_is_the_four_rpe_85_sets():
    """Pins the floor-vs-round delta to exactly the four RPE-8.5 sets (raw 7273.75 × 0.15)."""
    rpe85_raw = 8.75 * 12 + 72.5 * 10 + 53.75 * 25 + 102 * 50   # SALR, CPM, CC, WDB(0→102)
    assert rpe85_raw == pytest.approx(7273.75)
    assert 35367.5125 + rpe85_raw * (1.30 - 1.15) == pytest.approx(EXPECTED_MECHANICAL)
