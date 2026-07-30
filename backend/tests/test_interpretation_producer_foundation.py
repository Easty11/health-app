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

# Fields asserted ABSENT from every group / member.
#
# `_HELD_MEMBER_FIELDS` NO LONGER CONTAINS A GENUINE HOLD. Every member field in the
# contract is now emitted — stable_rationale + member_lever_effects (1a), mechanism (this
# increment), relations_rendered (4b-i). What is left are the two GROUP-level fields, kept
# here as the standing "a member never carries a group field" boundary check. Read the two
# lists together: `axis_verdict` in the GROUP list is the producer's one real remaining
# hold (#152 reduced it to {protocol_phase, text}; the projection still needs a
# source-factor rule and an authoring table); `shared_levers` appears ONLY in the member
# list because it is emitted at group level and must never leak onto a member.
_HELD_MEMBER_FIELDS = ["axis_verdict", "shared_levers"]
_HELD_GROUP_FIELDS = ["axis_verdict"]
# Ungrouped rows carry NO interpretive field — with no group, nothing in the
# interpretive layer attaches by construction. Defined EXPLICITLY, NOT derived from
# _HELD_MEMBER_FIELDS: as fields leave the held list on emission the ungrouped guard
# must not shrink with them, or a field emitted on grouped members could begin
# leaking onto ungrouped rows unnoticed.
_UNGROUPED_ABSENT_FIELDS = ["axis_verdict", "shared_levers", "member_lever_effects",
                            "mechanism", "stable_rationale", "relations_rendered"]


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


# ---------- 4a-G3 oracle: current / prior readings ----------

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


# ---------- 4a-G3 oracle: delta ----------

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


# ---------- 4a-G3 oracle: gates ----------

def test_oracle_news_and_range_gates_match_the_fixture(db_session):
    """Raw gate-1 is_news equals the fixture exactly here. Demotion exists but is not
    exercised on this panel — its feedback relation is `degraded` (the seed omits `lh`),
    which `test_news_gate_shape_and_no_unearned_demotion_on_the_s2_panel` pins explicitly;
    range_gate matches lab-flag-for-flag."""
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


# ---------- 4a-G3 / 4a-G6: should_surface and section placement ----------

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


# ---------- 4b-i-G7 boundary: relations_rendered emitted, held stays held ----------

def test_producer_emits_relations_rendered_but_holds_the_rest_of_4b(db_session):
    """The standing field-boundary check, tightened as fields landed.

    `relations_rendered` is a MEMBER field: emitted on grouped members, absent at group
    level, and absent from ungrouped rows (no group, no relations — by construction, not
    omission). The two remaining absence lists now mean different things: `axis_verdict` is
    the producer's one genuine hold (#152), while `shared_levers` is absent from MEMBERS
    only because it is emitted at GROUP level. The fixture proves both fields exist
    (asserted below), so their absence from the projection is real dropping, not a vacuous
    pass. `mechanism` left this check when it landed and is asserted positively in
    test_mechanism_is_emitted_per_member; it remains in _UNGROUPED_ABSENT_FIELDS."""
    g0 = _FIXTURE["groups"][0]
    assert "axis_verdict" in g0 and "shared_levers" in g0
    assert "relations_rendered" in g0["members"][0] and "mechanism" in g0["members"][0]

    user, current, prior = _seed_fixture(db_session, "boundary@example.com")
    out = _build(db_session, user, current, prior)

    assert out["groups"], "fixture seeds two authored groups — an empty result would pass vacuously"
    for group in out["groups"]:
        assert "relations_rendered" not in group, f"{group['group_key']} carries a member field at group level"
        for field in _HELD_GROUP_FIELDS:
            assert field not in group, f"{group['group_key']} leaked {field}"
        for member in group["members"]:
            assert "relations_rendered" in member, f"{member['marker_canonical']} missing relations_rendered"
            assert isinstance(member["relations_rendered"], list)
            for field in _HELD_MEMBER_FIELDS:
                assert field not in member, f"{member['marker_canonical']} leaked {field}"

    assert out["ungrouped"], "fixture seeds vitamin_d ungrouped — an empty list would pass vacuously"
    for row in out["ungrouped"]:
        for field in _UNGROUPED_ABSENT_FIELDS:
            assert field not in row, f"ungrouped {row['marker_canonical']} leaked {field}"


def test_stable_rationale_is_emitted_per_member(db_session):
    """1a shape gate. stable_rationale lands on every GROUPED member as a faithful
    projection of lever_dictionary.marker_interpretation[marker].stable_rationale —
    a reviewed string or null, never generated. Non-vacuous on BOTH branches: every
    §2-seed marker projects null, and a seeded bilirubin_total (hepatocellular member;
    the sole asset entry with a non-null rationale) projects the exact asset string.
    Ungrouped rows stay flat — guarded by _UNGROUPED_ABSENT_FIELDS in the boundary test."""
    ld = json.loads((_MARKER_GROUPS_JSON.parent / "lever_dictionary.json").read_text(encoding="utf-8"))
    bili_rationale = ld["marker_interpretation"]["bilirubin_total"]["stable_rationale"]
    assert isinstance(bili_rationale, str) and bili_rationale, \
        "asset must carry a non-null bilirubin_total rationale, else this test is vacuous"

    user, current, prior = _seed_fixture(db_session, "stablerat@example.com")
    _make_result(db_session, current.id, "Bilirubin (total)", "bilirubin_total",
                 value_num=22.0, unit_canonical="umol/L", ref_high=20.0, lab_flag="H")
    out = _build(db_session, user, current, prior)

    grouped = [m for g in out["groups"] for m in g["members"]]
    assert grouped, "seed authors groups — empty would pass vacuously"
    for m in grouped:
        assert "stable_rationale" in m, f"{m['marker_canonical']} missing stable_rationale"
        assert m["stable_rationale"] is None or isinstance(m["stable_rationale"], str), \
            f"{m['marker_canonical']}.stable_rationale wrong type"

    assert _row(out, "bilirubin_total")["stable_rationale"] == bili_rationale  # non-null projection
    assert _row(out, "ast")["stable_rationale"] is None                        # null projection


def test_mechanism_is_emitted_per_member(db_session):
    """1a-completion shape gate. `mechanism` lands on every GROUPED member as a faithful
    projection of `lever_dictionary.marker_interpretation[m].mechanism`, in the #152 shape
    `{text, protocol_factors_referenced}` — `confidence` is REMOVED from the output and its
    presence here would be a regression, so it is asserted absent.

    Non-vacuous: the asset text is read independently and compared per marker, so a producer
    that emitted a constant, an empty string, or a stale copy fails. Ungrouped rows stay
    flat (guarded by _UNGROUPED_ABSENT_FIELDS in the boundary test) — see Q64."""
    asset = json.loads((_MARKER_GROUPS_JSON.parent / "lever_dictionary.json")
                       .read_text(encoding="utf-8"))["marker_interpretation"]

    user, current, prior = _seed_fixture(db_session, "mech@example.com")
    out = _build(db_session, user, current, prior)

    grouped = [m for g in out["groups"] for m in g["members"]]
    assert grouped, "seed authors groups — empty would pass vacuously"
    for m in grouped:
        key = m["marker_canonical"]
        assert "mechanism" in m, f"{key} missing mechanism"
        mech = m["mechanism"]
        assert set(mech) == {"text", "protocol_factors_referenced"}, (key, sorted(mech))
        assert "confidence" not in mech, f"{key}: #152 removed mechanism.confidence"
        authored = asset[key]["mechanism"]
        assert mech["text"] == authored["text"], f"{key}: text is not the authored asset text"
        assert isinstance(mech["text"], str) and mech["text"].strip()
        assert mech["protocol_factors_referenced"] == authored["protocol_factors_referenced"]

    # the projection copies, so mutating output cannot corrupt the module-level asset
    grouped[0]["mechanism"]["protocol_factors_referenced"].append("mutated")
    again = _build(db_session, user, current, prior)
    fresh = next(m for g in again["groups"] for m in g["members"]
                 if m["marker_canonical"] == grouped[0]["marker_canonical"])
    assert "mutated" not in fresh["mechanism"]["protocol_factors_referenced"]


_GRADES = {"high", "moderate", "low", "very_low"}
_DIRS = {"raises", "lowers"}


def test_shared_levers_and_member_lever_effects_are_asset_projections(db_session):
    """1a I7 pair. shared_levers (group) + member_lever_effects (member) land together
    as deterministic projections of marker_groups.group_levers x lever_dictionary.levers.
    Assert shape + invariants, NEVER fixture-match (the fixture's status values pre-date
    #145 and are inverted).

    Invariants: I1 — every surfaced lever is cited (grade + rationale + non-empty refs);
    present-marker — member_effects non-empty and every marker is present in the panel;
    I7 — every lever a member names has a group-level shared_levers entry (same citation
    predicate drops a lever from both)."""
    user, current, prior = _seed_fixture(db_session, "levers@example.com")
    out = _build(db_session, user, current, prior)
    present = {m["marker_canonical"] for g in out["groups"] for m in g["members"]} | \
              {r["marker_canonical"] for r in out["ungrouped"]}

    assert out["groups"]
    for g in out["groups"]:
        assert isinstance(g["shared_levers"], list), g["group_key"]
        keys_here = {L["lever_key"] for L in g["shared_levers"]}
        for L in g["shared_levers"]:
            assert L["grade"] in _GRADES
            assert isinstance(L["grade_rationale"], str) and L["grade_rationale"]
            assert isinstance(L["evidence_refs"], list) and L["evidence_refs"], \
                f"{L['lever_key']} surfaced uncited (I1)"
            assert isinstance(L["label"], str) and isinstance(L["mechanism_summary"], str)
            assert L["status"] in {"surfaced", "already_in_play"}
            assert (L["already_in_play_reason"] is None) == (L["status"] == "surfaced")
            assert L["member_effects"], f"{L['lever_key']} surfaced with no present effect"
            for e in L["member_effects"]:
                assert e["marker_canonical"] in present, f"{L['lever_key']} effect on absent marker"
                assert e["direction"] in _DIRS and e["grade"] in _GRADES
        for m in g["members"]:
            assert isinstance(m["member_lever_effects"], list)
            for eff in m["member_lever_effects"]:
                assert eff["direction"] in _DIRS and eff["grade"] in _GRADES
                assert eff["lever_key"] in keys_here, \
                    f"{m['marker_canonical']} names lever {eff['lever_key']} absent from shared_levers (I7)"


def test_shared_levers_status_follows_declared_state_not_the_fixture(db_session):
    """#145 / Q57 (I3). A lever is `already_in_play` iff one of its declared_factor_keys
    is assumable-present; else `surfaced`. testosterone_substrate_load carries
    declared_factor_keys ["trt"]. Two branches:
      - no trt declared (the §2 seed) -> surfaced, reason null;
      - trt declared steady (assumable_present True) -> already_in_play, reason names trt.
    This is the exact INVERSE of the committed fixture (hand-authored, pre-#145) — proof
    the rule governs, not the fixture. A lever with empty declared_factor_keys stays
    surfaced even when trt is declared (present-and-empty is 'no factor represents me')."""
    def _tsl(user, c, p):
        hpg = _group(_build(db_session, user, c, p), "hpg_axis")
        return {L["lever_key"]: L for L in hpg["shared_levers"]}

    u1, c1, p1 = _seed_fixture(db_session, "lev_surf@example.com")
    levs1 = _tsl(u1, c1, p1)
    assert levs1["testosterone_substrate_load"]["status"] == "surfaced"
    assert levs1["testosterone_substrate_load"]["already_in_play_reason"] is None

    u2, c2, p2 = _seed_fixture(db_session, "lev_aip@example.com")
    _seed_declared(db_session, u2.id, "trt", _steady_trt())
    levs2 = _tsl(u2, c2, p2)
    tsl = levs2["testosterone_substrate_load"]
    assert tsl["status"] == "already_in_play"
    assert tsl["already_in_play_reason"] and "trt" in tsl["already_in_play_reason"]
    # empty declared_factor_keys -> still surfaced under a declared trt
    assert levs2["aromatase_inhibition"]["status"] == "surfaced"


# ---------- 4b-i-G4: relations degrade, never fabricate ----------

def test_relations_degrade_naming_missing_operands_never_fabricate(db_session):
    """G4. A relation with one operand missing renders `degraded` and NAMES the
    missing key; a relation with NO operand present in the panel is not rendered
    at all — never fabricated. Both directions asserted."""
    user, current, prior = _seed_fixture(db_session, "reln@example.com")
    out = _build(db_session, user, current, prior)

    # de_ritis (ast, alt): alt is absent from the panel -> degraded, alt named.
    ast = _row(out, "ast")
    de_ritis = next(r for r in ast["relations_rendered"] if r["relation_key"] == "de_ritis_ratio")
    assert de_ritis["operand_status"] == "degraded"
    assert de_ritis["operands_missing"] == ["alt"]

    # hpg_t_e2_ratio (testosterone_total, oestradiol): both present -> complete.
    tt = _row(out, "testosterone_total")
    t_e2 = next(r for r in tt["relations_rendered"] if r["relation_key"] == "hpg_t_e2_ratio")
    assert t_e2["operand_status"] == "complete"
    assert t_e2["operands_missing"] == []

    # Relations whose operands are ALL absent are rendered nowhere (not fabricated):
    #   shbg_free_fraction (free-T + shbg), cholestatic_co_movement (alp + ggt),
    #   bilirubin_isolation (ggt/alp/haemolysis_index/ld).
    rendered_keys = {r["relation_key"] for g in out["groups"] for m in g["members"]
                     for r in m["relations_rendered"]}
    assert "shbg_free_fraction" not in rendered_keys
    assert "cholestatic_co_movement" not in rendered_keys
    assert "bilirubin_isolation" not in rendered_keys


# ---------- 4b-ii-G3 / G5 / I1 / G7: preconditions resolve (Q56) ----------
# Gate-label convention (swept 2026-07-28, this brief): every section label is
# namespaced by increment — 4a-G*, 4b-i-G*, 4b-ii-G* — because bare G-letters
# collided across briefs (two G5s, two G6s). This is now the convention.

_MARKER_GROUPS_JSON = Path(__file__).resolve().parent.parent / "reference" / "marker_groups.json"


def _steady_trt():
    return {"active": True, "continuity": "continuous", "phase": None,
            "detail": "125mg/wk", "relevant_date": "2025-11-01"}


def _washout_trt():
    return {"active": False, "continuity": "stopped", "phase": None,
            "detail": "", "relevant_date": "2026-03-01"}


def _seed_declared(db, user_id, key, value, type_="protocol"):
    db.add(models.UserKnowledgeEntry(user_id=user_id, type=type_, key=key,
                                     source="onboarding", active=True, value=value))
    db.commit()


def _feedback_rel(out, marker="fsh"):
    return next(r for r in _row(out, marker)["relations_rendered"] if r["kind"] == "feedback")


def _derive_phase_return_set():
    """derive_phase's resolvable string return set, extracted programmatically:
    string constants in any Return (incl. inside IfExp) plus module-level string
    constants returned by name (EPISODIC, STOPPED, ...)."""
    import ast
    import declared_state
    src = Path(declared_state.__file__).read_text(encoding="utf-8")
    mod = ast.parse(src)
    consts = {t.id: n.value.value for n in mod.body if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name)
              and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    fn = next(n for n in ast.walk(mod) if isinstance(n, ast.FunctionDef) and n.name == "derive_phase")
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.add(sub.value)
                elif isinstance(sub, ast.Name) and sub.id in consts:
                    out.add(consts[sub.id])
    return out


def _authored_preconditions():
    groups = json.loads(_MARKER_GROUPS_JSON.read_text(encoding="utf-8"))
    return [(r["relation_key"], r["precondition"]) for g in groups["groups"]
            for r in g.get("relations", []) if "precondition" in r]


def test_precondition_admissible_phases_are_real_derive_phase_outputs():
    """4b-ii-G3. Every value in an authored precondition's admissible_phases must be
    a phase derive_phase can actually return — asserted against the function's
    resolved return set, programmatically not by eye. `on_trt` failed exactly this;
    ["steady"] passes it. re_entering is deliberately NOT admissible here (it is
    unreachable for a protocol-type factor), which this does not contradict —
    subset, not equality."""
    returns = _derive_phase_return_set()
    preconds = _authored_preconditions()
    assert preconds, "no precondition authored — would pass vacuously"
    for key, pc in preconds:
        assert set(pc["admissible_phases"]) <= returns, \
            f"{key}: {pc['admissible_phases']} not all in derive_phase returns {sorted(returns)}"
    assert "steady" in returns  # the value this brief authored


def test_precondition_evidence_refs_are_non_empty_I1():
    """4b-ii-I1. A precondition NOW feeds gate 1's delta arm — demotion has landed, and a
    `satisfied` precondition is exactly what withdraws a news verdict — so it is a
    gate-influencing read-constant: every authored precondition MUST carry non-empty
    evidence_refs (#95), as safety bands do. This test predates the authority and was
    written for the moment it arrived; that moment is now. Enforced by test —
    marker_groups.json has no _schema block — mirroring
    test_safety_thresholds_schema.validate()."""
    preconds = _authored_preconditions()
    assert preconds, "no precondition authored — vacuous"
    for key, pc in preconds:
        assert pc.get("evidence_refs"), f"{key}: precondition has empty evidence_refs (I1)"


def test_feedback_precondition_resolves_both_arms_and_names_absent_factor(db_session):
    """4b-ii-G5. The producer RESOLVES the precondition rather than asserting
    unresolvable. Positive control: declared trt in `steady` -> satisfied /
    expected_by_phase True. Not-satisfied control: trt in washout -> not_satisfied /
    False. Negative control: no trt declared -> unresolvable, NAMING the missing
    factor. All three, or the test proves nothing."""
    def _fsh_panel(email):
        u = _make_user(db_session, email)
        cur = _make_report(db_session, u.id, _CURRENT)
        _make_result(db_session, cur.id, "FSH", "fsh", value_num=0.1, value_operator="<",
                     unit_canonical="IU/L", ref_low=1.5, ref_high=12.4, lab_flag="L")
        return u, cur

    # satisfied
    u1, c1 = _fsh_panel("sat@example.com")
    _seed_declared(db_session, u1.id, "trt", _steady_trt())
    r1 = _feedback_rel(build_foundation(u1.id, db_session, c1, None))
    assert r1["relation_key"] == "hpg_gonadotropin_suppression"
    assert r1["precondition_status"] == "satisfied"
    assert r1["observed_phase"] == "steady"
    assert r1["expected_by_phase"] is True

    # not_satisfied (washout is not in admissible_phases)
    u2, c2 = _fsh_panel("notsat@example.com")
    _seed_declared(db_session, u2.id, "trt", _washout_trt())
    r2 = _feedback_rel(build_foundation(u2.id, db_session, c2, None))
    assert r2["precondition_status"] == "not_satisfied"
    assert r2["observed_phase"] == "washout"
    assert r2["expected_by_phase"] is False

    # unresolvable — factor absent from the ledger, named (never silently satisfied)
    u3, c3 = _fsh_panel("absent@example.com")
    r3 = _feedback_rel(build_foundation(u3.id, db_session, c3, None))
    assert r3["precondition_status"] == "unresolvable"
    assert r3["missing_factor_key"] == "trt"
    assert r3["expected_by_phase"] is None


def test_resolution_is_draw_dated_and_current_state_queried_once(db_session, monkeypatch):
    """4b-ii-G4. current_state is queried ONCE per build (the snapshot and the
    precondition phase map share it), and with today == the panel's collected_date,
    never date.today(). The fixture draw date (2026-05-30) != today, so a today-based
    resolution cannot pass."""
    import interpretation.producer as prod
    seen = []
    real = prod.current_state

    def spy(user_id, db, today):
        seen.append(today)
        return real(user_id, db, today)

    monkeypatch.setattr(prod, "current_state", spy)
    user, current, prior = _seed_fixture(db_session, "once@example.com")
    _build(db_session, user, current, prior)

    assert len(seen) == 1, f"current_state called {len(seen)}x, expected once"
    assert seen[0] == current.collected_date == date(2026, 5, 30)
    assert seen[0] != date.today(), "draw date must differ from today or the control is vacuous"


def test_on_trt_vocabulary_is_gone_from_source_and_live_asset():
    """4b-ii-G7. The dead `on_trt` vocabulary is gone from the producer source AND
    from every LIVE relation in marker_groups.json. History legitimately retains it
    (append-only DECISIONS, correct-don't-delete Q56 body, the held 4b-ii fixtures,
    and the _deferred trt_erythrocytosis_watch awaiting its own precondition
    authoring), so the scope is the live producer surface, not a whole-tree grep."""
    import subprocess
    repo = Path(__file__).resolve().parents[2]
    src = subprocess.run(["git", "grep", "-l", "on_trt", "--", "backend/interpretation/*.py"],
                         cwd=str(repo), capture_output=True, text=True)
    assert src.stdout.strip() == "", f"on_trt in producer source:\n{src.stdout}"

    groups = json.loads(_MARKER_GROUPS_JSON.read_text(encoding="utf-8"))
    for g in groups["groups"]:
        for r in g.get("relations", []):
            assert "precondition_phase" not in r, f"{r['relation_key']} keeps legacy precondition_phase"
            assert "on_trt" not in json.dumps(r), f"{r['relation_key']} live relation still carries on_trt"


# ---------- news_gate shape, and no UNEARNED demotion on the §2 panel ----------

def test_news_gate_shape_and_no_unearned_demotion_on_the_s2_panel(db_session):
    """FLIPPED, not deleted (was `test_no_demotion_news_gate_two_key_and_no_demot_basis`,
    asserting demotion did not exist). Demotion now DOES exist — see
    `test_in_phase_relation_demotes_the_delta_arm_end_to_end` and `test_relation_demotion.py`
    — so a blanket "no basis mentions demotion" would from here on be passing for a reason
    it no longer states, which is the drift this repo punishes.

    What survives unchanged: `news_gate` is exactly {is_news, basis} on every member and
    ungrouped row (shape is contract surface), and no basis ever leaks a `precondition` or
    `expected` token — resolving a precondition is not itself authority; only the named
    `relation_demoted_<key>` token is.

    What is now asserted POSITIVELY: the §2 panel does not demote, and the REASON is stated
    and checked — its feedback relation is `degraded`, because `_seed_fixture` seeds `fsh`
    without `lh`. Pinning the reason is the point: if that seed ever gains `lh`, this test
    fails loudly instead of quietly continuing to report "no demotion here"."""
    user, current, prior = _seed_fixture(db_session, "nodemote@example.com")
    _seed_declared(db_session, user.id, "trt", _steady_trt())  # precondition resolves satisfied
    out = _build(db_session, user, current, prior)

    # the precondition IS satisfied — so demotion is refused on the operand clause alone
    relation = _feedback_rel(out)
    assert relation["precondition_status"] == "satisfied"
    assert relation["operand_status"] == "degraded", \
        "the §2 seed omits `lh`; if that changed, this panel would start demoting"
    assert "lh" in relation["operands_missing"]

    rows = [m for g in out["groups"] for m in g["members"]] + out["ungrouped"]
    assert rows, "non-vacuous"
    for r in rows:
        assert set(r["news_gate"]) == {"is_news", "basis"}, \
            f"{r['marker_canonical']} news_gate is not exactly two keys"
        for b in r["news_gate"]["basis"]:
            assert not b.startswith("relation_demoted_"), \
                f"{r['marker_canonical']} demoted on a degraded relation: {b}"
            assert "precondition" not in b and "expected" not in b, \
                f"{r['marker_canonical']} basis leaked precondition authority: {b}"

    # fsh: satisfied precondition, still surfaced on its range breach (gate 2), not demoted
    assert _group(out, "hpg_axis")["should_surface"] is True
    assert _row(out, "fsh")["range_gate"]["is_out_of_range"] is True


def test_meta_carries_the_snapshot_and_names_both_panels(db_session):
    """Inverted from 4a's `test_meta_is_phase_free_...`: 4b-i emits
    `protocol_context_snapshot` (dated to the draw — see the as_of test below),
    where 4a asserted its absence. Everything else in meta is unchanged."""
    user, current, prior = _seed_fixture(db_session, "meta@example.com")
    meta = _build(db_session, user, current, prior)["meta"]

    assert "protocol_context_snapshot" in meta  # 4b-i emits it (was absent in 4a)
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


# ---------- 4b-i-G3: snapshot is DRAW-dated, never generation-dated ----------

def test_protocol_context_snapshot_as_of_is_the_draw_date_not_today(db_session):
    """G3. The snapshot's `as_of` is the trigger panel's collected_date, never
    date.today(). NEGATIVE CONTROL: the fixture's draw date (2026-05-30) is not
    today, so a `date.today()`-based implementation CANNOT pass this — the equality
    would land on the wrong string. Asserted in both directions: == draw date AND
    != today."""
    user, current, prior = _seed_fixture(db_session, "asof@example.com")
    snap = _build(db_session, user, current, prior)["meta"]["protocol_context_snapshot"]

    assert snap["as_of"] == "2026-05-30"
    assert snap["as_of"] == current.collected_date.isoformat()
    assert snap["as_of"] != date.today().isoformat(), \
        "draw date must differ from today or the negative control is vacuous"
    assert current.collected_date != date.today()  # the control is live, not accidental


def test_protocol_context_snapshot_projects_phase_fields_only(db_session):
    """The snapshot flattens declared_state across its three types and projects
    each factor to exactly {key, type, phase, assumable_present, relevant_date}.
    It carries NO `detail` (unbounded free text) and NO `active` (two-senses trap).
    A steady continuous protocol derives phase `steady` / assumable_present True."""
    user = _make_user(db_session, "snapfields@example.com")
    current = _make_report(db_session, user.id, _CURRENT)
    _make_result(db_session, current.id, "AST", "ast", value_num=20.0, ref_high=40.0)
    db_session.add(models.UserKnowledgeEntry(
        user_id=user.id, type="protocol", key="trt", source="onboarding", active=True,
        value={"active": True, "continuity": "continuous", "phase": None,
               "detail": "125mg/wk test-C", "relevant_date": "2025-11-01"},
    ))
    db_session.commit()

    snap = build_foundation(user.id, db_session, current, None)["meta"]["protocol_context_snapshot"]
    assert snap["as_of"] == "2026-05-30"
    trt = next(f for f in snap["factors"] if f["key"] == "trt")
    assert set(trt) == {"key", "type", "phase", "assumable_present", "relevant_date"}
    assert "detail" not in trt and "active" not in trt
    assert trt["type"] == "protocol"
    assert trt["phase"] == "steady"  # continuous + active, non-behavioural
    assert trt["assumable_present"] is True
    assert trt["relevant_date"] == "2025-11-01"


# ---------- 4a-G5: gate-2 source is lab_flag, not computed_flag ----------

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


# ---------- 4a-G6: non-vacuity of magnitude and crossed_ref ----------

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


# ---------- gate 3 -> gate 1 safety arm, END TO END through build_foundation ----------

def _seed_haematocrit_band_crossing(db, email):
    """A haematocrit pair that ESCALATES watch -> elevated through the real asset.

    Deliberately constructed so the ONLY reason the member is news is the safety arm:
      * both draws sit inside the lab's own 0.40-0.54 reference range, so gate 2 is quiet;
      * +2.9% is below haematocrit's authored 8% min_meaningful_delta, so the delta arm is
        quiet (`within_noise`) and no reference bound is crossed;
      * 0.515 clears the `watch` band (0.50) and 0.53 clears `elevated` (0.52), so the
        highest breached band escalates and `safety_gate.band_change` fires.

    A SEPARATE seed from `_seed_fixture` on purpose: the §2 oracle panel stays byte-identical,
    so this addition cannot move the canonical invariance baseline."""
    user = _make_user(db, email)
    prior = _make_report(db, user.id, _PRIOR, panel_name="FBC (prior)")
    current = _make_report(db, user.id, _CURRENT, panel_name="FBC")
    _make_result(db, prior.id, "Haematocrit", "haematocrit",
                 value_num=0.515, ref_low=0.40, ref_high=0.54)
    _make_result(db, current.id, "Haematocrit", "haematocrit",
                 value_num=0.53, ref_low=0.40, ref_high=0.54)
    return user, current, prior


def test_band_change_propagates_end_to_end_and_forces_news(db_session):
    """The safety arm through the REAL path, which no test had exercised before.

    `test_safety_gate.py` drives band_change at gate-unit level with an injected asset;
    `build_foundation` reads the module-level asset and nothing had ever seeded a banded
    marker, so no `band_change` had propagated through the producer at all. This closes
    that gap.

    NON-VACUITY: the two other gates are asserted QUIET here, so `is_news` cannot be
    arriving from anywhere but the safety arm. That also demonstrates #138's point that
    gate 3 is independent of gate 2 - an in-range value still sits in a band."""
    user, current, prior = _seed_haematocrit_band_crossing(db_session, "band@example.com")
    out = build_foundation(user.id, db_session, current, prior)

    group = _group(out, "erythroid")
    member = next(m for m in group["members"] if m["marker_canonical"] == "haematocrit")

    # gate 3 fired, and escalated between the two draws
    assert member["safety_gate"]["status"] == "in_band"
    assert member["safety_gate"]["band_change"] == "escalated"
    assert member["safety_gate"]["band_key"] == "elevated"
    assert member["safety_gate"]["undecidable_reason"] is None

    # the other two gates are quiet, so the news below is the safety arm's alone
    assert member["range_gate"]["is_out_of_range"] is False, "gate 2 must be quiet here"
    assert member["delta"]["magnitude"] == "within_noise", "delta arm must be quiet here"
    assert member["delta"]["crossed_ref"] is None

    # gate 1: forced true by the safety arm, and it NAMES the band change
    assert member["news_gate"]["is_news"] is True
    assert "safety_band_escalated" in member["news_gate"]["basis"]

    assert group["should_surface"] is True


# ---------- §4 relation demotion of gate 1's delta arm, END TO END ----------

def _seed_hpg_feedback_panel(db, email, fsh_prior, fsh_current, lab_flag=None,
                             ref_low=1.5, ref_high=12.4, declare_trt=True):
    """A panel where the `hpg_gonadotropin_suppression` feedback relation can actually
    demote: BOTH its operands (`lh`, `fsh`) are present so `operand_status` is `complete`,
    and a steady `trt` factor is declared so `precondition_status` resolves `satisfied`.

    `_seed_fixture` cannot serve here — it seeds `fsh` without `lh`, so the relation is
    permanently `degraded` there, and its `fsh` pair is censored-flat so there is no news to
    demote. That is also why demotion leaves the §2 oracle panel byte-identical."""
    user = _make_user(db, email)
    prior = _make_report(db, user.id, _PRIOR, panel_name="Gonadal (prior)")
    current = _make_report(db, user.id, _CURRENT, panel_name="Gonadal")
    for report, fsh_value in ((prior, fsh_prior), (current, fsh_current)):
        _make_result(db, report.id, "FSH", "fsh", value_num=fsh_value, unit_canonical="IU/L",
                     ref_low=ref_low, ref_high=ref_high, lab_flag=lab_flag)
    # lh present so the relation's operand set is COMPLETE (this is what _seed_fixture lacks)
    _make_result(db, prior.id, "LH", "lh", value_num=5.0, unit_canonical="IU/L",
                 ref_low=1.7, ref_high=8.6)
    _make_result(db, current.id, "LH", "lh", value_num=4.6, unit_canonical="IU/L",
                 ref_low=1.7, ref_high=8.6)
    # the relation's driver, for a physiologically coherent panel
    _make_result(db, prior.id, "Testosterone (total)", "testosterone_total",
                 value_num=22.5, unit_canonical="nmol/L", ref_low=10.0, ref_high=30.0)
    _make_result(db, current.id, "Testosterone (total)", "testosterone_total",
                 value_num=24.0, unit_canonical="nmol/L", ref_low=10.0, ref_high=30.0)
    if declare_trt:
        _seed_declared(db, user.id, "trt", _steady_trt())
    return user, current, prior


def test_in_phase_relation_demotes_the_delta_arm_end_to_end(db_session):
    """§4 through the real producer. FSH falls 8.0 -> 3.0 (-62.5%, well past the 0.30
    fallback threshold) entirely INSIDE the reference interval, so the delta arm is news and
    no bound is crossed. With steady TRT declared, the gonadotropin-suppression relation
    resolves `satisfied` with `complete` operands, so the movement is expected and gate 1 is
    withdrawn — naming the relation."""
    user, current, prior = _seed_hpg_feedback_panel(db_session, "demote@example.com", 8.0, 3.0)
    out = _build(db_session, user, current, prior)
    fsh = _row(out, "fsh")

    # the demotion path was genuinely live
    relation = _feedback_rel(out)
    assert relation["precondition_status"] == "satisfied"
    assert relation["operand_status"] == "complete"
    assert fsh["delta"]["magnitude"] == "meaningful"
    assert fsh["delta"]["crossed_ref"] is None

    assert fsh["news_gate"]["is_news"] is False, "an in-phase feedback relation demotes it"
    assert "delta_meaningful" in fsh["news_gate"]["basis"]
    assert "relation_demoted_hpg_gonadotropin_suppression" in fsh["news_gate"]["basis"]


def test_the_same_movement_is_news_without_the_declared_factor(db_session):
    """The control that makes the test above mean something: identical FSH movement, no
    declared `trt`, so the precondition resolves `unresolvable` and nothing demotes. Without
    this, the demotion could be an artefact of the seed rather than of the relation."""
    user, current, prior = _seed_hpg_feedback_panel(
        db_session, "nodemote@example.com", 8.0, 3.0, declare_trt=False)
    out = _build(db_session, user, current, prior)
    fsh = _row(out, "fsh")

    assert _feedback_rel(out)["precondition_status"] == "unresolvable"
    assert fsh["news_gate"]["is_news"] is True
    assert not any(b.startswith("relation_demoted_") for b in fsh["news_gate"]["basis"])


def test_gate_2_breach_survives_demotion_and_the_group_still_surfaces(db_session):
    """I5 UNDER PRESSURE, end to end. FSH sits BELOW the interval on both draws (lab flag L,
    so gate 2 fires) and falls 0.9 -> 0.3, a meaningful move with NO bound crossing — so the
    demotion path is live and does fire on gate 1.

    Gate 2 is untouched by it and the group still surfaces. That is the invariant: the breach
    is annotated by the relation, never hidden by it. Demotion is structurally unable to
    reach gate 2 — it only rewrites gate 1's return, and `should_surface` ORs the three."""
    user, current, prior = _seed_hpg_feedback_panel(
        db_session, "i5@example.com", 0.9, 0.3, lab_flag="L")
    out = _build(db_session, user, current, prior)
    fsh = _row(out, "fsh")

    assert fsh["delta"]["crossed_ref"] is None, "both draws out of range — no crossing"
    assert fsh["news_gate"]["is_news"] is False, "gate 1 demoted, so this is real pressure"
    assert "relation_demoted_hpg_gonadotropin_suppression" in fsh["news_gate"]["basis"]

    # ... and yet
    assert fsh["range_gate"]["is_out_of_range"] is True, "I5: gate 2 is not suppressible"
    assert _group(out, "hpg_axis")["should_surface"] is True, \
        "the group must still surface on the breach alone"


def test_demotion_never_reaches_gate_3(db_session):
    """Gate 3 is asserted untouched on the same panel: no relation writes to `safety_gate`,
    whatever it does to gate 1. (`fsh` has no authored band, so `no_asset` is the correct
    and only honest value here — this pins that demotion did not invent one.)"""
    user, current, prior = _seed_hpg_feedback_panel(db_session, "gate3@example.com", 8.0, 3.0)
    fsh = _row(_build(db_session, user, current, prior), "fsh")
    assert fsh["news_gate"]["is_news"] is False           # demotion did happen
    assert fsh["safety_gate"]["status"] is None
    assert fsh["safety_gate"]["band_change"] is None
    assert fsh["safety_gate"]["undecidable_reason"] == "no_asset"
