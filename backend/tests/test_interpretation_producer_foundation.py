"""Foundation producer (4a) — the §2 worked example as conformance oracle,
plus the boundary and non-vacuity gates.

ORACLE PROVENANCE (read before trusting this): the corrected §2 object lives in
INTERPRETATION_OUTPUT_CONTRACT.md, a UI-maintained knowledge file that is NOT in
the repo. tests/fixtures/interpretation_s2.json is the §2 worked example as
carried on feat/interpretation-view-skeleton — the same object, whose MECHANICAL
4a fields (current/prior/delta/gates) are stable across the 4b correction (the
correction touches the interpretive layer; the brief itself states raw-news ==
final-news for every member here). If the corrected contract file later diverges
on a mechanical field, this fixture must be re-synced.

TWO DOCUMENTED DIVERGENCES of the 4a producer output from the fixture object,
asserted explicitly rather than glossed:
  (1) vitamin_d_25oh is a group-of-one in the 4b fixture, but marker_groups.json
      authors no vitamin-D group, so 4a emits it FLAT in ungrouped[] (the brief's
      step 7; synthesising a group would author new marker_groups content, which
      the GUARD forbids).
  (2) testosterone_total's min_meaningful_delta is 0.20 in the fixture but 0.30
      from the producer — lever_dictionary has no testosterone_total entry, so it
      takes the _defaults fallback (0.30). The magnitude verdict is within_noise
      under either, so no gate moves; the producer emits what the asset says and
      invents no CVi.
"""
import json
from datetime import date
from pathlib import Path

import models
from interpretation.producer import build_foundation
from reads.labs_reads import marker_series

_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "interpretation_s2.json").read_text(encoding="utf-8"))

_PRIOR = date(2026, 1, 7)
_CURRENT = date(2026, 5, 30)
_VITD = date(2025, 12, 27)

# 4b fields the foundation must never emit.
_FOUR_B_MEMBER_FIELDS = ["axis_verdict", "relations_rendered", "shared_levers",
                         "member_lever_effects", "mechanism", "stable_rationale"]
_FOUR_B_GROUP_FIELDS = ["axis_verdict", "relations_rendered", "shared_levers"]


def _make_user(db, email):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_report(db, user_id, collected_date, panel_name="Panel", confidence=0.97):
    report = models.LabReport(
        user_id=user_id, lab_name="Test Lab", panel_name_raw=panel_name,
        collected_date=collected_date, source_completeness="unknown",
        source="file_extraction", overall_confidence=confidence,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _make_result(db, report_id, marker_name_raw, marker_canonical, value_num=None,
                 value_operator=None, unit_canonical=None, ref_low=None, ref_high=None,
                 ref_low_exclusive=False, ref_high_exclusive=False, lab_flag=None,
                 computed_flag=None, is_derived=False):
    result = models.LabResult(
        lab_report_id=report_id, marker_name_raw=marker_name_raw,
        marker_canonical=marker_canonical, is_derived=is_derived, value_num=value_num,
        value_operator=value_operator, unit_canonical=unit_canonical, ref_low=ref_low,
        ref_high=ref_high, ref_low_exclusive=ref_low_exclusive,
        ref_high_exclusive=ref_high_exclusive, lab_flag=lab_flag,
        computed_flag=computed_flag, confidence=1.0,
    )
    db.add(result)
    db.commit()
    return result


def _seed_fixture(db, email):
    """Reproduces the §2 worked example's current/prior readings exactly."""
    user = _make_user(db, email)
    prior = _make_report(db, user.id, _PRIOR, panel_name="Androgens")
    current = _make_report(db, user.id, _CURRENT, panel_name="Gonadal Hormones")
    vitd = _make_report(db, user.id, _VITD, panel_name="Vitamin D")

    _make_result(db, prior.id, "Testosterone (total)", "testosterone_total",
                 value_num=22.5, unit_canonical="nmol/L", ref_low=10.0, ref_high=30.0)
    _make_result(db, current.id, "Testosterone (total)", "testosterone_total",
                 value_num=24.0, unit_canonical="nmol/L", ref_low=10.0, ref_high=30.0)

    _make_result(db, prior.id, "Oestradiol", "oestradiol",
                 value_num=110.0, unit_canonical="pmol/L", ref_high=165.0)
    _make_result(db, current.id, "Oestradiol", "oestradiol",
                 value_num=141.0, unit_canonical="pmol/L", ref_high=165.0)

    _make_result(db, prior.id, "FSH", "fsh", value_num=0.1, value_operator="<",
                 unit_canonical="IU/L", ref_low=1.5, ref_high=12.4, lab_flag="L")
    _make_result(db, current.id, "FSH", "fsh", value_num=0.1, value_operator="<",
                 unit_canonical="IU/L", ref_low=1.5, ref_high=12.4, lab_flag="L")

    _make_result(db, prior.id, "AST", "ast", value_num=47.0,
                 unit_canonical="U/L", ref_high=40.0, lab_flag="H")
    _make_result(db, current.id, "AST", "ast", value_num=32.0,
                 unit_canonical="U/L", ref_high=40.0)

    _make_result(db, vitd.id, "25-OH Vitamin D", "vitamin_d_25oh", value_num=90.0,
                 unit_canonical="nmol/L", ref_low=50.0, ref_high=150.0)

    return user, current, prior


def _build(db, user, current, prior):
    return build_foundation(user.id, db, trigger_panel=current, prior_panel=prior)


def _row(out, marker):
    """Locate a marker's row anywhere in the output — in a group's members or
    in ungrouped[]."""
    for group in out["groups"]:
        for m in group["members"]:
            if m["marker_canonical"] == marker:
                return m
    for r in out["ungrouped"]:
        if r["marker_canonical"] == marker:
            return r
    raise AssertionError(f"{marker} not found in output")


def _group(out, key):
    return next(g for g in out["groups"] if g["group_key"] == key)


def _fixture_member(group_key, marker):
    g = next(g for g in _FIXTURE["groups"] if g["group_key"] == group_key)
    return next(m for m in g["members"] if m["marker_canonical"] == marker)


# ---------- G3 oracle: current / prior readings ----------

def test_oracle_readings_match_the_fixture(db_session):
    user, current, prior = _seed_fixture(db_session, "read@example.com")
    out = _build(db_session, user, current, prior)

    # Group display_name is producer-emitted from marker_groups.json. It was a
    # silent oracle gap — asserted nowhere — which let the asset's
    # "Hepatobiliary enzymes + bilirubin" diverge from the fixture unnoticed.
    # Assert it for BOTH authored groups against the fixture.
    for group_key in ("hpg_axis", "hepatocellular"):
        fixture_group = next(g for g in _FIXTURE["groups"] if g["group_key"] == group_key)
        assert _group(out, group_key)["display_name"] == fixture_group["display_name"], \
            f"{group_key}.display_name"

    for group_key, marker in [("hpg_axis", "testosterone_total"), ("hpg_axis", "oestradiol"),
                              ("hpg_axis", "fsh"), ("hepatocellular", "ast")]:
        fm = _fixture_member(group_key, marker)
        row = _row(out, marker)
        for field in ("value_num", "unit_canonical", "ref_low", "ref_high", "flag", "collected"):
            assert row["current"][field] == fm["current"][field], f"{marker}.current.{field}"
        if fm.get("prior") is not None:
            for field in ("value_num", "ref_low", "ref_high", "flag", "collected"):
                assert row["prior"][field] == fm["prior"][field], f"{marker}.prior.{field}"


# ---------- G3 oracle: delta ----------

def test_oracle_delta_matches_the_fixture(db_session):
    user, current, prior = _seed_fixture(db_session, "delta@example.com")
    out = _build(db_session, user, current, prior)

    for group_key, marker in [("hpg_axis", "testosterone_total"), ("hpg_axis", "oestradiol"),
                              ("hpg_axis", "fsh"), ("hepatocellular", "ast")]:
        fm = _fixture_member(group_key, marker)
        d = _row(out, marker)["delta"]
        for field in ("direction", "abs_change", "pct_change", "crossed_ref", "magnitude", "censored"):
            assert d[field] == fm["delta"][field], f"{marker}.delta.{field}: {d[field]} != {fm['delta'][field]}"


def test_min_meaningful_delta_is_asset_derived(db_session):
    """Divergence (2): T takes the 0.30 fallback (no lever_dictionary entry),
    NOT the fixture's authored 0.20. E2 and AST agree with the asset. Censored
    FSH omits the key entirely (no numeric change to threshold)."""
    user, current, prior = _seed_fixture(db_session, "mmd@example.com")
    out = _build(db_session, user, current, prior)

    assert _row(out, "testosterone_total")["delta"]["min_meaningful_delta"] == {"mode": "relative", "value": 0.3}
    assert _row(out, "oestradiol")["delta"]["min_meaningful_delta"] == {"mode": "relative", "value": 0.42}
    assert _row(out, "ast")["delta"]["min_meaningful_delta"] == {"mode": "relative", "value": 0.3}
    assert "min_meaningful_delta" not in _row(out, "fsh")["delta"]  # censored


# ---------- G3 oracle: gates ----------

def test_oracle_news_and_range_gates_match_the_fixture(db_session):
    """Raw gate-1 is_news equals the fixture exactly here (no relation demotion
    is exercised); range_gate matches lab-flag-for-flag."""
    user, current, prior = _seed_fixture(db_session, "gate@example.com")
    out = _build(db_session, user, current, prior)

    for group_key, marker in [("hpg_axis", "testosterone_total"), ("hpg_axis", "oestradiol"),
                              ("hpg_axis", "fsh"), ("hepatocellular", "ast")]:
        fm = _fixture_member(group_key, marker)
        row = _row(out, marker)
        assert row["news_gate"]["is_news"] == fm["news_gate"]["is_news"], f"{marker}.is_news"
        assert row["range_gate"]["is_out_of_range"] == fm["range_gate"]["is_out_of_range"], f"{marker}.oor"
        assert row["range_gate"]["flag"] == fm["range_gate"]["flag"], f"{marker}.flag"


def test_fsh_breach_is_the_only_hpg_breach_and_carries_no_phase_fields(db_session):
    user, current, prior = _seed_fixture(db_session, "fsh@example.com")
    out = _build(db_session, user, current, prior)
    fsh = _row(out, "fsh")

    assert fsh["range_gate"] == {"is_out_of_range": True, "flag": "L"}
    assert "expected_by_phase" not in fsh["range_gate"]
    assert "note" not in fsh["range_gate"]
    assert fsh["news_gate"] == {"is_news": False, "basis": ["flat_vs_prior"]}


def test_ast_is_news_via_crossed_ref_but_not_a_breach(db_session):
    user, current, prior = _seed_fixture(db_session, "ast@example.com")
    ast = _row(_build(db_session, user, current, prior), "ast")

    assert ast["delta"]["crossed_ref"] == "into_range"
    assert ast["news_gate"] == {"is_news": True, "basis": ["crossed_ref_into_range", "delta_meaningful"]}
    assert ast["range_gate"]["is_out_of_range"] is False


# ---------- G3 / G6: should_surface and section placement ----------

def test_should_surface_hpg_on_the_fsh_breach_alone(db_session):
    """Gate 2 independently load-bearing: nothing in hpg is news, yet it moves."""
    user, current, prior = _seed_fixture(db_session, "moved1@example.com")
    hpg = _group(_build(db_session, user, current, prior), "hpg_axis")

    assert hpg["should_surface"] is True
    assert not any(m["news_gate"]["is_news"] for m in hpg["members"])
    assert [m["marker_canonical"] for m in hpg["members"] if m["range_gate"]["is_out_of_range"]] == ["fsh"]


def test_should_surface_hepatocellular_on_ast_news_alone(db_session):
    """Gate 1 independently load-bearing: nothing in hepatocellular is out of
    range, yet it moves."""
    user, current, prior = _seed_fixture(db_session, "moved2@example.com")
    hep = _group(_build(db_session, user, current, prior), "hepatocellular")

    assert hep["should_surface"] is True
    assert not any(m["range_gate"]["is_out_of_range"] for m in hep["members"])
    assert [m["marker_canonical"] for m in hep["members"] if m["news_gate"]["is_news"]] == ["ast"]


def test_vitamin_d_is_ungrouped_stable_not_a_group(db_session):
    """Divergence (1): vitamin D is not in an authored group, so 4a emits it
    flat in ungrouped[], tagged, with no group / no axis_verdict. It is stable
    (not news, not breached)."""
    user, current, prior = _seed_fixture(db_session, "vitd@example.com")
    out = _build(db_session, user, current, prior)

    assert "vitamin_d_25oh" not in {g["group_key"] for g in out["groups"]}
    vd = next(r for r in out["ungrouped"] if r["marker_canonical"] == "vitamin_d_25oh")
    assert vd["ungrouped"] is True
    assert "axis_verdict" not in vd
    assert vd["delta"] is None
    assert vd["news_gate"] == {"is_news": False, "basis": ["no_prior_first_observation"]}
    assert vd["range_gate"] == {"is_out_of_range": False, "flag": None}


def test_all_stable_group_does_not_surface(db_session):
    """G6 non-vacuity: should_surface is NOT hardwired true. A group whose members
    are all in-range, non-news and in no safety band reports should_surface False — a `should_surface≡True`
    mutation fails here (the §2 fixture alone cannot catch it, since both its
    authored groups move)."""
    user = _make_user(db_session, "stable@example.com")
    prior = _make_report(db_session, user.id, _PRIOR)
    current = _make_report(db_session, user.id, _CURRENT)
    # AST + ALT, both flat and in range: no news, no breach.
    _make_result(db_session, prior.id, "AST", "ast", value_num=20.0, ref_high=40.0)
    _make_result(db_session, current.id, "AST", "ast", value_num=20.0, ref_high=40.0)
    _make_result(db_session, prior.id, "ALT", "alt", value_num=25.0, ref_high=45.0)
    _make_result(db_session, current.id, "ALT", "alt", value_num=25.0, ref_high=45.0)

    hep = _group(build_foundation(user.id, db_session, current, prior), "hepatocellular")
    assert hep["should_surface"] is False


# ---------- G3 boundary: 4b fields absent ----------

def test_producer_emits_no_4b_fields_though_the_fixture_carries_them(db_session):
    """The fixture proves these fields EXIST (asserted below), so their absence
    in the producer output is the projection dropping them, not a vacuous pass."""
    g0 = _FIXTURE["groups"][0]
    assert "axis_verdict" in g0 and "shared_levers" in g0
    assert "relations_rendered" in g0["members"][0] and "mechanism" in g0["members"][0]

    user, current, prior = _seed_fixture(db_session, "boundary@example.com")
    out = _build(db_session, user, current, prior)

    assert out["groups"], "fixture seeds two authored groups — an empty result would pass vacuously"
    for group in out["groups"]:
        for field in _FOUR_B_GROUP_FIELDS:
            assert field not in group, f"{group['group_key']} leaked {field}"
        for member in group["members"]:
            for field in _FOUR_B_MEMBER_FIELDS:
                assert field not in member, f"{member['marker_canonical']} leaked {field}"
    for row in out["ungrouped"]:
        for field in _FOUR_B_MEMBER_FIELDS:
            assert field not in row, f"ungrouped {row['marker_canonical']} leaked {field}"


def test_meta_is_phase_free_and_names_both_panels(db_session):
    user, current, prior = _seed_fixture(db_session, "meta@example.com")
    meta = _build(db_session, user, current, prior)["meta"]

    assert "protocol_context_snapshot" not in meta  # carries phase -> 4b
    assert meta["trigger_panel"] == {"panel_name_raw": "Gonadal Hormones", "collected": "2026-05-30"}
    assert meta["compared_against"] == {"panel_name_raw": "Androgens", "collected": "2026-01-07"}
    assert meta["first_ever_panel"] is False
    assert meta["regulatory_mode"] == "education"
    assert meta["lever_dictionary_version"] == "v0"
    assert meta["marker_groups_version"] == "v0"
    assert meta["overall_extraction_confidence"] == 0.97
    assert meta["generated_at"].startswith("20")  # ISO timestamp present


def test_first_ever_panel_true_when_no_prior_panel(db_session):
    user = _make_user(db_session, "first@example.com")
    current = _make_report(db_session, user.id, _CURRENT)
    _make_result(db_session, current.id, "AST", "ast", value_num=20.0, ref_high=40.0)

    meta = build_foundation(user.id, db_session, current, None)["meta"]
    assert meta["first_ever_panel"] is True
    assert meta["compared_against"] is None


# ---------- G5: gate-2 source is lab_flag, not computed_flag ----------

def test_range_gate_reads_lab_flag_not_computed_flag(db_session):
    """G5: computed_flag is withheld (V2). A row flagged H by COMPUTATION only
    must NOT read out of range; a row flagged H by the LAB must."""
    user = _make_user(db_session, "g5@example.com")
    current = _make_report(db_session, user.id, _CURRENT)
    # computed_flag H, lab_flag absent -> NOT a breach (computed is withheld)
    _make_result(db_session, current.id, "AST", "ast", value_num=99.0, ref_high=40.0,
                 lab_flag=None, computed_flag="H")
    # lab_flag H -> a breach
    _make_result(db_session, current.id, "ALT", "alt", value_num=99.0, ref_high=45.0, lab_flag="H")

    out = build_foundation(user.id, db_session, current, None)
    assert _row(out, "ast")["range_gate"] == {"is_out_of_range": False, "flag": None}
    assert _row(out, "alt")["range_gate"] == {"is_out_of_range": True, "flag": "H"}


# ---------- G6: non-vacuity of magnitude and crossed_ref ----------

def test_magnitude_is_mode_aware_not_raw_pct(db_session):
    """G6: E2 moves 28.2% against a 0.42 RELATIVE threshold -> marginal. A
    mode-blind check comparing 28.2 against 0.42 would call it meaningful."""
    user, current, prior = _seed_fixture(db_session, "mode@example.com")
    e2 = _row(_build(db_session, user, current, prior), "oestradiol")
    assert e2["delta"]["magnitude"] == "marginal"
    assert e2["news_gate"]["is_news"] is False


def test_crossed_out_of_range_direction(db_session):
    """The fixture only carries into_range; the opposite transition must read
    out_of_range (and be news)."""
    user = _make_user(db_session, "out@example.com")
    prior = _make_report(db_session, user.id, _PRIOR)
    current = _make_report(db_session, user.id, _CURRENT)
    _make_result(db_session, prior.id, "ALT", "alt", value_num=30.0, ref_high=45.0)
    _make_result(db_session, current.id, "ALT", "alt", value_num=60.0, ref_high=45.0, lab_flag="H")

    alt = _row(build_foundation(user.id, db_session, current, prior), "alt")
    assert alt["delta"]["crossed_ref"] == "out_of_range"
    assert alt["news_gate"]["is_news"] is True


def test_censored_value_emits_no_abs_or_pct(db_session):
    user, current, prior = _seed_fixture(db_session, "cens@example.com")
    fsh = _row(_build(db_session, user, current, prior), "fsh")
    assert fsh["delta"]["censored"] is True
    assert fsh["delta"]["abs_change"] is None
    assert fsh["delta"]["pct_change"] is None


# ---------- ungrouped assembly ----------

def test_every_ungrouped_marker_is_tagged_and_flat(db_session):
    user = _make_user(db_session, "ung@example.com")
    current = _make_report(db_session, user.id, _CURRENT)
    _make_result(db_session, current.id, "AST", "ast", value_num=20.0, ref_high=40.0)  # grouped
    _make_result(db_session, current.id, "Sodium", "sodium", value_num=140.0, ref_low=135.0, ref_high=145.0)
    _make_result(db_session, current.id, "25-OH Vitamin D", "vitamin_d_25oh", value_num=90.0,
                 ref_low=50.0, ref_high=150.0)

    out = build_foundation(user.id, db_session, current, None)
    ungrouped_keys = {r["marker_canonical"] for r in out["ungrouped"]}
    assert ungrouped_keys == {"sodium", "vitamin_d_25oh"}
    assert all(r["ungrouped"] is True for r in out["ungrouped"])
    # grouped markers never appear in ungrouped[]
    assert "ast" not in ungrouped_keys


def test_zero_data_group_is_omitted(db_session):
    user = _make_user(db_session, "zero@example.com")
    current = _make_report(db_session, user.id, _CURRENT)
    _make_result(db_session, current.id, "AST", "ast", value_num=20.0, ref_high=40.0)

    keys = {g["group_key"] for g in build_foundation(user.id, db_session, current, None)["groups"]}
    assert keys == {"hepatocellular"}  # hpg omitted — no members present


# ---------- the marker_series seam ----------

def test_marker_series_returns_newest_and_prior(db_session):
    user = _make_user(db_session, "series@example.com")
    r1 = _make_report(db_session, user.id, date(2026, 1, 1))
    r2 = _make_report(db_session, user.id, date(2026, 3, 1))
    r3 = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, r1.id, "Sodium", "sodium", value_num=138.0)
    _make_result(db_session, r2.id, "Sodium", "sodium", value_num=140.0)
    _make_result(db_session, r3.id, "Sodium", "sodium", value_num=141.0)

    series = marker_series(user.id, db_session)
    assert series["sodium"].current.value_num == 141.0
    assert series["sodium"].prior.value_num == 140.0  # second-newest, not oldest


def test_marker_series_prior_none_on_first_observation(db_session):
    user = _make_user(db_session, "series2@example.com")
    r1 = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, r1.id, "Sodium", "sodium", value_num=141.0)
    assert marker_series(user.id, db_session)["sodium"].prior is None


def test_marker_series_isolates_users(db_session):
    a = _make_user(db_session, "sa@example.com")
    b = _make_user(db_session, "sb@example.com")
    ra = _make_report(db_session, a.id, date(2026, 6, 1))
    rb = _make_report(db_session, b.id, date(2026, 6, 1))
    _make_result(db_session, ra.id, "Sodium", "sodium", value_num=138.0)
    _make_result(db_session, rb.id, "Sodium", "sodium", value_num=999.0)

    series = marker_series(a.id, db_session)
    assert len(series) == 1 and series["sodium"].current.value_num == 138.0
