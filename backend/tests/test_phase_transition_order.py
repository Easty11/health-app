"""4 Oct 2026 -- the phase-change save validates the WHOLE write before it creates a Hevy folder.

The 4 Oct fault: `POST /engine/phase/transition` created the Hevy folder first (#317's order), then the
transaction refused the microcycle (`slots[1].capacity: unknown capacity 'Gym'`) and nothing was
written, leaving an orphan folder -- twice, on the retry. The Hevy API (as the connector wraps it) has
create and get for folders and no delete, so an orphan cannot be compensated; the order is the fix.

The tests observe ORDER, not just outcome: every Hevy call and every commit lands in one event log, so
"the folder was created, and only then did anything commit" is an assertion, and so is "a refused form
never reached Hevy". Hevy is faked at the connector class (the route's own seam); no network.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

import encryption
import models
from auth import get_current_user
from database import get_db
from engine import taxonomy
from engine import training_phase as phase_mod
from routers import training_phase as tp

TODAY = datetime.now(timezone.utc).date()
PRIOR = TODAY - timedelta(days=14)
KEY = "phase_folders"


def _user(db):
    u = models.User(email="order@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _hevy(db, uid):
    db.add(models.UserIntegration(user_id=uid, provider="hevy", api_key_encrypted=encryption.encrypt("k")))
    db.commit()


def _micro(*slots):
    return {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": list(slots)}]}


GOOD_SLOT = {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}


def _phase(*slots, label="aerobic base"):
    return {"label": label, "probe_posture": "held", "microcycle": _micro(*(slots or (GOOD_SLOT,))),
            "entered_on": TODAY.isoformat(), "asserted_by": "user",
            "asserted_on": TODAY.isoformat(), "source": "api"}


def _body(phase, **kw):
    return {"phase": phase, "schedule_items": [], **kw}


class Log:
    """One ordered record of every Hevy call and every commit."""

    def __init__(self):
        self.events: list[str] = []


@pytest.fixture()
def world(db_session, monkeypatch):
    log = Log()
    u = _user(db_session)
    _hevy(db_session, u.id)
    event.listen(db_session, "after_commit", lambda s: log.events.append("commit"))

    class FakeHevy:
        fail = False

        def __init__(self, api_key):
            pass

        async def create_routine_folder(self, title):
            log.events.append(f"create_folder:{title}")
            if FakeHevy.fail:
                raise RuntimeError("hevy is down")
            return {"routine_folder": {"id": 4242, "title": title}}

    monkeypatch.setattr(tp, "HevyClient", FakeHevy)
    app = FastAPI()
    app.include_router(tp.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    log.events.clear()                       # setup commits are not the route's
    return type("W", (), {"db": db_session, "u": u, "log": log, "client": TestClient(app), "hevy": FakeHevy})


def _phases(db, uid):
    return db.query(models.TrainingPhase).filter_by(user_id=uid).count()


def _folders_pref(db, uid):
    row = (db.query(models.UserKnowledgeEntry)
           .filter_by(user_id=uid, type="preference", key=KEY, active=True).first())
    return None if row is None else row.value


# -- a refused form never reaches Hevy ---------------------------------------------------------------

def test_the_4_oct_capacity_refusal_creates_no_folder(world):
    """slots[1].capacity = 'Gym': refused with the validator's own message, no Hevy call at all, no commit,
    no orphan wording, and nothing written."""
    bad = {"capacity": "Gym", "sessions_per_cycle": 3, "minutes": 60}
    r = world.client.post("/engine/phase/transition",
                          json=_body(_phase(GOOD_SLOT, bad), new_folder_name="Aerobic Base Phase"))
    assert r.status_code == 422
    assert "unknown capacity 'Gym'" in r.json()["detail"] and "slots[1].capacity" in r.json()["detail"]
    assert "orphan" not in r.json()["detail"].lower() and "already created" not in r.json()["detail"]
    assert world.log.events == []                                  # no Hevy call, no commit
    assert _phases(world.db, world.u.id) == 0 and _folders_pref(world.db, world.u.id) is None


def test_the_second_metabolic_slot_refusal_creates_no_folder(world):
    """The 4 Oct retry: two load_window 'metabolic' slots (the duplicate rule). Same guarantee."""
    m = {"load_window": "metabolic", "device_sports": ["Running"], "sessions_per_cycle": 2, "minutes": 40}
    m2 = {"load_window": "metabolic", "device_sports": ["Cycling"], "sessions_per_cycle": 1, "minutes": 40}
    r = world.client.post("/engine/phase/transition",
                          json=_body(_phase(GOOD_SLOT, m, m2), new_folder_name="Aerobic Base Phase"))
    assert r.status_code == 422 and "duplicate load_window" in r.json()["detail"]
    assert world.log.events == [] and _phases(world.db, world.u.id) == 0


def test_a_schedule_overlap_is_refused_before_the_folder_and_carries_no_orphan_key(world):
    """The structured F17 refusal keeps its shape, and `orphan_folder` is absent: nothing was created."""
    phase_mod.open_phase(world.db, world.u.id, {**_phase(), "entered_on": PRIOR.isoformat(),
                                                "asserted_on": PRIOR.isoformat()})
    tp._stage_upsert_entry(world.u.id, tp.KnowledgeEntryIn(type="schedule_item", key="swim", source="api", value={
        "activity": "swim", "days": ["tuesday"], "hard": False, "expected_load": "moderate",
        "time_of_day": "evening", "same_day_training": False, "duration_weeks": None, "season_end": None}),
        world.db)
    world.db.commit()
    world.log.events.clear()
    clash = {"activity": "gym", "days": ["tuesday"], "hard": False, "expected_load": "moderate",
             "time_of_day": "evening", "same_day_training": False, "duration_weeks": None, "season_end": None}
    r = world.client.post("/engine/phase/transition", json={
        "phase": _phase(label="next"), "new_folder_name": "Block",
        "schedule_items": [{"action": "upsert", "key": "gym_tue", "value": clash}]})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "day_time_clash" and d["key"] == "gym_tue" and "orphan_folder" not in d
    assert world.log.events == []                                  # still nothing external, nothing committed


# -- a valid form creates the folder once, then commits ----------------------------------------------

def test_a_valid_form_creates_the_folder_then_commits_once_and_links_it(world):
    r = world.client.post("/engine/phase/transition",
                          json=_body(_phase(), new_folder_name="Aerobic Base Phase"))
    assert r.status_code == 200 and r.json()["no_op"] is False
    assert world.log.events == ["create_folder:Aerobic Base Phase", "commit"]     # create strictly first, then ONE commit
    assert _phases(world.db, world.u.id) == 1
    assert _folders_pref(world.db, world.u.id) == {"aerobic base": "4242"}


def test_an_existing_folder_is_linked_with_no_hevy_call_and_a_single_pass(world, monkeypatch):
    calls = []
    real = tp._apply_phase_transition
    monkeypatch.setattr(tp, "_apply_phase_transition", lambda *a, **k: calls.append(k.get("commit", True)) or real(*a, **k))
    r = world.client.post("/engine/phase/transition", json=_body(_phase(), folder_id="777"))
    assert r.status_code == 200
    assert calls == [True]                                          # no validate-only pass without an external call
    assert not any(e.startswith("create_folder") for e in world.log.events)
    assert _folders_pref(world.db, world.u.id) == {"aerobic base": "777"}


def test_the_validate_pass_is_rolled_back_and_the_real_write_follows(world, monkeypatch):
    calls = []
    real = tp._apply_phase_transition
    monkeypatch.setattr(tp, "_apply_phase_transition", lambda *a, **k: calls.append(k.get("commit", True)) or real(*a, **k))
    r = world.client.post("/engine/phase/transition", json=_body(_phase(), new_folder_name="F"))
    assert r.status_code == 200 and calls == [False, True]          # validate-only first, then the write
    assert world.log.events.count("commit") == 1                    # the validate pass committed nothing


# -- the remaining failure windows --------------------------------------------------------------------

def test_a_hevy_failure_writes_nothing_and_commits_nothing(world):
    world.hevy.fail = True
    r = world.client.post("/engine/phase/transition", json=_body(_phase(), new_folder_name="F"))
    assert r.status_code == 502 and "nothing written" in r.json()["detail"]
    assert world.log.events == ["create_folder:F"]                  # attempted, failed, no commit
    assert _phases(world.db, world.u.id) == 0 and _folders_pref(world.db, world.u.id) is None


def test_a_fault_in_the_real_write_after_the_folder_still_names_the_orphan(world, monkeypatch):
    """The one window left (a database fault or a race between the passes): the folder exists and cannot
    be deleted through the API, so the response names it. Validation can no longer cause this."""
    real = tp._apply_phase_transition

    def flaky(*a, **k):
        if k.get("commit", True):
            raise ValueError("simulated fault in the real write")
        return real(*a, **k)
    monkeypatch.setattr(tp, "_apply_phase_transition", flaky)
    r = world.client.post("/engine/phase/transition", json=_body(_phase(), new_folder_name="Aerobic Base Phase"))
    assert r.status_code == 422
    assert "'Aerobic Base Phase' was already created" in r.json()["detail"]
    assert world.log.events == ["create_folder:Aerobic Base Phase"]
    assert _phases(world.db, world.u.id) == 0


def test_hevy_not_connected_is_refused_before_anything(world):
    world.db.query(models.UserIntegration).delete()
    world.db.commit()
    world.log.events.clear()
    r = world.client.post("/engine/phase/transition", json=_body(_phase(), new_folder_name="F"))
    assert r.status_code == 422 and "not connected" in r.json()["detail"] and world.log.events == []


def test_an_identical_resubmit_is_still_a_noop_with_no_second_folder(world):
    first = world.client.post("/engine/phase/transition", json=_body(_phase(), new_folder_name="F"))
    assert first.status_code == 200
    world.log.events.clear()
    again = world.client.post("/engine/phase/transition", json=_body(_phase(), new_folder_name="F"))
    assert again.status_code == 200 and again.json()["no_op"] is True and world.log.events == []


# -- the vocabularies the form's pickers offer ----------------------------------------------------------

def test_slot_options_are_exactly_what_the_validator_accepts():
    opts = phase_mod.slot_options()
    assert opts["load_window"] == ["metabolic"] and "gym" not in opts["capacity"] and opts["capacity"]
    assert opts["capacity"] == [t.lower() for t in taxonomy.capacity_tokens()]
    for cap in opts["capacity"]:                                    # every offered capacity is writable as offered
        phase_mod.validate_microcycle(_micro({"capacity": cap, "sessions_per_cycle": 1, "minutes": 30}))
    for lw in opts["load_window"]:
        phase_mod.validate_microcycle(_micro({"load_window": lw, "device_sports": ["Running"],
                                              "sessions_per_cycle": 1, "minutes": 30}))


def test_the_draft_carries_slot_options(world):
    r = world.client.get("/engine/phase/transition/draft")
    assert r.status_code == 200 and r.json()["slot_options"] == phase_mod.slot_options()
