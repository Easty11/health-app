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

Code and schema changes always take full human review.

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

### Recent landings

_Pointer-only. Capped at the 3 most recent — one line each, canonical home only, no SHAs /
test counts / decision sub-bullets. Full history: `DECISIONS_LOG.md`. Latest handoff:
`closeout.md`. Forward-looking work: `ROADMAP.md` NOW/NEXT (not this block)._

- **Assertion provenance on profile entries; `review_on` prompts, never expires (#227/#228)** - `hard_stops` and `live_signals` recorded WHAT was asserted but not who asserted it, on what basis, or when, so a hard stop nobody remembers setting was indistinguishable from one that still applies. Each entry now carries `{asserted_by: user|engine|clinician, asserted_on, basis, review_on}` as keys INSIDE the entry - assertion and attribution stay atomic, no migration, no side table. WRITES REQUIRE PROVENANCE, READS TOLERATE ITS ABSENCE: a legacy profile keeps working (read backfills `user`/null/null) but the next edit must state who and when - the two halves are one change-management rule, since strict reads would 422 every existing profile and lenient writes would mean the store never fills in. Known consequence pinned as a test: GET -> PUT of a pre-provenance profile 422s on the null date, and the message names the fix. `review_on` IS A PROMPT, NEVER AN EXPIRY (#228, restating #223 in a second store) - a past `review_on` still blocks, guarded structurally by asserting `selection.py` never references the field; an un-applied safety rule fails OPEN, which is worse than a stale one. PROVENANCE DOES NOT CHANGE SELECTION - the same stop in both shapes gives the same verdict and reason. `asserted_by` is an AUTHORITY axis, deliberately not a rename of the existing `source` CHANNEL axis (`onboarding|chat|system`, `probe`, `hevy`) - orthogonal, and every knowledge row reads `source: "chat"` today, which is why channel carries no authority; it aligns instead with #222's `resolved_by`, differing by exactly `engine` (can assert, must never resolve). `weekly_template` takes NO block - a declaration has no truth value to attribute. Backend 1018->1069, frontend untouched. See DECISIONS_LOG #227/#228.

- **AM soreness prefill carries the last reported value; the absence fallback is 3, not 1 (#224/#225/#226)** - `derive_soreness_items` hardcoded `1`, which is the scale FLOOR, so every morning opened at "asymptomatic" regardless of yesterday: a genuinely sore injury had to be re-entered daily or the record understated it, and an unedited day silently reported recovery. Now carries that injury key's last reported value within `_PREFILL_LOOKBACK_DAYS` (7), one query for all keys, falling back to **3** - the value `calc_naive_baseline` ALREADY treats as no-information (`max(vals) if vals else 3`), so the prefill stops contradicting the scorer it feeds. THE FALLBACK CHANGE IS THE LOAD-BEARING HALF: `1` was doing double duty as both scale floor and untouched default, so a `review_when` exit condition of `soreness <= 1 sustained 3d` could be satisfied by three days of NOT touching the form - an injury clearing its own exit condition through inattention. It now requires entering `1` deliberately. Costs ~1.0 readiness point for a new injury with no history; intended effect of an honest input, and historical `naive_baseline` is frozen at capture so no stored score moves. A reported-vs-defaulted flag was CONSIDERED AND DECLINED (#226) - the `3` fallback fixes the same failure without a migration; residual is that a deliberate `3` and an untouched `3` are still indistinguishable, contained by #223's surfacing-only rule and load-bearing only if trajectory ever gains authority. Prefill stays a READ - no write, no record created. Formula, submit path and `injury_trajectory` untouched. Backend 980->1018, frontend untouched. See DECISIONS_LOG #224/#225/#226.

- **Injury resolution: the write end of a loop that could only be opened (#222/#223)** - an injury entry could be created and superseded-by-key but not RESOLVED, so `gather_active_injuries` kept returning healed injuries and `is_contraindicated` kept suppressing regions the user had recovered in - live wrong output, not a hypothetical. `GET /knowledge/injuries` (`?include_resolved=true` for history) lists them and `POST /knowledge/injuries/{id}/resolve` retires one: `active=False` plus a `resolution` block (`resolved_on`/`basis`/`resolved_by`) written into the row's JSON `value`. No model, no migration, `expires_at` semantics untouched. RESOLUTION IS NOT SUPERSESSION - both set `active=False`, but supersession names its successor in `superseded_by` while resolution leaves it null, and that field is the ONLY thing separating a healed hamstring from a re-worded one; the merge will look like tidying, which is why #222 records it. NOTHING AUTO-RESOLVES (#223, restating #72 rather than assuming it carries): not a passed `resolve_by`, not a soreness series at its exit condition, not a live `review` flag - `injury_trajectory` stays surfacing-only, enforced by a structural gate asserting its source carries no `.active =` assignment. Never deletes; the row is retained as history. Gates mutation-tested against four seeded defects, each caught by the intended gate and no other. Existing stale rows are NOT backfilled - operator-driven by design, a ROADMAP lane. Backend 945->980, frontend untouched. See DECISIONS_LOG #222/#223.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
