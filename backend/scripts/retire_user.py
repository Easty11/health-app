"""Retire a user account -- inventory, dry run (the default), and --execute.

Built for retiring test/demo accounts (candidates: users 6, 7, 8). Generic over the user
id, with the real accounts (users 1, 4, 5: PROTECTED_USER_IDS) hard-refused at every layer.

    # Dry run / inventory (the default; changes nothing). Run once per candidate user.
    /opt/venv/bin/python -m scripts.retire_user --user-id 7

    # Execute (one transaction; needs the confirm token the dry run printed).
    /opt/venv/bin/python -m scripts.retire_user --user-id 7 --execute --confirm <token>

In the container: `railway ssh --service health-app-backend`, `cd /app`, then the venv
interpreter above (CLAUDE.md "Prod psql route"). The target database is `DATABASE_URL`,
printed (host and database name only) at the top of every run so the operator can confirm
which instance answered.

How it decides what a delete removes. The FK graph is read from the LIVE database
(`sqlalchemy.inspect`), not from `models.py`: the deployed constraints are what a delete
obeys. From `users` it follows every ON DELETE CASCADE edge transitively (`hevy_sets` via
`hevy_workouts`, `hrv_samples` via `hrv_readings`, ...). It also reports the references that
do NOT cascade: SET NULL rows that survive, NO ACTION / RESTRICT references that would block
the delete, and any `*user_id` column with no FK to users (rows a delete would orphan). Any
blocker or orphan makes `--execute` refuse.

The execute path, in ONE transaction:
  1. refuse any id in PROTECTED_USER_IDS, an unknown user, a wrong confirm token;
  2. refuse on blockers / orphan-risk references / non-re-derivable rows (see below);
  3. snapshot the protected users' per-table row counts;
  4. delete the target's stored integration tokens (`user_integrations`), then the user row
     (the rest cascades);
  5. re-snapshot: the protected users' counts must be IDENTICAL, the target must have no rows
     left in any scoped table, else ROLL BACK and exit non-zero.

Non-re-derivable rows (the shared-key hazard). `hevy_workouts.hevy_id` and
`hevy_exercise_templates.id` are keyed on the Hevy id ALONE, and the sync re-assigns
`user_id` / `owner_user_id` to whichever user synced last. With one Hevy account behind two
keyed users, rows that belong to the operator's real history can be owned by the account
being retired, and the cascade would destroy them together with what Hevy cannot re-supply:
the operator's `excluded_at` adjudications, template `laterality` / `adjudicated_at` /
`bw_fraction`, and `exercise_region_tags`. The dry run counts them; `--execute` refuses while
any exist unless `--accept-loss` is passed (an explicit decision, never a default).

Sign-in artefacts. Web/API auth is a stateless JWT keyed on email: deleting the user row ends
it. The MCP `PersonalOAuthProvider` persists its tokens in `mcp_oauth_tokens` (hashed, with expiry
and revocation; Q196): the dry run counts the account's LIVE tokens (not revoked, not expired)
and when one was last used, and a delete cascades them away, so a deleted user's MCP session ends
at once. MCP sign-in verifies email + password against `users`, so the delete also ends that
sign-in path. No last-login is recorded anywhere. The dry run prints all of this, plus the
account's knowledge entries, so the operator can decide.

Never prints a secret: the credential column is never selected (integrations are listed by
provider and timestamps only), the email is masked, and the confirm token is a 12-char
SHA-256 digest. Output is pure ASCII (PowerShell mojibake, FEEDBACK section 30).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field
from typing import Any

from datetime import datetime, timezone

from sqlalchemy import DateTime, bindparam, inspect, text
from sqlalchemy.engine import Connection, Engine

# User ids this script must never touch, at any layer: the real accounts (operator ruling,
# 30 Sep 2026: users 1, 4 and 5 are real and never in scope).
PROTECTED_USER_IDS: frozenset[int] = frozenset({1, 4, 5})

# Columns tried, in order, for a table's "latest activity" line.
_ACTIVITY_COLUMNS = ("updated_at", "synced_at", "computed_at", "created_at", "added_at")

# Rows a Hevy re-sync cannot recreate, owned via the globally keyed Hevy tables.
# (label, table, WHERE over that table with :uid). `exercise_region_tags` has no owner column:
# it is counted through the graph scope instead (see `_non_rederivable`).
_NON_REDERIVABLE_HEVY = (
    (
        "hevy_workouts with excluded_at set (operator adjudication)",
        "hevy_workouts",
        "user_id = :uid AND excluded_at IS NOT NULL",
    ),
    (
        "hevy_exercise_templates annotated (laterality / adjudicated_at / bw_fraction)",
        "hevy_exercise_templates",
        "owner_user_id = :uid AND (laterality IS NOT NULL OR adjudicated_at IS NOT NULL"
        " OR bw_fraction IS NOT NULL)",
    ),
)
_REGION_TAGS_TABLE = "exercise_region_tags"


class RetireError(Exception):
    """Base for refusals. `exit_code` is what `main` returns."""
    exit_code = 2


class ProtectedUserError(RetireError):
    pass


class NoSuchUser(RetireError):
    pass


class ConfirmMismatch(RetireError):
    pass


class Blocked(RetireError):
    pass


class InvariantError(RetireError):
    exit_code = 3


class GraphError(RetireError):
    pass


def _refuse_protected(user_id: int) -> None:
    """The hard guard. An explicit raise, not `assert` (asserts vanish under `python -O`)."""
    if int(user_id) in PROTECTED_USER_IDS:
        raise ProtectedUserError(
            f"user_id {int(user_id)} is protected and can never be retired by this script"
        )


# -- FK graph ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Edge:
    child: str
    child_col: str
    parent: str
    parent_col: str
    rule: str  # CASCADE | SET NULL | SET DEFAULT | RESTRICT | NO ACTION


@dataclass
class Graph:
    tables: list[str]
    edges: list[Edge]
    columns: dict[str, set[str]]
    # table -> WHERE predicate (over that table's own columns, bind :uid) selecting the rows a
    # delete of users.id = :uid removes via CASCADE. `users` itself is the root.
    scope: dict[str, str] = field(default_factory=dict)
    # (table, column): named like a user reference but with no FK to users -- a delete orphans it.
    unenforced: list[tuple[str, str]] = field(default_factory=list)


def _quoter(engine: Engine):
    return engine.dialect.identifier_preparer.quote


def discover_graph(engine: Engine) -> Graph:
    insp = inspect(engine)
    tables = sorted(insp.get_table_names())
    if "users" not in tables:
        raise GraphError("no `users` table in the connected database -- wrong DATABASE_URL?")
    q = _quoter(engine)

    edges: list[Edge] = []
    columns: dict[str, set[str]] = {}
    for t in tables:
        columns[t] = {c["name"] for c in insp.get_columns(t)}
        for fk in insp.get_foreign_keys(t):
            cols, rcols = fk["constrained_columns"], fk["referred_columns"]
            if len(cols) != 1 or len(rcols) != 1:
                raise GraphError(
                    f"composite foreign key on {t} ({fk.get('name')}) -- unsupported, refusing"
                )
            rule = ((fk.get("options") or {}).get("ondelete") or "NO ACTION").upper()
            edges.append(Edge(t, cols[0], fk["referred_table"], rcols[0], rule))

    cascade_into: dict[str, list[Edge]] = {}
    for e in edges:
        if e.rule == "CASCADE" and e.parent != e.child:
            cascade_into.setdefault(e.child, []).append(e)

    memo: dict[str, str | None] = {"users": f"{q('id')} = :uid"}

    def predicate(table: str, seen: frozenset[str]) -> str | None:
        if table in memo:
            return memo[table]
        parts = []
        for e in cascade_into.get(table, []):
            if e.parent in seen:
                continue  # a cascade cycle adds no new rows
            pp = predicate(e.parent, seen | {table})
            if pp is None:
                continue
            parts.append(
                f"({q(e.child_col)} IN (SELECT {q(e.parent_col)} FROM {q(e.parent)} WHERE {pp}))"
            )
        result = " OR ".join(parts) or None
        if not seen:  # only cache top-level answers; a path-dependent partial is not the table's
            memo[table] = result
        return result

    scope: dict[str, str] = {}
    for t in tables:
        p = predicate(t, frozenset())
        if p is not None:
            scope[t] = p

    users_fk_cols = {(e.child, e.child_col) for e in edges if e.parent == "users"}
    unenforced = sorted(
        (t, c)
        for t, cols in columns.items()
        for c in cols
        if (c == "user_id" or c.endswith("_user_id"))
        and t != "users"
        and (t, c) not in users_fk_cols
    )
    return Graph(tables=tables, edges=edges, columns=columns, scope=scope, unenforced=unenforced)


# -- counting ------------------------------------------------------------------------------

def _count(conn: Connection, table: str, where: str, uid: int, q) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {q(table)} WHERE {where}"), {"uid": uid}).scalar_one())


def snapshot(conn: Connection, engine: Engine, graph: Graph, uid: int) -> dict[str, int]:
    """Per-table row counts of everything a delete of `uid` would cascade over."""
    q = _quoter(engine)
    return {t: _count(conn, t, graph.scope[t], uid, q) for t in sorted(graph.scope)}


def _via(graph: Graph, table: str) -> str:
    if table == "users":
        return "the user row"
    hops = [
        f"{e.child_col} -> {e.parent}.{e.parent_col}"
        for e in graph.edges
        if e.child == table and e.rule == "CASCADE" and e.parent in graph.scope and e.parent != table
    ]
    return " | ".join(hops) or "?"


def _latest(conn: Connection, engine: Engine, graph: Graph, table: str, uid: int) -> str:
    q = _quoter(engine)
    for col in _ACTIVITY_COLUMNS:
        if col in graph.columns[table]:
            val = conn.execute(
                text(f"SELECT MAX({q(col)}) FROM {q(table)} WHERE {graph.scope[table]}"), {"uid": uid}
            ).scalar_one()
            return f"{col}={val}" if val is not None else "-"
    return "-"


# -- plan ----------------------------------------------------------------------------------

@dataclass
class Plan:
    user_id: int
    user: dict[str, Any]
    token: str
    integrations: list[dict[str, Any]]
    rows: list[dict[str, Any]]            # per scoped table
    nulled: list[tuple[str, str, int]]    # (table, column, rows that survive with the ref nulled)
    blockers: list[str]
    orphans: list[tuple[str, str, int]]   # (table, column, rows a delete would orphan)
    hevy: list[dict[str, Any]]            # per-owner Hevy ownership, all owners
    at_risk: list[tuple[str, int]]        # non-re-derivable rows a cascade would destroy
    knowledge: list[dict[str, Any]] = field(default_factory=list)  # user_knowledge_entries breakdown
    legacy_knowledge: int = 0             # user_knowledge rows (legacy category store)
    reset_tokens: dict[str, Any] | None = None  # password_reset_tokens: a persisted auth table
    mcp_tokens: dict[str, Any] | None = None    # mcp_oauth_tokens: live MCP tokens (None = no such table)

    @property
    def total_rows(self) -> int:
        return sum(r["n"] for r in self.rows)

    @property
    def refusal_reasons(self) -> list[str]:
        out = list(self.blockers)
        out += [f"orphan risk: {t}.{c} has {n} row(s) with no FK to users" for t, c, n in self.orphans if n]
        return out


def _confirm_token(user_id: int, email: str) -> str:
    return hashlib.sha256(f"{user_id}:{email.lower()}".encode("utf-8")).hexdigest()[:12]


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else f"{email[:1]}***"


def build_plan(conn: Connection, engine: Engine, graph: Graph, uid: int) -> Plan:
    uid = int(uid)
    _refuse_protected(uid)
    q = _quoter(engine)
    u = conn.execute(
        text("SELECT id, email, full_name, created_at FROM users WHERE id = :uid"), {"uid": uid}
    ).mappings().first()
    if u is None:
        raise NoSuchUser(f"no user with id {uid} in this database")

    integrations: list[dict[str, Any]] = []
    if "user_integrations" in graph.tables:
        # provider + timestamps ONLY. The credential column is never selected.
        for r in conn.execute(
            text("SELECT provider, created_at, updated_at FROM user_integrations"
                 " WHERE user_id = :uid ORDER BY provider"), {"uid": uid}
        ).mappings():
            integrations.append({"provider": r["provider"], "created_at": r["created_at"], "updated_at": r["updated_at"]})

    counts = snapshot(conn, engine, graph, uid)
    rows = [
        {
            "table": t,
            "n": counts[t],
            "via": _via(graph, t),
            "latest": _latest(conn, engine, graph, t, uid) if counts[t] else "-",
        }
        for t in sorted(counts)
    ]

    nulled: list[tuple[str, str, int]] = []
    blockers: list[str] = []
    for e in graph.edges:
        if e.parent not in graph.scope or e.rule == "CASCADE":
            continue
        refs = (f"{q(e.child_col)} IN (SELECT {q(e.parent_col)} FROM {q(e.parent)}"
                f" WHERE {graph.scope[e.parent]})")
        in_scope = graph.scope.get(e.child)
        # CASE, not NOT(): a nullable column in the child's scope predicate yields NULL, and
        # NOT(NULL) would silently drop the row from the count.
        outside = f" AND CASE WHEN ({in_scope}) THEN 0 ELSE 1 END = 1" if in_scope else ""
        if e.rule in ("SET NULL", "SET DEFAULT"):
            n = _count(conn, e.child, refs + outside, uid, q)
            if n:
                nulled.append((e.child, e.child_col, n))
        elif e.rule == "RESTRICT":
            # RESTRICT is checked per row, even for rows the same cascade deletes: any reference blocks.
            n = _count(conn, e.child, refs, uid, q)
            if n:
                blockers.append(f"RESTRICT: {n} row(s) in {e.child}.{e.child_col} reference {e.parent}")
        else:  # NO ACTION: checked at statement end, so only references from OUTSIDE the scope block
            n = _count(conn, e.child, refs + outside, uid, q)
            if n:
                blockers.append(
                    f"NO ACTION: {n} row(s) in {e.child}.{e.child_col} outside the deletion scope"
                    f" reference {e.parent}"
                )

    orphans = [
        (t, c, _count(conn, t, f"{q(c)} = :uid", uid, q)) for t, c in graph.unenforced
    ]

    hevy: list[dict[str, Any]] = []
    if "hevy_workouts" in graph.tables:
        for r in conn.execute(text(
            "SELECT user_id, COUNT(*) AS n,"
            " SUM(CASE WHEN excluded_at IS NOT NULL THEN 1 ELSE 0 END) AS excluded,"
            " MIN(start_time) AS first_start, MAX(start_time) AS last_start, MAX(synced_at) AS last_sync"
            " FROM hevy_workouts GROUP BY user_id ORDER BY user_id"
        )).mappings():
            hevy.append(dict(r))

    at_risk: list[tuple[str, int]] = []
    for label, table, where in _NON_REDERIVABLE_HEVY:
        if table in graph.tables:
            n = _count(conn, table, where, uid, q)
            if n:
                at_risk.append((label, n))
    if _REGION_TAGS_TABLE in graph.scope:
        n = counts[_REGION_TAGS_TABLE]
        if n:
            at_risk.append((f"{_REGION_TAGS_TABLE} on templates owned by the target", n))

    knowledge: list[dict[str, Any]] = []
    if "user_knowledge_entries" in graph.tables:
        knowledge = [dict(r) for r in conn.execute(text(
            "SELECT type, source, active, COUNT(*) AS n, MAX(added_at) AS latest"
            " FROM user_knowledge_entries WHERE user_id = :uid"
            " GROUP BY type, source, active ORDER BY type, source, active"
        ), {"uid": uid}).mappings()]
    legacy = counts.get("user_knowledge", 0)
    reset_tokens = None
    if "password_reset_tokens" in graph.tables:
        r = conn.execute(text(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN used THEN 0 ELSE 1 END) AS unused,"
            " MAX(created_at) AS latest FROM password_reset_tokens WHERE user_id = :uid"
        ), {"uid": uid}).mappings().first()
        reset_tokens = {"n": int(r["n"] or 0), "unused": int(r["unused"] or 0), "latest": r["latest"]}
    mcp_tokens = None
    if "mcp_oauth_tokens" in graph.tables:
        # Live = not revoked and not expired. A typed bind keeps the timestamp comparison honest on
        # both Postgres (timestamptz) and the SQLite test substrate.
        now = bindparam("now", datetime.now(timezone.utc), type_=DateTime(timezone=True))
        live = {"access": 0, "refresh": 0}
        last_used = None
        for r in conn.execute(text(
            "SELECT kind, COUNT(*) AS n, MAX(last_used_at) AS last_used FROM mcp_oauth_tokens"
            " WHERE user_id = :uid AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > :now)"
            " GROUP BY kind"
        ).bindparams(now), {"uid": uid}).mappings():
            live[r["kind"]] = int(r["n"])
            if r["last_used"] is not None and (last_used is None or str(r["last_used"]) > str(last_used)):
                last_used = r["last_used"]
        mcp_tokens = {"access": live["access"], "refresh": live["refresh"], "last_used": last_used}

    return Plan(
        user_id=uid,
        user={"email_masked": _mask(u["email"]), "created_at": u["created_at"],
              "full_name": u["full_name"]},
        token=_confirm_token(uid, u["email"]),
        integrations=integrations, rows=rows, nulled=nulled, blockers=blockers,
        orphans=orphans, hevy=hevy, at_risk=at_risk,
        knowledge=knowledge, legacy_knowledge=legacy, reset_tokens=reset_tokens,
        mcp_tokens=mcp_tokens,
    )


def format_plan(plan: Plan, target: str) -> str:
    out: list[str] = []
    w = out.append
    w(f"Target database: {target}")
    w(f"User {plan.user_id}: full_name={ascii(plan.user['full_name'])}  email={plan.user['email_masked']}"
      f"  created_at={plan.user['created_at']}")
    w("No last-login is recorded anywhere; per-table latest activity is below.")
    w("")
    w("Sign-in artefacts:")
    if plan.reset_tokens is not None:
        rt = plan.reset_tokens
        w(f"  password_reset_tokens: {rt['n']} row(s), {rt['unused']} unused, latest {rt['latest'] or '-'}"
          " (an auth table persisted in the DB)")
    w("  web/API login: stateless JWT keyed on email; ends the moment the user row is deleted.")
    if plan.mcp_tokens is not None:
        m = plan.mcp_tokens
        w("  MCP OAuth (mcp_oauth_tokens, hashed; oauth_provider.PersonalOAuthProvider):")
        w(f"    live tokens for this user: {m['access']} access, {m['refresh']} refresh (not revoked, not")
        w(f"    expired); last used {m['last_used'] or 'never'}. They cascade-delete with the user, so a delete")
        w("    ends every MCP session this account holds at once. MCP sign-in also checks this account's")
        w("    email + password against `users`: if this account backs an MCP / demo connection, that")
        w("    connection stops working.")
    else:
        w("  MCP OAuth: table mcp_oauth_tokens is absent from this database (migration not applied), so MCP")
        w("    tokens cannot be inventoried here. MCP sign-in checks this account's email + password against")
        w("    `users`, so a delete ends that sign-in path.")
    w("")
    w("Knowledge:")
    if plan.knowledge:
        for k in plan.knowledge:
            w(f"  user_knowledge_entries type={k['type']} source={k['source']} active={bool(k['active'])}:"
              f" {k['n']} (latest added {k['latest']})")
    else:
        w("  user_knowledge_entries: (none)")
    w(f"  user_knowledge (legacy category store): {plan.legacy_knowledge}")
    w("")
    w("Stored integrations (credentials are not read; deleted first on execute):")
    if plan.integrations:
        for i in plan.integrations:
            w(f"  {i['provider']:<10} created={i['created_at']}  updated={i['updated_at']}")
    else:
        w("  (none)")
    w("")
    w("Rows removed by a delete of this user (CASCADE, transitive):")
    for r in plan.rows:
        if r["n"]:
            w(f"  {r['table']:<34} {r['n']:>8}   via {r['via']}   latest {r['latest']}")
    empty = [r["table"] for r in plan.rows if not r["n"]]
    w(f"  TOTAL {plan.total_rows} row(s) across {len(plan.rows) - len(empty)} of {len(plan.rows)} scoped tables")
    w(f"  scoped tables with 0 rows: {', '.join(empty) if empty else '(none)'}")
    w("")
    w("References that SURVIVE the delete (nulled, not removed):")
    if plan.nulled:
        for t, c, n in plan.nulled:
            w(f"  {t}.{c}: {n} row(s) kept, reference set to NULL")
    else:
        w("  (none)")
    w("")
    w("Hevy ownership (hevy_workouts, keyed on the Hevy id alone; the sync re-assigns the owner):")
    if plan.hevy:
        for h in plan.hevy:
            mark = "  <-- target" if h["user_id"] == plan.user_id else ""
            w(f"  user {h['user_id']}: {h['n']} workouts, {h['excluded'] or 0} excluded,"
              f" start {h['first_start']} .. {h['last_start']}, last sync {h['last_sync']}{mark}")
    else:
        w("  (no hevy_workouts rows)")
    w("")
    w("Non-re-derivable rows (Hevy cannot re-supply these; the cascade would destroy them):")
    if plan.at_risk:
        for label, n in plan.at_risk:
            w(f"  {n:>6}  {label}")
    else:
        w("  (none)")
    w("")
    reasons = plan.refusal_reasons
    if reasons:
        w("EXECUTE WILL REFUSE:")
        for r in reasons:
            w(f"  - {r}")
    if plan.at_risk:
        w("EXECUTE WILL REFUSE unless --accept-loss is passed (non-re-derivable rows above).")
    if not reasons and not plan.at_risk:
        w("No blockers.")
    w("")
    w("DRY RUN - nothing was changed.")
    w(f"To execute: --user-id {plan.user_id} --execute --confirm {plan.token}"
      + (" --accept-loss" if plan.at_risk else ""))
    return "\n".join(out)


# -- execute -------------------------------------------------------------------------------

@dataclass
class ExecResult:
    user_id: int
    integrations_deleted: list[str]
    rows_removed: dict[str, int]
    protected_counts: dict[int, dict[str, int]]


def execute_retirement(
    engine: Engine, uid: int, confirm: str | None, *, accept_loss: bool = False,
    graph: Graph | None = None,
) -> ExecResult:
    uid = int(uid)
    _refuse_protected(uid)
    graph = graph or discover_graph(engine)
    with engine.begin() as conn:  # one transaction: any raise below rolls everything back
        plan = build_plan(conn, engine, graph, uid)
        if not confirm or confirm != plan.token:
            raise ConfirmMismatch("--confirm token missing or does not match this user (re-run the dry run)")
        if plan.refusal_reasons:
            raise Blocked("; ".join(plan.refusal_reasons))
        if plan.at_risk and not accept_loss:
            raise Blocked(
                "non-re-derivable rows would be destroyed ("
                + "; ".join(f"{n} {label}" for label, n in plan.at_risk)
                + "); pass --accept-loss to proceed knowingly"
            )

        before = {p: snapshot(conn, engine, graph, p) for p in sorted(PROTECTED_USER_IDS)}
        removed = {r["table"]: r["n"] for r in plan.rows if r["n"]}

        # Tokens first, explicitly (the FK would cascade them anyway).
        tokens_deleted: list[str] = []
        if "user_integrations" in graph.tables:
            tokens_deleted = [i["provider"] for i in plan.integrations]
            conn.execute(text("DELETE FROM user_integrations WHERE user_id = :uid"), {"uid": uid})

        _refuse_protected(uid)  # last look before the irreversible statement
        res = conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
        if res.rowcount != 1:
            raise InvariantError(f"DELETE FROM users matched {res.rowcount} rows, expected 1")

        after = {p: snapshot(conn, engine, graph, p) for p in sorted(PROTECTED_USER_IDS)}
        if before != after:
            diff = {p: {t: (before[p][t], after[p].get(t)) for t in before[p] if before[p][t] != after[p].get(t)}
                    for p in before if before[p] != after[p]}
            raise InvariantError(f"protected user row counts changed (before, after): {diff}")
        left = {t: n for t, n in snapshot(conn, engine, graph, uid).items() if n}
        if left:
            raise InvariantError(f"target still has rows after the delete: {left}")
    return ExecResult(uid, tokens_deleted, removed, before)


# -- CLI -----------------------------------------------------------------------------------

def _target_label(engine: Engine) -> str:
    url = engine.url
    if engine.dialect.name == "sqlite":
        return f"sqlite file={url.database}"
    return f"{engine.dialect.name} host={url.host} port={url.port} db={url.database}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Retire a user: dry run by default, --execute to delete.")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--execute", action="store_true", help="Delete (default is a read-only dry run).")
    p.add_argument("--confirm", help="Token printed by the dry run for this user.")
    p.add_argument("--accept-loss", action="store_true",
                   help="Proceed although non-re-derivable Hevy-keyed rows would be destroyed.")
    args = p.parse_args(argv)

    try:
        _refuse_protected(args.user_id)
        if args.confirm and not args.execute:
            p.error("--confirm is only meaningful with --execute")
        import database  # deferred: importing opens no connection, but keeps --help cheap

        engine = database.engine
        graph = discover_graph(engine)
        if not args.execute:
            with engine.connect() as conn:  # read-only: nothing here writes, and it rolls back on close
                plan = build_plan(conn, engine, graph, args.user_id)
            print(format_plan(plan, _target_label(engine)))
            return 0
        print(f"Target database: {_target_label(engine)}")
        result = execute_retirement(engine, args.user_id, args.confirm,
                                    accept_loss=args.accept_loss, graph=graph)
    except RetireError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return exc.exit_code

    print(f"EXECUTED: user {result.user_id} retired (committed).")
    print(f"  integration tokens deleted: {', '.join(result.integrations_deleted) or '(none)'}")
    print(f"  rows removed: {sum(result.rows_removed.values())} across {len(result.rows_removed)} tables")
    for t, n in sorted(result.rows_removed.items()):
        print(f"    {t:<34} {n:>8}")
    for pid, counts in result.protected_counts.items():
        print(f"  protected user {pid}: {sum(counts.values())} rows across {len(counts)} tables,"
              " identical before and after (asserted in-transaction)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
