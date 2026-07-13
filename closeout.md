# closeout — health-app

Branch: **master** (feat/constraint-consumption LANDED at `e70437b`, pushed, deleted).
Session brief: constraint-consumption (`;build`) — make injury constraints a consumed input, not decorative.
Status: **complete + landed + prod-seeded.**

---

## 1. Real commits this session

Session-open ref: `2f1309e`. `git log --oneline 2f1309e..HEAD` (all now on master):

```
2b66890 gov: Railway seed done — 2 injury rows in prod (health-app-DB)
2782633 gov(branches): feat/constraint-consumption LANDED at e70437b
e70437b gov: number-at-merge — claim DECISIONS_LOG #72/#73 + Recent landings
d93ef01 chore: session close-out
2ba3e75 gov(branches): park feat/constraint-consumption (code-complete, ready to land)
a6bee90 gov: constraint-consumption — 2 decisions, Q20/Q21, FEEDBACK 1.10/1.11/2.6
785e349 fix(readiness): naive_baseline soreness term = max across all reported sites
d11d96e feat(injury): trajectory divergence + symptom-gated review (surfacing only)
0c235eb data(injury): declare trajectories for pes anserine + right hamstring
42879b4 feat(checkin): derive AM soreness items from active injuries (FEEDBACK 2.6)
5584666 data(injury): seed injury_pes_anserine_left (active irritation)
de8f8d3 data(injury): seed injury_hamstring_right (semimembranosus, neural limiter)
```

Feature/data (concern-split): `de8f8d3` `5584666` `0c235eb` (data) · `42879b4` (capture) · `d11d96e`
(mechanism) · `785e349` (scoring). Governance: `a6bee90` (stores) · `2ba3e75`/`e70437b`/`2782633`/
`2b66890` (park → number-at-merge → land → seed-done). `d93ef01` was the first close-out (pre-land).

What shipped, by brief step:
- **Step 1 (data):** two distinct right-side injuries seeded — right hamstring (structural proximal
  semimembranosus) `signal_type:"mechanical"` NOT neural (the VERIFY gate proved `neural` fires a
  signal-wide radicular block that would kill the wanted SL-RDL; neural finding rides in `detail`), and
  left pes anserine. Left hamstring untouched (distinct injury).
- **Step 2 (capture):** AM soreness items derive from the active injury ledger
  (`checkin_v2.derive_soreness_items`), keyed `{body_part}`/`{body_part}_{side}` (no hamstring collision);
  `CheckInAM.jsx` renders derived keys. No migration (soreness is JSON).
- **Step 3 (mechanism, JSON-only):** injury `trajectory` in `value`; `injury_trajectory.evaluate()`
  surfaces divergence + symptom-gated review in `get_readiness_snapshot`. Surfacing only — never gates.
- **Step 4 (scoring):** `calc_naive_baseline` soreness term = max across reported sites (was
  shoulder-only). Discontinuity accept-and-annotate, not backfilled (frozen-at-capture).

Verification: 74 backend tests green; divergence + review fire against the real seed trajectory; neural
exclusion-set probed over all 30 regions. **Prod seed done** — `seed_engine` against `health-app-DB` via
`DATABASE_PUBLIC_URL`, `injury ledger rows written: 2`.

---

## 2. Pending-queue reconciliation

**No `;cc` pending-commit queue was carried into this session** — it ran from a direct `;build` brief.
The two DECISIONS_LOG entries were minted by Code, headed `### #NEXT`, and **claimed #72 and #73 at merge**
(number-at-merge; DECISIONS max at open was 71). Everything committed, landed to master, and pushed —
nothing provisional.

Governance landed: DECISIONS_LOG #72 (restrictions set at onset; check-in monitors, does not gate) +
#73 (soreness scoring max) + withdrawn-draft note · OPEN_QUESTIONS Q20 (findings-vs-restrictions gap,
open) / Q21 (lab #63/SPEC_64 contract rhymes, no shared code, resolved) · FEEDBACK 1.10 / 1.11 / 2.6.

**Prod state:** injury data seeded (2 rows, with trajectories). The seed→prod path is proven. Not yet
observed live: the trajectory flags in `get_readiness_snapshot` — they need (a) the backend redeployed
with the Step-3 code and (b) an AM check-in recording soreness under the derived keys. Neither is a code
gap; both are organic.

---

## 3. Cold-resume handoff

### Single clearest next action
constraint-consumption is **done and in prod**. The one open loop is watching the trajectory flags fire
once live: confirm `health-app-backend` redeployed from master (`e70437b`+), then the first AM check-in
that records soreness under the derived keys (`pes_anserine_left` / `hamstring_right`) makes the
divergence/review series exist — a `get_readiness_snapshot` (read against **prod**, see caveat) should
then show a "Plan review flags" line. After that, pick up the ROADMAP NOW items.

### Known caveat to resolve
`get_readiness_snapshot` via the MCP connector **appears to read a non-prod DB** — it showed the two new
injuries before any prod seed had succeeded, so it is likely pointed at local sqlite. Verify prod state
with a direct Postgres query (`railway`-injected `DATABASE_PUBLIC_URL`, service `health-app-DB`), not the
MCP tool, until the connector's target is confirmed.

### Current sprint (ROADMAP NOW)
- Morning check-in screen (Hooper Index) — **advanced this session**; soreness items now injury-derived.
- Fix Health Connect permissions (companion app, record types 38/35/11/37).
- Samsung Health package-name correction (`com.sec.android.app.shealth`; verify via Railway query).
- Persistent conversation history; session cards not clickable; dual-panel scroll (UI bugs).
- `mcp_server.get_hevy_workouts` unimported `Session` type — pre-existing one-line import fix.

### Open questions by status
- **open:** Q7 (injury ledger missing right semimembranosus — **structured entry now exists in code +
  prod**; the findings-vs-restrictions modelling remains) · Q20 (findings vs restrictions schema gap,
  Q7 territory) · Q17/Q18 (HRV step-change; historical out-of-range sweep) · Q19 (desktop scroller).
- **resolved this session:** Q21 (lab #63/SPEC_64 expectation contract rhymes with injury trajectory but
  shares no code — kept as separate mechanisms).

### Branches
- `feat/constraint-consumption` — LANDED to master at `e70437b`, pushed, deleted (this session).
- `feat/recovery-metrics-rhr` — PARKED (prior session; not touched here), held on the HRV Task-1 node
  dump in `health-connect-app`.

### Untracked, left alone (not mine)
`.claude/launch.json`, `backend/gate_test.py`.
