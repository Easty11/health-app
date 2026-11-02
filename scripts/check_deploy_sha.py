#!/usr/bin/env python3
"""Post-deploy check: does each Railway service serve the code the merge put on master?

THE RULE (#433, made a check). Each service reports the commit it was built from
(`GET /version` on the backend, `GET /version.json` on the frontend: Railway's own
`RAILWAY_GIT_COMMIT_SHA`). For the merge under test, the service passes when the commit it serves
CONTAINS the last commit that touched the service's folder:

    floor  = the last commit touching <service folder> at the merge SHA
    served = the commit the live service reports
    pass   : floor is an ancestor of (or equal to) served, and served is on master

Not "served == the merge SHA". Railway watch paths (`/backend/**`, `/frontend/**`) deploy a service
only when its own folder changed, so a docs-only merge records SKIPPED on both and the live commit
legitimately stays an earlier one (#433), and a service can deploy on a merge that did not touch its
folder when the span from its last-deployed commit does (#442 (d)). An "equals the merge SHA" check
would fail on every governance merge and teach everyone to ignore it. This rule is equivalent to
"equals the merge SHA" exactly when the merge touched that folder.

PENDING vs FAIL. A served commit older than the floor means the deploy has not landed yet: poll.
A service that reports no commit, a malformed one, or a commit that is not on master is a FAIL at
once (no amount of waiting fixes it): it means the version door itself is broken, which is what this
check exists to notice.

Exit 0 = both services pass. Exit 1 = a service failed or never caught up within --timeout.
Exit 2 = usage. Stdlib only, so it runs on a bare runner. Usage:

    python scripts/check_deploy_sha.py --sha <merge sha> \\
        --backend-url https://<backend>/version --frontend-url https://<frontend>/version.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SERVICES = (("backend", "backend"), ("frontend", "frontend"))   # (name, folder)


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def last_commit_touching(repo: str, sha: str, folder: str) -> str:
    """The last commit at `sha` that touched `folder/` ('' if none ever did)."""
    r = git(repo, "log", "-1", "--format=%H", sha, "--", f"{folder}/")
    if r.returncode != 0:
        raise RuntimeError(f"git log failed for {folder}/ at {sha}: {r.stderr.strip()}")
    return r.stdout.strip()


def is_ancestor(repo: str, ancestor: str, descendant: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def knows(repo: str, sha: str) -> bool:
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def fetch_served(url: str, timeout: float = 15.0) -> tuple[str | None, str]:
    """(commit or None, note). A transport error or a non-JSON body is (None, why): the caller treats
    it as 'not up yet' while time remains, never as a pass."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"unreachable: {exc}"
    try:
        data = json.loads(body)
    except ValueError:
        return None, "not JSON (the version door is missing: an SPA fallback or an error page answered)"
    if not isinstance(data, dict):
        return None, "JSON, but not an object"
    commit = data.get("commit")
    return (commit if isinstance(commit, str) and commit else None), ("ok" if commit else "reports no commit")


def judge(repo: str, sha: str, folder: str, served: str | None, note: str) -> tuple[str, str]:
    """('pass' | 'pending' | 'fail', reason). Pure over the repo and what the service said."""
    floor = last_commit_touching(repo, sha, folder)
    if served is None:
        # Reachability / body problems may clear while a deploy is switching over; the loop turns this
        # into a fail at the deadline, with the last note.
        return "pending", f"{note}"
    if not SHA_RE.match(served):
        return "fail", f"serves {served!r}, which is not a full commit SHA"
    if not knows(repo, served):
        git(repo, "fetch", "--quiet", "origin", "master")          # a newer merge may have landed since checkout
        if not knows(repo, served):
            return "fail", f"serves {served[:12]}, a commit this repository does not have (not from master)"
    on_master = is_ancestor(repo, served, "origin/master") or is_ancestor(repo, served, sha)
    if not on_master:
        return "fail", f"serves {served[:12]}, which is not on master"
    if not floor:
        return "pass", f"serves {served[:12]} (the folder has never changed)"
    if is_ancestor(repo, floor, served):
        why = "serves the merge commit" if served == sha else (
            f"serves {served[:12]}, which contains {folder}/'s last change {floor[:12]}")
        return "pass", why
    return "pending", f"serves {served[:12]}, older than {folder}/'s last change {floor[:12]}"


def run(repo: str, sha: str, urls: dict[str, str], *, timeout: float, interval: float,
        fetch=fetch_served, sleep=time.sleep, clock=time.monotonic) -> dict[str, dict[str, str]]:
    """Poll each service until it passes, fails, or the deadline. Returns {name: {verdict, reason, served}}."""
    deadline = clock() + timeout
    result: dict[str, dict[str, str]] = {}
    pending = dict.fromkeys(urls)
    while pending:
        for name in list(pending):
            folder = dict(SERVICES)[name]
            served, note = fetch(urls[name])
            verdict, reason = judge(repo, sha, folder, served, note)
            if verdict == "pending" and clock() >= deadline:
                verdict, reason = "fail", f"never caught up within {int(timeout)}s: {reason}"
            if verdict != "pending":
                result[name] = {"verdict": verdict, "reason": reason, "served": served or ""}
                del pending[name]
        if pending:
            sleep(interval)
    return result


def report(sha: str, result: dict[str, dict[str, str]]) -> str:
    rows = [f"merge commit: {sha}", ""]
    for name, r in result.items():
        rows.append(f"{r['verdict'].upper():5} {name}: {r['reason']}")
    return "\n".join(rows)


def main(argv: list[str] | None = None, **kw) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sha", required=True, help="the merge commit under test")
    p.add_argument("--backend-url", required=True)
    p.add_argument("--frontend-url", required=True)
    p.add_argument("--repo", default=".")
    p.add_argument("--timeout", type=float, default=900.0)
    p.add_argument("--interval", type=float, default=20.0)
    try:
        a = p.parse_args(argv)
    except SystemExit:
        return 2
    if not SHA_RE.match(a.sha):
        print(f"--sha must be a full 40-hex commit SHA, got {a.sha!r}")
        return 2
    result = run(a.repo, a.sha, {"backend": a.backend_url, "frontend": a.frontend_url},
                 timeout=a.timeout, interval=a.interval, **kw)
    text = report(a.sha, result)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Served commit check\n\n```\n" + text + "\n```\n")
    return 0 if all(r["verdict"] == "pass" for r in result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
