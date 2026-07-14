"""Operator CLI — run the Hevy exercise-template sync in prod (DECISIONS_LOG #77).

The template subsystem (resolver #60/#61, create_and_resolve #65, catalogue
tagging #74/#75/#76) sits on `hevy_exercise_templates`. That table is populated
ONLY by `sync_exercise_templates`, which has no request-layer wiring and no job
— it must be run explicitly by an operator. This is that entry point.

Activation is OPERATOR-layer only (DECISIONS_LOG #77): an explicit, observable,
NON-ZERO-EXITING operation, never an implicit side-effect of a request. No HTTP
endpoint is added here.

    python backend/sync_hevy_templates.py            # sync every keyed user
    python backend/sync_hevy_templates.py --user-id 1  # sync one user (safety valve)

Exits NON-ZERO if nothing synced (users_synced == 0) or any user failed
(users_failed > 0), so a partial or empty run is a loud CI/operator failure, not
a green no-op.
"""
import argparse
import asyncio
import json
import logging

import hevy_templates

logger = logging.getLogger(__name__)


def _exit_code(summary: dict) -> int:
    """Non-zero on an empty or partial sync — the failure signal the whole brief
    exists to make loud."""
    if summary.get("users_synced", 0) == 0:
        return 1
    if summary.get("users_failed", 0) > 0:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Hevy exercise-template sync.")
    parser.add_argument(
        "--user-id", type=int, default=None,
        help="Sync only this user (operator safety valve — no exposure to a stale family key).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from database import SessionLocal

    db = SessionLocal()
    try:
        summary = asyncio.run(
            hevy_templates.sync_exercise_templates(db, only_user_id=args.user_id)
        )
    finally:
        db.close()

    print(json.dumps(summary, indent=2, default=str))
    code = _exit_code(summary)
    if code != 0:
        logger.error(
            "Hevy template sync did NOT fully succeed (users_synced=%s, users_failed=%s) "
            "— exiting %d.",
            summary.get("users_synced"), summary.get("users_failed"), code,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
