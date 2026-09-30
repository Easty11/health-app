r"""
Out-of-band interactive Garmin login → token blob (GUARD: the platform never stores
or receives the Garmin password).

The operator runs this LOCALLY. It prompts for email, password (never echoed), and
the MFA code, performs the garminconnect (curl_cffi) OAuth login, and prints ONLY the resulting token
JSON to stdout. Everything else — prompts, status, errors — goes to stderr, so the
stdout capture is exactly the blob to POST to /integrations/garmin/token.

LOCAL PREREQUISITES (this runs on your machine, not in the container):
  * Python >= 3.12. `garminconnect` 0.3.11 requires it; pip on an older Python cannot find it.
  * `pip install garminconnect==0.3.11`, the version pinned in backend/requirements.txt.
  * Check with: python -c "import garminconnect; print(garminconnect.__file__)"
Without them the script says so on stderr and exits 1 (it used to die on an import traceback).

Mint, then CHECK THE FILE (PowerShell, from `backend/`):

    python -m scripts.garmin_login | Out-File -Encoding ascii token.json
    if ($LASTEXITCODE -ne 0) { throw 'mint failed' }
    $j = Get-Content .\token.json -Raw | ConvertFrom-Json
    if (-not $j.di_token -or -not $j.di_refresh_token) { throw 'token file is empty or not a token' }
    # then POST {"token": "<contents>"} to /integrations/garmin/token
    # (and delete the local file afterward — the refresh token IS account access)

Why the last two lines and not just "does it parse": the redirect creates the file BEFORE Python
runs, so a failed mint always leaves an empty one, and `ConvertFrom-Json` of an empty file returns
nothing WITHOUT an error. A parse check alone therefore passes on exactly the failure it is meant
to catch. Check the exit code and that the fields are present. A real token file is not small; an
empty or near-empty one is a failed mint whatever its name.

This script itself refuses to exit 0 without a usable blob: it validates the dump (non-empty JSON
object carrying `di_token` and `di_refresh_token`) and otherwise writes NOTHING to stdout and
exits 1.

The password lives only in this process's memory for the duration of the login and is
never written, logged, or emitted. Only the token blob leaves.
"""
import getpass
import json
import sys

try:
    from garminconnect import Garmin
except ImportError:  # the local prerequisites are missing (see the docstring)
    Garmin = None

_REQUIRED_BLOB_KEYS = ("di_token", "di_refresh_token")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def blob_problem(token_json: object) -> str | None:
    """Why this is NOT a usable token blob, or None when it is: a non-empty JSON object carrying
    the DI access and refresh tokens. Exit 0 with anything less would hand the operator a file
    that looks like a success and is not."""
    if not isinstance(token_json, str) or not token_json.strip():
        return "the token dump is empty"
    try:
        data = json.loads(token_json)
    except ValueError:
        return "the token dump is not valid JSON"
    if not isinstance(data, dict):
        return "the token dump is not a JSON object"
    missing = [k for k in _REQUIRED_BLOB_KEYS if not data.get(k)]
    return f"the token dump lacks {', '.join(missing)}" if missing else None


def _ask(prompt: str) -> str:
    """Prompt on STDERR and read one line from stdin.

    Plain `input(prompt)` writes its prompt to STDOUT whenever stdout is redirected, and the whole
    point of this script is `python -m scripts.garmin_login > token.json`: the prompts
    ("Garmin email: ", "MFA code: ") would land in the token file ahead of the JSON and corrupt it.
    (`getpass` talks to the console directly, so the password prompt was never affected.)"""
    print(prompt, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip()


def main() -> int:
    if Garmin is None:
        _err("The `garminconnect` package is not installed. This script runs on YOUR machine and needs "
             "Python >= 3.12 and: pip install garminconnect==0.3.11")
        return 1
    _err("Garmin Connect login (out-of-band). Nothing but the token blob is emitted to stdout.")
    email = _ask("Garmin email: ")
    password = getpass.getpass("Garmin password (not stored): ")

    garmin = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        mfa_status, client_state = garmin.login()
    except Exception as exc:  # noqa: BLE001 — surface any auth failure to the operator
        _err(f"Login failed: {exc}")
        return 1

    if mfa_status == "needs_mfa":
        mfa_code = _ask("MFA code: ")
        try:
            garmin.resume_login(client_state, mfa_code)
        except Exception as exc:  # noqa: BLE001
            _err(f"MFA verification failed: {exc}")
            return 1

    # Wipe the password reference as soon as it is no longer needed.
    del password
    garmin.password = None

    try:
        token_json = garmin.client.dumps()
    except Exception as exc:  # noqa: BLE001
        _err(f"Could not serialise the token blob: {exc}")
        return 1

    problem = blob_problem(token_json)
    if problem:
        _err(f"Login appeared to succeed but {problem}; nothing was written to stdout. Not a usable token.")
        return 1

    _err("Login OK. Token blob written to stdout — POST it to /integrations/garmin/token, then delete it.")
    sys.stdout.write(token_json)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
