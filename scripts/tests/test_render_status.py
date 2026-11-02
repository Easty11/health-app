"""render_status.py end to end, against a fixture model and an `--issues-json` payload.

The renderer lives in health-app/scripts under Code's ownership so it is versioned and tested
beside the grammar it imports (DECISIONS_LOG, the ruling that moved it into this tree). It fetches
nothing and parses no store: the model reads the schema-2 `issues` block (DECISIONS_LOG #483) and
the page only reshapes it. These tests drive `main()` for real and fake only the two places the
model touches the network or a sibling clone (`resolve_master_sha`, `fetch`) plus the two reads
that would hit the operator's disk (`read_store_at_ref`, `_load_latest_snapshot`).

What is pinned: a readable block renders its non-PR count in `<h3>repo · N</h3>`, and a repo whose
tracker was not read renders `UNKNOWN for this repo, not zero` and NEVER a `· 0` heading.
"""
import json

import pytest

import gen_status_model as G
import render_status as R
import status_diff as SD

DECISIONS = "\n".join(f"### #{n}. Decision {n}\n\n**Decision:** x\n" for n in (1, 2, 3))
BRANCHES = ("| Branch | Purpose | Status | Detail |\n"
            "|---|---|---|---|\n"
            "| `feat/a` | one | DONE | landed |\n"
            "| `feat/b` | two | OWED | run `python3 scripts/x.py` |\n")
N_ISSUES = 74


def raw(n, pr=False):
    r = {"number": n, "title": f"issue {n}", "labels": [{"name": "watch"}],
         "created_at": "2026-10-01T00:00:00Z", "html_url": f"https://github.com/o/r/issues/{n}"}
    if pr:
        r["pull_request"] = {"url": "x"}
    return r


@pytest.fixture
def render(tmp_path, monkeypatch):
    """Run render_status.main() hermetically; returns a callable payload -> page html."""
    monkeypatch.setattr(G, "resolve_master_sha", lambda repo: "a" * 40)
    monkeypatch.setattr(G, "fetch", lambda repo, sha, store: DECISIONS if store == "DECISIONS_LOG" else BRANCHES)
    monkeypatch.setattr(SD, "read_store_at_ref", lambda repo, ref, key: BRANCHES)
    monkeypatch.setattr(SD, "_load_latest_snapshot", lambda: None)

    def run(payload):
        issues, out = tmp_path / "issues.json", tmp_path / "page.html"
        issues.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr("sys.argv", ["render_status.py", "--scripts-dir", str(G.Path(G.__file__).parent),
                                         "--issues-json", str(issues), "--no-ageing", "--out", str(out),
                                         "--generated", "2026-11-02 07:00 AEST"])
        assert R.main() == 0
        return out.read_text(encoding="utf-8")
    return run


def test_page_carries_the_non_pr_count_from_the_issues_block(render):
    items = [raw(n) for n in range(1, N_ISSUES + 1)] + [raw(900, pr=True), raw(901, pr=True)]
    page = render({"health-app": items, "health-connect-app": [raw(1)]})
    assert f"<h3>health-app · {N_ISSUES}</h3>" in page          # PRs excluded: 76 raw items -> 74
    assert "<h3>health-connect-app · 1</h3>" in page
    assert "UNKNOWN for this repo, not zero" not in page


@pytest.mark.parametrize("hca", [
    {"message": "Bad credentials"},   # the API answered, not with an issues array
    None,                             # repo absent from the file: the partial-file case
], ids=["non-list-payload", "repo-missing-from-file"])
def test_unreachable_repo_says_unknown_not_zero(render, hca):
    payload = {"health-app": [raw(n) for n in range(1, N_ISSUES + 1)]}
    if hca is not None:
        payload["health-connect-app"] = hca
    page = render(payload)
    assert "open-question state UNKNOWN for this repo, not zero" in page
    assert "<h3>health-connect-app</h3>" in page                # no count in the heading
    assert "health-connect-app · 0" not in page                 # an unread tracker is never zero
    assert f"<h3>health-app · {N_ISSUES}</h3>" in page          # the readable repo is unaffected
