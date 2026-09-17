# Session close-out — #303 wake-day HRV selector (standalone read helper)

## Real commits this session

Session-open ref: `be98a89` (master head, the #220 close-out merge). Landed via PR #221
(merge `07de28f`), then this close-out follow-up.

```
5c79e2b  Wake-day HRV selector — standalone read helper (current-day-strict)   [feature: backend + tests, non-migration]
4b3cf1b  gov(#303): wake-day HRV selector decision, Q157, BRANCHES row, Recent-landings roll
07de28f  Merge pull request #221 from Easty11/feat/hrv-wakeday-selector   [merge to master]
```
Plus the `chore: session close-out` commit carrying this file (its own docs-only
follow-up PR, branch cut fresh from master; governance/docs-only, self-merges on green).

All three required checks were green on #221 before merge — `placeholder guard (POSIX)`,
`backend tests (pytest)`, `frontend tests (vitest)`. The full backend suite passed on an
isolated Python 3.12 venv (prod parity, CI env vars): **1694 passed, 1 skipped**; the one
local red, `test_current_state`'s `git show 3360ed5:…`, is the shallow-clone artifact
(fails identically on the clean base), green in CI at `fetch-depth: 0`. No frontend touched.

**Merge disposition.** Additive helper, non-migration, implementing a chat-ratified brief
with no un-ratified judgment embedded → self-merged on green under § Merge disposition. Not
a hold. The garmin-primary-on-pair tie-break is inferred from the #298 card convention and
flagged to the operator (not a new ratified rule); names/module form were Code's delegated
call.

## Pending-queue reconciliation

No pending-commit queue (`;cc`) was carried in — the work arrived as a direct brief
(WAKE-DAY HRV SELECTOR — standalone helper, chat 17 Sep), itself the precondition the
earlier check-in HRV denorm brief STOPPED on. Nothing provisional; everything decided
landed on master.

- **#303** — DECISIONS_LOG `### 303` — landed `5c79e2b` (code+tests) / `4b3cf1b` (gov),
  merge `07de28f`.
- **PREREQ verified before writing (brief VERIFY-FIRST):** the two master HRV readers are
  still exactly `routers/health._pick_latest_hrv` (#298, newest-across-sources) and
  `reads/recovery_reads.hrv_deviation` (#292, `for_date` upper-bound); no selector with the
  `require_current_day` / `wake_day` / `stale_withheld` / tz-divergence / config-error
  tokens pre-existed. Maxima at open: decisions **302**, questions **Q156** (matched the
  brief's expectation).
- **Helper landed:** `select_wakeday_hrv(db, user_id, wake_day, *, require_current_day,
  today=None) -> HrvSelection` in `reads/recovery_reads.py`. Reads `hrv_readings` by
  day-equality. States value / pair (delta = primary−secondary, same-wake-day only, headline
  = richer source) / absent / stale_withheld (never returns yesterday) / config_error (>2
  sources). tz-divergence flags a wake_day±1 source without merging; baseline maturity passed
  through from `hrv_deviation`, surfaced, never gating the value. Nothing consumes it yet —
  deliberate.
- **Guards not disturbed:** `hrv_deviation`, `representative_source`, `_pick_latest_hrv`,
  `canonical_hrv`, and the arbitration layer are all untouched. No endpoint, no frontend,
  no schema.
- **Q157 raised** (OPEN) — `hrv_readings.source` has no enum/CHECK, so the >2-source guard is
  runtime; the schema-constraint upgrade is deferred (full human review). Cross-ref in
  `### 303`'s "do not revisit unless".
- **Governance batch (one gov commit, #176):** DECISIONS `### 303`, OPEN_QUESTIONS Q157,
  BRANCHES terminal row for `feat/hrv-wakeday-selector`, CLAUDE Recent-landings roll (#303
  on, #300 off — cap 3). `#176(b)`: the row rode its own branch.

## Cold-resume handoff

**Where the tree is.** master @ `07de28f`. Decisions max **#303**, questions max **Q157**.
The wake-day HRV selector is on master as a standalone, fully-tested read helper with **no
consumer**. Fresh-clone setup still required per session (`git config core.hooksPath
.githooks`; `git config --local alias.land …`) — unversioned, silent when absent. Backend
suite must run on an isolated **Python 3.12** venv (repo pins `garminconnect==0.3.11`, needs
≥3.12; sandbox default is 3.11) with CI env vars `FERNET_KEY` (fresh, ephemeral),
`SECRET_KEY`, `ALGORITHM` — see `.github/workflows/tests.yml`.

**Single clearest next action.** Land the **check-in HRV denorm** brief — it is now
**unblocked**: its sole prereq (this selector) is on master. That brief: (1) stop the
check-in save writing `daily_records.passive_hrv_ms`; (2) repoint the check-in HRV display
to `select_wakeday_hrv(..., require_current_day=True, wake_day=today)` — current value +
source chip + conditional delta/baseline, or "–"/withheld, never a prior-day value or a
"Ring HRV" label on a non-ring source; (3) correlation joins canonical `hrv_readings` at read
time; (4) historical consumers (series/readiness, `get_checkin_history`, context_builder)
per-wake-day join with the retired column as fallback. Consumer map was banked at the STOP:
`checkin_v2` write @ `638` + display @ `544`, `series.py:213`, `mcp_server.py:243`,
`context_builder.py:554`. **Gate (1c): the historical repoint is still gated on the Q152 prod
query** — does `hrv_readings` cover the wake-days `passive_hrv_ms` currently backs? Must be
run (no prod egress this session) before the historical arm ships; stage the rest behind the
column fallback until then.

**Open questions gating the Loop lane.**
- **Q152** [DEFERRED] — historical `passive_hrv_ms` backfill from canonical (Garmin cutover
  seam). Gates the denorm brief's historical repoint. Needs a prod query.
- **Q157** [OPEN] — `hrv_readings.source` enum/CHECK; defence-in-depth on the >2-source
  guard. Blocks nothing (runtime guard holds the floor).
- **Q156** [OPEN, P4] — Banister τ criterion/sensitivity harness; downstream, blocks no
  surface.

**What was NOT touched (named, per the ritual).**
- **`passive_sleep_min` denorm** — the sibling of the HRV denorm, explicitly out of scope
  of the selector brief and named as the deliberate NEXT step after HRV is clean. Its
  read-time consumers span the sleep-source work. Untouched this session.
- **Weekly resolver** (ROADMAP NOW, **Oct 5 anchor; v1 test 2 — Know**) — the dated,
  sequencing-priority lane. Not touched. Nothing HRV-related advances it.
- **Appointment brief** (v1 test 3 — **Walk in**) — the synthesising consumer that sets
  build order. Not touched.
- **The Loop daily habit itself** (v1 test 4) — this session hardened a *read* the check-in
  will use, not the loop's end-to-end run.

**v1-triage.** This session's landing (#303) serves **Loop** (v1 test 4) — a correctness
precondition for the check-in's HRV read — but is a helper with **no live consumer**, so it
moves no v1 test until the denorm brief consumes it. Flag for the next session: the recent
run of sessions (#298 card HRV, #300 card sleep, #301/#302 load model, #303 selector) has
gone repeatedly to the *instruments* around the check-in and card — reads, versioning,
helpers — while the **Weekly resolver** (the dated *Know* test) and the **appointment brief**
(the *Walk in* test that sets sequencing) have stood still. The denorm brief is the right
immediate next (it closes a live data-integrity bug: a stale dead-source HRV frozen into the
daily record on every Save), but after it, the next pull should be back to the dated Know
lane, not another check-in/card instrument — say so rather than letting lane momentum decide.
