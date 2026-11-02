"""Hook coverage: an injury written outside the upsert still gets its engine-default proposals.

The upsert hook (`_propose_engine_defaults`) cannot see an injury that a seed script writes straight to the
ORM. `seed_engine._seed_injuries` is such a writer, and it now calls `propose_engine_defaults_for_row` on
each row it creates, in the same transaction. What is pinned:
  * a fresh seed proposes exactly what the planner implies for each seeded injury, including the Q102
    entry-30 case (`pes anserine` reaches the knee set through its alias), and every one is a PROPOSAL
    (status proposed, no authority, source system) that blocks nothing;
  * re-seeding writes nothing more, and a resolved injury is not resurrected nor given proposals;
  * the helper itself: only an ACTIVE INJURY row, idempotent, in the caller's transaction (no commit), and a
    planning fault never raises into the seed.
`probe_resolver._synthetic_db` is deliberately NOT a caller: it builds a throwaway in-memory database of PINNED
fixtures for a live-model harness (its comment: "without inheriting [the ledger's] mutability"), so there is
no ledger there to close a gap in.
"""
import models
from engine import engine_defaults as ed
from engine import selection
from routers.knowledge import propose_engine_defaults_for_row
from seed_engine import _INJURY_SEED, _seed_injuries


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _defaults(db, user_id):
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint").all()
    return [r for r in rows if r.key.startswith(ed.DEFAULT_KEY_PREFIX)]


def _expected(db_session=None):
    out = {}
    for inj in _INJURY_SEED:
        out[inj["key"]] = {c["region_key"] for c in ed.candidate_regions(inj["value"])}
    return out


def test_a_fresh_seed_proposes_exactly_what_the_planner_implies(db_session):
    u = _user(db_session, "seedprop@example.com")
    _seed_injuries(db_session, u.id)
    by_parent: dict[str, set[str]] = {}
    for r in _defaults(db_session, u.id):
        by_parent.setdefault(r.value["parent_key"], set()).add(r.value["scope"]["region_keys"][0])
    expected = {k: v for k, v in _expected().items() if v}
    assert by_parent == expected
    assert len(_defaults(db_session, u.id)) == sum(len(v) for v in expected.values()) == 15


def test_pes_anserine_reaches_the_knee_set_through_the_seed(db_session):
    """Ledger entry 30 (Q102): the bare substring never matched; the declared alias does."""
    u = _user(db_session, "seedpes@example.com")
    _seed_injuries(db_session, u.id)
    regions = {r.value["scope"]["region_keys"][0] for r in _defaults(db_session, u.id)
               if r.value["parent_key"] == "injury_pes_anserine_left"}
    assert regions == {"single_leg_hop", "change_of_direction", "deceleration_landing"}


def test_every_seeded_proposal_is_a_proposal_and_blocks_nothing(db_session):
    u = _user(db_session, "seedinert@example.com")
    _seed_injuries(db_session, u.id)
    rows = _defaults(db_session, u.id)
    assert rows and all(r.active and r.source == "system" for r in rows)
    assert all((r.value["status"], r.value["asserted_by"], r.value["kind"]) == ("proposed", None, "block")
               for r in rows)
    assert selection.gather_active_constraints(db_session, u.id) == []
    queue = selection.compute_probe_queue(db_session, u.id, profile=None, loaded_region_keys=set())
    other = _user(db_session, "seedinert-control@example.com")        # same queue as a user with no injuries
    assert queue == selection.compute_probe_queue(db_session, other.id, profile=None, loaded_region_keys=set())


def test_reseeding_writes_no_further_proposals(db_session):
    u = _user(db_session, "seedagain@example.com")
    _seed_injuries(db_session, u.id)
    before = sorted(r.key for r in _defaults(db_session, u.id))
    assert _seed_injuries(db_session, u.id) == 0
    assert sorted(r.key for r in _defaults(db_session, u.id)) == before


def test_a_resolved_injury_is_neither_resurrected_nor_given_new_proposals(db_session):
    u = _user(db_session, "seedresolved@example.com")
    _seed_injuries(db_session, u.id)
    row = db_session.query(models.UserKnowledgeEntry).filter_by(
        user_id=u.id, type="injury", key="injury_hamstring_right").one()
    row.active = False
    for r in _defaults(db_session, u.id):                      # the operator declined its defaults
        if r.value["parent_key"] == "injury_hamstring_right":
            r.active = False
    db_session.commit()
    n = len(_defaults(db_session, u.id))
    assert _seed_injuries(db_session, u.id) == 0
    assert len(_defaults(db_session, u.id)) == n
    assert not [r for r in _defaults(db_session, u.id)
                if r.value["parent_key"] == "injury_hamstring_right" and r.active]


# ── the helper ────────────────────────────────────────────────────────────────

def _row(db, user, key="injury_knee_left", type_="injury", active=True,
         value=None):
    row = models.UserKnowledgeEntry(
        user_id=user.id, type=type_, key=key, source="system", active=active,
        value=value or {"body_part": "knee", "side": "left", "signal_type": "mechanical"})
    db.add(row)
    return row


def test_the_helper_stages_for_an_active_injury_and_is_idempotent(db_session):
    u = _user(db_session, "helper@example.com")
    row = _row(db_session, u)
    assert propose_engine_defaults_for_row(db_session, row) == 3
    assert propose_engine_defaults_for_row(db_session, row) == 0
    assert len(_defaults(db_session, u.id)) == 3


def test_the_helper_ignores_anything_but_an_active_injury(db_session, caplog):
    """Not merely "stages none": the validator would refuse a proposal under an inactive parent anyway, so the
    guard's job is to not TRY, which would log a refusal for every call. Pin the silence as well as the count."""
    u = _user(db_session, "helper-ignore@example.com")
    with caplog.at_level("WARNING"):
        assert propose_engine_defaults_for_row(db_session, _row(db_session, u, active=False)) == 0
        assert propose_engine_defaults_for_row(db_session, _row(db_session, u, key="pref", type_="preference")) == 0
    assert _defaults(db_session, u.id) == []
    assert "engine defaults" not in caplog.text


def test_the_helper_works_in_the_callers_transaction_and_does_not_commit(db_session):
    u = _user(db_session, "helper-txn@example.com")
    row = _row(db_session, u)
    propose_engine_defaults_for_row(db_session, row)
    assert len(_defaults(db_session, u.id)) == 3             # visible in this transaction
    db_session.rollback()
    assert _defaults(db_session, u.id) == []                 # and gone with it: the helper committed nothing


def test_a_planning_fault_never_raises_into_the_seed(db_session, monkeypatch):
    u = _user(db_session, "helper-fault@example.com")
    row = _row(db_session, u)

    def boom(*a, **k):
        raise RuntimeError("planner fault")
    monkeypatch.setattr(ed, "plan_engine_defaults", boom)
    assert propose_engine_defaults_for_row(db_session, row) == 0
    db_session.commit()
    assert db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, type="injury").count() == 1
