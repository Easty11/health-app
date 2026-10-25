"""Attach a Garmin Personal API key to a user -- the operator's route (S1). Run in the prod container:

    railway ssh --service health-app-backend
    cd /app
    /opt/venv/bin/python -m scripts.garmin_personal_attach --user-id 1 --expires 2027-10-24

The key is read from a HIDDEN prompt (getpass), never from argv, an environment variable or a file, so it
cannot reach shell history or a process listing. `--expires` is the expiry date Garmin showed when the key
was created (the key's owner sets it, up to one year; Garmin emails the owner, not the operator, before it
lapses, so the date is recorded here and warned on from the freshness card).

Same guard as the HTTP route (`garmin_personal_lanes.attach_key`): the key is exchanged once, the account it
belongs to is resolved from `userProfilePk`, and the attach is refused when that account is connected to a
different user, differs from this user's own DI connection, or cannot be resolved. Output is ASCII and carries
no key, token or account identifier. Re-running with a new key (the yearly replacement) is the same command.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import date, datetime, timezone

import garmin_personal_lanes as gpl
from database import SessionLocal


def main(argv: list[str] | None = None, *, read_key=getpass.getpass, db_factory=SessionLocal, today: date | None = None) -> int:
    p = argparse.ArgumentParser(description="Attach a Garmin Personal API key (hidden prompt).")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--expires", required=True, help="Key expiry date shown by Garmin (YYYY-MM-DD).")
    args = p.parse_args(argv)
    try:
        expires = date.fromisoformat(args.expires)
    except ValueError:
        print("--expires must be an ISO date (YYYY-MM-DD)", file=sys.stderr)
        return 2

    key = read_key("Garmin Personal API key (input hidden): ")
    db = db_factory()
    try:
        out = gpl.attach_key(db, args.user_id, key, expires, today=today or datetime.now(timezone.utc).date())
    except gpl.AttachError as exc:
        print(f"REFUSED ({exc.code}): {exc}", file=sys.stderr)
        return 1
    finally:
        del key
        db.close()
    print(f"Attached for user {args.user_id}: key expires {out['key_expires_on']} ({out['days_to_expiry']} days).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
