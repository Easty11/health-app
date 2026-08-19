"""AM soreness prefill carries the last reported value (#224/#225/#226).

`derive_soreness_items` hardcoded 1 — the scale FLOOR — so every morning opened at
"asymptomatic" regardless of yesterday. A genuinely sore injury had to be re-entered
daily or the record understated it, and an unedited day silently reported recovery.

Two gates carry the most weight and neither is about the happy path:

  * the WINDOW boundary, asserted at exactly 7 and exactly 8 days with a carried
    value of 2 — never 3 — so a boundary that silently failed open could not pass by
    landing on the fallback it was supposed to avoid;
  * the GUARD, that prefill writes nothing. It is a read on the daily path, and a
    route that quietly created a `daily_records` row would look like it worked.

The readiness formula is pinned on a fixed payload. This brief changes what the form
SUGGESTS, never how a submission scores.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import models
from routers import checkin_v2


TODAY = date(2026, 8, 19)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _injury(db, user_id, *, key="hamstring_right", body_part="hamstring",
            side="right", active=True):
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="injury", key=key,
        value={"body_part": body_part, "side": side,
               "signal_type": "mechanical", "restrictions": []},
        source="chat", added_at=TODAY, active=active,
    )
    db.add(row)
    db.commit()
    return row


def _record(db, user_id, days_ago, soreness):
    """A `daily_records` row `days_ago` before TODAY carrying this soreness dict."""
    row = models.DailyRecord(
        user_id=user_id, date=TODAY - timedelta(days=days_ago), soreness=soreness,
    )
    db.add(row)
    db.commit()
    return row


def _prefill(db, user_id):
    return checkin_v2.derive_soreness_items(user_id, db, today=TODAY)


# The soreness key `injury_soreness_key` derives for the default fixture injury.
# Pinned, so a change to that helper fails here rather than making every carry
# assertion vacuously compare an empty dict.
KEY = "hamstring_right"


def test_the_fixture_key_is_what_the_helper_derives(db_session):
    from injury_trajectory import injury_soreness_key
    assert injury_soreness_key(
        {"body_part": "hamstring", "side": "right"}) == KEY


# ── the carry ────────────────────────────────────────────────────────────────

def test_a_value_reported_yesterday_is_carried(db_session):
    u = _user(db_session, "carry-1@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 1, {KEY: 3})
    assert _prefill(db_session, u.id) == {KEY: 3}


@pytest.mark.parametrize("reported", [1, 2, 3, 4, 5])
def test_every_in_scale_value_is_carried_verbatim(db_session, reported):
    """Includes 1. The fallback applies to ABSENCE, not to a low reading — a
    deliberately entered 1 must survive, or the exit condition it feeds is
    unreachable."""
    u = _user(db_session, f"carry-scale-{reported}@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 1, {KEY: reported})
    assert _prefill(db_session, u.id) == {KEY: reported}


def test_the_most_recent_record_containing_the_key_wins(db_session):
    u = _user(db_session, "carry-recent@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 3, {KEY: 5})
    _record(db_session, u.id, 1, {KEY: 2})
    assert _prefill(db_session, u.id) == {KEY: 2}


def test_a_key_absent_from_an_intervening_record_does_not_reset_the_carry(db_session):
    """The most recent record CONTAINING the key wins — not the most recent record.
    A day where the operator logged another injury but not this one must not silently
    drop this injury back to the fallback."""
    u = _user(db_session, "carry-gap@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 3, {KEY: 4})
    _record(db_session, u.id, 2, {"some_other_injury": 2})
    _record(db_session, u.id, 1, {"some_other_injury": 1})
    assert _prefill(db_session, u.id) == {KEY: 4}


def test_an_explicit_null_is_treated_as_absent_not_as_a_reading(db_session):
    """Matches `injury_trajectory._soreness_series`, which skips null values."""
    u = _user(db_session, "carry-null@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 3, {KEY: 4})
    _record(db_session, u.id, 1, {KEY: None})
    assert _prefill(db_session, u.id) == {KEY: 4}


# ── the window boundary ──────────────────────────────────────────────────────

def test_a_value_exactly_seven_days_old_is_still_carried(db_session):
    """Boundary, inclusive side. The carried value is 2, deliberately NOT the
    fallback 3 — a boundary test whose expected value equals the fallback cannot
    tell "carried correctly" from "fell through"."""
    u = _user(db_session, "win-7@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 7, {KEY: 2})
    assert _prefill(db_session, u.id) == {KEY: 2}


def test_a_value_exactly_eight_days_old_is_not_carried(db_session):
    """Boundary, exclusive side. Same value 2, so this asserts the window moved the
    result rather than the fallback coinciding with the carry."""
    u = _user(db_session, "win-8@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 8, {KEY: 2})
    assert _prefill(db_session, u.id) == {KEY: 3}


def test_the_lookback_constant_is_named_and_is_seven(db_session):
    """The window is a named constant, not an inline literal, and the boundary tests
    above are stated against its actual value."""
    assert checkin_v2._PREFILL_LOOKBACK_DAYS == 7


def test_a_stale_record_does_not_shadow_a_fresh_one(db_session):
    u = _user(db_session, "win-mix@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 10, {KEY: 5})
    _record(db_session, u.id, 2, {KEY: 2})
    assert _prefill(db_session, u.id) == {KEY: 2}


def test_a_future_dated_record_is_not_carried(db_session):
    """Defensive: the window is bounded at both ends, so a clock-skewed or
    hand-inserted future row cannot become "the last reported value"."""
    u = _user(db_session, "win-future@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, -1, {KEY: 5})
    _record(db_session, u.id, 2, {KEY: 2})
    assert _prefill(db_session, u.id) == {KEY: 2}


# ── the fallback ─────────────────────────────────────────────────────────────

def test_a_new_injury_with_no_history_prefills_three_not_one(db_session):
    """The behaviour change, asserted explicitly. This used to be 1."""
    u = _user(db_session, "fb-new@example.com")
    _injury(db_session, u.id)
    assert _prefill(db_session, u.id) == {KEY: 3}


def test_the_fallback_matches_the_readiness_scorers_own_default(db_session):
    """`calc_naive_baseline` already treats "nothing reported" as 3. The prefill now
    agrees with the scorer it feeds instead of contradicting it — asserted against
    the scorer's behaviour, not against a duplicated literal."""
    assert checkin_v2._SORENESS_NO_INFO == 3
    with_nothing = checkin_v2.calc_naive_baseline(
        sleep_quality=4, fatigue=3, soreness={}, motivation=7)
    with_explicit_three = checkin_v2.calc_naive_baseline(
        sleep_quality=4, fatigue=3, soreness={KEY: checkin_v2._SORENESS_NO_INFO},
        motivation=7)
    assert with_nothing == with_explicit_three


@pytest.mark.parametrize("corrupt", [0, 6, 9, -1, "3", 2.5, True, False, [3], {"v": 3}])
def test_an_unusable_stored_value_falls_back_rather_than_propagating(db_session, corrupt):
    """Out of range or wrong type resolves to the fallback. Notably NOT clamped to
    the nearest bound: a stored 9 is corrupt data, not an emphatic 5, and inventing a
    plausible number from it is how bad data stops looking bad.

    `True`/`False` are in the list on purpose — `bool` is an `int` subclass, so an
    unguarded range check would read `True` as a valid 1."""
    u = _user(db_session, "fb-corrupt@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 1, {KEY: corrupt})
    assert _prefill(db_session, u.id) == {KEY: 3}


def test_a_corrupt_reading_does_not_reach_past_itself_to_an_older_one(db_session):
    """A key PRESENT but unusable ends that key's search. Reaching back to an older
    valid value would silently substitute a number the operator never re-stated."""
    u = _user(db_session, "fb-nopast@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 3, {KEY: 5})
    _record(db_session, u.id, 1, {KEY: 99})
    assert _prefill(db_session, u.id) == {KEY: 3}


# ── multiple injuries ────────────────────────────────────────────────────────

def test_two_injuries_with_different_histories_prefill_independently(db_session):
    u = _user(db_session, "multi@example.com")
    _injury(db_session, u.id, key="hamstring_right", body_part="hamstring", side="right")
    _injury(db_session, u.id, key="shoulder_left", body_part="shoulder", side="left")
    _record(db_session, u.id, 1, {"hamstring_right": 4})
    _record(db_session, u.id, 9, {"shoulder_left": 5})   # out of window
    assert _prefill(db_session, u.id) == {"hamstring_right": 4, "shoulder_left": 3}


def test_a_resolved_injury_produces_no_item_even_with_history(db_session):
    """#222's resolve retires the whole entry, so the item disappears from the form —
    a carried value must not resurrect it."""
    u = _user(db_session, "multi-resolved@example.com")
    _injury(db_session, u.id, key="hamstring_right")
    dead = _injury(db_session, u.id, key="shoulder_left",
                   body_part="shoulder", side="left", active=False)
    _record(db_session, u.id, 1, {"hamstring_right": 2, "shoulder_left": 5})

    assert _prefill(db_session, u.id) == {"hamstring_right": 2}
    assert dead.active is False


def test_no_active_injuries_is_an_empty_dict(db_session):
    u = _user(db_session, "multi-none@example.com")
    assert _prefill(db_session, u.id) == {}


def test_another_users_records_are_never_carried(db_session):
    mine = _user(db_session, "iso-mine@example.com")
    theirs = _user(db_session, "iso-theirs@example.com")
    _injury(db_session, mine.id)
    _record(db_session, theirs.id, 1, {KEY: 5})
    assert _prefill(db_session, mine.id) == {KEY: 3}


# ── GUARD: prefill is a read ─────────────────────────────────────────────────

class _StatementSpy:
    """Records every SQL statement executed on this session's engine."""

    def __init__(self, session):
        self.engine = session.get_bind()
        self.statements: list[str] = []

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        self.statements.append(statement)

    @property
    def selects(self):
        return [s for s in self.statements if s.lstrip().upper().startswith("SELECT")]

    @property
    def writes(self):
        return [s for s in self.statements
                if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]


def test_prefill_writes_nothing(db_session):
    """GUARD. Prefill must not create a `daily_records` row or mutate one. Asserted
    two ways — no write statement reaches the database, and the row count and stored
    payload are unchanged — because a count alone would miss an in-place UPDATE."""
    u = _user(db_session, "guard-write@example.com")
    _injury(db_session, u.id)
    _record(db_session, u.id, 1, {KEY: 2})

    before_count = db_session.query(models.DailyRecord).count()
    with _StatementSpy(db_session) as spy:
        assert _prefill(db_session, u.id) == {KEY: 2}
    assert spy.writes == [], f"prefill executed writes: {spy.writes}"

    db_session.expire_all()
    assert db_session.query(models.DailyRecord).count() == before_count
    rows = db_session.query(models.DailyRecord).filter_by(user_id=u.id).all()
    assert [r.soreness for r in rows] == [{KEY: 2}]


def test_prefill_creates_no_record_for_a_user_who_has_none(db_session):
    """GUARD, the case that would be easiest to get wrong — no row exists, and the
    prefill still must not make one."""
    u = _user(db_session, "guard-empty@example.com")
    _injury(db_session, u.id)
    with _StatementSpy(db_session) as spy:
        assert _prefill(db_session, u.id) == {KEY: 3}
    assert spy.writes == []
    assert db_session.query(models.DailyRecord).filter_by(user_id=u.id).count() == 0


# ── query count does not scale with injury count ─────────────────────────────

def _select_count(db, user_id):
    with _StatementSpy(db) as spy:
        _prefill(db, user_id)
    return len(spy.selects)


def test_query_count_does_not_scale_with_active_injury_count(db_session):
    """One query for the injuries, one for the records — regardless of how many
    injuries there are. A per-key lookup would be an N+1 on a route in the daily
    path. Asserted as a comparison between 1 and 8 injuries, not against a magic
    number, so an unrelated extra query does not make this fail spuriously."""
    one = _user(db_session, "n1-one@example.com")
    _injury(db_session, one.id)
    _record(db_session, one.id, 1, {KEY: 2})

    many = _user(db_session, "n1-many@example.com")
    for i in range(8):
        _injury(db_session, many.id, key=f"site_{i}", body_part=f"site{i}", side="left")
    _record(db_session, many.id, 1, {f"site{i}_left": 2 for i in range(8)})

    assert len(_prefill(db_session, many.id)) == 8, "precondition: 8 items derived"
    assert _select_count(db_session, many.id) == _select_count(db_session, one.id)


# ── the readiness formula does not move ──────────────────────────────────────

FIXED_PAYLOAD = dict(sleep_quality=4, fatigue=3, soreness={"hamstring_right": 4},
                     motivation=7)


def test_the_readiness_formula_is_unchanged(db_session):
    """A fixed submitted payload scores identically. This brief changes what the form
    SUGGESTS, never how a submission scores — the weighting, the max() across items
    and the (v-1)*2.5 transform are all pinned by this one arithmetic identity."""
    assert checkin_v2.calc_naive_baseline(**FIXED_PAYLOAD) == 6.4
    # Spelled out so a weighting change cannot be absorbed by adjusting the constant:
    # sleep 4*2=8 *0.30 + (10-3)*0.30 + (10-(4-1)*2.5)*0.20 + 7*0.20
    expected = 8 * 0.30 + 7 * 0.30 + (10 - 7.5) * 0.20 + 7 * 0.20
    assert checkin_v2.calc_naive_baseline(**FIXED_PAYLOAD) == round(expected, 2)


def test_max_not_mean_across_items_still_holds(db_session):
    """The one property of the soreness term the prefill change could plausibly be
    mistaken for licence to revisit."""
    quiet_and_severe = checkin_v2.calc_naive_baseline(
        sleep_quality=4, fatigue=3, soreness={"a": 1, "b": 5}, motivation=7)
    severe_only = checkin_v2.calc_naive_baseline(
        sleep_quality=4, fatigue=3, soreness={"b": 5}, motivation=7)
    assert quiet_and_severe == severe_only


def test_the_documented_cost_of_the_new_fallback(db_session):
    """The known consequence, pinned rather than left in prose: for a user with a new
    injury and no history, an untouched submission now carries 3 where it carried 1,
    costing ~1.0 readiness point. That is the intended effect of a more honest input,
    not a regression — recorded here so it is a decision and not a surprise."""
    old_default = checkin_v2.calc_naive_baseline(
        sleep_quality=4, fatigue=3, soreness={KEY: 1}, motivation=7)
    new_default = checkin_v2.calc_naive_baseline(
        sleep_quality=4, fatigue=3, soreness={KEY: checkin_v2._SORENESS_NO_INFO},
        motivation=7)
    assert old_default - new_default == 1.0
