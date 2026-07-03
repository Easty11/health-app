# CLAUDE.md — health-app

Read this in full at the start of every Code session. It is the contract the
session rituals enforce and the loop conforms to. If a pasted document, prior
summary, or habit contradicts this file, this file wins.

---

## Orientation (this repo)

- `health-app` — FastAPI (Python) backend + React/Vite frontend, deployed on Railway.
- Part of a three-module health intelligence platform — Fitness, Medical Protocol,
  Decision Support — on a shared event timeline. It is a health intelligence platform,
  not a fitness app.
- Companion app is a separate repo (`health-connect-app`, Expo React Native, Android-first).
  Not in this tree.

---

<!-- ════════════ BEGIN SHARED LOOP RULES ════════════ -->

## Shared loop rules — edit in `health-app`, propagate verbatim

*Everything from this heading down to "END SHARED LOOP RULES" is identical across every
repo in this project. Edit it only here, then copy it verbatim into
`health-connect-app/CLAUDE.md` and any future repo. Never edit a copy in place — that
re-creates the two-master drift this whole model exists to kill.*

### The loop (source-of-truth model)

- The **repo is the single source of truth** for all volatile state.
- **Code — and the `@claude` GitHub Action — is the only writer.**
- **Chat proposes; chat never commits.** The claude.ai GitHub connector grants chat
  read/attach only. Any instruction that has "chat commits", "chat writes a spec to the
  repo", or "chat files an issue" is wrong on this surface — chat emits text, a human or
  Code carries it across, Code/Action writes it.
- **The commit is the only sync point. Truth changes only at a commit.** Anything decided
  in chat is *pending* until a commit lands it. Treat an uncommitted decision as
  provisional, not done.
- **Read-back path:** repo → chat via Projects sync (the repo file is mirrored into the
  project and refreshed automatically), or by attach. Chat reads the mirror already in
  context; it keeps no separate editable copy.
- **Kill-rule:** decisions, open questions, roadmap, and task state are **never** saved
  into Claude.ai project knowledge. That is the exact mechanism that produced the drift
  this model exists to kill. Project knowledge holds stable orientation docs only.

### Canonical stores

| Store | Holds | Discipline |
|-------|-------|-----------|
| `DECISIONS_LOG.md` | Architecture decisions | Append-only. Supersede via a new entry that references the superseded number. Never edit a locked entry in place. |
| `OPEN_QUESTIONS.md` | Undecided forks, unverified-at-machine items | One status per item: `open` / `verifying` / `resolved → #`. |
| `ROADMAP.md` | Current sprint + horizon | Mutable. Code updates it at close-out. |
| `FEEDBACK.md` | Behavioural corrections and standing rules | Repo-canonical. Code reads it at session start. The project-knowledge copy is a refreshed mirror, not the master. |
| `ptb-tasks` (external board) | Task status | Single live board. Mutable. Referenced by task ID — never mirrored into the repo. |
| pending-commit queue | The chat → Code handoff payload | Transient. Emitted by the chat close-out as canonical-format entries flagged `PENDING`. Carried by paste, or materialised as a GitHub issue for `@claude`. Consumed at the next Code open, then discarded. Not a stored repo file. |

**Stays in project knowledge, never in the repo** (stable, chat-analysis context):
`Clinical_Protocol`, `Athlete_Profile`, lab PDFs, `Stack`, `API_CONTRACTS`,
`Hevy_Pattern`, `Readiness_Algorithm`.

### DECISIONS_LOG discipline

Preserve the existing entry format:

> **Decision · Rationale · Status · How you know · Do not revisit unless**

- Append-only. To change a decision, add a new entry that supersedes the old one by
  number. Do not edit a locked entry's text — the history is the point.
- Every decision that gates code carries a **How you know** artifact: a confirmed test, a
  verified search result, or official documentation. "The API has a field for it" is
  insufficient. Founding rule, earned from the HRV pipeline failure.
- **Number-at-merge.** On a branch, a new entry is headed `### #NEXT`. The integer is
  claimed only when the governance commit fast-forwards to master (next sequential at that
  instant). Eliminates the two-branches-both-claim-#N collision and the
  renumber-on-`--ff` dance.

### Session rituals (the contract the close-outs conform to)

The trigger is not the payload. The payload is defined here; the snippet/command bodies
must match it.

- **Session open** — at session start, before acting on any brief, Code reports the current
  `DECISIONS_LOG.md` max decision number (matching the file's actual `###` heading format).
  Chat re-aims any brief against it, so a stale project copy never masquerades as canon.
- **Chat close-out (`;cc`)** emits the **pending-commit queue**: canonical-format
  `DECISIONS_LOG` / `OPEN_QUESTIONS` entries for everything decided that session, each
  flagged `PENDING`, ready to paste or file as an issue with zero reformatting. Writes
  nothing to project knowledge.
- **Code close-out (`/closeout`)**:
  1. Reads the canonical stores.
  2. Reports the **actual commits** made this session (`git log` since open) — not
     suggested commit messages.
  3. **Reconciles the pending-commit queue**: confirms each `PENDING` item landed in a
     commit, or states why not.
  4. **Branch terminal-state gate** — every branch touched this session ends
     merged+deleted or listed in `BRANCHES.md`; none in undefined limbo. The gate
     enumerates local branches (`git branch`) as well as `refs/remotes/origin`; a local
     branch with `+` commits vs `origin/master` must be pushed, parked in `BRANCHES.md`,
     or discarded before close. If any touched branch is neither, the close-out HALTS
     until resolved.
  5. Regenerates the cold-resume handoff view from the stores.
  6. Overwrites a single `closeout.md`. Never appends narrative; never describes the act
     of writing the close-out.
  7. Writes the close-out body verbatim to `closeout.md` and prints only a terse pointer to
     stdout — path, branch, single next action, and the filenames of governance stores
     changed this session (`DECISIONS_LOG` / `OPEN_QUESTIONS` / `ROADMAP` / `FEEDBACK` /
     `Ideas`; names only, never contents). It does not emit store text; pre-merge copy-back
     is `cat`/open of the changed store file on disk. Chat replaces the project copies
     wholesale from those files and never regenerates these stores from memory.
- `/compact` is mid-session context compression, **not** a close-out. Do not conflate.

### Project-wide standing rules

- **Windows / PowerShell only.** No Linux syntax — no `head`, no backslash line
  continuation. Single-line, or PowerShell backtick continuation.
- **Verify before design.** Verify data paths end-to-end before designing against them.
  Standing rule after the HRV pipeline failure.
- **Empirical specificity.** A recorded test result must state the exact pathway
  exercised and the payload returned — never the generalised conclusion. "X is not
  available via AccessLink" is an assertion; "the exercise summary JSON returned no
  per-second field" is a fact. A negative is only as broad as its recorded scope — do
  not widen it to the whole route/API/device. Mirror of the rule above: as "the API has
  a field" doesn't prove capability, "a test failed" doesn't prove absence.
- **Device-agnostic schema.** All health data is normalised to a `source`- and
  `confidence`-tagged schema before any algorithm or AI layer. The intelligence layer
  never references device-specific schemas.
- **Data verification = Postgres query against Railway**, not on-device UI.
- **Branch disposition (patch-id, never SHA).** Merged-vs-pending is decided by
  `git cherry origin/master <branch>` (`-` = patch-upstream, delete; `+` = real work),
  never `merge-base`/`rev-list` — rebase/squash merges rewrite SHAs and make ancestry lie.
  Every branch not master lives in `BRANCHES.md` (repo root) until merged+deleted.
  Install once (git `!` aliases run in git's own sh; the invocation is single-line
  PowerShell-safe):
  `git config --global alias.stale '!f() { git fetch origin -q; git cherry origin/master "${1:-HEAD}"; }; f'`
  `git config --global alias.land '!f() { b="${1:-$(git branch --show-current)}"; git checkout master && git merge --ff-only "$b" && git push origin master && git branch -d "$b" && git push origin --delete "$b"; }; f'`
- **Branch naming & reuse.** One branch per concern, concern-named
  (`fix/validatenight-dedup`), reused across sessions until merged. Claude Code
  `claude/<session-hash>` auto-names are banned for in-flight work — they spawn duplicates.
- Full behavioural corrections live in `FEEDBACK.md`. Full decision history lives in
  `DECISIONS_LOG.md`. This file points at them; it does not duplicate them.

## END SHARED LOOP RULES — repo-specific below

<!-- ════════════ END SHARED LOOP RULES ════════════ -->

---

## Repo-specific — health-app

### Conventions

- **Hevy:** the canonical creation method is `create_workout`, not `create_routine` —
  custom exercise UUIDs do not resolve via the routine endpoint (confirmed API
  limitation). See `Hevy_Pattern` for the field/type matrix.

### Current sprint

_Code updates this block at each close-out from `ROADMAP.md` / `ptb-tasks`._

- [x] **PLATFORM canon reconciliation (this session, `chore/platform-canon-reconciliation`,
      `38061d1` + `0becd43`)** — shadow-store content from the PLATFORM chat/project-knowledge
      session reconciled into canonical repo homes so PLATFORM can collapse to stable
      orientation without data loss (CLAUDE.md kill-rule enforcement, no feature code):
      - **Standing rules** — Empirical Specificity bullet appended to CLAUDE.md's shared
        "Project-wide standing rules" (immediately after "Verify before design.") — a
        recorded test result must state the exact pathway/payload, never the generalised
        conclusion. Prior Art standing rule appended to FEEDBACK.md §2.13 — search
        developer forums/prior art before building third-party integrations, weighted
        asymmetrically ("can't be done" bankable provisionally; "works" needs
        re-verification against current platform state).
      - **Canon state** — four ROADMAP NEXT rows landed for the medical-spine build (lab
        upload pipeline, interpretation layer, appointment brief, `user_health_state`
        materialised view); OPEN_QUESTIONS Q8 filed `open` for the event-spine schema fork
        (`health_events`+`user_health_state` spine vs organic schema + overlay), which the
        `user_health_state` roadmap row is gated on.
      - **Owed:** the Empirical Specificity bullet is a shared-block change — verbatim
        propagation to `health-connect-app/CLAUDE.md` is a mandatory separate HCA session
        (not done here, single-repo scope). Also owed: pushing local `master` to
        `origin/master` — 2 commits ahead, not yet pushed this session.
- [x] **#42 per-user context isolation (this session, `fix/chat-context-per-user` +
      `fix/mcp-oauth-identity` + `docs/decisions-per-user-context`)** — the multi-user gap
      (any new user got Luke's identity/injuries/data) closed on both surfaces it lived on:
      - **Chat context (P1):** `_section_user_profile` no longer hardcodes Luke — identity
        was already dynamic (`_section_identity`), injuries already rendered per-user
        (`_section_schedule` from `type="injury"` entries); only the device/method mapping
        was truly orphaned, now a `type="preference", key="device_profile"` entry in
        `user_knowledge_entries`. Empty-profile users get a new onboarding-interview
        section that elicits scope then profile facts via the *existing* `knowledge_update`
        write path — no second store. `seed_engine.py` extended (not duplicated) to seed
        the device profile alongside its existing injury seeding.
      - **MCP identity (P2):** `oauth_provider.authorize()` no longer auto-approves —
        gated through a new `/mcp/login` form re-checking against the real `users` table;
        every issued token now binds to that `user_id`. All six `mcp_server.py` tools had
        `user_id: int = 1` removed entirely (no override param). Also fixed a second
        Luke-leak found in passing: `get_readiness_snapshot`'s hardcoded injury text, now a
        live per-user query.
      - Verify-first (standing rule) found the original brief's premise wrong before any
        code was written: `has_structured_profile` gated off `fortification_profiles`
        while `knowledge_update` writes landed in `user_knowledge_entries` — disjoint
        stores, resolved via `user_knowledge_entries` as canonical (user decision, this
        session). DECISIONS_LOG #42 carries the full "How you know" — all four gates
        (G1–G4) exercised against real code paths on local SQLite, not mocked/asserted.
      - **Owed:** `seed_engine.py` has not been run against Railway Postgres yet (no
        Railway credentials in this session) — Luke's device/injury facts are seeded
        locally only; production still reads an empty structured profile until this runs
        (ROADMAP NOW). Also found and logged but left untouched (out of scope):
        `mcp_server.get_hevy_workouts` references an unimported `Session` type (ROADMAP
        NOW); a fourth injury (right proximal semimembranosus) documented in `FEEDBACK.md`
        §5 was never in the seed data this session reused verbatim (OPEN_QUESTIONS Q7).
- [x] **#41 governance consolidation (prior session, `chore/governance-consolidation`)** —
      three remaining governance debts cleared in one concern-split branch (Rule 5 note:
      two commit-groups, store-currency + gate, consolidated by explicit decision):
      - **Store-currency:** OPEN_QUESTIONS Q2 flipped open → resolved — fixed in HCA
        `36df9a2` (`collapseSleepSessions()` de-dups overlapping SleepSessions, 9/9
        behavioral verification, patch-present on HCA master). DECISIONS_LOG
        "Things tried and abandoned" Polar line ("Flow → HC bridge is sufficient")
        annotated superseded-by-#17 in place — mutable appendix, no numbered entry
        touched, no new number minted (#17 controls).
      - **#41 gate extension:** #40's terminal-state gate + `stale`/`land` keyed on
        `refs/remotes/origin` only; local-only unpushed branches escaped the disposition
        net (HCA `fix/scraper-sh-relayout` carried 3 unpushed `+` commits invisible to
        every remote-based check). SHARED-block close-out bullet + `/closeout` step 4 now
        enumerate local branches (`git branch`) alongside remotes — a local branch with
        `+` vs `origin/master` must be pushed, parked in `BRANCHES.md`, or discarded
        before close. **Verbatim SHARED-block re-mirror owed to `health-connect-app`**
        (separate 2-min session — a copy, not a hand-merge, per HCA #16's block
        establishment).
- [x] **#40 branch & session lifecycle protocol (prior session,
      `chore/branch-lifecycle-protocol`)** — Rules 2–5 landed (Rule 1 delete-on-merge
      already live via GitHub settings, both repos, 2 Jul 2026): patch-id disposition
      (`git cherry`, never SHA ancestry) + `stale`/`land` aliases; `BRANCHES.md` ledger +
      branch terminal-state gate as `/closeout` step 4 (steps renumbered 1→9);
      number-at-merge (`### #NEXT` on-branch, integer claimed at `--ff`); concern-named
      branches, `claude/<session-hash>` auto-names banned for in-flight work. Four stale
      remotes pruned after zero-`+` `git cherry` verification
      (`chore/governance-session-lifecycle`, `docs/readiness-banister-canon`,
      `fix/samsung-hrv-backend-reconcile`, `chore/closeout-emit-retire`) — health-app is
      master-only; `BRANCHES.md` starts empty. **Mirror owed to `health-connect-app`**
      (separate session): SHARED block verbatim + its own `/closeout` gate + `BRANCHES.md`
      + its own DECISIONS_LOG claim (next canon = #16, since #34 voided the phantom #16).
- [x] First reconciliation — `DECISIONS_LOG.md` brought current: v3→v4 (#17),
      repo-canonical (#25), GitHub-inbound (#26), espanso-ritual (#27) logged; loop
      rituals committed (`11c82f1`).
- [x] **#36 + #37 MERGED to master this session (PR #8, rebase → linear)** — backend
      per-record writer-identity capture on `/health-connect/sync`, the wire-contract enabler
      for backend F1. Authored prior session on `feat/sync-writer-identity`; landed on master
      this session at `194ecd8` (#37 feature), `91e4d6a` (#36 governance), `44250cf` (branch
      close-out):
      - **#37** — new per-record table `health_connect_record_sources` captures
        `(record_type, record_start, source_package)` BEFORE `_aggregate_day` via
        `_capture_record_sources()`; `dataOrigin.packageName` (raw) + `sourcePackage` (alias)
        on every record model via a `WriterIdentity` mixin (#24 dual-field). Migration
        `c9b8a7d6e5f4`. `health_connect_syncs` untouched.
      - **#36** — source-priority dedup is **backend**, not on-device; HCA reduced to a
        faithful relay forwarding `dataOrigin.packageName`. Resolves #35's open F1 fork.
- [x] **Writer-identity key hardening (`4985ff3`, PR #8 review fix — this session)** — a review
      of the branch surfaced 3 findings; fixed 1 + 3, logged 5:
      - **Finding 1** — `uq_hc_record_source` now spans
        `(user_id, record_type, record_start, source_package)` so two apps at the same
        `(type, timestamp)` persist as two rows (the multi-writer signal F1 needs). Missing
        identity coalesces to sentinel `'unknown'` (a real NULL is UNIQUE-distinct on
        SQLite + Postgres, which would break re-sync idempotency). **Supersedes #37's
        "natural key collapses them" caveat — no new decision minted (Easty signed off at
        merge).** Migration edited in place (unreleased). `NULLS NOT DISTINCT` rejected:
        needs PG15+ and is unsupported on the SQLite test path.
      - **Finding 3** — `synced_at` migration column aligned to `NOT NULL` + `server_default`,
        matching the model.
      - **Finding 5** — non-atomic check-then-insert upsert logged as tech-debt (Known-open
        issue #14): swap to atomic `ON CONFLICT` before multi-tenant. Findings 2/4 left by design.
      - Re-verified on isolated SQLite: migration up/down clean, two-writers→two-rows,
        idempotent re-sync (0 new), `compare_metadata` zero drift.
- [x] **#38 close-out routing MERGED (PR #9, rebase → linear — this session)** — `/closeout`
      writes its body verbatim to `closeout.md` with pointer-only stdout; step 8
      governance-store emission kept as the one named exception. Luke's `chore/closeout-routing`
      (forked pre-#8, conflicted on `DECISIONS_LOG.md`) was rebased onto master and the conflict
      resolved (#36/#37 kept, #38 appended after — no renumber), landing at `aef8a6b` (command
      edit), `679b03c` (#38 entry).
- [x] **#35 + F2 landed (prior session)** — HC ingest source-of-truth filter. Governance and
      feature concern-split across two `--ff-only` merges, pushed `4352258..6b2ca40`:
      - **#35** (`33a1d54`, governance-only) ratifies the source-priority filter as TARGET
        architecture; backend enforcement **BLOCKED** — fork gate verified ABSENT (the
        `/health-connect/sync` payload carries no `dataOrigin.packageName`). Basis is the
        CLAUDE.md device-agnostic standing rule (the v1 draft's `#18` cite was wrong — #18
        is Banister/ACWR — and was corrected before append).
      - **F2** (`6b2ca40`, feature) — `_reject_pre2020` drops inbound HC records with a
        pre-2020 (epoch-zero) timestamp before aggregation; count logged + returned as
        `rejected_pre_2020`. Verified live against the real `SyncPayload`.
      - **F1 dropped** (re-routes to HCA), **F3b → HCA** (119% efficiency lives in the
        scraper, not this repo), **#20 enum** confirmed already shipped (`c61dfbc`; Q1 closed).
      - **F3a deferred (gate = RAW):** the set `_aggregate_day` sees is raw multi-app, so
        set-summing would double-count Samsung+Withings duplicate nights — the inflation
        blocked-F1 was to kill. Unblocks only with the upstream HCA dedup (= open Q2).
- [x] **#34 landed (prior session)** — withdrew #31's fabricated companion-repo citation
      (phantom `health-connect-app` "#16" / `findByIdValidBounds`); supersede-by-reference,
      #31 body untouched, its Postgres reconciliation stands. `61c6697`, `7e252a4..61c6697`.
- [x] **master converged #30 → #33** (prior session) — three branches landed linear via
      `--ff-only` (PR #6 / #7 rebased onto master first), pushed `059f869..acb994c`:
      - #5 (#31) Samsung HRV scalar misdate reconcile — `fix/samsung-hrv-backend-reconcile` → `b54fdd0`.
      - #6 (#32, #33) four-window Banister canon + ΔLoad primitive — `docs/readiness-banister-canon` → `5b80d5e`.
      - #7 governance session-lifecycle (FEEDBACK 2.12, closeout emit-stores, session-open report) — `chore/governance-session-lifecycle` → `acb994c`.
- [ ] **Supersede #3** — the one reconciliation entry still owed: Polar not session-only,
      AccessLink live, SDK R-R as highest-fidelity HRV path. Blocked on a *How you know*
      artifact (Polar R-R verification).
- [ ] **Next engineering action — HCA forwards writer identity (HCA session):** in
      `health-connect-app`, forward `dataOrigin.packageName` (+ an HC
      `health_data_category_priority_table` snapshot as policy input) in the
      `/health-connect/sync` payload. **Keystone reframed by #36:** source dedup is now
      backend, so HCA's `validateNight()` *loses* source dedup and is reduced to a faithful
      relay (the old "fix Q2 via cross-app source priority in HCA" framing is superseded —
      that arbitration moved backend). HCA forwarding is the producer half of the wire
      contract whose consumer half (per-record capture) landed this session.
- [ ] **Then — backend F1 filter (backend session):** apply source-priority dedup over the
      `health_connect_record_sources` table built this session. **Gated on** HCA actually
      forwarding the field (the above). Also unblocks **F3a** (frozen-session-set
      aggregation) once F1 lands. Q3 (HR cadence) and Q4 (date attribution) run in parallel.
- [x] **Deploy — auto-applies.** `feat/sync-writer-identity` merged to master (PR #8), so
      migration `c9b8a7d6e5f4` applies on the next Railway deploy — the start command runs
      `alembic upgrade head` (`backend/Procfile` / `backend/railway.toml`). No manual step
      owed; confirm the deploy log shows `upgrade head` succeeds and the container is healthy
      (not verifiable from this session — no prod DB access).
- [x] **Remote branch cleanup — DONE this session.** The prior session's git-proxy 403 on
      ref deletes did not recur; `chore/governance-session-lifecycle`,
      `docs/readiness-banister-canon`, `fix/samsung-hrv-backend-reconcile`, and
      `chore/closeout-emit-retire` deleted after zero-`+` `git cherry` verification
      (`chore/closeout-routing` already absent from origin — verified via `git ls-remote`).
      Post-prune, `git ls-remote --heads origin` shows master only.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
