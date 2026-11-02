"""Open issues in the status model (DECISIONS_LOG #483): normaliser, gate, both transports, the
fetcher, the snapshot, and the diff. The transport tests fake at the HTTP layer (a local server
speaking the GitHub API's pagination), not at a mocked function — the code interprets a third
party's response, so a test of the parsing must see real bytes and real headers."""
import http.server
import json
import threading

import pytest

import fetch_issues as FI
import gen_status_model as G
import status_diff as SD
from gen_status_model import StatusGateError


def raw(n, title="t", labels=("fork",), created="2026-11-01T21:14:00Z", pr=False):
    r = {"number": n, "title": title, "labels": [{"name": x} for x in labels],
         "created_at": created, "html_url": f"https://github.com/o/r/issues/{n}"}
    if pr:
        r["pull_request"] = {"url": "x"}
    return r


def norm(n, title="t", labels=("fork",), created="2026-11-01"):
    return {"number": n, "title": title, "labels": sorted(labels), "created_at": created,
            "html_url": f"https://github.com/o/r/issues/{n}"}


# --- the grammar: one normaliser ------------------------------------------------------------ #

def test_normalise_excludes_prs_keeps_five_fields_and_dates_the_age():
    out = G.normalise_issues([raw(580, pr=True), raw(9, labels=("watch", "design")), raw(3)])
    assert [i["number"] for i in out] == [3, 9]                      # PR gone, ascending
    assert set(out[0]) == set(G.ISSUE_ITEM_FIELDS)
    assert out[1]["labels"] == ["design", "watch"] and out[1]["created_at"] == "2026-11-01"


@pytest.mark.parametrize("bad", [
    {"x": 1}, [None], [{**raw(1), "number": "1"}], [{**raw(1), "number": True}],
    [{**raw(1), "title": None}], [{**raw(1), "created_at": "yesterday"}],
    [{**raw(1), "labels": None}], [{**raw(1), "labels": [{"nm": "x"}]}],
    [{**raw(1), "html_url": ""}], [raw(1), raw(1)],
])
def test_normalise_rejects_malformed_never_skips(bad):
    with pytest.raises(G.IssueShapeError):
        G.normalise_issues(bad)


def test_file_transport_every_non_list_is_unreachable_never_zero(capsys):
    for bad in (None, {"message": "Bad credentials"}, "x", [{"number": 1}]):
        b = G.issues_block_from_payload("r", bad)
        assert b == {"tracker": "unreachable", "count": None, "items": None}
        G.gate_issues_shape("r", b)
    with pytest.raises(TypeError):
        b["count"] + 1                                               # a consumer must crash, not print 0


# --- the gate ------------------------------------------------------------------------------- #

def test_gate_halts_on_zero_while_unread_and_on_ok_without_http_200():
    with pytest.raises(StatusGateError):
        G.gate_issues_shape("r", {"tracker": "unreachable", "count": 0, "items": None})
    with pytest.raises(StatusGateError):
        G.gate_issues_shape("r", {"tracker": "ok", "count": 0, "items": []})
    G.gate_issues_shape("r", {"tracker": "ok", "count": 0, "items": [], "http": 200})


def test_gate_halts_on_a_partial_item_and_a_count_that_disagrees():
    item = norm(1)
    with pytest.raises(StatusGateError):
        G.gate_issues_shape("r", {"tracker": "ok", "count": 1, "items": [{"number": 1}], "http": 200})
    with pytest.raises(StatusGateError):
        G.gate_issues_shape("r", {"tracker": "ok", "count": 5, "items": [item], "http": 200})
    with pytest.raises(StatusGateError):
        G.gate_issues_shape("r", {"tracker": "ok", "count": 2, "items": [item, item], "http": 200})


# --- the live transport, faked at the HTTP layer -------------------------------------------- #

class _Api(http.server.BaseHTTPRequestHandler):
    routes: dict = {}                    # path -> (status, body, headers)
    seen: list = []

    def do_GET(self):
        _Api.seen.append(self.path)
        status, body, headers = _Api.routes.get(self.path.split("?")[0] + ("?" + self.path.split("?")[1]
                                                if "?" in self.path else ""),
                                                 (404, b'{"message":"Not Found"}', {}))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def api(monkeypatch):
    _Api.routes, _Api.seen = {}, []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setattr(FI, "API_BASE", base)
    yield base
    srv.shutdown()


def _json(x):
    return json.dumps(x).encode()


def test_live_fetch_follows_link_pagination_excludes_prs_and_records_http(api):
    q = "?state=open&per_page=100"
    _Api.routes[f"/repos/o/r/issues{q}"] = (
        200, _json([raw(1), raw(580, pr=True)]), {"Link": f'<{api}/repos/o/r/issues?page=2>; rel="next"'})
    _Api.routes["/repos/o/r/issues?page=2"] = (200, _json([raw(2, labels=())]), {})
    b = G.fetch_open_issues("o", "r")
    assert b == {"tracker": "ok", "count": 2, "http": 200,
                 "items": [norm(1), norm(2, labels=())]}
    assert len(_Api.seen) == 2                                       # both pages read, none dropped
    G.gate_issues_shape("r", b)


def test_live_fetch_empty_200_is_ok_zero_with_http_recorded(api):
    _Api.routes["/repos/o/r/issues?state=open&per_page=100"] = (200, b"[]", {})
    b = G.fetch_open_issues("o", "r")
    assert b == {"tracker": "ok", "count": 0, "items": [], "http": 200}


@pytest.mark.parametrize("status,body", [
    (403, b'{"message":"rate limited"}'), (404, b'{}'), (500, b""), (200, b"not json"),
    (200, b'{"message":"an object, not an array"}')])
def test_live_fetch_any_failure_is_unreachable_null_never_zero(api, status, body):
    _Api.routes["/repos/o/r/issues?state=open&per_page=100"] = (status, body, {})
    b = G.fetch_open_issues("o", "r")
    assert b == {"tracker": "unreachable", "count": None, "items": None}


def test_live_fetch_a_failed_second_page_loses_the_whole_repo_not_just_a_page(api):
    _Api.routes["/repos/o/r/issues?state=open&per_page=100"] = (
        200, _json([raw(1)]), {"Link": f'<{api}/repos/o/r/issues?page=2>; rel="next"'})
    _Api.routes["/repos/o/r/issues?page=2"] = (502, b"", {})
    assert G.fetch_open_issues("o", "r")["tracker"] == "unreachable"


def test_live_fetch_connection_refused_is_unreachable(monkeypatch):
    monkeypatch.setattr(FI, "API_BASE", "http://127.0.0.1:9")        # discard port: refused
    assert G.fetch_open_issues("o", "r") == {"tracker": "unreachable", "count": None, "items": None}


def test_pagination_has_a_loud_stop_not_a_silent_cap(api, monkeypatch):
    monkeypatch.setattr(FI, "MAX_PAGES", 2)
    for p in ("/repos/o/r/issues?state=open&per_page=100", "/repos/o/r/issues?page=2",
              "/repos/o/r/issues?page=3"):
        _Api.routes[p] = (200, _json([]), {"Link": f'<{api}/repos/o/r/issues?page=3>; rel="next"'})
    with pytest.raises(FI.FetchError):
        FI.fetch_open_issues_raw("o", "r")


# --- one grammar, two transports ------------------------------------------------------------ #

def test_both_transports_produce_the_same_block(api, tmp_path):
    payload = [raw(1), raw(580, pr=True), raw(2, labels=("verify", "fork"))]
    _Api.routes["/repos/o/health-app/issues?state=open&per_page=100"] = (200, _json(payload), {})
    live = G.fetch_open_issues("o", "health-app")
    assert G.issues_block_from_payload("health-app", payload) == live


# --- fetch_issues.py: the file writer ------------------------------------------------------- #

def test_fetcher_writes_raw_payloads_and_exits_nonzero_leaving_a_failed_repo_out(api, tmp_path, monkeypatch):
    monkeypatch.setattr(FI, "owner_and_repos", lambda: ("o", ("good", "bad"), "test"))
    _Api.routes["/repos/o/good/issues?state=open&per_page=100"] = (200, _json([raw(1), raw(2, pr=True)]), {})
    _Api.routes["/repos/o/bad/issues?state=open&per_page=100"] = (403, b"{}", {})
    out = tmp_path / "sub" / "issues.json"
    assert FI.main(["--out", str(out)]) == 1
    written = json.loads(out.read_text(encoding="utf-8"))
    assert list(written) == ["good"] and len(written["good"]) == 2   # raw: the PR is still there
    assert "bad" not in written                                      # missing, so the model reads it unreachable


def test_fetcher_exit_zero_when_every_repo_reads(api, tmp_path, monkeypatch):
    monkeypatch.setattr(FI, "owner_and_repos", lambda: ("o", ("a",), "test"))
    _Api.routes["/repos/o/a/issues?state=open&per_page=100"] = (200, b"[]", {})
    out = tmp_path / "i.json"
    assert FI.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"a": []}


def test_fetcher_owner_and_repos_inside_the_clone_come_from_the_shared_names():
    owner, repos, source = FI.owner_and_repos()
    assert owner == "Easty11" and repos == ("health-app", "health-connect-app")
    assert "gov_dialects" in source


def test_fetcher_is_stdlib_only():
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path(FI.__file__).read_text(encoding="utf-8"))
    top = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    top |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    # gov_dialects / status_diff are imported lazily and only inside the clone (try/except ImportError)
    assert top <= {"argparse", "json", "re", "sys", "urllib", "pathlib", "__future__",
                   "gov_dialects", "status_diff"}


# --- build_model: --issues-json ------------------------------------------------------------- #

@pytest.fixture
def stub_stores(monkeypatch):
    texts = {
        "decisions": "### 1. First\n**Status:** landed\n",
        "branches": "| Branch | Purpose | Status | Detail | Blocker |\n|---|---|---|---|---|\n"
                    "| `a/b` | x | DONE | y | z |\n",
    }
    monkeypatch.setattr(G, "resolve_master_sha", lambda repo: "0" * 40)
    monkeypatch.setattr(G, "fetch", lambda repo, sha, store: texts[
        {v: k for k, v in G.STORE_FILE.items()}[store]])
    monkeypatch.setattr(G, "MIN_STORE_BYTES", 0)


def test_issues_json_means_no_live_fetch_and_a_missing_repo_is_unreachable(stub_stores, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("live fetch attempted despite --issues-json")
    monkeypatch.setattr(G, "fetch_open_issues", boom)
    model = G.build_model("2026-11-02T00:00:00Z", {"health-app": [raw(1), raw(580, pr=True)]})
    assert model["schema_version"] == 2
    assert model["repos"]["health-app"]["issues"] == {"tracker": "ok", "count": 1, "http": 200,
                                                      "items": [norm(1)]}
    assert model["repos"]["health-connect-app"]["issues"] == {"tracker": "unreachable",
                                                              "count": None, "items": None}


def test_live_transport_down_yields_unreachable_with_null_count(stub_stores, monkeypatch):
    monkeypatch.setattr(FI, "API_BASE", "http://127.0.0.1:9")
    model = G.build_model("2026-11-02T00:00:00Z")
    for repo in G.D.REPOS:
        assert model["repos"][repo]["issues"] == {"tracker": "unreachable", "count": None, "items": None}


def test_issues_file_unreadable_or_not_an_object_halts(tmp_path):
    p = tmp_path / "i.json"
    for body in ("{not json", "[]", '"x"'):
        p.write_text(body, encoding="utf-8")
        with pytest.raises(StatusGateError):
            G.load_issues_payload(p)
    with pytest.raises(StatusGateError):
        G.load_issues_payload(tmp_path / "absent.json")
    p.write_text('{"health-app": []}', encoding="utf-8")
    assert G.load_issues_payload(p) == {"health-app": []}


# --- snapshot ------------------------------------------------------------------------------- #

def _model(issues_by_repo):
    return {"schema_version": 2, "generated_utc": "2026-11-02T00:00:00Z",
            "repos": {r: {"provenance": {"ref": "master", "sha": "0" * 40}, "issues": b}
                      for r, b in issues_by_repo.items()}}


def test_write_snapshot_carries_the_issues_block_and_refuses_a_missing_one(tmp_path):
    ok = G.issues_block_ok([norm(1)], 200)
    snap, _ = G.write_snapshot(_model({"health-app": ok, "health-connect-app": G.issues_block_unreachable()}),
                               tmp_path)
    saved = json.loads(snap.read_text(encoding="utf-8"))
    assert saved["repos"]["health-app"]["issues"] == ok
    assert saved["repos"]["health-connect-app"]["issues"]["count"] is None
    m = _model({"health-app": ok, "health-connect-app": ok})
    del m["repos"]["health-app"]["issues"]
    with pytest.raises(StatusGateError):
        G.write_snapshot(m, tmp_path)


# --- the diff ------------------------------------------------------------------------------- #

def blk(*items):
    return G.issues_block_ok(list(items), 200)


def test_diff_issues_opened_closed_changed_by_number():
    base = blk(norm(1), norm(2, labels=("fork",)), norm(3, title="old"))
    cur = blk(norm(2, labels=("fork", "design")), norm(3, title="new"), norm(4))
    d = SD.diff_issues(base, cur)
    assert [i["id"] for i in d["opened"]] == ["GH#4"]
    assert [i["id"] for i in d["closed"]] == ["GH#1"]
    ch = {c["id"]: c for c in d["changed"]}
    assert set(ch) == {"GH#2", "GH#3"}
    assert ch["GH#3"]["from"] == {"title": "old"} and ch["GH#3"]["to"] == {"title": "new"}
    assert set(ch["GH#2"]["to"]) == {"labels"} and ch["GH#2"]["to"]["labels"] == ["design", "fork"]


def test_diff_issues_unchanged_is_empty_but_compared():
    d = SD.diff_issues(blk(norm(1)), blk(norm(1)))
    assert d == {"opened": [], "closed": [], "changed": []}


@pytest.mark.parametrize("base,cur", [
    (None, blk(norm(1))),                                            # schema-1 baseline: no `issues` key
    (G.issues_block_unreachable(), blk(norm(1))),
    (blk(norm(1)), G.issues_block_unreachable()),
    (blk(norm(1)), None),
])
def test_diff_issues_unread_side_is_not_compared_never_all_closed_or_opened(base, cur):
    d = SD.diff_issues(base, cur)
    assert set(d) == {"not_compared"} and "UNKNOWN" in d["not_compared"]


def test_diff_snapshots_schema1_baseline_and_no_baseline():
    cur = _model({"health-app": blk(norm(1)), "health-connect-app": blk()})
    schema1 = {"schema_version": 1, "repos": {"health-app": {"provenance": {}}, "health-connect-app": {}}}
    out = SD.diff_issues_snapshots(schema1, cur)
    assert all("not_compared" in v for v in out.values())
    out = SD.diff_issues_snapshots(None, cur)
    assert all("baseline run" in v["not_compared"] for v in out.values())


def test_report_never_says_closed_when_the_tracker_was_not_read():
    lines = SD._fmt_issues_delta("health-app", G.issues_block_unreachable(),
                                 SD.diff_issues(blk(norm(1), norm(2)), G.issues_block_unreachable()))
    text = "\n".join(lines)
    assert "NOT COMPARED" in text and "UNKNOWN" in text and "closed" not in text.replace("NOT COMPARED", "")


def test_snapshot_order_puts_the_same_second_suffix_after_the_plain_file(tmp_path):
    from pathlib import Path
    names = ["2026-11-02T000000Z_2_model.json", "2026-11-02T000000Z_model.json",
             "2026-11-01T230000Z_model.json", "2026-11-02T000000Z_3_model.json"]
    got = [p.name for p in sorted((Path(n) for n in names), key=SD._snapshot_order)]
    assert got == ["2026-11-01T230000Z_model.json", "2026-11-02T000000Z_model.json",
                   "2026-11-02T000000Z_2_model.json", "2026-11-02T000000Z_3_model.json"]


def test_report_formats_opened_closed_and_changed_lines():
    cur = blk(norm(2, labels=("fork", "design")), norm(4, title="brand new"))
    d = SD.diff_issues(blk(norm(1, title="gone"), norm(2)), cur)
    text = "\n".join(SD._fmt_issues_delta("health-app", cur, d))
    assert "2 open" in text and "+1 opened, -1 closed, ~1 changed" in text
    assert "opened  GH#4: brand new" in text and "closed  GH#1: gone" in text
    assert "changed GH#2 (labels)" in text


def test_build_report_end_to_end_schema1_baseline_then_schema2(tmp_path, monkeypatch):
    """The 'since last run' view over real snapshot files: a schema-1 predecessor (no `issues`
    key) must read as NOT COMPARED, then two schema-2 snapshots must diff by number."""
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    prov = {"provenance": {"ref": "master", "sha": "0" * 40}}
    s1 = {"schema_version": 1, "generated_utc": "2026-11-01T00:00:00Z", "repos": {"health-app": prov}}
    s2 = {"schema_version": 2, "generated_utc": "2026-11-02T00:00:00Z",
          "repos": {"health-app": {**prov, "issues": blk(norm(1), norm(2))}}}
    s3 = {"schema_version": 2, "generated_utc": "2026-11-03T00:00:00Z",
          "repos": {"health-app": {**prov, "issues": blk(norm(2), norm(3))}}}
    monkeypatch.setattr(SD, "STATUS_DIR", tmp_path)
    monkeypatch.setattr(SD, "read_store_at_ref", lambda *a, **k: None)
    monkeypatch.setattr(SD, "unreferenced_rules", lambda t: {"candidates": 0, "unreferenced": []})

    def put(name, snap, latest=True):
        (snaps / name).write_text(json.dumps(snap), encoding="utf-8")
        if latest:
            (tmp_path / "latest.json").write_text(json.dumps(snap), encoding="utf-8")

    put("2026-11-01T000000Z_model.json", s1)
    put("2026-11-02T000000Z_model.json", s2)
    r = SD.build_report()
    assert "health-app: issues 2 open; NOT COMPARED (baseline: no `issues` block (schema 1)" in r
    put("2026-11-03T000000Z_model.json", s3)
    r = SD.build_report()
    assert "issues 2 open; +1 opened, -1 closed, ~0 changed" in r
    assert "opened  GH#3" in r and "closed  GH#1" in r
