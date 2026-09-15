# Close-out — 2026-09-15 (garmin_sync gains a trigger — on-read + nightly sweep, #299)

## Real commits this session

Session-open ref: `dd6a475` (master head at start, "Merge pull request #214 …").
Branch: `feat/garmin-refresh-trigger` (concern-named per CLAUDE.md; NOT the harness-default
`claude/peaceful-darwin-vluqin` — the brief named this branch and `claude/<hash>` auto-names are
banned for in-flight work).

    ea0a4f7  feat(garmin): trigger garmin_sync — on-read refresh + nightly sweep job (#299)
    6425339  feat(recovery): trigger Garmin HRV refresh on the Recovery card open (#299)
    <gov>    chore: session close-out + gov(#299 garmin_sync trigger)

- `ea0a4f7` — backend: `POST /integrations/garmin/refresh` (`routers/garmin.py`, staleness-gated
  on `max(hrv_readings.created_at)` for garmin at 30 min, `force`-bypass, never errors the card);
  `garmin_sync` added to `load_sweep._sweep` as the second per-user job beside the load chain, via
  a non-CLI `scripts.garmin_sync.sweep_garmin_hrv` extracted from the CLI `main`. `tests/
  test_garmin_refresh_endpoint.py` (7) + `tests/test_load_sweep.py` (+1, 2 updated for the nested
  summary). Non-migration.
- `6425339` — frontend: `useRecoveryRefresh` (mirrors #297's `useLoadRefresh`) + `HealthPanel`
  wiring (mount refresh, re-fetch `/health/summary` on a real run, Refresh = force). `useRecovery
  Refresh.test.js` (7) + `HealthPanel.test.jsx` (2).
- The close-out governance commit carries `DECISIONS_LOG.md` (#299), `OPEN_QUESTIONS.md`
  (Q155 → DONE), `BRANCHES.md` (the DONE row), `CLAUDE.md` (Recent-landings, #296 rolled off),
  and this `closeout.md`. Batched here per #176 (governance/docs only; removed lines confined to
  declared regions — the Recent-landings cap-3 trim and the Q155 State rewrite).

Merge disposition: **self-merge on green** under § Merge disposition — this implements a
chat-approved brief whose decision text was pre-ratified; the only Code judgments were
brief-delegated (endpoint path, the data-recency marker) or verification (correcting the brief's
asyncio.run premise — the Garmin path uses no asyncio). All three commits ride this one branch →
one PR.

## Pending-queue reconciliation

No chat `;cc` pending-commit queue carried in — the session opened on a written brief (give
`garmin_sync` a trigger, resolve Q155). Nothing provisional is left uncommitted: backend
`ea0a4f7`, frontend `6425339`, governance in the close-out commit. The one operator-owed item is
verification, not a commit — see the handoff.

## Cold-resume handoff

**What landed.** #299 — `garmin_sync` gets the trigger #296 and #297 both named "the natural
second job on this scheduler, once it exists." Two legs on #297's in-process rail (no dedicated
cron — #297 tore that out as the fragile part):
- **On-read = freshness.** `POST /integrations/garmin/refresh` fires on Recovery-card open
  (~9am, after Garmin's ~6am sync), staleness-gated, `force`-bypassable — delivers this morning's
  HRV. Server-authoritative; the card always calls, the server decides.
- **Nightly = guarantee.** `garmin_sync` added as a second per-user job inside #297's existing
  02:00 Brisbane sweep. At 02:00 it can only land the PRIOR night (Garmin finalises overnight HRV
  post-wake) — accepted: this leg only guarantees no night is permanently lost for mornings the
  card isn't opened. On-read owns same-morning freshness.

**Gates cleared before build (both passed).** (1) `garmin_sync` was NOT already triggered —
`load_sweep._sweep` ran only the load chain; no `*/refresh` route mounted it. (2) The #297 02:00
rail is live in prod: `health-app-backend` logs (2026-09-15 05:30 UTC) show the startup self-heal
leg `refresh_load done: 3 succeeded, 0 failed`, per-user summary, no `.railway.internal` error —
the identical `_sweep`→`asyncio.to_thread` body the nightly Garmin leg rides. (The literal 16:00
UTC scheduled fire wasn't captured because the current deploy postdates today's boundary; the
startup leg is exactly the mechanism that covers that.)

**Staleness marker — the reported VERIFY finding.** There is NO per-user Garmin attempt-recency
timestamp. `UserIntegration.updated_at` is bumped by connect/disconnect + the token writeback, so
it reads "fresh" the instant a user connects (the Q155 bug) — DISQUALIFIED. Gate uses
`max(hrv_readings.created_at)` for `source='garmin'` (data-recency, migration-free; `captured_at`
is a `Date`, not a timestamp). Accepted cost: a night Garmin genuinely has nothing creates no
row, so the gate re-fires on each open until data arrives.

**Operator-owed (verification, not code):**
- **Post-merge live check (Luke):** open the Recovery card after 6am on a new day → last night's
  Garmin HRV appears with no manual sync; re-open inside 30 min → skipped/fast; Refresh → runs;
  next morning confirm `garmin_sync` in the 02:00 sweep log (`load sweep (02:00 Brisbane) done:`
  now carries a `garmin` sub-summary).
- **Frontend deploy-verify (#121):** after the frontend deploys, probe the served
  `assets/index-*.js` for the `useRecoveryRefresh` / `/integrations/garmin/refresh` string.

**Explicitly OUT of scope (each its own decision, do NOT let this brief's close imply they're
handled):**
- **Read-path composite (Luke's ratify owed):** the check-in HRV picker still shows Samsung 113
  while the card shows Garmin 78 — two surfaces disagreeing on latest HRV; and the card composites
  Garmin HRV (last night) with Samsung sleep (night before) as one record. The coherence-vs-recency
  fork is Luke's. This brief only makes Garmin ARRIVE on a trigger.
- **`get_hrv_range` ~7-day ceiling** caps missed-night self-heal at ~7 nights — known limit, not
  fixed; acceptance must not promise self-heal beyond it.
- **Duplicate Garmin `UserIntegration` (users 1 & 4)** — data hygiene; not fixed, but per-user
  isolation keeps the sweep clean regardless.
- **Garmin sleep/RHR/SpO2 ingestion** — Garmin is HRV-only in the store; not here (adding sleep
  is the trigger that reopens the read-path composite decision).

**Single clearest next action.** The read-path composite decision (Luke's ratify): the check-in
picker vs card HRV disagreement is now visible precisely because Garmin arrives reliably — the
next HRV-neighbourhood session should put the coherence-vs-recency fork to Luke, not touch code
first.

**Open questions (HRV/recovery neighbourhood).** Q155 **DONE → #299**. Q131 OPEN (`_SOURCE_RANK`
tuning — live divergent data recorded #298). Q151 OPEN (unmounted `recovery.py`). Q152 OPEN
(historical `passive_hrv_ms` backfill at the Garmin cutover seam). Q153 OPEN (delete the
`_SOURCE_RANK` arbitration branch once no consumer calls it). The multi-device readout ticket is
still PARTIAL: `context_builder._section_samsung_hrv` is the last single-scalar device readout.

**What was NOT touched — named, per the ritual.** Another HRV/plumbing session — it went to the
capture rail, not the product spine. Every v1 feature lane stood still: **lab upload pipeline** +
**interpretation layer** (Q36–Q41, Q64/Q65 — the medical hero path), **appointment brief v1**
(design brief still owed, not started), **surface-debt sweep**. #293–#299 have now all gone to HRV
instrumentation; the medical spine (lab → interpretation → appointment brief) is where the next
non-reactive session should go.

**Session-open maxima (this session):** decisions **298**, questions **155** →
after this close-out: decisions **299**, questions unchanged at **155** (Q155 resolved by #299,
not a new question).
