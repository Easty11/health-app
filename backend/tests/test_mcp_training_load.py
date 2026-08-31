"""The `get_training_load` MCP tool — a thin text formatter over the metabolic lane of
`load_metrics` (`metab-v1` / `banister-v1`, window `metabolic`).

The legacy aerobic acute:chronic ratio (ACWR) readout was retired in #255 once the
Metabolic→load_events transform landed (#251, the trigger #249 named). The tool now serves
the Banister metabolic lane — window-native Edwards TRIMP plus the acute/chronic trace —
with NO acute:chronic ratio and NO sweet-spot band verdict (#18: dosing never used ACWR;
the readout≠dosing boundary closes with the readout gone).

These target the pure formatter `_format_training_load` over the shape `_db_rows` returns
(the `@mcp.tool()` wrapper adds only `_current_user_id()` + the metabolic-lane query, which
need a live bearer token and are not the logic under test). Mirrors `test_mcp_lab_results`.
"""
from mcp_server import _format_training_load


def _row(**kw):
    """A load_metrics metabolic-lane row as `_db_rows` returns it (column-keyed dict)."""
    base = dict(
        day="2026-08-30", daily_load=120.0, fitness=880.0, fatigue=430.0, form=450.0,
        acute_load=110.0, chronic_load=95.0, maturity="ok", unit="trimp_edw_au",
    )
    base.update(kw)
    return base


def test_latest_row_renders_trimp_and_acute_chronic_trace():
    out = _format_training_load([_row()])
    assert "METABOLIC TRAINING LOAD (Banister)" in out
    assert "2026-08-30" in out
    assert "120.0 trimp_edw_au" in out          # window-native Edwards TRIMP
    assert "Acute (7d mean):    110.0" in out    # acute trace value
    assert "Chronic (28d mean): 95.0" in out     # chronic trace value
    assert "Form:               450.0" in out
    assert "Maturity:           ok" in out


def test_no_ratio_and_no_sweet_spot_band_language():
    """G3 as an executable assertion: no legacy-ratio computation or band verdict remains."""
    out = _format_training_load([_row()]).lower()
    assert "acwr" not in out
    assert "sweet spot" not in out
    assert "sweet-spot" not in out
    assert "injury risk" not in out
    assert "proceed with planned training" not in out
    # No acute:chronic RATIO is served — only the two trace values, never their quotient.
    assert "ratio:" not in out


def test_only_latest_day_is_served():
    rows = [_row(day="2026-08-30", daily_load=120.0), _row(day="2026-08-29", daily_load=88.0)]
    out = _format_training_load(rows)
    assert "2026-08-30" in out
    assert "120.0 trimp_edw_au" in out
    assert "2026-08-29" not in out
    assert "88.0" not in out


def test_empty_metabolic_lane_is_a_clean_no_data_readout():
    out = _format_training_load([])
    assert "No metabolic load metrics yet." in out
    assert "metab-v1 / banister-v1" in out
    assert "acwr" not in out.lower()
