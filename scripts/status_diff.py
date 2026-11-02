#!/usr/bin/env python3
"""status_diff.py — cross-repo governance diff + invokable status report (task-5 Steps 2-3).

Compares two governance snapshots (or the current stores vs the last snapshot) across BOTH
repos' stores, emitting opened / closed / changed per store. A MANUAL command —
no schedule, no daemon (Step 4 / S4 is gated).

Design contracts:

* ITEM IDENTITY. Decisions key on their number (append-only, never renumbered on master);
  branches key on name. Neither repo has a questions store any more (both retired, DECISIONS_LOG
  #468 / health-connect-app #54 — questions are GitHub issues), so there is no questions diff and
  no renumber handling: the fingerprint identity that survived a question renumber is gone with it.

* CROSS-REPO EVIDENCE (#184/#185). Each repo's stores are read FROM THAT REPO at the relevant
  ref (`git show <sha>:FILE`). No claim about repo B ever originates from repo A's files.

* ISSUES (schema 2, DECISIONS_LOG #483). Open GitHub issues are not in either repo's tree, so they
  diff snapshot-to-snapshot, not ref-to-ref: `diff_issues` keys on the issue number and emits
  opened / closed / changed (title or labels) per repo under an `issues` store. A side whose
  tracker was not read (`tracker: "unreachable"`, or a schema-1 snapshot with no `issues` block
  at all) is NOT COMPARED — never an empty diff, never "all N closed" and never "all N opened".

* SNAPSHOTS ARE READ-ONLY HERE. The diff never writes a snapshot and never writes any store.
  (`gen_status_model.py` is the writer.) The baseline side is reconstructed from the snapshot's
  recorded per-repo SHA, so the aggregate-only snapshot schema needs no per-item extension.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import gen_status_model as M
import gov_dialects as D

REPO_ROOT = Path(__file__).resolve().parent.parent          # health-app
HCA_ROOT = REPO_ROOT.parent / "health-connect-app"
STATUS_DIR = REPO_ROOT.parent / "_status"
REPO_PATHS = {"health-app": REPO_ROOT, "health-connect-app": HCA_ROOT}
STORE_FILE = {"decisions": "DECISIONS_LOG", "branches": "BRANCHES"}


@dataclass(frozen=True)
class Item:
    store: str
    ident: str        # display id: "#207" / branch name
    key: str          # identity key: number (decisions) / name (branches)
    title: str
    state: str


# --------------------------------------------------------------------------------------
# Per-item extraction (reuses the #207 reader's grammar; state logic matches the model)
# --------------------------------------------------------------------------------------

def extract_items(store_key: str, text: str, repo: str) -> list[Item]:
    lines = text.splitlines()
    items: list[Item] = []

    if store_key == "decisions":
        heads = [(i, int(m.group(1)), m.group(2))
                 for i, ln in enumerate(lines) if (m := D.DECISION_HEADING.match(ln))]
        for idx, (line_i, num, rest) in enumerate(heads):
            end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
            raw = D.decision_state(lines, line_i, rest, end)
            tok = D.decision_inline_state(rest) or ("stated" if raw else "unstated")
            items.append(Item("decisions", f"#{num}", str(num), rest.strip(), tok))

    elif store_key == "branches":
        for ln in lines:
            if not D.is_table_data_row(ln):
                continue
            cells = D.table_cells(ln)
            name = cells[0] if cells else "?"
            tok, _off = D.classify(M._branch_status_cell(cells), D.WORK_ITEM_STATES)
            items.append(Item("branches", name, name, name, tok or "—"))

    return items


def read_store_at_ref(repo: str, ref: str | None, store_key: str) -> str | None:
    """The store text for `repo` at `ref` (a git SHA), read from that repo. `ref=None` reads the
    current working tree. Returns None when the ref/file is unavailable (degrade, never guess)."""
    path = REPO_PATHS[repo]
    fname = STORE_FILE[store_key] + ".md"
    if ref is None:
        f = path / fname
        return f.read_text(encoding="utf-8") if f.exists() else None
    try:
        out = subprocess.run(["git", "-C", str(path), "show", f"{ref}:{fname}"],
                             capture_output=True, text=True, encoding="utf-8", check=True)
        return out.stdout
    except subprocess.CalledProcessError:
        return None


# --------------------------------------------------------------------------------------
# Diff
# --------------------------------------------------------------------------------------

def diff_store(store_key: str, base: list[Item], cur: list[Item]) -> dict:
    base_by = {it.key: it for it in base}
    cur_by = {it.key: it for it in cur}
    opened, closed, changed = [], [], []

    for k, it in cur_by.items():
        if k not in base_by:
            opened.append({"id": it.ident, "title": it.title, "state": it.state})
        else:
            b = base_by[k]
            if b.state != it.state:
                changed.append({"id": it.ident, "title": it.title, "from": b.state, "to": it.state})
    for k, b in base_by.items():
        if k not in cur_by:
            closed.append({"id": b.ident, "title": b.title, "state": b.state})

    return {"opened": opened, "closed": closed, "changed": changed}


def diff_repo(repo: str, base_ref: str | None, cur_ref: str | None) -> dict:
    out = {}
    for store_key in STORE_FILE:
        b_txt = read_store_at_ref(repo, base_ref, store_key)
        c_txt = read_store_at_ref(repo, cur_ref, store_key)
        if b_txt is None or c_txt is None:
            out[store_key] = {"unavailable": f"store text missing at "
                              f"{'baseline' if b_txt is None else 'current'} ref"}
            continue
        base = extract_items(store_key, b_txt, repo)
        cur = extract_items(store_key, c_txt, repo)
        out[store_key] = diff_store(store_key, base, cur)
    return out


# --------------------------------------------------------------------------------------
# Issues diff  (snapshot-to-snapshot; DECISIONS_LOG #483)
# --------------------------------------------------------------------------------------

def _readable_issues(block) -> list[dict] | None:
    """The items of an `issues` block, or None when the tracker was not read. A missing block
    (a schema-1 snapshot) is treated exactly as `tracker: "unreachable"` — never as zero."""
    if isinstance(block, dict) and block.get("tracker") == "ok" and isinstance(block.get("items"), list):
        return block["items"]
    return None


def diff_issues(base_block, cur_block) -> dict:
    base, cur = _readable_issues(base_block), _readable_issues(cur_block)
    if base is None or cur is None:
        why = [f"{side}: " + ("no `issues` block (schema 1)" if blk is None else "tracker unreachable")
               for side, blk, items in (("baseline", base_block, base), ("current", cur_block, cur))
               if items is None]
        return {"not_compared": "; ".join(why) + " — open-issue state UNKNOWN, not zero"}
    base_by = {it["number"]: it for it in base}
    cur_by = {it["number"]: it for it in cur}
    opened = [{"id": f"GH#{n}", "title": it["title"], "labels": it["labels"]}
              for n, it in cur_by.items() if n not in base_by]
    closed = [{"id": f"GH#{n}", "title": it["title"], "labels": it["labels"]}
              for n, it in base_by.items() if n not in cur_by]
    changed = []
    for n, it in cur_by.items():
        b = base_by.get(n)
        if b is None:
            continue
        frm, to = {}, {}
        if b["title"] != it["title"]:
            frm["title"], to["title"] = b["title"], it["title"]
        if sorted(b["labels"]) != sorted(it["labels"]):
            frm["labels"], to["labels"] = sorted(b["labels"]), sorted(it["labels"])
        if to:   # same from/to shape as diff_store's changed entries; only the changed facets
            changed.append({"id": f"GH#{n}", "title": it["title"], "from": frm, "to": to})
    return {"opened": opened, "closed": closed, "changed": changed}


def diff_issues_snapshots(base_snap: dict | None, cur_snap: dict) -> dict:
    """Per repo `issues` diff between two snapshots. No baseline snapshot -> every repo is
    not compared (the first run has nothing to compare against)."""
    out = {}
    for repo, rd in cur_snap["repos"].items():
        if base_snap is None:
            out[repo] = {"not_compared": "no previous snapshot — baseline run"}
        else:
            base_block = base_snap.get("repos", {}).get(repo, {}).get("issues")
            out[repo] = diff_issues(base_block, rd.get("issues"))
    return out


def _snapshot_order(path: Path) -> tuple:
    """Chronological key for `snapshots/<stamp>[_N]_model.json`. A plain sort is wrong: the
    same-second collision suffix `_2` sorts BEFORE the unsuffixed file ('2' < 'm')."""
    m = re.match(r"^(.*?)(?:_(\d+))?_model\.json$", path.name)
    return (m.group(1), int(m.group(2) or 1)) if m else (path.name, 0)


def _previous_snapshot() -> dict | None:
    """The snapshot written before `latest.json`, or None when there is no predecessor."""
    snaps = sorted((STATUS_DIR / "snapshots").glob("*_model.json"), key=_snapshot_order)
    return json.loads(snaps[-2].read_text(encoding="utf-8")) if len(snaps) >= 2 else None


# --------------------------------------------------------------------------------------
# Unreferenced-rule listing (Step 3b) — the pruning signal D1's ruling depends on
# --------------------------------------------------------------------------------------

_RULE_LANGUAGE = re.compile(r"\b(never|always|must|every session|each session|supersedes|"
                            r"invariant|standing (test|rule)|no session)\b", re.I)


def unreferenced_rules(text: str) -> dict:
    """Rule candidates (decisions whose text carries standing-rule language) whose `#N` is cited
    NOWHERE later — not by a later decision, nor a commit message. The definition is stated in the
    report so the heuristic is legible, per the brief."""
    lines = text.splitlines()
    heads = [(i, int(m.group(1)), m.group(2))
             for i, ln in enumerate(lines) if (m := D.DECISION_HEADING.match(ln))]
    candidates = []
    for idx, (line_i, num, rest) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        body = "\n".join(lines[line_i:end])
        if _RULE_LANGUAGE.search(body):
            candidates.append((num, rest.strip()))

    # citations: `#N` anywhere in the store AFTER the entry's own block, or in any commit message.
    store_cites = set(int(n) for n in re.findall(r"#(\d+)\b", text))
    try:
        log = subprocess.run(["git", "-C", str(REPO_ROOT), "log", "--format=%s%n%b"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        commit_cites = set(int(n) for n in re.findall(r"#(\d+)\b", log))
    except subprocess.CalledProcessError:
        commit_cites = set()

    unref = []
    for num, title in candidates:
        # self-reference in its own block is not a citation; count only OTHER decisions' cites +
        # commits. A cheap proxy: a rule is "referenced" if its number appears more than once in
        # the store (its own heading counts once) OR in any commit message.
        store_hits = len(re.findall(rf"#{num}\b", text))
        referenced = store_hits > 1 or num in commit_cites
        if not referenced:
            unref.append({"id": f"#{num}", "title": title})
    return {"candidates": len(candidates), "unreferenced": unref}


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------

def _load_latest_snapshot() -> dict | None:
    f = STATUS_DIR / "latest.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _fmt_store_delta(name: str, d: dict) -> list[str]:
    if "unavailable" in d:
        return [f"    {name}: unavailable ({d['unavailable']})"]
    bits = [f"+{len(d['opened'])} opened", f"-{len(d['closed'])} closed",
            f"~{len(d['changed'])} changed"]
    return [f"    {name}: " + ", ".join(bits)]


def _fmt_issues_delta(repo: str, cur_block, d: dict) -> list[str]:
    now = (f"{cur_block['count']} open" if isinstance(cur_block, dict) and cur_block.get("tracker") == "ok"
           else "open count UNKNOWN (tracker not read)")
    if "not_compared" in d:
        return [f"    {repo}: issues {now}; NOT COMPARED ({d['not_compared']})"]
    lines = [f"    {repo}: issues {now}; +{len(d['opened'])} opened, -{len(d['closed'])} closed, "
             f"~{len(d['changed'])} changed"]
    for tag, key in (("opened", "opened"), ("closed", "closed")):
        for it in d[key]:
            lines.append(f"      {tag:<7} {it['id']}: {it['title'][:80]}")
    for it in d["changed"]:
        facets = "+".join(k for k in ("title", "labels") if k in it["to"])
        lines.append(f"      changed {it['id']} ({facets}): {it['title'][:80]}")
    return lines


def build_report() -> str:
    snap = _load_latest_snapshot()
    lines = ["# Governance status report (manual run)", ""]
    if snap is None:
        return "\n".join(lines + ["No snapshot found at Projects/_status/ — run gen_status_model first."])

    lines.append(f"Baseline snapshot: {snap['generated_utc']}"
                 + ("  (BASELINE — first snapshot)" if snap.get("baseline") else ""))
    lines.append("")

    # (a) Cross-repo delta since last snapshot: current stores vs each repo's snapshot ref.
    lines.append("## (a) Delta since last snapshot")
    for repo, r in snap["repos"].items():
        base_ref = r["provenance"]["sha"]
        lines.append(f"  {repo}  (baseline {base_ref[:7]} → current working tree)")
        d = diff_repo(repo, base_ref, None)
        for store_key in STORE_FILE:
            lines += _fmt_store_delta(STORE_FILE[store_key], d[store_key])
    lines.append("")

    # (a2) Issues since the previous snapshot — snapshot-to-snapshot (the tracker is not in a tree).
    lines.append("## (a2) Open issues since the previous snapshot")
    for repo, d in diff_issues_snapshots(_previous_snapshot(), snap).items():
        lines += _fmt_issues_delta(repo, snap["repos"][repo].get("issues"), d)
    lines.append("")

    # (b) Unreferenced-rule listing — health-app only (senior store; #193 read HCA read-only).
    lines.append("## (b) Unreferenced rule candidates (health-app)")
    lines.append("  Definition: a decision whose text carries standing-rule language "
                 "(never/always/must/supersedes/invariant/standing test…) and whose `#N` is cited")
    lines.append("  nowhere else in the store nor in any commit message. This is the pruning "
                 "signal (#208 mint filter); referenced ≠ pruning candidate.")
    ha_dec = read_store_at_ref("health-app", None, "decisions")
    ur = unreferenced_rules(ha_dec or "")
    lines.append(f"  {ur['candidates']} rule candidate(s); {len(ur['unreferenced'])} unreferenced:")
    for u in ur["unreferenced"]:
        lines.append(f"    {u['id']}: {u['title'][:80]}")
    lines.append("")

    # (c) Baseline provenance caveat — mandatory on the first diff, in the body (not a comment).
    if snap.get("baseline"):
        lines += [
            "## (c) Baseline provenance",
            "This is the FIRST snapshot; it has no predecessor, so every item in (a) reads as",
            "'+movement since baseline'. The baseline snapshot itself was seeded DURING the",
            "status-tooling lane, so its +movement INCLUDES that lane's own governance output",
            "(the status decisions and this tooling). Read the first report's growth as",
            "'everything since the baseline ref', not 'new since a prior steady state'.",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-check", action="store_true",
                    help="run the gate suite (gen_status_model) and print PASS/FAIL loudly")
    args = ap.parse_args()

    try:                                    # em-dashes in store titles; force utf-8 on Windows
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if args.self_check:
        try:
            M.self_check()
        except SystemExit as e:
            print(f"SELF-CHECK: FAIL — {e}", file=sys.stderr)
            return 1
        print("SELF-CHECK: PASS — all gate positives fired")
        return 0

    print(build_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
