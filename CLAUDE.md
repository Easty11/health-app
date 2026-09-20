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

Identical across all repos in this project. Edit only here; copy verbatim into each other
repo's CLAUDE.md. Before copying, verify any grammar-dependent line (regex counts, store
paths) against the destination's actual file shape — if the source line is wrong for the
destination, fix it here first, then copy. Never hand-merge, never edit a copy in place.

Rules whose correctness depends on unversioned config (CI checks, local aliases) are
repo-specific and live below END SHARED LOOP RULES in their own repo.

### The loop
- The repo is the single source of truth for all volatile state.
- Code is the only writer. Chat proposes; chat never commits.
- The commit is the only sync point. An uncommitted decision is provisional.
- Read-back: repo → chat via Projects mirror or attach. Chat keeps no editable copy.
- Kill-rule: decisions, open questions, roadmap, task state never live in project
  knowledge — orientation docs only.

### Merge disposition
- **Code merges its own PRs.** The merge path's three acts are one motion: push, create,
  merge. PRs open **ready-for-review, never draft**, and Code merges as soon as every
  required check is green — no confirmation request, no waiting on the operator, and no
  scheduled check-in re-reporting a clean `mergeable_state`. A green PR left unmerged is a
  defect, not caution.
- **Origin creates no lane; draft is not a hold.** When the harness opens a PR as draft,
  flip it ready-for-review and self-merge on green the same turn. A PR merged in-turn ends
  its own subscription, so no check-in is scheduled. Session origin (harness vs local) never
  justifies an operator hand-off or a merge-watch. (Supersedes the Q125 two-lane convention.)
- **Holds — do not self-merge, wait for explicit operator instruction:** a PR containing a
  schema migration; anything the session was told to hold.
- **Un-ratified decisions route to chat — the one warranted merge-time friction.** If a PR
  embeds a call chat did not ratify (a resolved OPEN_QUESTION, a minted constraint/ordering
  rule, or a data-meaning default), hold it, surface the *decision* — not the diff — for
  ratification, and end the turn; a later session lands and closes it out. Implementing a
  chat-approved brief with no new judgment is already ratified: self-merge. Raising a new
  question needs no hold; resolving one does.
- Number-at-merge is unaffected: it resolves from master's max immediately before the merge
  Code itself performs.
- This is deliberate. A future session finding Code self-merging must not reinstate a human
  gate as a fix — see DECISIONS_LOG.

### The unseeable-surface rule
Chat can verify only what is on a pushed ref. Any brief statement about a surface chat
cannot read (UI knowledge files, unpushed branches, local disk, Railway state) is an
INSTRUCTION TO VERIFY, never a report of fact. Verify or STOP; never land on it.

### Canonical stores
| Store | Holds | Discipline |
|-------|-------|-----------|
| `DECISIONS_LOG.md` | Architecture decisions | Append-only; supersede by new entry, never edit locked text. |
| `OPEN_QUESTIONS.md` | Undecided forks | One `**State:**` per item: OPEN / OWED / DONE → #N. |
| `ROADMAP.md` | Current sprint + horizon | Mutable; Code updates at close-out. |
| `FEEDBACK.md` | Behavioural corrections, condensed verification rules | Read at session start. |
| `FEEDBACK_ARCHIVE.md` | Full provenance essays | NOT read at session start. |
| `ptb-tasks` (external) | Task status | Referenced by ID, never mirrored in. |
| pending-commit queue | Chat → Code handoff | Transient; emitted at chat close-out, consumed at Code open. |

Stays in project knowledge, never in the repo: `Clinical_Protocol`, `Athlete_Profile`,
lab PDFs, `Stack`, `API_CONTRACTS`, `Hevy_Pattern`, `Readiness_Algorithm`.

### State vocabulary
Work items: DONE (landed, SHA named) · BLOCKED (names blocker + owner) · OWED (settled,
loop-close named) · UNSTARTED. No "in progress". Questions (`OPEN_QUESTIONS.md` only):
OPEN · OWED · DONE → #N, under the label `**State:**`.

### DECISIONS_LOG discipline
- Entry format: **Decision · Rationale · Status · How you know · Do not revisit unless**.
- Append-only. Every code-gating decision carries a How-you-know artifact (confirmed test,
  verified search, official doc).
- Number-at-merge: entries on a branch are headed `### #NEXT`; resolve the integer by
  re-reading master's max immediately before landing, re-resolve if master advances.
  Enforced by `scripts/check_governance_placeholders.py` via the repo hook
  (`git config core.hooksPath .githooks`, once per clone).

### Session rituals
- **Open:** report both maxima — decisions `^### #?[0-9]+`, questions `^#{2,3} Q[0-9]+`
  (period-, sigil- and level-agnostic; the pinned forms return zero on one repo or the
  other). Chat re-aims any brief against these.
- **Chat close-out (`;cc`):** emits the pending-commit queue as canonical-format entries
  flagged PENDING. Writes nothing to project knowledge.
- **Code close-out (`/closeout`):** reads the stores; reports actual commits
  (`git log --format="%ad %s" --date=short -10`); reconciles every PENDING item;
  branch terminal-state gate — every touched branch ends merged+deleted or in
  `BRANCHES.md`, else HALT.

### Project-wide standing rules
- Windows / PowerShell only for operator commands. No Linux syntax. Avoid embedded double
  quotes in arguments (PowerShell strips them handing to native exes — fails with a
  misleading error). Exercise operator commands in PowerShell, not the Bash tool.
- Verify before design — data paths end-to-end first.
- Empirical specificity: record the exact pathway and payload, never the generalised
  conclusion. A negative is only as broad as its recorded scope.
- Device-agnostic schema: all health data normalised to source- and confidence-tagged
  schema before any algorithm layer.
- Data verification = Postgres query against Railway, not on-device UI.
- **Secrets:** never run a command that renders a secret value — no `railway variables`
  in any form (`--kv`, `-k`, `--json`, the `variable` singular, or the bare `list` — all
  print raw values), no `printenv`/`env`, no reading `.env` by any tool. Check existence
  by names only; use values via `railway run <cmd>`; compare values via SHA-256 digests,
  first 12 chars. `.claude/settings.json` deny patterns are a speed bump; this rule is
  the enforcement (#111).
- Branch disposition by patch-id, never SHA: `git cherry origin/master <branch>`
  (`-` delete, `+` real work). Alias `stale` is global; each repo defines its own `land`
  locally and documents its fresh-clone setup below END SHARED LOOP RULES.
- One branch per concern, concern-named. `claude/<hash>` auto-names banned for
  in-flight work.
- **Severity gate on review:** raise as a gate only defects that change an outcome,
  corrupt data, leak a secret, or block the next step. Cosmetic, consistency, and
  wording defects batch into a single trailing "nits" note — never a reason to withhold
  a green-light or halt a land.
- **Governance batching:** at most one `gov(...)` commit per session, at close-out.
  Governance edits never interleave with feature work mid-session.
- Full corrections live in `FEEDBACK.md`; full history in `DECISIONS_LOG.md` and
  `FEEDBACK_ARCHIVE.md`. This file points at them; it does not duplicate them.

## END SHARED LOOP RULES — repo-specific below

<!-- ════════════ END SHARED LOOP RULES ════════════ -->

---

## Repo-specific — health-app

### Merge path — PR-gated (#171)

- **The pull request is the only route to master.** Ruleset `master-pr-gated` (id `20414758`)
  requires a PR + the `placeholder guard (POSIX)` status check, forbids non-fast-forward, and
  has no bypass actors (`current_user_can_bypass: "never"`). Direct `git push origin master`
  is refused server-side.
- **This section is repo-specific** (not shared): a merge path depends on enforcement config
  outside the tree, set per repo. Other repos' state is read live (`gh api`), never asserted
  here (#184).
- **The motion** — three acts, not one:
  `git push -u origin <branch>` → `gh pr create --fill --base master` →
  `gh pr merge --merge --delete-branch`. Never `--auto` (queues a merge instant you don't
  hold — breaks number-at-merge). Never `--admin` (advertised in gh's refusal text; doesn't
  work here).
- **`--merge`, not `--squash`/`--rebase`:** `BRANCHES.md` rows record landing SHAs; squash and
  rebase rewrite the branch's commits so every recorded `DONE <sha>` would dangle. Cost
  accepted: master is not linear.
- **Strict mode forces a pause, not an adjudication.** If master advances between resolving
  `#NEXT` and merging, the merge blocks until the branch is updated and the guard re-runs —
  re-read master's max and re-resolve.

**Fresh-clone setup — health-app.** Two unversioned settings, both absent in a new clone,
neither fails loudly. Run both, then verify:

    git config core.hooksPath .githooks
    git config --local alias.land '!gh pr merge --merge --delete-branch'

Verify with `git config --get core.hooksPath` → `.githooks`, and
`git config --local --get alias.land` — the `--local` is required, or the bare form reads the
merged config and returns a stale global body, reading configured when it is not. `stale` is
global; the ruleset is server-side and needs nothing locally.

**Batched governance landings (#176).** Governance/docs-only edits — touching only
`DECISIONS_LOG`, `OPEN_QUESTIONS`, `BRANCHES`, `ROADMAP`, `CLAUDE.md`, `FEEDBACK`,
`FEEDBACK_ARCHIVE`, `closeout.md`; no code and no migrations — bank onto one branch and land
as one PR per checkpoint. Three invariants:

- **(a)** Nothing lands until its design has settled.
- **(b)** Housekeeping rides its originating branch: the branch writes its own terminal
  `BRANCHES` row and any Recent-landings pointer within itself, resolved at merge.
- **(c)** Gate by diff shape, not file class: a governance batch lands guard-gated only if
  every removed line falls inside a region the change explicitly declares it is replacing;
  any removed line outside a declared replacement region forces human review (the guard
  anchors on placeholder headings and cannot see content corruption).

Schema migrations take full human review (§ Merge disposition, hold (a)). Code changes
self-merge on green under § Merge disposition.

### Conventions

- **`FEEDBACK.md` §19 integrity ledger** (health-app only). The append-only ledger — rows
  typed `HUMAN`/`MODEL`/`COUPLED`, `status` mutable (`STANDS`/`STRUCK`); a row exists only if
  a procedural change would have prevented the failure (`prevention` mandatory), `caused_by`
  derived from `caused` — now lives in `FEEDBACK_ARCHIVE.md` §19 (post-prune). See #129–#132.
- **Hevy:** canonical creation is `create_workout`, not `create_routine` (custom exercise
  UUIDs do not resolve via the routine endpoint — confirmed API limit). Matrix: `Hevy_Pattern`.
- **CBT-I block references.** `cbti_blocks.id` is canonical for any operational reference
  (queries, `--block-id`, scripts). The programme ordinal ("block N") appears only in prose,
  with its `cbti_blocks.id` in brackets on first mention — never as a bare token that could reach
  `--block-id`. The ordinal currently runs +1 of the id (programme "block 3" = `cbti_blocks.id` 2;
  no id=3 row exists), but that offset is NOT a rule to rely on: verify the id against `cbti_blocks`
  before passing `--block-id`, never trust a store's "block N" as an id.
- **SCHEMA.md is repo-canonical** (root), the mirror of `backend/migrations/`. Update it in the
  same commit (or an immediately paired governance commit) as any schema-changing migration; it
  must never lag master.
- **Chat→Code file transport.** A project-knowledge doc crossing to Code is emitted as a raw
  fenced block read byte-faithfully from the mount (never the rendered view, which flattens
  markdown); Code diffs before landing. Repo-canonical docs are edited in place, never cross
  this transport.
- **Reference-JSON edit guard (#98).** `backend/reference/*.json` is hand-aligned pure ASCII
  (non-ASCII as `\uXXXX`). Never build a `\uXXXX` escape in heredoc source (the Bash tool eats
  one backslash even when quoted — use `chr(92)+"u2014"` or a script file); after any edit
  assert `raw.isascii() and raw.count(chr(0x2014))==0` and that it still parses; no `json.dump`
  round-trips. The bad-byte failure is silent — only the assertion catches it.
- **Irreversible-write pre-ship gate (#166, `FEEDBACK` §23).** When a decision's How-you-know
  admits an unexercised write path, ask what its failure COSTS before shipping. Non-destructive
  and loud → ship with an `OPEN_QUESTIONS` watch-point. Able to change state we cannot undo →
  the live probe is the gate, not the launch. Companion: for code interpreting a third party's
  response, at least one test must fake at the TRANSPORT layer.
- **Never chain a verification to an action in one command (#103).** Run it, read it, then act —
  or make the action conditional on its exit status. `FEEDBACK` §17.
- **Controls discriminate on identity, not just function (#103).** Where a probe could hit the
  wrong artefact (stale ref, cached copy, reused branch name), pin to a SHA or assert on content
  only the intended version carries. `FEEDBACK` §17.
- **Match on anchors, not substrings — especially in an audit (#113).** Anchor on the form the
  thing takes (`^### 104\.`, `^## Q45\.`, a whole word), read the matches not the count;
  corrected docs quote the superseded claim by design, so expect the hit. `FEEDBACK` §17.
- **Verify a deploy after it settles; confirm which instance answered (#116).** Check
  `railway deployment list` for SUCCESS before trusting an in-container answer, and prefer a
  probe whose result differs between the two images (a file listing, not a version string).
- **A deploy check must cover every service that changed (#121).** Two Railway services deploy
  from this repo (`health-app-backend`, `health-app-frontend`); probe the frontend by its served
  bundle (fetch the live `assets/index-*.js`, grep a string literal only new code carries).
- **Push branches even while holding for review (#98).** A local-only branch is unreadable to
  chat (`raw.githubusercontent.com` 404s). Pushing is not merging; push when work becomes
  reviewable, not when it lands.

### Tooling

- **MarkItDown — document→markdown ingestion.** Converts PDFs/Office docs to markdown
  deterministically, replacing vision-token native ingestion of structured documents.
  - **MCP (one-shot, in-context):** `markitdown` at user scope (`uvx markitdown-mcp`,
    machine-local `~/.claude.json`). Not a repo dependency.
  - **CLI (large docs, to disk):** `python -m markitdown <in> -o <out>.md` (the
    `markitdown.exe` shim is not on PATH). Installed as `markitdown[pdf,docx,pptx,xlsx,xls]`.
  - **Threshold:** >~30 pages → CLI-to-disk; smaller → MCP.
  - **Limits:** the PDF path is pdfminer text extraction — no table-structure detection.
    Genuine tables flatten to linear text; scanned/broken-font PDFs extract as `(cid:NN)`.
    `(cid:NN)` garbage is loud; table flattening and spurious fake-tables are SILENT (read as
    correct). When a table's structure is load-bearing, verify against source or use vision.
  - Machine-local: the MCP registration and CLI install do not replicate across machines —
    re-run the setup on any new machine.
- **Samsung Health package name** is `com.sec.android.app.shealth`, not `com.samsung.health`
  — the latter returns zero records in Health Connect queries.
- **Prod psql route.** `psql` is absent from the `health-app-backend` image; `railway connect`
  to the `health-app-DB` service is the operator's psql route for prod queries (the #242 closing
  query ran this way). Transform recomputes run in-container: `railway ssh --service
  health-app-backend` → `cd /app` → `/opt/venv/bin/python load_events.py`. Use the venv interpreter
  and `cd /app` explicitly — bare `python` is the system interpreter (no sqlalchemy), and the cwd is
  `/app`, not `/app/backend`. `load_events.window` is a Postgres reserved word — quote it (`"window"`)
  in hand queries. Windows psql needs `\encoding UTF8` for session titles to render.

### Recent landings

_Pointer-only. Capped at the 3 most recent — one line each, canonical home only, no SHAs /
test counts / decision sub-bullets. Full history: `DECISIONS_LOG.md`. Latest handoff:
`closeout.md`. Forward-looking work: `ROADMAP.md` NOW/NEXT (not this block)._

- **Week planner — the schedule checked against the phase, hard items first (#316). Pure, stateless derived read `engine/week_plan.py::plan_week` over the resolver's CURRENT window (no new store, no persisted plan state, no auto-writes, no ledger writes): per slot key `scheduled` (active linked `schedule_item`s) vs `quota` vs `done` (from resolve(), never recounted) + `excess`/`unplaced` — the #312 derivation EXTRACTED to `consistency_rows`/`schedule_sessions_per_week`, one definition read by both the chat line (byte-identical) and the planner; a per-DAY view (hard first → availability → `caution: day after heavy`); `unlinked_soft`; `one_off_notes` (active `load_context`, undated); `needs_planning` (quota declared, nothing placed); `freshness`. Built over all three slot kinds. Availability is an operator prior: day OF a heavy hard item UNAVAILABLE, day AFTER cautioned (advisory); `same_day_training` keeps a day available; `expected_load:"none"` never constrains. Freshness (ruling 4): HC = `max(HealthConnectSync.synced_at)` (device-contact, not arrival), Polar = newest-row `created_at` labelled "newest Polar session received" (no last-pull timestamp exists, Q154); INCOMPLETE only when the signal predates the window start. `GET /engine/week-plan` + `CurrentState.week_plan` (fail→None+log). Rendered under the resolver position, folding the next-7-days hard lines in (one week statement), gated on week_plan so the #312 tests stay byte-identical. `_local_day` is the single day source. GUARD: no change to `resolve()`, the validators, or #275 free-order; quota prompts, never locks; allow-listed on the #310 read-door guard (does not count — `done` is resolve()'s). Carry-over: `_strip_footer_echo` now strips model-echoed PER-ENTRY action lines too (#314 stripped only the tally; prod dup 20 Sep). Backend + tests; non-schema. `Q165` raised (dated one-off `schedule_item`, with the phase-change form brief). Code, self-merged on green (`#316`)** - Handoff: `closeout.md`.

- **Activity slots (device-evidenced, zero-load) + sport-scoped `load_window` + zero-load schedule items (#315). A THIRD microcycle slot kind `activity` (a declared sport recorded by a device, deposits NO load); a slot carries EXACTLY ONE of `capacity` | `load_window` | `activity`. A `load_window` AND `activity` slot now REQUIRE `device_sports` (a recorded WALK can never satisfy a conditioning quota — a declaration, not a floor); a `capacity` slot refuses it. `device_sports` is OPEN (non-empty strings; Polar sports are free-form), matched to a canonical session's `sport_name` exact but case-insensitive. Claim order: exclusions first (untimed/concurrent_strength), then `activity` slots by sport in declared order, then sport-scoped `load_window`; one session ≤ one slot; no match → `unclaimed_session` (detail `no_sport` on NULL sport) → "other activity". `schedule_item.satisfies` gains `{activity}`, `expected_load` gains `"none"`. Surfaces: chat position + `QuotaWindow` render the kind + due marker + unclaimed. GUARD: the resolver decides MEANING (which slot a session belongs to), never a load model — no load-side change, no sport inferred. Divergence flagged at G0 (G1 "optional" vs S2 "required" device_sports → operator ruled REQUIRED). Backend + frontend + tests; non-schema (microcycle + schedule_item are validated JSON). `Q164` raised (ingest-side sport-name normalisation). Code, self-merged on green (`#315`)** - Handoff: `closeout.md`.

- **The in-app coach reads and updates Hevy routines (#314). A `## Hevy routines` context section — compact index of ALL routines + the FULL contents of the working-set folder (the phase's declared folder via a `phase_folders` preference, else the MRU folder, saying so; ~2500-tok cap, overflow named by title; short-TTL in-process cache behind a 3s budget, stale-with-age or unavailable on error). Rendered by shared formatters (`hevy_routine_format.py`, one renderer for context + MCP). `<hevy_update_routine>` → `connector.update_routine` (PUT /v1/routines/{id}; confirm-first; diff vs a pre-write refetch; stale-refuse; `rpe` stripped; NO folder_id — PUT has no folder field and Hevy exposes no move endpoint). Folder set at CREATE only (phase folder, found-or-created). Removed the false `search_hevy_routines` prompt claim (a test asserts no MCP tool name appears in any prompt). Double-footer fixed (strip model footer-echo; one reply → one write per block + one footer). Egress-blocked surfaces (PUT-replace + POST routine_folders body) transport-faked, prod-confirmed on first use. Non-schema; FEEDBACK §46; `Q163` minted (a real tool-use runtime for the in-app chat — not built here). Code, self-merged on green (`#314`)** - Handoff: `closeout.md`.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
