# Close-out — 2026-07-12 — Hevy exercise-history path (#69)

## Real commits this session

Session-open master: `d6fbf5d` (chore: session close-out).

| Hash | Message |
|------|---------|
| `2fc21e2` | fix(hevy): exercise_history path -> /v1/exercise_history/{id} (#69) |

`2fc21e2` is master's current tip (ff-merged from `fix/hevy-exercise-history-path`,
now deleted). A `chore: session close-out` commit follows this file, carrying
`BRANCHES.md` + `CLAUDE.md` + `closeout.md`.

## Pending-queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — the work came in
as a direct Code brief (fix the Hevy exercise-history path, resolve Q16). Every brief
item landed:

- **FIX** — `get_exercise_history` path swapped `/exercise_templates/{id}/history` →
  `/v1/exercise_history/{id}`, template id unchanged, no caller signature change.
  Landed in `2fc21e2`.
- **PRE-MERGE caller audit** — `git grep '\.get_exercise_history('` returned **zero
  call sites**. The method is currently unwired, so correcting a silent-404 into real
  history carries no downstream silent-behaviour-shift. Recorded in DECISIONS_LOG #69.
- **VERIFY** — full backend suite **65 passed** (`.venv/Scripts/python.exe -m pytest -q`,
  one pre-existing Starlette deprecation warning, unrelated). No test exercises this
  path — none exists; doc-evidence is the basis. Live `exercise_history` corroboration
  was blocked (local Hevy MCP hung) and is flagged optional belt-and-braces, not gating.
- **LAND** — ff-merge → `BRANCHES.md` LANDED row (`2fc21e2`) → DECISIONS_LOG #69
  (Q16-resolved, number claimed at ff-merge; origin max was #68) → OPEN_QUESTIONS Q16
  `resolved → #69` → branch deleted. All landed.

Nothing provisional. `/v1` prefix confirmed single (from the `HEVY_BASE` join), not
doubled, not dropped.

## Cold-resume handoff

**Repo state:** on `master` at `2fc21e2` (+ the following close-out commit). master was
in sync with `origin/master` at session open; push master after close-out. No open
branches — `BRANCHES.md` is all LANDED rows.

**Landed this session:** DECISIONS_LOG **#69** — Hevy exercise-history path corrected;
Q16 resolved. Method is unwired (zero call sites), so it ships dormant: real history
will only flow once a caller is added.

**Active sprint (ROADMAP NOW):** Health Connect permissions fix (record types 38/35/11/37);
Samsung Health package-name correction (`com.sec.android.app.shealth`, verify via Railway
Postgres); Morning check-in screen (Hooper Index); persistent conversation history;
session-card click bug; dual-panel scroll bug; `mcp_server.get_hevy_workouts` unimported
`Session` type (one-line import fix).

**Open questions by status:**
- _resolved this session:_ **Q16** → #69 (Hevy exercise-history path).
- _still open:_ broader open forks live in `OPEN_QUESTIONS.md` (e.g. Polar zone retrieval,
  HRV gates Q3) — unchanged this session.

**Single clearest next action:** Push `master` to `origin` (`git push origin master`) to
sync the #69 fix + close-out. Optional follow-up: live-corroborate `/v1/exercise_history/{id}`
against a valid Hevy key when the local Hevy MCP is healthy (belt-and-braces on #69).

**Stores changed this session:** `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md` (+ `BRANCHES.md`,
`CLAUDE.md` in the close-out commit).
