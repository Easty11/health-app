"""The pre-push guard that stops an unresolved `#NEXT` reaching master.

A guard nobody tests is a guard that silently stops guarding. What carries risk here is
not "does the regex match" but the two ways this check could be worse than useless:

  * FALSE NEGATIVE — it fails to fire on the real defect, and everyone trusts a green.
    Pinned against the exact heading form that rode master for three sessions.
  * FALSE POSITIVE — it fires on prose ABOUT the convention, gets bypassed with
    `--no-verify` out of habit, and then protects nothing. This is the live risk in this
    repo: CLAUDE.md's own rule text, #148's entry, and several corrected entries all
    QUOTE the token. #113 is exactly this failure and the reason the patterns anchor on
    the heading rather than matching a bare substring.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_governance_placeholders.py"
sys.path.insert(0, str(REPO / "scripts"))

from check_governance_placeholders import CHECKS  # noqa: E402

DECISIONS_PATTERN = CHECKS[0][1]
QUESTIONS_PATTERN = CHECKS[1][1]


# ── it fires on the real thing ───────────────────────────────────────────────

def test_fires_on_an_unresolved_decision_heading():
    text = "### 164. Something\n\n### #NEXT. Titration becomes a hunting search\n"
    assert DECISIONS_PATTERN.search(text)


def test_fires_on_an_unresolved_question_heading():
    assert QUESTIONS_PATTERN.search("## Q77. Prior\n\n## Q#NEXT. A new fork\n")


def test_reports_every_offence_not_just_the_first():
    text = "### #NEXT. One\n\nprose\n\n### #NEXT. Two\n"
    assert len(DECISIONS_PATTERN.findall(text)) == 2


# ── it does NOT fire on prose about the convention (#113) ────────────────────

def test_does_not_fire_on_the_rule_text_that_names_the_token():
    """CLAUDE.md's own Number-at-merge rule contains the literal token. A substring
    match would make the guard unusable on the very file that defines it."""
    rule = "- **Number-at-merge.** On a branch, a new entry is headed `### #NEXT`. The integer is\n"
    assert not DECISIONS_PATTERN.search(rule)


def test_does_not_fire_on_a_correction_quoting_the_superseded_token():
    """Corrected entries quote the token inside their own correction — by design. #113:
    expect the hit, read the line, and anchor so it never counts as an offence."""
    body = (
        "### 165. A decision\n"
        "\n"
        "**Correction:** the branch landed while its heading still read `### #NEXT`,\n"
        "which is how #162 became a hole.\n"
    )
    assert not DECISIONS_PATTERN.search(body)


def test_does_not_fire_on_a_resolved_heading():
    assert not DECISIONS_PATTERN.search("### 165. Titration becomes a hunting search\n")
    assert not QUESTIONS_PATTERN.search("## Q78. Exclude-all starves a napper\n")


def test_does_not_fire_mid_line():
    assert not DECISIONS_PATTERN.search("see ### #NEXT for the convention\n")


# ── end to end, through the real script ──────────────────────────────────────

def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, cwd=REPO)


def test_current_working_tree_is_clean_of_placeholders_or_says_why():
    """On master this must pass. On a branch mid-work it legitimately fails — so assert
    the CONTRACT (0 or 1, never a crash) rather than a verdict that depends on where the
    suite happens to be run."""
    r = _run()
    assert r.returncode in (0, 1), r.stderr
    if r.returncode == 1:
        assert "REFUSED" in r.stderr


def test_an_unreadable_ref_exits_2_and_does_not_silently_pass():
    """A check that cannot run must never look like a check that passed."""
    r = _run("--ref", "definitely-not-a-ref")
    assert r.returncode == 2
    assert "cannot read" in r.stderr


def test_the_guard_fires_on_the_commit_that_actually_caused_the_hole():
    """001df4c is the `feat/hub-shell` merge that put a live `### #NEXT` on master and
    left #162 permanently empty. Not a synthetic fixture — the real defect."""
    r = _run("--ref", "001df4c")
    if "cannot read" in r.stderr:
        import pytest
        pytest.skip("shallow clone or history unavailable")
    assert r.returncode == 1
    assert "DECISIONS_LOG.md" in r.stderr
