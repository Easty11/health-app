#!/usr/bin/env python3
"""gen_status_model.py — append-only MACHINE status model across both repos.

Reads the governance stores of health-app and health-connect-app at **master** (via
raw.githubusercontent, pinned to a resolved SHA for provenance) and emits a JSON status
model: per-repo state-vocabulary tallies for branch rows, decision-sequence integrity, and an
off-vocabulary tally that is reported, never dropped. Neither repo has a questions store (both
retired, DECISIONS_LOG #468 / health-connect-app #54): open questions are GitHub issues, and
since schema 2 this tool reads them (DECISIONS_LOG #483): `repos[<repo>]["issues"]`. The status
RENDERER never fetches; it reads that block.

Distinct from `gen_governance_view.py` by design (DECISIONS_LOG #192): that renders a
human-readable digest; this produces diffable machine JSON that a cross-repo snapshot ages
over. The two share ONE thing — the dialect grammar — via `gov_dialects` (#191).

GATES — a status generator that under-reports silently is worse than none (#190). Before the
model is returned, four gates run; any failure HALTs with a non-zero exit and a stderr line
naming the store, and NOTHING partial is emitted:

  1. Count parity   — a crude, dialect-agnostic heading/row count (computed by an independent
                      path from the structured parser) vs the parsed count, per store per
                      repo. Mismatch => HALT.
  2. Sequence       — decisions are append-only and gapless: highest number == parsed count.
  3. Extraction     — count parity is necessary but INSUFFICIENT. If a state field resolves
                      EMPTY across ALL parsed items of a store, the parser matched a schema
                      that is not there (the live `**State:**`/`**Status:**` bug, #190). HALT.
  4. Issues shape   — every repo's `issues` block is exactly one of two shapes (below). A block
                      that could let a consumer read "0 open issues" while the tracker was never
                      read (`count: 0` with `tracker: "unreachable"`, an "ok" with no HTTP 200)
                      HALTs. An unreachable tracker is NOT a halt: it is carried, as UNKNOWN.

ISSUES (schema 2). Two transports, ONE grammar (`normalise_issues`):
  live  — `fetch_open_issues(owner, repo)` reads api.github.com itself;
  file  — `--issues-json PATH` reads raw API payloads keyed by repo name, produced by
          `fetch_issues.py` wherever the API is reachable. When given, NO live fetch is made.
The block, per repo:
  {"tracker": "ok", "count": N, "items": [{number, title, labels: [str], created_at: "YYYY-MM-DD",
                                          html_url}], "http": 200}
  {"tracker": "unreachable", "count": null, "items": null}
`count: null` is deliberate: a consumer that does arithmetic on it must crash, not print zero.
A repo missing from the file, a non-array value, or an item the normaliser rejects is unreachable.

Off-vocabulary state tokens are tallied per field and surfaced under `drift`; a clean-gate
run with non-zero off-vocab is still a finding, never a pass-in-silence.

Usage:
    python scripts/gen_status_model.py --dry-run     # build + gate, print JSON, write nothing
    python scripts/gen_status_model.py --issues-json PATH   # issues from a fetch_issues.py file
    python scripts/gen_status_model.py --self-check   # exercise the gates on synthetic input
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import fetch_issues as FI
import gov_dialects as D

RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{store}.md"

# Snapshots live OUTSIDE both repos (DECISIONS_LOG #192): a cross-repo view inside one repo
# recreates a two-master pattern. Default is Projects/_status — sibling to the repos, where
# repo = Projects/health-app, so parents[2] is Projects. Overridable with --out-dir.
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "_status"

# Store keys -> the store file basename.
STORE_FILE = {
    "decisions": "DECISIONS_LOG",
    "branches": "BRANCHES",
}

# A store smaller than this is a fetch failure, not a small store (mirrors gen_governance_view).
MIN_STORE_BYTES = 300

# 2: adds repos[<repo>]["issues"] (DECISIONS_LOG #483). A schema-1 snapshot has no `issues` key;
# `status_diff` reads it as tracker "unreachable" (not compared), never as zero.
SCHEMA_VERSION = 2


class StatusGateError(RuntimeError):
    """A gate failed. NEVER degrade to a partial or empty model — a quiet pass is the bug
    this tool exists to remove."""


# --------------------------------------------------------------------------------------
# Fetch  (kept local, not in gov_dialects: the shared module is dialect grammar only)
# --------------------------------------------------------------------------------------

def resolve_master_sha(repo: str) -> str:
    import subprocess
    url = f"https://github.com/{D.OWNER}/{repo}.git"
    out = subprocess.run(
        ["git", "ls-remote", url, "refs/heads/master"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not out:
        raise StatusGateError(f"{repo}: ls-remote returned nothing for refs/heads/master")
    sha = out.split()[0]
    if len(sha) != 40:
        raise StatusGateError(f"{repo}: implausible SHA {sha!r}")
    return sha


def fetch(repo: str, sha: str, store_file: str) -> str:
    url = RAW.format(owner=D.OWNER, repo=repo, sha=sha, store=store_file)
    with urllib.request.urlopen(url, timeout=30) as resp:
        if resp.status != 200:
            raise StatusGateError(f"{url} returned HTTP {resp.status}")
        text = resp.read().decode("utf-8")
    if len(text.encode("utf-8")) < MIN_STORE_BYTES:
        raise StatusGateError(
            f"{repo}/{store_file}.md is {len(text)} bytes — under the {MIN_STORE_BYTES}-byte "
            f"floor. Treating as a fetch failure, not a small store."
        )
    return text


# --------------------------------------------------------------------------------------
# Crude counts — the gate's own dialect-agnostic method, computed independently of the
# structured parser so a parser that silently drops entries diverges from it.
# --------------------------------------------------------------------------------------

def crude_count(store_key: str, text: str) -> int:
    lines = text.splitlines()
    if store_key == "decisions":
        return sum(1 for ln in lines if D.DECISION_HEADING.match(ln))
    if store_key == "branches":
        return sum(1 for ln in lines if D.is_table_data_row(ln))
    raise StatusGateError(f"crude_count: unknown store {store_key!r}")


# --------------------------------------------------------------------------------------
# Structured parse
# --------------------------------------------------------------------------------------

def parse_decisions(text: str, repo: str) -> dict:  # repo unused; uniform parser signature
    lines = text.splitlines()
    heads = [(i, int(m.group(1)), m.group(2))
             for i, ln in enumerate(lines) if (m := D.DECISION_HEADING.match(ln))]
    nums = [n for _, n, _ in heads]
    # Decision state is BEST-EFFORT and NEVER extraction-gated (see gate wiring in build_repo):
    # a decision with no extractable state is `unstated` — a legitimate optional-by-convention
    # absence (intent-only / ledger-meta entries), not a defect. `inline_states` surfaces HCA's
    # lowercase '· active'/'· held' dialect tokens as-authored; health-app decisions state via a
    # '**Status:**' body line (free prose) and contribute to `stated` without an inline token.
    inline: Counter = Counter()
    stated = 0
    for idx, (line_i, _num, rest) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        if D.decision_state(lines, line_i, rest, end):
            stated += 1
            tok = D.decision_inline_state(rest)
            if tok:
                inline[tok] += 1
    return {
        "count": len(nums),
        "max": max(nums) if nums else 0,
        "min": min(nums) if nums else 0,
        "gapless": bool(nums) and max(nums) == len(nums) == len(set(nums)),
        "stated": stated,
        "unstated": len(nums) - stated,
        "inline_states": dict(sorted(inline.items())),
    }


def _branch_status_cell(cells: list[str]) -> str:
    """The Status column of a BRANCHES row, robust to unescaped `|` inside prose/code cells.

    `| Branch | Purpose | Status | Detail | Blocker |` — column 3 is Status. But cells here
    carry raw `|` (e.g. a `float | None` type in a Purpose cell), which mis-splits the row and
    shifts every later column. The Status value always LEADS with a work-item token, so scan
    left-to-right (past the branch-name cell) for the first cell that does — that is the Status
    regardless of stray pipes. Fall back to the positional column only to surface a genuinely
    off-vocab or missing status."""
    for c in cells[1:]:
        if D.canonical_token(c) in D.WORK_ITEM_STATES:
            return c
    return cells[2] if len(cells) > 2 else ""


def parse_branches(text: str, repo: str) -> dict:  # repo unused; uniform parser signature
    lines = text.splitlines()
    by_state: Counter = Counter()
    off_vocab: Counter = Counter()
    missing_ids: list[str] = []
    rows = 0
    for ln in lines:
        if not D.is_table_data_row(ln):
            continue
        rows += 1
        cells = D.table_cells(ln)
        status_cell = _branch_status_cell(cells)
        tok, off = D.classify(status_cell, D.WORK_ITEM_STATES)
        if tok is None:
            missing_ids.append(cells[0] if cells else "?")   # the branch name names the offender
        elif off:
            off_vocab[tok] += 1
        else:
            by_state[tok] += 1
    return {
        "count": rows,
        "by_state": dict(sorted(by_state.items())),
        "off_vocab": dict(sorted(off_vocab.items())),
        "missing_state": len(missing_ids),
        "missing_ids": missing_ids,
    }


PARSERS = {
    "decisions": parse_decisions,
    "branches": parse_branches,
}


# --------------------------------------------------------------------------------------
# Issues  (DECISIONS_LOG #483) — the model owns the open-issues read AND its grammar. The
# renderer never fetches. One normaliser, two transports (live API / --issues-json file).
# --------------------------------------------------------------------------------------

ISSUE_ITEM_FIELDS = ("number", "title", "labels", "created_at", "html_url")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class IssueShapeError(ValueError):
    """A raw issue payload the normaliser will not interpret. The repo becomes tracker
    "unreachable" — a payload we cannot read is not a payload with zero issues."""


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def normalise_issues(raw) -> list[dict]:
    """Raw GitHub `GET /repos/{o}/{r}/issues` array -> normalised open issues, ascending by number.

    Pull requests (items carrying `pull_request` — the issues endpoint returns both) are
    EXCLUDED. Each issue becomes {number, title, labels: [str], created_at: 'YYYY-MM-DD',
    html_url}. A malformed item raises IssueShapeError; it is never skipped, because a skipped
    item is a silent under-count."""
    if not isinstance(raw, list):
        raise IssueShapeError(f"expected a JSON array of issues, got {type(raw).__name__}")
    items: list[dict] = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise IssueShapeError(f"item {i} is {type(r).__name__}, not an object")
        if "pull_request" in r:
            continue
        num = r.get("number")
        if not _is_int(num):
            raise IssueShapeError(f"item {i}: number {num!r} is not an integer")
        title, url, created = r.get("title"), r.get("html_url"), r.get("created_at")
        if not isinstance(title, str):
            raise IssueShapeError(f"issue {num}: title is {type(title).__name__}, not str")
        if not isinstance(url, str) or not url:
            raise IssueShapeError(f"issue {num}: html_url missing")
        if not isinstance(created, str) or not _ISO_DATE.match(created[:10]):
            raise IssueShapeError(f"issue {num}: created_at {created!r} is not an ISO timestamp")
        labels_raw = r.get("labels")
        if not isinstance(labels_raw, list):
            raise IssueShapeError(f"issue {num}: labels is {type(labels_raw).__name__}, not a list")
        labels: list[str] = []
        for lb in labels_raw:
            name = lb.get("name") if isinstance(lb, dict) else lb
            if not isinstance(name, str):
                raise IssueShapeError(f"issue {num}: label {lb!r} has no string name")
            labels.append(name)
        items.append({"number": num, "title": title, "labels": sorted(labels),
                      "created_at": created[:10], "html_url": url})
    nums = [it["number"] for it in items]
    if len(nums) != len(set(nums)):
        dup = sorted(n for n in set(nums) if nums.count(n) > 1)
        raise IssueShapeError(f"duplicate issue number(s) {dup} (overlapping pages?)")
    return sorted(items, key=lambda it: it["number"])


def issues_block_ok(items: list[dict], http: int) -> dict:
    return {"tracker": "ok", "count": len(items), "items": items, "http": http}


def issues_block_unreachable() -> dict:
    """`count: None` on purpose — a consumer that reads it as an int must crash, not print 0."""
    return {"tracker": "unreachable", "count": None, "items": None}


def issues_block_from_payload(repo: str, raw) -> dict:
    """FILE transport for one repo. A file entry exists only for a repo `fetch_issues.py` read
    completely (HTTP 200 on every page), so a list here records `http: 200`; anything that is
    not a list (null, an API error object) or does not normalise is unreachable."""
    try:
        return issues_block_ok(normalise_issues(raw), 200)
    except IssueShapeError as exc:
        print(f"    {repo}: issues payload rejected — {exc}", file=sys.stderr)
        return issues_block_unreachable()


def fetch_open_issues(owner: str, repo: str) -> dict:
    """LIVE transport for one repo: read the open issues from api.github.com (every page) and
    normalise through the same function as the file transport. ANY failure -> unreachable."""
    try:
        status, raw = FI.fetch_open_issues_raw(owner, repo)
        return issues_block_ok(normalise_issues(raw), status)
    except (FI.FetchError, IssueShapeError) as exc:
        print(f"    {repo}: issues fetch failed — {exc}", file=sys.stderr)
        return issues_block_unreachable()


def load_issues_payload(path: Path) -> dict:
    """The `--issues-json` file. An unreadable file or one that is not a JSON object is an
    operator error and HALTs; a REPO missing from a good file is the partial-file case and is
    unreachable (never zero)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StatusGateError(f"ISSUES FILE [{path}]: unreadable or not JSON ({exc}). "
                              f"Refusing to guess the tracker's state.") from exc
    if not isinstance(payload, dict):
        raise StatusGateError(f"ISSUES FILE [{path}]: top level is {type(payload).__name__}; "
                              f"expected an object keyed by repo name.")
    return payload


# --------------------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------------------

def gate_count_parity(repo: str, store_key: str, crude: int, parsed: int) -> None:
    if crude != parsed:
        raise StatusGateError(
            f"COUNT PARITY [{repo}/{STORE_FILE[store_key]}.md]: crude heading/row count "
            f"{crude} != parsed count {parsed}. The parser dropped or invented entries; "
            f"refusing to emit a model that under-reports."
        )


def gate_sequence(repo: str, decisions: dict) -> None:
    if not decisions["gapless"]:
        raise StatusGateError(
            f"SEQUENCE [{repo}/DECISIONS_LOG.md]: highest #{decisions['max']} but "
            f"{decisions['count']} entries (min #{decisions['min']}). Append-only decisions "
            f"must be gapless — a gap or duplicate is a store defect, not a parse to publish."
        )


def gate_extraction_nonempty(repo: str, store_key: str, parsed: dict) -> None:
    """Necessary-but-insufficient count parity is not enough (DECISIONS_LOG #190). If a state
    field was extracted for N>0 items and came back empty for ALL of them, the parser matched
    a schema that is not there — the exact `**State:**`/`**Status:**` failure class, which the
    count gate is structurally blind to."""
    n = parsed["count"]
    if n == 0:
        return
    extracted = sum(parsed["by_state"].values()) + sum(parsed["off_vocab"].values())
    if extracted == 0:
        raise StatusGateError(
            f"EXTRACTION [{repo}/{STORE_FILE[store_key]}.md]: state extracted EMPTY for all "
            f"{n} items ({parsed['missing_state']} missing). Count parity held, so the count "
            f"gate saw nothing — but the state field matched a schema that is not there. HALT."
        )


def gate_no_missing_state(repo: str, store_key: str, parsed: dict) -> None:
    """Branches carry MANDATORY state — unlike decisions, whose `**Status:**` is
    optional by convention (#209). Any branch missing its state is a store defect, so
    HALT on ANY non-zero missing (no threshold) and NAME the offenders. This is stricter than
    `gate_extraction_nonempty`, which only fires when ALL N are empty (the #190 schema-mismatch
    class); a single stateless item slips past that gate but not this one."""
    missing_ids = parsed.get("missing_ids", [])
    if missing_ids:
        ids = ", ".join(missing_ids)
        raise StatusGateError(
            f"MISSING STATE [{repo}/{STORE_FILE[store_key]}.md]: {len(missing_ids)} item(s) "
            f"declare no state: {ids}. Branches must each carry a state (#209); HALT."
        )


def gate_issues_shape(repo: str, block) -> None:
    """The `issues` block is EXACTLY one of two shapes (module docstring). The point is that no
    block can read as "0 open issues" while the tracker was never read:
      * unreachable: `count` and `items` both null — `count: 0` here is the bug this gate names;
      * ok: `http` is 200 (an empty list is believable only as a 200 with an empty array),
        `count` == len(`items`), and every item carries exactly the five fields, typed."""
    def bad(why: str):
        raise StatusGateError(f"ISSUES SHAPE [{repo}]: {why}. A block that can read as zero "
                              f"while the tracker was never read is the bug; HALT.")

    if not isinstance(block, dict):
        bad(f"`issues` block is {type(block).__name__}, not an object")
    tracker = block.get("tracker")
    if tracker == "unreachable":
        if set(block) != {"tracker", "count", "items"}:
            bad(f"unreachable block has keys {sorted(block)}")
        if block["count"] is not None or block["items"] is not None:
            bad(f"tracker is unreachable but count={block['count']!r}, items="
                f"{'null' if block['items'] is None else 'present'}; both must be null")
        return
    if tracker != "ok":
        bad(f"tracker is {tracker!r}, neither 'ok' nor 'unreachable'")
    if set(block) != {"tracker", "count", "items", "http"}:
        bad(f"ok block has keys {sorted(block)}")
    if not _is_int(block["http"]) or block["http"] != 200:
        bad(f"tracker ok without http 200 (http={block['http']!r})")
    items = block["items"]
    if not isinstance(items, list):
        bad(f"ok block items is {type(items).__name__}, not a list")
    if not _is_int(block["count"]) or block["count"] != len(items):
        bad(f"count {block['count']!r} != {len(items)} items")
    seen: set = set()
    for it in items:
        if not isinstance(it, dict) or set(it) != set(ISSUE_ITEM_FIELDS):
            bad(f"item fields {sorted(it) if isinstance(it, dict) else type(it).__name__} "
                f"!= {sorted(ISSUE_ITEM_FIELDS)}")
        n = it["number"]
        if (not _is_int(n) or not isinstance(it["title"], str) or not isinstance(it["html_url"], str)
                or not isinstance(it["created_at"], str) or not _ISO_DATE.match(it["created_at"])
                or not isinstance(it["labels"], list)
                or not all(isinstance(lb, str) for lb in it["labels"])):
            bad(f"issue {n!r} has a mistyped field")
        if n in seen:
            bad(f"duplicate issue number {n}")
        seen.add(n)


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------

def build_repo(repo: str, sha: str, texts: dict) -> dict:
    out = {"provenance": {"ref": "master", "sha": sha}}
    for store_key in STORE_FILE:
        text = texts[store_key]
        parsed = PARSERS[store_key](text, repo)
        crude = crude_count(store_key, text)
        gate_count_parity(repo, store_key, crude, parsed["count"])
        if store_key == "decisions":
            gate_sequence(repo, parsed)                        # decisions: sequence, not extraction (#209)
        else:
            gate_extraction_nonempty(repo, store_key, parsed)  # #190 all-empty schema-mismatch
            gate_no_missing_state(repo, store_key, parsed)     # #209 any partial-missing, ids named
        parsed.pop("missing_ids", None)   # transient — gate consumes it; never persisted (schema stays v1)
        out[store_key] = parsed
    return out


def collect_drift(model: dict) -> list:
    """Off-vocab on stateful stores is drift — surfaced, never a HALT (Step 1: accept-and-flag)."""
    drift = []
    for repo, rd in model["repos"].items():
        ov = rd["branches"]["off_vocab"]
        if ov:
            drift.append({"repo": repo, "store": "branches", "off_vocab": ov})
    return drift


def build_model(generated_utc: str, issues_payload: dict | None = None) -> dict:
    """`issues_payload` is the parsed `--issues-json` file (raw API arrays keyed by repo name), or
    None for the live transport. When it is given NO live fetch is attempted."""
    repos: dict = {}
    if issues_payload is not None:
        for extra in sorted(set(issues_payload) - set(D.REPOS)):
            print(f"  warning: --issues-json carries {extra!r}, not a tracked repo; ignored",
                  file=sys.stderr)
    for repo in D.REPOS:
        sha = resolve_master_sha(repo)
        print(f"  {repo}: master @ {sha[:7]}", file=sys.stderr)
        texts = {k: fetch(repo, sha, STORE_FILE[k]) for k in STORE_FILE}
        repos[repo] = build_repo(repo, sha, texts)
        for k in STORE_FILE:
            p = repos[repo][k]
            print(f"    {STORE_FILE[k]+'.md':<18} {p['count']:>4} items", file=sys.stderr)
        if issues_payload is None:
            block = fetch_open_issues(D.OWNER, repo)                     # live transport
        elif repo in issues_payload:
            block = issues_block_from_payload(repo, issues_payload[repo])  # file transport
        else:
            print(f"    {repo}: not in the --issues-json file", file=sys.stderr)
            block = issues_block_unreachable()                           # missing is never zero
        gate_issues_shape(repo, block)
        repos[repo]["issues"] = block
        print(f"    {'issues':<18} " + (f"{block['count']:>4} open (http {block['http']})"
              if block["tracker"] == "ok" else "UNREACHABLE — open-issue state UNKNOWN, not zero"),
              file=sys.stderr)
    model = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": generated_utc,
        "repos": repos,
    }
    model["drift"] = collect_drift(model)
    return model


# --------------------------------------------------------------------------------------
# Snapshot writer  (DECISIONS_LOG #192 / #193)
# --------------------------------------------------------------------------------------

README = """\
# _status — cross-repo governance status snapshots (DERIVED, not truth)

Generated by `health-app/scripts/gen_status_model.py`. This directory lives OUTSIDE both
repos on purpose (DECISIONS_LOG #192): a cross-repo view inside one repo recreates a
two-master pattern. Snapshots are DERIVED observations — the governance stores at each
repo's master are canonical. Each snapshot records the master SHA it read per repo, so it
is reproducible from those refs.

ACCEPTED LOSS, stated rather than left implicit: this directory is unbacked and
single-machine. Losing it costs AGEING history (the diff baseline), never correctness —
the model regenerates from the stores at any time.

- `snapshots/<ISO8601>_model.json` — append-only, one per run.
- `latest.json` — the most recent snapshot.
- Schema 2 adds `repos.<repo>.issues`: `{"tracker": "ok", "count": N, "items": [...], "http": 200}`
  or `{"tracker": "unreachable", "count": null, "items": null}`. `null` means the tracker was
  NOT READ — state unknown, never zero. A schema-1 snapshot has no `issues` block and reads the
  same way: not compared.
- The first snapshot with no predecessor carries `"baseline": true`: downstream diff
  consumers must render "baseline run, no comparison available", never an empty diff that
  reads as "no change".
"""


def _fs_stamp(generated_utc: str) -> str:
    """Filesystem-safe timestamp from the ISO instant — colons are illegal in Windows
    filenames. '2026-08-10T11:50:22Z' -> '2026-08-10T115022Z'."""
    return generated_utc.replace(":", "")


def write_snapshot(model: dict, out_dir: Path) -> tuple[Path, bool]:
    """Write the model as an append-only snapshot + refresh latest.json.

    Baseline is decided by predecessors present BEFORE this write: a snapshot with no prior
    is the baseline (#192/#193). Provenance per repo is already carried in the model.
    """
    for repo, rd in model["repos"].items():       # a schema-2 snapshot always carries a gated block
        gate_issues_shape(repo, rd.get("issues"))

    snap_dir = out_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    predecessors = sorted(snap_dir.glob("*_model.json"))
    model["baseline"] = len(predecessors) == 0

    stamp = _fs_stamp(model["generated_utc"])
    snap_path = snap_dir / f"{stamp}_model.json"
    n = 2
    while snap_path.exists():                       # keep append-only if two runs share a second
        snap_path = snap_dir / f"{stamp}_{n}_model.json"
        n += 1

    body = json.dumps(model, indent=2, ensure_ascii=False) + "\n"
    snap_path.write_text(body, encoding="utf-8", newline="\n")
    (out_dir / "latest.json").write_text(body, encoding="utf-8", newline="\n")

    readme = out_dir / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8", newline="\n")

    return snap_path, model["baseline"]


# --------------------------------------------------------------------------------------
# Self-check — synthetic exercise of each gate (no network). Real-positive proof is the
# live `**State:**` bug, demonstrated separately; this guards the gate logic itself.
# --------------------------------------------------------------------------------------

def self_check() -> int:
    def expect_halt(label, fn):
        try:
            fn()
        except StatusGateError:
            print(f"  ok   {label} -> HALT", file=sys.stderr)
            return
        raise SystemExit(f"  FAIL {label} did NOT halt")

    # 1. count parity
    expect_halt("count parity", lambda: gate_count_parity("r", "branches", 89, 88))
    # 2. sequence gap
    expect_halt("sequence gap",
                lambda: gate_sequence("r", {"count": 88, "max": 89, "min": 1, "gapless": False}))
    # 3. extraction empty across all N (the **State:** class)
    expect_halt("extraction empty", lambda: gate_extraction_nonempty(
        "r", "branches", {"count": 89, "by_state": {}, "off_vocab": {}, "missing_state": 89}))
    # off-vocab is NOT a halt — it is tallied.
    ov = {"count": 2, "by_state": {"DONE": 1}, "off_vocab": {"PARKED": 1}, "missing_state": 0}
    gate_extraction_nonempty("r", "branches", ov)  # must not raise
    print("  ok   off-vocab tallied, not halted", file=sys.stderr)

    # 4. any PARTIAL missing state (#209) — halts and names the offender, no threshold.
    expect_halt("missing state (partial)", lambda: gate_no_missing_state(
        "r", "branches", {"count": 3, "by_state": {"DONE": 2}, "off_vocab": {},
                          "missing_state": 1, "missing_ids": ["`feat/x`"]}))
    gate_no_missing_state("r", "branches", {"count": 2, "by_state": {"DONE": 2}, "off_vocab": {},
                                            "missing_state": 0, "missing_ids": []})  # clean: no raise
    print("  ok   no-missing-state gate (partial halts + names ids; clean passes)", file=sys.stderr)

    # 5. issues shape (DECISIONS_LOG #483): no block may read as zero while the tracker was unread.
    it = {"number": 7, "title": "t", "labels": ["fork"], "created_at": "2026-11-01",
          "html_url": "https://github.com/o/r/issues/7"}
    expect_halt("issues: count 0 but tracker unreachable", lambda: gate_issues_shape(
        "r", {"tracker": "unreachable", "count": 0, "items": None}))
    expect_halt("issues: unreachable with items []", lambda: gate_issues_shape(
        "r", {"tracker": "unreachable", "count": None, "items": []}))
    expect_halt("issues: ok, empty, no http 200", lambda: gate_issues_shape(
        "r", {"tracker": "ok", "count": 0, "items": []}))
    expect_halt("issues: ok, empty, http 403", lambda: gate_issues_shape(
        "r", {"tracker": "ok", "count": 0, "items": [], "http": 403}))
    expect_halt("issues: count != len(items)", lambda: gate_issues_shape(
        "r", {"tracker": "ok", "count": 2, "items": [it], "http": 200}))
    expect_halt("issues: item missing a field", lambda: gate_issues_shape(
        "r", {"tracker": "ok", "count": 1, "items": [{k: v for k, v in it.items() if k != "html_url"}],
              "http": 200}))
    expect_halt("issues: no block at all", lambda: gate_issues_shape("r", None))
    gate_issues_shape("r", {"tracker": "ok", "count": 0, "items": [], "http": 200})   # empty 200: allowed
    gate_issues_shape("r", {"tracker": "ok", "count": 1, "items": [it], "http": 200})
    gate_issues_shape("r", issues_block_unreachable())                                # carried, not halted
    assert issues_block_unreachable()["count"] is None, "unreachable count must be null, not 0"
    raw = [{"number": 9, "title": "pr", "pull_request": {}, "labels": [], "created_at": "2026-11-01T00:00:00Z",
            "html_url": "u"},
           {"number": 7, "title": "t", "labels": [{"name": "fork"}], "created_at": "2026-11-01T21:14:00Z",
            "html_url": "https://github.com/o/r/issues/7"}]
    assert normalise_issues(raw) == [it], "PR excluded; labels -> [str]; created_at -> ISO date"
    assert issues_block_from_payload("r", raw) == issues_block_ok([it], 200)
    assert issues_block_from_payload("r", {"message": "Bad credentials"}) == issues_block_unreachable()
    print("  ok   issues gate (zero-while-unread halts; empty-200 and unreachable-null pass) + normaliser",
          file=sys.stderr)

    # grammar positives for the reader-channel changes (no network).
    # Decision channel: the lowercase inline reader (HCA dialect).
    assert D.decision_inline_state("Title  ·  active  ·  supersedes #10") == "active", \
        "decision inline reader must SCAN segments, not take the last"
    assert D.decision_inline_state("Title  ·  held") == "held", "held is an enumerated inline token"
    assert D.decision_inline_state("### 45. health-app style, no middot") == "", \
        "no '·' -> no lowercase inline decision state (health-app decisions use **Status:**)"
    print("  ok   decision inline channel scans segments", file=sys.stderr)
    print("self-check: all gate positives fired", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="build + gate, print the model JSON to stdout, write no snapshot")
    ap.add_argument("--self-check", action="store_true",
                    help="exercise the gates on synthetic input and exit")
    ap.add_argument("--issues-json", type=Path, default=None, metavar="PATH",
                    help="raw GitHub issues payloads keyed by repo name, from fetch_issues.py; "
                         "when given, NO live issues fetch is attempted (a repo missing from "
                         "the file is unreachable, never zero)")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                    help=f"snapshot root (default: {DEFAULT_OUT_DIR})")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = load_issues_payload(args.issues_json) if args.issues_json else None
    model = build_model(generated, payload)

    if args.dry_run:
        json.dump(model, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0

    snap_path, baseline = write_snapshot(model, args.out_dir)
    tag = "BASELINE (no predecessor — downstream renders 'no comparison available')" if baseline \
        else "incremental"
    print(f"\n  wrote {snap_path}  [{tag}]", file=sys.stderr)
    print(f"  latest -> {args.out_dir / 'latest.json'}", file=sys.stderr)
    for repo in D.REPOS:
        print(f"    {repo}: master @ {model['repos'][repo]['provenance']['sha'][:7]}",
              file=sys.stderr)
    dark = [r for r in D.REPOS if model["repos"][r]["issues"]["tracker"] != "ok"]
    if dark:
        print(f"\n  ISSUES UNREACHABLE for: {', '.join(dark)} — open-issue state is UNKNOWN, "
              f"not zero; the diff will report 'not compared'.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StatusGateError as exc:
        print(f"\nHALT: {exc}", file=sys.stderr)
        sys.exit(1)
