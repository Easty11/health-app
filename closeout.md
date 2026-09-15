# Close-out — 2026-09-15 (multi-source HRV on the recovery card + MCP)

## Real commits this session

Session-open ref: `558a521` (master head at start, "Merge pull request #212 …").

    d3e2832  Merge pull request #213 from Easty11/claude/busy-cray-502ol8
    ed51ddf  fix(recovery): surface newest HRV across sources on the card + MCP, source-labelled

- `ed51ddf` — the feature: `/health/summary` additive `latest_hrv` (newest HRV across
  sources, `source`-tagged), `mcp_server.get_recovery_metrics` union of samsung+garmin rows
  (both labelled, never collapsed), `HealthPanel` source chip, `tests/test_recovery_source_label.py`
  (11). Non-migration. Merged **on green after Luke's live ratification** (it reverses the #291
  device-readout clause for these two surfaces → NOT self-merged), via PR #213 → merge `d3e2832`.
  Remote branch `claude/busy-cray-502ol8` deleted by the merge; recreated locally from master
  for this close-out.
- The close-out governance commit (this one — `chore: session close-out`) carries
  `DECISIONS_LOG.md` (#298), `OPEN_QUESTIONS.md` (Q155), `BRANCHES.md` (the DONE row),
  `CLAUDE.md` (Recent-landings), and this `closeout.md`. It lands via its own PR on the
  recreated `claude/busy-cray-502ol8` (guard-gated per #176 — governance/docs only).

## Pending-queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — it opened cold on a
reactive diagnosis task (recovery card showing stale Samsung HRV while Garmin was connected),
not a chat brief. Nothing provisional is left uncommitted: the feature landed in `ed51ddf`
(merged `d3e2832`), and the governance record lands in this close-out commit. The one
operator-owed item is verification, not a commit — see the handoff.

## Cold-resume handoff

**What landed.** #298 — the two Samsung-scoped device readouts (`/health/summary`, the
dashboard Recovery card; and MCP `get_recovery_metrics`) now show the newest HRV **across
sources**, source-labelled. This is the "multi-device readout ticket" #291's "do not revisit
unless" anticipated, delivered for these two surfaces. Newest-wins, same-night tie → richer
source (garmin), raw ms never blended (#292). Samsung sleep/baseline and the multi-source
deviation model (#291/#292 readiness/check-in/`/recovery/summary`) are untouched.

**Root cause was two-layered.** (1) Ingestion: Garmin HRV has **no scheduler** — connecting
Garmin stores a token and pulls nothing; the card was stale because no sweep had run. One
hand-run `scripts.garmin_sync --from 2026-09-13 --to 2026-09-15` (3 nights, 235 samples, token
alive) fixed the data. Filed **Q155** (the capture-trigger gap is NOT fixed — only the read
path). (2) Read path: both device readouts were Samsung-scoped — fixed by #298. Day-bucketing
was verified against prod: Samsung and Garmin both bucket to the **wake day** and agree on the
date, so no reconciliation was needed (an offset hypothesis was disproven by the data).

**Operator-owed (verification, not code):**
- **Frontend deploy-verify (#121):** after the frontend deploys, probe the served
  `assets/index-*.js` for the source chip / `latest_hrv` consumption.
- **Q155 decision:** how Garmin HRV should be pulled on a schedule (in-process nightly sweep
  à la #297 `load_sweep.py`, or on-demand fire-and-forget from a surface the user hits). Until
  decided, the card's freshness depends on a manual `scripts.garmin_sync` run.
- **Two Garmin users (ids 1 and 4)** pulled identical data on 2026-09-15 — likely one account
  under two `UserIntegration` rows. Verify / clean up if unintended (noted in Q155).

**Single clearest next action.** Decide Q155 (Garmin pull trigger) — it is the live gap a user
will hit again the moment they reconnect and expect data without knowing to run a sweep.

**Open questions (HRV/recovery neighbourhood).** Q155 OPEN (this session — Garmin ingestion
trigger). Q131 OPEN (`_SOURCE_RANK` tuning — now has live divergent data: samsung 113 vs
garmin 65 on the 13→14 night). Q151 OPEN (unmounted `recovery.py` adopt-or-delete). Q152 OPEN
(historical `passive_hrv_ms` backfill at the Garmin cutover seam). Q153 OPEN (delete the
`_SOURCE_RANK` arbitration branch once no consumer calls it). The multi-device readout ticket
is **partially** discharged: `context_builder._section_samsung_hrv` is the last single-scalar
device readout still open.

**What was NOT touched — named, per the ritual.** This was a reactive HRV/plumbing session; it
went to the instrument (the recovery readout), not to the product spine. Every v1 feature lane
stood still: **lab upload pipeline** + **interpretation layer** (Q36–Q41, Q64/Q65 — the medical
hero path), **appointment brief v1** (v1 test 3 "Walk in" — design brief still owed, not
started), **surface-debt sweep** (v1 test 4 "Loop"). None changed this session and none were
meant to. v1-triage: #298 serves the **"See"** test loosely (the recovery card is a
See-surface), but it was a correctness bug-fix pulled in by the operator, not a NOW-lane
advance — it should not be read as sprint progress. Consecutive recent sessions (#293–#298) have
now gone to HRV instrumentation; the medical spine (lab → interpretation → appointment brief) is
where the next non-reactive session should go.

**Session-open maxima (this session):** decisions **297**, questions **154** →
after this close-out: decisions **298**, questions **155**.
