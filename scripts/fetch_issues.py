#!/usr/bin/env python3
"""fetch_issues.py — fetch each repo's OPEN issues from the GitHub API into a raw payload file.

One transport of two for the status model's issues read (DECISIONS_LOG #483; the other is the
model's own live fetch). The status model OWNS the issue grammar (`gen_status_model.
normalise_issues`); this script normalises NOTHING. It writes the raw API arrays, keyed by repo
name, for `gen_status_model.py --issues-json PATH`:

    {"health-app": [<raw issue>, ...], "health-connect-app": [...]}

so the same function reads both transports (one grammar, two transports).

STDLIB ONLY (urllib) — no `gh`, no `requests` — so it runs as-is in a device shell with only
python3: `python3 fetch_issues.py --out <path>`. Run from a scratch directory, it falls back
to a hardcoded owner and repo list; run from inside the clone it takes them from
`gov_dialects.OWNER` and `status_diff.REPO_PATHS`.

A repo whose fetch fails (HTTP error, network error, malformed body, unfollowable pagination) is
LEFT OUT of the file and the exit code is 1; the model reads a missing repo as tracker
"unreachable", never as zero. A repo is written only after EVERY page was read: a truncated
list is not written as if complete.

The API is read unauthenticated (public repos, 60 requests/hour per IP — a run costs two).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.github.com"      # module-level so a transport test can point it at a local server
PER_PAGE = 100
MAX_PAGES = 50                            # 5000 issues: a safety stop that RAISES, never truncates
TIMEOUT_S = 30

FALLBACK_OWNER = "Easty11"
FALLBACK_REPOS = ("health-app", "health-connect-app")

_NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


class FetchError(RuntimeError):
    """A repo's open issues could not be read completely. Never degrade to a partial list."""


def owner_and_repos() -> tuple[str, tuple[str, ...], str]:
    """(owner, repos, where-they-came-from). Imported LAZILY: at module top, running this file as a
    script would import status_diff -> gen_status_model -> this module a second time, mid-import.
    Inside the clone the shared names win; standalone (a scratch dir on the device) the hardcoded
    fallback applies. Only ImportError falls back — a real error in the clone surfaces."""
    try:
        import gov_dialects
        import status_diff
    except ImportError:
        return FALLBACK_OWNER, FALLBACK_REPOS, "fallback (standalone)"
    return gov_dialects.OWNER, tuple(status_diff.REPO_PATHS), "gov_dialects.OWNER / status_diff.REPO_PATHS"


def fetch_open_issues_raw(owner: str, repo: str) -> tuple[int, list]:
    """GET /repos/{owner}/{repo}/issues?state=open&per_page=100, following `Link: rel="next"` to
    the end. Returns (last HTTP status, the concatenated raw items — pull requests included; the
    model's normaliser excludes them). Raises FetchError on anything but a complete read."""
    url = f"{API_BASE}/repos/{owner}/{repo}/issues?state=open&per_page={PER_PAGE}"
    items: list = []
    status = 0
    for _page in range(MAX_PAGES):
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "health-app-status-model",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                link = resp.headers.get("Link") or ""
        except urllib.error.HTTPError as exc:
            raise FetchError(f"{owner}/{repo}: HTTP {exc.code} from {url}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise FetchError(f"{owner}/{repo}: {type(exc).__name__}: {exc}") from exc
        if status != 200:
            raise FetchError(f"{owner}/{repo}: HTTP {status} from {url}")
        try:
            page = json.loads(body)
        except ValueError as exc:
            raise FetchError(f"{owner}/{repo}: response is not JSON ({exc})") from exc
        if not isinstance(page, list):
            raise FetchError(f"{owner}/{repo}: expected a JSON array, got {type(page).__name__}")
        items.extend(page)
        m = _NEXT_LINK.search(link)
        if not m:
            return status, items
        url = m.group(1)
    raise FetchError(f"{owner}/{repo}: still paginating after {MAX_PAGES} pages — refusing to "
                     f"truncate; raise MAX_PAGES deliberately if this is real")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path,
                    help="where to write the raw payload file (scratch, not derived state)")
    args = ap.parse_args(argv)

    owner, repos, source = owner_and_repos()
    print(f"  owner/repos from {source}: {owner} {list(repos)}", file=sys.stderr)

    payload: dict = {}
    failed: list[str] = []
    for repo in repos:
        try:
            status, items = fetch_open_issues_raw(owner, repo)
        except FetchError as exc:
            print(f"  FAIL {repo}: {exc}", file=sys.stderr)
            failed.append(repo)
            continue
        payload[repo] = items
        print(f"  ok   {repo}: HTTP {status}, {len(items)} item(s) (pull requests included)",
              file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
    print(f"  wrote {args.out}", file=sys.stderr)
    if failed:
        print(f"  EXIT 1: {len(failed)} repo(s) left out of the file: {', '.join(failed)} "
              f"(the model reads a missing repo as 'unreachable', never zero)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
