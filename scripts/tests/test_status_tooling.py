"""Status-tooling reader/gate tests (task-5 Step 1).

Covers the Step-1 remainder over #207's landed reader: the #209 any-missing-state gate that
names offenders, and the pipe-split column-bounding of the branch-status scan.
"""
import pytest

import gen_status_model as G
import status_diff as SD
from gen_status_model import StatusGateError


# --- #209 gate: questions/branches carry mandatory state; any missing halts, ids named ------ #

def test_gate_no_missing_state_halts_and_names_the_offender():
    with pytest.raises(StatusGateError) as e:
        G.gate_no_missing_state("health-app", "questions",
                                {"count": 3, "missing_state": 1, "missing_ids": ["Q42"]})
    assert "Q42" in str(e.value)


def test_gate_no_missing_state_passes_when_clean():
    G.gate_no_missing_state("health-app", "branches",
                            {"count": 2, "missing_state": 0, "missing_ids": []})  # must not raise


def test_parse_questions_collects_missing_state_ids():
    text = ("## Q1. First\n**State:** OPEN\n\n"
            "## Q2. Second, no state line\nsome body text\n\n"
            "## Q3. Third\n**State:** DONE\n")
    p = G.parse_questions(text, "health-app")
    assert p["missing_state"] == 1
    assert p["missing_ids"] == ["Q2"]


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


# --- diff engine: RENUMBER SURVIVAL (the Step-2 load-bearing contract) ---------------------- #

def test_diff_pure_renumber_survives_as_renumbered_not_close_open():
    """Q28 -> Q50, title+substance unchanged: identity survives on the title fingerprint, so it
    is reported as `renumbered`, never as a close + an open."""
    base = SD.extract_items("questions", "## Q28. A stable question title\n**State:** OPEN\n", "health-app")
    cur = SD.extract_items("questions", "## Q50. A stable question title\n**State:** DONE\n", "health-app")
    d = SD.diff_store("questions", base, cur)
    assert d["opened"] == [] and d["closed"] == []
    assert len(d["renumbered"]) == 1
    r = d["renumbered"][0]
    assert r["from"] == "Q28" and r["to"] == "Q50"
    assert r["state_change"] == ["OPEN", "DONE"]


def test_diff_renumber_with_title_edit_is_reported_not_auto_paired():
    """When the title is also edited the fingerprint does not survive — the tool must report the
    closed and the opened separately with a verify-by-hand note, NEVER fuzzy-pair them."""
    base = SD.extract_items("questions", "## Q28. Original wording here\n**State:** OPEN\n", "health-app")
    cur = SD.extract_items("questions", "## Q50. Completely rewritten wording\n**State:** OPEN\n", "health-app")
    d = SD.diff_store("questions", base, cur)
    assert len(d["opened"]) == 1 and len(d["closed"]) == 1
    assert d["renumbered"] == []
    assert "verify by hand" in d["renumber_suspects"].lower()


def test_diff_decisions_key_on_number():
    base = SD.extract_items("decisions", "### 1. First\n**Status:** active\n", "health-app")
    cur = SD.extract_items("decisions",
                           "### 1. First\n**Status:** active\n\n### 2. Second\n**Status:** active\n",
                           "health-app")
    d = SD.diff_store("decisions", base, cur)
    assert [o["id"] for o in d["opened"]] == ["#2"]
    assert d["closed"] == []
