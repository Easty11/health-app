# OPEN QUESTIONS

Undecided forks and unverified-at-machine items. One state per item, from the **question-state**
axis (`OPEN` / `OWED` / `DONE → #N`) defined in `CLAUDE.md` → **State vocabulary** (the sole
definition). The label is `**State:**` (never `**Status:**`). `DONE → #N` names the resolving
`DECISIONS_LOG` entry.

---

## Q3. HR sampling cadence during sleep unconfirmed (`hrMedianGapSec = 0`)

Gate 3 returned `hrMedianGapSec: 0` over 802 samples, not the expected ~60s (1/min). Caused
by duplicate HR timestamps from the same record-doubling as Q2. The artifact flagging depends
on real HR density during sleep, so this must be re-measured after HR is de-duped. Gate 3 is
INCONCLUSIVE — do **not** calibrate `DELTA_ARTIFACT` / `SPREAD_SPIKE` / `SHORT_MS` or wire
`runDeepConfidence` into readiness/Banister until resolved.

**State:** `DONE → #173` — **superseded, not answered.** Q3 gated two things: (a) calibrating the
artifact constants and (b) wiring `runDeepConfidence` into readiness/Banister, both pending a Gate 3
HR-cadence re-run. `#173` (extending `#71`) decides device deep-minutes will not drive readiness or
Banister at all, so **(b) is cancelled and (a) is moot** — diagnostic-only use needs no calibration, and
the re-run is no longer owed by anyone.

Footnote, because the correction matters more than the close: the prior **"the precondition has
CLEARED"** claim above was itself false. `collapseSleepSessions()` de-dups sleep **sessions** only; the
HR array is never de-duped on HCA master, so a re-run would likely have reproduced `hrMedianGapSec: 0`.
Q3 was therefore never actually re-runnable on the stated basis. *(That falsification is a
`health-connect-app` claim reported by the 2026-08-03 chat session and is **not verifiable from this
tree** — it is recorded, not attested. It does not carry the close: `#173` does.)* Cross-refs
`Q81`, `#71`.

---

## Q4. HC dates each night one day earlier than the scraper

After the Q1 backfill, corrected HC stage minutes match the scraper but under a consistent
one-day shift: `health_connect_syncs[date] ≈ samsung_hrv_readings[date+1]` (3 nights match
all three stages exactly, the rest within 1–2 min; 0 same-date matches). `_aggregate_day`
attributes a session by its bed-date while the scraper keys on the wake-date. This
pre-existed the Q1 fix — it was invisible while the HC values were garbage. It matters
because `_section_health_connect` selects "today/yesterday" and the dashboard joins by
date, so HC and scraper rows for the *same physical night* land on different days. Decide a
single canonical sleep-date convention (likely wake-date, to match the scraper) and align
`_aggregate_day`.

Resolved in code at DECISIONS_LOG #64
(`fix/hc-sleep-wake-date-attribution`): canonical sleep-date = **local (AEST) wake-date**
(`endTime`), aligning to the scraper; `_aggregate_day` filter + date-collection loop switched
to wake-date-only via a tz-aware `_wake_date`, and existing sleep values cleared by migration
`f4e1a2b3c6d7` for a post-deploy HCA re-sync. G4 (confirm `health_connect_syncs[date]` sleep
stages match `samsung_hrv_readings[date]` **same-date**, not date+1) is pending the
operational re-sync against live Railway data — an earlier session could not reach Railway.

**State:** `DONE → #64` — **G4 passed** against live Railway Postgres, 2026-08-03. A same-date join of
`health_connect_syncs` against `samsung_hrv_readings` (`captured_at = date`) matched 11 of 14 recent
nights (deep exact, REM/light within ~1–2 min), and the control join at `date + 1 day` returned
`still_shifted = 0` — the one-day shift is gone, which is precisely what G4 asked. The wake-date
convention holds in production.

Three nights still undercount, for a cause unrelated to date attribution — split out as `Q82`
(fragmented sessions) and `Q83` (source-blind selection) rather than left inside a closed
question. *(The G4 query was run by the 2026-08-03 chat session; the Railway CLI was non-functional in
the Code session that recorded this close, so the result is carried as reported and reproducible, not
re-attested here.)* Owner: Luke.

---

## Q5. Backend `/health-connect/sync` dual-field acceptance — collapse after confirming what mobile posts

`routers/health_connect.py` accepts both the raw Health Connect library field names and the
mapped JS names for the same value — `HeartRateRecord.beatsPerMinute`/`bpm` (`.get_bpm()`),
`HRVRecord.heartRateVariabilityMillis`/`rmssd` (`.get_rmssd()`), `StepsRecord.startTime`/`date`
(`.get_start()`) — the "intentionally flexible" tolerance that exists only because the contract
was not single-sourced. With the sleep-stage enum now single-sourced (DECISIONS_LOG #24), the
same can be done here: capture one real on-device sync, confirm exactly which field names
`health-connect-app` actually posts, pick the canonical name, then collapse the dual acceptance
and delete the `.get_*()` reconcilers (this is "Phase 2" of the contract work). Which name to
keep is unverified until an actual payload is captured.

**State:** OPEN — the **capture precondition is STRUCK**. Master source *is* the emitted contract: HCA's
mappers rename raw→mapped in the map expression and React Native serializes verbatim, so no build can
emit the raw names and no on-device capture can tell us anything the source does not. Canonical is
decided at `#174` = HCA's mapped names (`bpm` / `rmssd` / `date` / `type` / `workouts`).

Next action (CODE): delete the five dead branches — `HeartRateRecord.beatsPerMinute`,
`HRVRecord.heartRateVariabilityMillis`, `StepsRecord.startTime`, `ExerciseRecord.exerciseType`,
`SyncPayload.exercise` — and add the field-name contract test. `.get_kg()` / `.get_meters()` are
**excluded** (forward-compat for unposted record types, not a dual-name contract). The test is not
optional: the client half of `#174`'s evidence was read cross-repo and is unverifiable from this
tree, so the test is what converts it from assumption to assertion. → `DONE → #174` when the collapse
lands. Owner: Luke.

---

## Q6. Strength volume-load not yet ingested into daily training load

Decision 28 routes strength volume-load → the Mechanical + Neuromuscular windows as a
named, non-optional daily-TL input. The decision is settled, but it is unverified at the
machine: no Postgres query has confirmed Hevy strength volume actually populating the
per-window `load_metrics` rows. Verify a real query shows strength volume landing in the
load path before the four-window engine — or even Tier 0 with a strength term — can be
trusted. Was tracked as "B2" in an out-of-project session's scheme that never entered the
repo; recorded here under the canonical Q-series.

**State:** OPEN — **re-scoped 2026-08-03: this is unbuilt work, not an unverified one.** The named
check — a Railway query confirming Hevy strength volume populates per-window `load_metrics` rows — is
**unrunnable**, because no `load_metrics` table exists. Confirmed three ways: `to_regclass(
'public.load_metrics')` returned NULL against prod Railway (2026-08-03, chat session); no migration in
`backend/migrations/` creates it (re-verified against master this session); and `mcp_server.py:578`
says so in the user-facing output — "Hevy volume load is NOT yet integrated into this calculation
(aerobic_sessions only)."

`#28` already records the shape: *"Decided, not implemented … Gated on: per-window `load_metrics` at
ingestion · Hevy strength ingestion (Q6) · Polar zone (#10)."* So the work is: build Hevy strength
volume-load → Mechanical + Neuromuscular `load_metrics` rows, sequenced after the (also unbuilt)
`load_metrics` table. **Consequence today:** strength contributes **zero** to the deployed load metric,
which is the interim aerobic-only ACWR of `#8`. OPEN rather than BLOCKED — nothing prevents building
it; it simply has not been built. → `DONE → #28` when the ingestion exists **and** a query then shows
rows landing. Owner: Luke. Cross-refs `#28`, `#32`, `#10`, ROADMAP "Banister build".

---

## Q7. Structured injury ledger (`user_knowledge_entries`) is missing the right proximal semimembranosus tear

DECISIONS_LOG #42 migrated Luke's device/method facts and three injuries (left little
finger, right shoulder, left hamstring) into `user_knowledge_entries` — but reused
`seed_engine.py`'s existing `_INJURY_SEED` verbatim rather than authoring new injury data.
`FEEDBACK.md` §5 ("Easty's Current Injury State") documents a **fourth**, distinct injury —
right proximal semimembranosus, full-thickness partial-width rupture, confirmed ultrasound
Aug 2025 — explicitly called out there as DISTINCT from the left hamstring issue. It has
never been in the structured ledger (`seed_engine.py`'s `_INJURY_SEED` predates this
session and also only carried three). `_section_schedule`'s "THIS WEEK FLAGS" injury
render and `mcp_server.get_readiness_snapshot`'s injury query (both now sourced from
`user_knowledge_entries` as of #42) are therefore both missing this injury today. Also
missing: the richer three-valued provocative/clear/untested detail per injury that
`FEEDBACK.md` §5 carries but the current `_INJURY_SEED` schema (`body_part`, `side`,
`restrictions`, `detail`) does not have a field for.

**State:** `DONE → #72` — confirmed live 2026-08-03: a prod Railway query over
`user_knowledge_entries WHERE key LIKE 'injury_%'` returned **5 active injury rows**, including
`injury_hamstring_right` (right proximal semimembranosus). Authoring is complete and faithful to
FEEDBACK §5 — the seed is in fact a **superset**, also carrying `injury_pes_anserine_left`.

The findings-detail half is handed **wholly to Q20** (now decoupled), so it is not a residual here.
This discharges `#72`'s live-seed OWED. The remaining sliver of `#72`'s OWED — whether
`get_readiness_snapshot` actually *renders* the injury — is a code-path check, not ledger
completeness, and is tracked under `#72`, not Q7. *(Railway result carried as reported by the
2026-08-03 chat session; the Railway CLI was non-functional in the Code session recording this.)*

---

## Q9. Consolidate legacy free-text `user_knowledge` into `user_knowledge_entries`?

Legacy `user_knowledge` (free-text category/content) coexists with structured
`user_knowledge_entries` per #44. Fold the legacy KB in as a `type="note"` entry and
retire `routers/knowledge.py`'s legacy write path + `context_builder`'s parallel
`knowledge_entries` param — making `context_builder` a true single-source formatter over
`current_state` — or keep them permanently distinct (free-text notes vs typed declared
state)? Deferred by #44; not urgent.

**State:** OPEN — undecided design fork (fold the legacy KB in as `type="note"` vs keep the two
permanently distinct). Deferred by #44, not urgent. No blocker.

---

## Q10. Build AccessLink per-second ingest for the Metabolic-load window (HC/companion lane)?

#35 established the dependency: HC carries no per-second R-R/HR-zone; only AccessLink
(v3 REST exercise-samples / TCX export) does. #46 specified the exact pathway but it is
not built. PSL covers Luke's direct solo/gym capture, so the need only bites if the
HC/companion lane carries a Polar user requiring per-second — currently none (Deb's
wearable integration deferred, Cooper has no wearable).

**State:** OPEN — low priority, deliberately deferred. **Not BLOCKED**: #46 already specified the
pathway, so nothing prevents building it; there is simply no consumer yet (Deb's wearable integration
deferred, Cooper has no wearable). Revisit when the Metabolic-load channel is wired to Polar-in-HC data
for a real consumer.

---

## Q13. HRV is scraper-only — Health Connect `hrv_rmssd` structurally empty; single point of failure pending scraper canary (#9)

Both HRV surfaces in the app — the Recovery card and the v2 AM check-in passive tile — read
`samsung_hrv_readings.hrv_ms` (the Samsung Health accessibility-scrape). The parallel Health
Connect column `health_connect_syncs.hrv_rmssd` comes back **always NULL**. The ingest does
attempt to fill it: `_aggregate_day` averages `payload.hrv` via `get_rmssd()` (which accepts
both `rmssd` and `heartRateVariabilityMillis`), so an empty node means the inbound payload
carries **no HRV records at all**. Root cause is the confirmed, closed platform finding —
*Samsung does not write Ring HRV (nor RHR, sleep stages, respiratory rate) to Health Connect*
(DECISIONS_LOG "things tried and abandoned"). HRV therefore has exactly one delivery path (the
scraper); there is no HC fallback and no HC-side ingest change can recover it. That makes the
scraper a **single point of failure for HRV**, fragile to any Samsung Health UI change — the
motivation for the scraper canary (issue #9) and a per-Samsung-screen metric catalogue
(`health-connect-app` work; distinct from the frontend-page catalogue in `METRICS.md`).

Not-yet-verified-at-machine: "empty because HRV is absent from the payload" is **inferred**
from the closed finding + ingest logic, not re-confirmed against a live captured sync. The
competing (less likely) explanation is that HCA posts HRV under a field name neither
`get_rmssd()` branch maps — the open **Q5** territory. One captured real payload's `hrv[]`
(or a Railway sync/`health_connect_record_sources` check) disambiguates absent-vs-unmapped.

**State:** OWED — root cause is a closed platform finding; what remains is confirmatory. Outstanding
check: capture one real HC sync payload and confirm `payload.hrv` is empty (absent, not unmapped per Q5).
Owner: Luke. If absent-confirmed, the residual is the HRV single-point-of-failure risk, tracked to issue #9
(`health-connect-app` scraper canary). Cross-refs Q5, issue #9.

---

## Q15. `3497ab483935` prod-drift reconciliation

Autogenerate surfaced (and Code stripped) three divergences between local and prod at
revision `3497ab483935`: an `exercise_sessions` drop, `samsung_hrv_readings.context`, and
`api_key_encrypted` `VARCHAR`→`TEXT`. Confirm each is an intended local/prod difference or
a real un-migrated delta. Resolve against Railway Postgres, not local.

**State:** OWED — outstanding check: confirm each of the three divergences against **Railway Postgres**
(not local) as either an intended local/prod difference or a real un-migrated delta. Owner: Luke.

---

## Q18. `samsung_hrv_readings` historical out-of-range sweep

DECISIONS_LOG #70 added an ingest bounds guard that nulls-and-logs out-of-range biometrics going
forward (trigger: `2026-06-28 Eff=119%`), but **existing rows are unswept** — the sweep could not run
this session because the local `DATABASE_URL` is dev SQLite with zero production rows. Run the
full-schema `NOT BETWEEN` sweep (mirrors `_BOUNDS` in `routers/samsung_hrv.py`) against **Railway
Postgres**; for any historical violator, null/clamp the offending field (the guard only protects new
writes). If efficiency was unbounded, assume other fields were too — the sweep covers the whole
numeric schema, not just efficiency.

**State:** OWED — outstanding check: run the full-schema `NOT BETWEEN` sweep against Railway Postgres and
null/clamp any historical violator. Owner: Luke. Independent of Q17. Same loop as `BRANCHES.md`
`fix/hrv-sleep-integrity` Task 3.

---

## Q19. Desktop workout-detail exercise scroller starved to ~36px — right-column space allocation

Desktop full-width, a workout opened in `WorkoutDetail` (`frontend/src/components/WorkoutPanel.jsx`
lines 190–244): reported symptom, verbatim — "no scroll ability for the full column, only the
exercise section, which is small." Live DevTools measurement on the authenticated app (Chromium,
~779 px-tall viewport) confirms the exercise list at `WorkoutPanel.jsx:224`
(`flex-1 overflow-y-auto px-4 py-4 space-y-5`) computes `clientHeight 36` / `scrollHeight 1977`,
`overflow-y: auto` — scrollable, but squeezed to a 36 px window. **Nothing is stranded/unreachable**;
the fixed chrome above simply consumes the panel. Cause is **space allocation, not a
min-height/overflow CSS defect**: the right column (727 px) splits 50/50 between HealthPanel and
WorkoutPanel (both `flex-1 min-h-0`, `Dashboard.jsx:99/102`), so WorkoutPanel gets ~363 px; the two
`flex-none` blocks above the list — header (`:192`) and the stats-grid + session-analysis + "Get AI
Feedback" button block (`:197–223`) — consume ~327 px, leaving the `flex-1` exercise list ~36 px.

Falsified prior hypothesis: the `md:min-h-0`-on-four-scrollers fix (drafted as "#70", **withdrawn** —
the real #70/#71 are the HRV work) was disproven by measurement; all four targets are self
scroll-containers whose flexbox automatic-minimum is already 0, so `min-h-0` is inert (pre-fix sim
scrolled identically, 274 vs 3144). The Dashboard column chain is measurement-confirmed bounded
(LEFT/Chat scroller 573→112029 and HealthPanel 363→511 both scroll correctly); the LEFT-column prime
suspect was exonerated (clientH == scrollH == 727).

Fork (undecided): (a) let the whole detail view scroll as one unit — move the scroll boundary to the
panel root so the stats/analysis chrome scrolls with the exercise list rather than being pinned;
(b) rebalance the right-column 50/50 split so the expanded/active panel gets priority, or size to
content; (c) cap the chrome height so the list keeps a usable minimum. Frontend-only; no connector,
contract, or schema impact.

Not-yet-characterised: measured only at ~779 px viewport height — taller viewports give WorkoutPanel
more room and may not exhibit it. A faithful isolated repro (real compiled CSS, verbatim classes) did
**not** reproduce it; the trigger is specifically the detail-view chrome height vs the ~363 px
half-column, which the repro did not stage.

**State:** OPEN — frontend layout fork: decide direction (a) / (b) / (c), then implement. Branch
`fix/desktop-column-scroll` was cut then discarded (zero commits; deleted). No DECISIONS_LOG entry.
No blocker — the decision is Luke's to make at will, nothing external gates it.

---

## Q20. Clinical findings vs restrictions — `user_knowledge_entries.value` conflates them

Restrictions are structured (`restrictions[]`, enforced by `selection.py`); **findings are not**.
Positive right slump, S1-pattern referral, frontal-plane deficit have no first-class home in the injury
`value` JSON — they ride as `signal_type` + free-text `detail`. The constraint-consumption brief added a
`trajectory` key to `value` but deliberately did **not** model findings. Note the split surfaces
elsewhere too: FEEDBACK §5 documents these findings clinically, but the structured ledger the engine and
snapshot read does not carry them. Q7 territory.

**State:** OPEN — **decoupled from Q7 (2026-08-03).** The "resolve jointly with Q7 / Q7 is itself
UNSTARTED" framing is now stale: Q7's authoring is discharged at `#72`, so there is nothing left to
resolve jointly *with*. Q20 stands alone.

The question is unchanged in substance: give clinical findings — positive slump, S1-pattern referral,
frontal-plane deficit, "pressing untested" — a first-class structured home in the injury `value` JSON,
specifically the three-valued **provocative / clear / untested** status that FEEDBACK §5 carries as a
table column and the ledger does not. No blocker. Owner: Luke.

---

## Q22. Promote exercise-region tags to a source-agnostic canonical exercise layer

Tags are currently keyed on the **Hevy** template id (`exercise_region_tags.hevy_exercise_template_id`),
in tension with the device-agnostic-from-day-one principle. The labs module already solved the analogous
problem (`marker_canonical`). Deferred deliberately for the tagging brief — 493 rows are cheap to re-key,
and movement-identity-across-sources is a real design exercise that should not be rushed inside a tagging
task.

**State:** OPEN — deliberately deferred, not abandoned (#74). **Not BLOCKED**: 493 rows are cheap to
re-key, so nothing prevents it. Revisit when a second exercise source appears or the canonical-exercise
layer is designed.

---

## Q23. Do `_RADICULAR_BLOCKS` / `_RA_FLARE_BLOCKS` need revision now that region attribution is accurate?

Correctly tagging Pallof as `anti_rotation`-only (and Shoulder Rotation as NOT `rotation`) is what makes
the radicular rotation-block behave correctly for this user. Other blocks in `selection.py` may have been
tuned against wrong keyword inputs and never noticed — the block sets and the (now-fixed) loaded-region
inference were never independently validated.

**State:** OPEN — **the stated precondition has CLEARED**: active-window tags were human-confirmed
and seeded in prod on 2026-07-14 (`seed_exercise_region_tags.py 1 --confirm` → 37 tag rows, 56/56 titles
resolved; see `BRANCHES.md` `fix/exercise-tag-coverage`). The audit of `_RADICULAR_BLOCKS` /
`_RA_FLARE_BLOCKS` has simply not been run. No blocker.

---

## Q24. Does anything besides reconciliation consume `laterality`? Is there a `capability_state.side` join that should exist?

`capability_state` already carries a `side` column (left / right / bilateral). `hevy_exercise_templates.laterality`
now records whether a movement is unilateral. A unilateral logged exercise plausibly should feed a per-side
`capability_state` row, but no such join exists today. `laterality` is currently written and consumed only
by (future) plan↔log reconciliation.

**State:** OPEN — blocker: the plan↔log reconciliation is not built, and it is `laterality`'s ONLY
consumer, so whether a `capability_state.side` join *should* exist cannot be settled until that consumer
exists. Owner: Luke. Unblocks on: reconciliation being designed/built.

---

## Q27. Capability_Taxonomy v0 has no axis-type for joint-level STRENGTH RATIOS — grounded v1 family

Four independent instances in one user's last-90d log point at one structural hole: v0 is a movement-PATTERN
and screening vocabulary with no axis-type for **joint-level strength / strength-ratio** reads.

| Movement | v0 offers | Why it fails |
|----------|-----------|--------------|
| Copenhagen Plank | nothing | Adductor strength; `frontal_single_leg_stability` is closed-chain balance, `anti_lateral_flexion` is trunk — a side-lying adduction load demonstrates neither |
| Shoulder ER / IR | `shoulder_mobility` | Cable ER at load is STRENGTH; shoulder_mobility is a mobility screen — wrong capacity |
| Hip Add / Abd (machine) | nothing | Open-chain frontal-hip strength; not `frontal_single_leg_stability` (closed-chain stability) |
| Calf raise | `ankle_df` — REJECT | Plantarflexion STRENGTH ≠ dorsiflexion MOBILITY (category error, #76) |

This is a family, externally grounded, carrying some of the best-evidenced return-to-sport metrics there are:
**adductor:abductor** and the adductor squeeze (groin injury in field sport, HAGOS), **shoulder ER:IR** ratio
(overhead athlete / rotator cuff, isokinetic literature), **plantarflexion** strength. Four hits from one log
is what makes it structural, not anecdotal.

**Live impact:** the user's ER:IR ≈ 6.25 : 11.25 = **0.56** against a ~0.66–0.75 reference — a quantified,
flagged deficit he is actively fortifying, and the platform currently has no axis to represent it.
`capability_state` is already per-region-per-side, so ratio reads are natively supported once the vocabulary
exists — the schema is ready, the vocabulary is not.

**State:** OPEN — the v1 taxonomy bump is its own design pass: externally grounded (HAGOS / adductor
squeeze; ER:IR isokinetic references; return-to-sport LSI), with adductor:abductor and ER:IR as first-class
reads. NOT a bolt-on from a tag file (the taxonomy is external-authority so its breadth does not inherit the
user's blind spots — #76). No blocker — the external references are named and nothing gates starting it.
Unblocks the interim no-pattern verdicts on the four families above.

---

## Q28. `Pullover` is not a constraint-neutral probe subject — the resolver probe passes by luck

`backend/probe_resolver.py` `_RESOLVER_PROBE` labels its subjects "out-of-history AND constraint-neutral",
which is what stops an injury refusal from silently suppressing the resolver measurement (the whole reason
B3 swapped the subjects off BSS / single-leg RDL). `Calf Raise` and `Preacher Curl` hold. **`Pullover` does
not.**

**How you know:** the live container run (2026-07-15, 494-row catalogue, real model) opened with the model
flagging it unprompted — *"Pullovers involve shoulder movement… You've got an active shoulder injury with a
flag on horizontal adduction and overhead work. Pullovers can load the shoulder in a similar pattern."* It
proceeded after confirmation, so the probe still reached its subject and reported `[OK]`. That is the
problem: **the probe currently passes for a reason it does not state**, and it will stop passing if the
shoulder flag tightens or the model gets more conservative — a false-green waiting on someone else's
check-in (FEEDBACK §11).

**The fix is one line, but the candidate set is narrower than it looks.** A replacement must satisfy BOTH
constraints simultaneously, and the two suggested in passing each fail one:
- **Reverse Fly** — fails *out-of-history*. `Rear Delt Reverse Fly (Cable)` / `(Dumbbell)` / `Single Arm
  Rear Delt Cable Fly` are all in the user's 28-day window (they appear in the 2026-07-15 ID-keyed audit's
  ADJUDICATED NO-PATTERN list), so the model has ids for them and would never emit a title — the probe would
  measure nothing and, post-`5c5b43f`, correctly fail loudly. [Certain — from the audit output]
- **Cable Crossover** — likely fails *constraint-neutral*: horizontal adduction is the exact pattern the
  shoulder flag names. [Reasoning, not measured]

**Simplest resolution — probably no replacement at all:** drop `Pullover` and keep `Calf Raise` +
`Preacher Curl`. Both are prod-confirmed to force a guessed title and return genuine candidates, and two
subjects already exercise the ratio tier (`Preacher Curl` → `Rope Cable Curl` 0.643 / `Drag Curl` 0.636).
The third subject adds coverage, not capability.

**State:** OPEN — the resolution is already identified (drop `Pullover`, keep `Calf Raise` +
`Preacher Curl`); deferred to the next harness-open, not a branch. Test-instrument only; no production code
path is involved. No blocker. Ref: live probe run 2026-07-15; DECISIONS_LOG #83/#84; FEEDBACK §11.

---

## Q29. Historical HRV phantom-stale row reconciliation (`samsung_hrv_readings`)

Spawned by Q17's resolution on **(A)** (→ #89). Pre-fix `samsung_hrv_readings` HRV rows are
phantom-stale — each carries a *prior render's* value, not the night's, because the scraper's
`findById(...).firstOrNull()` bound a Compose recycling duplicate (HCA #19). The pre-install baseline
≈57 ms is an artifact, so any downstream trend / readiness / protocol attribution built on the 57→96
"rebound" rests on bad rows.

**Why no reconciliation runs yet — the changepoint is an APK-install event, not a commit.** The fix was
authored 26 Jun (unmerged `fix/scraper-sh-relayout`) and reached HCA master 11 Jul; the data step is
~6 Jul; HCA Q3 (RESOLVED) records a stale APK (`a5d1643`) still emitting the phantom `106` on 11 Jul. So
no single commit or merge date partitions the series — phantom-era and valid-era rows interleave by
*which build was installed when*. **Prerequisite: segment the series by APK-install history first.**
Reconciling against an unsegmented series bakes the error in permanently.

Distinct from **Q18** (out-of-range bounds sweep — those rows are wrong-*magnitude*; these are
stale-but-plausible) and from **Q17** (now resolved). The RHR discriminator is likewise contaminated:
`last_shr`/`sleep_hr_bpm` was phantom-affected too (fixed in the same HCA commit — see `BRANCHES.md`
`feat/recovery-metrics-rhr`), so Health Connect `resting_heart_rate` (`health_connect_syncs`) is the
only clean independent path.

**State:** OPEN — blocker: the series must be segmented by APK-install history first (the changepoint
is an install event, not a commit). Owner: Luke. **Do NOT reconcile, backfill, or delete a
single `samsung_hrv_readings` row until segmented.** Cross-refs Q17, Q18, issue #9, HCA #19 / Q3.

---

## Q30. Neither repo has a `.gitattributes` — `core.autocrlf` decides bytes per-machine

`health-app` and `health-connect-app` both lack `.gitattributes`, so with `core.autocrlf=true` the
line endings of a working-tree checkout are decided per-machine rather than by the repo. Measured
during the #91 sweep: the CLAUDE.md shared block is `i/lf w/lf` in health-app but `i/lf w/crlf` in
health-connect-app — identical in the index (the thing that propagates), 151 CR bytes apart in the
working tree.

**Why it matters beyond cosmetics:** any cross-repo verification that reads the *working tree* will
keep producing false divergence, and the G1 byte-identity guarantee becomes machine-dependent unless
every check is made through git. A raw `md5sum` of the two working trees says "diverged" while the
committed content is identical — the exact false verdict #91's gate had to be redefined to avoid.

**Action (named, not taken today):** add `* text=auto eol=lf` as `.gitattributes` in both repos.
Deliberately NOT done in the #91 brief: it changes working-tree checkouts on the next checkout in
both repos — a behavioural change beyond a governance brief's bounds.

**State:** OPEN — blocker-free, action named above. Owner: Luke.

---

## Q31. `DECISIONS_LOG.md`'s trailing Known-issues table is a fourth vocabulary — and may duplicate `OPEN_QUESTIONS`

`DECISIONS_LOG.md` carries a trailing "Known open issues" table whose Status column uses
`Open` / `Fixed` / `Tech-debt` — a fourth vocabulary, outside #88's stated scope
(`BRANCHES.md` / `OPEN_QUESTIONS.md` / `ROADMAP.md` / close-outs) and therefore untouched by both the
#90 and #91 sweeps. Whether it should adopt the four states, or is legitimately a different artifact
class (as `OPEN_QUESTIONS` was argued to be, then overturned by #91), is undecided.

**Second, independent defect — recorded, not investigated:** those rows resemble `OPEN_QUESTIONS`
content in kind. If the same issue is tracked in both files, that is a duplication defect independent
of vocabulary — two stores that can disagree about the same fact. Verify whether the sets overlap
before deciding either question; a vocabulary sweep over a duplicated store would entrench the
duplication rather than expose it.

**State:** OPEN — no blocker. Owner: Luke.

---

## Q32. The `/closeout` ritual definitions have diverged between repos — 77 vs 132 lines

`health-app/.claude/commands/closeout.md` is **77 lines**; `health-connect-app`'s is **132**. Both
define the same ritual, and both were carrying the struck `purpose / why-parked / unblocks-on`
column set (HCA Q9 item 2). health-app's copy is fixed at #92; **HCA's still teaches the dead
dialect**, and a ritual definition that does so re-emits it every session — the drift regenerates
itself rather than merely persisting.

Two undecided questions, deliberately left open rather than answered unilaterally (sweeping another
repo's ritual definition is out of this brief's scope, and doing it unbidden is not Code's call):

1. **Does HCA's copy need the same strike?** Almost certainly yes — HCA Q9 records it as the higher
   priority of its two items.
2. **Is the 77-vs-132 divergence intentional?** The shared loop-rules block is propagated verbatim
   and fingerprint-gated; the ritual definition is neither. If the ritual is meant to be shared, it
   needs the same treatment (markers + a parity gate). If it is meant to be per-repo — HCA's is a
   different app with different close-out needs — that should be *stated*, so the divergence stops
   reading as drift. Right now nothing distinguishes "intentionally different" from "quietly
   drifted", which is the same ambiguity the vocabulary sweeps existed to remove.

**State:** OPEN — no blocker; both questions are answerable at will. Owner: Luke.

---

## Q33. The shared loop-rules block still says `parked` — the definition outlasted every sweep

`CLAUDE.md:128` (health-app) and `CLAUDE.md:116` (health-connect-app) carry the same sentence:

> `branch with `+` commits vs `origin/master` must be pushed, parked in `BRANCHES.md`,`

This is a **generator instruction**, not narration — it tells the next session what to call a branch,
so it re-emits the struck vocabulary every time it is read. It survives the frame-vs-narration filter
that correctly exempts `retired` (prose) and the OAuth `parks the request` (different word-sense).

Knowingly deferred at #93, not missed. Two reasons, both structural:

1. It sits inside the **verbatim-propagated shared block**, fingerprint-gated at
   `4243c91ce78e0331ddfa5178aa3006b8` / 155 lines / 10232 B. Editing it from a health-app-rooted
   session re-breaches G1 — the exact obligation #92 discharged.
2. Under the paired-obligation protocol (#92), a shared-block edit creates a **pair**: the editing
   session records it OWED, the return session discharges it. It therefore needs its own brief and a
   mirror-first plan, not a drive-by fix at the end of an unrelated sweep.

The two repos are **identical** on this line, so nothing has diverged — the deferral is safe, not
merely tolerable. What is *not* safe is leaving it untracked: after #93 both rituals say `rowed`
while the document that defines the vocabulary says `parked`.

**State:** OPEN — no blocker; needs a shared-block brief with a mirror-first plan and a G1
re-fingerprint on both sides. Owner: Luke.

---

## Q35. The over-collapse guard is unit-only and cannot see same-unit semantic collapse

`backend/routers/labs.py:394` refuses a write when a raw label maps to a canonical whose
`unit_established` disagrees with the incoming `unit_canonical`. That catches a collapse where two
markers differ *dimensionally* — mapping something in `g/L` onto a canonical established in `mmol/L`.

It cannot catch a collapse where both markers share a unit. `glucose_fasting` and `glucose_random` are
the live example, canonical as of v0.3: both `mmol/L`, both plausibly labelled "Glucose" by a lab that
varies its wording. If a raw label were ever mapped to the wrong one of the pair, every value would be
dimensionally valid, the guard would stay silent, and the two series would merge into one — the exact
double-counting the COALESCE partition rule exists to prevent, arriving through the door the guard does
not watch. `hba1c_ngsp` (%) and `hba1c_ifcc` (mmol/mol) are safe by contrast: different units, so the
guard does cover that pair.

Note the guard is also inert wherever `unit_established` is null (`egfr`, `haemolysis_index`,
`haematocrit`, `chol_hdl_ratio`) — by design, but it means the null-unit markers have no protection of
either kind.

The fork: is a semantic-collapse guard worth building (e.g. asserting that a raw label maps to exactly
one canonical across the whole map, plus a same-unit sibling registry), or is exact-match on
`marker_name_raw` considered sufficient defence given the labels are verbatim from the report? The
`Saturation` entry is the argument for the former — it is a bare generic label, safe only because no
other panel has yet printed that word.

**State:** OPEN — no blocker. Owner: Luke.

---

### ▸ Interpretation 4b package — Q36–Q41

_These six forks travel together: they are the open questions blocking the interpretation-layer build (4b), and their single ROADMAP home is the **Interpretation layer build** NOW row (they do not each get a roadmap row). Kept as distinct entries — each carries separate content — but grouped here so the package is legible. Q35 above is related but **not** in the package: it carries no `Due 4b` tag and none of the six cross-reference it._

## Q36. `discriminator` field semantics are inverted between two authored relations

Both authored `discriminator` relations use the field to mean the opposite thing:

- **`ggt_hepatobiliary_discriminator`** — `discriminator: "ggt"` is the **evidence marker**;
  `operands: ["ast", "alt"]` are the markers being explained.
- **`bilirubin_isolation`** — `discriminator: "bilirubin_total"` is the **marker being explained**;
  `operands: ["ggt", "alp", "haemolysis_index", "ld"]` are the evidence.

Both are authored, both read coherently in prose, and 4b's renderer will need exactly one meaning.

**#96 took a side, which is why this is now urgent rather than tidy.**
`haemoconcentration_discriminator` follows the `ggt` reading — `discriminator: "albumin"` is the
evidence, `operands` are the red cell markers being explained. That makes it **2-to-1** for
evidence-in-`discriminator`. A renderer built on the `bilirubin_isolation` reading would render the new
relation **backwards**: it would announce albumin as the thing being explained by a red cell rise,
inverting the artefact-vs-expansion call that is the relation's entire purpose. That is the concrete
cost of leaving the ambiguity open, and it should be settled by decision rather than discovered at 4b.

**Secondary, and unresolved by picking a side:** `discriminator` is a single string, but
`haemoconcentration_discriminator` genuinely has **two** evidence markers — `albumin` *and*
`protein_total`. Only `albumin` fits the field. `protein_total` survives in the `reads` prose and in
`plasma_volume_status.target_markers`, i.e. nowhere a renderer can reach it. Should `discriminator`
become a list?

**State:** OPEN — no blocker. Due **4b**, with Q34 (`safety_threshold`), Q37 (I1 enforcement),
D3 and PV1. Owner: Luke.

---

## Q37. Does `gates.py` carry citation payload into the output? — I1's extension has no enforcement

#95 extended invariant I1 from levers to read-constants: any `marker_interpretation` constant that
influences a gate requires non-empty `evidence_refs`, or it falls back to `_defaults`. **Nothing
enforces this, and there is one live violation.**

`backend/interpretation/gates.py:39-53` falls back only when the entry is absent or its `value` is
`None`. It explicitly projects `evidence_refs` away, the docstring stating they "are asset citation
payload and are NOT part of a delta". Under extended I1, `alt` — `value: 0.45`, `evidence_refs: []`,
note "citation pending — CVi source not yet pinned to a DOI" — must fall back to `_defaults` (0.30).
It does not; it uses 0.45 today.

So canon and code disagree **by design**, each documenting the opposite intent. The fork: does
`gates.py` start reading citation payload to decide fallback — making `evidence_refs` load-bearing at
runtime rather than documentation — or does I1's extension get narrowed to something the producer can
honour without inspecting citations?

**This is the parent question to #96's withholding.** The `haematocrit`/`haemoglobin` read-constants
and `plasma_volume_status` were held back precisely because I1 forbids uncited constants. If I1's
extension is narrowed rather than enforced, that withholding was stricter than the invariant actually
requires — and if it is enforced, `alt` must move at the same time.

Recorded here because it lived only in #95's body and this file is what gets actioned; an obligation
in an append-only entry has nothing pointing at it. Flagged at #95's close-out and again before #96's
merge, unminted both times.

**State:** OPEN — no blocker. Due **4b**, with Q34, Q36, D3 and PV1. Owner: Luke.

---

## Q38. `min_meaningful_delta` has no interval awareness, but RCV is interval-dependent by construction

Thirup 2003 gives **~12%** for haematocrit between successive values 1 day to 1–2 months apart, and
**~15%** for intervals up to 6 months — the widening coming from warm-weather haemodilution, with the
population mean running ~3% lower in summer. Same marker, same paper, two different answers keyed to
the gap between draws.

`min_meaningful_delta` holds **one scalar**. So whichever value lands is wrong for roughly half of a
real draw series, and this repo's series are months apart and cross seasons — the condition that
selects the wider figure is the normal case here, not the edge case. #99 landed **0.12**, the tighter
of the two, deliberately: it produces false positives (news that is really seasonal drift) rather than
false negatives (a real change called noise), which is the safer direction to be wrong in for a marker
whose failure mode is erythrocytosis.

Options: interval-banded constants; a widening factor derived from `collected_at` deltas; or accept
the tighter value and absorb the seasonal false positives, annotating them. The third is the status
quo by default rather than by decision, which is the thing to fix.

**Update at #101 — the interval-dependence now has a citable basis, not chat's assertion.** Coşkun et
al. sampled **weekly over 10 weeks** and state this is **less than one erythrocyte turnover period
(~4 months)**, offering that as the reason erythrocyte CVI came out lower than for other parameters.
So the four constants landed at #101 are valid for roughly the interval this repo's recent draws span
(~10–12 weeks) and **understate variation beyond it**; Thirup's ~15% at 6 months is the widened
figure. The two sources are not in conflict — they measure different intervals, which is the whole
point of the question.

Note this reverses the direction of the concern as originally written. Q38 was minted against #99's
0.12, worrying it was *over*-sensitive for long intervals. At #101's 0.08 the constant is tighter
still, so the same argument now bites harder: the shortfall at long intervals is larger, not smaller.

**Convention, settled at #101 and recorded here because this is where a reader reasoning about
constants will look:** constants are derived **two-sided, Z = 1.96**, because the delta gate is
direction-agnostic. EFLM's calculator defaults to one-sided (Z 1.64); the one-sided statistic belongs
with `safety_threshold` (Q34), which is directional. Not an open fork — stated so it is not
re-derived differently next time.

**State:** OPEN — no blocker. Due **4b**, with Q34 (`safety_threshold`), Q36, Q37, Q39 and Q40.
Owner: Luke.

---

## Q39. Levers have no `effect_locus` — `plasma_volume_status` moves the reading, not the biology

Every lever authored before #100 changes the underlying physiology: a TRT dose really does raise
testosterone, alcohol really does raise GGT. `plasma_volume_status` does not. It leaves red cell mass
untouched and changes the denominator — which is *precisely why* the Dill & Costill derivation works,
since that equation depends on circulating red cell mass being constant across the two draws.

Surfacing it un-flagged means a UI offering "hydration" and "TRT dose" as comparable handles on
haematocrit. They are not comparable: one changes what the number *is*, the other changes what the
number *measures*. Acting on the second as though it were the first means chasing an artefact.

`channel` cannot carry this. It encodes **how the actor acts** — `pharmacologic` | `behavioural` — and
`plasma_volume_status` is genuinely behavioural on that axis. Adding a third value would conflate two
orthogonal dimensions in one field, and #100 explicitly declined to do so.

Proposal: an `effect_locus` field, `physiology` | `measurement`, defaulting to `physiology` so every
existing lever is correct without edit. The renderer can then refuse to rank a measurement-locus lever
alongside physiology-locus ones, or label it distinctly.

**State:** OPEN — no blocker. Due **4b**. Owner: Luke.

---

## Q40. RCV is asymmetrical for a rise and a fall, but `min_meaningful_delta` holds one scalar

EFLM's calculator and **Fokkema** (Clin Chem 2006;52:1602–3) give **different RCVs for a rise and for a
fall** — the log-normal distribution of most analytes means a 30% increase and a 30% decrease are not
equally improbable. `min_meaningful_delta` holds **one value**, applied to `abs()` of the change.

Symmetric and asymmetric forms **converge below roughly 5–10% CV**, so all four erythroid constants
landed at #101 are unaffected — CVI runs 0.72–2.82% across them. **`oestradiol` is not**: at 0.42 from
CVI ≈14%, it sits well inside the divergent region, so the single scalar is meaningfully wrong in one
direction. Which direction, and by how much, is the thing to determine.

This interacts with Q34 rather than duplicating it. `safety_threshold` is directional *by design* — it
asks "is this dangerous now", which has a side. The delta gate is direction-agnostic by design. So the
asymmetry question is whether a direction-agnostic gate can honestly use a statistic that isn't, or
whether the asymmetric form forces `min_meaningful_delta` to become a pair.

**State:** OPEN — no blocker. Due **4b**, with Q34, Q36, Q37, Q38 and Q39. Owner: Luke.

---

## Q41. `safety_thresholds.json` citation capture for haematocrit — the last thing before the band

The mechanism landed at #104/#105/#106 and is fully tested. ~~**The asset has no live entries**, so
`safety_gate` returns `no_asset` for every marker and the 0.50–0.54 band is still dark.~~
**Corrected #139:** the three haematocrit bands are now live in `thresholds`, each on its own
`evidence_refs`; `safety_gate` returns a band for haematocrit and `no_asset` only for markers still
uncovered. The quoted sentence describes the pre-#139 state and is preserved struck, not deleted.

Bands identified but **uncited**: **0.50** from cohort definitions, **0.52** from AUA / Endocrine
Society guidance, **0.54** from Canadian guidance. Also uncited: the two positions that make
`contested: true` honest — that cutoffs across guidelines appear arbitrarily chosen, and that the
evidence for benefit of intervention is thin in *both* directions.

None has a verified DOI. Under I1 as extended at #95, landing them would be exactly the failure #99
refused for `haemoglobin`: a citation pointing at a source that does not state the number, which makes
an unsupported value look supported. So `_deferred.haematocrit` held the shape and nothing was live
**until #139**, which promoted the three bands into `thresholds` with per-band citations.

**This is the last item between the repo and the clinical concern that opened the erythroid fork.**
Everything else on the 4b list — Q36 (discriminator semantics), Q37 (I1 enforcement), Q38
(interval-banding), Q39 (`effect_locus`), Q40 (asymmetrical RCV) — is correctness. This one is
coverage: until it lands, a haematocrit of 0.52 produces no safety signal at all.

Note the contested flag is not a hedge to be resolved away. If the cutoffs really are arbitrary, that
belongs in the output next to the band, which is why `contested` and `contested_note` are asset fields
rather than commentary.

**State:** DONE → #139. Resolved by #139 — three haematocrit bands promoted from `_deferred` to
`thresholds`, each carrying its own `evidence_refs` (0.50 monitoring ceiling; 0.52 observed risk
inflection, first-year scope recorded; 0.54 intervention threshold). Gate 3 fires for haematocrit;
gate 1's safety arm is reachable. Asset and test only — no gate or producer logic changed. Owner: Luke.
## Q42. The 12-hour-clock scrape failure in `parseSleepTimingContentDesc` is silent and cross-cutting — owned by `health-connect-app`

`HRVDataModel.parseSleepTimingContentDesc` captures `(\d+:\d+)` from a Samsung content-desc, and
`parseClockToMinutes` accepts it without a meridiem. If the phone clock is ever set to 12-hour, `10:12 pm`
is stored as `10:12` — a 12-hour error that reads as a valid time. It is silent, and it affects **every**
consumer of `bedtime`/`wake_time`, not just CBT-I (surfaced while designing the CBT-I diary prefill,
which now sanity-gates prefills against the prescribed window as a local defence — brief Step 6).

This is a scraper defect in the companion app's store, not health-app's. Raised here so it is not lost;
the fix and its canonical question belong in `health-connect-app`'s `OPEN_QUESTIONS`, not this repo.

**State:** OPEN — no blocker. Owner: Luke. **Next action:** carry to `health-connect-app`'s
`OPEN_QUESTIONS` (cross-repo; not editable from a health-app-rooted session).

**Re-scoped (2026-07-25, backlog triage — Step 5 stale check):** the 4h prefill sanity-gate shipped in
health-app (#117's safety catch) catches the *symptom* at prefill — a 12-hour-format value more than 4h
from the prescription is rejected rather than prefilled. It does **not** fix the source parse, which lives
in `health-connect-app` (`parseSleepTimingContentDesc` / `parseClockToMinutes`, absent from this repo,
verified) and is unverifiable from a health-app-rooted session. Scope is now explicit: **the gate covers
prefill only; the source mis-parse is still open and belongs to HCA.** So the question stays live, not
closed by tonight's gate.

---

## Q45. The VA CBT-I diary does not say which day a recorded nap belongs to — so the engine excludes nap nights rather than attributing them

`daily_records.naps_min` is silent when wrong. The titration engine reads naps for the night
terminating on wake-date W from `date = W-1`, which is only correct if the instrument's nap item refers
to the day *preceding* the recorded night. **The instrument does not say.**

**This search was run, and it was scoped.** Every text cell across all five sheets of the VA CBT-I
Sleep Diary Calculator export was matched against both a nap pattern and a temporal pattern
(`yesterday|today|last night|previous day|during the day|...`). Every nap reference is bare:
`Naps (minutes)`, `Naps`, `Biological Need for Sleep (TST + Naps)`. The FAQ mentions naps only for the
TST24 definition and for scheduled-nap timing advice — neither states which day a diary row's nap
covers.

**Positive control — this is what makes it a scoped null and not a failed search.** The temporal
pattern *did* fire elsewhere in the same workbook, on `"Did you eat before bed? How long before bed?"`.
The detector demonstrably finds temporal qualifiers in this instrument and found none attached to the
nap item. Per #110 clause 1, that is the difference between "the wording does not settle it" and
"nobody looked". **Do not re-run this search.**

**Resolution, adopted:** the engine **excludes nap-flagged nights entirely**, recording them in
`cbti_prescriptions.excluded_nights` with reason `nap`, rather than attributing them to a date. Two of
the imported block's 53 nights carry naps, so exclusion costs almost nothing while a wrong attribution
is silent. This is the standing behaviour until the question is answered, not a placeholder.

**State:** OPEN — no blocker; the engine's exclusion path is the interim answer. Owner: Luke.
**Next action to close it:** establish the nap item's referent from the VA CBT-I protocol
documentation or by asking the clinician who administered the block — not from the workbook, which has
already been searched to exhaustion.

---

_Gate summary (2026-06-22, on-device, SM-S921B): GATE 1 PASS → DECISIONS_LOG #20.
GATE 2 PASS (deep slivers survive the HC write at 30s resolution; deep is heavily
fragmented — ~26 of 30 deep segments are <3 min slivers). GATE 3 INCONCLUSIVE → Q3 (superseded
`#173` / `Q81`; principle `#71`)._

## Q46. No column records whether a prescription's `basis_tst` came from device or diary — only its adherence source

The `cbti_prescriptions` basis-source columns (`basis_n_samsung` / `basis_n_diary`, migration
`c4e8a2019bd7`) record the **adherence** source of each basis night — whether bedtime was checked
against Samsung or against the diary's own `lights_out`. They do **not** record whether `basis_tst_min`
itself was computed from device `actual_sleep_time_minutes` or from diary TST. These are different axes.

Surfaced opening block 3. Its opening prescription (block id=2, rx id=10) is **device-derived**:
`basis_n_samsung=27`, `basis_n_diary=0`, `basis_tst_min=349` computed from Samsung
`actual_sleep_time_minutes` over 2026-06-23..2026-07-23 — stated only in the prescription's `rationale`
text. Block 2's basis was diary-derived. A later reader comparing the two blocks' bases cannot tell the
two provenances apart from structured columns, and a device basis and a diary basis are not equivalent.

**State:** OPEN — no blocker; the interim is the rationale text on rx id=10. Owner: Luke. **No
column added mid-block** — block 3 is open, an additive nullable migration is safe, but a new provenance
axis is a design choice not a hotfix. **Next action to close it:** decide whether `basis_tst` provenance
warrants its own column (`device|diary|mixed`) or the rationale text suffices, before block 4 opens.

---

## Q47. The adherence gate prefers Samsung `bedtime`, whose detection lag can flip a night against a ±30 tolerance

`cbti/engine.py:230-235` establishes adherence from `samsung_bedtime` **in preference to** diary
`lights_out` where a `passive_overnight` row exists (`elif night.lights_out` is the fallback). Samsung's
`bedtime` is a **detected** onset; it lags the actual lights-out ("tried to sleep") by a measured ~10
min. The adherence tolerance (`ADHERENCE_TOL_MIN`) is ±30. A systematic 10-min lag is a third of the
band — enough to flip a borderline night between adherent and non-adherent, which changes whether it
counts toward a titration cycle (`ADHERENCE_FAIL_N` = 3 of 7 → HOLD). The diary `lights_out` and the
device `bedtime` are not the same instant, and the gate treats the preferred one interchangeably with
the prescription's lights-out.

**State:** DONE → #127. Resolved by choosing the third option — prefer diary `lights_out` for adherence —
but ON PRINCIPLE (recall-only), not by calibrating an offset: the `samsung_bedtime` arm is removed from
`classify_night`, so the detection lag can no longer flip a night. S4 (this session) tried to measure the
sensor−diary lag over 2026-06-08..2026-07-26 and found only n=2 nights with both a diary `lights_out` and a
`passive_overnight` bedtime (block 3 had just opened; mean +3.5 min) — too thin to characterize, which is
itself why the export's own `bedtime_detection_delay` (p50 14, n=211), not an in-app join, is the lag
source, and why adherence should not depend on the sensor at all.

---
## Q48. What is the settling period between prescription changes, and does it lengthen as TST approaches need?

The titration engine adjudicates each cycle on the trailing `CYCLE_NIGHTS`, so a move made soon after a
change is judged partly on nights run under the superseded window. A minimum settling period was proposed
as a gate and **not built** (#124): the parameter is undeterminable from both available sources — the SRT
literature has never studied titration interval as a variable (its named failure mode is *under*-titration),
and block 2 is confounded (an exclusion removed 29 of 53 nights, suppressed sleep in the window estimate,
a lumbar investigation spanning it). The physiological term is sleep-efficiency recovery after an
extension, which is state-dependent (fast at large deficit, slow near sleep need) — so a *lengthening*
settling time is itself a plateau signal, and this parameter and the exit criterion should be derived from
**one curve**, not guessed separately.

`nights_since_effective_from` is now recorded on every cycle verdict (#124) as the instrument. **Block 3 is
the dataset** and carries what block 2 lacked: waking cause, nap capture, alcohol, adherence against a
*recorded* prescription, an ISI baseline, a CPAP mask-off cross-check — and **no concurrent orthopaedic
investigation**. By-product from block 2's ledger, recorded but not evidence: nine prescriptions ran for
`[3,7,5,6,6,6,7,7,6]` nights (range 3–7, median 6).

**State:** OPEN — no blocker; the instrument exists and block 3 is accumulating the observations.
Owner: Luke. Sibling to the `MIN_VALID_NIGHTS` undeterminability recorded at #114/#115 — the same "cannot
be estimated from the one confounded block" about a different constant. **Next action:** once block 3 has
post-extension cycles, fit the SE-recovery curve; if it supports a threshold, #124's "do not revisit
unless" is met and this becomes a gate proposal with data behind it.

---
## Q49. The replay regenerates the prescription chain from row zero instead of reading the effective prescription per cycle — a mid-block operator correction is invisible to it, and reads as an adherence failure

`cbti/replay.py` seeds the initial lights-out from `rxs[0][1]` (the earliest prescription) and then
regenerates the chain by the engine's own titration logic; it never reads `cbti_prescriptions` for the
prescription in force in a later cycle, and it takes the wake anchor from `cbti_blocks.wake_anchor` (the
block's OPENING state, replay.py:174), not the effective prescription's. So block 3's operator correction
(#126: id=11, 22:30/05:00 from 2026-07-27, superseding id=10's 23:45/05:45) is invisible to a replay —
not just the anchor, the whole change. Concretely: cycle 1 spans 24–30 Jul (`CYCLE_NIGHTS`=7) and the
correction lands on night 4; a replay differences all seven nights against the seeded 23:45, so the four
nights actually run at 22:30 read ~75 min early, and with `ADHERENCE_FAIL_N`=3 the cycle FALSE-HOLDS on
GATE 2 adherence — the exact failure mode the V1 basis-boundary check was asked to rule out. It does not
bite today only because nothing auto-evaluates (`evaluate_cycle` is called only by `replay.py`, manually).

This is the general defect behind the anchor divergence #126 accepts: computation and ledger are divorced,
so they can disagree only quietly, and nothing records which of the two produced a given verdict.

**State:** DONE → #128. `replay.py` reworked to read the effective prescription per cycle from
`cbti_prescriptions` (window, lights-out, AND wake anchor); cycles anchor to each prescription's
`effective_from` and never span a boundary, so a mid-cycle correction is adjudicated against, not
false-held. Verified read-only against prod block 1 (9 cycles, one per ledger prescription) and block 3
(id=10 stub vs the id=11 correction). New `test_cbti_replay.py` pins the regression; suite 412. The live
evaluation trigger (#118) must reuse this same read (the shared "≥7 nights since effective_from" model).

---

## Q50. Where do the four operating rules live — project instructions or CLAUDE.md?

The 15 Jul calf investigation produced four rules that are not yet homed anywhere enforceable:

- **no hypothesis before the manifest**
- **inline source-of-claim tags** (per claim, naming the artefact it leans on)
- **artefact ≠ source** (a record-artefact is not the thing it describes)
- **a gate is a subtraction** (a constraint removes an exposure; log its cost at issue)

These are the `prevention` values of ledger rows 5, 6, 8, 10 and 15 (`FEEDBACK.md` §19.6, DECISIONS_LOG #129–#132).
The ledger records that the failures happened and what would have prevented them; it does not *enforce* the
rules. Enforcement needs a home that loads before the analysis starts.

**The fork.** Chat's position (schema proposal §6) is **project instructions** — permanent, enforced every chat,
model-uneditable, porting the existing EPISTEMIC DISCIPLINE block (which already holds the parent rule) into the
health lane where it was never applied. The alternative is **CLAUDE.md**, which reaches Code sessions but not
chat — and these failures happened in chat, not Code. A third option is both, which re-creates the two-master
drift the loop model exists to kill unless one is unambiguously the master.

**Why it is not decided here:** project instructions are a UI surface, not a repo write — Code cannot write them,
so this cannot be closed by the ledger's own commit. It is also the item the schema proposal flagged as bearing
on cross-repo propagation: if the rules land in CLAUDE.md they hit the shared verbatim block and propagate to
`health-connect-app`; if they land in project instructions they do not.

**State:** OPEN — blocking nothing in the repo; blocks the rules being enforced anywhere. Decide the surface
before writing them, not after.

---

## Q51. `BRANCHES.md`'s header describes a convention its own rows contradict

The header reads:

> `# BRANCHES — every branch not master lives here until merged+deleted`

"Until merged+deleted" says a row leaves once its branch lands. **The file does not do this.** 14 rows are
retained with a `**LANDED <date>**` status (`fix/probe-harness-fidelity`, `feat/hevy-resolver-activation`,
`chore/markitdown-mcp`, …), and the landing commits say so explicitly — `gov(branches):
fix/probe-harness-fidelity LANDED at adb67e8`. Practice is retain-and-mark; the header says delete.

**Practice is almost certainly the correct half.** Retained rows carry the `Unblocks on` column, which holds
owed operator loops that outlive the merge — e.g. `feat/hevy-resolver-activation`'s "loop closes on Luke,
post-merge + deploy: exercise the live path", and `chore/markitdown-mcp`'s parked Desktop registration.
Deleting a row on land would destroy the record of what is still owed *because* it landed. The header is
stale prose; the rows are the convention.

**Why this is logged and not patched.** It is a repo defect with a live cost — it already produced one
failure. `FEEDBACK.md` §19 row 16 records Code reading this header instead of the rows it governs and
writing a false instruction (`"Owed on land: delete this row"`) into `BRANCHES.md` at `17ffe60`, corrected
at `554e448`. That is row 8's class — an artefact read as the thing it describes — and the artefact here is
a canonical store's own header. Row 16 records the misread; this question records the thing misread. They
are the two halves of one `COUPLED` failure and neither is complete alone.

**The fork:** (a) rewrite the header to match practice — "every branch not master lives here until landed;
landed rows are retained and marked `LANDED`" — accepting that the file is an append-only branch history,
not a live-branch inventory; or (b) rewrite the practice to match the header, deleting landed rows and
relocating owed operator loops somewhere that survives. (a) is cheap and preserves the `Unblocks on`
record; (b) costs a new home for owed loops and would discard 14 rows of history.

**State:** OPEN — not Code's call to silently rewrite a header that 14 rows and the close-out
terminal-state gate depend on. Blocks nothing; misleads every reader until decided, including the next
model to read it.

---

---

## Q52. Three parallel readers of the `type='injury'` ledger — consolidate or leave?

Three functions independently query `UserKnowledgeEntry` for `type='injury', active=True`, each normalising
to its own shape:

| Reader | Returns | Used by |
|--------|---------|---------|
| `engine/selection.py:263` `gather_active_injuries` | `{body_part, side, signal_type, ra_flare, restrictions, raw}` | contraindication / selection |
| `routers/checkin_v2.py:74` `derive_soreness_items` | `{soreness_key: 1}` via `injury_soreness_key` | AM check-in `/prefill` |
| `injury_trajectory.py:146` `evaluate` | divergence / review messages | `get_readiness_snapshot` |

**Why it's open, not decided:** an implementation brief asserted a "one reader" rule citing FEEDBACK §10 and
directed `derive_soreness_items` through `gather_active_injuries`. Both halves were wrong and the instruction
was retracted: §10 is *False-green instruments*, not a reader rule, and no single-reader rule exists in
FEEDBACK anywhere. The refactor would also not have achieved its stated goal — `selection.py` and
`injury_trajectory.py` would have remained parallel paths regardless. So the question is genuinely undecided,
not merely unimplemented.

**The real trade-off:** three readers means three places to change when the ledger shape moves, and three
chances to drift. But `gather_active_injuries` normalises AWAY the fields the other two need (it drops
`trajectory`; the soreness key would have to be recovered through its `raw` passthrough), so consolidation is
not free — it either widens that return shape until it's a union of three concerns, or it establishes a raw
reader beneath three projections. Neither is obviously right at this scale.

**Not yet examined:** whether the three have already drifted (e.g. `gather_active_injuries` defaults
`signal_type` to `"mechanical"` while the others don't default it at all) — that drift, if real, is the
argument for consolidating, and nobody has looked.

**State:** OPEN — no decision, own concern, own branch when taken. Ref: DECISIONS_LOG #134; the retracted
citation is recorded here so the refactor is not re-proposed on the same false basis.

---

## Q53. `backend/gate_test.py` — land as an instrument, or delete?

Untracked in the working tree: an ad-hoc script that reads a real lab PDF from `~/OneDrive/Documents/Medical/`,
sends it to the **paid Anthropic API** via `routers.labs.EXTRACTION_SYSTEM_PROMPT`, and asserts on the extracted
Bilirubin row (`ref_high == 21.0`, `ref_high_exclusive`, `computed_flag == 'H'`, `flag_agreement`).

**Why it needs a decision rather than a silent leave-alone:** this is the second time this session an ad-hoc
probe that spends credits has turned up loose in the tree. The first was the resolver harness — it got landed
properly as a first-class instrument under DECISIONS_LOG #84 (operator-run, CI-excluded, key presence-checked,
never materialised into output). This one has had none of that adjudication. "Left it alone" is how a loose
instrument stays loose forever: untracked means it is invisible to review, absent from any suite, and one
`git clean` from gone.

**The two options:**
- **Land it** as a peer of `probe_resolver.py` under the #84 pattern — versioned, CI-excluded, key-presence-only,
  and with the hardcoded personal-medical path parameterised (it currently embeds an absolute path to a real
  lab report, which is why it cannot land as-is).
- **Delete it** — it was scaffolding for the labs extraction work and its assertions may already be carried by
  `tests/test_labs_reads.py`. Nobody has checked whether they are.

**State:** OPEN — NOT touched on `feat/checkin-injury-probe` (unrelated concern; the file stays untracked and
uncommitted). Ref: DECISIONS_LOG #84 for the precedent pattern; FEEDBACK §11.

---

---

## Q54. The interpretation view (increment 1/5) renders against a superseded contract — its fixture lacks the `ungrouped[]` the #86 producer emits

`frontend/src/fixtures/interpretationExample.json` has top-level keys `['groups', 'meta']`, but master's
#86 producer (`backend/interpretation/producer.py`, `build_foundation`) emits `{meta, groups[],
ungrouped[]}`. The view (increment 1/5, DECISIONS_LOG #135) is fixture-driven and ships **INERT** — it
renders the committed fixture, not the live producer — so nothing ships broken. But the increment that
wires the view to the live producer MUST (a) regenerate `interpretationExample.json` from current
`build_foundation` output and (b) add an `ungrouped` render section; wiring it against the current fixture
would silently DROP every ungrouped marker.

**State:** OPEN — no blocker; the view is inert (fixture-driven), so this is owed work, not a live
defect. **Next action** (at increment 2+, when the `context_builder` AI pointer is swapped to the live
producer): regenerate the fixture from `build_foundation` output and add an `ungrouped[]` render section.
Owner: Luke.

---

## Q55. Four CBT-I gate constants are chosen, not derived — no data or literature grounding

`NAP_EXCLUDE_MIN` (0), `TRAINING_RECOVERY_MIN` (90), `ADHERENCE_TOL_MIN` (30) and `ADHERENCE_FAIL_N` (3)
in `cbti/engine.py` are operating values set by choice — not estimated from data and not traced to a CBT-I
literature source. They are NOT block-2-derived (that block is discarded for outcome claims); they are
simply the numbers the gates were built with:

| Constant | Value | Gate | Basis on record |
|----------|-------|------|-----------------|
| `NAP_EXCLUDE_MIN` | 0 | any nap-flagged night excluded | Q45 policy choice (exclude, not attribute); the *threshold* 0 (vs >20) is chosen |
| `TRAINING_RECOVERY_MIN` | 90 | constrained-night floor = session end + 90 | chosen recovery margin; no source |
| `ADHERENCE_TOL_MIN` | 30 | ± tolerance, bedtime vs prescription | chosen; ±30 is conventional but uncited here |
| `ADHERENCE_FAIL_N` | 3 | ≥ N failures of 7 → HOLD | chosen; 3-of-7 is conventional but uncited here |

Same shape as Q27's reference-band gap and the constants already flagged undeterminable in code
(`MIN_VALID_NIGHTS`, `MAX_MOVE_MIN`, `PLATEAU_TOL_MIN`): the value functions, but nothing on record says it
is *right*.

**State:** OPEN — NOT blocking; the gates function as built and every exclusion is recorded with a
reason, so a wrong constant shows up in the output rather than acting silently. **Next action:** ground each
against a named CBT-I source (SRT adherence tolerance, nap-inclusion convention) or a cross-block distribution
once more than one live block exists — do not tune against the single discarded block. Owner: Luke.

---

## CLOSED

_Resolved questions, moved here verbatim (backlog triage, #123). `DONE → #N` names the
deciding `DECISIONS_LOG` entry. Per #112 closed questions are not scanned for live work — they
sit below the fold so the live list above is the scan surface. Nothing is deleted; only moved._

---

## Q1. Backend HC stage-constant fix + historical backfill

`routers/health_connect.py` stage constants are confirmed wrong (DECISIONS_LOG #20):
`SLEEP_STAGE_DEEP=4`, `REM=5`, `LIGHT=2`. Correct to the official enum — `LIGHT=4`,
`DEEP=5`, `REM=6`, `AWAKE=1` — and add handling for stage 6 (currently dropped) so
REM is counted. Then decide whether to **backfill** the corrupted `health_connect_syncs`
rows or let them age out: the HC path looks dormant (latest row 2026-06-21, all written
in a single backfill at 2026-06-21 19:04Z; live sleep stages currently come from the
scraper). Also re-verify the HC `sleep_score` derivation and the `_section_health_connect`
AI-prompt block, which both consume the mislabelled values.

**State:** DONE → #20. Fix deployed to Railway (PR #2) and all 31 HC rows
re-synced from device on 2026-06-22 (30-day backfill, range 05-22→06-21). Verified
against Railway Postgres: `light_sleep_minutes` now populated (was 0 on every row),
deep/REM no longer swapped, slivers no longer truncated; corrected values track the
scraper. Surfaced a new date-attribution bug — see Q4.

---

## Q2. Companion `validateNight` returns overlapping/duplicate SleepSession records

`validateNight()` for last night returned `sleepRecords: 4` with the per-stage `durMin`
arrays clearly doubled (totals ≈2× the real night: stage-5 deep 69→~34.5, stage-6 rem
134→67). `runDeepConfidence`/`flagDeepSegments` currently `flatMap` all sessions and will
double-count. Must de-duplicate before `trustedDeepMin` is meaningful — e.g. pick the
longest session per night (as `health_connect.py:_aggregate_day` does), or union by time
range. Until then `runDeepConfidence` output is not trustworthy.

**State:** DONE — fixed in `health-connect-app` `36df9a2` (confirmed patch-present
on HCA master): `collapseSleepSessions()` de-duplicates the overlapping SleepSession
records before downstream consumers, behaviorally verified 9/9.

---

## Q8. Event-spine schema fork

Adopt `health_events` + `user_health_state` as the canonical spine, OR keep the organic
schema (`aerobic_sessions`, `daily_records`, `daily_check_ins`, `samsung_hrv_readings`)
with `user_health_state` as an overlay view on top? Design-stage; not in master. Blocks
the `user_health_state` build and the Decision Support layer.

Resolution: overlay adopted; `user_health_state` is a compute-on-read `current_state`
read model over existing stores, not a `health_events` spine. `health_events` deferred
and narrowed to an additive projection scoped to the medical timeline; call timed to the
lab pipeline.

**State:** DONE → #43

---

## Q11. Lab store — where per-marker observed results live

Fork: `lab_result` typed table vs `user_knowledge_entries type="lab"` vs `health_events`.
Blocked the #49 build, the #48 write path, and lever-dictionary wiring alike.

**State:** DONE → #52 (`lab_report` + `lab_result` table pair).

---

## Q12. Per-marker minimum meaningful delta

Where the #49 delta-gate threshold lives; global vs per-marker.

**State:** DONE → #53 (per-marker `min_meaningful_delta`, in-repo #51-family reference asset).

---

## Q14. Hevy create-loop id contract

Does `POST /v1/exercise_templates` return the canonical string id (UUID/hex) or a bare
integer (the spec example shows an int)? This decides the create loop's shape:
create→single-row-upsert (if the create response carries the canonical id) vs
create→list-back (if it does not). Resolve empirically: one throwaway live create + a
list-match against `get_exercise_templates`. **How-you-know** artifact required before
any build.

**State:** DONE → #65 — the live OpenAPI spec types the `POST
/v1/exercise_templates` response as `{"id": <integer>}`, distinct from the canonical
string UUID `GET` returns; the create loop adopts create→list-back (create → sync →
resolve within the custom subset), so the POST-response representation never gates the
build. The deferred micro-opt (skip the re-pull if the POST is later confirmed to carry
the canonical UUID) is out of scope.

---

## Q16. `hevy.py` `get_exercise_history` path

The connector calls `/exercise_templates/{id}/history`; community docs show
`/exercise_history/{id}`. Verify against the live API and fix the connector path if it is
wrong.

**State:** DONE → #69. Path corrected to `/v1/exercise_history/{id}` (template id unchanged)
on `fix/hevy-exercise-history-path`; basis is official docs + 3 independent current clients.
Live corroboration remains optional belt-and-braces (local Hevy MCP hung this session).

---

## Q17. HRV step-change from 6 Jul — (A) instrumentation vs (B) physiology

`get_recovery_metrics(days=30)` surfaced a step (not ramp) in scraper HRV: pre-6-Jul (13 Jun–4 Jul,
22 nights) mean ≈57 ms, range 24–88, high variance; post-6-Jul (7 nights) mean ≈96 ms, range 83–117,
variance collapsed. No row exists for 5 Jul — the discontinuity sits in that gap. The 57 ms pre-period
mean matches the established operative baseline exactly, so old data was valid and the break is new.
Two hypotheses, possibly both true: **(A) instrumentation** — the phantom-node fix changed which node
the scraper binds, now reading a different metric (RMSSD→SDNN ≈ the observed 1.7× ratio); **(B)
physiology** — tirzepatide ceased 2+ weeks ago (~3 half-lives), GLP-1/GIP washout produces a genuine
HRV rebound, ~~corroborated by respiratory rate drifting ~14.0→~13.5 br/min over the same window via a
*different sensor path* (a scraper bug cannot move RR). The 68% rise exceeds published GLP-1 HRV
effects alone.~~ **[struck — resolved → #89 on (A): RR is NOT a different sensor path. It is
`vitality_respiratory_rate_average_title`, read from the same Vitality screen through the same
phantom-affected selector, fixed in the same HCA commit as HRV (`1db8833`/#19). The RR drift is a
*prediction* of (A); the "68% rise" is an artifact of stale reads, not a real rebound.]**

**Decision gate = Task 1 node dump** (branch `feat/hrv-node-dump` in **`health-connect-app`**, a
separate repo — not reachable from a health-app-rooted session). Dump the `HRVAccessibilityService`
node tree; identify the bound node's field/metric identity and whether a sibling node carries the
pre-6-Jul metric. Different node/metric → (A): correct the binding, then reconcile. Same node/metric →
(B): rebound is real. **Historical row reconciliation must NOT run until this gate resolves** —
reconciling against a moving metric definition bakes the error in permanently. Confirmatory input held
ready: `feat/recovery-metrics-rhr` (Task 2, RHR series in `get_recovery_metrics`) — but note the primary
`samsung_hrv_readings` RHR is the scraper's `sleep_hr_bpm`, same device family as HRV; the truly
independent discriminator is Health Connect `resting_heart_rate` (query `health_connect_syncs` directly).

**Resolution (→ #89 · 2026-07-19).** Closed on **(A) instrumentation**, verified against
`health-connect-app` master (`1db8833`/#19):
1. **(A) confirmed — mechanism is stale-phantom *selection*, not a metric change.** #19 routes all
   three Energy-score reads through `findByIdValidBounds` instead of `findById(...).firstOrNull()`; the
   phantom is a Compose view-recycling duplicate bearing the *prior* render's value with negative width,
   which `.firstOrNull()` returned. Same node, same metric (RMSSD) throughout — the scraper simply
   stopped binding the stale duplicate. (Authored 26 Jun on unmerged `fix/scraper-sh-relayout`; reached
   HCA master 11 Jul, renumbered #16→#19 — the gate's binary "different node→A / same node→B" missed
   this third case: same node, but the old reads were the phantom.)
2. **RMSSD→SDNN withdrawn as surplus.** The 1.7× ratio is coincidence. A stale prior-render value
   predicts the statistics directly — pre (mean 57, range 24–88, high variance) = scattered stale reads;
   post (mean 96, range 83–117, variance collapsed) = locked to on-screen truth — with no analyte change
   required.
3. **(B)'s corroborator is void — never independent.** RR shares the exact read path (see the struck
   clause above), so the 14.0→13.5 drift is a *prediction* of (A), not evidence against it.

(B) as *physiology* is **unevidenced, not disproven** — washout may still have moved HRV, but this
series cannot speak to it. The pre-install baseline ≈57 ms is not a baseline; trustworthy HRV history is
short, not long. **Historical rows are NOT reconciled here — see Q29** (install-history segmentation is
the prerequisite; the changepoint is an APK-install event, not a commit).

**State:** DONE → #89 (instrumentation limb; (A) confirmed vs HCA master). Cross-refs Q13, Q18,
Q29, issue #9, `BRANCHES.md` `feat/recovery-metrics-rhr`, HCA #19 / Q3.

---

## Q21. Does the lab-side expectation contract (#63 / SPEC_64) generalise to injury trajectories?

**State:** DONE (this session; no DECISIONS entry — logged conclusion only) — they **rhyme, they do not share code.** Both follow declare
expectation → surface divergence → never suppress (lab gate-2 "annotate, don't hide" ≡ injury "surface,
don't gate"). But the lab contract is bound to marker/delta semantics (`marker_groups.json`,
`min_meaningful_delta`, two-gate axis-verdicts) while injury trajectory is a soreness series vs a
declared shape (`injury_trajectory.py`). Kept as separate mechanisms deliberately — forcing a shared
abstraction over two things that merely share a shape is how you get a bad one. Logged per the
constraint-consumption brief; no further action unless a third expectation-gated surface appears and the
rhyme becomes a rule worth abstracting.

---

## Q25. (cross-repo, health-connect-app) Disposition of remote branch `claude/hevy-api-workout-query-teulc2`

Remote branch `claude/hevy-api-workout-query-teulc2` (`4dfccbe`) is on `origin` for **health-connect-app**,
unmerged, and is NOT in that repo's `BRANCHES.md` — whose own header states "every branch not master lives
here until merged+deleted." The store is violating its own rule. Needs a disposition: govern it (add to
BRANCHES.md) or kill it. Not this repo's / this brief's job — logged only.

**State:** DONE → #91 — the branch now carries a dedicated row in `health-connect-app`'s `BRANCHES.md`
(added at HCA `f15b545`, "row the unrowed branch"). This question asked whether the branch was **governed or
killed**; governing it discharges the question.

**Both limbs now closed (verified 2026-07-20, #93).** The disposition this entry left OWED in HCA's store has
since completed: the operator deleted the remote ref, HCA's row reads `DONE → discarded 2026-07-20`, and
`git ls-remote --heads origin claude/hevy-api-workout-query-teulc2` returns empty — verified from an
HCA read during the #93 session. Both the omission this question recorded and its subject are gone.
The row remains HCA's to hold; tracking it here too would be the duplication defect Q31 records.

---

## Q26. Taxonomy has no home for isolation / adductor-abductor work — G2 "zero fallback" vs benign empties

`Capability_Taxonomy_v0` is a movement-PATTERN + capacity vocabulary. A large share of the user's logged
work has no clean region: **Hip Adduction / Hip Abduction (Machine)** (frontal-hip strength — pes-anserine-
relevant, the injury the tagging brief itself cares about), knee isolations (leg extension / leg curl), and
arm/shoulder isolations (curls, raises, delt flies, triceps). These are left UNTAGGED in the v0 proposal —
the keyword fallback returns `[]` for all of them (benign: no wrong region, just a logged coverage-gap hit).
This puts G2 ("100% of active-window templates tagged, fallback hit-count 0") in tension with reality:
forcing a tag would pollute the region signal.

Three resolutions for Luke: (a) accept benign empties and redefine the coverage metric as "zero *wrong*
tags" rather than "zero fallback"; (b) add an accessory/no-pattern sentinel so isolations are "tagged" (bypass
the keyword path) but contribute no region — needs a mechanism, since region_key validates fail-closed
against the taxonomy; (c) extend the taxonomy (e.g. a frontal-hip adductor/abductor strength region) — a
`TAXONOMY_VERSION` bump. The adductor gap is the load-bearing one given the active pes anserine injury.

**State:** DONE → **DECISIONS_LOG #76**, option **(b)** with a correction. Not two states but THREE —
`tagged` / `adjudicated no-pattern` / `untagged` — via a `hevy_exercise_templates.adjudicated_at` timestamp,
NOT a sentinel region_key (which would weaken fail-closed validation). G2 stands UNSOFTENED (option (a) was
rejected: redefining coverage as "zero wrong tags" forfeits the ability to detect a real gap later). Option
(c) — the taxonomy bump — is deliberately NOT done inside a tag confirmation (the log must not shape the
screen); it is spun out to Q27 as a grounded v1 design pass. Interim: calf / shoulder ER-IR / Copenhagen /
hip add-abd are adjudicated no-pattern.

---

## Q34. Is `safety_threshold` a third class of read-constant, alongside delta and stable_rationale?

`lever_dictionary.marker_interpretation[*]` currently carries two kinds of authored constant:
`min_meaningful_delta` (is this change news?) and `stable_rationale` (is this persistent flag benign?).
Both answer *interpretive* questions — they shape how a reading is narrated.

Neither answers a **safety** question: is this value dangerous *now*, regardless of whether it moved or
whether it is constitutionally normal for this person? Haematocrit on TRT is the live case that
prompted this — `trt_erythrocytosis_watch` (now `ready_to_promote` at #95) is a context relation, and
context is not a threshold. A rising-but-in-range Hct and an Hct at 0.54 are different claims, and only
the second is a safety statement.

The open fork: does `safety_threshold` belong as a third key on `marker_interpretation`, or is it a
distinct asset that should not share a home with interpretive constants — on the grounds that mixing a
"this is interesting" constant with a "this is dangerous" constant in one dict invites a producer bug
that treats them interchangeably?

Whatever the shape, extended I1 (#95) applies: a safety threshold with empty `evidence_refs` must not
gate anything. That is more load-bearing here than for a delta, because the failure direction is
asymmetric — an uncited delta produces a boring narration, an uncited safety threshold produces a
false reassurance or a false alarm.

**State:** DONE → #104 — `safety_threshold` is a third class, and a third *gate*, not a third
read-constant. It lives in its own asset (`backend/reference/safety_thresholds.json`) rather than in
`lever_dictionary.marker_interpretation`, because the two existing constants are **measured**
(CVI/CVA-derived, non-expiring) while a safety threshold is **policy** — committee judgement carrying a
`review_due`. `gates.safety_gate()` compares a level to it, and the mechanism is complete and tested.

**The asset is empty and that is the remaining work — tracked as Q41, not here.** The question asked
what shape the thing should take; that is answered. Whether haematocrit's bands can be cited is a
different question with a different owner.

---

## Q43. Does production share `FERNET_KEY` (and `SECRET_KEY`) with the local development `.env`?

`mcp_server.py:288` decrypts `api_key_encrypted` for stored third-party credentials, so a shared Fernet
key makes every stored credential recoverable by anyone holding the dev value. The question is only
whether the two environments hold the same key, not what either key is.

Resolve by comparing **SHA-256 digests** local vs Railway — digests only, never values, per #110's
second clause. If they match, rotation is not a variable swap: every `api_key_encrypted` row was
encrypted under the old key and must be re-encrypted, so the fix carries a data migration.

**State:** DONE → #111. **Both keys are prod-isolated — the digests differ on both.** No shared key,
therefore no re-encryption migration over `api_key_encrypted` and no prod rotation on this account.

**Method, which matters as much as the outcome.** A single script run under
`railway run --service health-app-backend` held both sides at once: Railway's values arrived as
injected `os.environ`, the dev values were parsed from `backend/.env` on disk, and each was reduced to
`sha256(value)[:12]` *inside* the comparison. No value was printed, logged, or returned, and the
digests themselves are deliberately not recorded here — this repo is public and a digest of a live
secret is still identifying. The comparator carried both controls: identical input reported equal,
differing input reported unequal, so "differs" cannot be a broken comparison silently passing.

This entry supersedes an earlier assertion that the comparison had already been performed. It had been
reported in chat but never attested against an artefact — the third instance in this sequence of a
claim about an unreadable surface being carried as fact (see #110). The result happened to be correct;
the basis was not, until this run.

---

## Q44. `railway variables --kv` prints secret values into session transcripts — the fix is the command, not the operator

Established while settling #110's provenance question. Four of seven transcripts carry the Railway
Postgres credential **only** as `tool_result` output, never as operator input, and every one of those
originates from the same command shape:

```
railway variables --service <service> --kv
```

`--kv` returns name=value pairs, so any invocation persists live secrets into the transcript — and the
grep-for-a-name variants used alongside it (`| grep -i DATABASE_URL`) narrow the lines returned without
removing the values. This is #110 clause 2 as a live case rather than a retrospective one: the operator
did nothing wrong, the diagnostic did.

The credential-free substitute already exists and is proven on this machine: `railway run <cmd>` injects
`DATABASE_URL` into the child process without printing it (used for the phase-1 production reconcile).
For presence or equality checks, a digest comparison as in [[Q43]] — never `--kv`.

Open: whether to ban `--kv` outright in the loop rules or require it be piped through a masking filter;
and whether the seven existing transcripts are purged or retained after rotation, since they remain the
exposure surface once the credential is dead only if it is in fact dead.

**State:** DONE → #111. Resolved by a two-layer prohibition: the standing rule in `CLAUDE.md`'s
shared block (the enforcing layer) plus `.claude/settings.json` deny patterns (a speed bump, explicitly
not relied upon — see #111 for why).

**The rule is general, not vector-specific**, because the CLI's own `--help` showed the narrow reading
was wrong: `--kv` *and* `--json` both state they print raw values, the base command is `variable` with
`variables` as an alias, and `-k` is a short form — four bypasses of a `--kv`-only pattern. Since the
sanctioned substitute is `railway run` (a different command entirely, no flag dependency), the deny
patterns widened to the whole `railway variable(s)` family without blocking the replacement. Proven by
running the substitute after the deny list landed: 114 injected variables, names only, zero values.

**Residual — NOT immaterial, contrary to the initial framing, and verified rather than assumed.**
Presence-only search across 60 transcript files (positive control fired on a known-present string):
the dev `FERNET_KEY` appears in 2 files, `SECRET_KEY` in 2, and the `ANTHROPIC_API_KEY` value currently
in `backend/.env` in 1 file, 24 times. The local dev DB (`health-app.db`) is **not** fixtures — it holds
one `user_integrations` row, `provider='hevy'`, encrypted under that exposed dev Fernet key (the row was
never decrypted; only its existence was read). So a **local** rotation is owed: the Hevy credential
itself, then the dev `FERNET_KEY`, then re-encrypt or drop that row. Prod is unaffected (Q43).

**Still open, deliberately out of scope here:** whether the second Postgres digest seen across four
transcripts is a retired credential or a second live one — a cheap co-occurrence test, but a finding
rather than a fix. And whether the transcripts are purged or retained once the credentials in them are
dead.

---


## Q56. `precondition_phase` and `derive_phase` speak different vocabularies, so no `feedback` relation can be evaluated

`marker_groups.json` gates `hpg_gonadotropin_suppression` on `precondition_phase: "on_trt"`.
`declared_state.derive_phase` returns `steady | episodic | washout | stopped | re_entering | None`.
There is no mapping between them in either the assets or the code, and `on_trt` is not a value the
derivation can ever produce (verified by grep: `on_trt` appears in no non-test source file).

The consequence is not cosmetic. That relation is what distinguishes *expected* gonadotropin suppression
on TRT from suppression that is news — the single most load-bearing relation in the HPG group for this
user. Until it resolves, the relation is emitted as `unresolvable` (4b-i) and cannot demote anything.

Two shapes of fix, and they are not equivalent. The asset could adopt derived-phase vocabulary
(`steady` on the `trt` factor) — cheap, but it conflates "on a steady protocol" with "on *this*
protocol". Or the asset could carry an explicit precondition object naming a declared-factor key plus an
admissible phase set — more authoring, and it says what it means. A guessed mapping silently decides
whether LH/FSH suppression is expected or is news, which is the whole clinical content of that relation.

**State:** DONE → #143. Resolved by the **second** of the two shapes above — an explicit
precondition object, not derived-phase vocabulary adoption. `hpg_gonadotropin_suppression` now carries
`{ factor_key: "trt", admissible_phases: ["steady"], grade, rationale, evidence_refs, contested_note }`
(authored by Luke), and the producer resolves it against the declared-state phase map to
`satisfied` / `not_satisfied` / `unresolvable` (naming an absent factor). `admissible_phases` is
`["steady"]` only — `re_entering` is unreachable for a `protocol`-type factor. `on_trt` is gone from the
live relation and producer source. `expected_by_phase` is emitted with no authority; demotion of the
`feedback` arm stays held for 4b-ii. Owner: Luke.

## Q57. Levers carry no link to declared-state factors, so I3 filtering cannot be implemented

I3 requires filtered levers to be **shown with a reason**, never dropped. Filtering needs to know whether
a lever is already in play, which means joining a lever to the declared-state factor that represents it.
~~**That join does not exist.**~~ **Corrected #145:** the join now exists — each lever node carries
`declared_factor_keys` (struck-not-deleted per correct-don't-delete; the sentence described the
pre-resolution state).

Lever keys: `testosterone_substrate_load`, `aromatase_inhibition`, `aromatase_adiposity`, `alcohol`,
`exercise_muscle`, `plasma_volume_status`. Declared-state keys: `trt`, `tirzepatide`, `cbt_i`, `zinc`, …
Different namespaces. The lever node's fields are `label`, `mechanism_summary`, `grade`,
`grade_rationale`, `evidence_refs`, `actor`, `channel`, `draft_status` — **no mapping field**.
`testosterone_substrate_load` ↔ `trt` is obvious to a reader and unrepresented in data; `alcohol` has no
declared-state row at all.

Smallest fix: an authored `declared_factor_keys: []` on each lever node. Asset content, not code. The
filtering predicate then reads `is_assumable_present` on any matched factor — which is also what keeps an
episodic peptide from being treated as present at a draw it may not have been present for.

**State:** DONE → #145. Resolved as the body's own "smallest fix": `declared_factor_keys` authored on
all six lever nodes — only `testosterone_substrate_load` joined (to `["trt"]`), the other five `[]`
(a truthful "no declared factor represents this lever", distinguishable from the field being absent). No
declared-state entry was created for `alcohol`. The consumer — `shared_levers[]` already-in-play
filtering — is held for 4b-ii; the join lands before the consumer. Owner: Luke.

---

## Q58. The confirmation screen is read-only, which turns three separate defects into one design problem

Surfaced by the first real ingestion run. Three symptoms, one root cause — the confirm screen displays
extraction output and offers only Discard / Confirm, with no inputs. They are recorded as ONE row
because splitting them invites three partial fixes; the fix is one editable-confirm increment.

**A — read-only means a wrong value has no remedy but discard.** `Metrics.jsx`'s `STAGE.CONFIRM` renders
the report envelope and a results table (including a `Conf.` column) with two actions and no fields. A
reader who can see a value was extracted wrongly cannot correct it — the only recourse is discarding the
whole report and re-uploading. Per-field confidence is computed, displayed, and unactionable.

**B — `missingCollected` is a hard dead-end.** When extraction fails to find the collection date, Confirm
is disabled and the report cannot be saved; because the screen is read-only, the date cannot be typed in.
The user must discard and re-upload the same file hoping for a different extraction. Read-only design
producing an unrecoverable state on a plausible failure (scanned/photographed reports the likely trigger).

**C — provenance after an edit is undesigned.** `LabResult.confidence` currently describes the model's
certainty. If a human retypes a value, that number describes a guess that no longer exists: 1.0 erases the
distinction, leaving it untouched is false. *Human-checked* is a stronger, more useful claim than any
extraction confidence, and the query it enables — which values a person has actually verified against the
paper — needs its own field rather than being folded into `confidence`. This is the design call the
increment turns on: a column on `lab_results`, or a separate verification record.

**State:** OPEN — no blocker; nothing currently built depends on it. **Owner:** Luke — the design call
(provenance column vs verification record) comes first; a partial fix would set the schema by accident.
Deliberately not built this branch (the derived-confidence work makes the `Conf.` signal honest so this
increment has something trustworthy to highlight against).

---

## Q59. Nothing verifies the deployable artifact — no CI, and no check can observe "the application starts"

Surfaced by the 2026-07-28 deploy outage (an unpinned `mcp` resolved to a breaking major and the app
died at import while 460 tests passed). One gap with two faces; recorded as one row because they are
the same absence — nothing between "the suite passed in a session" and "Railway builds and deploys"
looks at the artifact that actually ships.

**A — there is no CI.** No `.github/workflows`, no pipeline config of any kind. The only gate between a
green session and a production deploy is a person, and every check the project relies on runs against a
developer venv that already has working dependencies installed — which is exactly why a clean-venv
resolution difference (the unpinned SDK) was invisible until Railway built from scratch.

**B — no check can observe that the application boots.** The failure was total: the process died at
import, before binding, and no test caught it because no test imports the app in a clean environment. A
boot check is not a one-liner: `main` imports `database`, which constructs an engine from
`DATABASE_URL`, so importing `main` needs environment to succeed at all. The check therefore needs
either a test harness with a throwaway env or a build-stage import in a deploy pipeline — and there is
no pipeline to put the latter in (finding A). That coupling is why the two are one question.

**State:** OPEN — no blocker; nothing built depends on it. **Owner:** Luke — design call on where a
boot check would live (test harness vs build stage) given there is no pipeline, and whether CI is worth
standing up for a single-developer project. Deliberately not built with the pin (production was down;
restoring service and designing a verification gate are different work).

---

## Q60. CBT-I has no user surface — the gating fork is #47 (verdict-as-directive), not display hygiene

The CBT-I titration engine is built (backend: `cbti/` engine + replay + block import + ISI;
#114/#115/#117/#118), but there is **no route, page, or nav link** — CBT-I is invisible to the user,
surfacing only as readiness-protocol modifiers and `_section_protocols` in chat context. Scoped in on
`feat/frontend-readback` (labs/check-in got interim surfaces there), deliberately not built blind: it
needs a design pass, and the first fork is regulatory, not cosmetic.

**Fork 1 — GATING — #47 education-not-clinical-advice: may the engine's VERDICT be surfaced at all?**
The engine's outputs are two different kinds of thing. *State* — the current prescription (window /
prescribed lights-out / anchor) and where you are in the cycle (days since `effective_from`, next-eval
gate) — is a factual read-back, the same class as the labs raw table. But the engine also produces a
**MOVE / REVERSE verdict** ("extend the window", "pull it back"): surfacing that as a directive is the
AI output layer issuing a **clinical instruction**, which is exactly the boundary #47 draws. So the fork
is: show *state only* (education-safe), or show the *verdict/action* (crosses into instruction and must
not ship without resolving #47 the way the interpretation lane resolves it for labs — #49). This is the
blocker; it is **not** cleared by clearing the firewall below. Recording it under I1 alone would let a
later session build the surface believing the regulatory question was settled when it was never asked.

**Fork 2 — diary capture: operator-script vs in-app.** The diary data the engine runs on is currently
loaded by **operator scripts** (`import_cbti_block.py`, `open_cbti_block3.py`). A user surface that only
*reads* state needs none of this; a surface that lets the user *log tonight's diary in-app* is a new
input path with its own design (and re-opens the nap-attribution question, Q45). Decide the surface's
scope — read-only vs capture — before its route.

**Constraint (not a fork) — I1 sensor firewall.** Whatever ships reads **recall-diary** columns only
(`diary_tst_min` / `diary_se_pct` / the prescription) and must **never** blend Samsung passive sleep
(`passive_sleep_min` / `passive_hrv_ms`) — a silent failure mode, enforced at the projection as the labs
read-back enforces #47. Real and hard, but display hygiene, not the gate.

**State:** OPEN — no blocker; the engine's outputs exist to read. **Owner:** Luke — resolve #47
(Fork 1) FIRST; it decides whether an interim surface is state-only or must wait on the regulatory call.
Scoped in (not "no interim surface until v2 titration") per the 2026-07-29 read-back triage. Numbered
`Q60` at the `feat/frontend-readback` merge.

---

## Q61. `GET /labs/results` omits `computed_flag`/`confidence` under a #47 bound that #47's text does not support — re-examine on its own merits

`routers/labs.py` `StoredResultOut` (~L292) projects the read-back to "the RAW education fields
only (#47)" and **deliberately omits** `computed_flag` and `confidence` (plus `is_derived` and
anything interpretive), recorded at build time as a `#47` bound with interpreted meaning deferred to
4b (#49). This question is about the **`#47` half of that justification for `computed_flag`** — read
against #47's actual text, it does not hold.

**Why the #47 bound is misapplied.** #47 (locked) bars connecting a lever to a *personalised
recommended action* — "given your dose, adjust X" is prescription; "levers that influence oestradiol"
and evidence-ranked lists are education; **comparison to the range printed on the user's own report is
education**. `computed_flag` is exactly that: it is our derivation of value-vs-normalised-reference-range
(`labs.py` extraction spec, L200 / L248-254 — `null` outside range handling and all), the *same class*
of information as `lab_flag`, **which this projection already returns** (L309). Reproducing an
in/out-of-range flag is not a personalised action, so #47 does not bound it out. The omission inherited
a #47 label that does not fit.

**Do NOT read "the #47 reason is wrong" as "therefore surface it."** There may be a separate and still
sound reason to keep both fields out of this surface; the point of this row is that the omission be
re-decided on *those* merits, not defended by a mislabel. Candidates to weigh:
- **#49 raw/interpreted seam.** This endpoint is deliberately the raw values/ranges/lab-flags surface;
  `computed_flag` is a *derived* read that arguably belongs to the interpreted 4b view (#49). Surfacing
  it here may blur the seam #49 draws — a coherence reason, distinct from #47.
- **`confidence` is extraction QA, not a clinical read** (the docstring's own words). A per-row
  extraction confidence shown at a glance can mislead — a genuinely different rationale from
  `computed_flag`'s, and one that may well stand. The two omitted fields should not be re-decided as a
  bundle.

**No code change this session** (verify-only; producer/endpoint build is frozen). Recorded so the
projection is re-examined on its own merits rather than inheriting "settled by #47."

**State:** OPEN — no blocker; the fields exist on the stored rows, the question is whether the
raw read-back should carry them and under what rationale. **Owner:** Luke — decide `computed_flag`
against the #49 seam (not #47) and `confidence` against the misleading-at-a-glance concern, separately.
Numbered `Q61` on the `gov/readback-riders` branch (pre-ff; max was Q60, no competing branch).

---

## Q62. How is `#47` enforced structurally for a generated field?

**State:** OPEN. **Blocks:** `axis_verdict.text`, and every future generated interpretation
field. **Related:** Q60 (the same question for a CBT-I titration verdict).

`#47` says enforcement is *"at the prompt layer **AND** structurally — no
interpretation-output field expresses a personalised action."* Every field the producer
emits today satisfies the structural half by construction: its content can only be what a
reviewed asset contains, or arithmetic over the user's own data. A **generated prose field
has no such bound.** Its only control is the prompt, which is the behavioural half alone.

This project has already rejected that trade once. `#59` made lab-value absence from the
standing chat prompt *structural* — values fetched on demand rather than present-but-
instructed-against — on the explicit reasoning that a "don't mention it" instruction over
data that is already present leaks under long context or clever prompting. A generated
`axis_verdict.text` reintroduces exactly that shape at the interpretation layer.

The question is not whether an axis verdict is inherently over the line. *"These three moved
together"* is description, and `#47` names explaining mechanisms as education. The question
is **what structural control replaces the one that generation removes.**

Candidates:

- **(a) Don't generate.** Bounded enum plus templated text assembled from asset fragments.
  Fully structural; least expressive. Cheapest if `verdict` proves derivable.
- **(b) Generate, then validate structurally.** A post-generation gate rejecting directive or
  prioritising constructs. Requires defining the reject set — and a reject set is itself a
  behavioural rule wearing a schema, so this needs care to be genuinely structural.
- **(c) Generate under prompt control only.** Matches `#47`'s prompt-layer half and abandons
  its structural half for this field. Weakest; recorded for completeness.
- **(d) Generate, then human-review before surfacing.** Reuses the existing
  `ai_draft` -> `human_verified` promotion gate already applied to `lever_dictionary.json` and
  `marker_groups.json`. Precedent exists in this repo; cost is a human in the loop per panel,
  which may not survive contact with a daily-use product.

**Resolve before:** any increment that emits generated prose. Not before 1a or delivery —
neither touches it.

Numbered `Q62` on the `feat/interp-producer-1a` branch (pre-ff; max was Q61, no competing branch).

---

## Q63. What does the interpretation tile show?

**State:** DONE → #162.

Resolved to candidate **(a)**, with one amendment: the shipped string reads `collected <date>`, not
`generated <date>`. `meta.generated_at` is stamped at request time, so it is always "now" and says
nothing about the draw; the "30 May" in (a)'s own example is the *collection* date in the fixture.
See the decision entry for the full reasoning.

A design question, not a regulatory one — under #150 Constraint A a tile may carry counts, deltas and
section structure. What it may not carry is a personalised priority ordering, which rules out the most
tempting phrasing ("2 things need your attention") but not the underlying counts.

Candidates:

- **(a) Structural counts** — "What Moved: 2 · Stable: 5 · last generated 30 May." Permitted,
  informative. A reader may still infer priority from the numbers, which is inference from their own
  data rather than the product ordering it for them.
- **(b) Existence only** — "Interpretation available, generated 30 May." Minimal.
- **(c) No tile** — reached from the Labs tile only. Removes the question.

**Why not decided here:** the producer's interpretive output shape is being settled in 4b-ii (1a landed
the deterministic asset fields; axis_verdict/mechanism remain held — Q62). Authoring tile content
before knowing what the producer emits is authoring against a guess.

**Resolve by:** the hub shell build, itself behind 4b-ii — so this resolves in that order without
blocking anything now.

Numbered `Q63` on the `gov/navigation-model` branch (pre-ff; max was Q62, no competing branch).

---

## Q64. Do marker-authored member fields belong on `ungrouped[]` rows? `vitamin_d_25oh` gets no explanation today

**State:** OPEN. **Blocks:** nothing — the producer follows a consistent rule today. **Related:**
`#138` (ungrouped markers render in their own section), `#152` (output shape), I9.

Two of the emitted member fields are **marker-authored**, not group-authored:
`stable_rationale` and `mechanism` both project from the flat
`lever_dictionary.marker_interpretation[marker]` slot and reference nothing about the group.
By the contract's own logic for `ungrouped[]` — member fields that do not depend on group
authorship may appear there — both **could** legitimately project onto ungrouped rows.

They do not. 1a scoped `stable_rationale` to grouped members, and the mechanism increment
followed that precedent rather than diverging silently. The consequence is concrete and
visible in the seeded fixture: **`vitamin_d_25oh` is a real panel marker, is ungrouped
(`marker_groups.json` authors no vitamin-D group), and therefore renders with no explanation
of what the marker is** — while an identically-authored explanation is shown for every grouped
marker. A reader will eventually ask why the lone marker is the one left unexplained.

Note the asymmetry is **not** uniform across the member fields, which is why this is a real
question rather than a tidy-up: `relations_rendered` and `member_lever_effects` are
group-derived and their absence from ungrouped rows is structural (no group, no relations, no
group_levers — by construction, not omission). Only the two marker-authored fields are
arguable.

Candidates:

- **(a) Project both onto ungrouped rows.** `vitamin_d_25oh` gains its mechanism; the flat slot
  already contains it for any canonical marker, so the producer change is small. Ungrouped rows
  become "a member row minus the group-derived fields", which is arguably what they already are.
- **(b) Keep grouped-only (status quo).** Ungrouped means minimally-rendered: value, gates,
  nothing interpretive. Defensible, and it keeps the ungrouped section visually distinct from
  What Moved — but it leaves the gap above.
- **(c) Project `mechanism` only, not `stable_rationale`.** A mechanism explains the marker
  and always applies; `stable_rationale` annotates a persistently-flagged marker that is not
  news, which is closer to a gate-adjacent judgement. Splits the two on what they actually do,
  at the cost of the flat-slot symmetry.

**Why not decided here:** the mechanism increment's job was plumbing an already-authored asset,
and widening the ungrouped projection changes what a whole section of the view renders — a
render-scope decision that belongs with the 1b delivery work, where the Ungrouped section is
being built anyway (it does not exist in the view yet).

**Resolve by:** the 1b view increment, which must add the Ungrouped section regardless — the
right moment to decide what a row in it carries. **Owner:** Luke.

Numbered `Q64` on the `feat/interp-mechanism-emit` branch (pre-ff; max was Q63, no competing branch).

---

## Q65. Four of the five relation kinds carry no machine-readable demotion condition — asset gap, or permanent boundary?

**State:** DONE → #154. **Was blocking:** any widening of #153's demotion predicate past `kind == "feedback"` — now permitted in principle but unbuilt; that widening lives in the branch-condition lane and `Q67` (its `co_movement` shape), not here.
**Related:** #153 (the predicate), #63 (`marker_groups.json` is "purely relational"), #141 (the
precondition object), I5/I8.

`feedback` is the only relation kind the producer can evaluate, because it alone carries a
machine-readable `precondition` (`factor_key` + `admissible_phases`). The other four —
`ratio`, `co_movement`, `discriminator`, `context` — carry a narrative `reads` string and
operand lists, and **nothing testable**: verified across all ten authored relations, no
`demotes` / `demotes_when` / `condition` / `predicate` field exists on any of them.

This matters because the most *intuitive* demotions all live in the four narrative kinds.
`ggt_hepatobiliary_discriminator` (normal GGT, so the transaminase rise is not hepatobiliary)
and `haemoconcentration_discriminator` (a red cell rise with albumin rising is a draw artefact)
both read like textbook demotions — and the producer cannot act on either, because nothing tells
it to compare GGT to its range or to check whether albumin moved. Acting anyway would emit an
explanation never checked.

Two futures, and they are genuinely different:

- **(a) Extend the asset with a declared demotion condition per relation** — e.g.
  `demotes_when: {operand: "ggt", state: "in_range"}` or
  `{co_operand: "albumin", direction: "same"}`. Demotion stays declared-in-asset and evaluated
  generically in code, the same split `precondition` already uses successfully. **The real
  question this branch tests is whether #63's "purely relational" asset can carry a predicate
  without becoming code.** A `demotes_when` vocabulary rich enough for the discriminator cases
  starts to look like a small expression language, and #63 drew the asset/code line specifically
  to keep judgement out of the producer. If the vocabulary stays small and declarative this is
  the better future; if it grows conditionals, the asset has become code wearing JSON.
- **(b) Accept that demotion is a `feedback`-kind capability by definition.** The other four
  kinds exist to *explain on the member line* — they already render their `reads` narrative to
  the reader — but never to change what surfaces. Defensible on a clean principle: only a
  relation whose applicability is resolvable from declared state should be able to silence news;
  the rest inform the reader who is looking rather than deciding whether they look. Costs nothing
  to adopt (it is the status quo) but permanently forecloses the GGT and albumin demotions above.

**Why not decided here:** #153 needed a predicate the data actually supports, and both branches
are compatible with the one it names — (a) supersedes its clause 2 later, (b) freezes it.
Choosing requires drafting a candidate `demotes_when` for the two discriminator cases and seeing
whether it stays declarative, which is design work, not a read.

**Second affected party — `axis_verdict`'s authoring table, not just demotion.** The same asset
gap forces that table to key on **evaluability** (which relations rendered, `operand_status` per
relation, and `precondition_status` for `hpg_gonadotropin_suppression` alone) rather than on
whether a relation *held* — a ratio has no threshold and a discriminator has no predicate, so
"held" is not computable. If branch (a) lands a declared `demotes_when`, the table could key on
truth instead, and its authored strings would be **superseded rather than extended**. Recorded
here so Q65 is not resolved on demotion's merits alone by a session that does not notice it
invalidated the verdict content.

**Resolution (#154).** Resolved toward branch (a), in a stronger form than this entry framed:
relations gain a declared machine-readable condition decomposed into an **eliminative branch
set** (`excluded` / `not_excluded` / `not_assessed`), not a single `demotes_when` predicate — so
partial exclusion becomes reportable information rather than a binary. #154 also **corrects this
entry's assumption that condition shape follows from relation kind**: it does not
(`haemoconcentration_discriminator` is declared `discriminator` but carries a co-movement
condition), so shape is authored per relation. #153's demotion predicate is unchanged until that
asset work lands. **Owner:** Luke.

Numbered `Q65` on the `feat/interp-demotion` branch (pre-ff; max was Q64, no competing branch).

---

## Q66. `LabResult` has no supersede affordance, so a corrected result cannot be marked as replacing an earlier one

**State:** OPEN. **Blocks:** nothing today; live from the next lab upload onward.
**Related:** `#156` (confirm-time duplicate detection), `#155` (retain-raw), `#52` (compute-on-read).

`#156` offers `skip` and `keep_both` on a marker collision and deliberately does not offer
`supersede`, because the only available implementation would delete the earlier row — contradicting
`#155`'s ratification that every observed analyte is retained. See `#156` for that reasoning; it is
not restated here.

The gap that leaves: pathology reports do issue corrected results, and for those the second value
at a collection date is the correct one. Today the only handling is `keep_both` plus manual
follow-up, after which the series carries two values for one draw with nothing recording which
supersedes which. `marker_series` orders `collected_date DESC, id DESC`, so the later-inserted row
wins **by insertion order rather than by any declared correctness**. That is right for a correction
and wrong for an accidental re-upload, and the two are indistinguishable after the fact — `#156`
established that nothing stored distinguishes them.

**Verified:** `LabResult` carries no supersede-capable column. Its 17 columns are `id`,
`lab_report_id`, `marker_name_raw`, `marker_canonical`, `is_derived`, `value_num`,
`value_operator`, `value_qualitative`, `unit_canonical`, `ref_low`, `ref_high`,
`ref_low_exclusive`, `ref_high_exclusive`, `lab_flag`, `computed_flag`, `confidence`,
`created_at` — nothing named for supersession, replacement, voiding or correction. The nearest
things are `id` and `created_at`, and both encode **insertion order**, which is precisely what this
question objects to being load-bearing. So the answer is not "narrow the question to whether an
existing field should carry it"; there is no such field.

Candidates:
- **(a) `superseded_at` / `superseded_by` on `LabResult`**, with `marker_series` filtering superseded
  rows. Retains the row, consistent with `#155`; declares the relationship explicitly; smallest
  schema change that closes it.
- **(b) Correction as a distinct ingest path** rather than a collision outcome — the operator marks
  an upload as a correction and every row in it supersedes its counterpart. Fewer per-marker
  decisions; requires knowing at upload time.
- **(c) Accept `keep_both` permanently** and let insertion order decide. Cheapest, and it makes the
  series silently order-dependent — the class of failure `#156` exists to prevent.

**Resolve before:** a correction is actually ingested, or before `marker_series` is relied on for a
marker where a correction is known to exist. **Owner:** Luke.

Numbered `Q66` on the `gov/two-open-questions` branch (pre-ff; max was Q65, no competing branch).

---

## Q67. `hpg_substrate_co_movement` is phase-conditional, and no `#154` condition shape expresses it

**State:** OPEN. **Blocks:** the relation branch-condition lane's `co_movement` shape work.
**Related:** `#154`.

**Pointer entry — the case is already named in `#154`, so this is work-tracking, not discovery.**
`#154`'s do-not-revisit clause ends: *"(`hpg_substrate_co_movement` is the near miss: decomposable,
but only under shape composition.)"* The analysis is there and is not restated here. What `#154`
does not carry — because a do-not-revisit clause is a supersession trigger, not a work item, and a
reader scanning for open work would not find it there — is the candidate set and the point at which
it must be resolved. That is what this entry adds.

**The clause does not FIRE on this case, and that is deliberate.** It triggers on a `reads` string
that cannot be decomposed into branch fragments. This one decomposes cleanly — co-moved and
diverged fragments are both statable. What fails is expressing its *condition* in the fixed shape
vocabulary. Expressibility, not decomposability. So the case is recorded but is not, and should not
be, a supersession trigger for `#154`.

**Verified:** `hpg_substrate_co_movement` carries `{relation_key, kind, operands, render_on, reads}`
and **no `precondition`** today; `hpg_gonadotropin_suppression` remains the only relation with one.
Its `reads` is *"On stable dosing these track the substrate pool together; divergence is the
signal."*

**Candidate (a) is a PRODUCER change, not a schema change.** `marker_groups.json` has no `_schema`
block, so nothing forbids authoring a `precondition` on a `co_movement` relation — but
`_relations_rendered` calls `_resolve_precondition` only when `kind == "feedback"` and hardcodes
`precondition_status: "not_applicable"` otherwise, so an authored precondition would be silently
inert. Representable in the asset, ignored by the code.

Candidates:
- **(a) Shapes compose** — any shape may carry an optional precondition, making
  `feedback_precondition` a modifier rather than a fourth peer shape. Most expressive; weakens
  "kind implies shape" further, which the live asset already falsified once via
  `haemoconcentration_discriminator` (`#154`).
- **(b) The relation is authored wrong and should be split** — an unconditional co-movement plus a
  separate phase-conditional reading. Keeps the vocabulary flat, at the cost of two relations where
  the physiology is one.
- **(c) Drop the phase clause from the condition** and leave it in prose, so the relation renders
  unconditionally and the reader carries the caveat. Cheapest; reintroduces exactly the
  reader-does-the-branch-work problem `#154` exists to remove.

**Resolve before:** the lane authors any `co_movement` shape — candidate (a) changes that shape's
schema for all four co-movement relations. **Owner:** Luke.

Numbered `Q67` on the `gov/two-open-questions` branch (pre-ff; max was Q66, no competing branch).

---

## Q68. A full-collision re-upload creates an empty `LabReport` envelope, and nothing decides whether it should

**State:** OPEN. **Blocks:** nothing today — the empty envelope is now visible as a fault, so this
is a correctness-of-model question, not a live defect. **Related:** `#155`, `#156`, `#157`.
**Numbering collision — read this before filing the cross-date operand question.** The brief that
produced this entry refers to "Q68's cross-date operand question" as though it exists; it is not in
this file and never was. Number-at-merge claims the next sequential integer at the instant of merge,
the repo max was Q67, so THIS entry is Q68. The cross-date operand question is still pending in chat
and takes the next free number when it lands.

**The fork.** `#155` ratifies retain-raw: the report row is created because the document genuinely
exists. `#156` keys duplicate detection at the marker level and explicitly adds **no report-level
key**. Together these mean a re-upload whose every marker collides produces a `lab_reports` row
with zero `lab_results` — ten such rows exist in production today. Neither entry decided whether
that is the *intended* outcome or an unexamined consequence of two independently correct choices.

**Why it is not obvious either way.** Retaining it is defensible: the document was uploaded, the
upload is an event, and `#155`'s whole argument is that discarding raw provenance is the mistake.
Discarding it is also defensible: the envelope carries no data, no `source_doc_filename` in some
cases, and duplicates provenance already held on the report that owns the rows — it is a record
that someone uploaded a file twice, which is operator behaviour rather than health data.

**What would settle it** is report-level identity (`Document ID` / `Lab ID`, currently uncaptured),
which is the same dependency `#157`'s do-not-revisit clause names. With it, the question stops
being "keep or discard the empty envelope" and becomes "recognise the document before writing
anything" — at which point the envelope is never created and the fork dissolves. **This is a
trigger, not a blocker:** the schema change is possible now, it is simply not yet worth doing.

**Do not resolve by deleting the existing ten rows** — that is a separate operator decision under
`#155`, and answering a design question by mutating the evidence for it is the wrong order.

## Q69. `marker_series` has no temporal bound, so the interpretation output is a composite of draws rather than a reading of one

**State:** DONE → #159. **Blocks (until the wiring bar is met):** wiring the interpretation view to live data (1b).
**Related:** `#155` (retain-raw), `#154` (eliminative branch model), `#147` (many panels per draw),
`Q65` (four relation kinds carry no machine-readable condition), `Q68` (empty envelope),
`Q66` (supersede affordance).

`marker_series` partitions on `COALESCE(marker_canonical, marker_name_raw)`, orders
`LabReport.collected_date DESC, LabResult.id DESC`, and takes `rn <= 2`. **Its only filter is
`LabReport.user_id`** — quoted from `backend/reads/labs_reads.py:131-156`, not from a report of it.
There is no bound on how old either row may be, and no requirement that the markers in one output
share a collection date. What the interpretation output presents as a panel is a **synthetic
composite of each marker's most recent value, whenever that was.**

**Measured against live data by running `marker_series(1, db)` itself**, newest draw `2026-05-30`:

| current `collected_date` | markers | age vs the newest draw |
|---|---|---|
| 2026-05-30 | 27 | — |
| 2026-04-20 | 1 | 40 days |
| 2026-03-06 | 30 | 85 days |
| 2025-12-27 | 7 | 154 days |
| 2025-05-16 | 1 | 379 days |

**39 of 66 markers carry a current value from a draw other than the newest one.** The composite is
the majority of the output, not an edge.

- **The hepatocellular group is absent from the 2026-05-30 draw entirely — confirmed.** Every
  member (`ast`, `alt`, `ggt`, `alp`, `bilirubin_total`) has current `2026-03-06` against prior
  `2025-12-27`. The whole group renders off an 85-day-old draw with a 69-day-old comparison,
  presented alongside erythroid data from `2026-05-30` as though contemporaneous.
- **`min_meaningful_delta` carries no time dimension — confirmed.** Across all 8 authored entries
  and the `_defaults` fallback the keys are exactly `{mode, value, note, evidence_refs}`; no key
  matching day/window/period/elapsed/interval exists anywhere in `lever_dictionary.json`, and
  `delta()` emits no elapsed field. The consequence is live *inside a single group*: in `hpg_axis`,
  `testosterone_total` moves over **40 days** (2026-05-30 vs 2026-04-20) while `oestradiol` moves
  over **154 days** (2026-05-30 vs 2025-12-27), and gate 1's delta arm judges both with the same
  bare percentage. `hpg_t_e2_ratio` then relates the two.

**Two claims from the drafting inventory did NOT survive verification, and the entry is weaker and
truer without them.**

1. **Albumin is not an operand of `haemoconcentration_discriminator`.** The relation carries a
   separate `"discriminator": "albumin"` field alongside `"operands": ["haemoglobin",
   "haematocrit", "rbc"]`, and **no code anywhere reads the `discriminator` key**. Albumin's age
   therefore cannot affect `operand_status`, because albumin is not consulted at all. That the
   relation asserts "this rise is a draw artefact" without ever looking at albumin is real, is
   already documented at `backend/interpretation/gates.py:351-353`, and is already **`Q65`** —
   a different question from this one.
2. **No relation today has operands from different draws.** Running the real operand check across
   all ten authored relations, every one resolves `operand_status: complete` with an operand date
   spread of **0 days**. The cross-draw-operand hazard is **latent, not observed**: nothing bounds
   it, and it arms the moment a group's members split across draws — which the hepatocellular
   group already demonstrates is the normal shape of this dataset. Stating it as latent is the
   honest form; claiming a current instance would have been false.

The question is not whether newest-per-marker is wrong. It is a reasonable answer to "what does the
platform know about this person." It is the wrong answer to "what does this panel say," and the
interpretation output presents itself as the second.

Candidates:

- **(a) Recency-bounded operands.** A value older than a declared window resolves `not_assessed`
  rather than counting as present. Smallest change; requires a window declared per marker or
  globally, and any global number is arbitrary across markers with very different half-lives.
- **(b) Draw-scoped interpretation.** The unit is a collection episode; markers absent from it are
  absent. Truest to what a reader expects from a panel, and it makes the temporal question
  disappear rather than parameterising it. On this dataset it would drop the entire hepatocellular
  group from a 2026-05-30 reading — 39 of 66 markers would fall out — which is either the correct
  answer or a fatal objection depending on which question the output is meant to answer.
- **(c) Surface the age.** **Cheaper than the draft assumed: the dates are already in the output.**
  The producer emits `groups[].members[].current.collected`, `.prior.collected`,
  `meta.trigger_panel.collected` and `meta.compared_against.collected`, and `LabRow` has carried
  `collected_date` since the read layer was built. A consumer can already compute every staleness
  figure in the table above. (c) is therefore **not a producer change at all** — it is the view
  choosing to display what it is already being handed. **Composes with the others rather than
  competing.**
- **(d) Hybrid.** Draw-scoped for gates and relations; newest-per-marker for trend display. The
  two readings answer different questions, and conflating them is what produced this.

`#154`'s eliminative model can express the result of any of these: a stale operand is a
`not_assessed` branch with a stated reason, and "this reading is from twelve weeks earlier" is
exactly the evidence its rule 3 exists to surface. So this question decides an input rule, not an
output shape.

**Episode identity, if (b) or (d) wins:** inferring a collection episode from `collected_date` is a
heuristic that breaks when two draws land on one date. The source documents carry a per-draw
accession — `Lab ID` — and the position is better than "uncaptured": **it is already extracted and
then discarded.** `ReportPatient.lab_accession` is parsed by `/labs/extract` and populated by the
system prompt, but `confirm_lab_report` never reads `report.patient` and `LabReport` has no column
for it, so it is dropped at the write. Persisting it is a schema change, not an extraction problem.
**Coverage is UNVERIFIED and must not be assumed:** no source PDFs exist in the repo, so whether
pre-2026 reports carry the accession in the same position could not be checked here. If the older
layouts differ, episode identity has a coverage gap over exactly the back-catalogue this dataset is
built from.

**Resolve before:** the interpretation view is wired to live data. A temporally incoherent reading
with a UI on top is harder to see than one in a JSON dump, and 1b's Step 0 exists to prevent
exactly that.

**Status note (2026-08-01, 1b delivery).** Everything in 1b except wiring has now landed:
`axis_verdict` emits the per-group frame, the fixture is generated, the view is corrected, and
`GET /interpretation` exists and is tested. **Delivery stopped here on this clause**, deliberately.
Candidate **(c) has been implemented** - the view shows each marker's collection date whenever it
did not come from the trigger panel - but (c) is by this entry's own text *"the mitigation that
holds whichever of (a), (b) or (d) is chosen"*, so implementing it does not decide which input
rule governs, and this clause requires resolution rather than mitigation. The remaining 1b work is
one commit: point the view at the endpoint and add a dashboard link. **Unblock by choosing between
(a), (b) and (d)** - nothing else is outstanding.

**RESOLVED -> `#159`: candidate (e), added to the set after the fact.** The candidates below were
drafted before the producer had ever run over real series. The first run (1b Step 0) falsified all
three substantive options on one piece of evidence: the `hepatocellular` group is absent from the
newest draw entirely and carries all three out-of-range markers in the dataset (`ast` 47 H, `alt`
53 H, `bilirubin_total` 28 H). Recency-bounding gives a cliff, draw-scoping deletes the finding
until a new liver panel is drawn, and the hybrid inherits draw-scoping for gates and relations. The
question asked which markers belong in the panel; the answer is all of them, and the answerable
question is what the output is a reading of. **(c) is built (`#158`) and is (e)'s foundation, not
its competitor.** The candidate list below is left standing as written — it is the record of what
was considered, and the amendment is only legible against it.

**Corrected while resolving:** (e)'s relation qualifier does NOT require a fourth state in `#154`.
`excluded` / `not_excluded` / `not_assessed` are BRANCH resolutions; operand provenance is a
property of the inputs whose peer is `operand_status`, outside the branch model. `#154` is not
amended.

**Not resolved by this:** `min_meaningful_delta` remains time-blind. Split out as its own question
rather than being marked resolved by a decision that does not address it.

**Wiring bar:** member-level dates (built) **and** group-level as-of rendered. Resolution on paper
does not discharge a concern about invisibility.

## Q70. A censored delta reports `delta_within_min_meaningful` without ever consulting the threshold, so a large suppression reads as quiet

**State:** OPEN. **Blocks:** nothing today — the surfacing verdict is coincidentally correct on the
live panel (see below), which is precisely why this needs recording rather than fixing in passing.
**Related:** `#153` (the demotion predicate), `#141` (the precondition object), `Q69` (temporal
bound), I8.

Found by running `build_foundation` over the real series for the first time (1b Step 0).

`delta()` collapses a censored comparison — either draw carrying a `<` or `>` operator — to
`abs_change=null`, `pct_change=null`, **`min_meaningful_delta` omitted entirely**, and
`magnitude="within_noise"`. `build_news_gate` then derives the basis token from `magnitude` alone
(`gates.py:416-426`): not `meaningful`, not `marginal`, direction not `flat`, so it falls to the
`else` branch and emits **`delta_within_min_meaningful`**.

That token asserts a comparison the producer did not perform. No percentage was computed, no
threshold was read, and the delta object carries no `min_meaningful_delta` to have compared
against. The honest statement is "magnitude unknown", not "within the minimum meaningful delta".

**Observed live, on the markers where it matters most:**

| marker | prior | current | emitted |
|---|---|---|---|
| `lh` | 1.0 IU/L | `<0.1` IU/L | `magnitude: within_noise`, basis `["delta_within_min_meaningful"]`, `is_news: false` |
| `fsh` | 3.0 IU/L | `<0.1` IU/L | same |
| `oestradiol` | `<50` pmol/L | 141 pmol/L | same |

A gonadotropin falling from 1.0 to below 0.1 is a suppression of at least an order of magnitude,
and the output says it was within noise. Oestradiol nearly tripling gets the same sentence.

**Why this is not caught by the surfacing tests, and why that is the danger.** The verdict
`is_news: false` is *correct* for `lh`/`fsh` on this panel — the subject is on TRT,
`hpg_gonadotropin_suppression` resolves `precondition_status: satisfied` with
`expected_by_phase: true`, and suppression is exactly what that relation predicts. So the right
answer is reached, **by the wrong route**: not by `#153`'s relation demotion, which would have
appended `relation_demoted_hpg_gonadotropin_suppression` and stated the real reason, but by a
censoring shortcut that asserts smallness. An invariant holding by accident is the shape `#156`
and `#157` were both about.

Candidates:

- **(a) A distinct basis token.** `delta_magnitude_unknown_censored` (or similar) instead of
  reusing `delta_within_min_meaningful`. Smallest change, and it makes the output honest without
  touching any surfacing decision. Does not by itself stop the value being read as quiet.
- **(b) Censored comparisons become news by default.** Defensible where a bound moved (`1.0` to
  `<0.1` crosses the censoring bound in a direction that is informative), but it would fire on
  every stable `<0.1` to `<0.1` pair, which is genuinely nothing.
- **(c) Bound-aware magnitude.** Where prior is uncensored and current is censored (or the
  reverse), the change is bounded below by `|prior - bound|` — a floor on the magnitude, which IS
  computable and could be compared against the threshold. Most informative, most work.
- **(d) Leave the verdict, fix only the statement.** (a) plus rendering censored deltas as
  "magnitude not computable" in the view.

**Do not resolve by widening `#153`'s demotion predicate** to reach this case. Demotion is a
different mechanism answering a different question, its predicate is deliberately narrow
(`kind == "feedback"` + precondition satisfied + operands complete), and `Q65`/`#154` already own
the question of widening it.

**Resolve before:** any claim is made that gate 1's basis tokens are a faithful account of why a
marker did or did not surface — for example before they are shown to the reader, or used to
generate prose.

## Q71. `min_meaningful_delta` has no time dimension, so an 8% move over 40 days and over 154 days are the same event to gate 1

**State:** OPEN. **Blocks:** nothing today. **Related:** `Q69`/`#159` (provenance partitioning,
which makes the interval visible but not consequential), `Q70` (censored deltas), `#95` (I1 extended
to read-constants), I1.

**Split out of `Q69`, which cited it as evidence for the composite problem. That was wrong.** This
defect would exist in a perfectly draw-scoped world with irregular draw spacing: it is a property of
the threshold, not of which draws the output composites. Left inside `Q69` it would have been marked
resolved by `#159`, which does not touch it.

**VERIFIED distinct from `Q70`.** `Q70` concerns a comparison that never happened — a censored delta
emitting `delta_within_min_meaningful` without consulting any threshold. This concerns a comparison
that *did* happen, against a threshold that is correct for an unstated interval. Different defect,
different fix; `Q70`'s four candidates are all about censoring and none of them touches this.

`min_meaningful_delta` is `{mode, value}` — verified across all 8 authored entries and the
`_defaults` fallback, with no key matching day/window/period/elapsed anywhere in
`lever_dictionary.json`, and `delta()` emits no elapsed field. The authored values are
reference-change-interval figures derived from within-subject biological variation (CVi), which is
itself measured over a stated interval in the source literature — so the numbers carry an implied
timescale that the asset does not record.

**Live spans in one output**, all judged by the same bare percentages: `hpg_axis` compares over
**40 days** (`testosterone_total`, `shbg`) and **143 days** (`lh`, `fsh`) and **154 days**
(`oestradiol`) *within the one group*; `hepatocellular` over **69 days**; `erythroid` over **85
days**. `hpg_t_e2_ratio` relates two markers whose comparisons are 114 days apart in span.

Candidates:

- **(a) Record the interval each authored value is valid over**, and resolve `not_assessed` (or a
  stated caveat) outside it. Honest, and cheap in code — but it is new authoring against I1 for
  every marker, and the CVi literature does not always state the interval.
- **(b) Scale the threshold with elapsed time.** Requires a model of how each analyte drifts, which
  is not CVi and is not authored anywhere. Most likely to invent physiology.
- **(c) Emit the elapsed days alongside the delta and state the span in the view**, leaving the
  threshold alone. The `Q69` (c) move applied to the delta arm: makes the arbitrariness visible
  without pretending to fix it. Composes with (a).
- **(d) Accept it.** Defensible if the draw cadence is regular enough that spans cluster — which
  this dataset falsifies, spanning 40 to 154 days inside one group.

**Resolve before:** any authored `min_meaningful_delta` is presented to the reader as the reason a
move was or was not meaningful.

## Q72. Sprint max velocity has no home on the v0 axis list, so the one Catapult measure most worth capturing cannot be recorded

**State:** OPEN. **Blocks:** recording `max_velocity_ms` from the GPS unit — and only that; the rest
of the `capability_observations` battery (`#161`) is seeded and working. **Related:** `#161`
(the measure registry and the observations table), the deferred Catapult `.gt` backfill.

The proposing brief seeded seven measures and left an eighth — a hamstring velocity proxy,
`max_velocity_ms`, m/s, from Catapult — with its region marked *TBD*, explicitly instructing that it
be flagged rather than guessed. It was not seeded. **Verified against the v0 axis list:** 31 regions,
and the only key containing any velocity/speed/sprint token is `gait_speed`, which is a §G
longevity-end axis, `queue_eligible=False`, `needs_norm=True`, probing test "Timed walk". A walking
axis is not a sprint max-velocity axis, and attaching the measure there would put GPS sprint data
onto a region whose norms are geriatric-referenced.

Why it matters more than the other six: max velocity is the closest available field proxy for
hamstring capacity at the speeds injuries actually occur, and it is the measure the GPS unit
produces most reliably. It is also the one with no self-report substitute — every other seeded
measure has one.

Candidates:

- **(a) A new §E region** (e.g. `max_velocity` / `sprint_velocity`, group E, `Capacity.POWER`,
  `per_side=False`). Honest to what is being measured, and §E is already the probe-priority
  comfort-gap group. Costs a `TAXONOMY_VERSION` bump — the axis list is external-authority and
  versioned, and adding an axis is exactly the change the version exists to record. Needs a probing
  test and an expectation grounded outside this repo, which is the real work.
- **(b) Attach it to `single_leg_hop` as a second measure.** Zero taxonomy change; `Region.measures`
  is already a tuple and the registry supports it today. But `single_leg_hop` is a per-side hop
  distance test and max velocity is a bilateral running quantity — the region's `probing_test` and
  `expectation` would then describe neither measure, and the LSI note attached to it would be
  meaningless for the second one.
- **(c) Leave it unseeded.** The current state, and not costly while the `.gt` backfill is itself
  out of scope. It stops being free the moment sprint data starts arriving with nowhere to land.

**OWNER'S POSITION (Luke, 2026-08-02) — (a), and the reasoning names a third region class.**
Recorded here rather than minted as a decision: the fork stays open until the region is actually
authored, but the direction and its rationale are settled and should not be re-derived.

Max velocity is a DISTINCT capability, not a second measure of an existing one. `single_leg_hop` is
unilateral concentric power; `change_of_direction` is deceleration plus re-acceleration under a
direction change; top-end speed is cyclic, and its peak hamstring demand arrives in late swing.
Different failure mode, different tissue demand — so candidate (b) would make the series
uninterpretable, not merely untidy. Proposed shape: `max_velocity`, group E, `Capacity.POWER`,
`Plane.SAGITTAL`, `per_side=False` (trunk-mounted unit cannot attribute), expectation
self-referenced against the athlete's own season peak so `needs_norm=False`, `Confidence.LIKELY`.

**The non-obvious flag is `queue_eligible=False`, and NOT for the §G reason.** §G axes are excluded
because they lack normative grounding. This one would be excluded because **Probe must never
schedule a sprint**: top speed on two velocity-gated hamstrings is a max effort the engine has no
business prescribing, and `injury_probes.py` already forbids instructing the user to load. The
observations arrive passively from the Catapult regardless of what the queue does.

That makes it the taxonomy's first **passively-observed** region — a third class alongside
probe-eligible and norm-blocked, where the axis is real and measured but the engine never initiates
the measurement. Worth naming as a class when this resolves, because every device-derived region
after it inherits the same shape and the same reason for exclusion.

**Resolve before:** the Catapult `.gt` backfill runs (`.gt` = zip → brotli → msgpack, speed in mm/s),
since that is the point at which a max-velocity series exists and needs a region to be written to.
Not before — nothing is lost by leaving it open while no sprint data is being ingested.


## Q73. The declared-state block sits in front of the content it contextualises

**State:** OPEN. **Blocks:** nothing. **Related:** the interpretation view; `#47`.

The interpretation page renders the declared-factor chips (23 on the live page per the 2026-08-02
review) between the panel header and the first finding. It is honest and correct, and it is the
largest block on the page while being context rather than content.

The proposed principle is placement, not compression: a declared factor belongs **where it changes
a reading**. TRT is why LH and FSH are suppressed and belongs against `hpg_axis`; it is largely
irrelevant to `erythroid`. This is the same principle as the fix already applied to the "not this
panel" badge, where the member defers to a coherent group.

Candidates:
- **(a) Collapsed summary plus per-group citation** — a one-line count at the top, with each factor
  cited at the group whose reading it affects. Most consistent with the rest of the design.
- **(b) Move the block below the findings** — cheapest; keeps it in one place, removes it from the
  path to the content.
- **(c) Compress in place** — smallest change, does not address that context precedes content.

**Resolve before:** the hub shell (`#150`) lands, since a busy page is what the hub exists to relieve
and this block is a large part of the busyness.

## Q74. A declared factor with no derived phase cannot satisfy a `feedback` precondition — evaluability, not a data gap

**State:** OPEN. **Blocks:** authoring any `feedback` relation precondition against a factor key whose `derive_phase` yields `None`. **Related:** `#85` (`derive_phase`), `#141` (the precondition object), `#154`/`Q67` (the branch-condition lane), `Q65`.

`hgh` and `ultra_muscleze_night` render as bare keys with no phase on the interpretation view. This is **not a data gap**: `derive_phase` (`backend/declared_state.py`) returns `None` by design for a superseded/inactive continuous factor and an inactive episodic one, and `#85` records exactly this — `hgh→None`, `ultra_muscleze_night→None` — as intended derivation, not omission.

The consequence worth checking is evaluability, not display. A `feedback` relation's precondition resolves `factor_key` + `admissible_phases` against the factor's derived phase (`gates.py` `_resolve_precondition`, `#141`). A factor whose phase is `None` can never resolve `precondition_status == "satisfied"` — so **it can never be the basis of a demotion**. For `hgh` / `ultra_muscleze_night` today nothing authors such a precondition, so this is latent, not live.

Establish, before any precondition is authored against a currently-`None` key: is the `None` the correct permanent answer for that factor (it genuinely has no interpretable phase), or a seam that a declared washout/re-entry window (the `as_of` parameter `derive_phase` accepts but no rule consumes) is meant to fill later.

**Resolve before:** a `feedback` precondition is authored against any factor key outside the currently phase-bearing set.
## Q75. The catalogue is now populated on connect, but nothing keeps it fresh — the sync has a trigger, not a schedule

**State:** OPEN. **Blocked by:** nothing — the today-fix (connect-time seed + `POST /integrations/hevy/sync`) is landed and sufficient for a populated substrate; this is unbuilt, not gated. **Related:** `#163` (the wiring decision), `#77`/`FEEDBACK` §8 (landed ≠ live), `#79`/`#81` (logged titles drift from catalogue titles), `#65` (the create-loop's own `sync_one_user` refresh).

The connect-time seed populates `hevy_exercise_templates` once, at the moment a key first exists, and the operator endpoint repopulates it whenever someone asks. Neither is a freshness guarantee. The catalogue drifts in three independent ways:

- **Hevy renames its default templates.** Already recorded as a live phenomenon (`#79`/`#81`) — it is the reason `catalogue_titles_by_id` exists at all. A stale row carries a title `resolve_exercise` will no longer match, since resolution is byte-exact by design.
- **The user adds customs outside the app** — in the Hevy client directly. Those ids never enter the store until a sync runs, so `resolve_custom_exercise` misses them and a create path would mint a duplicate against an idempotency check that cannot see them.
- **A row is never deleted.** The sync is upsert-only (the Hevy API cannot delete templates), so drift only ever accumulates.

Candidates:
- **(a) Cron / scheduled job** — a periodic family-wide sync. Predictable and observable, and the only option that keeps the store fresh with no user action. Costs a scheduler this repo does not currently have, and syncs users who are not using the app.
- **(b) Sync-on-read-staleness** — the resolvers check `synced_at` and refresh past a threshold. Freshness exactly where it matters, but it puts a network call on a read path that is currently pure, and a Hevy outage would then degrade reads that today succeed against the local store.
- **(c) Sync-on-workout-fetch** — piggyback the existing `/hevy/workouts` traffic, which already implies both a live key and a user present. No new scheduler, no new failure surface on a pure read; but freshness is only as regular as the user's habit, and a user who never opens the training view never resyncs.

The axis to decide first is **what freshness is actually for**: (b) and (c) keep the catalogue fresh only for the paths that read it, while (a) is the only one that would catch drift before a read needs it. That distinction only becomes load-bearing once a *write* path depends on the store being current — which is exactly what custom-exercise creation is.

**Resolve before:** custom-exercise creation (`<hevy_create_exercise>`) is wired to a user-facing surface. Its idempotency pre-check reads this store, so a stale catalogue there mints duplicate templates rather than merely missing a resolution.

## Q76. The create-enum lists live in two places and nothing detects when Hevy adds a member

**State:** OPEN. **Blocked by:** nothing — round-trip-and-correct is implemented and sufficient; this records the fork rather than gating on it. **Related:** `#164` (the block), `#65` (the create loop), `#83` (correctable-miss pattern).

The three create enums — `CustomExerciseType`, `EquipmentCategory`, `MuscleGroup` — are Hevy's, not ours. They now appear twice in this repo: as prose in `context_builder._section_exercise_creation` (so the model gets them right first time) and as tuples in `chat._CREATE_ENUM_BY_FIELD` (so a 400 can name the valid values). A test asserts the two agree, so they cannot drift from *each other* — but nothing detects them drifting from **Hevy**.

Crucially, neither copy **validates**. The processor passes the model's strings straight through and lets Hevy adjudicate. That is deliberate: a validating table would fail closed the day Hevy adds a type, rejecting a request the API would have accepted — the worst failure mode, because it is invisible and looks like our own rule working.

The fork is what to do about the drift that remains:

- **(a) Round-trip-and-correct — implemented.** Send what the model wrote; on a 400, echo the valid values for the named field so the next turn self-corrects. Never fails closed, no new machinery. Costs one wasted turn per enum miss, and the echoed list is stale in exactly the case that caused the miss.
- **(b) Hardcoded validating table.** Reject before the call. First-try accuracy, no wasted turn — but fails closed on any Hevy addition and needs re-capturing by hand.
- **(c) Periodic re-capture with a drift test.** A test that fetches `swagger-ui-init.js` and asserts the embedded `swaggerDoc` enums still equal the local copies. Catches drift loudly at CI time rather than at user time. Costs a network-dependent test — which this suite currently has none of, and which would fail on Hevy's outage rather than on a real change.

This is a live fork rather than settled because (c) is genuinely attractive and was not evaluated against the no-network-tests convention. Note the drift is not hypothetical: the GET-side vocabulary already carries four values the create enum lacks (`bodyweight_assisted`, `bodyweight_weighted`, `floors_duration`, `steps_duration`), which is direct evidence that Hevy maintains these lists independently and does change them.

**Resolve before:** a second surface needs the enums (a UI picker, a validation layer, the companion app), at which point a third copy makes the drift question load-bearing rather than tolerable.

## Q77. The live create→list-back round-trip is unproven — the first real custom-exercise creation is the test

**State:** OWED. **Outstanding:** one genuine create on a FRESH movement name reaching `+ Custom exercise ... created in Hevy` (owner Luke). **Related:** `#164` (the block), `#166` (the parse fix the watch-point exposed), `#65` (the create loop), `FEEDBACK` §8 (landed ≠ live).

Luke chose to land `#164` on the test suite and the enum artifact rather than mint a permanent custom exercise to prove the path. That is a reasonable trade against an API with no delete — but it leaves a named gap, and an unproven path that nobody has written down is the exact `FEEDBACK` §8 shape this project exists to avoid. So it is written down.

**Covered by the faked-client tests (`#65`, and this branch's 61):** the idempotency pre-check, the create call and its parsed fields, the sync, list-back within the user's own custom subset, the bounded retry over create-visibility latency, every typed error's message, and unresolved-raises-never-returns-None.

**Covered by the live spec (`#65`, re-confirmed 2026-08-03):** the wrapped `{"exercise": {…}}` body shape and the integer-id response that must not be trusted as the store key.

**NOT covered — what only a real POST can establish:** that Hevy accepts the body as this code assembles it, that the created template then appears in a follow-up `GET /exercise_templates` page, and that it does so within `_CREATE_RESOLVE_ATTEMPTS` syncs. Every one of those is an assumption about the live API's behaviour, and the retry bound in particular is a guess about eventual-consistency timing that no fixture can validate.

**Treat the first real create as a watch-point.** It is the de facto integration test, and it fails correctably: a rejected body surfaces the 400's field-and-enum message, and a create that does not surface returns `HevyCreateUnresolvedError`, whose message explicitly forbids a retry. Neither failure is silent and neither loses data — the worst case is one permanent template that the catalogue has not yet indexed. What to watch on that first run: whether the confirmation is `✓ … created in Hevy` (list-back succeeded within the retry bound) or the unresolved warning (it did not, and `_CREATE_RESOLVE_ATTEMPTS` or its backoff needs raising).

**WATCH-POINT FIRED 2026-08-03 — and the failure mode was a THIRD one, predicted by neither this entry nor the brief.** The first real create was attempted. It did not fail on body rejection (the shape was accepted) and it did not fail on visibility latency (the retry bound was never reached). It failed on **parsing the success response**: the live 2xx body is not the spec's `{"id": <int>}`, so `.json()` raised after Hevy had already created the template, unwinding past the sync. Net state: `Copenhagen Adductor Plank Hip Lift` live in Hevy, absent from `hevy_exercise_templates`, reported to the user as failed, one retry away from a permanent duplicate. Fixed by `#166`; the reusable lesson is `FEEDBACK` §23.

**This entry stays OWED rather than DONE, which is a correction to the brief that requested it be resolved.** The watch-point did its job and the defect it exposed is fixed, but the question itself — *does create -> sync -> list-back complete?* — is still not answered. What the incident DID prove, and this is genuine progress: Hevy **accepts the body as this code assembles it** and creates the template, so the first of the three unproven claims above is now settled affirmatively. The other two are untouched, because the parse aborted before the list-back half ever ran. Only a completed round-trip on a fresh name closes this.

**The re-test needs a new movement name.** `Copenhagen Adductor Plank Hip Lift` now exists in Hevy, so re-attempting that title short-circuits at the idempotency pre-check to "already in the catalogue" and exercises none of the create path. Any re-test asserting on that title would be a false pass.

**Resolve before:** custom creation is exercised by anyone other than Luke, or is invoked anywhere the failure message is not read by a human — a batch path, a scheduled job, or an agent loop that would retry on its own and duplicate.

---

## Q78. Exclude-all starves a frequent napper at a 4-night cadence — multi-user nap attribution needs solving before anyone else runs a block

**State:** OPEN. **Blocked by:** Q45 (the nap referent is unknown, so there is nothing to attribute
*to* yet). **Blocks:** any second user on the CBT-I module.

Q45 leaves the VA diary's nap referent unknown, and the engine's response is to exclude ANY
nap-flagged night outright (`NAP_EXCLUDE_MIN = 0`) rather than attribute it. At the old 7-night
cadence with a 5-night sufficiency threshold that cost a cycle only when three nights were lost. At
**4 nights with a 3-night threshold the margin is a single night**: two nap-flagged nights in a cycle
starve it, and the engine HOLDs.

For the current single user (Luke, an infrequent napper) this is tolerable and exclude-all stands —
it is the conservative reading of an ambiguous instrument, and a wrong attribution corrupts the
adherence basis silently, where an exclusion only costs a cycle. For a **frequent napper** it is not:
they would stall indefinitely, and — before this session — silently, with the surface saying only
"insufficient".

**Partially mitigated, not resolved (this session).** The HOLD reason now names the tally
(`insufficient_nights: 2 valid of 4, need 3 (2 excluded: nap x2)`), so a stall is diagnosable rather
than mysterious. That makes the failure *legible*; it does not make titration *work* for that user.

Candidates, none costed:

- **(a) Attribute the nap** once Q45's referent is known — the principled fix, wholly gated on Q45.
- **(b) A duration threshold** (`NAP_EXCLUDE_MIN > 0`) so short naps stop disqualifying a night.
  Cheap, but picks a number with no more evidence behind it than the current 0.
- **(c) Per-user cadence** — a napper runs a longer cycle, restoring the margin without touching the
  nap predicate at all.
- **(d) Degrade rather than exclude** — admit the night with a recorded caveat, which trades a clean
  basis for a decidable one.

**Do not resolve by:** loosening `NAP_EXCLUDE_MIN` for the single user to make a cycle decidable. That
is tuning the instrument to the outcome, and Q45's whole point is that the referent is unknown.

**Resolve by:** the second user onboarding to the CBT-I module, whichever comes first with Q45.

---

## Q79. The `#167` guard cannot see the `@claude` Action's pushes, and until now that gap lived only in prose

**State:** DONE → #170. **Related:** `#167` (the guard), `#169` (the cross-repo generalisation), `Q59` (nothing verifies the deployable artifact — adjacent, not the same hole), `Q12` in `health-connect-app` (**the mirror, still OPEN — owed**), `ROADMAP` NOW cross-repo row.

**THE GAP WAS REAL; THE AGENT NAMED BELOW IS NOT. Corrected at resolution, 2026-08-04.** health-app has **no `.github` directory in any commit on any ref** — the `@claude` Action has never been wired to this repo, so the push path this question was built on does not exist and never did. The question was minted on `#167`'s prose plus the shared block's claim that *"Code — and the `@claude` GitHub Action — is the only writer"*, and nobody checked whether the Action was installed: `FEEDBACK` §12 committed by Code rather than chat. **The real uncovered path was in this repo's own history the whole time** — five merges on master committed by `GitHub <noreply@github.com>` (`e62f89f`, `0aa0200`, `f4b538f`, `cb1b58f`, `9f9437c`), i.e. github.com web-UI merges, which are server-side ref updates. The original text is preserved below unedited, because a question resolved by discovering its own premise was wrong is worth more legible than a question quietly reworded.

**Resolved by `#170`** — `.github/workflows/governance-guard.yml`, `ubuntu-latest`, on `pull_request` + `push: [master]`. **Read the caveat with the close:** the `push` arm is *detection* (it fires after the ref has moved); prevention is the `pull_request` arm **plus branch protection requiring the check**, which is GitHub-side repo config, not committable, and **Luke's action, not Code's**. Until it is set the PR arm reports rather than blocks. `#NEXT` carries the full evidence, including the four control runs.

**Still unverified, deliberately:** whether a GitHub App holds push rights on this repo. GitHub-side, not in the tree — reported unknown rather than assumed either way, which is the mistake this question made in the first place.

**Original text, as minted, uncorrected:**

`core.hooksPath` is a **per-clone, client-side** setting. It cannot bind a runner. The `@claude` GitHub Action pushes from a checkout that never ran `git config core.hooksPath .githooks`, so every push on that path is unguarded — a placeholder can reach master exactly as it did three sessions running before `#167`, by the one route the guard structurally cannot watch.

**Why this is being minted now rather than at `#167`.** The gap was known and deliberately recorded when `#167` landed — but only inside the decision entry's prose and its `BRANCHES` row. Neither is a tracked item: a decision entry is append-only history, and a `BRANCHES` row dies when the branch merges. So the hole had **no home that would outlive the branch that found it**, and a reader of `OPEN_QUESTIONS` — the store whose entire job is "what is undecided" — would have seen a fully-enforced guard. That is the same shape as the defect `#169` just fixed: an instrument that reads green over a surface it cannot observe. The propagation brief asked for an HCA row "mirroring health-app's" and there was nothing to mirror.

**What closing it requires is a CI check, not a hook.** A workflow step running `python scripts/check_governance_placeholders.py --ref "$GITHUB_SHA"` on pushes to master would cover every path into the ref including the Action's, and the script already exits 0/1/2 with 2 reserved for cannot-run, so it is CI-shaped as written. The open forks are whether it duplicates the hook or replaces it (two implementations of one rule is the failure `#169` names), and whether a branch-protection rule is wanted so the check is required rather than merely reported.

**Blocked by:** nothing — this is buildable now. It is unstarted, not blocked.

**Do not resolve by:** asserting the Action does not push governance files. It merges branches and lands entries; that is the point of it, and "it probably will not" is the class of reasoning `#162` was created by.

**Mirror obligation:** `health-connect-app` inherits this hole verbatim on propagation and must mint the same row. Two repos with the same hole recorded is honest; two repos with the same hole and one of them silent is how it survives another four sessions.

---

## Q80. The guard polices the symptom, not the invariant — nothing checks that decision numbers are unique and gapless

**State:** OPEN. **Related:** `#167` (the guard), `#170` (its CI arm), `#171` (the PR-gated merge path and strict mode), `#172` (the boundary criterion), `#162` (the hole this class produced), `#148` (classified-not-counted renumbering).

**The gap.** `scripts/check_governance_placeholders.py` refuses an unresolved `#NEXT` reaching master. That is the *symptom*. The invariant the placeholder protects is that decision numbers are **unique and gapless** — and nothing checks it. `#162` was a gap; a two-branch collision would be a duplicate. Both pass the guard silently, because both are fully-resolved integers.

**Why it matters more under `#171` than it did before.** The PR-gated path made the resolve→merge window *visible* — strict mode refuses a merge when the branch is behind master, so an advance between resolving `#NEXT` and merging forces a pause. But a forced pause is not an adjudicated number: the pause tells you master moved, not that the integer you claimed is still free. The two halves compose exactly — **strict mode forces the update, a uniqueness-and-gapless arm would adjudicate at that update** — and neither closes the number race alone. With the arm, the race closes mechanically, with the operator sequencing nothing.

**Where it must live, already ruled.** In the guard, not the alias. A draft `land` body carrying the assertion was written and rejected: git aliases live in `~/.gitconfig` or `.git/config` — unversioned, per-machine, uncopyable, invisible to review. Putting adjudication there is enforcement on the least durable surface available, which is the exact property that made the guard necessary. The guard binds every path and every clone; it already reads the file the assertion needs.

**Shape, not yet designed:** assert over `DECISIONS_LOG.md` that the resolved headings form a contiguous run with no duplicates, anchored on the heading form per `#113` and level-agnostic per `#169` so it does not read empty against `health-connect-app`'s grammar. Open sub-questions: whether historical gaps (`#162`) are grandfathered by a floor or by an explicit allow-list — a check that fails on day one on known history gets disabled rather than fixed; and whether the arm runs in the same script or a sibling, given the script's exit-code contract (0 clean / 1 would-reach-master / 2 cannot-run) is already load-bearing.

**Third sub-question — the forward-reference class, which is the one nothing covers.** There are three ways a decision number goes wrong and the guard set covers two. An unresolved placeholder is caught by `#167`'s guard. A duplicate or a gap would be caught by the arm above. **A forward reference written as a literal number before the resolve is invisible to all of them** — `#171` in prose is syntactically perfect and semantically wrong if master moved, and no anchor, count or contiguity check can tell. `#171`'s own landing demonstrated it: nine refs were written as literal `#171`/`#172` ahead of the resolve and held only because master happened not to advance; the three tokens written as `#NEXT` in the same branch were safe by construction. **The cheap fix is a rule, not a check:** never write a resolved-looking number before the resolve — write the token and let the guard enforce it. The open part is what the token looks like when one branch carries two entries, since a bare inline `#NEXT` cannot say *which*; that ambiguity is exactly why the literals were written in the first place, so the rule needs a disambiguating form (`#173` / `#174`, or per-entry slugs) before it can be stated as binding. Decide the form here, then the rule can go in the shared block as an invariant — it is true regardless of merge path or enforcement surface.

**Blocked by:** nothing. Buildable now — UNSTARTED rather than blocked, and the reason it is a question rather than a roadmap row is the grandfathering fork above, which wants a ruling before code.

**Do not resolve by:** adding the assertion to the alias after all, or by asserting on a count rather than the heading forms (`#113`: read the matches, never the count).

---

## Q81. Device deep-sleep-stage validity is too low to drive readiness — deep-confidence is diagnostic, not a score input

PPG+accelerometer sleep trackers (the Samsung Ring class — direct Galaxy-Ring N3 validation is thin, so
this is class-level evidence plus Samsung-watch data, and is stated at that scope deliberately) classify
deep/N3 at roughly **50–58% per-epoch at best**. Two documented failure modes match Luke's records:

1. **Misclassification.** Deep sensitivity runs 0.14–0.58 across devices; ~51% epoch agreement (Oura).
   At near coin-flip per epoch the hypnogram flickers in and out of deep — which is what the Gate 2
   "~26 of 30 deep segments under 3 minutes" pattern *is*. It is an artifact signature, not physiology.
2. **Proportional under-report.** Devices under-count deep on exactly the nights with the most of it
   (Oura ~−20 min N3; Fitbit ~−15; Apple ~−43). "Little deep despite waking refreshed" is this bias.

Group averages mask large individual-night error, so a device that looks acceptable in aggregate can be
useless for any single night — and a daily readiness term consumes single nights.

**The asymmetry is the load-bearing part.** `deepSleepConfidence.js` can only **subtract** false deep
(artifact slivers). It can never recover **under-reported** deep — true SWS scored as light — which is
the dominant error here. So no amount of calibration makes the module a score input; it is structurally
incapable of correcting in the direction that matters.

**State:** `DONE → #173` — device deep-minutes are not a readiness or Banister input; the
deep-confidence module is retained diagnostic-only, its constants uncalibrated **by design**, feeding no
score. Extends `#71` from the daily sleep-score term to the module and to Banister.

Refs (supplied by the 2026-08-03 chat session, **not independently retrieved from this tree**):
Herberger 2025 (Sci Rep); Kainec 2024 (Sensors); Robbins 2024 (Sensors); de Zambotti 2017 (Behav Sleep
Med). Cross-refs Q3, `#71`.

---

## Q82. `_aggregate_day` keeps only the longest sleep session — fragmented Samsung nights undercount

Surfaced by the Q4/G4 drill-down (2026-08-03, live Railway). Three nights — wake-dates 2026-07-20,
-22, -23 — undercount the Samsung scraper across **all** stages, with date attribution correct
(same-date, `still_shifted = 0`). So this is not a residue of the Q4 shift; it is a separate defect that
the Q4 fix made visible.

**Mechanism.** Samsung writes a fragmented night as multiple non-overlapping `SleepSession` records.
`_aggregate_day` (`backend/routers/health_connect.py`, the `best = max(day_sleep, key=...duration())`
selection) persists **only the longest session and its stages**, discarding the rest of the night.
Per `health_connect_record_sources` the three undercounting nights carry 2 / 2 / 4 `shealth` sessions
(7/23 has four: 22:42, 02:14, 02:45, 04:46 AEST).

**Not every multi-session night.** 7/21 had two `shealth` sessions and matched exactly. The undercount
bites only when the fragments are **balanced** — when one session clearly dominates, `max()` happens to
pick nearly the whole night and the bug hides. That is why it survived Q4.

The in-code comment above the selection anticipated only **nap displacement** ("a same-day nap cannot
displace the main night because the max() tiebreak still picks the longest session") — it did not
anticipate a real night split into several main sessions, which is the case that breaks it.

**Fix:** replace max-only with a **union/merge** of the night's sessions, excluding same-wake-date naps.
"Which sessions constitute the night" is the design fork and is not yet decided.

**State:** OPEN — no blocker, but **sequenced after `Q83`**: a merge must run *within* the single
source that question selects, because merging sessions across Samsung and Withings would be incoherent.
Distinct from Q4 (`DONE → #64`). Owner: Luke. Cross-refs `Q83`, `#35`/`#36`/`#37`.

---

## Q83. HC sleep selection is source-blind — Withings and Samsung are silently blended, and the `#35`/`#36`/`#37` dedup enabler was never wired

Surfaced alongside `Q82` in the Q4/G4 drill-down (2026-08-03). `health_connect_record_sources`
shows Health Connect carries sleep from **two** writers: Samsung (`com.sec.android.app.shealth`) and
Withings (`com.withings.wiscale2`).

`_aggregate_day` selects by max-duration across **all sources with no priority**. So on any night a
Withings session happens to be the longest, the persisted `health_connect_syncs` sleep reflects
**Withings** staging rather than Samsung — silently. That breaks scraper parity and poisons every
downstream HC-sleep consumer: `sleep_score`, `_section_health_connect`, the dashboard.

**Designed, enabled, never wired.** `health_connect_record_sources` exists expressly as the
"source-priority dedup enabler (`#35` F1 / `#36` / `#37`)" — its own migration docstring says so — and
`_aggregate_day` never consumes it. The table is populated and ignored.

**The sub-finding is no longer unexplained — it is the cause (2026-08-05).** On four nights (7/19,
7/20, 7/21, 7/23) a Withings record shares an **identical `record_start`** with the Samsung one. That
is **confirmed as a Withings Health-Mate mirror of Samsung's own sleep**, not an independent sensor —
a re-post loop. Consequence: **no signal is lost by discarding those rows.** They are a copy of data
already held, so the choice is not "which of two measurements to trust" but "stop ingesting an echo".
*(Attested by Luke 2026-08-05; not independently verified from this tree — the Railway CLI was
non-functional in the recording session and Health Connect writer permissions are a device surface
neither Code nor chat can read. Recorded as reported.)*

**This reframes the fix, and the reframe is the point.** "Prefer Samsung" would have worked here by
coincidence and failed on the next mirroring app to appear:

- **(a) Source-side — the higher-leverage half, and it needs no repo work at all.** Revoke Withings'
  Health-Connect **write** permission for Sleep. That kills the duplicate *before* ingest, so nothing
  downstream has to reason about it. It is a phone setting Luke can change immediately, independent of
  any code below. **Do this first** — it makes (b) a robustness measure rather than a live bug fix.
- **(b) Code-side — `default-untrust`, not `prefer-Samsung`.** `_aggregate_day` selects from a
  **registered measuring source** and treats any other writer as **derivative unless explicitly known
  to be an independent sensor**. An allow-list, not a preference ordering: an unknown future writer is
  excluded by default rather than silently competing on duration. This survives the next Health-Mate.
  Runs **before** `Q82`'s fragment-merge, which is why this question gates that one — a merge across a
  measuring source and its own mirror would double-count the night.

The device-agnostic-schema rule makes this structural rather than a one-user quirk; `record_sources`
or the payload `source_package` is the input either way.

**State:** OPEN — cause confirmed, direction decided, and the reframe now **binds at `#175`**
(source admission replaces source priority; the OWED entry-note is discharged). What remains is code:
`_aggregate_day` still selects by max-duration across all writers.

**The `#175` identity precondition — RESOLVED in the safe direction, and narrowed (2026-08-05).**
`#175` flagged a contradiction: `WriterIdentity` documents *"current HCA builds send no dataOrigin"*
while this question's evidence shows real package names in `health_connect_record_sources` on
2026-08-03. **Identity does arrive; the docstring is the stale artifact** — HCA master's sleep mapper
and `heartRateMapper` thread `sourcePackage: r.metadata?.dataOrigin ?? null`, and the live table
carries real packages. The docstring predates the mapper change that added `sourcePackage`. So the
**"allow-list admits nothing, every night vanishes" scenario is withdrawn** — it was conditional on the
docstring being true. *(Attested by Luke 2026-08-05 from an HCA-rooted read plus prod data; neither
surface is readable from this tree.)*

**What survives, and it is the precondition's real content:** the allow-list must not silently drop the
`'unknown'` that **legitimately exists**. `_capture_record_sources` coalesces missing identity to
`'unknown'`, and that value arises for real reasons — historical rows written before HCA threaded
`dataOrigin`, any record type HCA does not tag, and a future build regression. A strict allow-list that
excludes `'unknown'` fail-closes those **silently**, which is the same defect class `#175` exists to
remove. So **`'unknown'` must be a decided value, not a default that means exclude**: admit-with-flag,
fall back to pre-`#175` max-pick for unidentified records, or log-and-count coverage per the `#74`
fallback-hit-rate pattern. Decide which before the filter is written.

**Two moves discharge it, both cheap:**
1. **When Railway is reachable**, one bounded query on `health_connect_record_sources`: per-record-type
   `source_package` coverage — what fraction of sleep rows are `'unknown'` vs real, **split by era**.
   That quantifies the historical-`'unknown'` exposure and confirms current sleep is fully identified.
   Measure the gap before trusting the filter.
2. **Correct the stale `WriterIdentity` docstring** — done on `gov/175-precondition-narrowed`. It was
   actively misleading, and it is what made a resolved question look like a live fail-closed risk.

→ `DONE → #175` when the code lands. **Higher priority than `Q82`, and gates it.** Distinct from Q4
(`DONE → #64`). Owner: Luke. Cross-refs `Q82`, `#35`/`#36`/`#37`, `#74`.

---

## Q84. The `/health-connect/sync` backend accepts record types HCA never posts

`_aggregate_day` writes `oxygen_saturation`, `respiratory_rate` and `distance_meters`, and the models
define `WeightRecord`, `DistanceRecord` and `MindfulnessRecord` — but HCA's `fetchAllData` posts only
sleep / hrv / heartRate / steps / workouts. So the Health Connect path never fills those columns; SpO2
and respiratory rate arrive via the Samsung scraper instead, and the HC-side columns sit permanently
null.

This is **not a bug** — it is schema-wider-than-client, and the backend is tolerant rather than wrong.
It is recorded because `#174` explicitly parks `.get_kg()` / `.get_meters()` as "out of scope —
forward-compat for record types HCA does not post", and without this row that exclusion points at
nothing: a reader of `#174` has no entry explaining why those two reconcilers were left alive when
the other five branches were deleted. **This question is the home for that exclusion.**

The fork: wire HCA to collect and post the missing record types, or trim the backend surface to what the
client actually sends. Deciding it also decides whether `.get_kg()` / `.get_meters()` eventually live or
die.

**State:** OPEN — no blocker. Surfaced by the Q5 drill-down (2026-08-03) and **distinct from Q5**: Q5 is
two names for one value, this is a name with no sender. Owner: Luke. Cross-refs Q5, `#174`.

---

## Q85. Which required field does the live extraction of a ref-less lead row actually drop?

The SNP Albumin/Creat Ratio report (collected 2026-08-04) is refused by `/labs/confirm` with a
Pydantic request-validation 422 — established by elimination in `#177`, which excludes both of
`confirm_lab_report`'s own raise sites against the screenshot. **Which field the validator refused
is not known**, because the banner discarded the `detail` that names it. `#177` Move 1 fixes the
banner; this question is the fork that fix exists to settle.

The two candidates predict different repairs and are not both fixable by the same change:

- **`field_confidence.*` (the leading hypothesis).** `FieldConfidence` (`backend/routers/labs.py:41`)
  requires `name/value/unit/ref` as bare `float`, no defaults, not `Optional`, while
  `field_confidence` as a whole is optional. The extraction prompt (`labs.py:280`) asks for a
  confidence "per field: name/value/unit/ref". `R U-Creatinine` has **no reference interval** —
  printed `—`, and sited above the results table, the most awkward shape in the corpus
  (`LAB_EXTRACTION_SCHEMA §4` case 3, absent-ref). A model asked to score its confidence in a `ref`
  that does not exist will plausibly omit the key or emit `null`; either fails validation. If this
  is it, the request contract is **stricter than the extractor's honest output** for a legitimate
  report shape, and the repair is `float | None = None` sub-fields.
- **`report.source_completeness` / `report.panel_name_raw`.** Both required `str` on
  `ReportEnvelope`. If the model invented a `ref` confidence and instead dropped a top-level field
  on this layout, the fault is an **extraction-prompt gap**, not a contract that is too strict, and
  loosening `FieldConfidence` would be a change made against no evidence.

A `field_confidence.*` answer carries a second, latent defect with it: `labs.py:603` does
`min(list(r.field_confidence.model_dump().values()))`, and `min` over a list mixing `float` and
`None` raises `TypeError`. Loosening the contract without dropping `None`s first (default `1.0`
when all-None) converts a 422 into a 500. Same category as the row/confidence alignment `assert`
already guarded at `labs.py:609`. Note also `Metrics.jsx:11` — `Object.values(conf).some(v => v < 0.85)`
treats `null` as `0` in JS, so a null `ref` would mark the row suspect; arguably right, but for the
wrong reason and worth deciding rather than inheriting.

**Resolved by:** re-uploading the same PDF once Move 1 is deployed and reading the `loc` off the
banner. Nothing about the reproducer is stored yet — the 422 persists nothing — so a clean
re-attempt exercises the genuine extract → confirm path. Record the verbatim `loc`/`msg`.

**Answered — and by NEITHER candidate above.** The captured banner, read off the deployed `#177`
instrument, named `results.0.ref_high_exclusive: Input should be a valid boolean`. The offending
field is a **third mode this question did not contemplate**: a non-Optional exclusivity `bool`
(`ResultItem.ref_low_exclusive` / `ref_high_exclusive`, declared `bool = False`) nulled by the
extractor on an absent-ref row — correctly, since with no bound there is nothing to be exclusive
about. `field_confidence` validated in full on this exact awkward report, so the leading hypothesis
is **disproven, not merely unconfirmed**, and the `min()`-over-`None` hazard flagged above was
contingent on that branch and did not occur. Both predicted branches were argued carefully from the
code and both were wrong; one live extraction settled it. That is the case for building the
instrument before guessing the fix — see `FEEDBACK` §26.

**Residual, recorded so it is not inherited silently:** `FieldConfidence`'s four floats remain
non-Optional and are the last members of this class. Left untouched deliberately — they work, and
changing a working contract on no evidence is the exact error this question's history warns about.

**State:** `DONE → #178` — resolved by the contract coercion (`null → False` on both flags, type
kept strictly `bool`, no migration). Cross-refs `#177` (the instrument), `#58` (unmapped is a
signal, not a failure), `#146` (derived, not model-reported, confidence), `FEEDBACK` §25 and §26.

**Not this question:** adding `R U-Creatinine` / `R U-Albumin` / `R U-Albumin/Creat` to the
canonical map. Unmapped rows persist fine and return in `unmapped`, so recognition does not affect
the save and is a separate track.
