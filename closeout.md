# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-05. Branch at close: `master` — all three session branches merged and
deleted both sides. Session-open ref: `a9d52d3`.

Canon at open: DECISIONS max **#170**, OPEN_QUESTIONS max **Q79**.
Canon at close: DECISIONS max **#172**, OPEN_QUESTIONS max **Q80**.

**The merge path changed under this session (`#171`).** master is now reachable only by pull
request, gated by a required status check. `git push origin master` is refused server-side.

---

## 1 — Real commits this session

`git log --oneline a9d52d3..HEAD`, before the close-out commit:

```
0a08ee7 Merge pull request #18 from Easty11/gov/forward-ref-and-clone-setup
ebbb27a fix(governance): the fresh-clone alias check must be --local, or it reads the old global body
6cc3cea governance: forward-ref sub-question on Q80; per-clone setup documented; closeout names what stood still
f85b389 Merge pull request #17 from Easty11/gov/merge-path-followup
485344e governance: close #171's recorded unknown - --delete-branch removes the local branch too
4308867 Merge pull request #16 from Easty11/chore/merge-path-pr-migration
113f04a governance: resolve #NEXT -> #171/#172, Q#NEXT -> Q80 (on-branch, pre-merge)
8191f70 governance: BRANCHES row for chore/merge-path-pr-migration
f9bea0a governance: PR-gated merge path + boundary criterion entries; Q on the number invariant
d9f45f3 governance: guard docs name the third enforcement surface (the ruleset)
56d71bc governance: merge-path mechanics leave the shared block; boundary criterion added
```

`git log --format="%ad %s" --date=short -10` — the repo's own dated record, which cannot drift
where a self-reported stamp can:

```
2026-08-05 Merge pull request #18 from Easty11/gov/forward-ref-and-clone-setup
2026-08-05 fix(governance): the fresh-clone alias check must be --local, or it reads the old global body
2026-08-05 governance: forward-ref sub-question on Q80; per-clone setup documented; closeout names what stood still
2026-08-05 Merge pull request #17 from Easty11/gov/merge-path-followup
2026-08-05 governance: close #171's recorded unknown - --delete-branch removes the local branch too
2026-08-05 Merge pull request #16 from Easty11/chore/merge-path-pr-migration
2026-08-05 governance: resolve #NEXT -> #171/#172, Q#NEXT -> Q80 (on-branch, pre-merge)
2026-08-05 governance: BRANCHES row for chore/merge-path-pr-migration
2026-08-05 governance: PR-gated merge path + boundary criterion entries; Q on the number invariant
2026-08-05 governance: guard docs name the third enforcement surface (the ruleset)
```

**Three merge commits, no fast-forwards.** Every one went through
`gh pr merge --merge --delete-branch` — PRs #16, #17, #18. This is the first session in this
repo's history in which nothing reached master by `git push origin master`, because that route
is now refused.

Backend suite **722 passed**; the guard's own tests **13 passed** after its docstring and
message string were edited. Governance and documentation only — no `backend/` logic, no
`frontend/`, no migration, no schema change.

---

## 2 — Pending-queue reconciliation

No `;cc` queue was carried in. The input was a chat brief in three revisions (3 Aug, and two on
4 Aug), each carrying a proposed `### #NEXT` LOG entry flagged for Code and two hard halts.

| Brief item | Outcome |
|---|---|
| Step 0 — verify prevention by observation | **Failed three times, then passed.** Failed 3 Aug and twice more this session: no ruleset, no branch protection, `rules/branches/master` empty. The brief presumed "Luke enables the ruleset" as a precondition; it had not happened. Resolved by Luke's ruling that Code hold the whole path — ruleset then created by Code and **tested rather than trusted**. Landed as `#171`. |
| Step 1 — rewrite `land` around `gh` | **Repo side landed; the alias itself is OWED.** Merge mode chosen with reason; `gh pr merge` refusal-on-failing-check tested and quoted; `--auto` confirmed to queue not bypass, and excluded anyway; `--admin` tested and refused. The alias **body** is unversioned config and no commit here can close it. |
| Step 1b — HALT for a ruling on the shared block | **Halted, ruled, executed.** HCA's state verified by inspection. Luke ruled option 1 — mechanics leave the block, invariants stay. Landed as `#172`. |
| Step 2 — number-at-merge names its window | **Landed** as a new shared-block bullet. Strict mode's forced pause recorded as a pause and explicitly *not* as an adjudication. |
| Step 3 — verify `#41`'s gate still holds | **Verified unmodified; no change made** — the brief's own stated likely outcome, recorded rather than edited. |
| Step 4 — sweep `land` / `--ff-only` | **Landed.** Anchored per `#113`, never substring — `land` matches `landed`/`landings` throughout the stores. Remaining hits are historical record or the verb. |
| The brief's proposed LOG entry | **Superseded by what landed.** Its central claim (that `#40` rule 1 was being corrected) held; its Step 3 claim did not. |

**Three brief claims were false and are corrected in-tree, not worked around.**

1. `--delete-branch` "removes the remote branch but leaves the local one". It removes **both**
   and switches to master. Recorded as unverified in `#171` while only `gh pr close` had been
   observed, then closed by `#171`'s own landing (PR #16) as a dated note that postdates the
   locked entry, scoped to what was actually seen (`gh` 2.93.0, run from a working copy on the
   branch being merged).
2. "`#16`'s propagation model" — that is `health-connect-app`'s numbering; health-app's `#16` is
   about metric verification. health-app has **no numbered entry** for the verbatim-propagation
   model at all. Recorded inside `#172`, because the absence is the point.
3. The ruleset was assigned to Luke — written before he directed that Code hold the whole path.

**One error of Code's own, self-caught pre-merge:** the fresh-clone verification line first
written as `git config --get alias.land` is a false green — `--get` reads *merged* config and
returns the **old global ff-only body**, so an unconfigured clone reads as configured. Fixed at
`ebbb27a` to `--local --get`. That is `#103`'s rule failing in text written minutes after `#103`
was cited. **A `FEEDBACK` §19 row was deliberately not minted:** the prevention it would name is
`#103`, which already exists, and this session's scaffolding already outruns what it scaffolds.
Available to mint if wanted.

---

## 3 — Cold-resume handoff

### What changed

**`#171` — the pull request is the sole route to master.** Ruleset `master-pr-gated`
(id `20414758`): PR required, `placeholder guard (POSIX)` required under a strict up-to-date
policy, non-fast-forward forbidden, `bypass_actors` empty (`current_user_can_bypass: never`, so
it binds the owner holding an admin token — tested, `--admin` is refused). Supersedes `#40` rule
1's enforcement claim, which had asserted a single merge path since the day it landed while
`a9d52d3` (a direct push, no PR) and PR #11 sat on the same log; and `#170`'s
prevention/detection caveat, which nominated itself for exactly this.

**`#172` — merge-path mechanics leave the shared block.** A rule is shared only if its
correctness is independent of any surface outside the tree. Invariants stay (number-at-merge,
terminal-state, patch-id, naming, single-writer); mechanics depending on unversioned config go
repo-local. The rejected alternative — a shared rule *conditioned* on whether the repo has a
required check — is recorded with its reason: the condition is invisible from the tree, so a
reader could not tell which branch of the rule applied to them.

**`Q80` — the guard polices the symptom, not the invariant.** Three ways a decision number goes
wrong; the guard set covers two. Unresolved placeholder: caught. Duplicate or gap: would be
caught by the proposed arm. **A forward reference written as a literal number before the resolve
is invisible to all of them** — demonstrated here, where nine literal `#171`/`#172` refs held
only because master happened not to advance, while the three `#NEXT` tokens on the same branch
were safe by construction.

### Enforcement spans three layers and two have no diff

`core.hooksPath` (per clone) · `.github/workflows/governance-guard.yml` (versioned) · ruleset
`20414758` (per repo). A fresh clone, a deleted ruleset, or an added bypass actor removes
enforcement silently and leaves every run green. **`#171` is the only in-tree record that the
ruleset is expected to exist.** Verify directly, never by a green run:

    gh api repos/Easty11/health-app/rules/branches/master

### Fresh-clone setup — neither item is cloned, neither fails loudly

    git config core.hooksPath .githooks
    git config --local alias.land '!gh pr merge --merge --delete-branch'

Verify with `git config --get core.hooksPath` and **`git config --local --get alias.land`**. The
`--local` is load-bearing: without it the check returns the stale global body and passes on an
unconfigured clone.

### OWED

1. ~~**The `land` alias body.**~~ **DISCHARGED 2026-08-05, post-close-out.** `--global --unset`
   run by Luke; `stale` verified surviving; the `--local` body set and verified with
   `git config --local --get alias.land`. **The documented body was wrong on first use and is
   corrected in the same pass:** the `!f() { … "$(git branch --show-current)" … }; f` form
   Bash-verified at `#171` cannot be entered from PowerShell — embedded double quotes do not
   survive PowerShell's native-command re-quoting, and `git config` reports it as
   `error: no action specified`, which names nothing about quoting. The working body is
   `!gh pr merge --merge --delete-branch`; no subshell is needed because `gh pr merge` already
   defaults to the current branch's PR. The **standing PowerShell rule in `CLAUDE.md` was
   sharpened** rather than a new instrument added: PowerShell-safe now explicitly means
   *no embedded double quotes*, and a command Code emits for Luke must be exercised in
   PowerShell — Code's Bash tool passes these strings cleanly and structurally cannot
   reproduce the failure.
2. **Shared-block propagation to `health-connect-app`** — the one genuinely outstanding item. — ROADMAP NOW row 4. HCA takes the
   amended block verbatim and **loses nothing**: its merge path is deliberately unaffected and
   its `land` stays as it is. health-app's repo-local `### Merge path` section does **not**
   propagate, by construction. HCA-rooted session, `pwd`-verified first.

### What was NOT touched — read this before picking up the queue

**Two consecutive days have gone entirely to instrument, and every artifact this session
produced points at more instrument.** `Q80`'s follow-on guard arm, the HCA propagation, the
`#171` alias item — all governance. Nothing here advances the product, and a cold reader infers
the queue from what is written down. So, explicitly:

- **`feat/cbti-eval-trigger`** — untouched this session. Local **and** remote, 2 `+` commits vs
  master (`git cherry`), rowed in `BRANCHES.md`. **BUILT but SUPERSEDED — needs rework, do not
  force-merge:** built against the 7-night engine, and `#165` then landed the 4-night retune and
  removed engine-`close`, so its 7-day offer eligibility and its whole close-refusal path are
  obsolete. A trial integration leaves 5 of its 11 tests failing, one semantically. Rework
  checklist is on the `BRANCHES.md` row. This is the closest thing to shippable product work in
  the tree.
- **`Q45`** — the VA CBT-I diary does not say which day a recorded nap belongs to. **DATED and
  contaminating capture right now:** `naps_min` is written at PM and the engine reads a night's
  naps from `date − 1`; that read is correct only if the instrument's nap item refers to the
  preceding day, which it does not state. Every nap-excluded night currently rests on an
  unverified attribution. Closes from the VA protocol docs or the administering clinician — not
  the workbook, searched to exhaustion. Owner: Luke.
- **`Q78`** — exclude-all starves a frequent napper at the 4-night cadence. Legible now (the
  HOLD names the tally) but not fixed. Gated by `Q45`.
- **The block-3 verdict on `#165`'s design** — the 4-night hunting titration has been live since
  block 3 opened, and neither this session nor the last looked at whether it works. This is the
  empirical test of a shipped design and the item most likely to be lost: no branch carries it,
  no question is headed by it, it appears in no OWED row. It exists only in this paragraph.
- **Lab / interpretation lane** — increments 2 (rephrase), 3 (lever-tap threads) and 5 (go-live)
  outstanding; `Q54`'s fixture-contract drift still gates the live-wiring increment.
- **Operator loops on already-merged rows** — several `BRANCHES.md` rows carry post-deploy
  checks only Luke can run (Railway, authed surfaces). Recorded, not done, and they do not
  expire.

**51 questions OPEN · 6 OWED · 23 DONE.** The OPEN count has grown every governance session.

### Single clearest next action

**Not more governance — and the setup item that used to sit here is done.** The clone is
configured and verified, so nothing stands between the next session and product work.

Pick up **`feat/cbti-eval-trigger`'s rework** or **`Q45`**. `Q45` is the sharper of the two: it
is contaminating capture *now*, every nap-excluded night currently rests on an unverified
attribution, and it closes from a document rather than from code. `feat/cbti-eval-trigger` is
the larger piece of shippable work but needs the `#165` rework first.

`Q80`'s guard arm and the HCA propagation are both real and neither is urgent. `Q80` would be
the third instrument in three sessions; let it wait until something has been built for it to
protect.
