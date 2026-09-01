"""
Out-of-band interactive Garmin login → token blob (GUARD: the platform never stores
or receives the Garmin password).

The operator runs this LOCALLY. It prompts for email, password (never echoed), and
the MFA code, performs the Garth OAuth login, and prints ONLY the resulting token
JSON to stdout. Everything else — prompts, status, errors — goes to stderr, so the
stdout capture is exactly the blob to POST to /integrations/garmin/token.

    python -m scripts.garmin_login > garmin_token.json
    # then POST the file contents as {"token": "<contents>"} to /integrations/garmin/token
    # (and delete the local file afterward — the refresh token IS account access)

The password lives only in this process's memory for the duration of the login and is
never written, logged, or emitted. Only the token blob leaves.
"""
import getpass
import sys

from garminconnect import Garmin


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    _err("Garmin Connect login (out-of-band). Nothing but the token blob is emitted to stdout.")
    email = input("Garmin email: ").strip() if sys.stdin.isatty() else sys.stdin.readline().strip()
    password = getpass.getpass("Garmin password (not stored): ")

    garmin = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        mfa_status, client_state = garmin.login()
    except Exception as exc:  # noqa: BLE001 — surface any auth failure to the operator
        _err(f"Login failed: {exc}")
        return 1

    if mfa_status == "needs_mfa":
        mfa_code = input("MFA code: ").strip()
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

    _err("Login OK. Token blob written to stdout — POST it to /integrations/garmin/token, then delete it.")
    sys.stdout.write(token_json)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
