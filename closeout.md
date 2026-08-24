# Session close-out — 2026-08-24 (post-deploy OWED discharge)

Session-open ref: `004da34` (master at open). Close ref: this close-out commit on `master`.
Maxima at close: decisions **#236** · questions **Q119** · feedback **§32** (all unchanged — nothing minted).

This was a **single-purpose governance session**: discharge the one OWED the prior session
(`feat/hc-sync-contract-collapse`, PR #95) left standing — the `§8`-class post-deploy real-sync
verification recorded in `#235` Status and the hc-sync `BRANCHES` row. The operator ran the sync
(2026-08-24, PASS) and reported the evidence; this session recorded the discharge and one structural
finding it surfaced. No code, no schema, no migration, no tests.

---

## 1. Real commits this session

`git log --oneline 004da34..HEAD` — 2 commits (1 on `gov/hc-sync-post-deploy-discharge` + the merge).

```
636c612 Merge pull request #98 from Easty11/gov/hc-sync-post-deploy-discharge
fc7dfa0 gov: discharge #235 post-deploy sync verification OWED (2026-08-24 PASS)
```

Governance stores touched (`git diff --name-only 004da34..636c612`): **`DECISIONS_LOG.md`**,
**`BRANCHES.md`** — plus `CLAUDE.md` (Recent-landings) and `closeout.md` in this close-out commit.

Branch terminal-state gate: **PASSES.** `git branch` and `refs/remotes/origin` (post-prune) both hold
`master` only. The one branch touched, `gov/hc-sync-post-deploy-discharge`, is merged (`636c612`) +
remote-deleted; `git cherry origin/master` reports nothing unmerged on any local branch.

---

## 2. Pending-queue reconciliation

**No `;cc` PENDING queue was handed to this session.** The work was a direct operator instruction —
"discharge the post-deploy OWED, evidence attached" — adjudicated and landed in one commit. Nothing is
provisional.

| Item | Landed | Where |
|---|---|---|
| `#235` Status: post-deploy `§8` verification marked DISCHARGED (2026-08-24 PASS), evidence quoted | YES | `fc7dfa0` (pure insertion, 13 lines) |
| `BRANCHES` hc-sync row: OWED item (3) → DISCHARGED; (1) done-at-merge; (2) still OWED session-2 | YES | `fc7dfa0` (declared OWED-cell replacement) |
| Structural HRV finding recorded as a cross-ref to `#236`/`Q83` (no new question minted) | YES | `fc7dfa0` (#235 Status + BRANCHES) |

`#176`(c) audit: `DECISIONS_LOG` is a pure insertion (0 removed); the single `BRANCHES` removal is the
declared OWED-cell replacement of the hc-sync row. Placeholder guard green (local hook + `placeholder
guard (POSIX)` on PR #98). No numbers minted — master maxima unchanged at **#236 / Q119**, so nothing to
re-resolve at the merge instant (base stayed `004da34` through merge).

**Recent-landings note:** this session's landing completes the immediately-prior pointer's own "still
owed" tail, so that line was **amended** to its current truth (post-deploy verified 2026-08-24) rather
than prepended as a near-duplicate feature line — pointer-only and non-contradictory, no new decision to
add.

---

## 3. Cold-resume handoff

### What this session changed

The `/health-connect/sync` post-deploy verification is **done**. One real sync ran 2026-08-24 10:43:37Z
against the deployed, now-stricter endpoint. **PASS** — eight in-window dates upserted, pre-window
`synced_at` untouched (non-destructive upsert), no 422 and no `HC sync rejected` shape-log, `unattributed
== 0` across `exercise` 75 / `sleep` 129 / `steps` 78 / `heart_rate` 49311. The `heartRateMapper`
`undefined`→dropped-`bpm` risk `#235` named did not fire on real data. The hc-sync contract collapse
(`#234`/`#235`/`#236`) is now **verified live end-to-end** — the loop the prior close-out named as the
immediate next action is closed.

### The one new finding — structural, carried as a cross-ref, NOT a new question

`health_connect_syncs.hrv_rmssd` has **never** been populated (`COUNT WHERE NOT NULL = 0` over the
table's life) and no `hrv` `record_type` has ever reached `record_sources`: **Samsung Health does not
write HRV to Health Connect.** The scraper path (`samsung_hrv_readings`, the `passive_overnight` stream
that already feeds `daily_records.passive_hrv_ms`) is the **sole** HRV source. This is upstream of the
sync contract — the contract is sound; the HRV gap is a source-availability fact — and it is exactly the
multi-writer HRV-source arbitration `#236`/`Q83` already own. It is recorded in `#235` Status and the
BRANCHES row as a cross-ref; **no new Q was minted** (operator instruction), and `Q119` stays OPEN at its
current priority. When the `#236` E3 lane / `Q83` device-switch arbitration is picked up, this is a
load-bearing input: any HRV-source blend must treat Health Connect as carrying **no** Samsung HRV.

### Immediate next action

With the hc-sync loop closed, the most concrete owed item in the repo is once again **`Q116` — the
`schedule_item` backfill** (18 active rows behind a live validator, never backfilled; needs
`railway connect health-app-DB`, operator-side; the GUARD stop-condition runs FIRST). It has been the
standing "one live gap between master and correct data" for two sessions and did not move here.

### Open questions, grouped (62 OPEN; the ones with live consequences)

- **Owed loop-closes from prior sessions:** **Q116** (`schedule_item` backfill — the one live master↔data
  gap, needs DB access), **Q117** (`expected_load` granularity).
- **The hc-sync session's forks, all OPEN, none blocking:** **Q118** (HC record metadata persistence —
  `id`/`recordingMethod`/`device` accepted-and-dropped; `id`-as-dedup-key is a `#36`/`#37` ruling),
  **Q119** (windowed backfill recovery path — sharpened, not gated, by this PASS: a break that outlives
  the ~7-day fetch window is still permanent-by-default; only becomes urgent if a real sync FAILS and the
  repair outruns the window).
- **Gating the E3 lane (`#236`):** **Q83** (HC sleep/HRV selection is source-blind — the multi-writer
  blend that gates a device switch; **now carrying this session's finding that HC holds no Samsung HRV**),
  **Q105**/**Q106** (weekly-resolver vocabulary), and the baseline/confidence/arbitration design lane
  named inside `#236` itself.

### NOT TOUCHED this session — read before planning the next

This was a **one-line governance discharge**, the second consecutive governance-class session after the
hc-sync product run. The product/feature lanes that stood still (unchanged from the prior close-out, and
named again because absence is not self-reporting):

- **`schedule_item` backfill (Q116)** — untouched. Still the one place master carries a live validator
  with 18 non-conforming rows behind it. Needs DB access, operator-side. The most concrete owed item.
- **The E3 lane (`#236`)** — ruled as a *design*, not built. Order: recovery-derivation design first
  (baseline/confidence/arbitration), adapter work after, session-2 HCA conformance at the tail. This
  session's HRV finding feeds directly into it.
- **HCA mapper de-dup + O3 client conformance** — session-2 work behind `#236`, still OWED on the hc-sync
  BRANCHES row (item 2); `SyncScreen.js` still discards the sync response, so the new per-stream counts
  reach no client yet (Q118 metadata likewise).
- **Interpretation lane** — increments **2 (rephrase, #202) done**; **3 (lever-tap) UNSTARTED**;
  **5 (go-live) done (#194)**. Increment 3 is the next sequenced product pick.
- **Weekly resolver (`ROADMAP` NEXT, `#221` deferred)** — untouched; gated on Q105/Q106.
- **Interpretation hub shell (#150)** — BUILT, held for review; unchanged for several sessions.
- **CBT-I** — no work; **Q83** (sleep/HRV source-blindness) and Q78 (nap-night starvation) both OPEN.
- **Injury-ledger backfill audit** (`#222`/`#223` deferred), **Banister build (OWED)**, the
  `restrictions[]` contraindication design pass (**Q102**) — all untouched.
- **Cross-repo shared-block edit** (`ROADMAP` NOW, OWED) — the `#NEXT` rule still names DECISIONS entries
  only; source still carries `#NEXT` tokens no guard sees. Unencoded.

### Operator-side items that decay if not captured (kill-rule keeps them out of the repo)

- **Ring-intermittency start date** — the approximate date the Galaxy Ring's HRV intermittency began.
  Now doubly relevant: this session confirmed the *only* HRV that reaches the model is the scraper's
  `passive_overnight` stream, so a corrupted-baseline span there has no HC fallback to cross-check against.
- **Samsung warranty status** — decides whether the Garmin / HRV-arbitration question (`Q83`) is live
  procurement or contingency.

### Method note worth carrying

The discharge followed the `feat/cbti-eval-trigger-v2` precedent (a merged branch's row updated in place
once the live check ran) and the irreversible-write pre-ship discipline (`#166`/`§23`): the OWED existed
precisely because `#235`'s How-you-know admitted an unexercised live write path, and the live probe — not
the golden fixture — was the gate. The probe also surfaced a finding the fixture could not (the
never-populated HRV column), which is the reason the gate was a real gate and not a formality.
