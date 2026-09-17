"""Drift guard for `docs/load-constants-provenance.md` (DECISIONS_LOG #305).

The standing rule: every coefficient in the three load modules has exactly one row in the
provenance table. This test enforces set-equality, per module, between:

  * the table's `constant` column (parsed from the markdown), and
  * the module's own `UPPER_CASE` module-level constants bound to int/float/dict/tuple
    (auto-collected — a NEW such constant added without a row fails here, naming it),
    PLUS an explicit allow-list of the function-embedded / derived coefficients (band
    tables, h(I) terms, the Epley and TRIMP divisors, the banister-v4 seed window) that a
    name scan cannot see.

Auto-collection catches the common drift (a new module-level prior lands unlabelled). The
allow-list is bookkeeping the table and this file keep in step — a function-embedded
coefficient added or removed must change both. Version-key / label strings
(`FORMULA_VERSION`, `WINDOW_*`, `UNIT_*`, `METRICS_VERSION`) are excluded by the
int/float/dict/tuple type filter — they are keys the table is versioned under, not rows.

Import-only: no DB session. The modules import under the suite's CI env vars (FERNET_KEY
etc.); nothing here touches Postgres.
"""
from __future__ import annotations

import re
from pathlib import Path

import load_events
import load_events_metabolic
import load_metrics

_DOC = Path(__file__).resolve().parents[1].parent / "docs" / "load-constants-provenance.md"

_MODULES = {
    "load_events": load_events,
    "load_events_metabolic": load_events_metabolic,
    "load_metrics": load_metrics,
}

# Function-embedded / derived coefficients that a module-level name scan cannot see. Keyed
# by module; the spelling MUST match the table's `constant` column exactly. Adding or
# removing one of these in code changes both the table row and this allow-list.
_ALLOW = {
    "load_events": {
        "_mech_mult (bands)", "_f_rir (table)", "_nm_reps_prior (bands)",
        "_h_intensity.base", "_h_intensity.span", "_h_intensity.I0", "_h_intensity.width",
        "Epley divisor",
    },
    "load_events_metabolic": {"TRIMP minute divisor"},
    "load_metrics": {"seed_window (banister-v4)"},
}


def _module_constants(mod) -> set[str]:
    """UPPER_CASE module-level names bound to int/float/dict/tuple (not bool, not str).

    `str.isupper()` with the leading-underscore guard keeps `BODYWEIGHT_KG`,
    `E1RM_WINDOW_DAYS`, `ZONES` and rejects `logger`, `_AEST`, dunders. The type filter drops
    the version-key and label strings. Imported UPPER_CASE numerics would leak in principle,
    but none exist across these three modules' imports (asserted by the set-equality below —
    a leak would show as an untabled extra and fail loudly)."""
    out: set[str] = set()
    for name, val in vars(mod).items():
        if name.startswith("_") or not name.isupper():
            continue
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float, dict, tuple)):
            out.add(name)
    return out


def _table_rows_by_module() -> dict[str, set[str]]:
    """Parse the provenance table: {module: {constant, ...}} from its first two columns."""
    text = _DOC.read_text(encoding="utf-8")
    by_mod: dict[str, set[str]] = {m: set() for m in _MODULES}
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        constant, module = cells[0], cells[1]
        if constant in ("constant", "") or set(constant) <= {"-", ":"}:
            continue  # header / separator
        constant = constant.strip("`").strip()
        if module in by_mod:
            by_mod[module].add(constant)
    return by_mod


def test_provenance_doc_exists_and_nonempty():
    assert _DOC.exists(), f"provenance table missing at {_DOC}"
    assert _DOC.read_text(encoding="utf-8").strip(), "provenance table is empty"


def test_every_constant_has_a_row_and_every_row_names_a_constant():
    table = _table_rows_by_module()
    for mod_name, mod in _MODULES.items():
        expected = _module_constants(mod) | _ALLOW[mod_name]
        actual = table[mod_name]

        missing_rows = expected - actual          # a constant in code with no table row
        stale_rows = actual - expected            # a table row naming nothing that exists

        assert not missing_rows, (
            f"{mod_name}: these coefficients have NO row in "
            f"docs/load-constants-provenance.md — add one each: {sorted(missing_rows)}"
        )
        assert not stale_rows, (
            f"{mod_name}: these table rows name nothing in the module (deleted constant or "
            f"typo) — remove or fix: {sorted(stale_rows)}"
        )


def test_allow_list_entries_are_really_function_embedded():
    """Guard against the allow-list quietly absorbing a real module-level constant (which
    would dodge auto-collection). No allow-list key may also be a module-level UPPER_CASE
    constant."""
    for mod_name, mod in _MODULES.items():
        overlap = _ALLOW[mod_name] & _module_constants(mod)
        assert not overlap, (
            f"{mod_name}: allow-list entries shadow real module constants "
            f"(auto-collect those instead): {sorted(overlap)}"
        )
