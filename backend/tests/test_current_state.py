"""
Tests for the current_state read model (DECISIONS_LOG #43 / OPEN_QUESTIONS Q8).

(a) active-only declared state assembled correctly for a seeded user
(b) supersede semantics honoured (superseded entry absent)
(c) empty-profile user returns a well-formed empty object, not an error
(d) context_builder output is unchanged pre/post refactor (formatter-only,
    no behavioural drift) — compared against master's pre-refactor
    context_builder.py loaded via `git show`.
"""
import os
import subprocess
import types
from datetime import date, datetime, timedelta

import pytz

import current_state as current_state_mod
import context_builder
import models
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

AEST = pytz.timezone("Australia/Brisbane")


def _make_user(db, email="fixture@example.com"):
    user = models.User(email=email, hashed_password="x", full_name="Fixture User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_entry(db, user_id, type_, key, value, active=True, source="chat"):
    entry = models.UserKnowledgeEntry(
        user_id=user_id, type=type_, key=key, value=value, source=source, active=active,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------- (a) active-only declared state ----------

def test_current_state_returns_active_declared_state(db_session):
    user = _make_user(db_session)

    _add_entry(db_session, user.id, "preference", "device_profile", {"hrv_source": "galaxy_ring"})
    _add_entry(db_session, user.id, "schedule_item", "physio_2026_07",
               {"activity": "physio", "days": ["monday"], "hard": True})
    _add_entry(db_session, user.id, "injury", "left_hamstring",
               {"body_part": "left hamstring", "restrictions": ["sprint"]})
    _add_entry(db_session, user.id, "load_context", "big_weekend", {"description": "big weekend"})
    inactive = _add_entry(db_session, user.id, "injury", "old_injury", {"body_part": "old"}, active=False)

    fort = models.FortificationProfile(user_id=user.id, primary_target="anti_lateral_flexion")
    db_session.add(fort)
    cap = models.CapabilityState(user_id=user.id, region_key="hinge", side="bilateral",
                                  status="pass", source="history")
    db_session.add(cap)
    db_session.commit()

    state = current_state_mod.current_state(user.id, db_session, today=date(2026, 7, 4))

    assert {e.key for e in state.knowledge_entries} == {
        "device_profile", "physio_2026_07", "left_hamstring", "big_weekend",
    }
    assert inactive.id not in {e.id for e in state.knowledge_entries}
    assert state.device_profile == {"hrv_source": "galaxy_ring"}
    assert state.fortification_profile["primary_target"] == "anti_lateral_flexion"
    assert state.fortification_profile_orm is fort
    assert [c.region_key for c in state.capability_state] == ["hinge"]


# ---------- (b) supersede semantics ----------

def test_current_state_excludes_superseded_entry(db_session):
    user = _make_user(db_session)

    first = upsert_knowledge_entry(
        user.id,
        KnowledgeEntryIn(type="schedule_item", key="physio_2026_07", value={"activity": "physio v1"}),
        db_session,
    )
    second = upsert_knowledge_entry(
        user.id,
        KnowledgeEntryIn(type="schedule_item", key="physio_2026_07", value={"activity": "physio v2"}),
        db_session,
    )

    state = current_state_mod.current_state(user.id, db_session, today=date(2026, 7, 4))

    ids = {e.id for e in state.knowledge_entries}
    assert second.id in ids
    assert first.id not in ids
    assert first.superseded_by == second.id
    assert first.active is False


# ---------- (c) empty-profile user ----------

def test_current_state_empty_profile_user_returns_well_formed_empty_object(db_session):
    user = _make_user(db_session, email="empty@example.com")

    state = current_state_mod.current_state(user.id, db_session, today=date(2026, 7, 4))

    assert state.knowledge_entries == []
    assert state.device_profile is None
    assert state.fortification_profile is None
    assert state.fortification_profile_orm is None
    assert state.capability_state == []
    assert state.hrv_baseline_7d is None


# ---------- (d) context_builder is formatter-only (no behavioural drift) ----------

def _load_master_context_builder():
    """Load master's pre-refactor context_builder.py as an isolated module."""
    src = subprocess.check_output(
        ["git", "show", "master:backend/context_builder.py"],
        cwd=os.path.dirname(__file__),
        encoding="utf-8",
    )
    module = types.ModuleType("context_builder_master")
    exec(compile(src, "context_builder_master.py", "exec"), module.__dict__)
    return module


def test_context_builder_output_unchanged_pre_post_refactor(db_session, monkeypatch):
    old_context_builder = _load_master_context_builder()

    user = _make_user(db_session, email="parity@example.com")

    _add_entry(db_session, user.id, "preference", "device_profile", {"hrv_source": "galaxy_ring"})
    _add_entry(db_session, user.id, "schedule_item", "physio_2026_07",
               {"activity": "physio", "days": ["monday"], "hard": True})
    _add_entry(db_session, user.id, "injury", "left_hamstring",
               {"body_part": "left hamstring", "restrictions": ["sprint"]})

    fort = models.FortificationProfile(
        user_id=user.id, primary_target="anti_lateral_flexion", vehicle_bias=["swim"],
    )
    db_session.add(fort)
    db_session.commit()

    base_day = date(2026, 6, 28)
    for i in range(5):
        db_session.add(models.SamsungHRVReading(
            user_id=user.id,
            captured_at=base_day + timedelta(days=i),
            hrv_ms=50.0 + i,
            context="passive_overnight",
        ))
    db_session.commit()
    samsung_readings = (
        db_session.query(models.SamsungHRVReading)
        .filter(models.SamsungHRVReading.user_id == user.id,
                models.SamsungHRVReading.context != "session")
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .all()
    )

    state = current_state_mod.current_state(user.id, db_session, today=date(2026, 7, 4))

    # Freeze "now" identically in both modules — the identity section renders
    # wall-clock time to the minute, which would otherwise flake if the two
    # calls straddled a minute boundary.
    fixed_now = AEST.localize(datetime(2026, 7, 4, 9, 30, 0))
    monkeypatch.setattr(context_builder, "_now_aest", lambda: fixed_now)
    monkeypatch.setattr(old_context_builder, "_now_aest", lambda: fixed_now)

    common_kwargs = dict(
        user=user,
        connected_integrations=["hevy"],
        hevy_data=None,
        knowledge_entries=None,
        today_checkin=None,
        health_connect_records=None,
        samsung_hrv=samsung_readings,
        daily_record=None,
        engine_selection=None,
    )

    old_prompt = old_context_builder.build_system_prompt(
        structured_entries=state.knowledge_entries,
        fortification_profile=state.fortification_profile,
        **common_kwargs,
    )
    new_prompt = context_builder.build_system_prompt(
        state=state,
        **common_kwargs,
    )

    assert old_prompt == new_prompt
