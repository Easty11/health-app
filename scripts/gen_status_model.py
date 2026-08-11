#!/usr/bin/env python3
"""gen_status_model.py — append-only MACHINE status model across both repos.

Reads the governance stores of health-app and health-connect-app at **master** (via
raw.githubusercontent, pinned to a resolved SHA for provenance) and emits a JSON status
model: per-repo state-vocabulary tallies for questions and branch rows, decision-sequence
integrity, and an off-vocabulary tally that is reported, never dropped.

Distinct from `gen_governance_view.py` by design (DECISIONS_LOG #192): that renders a
human-readable digest; this produces diffable machine JSON that a cross-repo snapshot ages
over. The two share ONE thing — the dialect grammar — via `gov_dialects` (#191).

GATES — a status generator that under-reports silently is worse than none (#190). Before the
model is returned, three gates run; any failure HALTs with a non-zero exit and a stderr line
naming the store, and NOTHING partial is emitted:

  1. Count parity   — a crude, dialect-agnostic heading/row count (computed by an independent
                      path from the structured parser) vs the parsed count, per store per
                      repo. Mismatch => HALT.
  2. Sequence       — decisions are append-only and gapless: highest number == parsed count.
  3. Extraction     — count parity is necessary but INSUFFICIENT. If a state field resolves
                      EMPTY across ALL parsed items of a store, the parser matched a schema
                      that is not there (the live `**State:**`/`**Status:**` bug, #190). HALT.

Off-vocabulary state tokens are tallied per field and surfaced under `drift`; a clean-gate
run with non-zero off-vocab is still a finding, never a pass-in-silence (Step 1: HCA carries
work-item states UNSTARTED/BLOCKED on question headings — accepted, tallied, flagged).

Usage:
    python scripts/gen_status_model.py --dry-run     # build + gate, print JSON, write nothing
    python scripts/gen_status_model.py --self-check   # exercise the gates on synthetic input
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import gov_dialects as D

RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{store}.md"

# Snapshots live OUTSIDE both repos (DECISIONS_LOG #192): a cross-repo view inside one repo
# recreates a two-master pattern. Default is Projects/_status — sibling to the repos, where
# repo = Projects/health-app, so parents[2] is Projects. Overridable with --out-dir.
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "_status"

# Store keys -> the store file basename.
STORE_FILE = {
    "decisions": "DECISIONS_LOG",
    "questions": "OPEN_QUESTIONS",
    "branches": "BRANCHES",
}

# A store smaller than this is a fetch failure, not a small store (mirrors gen_governance_view).
MIN_STORE_BYTES = 300

SCHEMA_VERSION = 1


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
    if store_key == "questions":
        return sum(1 for ln in lines if D.QUESTION_HEADING.match(ln))
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


def _tally_stateful(headings: list[tuple[int, str, str]], lines: list[str],
                    vocab: tuple[str, ...]) -> dict:
    """Shared tally for heading-driven stateful stores (questions). `headings` is
    [(line_index, ident, heading_remainder), ...] — `ident` names the offender when state is
    missing (#209 gate: questions carry mandatory state, so a missing one is named). Returns
    count, by_state, off_vocab, missing_state, missing_ids."""
    by_state: Counter = Counter()
    off_vocab: Counter = Counter()
    missing_ids: list[str] = []
    for idx, (line_i, ident, rest) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        raw = D.entry_state(lines, line_i, rest, end)
        if not raw:
            missing_ids.append(ident)
            continue
        tok, off = D.classify(raw, vocab)
        if tok is None:
            missing_ids.append(ident)
        elif off:
            off_vocab[tok] += 1
        else:
            by_state[tok] += 1
    return {
        "count": len(headings),
        "by_state": dict(sorted(by_state.items())),
        "off_vocab": dict(sorted(off_vocab.items())),
        "missing_state": len(missing_ids),
        "missing_ids": missing_ids,
    }


def parse_questions(text: str, repo: str) -> dict:
    lines = text.splitlines()
    headings = [(i, f"Q{m.group(1)}", m.group(2)) for i, ln in enumerate(lines)
                if (m := D.QUESTION_HEADING.match(ln))]
    # Per-repo vocab (#191 unify): UNSTARTED is a valid question state for HCA, off-vocab drift
    # for health-app. Classified against the repo's own tuple, never the shared one.
    return _tally_stateful(headings, lines, D.question_states(repo))


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
    "questions": parse_questions,
    "branches": parse_branches,
}


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
    """Questions and branches carry MANDATORY state — unlike decisions, whose `**Status:**` is
    optional by convention (#209). Any question or branch missing its state is a store defect, so
    HALT on ANY non-zero missing (no threshold) and NAME the offenders. This is stricter than
    `gate_extraction_nonempty`, which only fires when ALL N are empty (the #190 schema-mismatch
    class); a single stateless item slips past that gate but not this one."""
    missing_ids = parsed.get("missing_ids", [])
    if missing_ids:
        ids = ", ".join(missing_ids)
        raise StatusGateError(
            f"MISSING STATE [{repo}/{STORE_FILE[store_key]}.md]: {len(missing_ids)} item(s) "
            f"declare no state: {ids}. Questions and branches must each carry a state (#209); HALT."
        )


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------

def build_repo(repo: str, sha: str, texts: dict) -> dict:
    out = {"provenance": {"ref": "master", "sha": sha}}
    for store_key in ("decisions", "questions", "branches"):
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
        for store_key in ("questions", "branches"):
            ov = rd[store_key]["off_vocab"]
            if ov:
                drift.append({"repo": repo, "store": store_key, "off_vocab": ov})
    return drift


def build_model(generated_utc: str) -> dict:
    repos: dict = {}
    for repo in D.REPOS:
        sha = resolve_master_sha(repo)
        print(f"  {repo}: master @ {sha[:7]}", file=sys.stderr)
        texts = {k: fetch(repo, sha, STORE_FILE[k]) for k in STORE_FILE}
        repos[repo] = build_repo(repo, sha, texts)
        for k in ("decisions", "questions", "branches"):
            p = repos[repo][k]
            print(f"    {STORE_FILE[k]+'.md':<18} {p['count']:>4} items", file=sys.stderr)
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
    expect_halt("count parity", lambda: gate_count_parity("r", "questions", 89, 88))
    # 2. sequence gap
    expect_halt("sequence gap",
                lambda: gate_sequence("r", {"count": 88, "max": 89, "min": 1, "gapless": False}))
    # 3. extraction empty across all N (the **State:** class)
    expect_halt("extraction empty", lambda: gate_extraction_nonempty(
        "r", "questions", {"count": 89, "by_state": {}, "off_vocab": {}, "missing_state": 89}))
    # off-vocab is NOT a halt — it is tallied. (Example token is genuinely off-vocab: UNSTARTED
    # is now an IN-vocab question state, so it would no longer illustrate the off-vocab path.)
    ov = {"count": 2, "by_state": {"OPEN": 1}, "off_vocab": {"PARKED": 1}, "missing_state": 0}
    gate_extraction_nonempty("r", "questions", ov)  # must not raise
    print("  ok   off-vocab tallied, not halted", file=sys.stderr)

    # 4. any PARTIAL missing state (#209) — halts and names the offender, no threshold.
    expect_halt("missing state (partial)", lambda: gate_no_missing_state(
        "r", "questions", {"count": 3, "by_state": {"OPEN": 2}, "off_vocab": {},
                           "missing_state": 1, "missing_ids": ["Q42"]}))
    gate_no_missing_state("r", "branches", {"count": 2, "by_state": {"DONE": 2}, "off_vocab": {},
                                            "missing_state": 0, "missing_ids": []})  # clean: no raise
    print("  ok   no-missing-state gate (partial halts + names ids; clean passes)", file=sys.stderr)

    # grammar positives for the reader-channel changes (no network).
    # G6 — per-repo question vocab: UNSTARTED is DRIFT on a health-app question but CLEAN on an
    # HCA question. BOTH directions asserted; the health-app direction is exactly the drift
    # signal a shared-tuple edit would have silenced.
    assert D.classify("UNSTARTED", D.question_states("health-app")) == ("UNSTARTED", True), \
        "UNSTARTED on a health-app question must classify off-vocab (drift)"
    assert D.classify("UNSTARTED", D.question_states("health-connect-app")) == ("UNSTARTED", False), \
        "UNSTARTED on an HCA question must classify clean (in-vocab)"
    assert D.classify("active", D.question_states("health-connect-app")) == (None, False), \
        "lowercase 'active' is not a caps token — never a question state, either repo"
    assert D.decision_inline_state("Title  ·  active  ·  supersedes #10") == "active", \
        "decision inline reader must SCAN segments, not take the last"
    assert D.decision_inline_state("Title  ·  held") == "held", "held is an enumerated inline token"
    assert D.decision_inline_state("### 45. health-app style, no middot") == "", \
        "no '·' -> no lowercase inline decision state (health-app decisions use **Status:**)"
    print("  ok   G6 per-repo vocab (UNSTARTED drift@health-app / clean@HCA); decision channel scans",
          file=sys.stderr)
    print("self-check: all gate positives fired", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="build + gate, print the model JSON to stdout, write no snapshot")
    ap.add_argument("--self-check", action="store_true",
                    help="exercise the gates on synthetic input and exit")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                    help=f"snapshot root (default: {DEFAULT_OUT_DIR})")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model = build_model(generated)

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
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StatusGateError as exc:
        print(f"\nHALT: {exc}", file=sys.stderr)
        sys.exit(1)
