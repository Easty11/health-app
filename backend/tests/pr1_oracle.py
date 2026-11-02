"""The engine as PR1 of "Engine blocks are rows" merged it — the oracle the retirement is measured against.

`engine/selection.py` at the PR1 merge commit still carried the three injury-keyed block maps and their
arms. The retirement PR deleted them, so "does the new engine block what the old arms blocked, or is it
covered by an operator decision?" can only be asked of the OLD source. This loads it from git, pinned to
the merge commit's SHA, never "master" (master moves past the retirement, which would make the comparison
new-vs-new) and never a re-typed copy.

Needs the object in the clone: CI checks out full depth (`fetch-depth: 0`, tests.yml), as other tests that
`git show` a pinned commit already require.
"""
import os
import subprocess
import types

# The merge commit of PR1 (Easty11/health-app#596): the last engine with the injury-keyed arms.
PR1_MERGE_SHA = "d63b5343bbe0ef695718b7ace96267a1981fe53f"


def load_selection_at(sha: str, name: str = "engine._selection_oracle") -> types.ModuleType:
    """`engine/selection.py` exactly as it was at `sha`, loaded from git (never a re-typed copy)."""
    src = subprocess.check_output(
        ["git", "show", f"{sha}:backend/engine/selection.py"],
        cwd=os.path.dirname(__file__), encoding="utf-8",
    )
    module = types.ModuleType(name)
    module.__package__ = "engine"          # its `from . import taxonomy` resolves against the live package
    exec(compile(src, f"selection_{sha[:7]}.py", "exec"), module.__dict__)
    return module


def load_pr1_selection() -> types.ModuleType:
    return load_selection_at(PR1_MERGE_SHA, "engine._selection_pr1")


PR1 = load_pr1_selection()
