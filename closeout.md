# Session close-out — #305 constant-provenance table + #306 load_ratio descriptive (P6 + P2)

## Real commits this session

Session-open ref: `ceb1c22` (master head, the #304 close-out merge). Two work packages, two
branches, two PRs, run in order (WP-B off master after WP-A merged).

```
# WP-A (#305) — constant-provenance table + drift guard — PR #225, merge ac179c7
01e4731  Constant-provenance table for the load modules + drift-guard test
61a357a  gov(#305): constant-provenance table gate, Q156 input-list amend, design-doc discharge, BRANCHES, Recent-landings roll
ac179c7  Merge pull request #225 from Easty11/claude/p6-constant-provenance

# WP-B (#306) — load_ratio descriptive reclassification — PR #226, merge d687c29
af7237c  load_ratio is a descriptive spike indicator — docstring reclassification
7f8216a  gov(#306): load_ratio descriptive reclassification, Q158, design-doc annotations, BRANCHES, Recent-landings roll
d687c29  Merge pull request #226 from Easty11/claude/p2-load-ratio
```
Plus the `chore: session close-out` commit carrying this file (its own docs-only follow-up
PR, branch cut fresh from master; governance/docs-only, self-merges on green).

All three required checks (`placeholder guard (POSIX)`, `backend tests (pytest)`, `frontend
tests (vitest)`) were green on both PRs before merge. Full backend suite **1700 passed, 1
skipped** on an isolated Python 3.12 venv (prod parity, CI env vars); the one local red,
`test_current_state`'s `git show 3360ed5:…`, is the shallow-clone artifact (green in CI at
`fetch-depth: 0`).

**Merge disposition.** Both non-migration, implementing a chat-ratified brief → self-merged
on green. WP-A is docs + one test (no source change); WP-B is one docstring + docs (no
behaviour change — the ratio arithmetic and every consumer are byte-identical).

## Pending-queue reconciliation

No pending-commit queue (`;cc`) carried in — a direct two-WP brief (P6 + P2, chat 17 Sep).
Nothing provisional; everything decided landed on master. The brief arrived truncated
mid-A2; WP-A's A1 enumeration (read-only) was reported first, then the rest of the brief was
resent and the work proceeded.

- **#305 (WP-A)** — DECISIONS `### 305` — `docs/load-constants-provenance.md` (23 rows) +
  `backend/tests/test_load_constants_provenance.py` drift guard. Landed `01e4731`/`61a357a`,
  merge `ac179c7`.
  - **G-A1:** enumeration read from the tree, not the brief — the auto-collected `UPPER_CASE`
    set matched the 13 tabled module constants on the first run (no untabled constant).
    Adjudications: `_h_intensity` is four coefficients; Epley /30 and TRIMP /60 each a row;
    no HR-zone rows (upstream); version-key strings excluded.
  - **G-A2:** 23 rows = 13 auto-collected + 10 allow-listed; **15/23 "operator prior,
    uncited"** (the Q156 harness input list, τ_metabolic=4 first), 4 cited, 3 derived, 1
    operator input.
  - **G-A3:** drift guard demonstrated — deleting the `FORM_K` row fails naming `FORM_K`,
    green on restore. Standing rule set (a coefficient change changes its row in the same PR).
  - Governance: Q156 amended (input list pinned); design-doc candidate-OQ "strength-window τ
    priors vs 42/7 aerobic convention" discharged into the table.
- **#306 (WP-B)** — DECISIONS `### 306` — `load_ratio` reclassified descriptive. Landed
  `af7237c`/`7f8216a`, merge `d687c29`.
  - **G-B1:** the "strip risk-band language" surface list is **EMPTY** — the frontend renders
    no `load_ratio` (a chart fixture carries acute/chronic trace values only), and the MCP
    `get_training_load` readout was already de-ACWR'd in #255 (prints acute/chronic as trace
    values, "not a dosing ratio"; its test asserts no acwr/sweet-spot/injury-risk). B1a:
    coupled 7-in-28 trailing means (#249), no EWMA variant in code. B1c: design §4.1 (EWMA
    acute trace) and §11 (stale "MCP reports ACWR sweet-spot") both stale vs shipped code.
  - The reclassification is one `load_metrics` ΔLoad docstring + governance (no surface strip,
    no behaviour change). Governance: design §4.1 annotated Tier 3, §11 candidate-OQ CLOSED,
    Q158 raised (uncoupled chronic d8–28 = optional column, schema change deferred).

## Cold-resume handoff

**Where the tree is.** master @ `d687c29`. Decisions max **#306**, questions max **Q158**.
The load model now carries a **constant-provenance gate** (`docs/load-constants-provenance.md`
+ its drift test — no coefficient lands unlabelled) and a **descriptively-reclassified
`load_ratio`** (spike indicator, not a risk score; computation unchanged). Fresh-clone setup
still per session (`git config core.hooksPath .githooks`; `git config --local alias.land …`).
Backend suite runs on an isolated **Python 3.12** venv (repo pins `garminconnect==0.3.11`,
needs ≥3.12; sandbox default 3.11) with CI env vars `FERNET_KEY` (ephemeral), `SECRET_KEY`,
`ALGORITHM` — see `.github/workflows/tests.yml`.

**Single clearest next action.** The load model is now at a defensible resting point — the
only open load item is the **Q156 criterion/sensitivity harness** (P4), whose input list is
now pinned (the provenance table's operator-prior rows, τ_metabolic=4 first). The next pull
should NOT be another load-model increment: it should be the dated **Weekly resolver** (v1
test 2 — Know, Oct 5 anchor) or the **appointment brief** (v1 test 3 — Walk in). See the
instrument-vs-thing flag below.

**Open questions (load-model group, all downstream, blocking no surface).**
- **Q156** [OPEN, P4] — Banister τ criterion/sensitivity harness. Input list now pinned
  (#305); τ_metabolic=4 first, then the other τ_fatigue priors and the band coefficients. A
  fit that moves a provenance row from "operator prior" to "fitted" updates that row.
- **Q158** [OPEN] — uncoupled chronic (days 8–28) as an optional descriptive `load_ratio`
  denominator; needs a new column (schema change), so deferred. The coupled ratio ships
  descriptive under #306.
- **Q157** [OPEN] — `hrv_readings.source` enum/CHECK (defence-in-depth on the #303
  >2-source guard). Blocks nothing.
- **Q152** [DEFERRED] — historical `passive_hrv_ms` backfill; gates the check-in HRV denorm's
  historical arm. Needs a prod query.

**What was NOT touched (named, per the ritual).**
- **Check-in HRV denorm** — still pending; #303 landed its precondition (the wake-day
  selector), but the denorm itself is not started and its historical arm is gated on Q152.
- **`passive_sleep_min` denorm** — the sibling of the HRV denorm; still the named next step
  after HRV. Untouched.
- **Weekly resolver** (ROADMAP NOW, **Oct 5 anchor; v1 test 2 — Know**) — the dated,
  sequencing-priority lane. Not touched, again.
- **Appointment brief** (v1 test 3 — **Walk in**) — the synthesising consumer that sets
  build order. Not touched.
- **Q156 harness** itself — this session pinned its INPUT (the provenance table) but did not
  build the sweep; the harness is still unbuilt.

**v1-triage.** #305 and #306 are both **load-model hygiene** — a provenance gate and a
naming/framing correction. Neither moves a v1 test (See was already MET; Know / Walk in /
Loop are untouched). This continues a now-long run — #298 card HRV, #300 card sleep,
#301/#302/#304 load model, #303 HRV selector, #305/#306 load-model hygiene — that has stayed
entirely in the **reads/model around the check-in and card**. The dated **Know** lane (Weekly
resolver, Oct 5) and the **Walk in** lane (appointment brief) have not moved across any of
them. The load model is now well-instrumented and at rest; the honest next move is a v1-test
lane, not another model/reads pass. Flagged here and in the last three close-outs — worth the
operator naming the next brief against a v1 test rather than lane momentum.

_Out of scope, noted (not widened into these PRs): `mcp_server.get_training_load`'s docstring
still says "banister-v2" (stale since #304's v4 bump); the live constant is correct, only the
docstring literal lags. A one-line sweep when convenient._
