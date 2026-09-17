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

- **Wake-day HRV selector added as a standalone read helper — current-day-strict gate, same-wake-day-only delta, tz-divergence + >2-source guards; no consumers yet (#303). `select_wakeday_hrv(db, user_id, wake_day, *, require_current_day, today=None) -> HrvSelection` in `reads/recovery_reads.py`, reading `hrv_readings` by day-equality. States: value / pair (both sources surfaced, headline richer source garmin>samsung, `delta_ms = primary − secondary`) / absent / stale_withheld (`require_current_day` + no current reading but an earlier one exists — the stale value is WITHHELD, never returned) / config_error (>2 distinct sources — never a silent 2-of-3 pick). `require_current_day=true` NEVER returns a reading whose `captured_at != wake_day`; `=false` (card) headlines the newest available with its date. tz-divergence flags a source on wake_day±1 without auto-merging; baseline maturity passed through from `hrv_deviation` (called read-only) and surfaced, never gating the value. The precondition the check-in HRV denorm brief STOPPED on — both master readers (`_pick_latest_hrv` #298, `hrv_deviation` #292) are upper-bound/newest-ever and leak yesterday. Additive: no consumer, endpoint, frontend, or schema; existing readers/arbitration untouched. >2-source guard is runtime (`source` has no enum/CHECK) — schema upgrade deferred Q157. Backend + tests only; non-migration. Code, self-merged on green (`#303`)** - Handoff: `closeout.md`.

- **Per-user RPE epoch truncates the Banister series + session-median RIR imputation for RPE-absent sets (`tier0-v2` / `banister-v3`, #302). New nullable `users.rpe_complete_from` (migration `a7f3c1e29d84`): when set, `load_metrics` starts that user's daily calendar — EVERY lane — at the first load day on/after it (earlier `load_events` still feed the e1RM fit, never the stocks/ΔLoad); NULL = full history. Backfill: user 1 = 2026-05-11, all others NULL (user 4 pending adoption). An RPE-absent working set in an RPE-bearing session takes the session's floored-median RIR (#244) on the m/f·h path — flagged `rir_imputed`, kept out of the e1RM fit (`e1rm_samples` reads raw rpe), counted in provenance (`session_imputed_sets`, `rpe_unavailable_templates`); `reps_banded_sets` now counts only non-imputed absent sets. `FORMULA_VERSION` tier0-v1→v2, `METRICS_VERSION` banister-v2→v3 (recurrence unchanged — a recompute), `mcp_server._METAB_METRICS_VERSION`→banister-v3 (`_METAB_FORMULA_VERSION` unchanged). Global `EPOCH_RPE_COMPLETE` retired; diagnostic now per-user (NULL→never fires). `load_metrics`/`refresh_load` import the strength/metabolic version constants (no literals; no circular import) so the 02:00 sweep repopulates both lanes with no operator step. Backend + tests + schema migration. Code, HOLD under § Merge disposition (schema migration) — PR ready-for-review, awaiting operator merge instruction (`#302`)** - Handoff: `closeout.md`.

- **Banister stocks normalised — fitness/fatigue are true EWMAs (`banister-v2`), restoring #18 so `form = fitness − fatigue` can go negative (#301). `load_metrics.compute_window_series` weights the load term by `(1 − decay)` for both stocks (`stock = stock·decay + (1 − decay)·load`); `METRICS_VERSION` bumps `banister-v1` → `banister-v2` (a stock recompute per #248), `FORM_K` stays 1 (Coggan/Allen TSB = CTL − ATL). Un-normalised banister-v1 (`stock·decay + load`) pinned fitness ≥ fatigue on every day, so form was never negative — the bug #248 masked by mislabelling the recurrence "discrete EWMAs". Because τ_fat < τ_fit, fatigue now responds harder to a spike and decays faster in rest, so form crosses zero across training→rest. Consumer sweep: no absolute thresholds on the three values anywhere; `routers/series.py` keys on the imported `METRICS_VERSION` (banister-v1 rows left as dormant versioned history); `mcp_server._METAB_METRICS_VERSION` follows the bump to `banister-v2`; `scripts/refresh_load.py` uses the default version, so both lanes repopulate on the next 02:00 sweep with no operator step. Warm-up now biases form negative for ~τ_fit days (maturity-gated); the metabolic τ_fat=4 artefact + a criterion/sensitivity harness are preregistered as Q156. Backend + tests only; non-migration. Code, self-merged on green (`#301`)** - Handoff: `closeout.md`.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
