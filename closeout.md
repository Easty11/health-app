# closeout — health-app

Branch: `feat/constraint-consumption` (8 commits, local-only, parked in `BRANCHES.md`, **not merged**).
Session brief: constraint-consumption (`;build`) — make injury constraints a consumed input, not decorative.

---

## 1. Real commits this session

Session-open ref: `2f1309e` (master tip). `git log --oneline master..HEAD`:

```
2ba3e75 gov(branches): park feat/constraint-consumption (code-complete, ready to land)
a6bee90 gov: constraint-consumption — 2 decisions, Q20/Q21, FEEDBACK 1.10/1.11/2.6
785e349 fix(readiness): naive_baseline soreness term = max across all reported sites
d11d96e feat(injury): trajectory divergence + symptom-gated review (surfacing only)
0c235eb data(injury): declare trajectories for pes anserine + right hamstring
42879b4 feat(checkin): derive AM soreness items from active injuries (FEEDBACK 2.6)
5584666 data(injury): seed injury_pes_anserine_left (active irritation)
de8f8d3 data(injury): seed injury_hamstring_right (semimembranosus, neural limiter)
```

Concern-split honoured: data (`de8f8d3`, `5584666`, `0c235eb`) · capture (`42879b4`) · mechanism
(`d11d96e`) · scoring (`785e349`) · governance (`a6bee90`, `2ba3e75`) each separate.

What landed on the branch, by brief step:
- **Step 1 (data):** two distinct right-side injuries seeded into `_INJURY_SEED` — right hamstring
  (structural proximal semimembranosus) and left pes anserine. Right hamstring recorded
  `signal_type:"mechanical"` (NOT neural) after the VERIFY gate proved `neural` fires a signal-wide
  radicular block (hinge/rotation/carry/gait) that would kill the wanted SL-RDL lane; the neural finding
  rides in `detail`. Left hamstring untouched (distinct injury).
- **Step 2 (capture):** AM check-in soreness items derive from the active injury ledger
  (`checkin_v2.derive_soreness_items`), keyed `{body_part}` / `{body_part}_{side}` so the two hamstrings
  don't collide. Frontend `CheckInAM.jsx` renders whatever keys arrive; no migration (soreness is JSON).
- **Step 3 (mechanism, JSON-only — no migration):** injury `trajectory` in `value`;
  `injury_trajectory.evaluate()` surfaces divergence + symptom-gated review in `get_readiness_snapshot`.
  Surfacing only — never alters `restrictions[]` or gates selection.
- **Step 4 (scoring):** `calc_naive_baseline` soreness term generalised to max across reported sites
  (was shoulder-only). Discontinuity accept-and-annotate, NOT backfilled (frozen-at-capture).

Verification: full backend suite **74 green**. Divergence + review proven to fire against the real seed
trajectory (isolated in-memory sqlite). `neural`-exclusion probe run over all 30 taxonomy regions.

---

## 2. Pending-queue reconciliation

**No `;cc` pending-commit queue was carried into this session.** It ran from a direct `;build` brief,
not a chat close-out handoff. The two DECISIONS_LOG entries were minted by Code this session, headed
`### #NEXT` (integers claimed at merge per CLAUDE.md number-at-merge; DECISIONS max at open was 71).
Both are committed (`a6bee90`) and therefore synced, not provisional — but **unnumbered until the branch
fast-forwards to master**.

Governance written this session, all committed:
- DECISIONS_LOG `#NEXT×2` (restrictions-set-at-onset / check-in-monitors; soreness-scoring-max) +
  withdrawn-draft note (additive-checklist regulatory scope — void, fabricated premise).
- OPEN_QUESTIONS Q20 (findings-vs-restrictions schema gap, open) · Q21 (lab #63/SPEC_64 contract rhymes
  but shares no code, resolved).
- FEEDBACK 1.10 (scoring blind to all injuries but shoulder) · 1.11 (chat context not cross-device) ·
  2.6 dated confirmation (pes anserine uncapturable ~3 days).

**OWED (committed in-repo, but unproven against prod):** live Railway seed of the two new injury entries
+ trajectories, then `get_readiness_snapshot` read-back. Verified only on local sqlite this session — the
MCP connector was invalidated (needs reconnect). #42 precedent makes local-verify acceptable to commit,
but the seed→prod path is unproven. Recorded in `BRANCHES.md`.

CLAUDE.md "Recent landings" intentionally **not** updated — that block tracks work merged to master;
this branch is parked, not landed. It is tracked in `BRANCHES.md` instead.

---

## 3. Cold-resume handoff

### Single clearest next action
**Land the branch and close the OWED prod gap.** With sign-off: `git land feat/constraint-consumption`
(ff-only merge + push + delete). Then run `seed_engine` against **Railway Postgres** so
`injury_hamstring_right` + `injury_pes_anserine_left` (with trajectories) exist in prod, and confirm via
`get_readiness_snapshot` that both hamstrings + pes anserine render and the "Plan review flags" section
behaves. Note: `_seed_injuries` is add-only — the two new keys don't exist in prod yet so the first seed
includes their trajectory; the 3 pre-existing injuries stay unchanged (no trajectory, by design). If any
target injury already exists in prod, trajectory will NOT backfill — it needs an update path.

### Current sprint (ROADMAP NOW)
- Morning check-in screen (Hooper Index) — **this session advanced its soreness-capture surface**; items
  now injury-derived.
- Fix Health Connect permissions (companion app, record types 38/35/11/37).
- Samsung Health package-name correction (`com.sec.android.app.shealth`; verify via Railway query).
- Persistent conversation history; session cards not clickable; dual-panel scroll (UI bugs).
- `mcp_server.get_hevy_workouts` unimported `Session` type — pre-existing one-line import fix.

### Open questions by status
- **open:** Q7 (injury ledger missing right semimembranosus — **partially closed this session**: the
  structured entry now exists; the findings-vs-restrictions modelling remains) · Q20 (findings vs
  restrictions schema gap, Q7 territory) · Q17/Q18 (HRV step-change instrumentation-vs-physiology;
  historical out-of-range sweep) · Q19 (desktop workout-detail scroller layout).
- **resolved this session:** Q21 (lab #63/SPEC_64 expectation contract rhymes with injury trajectory but
  shares no code — kept as separate mechanisms).

### Branches
- `feat/constraint-consumption` — CODE-COMPLETE, parked, ready to ff-land (this session).
- `feat/recovery-metrics-rhr` — PARKED (prior session; not touched here), held on the HRV Task-1 node
  dump in `health-connect-app`.

### Untracked, left alone (not mine)
`.claude/launch.json`, `backend/gate_test.py`.
