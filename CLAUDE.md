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
- The repo and its GitHub tracker (Issues) are the single source of truth for all volatile state.
- Code is the only writer. Chat proposes; chat never commits.
- The commit is the only sync point. An uncommitted decision is provisional.
- Read-back: repo → chat via Projects mirror, attach, or the GitHub API (issues, design docs). Chat keeps no editable copy.
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
- **Door class decides the hold.** A **one-way door** — a schema migration (a PR containing one);
  a default that shapes stored rows (data-meaning); a cross-module contract change; anything the
  session was told to hold — is not self-merged: it holds for explicit operator instruction,
  whether raised or resolved. Everything else is a
  **two-way door**: Code resolves it in-PR, records a *ruling* entry in `DECISIONS_LOG` (Decision ·
  Reverse-by), and self-merges on green. The merge is the ratification; chat objects at the next
  session open, by issue, if it disagrees. Resolving a two-way door needs no hold; a one-way door
  does, whether raised or resolved.
- **Chat-side writes are approval-gated.** A chat-side session writes to the repo or
  tracker only behind an explicit operator approval given in-turn. One approval may cover
  a named group of actions; the group is stated, never inferred. A pasted queue or brief
  authorises nothing by itself.
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
| GitHub Issues (per repo) | Undecided forks, unknowns awaiting measurement, watch-points | Typed by label (`fork` / `stamp` / `verify` / `watch` / `design`); closed by `Closes #N` in the resolving PR or by the stale action (`abandoned`). Never mirrored into the tree (`GH#N` in prose; bare `#N` is a decision). |
| `docs/design/NNNN-*.md` | Architecture-scale design docs (RFD-style) | `**State:**` ideation / discussion / committed / abandoned; own Unresolved-questions table, every row resolved or struck before `committed`. |
| `ROADMAP.md` | Current sprint + horizon | Mutable; Code updates at close-out. |
| `FEEDBACK.md` | Behavioural corrections, condensed verification rules | Read at session start. |
| `FEEDBACK_ARCHIVE.md` | Full provenance essays | NOT read at session start. |
| `ptb-tasks` (external) | Task status | Referenced by ID, never mirrored in. |
| pending-commit queue | Chat → Code handoff | Transient; emitted at chat close-out, consumed at Code open. |

Stays in project knowledge, never in the repo: `Clinical_Protocol`, `Athlete_Profile`,
lab PDFs, `Stack`, `API_CONTRACTS`, `Hevy_Pattern`, `Readiness_Algorithm`.

### State vocabulary
Work items: DONE (landed, SHA named) · BLOCKED (names blocker + owner) · OWED (settled,
loop-close named) · UNSTARTED. No "in progress". Issues: open (typed by label) · closed-resolved (`Closes #N`; a ruling or decision entry where a call was made) · closed-abandoned (stale action). Design docs: ideation · discussion · committed · abandoned, under `**State:**`.

### Filing a question
- Nothing is filed bare. Every issue body carries four fields: **Proposed answer** · **Alternative
  it beats** · **Evidence that would settle it** · **Door** (one-way / two-way). If the evidence is a
  check runnable this turn, run it — no issue exists.
- Labels are the type: `fork` (operator ruling; surfaced at session open), `stamp` (proposed answer
  stands; acted on by the next PR touching the area unless the operator objects), `verify` (names
  the exact query or probe), `watch` (names the test/alert that guards it), `design` (pointer to a
  `docs/design` doc), `pinned` (stale-exempt), `abandoned` (set by the stale action).
- Architecture-scale items get a design doc, not an issue; the issue, if any, is a one-line pointer
  labelled `design`.
- A question survives only by being touched; the stale action closes the untouched at 60 days as
  `abandoned`. Abandoned is a normal ending.
- `build`: ruled, awaiting its trigger or capacity; the body names the trigger and the ruling entry.
- **Citation form.** Bare `#N` in every store is a `DECISIONS_LOG` number. A GitHub issue or PR is
  written `GH#N`. Never cite an issue bare.

### DECISIONS_LOG discipline
- Entry format: **Decision · Rationale · Status · How you know · Do not revisit unless**.
- Append-only. Every code-gating decision carries a How-you-know artifact (confirmed test,
  verified search, official doc).
- Number-at-merge: entries on a branch are headed `### #NEXT`; resolve the integer by
  re-reading master's max immediately before landing, re-resolve if master advances.
  Enforced by `scripts/check_governance_placeholders.py` via the repo hook
  (`git config core.hooksPath .githooks`, once per clone).
- Two tiers under the same `### #N` heading. Decision (one-way doors and anything architectural):
  Decision · Rationale · Status · How you know · Do not revisit unless. Ruling (two-way doors
  resolved in-PR): `**Tier:** ruling` then Decision · Reverse-by — two lines, nothing else.
  Number-at-merge and the guard apply to both.

### Session rituals
- **Open:** report the decisions max (`^### #?[0-9]+`) and the open `fork` issues, titles included:
  `gh api "repos/{owner}/{repo}/issues?labels=fork&state=open" --jq ".[] | \"GH#\(.number) \(.title)\""`
  (`gh` substitutes `{owner}/{repo}` from the current repo; locally `gh issue list --label fork --state open`;
  the short form fails in a cloud session, where GraphQL is blocked). Chat re-aims any brief against these.
  Optional at open, when a cold-start digest is wanted: `python scripts\gen_governance_view.py`
  (reads master; output is gitignored under `build\`). Never run it at close-out — it would
  digest master before this session's close-out merges.
- **Chat close-out (`;cc`):** emits the pending-commit queue as canonical-format entries
  flagged PENDING, then a one-line CHAT DISPOSITION (the GH# issues and `docs/design` docs served;
  LIVE / PARKED / CLOSED; the title to rename the chat to, or DELETE). Writes nothing to project knowledge.
- **Code close-out (`/closeout`):** reads the stores; reports actual commits
  (`git log --format="%ad %s" --date=short -10`); reconciles every PENDING item;
  branch terminal-state gate — every touched branch ends merged+deleted or in
  `BRANCHES.md`, else HALT.
- **Paste addressing:** Operator paste blocks are addressed to a session by name on their
  first line. A block whose address names a different session, or carries none while more
  than one session is live, is NOT acted on — report it back and wait. In a brief's header,
  the text after ` - ` is the source chat's name, not an instruction.

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
- One branch per concern. Harness-assigned names (`claude/<hash>`) are accepted; the PR title
  and the `BRANCHES.md` row carry the meaning, not the branch name.
- **Severity gate on review:** raise as a gate only defects that change an outcome,
  corrupt data, leak a secret, or block the next step. Cosmetic, consistency, and
  wording defects batch into a single trailing "nits" note — never a reason to withhold
  a green-light or halt a land.
- **Governance batching:** one `gov(...)` commit per landed ruling, written when that ruling
  lands (not one per session). Governance edits never interleave with feature work mid-session.
- Full corrections live in `FEEDBACK.md`; full history in `DECISIONS_LOG.md` and
  `FEEDBACK_ARCHIVE.md`. This file points at them; it does not duplicate them.
- **Parity artefacts beyond this block.** `.github/workflows/governance-guard.yml` is byte-identical
  from `name:` down (the comment header is repo-local); `scripts/check_governance_placeholders.py` is
  code-identical (docstrings and the `main()` advisory string are repo-local). Both are re-checked at
  every shared-block propagation; `closeout.md` is repo-specific and not a parity artefact.

## END SHARED LOOP RULES — repo-specific below

<!-- ════════════ END SHARED LOOP RULES ════════════ -->

---

## Repo-specific — health-app

### Merge path — PR-gated (#171)

- **The pull request is the only route to master.** Ruleset `master-pr-gated` (id `20414758`)
  requires a PR + the `placeholder guard (POSIX)` and `backend tests (pytest)` status checks, forbids non-fast-forward, and
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
`DECISIONS_LOG`, `BRANCHES`, `ROADMAP`, `CLAUDE.md`, `FEEDBACK`,
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
- **Reference-JSON edit guard (#98).** `backend/reference/marker_groups.json` and
  `backend/reference/safety_thresholds.json` are hand-aligned pure ASCII (non-ASCII as `\uXXXX`);
  their tests pin it (`raw.isascii()`). Never build a `\uXXXX` escape in heredoc source (the Bash
  tool eats one backslash even when quoted — use `chr(92)+"u2014"` or a script file); after any edit
  to those two assert `raw.isascii() and raw.count(chr(0x2014))==0` and that it still parses; no
  `json.dump` round-trips. The bad-byte failure is silent — only the assertion catches it. The other
  `backend/reference/*.json` files are not pinned: `exercise_region_tags_v0.json` is raw UTF-8 on
  master (29 em dashes), so edit it by line surgery that leaves every untouched line byte-identical
  and adds no non-ASCII, and assert it still parses (Q27 v1 found the old blanket rule failing on it).
- **Irreversible-write pre-ship gate (#166, `FEEDBACK` §23).** When a decision's How-you-know
  admits an unexercised write path, ask what its failure COSTS before shipping. Non-destructive
  and loud → ship with a test or alert that fires when the assumption fails; file a `watch` issue only when that cannot be built in-turn, naming where the alert will live. Able to change state we cannot undo →
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
- **A SKIPPED deployment is the expected result for a merge that changes neither service's folder (#433).** Railway watch paths
  (`/backend/**`, `/frontend/**`) deploy a service only when its own folder changes, so a governance or docs-only merge records
  SKIPPED on both. Read `railway deployment list` per service, matching on `commitHash`, not on position in the list: SUCCESS is
  owed only on a service whose folder changed, SKIPPED on the other is correct, and a code change that records SKIPPED is a defect
  (redeploy by hand, then recheck the patterns). **No record on either service, not even SKIPPED, means the trigger did not fire:**
  halt (#442 (b)). Recover with a deploy of master head, never the Redeploy action, which replays the commit of an existing
  deployment and so a stale one (#442 (c)). A service can deploy on a merge that did not touch its folder when the span from its
  last-deployed commit does (#442 (d)).
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
  `/app`, not `/app/backend`. The `load_events` window column is `load_window` (migration
  `1341a2cf6938`, #246), not `window`: the rename took it off the Postgres reserved word, so hand
  queries use `load_window` unquoted. Windows psql needs `\encoding UTF8` for session titles to render.
- **Operator scripts and psql, from the prod container.** `railway run` cannot run an operator script: the
  database host is a private hostname, and a directory linked to the frontend service has no `DATABASE_URL`.
  The recipe is `railway ssh --service health-app-backend`, then from `/app`
  `/opt/venv/bin/python -m scripts.<name>` (the container's bare `python` lacks the app's packages). psql via
  `railway connect` needs `PGCLIENTENCODING=UTF8` set first, or non-ASCII text (session titles) breaks.

### Recent landings

_Pointer-only. Capped at the 3 most recent — one line each, canonical home only, no SHAs /
test counts / decision sub-bullets. Full history: `DECISIONS_LOG.md`. Latest handoff:
`closeout.md`. Forward-looking work: `ROADMAP.md` NOW/NEXT (not this block)._

- **Wake-day capture: the morning fetch, the 10:00 backstop, the Recovery tile and Settings Garmin views, the snapshot's Garmin lanes with four retired writers, and the SpO2 minimum.** Code - Canonical home: `DECISIONS_LOG.md` #477, #478, #479, #480.

- **In-app per-session sRPE: one CR-10 per counted session, the whole-day fill retired, Pilates counted.** Code - Canonical home: `DECISIONS_LOG.md` #475.

- **Chat-side writes are approval-gated: a shared-block line, FEEDBACK §66 and §67, and a ruling entry.** Governance - Canonical home: `DECISIONS_LOG.md` #473.


---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
