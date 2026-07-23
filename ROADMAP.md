# ROADMAP

Last updated: July 2026

---

## NOW — active sprint

| Item | Notes |
|------|-------|
| **Cross-repo:** propagate the CLAUDE.md shared block to `health-connect-app` | **OWED.** The shared block gained #111's secret-rendering prohibition (health-app `CLAUDE.md`, between the `BEGIN/END SHARED LOOP RULES` markers). It must be copied **byte-identically** into `health-connect-app/CLAUDE.md` — a paraphrase is drift, which is the two-master failure the shared block exists to prevent. **Drift verified, not assumed** (read-only check, 2026-07-23): HCA is cloned at `Projects/health-connect-app` and carries the shared block's `BEGIN/END` markers, but greps **0** for the secret-rendering rule where health-app greps 1. Blocked here on three counts: `chore/secrets-residuals` is not cut in HCA, HCA's working tree is not clean, and a canonical-store edit in a second repo is forbidden from a health-app-rooted session. `.claude/settings.json` does **not** propagate (its deny patterns are health-app-specific paths). Owner: Luke, from an HCA-rooted session. Per #112 this is the canonical home for cross-repo debt. |
| **Security:** identify the second credential digest in the transcripts | **OWED — cheap, and it separates a finding from an unknown.** A second credential-shaped digest (`9688f2…`) appears in 4 session transcripts alongside the now-rotated Railway Postgres credential. Co-occurrence test: if it appears **only** in transcripts that also carry the rotated credential, it is almost certainly that credential's predecessor and is dead twice over. If it appears **independently**, it is a distinct credential nobody is tracking and its liveness is unestablished. A few minutes' work, digests and counts only, never values (#111). Until it runs, "open by choice" and "possibly a live credential" are both true of the same item, which is the thing that shouldn't hold. Recorded here rather than in Q44's body — Q44 is `DONE → #111` and closed questions are not scanned for live work (#112). Fold into the next phase-2 session. Owner: Luke. |
| **Guard:** a canonical-surface consistency test — two comparisons, one mechanism | **OWED.** Two canonical surfaces must agree with their source and **nothing enforces it**; both divergences so far were caught by a human-directed VERIFY inside a brief, which is not a mechanism. The never-lag rule says surfaces must not lag and provides nothing that would notice if they did. **(a) SCHEMA.md vs `models.py`** — four columns from migration `c4e8a2019bd7` (`basis_n_samsung`, `basis_n_diary`, `basis_n_alcohol_unknown`, `basis_tib_over_run_min`) sat in `models.py` and absent from SCHEMA.md until a VERIFY happened to look; an omission when the migration was folded in, and folds recur. **(b) CLAUDE.md conventions vs `DECISIONS_LOG` entries** — *presence* is verified (every `(standing, #N)` citation resolves to a real entry; negative control: a fabricated `#999` returns 0) but *content* is not. A convention can say more than the entry it cites, which reads as authoritative and is not. Live instance: the corrected-doc clause at `CLAUDE.md` L247 is marked `POSTDATES #113` — locally truthful, but that annotation pattern permits **unbounded cumulative drift**, since each note is individually visible while the total distance between a convention and its backing entry is visible nowhere. A content comparison is what would surface it. **The detector already exists** and was demonstrated on (a) with a negative control — a fabricated column name must report LAG, proving the check detects absence rather than always passing. That control is the part worth preserving; without it the OKs mean nothing. Separate concern from CBT-I surfaces, so not that branch. Owner: Luke. Recorded here per #112. |
| Fix Health Connect permissions | Companion app returning errors for record types 38, 35, 11, 37. Partially resolved via adb pm grant; proper in-app dialog fix still needed. |
| Samsung Health package name correction | Re-run Health Connect diagnostic with `com.sec.android.app.shealth` filter (not `com.samsung.health`). Verify via Railway Postgres query, not on-device UI. |
| Morning check-in screen | Hooper Index pattern (fatigue, sleep quality, stress, soreness). Primary daily touchpoint. Mutable post-submission with audit trail. See Ideas file for DOMS/soreness split design. |
| Persistent conversation history | Currently clears on browser refresh. Needs backend storage + frontend state management. |
| Session cards not clickable | UI bug — session cards in workout view not responding to click |
| Dual-panel scroll layout issue | UI bug — scroll behaviour broken in dual-panel view |
| `mcp_server.get_hevy_workouts` references unimported `Session` type | Pre-existing bug, found (not introduced) during #42's MCP work — `db: Session = SessionLocal()` with no `Session` import; will raise `NameError` at call time. Out of scope for #42 (Hevy endpoints explicitly not touched); needs a one-line import fix. |

---

## NEXT — queued

| Item | Notes |
|------|-------|
| CBT-I module phase 2 (engine + surfaces + ISI) | Phase-1 substrate landed on `feat/cbti-module` (held for review, DECISIONS_LOG #107/#108/#109): schema + completed-block import (1 block, 9 prescriptions, 53 nights, SE-reconciled). Phase 2 = titration engine (weekly eval; sufficiency/regularity/adherence gates; TST-plateau exit with SE≥85% as a floor; **replay against the imported block = Gate 5**); AM/PM surfaces with the 12h-clock prefill sanity-gate (Q42); ISI 7-item capture. Separate brief. Confirm the VA nap-timing convention before the engine relies on the `naps_min` date−1 read. |
| Scraper canary + honest score degradation | Detect null/stale/implausible scraper output. Surface degraded state to user when HRV unavailable — never silently score without it. |
| Basic readiness score | Formally suppressed until HRV data path is confirmed end-to-end with 7+ days of readings (scraper path confirmed; pending 7-day sample). Once confirmed: Banister fitness-fatigue model (Form = Fitness − Fatigue, dual EWMA) integrated with RMSSD baseline deviation, sleep architecture, and RHR trend. ACWR rejected — see Decisions Log. |
| Manual cardio entry | Unconnected sessions (Rogue Echo bike, gym machines) must be loggable to prevent ACWR silently under-reading load. |
| Deploy companion app to wife's phone | Garmin → Health Connect path. Verify data flowing before deploy. |
| Lab upload pipeline | PDF/photo → Vision extraction → confirmation screen with outlier flagging → stored. First stage of the medical spine. Consumer hero-feature dependency. File-first UX and marker canonicalisation design are Locked — DECISIONS_LOG #48 / #50; neither implemented. |
| Interpretation layer build | Design Locked, build pending — DECISIONS_LOG #49 (delta-first, three sections, filtered levers). Depends on the lab store (row above) and the lever dictionary — DECISIONS_LOG #51 (GRADE-tiered, decided not implemented). Education pathway (explain mechanisms, list/filter levers), NOT clinical advice — regulatory boundary per DECISIONS_LOG #47. |
| Appointment brief | Hero consumer feature — "Never waste a medical appointment again." Pre-appointment synthesis across modules. Depends on lab pipeline + interpretation layer. Can now query `current_state` directly instead of re-deriving it. |
| Supersede DECISIONS_LOG #3 | Polar not session-only, AccessLink live, SDK R-R as highest-fidelity HRV path. Blocked on a *How you know* artifact (Polar R-R verification). |
| HCA forwards writer identity (HCA session) | Forward `dataOrigin.packageName` + an HC `health_data_category_priority_table` snapshot in the `/health-connect/sync` payload. Producer half of the #36/#37 wire contract; source dedup arbitration now lives backend-side, so `validateNight()` becomes a faithful relay. |
| Backend F1 filter (backend session) | Apply source-priority dedup over `health_connect_record_sources` (built in #37). Gated on HCA forwarding the field (row above). Also unblocks F3a (frozen-session-set aggregation) once landed. |

---

## LATER — planned

| Item | Notes |
|------|-------|
| Injury object schema in project files | Schema and extraction method drafted in Ideas. Formalise into Decisions Log and API contracts once morning check-in screen is built. |
| Preset readiness models by sport/goal | Rugby vs endurance vs strength — different metric weighting presets |
| User-adjustable metric weighting | Let users tune what matters to their readiness score |
| AI-personalised model | After ~6 weeks of data per user; Claude infers pattern from history |
| GameTraka connector | Rugby performance data for Luke |
| Apple Health (son) | iOS path; requires either Expo iOS build or separate native integration |

---

## User rollout sequence

1. **Luke (Easty)** — primary dev user; Samsung scraper working; Health Connect partial
2. **Wife** — Samsung Galaxy + Garmin; needs companion app deployed and data flow verified
3. **Son** — iOS; future phase

---

## Dependencies and blockers

| Blocker | Blocks |
|---------|--------|
| Health Connect permissions fix | Polar and Garmin session data |
| Conversation history persistence | AI coaching continuity across sessions |
| Wife companion app deploy | Wife onboarding |
