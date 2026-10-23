"""Fallback-key `encryption` and `scripts.rotate_fernet`.

Keys are generated in-test (`Fernet.generate_key()`); none is read from the environment or a file.
Rows are real `UserIntegration` rows in the FK-enforced SQLite session (conftest), and every claim
about a row is asserted by reading the DB back, not by trusting the script's report. The stdout test
is what makes DECISIONS_LOG #111 a test rather than a convention.
"""
import io
from contextlib import redirect_stderr, redirect_stdout

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

import encryption
import models
from scripts import rotate_fernet as rf

SENTINEL = "SENTINEL-PLAINTEXT-4f2a"


def _key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture()
def keys():
    """Three fresh keys; the module's own configuration is restored afterwards."""
    saved = (encryption._current, encryption._multi, encryption._key_count)
    yield _key(), _key(), _key()
    encryption._current, encryption._multi, encryption._key_count = saved


def _under(key: str, plaintext: str) -> str:
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def _stored(db, row_id: int) -> str:
    return db.execute(text("SELECT api_key_encrypted FROM user_integrations WHERE id = :i"), {"i": row_id}).scalar_one()


def _add(db, user_id: int, provider: str, token: str) -> int:
    row = models.UserIntegration(user_id=user_id, provider=provider, api_key_encrypted=token)
    db.add(row)
    db.commit()
    return row.id


@pytest.fixture()
def world(db_session, keys):
    """A and B are the old and new keys; C is a stranger. Rows: 1 current(B), 2+3 previous(A)."""
    a, b, c = keys
    db = db_session
    for uid in (1, 2, 3, 4):
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
    db.commit()
    encryption._configure(b, a)
    ids = {
        "current": _add(db, 1, "hevy", _under(b, SENTINEL + "-cur")),
        "prev_garmin": _add(db, 2, "garmin", _under(a, SENTINEL + "-garmin")),
        "prev_polar": _add(db, 3, "polar", _under(a, SENTINEL + "-polar")),
    }
    return db, ids, (a, b, c)


def _run(fn, *args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = fn(*args)
    return code, out.getvalue(), err.getvalue()


def _dry(db):
    out = io.StringIO()
    return rf.dry_run(db.get_bind(), out), out.getvalue()


def _confirm(db):
    out, err = io.StringIO(), io.StringIO()
    return rf.confirm_run(db.get_bind(), out, err), out.getvalue(), err.getvalue()


# --- encryption -----------------------------------------------------------------------------------

def test_row_written_under_a_decrypts_after_swap_and_new_writes_use_b_alone(keys):
    a, b, _ = keys
    old = _under(a, "hevy-key-1")
    encryption._configure(b, a)
    assert encryption.decrypt(old) == "hevy-key-1"
    fresh = encryption.encrypt("hevy-key-2")
    assert Fernet(b.encode()).decrypt(fresh.encode()) == b"hevy-key-2"
    with pytest.raises(InvalidToken):
        Fernet(a.encode()).decrypt(fresh.encode())
    assert encryption.active_key_count() == 2


def test_without_a_previous_key_behaviour_is_single_key(keys):
    a, b, _ = keys
    encryption._configure(b, None)
    assert encryption.active_key_count() == 1
    encryption._configure(b, "")  # an empty FERNET_KEY_PREVIOUS counts as unset
    assert encryption.active_key_count() == 1
    with pytest.raises(InvalidToken):
        encryption.decrypt(_under(a, "x"))


def test_malformed_previous_key_fails_loudly_and_leaves_state_intact(keys):
    a, b, _ = keys
    encryption._configure(b, a)
    with pytest.raises(ValueError):
        encryption._configure(b, "not-a-fernet-key")
    assert encryption.active_key_count() == 2  # the failed call changed nothing
    assert encryption.decrypt(_under(a, "still-readable")) == "still-readable"


def test_rotate_moves_a_token_to_the_current_key(keys):
    a, b, _ = keys
    encryption._configure(b, a)
    moved = encryption.rotate(_under(a, "p"))
    assert Fernet(b.encode()).decrypt(moved.encode()) == b"p"


# --- dry run --------------------------------------------------------------------------------------

def test_dry_run_classifies_and_writes_nothing(world):
    db, ids, (_, _, c) = world
    bad = _add(db, 4, "polar", _under(c, SENTINEL + "-stranger"))
    before = {i: _stored(db, i) for i in (*ids.values(), bad)}

    code, out = _dry(db)

    assert code == rf.EXIT_UNREADABLE
    assert f"id={ids['current']} user_id=1 provider=hevy state=current" in out
    assert f"id={ids['prev_garmin']} user_id=2 provider=garmin state=previous" in out
    assert f"id={ids['prev_polar']} user_id=3 provider=polar state=previous" in out
    assert f"id={bad} user_id=4 provider=polar state=unreadable" in out
    assert "rows=4 current=1 previous=2 unreadable=1" in out
    assert {i: _stored(db, i) for i in before} == before


def test_dry_run_exits_zero_when_every_row_is_readable(world):
    db, _, _ = world
    code, out = _dry(db)
    assert code == 0
    assert "unreadable=0" in out


# --- confirm --------------------------------------------------------------------------------------

def test_confirm_rotates_previous_rows_only(world):
    db, ids, (a, b, _) = world
    current_before = _stored(db, ids["current"])

    code, out, err = _confirm(db)

    assert code == 0, err
    assert _stored(db, ids["current"]) == current_before  # byte-identical
    fb = Fernet(b.encode())
    assert fb.decrypt(_stored(db, ids["prev_garmin"]).encode()).decode() == SENTINEL + "-garmin"
    assert fb.decrypt(_stored(db, ids["prev_polar"]).encode()).decode() == SENTINEL + "-polar"
    assert f"id={ids['prev_garmin']} user_id=2 provider=garmin state=rotated" in out
    assert f"id={ids['current']}" not in out
    assert "rotated=2 already_current=1 rows=3" in out
    # the previous key is now dead weight: dropping it loses nothing
    encryption._configure(b, None)
    with db.get_bind().connect() as conn:
        assert {r.state for r in rf.classify(conn)[0]} == {rf.CURRENT}


def test_confirm_is_idempotent(world):
    db, ids, _ = world
    assert _confirm(db)[0] == 0
    after_first = {i: _stored(db, i) for i in ids.values()}
    code, out, _ = _confirm(db)
    assert code == 0
    assert "rotated=0" in out
    assert {i: _stored(db, i) for i in ids.values()} == after_first
    assert _dry(db)[0] == 0


def test_confirm_with_an_unreadable_row_writes_nothing(world):
    db, ids, (_, _, c) = world
    bad = _add(db, 4, "polar", _under(c, SENTINEL + "-stranger"))
    before = {i: _stored(db, i) for i in (*ids.values(), bad)}

    code, out, err = _confirm(db)

    assert code == rf.EXIT_UNREADABLE
    assert f"id={bad} user_id=4 provider=polar state=unreadable" in err
    assert out == ""
    assert {i: _stored(db, i) for i in before} == before  # not even the previous rows moved


def test_confirm_with_one_key_refuses(db_session, keys):
    a, b, _ = keys
    db = db_session
    db.add(models.User(id=1, email="u1@example.com", hashed_password="x"))
    db.commit()
    encryption._configure(b, None)
    rid = _add(db, 1, "hevy", _under(b, SENTINEL))
    before = _stored(db, rid)

    code, out, err = _confirm(db)

    assert code == rf.EXIT_REFUSED
    assert "no previous key set; nothing to rotate from" in err
    assert _stored(db, rid) == before


def test_failed_reread_rolls_the_whole_transaction_back(world, monkeypatch):
    db, ids, _ = world
    before = {i: _stored(db, i) for i in ids.values()}
    real = encryption.decrypts_under_current
    calls = {"n": 0}

    def flaky(token):  # classification passes; every post-write re-read "fails"
        calls["n"] += 1
        return real(token) if calls["n"] <= len(ids) else False

    monkeypatch.setattr(encryption, "decrypts_under_current", flaky)

    code, out, err = _confirm(db)

    assert code == rf.EXIT_REREAD_FAILED
    assert {i: _stored(db, i) for i in ids.values()} == before


def test_a_row_rewritten_since_the_read_aborts_and_is_not_overwritten(world, monkeypatch):
    db, ids, (_, b, _) = world
    winner = _under(b, "written-by-the-app-meanwhile")
    real = rf.encryption.rotate

    def racing(token):  # the app re-stores a credential between the script's read and its UPDATE
        db.execute(text("UPDATE user_integrations SET api_key_encrypted = :w WHERE id = :i"),
                   {"w": winner, "i": ids["prev_garmin"]})
        db.commit()
        return real(token)

    monkeypatch.setattr(rf.encryption, "rotate", racing)

    code, _, err = _confirm(db)

    assert code == rf.EXIT_REREAD_FAILED
    assert _stored(db, ids["prev_garmin"]) == winner


# --- #111: nothing secret reaches stdout or stderr -----------------------------------------------

def _assert_clean(db, ids, *streams):
    secrets = [SENTINEL] + [_stored(db, i) for i in ids]
    for s in streams:
        for secret in secrets:
            assert secret not in s


def test_no_mode_prints_a_plaintext_or_a_ciphertext(world):
    db, ids, (_, _, c) = world
    bad = _add(db, 4, "polar", _under(c, SENTINEL + "-stranger"))
    every = (*ids.values(), bad)
    cipher_before = [_stored(db, i) for i in every]

    _, dry_unreadable = _dry(db)                    # dry run with an unreadable row
    _, c_out, c_err = _confirm(db)                  # refused on the unreadable row
    db.execute(text("DELETE FROM user_integrations WHERE id = :i"), {"i": bad})
    db.commit()
    _, ok_out, ok_err = _confirm(db)                # a real rotation
    _, dry_after = _dry(db)
    cipher_after = [_stored(db, i) for i in ids.values()]

    for stream in (dry_unreadable, c_out, c_err, ok_out, ok_err, dry_after):
        assert SENTINEL not in stream
        for token in (*cipher_before, *cipher_after):
            assert token not in stream


def test_main_entrypoint_is_ascii_and_clean(world, monkeypatch, capsys):
    import database

    db, ids, _ = world
    monkeypatch.setattr(database, "engine", db.get_bind())
    assert rf.main(["--dry-run"]) == 0
    assert rf.main(["--confirm"]) == 0
    captured = capsys.readouterr()
    (captured.out + captured.err).encode("ascii")
    _assert_clean(db, ids.values(), captured.out, captured.err)
