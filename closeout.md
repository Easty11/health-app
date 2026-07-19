# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

Session: 2026-07-19 — Q17 HRV instrumentation-close. Branch `master` (all work landed).

---

## 1 · Real commits this session

Open-ref `4a65f4a` (the #88 session close-out, pre-existing at my start) → `HEAD`:

```
c271834 gov: mint #NEXT -> #89 at merge — master max was #88; step-5 HCA pointer deferred
74558ea gov: resolve Q17 on (A) instrumentation — RR corroborator was never independent (#NEXT)
```

Plus this close-out commit (`chore: session close-out`). All on `master`, pushed to
`origin/master`. Immutable-dated log (per #88):

```
git log --format="%ad %s" --date=short -6
```
Run at copy-back for the dated record; the two SHAs above are this session's substantive work.

**Governance stores changed this session:** `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`,
`BRANCHES.md`, `HANDOFF.md` (+ `CLAUDE.md` Recent-landings, `closeout.md`).

---

## 2 · Pending-queue reconciliation

No `;cc` PENDING queue was carried in — the payload was a full brief, not a queue. Reconciled
against the brief's items:

- **Q17 resolved on (A)** — LANDED `74558ea`. `OPEN_QUESTIONS.md` Q17 `Status: resolved → #89`;
  the (B) RR-corroborator clause struck-but-legible (G2). ✔
- **DECISIONS #89** (brief's draft `#89`, written `### #NEXT`, minted `#89` at merge) — LANDED
  `74558ea` / `c271834`. Conforms to health-app's Decision/Rationale/Status/How-you-know/
  Do-not-revisit format. ✔
- **`feat/recovery-metrics-rhr` BLOCKED→UNSTARTED** + corrected parking rationale — LANDED
  `74558ea`. ✔
- **HANDOFF CHAT→CODE receipt + CODE→CHAT close** — LANDED `74558ea` / `c271834`. ✔
- **Q29 minted** (NOT the brief's "Q5") — LANDED `74558ea`. The brief's "Q5 = historical
  stale-row reconciliation" was a stale-mirror mis-reference: real health-app Q5 is
  `/health-connect/sync` dual-field acceptance and was left untouched. Chat approved minting
  **Q29** as the reconciliation home instead. ✔

**Corrections applied to the brief (verified, not assumed):**
- `1db8833` was **authored 26 Jun** on unmerged `fix/scraper-sh-relayout`; it **reached HCA
  master 11 Jul** (renumbered #16→#19). The brief's "#19 landed 26 Jun" is imprecise; the
  entry now states authored-vs-reached. This *strengthens* the Q29 install-segmentation logic
  (no single commit/merge date is the changepoint).

**PROVISIONAL / OWED — Step 5 (HCA cross-repo pointer): NOT written.** Per chat's decision and
the single-repo rule, the HCA #19 → health-app Q29 pointer is **deferred to an HCA-rooted
session**. A ready-to-paste HCA `#20` entry was emitted to chat. Until it lands in
`health-connect-app`, HCA #19's "separate concern" is unnamed (health-app Q29 already
cross-refs HCA #19/Q3 one-directionally).

---

## 3 · Cold-resume handoff

**What just landed (#89).** The 6-Jul HRV step (pre mean ≈57 ms / post ≈96 ms) is
**instrumentation, not physiology**. HCA #19 (`1db8833`) routed three Energy-score reads
through `findByIdValidBounds` instead of `findById(...).firstOrNull()`, which had been
returning a negative-width Compose phantom bearing the prior render's value. Same RMSSD node
throughout — the scraper just stopped binding the stale duplicate. Q17's (B) physiology limb
is **unevidenced, not disproven**; its RR "corroborator" was void because RR shares the exact
read path (`vitality_respiratory_rate_average_title`, same screen, same selector, same commit).

**Consequence for readiness (ROADMAP NEXT).** The pre-install HRV baseline ≈57 ms is an
artifact, not a baseline. Trustworthy HRV history is **short** (post-install only), not long —
any readiness/trend/protocol attribution built on the 57→96 "rebound" rests on bad rows. The
"Basic readiness score" NEXT item's 7-day-sample gate should count only post-install nights.

**Open questions — HRV cluster:**
- **Q17** — RESOLVED → #89 (instrumentation limb).
- **Q29** (NEW) — PENDING. Historical `samsung_hrv_readings` phantom-stale reconciliation.
  **Prerequisite: segment the series by APK-install history first** (the changepoint is an
  install event, not a commit — fix authored 26 Jun, on HCA master 11 Jul, data step ~6 Jul,
  stale APK still emitting phantom 106 on 11 Jul per HCA Q3). **Do NOT reconcile/backfill/
  delete any row until segmented.**
- **Q18** — open (verify-at-machine). Out-of-range bounds sweep; distinct from Q29
  (wrong-magnitude vs stale-but-plausible).
- **Q13** — open. HRV single-point-of-failure (scraper-only) pending scraper canary (issue #9).

**Single clearest next action.** Carry the ready-to-paste HCA `#20` entry into a
`health-connect-app`-rooted Code session and land it (append-only; #19 untouched), pointing
#19's "separate concern" at health-app Q29. Then, separately, Q29's install-history
segmentation is the gate before any HRV row reconciliation.

**Branch terminal state.**
- `fix/q17-hrv-instrumentation` — merged (ff) to master + local-deleted (never pushed to
  origin). ✔
- Untouched-this-session but flagged: `feat/recovery-metrics-rhr` (1 `+`, in `BRANCHES.md` —
  now UNSTARTED), `feat/interpretation-view-skeleton` (3 `+`, named in `BRANCHES.md` prose),
  `feat/feedback-ledger` (4 `+`) and `feat/checkin-injury-probe` (2 `+`) — the last two are
  referenced only in `BRANCHES.md` numbering prose, not their own rows. Pre-existing; a future
  session should give them rows or land them. Not this session's to resolve.
