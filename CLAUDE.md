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

### The unseeable-surface rule

Chat can verify only what is on a pushed ref. Any brief statement about a surface chat cannot
read — UI-maintained knowledge files, unpushed branches, local disk, Railway/prod state, the
operator container — is an INSTRUCTION TO VERIFY, never a report of fact, regardless of how it
is phrased. Declarative mood does not make it attested. Verify against the surface or STOP and
report; never land on it.

### Canonical stores

| Store | Holds | Discipline |
|-------|-------|-----------|
| `DECISIONS_LOG.md` | Architecture decisions | Append-only. Supersede via a new entry that references the superseded number. Never edit a locked entry in place. |
| `OPEN_QUESTIONS.md` | Undecided forks, unverified-at-machine items | One status per item, from the four states — see **State vocabulary** below; that section is the sole definition. `DONE → #N` names the decision that resolved the question, as `DONE` names its SHA in `BRANCHES.md`. |
| `ROADMAP.md` | Current sprint + horizon | Mutable. Code updates it at close-out. |
| `FEEDBACK.md` | Behavioural corrections and standing rules | Repo-canonical. Code reads it at session start. The project-knowledge copy is a refreshed mirror, not the master. |
| `ptb-tasks` (external board) | Task status | Single live board. Mutable. Referenced by task ID — never mirrored into the repo. |
| pending-commit queue | The chat → Code handoff payload | Transient. Emitted by the chat close-out as canonical-format entries flagged `PENDING`. Carried by paste, or materialised as a GitHub issue for `@claude`. Consumed at the next Code open, then discarded. Not a stored repo file. |

**Stays in project knowledge, never in the repo** (stable, chat-analysis context):
`Clinical_Protocol`, `Athlete_Profile`, lab PDFs, `Stack`, `API_CONTRACTS`,
`Hevy_Pattern`, `Readiness_Algorithm`.

### State vocabulary

Four states, exhaustive, no fifth. Applies to `BRANCHES.md` Status, `OPEN_QUESTIONS.md`,
`ROADMAP.md`, and close-outs.

- **DONE** — landed on master (SHA) or applied to a named UI file. Nothing further required by
  anyone.
- **BLOCKED** — cannot proceed; names the blocker and its owner. A trigger for when work
  becomes *worth* doing is not a blocker on its being *possible* — that is UNSTARTED.
  Where the evidence does not settle whether a dependency is a barrier or a trigger,
  the row is UNSTARTED: a false BLOCKED tells a reader not to try.
- **OWED** — work or decision settled, loop not closed; names the exact command or check
  outstanding.
- **UNSTARTED** — untouched.

No "in progress": half-done work is **BLOCKED** (has a blocker) or **UNSTARTED** (doesn't).

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
     suggested commit messages. Additionally emits
     `git log --format="%ad %s" --date=short -10` so the handoff carries the repo's own
     record — commit dates are immutable and cannot drift, where a self-reported stamp can.
     (This binds here, not in `closeout.md`: that file is session-local and overwritten every
     close-out, so a rule left only there would not survive.)
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
- **Never run a command that renders a secret value.** Includes `railway variables` in
  any form (`--kv`, `-k`, `--json`, the `variable` singular, and the bare `list` — the
  CLI's own help states that both `--kv` and `--json` print raw values), `printenv`,
  `env`, and reading any `.env` by any tool or alias. **To check existence**, read names
  or presence. **To use a value**, inject it with `railway run <cmd>` — the value enters
  the child process and never the transcript. **To compare values**, compare SHA-256
  digests, first 12 characters, both sides. Earned twice: a `--kv` invocation put a live
  Postgres credential into four session transcripts, and a `.env` grep matching key
  *names* printed a live API key and a Fernet key while establishing that nothing had
  been printed. `.claude/settings.json` carries deny patterns as a second layer; it is a
  speed bump, not the enforcement — this instruction is (DECISIONS_LOG #111).
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

- **SCHEMA.md is repo-canonical** (root), the human/AI-readable mirror of
  `backend/migrations/`. Code updates it in the same commit — or an immediately
  paired governance commit — as any migration that changes the schema. It must
  never lag master; a canonical-but-stale schema doc is worse than a stale
  project-knowledge copy.

- **Chat→Code file transport.** When a project-knowledge doc must cross to Code, chat
  grabs it from the project mount (byte-faithful read) and emits it as a raw fenced
  block — never copied from the rendered project view, which flattens markdown (bold,
  inline code, numbered lists, horizontal rules). The human carries the paste; Code
  diffs the written file against the intended source before landing. Repo-canonical
  docs are edited in place and never cross this transport.

- **Reference-JSON edit guard (standing, #98).** `backend/reference/*.json` is hand-aligned
  and pure ASCII, with non-ASCII written as `\uXXXX`. Two rules, both mechanical:
  1. **Never construct a `\uXXXX` escape inside heredoc source.** The Bash tool's heredoc
     consumes one backslash *even when quoted* (`<<'EOF'`), so `—` in source arrives at
     Python as a literal em dash and gets written into the file. Build the backslash via
     `chr(92) + "u2014"`, or write the script to a file first.
  2. **After any edit, assert the file is pure ASCII with zero literal em dashes** —
     `raw.isascii() and raw.count(chr(0x2014)) == 0` — and that it still parses. This fires
     regardless of who is careful.
  Rationale: the failure is silent *in the direction that writes bad bytes*. The malformed
  case succeeds and produces a valid, value-identical file that violates the encoding
  convention; only the assertion catches it. Also: **no `json.dump` round-trips** on these
  files — re-serialising reflows every hunk and rewrites escapes, burying a small change in
  a whole-file diff. Surgical text edits only.

- **Never chain a verification to an action in one command (standing, #103).** A check whose
  failure cannot stop what follows is not a check. Run the check, read the result, then act —
  or make the action explicitly conditional on the check's exit status. Earned when a failed
  assertion was followed by `git add && git rebase --continue` in the same command, completing
  a rebase that committed conflict markers into an append-only ledger. Chaining is a reflex,
  not a decision, which is why it needs a gate rather than care. See `FEEDBACK` §17.

- **Controls discriminate on identity, not just function (standing, #103).** A positive control
  proves the instrument works; it does not prove the thing probed is the thing you meant. Where
  a probe could succeed against the wrong artefact — stale refs, cached CDN copies, reused
  branch names — pin to a SHA or assert on content only the intended version carries. Earned
  when three honest HTTP 200s described pre-rebase bytes. See `FEEDBACK` §17.

- **Match on anchors, not substrings — especially in an audit (standing, #113).** A grep that
  decides whether something is recorded must anchor on the form the thing actually takes
  (`^### 104\.`, `^## Q45\.`, a whole word) rather than a bare substring. Unanchored, the audit
  can report the very condition it is auditing for: a check for `nap` in `BRANCHES.md` matched
  **`snapshot`**, which would have certified a decision as recorded when it was not recorded
  anywhere. Same defect as a bare `s/104/107/` renumber, and the same fix. This is
  "controls discriminate on identity" (above) applied to search patterns: a hit count answers
  *did the pattern fire*, never *did it fire on the thing you meant*. **Read the matches, not
  the count** — that habit is what caught this one, and it is cheaper than the rule.

- **Push branches even while holding for review (standing, #98).** A local-only branch is
  unreadable to chat — `raw.githubusercontent.com` 404s — so a "hold before merge" gate that
  chat cannot independently verify rests on Code's report alone, which is the one thing the
  loop's evidence rules exist to avoid. Pushing costs nothing and is not a merge. Push at the
  point work becomes reviewable, not at the point it lands.

### Tooling

- **MarkItDown — the document→markdown ingestion path.** Microsoft MarkItDown converts
  PDFs and Office documents (TGA guidance, AS/NZS standards, council specs, clinical
  papers) to markdown deterministically, replacing native Claude ingestion of structured
  documents — which costs vision tokens and extracts tables non-deterministically. Two
  invocation paths:
  - **MCP (one-shot, in-context).** `markitdown` registered at **user scope**
    (`uvx markitdown-mcp`, machine-local `~/.claude.json`), for converting a single
    document straight into the conversation. Not a repo dependency.
  - **CLI (large documents, to disk).** For anything past the threshold, convert to a
    file and read it selectively rather than dumping it into context. Invoke
    `python -m markitdown <in> -o <out>.md` (the `markitdown.exe` shim is not on PATH;
    `python -m` is PATH-independent). Installed as `markitdown[pdf,docx,pptx,xlsx,xls]`
    (`[all]` is unsatisfiable on Python 3.14 — its `onnxruntime<=1.20.1` pin, audio-only,
    has no 3.14 wheel; the document extras carry every PDF/Office converter regardless).
  - **Threshold:** **>~30 pages → CLI-to-disk**; smaller → MCP is fine.
  - **Limits (verified at adoption).** The PDF path is pdfminer *text* extraction — it has
    no table-structure detection: genuine tables **flatten to linear text** (column pairing
    lost), and scanned / broken-font PDFs (no ToUnicode CMap) extract as `(cid:NN)` garbage.
    Output is deterministic and clean on born-digital prose, but for a document where a
    specific table's *structure* is load-bearing, or a scanned/garbled source, **fall back
    to native Claude vision** on that page. `az-doc-intel` (Azure Document Intelligence) is
    the table-aware upgrade path if ever needed — not wired.
  - **Loud vs silent failure (trust calibration, refines DECISIONS_LOG #78).** The three failure modes are
    NOT equally dangerous. `(cid:NN)` garbage is **loud** — obviously broken on sight, so you
    won't act on it. Table **flattening** (plausible prose, column pairing gone) and
    **spurious fake-tables** (valid-looking GFM built from shattered prose) are **silent** —
    they read as correct. So the risk isn't the garbled scan you'll catch; it's the clean-
    looking table you'll trust. When a table's structure carries meaning, verify against the
    source or use vision — don't trust MarkItDown's table shape on faith.
  - Machine-local: the MCP registration and CLI install do not replicate across machines —
    re-run the setup on any new machine. See DECISIONS_LOG for the adoption decision.

### Recent landings

_Pointer-only. Capped at the 3 most recent — one line each, canonical home only, no SHAs /
test counts / decision sub-bullets. Full history: `DECISIONS_LOG.md`. Latest handoff:
`closeout.md`. Forward-looking work: `ROADMAP.md` NOW/NEXT (not this block)._

- **#114/#115** — CBT-I titration engine: regularity is instrumented not gating and three constants are recorded unvalidated rather than chosen; the +30 buffer is recovered from the prior block, whose sleep-need basis week itself over-ran. See DECISIONS_LOG #114, #115.
- **#113** — An unanchored audit can certify the condition it is auditing for; match on anchors and read the matches, not the count. See DECISIONS_LOG #113.
- **#112** — Cross-repo propagation debt is recorded in `ROADMAP.md` NOW, the only store that is neither session- nor branch-scoped; `closeout.md` may point at it but never hold it. See DECISIONS_LOG #112.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._
