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
  4. Regenerates the cold-resume handoff view from the stores.
  5. Overwrites a single `closeout.md`. Never appends narrative; never describes the act
     of writing the close-out.
  6. Emits the full current text of every governance store touched this session
     (`DECISIONS_LOG` / `OPEN_QUESTIONS` / `ROADMAP` / `FEEDBACK` / `Ideas`) for wholesale
     project-copy replacement — not a prose summary. Chat replaces the project copies
     wholesale and never regenerates these stores from memory.
- `/compact` is mid-session context compression, **not** a close-out. Do not conflate.

### Project-wide standing rules

- **Windows / PowerShell only.** No Linux syntax — no `head`, no backslash line
  continuation. Single-line, or PowerShell backtick continuation.
- **Verify before design.** Verify data paths end-to-end before designing against them.
  Standing rule after the HRV pipeline failure.
- **Device-agnostic schema.** All health data is normalised to a `source`- and
  `confidence`-tagged schema before any algorithm or AI layer. The intelligence layer
  never references device-specific schemas.
- **Data verification = Postgres query against Railway**, not on-device UI.
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

- [x] First reconciliation — `DECISIONS_LOG.md` brought current: v3→v4 (#17),
      repo-canonical (#25), GitHub-inbound (#26), espanso-ritual (#27) logged; loop
      rituals committed (`11c82f1`).
- [x] **#36 + #37 landed this session** — backend per-record writer-identity capture on
      `/health-connect/sync`, the wire-contract enabler for backend F1. Branch
      `feat/sync-writer-identity`, pushed; concern-split per #27:
      - **#37** (`417c1bd`, feature) — ingest read confirmed **Case (b)** (`_aggregate_day`
        collapses to one daily row; writer identity verified ABSENT). New per-record table
        `health_connect_record_sources` captures `(record_type, record_start, source_package)`
        BEFORE aggregation via `_capture_record_sources()`; optional `dataOrigin.packageName`
        (raw) + `sourcePackage` (alias) on every record model via a `WriterIdentity` mixin
        (#24 dual-field). Nullable end-to-end (no 422 for current HCA builds); idempotent via
        `uq_hc_record_source`. Migration `c9b8a7d6e5f4` up→down→up clean in isolation (#21).
        OpenAPI publish + round-trip (with→stored, without→null, both 200) + idempotency all
        verified. `health_connect_syncs` untouched. **Not yet applied to Railway/Postgres.**
      - **#36** (`ddfd8c7`, governance) — source-priority dedup is **backend**, not on-device;
        HCA reduced to a faithful relay forwarding `dataOrigin.packageName`. Resolves #35's
        open F1 fork; supersedes its "or filters read-side" horn as a false fork.
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
- [ ] **Deploy** — apply migration `c9b8a7d6e5f4` to Railway/Postgres when
      `feat/sync-writer-identity` merges to master.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
