#!/usr/bin/env python3
"""render_status.py — the PRESENTATION layer for the cross-repo governance status.

Owns nothing but rendering. The model and the diff belong to health-app's own
tooling (`gen_status_model.py`, `status_diff.py`, `gov_dialects.py`, DECISIONS
#190-#193); this imports them and calls their functions, so there is exactly ONE
store grammar in existence. Never re-parse a governance store here — a second
parser is the two-master pattern the whole loop exists to kill.

CONTRACT NOTE (2026-11-02): the questions store is RETIRED in both repos
(DECISIONS #468 / health-connect-app #54) — open questions are GitHub issues.
Since DECISIONS #483 (schema 2) the MODEL owns the tracker read — live, or from a
`--issues-json` payload that health-app's `scripts/fetch_issues.py` wrote wherever
api.github.com is reachable — and this renderer only reshapes the model's `issues`
block. Ageing/fruit come from the BRANCHES work-item rows via health-app's own
grammar. No store is parsed here, and nothing is fetched here.

Adds three things that layer has no opinion on, all read-only:

  * AGEING      — first-seen date per open branch row, by replaying git history
                  with the SAME extraction status_diff uses.
  * FRUIT       — items that are cheap to close: an OWED row whose outstanding
                  action is one named command, or a row whose stated blocker has
                  since cleared.
  * HTML        — the dashboard the persisted Cowork artifact renders.

Usage:
    python3 render_status.py --scripts-dir /path/to/health-app/scripts \\
        --out dev-status.html [--generated "YYYY-MM-DD HH:MM TZ"] [--no-ageing]
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ── Fruit heuristics ────────────────────────────────────────────────────────
# Deliberately conservative: a false "this is easy" wastes a trip to the machine,
# which is exactly the cost the section exists to avoid.
ONE_COMMAND = re.compile(
    r"outstanding[:\s]|owed[:\s]|one (?:postgres |railway |single )?(?:query|command|check|run|read)\b"
    r"|a single (?:query|command|check|read)\b|closes on\b|loop closes\b", re.I)
CLEARED = re.compile(
    r"\bCLEARED\b|no longer (?:blocked|gated|blocks)|gate lifted|unblocked\b"
    r"|precondition (?:has|is) (?:cleared|met)|blocker (?:has )?(?:cleared|gone)", re.I)
CMD_HINT = re.compile(r"`([^`\n]{8,120})`")
# A bare identifier is not an action. Prefer a backticked string that reads like
# something you could actually run, else show nothing rather than a misleading hint.
CMD_LIKE = re.compile(r"\s|SELECT |select |python|git |railway|npm |\.py\b|/|--|\w\(", re.I)


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)


def compute_ageing(SD, repo_paths, store_key="branches"):
    """First-seen date per item key, replayed forward through git history, using
    status_diff's OWN extract_items — identity matches the diff's rule exactly."""
    out = {}
    fname = {"decisions": "DECISIONS_LOG.md", "branches": "BRANCHES.md"}[store_key]
    for repo, root in repo_paths.items():
        seen = {}
        log = _run(["git", "log", "--reverse", "--format=%H %ad", "--date=short",
                    "--", fname], root)
        if log.returncode != 0:
            continue
        for line in log.stdout.splitlines():
            if not line.strip():
                continue
            sha, _, date = line.partition(" ")
            blob = _run(["git", "show", f"{sha}:{fname}"], root)
            if blob.returncode != 0:
                continue
            try:
                items = SD.extract_items(store_key, blob.stdout, repo)
            except Exception:
                continue
            for it in items:
                if it.key not in seen:
                    seen[it.key] = date
        out[repo] = seen
    return out


def classify_fruit(items_with_body):
    """Return (one_command, gate_cleared) lists. Body text drives both."""
    one_cmd, cleared = [], []
    for rec in items_with_body:
        body, state = rec.get("body", ""), (rec.get("state") or "").upper()
        if state == "OWED" and ONE_COMMAND.search(body):
            rec = dict(rec)
            hunt = rec.get("owed_cell") or body
            cands = [c.strip() for c in CMD_HINT.findall(hunt)]
            cands = [c for c in cands if CMD_LIKE.search(c)]
            rec["hint"] = max(cands, key=len) if cands else None
            one_cmd.append(rec)
        if CLEARED.search(body) and state in ("OWED", "BLOCKED", "UNSTARTED"):
            cleared.append(rec)
    return one_cmd, cleared


_MD_NOISE = re.compile(r"\*\*|`")


def branch_bodies(D, M, SD, repo, text):
    """Pair each BRANCHES work-item row with its raw row text, using the repo's
    own grammar (is_table_data_row / table_cells / _branch_status_cell / classify
    all belong to health-app's tooling — nothing is re-parsed here)."""
    recs = []
    for ln in text.splitlines():
        if not D.is_table_data_row(ln):
            continue
        cells = D.table_cells(ln)
        name = cells[0] if cells else "?"
        tok, _off = D.classify(M._branch_status_cell(cells), D.WORK_ITEM_STATES)
        purpose = _MD_NOISE.sub("", cells[1]) if len(cells) > 1 else ""
        title = (purpose[:180] + "…") if len(purpose) > 180 else purpose
        owed_cell = cells[-1] if len(cells) >= 5 else ""
        m = re.match(r"`([^`]+)`", name)
        short = m.group(1) if m else _MD_NOISE.sub("", name).split()[0] if name.split() else name
        recs.append({"repo": repo, "id": short, "key": name,
                     "title": title or name, "state": tok or "—", "body": ln,
                     "owed_cell": owed_cell})
    return recs


def issues_from_model(model):
    """Open issues as the MODEL carries them (schema 2, DECISIONS #483): the model owns the
    tracker read — live `api.github.com` or a `--issues-json` payload fetched where the API is
    reachable — and this renderer only reshapes the block for display. A block whose tracker is
    `unreachable` (or an older schema with no block) is None: the page must SAY the tracker was
    not read, never render a silent zero. `count: null` in that block is deliberate."""
    out = {}
    for repo, rd in model["repos"].items():
        blk = rd.get("issues")
        if not (isinstance(blk, dict) and blk.get("tracker") == "ok"
                and isinstance(blk.get("items"), list)):
            out[repo] = None
            continue
        out[repo] = [{"repo": repo, "id": f"GH#{it['number']}", "title": it["title"],
                      "labels": list(it["labels"]), "created": it["created_at"],
                      "url": it["html_url"]} for it in blk["items"]]
    return out


# ── HTML ────────────────────────────────────────────────────────────────────
STATE_META = {
    "BLOCKED": ("critical", "⛔"), "OWED": ("warning", "⏳"), "OPEN": ("neutral", "○"),
    "UNSTARTED": ("neutral", "○"), "DONE": ("good", "✓"), "OFF-VOCAB": ("serious", "⚠"),
}
ORDER = ["BLOCKED", "OWED", "OPEN", "UNSTARTED", "OFF-VOCAB", "DONE"]


def esc(s):
    return html.escape(str(s if s is not None else ""))


def chip(state):
    cls, icon = STATE_META.get((state or "").upper(), ("neutral", "·"))
    return f'<span class="chip chip-{cls}"><span class="ic">{icon}</span>{esc(state)}</span>'


def days_since(d, today):
    try:
        return (today - datetime.date.fromisoformat(d)).days
    except Exception:
        return None


def bar(counts, title):
    total = sum(counts.get(s, 0) for s in ORDER)
    if not total:
        return ""
    segs, leg = [], []
    for s in ORDER:
        n = counts.get(s, 0)
        if not n:
            continue
        cls, icon = STATE_META[s]
        segs.append(f'<div class="seg seg-{cls}" style="flex:{n}" title="{s}: {n}">'
                    f'{n if n/total > .07 else ""}</div>')
        leg.append(f'<span class="lg"><span class="dot dot-{cls}"></span>{icon} {s} <b>{n}</b></span>')
    return (f'<div class="barblock"><div class="bartitle">{esc(title)} · {total}</div>'
            f'<div class="bar">{"".join(segs)}</div><div class="legend">{"".join(leg)}</div></div>')


def render(model, diff, fruit, issues, meta):
    today = meta["today"]
    repos = model["repos"]

    # ── header tiles ──
    tiles = []
    for name, r in repos.items():
        b = r["branches"]["by_state"]
        live_rows = sum(v for k, v in b.items() if k != "DONE")
        iss = issues.get(name)
        iss_bit = (f'{len(iss)} open issues' if iss is not None
                   else '<span class="warn">tracker unreachable</span>')
        tiles.append(f'''
      <div class="tile"><div class="k">{esc(name)}</div>
        <div class="v">#{esc(r["decisions"]["max"])}</div>
        <div class="s">{iss_bit} · {live_rows} live branch rows · {esc(r["provenance"]["sha"][:7])}</div></div>''')

    # ── contract-change callout ──
    retired = ('<div class="callout"><b>Questions store retired</b> (DECISIONS #468 / '
               'health-connect-app #54): open questions are now GitHub issues, listed below from '
               'the tracker. Earlier runs\' "live questions" tiles counted the retired store — '
               'their disappearance here is a contract change, not a mass closure.</div>')

    # ── since last run ──
    delta = retired
    if meta["baseline"]:
        delta += ('<div class="callout"><b>Baseline run — no comparison available.</b> '
                  'The only snapshot on record is the first one, so everything below reads as '
                  '"movement since baseline", never "new since a steady state". The next run '
                  'produces the first real delta.</div>')
    rows = []
    for repo, d in diff.items():
        for store, sd in d.items():
            if store in ("base_ref", "cur_ref") or "unavailable" in sd:
                continue
            if "not_compared" in sd:
                rows.append(f'<tr><td class="mono">{esc(repo)}</td><td>{esc(store)}</td>'
                            f'<td class="warn">NOT COMPARED — {esc(sd["not_compared"])}</td></tr>')
                continue
            o, c, ch = len(sd.get("opened", [])), len(sd.get("closed", [])), len(sd.get("changed", []))
            rn = len(sd.get("renumbered", []))
            if not (o or c or ch or rn):
                continue
            bits = []
            if o: bits.append(f'<span class="up">+{o} opened</span>')
            if c: bits.append(f'<span class="down">−{c} closed</span>')
            if ch: bits.append(f'{ch} changed')
            if rn: bits.append(f'{rn} renumbered')
            rows.append(f'<tr><td class="mono">{esc(repo)}</td><td>{esc(store)}</td>'
                        f'<td>{" · ".join(bits)}</td></tr>')
            if sd.get("renumber_suspects"):
                rows.append(f'<tr><td></td><td></td><td class="warn">⚠ '
                            f'{esc(sd["renumber_suspects"])}</td></tr>')
    delta += (f'<table class="t"><tr><th>Repo</th><th>Store</th><th>Movement</th></tr>'
              f'{"".join(rows)}</table>' if rows else '<div class="empty">no movement</div>')

    # closed / state-changed items, named
    closed_named = []
    for repo, d in diff.items():
        for store, sd in d.items():
            if store in ("base_ref", "cur_ref") or "unavailable" in sd or "not_compared" in sd:
                continue
            if store == "issues":
                for it in sd.get("closed", []):
                    closed_named.append(
                        f'<div class="row"><div class="rh"><span class="rid">{esc(it["id"])}</span>'
                        f'<span class="rt">{esc(it["title"][:160])}</span>'
                        + "".join(f'<span class="chip chip-neutral">{esc(l)}</span>' for l in it.get("labels", []))
                        + f'<span class="chip chip-good"><span class="ic">✓</span>closed</span>'
                        f'<span class="owner">{esc(repo)} · issues</span></div></div>')
                for it in sd.get("changed", []):
                    facets = ", ".join(sorted(it.get("to", {}).keys())) or "changed"
                    closed_named.append(
                        f'<div class="row"><div class="rh"><span class="rid">{esc(it["id"])}</span>'
                        f'<span class="rt">{esc(it["title"][:160])}</span>'
                        f'<span class="owner">{esc(facets)} changed · {esc(repo)} · issues</span></div></div>')
                continue
            for it in sd.get("closed", []):
                closed_named.append(
                    f'<div class="row"><div class="rh"><span class="rid">{esc(it["id"])}</span>'
                    f'<span class="rt">{esc(_MD_NOISE.sub("", it["title"])[:160])}</span>{chip(it.get("state"))}'
                    f'<span class="owner">{esc(repo)} · {esc(store)}</span></div></div>')
            for it in sd.get("changed", []):
                closed_named.append(
                    f'<div class="row"><div class="rh"><span class="rid">{esc(it["id"])}</span>'
                    f'<span class="rt">{esc(_MD_NOISE.sub("", it["title"])[:160])}</span>'
                    f'{chip(it.get("from"))}<span class="owner">→</span>{chip(it.get("to"))}'
                    f'<span class="owner">{esc(repo)} · {esc(store)}</span></div></div>')
    closed_html = ("".join(closed_named) if closed_named
                   else '<div class="empty">nothing closed or re-stated since the baseline</div>')

    # ── open issues (the questions successor) ──
    iss_blocks = []
    for name in repos:
        iss = issues.get(name)
        if iss is None:
            iss_blocks.append(f'<h3>{esc(name)}</h3><div class="warn">GitHub tracker '
                              f'unreachable at render time — open-question state UNKNOWN for this repo, not zero.</div>')
            continue
        if not iss:
            iss_blocks.append(f'<h3>{esc(name)} · 0</h3><div class="empty">no open issues</div>')
            continue
        for it in iss:
            it["age_days"] = days_since(it["created"], today)
        iss.sort(key=lambda r: r.get("age_days") or 0, reverse=True)
        rows_h = "".join(
            f'<div class="row"><div class="rh"><span class="rid">{esc(r["id"])}</span>'
            f'<span class="rt">{esc(r["title"])}</span>'
            + "".join(f'<span class="chip chip-neutral">{esc(l)}</span>' for l in r["labels"])
            + (f'<span class="age">{r["age_days"]}d</span>' if r.get("age_days") is not None else "")
            + f'<span class="owner">{esc(name)}</span></div></div>' for r in iss)
        iss_blocks.append(f'<h3>{esc(name)} · {len(iss)}</h3>{rows_h}')
    issues_html = "".join(iss_blocks)

    # ── fruit ──
    def fruit_rows(items):
        if not items:
            return '<div class="empty">none detected</div>'
        out = []
        for rec in sorted(items, key=lambda r: r.get("age_days") or 0, reverse=True):
            age = rec.get("age_days")
            age_html = (f'<span class="age">{age}d</span>' if age is not None else
                        '<span class="age unk">age unknown</span>')
            hint = (f'<div class="hint"><code>{esc(rec["hint"])}</code></div>'
                    if rec.get("hint") else "")
            out.append(f'<div class="row"><div class="rh"><span class="rid">{esc(rec["id"])}</span>'
                       f'<span class="rt">{esc(rec["title"])}</span>{chip(rec["state"])}{age_html}'
                       f'<span class="owner">{esc(rec["repo"])}</span></div>{hint}</div>')
        return "".join(out)

    # ── ageing ──
    aged = [r for r in fruit["all_open"] if r.get("age_days") is not None]
    aged.sort(key=lambda r: r["age_days"], reverse=True)
    oldest = aged[:12]
    age_html = "".join(
        f'<div class="row"><div class="rh"><span class="rid">{esc(r["id"])}</span>'
        f'<span class="rt">{esc(r["title"])}</span>{chip(r["state"])}'
        f'<span class="age">{r["age_days"]}d</span>'
        f'<span class="owner">{esc(r["repo"])}</span></div></div>' for r in oldest) \
        or '<div class="empty">no live branch rows with ageing data</div>'

    # ── drift ──
    drift_html = ""
    if model.get("drift"):
        items = "".join(
            f'<div class="row"><span class="rt">{esc(d["repo"])} · {esc(d["store"])} — '
            f'{esc(", ".join(f"{k}×{v}" for k, v in d["off_vocab"].items()))}</span></div>'
            for d in model["drift"])
        drift_html = (f'<div class="drift"><div class="dh">⚠ Vocabulary drift — tallied, not '
                      f'dropped</div>{items}<div class="dn">Reported by the model\'s own '
                      f'off-vocab tally. A clean gate with non-zero drift is still a finding.</div></div>')

    bars = "".join(bar(r["branches"]["by_state"], f"{n} · branch rows")
                   for n, r in repos.items())

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dev project status</title>
<style>
 :root{{color-scheme:light;--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;
  --muted:#898781;--grid:#e1e0d9;--ring:rgba(11,11,11,.10);--good:#0ca30c;--warning:#fab219;
  --critical:#d03b3b;--serious:#ec835a;--neutral:#898781;--goodtext:#006300;--accent:#2a78d6}}
 @media(prefers-color-scheme:dark){{:root{{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;
  --ink2:#c3c2b7;--grid:#2c2c2a;--ring:rgba(255,255,255,.10);--goodtext:#0ca30c;--accent:#3987e5}}}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--plane);color:var(--ink);padding:24px;
  font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
 h1{{font-size:20px;margin:0 0 2px}} h2{{font-size:16px;margin:0 0 12px}}
 h3{{font-size:12px;margin:16px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
 .sub{{color:var(--ink2);font-size:12.5px}} .note{{color:var(--muted);font-size:12px;margin-bottom:18px}}
 .card{{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:18px 20px;margin-bottom:16px}}
 .tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:16px}}
 .tile{{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:10px 12px}}
 .tile .k{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}}
 .tile .v{{font-size:24px;font-weight:600;margin:2px 0}} .tile .s{{font-size:12px;color:var(--ink2)}}
 .t{{border-collapse:collapse;width:100%;font-size:13px}}
 .t th{{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;
  letter-spacing:.05em;padding:4px 8px;border-bottom:1px solid var(--grid)}}
 .t td{{padding:5px 8px;border-bottom:1px solid var(--grid);vertical-align:top}}
 .mono{{font-variant-numeric:tabular-nums;font-weight:600}}
 .up{{color:var(--accent);font-weight:600}} .down{{color:var(--goodtext);font-weight:600}}
 .warn{{color:var(--serious)}}
 .row{{border-top:1px solid var(--grid);padding:7px 0}}
 .rh{{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}}
 .rid{{font-weight:600;font-size:12.5px;color:var(--ink2);font-variant-numeric:tabular-nums}}
 .rt{{flex:1;min-width:220px}} .owner{{font-size:11.5px;color:var(--muted)}}
 .age{{font-size:11.5px;font-weight:600;color:var(--serious);font-variant-numeric:tabular-nums}}
 .age.unk{{color:var(--muted);font-weight:400}}
 .hint{{margin-top:4px}} code{{font-size:12px;background:var(--plane);padding:1px 5px;
  border-radius:4px;border:1px solid var(--ring)}}
 .chip{{font-size:11px;font-weight:600;border-radius:99px;padding:1px 8px;border:1px solid;
  display:inline-flex;gap:4px;align-items:center;white-space:nowrap}} .ic{{font-size:10px}}
 .chip-critical{{color:var(--critical);border-color:var(--critical)}}
 .chip-warning{{color:var(--ink);border-color:var(--warning);
  background:color-mix(in srgb,var(--warning) 22%,var(--surface))}}
 .chip-serious{{color:var(--ink);border-color:var(--serious);
  background:color-mix(in srgb,var(--serious) 18%,var(--surface))}}
 .chip-good{{color:var(--goodtext);border-color:var(--good)}}
 .chip-neutral{{color:var(--ink2);border-color:var(--muted)}}
 .empty{{color:var(--muted);font-size:12.5px;padding:4px 0}}
 .callout{{border-left:3px solid var(--warning);padding:9px 13px;margin-bottom:12px;font-size:13px;
  background:color-mix(in srgb,var(--warning) 8%,var(--surface))}}
 .drift{{border:1px solid var(--serious);border-radius:8px;padding:9px 13px;margin-top:12px}}
 .dh{{font-weight:600;margin-bottom:4px}} .dn{{font-size:12px;color:var(--ink2);margin-top:6px}}
 .bars{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
 .bartitle{{font-size:12px;color:var(--ink2);margin-bottom:4px}}
 .bar{{display:flex;gap:2px;height:20px;border-radius:4px;overflow:hidden}}
 .seg{{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;
  color:var(--surface);min-width:4px}}
 .seg-critical{{background:var(--critical)}} .seg-warning{{background:var(--warning);color:#0b0b0b}}
 .seg-serious{{background:var(--serious);color:#0b0b0b}} .seg-good{{background:var(--good)}}
 .seg-neutral{{background:var(--neutral)}}
 .legend{{display:flex;gap:12px;flex-wrap:wrap;margin-top:5px;font-size:11.5px;color:var(--ink2)}}
 .lg{{display:inline-flex;gap:4px;align-items:center}}
 .dot{{width:8px;height:8px;border-radius:50%}}
 .dot-critical{{background:var(--critical)}} .dot-warning{{background:var(--warning)}}
 .dot-serious{{background:var(--serious)}} .dot-good{{background:var(--good)}}
 .dot-neutral{{background:var(--neutral)}}
 footer{{color:var(--muted);font-size:11.5px;margin-top:4px}}
</style></head><body>
<h1>Dev project status</h1>
<div class="sub">Derived from the governance stores at each repo's master. The model and diff come
from health-app's own tooling (#190–#193); this page only renders them. Open questions come from
the GitHub tracker, their canonical home since the store's retirement (#468).</div>
<div class="note">Generated {esc(meta['generated'])} · baseline snapshot {esc(meta['baseline_stamp'])}
· read-only projection, regenerated not edited.</div>

<div class="tiles">{"".join(tiles)}</div>

<div class="card"><h2>Since last run</h2>{delta}
  <h3>Closed / re-stated</h3>{closed_html}</div>

<div class="card"><h2>Open questions — GitHub issues</h2>
  <div class="sub" style="margin-bottom:10px">The tracker replaced the questions store
  (#468 / hca #54). Open issues, oldest first; the stale action abandons the untouched at 60 days.</div>
  {issues_html}</div>

<div class="card"><h2>Low-hanging fruit</h2>
  <div class="sub" style="margin-bottom:10px">Live BRANCHES rows cheap to close, ranked oldest
  first — the work most likely to have been forgotten precisely because it is nearly done.</div>
  <h3>One named action outstanding</h3>{fruit_rows(fruit['one_command'])}
  <h3>Stated blocker has since cleared</h3>{fruit_rows(fruit['cleared'])}</div>

<div class="card"><h2>Oldest live branch rows</h2>
  <div class="sub" style="margin-bottom:10px">Age is the row's first appearance in git history,
  extracted with the diff's own grammar — rewordings of a row do not reset the clock.</div>
  {age_html}</div>

<div class="card"><h2>Distribution</h2><div class="bars">{bars}</div>{drift_html}</div>

<footer>Work items: DONE · BLOCKED · OWED · UNSTARTED. Issues: typed by label
(fork / stamp / verify / watch / design / build / pinned). Model: gen_status_model.py ·
Diff: status_diff.py · Grammar: gov_dialects.py (health-app/scripts) · Issues: the model's schema-2 block (#483), live or --issues-json.</footer>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scripts-dir", required=True,
                    help="health-app/scripts — the single source of store grammar")
    ap.add_argument("--out", default="dev-status.html")
    ap.add_argument("--generated", default=None)
    ap.add_argument("--no-ageing", action="store_true",
                    help="skip the git replay (fast, but ages read 'unknown')")
    ap.add_argument("--json-out", default=None, help="also write the assembled data")
    ap.add_argument("--issues-json", default=None, metavar="PATH",
                    help="raw GitHub issues payload keyed by repo, from health-app's "
                         "scripts/fetch_issues.py run wherever api.github.com is reachable; "
                         "without it the model fetches live and degrades to 'unreachable'")
    args = ap.parse_args()

    sys.path.insert(0, os.path.abspath(args.scripts_dir))
    import gen_status_model as M
    import status_diff as SD
    import gov_dialects as D

    today = datetime.date.today()
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. MODEL — theirs, gates and all. A gate failure raises; we do not catch it.
    payload = M.load_issues_payload(Path(args.issues_json)) if args.issues_json else None
    model = M.build_model(now_utc, issues_payload=payload)

    # 2. DIFF — theirs.
    snap = SD._load_latest_snapshot()
    baseline = bool(snap and snap.get("baseline"))
    baseline_stamp = snap.get("generated_utc", "none") if snap else "none"
    diff = {}
    if snap:
        for repo in SD.REPO_PATHS:
            base_sha = snap.get("repos", {}).get(repo, {}).get("provenance", {}).get("sha")
            diff[repo] = SD.diff_repo(repo, base_sha, None)
        # issues diff snapshot-to-snapshot (schema 2); a side not read is "not compared", never 0
        for repo, idiff in SD.diff_issues_snapshots(snap, model).items():
            diff.setdefault(repo, {})["issues"] = idiff

    # 3. AGEING — ours, read-only, via the diff's own extractor.
    ageing = {} if args.no_ageing else compute_ageing(SD, SD.REPO_PATHS)

    # 4. FRUIT — ours, over live BRANCHES rows.
    all_open, one_cmd, cleared = [], [], []
    for repo in SD.REPO_PATHS:
        text = SD.read_store_at_ref(repo, None, "branches")
        if not text:
            continue
        recs = branch_bodies(D, M, SD, repo, text)
        for r in recs:
            first = ageing.get(repo, {}).get(r["key"])
            r["age_days"] = days_since(first, today) if first else None
        live = [r for r in recs if (r["state"] or "").upper() != "DONE"]
        all_open += live
        a, b = classify_fruit(live)
        one_cmd += a
        cleared += b

    # 5. ISSUES — the questions successor; read by the MODEL (#483), reshaped here only.
    issues = issues_from_model(model)

    fruit = {"one_command": one_cmd, "cleared": cleared, "all_open": all_open}
    meta = {"generated": args.generated or datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "today": today, "baseline": baseline, "baseline_stamp": baseline_stamp}

    page = render(model, diff, fruit, issues, meta)
    Path(args.out).write_text(page, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {"model": model, "diff": diff, "issues": issues, "fruit": {k: [
                {kk: vv for kk, vv in r.items() if kk != "body"} for r in v]
                for k, v in fruit.items()}}, indent=2, default=str), encoding="utf-8")

    iss_counts = {k: (len(v) if v is not None else "UNREACHABLE") for k, v in issues.items()}
    iss_src = f"--issues-json {args.issues_json}" if args.issues_json else "live fetch"
    print(f"Wrote {args.out} ({len(page):,} bytes)")
    print(f"  open issues {iss_counts} ({iss_src}) · live branch rows {len(all_open)} · "
          f"fruit: {len(one_cmd)} one-command, {len(cleared)} cleared · "
          f"ageing: {'off' if args.no_ageing else 'on'}")
    if baseline:
        print("  BASELINE run — diff renders as 'no comparison available'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
