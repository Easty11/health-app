"""Status-tooling reader/gate tests (task-5 Step 1).

Covers the Step-1 remainder over #207's landed reader: the #209 any-missing-state gate that
names offenders, and the pipe-split column-bounding of the branch-status scan. Neither repo has a
questions store any more (DECISIONS_LOG #468; health-connect-app #54), so the tools read decisions
and branches only; the last section pins that no questions section can come back.
"""
import pytest

import gen_status_model as G
import status_diff as SD
from gen_status_model import StatusGateError


# --- #209 gate: branches carry mandatory state; any missing halts, ids named ---------------- #

def test_gate_no_missing_state_halts_and_names_the_offender():
    with pytest.raises(StatusGateError) as e:
        G.gate_no_missing_state("health-app", "branches",
                                {"count": 3, "missing_state": 1, "missing_ids": ["`feat/x`"]})
    assert "`feat/x`" in str(e.value)


def test_gate_no_missing_state_passes_when_clean():
    G.gate_no_missing_state("health-app", "branches",
                            {"count": 2, "missing_state": 0, "missing_ids": []})  # must not raise


# --- pipe-split: the branch-status scan is COLUMN-bounded, not row-scanned ------------------- #

def test_branch_status_is_column_bounded_not_row_scanned():
    """A work-item token embedded mid-prose in the Purpose cell must NOT be lifted as the status.
    Purpose contains 'DONE'; the real Status is OWED. A row-bounded scan would report DONE."""
    text = ("| Branch | Purpose | Status | Detail |\n"
            "|---|---|---|---|\n"
            "| `feat/z` | reverts the DONE flag change | OWED | note |\n")
    p = G.parse_branches(text, "health-app")
    assert p["by_state"] == {"OWED": 1}
    assert p["missing_state"] == 0


def test_branch_status_robust_to_stray_pipe_in_prose():
    """An unescaped `|` inside a Purpose cell mis-splits the row and shifts positional columns;
    the leading-token scan still finds the real Status (DONE)."""
    text = ("| Branch | Purpose | Status | Detail |\n"
            "|---|---|---|---|\n"
            "| `feat/x` | adds `float | None` typing | DONE | landed |\n")
    p = G.parse_branches(text, "health-app")
    assert p["by_state"] == {"DONE": 1}
    assert p["missing_state"] == 0


def test_branch_missing_status_is_named_by_branch():
    text = ("| Branch | Purpose | Status | Detail |\n"
            "|---|---|---|---|\n"
            "| `feat/nostate` | a purpose with no status token anywhere | | |\n")
    p = G.parse_branches(text, "health-app")
    assert p["missing_state"] == 1
    assert p["missing_ids"] == ["`feat/nostate`"]


# --- diff engine ------------------------------------------------------------------------------ #

def test_diff_decisions_key_on_number():
    base = SD.extract_items("decisions", "### 1. First\n**Status:** active\n", "health-app")
    cur = SD.extract_items("decisions",
                           "### 1. First\n**Status:** active\n\n### 2. Second\n**Status:** active\n",
                           "health-app")
    d = SD.diff_store("decisions", base, cur)
    assert [o["id"] for o in d["opened"]] == ["#2"]
    assert d["closed"] == []


# --- question layer Phases B + C2/C3: no questions store in either repo ----------------------- #

BOTH_REPOS = ("health-app", "health-connect-app")


def test_no_questions_section_in_the_governance_view():
    import gen_governance_view as GV

    assert GV.STORES == ("DECISIONS_LOG", "FEEDBACK", "ROADMAP")
    entry = GV.Entry(label="1", title="t", status="s", line=1)
    data = {repo: {"sha": "0" * 40, "dmax": 1, "DECISIONS_LOG": [entry], "FEEDBACK": [entry],
                   "ROADMAP": [("NOW", [("- row", 1)])]} for repo in BOTH_REPOS}
    lines, counts = GV.build(data, "2026-10-31 00:00 +0000")
    text = "\n".join(lines)
    assert "questions" not in text.lower()
    assert not any("question" in k.lower() for k in counts)
    assert len(counts) == len(GV.STORES) * len(BOTH_REPOS)


def test_no_questions_store_in_the_status_model():
    assert "questions" not in G.STORE_FILE and "questions" not in G.PARSERS
    texts = {
        "decisions": "### 1. First\n**Status:** landed\n\n### 2. Second\n**Status:** landed\n",
        "branches": "| Branch | Purpose | Status | Detail | Blocker |\n|---|---|---|---|---|\n"
                    "| `a/b` | x | DONE | y | z |\n",
    }
    for repo in BOTH_REPOS:
        out = G.build_repo(repo, "0" * 40, texts)
        assert set(out) == {"provenance", "decisions", "branches"}
        assert out["decisions"]["count"] == 2 and out["branches"]["count"] == 1
    assert G.collect_drift({"repos": {r: G.build_repo(r, "0" * 40, texts) for r in BOTH_REPOS}}) == []


def test_no_questions_store_in_the_status_diff(monkeypatch):
    monkeypatch.setattr(SD, "read_store_at_ref", lambda repo, ref, key: None)
    assert "questions" not in SD.STORE_FILE
    for repo in BOTH_REPOS:
        assert set(SD.diff_repo(repo, None, None)) == {"decisions", "branches"}
