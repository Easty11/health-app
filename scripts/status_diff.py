#!/usr/bin/env python3
"""status_diff.py — cross-repo governance diff + invokable status report (task-5 Steps 2-3).

Compares two governance snapshots (or the current stores vs the last snapshot) across BOTH
repos' stores, emitting opened / closed / changed / renumbered per store. A MANUAL command —
no schedule, no daemon (Step 4 / S4 is gated).

Design contracts:

* RENUMBER SURVIVAL. Number-at-merge renumbers questions when branches land (Q28 -> Q50). Item
  identity is therefore a CONTENT FINGERPRINT (normalised title), never the number, for
  questions. A pure renumber keeps its fingerprint -> reported as `renumbered`, not close+open.
  Where the fingerprint does NOT survive (title edited too), the tool reports the closed and the
  opened SEPARATELY plus "possible renumber — verify by hand"; it never fuzzy-matches titles.
  Decisions key on their number (append-only, never renumbered on master); branches key on name.

* CROSS-REPO EVIDENCE (#184/#185). Each repo's stores are read FROM THAT REPO at the relevant
  ref (`git show <sha>:FILE`). No claim about repo B ever originates from repo A's files.

* SNAPSHOTS ARE READ-ONLY HERE. The diff never writes a snapshot and never writes any store.
  (`gen_status_model.py` is the writer.) The baseline side is reconstructed from the snapshot's
  recorded per-repo SHA, so the aggregate-only snapshot schema needs no per-item extension.
"""
from __future__ import annotations

import argparse
import hashlib
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
STORE_FILE = {"decisions": "DECISIONS_LOG", "questions": "OPEN_QUESTIONS", "branches": "BRANCHES"}


@dataclass(frozen=True)
class Item:
    store: str
    ident: str        # display id: "#207" / "Q88" / branch name
    key: str          # identity key: number (decisions) / fingerprint (questions) / name (branches)
    title: str
    state: str


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _fp(s: str) -> str:
    return hashlib.sha256(_norm(s).encode("utf-8")).hexdigest()[:16]


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

    elif store_key == "questions":
        heads = [(i, int(m.group(1)), m.group(2))
                 for i, ln in enumerate(lines) if (m := D.QUESTION_HEADING.match(ln))]
        vocab = D.question_states(repo)
        for idx, (line_i, qn, rest) in enumerate(heads):
            end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
            raw = D.entry_state(lines, line_i, rest, end)
            tok, _off = D.classify(raw, vocab)
            # identity survives renumber: fingerprint the TITLE only (number + state excluded)
            items.append(Item("questions", f"Q{qn}", _fp(rest), rest.strip(), tok or "—"))

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
    opened, closed, changed, renumbered = [], [], [], []

    for k, it in cur_by.items():
        if k not in base_by:
            opened.append({"id": it.ident, "title": it.title, "state": it.state})
        else:
            b = base_by[k]
            if it.ident != b.ident:  # same fingerprint, different number => renumber (questions)
                renumbered.append({"from": b.ident, "to": it.ident, "title": it.title,
                                   "state": it.state,
                                   "state_change": None if b.state == it.state else [b.state, it.state]})
            elif b.state != it.state:
                changed.append({"id": it.ident, "title": it.title, "from": b.state, "to": it.state})
    for k, b in base_by.items():
        if k not in cur_by:
            closed.append({"id": b.ident, "title": b.title, "state": b.state})

    result = {"opened": opened, "closed": closed, "changed": changed, "renumbered": renumbered}
    # Where identity did NOT survive on BOTH sides, a renumber-with-edit is indistinguishable from
    # a real close+open. Report it, never pair it (the brief's explicit contract).
    if store_key == "questions" and opened and closed:
        result["renumber_suspects"] = (
            f"{len(closed)} closed + {len(opened)} opened in questions — possible renumber(s) "
            f"with an edited title (fingerprint did not survive). VERIFY BY HAND; not auto-paired."
        )
    return result


def diff_repo(repo: str, base_ref: str | None, cur_ref: str | None) -> dict:
    out = {}
    for store_key in ("decisions", "questions", "branches"):
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
    if d.get("renumbered"):
        bits.append(f"№{len(d['renumbered'])} renumbered")
    out = [f"    {name}: " + ", ".join(bits)]
    for r in d.get("renumbered", []):
        sc = f" (state {r['state_change'][0]}→{r['state_change'][1]})" if r["state_change"] else ""
        out.append(f"        renumber {r['from']} → {r['to']}: {r['title'][:60]}{sc}")
    if d.get("renumber_suspects"):
        out.append(f"        ⚠ {d['renumber_suspects']}")
    return out


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
        for store_key in ("decisions", "questions", "branches"):
            lines += _fmt_store_delta(STORE_FILE[store_key], d[store_key])
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
