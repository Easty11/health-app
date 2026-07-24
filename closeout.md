# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-24 · Block 3 opened live in prod; CBT-I capture surfaces built, merged, deployed and verified — the module is now usable *during* the block

## 1. Real commits this session

Session-open ref: `75e0919` (prior close-out). Five commits, all on **master @ `e59d496`**,
pushed. The four feature/governance commits were authored on `feat/cbti-surfaces` and
ff-merged; `e59d496` is the branch-retirement governance commit on master.

```
e59d496 governance: retire feat/cbti-surfaces (merged+deleted); record the remaining surface work
2f9004e governance: mint #117/#118/#119; file the basis-provenance and adherence-lag gaps and the CPAP instrument
9c05100 feat(cbti): CheckInAM sleep-diary section, render-gated on an open block
a361b78 feat(cbti): AM submit accepts the diary and freezes SE/TST; waking-cause columns
8cd5cd8 feat(cbti): open block 3 — one-shot script, run live against prod
```

```
2026-07-24 governance: retire feat/cbti-surfaces (merged+deleted); record the remaining surface work
2026-07-24 governance: mint #117/#118/#119; file the basis-provenance and adherence-lag gaps and the CPAP instrument
2026-07-24 feat(cbti): CheckInAM sleep-diary section, render-gated on an open block
2026-07-24 feat(cbti): AM submit accepts the diary and freezes SE/TST; waking-cause columns
2026-07-24 feat(cbti): open block 3 — one-shot script, run live against prod
```

Maxima: DECISIONS **#119**, questions **Q47** (Q46/Q47 new this session). Migration head
advanced to **`b2d5f9e04a17`** (waking-cause columns), applied on Railway at deploy. Backend
suite **386 passed** (was 352 at the prior close-out; +11 block-context, +13 prefill-gate,
+10 diary-freeze). `frontend/src` no longer byte-identical to master (`CheckInAM.jsx` +130).

## 2. Pending-queue reconciliation

No `;cc` queue carried in — a Code-driven "light up the block" reordering brief (Steps A–D).
Nothing decided this session is uncommitted.

| Brief step | Outcome |
|---|---|
| A — open block 3 (script + prod insert) | **DONE** `8cd5cd8`; block id=2 / rx id=10 written and read back from prod |
| B — AM submit accepts diary, freezes SE/TST; waking-cause migration | **DONE** `a361b78` |
| C — `CheckInAM.jsx` section, render-gated on `block_open` | **DONE** `9c05100` |
| D — mint #117/#118/#119, file Q46/Q47 + CPAP; ff-merge; deploy; verify | **DONE** `2f9004e` (+ `e59d496` retire); deployed + verified |

## 3. Cold-resume handoff

**Branch:** on **`master` @ `e59d496`**, level with `origin/master`. `feat/cbti-surfaces` is
**merged + deleted** (ff at `2f9004e`, `git cherry` clean), rowed DONE in `BRANCHES.md`.
Untracked stray: `.claude/launch.json` (known). Four parked branches untouched this session,
all rowed: `feat/checkin-injury-probe`, `feat/feedback-ledger`,
`feat/interpretation-view-skeleton`, `feat/recovery-metrics-rhr`.

**Branch terminal-state gate — passes.** No touched branch in undefined limbo.

### What landed, and the state of block 3

Block 3 is **open and live in prod** (`cbti_blocks` id=2, open, anchor 05:45; prescription
id=10 `adopt`, 23:45→05:45, window 360, device-derived basis tst=349/se=89.3 over 27 nights,
excluding `2026-06-28` impossible + `2026-07-18` partial). The AM check-in now captures the
diary and freezes `diary_se_pct`/`diary_tst_min` server-side (formula validated 12/12 against
block 2's stored rows). `CheckInAM.jsx` renders the diary only while a block is open.

**Deploy verified after settle (#116):** deployment `63523eb4` SUCCESS, `alembic current` =
`b2d5f9e04a17` with the migration file present in the image (the discriminating probe, not just
the revision string), deployed `checkin_v2.py` carries `diary_prefill`/`_freeze_diary`.

**Two findings from the build worth carrying:**
- The Step-A basis mean was measured at **349 min / 27 nights** (the brief's ≈361 was ~12 min
  high; SE 89.3% matched). Stored as measured; the window is operator-set (360) so it was
  unaffected.
- The 1/31 mapping outlier (`2026-06-28`) is a **bad source row**, not a wrap bug — window
  agrees under both wrap methods; `actual_sleep` exceeds the clock span. Step B's night-validity
  filter now excludes exactly this shape (TST > TIB freezes to NULL).

### NEXT: one piece left to close the titration loop through the app

Updated 2026-07-25 (post `feat/cbti-pm-naps`, merged `802ddd6`). AM capture, PM prescription
display, ISI storage, and PM nap capture are all in. **One piece remains:**

1. **PM prescribed-lights-out display** — **DONE** (`9331c31`). **PM nap capture** — **DONE**
   (`802ddd6`, #122): `NightlyCloseOut.jsx` accepts `naps_min`, blank→0 while a block is open so the
   engine's nap exclusion can fire.
2. **The manual witnessed evaluation trigger — THE LAST PIECE.** #118's PM-offer half: offer
   evaluation on PM close-out once ≥7 days since `effective_from`; engine returns the decision, row
   minted on acceptance. #118's block-open half is DONE. **Dependency, not deferral:** it cannot
   fire before ~31 Jul — it needs a full cycle of nights and the block opened 24 Jul.
3. **ISI storage** — **DONE** (`9331c31`, #120): block 3's baseline is stored (`cbti_isi` id=1).

**Single clearest next action:** the **manual evaluation trigger** (item 2) — the only remaining piece
of the in-app titration loop. Not before ~31 Jul: it needs a full cycle of nights and block 3 opened
24 Jul, so there is no work-forcing urgency before then. Cut a fresh branch from master.

**Carried (from #122):** block 3's nights logged 24 Jul → 25 Jul (pre-nap-capture) keep `naps_min = NULL`
and cannot be nap-gated retrospectively without a memory backfill. Two nights — worth a manual note.

### #118 is minted but half-built — a live watch-item

`#118` (manual/witnessed titration, manual block-open) is on master and locked. Its block-open
half is instantiated (Step A); its **PM evaluation-trigger half is not built**. The entry's
Status says so. If it should have waited for the trigger, supersede it with a new entry — do not
edit the locked one.

### OWED — filed this session, not yet worked

- **Q46** — no column distinguishes a device- vs diary-derived `basis_tst` (only adherence
  source); block 3's device basis is stated in the rx rationale only.
- **Q47** — the adherence gate prefers Samsung `bedtime` (`engine.py:230-235`), whose ~10-min
  detection lag against a ±30 tolerance can flip a night's verdict. Measure the lag distribution
  across block 3's live nights before adjusting.
- **ROADMAP** — CPAP mask-off events as an objective nocturia instrument to check
  `wakings_nocturia_n`.

### OWED — carried from before, still not next

The generalised **canonical-surface consistency guard** (ROADMAP NOW, three instances incl. the
Samsung-context allowlist drift). The **`total_`/`actual_` field swap** at three sites (semantic).
The **`9688f2…` co-occurrence test**. The **`health-connect-app` shared-block propagation** (HCA
still greps 0 for #111's secret-rendering rule; HCA-rooted session). FEEDBACK **§18**. **Q45**
(nap attribution — from VA protocol docs). The **`mcp_server.py` `Session` import** one-liner.
