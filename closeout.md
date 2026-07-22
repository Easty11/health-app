# Close-out — CBT-I module phase 1 (brief Steps 1–4)

Branch: `feat/cbti-module` (cut from `master` @ `d22eeba`). Held for review, pushed, **not merged**.

---

## 1 — Real commits this session (`d22eeba..HEAD`)

```
894f335 governance: DECISIONS_LOG #107/#108/#109, OPEN_QUESTIONS Q42, CLAUDE recent-landings
88fb61d feat(cbti): completed-block importer + reconciliation (Gate 4)
876dbd8 chore(cbti): gitignore personal-data workbooks before import
f0899eb feat(cbti): data substrate — diary fields + block/prescription ledgers
```

```
2026-07-22 894f335 governance: DECISIONS_LOG #107/#108/#109, OPEN_QUESTIONS Q42, CLAUDE recent-landings
2026-07-22 88fb61d feat(cbti): completed-block importer + reconciliation (Gate 4)
2026-07-22 876dbd8 chore(cbti): gitignore personal-data workbooks before import
2026-07-22 f0899eb feat(cbti): data substrate — diary fields + block/prescription ledgers
```

A fifth commit (`chore: session close-out`) lands this file + the store updates from this ritual.

What landed, against the brief's gates:

- **Gate 1** — `alembic heads` → single head `c3a2d8e5f109`. Migration `e5f2a9c7b104` chained on it.
- **Gate 2** — migration up/down/up verified clean on SQLite **in isolation** (the full chain is not
  SQLite-runnable — a pre-existing `ALTER COLUMN … DROP DEFAULT` is Postgres-only, which is why the
  suite builds via `create_all`), AND applied for real to Railway/Postgres. Suite **223 passed** (was
  206; +10 substrate, +7 import), 2 new test files.
- **Gate 3** — `cbti_blocks` + `cbti_prescriptions` created. Append-only is a model+application
  invariant (no DB trigger: no repo precedent, and a trigger would be invisible to the `create_all`
  test path). One DB-enforced constraint: `ck_cbti_prescription_decision`
  (`adopt|extend|hold|compress|close`), proven by a negative control that raises `IntegrityError` on
  `decision='tighten'`.
- **Gate 4** — completed 2026-03-19→05-13 block loaded to Railway (user 1): **1 block, 9
  prescriptions, 53 daily_records**. Per-night SE recomputed independently and reconciled vs the
  sheet's `Sleep Efficiency` **0/53 to ±0.001** (worst residual 0.000047); DB-stored `diary_se_pct`
  re-queried and reconciled 0/53. Negative control (perturb one night 0.01) flags exactly that night.
  Workbook git-ignored and read from outside the tree — never committed. `git status` shows no xlsx
  tracked.

Amendment made before acting on it (now DECISIONS_LOG #109): the Gate 4 reconciliation gained a
negative control. It earned its keep — the independent recompute caught a real defect (an
unconditional +24h midnight wrap under-read one after-midnight night by 0.445) before the load ran.

Findings surfaced, not worked around:

- `feat/cbti-module` did not exist at session open (session was on `master`); branch was cut, not adapted.
- Brief's LOG numbering was stale (said master max 100; actual **103**) — entries minted #107/#108/#109.
- The named workbook was absent at first; a differently-dated `cbti_user_data_4_April_2026.xlsx` was
  on disk and correctly refused (an April export cannot hold data through May). Correct file supplied.
- **`naps_min` attribution is silent-when-wrong** — stored on the diary's own row-date, NOT shifted.
  The VA diary's nap-timing convention must be confirmed before the engine relies on the date−1 read.
  Only 2 nap nights in this block.

---

## 2 — Pending-commit queue reconciliation

**No `;cc` pending-commit queue was carried into this session.** Work ran from a pasted brief (the
proposal), not from a chat close-out queue. The brief's own proposed decisions all landed:

- Titration-on-TST / SE-as-floor → DECISIONS_LOG **#107** (`894f335`). *(Brief called it #101; renumbered.)*
- Block-structured / readiness-isolated → DECISIONS_LOG **#108** (`894f335`). *(Brief called it #102.)*
- Negative-control amendment → DECISIONS_LOG **#109** (`894f335`).
- 12h-clock scrape failure (raise, don't fix) → OPEN_QUESTIONS **Q42** (`894f335`).

Nothing decided this session is uncommitted. Numbers are **provisional per number-at-merge** (master
max #103 / Q40): claimed at the ff-merge, renumbered if `feat/feedback-ledger` (#85–88) or
`feat/checkin-injury-probe` (#89–90) merge first.

---

## 3 — Cold-resume handoff

**State.** Phase-1 CBT-I substrate is built, tested (223 green), and loaded to Railway. The branch is
pushed and **held for chat review** — not merged. Prod schema is **ahead of master**: the migration is
applied to Railway (Postgres at `e5f2a9c7b104`) but the migration file lives only on this branch
(master's chain ends at `c3a2d8e5f109`). Merging reconciles this; abandoning the branch would strand a
prod migration with no master file.

**Open questions (this module).**
- **Q42** — UNSTARTED. 12h-clock scrape failure in `parseSleepTimingContentDesc`; owned by
  `health-connect-app`'s store; carry it there in an HCA-rooted session.
- Nap-timing convention (VA diary) — confirm before the phase-2 engine trusts the `naps_min` date−1 read.
- `~7h30` sleep-need estimate rests on **one** unconstrained week (#107's "do not revisit unless").

**Phase 2 (brief Steps 5–7) — a separate future brief, none started:**
- **Step 5** titration engine — weekly eval; sufficiency/regularity/adherence gates; TST-plateau exit
  with SE≥85% as a *floor*; adherence reads `samsung_hrv_readings` only via the `passive_overnight`
  allowlist; **replay against the imported block = Gate 5** (divergence is a finding about the rule).
- **Step 6** AM/PM surfaces — diary fields render only when an open `cbti_block` exists; prefill
  `lights_out`/`out_of_bed`/`final_wake` from Samsung but **never** `sleep_latency_min`/`waso_min`;
  reject a prefill >~4h from prescription (the Q42 12h-clock guard).
- **Step 7** ISI 7-item capture at block open/mid/close.

**Single clearest next action:** review the pushed `feat/cbti-module`, then
`git checkout master; git merge --ff-only feat/cbti-module; git push origin master; git branch -d feat/cbti-module; git push origin --delete feat/cbti-module`
— renumber #107/#108/#109 + Q42 if another governance branch merges first. Then take phase 2 as a new brief.

**Security note (one-off):** the Railway Postgres password was pasted into chat this session to enable
the load. Consider rotating it.
