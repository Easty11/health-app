"""Declared-state ledger — phase derivation and the current_state lift.

Pure-logic tests over synthetic entries. The SEED's own conformance (the 23
real factors, idempotency, provenance) is a separate concern and lives in
test_declared_state_seed.py.

The load-bearing distinction under test is CONTINUITY, not a bare active flag:
  continuous + taken   -> steady      -> assumable present at any draw
  episodic             -> episodic    -> NOT assumable present at any draw
  stopped + dated      -> washout     -> NOT assumable present (a draw-specific call)
  continuous + dropped -> None        -> history (superseded), no current phase
  never                -> None
"""
from datetime import date

import models
from declared_state import derive_phase, is_assumable_present, lift_declared_state
from current_state import current_state

_TODAY = date(2026, 7, 17)


def _make_user(db, email):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _entry(entry_type="protocol", key="x", **value):
    return models.UserKnowledgeEntry(
        user_id=1, type=entry_type, key=key, value=value,
        source="system", active=True, notes=value.get("detail"),
    )


# ---------- derive_phase: one branch per continuity ----------

def test_continuous_and_taken_derives_steady():
    entry = _entry(active=True, continuity="continuous", phase=None, detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) == "steady"


def test_continuous_but_no_longer_taken_derives_none():
    """Superseded history carries no current phase."""
    entry = _entry(active=False, continuity="continuous", phase=None, detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) is None


def test_stopped_with_a_date_derives_washout():
    """A stopped factor still has a phase — that is the whole point. Deriving
    None here (by letting an inactive check preempt continuity) would make a
    dated washout invisible, which is the distinction a bare active flag
    flattens."""
    entry = _entry(active=False, continuity="stopped", phase=None, detail="d",
                   relevant_date="2026-06-22")
    assert derive_phase(entry, _TODAY) == "washout"


def test_stopped_without_a_date_derives_stopped_not_washout():
    """No anchor to wash out from."""
    entry = _entry(active=False, continuity="stopped", phase=None, detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) == "stopped"


def test_episodic_derives_episodic():
    entry = _entry(active=True, continuity="episodic", phase=None, detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) == "episodic"


def test_inactive_episodic_derives_none():
    entry = _entry(active=False, continuity="episodic", phase=None, detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) is None


def test_never_derives_none():
    entry = _entry(active=False, continuity="never", phase=None, detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) is None


def test_behavioural_continuous_with_a_date_derives_re_entering():
    entry = _entry("behavioural", active=True, continuity="continuous", phase=None,
                   detail="d", relevant_date="2026-07-19")
    assert derive_phase(entry, _TODAY) == "re_entering"


def test_re_entering_is_behavioural_only():
    """The rule keys on the entry's type, not just the presence of a date — the
    same shape under `protocol` is steady."""
    protocol = _entry("protocol", active=True, continuity="continuous", phase=None,
                      detail="d", relevant_date="2026-07-19")
    assert derive_phase(protocol, _TODAY) == "steady"


def test_behavioural_continuous_without_a_date_derives_steady():
    entry = _entry("behavioural", active=True, continuity="continuous", phase=None,
                   detail="d", relevant_date=None)
    assert derive_phase(entry, _TODAY) == "steady"


def test_unrecognised_or_absent_continuity_derives_none():
    assert derive_phase(_entry(active=True, detail="d"), _TODAY) is None
    assert derive_phase(_entry(active=True, continuity="sporadic", detail="d"), _TODAY) is None


def test_empty_value_does_not_raise():
    entry = models.UserKnowledgeEntry(user_id=1, type="protocol", key="x", value={},
                                      source="system", active=True)
    assert derive_phase(entry, _TODAY) is None


# ---------- mutation proof: the derivation is not vacuous ----------

def test_flipping_continuity_changes_the_derived_phase():
    """If derive_phase echoed value["phase"], or returned a constant, none of
    these would move."""
    entry = _entry(active=True, continuity="continuous", phase="steady", detail="d",
                   relevant_date="2026-06-22")
    assert derive_phase(entry, _TODAY) == "steady"

    entry.value = {**entry.value, "continuity": "episodic"}
    assert derive_phase(entry, _TODAY) == "episodic"

    entry.value = {**entry.value, "continuity": "stopped"}
    assert derive_phase(entry, _TODAY) == "washout"

    entry.value = {**entry.value, "continuity": "never"}
    assert derive_phase(entry, _TODAY) is None


def test_derive_phase_ignores_the_declared_phase_field():
    """The declared `phase` is authored intent; the phase is COMPUTED from
    continuity/active/relevant_date. A lying declaration must not win."""
    assert derive_phase(
        _entry(active=True, continuity="episodic", phase="steady", detail="d", relevant_date=None),
        _TODAY,
    ) == "episodic"
    assert derive_phase(
        _entry(active=True, continuity="continuous", phase="washout", detail="d", relevant_date=None),
        _TODAY,
    ) == "steady"


def test_flipping_active_changes_the_continuous_phase():
    taken = _entry(active=True, continuity="continuous", phase=None, detail="d", relevant_date=None)
    dropped = _entry(active=False, continuity="continuous", phase=None, detail="d", relevant_date=None)
    assert derive_phase(taken, _TODAY) == "steady"
    assert derive_phase(dropped, _TODAY) is None


# ---------- the not-present-by-default semantics ----------

def test_only_steady_is_assumable_present():
    assert is_assumable_present("steady") is True
    for phase in ("episodic", "washout", "stopped", "re_entering", None):
        assert is_assumable_present(phase) is False, phase


def test_an_active_episodic_factor_is_not_assumable_present():
    """The load-bearing case: episodic is ACTIVE and still not assumable at any
    given draw. `active` alone cannot express this."""
    entry = _entry(active=True, continuity="episodic", phase=None, detail="d", relevant_date=None)
    assert entry.value["active"] is True
    assert is_assumable_present(derive_phase(entry, _TODAY)) is False


# ---------- the lift ----------

def test_lift_always_returns_all_three_keys():
    assert lift_declared_state([], _TODAY) == {"protocol": [], "supplement": [], "behavioural": []}


def test_lift_ignores_unrelated_entry_types():
    entries = [
        _entry("injury", key="injury_shoulder_right", detail="d"),
        _entry("preference", key="device_profile", detail="d"),
        _entry("protocol", key="trt", active=True, continuity="continuous", detail="d"),
    ]
    lifted = lift_declared_state(entries, _TODAY)
    assert [f["key"] for f in lifted["protocol"]] == ["trt"]
    assert lifted["supplement"] == []
    assert lifted["behavioural"] == []


def test_lift_groups_by_type():
    entries = [
        _entry("protocol", key="trt", active=True, continuity="continuous", detail="d"),
        _entry("supplement", key="boron", active=True, continuity="continuous", detail="d"),
        _entry("behavioural", key="cbt_i", active=True, continuity="continuous", detail="d",
               relevant_date="2026-07-19"),
    ]
    lifted = lift_declared_state(entries, _TODAY)
    assert [f["key"] for f in lifted["protocol"]] == ["trt"]
    assert [f["key"] for f in lifted["supplement"]] == ["boron"]
    assert [f["key"] for f in lifted["behavioural"]] == ["cbt_i"]


def test_lift_carries_derived_phase_and_presence():
    entries = [
        _entry("protocol", key="trt", active=True, continuity="continuous", detail="d",
               relevant_date=None),
        _entry("protocol", key="peptide", active=True, continuity="episodic", detail="d",
               relevant_date=None),
    ]
    by_key = {f["key"]: f for f in lift_declared_state(entries, _TODAY)["protocol"]}

    assert by_key["trt"]["phase"] == "steady"
    assert by_key["trt"]["assumable_present"] is True
    assert by_key["peptide"]["phase"] == "episodic"
    assert by_key["peptide"]["assumable_present"] is False


def test_lift_factor_shape():
    entry = _entry("protocol", key="trt", active=True, continuity="continuous",
                   phase="steady", detail="TRT active", relevant_date="2026-06-09")
    factor = lift_declared_state([entry], _TODAY)["protocol"][0]
    assert factor == {
        "key": "trt", "type": "protocol", "active": True, "continuity": "continuous",
        "phase": "steady", "assumable_present": True, "detail": "TRT active",
        "relevant_date": "2026-06-09",
    }


# ---------- current_state wiring ----------

def test_current_state_declared_state_empty_for_a_user_with_no_declarations(db_session):
    """LANDED != LIVE: reads empty until the seed runs."""
    user = _make_user(db_session, "empty@example.com")
    state = current_state(user.id, db_session, _TODAY)
    assert state.declared_state == {"protocol": [], "supplement": [], "behavioural": []}


def test_current_state_lifts_declared_entries(db_session):
    user = _make_user(db_session, "wire@example.com")
    db_session.add(models.UserKnowledgeEntry(
        user_id=user.id, type="protocol", key="trt",
        value={"active": True, "continuity": "continuous", "phase": "steady",
               "detail": "d", "relevant_date": None},
        source="system", active=True, notes="d",
    ))
    db_session.commit()

    state = current_state(user.id, db_session, _TODAY)
    assert state.declared_state["protocol"][0]["phase"] == "steady"


def test_current_state_declared_state_does_not_leak_across_users(db_session):
    user_a = _make_user(db_session, "da@example.com")
    user_b = _make_user(db_session, "db@example.com")
    db_session.add(models.UserKnowledgeEntry(
        user_id=user_a.id, type="protocol", key="trt",
        value={"active": True, "continuity": "continuous", "detail": "d"},
        source="system", active=True,
    ))
    db_session.commit()

    assert current_state(user_b.id, db_session, _TODAY).declared_state["protocol"] == []
