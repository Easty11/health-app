# Close-out — Connector error policy + "See all" true pagination (#66, #67)

_Session date: 2026-07-11 · Branch at close: `master` (feature branch merged + deleted)_

---

## 1. Real commits this session

Session-open ref: `cf425d3` (`chore: session close-out`). `git log --oneline cf425d3..HEAD`:

```
bb0aed0 gov: BRANCHES.md — feat/connector-error-policy LANDED at 51c7091; Recent landings → #66/#67
51c7091 fix(connectors): decouple connector failures from session auth; See-all true pagination (#66, #67)
```

`feat/connector-error-policy` was cut from `master` at `cf425d3`, ff-merged back at
`51c7091`, and pushed (`cf425d3..51c7091 master -> master`); local branch deleted. The
feature branch was **never pushed to origin** (master carried it forward by fast-forward),
so there is no remote ref to delete. `bb0aed0` is the governance follow-up (BRANCHES.md
LANDED row + CLAUDE.md Recent-landings), also pushed.

**Single-commit rationale:** the brief's 3-commit plan (Steps 1–3+6 / Step 5 / Step 4)
assumed the top-10 stopgap scope. Luke's ruling (true pagination, aggregator built
in-branch) put the error-policy change (Steps 1–2) and the new `/workouts/all` endpoint in
the **same file** (`routers/integrations.py`), and both decisions (#66, #67) in the same
`DECISIONS_LOG.md` edit. Per-hunk staging is unavailable on this shell, and a file-level
split would scatter #66 across commits — so the branch landed as one cohesive commit
enumerating both decisions. One ff-merge = one sync point regardless.

## 2. Pending-queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — the input was a build
brief (ANCHOR/OBJECTIVE/STEPS/GATES/LOG/GUARD), not a `PENDING` queue. Reconciling against
the brief's own gates + the two GUARD forks Luke resolved:

| Brief item | Landed? |
|------------|---------|
| Step 1 — `_hevy_error_to_http` `HevyAuthError` 401→424 | ✅ `51c7091` (403/502 branches unchanged) |
| Step 1 VERIFY — session 401s live only in `auth.py`/`routers/auth.py` | ✅ grep confirmed; `connectors/hevy.py:33` is raw-401→exception, not an HTTP status |
| Step 2 — read handlers catch `httpx.HTTPStatusError` | ✅ `hevy_workout_count`/`hevy_workouts`/`hevy_get_routines` (+ new `hevy_workouts_all`) |
| Step 3 — Polar token-refresh 401→424 | ✅ verified connector (not session) failure at `polar.py:104` |
| Step 4 — global 500 CORS guard | ✅ **LANDED** (not fiddly) — `cors_errors.add_cors_error_handler`; empirically verified against real `main.app` |
| Step 5 — "See all" | ✅ **Fork 1 = true pagination** (not top-10 stopgap): new `GET /integrations/hevy/workouts/all` page-loop + frontend rewire |
| Fork 2 — aggregator timing | ✅ **built in-branch** (Luke's call), not split to follow-up |
| Step 6 — tests assert 424/502, suite green | ✅ +18 tests; full backend suite **56 green**; frontend `npm run build` green |
| LOG — DECISIONS_LOG #66 + #67 (canonical 5-field), issue #13 updated | ✅ `51c7091` |

**One honest gap (recorded in #67 + BRANCHES.md):** "See all" was **not** E2E-verified
against a live Hevy account — the connected Hevy key is invalid/expired (the exact
revoked-key case #66 fixes). The pageSize=10 ceiling is proven from the Hevy MCP tool
schema (`pageSize maximum: 10`); `page_count` is cross-confirmed as the real envelope field
by the production template sync (`hevy_templates.py:181`). Worst case degrades to page 1,
guarded by the 502 helper — never a crash. Nothing else provisional: every landed gate is
in a commit on `master`.

## 3. Cold-resume handoff

**What landed:** DECISIONS_LOG **#66** — a connector (Hevy/Polar) failure never surfaces as
a session-auth 401 or an unhandled 500. Remapped at the backend choke point: `HevyAuthError`
401→424; read handlers route `httpx.HTTPStatusError`→helper (clean 502, not a CORS-stripping
500); Polar token-refresh 401→424; a global `Exception` handler (`cors_errors.py`) guarantees
any residual 500 carries CORS headers (Starlette's `ServerErrorMiddleware` sits outside
`CORSMiddleware`). Frontend `api.js` interceptor untouched — correct by construction once no
connector path emits 401. DECISIONS_LOG **#67** — "See all" now means genuinely all workouts
via `GET /integrations/hevy/workouts/all` (`HevyClient.get_all_workouts` loops every Hevy
`/workouts` page, which caps at pageSize 10); the old `page_size=20` request was over the
ceiling and produced the fake-CORS 500. Issue #13's "dead handler" description is superseded.
No schema change; SCHEMA.md untouched; no migration. **Deployed to Railway** on merge.

**Current sprint (ROADMAP NOW — unchanged this session):** HC permissions fix (record types
38/35/11/37); Samsung Health package-name correction (`com.sec.android.app.shealth`, verify
via Railway Postgres); morning check-in screen (Hooper Index); persistent conversation
history; UI bugs (session cards not clickable, dual-panel scroll);
`mcp_server.get_hevy_workouts` unimported `Session` one-line fix.

**Open questions by status (no Q opened or resolved this session):**
- `open`: **Q15** (`3497ab483935` prod-drift reconciliation — resolve against Railway
  Postgres, not local); **Q16** (`hevy.py` `get_exercise_history` path); plus standing
  Q3/Q5/Q7/Q9/Q13.
- `verifying`: **Q4** (HC sleep⇄scraper same-date — deferred to live re-sync / G4 on
  Railway, per #64).

**Single clearest next action:** **Verify "See all" live** — reconnect a valid Hevy API key
(the currently stored key is invalid — now surfaced as a clean 424, no forced logout), open
Training Data → "See all", and confirm the full workout history renders with no CORS error
and no page-1 truncation. This closes the one unverified path in #67. (Standing roadmap NEXT
remains **Hevy resolver activation** — wire `context_builder` to emit titles so the #60/#61 +
#65 resolver fires.)

**Governance stores changed this session:** `DECISIONS_LOG.md` (+ `BRANCHES.md` ledger and
`CLAUDE.md` Recent-landings, which are repo-canonical, not project-mirrored). Pre-merge
copy-back = `cat`/open of each file on disk; chat never regenerates from memory.
