# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-23 → 07-24 · CBT-I surfaces brief: Steps 2 and 3 landed on the branch — block status, and Samsung prefill with a verified mapping and a demonstrated gate

## 1. Real commits this session

Session-open ref: `6662439` (the prior close-out). Five commits on **`feat/cbti-surfaces`**,
all pushed, **none merged** — `git cherry origin/master` marks all five `+` (real work,
upstream-absent). `origin/master` is unchanged at `6662439`.

```
8300595 governance: reclassify total_/actual_ as semantic; record Step-3 findings on the branch row
4636b94 feat(cbti): prefill diary clock defaults from Samsung, gated against the prescription
89eca95 review: correct the date-shadow mechanism, log the inference pattern, file the denylist drift
d61412b feat(cbti): block status and prescription-in-force on /prefill and /today
e70f7da docs: fold waking-cause instrumentation into the standing brief's Steps 4/6
```

```
2026-07-24 governance: reclassify total_/actual_ as semantic; record Step-3 findings on the branch row
2026-07-24 feat(cbti): prefill diary clock defaults from Samsung, gated against the prescription
2026-07-24 review: correct the date-shadow mechanism, log the inference pattern, file the denylist drift
2026-07-23 feat(cbti): block status and prescription-in-force on /prefill and /today
2026-07-23 docs: fold waking-cause instrumentation into the standing brief's Steps 4/6
```

Maxima **unchanged**: DECISIONS `#116`, questions `Q45`, FEEDBACK `§18` (new this session).
`DECISIONS_LOG.md` and `OPEN_QUESTIONS.md` were **not** touched — no `#` minted (surfaces
brief's `#117`/`#118` mint at merge, with the build), so the CLAUDE.md recent-landings block
is unchanged (nothing merged, nothing to point at). Backend suite **376 passed** (was 352 at
session open; +11 block-context, +13 prefill-gate). Migration head unchanged at
`c4e8a2019bd7` — Steps 2–3 added no columns. Prod still at `c4e8a2019bd7`.

## 2. Pending-queue reconciliation

No `;cc` queue carried in — this was a Code-driven brief session. The surfaces brief drove
**Steps 2 and 3**; the review turn and the close-out captures produced the two governance
commits. Nothing decided this session is uncommitted.

| Brief step | Outcome |
|---|---|
| 1 — correct `docs/checkin-schema.md`; check SCHEMA.md | **DONE** (prior session, `7442bb5`, on master) |
| 2 — block status on `/prefill` + `/today` | **DONE** `d61412b` (+ review corrections `89eca95`) |
| 3 — Samsung prefill + 4h sanity gate | **DONE** `4636b94` |
| 4–9 — AM submit/freeze, PM naps, JSX, trigger, block-open | **UNSTARTED** — held one night, deliberately (see §3) |
| LOG `#117`/`#118` | **NOT WRITTEN** — numbers free, mint at merge |

## 3. Cold-resume handoff

**Branch:** `feat/cbti-surfaces`, pushed, **+5 ahead of `origin/master`**, all pending
(`git cherry` all `+`). Untracked stray: `.claude/launch.json` (known, ignored).

**Branch terminal-state gate — passes.** Six local branches; the touched one is rowed OWED,
the other five untouched and rowed:

```
feat/cbti-surfaces                 +5  OWED   (Steps 1-3 done; resume Step 4) — on origin
feat/checkin-injury-probe          rowed, untouched this session — on origin
feat/feedback-ledger               rowed, untouched this session — on origin
feat/interpretation-view-skeleton  rowed, untouched this session — on origin
feat/recovery-metrics-rhr          rowed, untouched this session — on origin
master                             at 6662439, level with origin/master
```

### What Steps 2–3 established

- **Step 2 — a shape test caught a real bug.** `TodayOut.date: Optional[date] = None`
  collapsed to `Optional[None]` — no `from __future__ import annotations` here, so the
  eager class-body default binds `date = None` before the annotation's `LOAD_NAME date`
  resolves. Every real record would have been rejected by `/today`. Fixed with `_dt.date`;
  the mechanism was mis-stated as `get_type_hints` in the first pass and corrected in
  `89eca95` (the review turn). The corruption is **positional** — only the shadowing line
  and later `date`-annotated siblings; `TodayOut` has none after it.
- **Step 3 — the mapping is VERIFIED, and the brief's join-worry was false.** `bedtime`,
  `wake_time` and `actual_sleep_time_minutes` are **co-located** on each
  `samsung_hrv_readings` row — no cross-table join to `health_connect_syncs`. A read-only
  Railway query over 31 real `passive_overnight` nights put `(wake − bedtime) − actual_sleep`
  at median **+35 min**, 30/31 positive → **`bedtime → got_into_bed` (bed-entry), VERIFIED**
  (the UNVERIFIED fallback is not taken). The gate's rejection is **demonstrated** (#110):
  synthetic `10:12`-for-`22:12` suppressed, valid value passes — 13 tests.

### Three findings to carry into Step 4 (also on the `BRANCHES.md` row)

1. **The 1/31 outlier is a BAD SOURCE ROW, not a wrap bug.** Night `2026-06-28`: window is
   366 min under **both** the conditional wrap and mod-1440 (they agree — exonerating
   `clock_delta_minutes`), yet `actual_sleep=435` / `total_sleep=462` exceed it, `SE=None`.
   **Step 4's night-validity gate must exclude nights where scored sleep > clock window.**
2. **`total_sleep_time_minutes` is the in-bed span, not sleep** (remainder ~0 vs the window;
   `actual_` is scored sleep). Three display sites — `context_builder.py:601`,
   `routers/recovery.py:67`, `HealthPanel.jsx:92` — show TIB labelled as sleep duration,
   ~30–45 min inflated. **Reclassified in ROADMAP from cosmetic to semantic** (`8300595`);
   still ROADMAP, does not interrupt the build. The correct SE numerator for Step 4 is
   `actual_sleep_time_minutes`.
3. **The freeze mutation control needs its inverse.** Step 4's freeze test (write, mutate
   the derived-from inputs, re-read, assert unchanged) also passes if the value was never
   written — pair it with a sanctioned recompute that DOES move it, or it cannot tell frozen
   from absent.

### THE ONE-NIGHT HOLD IS DELIBERATE — do not collapse it

Dormancy already ended at **Step 3**, not Step 4: the 4h gate needs the wrapped clock delta,
a local re-implementation is forbidden, so `checkin_v2.py` imports `cbti.timeutil` now and is
the first non-test consumer of `cbti/`. This is **better** than the brief's Step-4 placement —
the break landed on **prefill** (a recoverable default) rather than **submit** (a stored
value), moving the controlled failure onto the forgiving surface. Tomorrow morning's check-in
is therefore the first live run of `cbti/timeutil`, exercising **prefill only** — a clean
negative control on the just-un-dormant primitive. Running Step 4 tonight would forfeit it: the
first live run would exercise gate and freeze simultaneously, and a `timeutil` fault would
surface as a stored `diary_se_pct` instead of an ignorable wrong default.

### NEXT SESSION: Step 4 (tomorrow, after the live prefill-only run)

**Single clearest next action:** resume the surfaces brief at **Step 4** — AM submit accepting
the seven diary fields, freezing `diary_se_pct` / `diary_tst_min` at write. Bring the three
findings above: the night-validity exclusion (finding 1), `actual_` as the SE numerator
(finding 2), and the mutation control **plus its inverse** (finding 3). The waking-cause
columns (`wakings_nocturia_n` / `wakings_pain_n` / `wakings_spontaneous_n`) fold into Step 4's
migration + contract, observational-only — `grep -rn 'wakings_' backend/cbti/` must stay empty.
Then Steps 5–9, then merge with `#117`/`#118`, then the ISI brief before block 3 opens.

**Hold governance during the remaining build** (bar: a defect producing incorrect behaviour or
an unrecoverable record, not an improvement to how something is recorded). This session's two
governance commits were review-directed corrections and close-out captures, both tied to work
that landed — not free-standing governance turns.

**OWED — queued, deliberately not next:** the generalised **canonical-surface consistency
guard** (ROADMAP NOW — now THREE instances: SCHEMA.md vs `models.py`; CLAUDE.md conventions vs
`DECISIONS_LOG`; and the new (c) Samsung-context allowlist vs the two `!= 'session'` denylist
reads in `checkin_v2.py`). The **`total_`/`actual_` field swap** at three sites (ROADMAP, now
semantic). The **`9688f2…` co-occurrence test**. The **`health-connect-app` shared-block
propagation** (HCA-rooted session). **ISI capture** — the only owed item that BLOCKS block 3,
since a block-open ISI cannot be retrofitted. The **`mcp_server.py` `Session` import** one-liner.

**OWED, carried:** FEEDBACK **§18** landed this session (state-inferred-from-adjacent-attestation).
**Q45** (nap attribution — close from VA protocol docs, not the workbook). Cross-repo: HCA still
greps 0 for the #111 secret-rendering rule; propagate byte-identically from an HCA-rooted session.
