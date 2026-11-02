"""The post-deploy SHA check (#433, made a check): `scripts/check_deploy_sha.py`.

THE RULE UNDER TEST. A service passes when the commit it serves CONTAINS the last commit that touched its
folder, not when it equals the merge SHA: a docs-only merge is SKIPPED on both services by design, so an
equality check would fail on every governance merge. It is equivalent to equality exactly when the merge
touched that folder. A served commit older than that is PENDING (the deploy has not landed) and a FAIL
at the deadline; a service that reports no commit, a malformed one, or a commit that is not on master is
a FAIL.

Built on real throwaway git repositories (ancestry is the whole logic), and the HTTP read is exercised at
the TRANSPORT layer against a local server: a JSON body, the SPA fallback page that answers when
`version.json` is missing (200 + HTML: the failure that would read as a pass), and an error.
"""
import http.server
import importlib.util
import os
import subprocess
import threading

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_deploy_sha", os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "check_deploy_sha.py"))
chk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(chk)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def _commit(repo, path, text="x"):
    f = repo / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"{text}\n{len(list(repo.rglob('*')))}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"touch {path}")
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "master")
    c1 = _commit(tmp_path, "backend/a.py")
    c1f = _commit(tmp_path, "frontend/a.js")
    c2 = _commit(tmp_path, "backend/b.py")          # the last backend change
    c3 = _commit(tmp_path, "docs/x.md")             # the merge under test: docs only
    return {"path": str(tmp_path), "c1": c1, "c1f": c1f, "c2": c2, "c3": c3}


# ── judge: the rule ───────────────────────────────────────────────────────────

def test_a_docs_only_merge_passes_when_each_service_serves_its_own_last_change(repo):
    assert chk.judge(repo["path"], repo["c3"], "backend", repo["c2"], "ok")[0] == "pass"
    assert chk.judge(repo["path"], repo["c3"], "frontend", repo["c1f"], "ok")[0] == "pass"


def test_serving_the_merge_commit_itself_passes_and_says_so(repo):
    v, why = chk.judge(repo["path"], repo["c3"], "backend", repo["c3"], "ok")
    assert (v, why) == ("pass", "serves the merge commit")


def test_a_service_serving_a_commit_before_its_last_change_is_pending(repo):
    v, why = chk.judge(repo["path"], repo["c3"], "backend", repo["c1"], "ok")
    assert v == "pending" and "older than backend/'s last change" in why


def test_the_frontend_floor_is_the_frontend_folder_not_the_backend_one(repo):
    """c2 touched only backend/: the frontend serving c1f is current, serving c1 is not."""
    assert chk.judge(repo["path"], repo["c3"], "frontend", repo["c1f"], "ok")[0] == "pass"
    assert chk.judge(repo["path"], repo["c3"], "frontend", repo["c1"], "ok")[0] == "pending"


def test_a_folder_that_never_changed_passes_on_any_valid_master_commit(repo):
    assert chk.judge(repo["path"], repo["c3"], "ops", repo["c1"], "ok")[0] == "pass"


def test_no_commit_reported_is_pending_with_the_services_own_note(repo):
    v, why = chk.judge(repo["path"], repo["c3"], "backend", None, "reports no commit")
    assert (v, why) == ("pending", "reports no commit")


@pytest.mark.parametrize("served", ["abc", "HEAD", "0" * 39, "g" * 40, "refs/heads/master"])
def test_a_malformed_commit_fails_at_once(repo, served):
    v, why = chk.judge(repo["path"], repo["c3"], "backend", served, "ok")
    assert v == "fail" and "not a full commit SHA" in why


def test_a_commit_the_repository_does_not_have_fails(repo):
    v, why = chk.judge(repo["path"], repo["c3"], "backend", "a" * 40, "ok")
    assert v == "fail" and "does not have" in why


def test_a_commit_on_a_side_branch_is_not_master_and_fails(repo):
    _git(repo["path"], "checkout", "-q", "-b", "feature")
    side = _commit(__import__("pathlib").Path(repo["path"]), "backend/side.py")
    _git(repo["path"], "checkout", "-q", "master")
    v, why = chk.judge(repo["path"], repo["c3"], "backend", side, "ok")
    assert v == "fail" and "not on master" in why


def test_a_newer_master_commit_than_the_one_under_test_passes(repo):
    """Two merges in quick succession: the check for the first sees the second's build. It contains the
    first, and origin/master (what the runner fetched) has it."""
    p = __import__("pathlib").Path(repo["path"])
    c4 = _commit(p, "backend/c.py")
    _git(repo["path"], "update-ref", "refs/remotes/origin/master", c4)
    assert chk.judge(repo["path"], repo["c3"], "backend", c4, "ok")[0] == "pass"


# ── run: polling ──────────────────────────────────────────────────────────────

class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def _fetch_from(table):
    """A fake service: each URL replays its list of served commits, then repeats the last."""
    seen = {u: 0 for u in table}

    def fetch(url):
        seq = table[url]
        i = min(seen[url], len(seq) - 1)
        seen[url] += 1
        c = seq[i]
        return c, ("ok" if c else "reports no commit")
    return fetch


def test_the_check_waits_for_a_deploy_that_lands_late(repo):
    clock = Clock()
    res = chk.run(repo["path"], repo["c3"], {"backend": "b", "frontend": "f"}, timeout=900, interval=20,
                  fetch=_fetch_from({"b": [repo["c1"], repo["c1"], repo["c2"]], "f": [repo["c1f"]]}),
                  sleep=clock.sleep, clock=clock.now)
    assert {k: v["verdict"] for k, v in res.items()} == {"backend": "pass", "frontend": "pass"}
    assert clock.sleeps == [20, 20]


def test_a_deploy_that_never_lands_fails_with_the_deadline_in_the_reason(repo):
    clock = Clock()
    res = chk.run(repo["path"], repo["c3"], {"backend": "b", "frontend": "f"}, timeout=60, interval=20,
                  fetch=_fetch_from({"b": [repo["c1"]], "f": [repo["c1f"]]}), sleep=clock.sleep, clock=clock.now)
    assert res["backend"]["verdict"] == "fail" and "never caught up within 60s" in res["backend"]["reason"]
    assert res["frontend"]["verdict"] == "pass"


def test_a_service_that_never_reports_a_commit_fails_not_passes(repo):
    clock = Clock()
    res = chk.run(repo["path"], repo["c3"], {"backend": "b"}, timeout=40, interval=20,
                  fetch=_fetch_from({"b": [None]}), sleep=clock.sleep, clock=clock.now)
    assert res["backend"]["verdict"] == "fail" and "reports no commit" in res["backend"]["reason"]


# ── main: exit codes and the summary ─────────────────────────────────────────

def _main(repo, urls, **kw):
    clock = Clock()
    return chk.main(["--sha", repo["c3"], "--backend-url", "b", "--frontend-url", "f", "--repo", repo["path"],
                     "--timeout", "40", "--interval", "20"],
                    fetch=_fetch_from(urls), sleep=clock.sleep, clock=clock.now, **kw)


def test_main_exits_zero_when_both_pass_and_one_when_either_fails(repo, capsys, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert _main(repo, {"b": [repo["c2"]], "f": [repo["c1f"]]}) == 0
    out = capsys.readouterr().out
    assert f"merge commit: {repo['c3']}" in out and "PASS  backend" in out and "PASS  frontend" in out
    assert "### Served commit check" in summary.read_text()
    assert _main(repo, {"b": [repo["c1"]], "f": [repo["c1f"]]}) == 1
    assert "FAIL  backend" in capsys.readouterr().out


def test_main_refuses_a_short_or_missing_sha(repo, capsys):
    assert chk.main(["--sha", "abc123", "--backend-url", "b", "--frontend-url", "f"]) == 2
    assert chk.main(["--backend-url", "b", "--frontend-url", "f"]) == 2


# ── the transport layer: what a real service answers ─────────────────────────

@pytest.fixture
def server():
    routes = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, ctype, body = routes.get(self.path, (404, "text/plain", b"nope"))
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield routes, f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_fetch_reads_the_commit_from_a_json_body(server):
    routes, base = server
    routes["/version"] = (200, "application/json", b'{"service": "x", "commit": "' + b"a" * 40 + b'"}')
    assert chk.fetch_served(base + "/version") == ("a" * 40, "ok")


def test_fetch_reports_a_null_commit_as_no_commit(server):
    routes, base = server
    routes["/version"] = (200, "application/json", b'{"service": "x", "commit": null}')
    assert chk.fetch_served(base + "/version") == (None, "reports no commit")


def test_fetch_does_not_mistake_the_spa_fallback_page_for_a_version(server):
    """`serve -s` answers a missing file with index.html and a 200: the failure that would read as a pass."""
    routes, base = server
    routes["/version.json"] = (200, "text/html", b"<!doctype html><html><body>app shell</body></html>")
    commit, note = chk.fetch_served(base + "/version.json")
    assert commit is None and "not JSON" in note


def test_fetch_treats_a_server_error_and_a_dead_port_as_not_up_yet(server):
    routes, base = server
    routes["/version"] = (503, "text/plain", b"deploying")
    commit, note = chk.fetch_served(base + "/version")
    assert commit is None and "unreachable" in note
    commit, note = chk.fetch_served("http://127.0.0.1:1/version", timeout=2)
    assert commit is None and "unreachable" in note


def test_fetch_refuses_a_json_array(server):
    routes, base = server
    routes["/version"] = (200, "application/json", b'["a"]')
    assert chk.fetch_served(base + "/version")[0] is None
