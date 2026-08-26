# Session close-out — Q6 gate 2 (Tier-0 `load_events` transform), landed + live-verified; Q6 DONE

## 1. Real commits this session

`git log --oneline cd1c81f..HEAD` (session-open ref `cd1c81f`, master tip at session start). All
landed on master via the PR #107 merge commit `c36825d`:

```
709ef35 gov: resolve #NEXT->#241 / Q#NEXT->Q121 at land; BRANCHES DONE
14024de gov: correct gate-2 entry + stale ROADMAP row-79 wording
41d0cdb fix(load): per-set RPE + load-sums-as-logged (review defects 1 & 2)
4402eae gov: Q6 gate 2 stores — decision, question, roadmap, branches
dd7193c feat(load): Tier-0 load_events transform + store (Q6 gate 2)
```
Merge: `c36825d Merge pull request #107` (merge commit, `--merge`, branch remote-deleted).

Plus this close-out commit (`chore: session close-out`) on the restarted branch
`claude/q6-gate2-load-events-9kejqs` (from `c36825d`) → a new follow-up governance PR.

**One PR this session, plus the close-out PR:**
- **#107** `c36825d` — the gate-2 transform + store + review corrections + governance. Contained
  the schema migration `c7d9e2f14a86` (`load_events`); opened held per `#238`, merged on explicit
  operator release. Deploy SUCCESS; migration applied clean (`f9a2c1d40b73 -> c7d9e2f14a86`); the
  dual-head signature did NOT fire.
- **close-out PR** — `#242` live-verify entry, Q6 → DONE, ROADMAP gate-3-NOW, FEEDBACK §1 standing
  correction, container-tooling note, CLAUDE.md Recent-landings + Tooling, BRANCHES. Governance
  only (no schema) → merge-on-green.

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried in — the session opened from a task brief, not a chat
close-out. Nothing provisional is outstanding. Every decision reached this session landed:
- Gate-2 transform + store + `_rpe_coverage` fix → `dd7193c` (in #107).
- Review corrections (per-set RPE, load-sums-as-logged, epoch diagnostic-only) → `41d0cdb` (#107).
- `#241` + governance, number-at-merge resolution → `4402eae`/`14024de`/`709ef35` (#107).
- `#242` live-verify + Q6 DONE + standing correction + container note → this close-out commit.

## 3. Cold-resume handoff

### What landed and is live
Q6 **gate 2 is DONE and live-verified** (`#241` transform, `#242` live-verify). The Tier-0
`load_events` transform derives per-session-window Mechanical + Neuromuscular load from
`hevy_workouts.raw` (`formula_version 'tier0-v1'`), recompute-not-migrate (D-B), source-neutral
store, gap-recording `provenance`. **Prod closing query (54 non-excluded sessions): Neuromuscular 480.818 `nm_au`** (unaffected) —
strength volume non-zero in the per-window load path for the first time since Q6 was filed. The
first **Mechanical** sum (3,056,351.056 `kg_reps`) was **defect-affected** and is superseded by the
operator's post-`#243` recompute: `#243` fixed a bodyweight-COALESCE leak that priced weight-NULL
Hevy cardio (treadmill/bike/row) as mechanical work. Q6 stays DONE (strength is in the path); only
the Mechanical magnitude was wrong. Recompute diagnostics: 36 sessions
e1RM-fit, 24 reps-banded (pre-epoch tail), 0 indeterminate-laterality, 0 artifact-signature.

Two rules carried in the governance, both now canonical:
- **Standing correction (FEEDBACK §1, `#242`):** a held PR is held for the RELEASE DECISION only;
  on release Code executes the entire land end-to-end (resolve `#NEXT` → push → guard green →
  un-draft → merge → delete → verify deploy + migration in boot logs). Operator residue = release
  decision + prod-credentialed execution + data judgement, nothing mechanical.
- **Container-tooling (CLAUDE.md Tooling):** `psql` absent from the backend image; `railway
  connect` to `health-app-DB` is the operator's prod psql route. Transform recompute is
  `python backend/load_events.py` in-container.

### Current sprint / NOW
**Gate 3 — `load_metrics` daily rollup + the Banister fitness-fatigue model (per `#32`).** Daily
per-window derived rollup, recomputable from `load_events` (D-B); four independent Fitness/Fatigue
channels, per-window τ (Mechanical slowest ~10 d, Neuromuscular ~6 d, Metabolic ~4 d, Fitness
~42 d), no global fatigue term; Neuromuscular fed by velocity/RFD proxy never raw CMJ. This is what
wires the strength term into a **consumed** metric and retires the aerobic-only ACWR of `#8`
(`mcp_server.get_training_load` is still aerobic-only today).

### Open questions by status
- **DONE this session:** Q6 → `#242` (strength volume in the per-window load path).
- **OPEN, gating forward load work:** `Q121` (Tier-0 modelling gaps — weighted-bodyweight
  undercount, non-rep NM=0, half-point RIR banding; all recompute-away under a new
  `formula_version`, none blocking gate 3). `Q117` (are three `expected_load` levels enough).
- **OPEN, unrelated to load:** `Q120` (injury onset field), `Q118` (Health Connect record
  metadata dropped), `Q116` (`schedule_item` validator backfill).

### Single clearest next action
Build **gate 3**: the `load_metrics` migration + daily per-window rollup reading `load_events`,
then the Banister dual-EWMA per `#32`. Contains a schema migration → the PR opens held for the
release decision per `#238`/`#242`.

### What was NOT touched this session (name the standing lanes)
This session — like gates 1 and 2 before it — went entirely to the **load instrument** (Q6), not
to user-facing product. Three consecutive Q6 sessions have built the strength-load substrate; no
product surface moved. Standing still, explicitly:
- **CBT-I user surface (interim)** — the titration engine is built (`cbti/`) but invisible in the
  app: no route/page/nav. Gated on `#47` (show engine state vs the MOVE/REVERSE verdict) and the
  diary-capture fork, not on display hygiene. Untouched.
- **The `#116`/`#121` frontend deploy probe** — never run; the served-bundle grep that would
  confirm a frontend deploy remains owed from earlier sessions.
- **Medical Protocol and Decision Support modules** — the other two of the three platform modules;
  no work this session (Fitness/load lane only).
- **`Q120` injury-onset** and the ROADMAP injury reframe / edit-supersede lane — untouched.
- **Parked latent hazard:** the pre-existing second alembic head `e2d5c7a1b9f3` (predates the Q6
  lane) — deploys boot clean with both heads, but a future single-linear-head migration or an
  `alembic upgrade head` (singular) path trips `Multiple head revisions`. Resolve with a merge
  migration when that lane is picked up (`#242`). Not this lane's to fix.
