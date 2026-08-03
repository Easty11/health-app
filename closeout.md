# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-03. Branch at close: none — `gov/next-resolution-guard` ff-merged to master
and deleted both sides. Session-open ref: `3fadc96`.

**Number-at-merge is now enforced rather than trusted (`#167`).** A pre-push ref guard refuses any
push to master carrying an unresolved `### #NEXT` or `## Q#NEXT`.

**Read this before trusting anything below: TWO Code sessions shared this clone today.** Master's
current state is the product of both. `#166` and `#168` are the other session's; `#167` is this
one's. The overlap produced one real incident, recorded as `FEEDBACK` §19 rows **17** and **18** and
summarised in §3. Any state either session reports is stale on arrival while that condition holds.

## 1. Real commits this session

`git log --oneline 3fadc96..master`, **this session's own** marked ▸:

```
e32fd8d governance: resolve #NEXT -> #168 (on-branch, pre-ff)              [other session]
ad94ee3 feat(chat): #NEXT show the model the whole exercise catalogue       [other session]
0f996ea governance: resolve #NEXT -> #167 (on-branch, pre-ff)              ▸
9973a14 governance: BRANCHES row, FEEDBACK §19 rows 17/18, ROADMAP debt    ▸
672e0ca feat(governance): enforce number-at-merge with a pre-push ref guard ▸
784763c governance: #166 owed-item (1) discharged — orphan recovered       ▸ (other session's CONTENT)
11b6b9d governance: #166 landed and deployed                               [other session]
e438f45 governance: resolve #NEXT -> #166; FEEDBACK §23.1                  [other session]
23d3e9b fix(hevy): #NEXT create-response parse aborted after the create     [other session]
```

`784763c` is committed by this session but **authored by the other** — see §3.

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-08-03 governance: resolve #NEXT -> #168 (on-branch, pre-ff)
2026-08-03 feat(chat): #NEXT show the model the whole exercise catalogue — #61's capability, unsurfaced
2026-08-03 governance: resolve #NEXT -> #167 (on-branch, pre-ff)
2026-08-03 governance: BRANCHES row, FEEDBACK §19 rows 17/18, ROADMAP propagation debt
2026-08-03 feat(governance): enforce number-at-merge with a pre-push ref guard
2026-08-03 governance: #166 owed-item (1) discharged — orphan recovered and resolver-verified
2026-08-03 governance: #166 landed and deployed — row carries the three owed items
2026-08-03 governance: resolve #NEXT -> #166; FEEDBACK §23.1 standing gate; CLAUDE convention + landings
2026-08-03 fix(hevy): #NEXT create-response parse aborted after the create — false negative + orphan
2026-08-03 governance: record the #165 merge, deploy verification, and the eval-trigger rework
```

## 2. Pending-queue reconciliation

No `;cc` queue. The input was a directive, not a brief: *build the pre-land `#NEXT` guard now*,
after it had been parked twice as "when I'm not mid-tangle".

| Item | Outcome |
|---|---|
| Pre-push `#NEXT` guard | **Landed** as `#167`. Script + repo-versioned hook + shared-block rule. |
| Mechanism fork (land-alias vs ref check) | **Adjudicated to the ref**, on evidence — see §3. |
| `FEEDBACK` §19 rows | **Landed** — 17 (`COUPLED`) and 18 (`MODEL`), `17 caused 18`. |
| ROADMAP propagation debt | **Landed** — the shared-block edit owes HCA a byte-identical copy. |
| `BRANCHES` row | **Landed**, and the branch is now DONE. |
| `#NEXT` → integer | **#167**, claimed on-branch pre-ff with master re-read at that instant (#166). |
| HCA propagation itself | **NOT done — owed.** Requires an HCA-rooted session. |

## 3. Cold-resume handoff

### The guard (`#167`)

- `scripts/check_governance_placeholders.py` — exits 0 clean, 1 on a placeholder (printing every
  offending file and line, so matches are **read, not counted**), 2 when it cannot run. A check that
  could not run must never be indistinguishable from one that passed.
- `.githooks/pre-push` — refuses a push whose remote ref is `master`/`main`. Branch pushes untouched:
  a placeholder is *correct* on a branch and only wrong on master.
- `CLAUDE.md` — the rule, **inside the shared loop block**, plus the `git config core.hooksPath
  .githooks` install line beside the `land`/`stale` aliases.

**Why the ref and not `git land`** — this is the load-bearing choice and it was settled by evidence,
not preference. The merge that healed `#162` was done **by hand**
(`checkout master && merge --ff-only && push`), so an alias-only guard would not have fired for it.
The placeholder reaches master by whichever path is convenient that day.

**Why anchored on the heading** (`#113`) — `CLAUDE.md`'s own rule text, `#148`'s entry and every
corrected entry legitimately quote the token. A substring match would fire on the files that define
the convention, get bypassed out of habit, and protect nothing.

**Controls.** Positive control is the *real defect, not a fixture*: run against `001df4c` — the
actual `feat/hub-shell` merge that put a live `### #NEXT` on master — and it exits 1 naming
`DECISIONS_LOG.md:5833`. Negative: clean master exits 0, and the three false-positive shapes are
asserted explicitly. Hook end-to-end with crafted stdin: master+placeholder REFUSED, same ref to a
branch ALLOWED, clean master ALLOWED, zero-sha deletion ALLOWED.

**Exercised on its own landing** — the branch push carrying `### #NEXT` was allowed, and the master
push after resolution was allowed. Both pushes verified by `git ls-remote`, not by exit status.

**Known gap, recorded not papered over:** the `@claude` GitHub Action pushes without a local hook and
is **not** covered. Closing it means a CI check, not a hook.

**`core.hooksPath` is per-clone config.** A fresh clone gets the files and no active hook until
`git config core.hooksPath .githooks` is run. Landing the file does not arm it.

### The incident — and why it was smaller than first reported

The other session ran `git add -A` in the shared tree and swept this session's uncommitted guard work
into a commit (`f64d4bb`) whose message described only its own one-line `BRANCHES.md` edit.

It was then reported to the operator as *"committed and pushed to master"*, and an A/B/C recovery
decision was escalated. **Independently verified: the push never landed.** `origin/master` was
`11b6b9d` throughout and `f64d4bb` reached no remote. All three recovery options were premised on a
breach that did not happen; the question dissolved rather than being answered.

Resolution, in the order that mattered:

1. **Split before push, not after.** The branch tip *was* the mixed commit. Unpushed, the split was a
   soft reset and path-scoped restage — free. Pushed, it would have cost a force-push on shared
   history. This is the one place `#98`'s push-early instinct and rewrite-while-cheap genuinely
   conflict, and the rewrite has to win because the window closes permanently at the push.
2. **The other session's line was preserved, not re-authored.** Extracted to a patch outside the repo
   *before* any reset, then committed alone as `784763c` with authorship stated in the body. It is
   the `#166` orphan-discharge record — resolver-verified — and re-deriving a verified record from
   memory is how a closed loop silently re-opens.
3. `FEEDBACK` §19 rows **17** and **18**, `17 caused 18` (`caused_by` derived, never authored).

Row 17 is **COUPLED**, not `MODEL`: a `MODEL` row types the fix as "the agent should have been more
careful", which fails on the next tired session. Prevention is two-part — path-scoped staging
(proximate) and **worktree isolation** (the one that makes the condition unreachable). Row 18 is
`MODEL` and stands alone: *a push is verified by the remote ref, never by the push command's exit.*
Not a new principle — it is `#116`/`#121`'s probe-the-artefact rule and `#103`'s
discriminate-on-identity rule, applied one layer down to git.

### State at close

- `master` = `e32fd8d`, local == remote (verified by `ls-remote`), working tree clean.
- Audit: **max 168 · dupes none · gaps none · unnumbered `#NEXT` 0 · Q max 78.**
- Backend suite **719 passed**. Guard passes against `origin/master` (exit 0).
- `#162`, which rode master for three sessions, remains healed.

### Outstanding (owner: Luke)

1. **HCA propagation — the substantive one.** The `CLAUDE.md` change is inside the shared loop block,
   so `health-connect-app/CLAUDE.md` owes a byte-identical copy: **two** insertions (the enforcement
   bullet, and the `core.hooksPath` install line beside the aliases), between the `BEGIN`/`END SHARED
   LOOP RULES` markers. HCA-rooted session only, `pwd`-verified first — the folder picker has opened
   the wrong repo before. The script and hook do **not** propagate; whether HCA wants its own
   enforcement is left undecided rather than pre-empted. Recorded in `ROADMAP` NOW per `#112`.
2. **`feat/cbti-eval-trigger` — rework, do not merge.** Superseded by `#165` before it landed: its
   7-day offer eligibility and its whole close-refusal path are obsolete, and a trial integration
   leaves 5 of its 11 tests failing, one semantically. Full checklist on its `BRANCHES.md` row. Its
   `#NEXT` is now **169** — master has moved twice since that row was written.
3. **Concurrent sessions in one clone.** The generator of the whole incident. Until sessions are
   isolated (separate worktrees), every reported state is stale on arrival — this session watched
   master move under it three times while reporting.
4. **`#165`'s real verdict is not in the code.** The first genuine 4-night cycle on block 3 decides
   whether the dither centres or wanders. If it wanders, the entry's revisit clause names the first
   suspects: the `Q45` nap exclusion and `SE_FLOOR_PCT`.

### Single next action

Discharge the HCA propagation from an HCA-rooted session — it is the only item where delay actively
degrades something, because master now carries a shared-block edit with nothing mirroring it, which
is the two-master drift the block exists to prevent.

### Governance stores changed this session

`DECISIONS_LOG.md` · `FEEDBACK.md` · `ROADMAP.md` · `BRANCHES.md` · `CLAUDE.md`
(`OPEN_QUESTIONS.md` unchanged by this session — `Q78` was the prior one's.)
