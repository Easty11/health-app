"""Move every `user_integrations.api_key_encrypted` row from the previous Fernet key to the current one.

`encryption` encrypts under FERNET_KEY and decrypts under FERNET_KEY or, when set, FERNET_KEY_PREVIOUS,
so a key swap breaks no read. This script is the second half: it re-encrypts the rows still under the
previous key, so the previous key can then be deleted. Procedure: docs/rotation-runbook-2026-10.md.

    # Dry run (the default; changes nothing). Exits non-zero if any row is unreadable.
    /opt/venv/bin/python -m scripts.rotate_fernet --dry-run

    # Rotate (one transaction). Read the dry run first; this is a separate command.
    /opt/venv/bin/python -m scripts.rotate_fernet --confirm

Per row the state is `current` (decrypts under FERNET_KEY alone), `previous` (only under the fallback)
or `unreadable` (neither). `--confirm` refuses with fewer than two active keys or with any unreadable
row, and writes nothing in either case. After writing it re-reads every written row and requires it to
decrypt under the current key alone to the same plaintext, else the whole transaction rolls back (exit 3).
Idempotent: a second `--confirm` finds no `previous` row and changes nothing.

Output is pure ASCII: ids, provider and state only. No plaintext and no ciphertext is ever printed,
logged or returned (DECISIONS_LOG #111).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import TextIO

from cryptography.fernet import InvalidToken
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

import encryption

CURRENT, PREVIOUS, UNREADABLE, ROTATED = "current", "previous", "unreadable", "rotated"

EXIT_UNREADABLE = 1
EXIT_REFUSED = 2
EXIT_REREAD_FAILED = 3


class RereadFailed(Exception):
    pass


@dataclass(frozen=True)
class Row:
    id: int
    user_id: int
    provider: str
    state: str


def _state(token: str) -> str:
    if encryption.decrypts_under_current(token):
        return CURRENT
    try:
        encryption.decrypt(token)
    except (InvalidToken, ValueError, TypeError):
        return UNREADABLE
    return PREVIOUS


def classify(conn: Connection) -> tuple[list[Row], dict[int, str]]:
    """Every row's state, plus the ciphertexts keyed by id (in memory only; never printed)."""
    tokens: dict[int, str] = {}
    rows: list[Row] = []
    for r in conn.execute(text(
            "SELECT id, user_id, provider, api_key_encrypted FROM user_integrations ORDER BY id")).mappings():
        tokens[int(r["id"])] = r["api_key_encrypted"]
        rows.append(Row(int(r["id"]), int(r["user_id"]), str(r["provider"]), _state(r["api_key_encrypted"])))
    return rows, tokens


def _line(row: Row, state: str | None = None) -> str:
    return f"id={row.id} user_id={row.user_id} provider={row.provider} state={state or row.state}"


def _counts(rows: list[Row], out: TextIO) -> None:
    n = {s: sum(1 for r in rows if r.state == s) for s in (CURRENT, PREVIOUS, UNREADABLE)}
    print(f"rows={len(rows)} current={n[CURRENT]} previous={n[PREVIOUS]} unreadable={n[UNREADABLE]}"
          f" active_keys={encryption.active_key_count()}", file=out)


def dry_run(engine: Engine, out: TextIO) -> int:
    with engine.connect() as conn:  # SELECT only; rolls back on close
        rows, _ = classify(conn)
    for r in rows:
        print(_line(r), file=out)
    _counts(rows, out)
    return EXIT_UNREADABLE if any(r.state == UNREADABLE for r in rows) else 0


def _rotate_all(conn: Connection, rows: list[Row], tokens: dict[int, str], out: TextIO) -> None:
    for r in rows:
        if r.state != PREVIOUS:
            continue
        new = encryption.rotate(tokens[r.id])
        # Match on the old ciphertext as well, so a row rewritten since the read is never overwritten.
        done = conn.execute(
            text("UPDATE user_integrations SET api_key_encrypted = :new"
                 " WHERE id = :id AND api_key_encrypted = :old"),
            {"new": new, "old": tokens[r.id], "id": r.id}).rowcount
        if done != 1:
            raise RereadFailed(f"id={r.id} changed since it was read; nothing written")
    for r in rows:
        if r.state != PREVIOUS:
            continue
        now = conn.execute(text("SELECT api_key_encrypted FROM user_integrations WHERE id = :id"),
                           {"id": r.id}).scalar_one()
        if not encryption.decrypts_under_current(now) or encryption.decrypt(now) != encryption.decrypt(tokens[r.id]):
            raise RereadFailed(f"id={r.id} does not read back under the current key; rolled back")
        print(_line(r, ROTATED), file=out)


def confirm_run(engine: Engine, out: TextIO, err: TextIO) -> int:
    if encryption.active_key_count() < 2:
        print("REFUSED: no previous key set; nothing to rotate from", file=err)
        return EXIT_REFUSED
    try:
        with engine.begin() as conn:  # one transaction: any raise rolls everything back
            rows, tokens = classify(conn)
            bad = [r for r in rows if r.state == UNREADABLE]
            if bad:
                for r in bad:
                    print(_line(r), file=err)
                print(f"REFUSED: {len(bad)} row(s) decrypt under neither key; nothing written", file=err)
                return EXIT_UNREADABLE
            _rotate_all(conn, rows, tokens, out)
    except RereadFailed as exc:
        print(f"FAILED: {exc}", file=err)
        return EXIT_REREAD_FAILED
    rotated = sum(1 for r in rows if r.state == PREVIOUS)
    print(f"rotated={rotated} already_current={len(rows) - rotated} rows={len(rows)}", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Re-encrypt user_integrations rows under the current Fernet key.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Classify every row; write nothing (default).")
    mode.add_argument("--confirm", action="store_true", help="Rotate the rows still under the previous key.")
    args = p.parse_args(argv)
    import database

    if args.confirm:
        return confirm_run(database.engine, sys.stdout, sys.stderr)
    return dry_run(database.engine, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
