# Session close-out — 2026-08-05 → 2026-08-06

Session-open ref: `f68c73c`. Head at close: `ec26319` (pre-close-out commit).

---

## 1 — Real commits this session

`git log --oneline f68c73c..HEAD`

```
ec26319 Merge pull request #26 from Easty11/gov/175-precondition-narrowed
61a82ec gov: mint #176 — governance edits bank to one batched PR, gated by diff shape
95c18da gov: #175's identity precondition resolves safe and narrows; correct the stale docstring
2e91f15 Merge pull request #25 from Easty11/gov/175-source-admission
9ef8f73 gov: mint #175 — source admission replaces source priority for HC sleep
82453b5 Merge pull request #24 from Easty11/gov/q83-mirror-loop-resolution
84b8644 gov: Q83 — the Withings sub-finding is confirmed as the cause, and it reframes the fix
e84154c Merge pull request #23 from Easty11/chore/branches-self-row-convention
89a41ad chore(governance): a branch's own BRANCHES row records its terminal state, not its in-flight state
9ebd583 Merge pull request #22 from Easty11/chore/post-landing-pointers
e10e639 chore: refresh Recent landings and close the BRANCHES row for #173/#174
51f19c1 Merge pull request #21 from Easty11/gov/open-questions-sweep
9bd31b9 gov: OPEN_QUESTIONS sweep — close Q3/Q4/Q7, re-scope Q5/Q6/Q20, mint Q81–Q84
```

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-08-06 Merge pull request #26 from Easty11/gov/175-precondition-narrowed
2026-08-06 gov: mint #176 — governance edits bank to one batched PR, gated by diff shape
2026-08-05 gov: #175's identity precondition resolves safe and narrows; correct the stale docstring
2026-08-05 Merge pull request #25 from Easty11/gov/175-source-admission
2026-08-05 gov: mint #175 — source admission replaces source priority for HC sleep
2026-08-05 Merge pull request #24 from Easty11/gov/q83-mirror-loop-resolution
2026-08-05 gov: Q83 — the Withings sub-finding is confirmed as the cause, and it reframes the fix
2026-08-05 Merge pull request #23 from Easty11/chore/branches-self-row-convention
2026-08-05 chore(governance): a branch's own BRANCHES row records its terminal state, not its in-flight state
2026-08-05 Merge pull request #22 from Easty11/chore/post-landing-pointers
```

**Six PRs (#21–#26), six branches, all merged and remote-deleted.** Behaviour shipped: **none** — the only
non-markdown change all session was a corrected docstring in `backend/routers/health_connect.py`.

---

## 2 — Pending-queue reconciliation

Carried in from the 2026-08-03 chat close-out as the *OPEN_QUESTIONS sweep* brief. **Every item landed.**

| Brief item | Disposition | Commit |
|---|---|---|
| A1 — new decision, deep-sleep extends `#71` | Landed as **`#173`** (brief said `#168`) | `9bd31b9` |
| A2 — new decision, HC field contract | Landed as **`#174`** (brief said `#169`), Status **OWED** | `9bd31b9` |
| B1 — Q3 → `DONE → #168` | Landed as `DONE → #173` | `9bd31b9` |
| B2 — Q4 → `DONE → #64` | Landed | `9bd31b9` |
| B3 — Q5 re-scope, capture precondition struck | Landed, OPEN | `9bd31b9` |
| B4 — Q6 re-scope (unbuilt, not unverified) | Landed, OPEN | `9bd31b9` |
| B5 — Q7 → `DONE → #72` | Landed | `9bd31b9` |
| B6 — Q20 decoupled from Q7 | Landed, OPEN | `9bd31b9` |
| C1/C2/C3 — three new questions | Landed as **Q81/Q82/Q83** (brief said Q79/Q80/Q81) | `9bd31b9` |
| D — Gate-3 footnote pointer | Landed | `9bd31b9` |
| E1 — optional Q82 (schema wider than client) | **Confirmed by operator**, landed as **Q84** | `9bd31b9` |

**Numbering: the brief's only casualty.** It hardcoded `#168`/`#169`/`Q79`/`Q80`; master had claimed all four
for unrelated content between drafting and this session (`#168` exercise catalogue, `#169` guard heading
grammar, `Q79` `@claude` Action pushes, `Q80` uniqueness-and-gaplessness). Resolved by writing placeholders
and adjudicating at merge — master's max was re-read immediately before **every** merge this session.

**Emergent items, not in the brief** — all landed:

| Item | Disposition | Commit |
|---|---|---|
| `BRANCHES` self-row convention (terminal state, not in-flight) | Landed | `89a41ad` |
| Q83 Withings sub-finding → confirmed mirror loop, fix reframed | Landed | `84b8644` |
| **`#175`** — source admission replaces source priority | Landed, Status **OWED** | `9ef8f73` |
| `#175` identity precondition resolved safe + narrowed; stale docstring corrected | Landed | `95c18da` |
| **`#176`** — batched governance landings, gated by diff shape | Landed | `61a82ec` |

**Nothing is provisional.** No decided-but-uncommitted item remains.

**Banked for the next batch — deliberately NOT actioned** (per `#176`(a): do not spawn a new item at
close-out): *"A check whose own pattern is unverified is not yet a check."* Three times this session a
substring/anchor mistake produced a confidently-green wrong answer — the `#NEXT` blanket replace that
corrupted 55 + 104 lines with the guard at exit 0; the invariant-(c) removal census whose own `^-[^-]`
pattern could not match a removed markdown bullet; and the guard's own heading-only blind spot that
motivated `#176`(c). This belongs in governance as a rule. Mint it in the next governance batch, not here.

---

## 3 — Cold-resume handoff

### What is canonical now

- **Decisions `#173`–`#176`** on master. `#174` and `#175` are Status **OWED** — decided, not implemented.
- **Questions `Q81`–`Q84`** minted; **Q3 / Q4 / Q7** closed; **Q5 / Q6 / Q20 / Q83** re-scoped and OPEN.
- **`CLAUDE.md`** gained *Batched governance landings* (`#176`) in the repo-specific merge-path section —
  verified outside the shared loop-rules block (markers at lines 20 / 278), so **no HCA mirror is owed for it**.
- Guard green on master; `#176` unique and contiguous; no branch in limbo.

### The three live threads (OWED — none blocks closing)

1. **Q83 / Withings.** Cause confirmed: the identical-`record_start` rows are a **Health-Mate mirror** of
   Samsung's own sleep, not a second sensor — so discarding them loses no signal.
   - **(a) Source-side — do this first, needs no repo work at all.** Revoke Withings' Health-Connect
     **write** permission for Sleep, on the phone. Kills the duplicate *before* ingest and demotes (b) from
     live bug fix to robustness.
   - **(b) Code-side — `#175`'s admission filter.** Blocked behind the identity question below.
2. **`#175` — OWED on implementation.** `_aggregate_day` still selects by max-duration across all writers.
   Before the filter is written: decide **`'unknown'`'s policy explicitly** (admit-with-flag / fall back to
   pre-`#175` max-pick / log-and-count per `#74`) — a strict allow-list excluding `'unknown'` fail-closes
   the legitimately-unidentified rows *silently*, which is the defect class `#175` exists to remove. Plus
   one bounded `health_connect_record_sources` coverage query when Railway is reachable: `'unknown'` vs
   real per record type, **split by era**. Admission runs **before** Q82's fragment-merge.
3. **`#174` — OWED on the field-name contract test.** The five dead-branch deletions in
   `backend/routers/health_connect.py` **must not ship without it**: the load-bearing half of `#174`'s
   evidence (what HCA actually posts) is a cross-repo read unverifiable from this tree, so without the test
   the deletion breaks production **silently** on the next sync.

### What did NOT move — name it, because it is invisible otherwise

**This session shipped zero behaviour.** Six PRs, ~all prose, one docstring. It went entirely to the
*instrument* — the governance stores and the rules governing them — and so did the sessions immediately
before it (`#169` governance grammars, `#170` guard CI surface, `#171`/`#172` PR-gated merge path). That is
**four consecutive sessions on the instrument rather than the thing being instrumented**, and it is stated
here because a close-out that lists only what moved hands the next session more of the same: the queue a
cold reader infers is the queue that is legible.

Even this session's substantive decisions (`#173` readiness, `#174` field contract, `#175` source
admission) are **all decided-not-implemented**. Nothing in the product changed.

**Standing still, unchanged this session, gated as noted** — from `ROADMAP.md` NOW/NEXT:

| Lane | State | Gate |
|---|---|---|
| **CBT-I nap day-attribution (Q45)** | DATED, contaminating capture **now** | Close from VA CBT-I protocol docs or the clinician. Every nap-excluded night currently rests on an unverified attribution. |
| **CBT-I manual evaluation trigger** | Built but **SUPERSEDED — REWORK** | `feat/cbti-eval-trigger` obsolete against `#165`'s 4-night retune; 5 of 11 tests fail. Do **not** force-merge. |
| **Lab upload pipeline** | Uploading unpaused | Operator decision owed on the junk rows. |
| **Interpretation layer** | 1b delivered; **2 / 3 / 5 UNSTARTED** | Rephrase pass → lever-tap thread → go-live. Nothing gates increment 2. |
| **Hub shell (`#150`)** | UNBLOCKED, operator-preferred next pick | Nothing. |
| **`lab_accession`** | Queued, strongest small alternative | Nothing. |
| **Appointment brief** | Not started | Lab pipeline + interpretation layer. |
| **Q82** — fragmented Samsung nights undercount | OPEN | Sequenced after Q83/`#175`. |
| **Q6** — strength volume-load | OPEN, re-scoped to unbuilt | No `load_metrics` table exists. Strength contributes **zero** to the deployed load metric today. |
| **Cross-repo propagation ×4** | All **OWED** | HCA-rooted session only, `pwd`-verified. `#172`'s boundary criterion is the newest of the four. |

### Single clearest next action

**Do the Withings Health-Connect write revoke for Sleep, on the phone.** It is free, needs no keyboard, and
removes a live data-contamination bug **at source** rather than documenting it.

Then, at a keyboard: the next session should go to a **product lane**, not the instrument. `ROADMAP.md` NOW
is dated and ordered; **interpretation increment 2 (rephrase pass)** and the **hub shell (`#150`)** are both
unblocked and need nothing decided first.
