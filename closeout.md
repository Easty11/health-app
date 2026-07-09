# Close-out — 2026-07-09

## 1. Real commits this session

Session-open ref: `d73684e` (`chore: session close-out`). `git log --oneline d73684e..HEAD`:

```
560ea80 gov: OPEN_QUESTIONS Q13 — HRV is scraper-only; HC hrv_rmssd structurally empty
e25ba64 docs: METRICS.md — per-page metric catalogue (drift baseline)
4d6a381 gov: Q4 resolved in code — HC sleep on local wake-date (#64)
0a45e6d fix: HC sleep attributed to local wake-date (Q4)
```

All four are on `master`, pushed. `HEAD == origin/master == 560ea80`.

Concern-split as designed:
- `0a45e6d` (feature) — `_wake_date` helper (tz-aware AEST), `_aggregate_day` sleep
  filter → wake-date-only, date-collection loop → wake-date-only, `/sync` window upper
  bound widened to AEST-today, backfill migration `f4e1a2b3c6d7` (nulls the five sleep
  columns), and 7 new unit tests. Full suite 29/29 green.
- `4d6a381` (governance) — DECISIONS_LOG #64; OPEN_QUESTIONS Q4 → `verifying`.
- `e25ba64` (docs) — `METRICS.md` at repo root: per-page metric catalogue at
  display-label → code-field → endpoint → column depth. Not repo-canonical; no lockstep
  rule.
- `560ea80` (governance) — OPEN_QUESTIONS Q13 (HRV scraper-only / HC `hrv_rmssd`
  structurally empty / single point of failure pending scraper canary #9).

## 2. Pending-commit queue reconciliation

No chat `;cc` pending-commit queue was carried into this session. Work originated from
the Q4 ANCHOR/OBJECTIVE brief plus three in-session requests (METRICS.md, Q13 log,
scraper-canary brief). Every committable item landed (hashes above). Explicitly
**provisional / not committed by design**:

- **Q4 G4 verification** — same-date `health_connect_syncs[date]` ⇄ `samsung_hrv_readings[date]`
  check. Requires the post-deploy operational re-sync on live Railway (unreachable this
  session). Q4 stays `verifying` until G4 passes; then flip to `resolved → #64`.
- **Q13 payload verification** — absent-vs-unmapped (`payload.hrv` empty vs posted under an
  unmapped field name, Q5 territory). Handed to **chat-side** verification per Luke.
- **Scraper canary + Samsung-screen catalogue** — scoped brief prepared, not executed
  (cross-repo, `health-connect-app`). Brief lives in this session's scratchpad
  (`hca-scraper-canary-brief.md`), carried by paste; nothing committed to `health-app`.

## 3. Cold-resume handoff

### State
`master` @ `560ea80`, clean and in sync with `origin/master`. No branches in limbo (all
three feature branches ff-merged + deleted). Untracked, unrelated to this session, left
alone: `.claude/launch.json`, `backend/gate_test.py`.

DECISIONS_LOG max: **#64**. OPEN_QUESTIONS max: **Q13**.

### Single clearest next action
**Confirm the Railway backend deploy is live** (shows commit ≥ `4d6a381`, `/health` green
— the start command runs `alembic upgrade head`, applying migration `f4e1a2b3c6d7`), then
**fire an HCA re-sync** and run **Q4 G4**: verify `health_connect_syncs[date]` sleep stages
match `samsung_hrv_readings[date]` same-date (not date+1). A re-sync against the *old* code
just repopulates the bug — order matters.

### Open questions by status
- **verifying:** Q4 (HC sleep wake-date — code+migration landed #64; G4 pending live re-sync).
- **open:** Q3 (HR cadence during sleep — INCONCLUSIVE, gated on Q2 de-dup), Q5 (HC
  dual-field acceptance — needs a captured payload), Q6 (strength volume-load into daily TL
  — Postgres verify → #28), Q7 (injury ledger missing right proximal semimembranosus), Q9
  (consolidate legacy `user_knowledge`), Q13 (HRV scraper-only SPOF — payload verify
  chat-side; residual tracked to canary #9).
- **parked:** Q10 (AccessLink per-second ingest — revisit when Metabolic-load channel wired).
- **resolved:** Q1→#20, Q2 (HCA `36df9a2`), Q8→#43, Q11→#52, Q12→#53.

### Sprint (ROADMAP)
- **NOW:** HC permission errors (types 38/35/11/37); Samsung package-name correction
  (`com.sec.android.app.shealth`, verify via Railway); morning check-in screen; persistent
  conversation history; two UI bugs (session cards not clickable, dual-panel scroll);
  one-line `mcp_server.get_hevy_workouts` `Session` import fix.
- **NEXT:** **Scraper canary + honest score degradation** (aligns with Q13/#9 — brief
  prepared this session); basic readiness score (suppressed until HRV path confirmed
  end-to-end, 7+ days); manual cardio entry; CLAUDE.md for both repos; deploy companion to
  wife's phone; lab upload pipeline; interpretation layer build; appointment brief;
  supersede #3 (Polar R-R); HCA forwards writer identity; backend F1 source-priority filter.

### Related non-repo artifact
`health-connect-app` scraper-canary + Samsung-screen catalogue brief — in this session's
scratchpad as `hca-scraper-canary-brief.md`. Execute in a `health-connect-app`-rooted
session with the device attached.
