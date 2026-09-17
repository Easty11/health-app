# Close-out — metabolic `load_window` slot kind (#307), backend + frontend

## Real commits this session

Session-open ref: master `e8cd1a8` (the #305/#306 close-out merge). Two PRs.

**PR1 #228 — backend #307 (merged, `a5e04e3`):**

```
b1a3b04 gov(#307): metabolic load_window slot kind — DECISIONS, ROADMAP, BRANCHES, Recent-landings
71179f6 feat(resolver): metabolic load_window slot kind — declare + count conditioning (#307)
5feb16d docs(handoff): GO receipt — metabolic slot-kind resolver, Amendment 1 + S6
a6fde9f docs(handoff): CHAT→CODE receipt — metabolic slot-kind resolver brief received
```

**PR2 `feat/quota-window-conditioning` — frontend S5 (this branch):**

```
<gov>    gov(#307 PR2): closeout, BRANCHES row, ROADMAP surfacing-1 + sequencing guardrail
f177db8  feat(frontend): QuotaWindow renders the load_window conditioning slot (#307 PR2)
0bcbd65  docs(handoff): GO receipt — PR2 frontend QuotaWindow + G2/sequencing rulings
```

Both branches merged + remote-deleted at land. Non-migration throughout. Self-merge on green
under § Merge disposition (chat-ratified brief + Amendment 1 + operator GO on PR2; no new
judgment — PR2 is #307's frontend, no new decision).

## Pending-queue reconciliation

No `;cc` pending-commit queue was carried in — the brief was the Chat→Code handoff. Everything
it named LANDED; nothing provisional:

- Backend S1–S4 + S6, governance #307 — PR1 (`71179f6`/`b1a3b04`), merged `a5e04e3`.
- Frontend S5 (`QuotaWindow` renders the `load_window` kind, the due marker via `due_slot` on
  either kind, the `concurrent_strength`/`untimed` uncounted reasons) — PR2 (`f177db8`).
- G0 open calls (no floor; untimed fail-closed) ruled from the prod probe.
- Operator review rulings actioned: G2 gate amended (two baseline dict literals gained the
  additive `due_slot: None`; recorded on PR #228); the cross-PR sequencing rule recorded (PR #228)
  and carried below.

Gates: G1–G4 (backend) green — full backend suite 1719 passed on a 3.12 venv; G3 clean. Frontend
suite 195 passed (29 files); the QuotaWindow suite covers both kinds, the due marker on a
load_window slot, and all four uncounted reasons. #121 served-bundle grep is operator-side.

## Cold-resume handoff

**Sprint — v1 test 2 (Know): "what's due, enforced against the plan."** The due-slot resolver
(#276) and the metabolic `load_window` slot kind (#307, backend + frontend) are landed: a phase
microcycle may declare a conditioning quota (`load_window: "metabolic"`) that the resolver counts
from canonical `aerobic_sessions` (session-count only — no dose, bands, or write-back), and
`QuotaWindow` renders it. The engine still never SELECTS conditioning (#270 narrowed, not broken).

**Single clearest next action — operator, gated.** Open the block-2 phase with a conditioning
quota. **DO NOT open it until PR2 (frontend) is deployed AND you have seen the served bundle
render the `load_window` slot** (#121 grep for the "Conditioning" render string on the live
`assets/index-*.js`). Rationale: before PR2 deploys, the old `QuotaWindow` would render a
conditioning slot with an undefined label and show the two new uncounted reasons as "off-plan"
(recorded on PR #228). PR1's backend response is backward-compatible for capacity slots, so
nothing breaks until such a phase exists. Once the served bundle is confirmed, this guardrail
lifts. After that: the wrap-vs-plan view (surfacing item 2, increment 4).

**Open questions gating.** Q106 — the `minutes` reading keeps dose LATER; nothing reads `minutes`.
Q154 — aerobic ingest is not automatable (below). Q158 — uncoupled chronic denominator (unrelated).

**NOT touched this session — named explicitly.**

- **The metabolic INGEST gap is the real ceiling on #307 and it stood still (Q154 / OPEN CALL 0).**
  The prod probe (P5) confirmed Garmin Connect reaches Health Connect (1 exercise + 1204
  heart_rate records in 30 d) but the backend writes NO `aerobic_sessions` row for it — HC
  exercise is source-captured only (`health_connect.py`, #189); the only `aerobic_sessions`
  writers are Polar (`routers/polar.py`, `import_polar.py`, source `polar_flow_export`). So the
  #307 conditioning quota counts ONLY Polar-Flow-export sessions; every Garmin/Samsung/HC session
  is invisible to it (and to the load model). The H10/Polar export is the no-build cover. The
  Garmin→metabolic bridge (HC-workout ingest with zones from posted HR, vs a direct
  `garminconnect` pull) is its own operator brief — the highest-leverage next thing, and where
  the OPEN CALL 1 session-floor question becomes real. A data-path lane, not more resolver
  instrumentation.
- **Interpretation layer / Appointment brief lanes** — no change; substrate-complete, unstarted.

**v1-triage (NOW lanes).** The exposure/Know lane served **Know** (test 2) this session, backend
and frontend both landed; it remains its home. No NOW lane rode by momentum without a v1 test.
The metabolic-ingest bridge, once briefed, serves Know AND the load model (readiness) — the lane
that makes #307's count complete rather than Polar-only. Operator's own owed (not Code):
plan-of-record v2 (pending knee-consult + club-start dates); the HCA HR-lag brief go-ahead.
