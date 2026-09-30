"""Undo a Garmin account mix-up: disconnect the WRONG user's Garmin, purge its copies, and
(only on a separate operator ruling) reassign its rows that belong to the owner.

One Garmin account (the owner's) was connected to two users, so the wrong user holds rows pulled
from the owner's account. The dry run sorts every wrong-user garmin night into three classes:

  A  the owner has a reading for the SAME night with the IDENTICAL rmssd_ms: a provable copy.
     `--execute` purges these (with their hrv_samples) and disconnects the wrong user's garmin
     integration.
  B  the owner has NO reading for that night. Not a copy, so it is never purged. They are
     candidates to REASSIGN to the owner (readings and their samples together), which is a change
     to the owner's data and needs its own flag and token, run only after the operator's explicit
     ruling. If the operator rules they are the wrong user's own, they simply stay.
  C  the owner HAS a reading for that night but a DIFFERENT (or missing) rmssd_ms. Unexpected, and
     possibly the wrong user's own genuine data: HALT. Any C makes every execute refuse; there is
     no override flag, the script is changed to match the operator's ruling.

    # Dry run (the default; changes nothing)
    /opt/venv/bin/python -m scripts.garmin_purge_copies --wrong-user 4 --owner 1

    # Class A + disconnect (one transaction; token printed by the dry run)
    /opt/venv/bin/python -m scripts.garmin_purge_copies --wrong-user 4 --owner 1 --execute --confirm <tokenA>

    # Class B reassignment ONLY, after the operator's ruling (re-run the dry run first: the
    # tokens pin the exact rows, so they change after class A is executed)
    /opt/venv/bin/python -m scripts.garmin_purge_copies --wrong-user 4 --owner 1 --execute --reassign-b --confirm <tokenB>

Guards, all asserted in-transaction (a violation ROLLS BACK, exit 3):
  * class A mode: the owner's garmin readings, samples, rmssd sum and integrations are
    IDENTICAL; the wrong user's non-garmin HRV and non-garmin integrations are identical; the
    class B rows are still exactly there; nothing else remains but class B;
  * class B mode: the owner gains EXACTLY the class B readings and their samples (count, sample
    count, rmssd sum) and nothing else changes; the wrong user keeps only its class A rows.
  * only source 'garmin' exists here (no source argument, every statement names it, the API refuses
    another value); the wrong user can never be user 1 (`PROTECTED_WRONG_USERS`) nor the owner;
  * the confirm tokens are digests of the exact rows (ids, nights, values, classes): anything that
    changes between the dry run and `--execute` invalidates them.

The credential column is never selected (provider and timestamps only). Not fixed here, reported
by the dry run: `daily_records.passive_hrv_ms` is frozen at AM capture (append-only), so the wrong
user's daily records may carry copies of the owner's HRV; that needs its own ruling.

Output is pure ASCII and carries no secret (FEEDBACK section 30).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection, Engine

SOURCE = "garmin"
PROTECTED_WRONG_USERS: frozenset[int] = frozenset({1})


class Refused(Exception):
    exit_code = 2


class InvariantError(Refused):
    exit_code = 3


@dataclass
class NightRow:
    reading_id: int
    night: str
    value: float | None
    owner_value: float | None
    owner_has_night: bool
    n_samples: int

    @property
    def klass(self) -> str:
        if not self.owner_has_night:
            return "B"
        if self.value is not None and self.value == self.owner_value:
            return "A"
        return "C"

    @property
    def reason(self) -> str:
        return {"A": "A  copy -> purge",
                "B": "B  owner has no reading this night -> reassign candidate",
                "C": "C  values DIFFER -> HALT"}[self.klass]


@dataclass
class Plan:
    wrong: int
    owner: int
    rows: list[NightRow]
    integrations: list[dict[str, Any]]
    other_sources: dict[str, int]
    passive: dict[str, int] | None
    token_a: str = ""
    token_b: str = ""

    def of(self, klass: str) -> list[NightRow]:
        return [r for r in self.rows if r.klass == klass]


def _refuse_pair(wrong: int, owner: int, source: str) -> None:
    if source != SOURCE:
        raise Refused(f"only source {SOURCE!r} may be purged; refusing {source!r}")
    if int(wrong) == int(owner):
        raise Refused("--wrong-user and --owner must differ")
    if int(wrong) in PROTECTED_WRONG_USERS:
        raise Refused(f"user {int(wrong)} is protected and can never be the wrong user")


def _token(mode: str, wrong: int, owner: int, rows: list[NightRow]) -> str:
    payload = json.dumps([mode, wrong, owner,
                          [(r.reading_id, r.night, repr(r.value), r.klass, r.n_samples) for r in rows]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _exists(conn: Connection, uid: int) -> bool:
    return conn.execute(text("SELECT 1 FROM users WHERE id = :u"), {"u": uid}).first() is not None


def build_plan(conn: Connection, wrong: int, owner: int, source: str = SOURCE) -> Plan:
    wrong, owner = int(wrong), int(owner)
    _refuse_pair(wrong, owner, source)
    for uid in (wrong, owner):
        if not _exists(conn, uid):
            raise Refused(f"no user with id {uid} in this database")

    rows = [
        NightRow(int(r["id"]), str(r["captured_at"]), r["rmssd_ms"], r["owner_rmssd"],
                 r["owner_id"] is not None, int(r["n_samples"]))
        for r in conn.execute(text(
            "SELECT r.id, r.captured_at, r.rmssd_ms, o.id AS owner_id, o.rmssd_ms AS owner_rmssd,"
            " (SELECT COUNT(*) FROM hrv_samples s WHERE s.hrv_reading_id = r.id) AS n_samples"
            " FROM hrv_readings r LEFT JOIN hrv_readings o"
            "   ON o.user_id = :owner AND o.source = 'garmin' AND o.captured_at = r.captured_at"
            " WHERE r.user_id = :wrong AND r.source = 'garmin' ORDER BY r.captured_at"
        ), {"wrong": wrong, "owner": owner}).mappings()
    ]

    integrations = [
        dict(r) for r in conn.execute(text(  # provider + timestamps ONLY: never the credential column
            "SELECT provider, created_at, updated_at FROM user_integrations"
            " WHERE user_id = :w AND provider = 'garmin'"), {"w": wrong}).mappings()
    ]
    other = {
        str(r["source"]): int(r["n"]) for r in conn.execute(text(
            "SELECT source, COUNT(*) AS n FROM hrv_readings"
            " WHERE user_id = :w AND source <> 'garmin' GROUP BY source ORDER BY source"), {"w": wrong}).mappings()
    }

    passive = None
    try:
        p = conn.execute(text(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN o.id IS NOT NULL THEN 1 ELSE 0 END) AS same"
            " FROM daily_records d LEFT JOIN hrv_readings o"
            "   ON o.user_id = :owner AND o.source = 'garmin' AND o.captured_at = d.date"
            "  AND o.rmssd_ms = d.passive_hrv_ms"
            " WHERE d.user_id = :wrong AND d.passive_hrv_ms IS NOT NULL"),
            {"wrong": wrong, "owner": owner}).mappings().first()
        passive = {"n": int(p["n"] or 0), "same": int(p["same"] or 0)}
    except Exception:  # noqa: BLE001 -- informational only; a missing table must not block the plan
        passive = None

    plan = Plan(wrong, owner, rows, integrations, other, passive)
    plan.token_a = _token("purge-A", wrong, owner, rows)
    plan.token_b = _token("reassign-B", wrong, owner, rows)
    return plan


def format_plan(plan: Plan, target: str) -> str:
    out = [f"Target database: {target}",
           f"Wrong user {plan.wrong}, rightful owner {plan.owner}, source '{SOURCE}' only.", ""]
    out.append(f"Garmin integration of user {plan.wrong} (deleted first on execute; credential not read):")
    if plan.integrations:
        for i in plan.integrations:
            out.append(f"  garmin  created={i['created_at']}  updated={i['updated_at']}")
    else:
        out.append("  (none: already disconnected)")
    out.append("")
    out.append(f"user {plan.wrong} garmin hrv_readings ({len(plan.rows)}), compared with user {plan.owner}"
               " on the same night:")
    out.append(f"  {'night':<12}{'wrong':>10}{'owner':>10}{'samples':>9}  verdict")
    for r in plan.rows:
        out.append(f"  {r.night:<12}{str(r.value):>10}{str(r.owner_value) if r.owner_has_night else '-':>10}"
                   f"{r.n_samples:>9}  {r.reason}")
    a, b, c = plan.of("A"), plan.of("B"), plan.of("C")
    out.append(f"  A (copies, purge) {len(a)} [{sum(r.n_samples for r in a)} samples]   "
               f"B (owner has no row) {len(b)} [{sum(r.n_samples for r in b)} samples]   C (values differ) {len(c)}")
    out.append("")
    out.append(f"user {plan.wrong} non-garmin hrv_readings (NOT touched): "
               + (", ".join(f"{s}={n}" for s, n in plan.other_sources.items()) or "(none)"))
    if plan.passive is not None:
        out.append(f"user {plan.wrong} daily_records with passive_hrv_ms set: {plan.passive['n']}, of which"
                   f" {plan.passive['same']} equal user {plan.owner}'s reading for the same date."
                   " Frozen at AM capture, NOT changed by this script; they may hold copies (needs its own ruling).")
    out.append("")
    if c:
        out.append(f"HALT: {len(c)} class C row(s): user {plan.owner} has a reading for the night but a"
                   f" different value, so they may be user {plan.wrong}'s own genuine data."
                   " EVERY execute will refuse until the operator rules.")
    else:
        out.append("No class C rows.")
    if b:
        out.append(f"Class B ({len(b)} rows) is NEVER touched by --execute. Reassigning it to user {plan.owner}"
                   " changes that user's data and needs the operator's explicit ruling; if they are"
                   f" user {plan.wrong}'s own, they stay.")
    out.append("")
    out.append("DRY RUN - nothing was changed.")
    if c:
        out.append("No execute command is offered while class C exists.")
    else:
        out.append(f"To execute class A + disconnect: --wrong-user {plan.wrong} --owner {plan.owner}"
                   f" --execute --confirm {plan.token_a}")
        if b:
            out.append(f"To reassign class B (ONLY after the ruling; re-run this dry run first if class A"
                       f" was executed since): --wrong-user {plan.wrong} --owner {plan.owner}"
                       f" --execute --reassign-b --confirm {plan.token_b}")
    return "\n".join(out)


def _snapshot(conn: Connection, wrong: int, owner: int) -> dict[str, Any]:
    def one(sql: str, **p: Any) -> Any:
        return conn.execute(text(sql), p).scalar_one()
    return {
        "owner_readings": one("SELECT COUNT(*) FROM hrv_readings WHERE user_id = :o AND source = 'garmin'", o=owner),
        "owner_rmssd_sum": float(one("SELECT COALESCE(SUM(rmssd_ms), 0) FROM hrv_readings"
                                     " WHERE user_id = :o AND source = 'garmin'", o=owner)),
        "owner_samples": one("SELECT COUNT(*) FROM hrv_samples s JOIN hrv_readings r ON r.id = s.hrv_reading_id"
                             " WHERE r.user_id = :o AND r.source = 'garmin'", o=owner),
        "owner_integrations": one("SELECT COUNT(*) FROM user_integrations WHERE user_id = :o", o=owner),
        "owner_non_garmin": one("SELECT COUNT(*) FROM hrv_readings WHERE user_id = :o AND source <> 'garmin'", o=owner),
        "wrong_non_garmin": one("SELECT COUNT(*) FROM hrv_readings WHERE user_id = :w AND source <> 'garmin'", w=wrong),
        "wrong_other_integrations": one("SELECT COUNT(*) FROM user_integrations"
                                        " WHERE user_id = :w AND provider <> 'garmin'", w=wrong),
        "wrong_garmin_integrations": one("SELECT COUNT(*) FROM user_integrations"
                                         " WHERE user_id = :w AND provider = 'garmin'", w=wrong),
        "wrong_garmin_readings": one("SELECT COUNT(*) FROM hrv_readings WHERE user_id = :w AND source = 'garmin'", w=wrong),
        "wrong_garmin_samples": one("SELECT COUNT(*) FROM hrv_samples s JOIN hrv_readings r ON r.id = s.hrv_reading_id"
                                    " WHERE r.user_id = :w AND r.source = 'garmin'", w=wrong),
        "wrong_garmin_rmssd_sum": float(one("SELECT COALESCE(SUM(rmssd_ms), 0) FROM hrv_readings"
                                            " WHERE user_id = :w AND source = 'garmin'", w=wrong)),
    }


@dataclass
class ExecResult:
    mode: str
    integrations_deleted: int
    readings_deleted: int
    samples_deleted: int
    readings_reassigned: int
    before: dict[str, Any]
    after: dict[str, Any]


def _expect(before: dict[str, Any], after: dict[str, Any], changes: dict[str, float]) -> None:
    """`after` must equal `before` except for EXACTLY the named deltas."""
    bad = {}
    for k in before:
        want = before[k] + changes.get(k, 0)
        if abs(after[k] - want) > 1e-9:
            bad[k] = (want, after[k])
    if bad:
        raise InvariantError(f"unexpected change (expected, actual): {bad}")


def execute_purge(engine: Engine, wrong: int, owner: int, confirm: str | None,
                  source: str = SOURCE, *, reassign_b: bool = False) -> ExecResult:
    wrong, owner = int(wrong), int(owner)
    _refuse_pair(wrong, owner, source)
    with engine.begin() as conn:  # one transaction: any raise rolls everything back
        plan = build_plan(conn, wrong, owner, source)
        want = plan.token_b if reassign_b else plan.token_a
        if not confirm or confirm != want:
            raise Refused("--confirm token missing or does not match the current rows (re-run the dry run)")
        a, b, c = plan.of("A"), plan.of("B"), plan.of("C")
        if c:
            raise Refused(f"HALT: {len(c)} class C row(s) (values differ from the owner's); nothing was changed")
        before = _snapshot(conn, wrong, owner)

        if reassign_b:
            if not b:
                raise Refused("no class B rows to reassign")
            ids = [r.reading_id for r in b]
            n = conn.execute(
                text("UPDATE hrv_readings SET user_id = :o WHERE id IN :ids AND user_id = :w AND source = 'garmin'")
                .bindparams(bindparam("ids", expanding=True)), {"o": owner, "w": wrong, "ids": ids}).rowcount
            if n != len(b):
                raise InvariantError(f"reassigned {n} readings, expected {len(b)}")
            n_samp = sum(r.n_samples for r in b)
            rm = sum(float(r.value) for r in b if r.value is not None)
            after = _snapshot(conn, wrong, owner)
            _expect(before, after, {
                "owner_readings": len(b), "owner_samples": n_samp, "owner_rmssd_sum": rm,
                "wrong_garmin_readings": -len(b), "wrong_garmin_samples": -n_samp, "wrong_garmin_rmssd_sum": -rm})
            return ExecResult("reassign-B", 0, 0, 0, n, before, after)

        ids = [r.reading_id for r in a]
        n_int = conn.execute(text("DELETE FROM user_integrations WHERE user_id = :w AND provider = 'garmin'"),
                             {"w": wrong}).rowcount
        n_samples = n_readings = 0
        if ids:
            n_samples = conn.execute(
                text("DELETE FROM hrv_samples WHERE hrv_reading_id IN :ids").bindparams(
                    bindparam("ids", expanding=True)), {"ids": ids}).rowcount
            n_readings = conn.execute(
                text("DELETE FROM hrv_readings WHERE id IN :ids AND user_id = :w AND source = 'garmin'")
                .bindparams(bindparam("ids", expanding=True)), {"ids": ids, "w": wrong}).rowcount
        if n_readings != len(ids):
            raise InvariantError(f"deleted {n_readings} readings, expected {len(ids)}")
        a_rm = sum(float(r.value) for r in a if r.value is not None)
        after = _snapshot(conn, wrong, owner)
        _expect(before, after, {
            "wrong_garmin_integrations": -n_int, "wrong_garmin_readings": -len(a),
            "wrong_garmin_samples": -sum(r.n_samples for r in a), "wrong_garmin_rmssd_sum": -a_rm})
        if after["wrong_garmin_readings"] != len(b):
            raise InvariantError(f"{after['wrong_garmin_readings']} garmin readings remain, expected the {len(b)} class B")
    return ExecResult("purge-A", n_int, n_readings, n_samples, 0, before, after)


def _target(engine: Engine) -> str:
    u = engine.url
    return (f"sqlite file={u.database}" if engine.dialect.name == "sqlite"
            else f"{engine.dialect.name} host={u.host} port={u.port} db={u.database}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Disconnect the wrong user's Garmin and purge its copied HRV.")
    p.add_argument("--wrong-user", type=int, required=True)
    p.add_argument("--owner", type=int, required=True)
    p.add_argument("--execute", action="store_true", help="Delete (default is a read-only dry run).")
    p.add_argument("--confirm", help="Token printed by the dry run.")
    p.add_argument("--reassign-b", action="store_true",
                   help="With --execute: reassign class B rows to the owner INSTEAD of purging class A."
                        " Only after the operator's explicit ruling.")
    args = p.parse_args(argv)
    try:
        _refuse_pair(args.wrong_user, args.owner, SOURCE)
        if (args.confirm or args.reassign_b) and not args.execute:
            p.error("--confirm and --reassign-b are only meaningful with --execute")
        import database

        engine = database.engine
        if not args.execute:
            with engine.connect() as conn:  # SELECT only; rolls back on close
                plan = build_plan(conn, args.wrong_user, args.owner)
            print(format_plan(plan, _target(engine)).encode("ascii", "backslashreplace").decode("ascii"))
            return 0
        print(f"Target database: {_target(engine)}")
        res = execute_purge(engine, args.wrong_user, args.owner, args.confirm, reassign_b=args.reassign_b)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return exc.exit_code
    if res.mode == "reassign-B":
        print(f"EXECUTED (committed): {res.readings_reassigned} class B readings (with their samples) reassigned"
              f" from user {args.wrong_user} to user {args.owner}; nothing else changed (asserted in-transaction).")
    else:
        print(f"EXECUTED (committed): garmin integration of user {args.wrong_user} deleted ({res.integrations_deleted}),"
              f" {res.readings_deleted} class A readings and {res.samples_deleted} samples purged;"
              f" user {args.owner}'s garmin rows identical before and after (asserted in-transaction).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
