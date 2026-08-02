# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-02, **amended 2026-08-03 at the merge**. Branch at close: none — `feat/hevy-template-sync-wiring` ff-merged to master at `9c8176a` and deleted both sides.
Session-open ref: `d11b2b8`. Session-open `DECISIONS_LOG` max on master: **161** (counted
`^### [0-9]+`, period-agnostic). The brief was written against #161 / Q74 — no re-aim needed.

**The Hevy exercise-template sync now has call sites; the population half of the prod gate is
still OWED.** The operator endpoint and the connect-time seed are built, tested, merged (`9c8176a`)
and deployed. Post-merge the route is live and auth-gated — see §2 — but the authenticated POST that
actually repopulates the catalogue has not been taken, so the gate is **not claimed**.

## 1. Real commits this session

`git log --oneline d11b2b8..HEAD`:

```
c7bed98 governance: #NEXT (sync wiring), Q#NEXT (recurring-sync fork), BRANCHES row
2f377ad feat(hevy): #NEXT wire the exercise-template sync — operator endpoint + connect-time seed
```

Plus this close-out commit. Both pushed to `origin/feat/hevy-template-sync-wiring`;
`git cherry origin/master HEAD` reports both as `+` (real, unmerged work).

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-08-02 governance: #NEXT (sync wiring), Q#NEXT (recurring-sync fork), BRANCHES row
2026-08-02 feat(hevy): #NEXT wire the exercise-template sync — operator endpoint + connect-time seed
2026-08-02 chore: session close-out
2026-08-02 feat(frontend): #150 hub shell — tile grid on /dashboard, chat docked, panels relocated
2026-08-02 governance: question-state vocab (carve+sweep), Q65 collapse, Q73/Q74, FEEDBACK §22, CLAUDE accretion compress, ROADMAP NEXT reconcile
2026-08-02 governance: renumber #NEXT -> #161 and land; Q72 carries the owner's position
2026-08-02 governance: #NEXT (verdict-vs-measurement scoping), Q72, BRANCHES row
2026-08-02 feat(engine): capability_observations — graded, timestamped measurement
2026-08-01 chore: session close-out
2026-08-01 governance: resolve #NEXT -> #160 (on-branch, pre-ff)
```

### What landed in code

`backend/routers/integrations.py` — `sync_exercise_templates` gains its two call sites:

- `POST /integrations/hevy/sync` — `async def`, `get_current_user` auth, calls
  `sync_exercise_templates(db, only_user_id=current_user.id)` and returns the summary verbatim.
  Scoped to the caller: a user-facing route never runs a family-wide sync.
- `connect_hevy` — converted `def` → `async def`; after the key's `db.commit()` it calls the
  **same** path. Ordering is load-bearing: the commit is what makes the key visible to
  `users_with_hevy_key`, which the sync reads.
- `_sync_failure(summary)` — the failure signal mapped to HTTP. `users_attempted == 0` → 404
  carrying the byte-identical body `_require_integration` produces
  (`"hevy integration not connected"`); `users_failed >= 1` → the recorded error routed through
  the existing `_hevy_error_to_http` choke point. A failed run is never a 200 with a silent zero.
- `_SYNC_ERROR_TYPES` / `_sync_error_to_http` — the summary keeps only
  `f"{type(exc).__name__}: {exc}"`, so the two types whose mapping is not the 502 default
  (`HevyAuthError`, `HevyForbiddenError`) are rehydrated from that string. Without this a revoked
  Hevy key would flatten to 502 and quietly undo `#66`'s 401→424 decoupling — whose whole point is
  that a dead *connector* key must not log the user out of the app.
- Connect-time seed failure: 201 stands (storing the key is the request's contract) and the failure
  is **not** swallowed — the response body gains `sync`, carrying the summary (whose `users_failed`
  / `rows_processed` expose a partial run) or a failure shape.

`backend/hevy_templates.py` is **untouched** — the summary contract, per-user isolation and the CLI
keep their behaviour. No migration, no schema change. The routine contract,
`context_builder._section_routine_creation` and `chat.py`'s block parser were not edited; the
brief's scope fence held. Custom-exercise creation (`<hevy_create_exercise>`) is step 2 and is not
started.

### Tests

`backend/tests/test_hevy_sync_wiring.py`, 16 new tests. Full backend suite **594 passed**
(baseline on `master` before the branch: **578**).

```powershell
cd C:\Users\lukee\Projects\health-app\backend; .\.venv\Scripts\python.exe -m pytest -q
```

Two choices worth carrying forward:

- The tests drive the **routes** over a standalone `FastAPI` app with `get_db` /
  `get_current_user` overridden — not the handler objects, as the house pattern in
  `test_connector_error_policy.py` otherwise does. The defect being fixed is precisely "the
  function exists and nothing reaches it"; a handler-object call would prove the body and skip the
  wiring, which is the only thing under test.
- **Paired negative controls** (`FEEDBACK` §17, `#103` — a control must discriminate on identity,
  not just function). Renaming the route to `/hevy/sync-UNWIRED` fails **6 of 16** and passes the
  10 that never touch that path; replacing the connect-time seed call with a literal fails the
  **4** connect tests and passes the other 12. Each control fails exactly its own half, so neither
  half is being carried by the other. The keyless-caller assertion checks the **detail string**,
  not just the status code, because an unregistered route also returns 404 and would otherwise pass.

## 2. Pending-queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — the brief arrived as prose, not
as `PENDING` canonical entries. Reconciled instead against the brief's own deliverables:

| Brief item | Landed? |
|-----------|---------|
| `POST /integrations/hevy/sync`, async, `get_current_user`, `only_user_id=current_user.id`, summary verbatim | **YES** — `2f377ad` |
| `users_failed >= 1` → error through `_hevy_error_to_http`; `users_attempted == 0` → 404 | **YES** — `2f377ad` (`_sync_failure`) |
| `connect_hevy` → `async def`, seed after `db.commit()`, same path | **YES** — `2f377ad` |
| Seed failure never fails the key store; reported in `response.sync` | **YES** — `2f377ad` |
| Unit tests: endpoint 200 / non-200 / 404, connect-seed happy + raising | **YES** — 16 tests, `2f377ad` |
| Full backend suite green, count reported | **YES** — 594 passed (was 578) |
| **Prod population gate, paired before/after** | **NO — OWED.** See below. |
| `DECISIONS_LOG ### #NEXT` | **YES** — `c7bed98`, resolved to **#163** at the ff |
| `OPEN_QUESTIONS Q#NEXT` (recurring sync deferred) | **YES** — `c7bed98`, resolved to **Q75** at the ff |
| Branch pushed even while held (`#98`) | **YES** — `origin/feat/hevy-template-sync-wiring` |

### The prod population gate — BEFORE recorded, route deployed and gated, POPULATION half owed

Read via `railway run --service health-app-DB` over `DATABASE_PUBLIC_URL` (`#56` — `railway run`
injects the private-network hostname, unresolvable from a laptop), printing counts only and never a
credential (`#111`):

```
hevy_exercise_templates total=494 defaults=451 customs=43
max_synced_at=2026-07-14 12:09:06.888252+00:00
user_integrations provider=hevy rows=3
```

So the table is **not** the zero-row substrate `FEEDBACK` §8 recorded — the one-off CLI run of
2026-07-14 populated it, and `max(synced_at)` shows nothing has touched it since. That is the
precise state this wiring exists to end: populated once by someone remembering, never by the
application.

**Post-merge (2026-08-03), the deploy half passes on both axes.** Timing (`#116`):
`railway deployment list --service health-app-backend` reports `34cda96f` **SUCCESS** at
2026-08-03 07:38. Coverage (`#121`): the live `openapi.json` now lists **six** `/integrations/hevy*`
paths including **`/integrations/hevy/sync`** — it listed five before the merge. Unauthenticated
`POST /integrations/hevy/sync` returns **401** while `POST /integrations/hevy/sync-does-not-exist`
returns **404**: a paired control discriminating on identity, so the 401 proves the route is
registered and auth-gated rather than merely missing.

**What is still owed: the authenticated POST, owner Luke.** Code cannot take it — it needs a session
token, and handling the operator's credentials is prohibited regardless of who offers them. The
population half is therefore unproven and the gate is **not claimed**.

**One correction for whoever runs the after-half.** The paired before/after count is the right
control, but its signal here is not what a naive read expects: the sync is **upsert-only** (`#77` —
the Hevy API cannot delete templates) and the table already holds 494 rows. On a healthy prod the
after-count is expected to be **494 unchanged, not higher** — a zero delta is the success case, not
a failure. The signals that must actually move are `defaults_seen > 0` in the returned summary and
`max(synced_at)` advancing off 2026-07-14. A rising count would additionally mean new templates
exist upstream.

Remaining sequence — merge, deploy and route checks are all discharged above; only these two steps
are left, read one before running the next rather than chained (`#103`).

**Step 1, Luke only.** Open the logged-in app, devtools console, and run this. The token is already
in the browser's `localStorage`; it never leaves the machine and never enters a transcript:

```javascript
await (await fetch('https://health-app-backend-production-760e.up.railway.app/integrations/hevy/sync', {method:'POST', headers:{Authorization:`Bearer ${localStorage.getItem('token')}`}})).json()
```

Read `defaults_seen` off the returned summary — it must be `> 0`. A `users_failed >= 1` means the
stored Hevy key is dead; a 404 means no key is stored for that account.

**Step 2.** Re-run the count:

```powershell
railway run --service health-app-DB -- C:\Users\lukee\Projects\health-app\backend\.venv\Scripts\python.exe C:\Users\lukee\AppData\Local\Temp\claude\C--Users-lukee-Projects-health-app\df14783b-6605-4913-969e-8c50f9c67901\scratchpad\count_templates.py
```

That script is session-scratchpad and prints counts, `max(synced_at)` and the hevy-key row count
only — reproduce it in-repo if the gate outlives the scratchpad.

## 3. Cold-resume handoff

### Branch terminal states (gate PASSED — nothing in limbo)

Local branches: `master`, `feat/cbti-eval-trigger`, `feat/hevy-template-sync-wiring`.

| Branch | `git cherry origin/master` | State |
|--------|---------------------------|-------|
| `feat/hevy-template-sync-wiring` | 2 × `+` (`2f377ad`, `c7bed98`) | **OWED** — pushed, rowed in `BRANCHES.md`. Outstanding: the prod population gate above; command sequence in §2. Owner: Luke. |
| `feat/cbti-eval-trigger` | 2 × `+` (`f30dd49`, `fec0324`) | **Not touched this session** — carried in as the session-open branch, read only, never committed to. Pushed to `origin` and carries its own `BRANCHES.md` row on its own branch. Not in limbo. |
| `master` | — | at `d11b2b8`, clean. |

Remote refs: `origin/master`, `origin/feat/cbti-eval-trigger`, `origin/feat/hevy-template-sync-wiring`.
Nothing unpushed, nothing undiscarded.

### Governance numbering — resolved to #163 / Q75 at the ff-merge

This branch's tokens were resolved on-branch before the fast-forward, per number-at-merge and
`#148` (renumber scope follows the branch's **own** tokens, wherever they live; residuals are
**classified**, not counted).

It took **#163, not #162**. Master already carried one unnumbered `### #NEXT` — the hub-tile
entry, which sits *earlier* in the append-only file and had already been staked as **162** by
`feat/cbti-eval-trigger`. Taking 162 here would have numbered this entry below an entry that
physically precedes it, and collided with that branch. So 162 stays owed to the hub-tile
placeholder, and master carries a visible, explained gap until `feat/cbti-eval-trigger` lands.

Residual `#NEXT` tokens left deliberately, classified per `#148`: the rule text in `CLAUDE.md`
(number-at-merge) and `ROADMAP.md` L19; the hub-tile entry in `DECISIONS_LOG.md` and its
`DONE → #NEXT` in `OPEN_QUESTIONS.md`; other branches' `BRANCHES.md` rows; the historical
`#NEXT` references inside locked entries; and the quoted `git log` commit messages in §1, which
are immutable and must not be rewritten.

### Current sprint

`ROADMAP.md` NOW is unchanged by this session and still carries: CBT-I `Q45` nap day-attribution
(dated, contaminating capture now), CBT-I `#118` PM evaluation trigger (built on
`feat/cbti-eval-trigger`, unmerged), the lab upload pipeline, the interpretation layer build (4b-ii
closed; increments 2 / 3 / 5 unstarted), and the two cross-repo OWED rows.

`ROADMAP.md` NEXT gained one row: **Hevy custom-exercise creation (step 2)** — the
`<hevy_create_exercise>` wiring, explicitly gated on the step-1 prod gate closing, because
`create_and_resolve`'s idempotency pre-check reads `hevy_exercise_templates` and a stale or empty
catalogue makes it mint duplicate templates rather than short-circuit. A wrong write, not a missed
read.

### Open questions touched

- **`Q75`** (new, OPEN, gated on nothing) — the catalogue now gets populated on connect, but
  nothing keeps it fresh. Three independent drift sources: Hevy renames its defaults (`#79`/`#81`,
  already a live phenomenon and the reason `catalogue_titles_by_id` exists), the user adds customs
  in the Hevy client directly, and the sync is upsert-only so drift only accumulates. Candidates:
  (a) cron, (b) sync-on-read-staleness, (c) sync-on-workout-fetch. The axis to decide first is what
  freshness is *for* — (b) and (c) refresh only what a read touches, (a) is the only one that
  catches drift before a read needs it, and that distinction only bites once a **write** path
  depends on the store being current. Resolve-before: custom-exercise creation.
- No existing question was resolved or restated. `Q74` (the brief's stated aim point) was not
  touched.

### Single clearest next action

**Luke runs the authenticated POST** (the devtools one-liner in §2), then the count script — and
the assertion is `defaults_seen > 0` plus `max(synced_at)` advanced off 2026-07-14, **not** that the
row count rose. Everything else on the gate is discharged: merged, deployed, route live and
auth-gated. Until that one call lands, the catalogue is still the July hand-run CLI's output, which
is the exact `FEEDBACK` §8 state this work exists to end — and **step 2 (custom-exercise creation)
must not start**, because `create_and_resolve`'s idempotency pre-check reads this substrate and
would mint permanent duplicates against a stale copy.
