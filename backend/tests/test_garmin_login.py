"""`scripts.garmin_login` -- stdout must be EXACTLY the token blob.

The operator runs `python -m scripts.garmin_login > token.json` and POSTs the file. A prompt on
stdout ends up in that file ahead of the JSON (plain `input()` writes its prompt to stdout when
stdout is redirected), so the token no longer parses. Guarded here with the streams captured
separately: stdout is the blob and nothing else, prompts and status are stderr.
"""
import io
import sys

import pytest

from scripts import garmin_login as gl

BLOB = '{"di_token": "T", "di_refresh_token": "R", "di_client_id": "C"}'


class FakeClient:
    def dumps(self):
        return BLOB


class FakeGarmin:
    mfa = False
    fail_login = False
    fail_mfa = False

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.email, self.password, self.client = email, password, FakeClient()

    def login(self):
        if self.fail_login:
            raise RuntimeError("bad credentials")
        return ("needs_mfa", {"s": 1}) if self.mfa else ("ok", None)

    def resume_login(self, state, code):
        if self.fail_mfa:
            raise RuntimeError("bad code")
        self.mfa_code_seen = code


@pytest.fixture()
def run(monkeypatch, capsys):
    def go(stdin_text, **flags):
        garmin = type("G", (FakeGarmin,), flags)
        monkeypatch.setattr(gl, "Garmin", garmin)
        monkeypatch.setattr(gl.getpass, "getpass", lambda prompt="": "hunter2-password")
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
        rc = gl.main()
        cap = capsys.readouterr()
        return rc, cap.out, cap.err
    return go


def test_stdout_is_exactly_the_blob_without_mfa(run):
    rc, out, err = run("deb@example.com\n")
    assert rc == 0 and out == BLOB
    assert "Garmin email:" in err and "Login OK" in err


def test_stdout_is_exactly_the_blob_with_mfa_and_the_mfa_prompt_is_stderr(run):
    rc, out, err = run("deb@example.com\n123456\n", mfa=True)
    assert rc == 0 and out == BLOB
    assert "Garmin email:" in err and "MFA code:" in err
    assert "Garmin email" not in out and "MFA" not in out


def test_the_password_never_appears_on_either_stream(run):
    _, out, err = run("deb@example.com\n123456\n", mfa=True)
    assert "hunter2-password" not in out and "hunter2-password" not in err


def test_failures_emit_nothing_on_stdout(run):
    rc, out, err = run("deb@example.com\n", fail_login=True)
    assert rc == 1 and out == "" and "Login failed" in err
    rc, out, err = run("deb@example.com\n000000\n", mfa=True, fail_mfa=True)
    assert rc == 1 and out == "" and "MFA verification failed" in err
