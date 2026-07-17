"""The declared-state SEED — composition, idempotency, and provenance integrity.

Separate from test_declared_state.py by concern: that file tests the derivation
rules over synthetic entries; this one tests the shipped clinical data and the
seeder that writes it. Tests here run against `_DECLARED_STATE_SEED` itself, not
a re-typed copy — a transcription error in provenance-bearing clinical data must
fail here, not survive because the test restated the same mistake.
"""
from datetime import date

import models
from declared_state import derive_phase
from current_state import current_state
from seed_engine import _DECLARED_STATE_SEED, _seed_declared_state

_TODAY = date(2026, 7, 17)


def _make_user(db, email):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seeded(key):
    entry_type, factor = next((t, f) for t, f in _DECLARED_STATE_SEED if f["key"] == key)
    return models.UserKnowledgeEntry(
        user_id=1, type=entry_type, key=key, value=factor["value"],
        source="system", active=True, notes=factor["value"].get("detail"),
    )


# ---------- composition ----------

def test_seed_writes_23_factors(db_session):
    user = _make_user(db_session, "seed@example.com")
    assert _seed_declared_state(db_session, user.id) == 23


def test_seed_composition_is_6_protocol_16_supplement_1_behavioural(db_session):
    user = _make_user(db_session, "comp@example.com")
    _seed_declared_state(db_session, user.id)

    counts = {
        t: db_session.query(models.UserKnowledgeEntry).filter_by(user_id=user.id, type=t).count()
        for t in ("protocol", "supplement", "behavioural")
    }
    assert counts == {"protocol": 6, "supplement": 16, "behavioural": 1}


def test_seed_keys_are_unique():
    keys = [f["key"] for _, f in _DECLARED_STATE_SEED]
    assert len(keys) == len(set(keys))


def test_every_seed_factor_matches_the_value_schema():
    for _, factor in _DECLARED_STATE_SEED:
        value = factor["value"]
        assert set(value) == {"active", "continuity", "phase", "detail", "relevant_date"}, factor["key"]
        assert isinstance(value["active"], bool), factor["key"]
        assert value["continuity"] in ("continuous", "episodic", "stopped", "never"), factor["key"]
        assert value["detail"], factor["key"]


# ---------- idempotency ----------

def test_seed_is_idempotent(db_session):
    """Second and third runs add zero rows — INCLUDING the four factors the user
    does not take. Had the row's `active` column mirrored value["active"], the
    skip (which keys on active=True) would never match those four and every
    re-run would duplicate them."""
    user = _make_user(db_session, "idem@example.com")
    assert _seed_declared_state(db_session, user.id) == 23
    assert _seed_declared_state(db_session, user.id) == 0
    assert _seed_declared_state(db_session, user.id) == 0

    total = db_session.query(models.UserKnowledgeEntry).filter(
        models.UserKnowledgeEntry.user_id == user.id,
        models.UserKnowledgeEntry.type.in_(("protocol", "supplement", "behavioural")),
    ).count()
    assert total == 23

    for key in ("tirzepatide", "glow", "hgh", "ultra_muscleze_night"):
        n = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=user.id, key=key).count()
        assert n == 1, f"{key} duplicated on re-run"


def test_seed_does_not_disturb_other_users(db_session):
    user_a = _make_user(db_session, "ua@example.com")
    user_b = _make_user(db_session, "ub@example.com")
    _seed_declared_state(db_session, user_a.id)
    assert db_session.query(models.UserKnowledgeEntry).filter_by(user_id=user_b.id).count() == 0


def test_seed_mirrors_the_injury_ledger_row_shape(db_session):
    user = _make_user(db_session, "shape@example.com")
    _seed_declared_state(db_session, user.id)

    trt = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=user.id, key="trt").one()
    assert trt.type == "protocol"
    assert trt.source == "system"
    assert trt.notes == trt.value["detail"]
    assert trt.active is True


def test_untaken_factors_are_written_as_active_declarations(db_session):
    """The row flag means "this DECLARATION is current"; value["active"] means
    "the user takes this". A stopped or never-used factor is still a
    currently-true declaration, and must stay queryable."""
    user = _make_user(db_session, "decl@example.com")
    _seed_declared_state(db_session, user.id)

    for key in ("tirzepatide", "glow", "hgh", "ultra_muscleze_night"):
        row = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=user.id, key=key).one()
        assert row.active is True, f"{key} row must stay queryable"
        assert row.value["active"] is False, f"{key} is not being taken"


# ---------- derived phases for the real stack ----------

def test_trt_derives_steady():
    assert derive_phase(_seeded("trt"), _TODAY) == "steady"


def test_tirzepatide_derives_washout():
    assert derive_phase(_seeded("tirzepatide"), _TODAY) == "washout"


def test_episodic_peptides_derive_episodic_and_are_not_assumable_present(db_session):
    """CJC-1295/Ipamorelin and IGF-1 LR3 are ad-hoc: active, but never
    assumable at a given draw. Clinical_Protocol.md had them as discontinued."""
    user = _make_user(db_session, "epi@example.com")
    _seed_declared_state(db_session, user.id)
    state = current_state(user.id, db_session, _TODAY)
    by_key = {f["key"]: f for f in state.declared_state["protocol"]}

    for key in ("cjc_ipamorelin", "igf1_lr3"):
        assert by_key[key]["active"] is True, key
        assert by_key[key]["phase"] == "episodic", key
        assert by_key[key]["assumable_present"] is False, key


def test_glow_derives_stopped_not_washout():
    """Stop date not recorded — no anchor, so not a washout."""
    assert derive_phase(_seeded("glow"), _TODAY) == "stopped"


def test_hgh_derives_none_and_records_the_correction():
    """HGH was NEVER used or sourced. This row exists to correct
    Clinical_Protocol.md, which recorded it active."""
    entry = _seeded("hgh")
    assert derive_phase(entry, _TODAY) is None
    assert entry.value["continuity"] == "never"
    assert "NEVER used" in entry.value["detail"]


def test_cbt_i_derives_re_entering():
    assert derive_phase(_seeded("cbt_i"), _TODAY) == "re_entering"


def test_superseded_supplement_derives_none_but_keeps_its_history():
    entry = _seeded("ultra_muscleze_night")
    assert derive_phase(entry, _TODAY) is None
    assert "superseded by l_theanine_pm" in entry.value["detail"]


def test_declared_phase_agrees_with_the_derivation_where_declared():
    """Cross-check: the seed's authored `phase` against the computed one. A
    disagreement means either the transcription or the rule is wrong."""
    for _, factor in _DECLARED_STATE_SEED:
        declared = factor["value"].get("phase")
        if declared is None:
            continue
        assert derive_phase(_seeded(factor["key"]), _TODAY) == declared, factor["key"]


# ---------- provenance ----------

def test_tirzepatide_date_is_flagged_as_triangulated_not_a_dosing_log():
    """The last-shot date is triangulated (HRV step + Monday constraint +
    recollection). Flagged in the data so it is never counted twice as evidence
    for the Q17 washout hypothesis it was partly derived from."""
    detail = _seeded("tirzepatide").value["detail"]
    assert "triangulated" in detail
    assert "not a dosing log" in detail


def test_glow_records_its_real_composition():
    """GLOW = BPC-157 + TB-500 + GHK-Cu — Clinical_Protocol.md mis-recorded KPV."""
    detail = _seeded("glow").value["detail"]
    for component in ("BPC-157", "TB-500", "GHK-Cu"):
        assert component in detail
    assert "KPV" not in detail


def test_cumulative_source_totals_are_recorded():
    """Mg (3 sources) and Zn (2 sources) are cumulative — recorded so a
    Mg/Zn/Cu read is not misjudged against a single-source assumption."""
    assert "3 sources" in _seeded("mg_glycinate").value["detail"]
    assert "2 sources" in _seeded("zinc").value["detail"]


def test_lab_confounders_are_tagged_per_factor():
    """The per-factor confounder tagging is the capability this ledger unlocks
    for 4b's "already in play" lever curation (#49)."""
    for key, marker in [
        ("berberine", "HbA1c"),
        ("b_complex", "B12"),
        ("vit_d3_k2", "25-OH vitamin D"),
        ("creatine", "creatinine"),
        ("leucine_protein", "urea"),
        ("apigenin", "aromatase_inhibition"),
        ("prebiotic_fibre", "estrobolome"),
    ]:
        assert marker.lower() in _seeded(key).value["detail"].lower(), f"{key} should tag {marker}"


# ---------- end-to-end: seed -> current_state ----------

def test_current_state_declared_state_carries_every_seeded_phase(db_session):
    user = _make_user(db_session, "e2e@example.com")
    _seed_declared_state(db_session, user.id)

    state = current_state(user.id, db_session, _TODAY)
    phases = {f["key"]: f["phase"] for group in state.declared_state.values() for f in group}

    assert phases["trt"] == "steady"
    assert phases["tirzepatide"] == "washout"
    assert phases["cjc_ipamorelin"] == "episodic"
    assert phases["igf1_lr3"] == "episodic"
    assert phases["glow"] == "stopped"
    assert phases["hgh"] is None
    assert phases["cbt_i"] == "re_entering"
    assert phases["ultra_muscleze_night"] is None
    assert phases["boron"] == "steady"
    assert len(phases) == 23


def test_untaken_factors_reach_current_state(db_session):
    """The regression this design exists to prevent: a stopped/never factor
    must not vanish from declared_state, or its phase is underivable and the
    ledger cannot answer the question it was built for."""
    user = _make_user(db_session, "reach@example.com")
    _seed_declared_state(db_session, user.id)

    state = current_state(user.id, db_session, _TODAY)
    keys = {f["key"] for group in state.declared_state.values() for f in group}
    assert {"tirzepatide", "glow", "hgh", "ultra_muscleze_night"} <= keys
