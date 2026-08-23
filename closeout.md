# Session close-out — 2026-08-23

Session-open ref: `b9b1dc5` (master at open). Close ref: `e315fbc`.
Maxima at close: decisions **#233** · questions **Q117** · feedback **§32**.

---

## 1. Real commits this session

`git log --oneline b9b1dc5..HEAD` — 15 commits, 5 merges, 5 branches all merged+deleted.

```
e315fbc Merge pull request #93 from Easty11/feat/schedule-item-schema
ed3fb91 feat(schedule): validated schedule_item shape at write; close both read-path drops
3715108 chore(handoff): CHAT→CODE receipt for the schedule_item schema brief (v2)
aca2363 Merge pull request #92 from Easty11/governance/feedback-crossref-propagation
6ad4feb governance: FEEDBACK §32 — a cross-ref in an append-only entry is a propagation source
205566f Merge pull request #91 from Easty11/governance/roadmap-84-below-fold-crossref
14b2a1e governance: ROADMAP row 84 cites #123, not #112
1d028d5 Merge pull request #90 from Easty11/governance/oq-fold-divider-crossref
63efeba governance: OPEN_QUESTIONS fold divider cites #123, not #112
e834cc3 Merge pull request #89 from Easty11/governance/q115-sprint-load-routing
3f4ee10 governance: rename branch to its concern name; BRANCHES row OWED -> DONE
49514c1 governance: correct Q115's Polar cross-ref to #17/#46; record #28's own wrong pointer
8a1d025 governance: BRANCHES row for the Q115 routing-question branch
3b65d0e governance: resolve Q#NEXT -> Q115 (master max re-read Q114/#232)
17d48ef governance: open question — supramaximal work routes Metabolic-only under #28
```

Suites at close: backend **1113** (open baseline 1087), frontend **47**. Zero regressions.

Branch terminal-state gate: **PASSES.** `git branch` and `refs/remotes/origin` both hold
`master` only. Every branch touched this session is merged + remote-deleted:
`claude/neuromuscular-sprint-routing-16u397` (renamed, then deleted by the operator after this
session's git transport refused every ref-deletion form),
`governance/q115-sprint-load-routing`, `governance/oq-fold-divider-crossref`,
`governance/roadmap-84-below-fold-crossref`, `governance/feedback-crossref-propagation`,
`feat/schedule-item-schema`.

---

## 2. Pending-queue reconciliation

**No `;cc` PENDING queue was handed to this session.** Chat→Code crossings were two drafts and
one brief, each transcribed rather than queued. Reconciled individually:

| Chat-side item | Landed | Where |
|---|---|---|
| `OPEN_QUESTIONS` draft — supramaximal work routes Metabolic-only | YES | `17d48ef` / `3b65d0e`, merged `e834cc3` → **Q115** |
| Ruling — amend Q115's `#10` cross-ref, do not mint a `#28` supersession | YES | `49514c1` |
| Ruling — rename the branch off the banned `claude/<hash>` form | YES | `3f4ee10` |
| Ruling — correct `OPEN_QUESTIONS.md:1123` to `#123` | YES | `63efeba`, merged `1d028d5` |
| Ruling — same treatment for `ROADMAP.md:84` | YES | `14b2a1e`, merged `205566f` |
| `FEEDBACK` draft — a cross-ref in an append-only entry is a propagation source | YES | `6ad4feb`, merged `aca2363` → **§32** |
| `schedule_item` schema brief (v2), steps 1/2/3/5/6 | YES | `ed3fb91`, merged `e315fbc` → **#233**, `SCHEMA.md` 024, **Q116**/**Q117** |
| `schedule_item` brief, step 4 (backfill) + GATE 4 (prod assertions) | **NO** | Not runnable — no DB route from this session. Carried in **Q116**, not provisional: it is a recorded open question with its own next action. |

**Nothing decided this session is uncommitted.** The one piece of scope that did not land is
step 4, and it did not land because it was not executable here — recorded, not forgotten.

---

## 3. Cold-resume handoff

### What this session changed

`schedule_item` gained a **closed, validated shape at write** (#233). `validate_schedule_item`
refuses 422 on an unknown key, a non-weekday in `days`, a truthy-string boolean,
`sessions_per_week` outside 1–14, a missing required field, an out-of-set
`expected_load`/`time_of_day`; an unacknowledged day overlap is a structured 409 naming every
clashing row. It sits inside `upsert_knowledge_entry` — the shared path for
`POST /knowledge/entry`, chat, and `routers/health.py` — **not** only on the route the brief
named, because chat does not write through that route and Step 2's whole objective was the chat
writer seeing a rejection. `hard` (scheduling) and `expected_load` (cost) are separated as two
axes; any future cost axis resolves into `expected_load`'s vocabulary rather than minting a
parallel one. `supersedes` triggers on **day overlap alone**. Both `context_builder` silent-drop
sites for unknown weekday names are closed and now report into THIS WEEK FLAGS.

Four governance corrections also landed: **Q115** (the neuromuscular routing question), and the
`#112`→`#123` cross-reference propagation in two mutable stores plus **§32**, the rule that a
cross-reference in an append-only entry is a propagation source rather than a leaf.

### Immediate next action — one thing, and it is the operator's

**Run `Q116`: the `schedule_item` backfill.** Route is `railway connect health-app-DB` from
PowerShell, **one statement per run** (`FEEDBACK` §29 — the dashboard editor silently returns
zero rows on a multi-statement paste). Order is fixed and the first step is not the backfill:

1. **GUARD stop-condition first** — verify the live row set against the 2026-08-23 read
   (25 rows, 18 active, 4 users, the duplicate pairs, the three stale-active rows). **If it has
   moved, the row table in Q116 is a hypothesis: re-derive, do not apply.**
2. Backfill — 3 retire, 5 correct (user 1), 10 conform (users 5/7/8).
3. The five GATE-4 assertions, each paired with a positive control (`FEEDBACK` §17).
4. Q116 closes.

`Health_app_data` does **not** unblock this: its tools are read-only scoped health readers with
no arbitrary SQL and no `schedule_item` reader. The backfill is operator-side regardless.

### Open questions, grouped

- **Loop-closes owed from this session:** **Q116** (the backfill above — the one live gap
  between master and correct data), **Q117** (`expected_load` granularity; not actionable until
  a second between-levels session appears).
- **Gating the next two lanes:** **Q105** (capacity-token spelling), **Q106** (how a slot's
  `minutes` reaches the prescription) — both belong to the weekly resolver.
- **Design-pass questions, unblocked but unstarted:** **Q115** (routing amendment to `#28`,
  which also carries the `#10`→`#17`/`#46` correction), **Q102** (`restrictions[]` is dead
  data), **Q109**, **Q111**, **Q112** (appended this session; its cited `phases` evidence goes
  with Q116's row-9 correction), **Q114** (`FEEDBACK` has no `CHECKS` arm — a live instance
  occurred this session and was resolved by hand).
- 121 `**State:** OPEN` markers across the store; the above are the ones with live consequences.

### NOT TOUCHED — read this before planning the next session

**Four of five merges this session were governance.** One feature lane moved (`schedule_item`).
That is a better ratio than a pure-instrument session, but the pull is visible and worth naming:
three of the five branches existed only to correct cross-references between governance entries.
The corrections were real and one of them (`§32`) generalises — but a reader inferring the queue
from what is written down would conclude this project's work is governance, and it is not.

Standing still, with nothing about them changed this session:

- **Calendar view** — next in the queue and **not brief-ready**. It needs a chat design pass
  first: `GET /knowledge/schedule` (`routers/knowledge.py:238–249`) returns raw rows and
  interprets no shape, so a view built on it renders `schedule_item` directly and gets rewritten
  when the resolver lands — or it waits for the resolver. That is an ordering decision about the
  resolver, not a view detail. Do **not** open it as a brief until settled.
- **Weekly resolver** (`ROADMAP` NEXT, the lane #221 deferred) — untouched, gated on Q105/Q106.
  `weekly_template` has been a declaration with no consumer since #221.
- **Hevy set store** — queued behind both of the above; no work this session.
- **Injury-ledger backfill audit** (the lane #222/#223 deferred) — untouched.
- **Interpretation hub shell (#150)** — still BUILT, held for review. Unchanged for multiple
  sessions.
- **CBT-I** — no work this session. Q78 (two over-threshold nap nights starving a cycle) still
  OPEN and now unblocked rather than gated.
- **The cross-repo shared-block edit** (`ROADMAP` NOW, OWED) — the `#NEXT` rule still names
  `DECISIONS` entries only, and the tree still carries ~20 `#NEXT` tokens in `.py`/`.jsx` that
  no guard can see. This session hand-executed the count-verified scoped replace that row
  prescribes; it remains unencoded.

### Carried, deliberately not minted

- **Clone-depth dependency.** `test_context_builder_output_unchanged_pre_post_refactor` shells
  out to `git show 3360ed5:backend/context_builder.py`. On a **fresh shallow clone** that object
  is absent and the test fails, so master reports red until `git fetch --unshallow`. Nothing
  declares the dependency. A `FEEDBACK` candidate; not minted here because `§32` already landed
  off this session and two entries from a schema session fails the moratorium filter.
- **`#112` has now been mis-cited three independent times** — `OPEN_QUESTIONS.md:1123`,
  `ROADMAP.md:84`, and an earlier brief that resolved it to `#115` (recorded at
  `BRANCHES.md:84`). `§32` covers the mechanism; the specific number attracting errors is the
  observation. Stronger `FEEDBACK` candidate than the branch-name gap below if either is minted.
- **Brief-writing-path gap.** A session brief specified a branch name `CLAUDE.md` bans and
  nothing caught it until PR review. One instance; `FEEDBACK` only if it recurs.
- **The origin of the `#112` miscitation is unfixable in place.** `#123`'s own Rationale
  (`DECISIONS_LOG.md:3938`) carries it, and `DECISIONS_LOG` is append-only. `§32` is where a
  reader tracing the pattern lands instead.

### Method notes worth carrying

Three defects this session were caught by **reading the cited source before relying on it**,
not by any guard: the `#10` cross-ref in the Q115 draft, the `#112` cross-ref in two stores
(including one in the ruling that commissioned the fix), and — the near-miss — the `#NEXT`
resolution that asserted 9 tokens in the appended region and found 8, the ninth sitting in the
`Q112` edit above it. A blanket replace would have taken the pre-existing prose with it, which
is `#175`/`#220` exactly. The count-invariant worked **because it was an assertion rather than
a sweep**.

`Q114` is live and was demonstrated: `CHECKS` has no `FEEDBACK` arm, so nothing mechanical would
have caught a `§#NEXT` reaching master in `6ad4feb`. It was resolved by hand.
