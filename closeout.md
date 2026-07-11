# Close-out — Hevy create-loop (`create_and_resolve`)

_Session date: 2026-07-11 · Branch at close: `master` (feature branch merged + deleted)_

---

## 1. Real commits this session

Session-open ref: `b219aa4` (`chore: session close-out`). `git log --oneline b219aa4..HEAD`:

```
1dcce25 gov: BRANCHES.md — feat/hevy-create-loop LANDED at e13e3a2
e13e3a2 gov: claim DECISIONS_LOG #65 at merge (was #NEXT); Q14 -> resolved #65
a029a0b gov: DECISIONS_LOG #NEXT (Hevy create-loop, list-back-always); Q14 resolved
9d5487e feat(hevy): create_and_resolve — app-originated customs via list-back
d5aadc8 refactor(hevy): extract sync_one_user from sync_exercise_templates
```

(A sixth commit, `chore: session close-out`, lands this file.)

`feat/hevy-create-loop` was ff-merged to `master` at `e13e3a2` and pushed
(`b219aa4..1dcce25 master -> master`); local branch deleted. The feature branch was
never pushed to the remote (master carried it forward by fast-forward), so there is no
remote ref to delete.

**Concern-split, as briefed:**
- `d5aadc8` — S2 pure refactor: `sync_one_user(db, user_id, api_key)` lifted out of
  `sync_exercise_templates`' per-user loop. Behaviour-preserving; `test_hevy_templates.py`
  green with zero test changes (4 passed).
- `9d5487e` — S1 connector method + S3 `create_and_resolve` + tests
  (`test_hevy_create_loop.py`, 9 new). Full backend suite 38/38 green.
- `a029a0b` / `e13e3a2` — governance (DECISIONS_LOG #65, Q14 flip, BRANCHES ledger),
  number claimed at ff-merge.
- `1dcce25` — BRANCHES.md marked LANDED.

## 2. Pending-queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — the input was a
build brief (ANCHOR/OBJECTIVE/STEPS/GATES/LOG/GUARD), not a `PENDING` queue. Reconciling
against the brief's own deliverables instead:

| Brief item | Landed? |
|------------|---------|
| S1 `create_exercise_template` connector (typed 403/400) | ✅ `9d5487e` |
| S1 VERIFY — request-body shape cited from live spec | ✅ **wrapper** `{"exercise": {...}}`, not flat — corrected before landing; cited in `9d5487e` message + DECISIONS_LOG #65 How-you-know |
| S2 `sync_one_user` extraction (own refactor commit) | ✅ `d5aadc8`, 4/4 green, zero test changes |
| S3 `create_and_resolve` (list-back, custom-subset, bounded retry) | ✅ `9d5487e` |
| S3 tests (a)–(e) + extras | ✅ 9 tests; full suite 38/38 |
| DECISIONS_LOG `#NEXT` entry, integer claimed at merge | ✅ claimed **#65** (`e13e3a2`) |
| Q14 → `resolved → #65` (same governance as LOG) | ✅ `a029a0b`/`e13e3a2` |
| BRANCHES.md carries branch until ff-merge+delete | ✅ `1dcce25` (LANDED) |
| Out-of-scope: resolver-activation wiring | ✅ untouched — `create_and_resolve` calls `resolve_exercise` as a library function only |

Nothing provisional: every briefed deliverable is in a landed commit on `master`.

## 3. Cold-resume handoff

**What landed:** DECISIONS_LOG **#65** — the Hevy create-loop. `create_and_resolve`
(backend, `hevy_templates.py`) mints an app-originated custom exercise on Hevy and returns
its **canonical** id by list-back (create → `sync_one_user` → `resolve_custom_exercise`
within `is_custom=True AND owner_user_id`), never trusting the POST body. The live spec
confirmed POST returns `{"id": <integer>}` while GET returns a string UUID — so the re-pull
is load-bearing, and this **resolves Q14**. Idempotency pre-check short-circuits an existing
default (#60 default-wins) or the user's own custom; 403/400 map to typed connector errors;
created-but-unresolved raises `HevyCreateUnresolvedError` (never silent None). No schema
change; SCHEMA.md untouched; no migration.

**Current sprint (ROADMAP NOW):** HC permissions fix (record types 38/35/11/37); Samsung
Health package-name correction (`com.sec.android.app.shealth`, verify via Railway Postgres);
morning check-in screen (Hooper Index); persistent conversation history; UI bugs (session
cards not clickable, dual-panel scroll); `mcp_server.get_hevy_workouts` unimported `Session`
one-line fix.

**Open questions by status:**
- `resolved → #65`: **Q14** (Hevy create-loop id contract — POST returns int, list-back
  adopted).
- `open`: **Q15** (`3497ab483935` prod-drift reconciliation — resolve against Railway
  Postgres, not local); **Q16** (`hevy.py` `get_exercise_history` path).
- `verifying`: **Q4** (HC sleep⇄scraper same-date — deferred to live re-sync / G4 on Railway,
  per #64).

**Single clearest next action:** **Hevy resolver activation** (ROADMAP NEXT) — wire
`context_builder` to emit exercise titles so the landed #60/#61 resolver (and now the #65
create-loop) actually fire in the provisioning path; requires the byte-parity guard
re-baseline and a title-match policy decision (exact-canonical vs fuzzy). This ships the
currently-dormant capability that #65 depends on for real use.

**Governance stores changed this session:** `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`
(+ `BRANCHES.md` ledger, `CLAUDE.md` Recent-landings). Pre-merge copy-back = `cat`/open of
each file on disk; chat never regenerates from memory.
