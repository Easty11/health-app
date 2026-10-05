# OPEN QUESTIONS

Undecided forks and unverified-at-machine items. One state per item, from the **question-state**
axis (`OPEN` / `OWED` / `DONE → #N`) defined in `CLAUDE.md` → **State vocabulary** (the sole
definition). The label is `**State:**` (never `**Status:**`). `DONE → #N` names the resolving
`DECISIONS_LOG` entry.

---

## Q10. Build AccessLink per-second ingest for the Metabolic-load window (HC/companion lane)?

#35 established the dependency: HC carries no per-second R-R/HR-zone; only AccessLink
(v3 REST exercise-samples / TCX export) does. #46 specified the exact pathway but it is
not built. PSL covers Luke's direct solo/gym capture, so the need only bites if the
HC/companion lane carries a Polar user requiring per-second — none confirmed (Deb's
wearable integration is no longer deferred as of 2026-08-10 — see State; Cooper has no wearable).

**State:** OPEN — low priority. **Not BLOCKED**: #46 already specified the pathway, so nothing
prevents building it; the trigger is a real consumer, and the one deferral that held it off has lifted.
**2026-08-10 (Luke, confirmed):** Deb's wearable integration is **no longer deferred**. This does not by
itself make Q10's consumer real — the pathway bites only if Deb's device delivers Polar-in-HC per-second
data (R-R / HR-zone), which is not yet established — but it removes the reason this was parked, so Q10
re-enters live consideration. Revisit when the Metabolic-load channel is wired to a confirmed
Polar-in-HC consumer.

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

**Re-measured 30 Sep 2026 (Brief A G7, after the A3/A5 changes to `WorkoutPanel`, #355).** On the built app in
Chromium, `/training` (the panel no longer sits in the Dashboard's 50/50 column; it lives in an
`h-[75vh] min-h-[420px]` box beside the docked chat), API mocked, a 9-exercise Hevy workout open in
`WorkoutDetail`: the exercise scroller (`flex-1 overflow-y-auto`) measures **361 px tall x 819 px wide** at
1280x779 (`scrollHeight` 1479) and **452 x 926** at 1440x900, `overflow-y: auto`. That is not the 36 px of the
original measurement, so on the route the panel now occupies the starvation is not reproduced; the Dashboard
column it was measured in no longer hosts `WorkoutPanel`. Not measured: a phone-width viewport, and a workout
with a long session-analysis block. State unchanged (the fork is moot on `/training` unless the panel returns
to a half-height column).

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

**Interim axes landed (2026-09-26, #334/#336).** `shoulder_er_ir`, `hip_adduction` and `knee_flexion` (plus
`trunk_lateral_flexion` and `dip`) now exist as STRENGTH regions so tagged exercises stop falling to the keyword
fallback. They are probe-inert bolt-ons, explicitly NOT this question's answer. Shoulder ER/IR, Copenhagen, Hip
Adduction and the leg curls moved off no-pattern onto them; calf and hip abduction stay no-pattern. The v1 pass
supersedes them.

> **SUPERSEDED (2026-10-01, #363).** The slot-keying question below (options a / b / c) is moot: a quota slot is
> satisfied by doing the PLANNED session, not by the logged session's capacity, plane or region set. Kept verbatim as
> the record of how the question was framed.

**Scope extension (2026-09-26): what does a quota slot KEY on?** Region definitions alone do not close this.
The decompression phase exposed a second hole: its real intent is a PLANE PERMISSION on strength work ("strength in
these planes, not the provocative ones"), and a `capacity` slot (Rule 1, `engine/resolver.py`) counts every
STRENGTH-dominant workout the same, provocative-plane work included. Regions already carry a `Plane`, so v1 must also
decide the slot key: **(a)** capacity alone (today), **(b)** capacity × plane, or **(c)** an explicit region
allow/deny set per slot. Which one is enough turns on an operator input not yet given: are the currently provocative
loads plane-level (e.g. all transverse loading) or finer (specific regions within a plane)? If Q27 closes on region
definitions alone, the phase gets rebuilt on the same flawed base.

**Scope note (2026-09-27): the real restrictions are not planes.** The operator's current restrictions, recorded as
evidence for the slot-keying question above:
1. **Lumbar** (clinician: Dr Aubrey). DENY end-of-range flexion COMBINED with rotation. All other lumbar movement is
   PERMITTED under a pain-gated progression rule (start small, build up; pain halts progression). Heavy or end-range
   hinge (flexion without rotation) is clinically cleared; whether an operator-chosen ceiling remains is PENDING the
   operator. Deficit KB RDL (20 kg, flossing, #338) sits inside the clearance.
2. **L knee → squat.** RANGE-LIMITED (depth). Likely extends to leg-press depth and step-up height.
3. **L thumb.** EXERCISE- or POSITION-specific, only under direct thumb load: renegade row (worst), dead bug with a
   dumbbell overhead (angle), dip hand position. Carries and pulls are unaffected.

None of these is plane-level. That is evidence against option **(b) capacity × plane**: planes never appear in the
restrictions actually in force.

> **MOVED to Q197 (2026-10-01).** The restriction-record design below, including the pain-gated progression
> qualifier and its capture point, now lives in Q197 (a "pain" reason on a deviation is the per-session capture
> point). The restrictions listed above stay here as evidence. The counting half of "Separate counting from
> permission" is SUPERSEDED by #363: counting keys on plan-conformance, not on region/capacity.

Design direction (chat proposal, not ruled):
- **Separate counting from permission.** Quota counting keys on region/capacity and stays ungated. Hevy exposes load
  but not range, depth or hand position, so range gates cannot be enforced at count time.
- **Permission lives in a restriction record**, enforced at prescription, probe and warning time:
  `{target, qualifier, side, reason, source, review_date}`.
  - `target` = region → a load ceiling and/or a range limit (expressible as "end-range permitted below load X").
  - `target` = movement combination → deny (e.g. EOR flexion + rotation).
  - `target` = exercise → a position/setup note the engine cannot detect, carried wherever the exercise is
    prescribed or shown.
- **Qualifier type PROGRESSION RULE (pain-gated).** Enforceable only if a pain signal is captured (a check-in field or
  a per-session flag); otherwise advisory. Q27 decides the capture point.

> **Partly SUPERSEDED (2026-10-01, #363).** Bullet 1 (the capacity-ruling finding) is folded into #363: capacity is
> the wrong quota key, and it stays a descriptor only. Bullet 2 (sided pairs voting twice) is moot once counting
> leaves Rule 1. Bullet 3 (exposure never suppresses screening of a MEASURED region) STANDS and is retained below.

**Findings after the v0.1 seed (2026-09-27, #339). Q27 stays OPEN.**
- **Operator ruling: capacity is the wrong quota key for this program.** Here the stability/strength split is a
  misnomer, because all "stability" work is strength work. Capacity STAYS in the taxonomy as a descriptor (#76's
  external grounding; other users may need it), but it is not necessarily what a slot keys on. This narrows the
  slot-keying question above; it does not close it.
- **Sided pairs vote twice in Rule 1.** On 09-21 the split was 5–3 for Stability per MOVEMENT but a 6–6 tie in VOTES.
  The slot-order tie-break resolved it to Stability, and the Deficit KB RDL's move off primary `hinge` (#338) alone
  decided the tie. Folded in here rather than fixed separately, because dominant-capacity counting itself is under
  review.
- **Training exposure must not suppress screening (generalised from #338).** Tagging an exercise to a region makes the
  router prescribe that exercise instead of the region's screen, and logging it removes the region from probe
  candidates. Principle for the redesign: exposure never suppresses periodic screening of a MEASURED region.

**Scope after #363 (2026-10-01).** Q27 is narrowed to the v1 VOCABULARY and how each axis is MEASURED. It no longer
decides what a quota slot keys on (superseded by #363) or how restrictions are recorded (moved to Q197).
- **v1 vocabulary (ratio-first axes):** ER:IR, adductor:abductor, plantarflexion; hamstring is a candidate.
- **Region tags stay load-bearing.** Substitution equivalence in Q197's adjudication runs on them, so the tags keep
  their job even though capacity no longer keys the quota.
- **Exposure never suppresses screening of a MEASURED region** (retained from #338; see Findings above, bullet 3).

**Sub-question (2026-10-01): MEASUREMENT ROUTE per axis.** The ER:IR comparison above is not like-for-like. The
logged 0.56 is a cable-load ratio (6.25 : 11.25 kg); the 0.66–0.75 band is an isokinetic-torque reference. Different
units, so the gap between them does not size a deficit. Each axis needs a route chosen:
- **(i) Log-derived ratio.** Same setup both sides, e1RM-normalised, judged against an INTERNAL band (the user's own
  baseline and trend). Literature is used for DIRECTION only, never as a threshold.
- **(ii) Protocol probe.** A handheld dynamometer or squeeze test, read against literature norms. The norm and the
  measurement share a unit, so the literature band is usable as a threshold.

Decide per axis (ER:IR, adductor:abductor, plantarflexion, hamstring if admitted). **Pending operator:** whether a
dynamometer or squeeze gauge is available. Route (ii) cannot be chosen for any axis until that is known.

**State:** OPEN — the v1 taxonomy bump is its own design pass: externally grounded (HAGOS / adductor
squeeze; ER:IR isokinetic references; return-to-sport LSI), with adductor:abductor and ER:IR as first-class
reads. NOT a bolt-on from a tag file (the taxonomy is external-authority so its breadth does not inherit the
user's blind spots — #76). Narrowed by #363 to vocabulary plus measurement route. The vocabulary work has no
blocker. Measurement route: blocker for route (ii) only is the operator's equipment answer (Owner: Luke).
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

---

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

---

## Q74. A declared factor with no derived phase cannot satisfy a `feedback` precondition — evaluability, not a data gap

**State:** OPEN. **Blocks:** authoring any `feedback` relation precondition against a factor key whose `derive_phase` yields `None`. **Related:** `#85` (`derive_phase`), `#141` (the precondition object), `#154`/`Q67` (the branch-condition lane), `Q65`.

`hgh` and `ultra_muscleze_night` render as bare keys with no phase on the interpretation view. This is **not a data gap**: `derive_phase` (`backend/declared_state.py`) returns `None` by design for a superseded/inactive continuous factor and an inactive episodic one, and `#85` records exactly this — `hgh→None`, `ultra_muscleze_night→None` — as intended derivation, not omission.

The consequence worth checking is evaluability, not display. A `feedback` relation's precondition resolves `factor_key` + `admissible_phases` against the factor's derived phase (`gates.py` `_resolve_precondition`, `#141`). A factor whose phase is `None` can never resolve `precondition_status == "satisfied"` — so **it can never be the basis of a demotion**. For `hgh` / `ultra_muscleze_night` today nothing authors such a precondition, so this is latent, not live.

Establish, before any precondition is authored against a currently-`None` key: is the `None` the correct permanent answer for that factor (it genuinely has no interpretable phase), or a seam that a declared washout/re-entry window (the `as_of` parameter `derive_phase` accepts but no rule consumes) is meant to fill later.

**Resolve before:** a `feedback` precondition is authored against any factor key outside the currently phase-bearing set.

---

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

---

## Q78. Nap exclusion still starves a frequent napper at a 4-night cadence — needs solving before anyone else runs a block

**State:** OWED → #262 (2026-09-02) — fork **(c) per-user cadence** chosen. **BUILD
DEFERRED** to second-user CBT-I onboarding. **Not DONE:** no code lands, and the
frequent-napper stall persists in the engine until (c) is built. **No longer an open fork**
— the question (which candidate?) is answered; only the implementation waits, on a trigger
that does not yet exist. **Blocks:** any *frequent-napper* second user on the CBT-I module,
until (c) ships — now a build dependency, not an undecided design question. **No longer
blocked by Q45** (closed → #219, 2026-08-17).

**Original text, as it stood at decision, preserved below:**

**Premise updated 2026-08-17 — the numbers below moved, the fork did not.** The engine no longer
excludes ANY nap-flagged night; it excludes naps over `NAP_EXCLUDE_MIN`, now **30**, and attributes
each nap to the night it precedes. At the old 7-night cadence with a 5-night sufficiency threshold a
lost night cost a cycle only when three were lost. At **4 nights with a 3-night threshold the margin
is a single night**: two OVER-THRESHOLD nap nights in a cycle still starve it, and the engine HOLDs.

So #219 eased this question without answering it. It removed the trivial-nap stalls — the ones that
cost a whole cycle for a 15-minute nap — but a genuine frequent napper, who by definition takes real
naps, still stalls. That residue is a **data-consequence** fork, not a referent one: it was always
about what losing nights costs at a one-night margin, which is exactly why it did not close with Q45.

For the current single user (Luke, an infrequent napper) the current setting is tolerable. For a
**frequent napper** it is not: they would stall repeatedly — though no longer silently, since the
HOLD names the tally.

**Partially mitigated, not resolved (this session).** The HOLD reason now names the tally
(`insufficient_nights: 2 valid of 4, need 3 (2 excluded: nap x2)`), so a stall is diagnosable rather
than mysterious. That makes the failure *legible*; it does not make titration *work* for that user.

Candidates, none costed:

- **(a) Attribute the nap** — **TAKEN (#219)**, and it was the principled fix. No longer a candidate;
  it is the current behaviour. It did not by itself resolve this question.
- **(b) A duration threshold** (`NAP_EXCLUDE_MIN > 0`) — **PARTLY TAKEN (#219)**, set to 30. Still a
  live lever, but raising it further to buy a decidable cycle is what the do-not-resolve-by below
  forbids. The floor moved because the referent was settled, not because a cycle needed saving.
- **(c) Per-user cadence** — a napper runs a longer cycle, restoring the margin without touching the
  nap predicate at all.
- **(d) Degrade rather than exclude** — admit the night with a recorded caveat, which trades a clean
  basis for a decidable one.

**Do not resolve by:** loosening `NAP_EXCLUDE_MIN` further to make a cycle decidable. That is tuning
the instrument to the outcome. **This still stands after #219, and #219 did not cross it:** the floor
moved because the referent was determined and an amount question replaced a presence question — not
because a cycle needed rescuing. The justification is the test, not the direction of travel.

**Resolve by:** the second user onboarding to the CBT-I module. Q45 is no longer a co-condition.

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

**Premise corrected against `health_connect_record_sources` (2026-08-09, Brief K).** The
identity-distribution measurement (`railway connect health-app-DB`, operator-run 2026-08-08; recorded
in `#188`) falsifies the two-writer sleep premise as written at the top of this question, while
leaving the selector finding intact:

- **Falsified — the Withings-blending premise.** Withings totals **33 rows across all record types
  combined**, first seen **2026-07-15** (ten days after the 2026-07-05 identity cutover), is **absent
  from every contaminated group** (the 11 contaminated sleep groups included), and its Health-Connect
  write access was **revoked 2026-08-08**. There is no night on which "a Withings session happens to be
  the longest" — the scenario has no rows behind it. The four identical-`record_start` mirror nights
  (7/19–7/23) still stand as recorded — an echo, not a rival sensor — but they are not a live blending
  risk, and Samsung, not Withings, is the sole real sleep writer.
- **Untouched — whether `_aggregate_day` is source-blind.** A max-duration selector with **no
  priority** is still source-blind even when only one writer feeds it, and that is a code property this
  brief has **not read**. The (b) `default-untrust` allow-list remains the design and still gates
  `Q82`. What changed is only the premise's factual claim about *who* writes sleep — not the selector's
  behaviour and not this question's severity.

Premise only; **State stays OPEN**. Remaining work unchanged: read `_aggregate_day` against the source
table and wire the allow-list (→ `#175`).

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

## Q86. Does any report-LEVEL required scalar ever get nulled by a real extraction?

`#179` closed the null-on-sparse-row class for **row-level** fields (`ResultItem` +
`FieldConfidence`), and asserted it closed with a `model_fields` walk. It deliberately did **not**
touch the report-level required scalars — `ReportEnvelope.lab_name`, `panel_name_raw`,
`source_completeness` — which stay non-Optional by design. This question is that decision's
watch-point.

**The reasoning for leaving them fail-closed.** A sparse *row* is legitimate (ref-less, censored,
qualitative), so the contract must tolerate a null there. A *report* missing its lab name or panel
identity is not a legitimate sparse shape — it is an extraction that went wrong, and it should be
refused, loudly, now that `#177` makes the refusal readable rather than a blank banner. If one of
these is ever nulled by a live extraction, the correct fix is in **extraction** (the prompt, or the
model, or the document handling), NOT in loosening the contract — loosening would swallow a real
fault the same way the row-level bug bricked a real document.

**Why it is a question and not just a note.** The premise — that these three are always present on a
real report — is an assumption about model output on awkward inputs, and the whole `#177`→`#179`
thread is a record of such assumptions being wrong. It is asserted here, not proven. Only a live
capture settles it: a report whose confirm 422s on `report.lab_name` / `panel_name_raw` /
`source_completeness` would prove a report-level field can be nulled, and would move this from
"correctly fail-closed" to "extraction bug to fix upstream". Until then there is nothing to do —
which is exactly why it is OPEN, not OWED.

**State:** OPEN — no blocker, nothing owed. A pure watch-point resolvable only by a live 422 on a
report-level field; absent that capture there is no action, and pre-emptively loosening these would
be the error `#179`'s own rationale warns against. Owner: Luke (a capture needs a real upload).
Cross-refs `#177`, `#178`, `#179`, `FEEDBACK` §25/§26/§27.

**Not this question:** the row-level class — closed by `#179` and asserted closed. And the urine-ACR
canonical mapping — a separate data-addition track (`LAB_EXTRACTION_SCHEMA §7`), not a contract
question.

---

## Q87. Which cross-repo-parity artefacts are governed, and by what rule?

The shared-loop model has exactly one explicit parity mechanism: **G1** governs the verbatim-
propagated shared block by byte-identity, measured, under `#92`'s paired-obligation protocol. But
several files OUTSIDE the shared block are also expected to stay in parity across `health-app` and
`health-connect-app`, and no store enumerates which, under which mechanism, or with what equivalence
criterion (byte-identity vs behavioural-equivalence). Four such artefacts and their current status
(cross-repo halves are as reported by Brief D / HCA's own stores — not verifiable from this tree):

| Artefact | Parity status |
|----------|---------------|
| shared loop block (`CLAUDE.md`) | **G1-governed** — byte-identity, measured, paired-obligation (`#92`) |
| `.github/workflows/governance-guard.yml` | mirrored byte-identical, **ad hoc** (HCA `#24`) — under no named rule |
| `scripts/check_governance_placeholders.py` | **drifted, undeclared** — health-app's copy carried both a `read()` exit-contract defect and two stale cross-repo docstring sentences, fixed this session |
| `.claude/commands/closeout.md` | **undeclared** — health-app 90 lines (verified here) vs HCA 134 (per Brief D) |

Two of the four are known-drifted, and nothing declares which paths are parity-governed. The checker
is the sharp case: its own comment says it is *one implementation of one rule across every repo*, yet
no register names it a parity artefact and nothing checks the two copies against each other — so a fix
or a docstring correction in one repo silently leaves the other stale, which is exactly the drift this
session's strike was cleaning up.

**Sweep input (`gov/cross-repo-sweep`, 2026-08-08, `#185`).** `#184`'s test, run repo-wide over every
tracked `*.md`/`*.py`, enumerated the whole cross-repo reference surface — 263 matching lines across 17
files — and classified each: **1** struck live state claim (`CLAUDE.md:293`), **1** held for separate
review (`backend/models.py:224`, wire-contract, `#175`/`Q83`), the rest append-only history / structural
grammar / task-pointers. This is the enumeration of *instances*, not the *register* this question asks
for — the register still owes each cross-repo-governed path its governing mechanism and equivalence
criterion. The two undeclared-parity artefacts named above (`check_governance_placeholders.py`,
`.claude/commands/closeout.md`) reappeared in the sweep unchanged, still under no named rule.

**Classifier defect — Brief J mis-classified a migration by its class, not its state (2026-08-09).**
The same sweep (Brief J) classified `backend/migrations/versions/*.py` as **④ LEAVE**, reason
*"immutable migrations, never edited post-land"*. Brief K then edited `c9b8a7d6e5f4` **correctly** — its
own docstring (lines 26–27) declares *"This migration is unreleased (master has not run it); edited in
place rather than stacked per the no-new-migration directive."* J applied the **rule's wording without
reading the file's state**: the class label holds in general and was wrong for this member, so the stale
`no dataOrigin` clause inside that migration sat under a LEAVE verdict and would have survived had Brief
K not grepped the backend independently. This is the **same defect as `#184`, one generation on** — J's
sweep was the *fix* for `#184`'s file-scoped grep, yet it under-reported not by missing a file (its
scope was whole-repo) but by **mis-classifying** one it saw. An enumeration is only as good as its
classifier — which is this question's strongest argument yet: a parity register that assigns a mechanism
per path is worth little if the assignment is read off a file's presumed class rather than its declared
state.

**State:** OPEN — no blocker, nothing owed. The fork: build an explicit artefact-parity register
(each cross-repo file, its governing mechanism, its equivalence criterion) or keep parity ad hoc per
artefact. Not settled here — Brief D scope is to state the question, not build the register. Owner:
Luke (a register spans both repos). Cross-refs `#92` (G1 / paired-obligation), `#182` (evidence is
repo-local, not shared), this session's `#183`/`#184`, HCA `#24` (the workflow mirror).

**Not this question:** the shared block itself (G1-governed, settled) and any single artefact's
current drift (a data point, not the governance gap).

---

## Q88. Empirical calibration of `OVERLAP_THRESHOLD` against real Polar/HC pairs

`reads/aerobic_reads.py` (`#189`) sets `OVERLAP_THRESHOLD = 0.50` of the shorter session's duration as
the "same physical bout" cutoff for read-time cross-source arbitration — a **proposed default, not a
measured one**. It has never been tested against real overlapping Polar/HC captures, because none exist
yet: HC exercise ingestion is held (`#189` Status — HCA forwards no exercise identifier). Set too low,
the rule merges genuinely separate back-to-back bouts into one and suppresses a real session; set too
high, it splits one bout whose two sensors clocked slightly different start/stop and double-counts it.
One tunable constant, one place.

**State:** OPEN — deferred until HC exercise ingestion lands and real Polar/HC pairs exist to measure.
Cross-refs `#189`, `Q83` (distinct dedup class), `Q89`.

---

## Q89. Do HC auto-detected micro-sessions warrant a minimum-duration floor?

Health Connect can auto-detect short activity bouts (sub-5-minute walks) that Polar never records. If
ingestion (step 3, held) admits them, they arrive as `aerobic_sessions` rows with no Polar counterpart —
`canonical` by construction (`#189`) — and could flood the training-load reads with noise the Polar-only
world never carried. The brief's GUARD is explicit: **STOP and report counts + a duration distribution
before filtering anything**; a floor is a chat decision, never a silent filter.

**State:** OPEN — decide at HC ingestion (step 3). No floor exists yet; none is to be added without the
count/distribution evidence first. Cross-refs `#189`, `Q88`.

---

## Q90. HCA question headings carry work-item states — vocabulary drift or a deliberate dialect?

`gen_status_model` flags 6 health-connect-app questions headed `· UNSTARTED` (and `BLOCKED` appears
too) — work-item vocabulary on question headings. The `### State vocabulary` block is byte-identical
across both repos' `CLAUDE.md` (SHA `27337630fca6db03`, verified 2026-08-10) and restricts question
state to `OPEN / OWED / DONE → #N`; `UNSTARTED`/`BLOCKED` are the work-item set. Because the vocabulary
is shared and agreed, this is un-propagated store debt in HCA, not a first-class dialect.

**State:** OPEN — drift, not a decision (Step 1 of the status-parser-gate brief resolved this: blocks
match ⇒ accept-and-flag). The status model accepts and tallies the tokens as off-vocab `drift`, never
coercing or dropping them, so the finding surfaces every run. Resolution is an HCA-side store edit
(re-home those questions' true state, or record why `UNSTARTED` is meant there) — cross-repo, owner
Luke, not actionable from a health-app write session. Cross-refs `#190`, `#193`.

---

## Q92. Should asset verification status gate rendering in code, or stay a curation convention?

Go-live (`#194`) confirmed the #51 enforcement-locus finding: no code reads a reference asset's
`_meta.status` or a lever's `draft_status`. The producer reads only `_meta["version"]` and the frontend
has no status gate, so #51's "nothing renders Section 3 until `human_verified`" is enforced by curation
discipline alone — an unverified asset would render identically to a verified one. Nothing was built to
close this: an enforcement gate is exactly the kind of mechanism the moratorium forbids adding unbidden.

**State:** OPEN. The fork: (a) leave it convention — the promotion event (`ai_draft → human_verified`)
is provenance, and the operator's O2 discipline is the control; or (b) make the producer/gate refuse to
surface an entry whose status is not `human_verified`, turning the convention into a runtime invariant.
(b) is a real mechanism with real cost (a half-verified asset would blank sections mid-review) and needs
a decision before it is built, not a reflex. No current consumer is harmed either way — the live assets
are now all `human_verified`. Cross-refs `#51`, `#194`.

---

## Q93. Garmin recovery route: Health Sync bridge vs server-side connector

Garmin does not write HRV to Health Connect (documented withhold list, corroborated by Apple Health
omission). Two routes to Garmin recovery data:

(a) Health Sync (healthsync.app) — third-party Android app, reads Garmin Connect, writes to Health
Connect incl. HRV RMSSD (5-min intervals within the sleep window per Fitrockr's account of the Garmin
Connect mobile path), VO2 Max, respiration, SpO2. No connector to build; credentials go to the vendor,
not our DB; paid app; their status page documents repeated Garmin-side breakages.

(b) Server-side connector on python-garminconnect — full derived scores (Body Battery, HRV status,
Training Readiness, VO2 Max, training load). Requires the user's Garmin *password* at first login (no
OAuth consent flow), stored refresh token, and we own the arms race.

**State:** OPEN — decision deferred pending Deb's first sync (HR sample density, recordingMethod/device
population for a Garmin writer). Owner: Luke.

---

## Q94. Health Sync as a mirror writer

If route (a) in `Q93` is taken, Garmin Connect and Health Sync both write Garmin-origin records to Health
Connect under different dataOrigin values. This is the Withings-echo case governed by #35/#36/#37 and the
#175 admission allow-list. Requires one-writer-per-data-type configuration or the admission list extended
before Deb syncs, or she double-counts sleep/HR/steps.

**State:** OPEN — contingent on `Q93` taking route (a); must be configured before Deb's first sync or she
double-counts. Owner: Luke.

---

## Q95. Vendor and transport names where the meaning is a role

Single question, multiple targets, distinct cost tiers:

  - cheap    — GitHub repo name `health-connect-app`; app display name
  - moderate — `/integrations/polar/aerobic-sessions` (now serves cross-source arbitrated data);
    `health_connect_syncs`
  - expensive— `samsung_hrv_readings` / `SamsungHRVReading` / `/samsung-hrv/sync` (migration + every
    consumer)
  - one-way  — Android package id `com.anonymous.healthconnectapp` (new app identity: HC grants reset,
    accessibility service re-enable, AsyncStorage token lost)

Rename at natural touch points, not as a campaign. The recovery substrate is first in the queue
regardless — Garmin forces it.

**State:** OPEN — rename at natural touch points, not a campaign; the recovery substrate (`Q93`) is first
in the queue regardless. Owner: Luke.

---

## Q96. `exercise_sessions` is a superseded empty table

Zero rows across all users; `aerobic_sessions` carries the live data (user 1: 32 polar_flow_export, 16
polar_v4). Still holds a unique constraint, two indexes and an FK. Drop candidate.

**State:** OPEN — drop candidate; zero rows across all users, live data lives in `aerobic_sessions`.
Owner: Luke.

---

## Q97. No local strength-training store for any user

Hevy workouts are fetched live from the Hevy API and never persisted; only `hevy_exercise_templates`
exists locally. Consequence: no store to compute strength load trends against, and every view depends on
Hevy uptime plus a valid token. Sits awkwardly beside `capability_observations` and the already-logged
Hevy weight-semantics defect (cable-machine markings, per-limb vs bilateral under one exercise name).

**State:** OPEN — no local strength store; every strength view depends on Hevy uptime + a valid token.
Related: `Q6` (unit-trustworthiness addendum). Owner: Luke.

---

## Q98. HC aerobic rows carry no load

Health Connect exports duration, type and HR but no zone seconds and no cardio_load. Any consumer keying
on cardio_load will be permanently silent for HC-sourced users, not temporarily sparse. Options: derive a
TRIMP-style estimate (requires max and resting HR; not comparable to Polar's cardio_load — a parallel
metric, not a substitute), accept the gap, or take the server-side-connector route in `Q93`.

**State:** OPEN — HC aerobic rows carry no `cardio_load`; consumers keying on it go permanently silent for
HC-sourced users. Owner: Luke.

---

## Q99. Multi-user paths are unexercised

Three accounts (1 Luke, 4 Deb, 5 Cooper). Every provider path, the HCA sync route, and readiness/recovery
logic have only ever executed against user_id 1. Readiness baselines are calibrated to user 1. Not
evidence of a defect — but untested, and Deb's first sync is the first exercise of it. Cooper (ACL
reconstruction ~18 months post-op, contact rugby) is a third profile with onboarding context and no
recovery source.

**State:** OPEN — multi-user paths unexercised; Deb's first sync is the first real exercise of them.
Owner: Luke.

---

## Q100. User 5's stored Hevy key authenticates to an empty account (0 customs, 0 workouts)

The exercise-template seeder (`sync_hevy_templates.py --user-id 5`) synced clean for Cooper (user 5) but
recorded `customs_seen = 0`, unlike Luke (50→55) and Deb (10). Read-only investigation against prod
(2026-08-12), three hypotheses in priority order:

- **H1 — user-id mapping wrong: RULED OUT.** `users.id = 5` is `cooper.eastlake@outlook.com` / Cooper
  Eastlake; the `user_integrations` row (id 11, provider `hevy`) links to user_id 5. Not a mix-up.
- **H2 — stored key is a copy of another user's key: RULED OUT.** Decrypted, user 5's key SHA-256
  (first 12) `b13844046e7d` differs from Luke's `4946bd83a731` and Deb's `2499e2d5b79d`.
- **The account behind the key is empty.** A live `GET /v1/exercise_templates` with user 5's stored key
  returns 451 global defaults and **0 customs**; `GET /v1/workouts/count` returns `{"workout_count": 0}`.
  The key authenticates (200s, defaults returned) but its account holds no workouts and no custom
  templates.

**Empirical boundary (per the scope note):** these negatives attest only to the account the stored key
points at — nothing about any other Hevy account Cooper may hold. Two explanations remain
indistinguishable from our side: (a) the belief that Cooper has customs is stale — this is his account
and it is simply empty; or (b) the stored key was issued from a different, empty Hevy account than the
one holding his real training data. The Hevy API exposes no whoami, and with 0 workouts there is no
in-band identity signal to separate them.

**State:** OPEN — Cooper's stored Hevy key authenticates to an account with 0 customs and 0 workouts;
H1 (mapping) and the copied-key form of H2 are ruled out. Cannot tell from our side whether the belief is
stale (a) or the key is for the wrong account (b). Resolution needs Cooper: confirm the key was generated
from the Hevy account that shows his workouts/customs, and re-issue it from that account if not. Related:
`Q75` (catalogue-freshness), `Q99` (multi-user paths unexercised). Owner: Luke.

---

## Q102. `restrictions[]` is dead data — `is_contraindicated` cannot express the ledger's clinical language

`gather_active_injuries` normalises `restrictions` onto every injury row, and `is_contraindicated` reads it
for exactly one thing: the `"ra_flare" in restrictions` alias. Every other restriction string the ledger
carries is inert. Blocking is driven entirely by `signal_type` + set membership + a `body_part` substring
match, and that vocabulary cannot express what the entries actually say. Evidence, from the live ledger
(read-only Railway, 2026-08-16):

- **Entry 29 — the typing is load-bearing and deliberately wrong.** A documented neural sign is typed
  `mechanical` because typing it `neural` would block its own desensitisation lane: the loaded hinge is
  tolerated and *wanted*, and the aggravator is passive end-range tension. The vocabulary forces a choice
  between an honest `signal_type` and a workable plan, and the entry chose the plan. Any audit that trusts
  `signal_type` as clinical truth is reading a field that has been bent to route around the blocker.
- **Entries 18/29 — a live over-block, and no time limit.** `lunge_single_leg` is contraindicated
  bilaterally via `_ACUTE_TISSUE_BLOCKS["hamstring"]` against a region the user is actively training, and
  nothing expires it — despite the map's own docstring promising a "time-limited" exclusion.
- **Entry 30 — the substring match misses.** `"pes anserine"` does not contain `knee`, so it never reaches
  `_ACUTE_TISSUE_BLOCKS`; its restriction `"deep-flexion unilateral"` enforces nothing.
- **Entry 16 — plain dead text.** `"heavy gripping"` restricts nothing at all.

Design pass owed: a restriction-vocabulary → region-key mapping, plus either a `signal_type` refinement or
per-entry overrides, so an entry can say "neural, but this lane is the treatment" without lying about its
type.

**Explicitly NOT patched on `fix/contra-block-sets`:** the live `lunge_single_leg` over-block stays in
place. Removing it ad hoc trades a known over-block for an unknown under-protection, and it originates in
the very entry whose typing this question argues is unreliable — it belongs to the design pass, not to a
one-line set edit.

**State:** OPEN — no blocker; the audit that spawned it is closed. Owner: Luke. Cross-refs `Q23`
(→ #216), `#216`.

---

## Q103. `lab_results.is_derived` is write-dead — no production path ever sets it true

Found while tracing what writes `is_derived = true`, commissioned as the last open input to Brief
B's placement fork. Nothing does.

- Only two non-test constructions of `LabResult` exist: `routers/labs.py` (the confirm endpoint) and
  `scripts/gen_interpretation_fixture.py` (fixture generation, not a prod path).
- The confirm construction **omits `is_derived` entirely**, so every row written takes the column
  default `false`.
- `is_derived` is absent from the extraction schema, so the model is never asked for it — there is
  no inbound path even in principle.
- The only `true` settings anywhere are three tests assigning the ORM attribute directly.

**The visible consequence:** `context_builder.py`'s stale-derived branch — which appends
`" (stale — derived, carried from an earlier panel)"` when a derived row predates the latest panel —
is unreachable in production. It corrupts nothing and is not a gate. It is recorded so nobody later
debugs it as a mystery, or "fixes" a suffix that never appears by changing something else.

**The fork.** Either the column is dead-by-design — lab-derived markers such as
`testosterone_free_calculated` are ordinary stored rows whose derived-ness is already carried as
reference metadata in `marker_groups.json`, which would make the column redundant and better removed
than left as a trap — or the confirm path was always meant to set it and the wiring was never done.
Nothing in `#58` settles which, and the two answers point opposite ways.

Not urgent, and explicitly not a blocker on Brief B: B's metrics are computed at read time and
stored nowhere, so they fit neither `is_derived` channel. That is precisely what closed B's
placement fork onto a producer output slot of its own rather than a reused flag.

**State:** OPEN — no blocker; the trace that spawned it is complete. Owner: Luke. Cross-refs `#58`
(the column's origin), `#217` (the session that found it), Brief B's placement fork.

---

## Q104. `gates.py`/`rephrase.py` read `marker_canonical.json` directly; post-cutover the JSON is a seed snapshot, stale for any runtime-bound marker

After #220 the canonical map lives in `marker_canonical_entries` and is runtime-mutable via
`POST /labs/canonical/bind`. `backend/interpretation/gates.py` and
`backend/interpretation/rephrase.py` still load `backend/reference/marker_canonical.json` at
import. That file is now the table's migration SEED, so it is stale for every marker bound at
runtime, and these two readers are the only remaining consumers of the stale copy.

**A bound marker does reach them** — this was tested, not assumed, and the phasing rationale
originally offered (that interpretation only covers grouped markers) is false.
`producer._ungrouped()` emits every non-grouped panel marker as a flat row and
`presentation.py:237` builds rephrase fragments from those rows.

**Verified degrades-safe at #220, which is why phasing is disciplined rather than lazy:**

- `rephrase._KNOWN_ENTITIES` is a **detector** allowlist — `rephrase_validator.py` iterates
  the vocabulary and flags only a word that is IN the set and appears in candidate-but-not-source.
  A marker absent from the stale set is never tested, so staleness narrows hallucination
  coverage (a missed detection) but never causes a false rejection.
- `gates._UNIT_ESTABLISHED` is consulted only for markers authored in `safety_thresholds.json`,
  which a freshly-bound marker is not, and the absent case falls back to `value_plausibility`
  (weaker, not wrong).

**The safe-degradation stops holding only if downstream changes:** `_KNOWN_ENTITIES` inverted
to a permit-list, or `_resolve_band` made to hard-require `_UNIT_ESTABLISHED`. Either change
must migrate these readers to the DB in the same stroke.

**Migration cost is asymmetric** and is what decided the phasing: `generate_plain` is called
from an endpoint already holding a `db` and already accepts a `known_entities=` injection param,
so rephrase is nearly free; `_resolve_band` sits ~4 levels below `build_foundation` inside the
pure #86 producer, reached via two paths, with no injection param for the unit map — it needs
a session threaded through ~6 signatures in contract-sensitive machinery.

Resolve by migrating both readers to the DB, or by formalising the JSON as their governed
snapshot and binding those two downstream changes to this question.

**State:** OPEN — blocks nothing today. Owner: Luke. Cross-refs #220 (the cutover), #50
(the guard's origin), #86 (the producer pipeline), #202 (the rephrase validator).

---

## Q105. `weekly_template` stores capacity tokens verbatim, so the same slot can be spelled two ways

`validate_weekly_template` accepts either the `Capacity` enum NAME (`"STABILITY"`) or its VALUE
(`"stability"`), case-insensitively, and stores whichever the client sent. That was a deliberate
read of #221's round-trip gate — `PUT` then `GET` byte-identical — but it means the column can
hold `"STABILITY"` for one user and `"stability"` for another, both valid, and every consumer
must go through `taxonomy.resolve_capacity` rather than comparing strings.

**Why it is not obviously wrong:** the repo's own `measure_key` reasoning (#161) says declare
the set and validate at write, which this does — the set is closed and a non-member is refused.
What is left open is only the SPELLING, and the resolver is the single point that absorbs it.

**Why it may still be wrong:** the risk is a consumer written against the wrong half. A
`slot["capacity"] == region.capacity.value` comparison looks correct and silently never matches
a template written in uppercase. Nothing in the type system prevents that; only the convention
of routing through `resolve_capacity` does. `select_next` already normalises internally for
exactly this reason.

Resolve by either (a) canonicalising on write and downgrading the round-trip gate to
"semantically identical", or (b) keeping verbatim storage and adding a test that no consumer
compares a slot capacity to a string directly.

**State:** OPEN — blocks nothing today; one consumer exists (`select_next`) and it normalises.
Owner: Luke. Cross-refs #221 (the decision), #161 (the declare-the-set precedent).

---

## Q106. How a slot's `minutes` reaches the prescription is undefined

A `weekly_template` slot declares `minutes` (5-180, a session length rather than a weekly
total). Nothing reads it. Region dosing comes from `selection._dosing(capacity, probe=...)`,
which names the physiological windows a recommendation deposits load into and explicitly does
NOT fabricate a quantitative dose — that plugs into the designed-but-unbuilt Banister Form load
model (#18).

Three readings are open and they are not equivalent:

- **`minutes` scales set volume** — the slot's duration drives how much work is prescribed
  within the selected region. Needs the load model, or a cruder volume heuristic that would then
  be hard to retire.
- **`minutes` caps region count per session** — a 15-minute slot fits one region, a 45-minute
  slot three. Buildable today, but it silently couples session length to breadth, which is a
  programming opinion the engine has not otherwise taken.
- **`minutes` is advisory text only** — surfaced to the user, read by nothing. Honest about the
  current state, and the cheapest to reverse.

Deliberately out of scope at #221: the template is a declaration, and consuming it is a separate
lane. The field is validated and stored so the consuming lane needs no migration.

**State:** OPEN — blocks the weekly-resolver lane, nothing else. Owner: Luke. Cross-refs #221
(the declaration), #18 (the load model the first reading depends on), Q105.

**Scope amended (#270).** The resolver's input is no longer `weekly_template` alone: when a
`training_phases` row is open with a `microcycle`, the week-to-date / due-slot resolver reads
`phase.microcycle` (the phase-scoped A/B shape, whose count key is `sessions_per_cycle`) and falls
back to `weekly_template` only at baseline (zero-open). The `minutes` question here is unchanged —
the microcycle slot carries the same `minutes` field with the same three open readings — but the
resolver this question owns must now compose phase-current over profile-baseline, mirroring
phase-now over profile-intent. Landed ≠ live: #270 gives the resolver phase-scoped input; it does
not build the resolver.

**Resolver half discharged (#276).** The week-to-date / due-slot resolver this question's #270 scope
amendment describes is now BUILT — `engine/resolver.py`, `GET /engine/resolver`, and `/engine/next`
default-to-due. Q106 **remains OPEN on `minutes` alone**: the resolver never reads a slot's `minutes`
(asserted by `grep minutes engine/resolver.py` → empty), so the three non-equivalent readings are
untouched and still owed. The consuming lane the field waited for now exists without having consumed
it; the `minutes` fork is LATER per the #275 steer.

---

## Q109. `review_when` supports only the soreness metric, so an injury whose real exit criterion is a different observable has prose and trigger disagreeing

An injury entry's `trajectory.review_when` is written with a `metric` key —
`{"metric": "soreness", "op": "<=", "threshold": 1, "sustained_days": 3}`. **That key is never
read.** Verified in-tree this session: `metric` appears in `injury_trajectory.py` exactly once,
in the module docstring's example, and `_review_message` takes `review_when` and the soreness
series only. Whatever `metric` says, the evaluator watches the generic soreness item for that
injury key.

So `metric` is decorative, and an entry can carry a machine-readable trigger that disagrees with
its own prose without anything detecting the disagreement.

**The reported instance — NOT verified in this session.** The brief that raised this states that
entry id 30 (`injury_pes_anserine_left`) declares in its `detail` that review is gated on point
tenderness, while its `review_when` watches the generic soreness item. That is a live
`user_knowledge_entries` row and is not readable from a Code session; it is recorded here as a
claim to check, not as a finding. Settling it is a read-only prod query for that row's `value`,
via `railway run --service health-app-DB` reading `DATABASE_PUBLIC_URL` (per the secrets rule —
print the row, never the URL).

**The fork, which is live regardless of what row 30 says:**

- **Make `metric` real.** `review_when` gains support for observables other than soreness, which
  means naming what they are and where they are captured. Point tenderness is not a
  `daily_records` column and has no capture surface, so this is a capture-schema change wearing a
  trajectory-evaluation costume.
- **Delete `metric` and correct the prose.** Honest about what the evaluator does, and cheap. The
  cost is that an injury whose genuine exit criterion is not soreness has no machine-readable
  exit criterion at all — its trajectory shape becomes surfacing-only in a weaker sense than #72
  intended.
- **Keep `metric` but validate it.** Refuse an entry whose `metric` is anything but `soreness`,
  so the field stops being able to lie. Smallest change that removes the disagreement, and it
  makes the limitation visible at write time instead of never.

Related but distinct: #226's residual (a defaulted `3` is indistinguishable from a stated one)
also degrades what a `review_when` evaluation is worth. Both are contained by #223 —
surfacing-only means a wrong flag costs a prompt, not a write.

**State:** OPEN — blocks nothing; the evaluator behaves consistently, it just may not be
evaluating what an entry's prose claims. Owner: Luke. Cross-refs #72 (trajectory's scope), #223
(surfacing-only containment), #226 (the other input-quality residual), #224/#225 (the prefill
that feeds the soreness series).

---

## Q111. Should the store represent that two injury entries are one presentation, and if so how?

`injury_pes_anserine_left` (75) and `injury_calf_left` (76) are two rows describing one thing. The
medial gastrocnemius origin sits on the medial femoral condyle, so calf mechanics drive medial knee
loading and the pes anserine is stalled downstream of the calf rather than alongside it. Treating
them as independent gets the sequencing wrong: the knee will not settle while the calf that loads
it is still the live constraint.

The store holds that relationship only as prose in two `detail` fields, where nothing reads it.
`is_contraindicated` evaluates each row independently, so clearing one entry says nothing about the
other, and the coupling survives exactly as long as the operator remembers it.

**Fourth instance of the same shape** — the store records facts, not relationships. Cf. the
duplicated schedule items, the weekly-store split, and the absent phase concept (the next question
in this batch). Each was survivable alone; four of them says the omission is structural rather than
incidental.

The fork:

- **An explicit `coupled_with` key** — names the relationship where an evaluator could read it,
  at the cost of a schema addition and a direction convention (does the calf point at the knee, the
  knee at the calf, or both?).
- **Leave it as prose** — correct if the coupling is genuinely operator knowledge that no code
  should act on; the cost is that it stays unreadable and dies with the memory of it.
- **A group id** — cheapest to write, weakest to query: it asserts that these belong together
  without saying which one drives the other, and the direction is the half that matters here.

**State:** OPEN — blocks nothing today; both entries are active and independently correct, and
the wrong answer is only reachable through a plan that clears the knee while the calf still loads
it. Owner: Luke. Cross-refs #222/#223 (injury resolution, surfacing-only), the phase question below
(the same missing-relationship shape one layer up), Q109 (an entry whose prose outruns what code
reads).

---

## Q114. Should `FEEDBACK.md` get a `CHECKS` arm, and should it guard placeholders or collisions?

`scripts/check_governance_placeholders.py` pins two arms: `DECISIONS_LOG.md` for `#NEXT` and
`OPEN_QUESTIONS.md` for `Q#NEXT`. `FEEDBACK.md` has none. A `§N` written on one branch has nothing
catching a collision with a `§N` written on another, and nothing catching an unresolved token either.
Surfaced by `§31` in this batch, which is safe only because `§30` is still master's max and this branch
is the only writer.

**The fork is not simply "add the missing arm".** The two stores differ in shape, and the uniform answer
may be the wrong one:

- **Adopt `§NEXT` placeholders and add a placeholder arm** — uniform with the other two stores, one
  mechanism to understand, and the guard already knows how to say it. Costs another token to resolve on
  every FEEDBACK-touching branch, on a store whose entries are usually a single line.
- **Keep concrete numbers and add a collision arm instead** — `FEEDBACK.md` is a sorted one-per-line
  list, so a duplicate `§31` is visible on sight in a way an unresolved placeholder in a 700-line
  DECISIONS entry is not. The store's shape already does half the work a placeholder does elsewhere, and a
  collision check catches the failure that can actually reach master here.

Answering it means deciding whether the guard enforces one convention across three stores or the right
convention per store — and the second is more work to maintain but is the honest reading of why the arms
were written differently in the first place.

**State:** OPEN — blocks nothing today; `§31` is uncontested and this branch resolves before it lands.
Owner: Luke. Cross-refs `§20` (hardcoded governance numbers accrue renumber debt), `#162` (the hole an
unseen placeholder rode through, and the reason the guard exists), `#113` (anchored match, not substring
— either arm must anchor on the heading form).

---

## Q115. Supramaximal / repeated-sprint work routes Metabolic-only under `#28` — the neuromuscular cost is discarded

`#28` fixes the four-window load routing:

> strength volume-load → Mechanical + Neuromuscular · HR/zone-derived load → **Metabolic** ·
> sRPE / subjective-vs-objective divergence → Psychological

Strength dual-routes. Nothing else does. So an all-out interval session — 6 × 30 s, or a rugby
match's repeated accelerations — is HR/zone-derived and lands in **Metabolic alone**, in the same
channel as steady-state aerobic work.

Two consequences, both from `#32`'s per-window τ pairs:

| | Assigned | Plausible |
|---|---|---|
| Sprint session recovery constant | Metabolic τ ≈ 4 d | Neuromuscular τ ≈ 6 d, or longer |
| Neuromuscular fatigue accrued | **zero** | substantial |

The cost is not merely mis-weighted, it is **absent from the channel that should carry it**, and
what does get recorded is assigned a faster recovery constant than the tissue takes. **Likely** —
first-principles from the routing rule and the declared τ priors, not measured.

**This is discoverable pre-implementation.** `#32` confirms no Banister/four-window code exists;
the only load computation is `get_training_load()` (ACWR) in `backend/mcp_server.py`, already
recorded as tech-debt retiring on Tier 0. Correcting the routing now costs a spec amendment.
Correcting it after Tier 0 lands costs a migration of computed history.

### What this is not

**Not a fifth window.** `#32`'s revisit clause orders the levers: τ is tuned first, and the
four-window split is reconsidered only after — governed by `#28`'s own revisit clause. This
question proposes a **routing amendment** in the existing taxonomy, mirroring the dual-route
strength already uses. It does not touch the split.

**Not a weighting claim from the proteomics.** The prompting evidence (Olsen et al.,
Cell Rep Med 2026;102988 · PMID 42594877 — 714 of 2,884 plasma proteins moved by three minutes of
sprinting vs 7 by 90 minutes of moderate cycling) is a **stimulus-quality** finding, not a cost
finding, and it confounds intensity with modality, duration, and sampling window — the moderate
session was slower rather than inert, with fatty-acid and liver-derived responses appearing hours
later. Load is a cost currency. Importing an adaptation finding into a fatigue model is the same
category error as conflating `hard` with `expected_load`. The proteomics motivated the look; it is
not the argument. **Source not independently verified — supplied to chat, not retrieved.**

The load argument stands on the routing rule and the τ priors alone.

### The hard part — the discriminator

Correcting the routing requires the ingestion path to distinguish supramaximal/intermittent work
from continuous work. **Average HR cannot do it.** Six 30-second efforts with recovery produce an
unremarkable session mean — which is the same blindness `get_training_load()`'s `hr_avg` has today,
and the reason the defect is invisible in the current metric.

Candidate discriminators, unranked:

- **Catapult SPT3** (`.gt`; 100 Hz IMU, 10 Hz GNSS) — resolves individual accelerations and sprint
  efforts. The only currently-owned instrument that measures the thing directly. Strengthens the
  case for the `.gt` ingestion path independent of field-session capture.
- **Polar zone-time distribution** rather than mean HR — time above a high zone as a proxy for
  intermittency. Cheaper, coarser, already retrievable per `#17` (AccessLink v4) and `#46`
  (per-second exercise-HR).
- **Session-type declaration** at ingestion — honest, zero-inference, but pushes the judgement onto
  the user and is exactly the kind of self-report the platform prefers to instrument around.

*Cross-ref defect, recorded here because this is where the design pass hits it:* `#28`'s Status line
cites **"Polar zone retrieval (#10)"**, but `#10` is *Annotate confounds, don't discount scores* —
Polar retrieval is `#17` / `#46`. The draft of this question inherited the wrong pointer and it was
corrected here before landing; `#28`'s own line is locked append-only text, so **the correction
rides with the routing amendment this question schedules** rather than costing a decision entry of
its own.

No recommendation. The discriminator choice is the substance of the design pass.

### Live impact

The operator plays rugby union in contact and coaches/attends conditioning built on repeated
running efforts. Match play and Tuesday conditioning are both intermittent by nature, so under the
current routing **most of his high-intensity exposure would accrue no neuromuscular fatigue at
all** while carrying a right proximal semimembranosus rupture (full-thickness, partial-width),
a left hamstring provoked specifically by striding and sprinting, and bilateral L5 pars defects.

Neuromuscular is the channel that would otherwise flag accumulating sprint exposure against a
hamstring that is known to fail at exactly that stimulus. That is the concrete cost of the gap.

### Related

- `#28` — four-window taxonomy and routing. This question targets the routing clause only.
- `#32` — per-window independent τ pairs; revisit ordering (τ before split).
- ΔLoad primitive — per-window acute spike detection, carved out to survive ACWR's retirement.
  Sprint work is the spike-prone stimulus that justifies it; a Metabolic-only route sends the
  spike to the wrong window too.

**State:** OPEN — **NOT blocking.** No Banister code exists, so nothing is currently computing a
wrong number; this is a correction to a spec before it is built. **Next action:** design pass on
the discriminator, then a routing amendment to `#28` (supersede-not-amend, per the append-only
rule). Do not open it as part of the Banister implementation itself — the amendment should land
first so the implementation is built to a corrected spec. **That amendment also carries the `#10`
cross-ref correction recorded above** — it is the reason no separate entry was minted for it. Per
`#123` closed questions leave the scan surface, so if this question closes *before*
the routing amendment lands, the cross-ref correction loses its only live home and needs relocating
at that moment. Owner: Luke.

**Annotation (2026-08-25) — D-B removes the migration-cost urgency, not the substance.** This
question's urgency framing was "correct the routing now or pay a migration of computed history
later." The two-level store settled this lane (D-B: `load_events` append-only → `load_metrics`
derived and recomputable) removes that cost: a routing amendment after Tier 0 lands is a recompute
against `load_events`, not a migration. So the *when* relaxes — the amendment no longer has to beat
the transform to master. What does NOT relax is the **substance**: the discriminator that
distinguishes supramaximal/intermittent from continuous work (average HR cannot do it) still has to
be designed, and the routing amendment to `#28` still has to be authored. Recompute-cheap is not
built-for-free. Still OPEN; still owned by the discriminator design pass.

---

## Q117. Are three `expected_load` levels enough, and what does a between-levels session do?

`#233` declares `expected_load` as `light` | `moderate` | `heavy`. The set was earned in-session
and immediately strained: Tuesday seniors was described as **"moderate to heavy"** and landed
between levels.

It was assigned `moderate`, on a specific ground rather than a coin toss — `heavy`'s only v1
consumer marks the **prior day** for scale-back, so `heavy` on Tuesday would shadow Monday gym,
which the operator would reject. That is a defensible call for one row and an uncomfortable one as
a rule: the level was chosen by what the consumer would do with it, not by what the session costs.

**Do not widen the set now.** It is the cheapest thing in this design to reverse, and the right
granularity is learned by use, not by argument. A fourth level added before there is evidence of
where the boundary actually falls would be a vocabulary decision made on one data point.

**Widening later touches more than one axis.** `#233` states that any future axis expressing
training cost — including a training-goal axis — resolves into **this** vocabulary rather than
minting a parallel one. So a fourth level is not a local edit to one field's enum; it changes the
shared cost vocabulary and every consumer that reads it. That is an argument for waiting, not for
never.

The open fork is narrower than "three or four": **what should a genuinely between-levels session
do?** Round toward the consumer's cheaper action (what happened here), round toward caution, or
carry the ambiguity explicitly rather than resolving it at write.

**State:** OPEN — not blocking; three levels are live and one row is knowingly rounded. Owner:
Luke. **Next action:** none until a second between-levels session appears — two instances make a
boundary, one makes an anecdote. Cross-refs `#233` (the vocabulary and the resolve-into rule),
`Q116` (the backfill that writes the first real load values), `#221` (`weekly_template`, the other
store whose vocabulary a cost axis must not fork).

---

## Q118. Health Connect record metadata (`id` / `recordingMethod` / `device`) is forwarded by HCA and accepted-but-dropped by the backend

`workoutMapper` forwards `metadata.id`, `metadata.recordingMethod` and `metadata.device`;
`ExerciseRecord` declared none of them, so Pydantic dropped them. `#234` declares them `Optional`
accept-and-drop so they are first-class attributes rather than `model_extra` (and so `extra="allow"`
does not mask them). **Persistence is the open part.**

Two consumers make them load-bearing. **(1)** `id` is the Health Connect record UUID and would make
`health_connect_record_sources` dedup exact, replacing the synthesized
`(record_type, record_start, source_package)` key — that substitution changes a uniqueness key and is a
`#36`/`#37` ruling, not a schema task, which is why it did not ride a contract-collapse commit.
**(2)** `recordingMethod` (0 UNKNOWN / 1 ACTIVELY_RECORDED / 2 AUTO / 3 MANUAL) and `device` are how a
new writer gets characterised at admission — `#175`'s unimplemented step, and structural under `#236`'s
multi-source contract. Samsung leaves both at sentinel 0 today; Garmin and Apple may not, which is when
the fields start carrying information.

**State:** OPEN — no blocker; the fields are accepted-and-dropped, so nothing is lost that was persisted
before, and nothing yet reads them. Owner: Luke. Cross-refs `#36`, `#37`, `#175`, `#234`, `#236`.

---

## Q119. A windowed/manual backfill path for `/health-connect/sync`, so a contract break outliving the rolling fetch window is still recoverable

`#235` accepts whole-batch rejection as the cost of loudness on the ground that a break is a **gap,
not corruption** — HCA re-reads a rolling window every sync and the upsert never overwrites a stored
value with null, so the next good sync backfills it. That reasoning has a hard edge `#235` records as an
exposure but does not fix: **the self-heal only reaches back as far as the fetch window.** `fetchAllData`
posts `periodDays` (default 7) and the sync handler bounds aggregation to `[today - periodDays, today]`.
A break — the post-deploy `bpm`-`undefined` 422 in `#235`'s OWED is the live candidate — that takes
**longer than the window to repair** leaves a permanent-by-default hole: by the time the fix ships, the
days lost are already outside every subsequent fetch.

`#235`'s mitigations are all **detection** — the Step-4 shape log, the per-stream counts, `unattributed`.
None of them **recovers** the lost span. The missing piece is a **recovery** path: a sync variant with a
caller-supplied window (or explicit date range), so a one-off backfill can re-fetch and re-post an
arbitrary historical span after a break is fixed, independent of the 7-day default.

**The fork — this is why it is a question, not queued work:**
- **Shape.** A `periodDays`/`since` override on the existing `/sync` (smallest surface, but widens a
  hot endpoint's contract), a separate operator-only `/health-connect/backfill` endpoint (clean scope,
  more surface), or a one-off script run against Railway (no endpoint, but no client path and manual).
- **Timing.** Build it **now** (pre-first-break insurance, but speculative — the break may never come and
  the window may always suffice), or **after** the first real break proves the gap reachable (cheaper if
  it never fires, but that is precisely when the permanent-by-default hole is already forming).
- **Auth.** Operator-only by construction — a caller-supplied window is a re-post primitive and must not
  be a general client capability.

**State:** OPEN — **not blocking the merge.** It sharpens `#235`'s post-deploy OWED rather than gating
it: run the real sync first; this question only becomes urgent if that sync 422s **and** the repair
outruns the window. Owner: Luke. Cross-refs `#235` (the exposure and the detection mitigations this
recovers from), `#235`'s post-deploy verification OWED, `#189`/`#175` (the ingestion/admission context a
backfill re-post would flow through), `#236` (a source-neutral contract would give the re-post a stable
target).

---

## Q120. The injury value shape has no onset field — "on record since" is a compensation for that absence, not a design preference

The `type='injury'` value dict carries `body_part`, `side`, `signal_type`, `restrictions[]`, optional
`detail`/`trajectory`/`resolution` — and **no field for when the injury actually began.** `declared_on`
inside `trajectory` is a divergence-timing baseline, not onset, and it is not even reliably that: for the
four api-sourced rows (ids 75–78) it reads `2026-08-19`, an import artefact. `added_at` is no better —
it was **rewritten** for ids 75–78 by a `source` backfill routed through `upsert_knowledge_entry`, which
supersedes by key and mints a NEW row rather than updating in place, so the row's `added_at` is the
backfill date, not first-record date (verified: id 29's `declared_on` 2026-07-13 sits against an
August-2025 right hamstring; id 76's dates sit against a mid-July calf event).

`/injuries` (#100) shows the **chain-earliest `added_at`** — walked back through `superseded_by` to the
root — labelled **"on record since"**, and explicitly NOT "onset" or "age". That is the least-wrong
recoverable value: a record-age floor ("the ledger has held this at least this long"), not onset. **This
is a compensation for the missing field, not a design choice** — recorded here so it does not later read
as a deliberate preference once the context is gone. Three of five active rows recover a real earlier
date via the chain (finger/shoulder to 2026-06-22, pes anserine to 2026-07-13); calf and right hamstring
do not, and no row recovers true onset.

**The fork:** adding an `onset`/`injured_on` field to the value shape is a **value-shape change with a
backfill of its own** — every historical row would need an onset supplied (operator recall, since no
field holds it), and the backfill would route through the same `upsert_knowledge_entry` supersession
path that destroyed the age information in the first place, so it needs the #103/#116 verify-then-write
discipline. Whether onset is even worth capturing depends on what reads it: nothing does today.

**State:** OPEN — not blocking; `/injuries` compensates read-side and asserts nothing false. Owner:
Luke. **Next action:** none until a consumer needs true onset (the backfill-audit lane below is the
first candidate — it is a human-recall exercise precisely because this field is absent). Cross-refs
`#100`, `#222`/`#223`, `#233` (supersession-by-key as a propagation/rewrite source).

---

## Q121. Tier-0 load transform modelling gaps — weighted-bodyweight, flat BW fraction, non-rep NM, half-point RIR

The gate-2 `load_events` transform (`formula_version 'tier0-v1'`, DECISIONS_LOG #241)
shipped four deliberate Tier-0 simplifications. Each is **surfaced, not hidden** — none is a
defect in the landed transform. (Distinct from `#243`, a genuine defect — the bodyweight coalesce
leaking into the non-rep branch — already fixed in-version.) **Gap 4 (flat bodyweight fraction) is
now RESOLVED — built as `#245` (`bw_fraction`), promoted build-now ahead of gate 3.** Three honest
priors remain below.

- **Weighted-bodyweight undercount.** `effective_weight = weight_kg` when a plate is logged, else
  `BODYWEIGHT_KG` (102). A weighted pull-up (+20 kg) therefore scores on 20 kg, not ~122 kg — the
  body is the load and the plate is the increment, but Tier 0 has no per-template bodyweight-movement
  flag to know that. A pure-bodyweight set (no plate) correctly uses `BODYWEIGHT_KG`; a barbell lift
  correctly uses the bar load. Only the *weighted-bodyweight* case undercounts. Fix needs a
  per-template "adds bodyweight" tag (a template annotation, like `laterality`).
- **Flat bodyweight fraction — RESOLVED `#245` (2026-08-26).** Built as `hevy_exercise_templates.bw_fraction`:
  a rep set with `weight_kg` NULL/0 scores `BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0)`; a logged weight
  is never scaled. **Tagging amendments (2026-08-26, operator):** Weighted Dead Bug `bw_fraction` revised
  **0.25 → 0.1** (undercount-preferred for the unweighted pattern; logged-weight sets unchanged — that load
  is the overhead hold). Effective at the next recompute; no recompute forced now. The 13 Jul reconciliation
  fixture is **unaffected** — it embeds `0.25` as a test convention to guard the formula, not a prod tag.
  Data provenance: the 13 Jul `0kg×60` / `0kg×50` dead-bug sets are **confirmed genuine reps** (operator),
  so the fixture's rep interpretation is confirmed, not assumed. The additive weighted-bodyweight case (bodyweight + plate) is NOT covered by `#245` and
  remains the **weighted-bodyweight** gap above (it needs the e1RM fit to read the same coalesced load —
  a `formula_version` consideration, and the Hevy assisted-set sign is still UNVERIFIED). Original note
  kept for provenance: `_effective_weight` priced every pure-bodyweight
  REP set at `BODYWEIGHT_KG × 1.0`, but the loaded fraction is class-dependent: force-plate data puts
  it at ~0.65 for horizontal push/row (push-up ~0.64 top / ~0.75 bottom; the coaching "85%" is not
  supported), ~0.9 lower-body BW (shanks unloaded), ~0.95 hanging (pull-up/dip), ~0.5
  kneeling/regressed. So Mechanical **over**counts push-up-class work by ~45%, lower-body BW by
  ~10–15%, hanging by ~5%. **NM is unaffected** — the per-template e1RM is fitted from the same
  coalesce, so the fraction cancels in `I = effective_weight / e1RM`. Within-class precision sits
  inside `m()`/`K_dist`/`K_time` prior noise once smoothed through the ~10 d Mechanical τ (`#32`); the
  *class-level* 1.0-vs-0.65 gap does not. **Shares the weighted-bodyweight remedy:** one per-template
  annotation carrying both "adds bodyweight" and a `bw_fraction` (3–4 class defaults,
  operator-overridable; no separate leverage axis — Hevy already splits elevated/decline/ring
  variants into distinct templates). Weighted: `BW × fraction + weight_kg`; assisted:
  `BW × fraction − weight_kg` (the sign convention on Hevy's assisted set types is **UNVERIFIED** —
  read it off `hevy_workouts.raw` before coding). `#243` already scoped the coalesce to REP sets only
  (weight-NULL non-rep skips), so a `bw_fraction` added to `_effective_weight` touches only rep-based
  bodyweight — confirmed this session.
- **Non-rep NM = 0.** Carries/sleds and timed holds bridge into Mechanical (D-D `K_dist`/`K_time`)
  but contribute **zero** Neuromuscular. Flagged arguable in D-D for maximal sled efforts, which
  carry a real velocity/RFD demand a flat 0 discards.
- **Half-point RIR banding.** RIR = **`floor`(10 − RPE)** (pinned `#244`; RPE 8.5 → RIR 1 → m 1.30) —
  a half point bands DOWN to the harder tier. The m()/f() tables are integer-keyed, so a half point is
  banded rather than interpolated. Deterministic and documented, but a Tier-1 transform may interpolate
  f/m across the half instead (a `formula_version` bump).

**State:** OPEN — not blocking; the transform is correct and honest at Tier 0, and `provenance`
records where each gap bit. **Next action:** none until Tier 1; the per-template annotation carrying
both "adds bodyweight" and `bw_fraction` is the first candidate — it resolves the weighted-bodyweight
undercount and the flat-fraction overcount in one operator-annotation path (like `laterality`), and
verify the Hevy assisted-type sign against `hevy_workouts.raw` before coding it. Owner: Luke.
Cross-refs `#241` (the gate-2 entry), `#243` (the coalesce non-rep-leak fix — scoped it to rep sets),
`#28`/`#32` (D-A/D-C/D-D), `#74`/`#76` (template tags).

---

## Q124. Field-session (Catapult/GPS) ingestion into `aerobic_sessions`

`#251`'s transform scores whatever rows exist in `aerobic_sessions`, today seeded from Polar Flow export
(HR-zone based) and provisioned for Health Connect. Field sessions instrumented by GPS/accelerometer
units (e.g. Catapult) carry an external-load model (PlayerLoad, high-speed-running distance) that is NOT
HR-zone based and would not populate `z*_seconds`, so an Edwards TRIMP cannot see them. Open: is field-
session external load a fourth ingestion into `aerobic_sessions` (with a distinct sub-formula and its own
`formula_version`), a separate source table, or out of the Metabolic window entirely (a different load
axis)? Out of S1 scope — recorded so the ledger gap is named, not silently narrowed to HR-only aerobic
work.

**State:** OPEN

**Cross-reference (#365, Q203).** #365 makes the Catapult SPT3 the preferred field source, optional and not guaranteed. The missing-data side of that (an expected SPT absent) is Q203.

---

## Q126. `_sleep_score` has no total-sleep-adequacy or awakening term — it clamps to 10 on a badly-disrupted night

`_sleep_score(deep, rem, total)` (`backend/routers/health_connect.py`) is purely a quality ratio,
`1 + round((deep + rem) / total / 0.35 * 9)`, clamped to [1, 10]. It reads no total-sleep-adequacy term
(a 402-min night and a 240-min night with the same deep+rem proportion score identically) and no awakening
/ WASO term. On the verified 2026-08-30 back-pain night — ~2 h awake — it returns 10 both **pre- and
post-#254**: post-union, deep 15 + rem 158 over TST 402 still pegs the `(deep+rem)/total ÷ 0.35` clamp.
The #254 union fix corrected the TST the score divides by, but did **not** touch the formula, so the
clamp behaviour is unchanged by design. The score feeds the same MCP (`actual_sleep_time_minutes`
siblings) and AI-context readers as the duration, so a 10 on a wrecked night misinforms both surfaces.
Separate ticket from #254 (value-fix only, GUARD: do not touch `_sleep_score`). A fix adds a
total-adequacy and/or awakening term; the exact form (and whether it stays a 1–10 clamp) is undecided.

**State:** OPEN

---

## Q128. Union-total sleep permissiveness — 429 (union) vs Samsung 402 (+27): track or tighten

The #254 union rule computes TST as the union of **all** asleep stage-intervals across the wake-date's
session set — "any session says asleep at minute *t* → *t* is asleep." On the verified 2026-08-30 night
this yielded `sleep_duration_minutes = 429` vs Samsung's own consolidated total of **402** (+27), because
the union is strictly **more permissive** than Samsung's internal merge: where Samsung dropped a contested
seam minute to AWAKE/OUT-OF-BED, a single overlapping session still labelling it asleep pulls it back into
the union. This is a property of the **total**, distinct from the breakdown-coherence fix (#256, which is
total-invariant by design and left this untouched) and from Q126 (`_sleep_score`'s missing adequacy term,
which reads whatever TST this decides). Open: is the union total's permissiveness acceptable as-is (it is
already reference-only — titration scores off the diary, #256 scope note), or should the total tighten
toward a majority/consensus or a source-preferred merge? A tightening is a **new ticket touching the total**
(GUARD on #256: do not fold total changes into the breakdown fix) — it would revisit #254's union rule, not
#256's partition. No code owed here yet; this is the watch-point #256 promised.

**State:** OPEN

---

## Q129. Garmin sleep source — pull server-side or leave on HC?

Garmin sleep currently reaches the platform only via the companion app → Health Connect →
`health_connect_syncs`, coupling it to the Samsung-purposed companion app and the phone chain the
garth pull otherwise escapes. Option A: leave on HC (official, resilient, but companion-app-coupled).
Option B: pull sleep via garth and extend arbitration to sleep (severs the coupling, richer
Garmin-native sleep, but widens the fragile garth dependency to a commodity signal and requires
building sleep source-arbitration — none exists today). Household tolerates A; B2B goes fully
server-side/official and moots it. Decide on its own merits; do NOT build either way inside the
ingestion lane (#258/#259).

**State:** OPEN

---

## Q131. HRV `_SOURCE_RANK` is currently unexercised

`recovery_reads._SOURCE_RANK` ranks garmin > samsung, but per-user overlap is nil today (Deb=Garmin,
Luke=Samsung), so no night is actually contested. Revisit the ranking only if a single user acquires
both sources.

**State:** OPEN

---

## Q132. Garmin garth refresh-token re-login cadence

Observe how often Garmin invalidates the refresh token (forcing a manual `garmin_login.py` re-run).
Informs whether silent re-auth is tolerable or needs an operator nudge/alert on the "reconnect Garmin"
424 state.

**State:** OPEN

---

## Q134. Full `/recovery/summary` restructure — retire the Samsung-block HRV duplication + source-agnostic sleep read

#265 added an `hrv` block additively and left the device-shaped `samsung` and `health_connect` blocks
byte-for-byte, because repointing them breaks the current frontend contract. The follow-on: once the
frontend reads the `hrv` block, retire the `samsung` block's HRV duplication (its `hrv_ms`/`trend`/
`baseline_*` overlap the new block) and introduce a source-agnostic SLEEP read across HC + Samsung
(sleep still lives only in `samsung_hrv_readings`). Also decide `has_data` semantics at that point —
whether it should reflect the `hrv` block (a Garmin-only user currently reads `has_data=false` despite a
populated `hrv` block). Requires a coordinated frontend change (health-connect-app), so it is a
cross-surface restructure, not a backend-only edit.

**State:** OPEN (deferred — blocks on frontend readiness to consume the `hrv` block)

---

## Q135. Drop `samsung_hrv_readings.hrv_ms` once dual-write is proven and the frontend reads the `hrv` block

#266 retains `samsung_hrv_readings.hrv_ms` (dual-write, not move) so the `samsung` block keeps working
and no destructive column drop rides this brief. Once (a) the dual-write is proven live (new Samsung
nights present in both tables) and the backfill has run, and (b) the frontend reads HRV from the `hrv`
block rather than the `samsung` block, `hrv_ms` becomes redundant and can be dropped — `samsung_hrv_readings`
then holds sleep only. Gated on Q134 (the frontend read-path move) and on the live parity check.

**State:** OPEN (deferred — gated on Q134 + live dual-write/backfill parity)

---

## Q136. `SamsungHRVReading` model constraint drift — declares `uq_samsung_hrv_user_date`, live is `uq_samsung_hrv_user_date_context`

`models.SamsungHRVReading` still declares `UniqueConstraint("user_id", "captured_at",
name="uq_samsung_hrv_user_date")`, but migration `e1f2a3b4c5d6` DROPPED that key and ADDED
`uq_samsung_hrv_user_date_context` (user_id, captured_at, context). The model was never updated. Two
live consequences: (1) `routers/samsung_hrv.py` upserts with `constraint="uq_samsung_hrv_user_date_context"`
— a name that does NOT exist in the create_all'd SQLite test DB, so the `/samsung-hrv/sync` endpoint's
DB path is untestable on the test substrate (only the pydantic bounds validator is covered today); (2) a
fresh clone's tests enforce a 2-column uniqueness prod does not have (and vice-versa), so the substrate
disagrees with prod on how many rows a (user, night) can hold. Fix: update the model's `UniqueConstraint`
to `(user_id, captured_at, context)` to match the live schema (no migration — the DB is already correct).
Found while building the Q130 backfill (the collapse logic depends on which constraint is live); flagged,
not fixed, to keep this brief scoped.

**State:** OPEN

---

## Q138. Session-close should sweep OWED/BLOCKED BRANCHES rows against merge/ref reality

**State:** OPEN — On 2026-09-08 a session-close sweep found **6 of 10** OWED `BRANCHES` rows were stale: the named branch had a master merge commit (work long since landed) or no remote ref at all, yet the row still read OWED with an unrun loop. `feat/hub-shell` was the sharp case — OWED "NOT merged" while `001df4c` had merged it on 2026-08-02 and `#162`/`Q63` were resolved on master. The fruit/ageing scan reads the questions store only; it does not cross-check branch rows against `git`. **The ask:** a close-out check that, for every OWED (and BLOCKED) `BRANCHES` row, flags rows whose named branch (a) is absent from `origin` and (b) has its work on master — patch-id via `git cherry origin/master`, or the row's cited SHA an ancestor of master — so a landed-but-unflipped row surfaces automatically instead of waiting for a manual sweep. Not blocking; a governance-hygiene detector, kin to `scripts/check_governance_placeholders.py` but for branch-row staleness. Owner: Luke / a tooling session. Cross-refs `#123` (below-the-fold scan surface), the `stale`/`land` patch-id disposition in `CLAUDE.md`.

---

## Q139. Interpretation increment 3 — frontend tap-to-thread surface (build-sequence step 5)

**State:** OPEN — The backend spine of increment 3 landed (`#268`): `POST /interpretation/education-thread`,
the scoped seed builder, the fail-closed output guard, and the three evals. What remains to make the
feature user-complete is the increment-3 brief's **STEP 5** (the frontend; not increment 5/go-live, which is DONE): make the surfaced lever nodes in the interpretation
view tappable, open a scoped thread panel/route distinct from general chat, POST the client-held turn
history (Fork A stateless — re-send each call, hold no persistent history), and render the returned
`text`/`source`/`deflected`. Deliberately split out because the frontend is a surface chat cannot verify
(the unseeable-surface rule) — it needs its own verification against the served bundle (`#121`), not a
backend-test green. The contract is fixed by the endpoint: `{lever_key, marker_canonical, messages[]}` in,
a 422 structural refusal for an untappable lever, `{text, source, deflected}` out. Owner: Luke / a frontend
session. Cross-refs `#49` (design lock), `#47` (education boundary), `#268` (the spine), and the
"Selectable term definitions / glossary" ROADMAP row (kin surface, possible fold-in).

---

## Q140. Naive `date.today()` in AEST-computing prod paths — two live skew sites (from Q137 step 4)

Q137's prod-code sweep found three `backend/` non-test `date.today()` sites; two compute a **user-facing**
"today" in UTC while the app's canon is `_local_day()` (AEST, Q42 single source), so both skew by a day in the
evening-AEST / prior-UTC-day window (AEST = UTC+10):

- `routers/knowledge.py:315` — `expire_stale_entries`: `today = date.today()`, then filters `expires_at < today`.
  Live via `routers/chat.py:677` and `routers/knowledge.py:603`. Because AEST leads UTC, a knowledge entry that
  should expire on the AEST calendar day stays `active` up to ~10h too long until UTC rolls over. Surfacing /
  suppression only; no data corruption; self-heals at the next UTC midnight.
- `injury_trajectory.py:144` — `evaluate(user_id, db, today=None)`: takes an injected date, but the sole live
  caller `mcp_server.py:486` passes none, so the UTC `date.today()` fallback fires. The divergence / review
  windows are then anchored on a UTC "today" in the MCP plan-review surface. Surfacing only (returns messages,
  changes nothing).

Not live: `cbti/replay.py:349` (`d1 = block.closed_on or date.today()`) is inside `main()` under
`if __name__ == "__main__"` — an operator replay CLI, not a request path; at most an off-by-one on an open-block
window end.

Fix for both live sites: `_local_day()`, or inject an AEST `today` at the caller. Deliberately scoped OUT of Q137
(test-only, single concern). Not blocking — boundary-window, self-healing, no irreversible write (#166 gate:
non-destructive → ship-with-watch class, not a live-probe gate). Owner: Luke / a code session.

**State:** OPEN

---

## Q141. What observed quantity is `model_forecast` a prediction of, on what scale, and does anything write it?

Raised deferring the actual-vs-forecast half of Visuals increment 2 (the ReadinessChart). The brief specced
`morning_readiness` (actual) vs `model_forecast` (forecast) as two lines with a residual (actual − forecast) as
"the model's accuracy view". Three facts make that unbuildable today:

- **Scale mismatch.** `daily_records.morning_readiness` is a 1–5 ordinal self-report (`ge=1, le=5`, tagged in
  `models.py` "primary OUTCOME"); `model_forecast` is a 0–10 float (`context_builder.py` renders it `{mf:.1f}/10`,
  the `naive_baseline` space). Subtracting a 0–10 forecast from a 1–5 Likert is not a residual, and linearly
  mapping the five-point ordinal onto a continuous 0–10 is false precision that would pass every render test.
- **Written nowhere.** No non-test assignment to `DailyRecord.model_forecast` exists (`grep` clean); the column is
  null in prod, so the forecast line is empty — the "accuracy view" would be a chart of nothing.
- **Undecided semantics.** What the forecast is a prediction OF — which observed quantity, on which scale — is not
  recorded in any store. `context_builder`'s guardrail frames the model's job as "beat the naive baseline on this
  user's data", which points at `naive_baseline` (0–10) as the comparison partner, but that is an inference, not a
  decision.

Increment 2 therefore ships observed-only: `/series/readiness` carries `morning_readiness` + `passive_hrv_ms`, and
the ReadinessChart is small multiples on honest per-series scales — no forecast field, no residual. A
forecast-vs-actual chart is a real feature and lands as its own increment once this resolves: pin the predicted
quantity + scale, wire a writer for `model_forecast`, then build. Owner: Luke / chat (data-meaning), then a code
session.

**State:** OPEN

---

## Q142. Imaging / DEXA ingestion target — where do narrative studies and structured DEXA numerics land?

Raised deferring the imaging half of the 2026-08/09 lab batch (#280). `imaging_extraction_new_batch.json` holds three
studies: MRI pituitary (no lesion — narrative), US urinary tract (chronic bladder outlet obstruction, PVR 234 mL,
11 mm renal cyst — narrative), and a baseline DEXA (total-body BMD T +1.8; structured body-composition numerics). No
landed home exists today:

- **Narrative MRI/US** need the generic `health_events` parent, deferred at #43/#52 — there is no table for a narrative
  study.
- **DEXA numerics** are structured (BMD, T/Z-score, lean/fat mass, RSMI, segmental) and could seed a numeric series,
  but NOT `lab_results` — DEXA is not a lab panel, and forcing it would require declaring ~15 new canonicals and misusing
  a lab table for imaging (#280 refused this; the handoff itself warns against it).

Options: (a) wait for the `health_events` parent, land all three there; (b) a dedicated imaging/DEXA schema — a migration,
so Merge disposition hold (a), full human review; (c) a DEXA-only numeric series now, narrative MRI/US still deferred.
Operator deferred the decision this session. Owner: Luke / chat (data-meaning + schema), then a code session.

**State:** OPEN

---

## Q143. MCP temporal re-anchoring + failure acknowledgement — the out-of-repo halves flagged by #281

Raised closing the decompression-schedule verify-then-fix (#281). Two halves sit outside `health-app` and were flagged
rather than forced into the tree:

- **Per-turn `as_of` re-anchor + day-boundary re-pull (WS3).** #281 stamped every MCP tool output with a visible
  Brisbane `as_of` — the in-repo half. But a thread persisting across calendar days also needs the MCP CLIENT to
  re-inject "now" into context each turn, and to force a fresh readiness/schedule pull when the gap since last
  interaction crosses a day boundary. Those live at the chat/client/orchestration layer (Claude Desktop / mobile /
  companion), not in health-app. Until they exist, the tool-side `as_of` is the only anchor — present but passive (the
  model must read it). If the client gains its own per-turn datetime injection, the tool stamp becomes
  belt-and-suspenders (see #281 "do not revisit unless").

- **Failure acknowledgement discipline (WS4).** The observed session narrated "saved / locked" while calls returned
  `✗`. **In-repo substrate DONE → #283 (Q143a); in-repo GATE DONE → #284.** #283 made each write's outcome
  machine-checkable (`ChatResponse.write_results`, one `{saved, reason_code, reason, key}` per `<knowledge_update>`
  block, per-row never a roll-up). #284 closed the loop on the NARRATION server-side: `/chat` regenerates the reply
  after a failed write (bounded pass-2, affordance type-derived from `reason_code`) and appends an always-on
  deterministic footer computed from `write_results`, so the reply the client renders is already truthful with a hard
  floor. **The #283/this-item claim that "`frontend/` has no chat component and no `/chat` caller" was WRONG — a grep
  miss (FEEDBACK §42):** `frontend/src/components/ChatPanel.jsx:78` posts `api.post('/chat', …)` and renders
  `data.response` verbatim (FEEDBACK §36, from #273, had already cited `ChatPanel.jsx` by name). So Luke drives chat
  from the web app, and the truthful `response` + footer reach it with no client change. The out-of-repo consuming gate
  is therefore **no longer REQUIRED for truthfulness** — it becomes belt-and-suspenders; an agent-prompt rule surfacing
  `saved:false` before any success claim stays a nice-to-have at the orchestration layer. **Residual (recorded, not a
  blocker):** on an all-SAVED turn no pass-2 fires, so a prose claim about a write the model never EMITTED as a block is
  not regenerated away; the always-on footer mitigates it (the `✓ N saved` tally, from `write_results`, gives the reader
  a cross-check against an over-claiming sentence) but does not fully catch it. **Still pending (in-repo option):**
  extend `write_results` + narrate-after-write to the Hevy routine/exercise lanes — same shape, their own codes
  (#283/#284), not built.

Owner: Luke / chat + client-layer. The WS3 per-turn re-anchor remains out-of-repo; the WS4 in-repo substrate (#283) and
gate (#284) both landed, and the out-of-repo consuming gate is now optional rather than the only home for the
discipline. Q143 stays OPEN on WS3 (and the Hevy-lane option).

**State:** OPEN

---

## Q145. Directly-supplied (corrupted/typo'd) exercise_template_id is not catalogue-validated on create

Verify-don't-patch finding (WED decompression routine, Concern A). The right-side entry carried
`b4bab549-a143-4166-9615-249185e5a4a2` vs the left's `b4bab549-a143-4186-9615-249165e5a4a2` — two digits
off, a model typo. `_resolve_missing_ids` only fills ids for TITLE-only exercises; an entry that already
carries an id is passed straight through (#60), so a corrupted-but-format-valid id is NOT caught as
`unresolved_exercise` — it reaches Hevy and fails as `create_failed` (Hevy rejects the unknown id). So the
failure IS surfaced honestly (never silent, never a duplicate), just via the Hevy-rejection path, not the
catalogue resolver. Pinned by `test_hevy_routine_numeric_and_folder.py::test_wed_directly_supplied_corrupted_id_is_create_failed_not_unresolved`.

Open fork: should a directly-supplied `exercise_template_id` be validated against the local catalogue
before the POST (surfacing a typo as `unresolved_exercise` with candidate suggestions, like the title path),
or is the current create_failed-via-Hevy path good enough? Validating pre-POST would name the typo'd exercise
and could suggest the intended id, but adds a catalogue lookup on every id-bearing create. Per the brief:
report, don't patch — Luke's call.

**State:** OPEN

---

## Q147. Should the deterministic numeric floor extend to the workout READ/parse path?

#289 put a numeric floor on the routine-CREATE (write) path. The workout READ/parse path (`load_events`) also
consumes set numerics (weight, reps, rpe → load calcs). A non-finite value arriving from Hevy's read side
(or a bad stored value) could poison a load computation silently rather than 400ing. Open: whether to apply
the same finite-or-reject discipline on the read/parse path, or whether the read path already guards
(e.g. `_e1rm`, RIR bands) against NaN/None. Not investigated this session (Concern A was the write path).

**State:** OPEN

---

## Q148. Progression-tiered lifecycle, §G measure declaration, and proactive §G surfacing (DEFERRED from #290)

Three follow-ons deliberately not built in the loose consumer (#290):

- **(a) Tight consumer — screen→train lifecycle.** A per-region screen→train lifecycle where a passing
  screen auto-promotes the region to trainable AND the screen result selects a progression tier
  (regression → full expression), especially §E/§G (e.g. hop: pogo → line hops → bounding → depth). Needs
  progression-tiered pool tagging that does not exist. The rotation/recency rule in #290 is the intended
  hook point for tier selection.
- **(b) Declare §G measures on the taxonomy.** Give `sit_to_rise`, `gait_speed`, `grip_strength`,
  `single_leg_balance_eyes_closed`, `loaded_carry_capacity_bw` a `Region.measures` entry so §G screens via
  the Measure layer instead of #290's honest "no instrument yet" stub. Additive, no migration. Gated on
  domain grounding — some clinical-adjacent (practitioner input), some sport/longevity norms — which is why
  #290 did NOT invent them (they are `Confidence.GUESSING`/`needs_norm`).
- **(c) Proactive §G surfacing.** `compute_probe_queue` excludes `queue_eligible=False` regions, so #290's
  consumer only handles §G reactively (as a `fortify` target). Making the engine actively schedule §G
  screens is an upstream `compute_probe_queue` change, out of #290's scope.

Revisit once the loose router has real screen data flowing and tags are being confirmed.

**State:** OPEN (DEFERRED — logged not built with #290)

---

## Q150. Oxygenation awareness capture — overnight SpO2 as a series, not a scalar [SAFETY-RELEVANT]

Retrospective, morning-review awareness of overnight oxygenation for a CPAP-dependent user
(ResMed AirMini — sealed, no SpO2 input, no clinician-grade export; verified dead end). On
current hardware the Samsung wrist/ring path is the ONLY oxygenation source. Hardware path
forward is owned separately, deliberately not specced here.

**What this is:** nightly SpO2 MINIMUM, count/duration of dips below a threshold (88% clinical
convention, user-configurable), and dip timestamps — so mask-off / mask-shift desaturations
are visible after the fact and trends are trackable over weeks.

**Hard scope boundary — must be enforced in UI + framing:** NOT real-time alerting (cannot and
must not wake the user), NOT a safety device, NOT a mask-failure backstop. The CPAP and its own
alarms are the safety layer; this is pattern-awareness only, never positioned or relied on
otherwise.

**Storage shape (decided-in-brief, gated only on build):** series, not a scalar — a
`hrv_readings`/`hrv_samples`-style parent+child (see `models.py:482–533`), NOT a mean.
`SamsungHRVReading.spo2_average_pct` (`models.py:476`) is ACTIVELY WRONG for this purpose: a
nightly mean masks the dips by construction. It is currently surfaced as the SpO2 figure in
`context_builder.py:805`, `routers/recovery.py:65`, `routers/health.py:52`, and
`mcp_server.py` (×2) — every one of those reads the masking average. The device-agnostic target
already reserves the metric: `'spo2'` is in `CANONICAL_METRIC_TYPES` (SCHEMA.md). SpO2 is
therefore pulled OUT of the trim decision entirely — neither keep nor trim: it is REBUILD.

**BLOCKING GATE — scraper-trace capability test (owned by `health-connect-app`, NOT answerable
from this tree):** can the accessibility scraper extract the SAMPLE SERIES behind Samsung
Health's sleep-oxygenation graph, or only the rendered summary tile?
  - Trace reachable → event-detection (min + time-below + timestamps) is buildable → full scope.
  - Summary only → best achievable is a coarse nightly minimum → ship that for TREND only;
    event-detail deferred to next-hardware.
  HC path is insufficient regardless (sparse daytime-mixed spot reads, gaps span mask-off
  windows — verified). Cannot found event-detection on spots.

  **In-tree evidence, not an answer:** as of the last integration the scraper POSTs only a scalar
  `spo2_average_pct` to `routers/samsung_hrv.py` (payload + bounds at `samsung_hrv.py:49,72`) —
  no SpO2 series field exists. That places the scraper on the "summary" side *today*, but it does
  NOT settle the ceiling: a scraper that aggregates a series it CAN see is indistinguishable from
  one that can only read the tile, from this end. Only a trace test against a live sleep-oxygenation
  graph in `health-connect-app` distinguishes them. That test is the gate; it is unseeable here.

**GUARDRAIL — false reassurance is the critical failure mode for this user:** never render a
night "fine"/green on sparse or thin coverage. Absence of a recorded dip is NOT absence of a dip.
Every oxygenation surface must show coverage/confidence and degrade to "minimum recorded: X%,
coverage thin" rather than an unearned all-clear.

**Value even at coarse resolution:** the AirMini gives zero SpO2 visibility. A consistent nightly
minimum alone surfaces mask-effectiveness drift over weeks, clustering of bad nights, and the
effect of a mask/cushion change — the near-term win is retrospective trend.

**Related:** skin-temp + respiration overnight traces are the same "capture withheld Samsung
traces" family, same two-gate logic (withheld-from-HC + scraper-reachable), lower priority —
separate ticket. The trim decision (SpO2 excised per above) is not yet registered in this repo.

**RESOLVES WHEN:** trace-test answered (in `health-connect-app`); capture built to whatever
resolution that allows; storage in series shape; guardrail enforced; SpO2 removed from the trim
scope once that ticket lands. Full event-detection may remain gated on next hardware.

**State:** OPEN — blocked on the `health-connect-app` scraper-trace test. Storage is a schema
migration → § Merge disposition hold (a): full human review, no self-merge. Not built this
session (gate unanswered + shape gate-dependent + migration hold).

---

## Q151. recovery.py — unmounted canonical-recovery surface: adopt with a consumer or delete

`routers/recovery.py` carries a working source-agnostic `hrv` block (built on `canonical_hrv`)
alongside the Samsung + HealthConnect blocks, but its router is NOT mounted in `main.py` — nothing
consumes `/recovery/summary`. It partially duplicates `/health/summary` and the MCP recovery tool.
Deliberately left unmounted in the #291 HRV-consumption rewire (Q130): the Garmin-into-readiness
goal is already delivered by the checkin / current_state / MCP-readiness / series rewires, so
mounting it would ship a live, testable, maintainable endpoint for zero consumers — surface sprawl
this task did not need. Decide adopt-or-delete as its own scoped call: adopt WITH a defined consumer
(a frontend/dashboard that reads the `hrv` block), or delete the module.

**State:** OPEN (deferred — decide when a consumer is proposed, or delete)

---

## Q152. Historical `daily_records.passive_hrv_ms` backfill from `canonical_hrv` (Garmin cutover seam)

`/series/readiness` reads `daily_records.passive_hrv_ms`, a value frozen at AM check-in. The #291
rewire repoints the snapshot source to `canonical_hrv` for FUTURE check-ins only; historical rows
keep their Samsung-snapshotted values, leaving a seam at the date a user connects Garmin (before it:
Samsung-snapshotted; after: canonical). A clean history needs a one-off script recomputing
`passive_hrv_ms` from `canonical_hrv` as-of each past date. Non-destructive (recomputes a
forward-frozen scalar) and a NO-OP today: canonical == Samsung on every existing night (per-user
overlap nil, Q131), so backfilling now changes nothing. Defer until Garmin has synced a stretch of
history worth reflecting, then run it as-of each past date. Watch-point, not owed work.

**State:** OPEN (deferred — no-op until Garmin has overlapping history)

---

## Q153. `_SOURCE_RANK` arbitration branch — delete once no consumer calls it; keep `canonical_hrv` row-reading

#292 made `hrv_deviation` the HRV consumption model and migrated all four live #291 consumers off `canonical_hrv`'s arbitration selection. The arbitration branch (`_SOURCE_RANK`, `_rank`, `_win_key`, `arbitrate`, the derived `.canonical` flag) is now SUPERSEDED but kept callable, because one caller remains: the UNMOUNTED `routers/recovery.py` (Q151). The exit is the fine cut — delete the selection layer, keep `_hrv_rows` (the source-tagged row-reading plumbing the deviation reader depends on).

**Trigger to close:** when Q151 resolves recovery.py (adopt with a consumer that reads `hrv_deviation`, or delete the module) AND no consumer calls the arbitration selection (`.canonical`). Then delete `_SOURCE_RANK` + the arbitration branch and keep `_hrv_rows`. If a future need for a single arbitrated number arises, derive it from the deviation model via `representative_source` (highest-confidence/highest-weight source) — NEVER a resurrected rank. Until then the branch stays callable but no NEW consumer may call it (enforced by review + the `recovery_reads` docstring). This is coupled to Q151, not independent; track consumer migration to completion so dual-reader does not become permanent (the failure mode Q151 itself names).

**State:** OPEN (deferred — blocked on Q151; the branch is superseded but callable until recovery.py's disposition is decided)

---

## Q156. Criterion/sensitivity harness for the Banister τ-set — no wire-up exists (P4)

Preregistered 2026-09-16 with banister-v2 (#301). The normalised stocks (#301) restore #18 but nothing yet VALIDATES the τ-set against an observable. The model needs a **criterion series** the fitness trace must eventually agree with, plus a way to sweep τ and read the divergence. Per `docs/load-governor-trajectory-design.md` §3.2, the mechanical/NM criterion is **rolling per-template e1RM** — ALREADY computed (`rolling_e1rm`, `load_events.py`, 60-day window); §3.2 marks it **"wire-up only"** (the observable exists; it just needs connecting to a trace-vs-criterion comparison). The metabolic window has no built criterion yet (§3.2).

**Why it is not free.** There is NO sensitivity/sweep hook in the tree. `load_sweep.py` is the #297 nightly SCHEDULER — it fires `refresh_load` at 02:00 Brisbane and recomputes ONE τ-set (the current `METRICS_VERSION`); it does not sweep τ or score a criterion. A harness would: (a) wire the e1RM criterion to the mechanical/NM fitness trace as a divergence flag; (b) sweep candidate τ values OFFLINE over stored `load_events` (not a prod recompute — a τ change is a `metrics_version` bump per #248); (c) score each against the criterion, feeding the "τ is the first tuning lever" clause of #18/#301. The metabolic τ_fat=4 near-instantaneous artefact (#301, queued P6/P4) is the first concrete tune this harness would adjudicate; because a τ bump is a live recompute, the harness must run BEFORE any τ change reaches prod.

**Amended (P3, #302).** The criterion sweep is now POST-EPOCH by construction: `banister-v3` truncates each user's series at `users.rpe_complete_from`, so the e1RM-vs-fitness comparison only ever runs over the RPE-complete span — there is no cross-epoch logging-behaviour step left for the harness to model around. User 4 has NO e1RM criterion until ~60 d of RPE-present sets accrue, and that is contingent on her adopting RPE at all (her epoch is currently NULL); until then her fitness trace has no observable to validate against. The metabolic-window criterion (§3.2) remains unbuilt.

**Amended (P6, #305).** The harness's INPUT LIST is now explicit: `docs/load-constants-provenance.md` tables every load coefficient with a provenance class, and its "operator prior (uncited)" rows (15 of 23) are exactly what the sweep must adjudicate. **Sweep order: τ_metabolic=4 first** (against McGregor 2007 / Vermeire 2021), then the other τ_fatigue priors (mech 10, nm 6), then the mechanical/NM band coefficients (`_mech_mult`, `_f_rir`, `_nm_reps_prior`, `_h_intensity`) and the bridging constants (`K_DIST`, `K_TIME`, `E1RM_WINDOW_DAYS`, `H_NO_E1RM`). A fit that moves any row from "operator prior" to "fitted" updates that row (the standing rule, #305). `TAU_FITNESS_DAYS` (42) and `FORM_K` (1) are the tabled *cited* rows the sweep tests against their conventions, not blank priors.

**State:** OPEN (P4). Blocks no current surface — banister-v2/-v3/-v4 ship without it; criterion validation is downstream. Input list now pinned (#305).

---

## Q157. `hrv_readings.source` has no enum/CHECK — the wake-day selector's >2-source guard is runtime, not schema

Raised 2026-09-17 with #303. `HrvReading.source` is an unconstrained `String(50)`; any writer can stamp any string, so >2 distinct sources on one wake-day is a real state, not theoretical. `select_wakeday_hrv` (#303) guards it at READ time — three sources → `config_error`, never a silent 2-of-3 pick — but nothing stops the rows being written in the first place, and every future reader of `hrv_readings` must re-implement the same guard or silently mispick. A `source` enum (or a CHECK against the known set `{garmin, samsung, …}`) would move the guarantee from per-reader runtime to the schema, catching a bad/typo'd source at ingest and letting readers trust a bounded source set.

**Why deferred, not done in #303.** #303 is scoped additive/non-migration (helper + tests only) precisely so it self-merges on green ahead of the denorm brief; a schema constraint is a migration, which takes full human review (§ Merge disposition hold (a)) and would block the precondition. The runtime guard is the correct floor regardless — a schema constraint complements it (defence at write), it does not replace the read-time guard (a reader must still decide what to DO with a legit multi-source night).

**To close:** a migration adding a CHECK/enum on `hrv_readings.source` (decide the allowed set — at least `garmin`, `samsung`; whether to admit `withings`/others already seen in `health_connect_record_sources`), plus a decision on whether the read-time `config_error` path stays (it should — the guard is about >2 same-night sources, which a per-value CHECK does not prevent). Full human review (schema migration).

**State:** OPEN. Blocks no surface — the runtime guard (#303) holds the correctness floor; this is a defence-in-depth upgrade.

---

## Q158. Uncoupled chronic (days 8–28) as an optional descriptive `load_ratio` denominator

Raised 2026-09-17 with #306. `load_ratio = acute(7d)/chronic(28d)` is a COUPLED ratio — the 28-day chronic window contains the 7-day acute window, which induces a spurious ~0.5 correlation between numerator and denominator (Lolli 2017 / Windt 2018). #306 keeps the coupled form at Tier 0 because the practical effect is small (Coyne 2019) and de-coupling is not free: an uncoupled chronic (days 8–28, excluding the acute window) needs a **new `load_metrics` column** (`chronic_uncoupled`) and a migration, plus the recompute/versioning that any stored-series change carries (#248 disposition). 

**To close (if built):** add the column + a `_trailing_mean` over days 8–28, surface it as a SECOND descriptive ratio (never a risk band — the #306 reclassification binds it too), and decide whether the coupled ratio stays or is superseded. It remains descriptive-only; a criterion (Q156) is required before any threshold rides either denominator. Schema change → full human review.

**State:** OPEN. Blocks nothing — the coupled ratio ships descriptive under #306; this is an optional precision upgrade, not a correctness fix.

---

## Q159. Stage-2 HC exercise zones — load treatment of a zoned activity session

Raised 2026-09-18 with #309 (HC exercise ingest stage 1). Stage 1 ingests HC exercise records as ZONELESS `aerobic_sessions` rows (`z*_seconds` NULL, INV-7 fail-closed → no metabolic `load_event`). Stage 2 would derive HR-zone seconds from the HC heart-rate samples posted alongside the workout, at which point a session deposits metabolic TRIMP like any Polar row.

**Named blocker:** the HCA HR-lag finding — HR samples arrive ~6 days behind the sync that carries the workout (observed ~15 s sample spacing during Garmin activities on user 4, ~2 min outside them), so a zone reconstruction on the workout's sync would score an empty window. Stage 2 cannot be built until the lag is characterised and the reconstruction reads the later-arriving HR.

**Coupled load-model decision (NOT a resolver one, #302 series invariance):** a zoned pilates or walk session would deposit metabolic TRIMP. Whether some sports (rehab swimming, pilates, walks) are EXCLUDED from the metabolic window is a LOAD-MODEL call — it changes what the transform computes, not what the resolver counts — and is explicitly NOT made in #309. The resolver's `activity`-slot brief (v2, queued) decides what a session MEANS for the plan; it never alters the load model.

**To close (if built):** characterise the HR-lag, reconstruct zones from the posted HR onto the existing zoneless row (a recompute, not a new row), and rule the sport-exclusion question at the load layer. Schema-neutral if it only fills existing `z*_seconds`; the recompute/versioning discipline (#248) applies.

Unblocked 22 Sep. HR coverage confirmed via `record_sources` (HCA Q22 closed). HC sessions still carry null `hr_avg`/`hr_max` by stage-1 design; this is the stage-2 join.

#302 sport call ruled #322: no sport exclusion for the metabolic deposit. Stage 2 unblocked on the load-model side.

**Resolution (#364, 1 Oct 2026).** Stage 2 is built as a source-neutral HR zoning: raw samples in `hr_samples`, a per-user dated HRmax in `user_hrmax`, our own %HRmax bands, zones filled onto `health_connect` rows by the soft-fail chain step `hc_zone_enrich`. The named blocker did not hold: the newest HR sample is 0.0-7.6 h old at each POST (not ~6 days) and every POST re-sends about 7 days. The sport-exclusion question was ruled #322 S2 and reaffirmed by the operator on 1 Oct (no exclusion; zone weighting prices every zoned session). Polar re-zoning from raw HR is the follow-on, Q198.

**Reopened (4 Oct 2026, #369).** Measured lag: the 26 Sep Pilates in-activity HR (241 Garmin samples at 13 s) reached `hr_samples` only after the 7-day manual sync at 13:47Z on 3 Oct, about 7 days after the session, and was absent after the 30-day manual sync at 03:33Z. That agrees with the lag named above (about 6 days, HCA Q22, user 4). The Resolution above set the blocker aside on "the newest HR sample is 0.0-7.6 h old at each POST"; that measures the freshest passive sample and does not cover in-activity lateness. What stays open: what the app shows and deposits for a session inside the lag window (a zoneless row reads as zero load, silently: Q202, Q203), and the re-read depth that covers it (#370 sets the scheduled window to 30 days). The recompute on every chain run (#364) is what fills such a row once its HR is stored.

**Garmin activity read as a lag-bypass candidate (4 Oct 2026, operator; a note, not a decision).** The 1 Oct "no client built" position for a direct Garmin read (the Q198 inventory table) is REOPENED, scoped to a read-only activity read: self-evaluation first (Q209), and in-activity HR as a candidate fix for the lag measured in #369. The operator reports Garmin Connect holds the full wrist HR for the 26 Sep Pilates (Q207), where Health Connect delivered it about 7 days late. `garminconnect` 0.3.11 exposes `get_activity_details` (`__init__.py:2957`) and `download_activity` (`:2839`); which of them carries per-sample HR, and how soon after a session, is unverified. Any live read follows #361 (never refresh a Garmin token), and the library is an unofficial, ToS-grey lane (`requirements.txt:22`). The ruling follows the Q209 probe and is tied to it. Related: Q209.

**Garmin activity read built for self-evaluation only (4 Oct 2026, #372).** The read-only Garmin activity read now exists, scoped to perceived effort and feel (Q209, landed via PR #309). It does NOT read in-activity HR: the HR read stays a separate candidate for the lag measured above, still unbuilt and unruled.

**First live self-evaluation read (4 Oct 2026, #372; operator-reported, not read by Code).** Five rated activities linked to Health Connect rows 86, 87, 89, 93 and 99, and four unrated marker rows. The 1 Oct run was captured at RPE 6: the operator revised it in Garmin before the first read (it was 4 at save), so the stored value is the revised one, read once. Garmin prompts RPE and feel separately, so "rated" means RPE present and feel is optional. Health Connect row 94 (1 Oct 22:29, "Other Workout") is a Garmin breathwork activity. The nightly sweep's "unrated 22" in the startup log is summed over users 1 and 4, so it is not compared with the four rows here.

**Scheduled-sync evidence (5 Oct 2026, Code, Railway HTTP log; the first reading of it, superseded in part: #370 is confirmed, #377).** The operator saw HRV and sleep update overnight 4 to 5 Oct with no manual sync, on build `e3e2333`. What the log shows:
- *HRV is not phone evidence.* It reaches the app by the server-side Garmin sweep (`garmin sweep: user 1 OK`, 16:00:26Z = 02:00 Brisbane on 5 Oct) and by the web app's own `POST /integrations/garmin/refresh` on open (`useRecoveryRefresh.js`; 20:56Z and 23:49Z, 06:56 and 09:49 Brisbane). Neither involves the phone's scheduled sync, so an updated HRV says nothing about it.
- *Sleep is the phone's* (HC `SleepSession` through `POST /health-connect/sync`). Phone POSTs since 4 Oct 14:00 Brisbane: 06:04Z (10.5 s), 12:08Z (237 s), 18:09Z (8.5 s, 04:09 Brisbane on 5 Oct) and 00:09:50Z (8.1 s, 10:09 Brisbane), all 200. The last was absent from the log when it was first read, at about 00:14Z, so the log lags: "none since" in the first reading was wrong. About 6 hours apart (Likely a scheduled cadence). The pre-fix empty background POSTs took 40 and 42 ms (2 Oct 18:50Z, 3 Oct 00:51Z), so 8.5 s means the 18:09Z POST carried data.
- *The server cannot say what triggered a POST, though the phone does.* Build `e3e2333` stamps `client.trigger` (`'manual'` or `'background'`) on every POST (companion `syncRunner.js:93`, `backgroundSync.js:57`, `SyncScreen.js:177`). `ClientInfo` accepts it (`extra="allow"`) and the sync-event row drops it (`routers/health_connect.py:1152-1159`; there is no column), so it is not stored (Q214). The user agent is `okhttp/4.9.2` on all of them and the deploy log holds only the access line, so scheduled versus app-open cannot be read from the logs. Data-carrying POSTs also come from app-open (3 Oct 19:48Z, 12.6 s).
- *Open points, settled by #377.* The sync-event rows for the POSTs after 12:00Z are ids 66-68 (operator read): build `52f9d4d`, `period_days` 30, no error, heart rate 29.4-29.6k received, `hrv` 0. The newest sleep record is 2026-10-03T14:44:45Z in row 67 (04:09 Brisbane) and 2026-10-04T13:54:37Z in row 68 (10:09), which is consistent with the night's sleep arriving in the later POST, not the 04:09 one.
- *P1 is built and device-confirmed (#377).* The companion's PR #64 (merge `e3e2333`) initialises Health Connect in the background task, returns `ok:false` on an all-failed fetch, and widens the scheduled window from 7 to 30 days. Sync events 66-68, on build `52f9d4d` (a descendant of `e3e2333`), show it reading with no error (operator read, 5 Oct). The acceptance criterion is amended to "a build containing `e3e2333`". #371's overlap proof stays owed.

**Read owed (5 Oct 2026, operator): has the 30-day Health Connect window delivered the Garmin in-activity HR for the 1 Oct run?** Code has no database route. Notes before it is run:
- *The receipt count cannot answer it.* Sync events 66-68 show heartRate received 29,475, 29,357 and 29,569 (#377). The window slides, so old days leave as new ones arrive: the count fell from 66 to 67 and rose from 67 to 68 with no change in the 1 Oct run.
- *Expected timing.* Garmin writes in-activity HR about 7 days after the session (#369; the 26 Sep Pilates arrived about 3 Oct). For a 1 Oct session that is about 8 Oct, so a read on 5 Oct is expected to show passive samples only (Likely): read it on or after 9 Oct. What the 30-day window changes is whether a write later than 7 days is still picked up, which a session this young cannot show.
- *A test that can be run now.* A session older than 7 days with no in-activity HR: the same read with `WHERE ... id IN (69, 85, 92)` in place of the time predicate (the rows named in Q207's first read). In-activity samples appearing there after the 30-day scheduled runs would be the window working.
- *Reading the result.* A Garmin writer with a median gap of 7-16 s (in activity, Q198) on an arrival day after the late write is recovered; only 120 s gaps (passive) is not yet. `arrived_on` is the Brisbane day each sample first reached `hr_samples` (`created_at`, insert-once).

Parser-checked with `pglast` 8.5 and against `SCHEMA.md`; not run:

    WITH s AS (SELECT id AS sid, sport_name, source_package AS session_pkg, start_time AS st, stop_time AS sp FROM aerobic_sessions WHERE user_id = 1 AND source = 'health_connect' AND start_time >= TIMESTAMPTZ '2026-09-30 14:00:00+00' AND start_time < TIMESTAMPTZ '2026-10-01 14:00:00+00'), g AS (SELECT s.sid, h.source_package AS hr_pkg, h.sample_time, h.created_at, h.sample_time - lag(h.sample_time) OVER (PARTITION BY s.sid, h.source_package ORDER BY h.sample_time) AS gap FROM s JOIN hr_samples h ON h.user_id = 1 AND h.sample_time >= s.st AND h.sample_time <= s.sp) SELECT s.sid, s.sport_name, s.session_pkg, round(extract(epoch FROM (s.sp - s.st)) / 60.0, 1) AS dur_min, g.hr_pkg, (g.created_at AT TIME ZONE 'Australia/Brisbane')::date AS arrived_on, count(g.sample_time) AS n_samples, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM g.gap))::numeric, 1) AS median_gap_s, round(max(extract(epoch FROM g.gap))::numeric, 0) AS max_gap_s FROM s LEFT JOIN g ON g.sid = s.sid GROUP BY s.sid, s.sport_name, s.session_pkg, s.st, s.sp, g.hr_pkg, 6 ORDER BY s.sid, g.hr_pkg, 6;

The window `[2026-09-30 14:00Z, 2026-10-01 14:00Z)` is 1 Oct in Brisbane, so it returns every session that day (the run, and the 22:29 "Other Workout" that is Garmin breathwork).

**State:** OPEN. Owner: Luke. Not blocking. Related: #369, #370, Q202, Q203, Q207.

---

---

## Q163. A real tool-use runtime for the in-app chat?

Raised 2026-09-20 with #314. The in-app coach has NO tool loop — it acts through embedded tags (`<hevy_create_routine>`, `<hevy_update_routine>`, `<knowledge_update>`, `<capability_update>`) parsed out of a single completion, and reads everything it needs (routines included, #314) from the prepared context. The MCP tools (`search_hevy_routines`, `get_hevy_routine`, …) exist only for EXTERNAL MCP clients. #314's GUARD: do NOT build a tool runtime there — it is a larger decision.

**To decide:** whether the in-app chat should gain a genuine Anthropic tool-use loop (`tools=` + tool-call turns), letting the coach fetch a routine on demand rather than reading a bounded working set from context, and folding create/update into tool calls. Trade-offs: per-turn latency + cost of multi-step tool turns vs the current single-pass + tags; and how the write-result/footer truthfulness discipline (#283/#313/#314) maps onto tool results.

**State:** OPEN. Not blocking — the tag lane works and #314's read/update ride it. A capability question, revisited if the working-set-from-context model proves too limiting.

---

## Q164. Ingest-side sport-name normalisation for slot membership?

Raised 2026-09-20 with #315. Activity and sport-scoped `load_window` slots decide membership by matching a slot's declared `device_sports` against a canonical session's `sport_name` — EXACT but case-insensitive, no fuzzy/category matching (ruling 4c). `device_sports` is an OPEN vocabulary because Polar sports are free-form (`Fitness`, `Road cycling`, `Other outdoor`, …) and HC produces title-cased `ExerciseSessionType` names; a closed set would refuse a real Polar sport. The cost of open + exact: a typo or a source-specific spelling (HC "Walking" vs a Polar "Walk") matches no slot and surfaces as `unclaimed_session` — visible and fixable, but silent to the quota until fixed.

**To decide:** whether the ingest path should NORMALISE `sport_name` to a canonical vocabulary (a source→canonical map, e.g. HC `WALKING`→"Walking", Polar "Walk"→"Walking") so slot membership rests on a canonical token rather than the raw device string, and whether `device_sports` should then validate against that canonical set (closing the vocabulary) or stay open. Trade-off: robustness of matching + a closed validatable set vs the maintenance of a per-source map and the risk of refusing a genuinely new sport at write.

Ruled #322: not built; trigger unchanged.

**State:** OPEN. Not blocking — exact case-insensitive matching works for the sports observed in prod, and a miss is visible (`unclaimed_session`, "other activity"), never a silent miscount. Revisited if real sessions repeatedly go unclaimed on spelling.

---

## Q166. A structured planned-phase store (so "Move to a new phase" can prefill from the plan)?

Raised 2026-09-20 with #317. The phase-change form's "Move to a new phase" step (vs "Continue") asks for a new label + intent + microcycle with NOTHING prefilled — the plan of record (#312) is prose (`training_plan.macro`), and the form deliberately never parses it (GUARD). So the operator retypes the next block from memory / by reading the plan beside the field. The plan stays prose by design (#312: a macro the coach reads, not a machine schedule).

**To decide:** whether to add a STRUCTURED planned-phase store — e.g. an ordered list of upcoming `{label, intent, microcycle}` blocks the athlete/coach fills once, from which "Move to a new phase" prefills — WITHOUT turning the prose plan into a scheduler (the #270/#275 line: the ledger is history+current, never a plan; a planned-phase store would be a SEPARATE forward-looking object the transition reads but the engine never auto-applies).

**State:** OPEN. Not blocking — "Move" works from a blank label today, and "Continue" (the common case, incl. 5 Oct) prefills from the outgoing phase. Deliberately NOT built in #317/#318. Revisited if retyping the next block proves a real friction.

---

## Q167. Two watch-points on `health_connect_sync_events` (per-POST sync telemetry, #321)

Raised 2026-09-21 with #321. The new per-POST table (`git_sha`/`fetch_meta`/…) is capture-only and rides `sync()`'s single transaction. Two boundaries were accepted rather than solved, recorded so a future reader does not mistake either for an oversight:

**(i) Failed syncs are undiagnosed.** The event row commits with `sync()`'s transaction, so a POST that raises and rolls back leaves NO event row — the exact case (a build erroring mid-sync) most worth a fingerprint is the one that records nothing. Accepted at current scale (single operator, low sync volume; the successful-POST fingerprint is what the HR-lag read needed). **To decide, if it becomes a need:** write the event row in its own committed transaction (or a `try/finally` that commits the event even on aggregation failure), trading atomicity-with-the-sync for failed-sync visibility.

**(ii) The week planner could repoint its HC-freshness read.** The week planner currently derives "how fresh is the newest HC record" from `health_connect_syncs`; `health_connect_sync_events.synced_at` (server clock, per POST) plus `fetch_meta[*].newestAt` is a cleaner, more direct source. **To decide, if the freshness read proves imprecise:** repoint it. Explicitly NOT in #321 (that touched no read path, GUARD).

**State:** OPEN. Neither blocks #321. Both are follow-ups the table now makes possible; revisit (i) if a failed sync needs post-mortem, (ii) if week-planner freshness drifts.

---

## Q168. No Polar last-pull timestamp — the week planner's Polar freshness is data recency, not pull recency

Raised 2026-09-22. Nothing records when a Polar pull last ran — no last-successful-pull timestamp exists anywhere in the store (the pull is manual, `Q154`). The week planner's freshness read therefore falls back to the newest Polar row's `created_at` and labels it **"newest Polar session received"**, not "last pull" (`backend/engine/week_plan.py:139-175`; `polar_pull_ts_exists` is emitted `False` so the render can say so). The label is honest about what it measures, and the two facts it cannot separate are DATA recency and PULL recency: a pull that ran today and returned nothing reads identically to a pull that has not run for a week.

**To decide:** whether to persist a per-source last-pull timestamp (server clock, written on every pull attempt whether or not it yields rows) and surface pull recency alongside data recency, or leave the single honest data-recency label and accept that pull recency is unknowable. Cross-ref `Q154` (aerobic ingest is not automatable — the same lane from the trigger side, and the reason no pull timestamp exists).

**State:** OPEN

---

## Q170. No capture path for a training-constrained CBT-I night — `training_constrained` is device-derived only

Raised 2026-09-24 with #326. The CBT-I ruling in #326 relies on the late-session constraint being recorded at capture ("record it the morning after"). On master no such capture path exists. `training_constrained` is derived at EVALUATION time from `aerobic_sessions.stop_time` (`cbti/replay.py` `_TRAINING_SQL` → `Night.training_end` → `cbti/engine.py:460`). No diary or check-in field feeds it, so a late session no device recorded cannot constrain a night. The same is true of `travel_or_match`: `Night.travel_or_match` defaults `False` and nothing in `load_nights` or `checkin_v2` ever sets it. The one other late-arriving input, a device session ingested after the fact (a later Polar pull, Q119 backfill), already changes a past night's verdict on the next replay, because the replay re-reads `aerobic_sessions` on every run. Accepted prescriptions are snapshotted, so only unaccepted cycles move.

**To decide:** whether to add a capture-time field (an AM check-in "trained late last night" or a training-end time on `daily_records`, which is a schema change) that `load_nights` reads alongside the device value, and how the two combine (device wins, or either constrains). Also decide whether `travel_or_match` should gain a writer on the same path or be retired as dead.

**State:** OPEN. Not blocking #326 (the marker has no CBT-I effect whatever this decides). Risk until built: an unrecorded late session reads as an unconstrained night.

---

## Q171. MCP `get_readiness_snapshot` 7-day session count keys on the UTC date

Raised 2026-09-24 with #327 (nit accepted, not fixed there). #327 moved the readiness HRV read to the AEST wake-day (`_aest_wake_day`), but the same tool's training summary still windows sessions with `datetime.now(timezone.utc).date() - timedelta(days=7)` (`mcp_server.py`, the `arbitrated_sessions(since=...)` call). Before 10:00 AEST that window is one day off the local one.

**To decide:** whether to key the window on `_aest_wake_day()` like the HRV read (one-line change plus a test at 07:00 AEST), or leave it and document why.

**State:** OPEN. Low impact: an off-by-one edge on a 7-day count.

---

## Q173. S8 — latest-row readers of the dead ring table and the HC aggregate that reach a surface

Raised 2026-09-25 with the HC sleep-clocks decision (#328). This is an audit (the table is in PR2's description), and no reader is fixed there. Several user- and coach-facing readers take the newest `samsung_hrv_readings` row, or a window of it, with no same-day gate. The ring scraper has been dead since 2026-09-14. The sharpest case is the MCP readiness snapshot's "Latest biometrics (<date>)" block, which sits under "TODAY'S READINESS SNAPSHOT" with 2026-09-14 sleep/SpO2 values. It is dated, but headlined as today.

**To decide:** per reader, gate to same-day, keep dated but re-headline, or retire now that the ring is returning (the scraper stays the ring-HRV path).

**State:** OPEN.

---

## Q174. Generic SLEEPING (stage 2) is outside the asleep set: a SLEEPING-only writer yields TST 0

Raised 2026-09-25 with the HC sleep-clocks decision (#328), accepted as #259 ruling 1. `_ASLEEP_STAGES` (#254/#256) is LIGHT/DEEP/REM. Health Connect's generic `SLEEPING` (2) is not in it. So a writer that emits only `SLEEPING` stages contributes no asleep minutes. Its night has TST 0, no main period is selected on asleep time, and `sleep_onset` is NULL. This is pre-existing and latent: Garmin and Samsung Health both write detailed stages. It is not fixed with the clocks because it changes #256's TST semantics.

**To decide:** whether `SLEEPING` counts as asleep for TST, period selection and onset (and how it combines with a detailed-stage writer on the same night), or whether a SLEEPING-only writer is treated as stageless.

**State:** OPEN. Latent; no current writer triggers it.

---

## Q175. Device identity for HC sleep sessions — persist the recording device so per-source rules key on it

Raised 2026-09-25 with #329. Per-source sleep rulings must key on the **recording device**: Samsung Health relays other devices' sessions (09-16), so `sourcePackage` is the writer app, not the device. The device is not on the wire for sleep. HCA's `fetchSleepData` mapper (`healthConnect.js` L227–234) sends only `startTime`, `endTime`, `stages`, `durationMinutes` and `sourcePackage`, and drops the library's `metadata.device`, `recordingMethod` and `id`. The exercise mapper does forward them; per #35, Samsung Health leaves them at their UNKNOWN sentinels there. The backend's `extra="allow"` would retain them if sent.

**To decide:** add `metadata.device` (manufacturer/model/type), `recordingMethod` and `id` to HCA's sleep mapper, and persist a per-endpoint device alongside `sleep_*_source_package`. Settle first whether relaying writers populate the device at all (the #35 sentinels suggest Samsung Health may not).

**State:** OPEN. Needs an HCA change and a schema migration (hold (a)).

## Q176. Ring validation window at ring return — suspend the ring `got_into_bed` prefill for about 10 nights and re-run S7

Raised 2026-09-25 with #329. The ring and Samsung start semantics are unruled because the diary evidence is contaminated: `got_into_bed` was prefilled from the ring itself (circular) or corrected selectively (biased).

**To decide:** when the ring returns, suspend the ring `got_into_bed` prefill for about 10 nights (recall-only entry), then re-run S7 on those independent nights and rule on the ring's start per recording device (Q175).

**State:** OWED. Triggered by the ring returning.

---

## Q177. After the #331 anchor correction — act on the flipped titration history, and clean the contaminated instruments?

Raised 2026-09-26 with #331. rx 11–17 were titrated against windows 45 min shorter than the one run (anchor 05:00 recorded, 05:45 used). With the window actually run, three of five adjudicated moves flip from extend to compress (rx 14, 16, 17). Lights-out moved 42 min earlier when the rule, correctly applied, pointed later.

**To decide:**
1. Wait for the engine's next 4-night cycle from the corrected 477, or make an immediate operator move now. The rule's current reading is 406 + 30 = 436 against 477, so a capped compress to 462 / 22:03 is Likely. This is a clinical call (operator/chat), not an engine change.
2. Should `centre_estimate` (the check-in's sleep-need readout) exclude or 45-min-adjust rx 11–17? After the correction it mixes true and understated windows for up to four cycles.
3. `basis_tib_over_run_min` on rows produced from rx 11–17 windows is overstated by about 45, and it is the dataset a future TIB threshold is meant to be set against. Should it be annotated, or excluded from that distribution?

**Item 2 resolved → #333** (centre restarts at the latest `adopt`, operator-ratified 2026-09-26). Items 1 and 3 remain open.

**State:** OPEN.

---

## Q178. Rename the waking-cause columns to `*_min`, and settle the one count-shaped value (08-13)

Raised 2026-09-26 with #332. `wakings_nocturia_n` / `_pain_n` / `_spontaneous_n` now mean minutes of WASO by cause. The `_n` suffix misstates the unit to every reader of the schema. The MCP header already relabels them.

**To decide:**
1. Rename to `waso_nocturia_min` / `waso_pain_min` / `waso_spontaneous_min`. That is a migration (hold (a)) touching the model, the check-in schema, the form payload and the MCP projection.
2. The 2026-08-13 row (`wakings_nocturia_n`=1, `waso_min`=35, one waking) reads as a count. Either correct it to 35, which is an operator witnessed data fix on an AM-frozen field, or annotate it as unit-ambiguous.

**State:** OWED. Loop-close: a migration PR released by the operator, plus the 08-13 disposition.

---

## Q180. Browser chat history is a single non-expiring conversation re-sent every turn

Raised 2026-09-27 with the injury clearance sweep (#340; G0 ruling 5). The chat panel keeps ONE conversation per user in
browser `localStorage` (`chat_history_{sub}`, `ChatPanel.jsx`) and sends all of it as `conversation_history` on every
turn (`chat.py`). Nothing expires or trims it. Two costs:
1. **Unsearchable copy store.** A resolved injury (or any retired fact) discussed in chat stays in context on every
   later turn, re-imposing it. The backend never sees the history at rest, so the clearance sweep cannot search it;
   it is on the sweep's fixed manual checklist ("browser chat history") only.
2. **Unbounded token growth.** Every turn re-sends the whole conversation.

**To decide:** a server-side, bounded history (summarised, or windowed with older turns behind a tool), or a
client-side window/expiry, or an explicit "new conversation" affordance — and whether resolved-fact copies in it
are handled by the summary or by the operator.

**Annotation (2026-09-28, typed entries #342/#343).** The typed-entries brief's "server-side, summarised chat
history" item IS this question — routed here rather than minted twice. LATER per #275 ("chat not required" for
v1); ROADMAP LATER row.

**State:** OPEN. No blocker.

---

## Q181. Retire or render-gate the legacy free-text `user_knowledge` store

Successor to Q9, which closed DONE → #343 on its fork only (the legacy KB folds into typed `finding` /
`constraint` rows; no `note` type). What Q9 still carried moves here verbatim:

- **Forward-compat (G2 ruling):** the sweep's `reaches_context` label is currently a per-store constant (`"yes"`
  for `user_knowledge`, `injury_sweep.sweep_user_knowledge`). When this Q render-gates the free-text store, that
  label must be DERIVED from the renderer's actual inclusion rule, not the constant, so it flips with the gate.
- **Step-1 ruling (operator, 2026-09-27): GO.** The `user_knowledge` render path and write path are retired
  TOGETHER, in a separate brief (not yet cut). #341 (the prompt no longer offers "Injury History"/"Constraints")
  stands as landed and is now a subset of that retirement. The typed `constraint`/`finding` brief is a separate,
  parallel lane.

The cost is Q9's 2026-09-27 annotation: the store has no active flag and no resolution, and renders unfiltered
every turn, so a retired fact re-imposes itself from here. Typed rows now exist to fold into (#342, #343); the
S6 seed covers injury `restrictions[]` only, not free-text lines.

**State:** OWED — settled GO (Step-1 ruling); loop-close: the `user_knowledge` retirement brief (brief 2), not yet
cut.

---

## Q182. Default constraint templates from `_ACUTE_TISSUE_BLOCKS` / `_RADICULAR_BLOCKS`

Raised with #342 (the brief kept both maps unchanged). `engine/selection.py` hard-codes body-part → region
blocks (the acute-tissue and radicular seed heuristics, spec §8). They have no exit, no review date and no
visible authority — the gap #342 closes for everything else. Convert them into default ENGINE-tier `block`
constraints seeded per injury at creation (`asserted_by: "engine"`, `with_parent` exit), so the coach and the
sweep see them as rows.

**To decide:** seeded as proposals (the operator confirms) or confirmed with engine authority; how existing
active injuries migrate; whether the in-code maps then retire; and the byte-identity gate against the current
arms (#342's pinned-SHA pattern).

**State:** OPEN. No blocker.

---

## Q183. Engine-tier `cap` and `caution` constraints

Raised with #342 (G2 ruling 2): the engine tier accepts `block` only in v1. `cap` means a load ceiling and the
engine has no dose seam to enforce one (Q106 / the Banister dosing wire), so an engine cap would silently become a
block. `caution` through the boolean `is_contraindicated` (#72: it stays boolean) is indistinguishable from a block.
Both remain advisory-tier kinds.

**To decide, when its trigger fires:** engine `cap` when the dose seam lands (what the cap bounds, and how it is
enforced); engine `caution` only if `is_contraindicated` becomes graded.

**State:** OPEN — watch; no action until the dose seam lands or #72's boolean changes.

---

## Q184. Budgeted context builder with history behind a tool

Raised with #342/#343 (brief S7). The standing prompt grows section by section, each with its own cap: the
#314 routines budget, the #343 findings budget (2,000 chars, overflow named), and the knowledge-update guidance
(+1113 bytes at #342). A whole-prompt budget with lower-priority and historical material behind read tools
(the `get_findings` pattern) would replace per-section caps.

**State:** OPEN — LATER per #275 ("chat not required" for v1); ROADMAP LATER row.

---

## Q186. App chat has no current date — anchors "today" to the newest data

The 27 Sep weekly summary reported Fri/Sat as "scheduled" after Saturday's Pilates had
landed, and computed "11 days to 05 Oct" from 24 Sep (the last logged session). A second
instance on 28 Sep: asked for an injury row's key, chat said the row was saved "on
18 Sep" (the MRI date in its context); the ledger shows 28 Sep. The MCP layer emits
`as_of` (Brisbane); the chat handler's system-prompt assembly is the suspect
(hypothesis — verify against `routers/chat.py`). Browser chat history (Q180) re-sends
old "today" references every turn and may compound it. Session status should be derived
in code (planned vs logged), not read by the model.

**State:** OPEN — brief owed. Owner: Luke (rule), Code (verify + fix).

---

## Q188. Session card shows the UTC date, MCP shows the local date

Saturday 26 Sep Pilates renders as 2026-09-25 on the Training session card and as
2026-09-26 in `get_training_sessions`. Hypothesis: card renders UTC `start_time`; before
10:00 AEST a session lands on the previous day. Affects which day load is booked to.

**State:** OPEN — one-line fix once verified (`_local_day` is the single source, #276).

---

## Q189. Session-RPE for device-only sessions (Pilates, swim) with no logged sets

HC Pilates sessions arrive with no HR/kcal and no sets, so they deposit nothing in the
neural/tissue lanes. Proposal: capture one session RPE (card field, or next AM check-in
prompt), load = RPE × minutes, with a declared conversion into lane units. HR remains a
quality signal, not a load driver. Garmin → Health Connect HR absence is unverified
(operator check in HC app pending; Q159 adjacent).

**Garmin-watch sessions get a captured rating (4 Oct 2026, #372).** A per-session RPE and feel, immutable and linked to the Health Connect row, is built for sessions the Garmin watch records, landed via PR #309. It does not cover H10-only sessions, and Q209's path (b) (a companion-app notification on Polar session arrival) is undecided; this question's own fork (what a device-only session's effort is worth in load) is unchanged.

**State:** OPEN — design fork (capture surface; scaling rule). Owner: Luke.

**Cross-reference (#365, Q202).** The running case the device hierarchy creates, a watch-owned run with no usable HR zones, is filed as Q202. Resolve the two together.

**Case A lean (4 Oct 2026, the `srpe-floor` session; a lean, not a ruling).** If a floor is ever built (Q202), it fires only where the unzoned session is the day's only counted session, and a non-training sport (Walking, Pilates, Yoga, Stretching; #322 S3) is excluded, because `session_rpe` is one whole-day rating (`daily_records.session_rpe`). The consequence for this question's own example: a Pilates session does not floor until a session-specific capture surface exists, which is Q209. The brief's S1 found only 2 paired days (Q202), so there is no kappa to apply either way.

---

## Q190. Two devices, one session: source-wins rule and overlap dedupe

Operator intends watch (Garmin/HC) for runs and Polar H10 for training/games. A run
recorded on both arrives as a Polar row and an HC row; whether ingestion merges
overlapping sessions across sources is unverified. Proposal: per-activity source
priority + overlap dedupe surfaced (never silent), mirroring the Hevy `dedup_flag` door.

**State:** OPEN — verify current arbitration first (#309 writer-class ladder is
same-source only). Owner: Code (verify), Luke (rule).

**Update (#365, Q201).** Arbitration was verified against master `054d2d9`. The premise above is stale: cross-source arbitration exists (#260) and #309 added a same-source `health_connect` arm. The findings, the gaps and the live-case queries are in Q201, and the device rule is recorded as #365. This entry stays OPEN for the arbitration and surfacing ruling, which Q201 now carries; close the two together.

---

## Q191. Standing review sweep — entries past `review_by` or with a resolved parent

#340 sweeps on resolution only. The design (chat, 28 Sep) adds a scheduled/check-in
sweep listing constraints and findings past `review_by`, or whose parent resolved
(`parent_resolved_survives`). Surfacing only (#223). Six live constraints share
`review_by` 2026-10-26; align them to the outcome of the 1 Oct 2026 follow-up.

**State:** OPEN — small brief; belongs with Q181 or after. Owner: Luke.

---

## Q193. Polar webhook trigger for aerobic ingest — feasible, and likely blind to Flow-app sessions

#353 closes the freshness gap by pulling. The pull runs when the Training page opens and in the 02:00 sweep. A webhook would push instead: a session would land without the page being opened. Brief C S4 asked for feasibility only: no handler, and no prod registration.

**Findings (29 Sep 2026, docs-only).** The official AccessLink docs (`www.polar.com/accesslink-api`) are blocked by this container's egress policy. The findings below come from third-party sources, so they are tagged. Sources for polar.sh (a payments company) turned up in the same searches and were discarded: their `webhook-id` / `webhook-timestamp` signature scheme is not AccessLink's (#103).

- **(a) Registration.** *Likely.* Webhooks are a **v3** client-level resource, `POST/GET/PATCH/DELETE /v3/webhooks`, authenticated with the client's Basic credentials, not a user token. The create body is `{events, url}`, with EXERCISE and ACTIVITY_SUMMARY as defaults. On create or update, AccessLink sends a PING to the URL, and the endpoint must answer 200 or the webhook is refused. Third-party code states there is **one webhook per client**. Whether this app's client, which today uses v4 OAuth at `auth.polar.com`, can also hold a v3 webhook: *Guessing*, untested.
  - **Decisive caveat.** *Likely.* The EXERCISE event belongs to v3's exercise pipeline. The repo's own v4 rationale (`connectors/polar.py` header, Decision 17) records that v3 exercise-transactions exclude sessions recorded in the Polar Flow **phone app**, returning 204. That is how the operator records H10 sessions. So an EXERCISE webhook would probably never fire for exactly the sessions this is for. Nothing found shows a v4 (Dynamic API) webhook.
- **(b) User identifier.** *Likely.* The payload carries `event`, `user_id` (Polar's user id), `entity_id`, `timestamp` and `url`. *Certain:* we store nothing that maps a Polar user id to our `user_id`. `polar_ingest.store_tokens` persists only `access_token`, `refresh_token`, `expires_at`, `scope` and `token_type`. The OAuth `state` carries our id only during the callback. v4 has no user-registration step. Whether the v4 token response carries a Polar user id (the v3 flow's `x_user_id`): *Guessing*. Capturing one is possible with no schema change, inside the encrypted token payload, but it would need a lookup that decrypts every row. Adding a column is a migration, which is hold (a).
- **(c) Verification.** *Likely.* A `Polar-Webhook-Signature` header carries an HMAC-SHA256 of the raw body, keyed by `signature_secret_key`. That key is returned **only once**, in the create response. The PING arrives before the key exists, so it is unsigned. A handler would read the raw body, compare in constant time, and fetch the data with the user's token rather than trust the payload. The payload is a pointer, not data.

**Recommendation: do not build now.** The pull triggers in #353 already give freshness on page open and a nightly guarantee. The webhook's value depends on caveat (a), which is probably fatal. Reopen only once a **non-prod probe** shows that an EXERCISE event fires for a Flow-app H10 session. The probe would register a separate test client in `admin.polaraccesslink.com`, because the one-webhook-per-client limit and the one-time secret make registering on the prod client a hard-to-undo act (#166). The probe would also establish (a) and whether (b)'s id is available from v4.

**State:** OPEN — probe owed before any build. Owner: Luke (test client + probe decision), Code (probe script + handler if green).

---

## Q195. The Hevy sync re-owns a workout (and a template) to whichever user synced last

`hevy_workouts.py:189` says a resync never re-owns a workout to another user; `:190` does exactly that (`row.user_id = user_id`). `hevy_workouts.hevy_id` is the primary key ALONE (globally unique) and `hevy_sets` hangs off it, so two users whose syncs fetch the same Hevy workout id fight for one row: the later sync owns it, the other user silently loses it, and the operator-owned annotations that ride the row (`excluded_at`, and on templates `laterality`, `adjudicated_at`, `bw_fraction`, `exercise_region_tags`) go with it. `hevy_templates._upsert_template` has the same shape (`row.owner_user_id = owner_user_id` on a table keyed on the Hevy id alone).

**Dormant today (operator-verified, 30 Sep 2026).** Users 1, 4 and 5 hold distinct Hevy accounts: the credential digests differ, and user 4's 54 workouts (2026-04-06 to 2026-09-28) were checked against Deb's own Hevy app and are hers, with no overlap with user 1's 65. The prod evidence agrees: user 4's sync ran 12 seconds after user 1's and user 1 still owned every one of its workouts. It bites only when two users' Hevy fetches return the same id (one Hevy account behind two keys, or a shared workout). **Fix required before any further user joins.**

Options (a proposal, not a ruling): (a) never re-own: ownership is set on insert only, and a same-id-different-user conflict is logged at ERROR and skipped; no migration. (b) key by `(user_id, hevy_id)`: a migration touching the `hevy_sets` FK. (c) an attach-time guard for Hevy like #358's (the `account_fingerprint` column and the provider-keyed index already exist), which prevents the shared-account case but not a shared workout id.

**State:** OPEN — a fork on the fix, and a defect to fix before user-count grows. Owner: Luke (rule the option), Code (fix + a test that runs two users' syncs over one id).

---

## Q196. The MCP OAuth provider is in-memory: tokens never expire, outlive a deleted user until restart, and are lost on every redeploy

`oauth_provider.PersonalOAuthProvider` keeps its clients, authorization codes, access and refresh tokens and pending logins in process dicts, and issues tokens with `expires_at=None`. Consequences, each read from the code and pinned by `test_mcp_provider_really_persists_nothing`: (1) every deploy or restart drops every MCP session (at least five backend deploys on 30 Sep alone: 01:51, 04:05, 08:42, 08:55 and 10:10 UTC); (2) a token for a deleted user keeps resolving to that `user_id` (finding no rows, failing on writes) until the process restarts; (3) nothing can be revoked or inventoried from the database, so `retire_user`'s dry run can only state that it cannot see them; (4) tokens never expire. MCP sign-in itself verifies email and password against `users` each time. Found while building the retirement dry run (#360); user 7 was held partly for that reason (the database cannot show whether an account backs an MCP or demo sign-in) and was retired on 30 Sep once the operator confirmed it a test account (#362).

Options (not a ruling): persist tokens in a table (hashed, with expiry and revocation; a migration), give the in-memory tokens an expiry only, or accept and document it. If persistence is added, the retirement dry run's MCP paragraph and the pinning test must change with it.

**State:** OPEN — needs a ruling on whether MCP sessions must survive a deploy and be revocable. Owner: Luke (rule), Code (build).

---

## Q197. Plan-conformance adjudication: how deviations from a planned session are judged

#363 rules that a quota slot is satisfied by doing the PLANNED session. That leaves the judgment of a session that
does not match its plan: moved, substituted, added to, cut short. This question is that judgment. **Everything below
is a chat proposal, not ruled.** The thresholds are placeholders.

**Proposal (2026-10-01).**
- **Match by identity, within the week, not by date.** A logged workout is matched to a planned session by routine
  and exercise overlap. A session done on another day is recorded as MOVED, not as a deviation.
- **Per planned exercise, one of four outcomes:**
  - *done*: logged as planned.
  - *substituted*: a different exercise with the same PRIMARY region (region tags carry this; see Q27).
  - *added*: in-brief if its region is in the session's planned region set. Out-of-brief neither counts nor
    penalises.
  - *dropped*.
- **Drops: auto-credit first.** If a same-window activity covers the dropped regions, the drop is credited. This
  needs a coarse activity-type → region map for non-Hevy activities (Pilates → trunk/core, for example). Worked case:
  the Monday session moves to Tuesday; core is dropped because a fixed Pilates appointment followed. Covered, counted.
- **Bands.** Region-matched share of planned working sets ≥ ~80% with no restriction hit → auto-tick. < ~50% → not
  done. Between → the operator gets a one-tap confirm with a REASON CODE: covered elsewhere / time / pain / fatigue /
  equipment.
- **Pain reason = the per-session pain capture point** (moved from Q27). A "pain" reason routes to the restriction
  record `{target, qualifier, side, reason, source, review_date}`, including the pain-gated progression qualifier.
  The restrictions in force at the move are recorded in Q27 (lumbar, L knee squat depth, L thumb) as evidence.
- **Repeat drops flag the plan.** A drop reason repeating across weeks on sessions done ON their planned day flags
  the plan for revision. Drops in MOVED sessions do not.
- **No LLM in the verdict.** It is deterministic. An LLM may write the one-line explanation shown on the confirm.

**Hypothesis to verify before the design relies on it.** Does the Hevy workout payload carry the source routine id?
If not, matching falls back to date window + exercise overlap. Findings (2026-10-01, this session):
- *Certain:* nothing in this repo reads a workout-side routine id. `routine_id` appears only on the routine
  read/update paths (`connectors/hevy.py`, `routers/chat.py`, `mcp_server.py`, `context_builder.py`), which take a
  routine id as INPUT.
- *Certain:* the untouched workout payload is already stored. `hevy_workouts.raw` is JSONB and `hevy_workouts.py`
  writes `row.raw = w`. If Hevy sends the field, it is in prod storage now and needs no re-fetch.
- *Not verified:* whether Hevy sends it. The public API docs (`api.hevyapp.com`) are blocked by this container's
  egress policy. From memory the public Workout object includes `routine_id` (*Guessing*, not evidence). This is an
  instruction to verify, not a fact.
- **Verification query (operator, via `railway connect` to `health-app-DB`):**

      SELECT count(*) AS n,
             count(*) FILTER (WHERE raw ? 'routine_id') AS has_key,
             count(*) FILTER (WHERE coalesce(raw->>'routine_id','') <> '') AS non_empty
      FROM hevy_workouts WHERE user_id = 1;

  Read `has_key` against `non_empty`: a key that is present but always null means Hevy sends the field and only
  workouts started FROM a routine fill it. That is still usable for matching, but it cannot cover workouts started empty.

**Dependency.** Plan↔log reconciliation, the unbuilt consumer named in Q24 (`laterality` and any `capability_state.side`
join wait on it too). This is the same component. Q27's region tags feed the substitution test.

**State:** OPEN — chat proposal, not ruled; the Hevy routine-id check is owed before design relies on it. Owner: Luke.

---

## Q198. Source-neutral re-zoning from raw HR (Polar and any other pathway the inventory shows)

Raised 2026-10-01 with #364. #364 zones `health_connect` rows only; Polar rows keep the zones Polar computed, under Polar's own
HRmax and limits. This follow-on is to re-zone Polar (and any other pathway with raw per-sample HR) onto the same model from
`hr_samples`, with a full-history recompute. The follow-on brief is scoped from the inventory below, not from chat's
assumptions. The table is the S0(e) inventory carried verbatim, updated with the prod reads of 1 Oct 2026 (operator-run
queries Q1/Q3/Q4/Q7 on `health_connect_record_sources`, `aerobic_sessions` and `health_connect_sync_events`). A negative
covers only the exact pathway tested; anything not tested says "untested".

| pathway | raw per-sample HR available? | resolution (in activity / outside) | typical lag to arrival | history depth reachable | currently persisted? (where, or "discarded at <file:line>") | evidence | exact endpoint / path tested |
|---|---|---|---|---|---|---|---|
| Health Connect · `com.garmin.android.apps.connectmobile` | Y | in activity: median gap 7-16 s, max 25-44 s; passive (outside activity, and Pilates rows 69/85/92): exactly 120 s | newest sample 0.0-7.6 h old at each of 47 POSTs; every POST re-sends ~7 days, so late in-bout HR reflows for 7 days | 17,828 records since 2026-08-23; deepest re-post seen 30.9 days (a `periodDays=30` POST) | before #364: discarded at `routers/health_connect.py` `_capture_record_sources` (keeps type, timestamp, writer only; bpm fed only the daily median in `_aggregate_day`). From #364's deploy: `hr_samples` | prod queries Q1, Q3, Q4 (operator, 1 Oct 2026) | `POST /health-connect/sync`, `heartRate[]` of `{time, bpm, sourcePackage}` |
| Health Connect · `com.sec.android.app.shealth` (Samsung Health / Galaxy Ring) | Y until 2026-09-14 | median 10 s, max 10 s; the HR stream starts ~3.5 min after the walk's start (rows 79-83) | as above | 28,511 records, 2026-06-27 to 2026-09-14, 76 days; none after 14 Sep (Samsung exercise rows 68/84 have no same-writer HR) | as above | Q1, Q4 | same |
| Health Connect · `fi.polar.polarflow` (H10 via the Polar Flow app) | Y | median 1 s, max gap 1-5 s (row 88: 2,026 samples in 33.8 min) | as above | 24,332 records on 9 days since 2026-06-30; 14 Polar bouts have an HC copy (operator-reported, Q7); sessions before 30 Jun (rows 29-42 and their twins) have no HC copy | as above | Q1, Q4, Q7 | same |
| Health Connect · `unknown` writer | Y, no identity | untested | n/a | 13,939 records, 2026-06-24 to 2026-07-04 (before the identity cutover); never attributable | as above | Q4 | same |
| Health Connect · `nl.appyhapps.healthsync`, `com.withings.wiscale2` | Y | untested | n/a | 468 records (27-28 Jun) and 14 records (29 Jul to 26 Aug) | as above | Q4 | same |
| Polar AccessLink v4 `samples` | untested. Third-party summaries (one web search; `polar.com` is egress-blocked here) say a `samples` feature exists returning per-second HR inline: a hypothesis, not evidence | untested | untested | untested. The `zones` feature caps `to - from` at one day (#261, live-probed); the cap for `samples` is untested | never requested: `connectors/polar.py` `list_zoned_sessions` sends `features='zones'` only; if fetched, `import_polar._parse_session` reads only `exercises[0].zones[].inZone` and would drop it | tree; one web search | `GET /v4/data/training-sessions/list?features=samples`; read OWED: `s0_polar_read.py --mode samples` (may refresh the Polar token via the app's own `store_tokens`) |
| Polar Flow export (ZIP) | untested | untested | manual upload (user-triggered) | the whole account at export time (Likely) | discarded: `import_polar.import_flow_export` opens only `training-session_*.json` members and `_parse_session` reads only `exercises[0].zones[].inZone` | tree | read OWED (local, no token): list the ZIP's members and one session's `exercises[0]` keys |
| Garmin direct connector (`scripts/garmin_sync`, `connectors/garmin.py`) | untested | n/a | n/a | n/a | not fetched: the connector calls only `get_hrv_data` (5-min RMSSD, not HR) and the social-profile call; no HR or activity endpoint is called anywhere | tree | none. Stays untested; no client built (operator, 1 Oct). A live read must follow #361 (never refresh a Garmin token) and build on `scripts/garmin_identity.py`'s no-refresh seam |

Separate from raw HR but needed to compare with Polar: the per-zone LIMITS Polar applied. They are not persisted (`_parse_session`
reads `inZone` only, for both v4 and the Flow export), and whether either payload carries them is untested; read OWED:
`s0_polar_read.py --mode zones` (prints the zone dicts raw, derives the implied HRmax and % bands).

**Update (5 Oct 2026, #384).** The `s0_polar_read.py` reads named above (`--mode zones` and `--mode samples`) are retired as owed: the file is in no repo, ref or container. The operator reads Polar Flow's profile HRmax by hand and reports it as context. The per-limit read of Polar's own zones, and the `samples` feature's availability, stay untested.

**What the data already shows.** The 28 Sep elliptical is three rows (HC `fi.polar.polarflow` #88, HC Garmin #89, `polar_v4` #91, the
only one zoned before #364). Row 88 is the same H10 stream Polar zoned, at 1 s: it isolates the zone MODEL (HRmax and bands) from the
sensor. #364's G2 report compares HC-zoned minutes per band against Polar's stored zones for every HC row that shares a bout with a
Polar row, as the interim invariance check.

**To decide.** (a) Whether Polar rows with an HC copy are re-zoned from `hr_samples` (a series-wide change: it moves the metabolic
series, so it needs a ruling and a recompute, never an edit). (b) The pathway for sessions with no HC copy (the Flow ZIP's samples if
the read shows they exist, or keep Polar's zones). (c) Whether Polar raw HR through the API is worth fetching at all, given HC already
carries 1 s Polar H10 HR from 30 Jun.

**State:** OPEN. Not blocking; #364 stands without it.

---

## Q199. HRmax benchmark test (Echo Bike) to replace the observed seed

Raised 2026-10-01 with #364. User 1's HRmax is seeded at 173 bpm, provenance `observed`: the highest chest-strap session maximum
in a year (Fitness sessions 2026-06-17 and 2026-07-17; the next two are 172 and 173). An observed training maximum is a floor on
true HRmax, not an estimate of it, and every zone boundary is a fraction of it. A maximal-effort Echo Bike test would give a
`tested` value. It lands as a NEW `user_hrmax` row with a later `effective_from` (never an edit), after which the chain run reflows
the affected rows. Until then the over-ceiling count in the chain report is the evidence: a plausible sample above 173 flags its row
and never raises HRmax.

**To decide.** The protocol and date, who supervises it, and the `effective_from` convention for a tested value (from the test date
forward, or backward over the seed's range as the seed does).

**Update (3 Oct 2026, with #367).** Operator-reported, not read by Code (no DB route). The observed 173 came from Polar rows 35 and 47, both short conditioning segments, not rugby (Guessing: the two Fitness sessions named above, 2026-06-17 and 2026-07-17; the row dates were not given). Only three field sessions were recorded through Polar all season (rows 31, 67 and 90). So the seed is a maximum seen in conditioning segments, not in field play, and a maximal-effort test is owed. This entry is the home for that test; its "To decide" is unchanged.

**Update (5 Oct 2026, session `hc-zones-verify`).** The seed row is `user_hrmax` id 1 (user 1, effective 2026-03-01, 173, `observed`), written 2026-10-01 07:49:05Z by the operator's `scripts/set_hrmax` run. The first post-deploy read of the zones against Polar's own is in the ROADMAP HC zones row. On the 28 Sep H10 bout (HC row 88 against Polar row 91, same stream, same `hr_max` 167) our 50/60/70/80/90-of-173 bands put more time in z1 and z5 and less in z3 and z4 than Polar's stored zones, and in all seven HC-with-Polar-twin bouts HC z5 is at or above Polar's while z3 and z4 are at or below. That is what a Polar HRmax above 173 would produce (Likely, not shown); `s0_polar_read.py --mode zones` would print it. It bears on this test: a higher true maximum would move every boundary. The ruling on bands or HRmax is the operator's and nothing was edited.

**Update (5 Oct 2026, #384).** The operator ruled that HRmax changes: target 177 as a #383 restatement (retroactive from 2026-03-01, 173 and the reason kept), bands unchanged, because 173 was observed only on an Echo bike and is a modality-limited lower bound. Nothing is applied yet; the corrective-path design is owed as its own proposal. This test remains the route to a `tested` value, which would restate again.

**Update (5 Oct 2026, #385).** The operator set the target at 175, not 177 (#385 supersedes #384's value; the 177 projection brackets Polar's zoning). The restatement path and the `adjusted` provenance are built and held for release. A `tested` value from this test would be a further restatement: `set_hrmax --restate --provenance tested`.

**State:** OPEN. Not blocking.

---

## Q200. `health_connect_syncs.resting_heart_rate` is the day's median of all HR samples, but the coach reads it as "Resting HR"

Raised 2026-10-01 with #364 (operator-recorded; found while tracing where HR bpm is used). `routers/health_connect._aggregate_day`
stores the MEDIAN of EVERY heart-rate sample posted for the day in `health_connect_syncs.resting_heart_rate` (the "Heart rate" block,
`:1012-1019`). `context_builder.py:1214-1215` presents it to the coach as "Resting HR: N bpm"; `routers/recovery.py:131` and
`mcp_server.py:228` (aliased `sleep_hr_bpm`) carry the same value. A day with a hard session posts a higher median than a rest day
with the same true resting rate, so the coach is told a training-contaminated number is a resting one. No decision here relies on it.

**To decide.** Rename or relabel it honestly (for example "median HR"), or derive a true resting value (for example the lowest
sustained overnight stretch, which `hr_samples` can now supply).

**State:** OPEN. Not blocking; a read-surface honesty question.

---

## Q201. Two sources for one bout: cross-source dedup is read-time and silent, and ranks by richness, not by the #365 hierarchy

Raised with #365. Verified against master `054d2d9` by reading code and running the real `arbitrate()` on synthetic rows; the prod rows were not read (no DB route in that session).

**Question.** When one session arrives from two sources (Garmin through Health Connect, and Polar), does ingestion or load dedupe it? Live case: 1 Oct 2026, about 18:49. Garmin "Trail Running" 3.34 km 21:33; Polar "Jogging" 3.36 km 22:05.

**Findings.**
- **Ingestion does not dedupe across sources.** Both rows persist. HC admission drops only `com.hevy` mirrors and a lower-writer-class record whose start instant is identical to a higher one's (`routers/health_connect.py:689-731`); two independent detections are deliberately left to read time (`:679-681`). Polar sync skips a session only when the same `source_session_id` already exists under a Polar source (`polar_ingest.py:155-168`), and never looks at HC rows.
- **Load dedupes at read time.** `compute_metabolic_load_events` reads through `arbitrated_sessions` (`load_events_metabolic.py:177`) and skips non-canonical rows (`:197-199`). Felt load, the MCP session tools and session focus read canonical rows only (`reads/psychological_reads.py:312`, `mcp_server.py:559,749`, `session_focus.py:168`).
- **The rule.** Two rows are one bout when they overlap by at least 50% of the shorter duration (`reads/aerobic_reads.py:38,218`). The winner is the richer data tier (zones, then HR only, then neither), then source rank (`polar_flow_export` > `polar_v4` > `health_connect`), then the longer duration (`:63-67,125-167`).
- **Simulation (real `arbitrate()`, synthetic rows at the reported durations; not prod data).** Exactly one canonical row when the Polar start is within about 640 s of the Garmin start, whatever the zone state of either row. Two canonical rows, so two metabolic deposits, at about 700 s or more, or when either row has no usable start/stop (`:186-187,194-198`). Polar wins when both rows are zoned or when the Garmin row has no HR; Garmin wins only when it is zoned and the Polar row has HR only.
- **Suppression is silent.** `sessions_skipped_non_canonical` exists only in the transform's return dict (`load_events_metabolic.py:230-238`) and no non-test code reads it. The `canonical` flag is exposed on the Polar aerobic list only (`routers/polar.py:316-335`).

**Gaps.**
1. #365 makes the watch the owner of running, but when both rows are zoned the Polar row is canonical and the Garmin row is dropped. The rule is richness-first (#356); the hierarchy is not an input.
2. Nothing tells the operator or the coach that a recorded session was suppressed as a twin.
3. A pair whose starts are more than roughly ten minutes apart, or that lacks a time, double-deposits. The tolerance follows from the 50% rule and the two durations; it is not a declared number.

**Live case (owed, operator).** Over `railway connect` to `health-app-DB`, user 1:

    SELECT id, source, source_package, sport_id, sport_name, start_time, stop_time, duration_minutes, hr_avg, z1_seconds FROM aerobic_sessions WHERE user_id = 1 AND session_date = '2026-10-01' ORDER BY start_time;
    SELECT source_ref, load, occurred_at, provenance->>'zone_source' AS zone_source FROM load_events WHERE user_id = 1 AND load_window = 'metabolic' AND occurred_at >= '2026-09-30' ORDER BY occurred_at;

The two start times settle which side of the tolerance the pair falls. One metabolic row for the run means dedup held, and `source_ref` is the winning `aerobic_sessions.id`. Two rows for the run is a data defect: report it and rule before anything is touched, and nothing is deleted without that ruling.

**To decide (Luke).** (a) Does the hierarchy enter arbitration, and where relative to the data tier (today a row without HR never suppresses a row with HR)? (b) Must suppression be surfaced, for example an "also recorded by" note on the canonical row? (c) Is the start-offset tolerance acceptable as it stands?

Code's lean, not a ruling: leave arbitration alone. With the H10 paired to the watch (#365) a run produces one record and the question stops arising for runs; surface suppression instead, after the live case is read.

**Update (3 Oct 2026, with #366).** The operator read the live case in prod on 2 Oct (operator-reported; Code has no DB route). Row 93 (`health_connect`, Garmin package, HC sport 56, stored "Running") and row 95 (`polar_v4`, `sport_id` 4) were both zoned, `hr_avg` 145 each, starts 9 s apart. **Dedup held:** `load_events` carries one metabolic row for the run, `source_ref` 95, load 81.85. Polar won on source rank, which is what the findings above predict for two zoned rows, and the canonical row was labelled "Walking": id 4 had been mis-mapped (it is "Jogging" in Polar Flow), fixed by the corrected Polar sport-id map (#366). The row with the watch's own label (93) was the suppressed twin, so gap 1 above is now observed, not only predicted, for the running class.

**The tie-break was scoped and dropped, not built.** The scoped change was: when candidates tie on data tier, prefer the #365 owner for the running class (HC sport 56/57 from the Garmin package) before source rank. It is deferred because a chat design for a source-agnostic input layer (day-level merged per-second HR with a source precedence) is pending and would make session-level metabolic arbitration redundant. `_win_key` is untouched; `metab-v1` (Edwards zone-seconds) stays the metric. Decision (a) is therefore deferred to that design rather than ruled here; (b) and (c) are unchanged.

**State:** OPEN. Owner: Luke (rule, with the input-layer design). The live case is read and no longer owed. Not blocking.

---

## Q202. RPE floor: a session with no usable device HR deposits no load, and nothing floors it

Raised with #365. Verified against master `054d2d9`.

**Question.** Does the load model compute sRPE × duration when a session has no device HR? Can a session with zero device data exist in load at all?

**Findings.**
- **No floor.** The metabolic load is Edwards zone-seconds TRIMP only; a session with no usable zones emits no `load_events` row and is counted in `sessions_skipped_no_zones`, which is in the return dict only (`load_events_metabolic.py:24-29,99-112,204-206`). There is no HR-based fallback and no RPE term in any physical load.
- **sRPE × duration exists in one place:** the regression target of `psychological_residual`, from the day's whole-day `daily_records.session_rpe` (`reads/psychological_reads.py:363-392`, `models.py:164`). It is a diagnostic, not a load input.
- **A session with zero device data cannot exist in `aerobic_sessions`.** Its only writers are HC ingest (`routers/health_connect.py:765`), Polar sync (`polar_ingest.py:169`) and Polar import (`import_polar.py:196`). No manual path writes it. A Hevy strength session is the exception that needs no device: Tier-0 loads from logged sets, and a per-set RPE only bands RIR (`load_events.py:129-141,180-200`).
- **What puts a watch-owned run into load (#365).** A Garmin HC row is zoned by `hc_zone_enrich` from same-writer HR samples (#364). It deposits only if a `user_hrmax` row is in force and the credited coverage reaches 0.6; otherwise it stays zoneless and deposits nothing (`hr_zones.py:48`, #364).

**Gap.** A watch-owned run without usable HR reads as zero load, silently.

**To decide (Luke).** For a zoneless watch-owned run: (a) stay fail-closed but make the absence explicit (Q203); (b) floor it with RPE × minutes, which is Q189's design fork (capture surface, scaling into lane units); (c) both. Q189 covers device-only sessions such as Pilates and swimming; this entry is the running case the hierarchy creates. Resolve together.

**Brief verified and halted (4 Oct 2026, the `srpe-floor` session; master `53f5925`).** The sRPE-floor brief (A: an Edwards-skipped unzoned device session emits a floor event; B: an "unrecorded session" marker row carrying date, class, minutes and sRPE; C: a per-athlete kappa fitted from paired sessions) was verified before any build, and nothing was built. Findings:
- **#326 forbids Case B.** Its Context says "no self-reported session rows, no load and no TRIMP", its Rationale says "The marker changes confidence, not values", and the Q169 principle it ratifies says "No per-session detail, RPE, duration, or time" and rejects "an sRPE variant". **Ruled (operator, 4 Oct): #326 stands, Case B is dropped, Q169's rejection is not superseded.**
- **sRPE is one rating per day, overwritten, with no snapshot.** `daily_records.session_rpe` (Float, 0-10, `models.py:164`) is written by `POST /pm` (`routers/checkin_v2.py:758`, nulled when `trained_today` is false; `pm_timestamp` is overwritten too, `:755`). A delete-and-reinsert transform (`load_events_metabolic.py:180-185`) would follow a revised rating, so "sRPE at recording time only" needs an immutable capture (Q209). `users.rpe_complete_from` is the Hevy set-RPE epoch (`load_metrics.py:297`), not a `session_rpe` capture epoch.
- **The rollup does not pick up a new formula version without wiring.** `compute_load_metrics` reads `load_events` for one `formula_version` (`load_metrics.py:277-283`), and the chain calls the metabolic step with `metab-v1` only (`scripts/refresh_load.py:158-161`), so `srpe-floor-v1` rows would never roll up. **Ruled (operator, 4 Oct): option (a), when the floor is built: the metabolic rollup reads both versions and the event rows keep their own. Nothing now.**
- **A day's RPE does not describe every session.** Felt-load already leaves Walking, Pilates, Yoga and Stretching out of its RPE minutes (#322 S3, `reads/psychological_reads.py:290-294`) and skips an aerobic row that overlaps a counted Hevy workout (`:316-317`). The Case A lean is recorded on Q189.
- `load_events.provenance` is JSONB (`models.py:12,1295`; migration `c7d9e2f14a86:55`). MCP `get_training_load` reads `load_metrics` only (`mcp_server.py:917-941`), so a floor event's `provenance.method` would not show there without a new read.
- The brief's "3 Oct: 10 skipped for no zones, 12 of 26 HC rows unzoned" is operator-reported and appears in no repo text; it was not used.

**S1 result (operator-reported, 4 Oct).** The paired-session query returned **n = 2** pair-days (2026-06-17 and 2026-09-09). No fit is possible; the gate was n >= 20. The operator confirmed the cause: the bedtime check-in is the only RPE surface and is often skipped. **Scope change (operator): report and governance only. No migration, nothing built. The floor and kappa wait on a capture surface (Q209).**

**Capture rate, OWED (operator).** The count of training days that carry a `session_rpe` has not been read. Read-only, one statement; a training day is any non-excluded Hevy workout day or `aerobic_sessions` day (walks included): `WITH tr AS (SELECT session_date AS day FROM aerobic_sessions WHERE user_id = 1 UNION SELECT (start_time AT TIME ZONE 'Australia/Brisbane')::date FROM hevy_workouts WHERE user_id = 1 AND excluded_at IS NULL AND start_time IS NOT NULL) SELECT date_trunc('month', tr.day)::date AS month, count(*) AS training_days, count(*) FILTER (WHERE d.session_rpe IS NOT NULL) AS with_session_rpe, count(*) FILTER (WHERE d.pm_timestamp IS NOT NULL) AS with_pm_checkin FROM tr LEFT JOIN daily_records d ON d.user_id = 1 AND d.date = tr.day GROUP BY 1 ORDER BY 1;` Append the result here when pasted.

**Scope note (4 Oct 2026, operator, with #369).** The Q202 brief is to follow. Its case A is rows inside the Garmin in-activity HR lag window (about 7 days from the session). It is not a cover for the scheduled-sync failure (#370).

**Floor input now exists for watch sessions (4 Oct 2026, #372, #373, #374).** The per-session capture this entry was waiting on is built for Garmin-watch sessions (Q209, closed): an immutable per-activity RPE (CR-10) and feel, linked to the Health Connect row, landed via PR #309, first live run owed. No kappa fit is possible until paired data accumulates (n = 2 paired days when read). The two rulings recorded above are now decisions: #326 stands and Case B is dropped (#373); the rollup reads both formula versions, when the floor is built (#374). H10-only sessions have no captured rating (Q189).

**State:** OPEN. Owner: Luke. Not blocking.

---

## Q203. Missingness: the load model cannot tell "expected device data absent" from "low load"

Raised with #365. Verified against master `054d2d9`.

**Question.** Can the model distinguish expected device data being absent from a light session? Is there a data-completeness field?

**Findings.**
- **No.** A day with no events is an exact zero (`load_metrics.py:207`), and the trailing means count such days as zero (`:148-153`). `DayMetric` has no completeness field (`:136-145`); `maturity` records only how long the series is (`:229`).
- **Partial signals exist; none reaches the series or the coach.** `sessions_skipped_no_zones` and `sessions_skipped_non_canonical` (return dict only, `load_events_metabolic.py:230-238`); the `hc_zone_enrich` reasons `sparse | no_same_writer_hr | no_hrmax` (`hr_zones.py:48`), printed by the chain (`scripts/refresh_load.py:236-245`) and not stored per row; the resolver's "(unzoned)" note on a counted conditioning session (`context_builder.py:1805`); the Polar zone-coverage counts (`reads/aerobic_reads.py:324-376`).
- **No concept of an expected device.** `recorded_via` on a slot is metadata with no consumer, and its closed set has no Catapult value (`engine/training_phase.py:65-71,235`). Catapult appears only as a `source` tag on capability observations (`engine/observations.py:47`). Q124 (field-session ingestion) is OPEN, so the load model has no external-load lane (accel/decel, high-speed running, contact). No consumer reads contact data, so nothing today reads an absent SPT as low contact; the #365 principle binds the first consumer that does.
- **Related and ratified, not built.** Q169 (#326) records a date-range "trained, not fully recorded" marker; the build is OWED and no table or code exists on master. It covers a day on which nothing was recorded, not a session captured by one device while another was expected.

**Gap.** Absence has no representation that survives into a consumer. A missing SPT file, a zoneless watch run and a rest day all read as zero.

**To decide (Luke).** The shape of an explicit expected-but-absent signal. (a) Extend #326's marker with a closed kind for device-absent. (b) Derive it at read time from a declared expectation: add a Catapult value to `recorded_via` (a validator-only change, like #317) and flag a window in which the declared source has no row. (c) A per-session operator status.

Code's lean, not a ruling: (b) for the declared case, being read-time with no schema, and #326's marker kept for days with nothing recorded.

**State:** OPEN. Owner: Luke. Not blocking.

---

## Q205. Verify the Polar sport-id table against Polar's own v4 list

Raised with #366. `import_polar.SPORT_NAMES` is the Polar Flow sport-id list (ids 1-142), but the copy read is a secondary one: Polar Flow's sports settings page as reproduced at https://github.com/pcolby/bipolar/wiki/Polar-Sport-Types. Polar's own page and its v4 docs are egress-blocked from the build environment, so the table has not been compared with anything Polar publishes directly. Two live datapoints agree with it (id 4 "Jogging", id 55 "Cross-trainer"), and the operator confirms the labels Polar shows are the sport profile chosen at the start of a recording.

**To do.** At the next Polar re-auth, call `GET /v4/data/sports/list` and diff it against `SPORT_NAMES`. A mismatch means a corrected table and a backfill (`scripts/polar_sport_backfill.py` is reusable as it stands: it relabels from the retained `sport_id`).

**The dependency to surface.** That endpoint sits behind the `sports:read` scope, which `connectors/polar.py:39` does not request, and the ruling for #366 is not to add it. So the check can run only if the scope is requested at a re-auth deliberately, which is Luke's call at that point. Without the scope, the cheaper evidence is the operator's grouped `sport_id` query (19 rows on 2 Oct) read against the labels Polar Flow shows for those ids: each id seen in prod can be confirmed that way, and an id never seen in prod cannot be wrong in a way that shows.

**Ruling (3 Oct 2026, #368).** Add `sports:read` at the next Polar re-auth, whatever occasions it, and verify the sport table then. Nothing before: no re-auth is forced for this, and no scope change lands now. The scope is the `SCOPES` constant at `connectors/polar.py:39`, so the one-line change is made as the first step of that re-auth, before the authorise URL is built; the brief for that re-auth names it.

**State:** OWED. Loop-close: the next Polar re-auth, whatever its reason; request `sports:read` then and diff `GET /v4/data/sports/list` against `SPORT_NAMES` (#368). Owner: operator (the re-auth). Not blocking.

---

## Q206. Polar H10 rows that are whole Hevy gym sessions: what the app does with them today, and what the input-layer design has to reckon with

Raised with #366 as a report-only investigation: nothing is built and no design is proposed. **Operator-reported (2 Oct 2026; not read by Code):** most Polar rows are H10 recordings of WHOLE Hevy gym sessions, warm-up cardio included, not standalone aerobic sessions. Example: 2026-04-25, Hevy "Back-Safe Full Body", 07:40 local, 2h19m, with the Polar zones attached to the Hevy session as an image only. Code facts below are read from master `7087026` (file:line). The entry is framed as input to the pending source-agnostic input-layer design (day-level merged per-second HR, source precedence); `metab-v1` stays the metric and the baseline any alternative is compared with. Queries were checked with a Postgres parser (`pglast`); none was run.

**(a) Which Polar rows overlap a Hevy workout. OWED (operator), unmeasured.** The app's test is strict interval intersection, all four endpoints present (`reads/aerobic_reads.py:279-298`); a row with a NULL start or stop never counts as overlapping. This mirrors it (it keeps non-canonical rows, and filters Hevy on `excluded_at IS NULL` only, where the door also drops an unadjudicated dedup pair). Detail, one row per overlapping workout (a row with no overlap shows NULL Hevy columns):

    SELECT a.id AS aerobic_id, a.source, a.session_date, a.sport_id, a.sport_name, round(a.duration_minutes::numeric, 1) AS dur_min, a.start_time, a.stop_time, h.hevy_id, h.title, h.start_time AS hevy_start, h.end_time AS hevy_end FROM aerobic_sessions a LEFT JOIN hevy_workouts h ON h.user_id = a.user_id AND h.excluded_at IS NULL AND a.start_time < h.end_time AND h.start_time < a.stop_time WHERE a.source IN ('polar_v4', 'polar_flow_export') ORDER BY a.start_time;

Counts, with the untimed rows split out:

    SELECT a.source, (h.hevy_id IS NOT NULL) AS overlaps_hevy, count(DISTINCT a.id) AS sessions, count(DISTINCT a.id) FILTER (WHERE a.start_time IS NULL OR a.stop_time IS NULL) AS untimed FROM aerobic_sessions a LEFT JOIN hevy_workouts h ON h.user_id = a.user_id AND h.excluded_at IS NULL AND a.start_time < h.end_time AND h.start_time < a.stop_time WHERE a.source IN ('polar_v4', 'polar_flow_export') GROUP BY 1, 2 ORDER BY 1, 2;

**(b) How an overlapping row is treated today.**
- **Metabolic load: deposited.** The transform has no overlap test. It emits one row per canonical, zoned `aerobic_sessions` row (`load_events_metabolic.py:177-206`), and its header says a session captured by both Hevy and Polar deposits into different windows by design (`:31-33`). A gym-session H10 trace therefore becomes metabolic load over the whole recorded interval, rests between sets included.
- **Felt load: nothing.** An aerobic session overlapping a counted Hevy workout contributes no minutes and no tally; the Hevy minutes count (`reads/psychological_reads.py:316`).
- **Resolver and quota: not claimed.** An overlapping canonical session is `concurrent_strength` and never reaches an activity or `load_window` slot (`engine/resolver.py:391-392`); it is listed in `uncounted[]` and rendered "conditioning session overlapping a gym workout" in the chat context (`context_builder.py:1657-1658`). Capacity slots count Hevy only.
- **Coach and MCP visibility: inconsistent.** `get_training_sessions` lists canonical sessions with zones and no overlap marker (`mcp_server.py:547-572`), and the readiness summary counts them as sessions (`:738-758`). Nothing in `aerobic_format.py`, `session_focus.py` or `mcp_server.py` tests overlap. So the resolver and chat context read the row as strength, while the MCP reader sees a standalone aerobic session.

**(c) Does Hevy expose per-set or per-exercise timestamps.** The app stores workout-level `start_time` and `end_time` (`hevy_workouts.py:191-192`) and the full payload verbatim in `hevy_workouts.raw` (`models.py:1148-1200`, JSONB). The set reader takes `type`, `weight_kg`, `reps`, `duration_seconds`, `distance_meters` and `rpe` only, and nothing in the code or the test fixtures reads a timestamp at exercise or set level (`hevy_workouts.py:80-103`). **Not confirmed from Hevy's schema:** its docs host is egress-blocked from the build environment (Guessing: the public API has workout-level start, end, created and updated times and nothing finer). Because `raw` is stored untouched, one query settles it on real payloads:

    SELECT 'workout' AS level, k FROM (SELECT DISTINCT jsonb_object_keys(raw) AS k FROM hevy_workouts) w UNION ALL SELECT 'exercise', k FROM (SELECT DISTINCT jsonb_object_keys(e) AS k FROM hevy_workouts h, jsonb_array_elements(h.raw -> 'exercises') e) x UNION ALL SELECT 'set', k FROM (SELECT DISTINCT jsonb_object_keys(s) AS k FROM hevy_workouts h, jsonb_array_elements(h.raw -> 'exercises') e, jsonb_array_elements(e -> 'sets') s) y ORDER BY 1, 2;

**(d) Exercise-window HR inventory.**

| source | raw samples kept? | where / precision / retention |
|---|---|---|
| `health_connect`, any writer (Garmin `com.garmin.android.apps.connectmobile`; `fi.polar.polarflow` for the H10 via the Polar Flow app) | Yes | `hr_samples (user_id, sample_time timestamptz, bpm, source, source_package)`, unique on those four (`models.py:318-346`). Every posted sample is kept, with no window bound, `bpm` as received (`routers/health_connect.py:577-633`). Timestamps are parsed to UTC with the fraction stripped, so precision is 1 s and two same-writer samples in one second collapse to one (`:424-438`). No retention or delete path exists besides the user cascade. |
| `polar_v4` | No: zone-seconds only | `list_zoned_sessions` requests `features='zones'` (`connectors/polar.py:162-200`); the parser keeps `exercises[0].zones[].inZone` (`import_polar.py`, `_parse_session`). Per-sample HR through the API is untested (Q198). `ppi_data:read` is requested (`connectors/polar.py:39`) and nothing in the backend reads PPI. |
| `polar_flow_export` | No: zone-seconds only | Same parser. Whether the ZIP carries samples is untested (Q198). |

Resolution and depth, from the operator's 1 Oct prod reads recorded in Q198: Garmin in activity median gap 7-16 s and max 25-44 s (passive exactly 120 s), records since 2026-08-23; Polar H10 through HC median 1 s and max gap 1-5 s (row 88: 2,026 samples in 33.8 min), 24,332 records on 9 days since 2026-06-30, 14 Polar bouts with an HC copy. **Consequence:** a gym session before 30 Jun, such as 2026-04-25, has no HR timeline in the app at all, only five zone-second totals, so no per-exercise or per-set window can be computed for it from any stored data. Only the HC-covered days have a timeline to window.

**Gap distribution across stored sessions. OWED (operator).** Q198 gives per-writer medians and maxima, not a per-session distribution. This returns, for the 30 most recent timed `health_connect` sessions, each writer's sample count, median gap, longest gap and the number of gaps over 10 s and over 60 s (60 s is `hr_zones.MAX_SAMPLE_GAP_S`, the most credit a single gap earns):

    WITH s AS (SELECT id AS sid, user_id, start_time AS st, stop_time AS sp FROM aerobic_sessions WHERE user_id = 1 AND source = 'health_connect' AND start_time IS NOT NULL AND stop_time IS NOT NULL ORDER BY start_time DESC LIMIT 30), g AS (SELECT s.sid, h.source_package AS pkg, h.sample_time - lag(h.sample_time) OVER (PARTITION BY s.sid, h.source_package ORDER BY h.sample_time) AS gap FROM s JOIN hr_samples h ON h.user_id = s.user_id AND h.sample_time BETWEEN s.st AND s.sp) SELECT sid, pkg, count(*) AS n_samples, round(extract(epoch FROM percentile_cont(0.5) WITHIN GROUP (ORDER BY gap))::numeric, 1) AS median_gap_s, round(extract(epoch FROM max(gap))::numeric) AS max_gap_s, count(*) FILTER (WHERE gap > interval '10 seconds') AS gaps_gt_10s, count(*) FILTER (WHERE gap > interval '60 seconds') AS gaps_gt_60s FROM g GROUP BY sid, pkg ORDER BY sid, pkg;

**A parallel metric version beside `metab-v1`: yes by reading, not exercised.** `load_events` is unique on `(source, source_ref, load_window, formula_version)` (`models.py:1274-1278`) and its docstring says a new version's rows coexist beside the old until the rollup switches. The metabolic transform deletes and reinserts only `(user, FORMULA_VERSION_METABOLIC)` (`load_events_metabolic.py:19-21,181-184`), so another version's rows are untouched by it. The rollup takes `formula_version` as a parameter (`load_metrics.py:247,361-368`) and `load_metrics` is unique on both version axes. Every consumer pins the constant (`reads/psychological_reads.py:59`, `scripts/refresh_load.py:157-161`), so a shadow version is invisible until a reader is pointed at it. Two constraints: `source`, `unit` and `formula_version` are VARCHAR(20), and `source_ref` names one session, so a day-level metric needs a convention for what it points at. No schema change is implied.

**Results (3 Oct 2026).** Operator-run queries, reported by the operator; Code has no DB route and did not read them.
- **(a) Overlap.** `polar_flow_export`: 25 of 50 rows overlap a Hevy workout. `polar_v4`: 9 of 22. No untimed rows. The sessions from 15 Jun to 12 Aug exist in both Polar sources (twins) and arbitration collapses them. The pattern: a gym session is recorded as two Polar segments, a warm-up as Cross-trainer (id 55) followed by Circuit training (id 20). The VO2 bike blocks (17 and 24 Jun) sit inside Hevy sessions.
- **(b) Ruling, #367.** Gym-overlapping HR stays in the metabolic window: the transform deposits it as it does today. The fix is to expose the `concurrent_strength` marker in `get_training_sessions` and in the readiness summary so the MCP agrees with the resolver. Filed OWED, below.
- **(c) Hevy payload keys, confirmed on real payloads.** There is no exercise- or set-level timestamp. Exercise keys: `index`, `notes`, `sets`, `superset_id`, `title`, `exercise_template_id`. Set keys: `index`, `type`, `reps`, `weight_kg`, `duration_seconds`, `distance_meters`, `rpe`, `custom_metric`. Per-exercise HR windowing is therefore not possible from Hevy data, which settles the Guessing in (c). The operator's convention is one recorded activity per block: warm-up/conditioning is one recorded activity and lifting another.
- **(d) Gap distribution, the 30 most recent HC sessions.** `fi.polar.polarflow`: median gap 1 s, max 1-5 s, no gap over 10 s. Garmin in activity: median 6-16 s, max 25-44 s, none over 60 s, so the 60 s cap (`hr_zones.MAX_SAMPLE_GAP_S`) did not bind on any of them. Sessions 68, 69, 71, 80-85 and 92 contain only Garmin passive samples (120 s) and are the `no_same_writer_hr` rows; that is Q207. `com.sec.android.app.shealth` writes 10 s samples on 79-83. Paired Garmin and H10 samples exist on 88, 89, 93 and 96 (calibration pairs).
- **Input to the pending design (Q201).** Whatever replaces session-level metabolic arbitration must still deposit HR recorded over a gym session (#367).

**State:** OWED. Ruled in #367: the deposit stays as it is, and the marker exposure is the fix. Loop-close: expose `concurrent_strength` in `get_training_sessions` (`mcp_server.py:547-572`) and in the readiness summary's session count (`:738-758`), so an MCP reader sees what the resolver and the chat context see. Display and counting only; no load value changes. Owner: Luke (brief), Code (build). The input-layer design stays with Luke (Q201). Not blocking. Related: Q198 (re-zoning from raw HR), Q201, Q203, Q124, Q207.

---

## Q208. Overlapping Health Connect syncs: the sibling read-then-add paths, and whether to serialise syncs per user

Raised 4 Oct 2026 with #371, which fixed the `record_sources` race (PR #305). The same shape remains on two paths. `_ingest_exercise_sessions` loads the user's existing `health_connect` rows and adds the missing ones through the ORM (unique `uq_aerobic_session_source`), and `sync()` does `.first()` then `add` for the per-day `HealthConnectSync` row. Two overlapping POSTs that both carry a new exercise or a new day can still collide. Since #305's `flush()` the failure surfaces as itself, but the sync still returns 500 and rolls back whole.

**What is known about the overlap.** Four POSTs started within 15 s on 3 Oct, two at the same instant (Railway HTTP log). The manual buttons are disabled while a sync runs (`SyncScreen.js:269,279`), so one tap cannot overlap itself, and the background task has no coordination with them (`backgroundSync.js:51`, `syncRunner.js:66`). The source is unknown (Guessing: the background task overlapping a manual run).

**To decide.** (a) A per-user advisory lock at the start of `sync()` (`pg_advisory_xact_lock`; Postgres only, no schema), so overlapping syncs queue. (b) `ON CONFLICT` upserts for the exercise and day rows: more change, and the exercise upsert carries the mirror-drop and the "never touch z*" rules. (c) A phone-side single-flight guard (companion repo). (d) Nothing until a second failure is seen.

Code's lean, not a ruling: (a), as the one change that closes the whole class, and (c) alongside P1 (#370).

**State:** OPEN. Owner: Luke. Not blocking. Related: #371, #370, Q207.

---

## Q212. A Move to a new phase seeds the posture, label, intent and slots from the outgoing phase: should posture carry over?

Raised 5 Oct 2026 (operator observation, 5 Oct: "recovery vehicles ranked first" under the phase `aerobic base`). Report first; nothing is changed until ruled.

**Source of the note, verified on master `21839a4`.**
- The note is emitted only when the OPEN phase's stored `probe_posture` is `suppressed` (`engine/selection.py:578-581`, `:687-691`). So by the code the open `aerobic base` row carries `suppressed`. It is not derived from the label: no backend code branches on a phase label, and there is no default for an unmatched name.
- **One value drives three behaviours.** (1) The effective probe budget is forced to 0 and the mode to fortify (`selection.py:574-581`; the note at `:695-700`). (2) The probe block is withheld (`:733-737`). (3) The recovery-first vehicle re-rank (`:646-650`; the note at `:687-691`). The re-rank fires on `probe_suppressed` alone, with no read of the label. So a posture carried by mistake also silences probing, and a phase cannot ask for the re-rank without the other two.
- **Where the value comes from, by path.** The wizard seeds `label`, `intent` and `probe_posture` from the current phase (`PhaseTransitionFlow.jsx:118-123`), so a Move keeps the outgoing posture unless the operator toggles it. The direct form has no default and refuses submit until one is chosen (`PhaseForm.jsx:22`, `canSubmit`). **Which one set it on 4 Oct is not read:** it depends on the row's `probe_posture` in the ledger, per row, which is owed (ROADMAP row 39).

**Question.** On a Move, should the new phase's posture be (a) seeded from the outgoing phase (today), (b) defaulted to `held`, or (c) left unset so the operator must choose, as the direct form does? Slots are seeded on purpose and marked as a prefill (F6); a posture is a quieter default with a bigger effect.

**If the three behaviours should come apart** (a separate question from the seeding, raised by the same observation). Options: (i) a third posture value. `training_phases` has a database `CHECK` on `probe_posture IN ('suppressed','held')` (`models.py:1107`, `ck_training_phase_probe_posture`), so this is a migration (held) plus the validator constant (`engine/training_phase.py:62`). (ii) A separate per-phase ranking field: a new column, also a migration. (iii) Drop the phase from the re-rank triggers, leaving readiness and life-load; no schema, but it changes decompression, whose re-rank the T2 tests pin (`tests/test_training_phase.py:478-513`). Code's lean, not a ruling: none yet; fix the seeding first (a)-(c) and see whether the coupling ever bites.

**Evidence (operator, 5 Oct 2026).** `suppressed` on `aerobic base` is intended: the operator chose it to stop probes while run, sprint and VO2 work all start. They want probe-off WITHOUT the recovery-first ranking, which is the case for separating the three behaviours (the options above), and they did not choose the ranking.

**Ruling (operator, 5 Oct 2026).** Deferred to the aerobic base review (16 Nov 2026). `suppressed` stays, and the recovery-first ranking is accepted for this phase. No change is made. Whether to separate the behaviours, and whether a Move should seed posture from the outgoing phase, are decided at that review.

**State:** OWED. Loop-close: the aerobic base review (16 Nov 2026) decides the separation (the options above) and the seeding (a)-(c). Owner: Luke. Not blocking. Related: #317, #375, #378, Q211 (closed).

---

## Q213. The HR input layer, per second: Edwards retained, source precedence, bounded gap interpolation, and the sRPE floor

Raised 5 Oct 2026 (operator; carried from the 1-4 Oct close-out). **Not drafted; nothing built; this records the design direction the operator named, not a ruling.** The direction: Edwards TRIMP stays the load measure; a per-second source precedence (which source's samples win where several cover one bout); bounded gap interpolation; and the sRPE floor (Q202) as the fallback when no usable device HR exists.

**It waits on Polar per-second ingest.** Polar rows are zone-seconds only today, so the layer has no per-second Polar input (Q10: AccessLink per-second ingest, pathway specified in #46, not built; Q198: the v4 `samples` feature is untested). Health Connect rows already keep every posted sample (`hr_samples`).

**Where the pieces already sit.** Source ranking (#365, Q201, Q203); the sRPE floor and its capture (Q202, Q209 closed, Q189); the whole-session overlap with Hevy (Q206). Zoning credits at most `hr_zones.MAX_SAMPLE_GAP_S` (60 s) per gap, the gap bound Q206 records; whether another exists was not searched for.

**To decide (Luke).** When to draft, and whether it is one brief or follows Q10's trigger. A related brief, instrument datasheets, is not drafted either (ROADMAP LATER).

**State:** OPEN. Owner: Luke. Not blocking; waits on Q10. Related: Q10, Q198, Q201, Q202, Q203, Q189, Q206.

---

## Q214. Persist `client.trigger` on `health_connect_sync_events`: the phone already stamps it, the server drops it

Raised 5 Oct 2026 (a duplicate session's finding, verified here against both repos). The companion build `e3e2333` stamps `client.trigger` (`'manual'` or `'background'`) on every POST (`health-connect-app` `src/syncRunner.js:93`; `backgroundSync.js:57`; `SyncScreen.js:177`). Its comment at `:92` calls persisting it "the owed health-app follow-up (OPEN_QUESTIONS)", and the companion's own stores hold it as its Q23 (migration = HOLD). **No store in this repo held it until now.**

**Verified on master `9fc2973`.** `ClientInfo` has `extra="allow"`, so the field is accepted (`routers/health_connect.py:303-312`). The row written per POST takes `gitSha`, `builtAt`, `appVersion`, `platform`, `periodDays` and `fetchMeta` only (`:1152-1159`), and `HealthConnectSyncEvent` has no column for it (`models.py:393-414`). So the trigger is dropped, and the event table cannot say which POSTs were scheduled.

**What it would settle, by data and not by timestamp.** The device read for #370 (the companion's G2), the overlap proof for #371 (the companion's own note says to distinguish the two syncs by timestamp "because Q23 is held"), and the 4-5 Oct question of whether a given POST was a background run (the note on Q159).

**Options (not decided).** (a) A nullable `trigger` column on `health_connect_sync_events`, clipped like its sibling fields; old builds send none, so NULL. A migration: HOLD, full human review. (b) Write it into `fetch_meta` under a reserved key. No migration, but `fetch_meta` is stored verbatim by contract (`SCHEMA.md` §035), so this is a data-meaning default. (c) Nothing; keep inferring from timestamps.

**To decide (Luke).** Which option. Code's lean, not a ruling: (a), the shape the phone's own comment assumes.

**State:** OPEN. Owner: Luke. Not blocking. Related: #370, #371, Q159, Q208, HCA Q23.

---

## Q216. Should HC zoning move to heart-rate reserve (Karvonen: resting HR to HRmax), so zones adapt forward with fitness through resting HR?

Raised 5 Oct 2026 (operator, with #383). The platform's zones are %HRmax: `hr_zones.BAND_PCT` 50/60/70/80/90 of the HRmax in force (#364; SCHEMA.md HR Zone Computation). Garmin already zones by %HRR on the watch (max 180, resting 66, LTHR 157, the LTHR estimated; the context note in #365), and none of that is an input to the app. The proposal: derive HC zones from reserve, so a falling resting HR through fitness moves the zones forward without anyone writing a new HRmax, while HRmax stays a quasi-fixed constant that is restated, not dated (#383).

**What a reserve model needs, checked on master `2236cd4`.**
- **A resting-HR input the app does not have.** `health_connect_syncs.resting_heart_rate` is the day's median of every HR sample, not a resting value (Q200), so it cannot be the input. Q200's own "derive a true resting value" from `hr_samples` is the candidate, and it is untested. SCHEMA.md forbids age-predicted values, so a resting HR would have to be measured.
- **A dated resting-HR store** the way HRmax has `user_hrmax`, or a rolling derivation; which, and what a row before the first value does, is open (an unseeded user reads `no_hrmax` today; the equivalent state would be a new reason in the closed set).
- **The band edges.** Karvonen's target is resting HR plus a percentage of (HRmax minus resting HR). Whether the platform keeps 50/60/70/80/90 of reserve or adopts the edges Garmin uses is open; Garmin's edges are not read anywhere in this repo.
- **Series effect.** Every HC row's zones would move, and with them the metabolic TRIMP series and the ACWR. The step at the switch is what #383 warns about; a full-history recompute is the only way to avoid one, and it is a series-wide change that needs a ruling.
- **Comparability.** Polar rows keep Polar's own zones (Q198), so a reserve model for HC rows changes the HC-against-Polar read recorded in the ROADMAP HC zones row, and Q198's re-zoning question moves with it.
- **Supersession.** SCHEMA.md's HR Zone Computation (`ZONE_BOUNDARIES_PCT_HRMAX`) and #364 R3 would be superseded by a new decision, not edited.

**To decide (Luke).** Whether to move at all; if so the resting-HR source and its provenance, whether it is dated like HRmax, the band edges, and the recompute. Not this session's build.

**State:** OPEN. Not blocking; nothing built. Related: #364, #383, Q198, Q199, Q200.

---

## CLOSED

_Resolved questions, moved here verbatim (backlog triage, #123). `DONE → #N` names the
deciding `DECISIONS_LOG` entry. Per #123 closed questions are not scanned for live work — they
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

**State:** `DONE → #234`. The collapse landed as **six** branches (the fifth-plus-`dataOrigin`), with
loudness built rather than assumed — required canonical fields + `extra="allow"`, `type: int`, a
shape-only reject diagnostic, and per-stream ingest counts. Backend-only golden fixture
(machine-verified against HCA `7a63b15`) plus the negative battery close Q5 without the on-device
capture its own text once demanded — the capture precondition was struck, and source proved to be the
contract. **Pointer-integrity note (cross-reference class):** this question's own text and `#174`
predicted `DONE → #174`; the work landed under `#234`, which **supersedes** `#174` (deletion alone
delivered no loudness; the collapse was six branches). Resolving to `#234`, not `#174`, and recording
the divergence here rather than leaving a reader to reconcile the two pointers. The client-side
conformance check (`#174`'s O3) is deferred behind `#236`'s source-neutral contract. Owner: Luke.

---

## Q6. Strength volume-load not yet ingested into daily training load

Decision 28 routes strength volume-load → the Mechanical + Neuromuscular windows as a
named, non-optional daily-TL input. The decision is settled, but it is unverified at the
machine: no Postgres query has confirmed Hevy strength volume actually populating the
per-window `load_metrics` rows. Verify a real query shows strength volume landing in the
load path before the four-window engine — or even Tier 0 with a strength term — can be
trusted. Was tracked as "B2" in an out-of-project session's scheme that never entered the
repo; recorded here under the canonical Q-series.

**State:** DONE → #242 (gate 2 landed + live-verified 2026-08-25; strength volume is non-zero
in the per-window load path — Q6's DONE bar). Gates 3–4 (the `load_metrics` + Banister rollup)
continue as ROADMAP forward engineering, no longer an open question. **Re-scoped 2026-08-25 into
four sequenced gates.** The original single check (a Railway query showing strength volume in
per-window load rows) was unrunnable because the whole chain below it was unbuilt: nothing
persisted Hevy workouts, no transform, no load store. The work decomposes into four gates, built
in order, each the substrate of the next:

- **Gate 1 — persistence — DONE 2026-08-25, live-verified (#239, #240).** `hevy_workouts` +
  `hevy_sets` store (PK-upsert, raw payload kept), backfill, dedup flag-and-adjudicate (D-G),
  usage-joined laterality-coverage audit (`audit_laterality_coverage`), laterality
  session-pairing mechanism (D-E). Landed as `#103`/`#104`/`#105`. **Live backfill assertions
  (prod, post-#104 fix):** 56 workouts / 1710 sets; span 2026-04-05 → 2026-08-24 (entire Hevy
  history fits inside 180 d, so backfill depth is moot — the store is COMPLETE, not merely
  180-day). Dedup flagged exactly the two known same-day pairs (16/17 Jun VO2+Upper, 01 Jul
  Upper ×2); the planned-routine-artifact copy of each (larger set count, zero RPE) was
  operator-`excluded_at` → effective store **54 workouts / 1609 sets**. RPE coverage is ~100%
  of RPE-CAPABLE sets from the mid-May 2026 epoch (April is a bounded pre-RPE era); the raw
  68.6% conflates that with the now-excluded artifacts and 34 structurally RPE-incapable
  non-rep sets. Two carried defects (transform session, not now): `_rpe_coverage`'s denominator
  is `type='normal' AND weight_kg NOT NULL` and must become `reps NOT NULL` + excluded-aware;
  and Hevy planned-vs-performed artifact duplicates (signature: 0-RPE post-epoch rep-based
  workout, usually a same-day full-RPE partner) — dedup half-catches them, a signature check is
  candidate hardening. Both in ROADMAP "Banister build".
- **Gate 2 — transform (`load_events`) — DONE 2026-08-25, live-verified (#241, #242).** Per-set
  Tier-0 Mechanical + Neuromuscular per D-C (RPE/RIR-dominant, intensity-modified) and D-D (non-rep
  work in via a named bridging constant), recomputable + `formula_version`-tagged (`tier0-v1`),
  reading Gate 1's `hevy_workouts.raw`. Review corrected two defects before land (epoch-gated RPE
  and laterality halving in the load path → per-set date-independent RPE, load-sums-as-logged,
  epoch diagnostic-only). **Prod closing query (54 non-excluded sessions):** Mechanical
  **3,056,351.056 `kg_reps`**, Neuromuscular **480.818 `nm_au`** — non-zero, one row per window per
  session. This is Q6's DONE bar met.
- **Gate 3 — rollup (`load_metrics` + Banister) — NEXT.** Daily per-window derived rollup, and the
  fitness-fatigue model (ROADMAP "Banister build"). Recomputable from `load_events` (D-B), so
  coefficient/routing corrections are recomputes, never migrations of computed history.
- **Gate 4 — the machine check** (original Q6 wording: a query showing strength volume in
  per-window rows, non-zero) is **satisfied at the `load_events` layer** by the gate-2 closing
  query above; its `load_metrics` form lands with gate 3.

**Consequence today:** strength volume now lands non-zero in the per-window `load_events` path
(gate 2), but the **deployed** user-facing load metric is still the interim aerobic-only ACWR of
`#8` (`mcp_server.get_training_load` unchanged) — the strength term reaches a consumed metric only
once gate 3 (`load_metrics` + Banister) wires it. Q6's own bar (strength demonstrably in the
per-window load path) is met; the Banister engine that reads it is forward work.
Resolved **DONE → #242** (gate 2 landed + live-verified; closing query shows rows landing).
Owner: Luke. Cross-refs `#28`, `#32`, `#10`, `#33`, `#239`/`#240` (gate 1), `#241`/`#242` (gate 2),
ROADMAP "Banister build".

**Region-tag note (2026-08-25):** all 57 custom templates remain region-unadjudicated. This
blocks a future region-DISTRIBUTED Mechanical channel (per-region load) but NOT the systemic
Tier-0 Mechanical of D-C, which is region-agnostic. No action this lane; recorded so Gate 2's
region variant does not read the empty tag coverage as "no regions loaded".

**Region-distribution quirks list (started 2026-08-26):** movements whose load will misassign under
single-region attribution, to handle when the region-distributed Mechanical channel is built:
- **Weighted Dead Bug is a COMPOSITE.** Its logged weight loads the shoulder girdle / serratus (the
  overhead hold), while its `bw_fraction` (#245) loads the trunk / hip flexors (the leg-lower). Attributing
  the whole movement to one region misassigns it — the two load components belong to different regions.

**Addendum (2026-08-11) — Hevy unit-trustworthiness.** Before Hevy kg feeds `load_metrics`, three
weight-semantics hazards, operator-confirmed:

1. **Arbitrary-unit rows, bounded:** the M&F 2:1-ratio cable machine's markings are neither kg nor lb —
   arbitrary units logged as kg, unrecoverable by ratio correction. Scope is historic M&F sessions on that
   machine only; operator has retired it (alternates exist per machine), so the forward stream is clean by
   practice, not by mechanism — the affected historic rows are unmarked in-data and need a
   venue/exercise/date filter at integration time.
2. **Laterality:** unilateral sets log per-limb load under the same exercise name as bilateral work; the
   in-data signature is duplicated exercise blocks within a session; `hevy_exercise_templates.laterality`
   is the schema hook.
3. **Machine identity:** same exercise name spans machines with different leverage across venues (observed:
   leg extension 117 kg vs 50 kg equivalent effort). No machine/venue key exists in Hevy data, so the
   profile's "compare within-machine only" rule is unenforceable at the data layer. Low severity —
   distorts cross-machine trends, not safety — but any `load_metrics` consumer must treat cross-venue steps
   in a single exercise's history as suspect. Tag hook analogous to laterality if it ever matters enough.

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

## Q9. Consolidate legacy free-text `user_knowledge` into `user_knowledge_entries`?

Legacy `user_knowledge` (free-text category/content) coexists with structured
`user_knowledge_entries` per #44. Fold the legacy KB in as a `type="note"` entry and
retire `routers/knowledge.py`'s legacy write path + `context_builder`'s parallel
`knowledge_entries` param — making `context_builder` a true single-source formatter over
`current_state` — or keep them permanently distinct (free-text notes vs typed declared
state)? Deferred by #44; not urgent.

**Annotation (2026-09-27, injury clearance sweep; #340, #341).**
The fork now has a live cost. Verified on master `360b385`: `user_knowledge` has no active flag and no
resolution; chat loads it unfiltered (`chat.py`) and `_section_knowledge` renders every row every turn; and the
legacy write path APPENDS to one row per category, so a row mixes facts about several injuries (prod row 2,
Injury History, is 66 lines). A resolved injury therefore keeps re-imposing itself from here. Mitigations landed
without deciding this Q: the coach no longer writes "Injury History"/"Constraints" (prompt-only;
`VALID_CATEGORIES` untouched), and the sweep finds the copies per line for the operator to edit. Retirement, or a
render gate on this store, is still this Q.
- **Forward-compat (G2 ruling):** the sweep's `reaches_context` label is currently a per-store constant (`"yes"`
  for `user_knowledge`, `injury_sweep.sweep_user_knowledge`). When this Q render-gates the free-text store, that
  label must be DERIVED from the renderer's actual inclusion rule, not the constant, so it flips with the gate.
- **Step-1 ruling (operator, 2026-09-27): GO.** The `user_knowledge` render path and write path are retired
  TOGETHER, in a separate brief (not yet cut). #341 (the prompt no longer offers "Injury History"/"Constraints")
  stands as landed and is now a subset of that retirement. The typed `constraint`/`finding` brief is a separate,
  parallel lane.

**State:** DONE → #343 (ruled 2026-09-28 on the fork only: the legacy KB folds into typed `finding` /
`constraint` rows — there is NO `note` type). The store's retirement / render gate is NOT closed by this: the
Forward-compat note and the Step-1 ruling above move verbatim to **Q181**, which the retirement brief closes.

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

**State:** `DONE → #215` — **absent-confirmed** against Railway Postgres, 2026-08-16, by a stronger route
than the one this question asked for: instead of capturing a single sync payload,
`health_connect_record_sources` answers it for all time. `hrv_rmssd` non-null count is **0** across the whole
table, and the record-type inventory holds only exercise, heart_rate (47,250 rows), sleep and steps — **no
HRV record type has ever arrived**. The 47,250 heart-rate rows are what make this a positive finding rather
than an inconclusive one: the pipeline demonstrably reads and stores Samsung-written Health Connect records,
so the empty HRV node is not a dead ingest path. The absence is at source. **Q5's unmapped-field hypothesis
is therefore eliminated for HRV** — it remains live for other fields. Residual: the scraper is the confirmed
sole HRV path, so the single point of failure stands — transferred, not closed, to `health-connect-app`
issue #9 (scraper canary). Zero prod writes. Cross-refs Q5, issue #9.

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

## Q15. `3497ab483935` prod-drift reconciliation

Autogenerate surfaced (and Code stripped) three divergences between local and prod at
revision `3497ab483935`: an `exercise_sessions` drop, `samsung_hrv_readings.context`, and
`api_key_encrypted` `VARCHAR`→`TEXT`. Confirm each is an intended local/prod difference or
a real un-migrated delta. Resolve against Railway Postgres, not local.

**State:** `DONE → #215` — resolved against Railway Postgres, 2026-08-16. `alembic_version` reads
`e2d5c7a1b9f3`, identical to local head, so prod is not behind. All three divergences are present in prod
with their intended types: `exercise_sessions` exists, `samsung_hrv_readings.context` is `varchar`, and
`user_integrations.api_key_encrypted` is `text`. The `3497ab483935` drift was therefore **local behind
prod**, since reconciled by `0f1ac6f33c40` / `e1f2a3b4c5d6` / `a7d4f8e21c93` — not a real un-migrated delta.
Zero prod writes.

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

## Q18. `samsung_hrv_readings` historical out-of-range sweep

DECISIONS_LOG #70 added an ingest bounds guard that nulls-and-logs out-of-range biometrics going
forward (trigger: `2026-06-28 Eff=119%`), but **existing rows are unswept** — the sweep could not run
this session because the local `DATABASE_URL` is dev SQLite with zero production rows. Run the
full-schema `NOT BETWEEN` sweep (mirrors `_BOUNDS` in `routers/samsung_hrv.py`) against **Railway
Postgres**; for any historical violator, null/clamp the offending field (the guard only protects new
writes). If efficiency was unbounded, assume other fields were too — the sweep covers the whole
numeric schema, not just efficiency.

**State:** `DONE → #215` — swept against Railway Postgres, 2026-08-16. The full 15-field `_BOUNDS`
`NOT BETWEEN` sweep ran over all 56 rows of `samsung_hrv_readings` and returned **zero violators**; the
`2026-06-28` trigger row's `sleep_efficiency_pct` is already NULL. No historical violator existed, so no
backfill was required and no rows were written. Closes the `BRANCHES.md` `fix/hrv-sleep-integrity` Task 3
loop. Independent of Q17.

---

## Q20. Clinical findings vs restrictions — `user_knowledge_entries.value` conflates them

Restrictions are structured (`restrictions[]`, enforced by `selection.py`); **findings are not**.
Positive right slump, S1-pattern referral, frontal-plane deficit have no first-class home in the injury
`value` JSON — they ride as `signal_type` + free-text `detail`. The constraint-consumption brief added a
`trajectory` key to `value` but deliberately did **not** model findings. Note the split surfaces
elsewhere too: FEEDBACK §5 documents these findings clinically, but the structured ledger the engine and
snapshot read does not carry them. Q7 territory.

**State:** DONE → #343 (ruled 2026-09-28): findings are separate `type="finding"` rows with an optional
`parent_key` (any entry), not nested in the injury value, carrying Q20's three-valued `marker_status`
(`provocative | clear | untested`). (Was OPEN, decoupled from Q7 on 2026-08-03 when Q7's authoring was
discharged at `#72`.)

The question is unchanged in substance: give clinical findings — positive slump, S1-pattern referral,
frontal-plane deficit, "pressing untested" — a first-class structured home in the injury `value` JSON,
specifically the three-valued **provocative / clear / untested** status that FEEDBACK §5 carries as a
table column and the ledger does not. No blocker. Owner: Luke.

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

## Q23. Do `_RADICULAR_BLOCKS` / `_RA_FLARE_BLOCKS` need revision now that region attribution is accurate?

Correctly tagging Pallof as `anti_rotation`-only (and Shoulder Rotation as NOT `rotation`) is what makes
the radicular rotation-block behave correctly for this user. Other blocks in `selection.py` may have been
tuned against wrong keyword inputs and never noticed — the block sets and the (now-fixed) loaded-region
inference were never independently validated.

**State:** `DONE → #216` — audit run 2026-08-16: taxonomy × the confirmed tags × sole-consumer
verification, with the live injury ledger read read-only from Railway the same session. Three findings,
all landed on `fix/contra-block-sets`:

1. **Over-block direction is clean** against the confirmed tags — no region a confirmed tag reaches is
   wrongly blocked. The question's stated worry does not reproduce.
2. **Membership was swept for the A–E vocabulary and never for G.** `_RADICULAR_BLOCKS` gains
   `hip_flexion_pc_length` (a PC-length screen is functionally an SLR — a neural provocation test, so
   probing it under an active radicular sign is the literal case the "don't discover your way into a
   flagged nerve" rule forbids) and `loaded_carry_capacity_bw`; `_RA_FLARE_BLOCKS` gains `grip_strength`
   (its own rationale reads "grip compromised", yet it left the grip region itself probeable mid-flare)
   and `loaded_carry_capacity_bw`. Both sets blocked `carry` while leaving its G-axis twin open.
3. **The radicular arm was unscoped by body part**, so a peripheral neural entry (cubital tunnel, say)
   would trigger a lumbar-shaped stand-down. Now gated on `_SPINAL_PARTS`, with an empty `body_part`
   degrading to the broader caution rather than to permission.

**Neither named set has ever fired in prod** — all five live ledger entries are typed `mechanical` — so
this change is protective, not corrective. The live defects the audit did surface are not in these sets at
all; they are in how `restrictions[]` is (not) consumed, spawned as **Q102**.

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

**State:** DONE → #186/#34. Free closure verified 2026-08-11: `parked` is absent from both CLAUDE.md
files — health-app pruned at #186, the HCA mirror pruned at HCA #34 ("Shared loop-rules block pruned to
invariants; health-app return trip"). The shared block moved in lockstep, so the struck vocabulary is
gone from the generator instruction on both sides and nothing has diverged.

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

**State:** DONE → #195. Ruled 2026-08-10: evidence-in-field + list promotion.

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

**State:** DONE → #196. Ruled 2026-08-10: enforce, cite `alt` first; cold-fallback ruling included.

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

**State:** DONE → #197. Ruled 2026-08-10: two interval bands, erythroid.

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

**State:** DONE → #198. Ruled 2026-08-10: ratified as proposed.

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

**State:** DONE → #199. Ruled 2026-08-10: uniform pair schema, all markers.

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

## Q45. Which day a recorded nap belongs to — settled by operator determination, not by the instrument

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

**Former resolution, superseded 2026-08-17:** the engine excluded nap-flagged nights entirely
(`NAP_EXCLUDE_MIN = 0`), recording them in `cbti_prescriptions.excluded_nights` with reason `nap`,
rather than attributing them to a date. That was the conservative reading of an ambiguous instrument,
and it was correct while the referent was genuinely undetermined.

**Resolution, adopted 2026-08-17 — OPERATOR DETERMINATION.** A nap attributes to the night it
**precedes**: the nap recorded on day D belongs to the night terminating on the morning of D+1.
`cbti.replay.load_nights` performs that read (Night(W) reads row W-1), and `NAP_EXCLUDE_MIN` rises
0 -> 30, so a sub-30-minute nap no longer excludes.

**The closing bar changed, and that is the substance of this close.** The prior next-action —
establish the referent from VA CBT-I protocol documentation or the administering clinician — was
never the right gate. Which night a nap belongs to is a **modelling convention**, not a fact about the
world awaiting discovery: the operator is entitled to define it, and defining it is what makes the
stored data interpretable at all. Holding the close hostage to a citation that may not exist would
have stranded a sound convention indefinitely, and left the store asserting a clinical provenance it
never had. The convention is also the natural reading of the app's own PM instrument, which records
"naps today" against the nap's own calendar day (`_today_aest`) — so for every night live titration
actually runs on, the referent is fixed by the capture surface rather than inferred.

**The scoped null STANDS and is not re-run.** The workbook search recorded above is untouched by this
close; it remains the record that the VA instrument's wording does not settle the question. This close
says that question no longer gates the engine — not that it was answered.

**Corollary — a contract finally honoured.** `models.DailyRecord.naps_min` has carried the column
comment *"Logged PM on date D; belongs to night terminating D+1. Engine reads from (date-1)"* since the
column was created, while the engine read the nap off the night's own row. The two disagreed, and the
model's own comment flagged the disagreement silent-when-wrong. This close makes the code match the
contract the schema always declared.

**Scope of the determination.** It governs app-captured naps, which is every night live titration runs
on. It does NOT retroactively establish the VA workbook's convention; `import_cbti_block.py` records
that limit, and it is moot there because the imported block is historical and mints no live verdict.

**State:** DONE → #219. Owner: Luke. **Related:** **Q78** (frequent-napper exclude-vs-attribute at the
4-night cadence) stays **OPEN** — it was never blocked on the referent, but on the data consequence of
losing nights at a one-night margin, which the 30-minute floor eases without resolving.

---

_Gate summary (2026-06-22, on-device, SM-S921B): GATE 1 PASS → DECISIONS_LOG #20.
GATE 2 PASS (deep slivers survive the HC write at 30s resolution; deep is heavily
fragmented — ~26 of 30 deep segments are <3 min slivers). GATE 3 INCONCLUSIVE → Q3 (superseded
`#173` / `Q81`; principle `#71`)._

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

## Q54. The interpretation view (increment 1/5) renders against a superseded contract — its fixture lacks the `ungrouped[]` the #86 producer emits

`frontend/src/fixtures/interpretationExample.json` has top-level keys `['groups', 'meta']`, but master's
#86 producer (`backend/interpretation/producer.py`, `build_foundation`) emits `{meta, groups[],
ungrouped[]}`. The view (increment 1/5, DECISIONS_LOG #135) is fixture-driven and ships **INERT** — it
renders the committed fixture, not the live producer — so nothing ships broken. But the increment that
wires the view to the live producer MUST (a) regenerate `interpretationExample.json` from current
`build_foundation` output and (b) add an `ungrouped` render section; wiring it against the current fixture
would silently DROP every ungrouped marker.

**State:** DONE → #158–#160. Free closure verified 2026-08-11: `frontend/src/fixtures/interpretationExample.json`
now carries top-level `ungrouped[]`, and `InterpretationView.jsx` renders it via `UngroupedLine.jsx`. The
view-pointer swap (view reads the live `GET /interpretation`, #158) and the ungrouped render section both
landed; the drop-every-ungrouped-marker hazard is closed.

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

---

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

**State:** DONE → #200. Fork 1 resolved by scope ruling 2026-08-10 (CBT-I is not a consumer-facing
product; verdict may surface). Fork 2 resolved with it: the interim surface is READ-ONLY — prescription
state, cycle inputs (SE/TST vs gates, nights clean), and the engine's decision with its reason, labelled
as this platform's titration logic. In-app diary capture is deliberately NOT in scope: a new input path
that re-opens Q45, which is still unresolved — capture is its own increment, gated on Q45. I1 sensor
firewall (diary columns only, never passive Samsung sleep) binds at the projection, enforced as the labs
read-back enforces #47.

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

**State:** DONE → #201. Ruled 2026-08-10 (a): both omitted, rationales corrected — seam for
`computed_flag`, QA-not-clinical for `confidence`.

---

## Q62. How is `#47` enforced structurally for a generated field?

**State:** DONE → #202. Ruled 2026-08-10: rephrase-form only, structurally gated, fail-closed to
template; dial fragment-wise/whole-block; (c) foreclosed.

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

**State:** DONE → #203. Ruled 2026-08-10 (c): `mechanism` onto ungrouped, `stable_rationale`
grouped-only.

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

## Q67. `hpg_substrate_co_movement` is phase-conditional, and no `#154` condition shape expresses it

**State:** DONE → #204. Ruled 2026-08-10 (a): shapes compose; `precondition` is an optional modifier
on any kind.

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

---

## Q70. A censored delta reports `delta_within_min_meaningful` without ever consulting the threshold, so a large suppression reads as quiet

**State:** DONE → #205. Ruled 2026-08-10 (a+d): honest token + honest rendering; (c) declined pending
a live case.

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

---

## Q71. `min_meaningful_delta` has no time dimension, so an 8% move over 40 days and over 154 days are the same event to gate 1

**State:** DONE → #197 (Q38's entry). Same hole as Q38, minted independently; answered by the
interval-band ruling, not separately.

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

---

## Q72. Sprint max velocity has no home on the v0 axis list, so the one Catapult measure most worth capturing cannot be recorded

**State:** DONE → #206. Ruled 2026-08-11 (Doc-8 shape): `max_velocity_ms` homed in a new
passively-observed §E region; `per_side`/`needs_norm`/`queue_eligible` all False; the engine reads,
never initiates.

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

---

## Q75. The catalogue is now populated on connect, but nothing keeps it fresh — the sync has a trigger, not a schedule

**State:** DONE → #211 (RESOLVED 2026-08-12). Option (c) — sync-on-workout-fetch, staleness-gated on the per-user marker `user_integrations.templates_synced_at` (24h). Resolution note at the end of this item. **Related:** `#163` (the wiring decision), `#77`/`FEEDBACK` §8 (landed ≠ live), `#79`/`#81` (logged titles drift from catalogue titles), `#65` (the create-loop's own `sync_one_user` refresh), and `#211` (the decision).

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

**RESOLVED 2026-08-12 → #211 — option (c).** Catalogue freshness piggybacks a per-user, staleness-gated `sync_one_user` on the workout-fetch path. Options (a) and (b) rejected on their own Q75 trade-offs: (a) a new scheduler is a new failure surface for drift no read has yet needed; (b) a network call on a currently-pure read path lets a Hevy outage degrade reads that today serve from the local store. The 2026-08-05 incident is the discriminating evidence — workouts synced while templates did not (store `max(synced_at)` 2026-08-04; two of the three Aug-5 customs absent), the exact traffic (c) rides. Implemented NOT as the enumerated "resolver checks `synced_at`" (that column is per-row and re-stamped by any user's sync, so an aggregate reads fresh off another user's run) but as a per-user marker `user_integrations.templates_synced_at`, correct under multi-user (4 users live in prod).

Note on the resolve-before condition above: the write path (`<hevy_create_exercise>`) IS now user-facing via chat (`routers/chat.py:748`), and its idempotency pre-check reads this store — so the condition this item named is met. (c) mostly defuses it (an active user's workout fetch refreshes the catalogue in the same session) but does NOT gate the create path; a create with no recent fetch can still race a stale catalogue. That residual — option (a) or a create-time freshness gate — is a separate flag, out of #211's scope.

---

## Q77. The live create→list-back round-trip is unproven — the first real custom-exercise creation is the test

**State:** DONE — RESOLVED 2026-08-03. The round-trip completed on a fresh name. `Half-Kneeling Cable Rotation` was created live: with #168 catalogue visibility the model confirmed it absent, `create_and_resolve`'s idempotency pre-check agreed, the POST succeeded, and list-back resolved it within `_CREATE_RESOLVE_ATTEMPTS` → `✓ Custom exercise 'Half-Kneeling Cable Rotation' created in Hevy`. The two claims left unproven after the Copenhagen incident — that the created template surfaces in a follow-up GET, and does so inside the retry bound — are now both settled affirmatively. **How you know:** the live ✓, non-destructive, first end-to-end completion of create→sync→list-back. **Related:** `#164` (the block), `#166` (the parse fix the watch-point exposed), `#65` (the create loop), `FEEDBACK` §8 (landed ≠ live).

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

---

## Q91. Should brief-authoring carry a verify-checkpoint for unseeable-surface claims?

The `status-parser-gate` brief asserted an existing committed generator "returned 0 blocked / 0 owed /
0 unstarted / 0 off-vocab, exit-0" — the diagnosis that motivated the whole build. Step 0 falsified it:
no committed generator produces those buckets; the 0/0/0/0 was a chat-side ad-hoc parse, promoted from
hypothesis to diagnosis in the brief. The author's own review had flagged that line as "chat inferring
where Code adjudicates" and tagged it a hypothesis — then the brief promoted it anyway.

**State:** DONE — resolved 2026-08-11, no rule minted. Brief-authoring gets no verify-checkpoint
mechanism. The executing side is the only side that can verify at execution time, and the 2026-08-10
Brief A stop — Code re-verified at session open, found master seven decisions past the brief's anchor,
found #187 already landed, and halted without re-litigating — is the existence proof the checkpoint
already operates where it belongs. Authoring-side mitigation is convention, adopted without a rule:
briefs date their anchors and state that claims yield to the tree (practised in the go-live brief). A
second enforcement point would be redundant belt-and-braces of the class #186's severity gate exists to
refuse. Cross-refs `#190`, `#186`.

---

## Q101. The offer surfaces the last elapsed cycle, which a later insufficiency-hold can bury over a fully-logged actionable step

`evaluate_live_cycle` returns `complete[-1]` — the last cycle whose 4-day span has elapsed, not the last
*sufficiently-logged* one. On block 2 (`cbti_blocks.id`=2), a fully-logged `compress 390→375`
(2026-08-04…08-07, n=4) was superseded by an insufficiency-`hold` (08-08…08-11, n=2 < `MIN_VALID_NIGHTS`);
accepting the hold buried the compress and reset the cycle clock. Confirmed in the ledger: the accept minted
`cbti_prescriptions.id`=12 as `decision='hold'`, `basis_nights_n=2`, window unchanged at 390/22:30 (#213's
first live run).

Two forks:

- **(a) selection.** When the last-elapsed cycle is an insufficiency-hold (a non-decision — the engine could
  not adjudicate on merits, not a decision-on-merits), should the offer defer to the most recent cycle that
  clears the sufficiency gate rather than adjudicate on nights that don't meet it?
- **(b) clock.** Should accepting an insufficiency-hold reset the cycle clock at all, or is "not enough data
  to decide" a non-event that shouldn't cost ~4 days?

This is how sparse logging compounds: each accepted insufficiency-hold pushes the next look further out while
the diary stays thin. Mechanical / confirmed against live block-2 data. Neighbours `Q45` (sparse-diary
attribution).

**Resolution.** Both forks answered by ONE rule, taken at fork (b) rather than (a): **an insufficiency-hold is
not an acceptable event.** It mints nothing, resets nothing, and renders information-only. "Not enough data to
decide" is a finding, not a decision, so there is no event to record and nothing that should cost ~4 days.

- **Fork (b) — the clock: no.** Accepting a non-decision closes the current cycle and restarts the evaluation
  clock, which is what buried the compress. Removing the accept removes the reset; the cycle simply continues
  under the prescription already in force, and the next elapsed cycle is adjudicated on whatever nights exist
  by then.
- **Fork (a) — selection: unchanged, `complete[-1]` stands.** Deferring to an older sufficient cycle was
  rejected: it violates the staleness principle the selection encodes. An unaccepted elapsed decision EXPIRES;
  it does not sit waiting to be resurrected once a later cycle fails to adjudicate. Answering (b) makes (a)
  moot in practice — with no accept on the non-decision, nothing buries anything.
- **Carve-out — a converged HOLD remains acceptable.** The rule discriminates on decision CLASS, not on the
  `hold` verb. An adherence HOLD and a converged HOLD are decisions-on-merits; the converged one in particular
  is the block's memory of the level it found, and the engine emits no other block-ending signal (#107), so
  refusing it would make that level unrecordable. Only the sufficiency gate's HOLD is a non-decision.
- **Enforced server-side (409), not merely hidden client-side.** A UI that omits a control is not an
  enforcement. The engine gained a structural discriminator (`CycleDecision.sufficient`) rather than leaving
  the `insufficient_nights:` reason PREFIX as the carrier, so nothing downstream adjudicates by string match.
- **`cbti_prescriptions.id`=12 is let stand.** The ledger is append-only and the row is a faithful record of
  what was accepted. Reversing it is an operator matter (a corrective prescription), not a migration.

The harm event was itself the #214 defect firing — a single tap on a live `Accept and prescribe` — so the
same landing installs #214's two-step confirm restating the actual write. See #218; cross-refs #213 (the
first live run), #214 (the confirm defect).

**State:** DONE → #218.

---

## Q107. Should a `review` flag surface a resolve prompt, and on which surface?

`injury_trajectory.evaluate()` raises a symptom-gated `review` flag when soreness reaches an
injury's declared exit condition — "looks resolved, review the restriction". As of #222/#223
there is somewhere to put the answer (`POST /knowledge/injuries/{id}/resolve`), but nothing
connects the two: the flag surfaces in `get_readiness_snapshot` and the operator must navigate
to the resolve call themselves.

The open part is not WHETHER to connect them but WHERE, and the surfaces are not equivalent:

- **AM check-in.** Closest to the soreness capture that raised the flag, and the operator is
  already answering questions. But the check-in is a two-minute ritual and #72 was explicit that
  it monitors rather than renegotiates — putting a state-changing control there is the exact
  shape of drift that decision guards against.
- **Interpretation / decision-support surface.** Matches the flag's actual register (a prompt to
  revisit a plan, not a daily data point) and keeps the check-in read-only. Costs a navigation
  step at the moment the user is least motivated to take one.
- **A standing "injuries" view over `GET /knowledge/injuries`.** The most honest home — the list
  exists now, and a review flag becomes a badge on a row rather than an interruption. Slowest to
  reach, so a stale injury could sit flagged for weeks.

Whichever wins, the prompt must stay a PROMPT: #223 is unconditional, so no surface may resolve
without an explicit operator action carrying a `basis`.

**State:** DONE → #232. The standing view over `GET /knowledge/injuries` wins: a review flag
becomes a badge on a row, and decision-support carries a count pointer into that view rather than
a resolve control. The AM check-in is refused on #72's scope. Answered as ONE decision with Q110 —
same question, two stores — so the two prompts share a convention instead of drifting into two.
#232 decides WHERE, not what gets built; it authorises no UI work by itself. **Related:** `#223`
(nothing auto-resolves — unconditional, and #232 inherits it), `#222` (the write), `#72` (the
check-in's scope), `Q110` (answered with this), `Q108`.

---

## Q108. Should the `clinician` authority tier carry identity? (Both stores now exist)

`resolved_by` accepts `"user"` or `"clinician"`. It records the CLASS of assertor, not the
assertor: a clinician-resolved injury and a self-resolved one are distinguishable, but which
clinician, when consulted, and on what basis beyond the free-text `basis` field are not.

**Why it might matter:** the two classes carry different evidential weight, and a resolution is
the moment an engine constraint lifts. If a resolution is later questioned — a re-injury in the
same region — "clinician" with no attribution is close to unfalsifiable. The `basis` field
absorbs this in practice today, since it is free text and mandatory, but it is prose and nothing
reads it.

**Why it might not:** this is a single-operator platform; identity would be a name typed into a
box, self-asserted, with no verification path. A field that LOOKS like provenance but is
unverified is worse than an honest free-text `basis` — the #133 reasoning about inputs the app
cannot verify applies to the assertor as much as to the assertion.

**The second store now exists, and half of this question is answered.** #227 added `asserted_by`
to profile `hard_stops` and `live_signals`, and it did NOT invent a second vocabulary: the two
authority fields are aligned, differing by exactly one member — `engine`, which can assert but
must never resolve (#223) — and that alignment is pinned by a test rather than left to convention.
So the "should the answer bind both stores" half is settled: yes, and the mechanism that makes it
bind is a gate, not a note.

**What remains open is only the identity question itself**, and neither store forces it yet. Both
briefs reached the same conclusion independently — a second user with an opinion is what forces
it, and there isn't one. When it is answered it changes `resolved_by` (#222) and `asserted_by`
(#227) in the same change, or it is drift.

**State:** DONE → #231. No. Both fields record a CLASS, not an identity; `basis` — mandatory free
text — absorbs attribution and stays prose. #133's reasoning decides it: a self-asserted,
unverified name field looks like provenance and isn't, which is worse than honest prose, because a
later reader trusts the structured field and reads past the free text. The binding half was already
closed by #227 (aligned vocabularies, pinned by a test), so #231 closes only the identity question.
**Related:** `#222`/`#223` (where `resolved_by` is written), `#227` (where `asserted_by` is written
and the vocabularies were aligned), `#133` (unverifiable-input reasoning), `Q110`/`Q107` (the other
answer-once-for-both-stores pair, closed by `#232`).

---

## Q110. What surfaces a due review to the user, and does it share a home with Q107's resolve prompt?

`review_on` (#227) records a date to ask again, and #228 guarantees that date does nothing on its
own. Nothing reads it. There is no surface that says "these three assertions are due for review",
so a `review_on` written today is a note to a person who will never be shown it.

The candidate surfaces are the same three Q107 weighs for injury resolve prompts, and that is the
point of raising this here rather than separately:

- **AM check-in** — highest attention, but #72 scoped it to monitoring rather than renegotiation,
  and a due-review prompt is a renegotiation invitation.
- **Interpretation / decision-support surface** — matches the register (revisit a standing
  decision), keeps the check-in read-only, costs a navigation step.
- **A standing profile view** — the most honest home, since `GET /engine/profile` already returns
  every entry with its block; a due review becomes a badge on a row rather than an interruption.

**Answer this with Q107, not after it.** Q107 asks where an injury `review` flag should surface a
resolve prompt; this asks where a profile `review_on` should surface a review prompt. Same
question, two stores, and answering them independently produces two review surfaces with
different conventions — the same drift Q108 exists to prevent for vocabulary. If one surface
serves both, that is a design decision worth taking deliberately rather than discovering.

Constraint on any answer: the prompt stays a PROMPT. #228 is unconditional, so no surface may
retire an entry without an explicit operator write carrying a basis.

**State:** DONE → #232. A due `review_on` surfaces as a badge on its row in `GET /engine/profile`
— the standing view for this store — with decision-support carrying a count pointer into it and no
retire control. Answered in the same decision as Q107, which was the point of raising it here: one
convention applied to two stores. #228 is inherited unchanged — the prompt stays a PROMPT, and
nothing retires without an explicit operator write carrying a `basis`. **Related:** `#227`/`#228`
(the field and its guard), `Q107` (the same question for injury resolve prompts, closed by the same
entry), `#72` (the check-in's scope), `Q108` (the vocabulary precedent for answering once, closed
by `#231`).

---

## Q112. Does the engine need a phase concept, or is a deliberate settle the operator's to hold outside the system?

The profile carries `horizon=life` and `ceiling=breadth` — a standing statement of intent, and a
true one. The engine reads it and recommends a probe at 0.25 budget. Meanwhile the operator is
holding a deliberate settle across a linked left-leg cluster with running restricted: a temporary
posture that contradicts nothing about the standing intent and everything about what this week
should look like.

**The back-off is entirely outside the system.** Nothing in the store separates what the operator
is building toward from what the operator is doing right now, so the engine cannot be wrong about
the phase — it has no phase to be wrong about. The gap is absorbed by ignoring the
recommendation, which is the failure mode where the engine quietly stops being consulted at all.

`schedule_item` id 9 already carries a `phases` block that nothing reads. That is either the start
of the answer or evidence the concept was reached for once and left unfinished.

**The cited evidence has been struck (2026-09-08, Q116 backfill DONE), and this question does NOT resolve with it (#233).**
`phases` is not a member of the validated `schedule_item` shape, so id 9's block was struck when the
backfill runs — its content is June rehab ("hamstring grade 1 strain"), long overtaken, and nothing
reads it. What that removes is a dead field, not the question: whether the engine needs a phase
concept is unchanged by deleting one unread instance of a half-reached-for one. Recorded here so the
question no longer points at data that exists. The phase-concept design question stands; the backfill ran under Q116 (DONE 2026-09-08).

**Partly blocked by `upsert_profile`'s null-guard.** A phase that cannot be cleanly unset is worse
than no phase: a settle outliving its reason becomes a standing restriction nobody chose, which is
the failure #228 names for `review_on` in the store next door. Answering this means either changing
the null-guard or accepting that a phase can be overwritten and never cleared.

**State:** DONE → #270. The engine needs a phase concept, and it is a STORE, not a field: the
`training_phases` ledger (append-only, exactly-one-open, structurally `cbti_blocks`) separates DOING
NOW from the profile's standing BUILDING TOWARD. It carries `probe_posture` (`suppressed | held`), an
optional `capacities` allow-list, a phase-scoped A/B `microcycle`, an `entered_on` anchor and a
`review_on` prompt (#228), and modulates `select_next` (suppressed → probe budget 0/fortify;
capacities REMOVE-only-filter the queue; the Fortify target is never dropped, disagreement surfaced).
The `upsert_profile` null-guard concern dissolves — a phase is INSERTed, never upserted; there is
nothing to fail to unset, you close a row and open (or don't) the next; `upsert_profile` is
untouched. Scope boundary: movement-quality capacities only — aerobic posture stays in `intent`
prose, enforced by nothing. The ledger is history + current, never a plan (the offseason sequence is
ROADMAP, operator-held). Owner: Luke.

---

## Q113. Which `source` value names an operator write made directly against the API?

Rows 75–78 were written by the operator, from PowerShell, against `POST /knowledge/entry`. They
carry `source: "chat"`, which is false — no chat turn produced them. The value was never chosen;
it is the default, and the default was the only member the vocabulary had that could absorb them.

Two candidates, and they are not the same kind of answer:

- **`api`** — names the channel the write arrived on, which is what `onboarding | chat | system`
  already enumerates. Consistent with the existing axis; says nothing about who was behind it.
- **`operator`** — names the writer, which is an authority claim — the axis #227 introduced
  separately as `asserted_by` (`user | engine | clinician`). Says who; says nothing about how the
  write arrived.

**Picking one silently decides which axis `source` is.** Today it is a channel field whose members
happen to imply an author, and that ambiguity is why a PowerShell write had nowhere honest to land.
Adding `operator` resolves these four rows and makes `source` a mixed axis; adding `api` keeps the
axis clean and leaves authority to `asserted_by`, at the cost of `source` never answering "who".

Cross-ref Q108, which binds `asserted_by` across two stores: whichever way this is answered sets the
same kind of precedent for the next store that adopts it, so answer it with the axis question
explicit rather than by picking whichever word reads well against row 75.

**State:** DONE → #230. `api`, not `operator` — `source` is a CHANNEL axis and stays one, with
authority left to `asserted_by` (#227) and `resolved_by` (#222). The set is now declared and
validated at write, and the `"chat"` default is REMOVED, which is the load-bearing half: the four
rows were not a wrong choice but no choice, so a member without the removal would leave a caller
free to mislabel by silence. Stated cost: `source` will never answer "who". **Rows 75–78 are not
corrected by that landing** — relabelling them is a prod write against live data and is the
operator's, per `§8`. **Related:** `§31` (the audit that missed this), `#227` (the `asserted_by`
authority axis), `Q108` (vocabulary bound across stores, closed by `#231`), `#222` (`resolved_by`,
the other authority field).

---

## Q116. The `schedule_item` validator is live and the 18 active rows were never backfilled

`#233` landed the validated shape at write. **The live rows were not corrected**, because the
session that landed it had no route to the production database: no Railway CLI, and every
credential path closed by `#111` (no `railway variables` in any form, no `env`, no reading `.env`).
The split was ruled deliberately rather than discovered — implementation and backfill divided along
a real capability boundary — and this question is the half that did not run.

**Nothing is broken by the gap.** Validation is at write, so the legacy rows read back unchanged
and are refused nothing. What is true is that master now carries a validator with 18 non-conforming
rows behind it, and without this entry that fact lives only in two chat sessions.

### The stop-condition was never executed

The row table below is a **2026-08-23 chat read carried forward unverified**. Before any backfill:
confirm the live row set still matches it, and **STOP and report the delta** if it does not. Nothing
in this session confirmed it against the actual table.

### Retire — 3 rows (`active=false`, reason in `notes`)

| id | key | why |
|---|---|---|
| 2 | `rugby_u8s_coaching_2026` | U8s coaching finished; no finals, no scores recorded |
| 7 | `rugby_u8s_2026` | duplicate of 2, same retirement |
| 79 | `physio_202608` | written 2026-08-21 as `active: true` / "Ongoing"; had already finished |

### Correct — 5 rows (user 1)

ids 1 and 6 were duplicates on `[tuesday, thursday]`; they **split by day** rather than merging,
because the two sessions carry different content.

| id | days | activity | load | `season_end` |
|---|---|---|---|---|
| 1 | `[tuesday]` | Rugby Training — Seniors (conditioning) | `moderate` | 2026-09-05 |
| 6 | `[thursday]` | Rugby Training — Seniors (set piece / team run) | `moderate` | 2026-09-05 |
| 8 | `[saturday]` | Rugby — 3rds (primary) + 2nds (fringe) | `heavy` | 2026-09-05 |
| 5 | `[mon…fri]` | Work — Instrument Fitter | `light` | null |
| 9 | `[tuesday]` | Optional accessory / rehab / sprint | `light` | null |

Also on these rows: ids 1, 2 hold constraint **prose** in `same_day_training` — move the text to
`same_day_note`, set the bool `true`. id 1 retains `time_range` `"6:00pm - 7:30/8:00pm"`; copy to
id 6 (same session block). id 9 — **strip the `phases` block** (June rehab content, long overtaken,
read by nothing; `phases` is not a member of the validated shape). Q112 already records that its
cited evidence goes with it and that it does **not** resolve on that removal.

**ids 1 and 9 both land on Tuesday for user 1.** Under the day-overlap trigger these overlap. The
backfill writes directly and is not subject to the write-path validator, but this pair is a
**legitimate same-day distinct** case — the first chat write touching either must not read it as a
duplicate.

### Conform only — 10 rows (users 5, 7, 8), `expected_load: null`

| id | user | from | to |
|---|---|---|---|
| 66 | 7 | `days: ["flexible"]` | `sessions_per_week: 1`, no `days` |
| 74 | 8 | `days: ["flexible"]` | `sessions_per_week: 1`, no `days` |
| 65 | 7 | `days: [monday, wednesday, "flexible_third_day"]` | `days: [monday, wednesday]`, `sessions_per_week: 3` |
| 72 | 8 | `days: [mon, wed, fri]` + `minimum_days: 2` | `days: [mon, wed, fri]`, `sessions_per_week: 2` — the note is the truth ("minimum 2, usually 3"); `minimum_days` was the workaround for a missing field |

**id 23 (user 5) stays a single row.** Its note names three different intensities across tue/thu/sat,
so it violates the uniform-load rule — but with `expected_load: null` no load is asserted, so nothing
is wrong yet. It splits when that user's next chat conversation supplies values. Do not split it
speculatively.

The 7 inactive rows are **not touched** — they are history, correctly superseded.

### The five prod assertions, all unperformed

Read-only, **one statement per run** (`FEEDBACK` §29 — Railway's dashboard editor silently returns
zero rows on a multi-statement paste), each paired with a positive control (`FEEDBACK` §17):

1. active `schedule_item` count is **15** (18 − 3 retired), across 4 users
2. zero active rows carry a key outside the declared set
3. zero active rows carry a non-boolean `same_day_training`
4. zero active rows carry a `days` value outside the weekday set
5. user 1's active count is **5**, and Thursday resolves to **1** entry (id 6), down from 4

**State:** DONE — executed 2026-09-08 (operator via `railway ssh` into health-app-backend; scripts drafted chat-side, no repo writes from chat); **GATE 4 satisfied.** Stage 1 stop-condition PASS (live table matched the 2026-08-23 read exactly: 18 active across users 1:8/5:1/7:4/8:5, dup ids 1/6 on [tuesday,thursday], id 23 single, nothing added since id 79). Stage 2 backfill COMMITTED — 22 changes, **SEASON_MODE=retire** (season_end 2026-09-05 had passed by run date, so rows 1/6/8 were corrected for history then retired), single commit with an inline abort-on-delta re-check on the exact 18-id set; end-state **12 active, not the spec's 15** (retired 2/7/79 per spec + 1/6/8 season-over; conformed 10 rows across users 5/7/8; `phases` stripped from id 9, discharging Q112's cited evidence; `same_day_training`→`same_day_note` prose on 1/2). Stage 3 five assertions PASS, each with a positive control (controls fired on inactive ids 14/4 and a synthetic 'flexible'); **A5 re-derived** — the "user1 thursday = 0" predicate was mis-specified (id 5 work mon–fri legitimately includes thursday); the correct printed result holds: user1 active == {5, 9}, thursday active == [5], all rugby/physio thursday rows (1/2/6/7/79) retired — the pile-up A5 existed to catch is gone. The historical framing below (loop-close for #233's landed half; "Not blocking"; the Next-action plan) is superseded by this execution. **[Original framing follows.]** — **the loop-close for `#233`'s landed half.** Not blocking: the validator is live
and correct, and nothing miscomputes while the legacy rows sit. Owner: Luke, or any session with
database access. **Next action (executed 2026-09-08 — see the DONE record above):** run the stop-condition check first, then the backfill, then the
five assertions. Cross-refs `#233` (the shape), `Q112` (the `phases` block struck by row 9's
correction), `Q117` (`expected_load` granularity), `FEEDBACK` `§29`/`§17`.

---

## Q122. Psychological window — EWMA-stock or divergence-criterion, and its τ

Psychological (#28: sRPE / subjective-vs-objective divergence) is provisioned in the `load_metrics`
window-set but computed by nothing — no sRPE ingestion exists and #32 assigns it no τ. Open: is
Psychological a Banister EWMA stock (needing a τ prior it lacks) or a divergence criterion
(criterion-not-input, no τ, echoing the L4/L5-tension check-in pattern)? Data prerequisite either way:
per-session sRPE captured alongside objective load — a check-in-lane field. Resolve when sRPE ingestion
is built; until then the window is schema-present, compute-absent (fail-closed — the fatigue-τ table in
`load_metrics.py` has no `psychological` key, so a psychological load_event produces no metric row).

**State:** DONE → #267. Resolved to the divergence-criterion horn: a read-time residual producer
(ridge of actual sRPE = session_rpe×duration vs the per-day per-window `daily_load` impulse; one ~7 d
τ on the residual, cold-start hard flip at N=15) plus a down-only life-load modulator wired as a
sibling to `readiness_hint` in the selection re-rank. No Banister τ; the `load_metrics` fail-closed
guard stays. `sRPE` ingestion prerequisite met by `daily_records.session_rpe`. See DECISIONS_LOG #267.

---

## Q123. Zone-less aerobic sessions — calibrated Banister-TRIMP mapping vs permanent skip

The Metabolic transform (`#251`, `metab-v1`) is fail-closed (INV-7): a session with no usable HR-zone
breakdown — every `z*_seconds` NULL, or a zero zone-sum — emits no `load_events` row and is counted in
`sessions_skipped_no_zones`. Edwards TRIMP needs zone seconds, and v1 deliberately admits NO fallback
formula (INV-2 unit-lock: a Banister-TRIMP `duration × avg_HR` row mixed into the same window's series
would break within-window comparability). Open: should a zone-less session that DOES carry `hr_avg` +
`duration_minutes` (Health Connect sessions often do; some Polar exports lack the zone split) be scored
by a calibrated Banister-TRIMP mapped onto the Edwards scale, or stay a permanent skip? A mapping needs a
per-athlete HR-reserve calibration (resting/max HR) to be commensurable with the zone-weighted units, and
lands as a `formula_version` bump (`metab-v1`→`v2`), never an in-place edit. Data prerequisite:
`sessions_skipped_no_zones` volume from a live recompute tells us how much coverage is actually at stake.

**State:** DONE → #255. Ruled a **transport gap**, not a scoring gap: the Polar v4
`/training-sessions/list` endpoint omits `trainingLoadReport`/zones (`backend/connectors/polar.py:196`
— `z*_seconds` null on live-sync, zones ZIP-only), so the fail-closed metabolic transform (INV-7)
correctly skips those rows. Resolved by the Flow (ZIP) export refresh, which carries the zone split
(operator-run 2026-08-29; operator-reported `load_events` 30→47, residual skips = v4 twins + 2 no-HR
one-offs + 1 blip — device-side, not verified against Railway this session). **No fallback formula,
permanently** (INV-2 unit-lock: a `duration × avg_HR` row mixed into one window's series breaks
within-window comparability). The calibrated zone-less-mapping option stays a future `formula_version`
bump (`metab-v1`→`v2`), never an in-place fallback — folded into this closure, not a live open fork.

---

## Q125. Does the web-task harness's draft / no-self-merge constraint conflict with CLAUDE.md's self-merge disposition?

The web-task harness opens PRs as **draft** and does not self-merge them (operator merges). CLAUDE.md's
merge disposition says Code merges its own PRs, ready-for-review, on green. Prior chat framing called this
a contradiction. Is it?

RESOLVED (by convention; no ruling required). No conflict — two non-overlapping PR classes: **(1)**
harness-originated feature PRs open **draft, operator-merged**; **(2)** Code-originated PRs open
**ready-for-review, self-merged on green**. The disposition already scopes to Code's own PRs ("Code merges
its own PRs"), so a harness-originated draft is simply the other lane, not a violation of it. Evidence in
this repo's own history: the feature lane — PR #122, PR #125 (drafted, operator-merged); the
Code/governance lane — PR #124, PR #126 (ready-for-review, self-merged on green). Framing corrected from
"contradiction" to "two lanes."

Not recorded as a DECISIONS entry — this is a clarification, not a decision (a third copy would be
triple-recording). No CLAUDE.md edit: the disposition block already reads "Code merges its own PRs", so it
is already scoped to Code-originated PRs and the conditional carry-forward clause was a no-op (dropped per
its own GUARD; see closeout).

**State:** DONE — resolved by convention (mint-then-close; no DECISIONS entry, no CLAUDE.md change).

**Superseded by DECISIONS #257** — the operative "two non-overlapping PR classes" convention is retired (origin creates no lane; one disposition, one hold for un-ratified decisions). The question stays DONE and append-only; only its convention is superseded, not the question.

---

## Q127. Route `load_events_metabolic.py` through the same-bout arbitration in `reads/aerobic_reads.py`

The Metabolic transform (`backend/load_events_metabolic.py`) reads `AerobicSession` **raw**
(`select(models.AerobicSession).where(user_id == …)`, line 164) — it does **not** route through
`reads/aerobic_reads.arbitrated_sessions` / `arbitrate`, the read-time cross-source same-bout
arbitration (Polar vs Health Connect, interval overlap ≥ `OVERLAP_THRESHOLD` of the shorter bout →
higher-fidelity source is canonical). Today single-emission of the metabolic series is guaranteed only
**accidentally**: a Polar v4 (`polar_v4`) row and its Flow-export (`polar_flow_export`) twin describe the
same bout, but the v4 row is zoneless (v4 list endpoint omits zones, #255/Q123), so the fail-closed
transform (INV-7) skips it — the skip is doing arbitration's deduplication job by side effect, not by
design. Open: should the transform consume `arbitrated_sessions` (emit only from the canonical row of
each same-bout cluster) so single-emission is a *guaranteed* property rather than a coverage artifact?

**Ordering constraint (state verbatim, load-bearing):** this OQ **BLOCKS any Polar v4 zone-enrichment
work; enriching v4 rows before arbitration lands double-emits every dual-lane bout.** Once a v4 row
carries zones, both it and its Flow-export twin qualify (INV-7 no longer skips the v4 row) and both emit
a metabolic `load_event` for the same bout — a double-count in every window the pair touches. So the
arbitration-routing here must land *before* any v4 zone-enrichment (which is itself the `metab-v1`→`v2`
fork noted in Q123/#255). Out of scope for #255, which retired the ACWR readout only and did not touch
the transform's source query.

**State:** DONE → #260. The transform now sources rows through `arbitrated_sessions` and emits
only canonical + qualifying rows. The precondition check (per the brief) surfaced that the
"flow_export twin is non-canonical" premise did NOT hold as written: `_SOURCE_RANK` tied
`polar_v4 == polar_flow_export`, so a byte-identical twin fell through to the id tie-break and
the earlier-ingested (zoneless) v4 row could win canonical — dropping the bout, not a no-op.
Resolved (operator-ratified) by ranking `polar_flow_export` (3) > `polar_v4` (2) > `health_connect`
(1): the export row is strictly richer than the list-sourced v4 twin, so it is deterministically
canonical. Single-emission is now a guaranteed property. The one intended output change is a zoned
cross-source overlap collapsing from two emissions to one.

---

## Q130. Samsung HRV unification into `hrv_readings` + recovery.py rewire

Migrate existing Samsung HRV from `samsung_hrv_readings` into `hrv_readings` (`source='samsung'`,
`rmssd_ms=hrv_ms`), repoint the scraper's HRV write, and rewire `recovery.py`'s HRV read to
`recovery_reads.canonical_hrv`. Until done: HRV is transitionally split (Garmin in `hrv_readings`,
Samsung in `samsung_hrv_readings`) and `recovery.py`'s user-facing HRV read is unchanged.
`samsung_hrv_readings` then becomes the Samsung sleep store. This is the consumption/unification
follow-on to the ingestion lane (#258/#259).

**Resolution (#265/#266).** Unification done: `samsung_hrv.py` dual-writes each `passive_overnight`
reading into `hrv_readings` and a held Alembic backfill (`c1d2e3f4a5b6`) migrates existing rows
(insert-only). Consumption done ADDITIVELY: `/recovery/summary` gains a source-agnostic `hrv` block
built from `canonical_hrv` — Garmin and (post-unification) Samsung are now read, not just stored. The
`recovery.py` "rewire" was scoped to ADDING the block, not repointing the existing `samsung` block: the
FULL restructure (retire the samsung-block HRV duplication + a source-agnostic sleep read) is deferred
to Q134, and dropping `samsung_hrv_readings.hrv_ms` to Q135.

**State:** DONE → #265/#266 (residual full restructure → Q134; `hrv_ms` drop → Q135)

---

## Q133. garth is deprecated upstream — durability of the Garmin HRV lane

Discovered during #258 implementation: `garth` (0.8.0, the OAuth engine under `python-garminconnect`)
prints a deprecation notice ("Garth is deprecated and no longer maintained") pointing to a GitHub
discussion. The lane is deliberately fragile-by-design and household/operator-only (#258), and the deps
are pinned EXACT, so a passive break is guarded against. But a deprecated auth engine is a standing risk:
Garmin auth changes will eventually not be tracked upstream. Watch for a maintained fork or an alternate
transport; if the lane goes dark and no fix exists, it degrades to the clean "reconnect Garmin" state
(costing only HRV, not the HC-sourced commodity signals — the resilience rationale of #258). No code owed
now; this is the durability watch-point.

**Reframe + resolution (#263).** The framing understated it: garth was not merely *deprecated*, its
mobile-app auth was *server-side blocked* — Garmin's March-2026 Cloudflare TLS fingerprinting rejects
the pre-curl_cffi handshake, so new garth logins fail outright (not a future risk; a live break). "Pin
EXACT" had frozen the broken version rather than mitigating it. Resolved by moving to
garminconnect==0.3.11, which rebuilt auth on curl_cffi (Chrome JA3 TLS impersonation) and dropped garth
entirely; garth removed from requirements. The token/exception surface is unchanged, so no connector
logic changed — dependency fix only (#263).

**Residual watch (unchanged in kind).** This is a cat-and-mouse lane: Garmin is actively hardening (TLS
fingerprinting now, OAuth 1.0a retiring end-2026). When the next tightening lands, the fix is to bump
the pin *forward* to the next working garminconnect release — never freeze backward on a version broken
server-side. The durable, B2B-viable channel remains the self-fronting aggregator, outside the
consumer-auth arms race.

**State:** DONE → #263 (residual cat-and-mouse watch continues — bump the pin forward when Garmin next tightens)

---

## Q137. Audit other tests for naive `date.today()` anchoring against AEST-computing code

The CBT-I eval-trigger fix (PR #154) found `tests/test_cbti_eval_trigger.py` seeding fixtures on naive
`date.today()` (container-local, ≈UTC in CI) while the engine counts elapsed days against AEST
(`_today_aest()` = `datetime.now(Australia/Brisbane).date()`, `routers/checkin_v2.py`), so day-count and
`effective_from` assertions went off-by-one whenever the local date lagged the AEST date — the suite
reddened on the calendar, not on a code change. The same anti-pattern may recur wherever a test anchors
its "now" on naive `date.today()`/`datetime.now()` but exercises code that computes "today" in AEST.

Concrete lead: `tests/test_capability_observations.py::test_a_future_measurement_date_is_refused` fails on
clean master ("DID NOT RAISE ValueError") — a future-date guard whose seed may be computed naive against an
AEST refusal boundary (UNCONFIRMED; could also be a genuine pre-existing bug unrelated to tz). Verify before
assuming tz.

The sweep: grep tests for naive `date.today()`/`datetime.now()` used as the "now" anchor, cross-check
against whether the exercised code uses `_today_aest()` (or otherwise computes AEST), and repoint the test
to the engine's clock — as PR #154 did. Do NOT "fix" the engine to UTC: AEST is the user's calendar, the
engine is correct. Scoped out of PR #154 deliberately (test-only, single concern).

**State:** DONE → (no entry) — resolved by PR #182 (2026-09-10) — three anchors repointed onto the AEST helper each code path
actually uses (the #154 pattern), engine untouched, full backend suite green (1449 passed).

- **Repointed (were live):** `test_a_future_measurement_date_is_refused` → `observations._today()` — the
  write-path future guard's own clock (`engine/observations.py:130`, `if observed > _today()`). Confirmed
  the Q137 "could be a real bug" lead was skew, not a bug: with the runner on UTC and AEST a day ahead,
  `date.today()+1d` collapses onto the engine's today, so the strict-greater guard correctly does not fire.
  Both `test_resolved_on_defaults_to_today_when_omitted` (injury + schedule) → `_local_day()` — the resolve
  path's `resolved_on` default (`routers/knowledge.py:676`, AEST/Q42), which the tests had asserted `==`
  UTC `date.today()`.
- **Audited, non-live (not repointed):** the remaining ~28 `date.today()` + 17 `datetime.now()` anchors in
  `backend/tests/`. Evidence they are non-live: green on #180's in-window run `7c9a570` AND on this session's
  local run. Every `datetime.now()` is tz-aware `datetime.now(timezone.utc)` compared against UTC quantities;
  the surviving `date.today()` uses store fixture creation dates (`added_at=`) never asserted-equal to an
  AEST-computed value. Only the three where a runner-clock value was asserted `==` an AEST-computed date
  actually skewed.
- **Prod-code `date.today()` (reported, not fixed — see Q140):** three `backend/` non-test sites.
  `cbti/replay.py:349` is CLI-only (`main()` under `__main__`), not a request path. `routers/knowledge.py:315`
  (`expire_stale_entries`, live via `chat.py:677` / `knowledge.py:603`) and `injury_trajectory.py:144`
  (`evaluate`, live via `mcp_server.py:486`, which passes no `today` so the UTC fallback fires) both compute a
  user-facing "today" in UTC → a real AEST-boundary skew. Two live → Q140 opened.

---

## Q144. Hevy routine-create hardening — two prior-art findings the create path must inherit

Surfaced building the routine read-back (#285). Recorded here, NOT acted on in #285 (a read-only tool); they gate the
next arc item — the routine create-guard ("#1"). Both are settled findings, owed to that build:

- **(a) Check-exists-before-create — Hevy has no delete.** The Hevy API exposes no delete for routines OR exercise
  templates, so a create-on-retry (or a create the model fires without checking) mints an UNDELETABLE duplicate — the
  same class the custom-exercise path already guards against (`create_and_resolve` idempotency pre-check, #65; the
  connector comment "an API with no delete"). The routine-create path has no such guard today. **Fix owed to #1:** the
  create must first read existing routines (via #285's `search_hevy_routines`) and short-circuit / confirm on a
  title-existence hit rather than blindly POST. This is precisely why #285's cheap compact list exists.

- **(b) Strip `rpe` from routine-create set payloads — routines ignore it.** Hevy routines are prescriptions; RPE is a
  live-logging (workout) field only (Hevy docs), so a routine set's `rpe` is rejected/ignored. Yet the create payload
  builder emits `rpe` on routine sets (`connectors/hevy.py`, the `for field in (... "rpe" ...)` set loop) — carried over
  from the workout-set shape. **Fix owed to #1:** drop `rpe` from the routine-create set fields (leave the workout read
  path untouched — `format_set` rendering RPE on read-back is correct there).

Owner: Luke / next build (routine create-guard). Neither blocks #285.

**Discharged (#286, this arc).** Both findings acted on in the connector floor:
- **(a) idempotency — DONE.** `create_routine` now reads the paginated `/routines` list and raises typed
  `RoutineAlreadyExists` before the POST on a same-(title, folder) collision (case-insensitive title, equal folder;
  refuse+offer, never auto-clobber — [fork] ratified by Luke: refuse+offer, title+folder). Both entry points inherit it
  (chat → WriteResult `already_exists`; REST → 409).
- **(b) rpe strip — DONE.** `rpe` removed from the routine set-field tuple; deterministic floor, not prompt-only. The
  workout READ path (`load_events`, `format_set`) is untouched — there is no workout-CREATE path to affect.
- **Superset write (d, #287)** also landed this arc: `superset_id` + the fragile conventions documented in
  `_section_routine_creation`.

**Residual — DISCHARGED (#288).** The exercise-action lane (`_process_exercise_actions`) is folded onto
`write_results` — wrap-only, no collision guard, because the lane is already idempotent (the `resolve_exercise`
pre-check + `create_and_resolve`'s #65 pre-check + the #212 freshness gate structurally prevent a duplicate mint). It was
the last string-only Hevy write surface; with it wrapped, the acknowledgement-discipline arc across schedule
(#281/#283/#284), `/chat` knowledge, Hevy routine (#286) and Hevy exercise (#288) is complete — no write lane can narrate
an unverified success.

**State:** DONE → #286 (a,b) · #287 (d) · #288 (exercise-lane fold; residual discharged — arc complete)

---

## Q146. Schedule-save narration doubling — cosmetic or duplicate rows? (Concern B)

The `/chat` turn that saved the five decompression schedule entries emitted each save line twice, then
`✓ 5 saved` (ten ticks for five entries). Code analysis (this session — NOT a prod read, per the unseeable-
surface rule; no psql from the sandbox, the data connector needs auth it can't do non-interactively):
- **No duplicate ACTIVE rows possible by construction.** `upsert_knowledge_entry` supersedes any existing
  active row with the same key (deactivates it, `superseded_by`), so per key there is at most one active row;
  the five keys are distinct (`decompression_gym_mon/wed/fri`, `decompression_swim_tue/thu`) → five active rows.
  A genuine double-write of one key would leave an inactive SUPERSEDED sibling, not a second active row.
- **The doubling is Likely cosmetic.** The `✓ 5 saved` footer is computed from `write_results` (5 entries) →
  5 blocks processed → 5 writes; the extra five ticks are the model echoing the confirmations in its own prose
  alongside the deterministic action strings. Ten visible ticks, five writes.

Definitive confirmation is a read Luke runs (via the health-app data MCP in chat, or `railway connect
health-app-DB`): expect five keys, each `active=true` once, correct day/time, and NO superseded siblings.
Superseded siblings would prove a real double-write (a schedule-lane idempotency bug); their absence proves
cosmetic. Do not auto-clean if duplicates are found — Luke rules.

**Resolved (verified by direct prod read, Luke 2026-09-12).** The five entries exist as ids 82–86
(`decompression_gym_mon/wed/fri_2026`, `decompression_swim_tue/thu_2026` — note the `_2026` key suffix the
first verification query dropped, §43), each `active=t`, exactly one row per key, NO `active=f` superseded
siblings — plus the earlier 80–81 (Sat pilates, Sun recovery) as single clean rows. So the doubled `✓` ticks
were cosmetic exactly as the structural analysis predicted: five blocks, five writes, five rows. No
double-write, no idempotency bug. The write path was truthful throughout; the earlier "0 rows / serious case"
scare was a truncated-key verification query, not missing data (§43).

**State:** DONE → #289 (Concern B closed, verified not inferred)

---

## Q154. Aerobic ingest is not automatable — the metabolic branch of the scheduled load chain rolls stale `aerobic_sessions`

The #296 scheduled orchestrator (`scripts/refresh_load.py`) automates the resistance ingest (Hevy API → `hevy_workouts`) but NOT the aerobic ingest. Step 3 (`load_events_metabolic`) only ROLLS whatever is already in `aerobic_sessions`; nothing in the nightly sweep refreshes that table, so metabolic load silently ages to the last manual Polar pull. Verified 2026-09-14: the two writers of `aerobic_sessions` are both unautomatable as-is —

- `routers/polar.py::sync_polar_sessions` — the Polar AccessLink **API** pull, the only path that fetches fresh sessions. Request-coupled: `current_user` dependency + a per-request OAuth client (`_valid_client(current_user.id, db)`). Making it batch-callable crosses the router/contract boundary #296 was explicitly scoped OUT of.
- `import_polar.py::import_flow_export` — a batch-callable **ZIP-export** CLI, but it needs a human-downloaded Polar Flow export ZIP per run (no API pull). Not a recurring automation candidate.

So v1 scopes to rolling existing aerobic sessions only (#296 decision), leaving a freshness gap on the metabolic window.

**Trigger to close / options:** extract the Polar AccessLink fetch+persist core out of `sync_polar_sessions` into a per-user batch callable (token read from `UserIntegration(provider="polar")`, refresh handled outside the request), then add it as the aerobic counterpart to step 1 in `refresh_load.py` (Hevy and Polar ingests side by side, each per-user isolated). The refactor must preserve the endpoint's contract (the router keeps calling the extracted core). Until then the nightly metabolic figure is only as fresh as the last manual Polar sync.

**Resolution (#353).** Brief C extracted the Polar v4 fetch+persist core (`backend/polar_ingest.py::sync_user`), as the trigger above proposed. The token store and refresh moved with it. The manual route delegates and keeps its contract: the response is byte-identical, with 404 / 424 / 502 as before. The load chain now runs `polar_sync` after `hevy_sync` and before `load_events_metabolic`, so a new session lands on Training-page open or pull-to-refresh (30-day window) and in the 02:00 sweep (180 days). It runs with no cascade, because the chain's own metabolic steps recompute. It is soft-fail (ruled): a missing Polar connection or a failed pull is recorded in the step and never fails or stalls the chain. The webhook alternative is split out as Q193, feasibility only. The prod check (record a session, don't press Sync, open Training) is OWED (operator).

**State:** DONE → #353

---

## Q155. Garmin HRV has no ingestion trigger — connecting stores a token but nothing pulls

Diagnosed 2026-09-15 (#298): Garmin overnight HRV reaches `hrv_readings` only when something RUNS the pull — `POST /integrations/garmin/sync`, the `scripts/garmin_sync.py` ops runner, or the export backfill. There is NO scheduler: `main.lifespan` runs only the #297 load sweep, not Garmin, and connecting Garmin (`POST /integrations/garmin/token`) stores an encrypted token and pulls nothing. So a freshly-connected user sees no HRV until a manual sweep, and the recovery card's freshness silently depends on that sweep having run — exactly this session's failure, fixed by one hand-run `scripts.garmin_sync --from 2026-09-13 --to 2026-09-15` (3 nights, 235 samples, token alive).

**Options / trigger to close:** the parallel to #297's load model — either an in-process nightly sweep in `main.lifespan` over Garmin-connected users (off the loop via `asyncio.to_thread`, mirroring `load_sweep.py`), or an on-demand `POST /integrations/garmin/sync` fired fire-and-forget from a surface the user already hits (check-in / dashboard load), staleness-gated. The unofficial `garminconnect` auth is fragile (curl_cffi cat-and-mouse, #259) and a dead token raises `GarminReconnectError` → 424, so any sweep must isolate per-user failures (as `garmin_sync.py` already does) and never abort the batch. Distinct from Q154 (aerobic ingest): same shape (an un-automated ingest feeding a downstream read), different source.

**Also surfaced (ops, not this question):** the 2026-09-15 sweep hit TWO Garmin-connected users (ids 1 and 4) with identical pulls — likely one Garmin account stored under two `UserIntegration` rows. Verify and clean up if unintended; left untouched this session (may be a test + real split).

**Resolution (#299).** Both triggers, on #297's in-process rail (not a dedicated cron — #297 removed that as the fragile part): (a) on-read `POST /integrations/garmin/refresh` fires on Recovery-card open, staleness-gated, `force`-bypassable — the freshness leg that lands this morning's HRV after Garmin's ~6am sync; (b) `garmin_sync` added as a second per-user job in the 02:00 Brisbane sweep — the guarantee for un-opened mornings, accepted as landing only the prior night. Per-user isolation reused from `garmin_sync.py` (dead token caught, rolled back, skipped). No schema change: the gate reads `max(hrv_readings.created_at)` (data-recency; no attempt-recency marker exists — `UserIntegration.updated_at` reads fresh right after connecting). The two ops notes above stay open as their own concerns: the get_hrv_range ~7-day self-heal ceiling is a known limit (not fixed here), and the duplicate Garmin `UserIntegration` for users 1 & 4 is data hygiene (per-user isolation keeps the sweep clean regardless).

**State:** DONE → #299 (both triggers landed; the read-path composite decision — Garmin HRV vs Samsung sleep coherence on one record — is deliberately out of scope, falls due only if Garmin sleep ingestion is added).

---

## Q160. Do non-training activity minutes belong in the psychological felt-load term?

Raised 2026-09-18 with #309 (HC exercise ingest) at PR review. `reads/psychological_reads._duration_min_by_day` sums per-day training minutes; that Σminutes × `session_rpe` is the "felt" load — the target `y` of the ridge regression in `psychological_residual` (the subjective-vs-objective decoupling marker, #28; a down-only diagnostic, consumer deferred) — and its session count flags a multi-session day.

#309 fixed the double-count (canonical aerobic rows only; a bout overlapping a counted Hevy workout excluded; Hevy via the `counted_workouts` door) but deliberately did NOT decide **whether a canonical walk, rehab swim, or pilates session should contribute minutes to this felt-load term at all**. The resolver excludes such sessions from a *conditioning* quota by sport declaration (activity-slot v2), but the psychological felt-load term is a different consumer with its own meaning: a 40-minute walk at RPE 2 is real perceived effort, or it is noise that dilutes the decoupling signal — not obvious either way.

**INTERIM (merge condition 1, #309):** `health_connect`-source rows contribute NOTHING to this metric — no minutes, no session tally — so the ingest does not perturb the pre-#309 Polar+Hevy series. Decision pending, **likely by declared sport** (reuse the activity-slot v2 declaration, not a second sport list). Until then, HC activity is OUT.

**To close:** rule whether the felt-load term filters by sport/activity kind (and which kinds), and lift the interim HC exclusion accordingly. Read-time only; no schema.

**State:** DONE → #322. Sessions in the static `NON_TRAINING_SPORTS` set (Walking/Pilates/Yoga/Stretching, case-insensitive, all sources) contribute no minutes and no tally; the #309 interim HC exclusion is lifted for everything else. The set is static, NOT the activity-slot declaration this entry anticipated, because declarations are phase-scoped (#302 series invariance).

---

## Q161. Reader-consistency audit — which readers of `aerobic_sessions` / `hevy_workouts` skip the canonical / excluded_at / dedup_flag filters

Raised 2026-09-18 with #309, at PR review. The `_duration_min_by_day` double-count (fixed in #309) is one instance of a class: a reader that sums or lists rows without the read-time canonical filter (aerobic) or the `excluded_at`/`dedup_flag` filters (hevy) over-counts once the HC ingest lands (a bout gains twins + a Hevy co-log). The operator asked for a sweep of ALL readers; this entry is its durable home and the **S0(d) input to the queued Hevy-deletion brief** — do it once.

**Aerobic — no canonical filter (twins/mirrors double-count):**
- `reads/psychological_reads._duration_min_by_day` — **FIXED in #309.**
- `mcp_server.get_readiness_snapshot` — raw SQL `COUNT(*)` + `SUM(duration_minutes)` over last-7d `aerobic_sessions`; readiness numbers can double-count a Garmin bout + its twins. **Newly material.** Feeds EXTERNAL MCP clients (not the in-app coach, which has no tool runtime).
- `mcp_server.get_training_sessions` — raw SQL list of last-N-days sessions; lists each twin. **Newly material.** External MCP clients.
- `cbti/replay.load_nights` (`_TRAINING_SQL`) — raw SQL; partly mitigated (keys into a `{date: stop_time}` dict so same-day twins collapse, but the surviving `stop_time` is arbitrary, not the canonical row's).
  (The three raw-SQL readers cannot reuse `arbitrated_sessions` trivially — `canonical` is a read-time Python flag, not a column — so a fix restructures the query or routes through the read helper; a design call for the brief, not a drive-by.)

**Hevy — missing `excluded_at` and/or `dedup_flag`:**
- `reads/psychological_reads._duration_min_by_day` — **FIXED in #309** (now filters both).
- `load_events.compute_*` (the Tier-0 strength load transform) — filters `excluded_at` only. Round 2 established this is RIGHT for an adjudicated pair (the excluded artifact drops, the retained log counts) but counts BOTH members of an UNADJUDICATED pair. It adopts `counted_workouts` in the follow-up read-door PR behind a gate proving `load_events`/`load_metrics` are byte-identical before/after for users 1 and 4 (they are — every current pair is adjudicated). NOT touched in #309 (the GUARD forbids the load transform here). The operator is pulling the flagged prod rows to confirm.
- `engine/region_exercise.recent_template_ids` — has `excluded_at`, missing `dedup_flag` (a dup biases exercise-rotation recency).
- `audit_bodyweight_templates.audit` — has `excluded_at`, missing `dedup_flag` (audit script; dup inflates counts).
- `audit_laterality_coverage` — neither filter (only `user_id` scope; audit script).

**Well-behaved (for reference):** `load_events_metabolic`, `engine/resolver._in_window_aerobic`, `routers/polar.get_aerobic_sessions` (aerobic, all canonical); `engine/resolver._in_window_workouts`, `routers/series` (hevy, both filters).

**Routing (operator, round 2):** NOT the Hevy-deletion brief (bottom of queue). A **dedicated read-door PR immediately after #231, before plan-of-record**: one read door per table (`arbitrated_sessions` for aerobic; `reads.hevy_reads.counted_workouts` for hevy — both seeded by #309); the two `mcp_server` readers restructured through them (correctness over query elegance); a **drift-guard test that FAILS when either table is queried outside a file allow-list**, so reader N+1 cannot repeat this; every other swept reader fixed or explicitly allow-listed with a reason; `load_events`/`load_metrics` adopt the hevy door behind the byte-identical gate above. #309 fixed only `psychological_reads` (the metric the ingest made blocking) and the resolver (via the shared door).

**State:** DONE → #310. The read-door PR landed the routing: `mcp_server`'s two readers, `region_exercise`, and `series` onto the doors; `load_events` adopts `counted_workouts` behind the byte-identical gate; `cbti/replay` + the two audit CLIs allow-listed with reasons; a drift-guard test (`tests/test_read_door_drift_guard.py`) fails on any new un-doored toucher.

---

## Q162. Which activities constrain a CBT-I night (training_end)?

Raised 2026-09-19 with #311. `cbti/replay.load_nights` sets `training_end` = a training session's stop on the day before a night; a night whose lights-out is within `TRAINING_RECOVERY_MIN` (90) of that is `training_constrained` and excluded from titration. Pre-#309 only Polar fed this (H10 chest strap → deliberate hard sessions). The HC ingest now brings Garmin/Samsung-recorded sessions of ALL kinds into `aerobic_sessions`, so the question is which of them should constrain a night.

**Interim (#311):** `source='health_connect'` is EXCLUDED from `training_end` — no HC session constrains a night — preserving the pre-#309 behaviour. A walk almost certainly does NOT constrain sleep; a hard evening session recorded on Garmin/Samsung arguably does. Not picked here.

**To close:** rule which HC activities constrain a night (likely by declared sport — reuse the activity-slot v2 declaration rather than a second sport list), and lift the interim exclusion for those. `CBTI_TITRATION_POLICY` (operator-held, not in the tree) may define "training session" for this purpose — anchor the ruling on it if so. Read-time only; no schema. Companion to Q160 (the felt-load felt-minutes scope) — same "which activities count for which consumer" shape, different consumer (the sleep engine vs the psychological residual).

**State:** DONE → #322. Sessions in the static `NON_TRAINING_SPORTS` set never constrain a night; every other session does (generic names and a blank/NULL `sport_name` included). The #311 interim HC exclusion is lifted, and per-day `training_end` stays `MAX(stop_time)`.

---

## Q165. A dated / date-range one-off hard item on `schedule_item`?

Raised 2026-09-20 with #316. `schedule_item.days` are WEEKDAY recurrence; `duration_weeks` bounds how long the recurrence lasts; `season_end` is an end date. There is no field for a ONE-OFF dated event (a carnival on 19–20 Sep, travel, an appointment on a specific date). `load_context` carries a `description` + a single `expires_at` and renders as a note, not a day-occupying item the week planner's day-view reads. #316 defers this: active `load_context` entries are surfaced beside the week as undated one-off notes, but a dated one-off does not occupy its day in the availability model.

**To decide:** the smallest shape for a dated one-off hard item — an optional `event_date` or `[start, end]` on `schedule_item`, validated as ISO dates (a validator-only change; `schedule_item.value` is JSON, so NON-schema, like `satisfies` #312 and `activity` #315). It would make the planner mark those exact dates unavailable (and drive the `caution: day after heavy` off them).

**State:** DONE → #317. `schedule_item` gained `event_date` + optional `event_end` (ISO, exclusive with `days`), validator-only (non-schema); `plan_week` marks the days unavailable with the heavy→next-day caution, `_section_schedule` renders a dated line while live, and the phase-change transition writes them. Built with the phase-change form brief as planned.

---

## Q169. Unrecorded training — how should days with training no device captured be represented?

Raised 2026-09-23 after #322. Prod read, 23 Sep: from finals through the decompression phase, user 1 trained without the H10. Only device-recorded sessions exist (4 HC rows, 25 Aug – 20 Sep); operator confirms this is not all training done. No manual write path to `aerobic_sessions` exists (writers: Polar `/sync`, `/import-export`, HC ingest). Q119 backfill cannot recover sessions no device recorded.

**The problem is missingness, not a missing session row.** An unrecorded training day currently reads as a rest day (zero) in every consumer: felt load (`_duration_min_by_day`), CBT-I `training_end` (`cbti/replay._TRAINING_SQL`), and the metabolic window (`load_events_metabolic`, and post-Q159 stage 2). The main harm: the next zoned block reads as a spike against a falsely detrained baseline.

**Decided in principle (operator, 2026-09-24): coverage marker only. No self-reported session rows.**
- The operator can mark a date range as "trained, not fully recorded". No per-session detail, RPE, duration, or time.
- The marker deposits no load and no TRIMP (INV-7 and #255 are unaffected). It changes how confident consumers are in a day, not the day's values.
- Device-recorded sessions inside a marked range still count as usual. For marked days, measured load is a lower bound, not a total.
- Rejected: self-reported `aerobic_sessions` rows, including an sRPE variant. Recalled sessions add build and provenance cost for consumers that the marker already protects.

**Mechanism: open items, adjudicated against master `01d9c38` (Code, 2026-09-24).** These are findings plus a recommendation for each item. Nothing below is ruled; the rulings route to chat.

1. **Store and shape.** #230 governs `source` on `user_knowledge_entries`, but the phase store already imports both provenance domains for its own rows (`engine/training_phase.py:305-315`: `asserted_by` ∈ `ASSERTED_BY_VALUES` (#227, `user|engine|clinician`), `source` ∈ `SOURCE_VALUES` (#230, `onboarding|chat|system|api`), both required, no default). That pattern carries over directly: a marker row carries `source` (channel: `api` for a form or direct write, `chat` if a coach tag writes it) and `asserted_by='user'`, and the write refuses a missing value. `kind` should be a closed vocabulary with one member for now. **A new table is a schema migration → hold (a), full human review, SCHEMA.md in the same commit.** Recommend: the range table as briefed plus `asserted_by`/`source`/`asserted_on`, plus a CHECK on `end_date >= start_date`. Overlapping ranges are allowed (consumers read "any overlap").
2. **Metabolic window: the premise needs correcting.** No spike/ACWR *flag* exists to suppress: #255 retired ACWR, and #306 made `load_ratio` a descriptive value with no band or threshold on any surface. What the marker actually corrupts are the stored `load_metrics` values: `chronic_load` is a trailing 28-day mean with rest days counted as 0 (`load_metrics.py:148-153, 207, 226-228`), and the Banister stocks decay through zero days, so a marked range deflates `chronic`/`fitness` and inflates the next block's `load_ratio`. Readers are `routers/series.py` (chart), the MCP `get_training_load` readout, and `routers/load.py` (freshness only); selection/dosing does not read `load_metrics` (#248). A further point: HC rows are zoneless until Q159 stage 2, so they deposit **no** metabolic TRIMP (`load_events_metabolic.py:204-206`). For the finals block the metabolic window is empty on marked days, not just a lower bound. Recommend: **emit with a low-confidence annotation, computed at read time**, following the `maturity` annotate-never-suppress precedent (#10/#28). A row whose 28-day window overlaps a marked day is tagged. Suppressing or down-weighting the baseline would mean inventing values the marker was defined *not* to produce. It would also need a stock model for skipped days, which Banister does not have.
3. **Felt load: the premise needs correcting.** No baseline denominator exists. `psychological_residual` pairs a day only if `session_rpe` is present AND resolved duration > 0 (`reads/psychological_reads.py:386-391`), so a marked day with no recorded session is **already excluded**, not counted as zero. The real exposure is the opposite case: a marked day with a *partially* recorded session and a whole-day `session_rpe` enters the ridge fit with `actual = rpe × partial minutes` (understated) against partial predictors. That produces a mis-paired row, not a missing one. Recommend: exclude every marked day from pairing, with or without a recorded session.
4. **CBT-I `training_end`: confirmed, replay does NOT distinguish unknown from none.** `load_nights` sets `training_end=training.get(d-1)` (`cbti/replay.py:153-154, 171`). A missing session and "no training" both give `None`, and the engine acts only on `is not None` (`cbti/engine.py:460`, `training_constrained`). A marked night with unrecorded late training is therefore judged as a normal valid night, which can score as an adherence miss rather than a physical floor. The fix is a tri-state on `Night` (e.g. `training_unknown: bool`) plus an engine rule. **The engine rule is an un-ratified call.** The `naps_min` precedent (`engine.py:446-448`) treats null as UNKNOWN and does *not* exclude, while the `training_constrained` logic argues for exclusion (reason `training_unknown`). Changing that verdict re-adjudicates closed blocks on replay; the `cbti_prescriptions` ledger itself is not rewritten.
5. **Retro-entry and #248, per consumer.** The marker changes no stored *value*, so:
   - felt-load residual: read-time, no recompute needed.
   - metabolic `load_events`: values unchanged, no recompute needed.
   - `load_metrics`: stored rows, but the confidence tag is **read-time** under recommendation 2, so no recompute. The tag becomes a recompute (`scripts/refresh_load.py`) only if it is stored as a column, which is a second migration. Read-time avoids both the migration and the recompute.
   - CBT-I replay: read-time; the historical ledger is untouched (see 4).
   - context/MCP readouts: read-time.

**To decide (chat):** (i) CBT-I engine rule for a `training_unknown` night: exclude or keep valid (item 4); (ii) confirm read-time annotation over suppression or down-weighting for `load_metrics` (item 2); (iii) confirm that felt-load pairing excludes every marked day, including days with a partial recording (item 3). Once ruled, the build is one migration (marker table, hold (a)) plus read-time consumers.

**Rulings (chat, 2026-09-24) → #326.** Three consumers are in scope and one is out:
- **CBT-I: out of the marker's scope, past and future.** Code offered two options (exclude, or a `training_unknown` state); chat ruled a third. Every night keeps the verdict the engine gives it today, and replay never reads the marker. Chat's reason: the titration policy (§7, project knowledge) records a night's exclusion class at capture, not at evaluation, to stop post-hoc excusal. A range marker entered after the fact is exactly post-hoc excusal. Both exclusion shapes also fail on master's mechanics. As *excused*, a multi-week range breaches #253's one-excused-per-cycle cap. As *disqualifying*, it drops every night in the range and turns each cycle into an insufficiency HOLD, which penalises the operator for flagging the gap honestly. The finals-block verdicts stand as computed.
- **Metabolic: read-time low-confidence tag.** A `load_metrics` row is tagged when a marked range overlaps ANY window its value depends on: the acute (7 d) and chronic (28 d) trailing means, and the fitness/fatigue decay history. Stored values are unchanged, so no second migration and no #248 recompute. Because HC rows are zoneless (Q159 stage 1), the finals block is a genuine gap in this window, not a partial undercount.
- **Felt load: read-time exclusion.** Every marked day is left out of `psychological_residual` pairing, including days with a partial recording.

**Build:** one held migration (the marker table, hold (a), SCHEMA.md in the same commit) plus read-time consumers for metabolic and felt load. No CBT-I change. The residual CBT-I risk (an unrecorded late session scored as an adherence miss) has no capture path on master → raised as Q170.

**State:** DONE → #326. Marker-only; CBT-I out of scope; metabolic read-time tag; felt-load read-time exclusion. Build follows the migration review.

---

## Q172. S7 — which diary entry-side fields may each HC source's session start fill?

Raised 2026-09-25 with the HC sleep-clocks decision (#328). `health_connect_syncs` now persists `sleep_start` / `sleep_onset` / `sleep_end` with per-endpoint writer packages. Nothing maps start or onset to `got_into_bed` / `lights_out` / `out_of_bed` (#127). Whether a device's "start" means into-bed, lights-out, onset, or none of them differs by writer and is unmeasured.

**Evidence owed (report only, after release and the operator's 30-day deep sync, HCA `handleSync(30)`):**
- For each night with a recalled diary, compute in minutes: `sleep_start − got_into_bed`, `sleep_start − lights_out`, `sleep_onset − lights_out`, `sleep_end − final_wake`.
- Group start-based deltas by `sleep_start_source_package` and end deltas by `sleep_end_source_package`, with median and IQR per source.
- Report mixed-writer nights (start writer ≠ end writer) separately, never pooled.
- Where a same-day Samsung scrape exists, also compare the scraped bedtime with `sleep_start`.

**To decide:** a per-source table of which entry-side fields that source's start or onset may prefill (possibly none).

**Evidence (operator S7 run, 2026-09-25, 25 nights):**
- Garmin, independent-diary nights 09-16..09-24: `start − (lights_out + recalled SOL)` = −5, −5, +17, +1, +4, 0 (09-16 −20). So Garmin start ≈ sleep onset.
- `end − final_wake` = 0, 0, 2, −1, −4, 0. So Garmin end is validated as final wake.
- 09-19: the diary `final_wake` of 06:00 is true (woke about 03:55, back to bed, slept to 06:00), but the HC end was 03:55. The record-sources query found one Garmin session only: the re-sleep never reached HC.
- Ring nights: `got_into_bed` was prefilled from the same source (circular) or selectively corrected (biased), so no ruling is possible.
- 09-16: the start writer was `com.sec.android.app.shealth` while the ring was dead. Samsung Health relays other devices' sessions, so the writer package is not the recording device.
- 08-26: the main-period start was 04:22 against `got_into_bed` 22:35. A main period can be a late fragment.

**State:** DONE → #329. Garmin start = onset and fills no entry-side field. Garmin end is validated for `final_wake`. Ring and Samsung are unruled (#127 stands; validation window Q176). Future rules key on the recording device (Q175). Any start-based prefill must guard against a late-fragment main period.

---

## Q179. Pre-existing unconfirmed exercise tags — confirm or remove before the v0.1 seed?

Raised 2026-09-27 with #338. A plain (non-`--confirm`) seed run writes `llm_proposed` rows, and Rule 1
(`engine/resolver.py`) counts every tag regardless of `source`. So rows from earlier plain runs may already be
crediting quotas with nothing a human signed. Code cannot see prod. `seed_exercise_region_tags.py 1 --dry-run` now
lists every such row and marks each one either **re-stamped by --confirm** (the reference still plans it) or
**PRUNE** (it does not).

**Proposed ruling (one, covering all of them):** run the seed as `--confirm --prune-unconfirmed`. Rows the reference
still plans pass through the confirm gate and become `human_confirmed`; every other unconfirmed row is deleted. After
the run no unconfirmed row remains, so Rule 1 counts only what the reference, as confirmed, says. Deletion is
recoverable by adding the entry to the reference and re-seeding. Keeping an unreviewed row is not recoverable, because
it keeps counting silently. The alternative, `--confirm` without prune, leaves the PRUNE rows counting as `llm_proposed`.

**Evidence (operator, 2026-09-27):** `--dry-run --prune-unconfirmed` reported **0 pre-existing unconfirmed tag rows**, so there was nothing to prune. The seed then ran as `--confirm` without prune.

**State:** DONE → #339. Moot: prod held 0 unconfirmed tags on 2026-09-27, so neither branch of the ruling applied. The flag stays available for a future non-confirm run.

---

## Q185. Bounded in-turn retry for a refused chat write?

Raised 2026-09-28 with the typed-entry write-shape fix. A `<knowledge_update>` refused for shape is final for
the turn: the model cannot see the validator message until the NEXT turn, so the user must ask again.
Prod, 28 Sep: three constraint writes refused in a row. Retries with the user's corrected block also failed,
because the server parses blocks only in the MODEL's reply, never in the user's message, and the model
re-emitted its own shape. The generated write-shape docs remove the cause. This question is about the
remaining recovery path.

**Proposal (not built):** on a 422-class refusal (`invalid_shape` / `unknown_field` / typed lifecycle codes),
hand the model the validator message once and let it re-emit the block before replying. Cap: 1. Only the
refused block is re-emitted, and no other write re-runs.

**To decide:**
- whether at all;
- which codes qualify (never `day_time_clash` or `operator_only`, which are user or operator decisions);
- the cost: one more model call on a refused turn, on top of pass-2;
- how it interacts with narrate-after-write, which already costs one extra call on failed-write turns.

**State:** DONE → #344 (ruled 2026-09-28: yes, scoped — shape refusals only, cap 1 per write per turn, the validator's message verbatim, every outcome logged; the region list also leaves the prompt).

---

## Q187. Chat asks "Do you confirm?" before a typed write, then the "yes" turn writes nothing and renders empty

Raised 2026-09-28 (operator, prod). Before a finding write (`finding_mri_cervical_20260918`) the coach asked a
conversational "Do you confirm?". The operator's "yes" came back as an EMPTY bubble and nothing was written.
Re-sending the original request wrote the row first time. This matches the "first attempt never writes" pattern
seen since #273. It is not a shape refusal, so the #344 retry never fires.

**Evidence.**
- *Transport.* Every `POST /chat` on 28 Sep (Railway http log, 03:29–09:53Z) returned 200. The empty bubble was
  a 200 with an empty `response`, not a server error.
- *What the model returned is unrecoverable.* The backend deploy log carries one Anthropic `HTTP Request: POST` per
  turn (two when pass-2 fires) and no reply content, stop reason or block count. Scope of this negative: the deploy
  stream of `health-app-backend`, 28 Sep.
- *H3, previous instance (operator):* the "yes" turn wrote nothing. This instance's duplicate check is OWED to the
  operator (Code cannot see prod): `SELECT id, key, active, source, added_at, superseded_by, value->>'status' AS status FROM user_knowledge_entries WHERE user_id = 1 AND type = 'finding' AND key LIKE 'finding_mri_cervical%' ORDER BY id;`
  (columns read from `models.UserKnowledgeEntry`; an upsert on a reused key supersedes, so a second write shows
  as an inactive row with `superseded_by` set).
- *H1, mechanism (operator, prod, 28 Sep):* appending "Write it now; don't ask me to confirm." made the write land
  on the first turn. The in-chat confirm step is prompt-induced. The typed-entry guidance said "You only ever
  PROPOSE one: the user confirms it themselves", and SCHEDULE INTELLIGENCE STEP 1 ("ASK BEFORE WRITING") covers
  "injury management". The confirm gate is the Injuries page's Confirm button (`Injuries.jsx:312-314`, #346), not chat.
- *H2, code reading.* Paths that give a 200 with no text, no write and no footer: a reply made only of a mimicked
  save line ("✓ Finding entry saved: …", eaten by the #314/#316 echo strip); a reply of only `<thinking>` (eaten
  by #313's strip); an empty reply. Two further silent drops: a typed block with no top-level `key` fell through to the
  legacy branch and was dropped unrecorded; a legacy block with empty `content` was dropped unrecorded. Which path
  fired on 28 Sep is not determined. A mimicked save line is the likeliest, since the history carries prior footers.

H3 answered 28 Sep: operator prod query returned one row (id 105,
finding_mri_cervical_20260918, active, confirmed); no duplicate. The "yes" turn wrote
nothing. PR #278 prod proof: the next chat write lands on the first turn.

**State:** DONE → #347 (prompt: write proposals directly, never confirm in chat; a turn never renders empty; silent
drops become reported refusals; per-turn metadata logged).

---

## Q192. A live restriction under an already-resolved injury cannot be parented

The operator ruled (29 Sep) that `constraint_shoulder_right_er_load_cap` (prod id 104, active,
confirmed, `parent_key` null) is a live restriction to be parented to `injury_shoulder_right`,
which stays resolved (2026-09-24). With a null parent the row sits in no appointment's scope,
so no brief can ever show it (`appointment_brief.py:187`). The standard write path refuses the
fix: `_validate_typed_write` requires `parent_key` to name an ACTIVE row
(`routers/knowledge.py:1039-1052`), and a resolved injury is `active=False`. The target state
already exists in the model (`parent_resolved_survives`, `injury_sweep.py:313-331`), but only
when a parent resolves after parenting. Options: (a) allow `parent_key` to name a resolved,
unsuperseded injury when `exit.with_parent` is not true (recommended; narrow, and it matches
G5 ruling 1); (b) scope the brief by ask links as well as parents; (c) reopen the injury
(ruled out by the operator). No ledger write until ruled (#351).

Operator reads owed (psql via `railway connect` to `health-app-DB`, one statement each):
- `SELECT id, key, active, value->'exit' AS exit, value->>'review_by' AS review_by, value->>'parent_key' AS parent_key, value->>'status' AS status, value->>'asserted_by' AS asserted_by FROM user_knowledge_entries WHERE id = 104;`
  (HALT the write if `exit` is `with_parent` alone, with no `on_date` or `on_condition`.)
- `SELECT id, active, value->'scope'->'parent_keys' AS parent_keys FROM user_knowledge_entries WHERE key = 'appt_20261001_aubrey' ORDER BY id DESC LIMIT 1;`
- `SELECT id, active, value->'resolution' AS resolution FROM user_knowledge_entries WHERE key = 'injury_shoulder_right' ORDER BY id DESC LIMIT 1;`
- Orphans: `SELECT id, key, value->>'status' AS status, value->'exit' AS exit FROM user_knowledge_entries WHERE type = 'constraint' AND active AND COALESCE(value->>'parent_key', '') = '' ORDER BY id;`
- Asks pointing at one: `SELECT a.key AS appointment, ask->>'id' AS ask_id, ask->'resolves'->>'entry_key' AS entry_key FROM user_knowledge_entries a, json_array_elements(a.value->'asks') ask WHERE a.type = 'appointment' AND a.active AND ask->'resolves'->>'entry_key' IN (SELECT key FROM user_knowledge_entries WHERE type = 'constraint' AND active AND COALESCE(value->>'parent_key', '') = '');`

**Ruling (operator, 29 Sep 2026):** option (a), narrowed. A constraint may name an injury whose current row is
resolved, only when `exit.with_parent` is not true; `with_parent` true on a resolved parent is refused with its own
message. Missing, superseded, proposed and rejected parents stay `invalid_parent`, and so does a finding with an
inactive parent. (b) is rejected: an ask must not widen brief scope (#345), and it would hide orphans rather than fix
them. (c) was already ruled out. Row 104's exit read: `on_condition` only, so the HALT case did not apply. Row 110
supersedes row 104 under `injury_shoulder_right`. The orphan query above is still OWED (operator), carried in
`closeout.md`.

**State:** DONE → #352 (validator `0a2c138`, PR #285; row 104 superseded by row 110; the prod brief lists the cap once and
the ask resolving it has `unresolved: false`).

## Q194. Should the session focus persist across follow-up turns of a review conversation?

#354's `focus_session` rode the trigger turn only: the pinned session block was appended to that turn's system
prompt and was not in `conversation_history`, so a follow-up such as "why was set 3 at RPE 9?" saw the earlier
reply but not the session record.

Fork was: (a) leave as briefed (one turn); (b) `ChatPanel` keeps the focus for the conversation and re-sends it
with every subsequent turn until the conversation is cleared or a new review replaces it (cost: one DB read per
turn); (c) the server re-pins from a focus id echoed back in the response.

**State:** DONE → #354. **RULED (operator, 30 Sep): option (b).** The frontend holds `focus_session` and resends it
on every turn until a new focus is set or the chat is cleared/new. Built with a dismissible "Reviewing: ..." chip
and a "New chat" control, since the panel had no way to clear a chat.

---

## Q204. Activity type: Garmin "Trail Running" arrives through Health Connect as a code, not a label

Raised with #365. Verified against master `054d2d9`.

**Question.** How does Garmin "Trail Running" map through Health Connect into the app's session type and the metabolic load window? Does it differ from "Running"?

**Findings.**
- **The label does not survive Health Connect.** HC's exercise enum has no trail-running member; the running members are `RUNNING` (56), `RUNNING_TREADMILL` (57) and `HIKING` (37) (`routers/health_connect.py:66-127`). `sport_name` is derived from the integer `type` alone (`:130-145`, written at `:758`). `title` is accepted (`:238`) and then dropped: it is not among the stored fields (`:753-762`). Which code Garmin writes for a trail run is not known from master (Guessing: 56, stored as "Running"); the row's `sport_id` settles it.
- **Effect on the metabolic load window: none.** The transform scores zone seconds and uses `sport_name` only as provenance (`load_events_metabolic.py:216-222`), and there is no sport exclusion (#322 S2). "Running", "Running Treadmill" and "Hiking" deposit identically when zoned.
- **Effect on string-matching consumers.** `device_sports` matching is exact and casefolded (`engine/resolver.py:394-405`), so a slot declaring "Running" does not claim "Running Treadmill" or "Hiking". `NON_TRAINING_SPORTS` is Walking, Pilates, Yoga and Stretching only (`sport_classes.py:27`). A NULL sport is reported as `unclaimed_session` with detail `no_sport` (`engine/resolver.py:394-397`).
- **Polar side.** `SPORT_NAMES` has no "Jogging" (`import_polar.py:31-52`); a sport id outside the map stores `sport_name` NULL with the id retained (`:105-106`). The id on the 1 Oct Polar row is unread. Arbitration ignores sport, so dedup is unaffected.

**Gap.** There is no trail/road distinction in the app, the same activity carries a different name by source, and the operator's own label is lost at ingest.

**To decide (Luke).** (a) Accept it, since load is unaffected, and declare every running name a slot should claim. (b) Persist `title` on `aerobic_sessions`, which is a schema migration and so a hold under § Merge disposition. (c) Add a source-neutral activity class above `sport_name` for the string-matching consumers.

**Live check (owed, operator):** the first query in Q201 returns `sport_id`, `sport_name` and `source_package` for both rows of the 1 Oct run.

**Resolution (3 Oct 2026).** The live check was read by the operator on 2 Oct (operator-reported; Code has no DB route). Garmin "Trail Running" arrives through Health Connect as sport 56, so it is stored "Running": row 93, `health_connect`, Garmin package, `sport_id` 56, `sport_name` "Running", `hr_avg` 145, zoned (`z1_seconds` 30). That settles the Guessing above. The activity title is dropped at ingest (`routers/health_connect.py:238` accepts it; the stored fields at `:753-762` omit it), so the operator's "Trail Running" label is not kept. There is no load effect: the metabolic transform scores zone seconds and uses `sport_name` as provenance only, with no sport exclusion (#322 S2). Option (a) is taken: accept the loss and declare every running name a slot should claim; options (b) (persist `title`, a schema migration) and (c) (a source-neutral activity class) are not pursued. The Polar half of the finding ("`SPORT_NAMES` has no Jogging") was a wrong-table defect, not a gap: the whole Polar map was replaced from the Polar Flow list (#366).

**State:** `DONE → #366`.

---

## Q207. Which writer owns sessions 68, 69, 71, 80-85 and 92, and why did Garmin write no activity HR for them?

Raised 3 Oct 2026 with #367 from the Q206 gap-distribution read. Report-only: nothing is built and nothing is proposed. **Operator-reported, not read by Code:** across the 30 most recent HC sessions, sessions 68, 69, 71, 80-85 and 92 contain only Garmin passive HR samples (120 s apart), and they are the `no_same_writer_hr` rows. `com.sec.android.app.shealth` writes 10 s samples on 79-83.

**What the code says the reason means.** `hr_zones.zone()` returns `no_same_writer_hr` only when there are no plausible same-writer samples inside `[start, stop]` (`hr_zones.py:112-114`); a writer with passive 120 s samples inside the window would return `sparse` (coverage about 0.5 against 0.6, `:130`). So a row reported as `no_same_writer_hr` with only Garmin passive samples around it is a row whose session writer is not the writer of those samples, or whose window holds none of them. Which of those it is has not been read.

**Question.** For each of these sessions, which package wrote the exercise record (`aerobic_sessions.source_package`), which packages wrote HR inside its window, and why did the Garmin watch write no activity-rate HR for it? Guessing, to be tested not assumed: (i) the exercise record's writer is not Garmin (Samsung Health on 79-83 is the obvious candidate); (ii) the writer is Garmin but the session is shorter than the passive interval, so no sample falls inside it; (iii) Garmin recorded the activity but its activity HR never reached Health Connect.

**First read (owed, operator).** One row per session and HR writer, with zero HR rows showing as a NULL `hr_pkg`. Parser-checked with `pglast` and against `SCHEMA.md`; not run:

    WITH s AS (SELECT id AS sid, user_id, source_package AS session_pkg, sport_name, start_time AS st, stop_time AS sp, round(duration_minutes::numeric, 1) AS dur_min FROM aerobic_sessions WHERE user_id = 1 AND id IN (68, 69, 71, 80, 81, 82, 83, 84, 85, 92)), g AS (SELECT s.sid, h.source_package AS hr_pkg, h.sample_time, h.sample_time - lag(h.sample_time) OVER (PARTITION BY s.sid, h.source_package ORDER BY h.sample_time) AS gap FROM s JOIN hr_samples h ON h.user_id = s.user_id AND h.sample_time BETWEEN s.st AND s.sp) SELECT s.sid, s.session_pkg, s.sport_name, s.dur_min, g.hr_pkg, count(g.sample_time) AS n_samples, round(extract(epoch FROM percentile_cont(0.5) WITHIN GROUP (ORDER BY g.gap))::numeric, 1) AS median_gap_s FROM s LEFT JOIN g ON g.sid = s.sid GROUP BY s.sid, s.session_pkg, s.sport_name, s.dur_min, g.hr_pkg ORDER BY s.sid, g.hr_pkg;

**Findings (3 Oct 2026).** Report-only; nothing is built. **Operator-reported, not read by Code:** the loss is located for the Pilates session (53:45, average about 100 bpm). Garmin Connect holds the full wrist HR; Health Connect holds Garmin HR for the same span at about 5 records a minute; the app's `hr_samples` holds only the Garmin passive 120 s rows there. The loss is HC to app. Code read both repos: this one on master `3b275c1`, and the companion `health-connect-app` at `0c2f982` (24 Sep; shallow, read-only). The phone runs whichever build the operator installed, and `health_connect_sync_events.git_sha` names it; that was not read.

**(1) Does the sync re-read HR for past windows? Yes, to a fixed depth. It is not read once at arrival.**
- *Phone.* `fetchAllData(days)` reads the whole window, `daysAgo(days)` to now, for every stream on every sync, with no cursor and no last-sync state (`src/healthConnect.js:418-444`, `daysAgo` at `:91-96`). The windows are 7 days for the background task (`src/backgroundSync.js:52`) and for the manual button (`src/SyncScreen.js:268`), and 30 days for the second manual button (`:278`). HR is read as `HeartRate` records with every sample flattened (`healthConnect.js:252-255`), paged at 1000 and ascending, capped at 100 pages (`src/fetchMeta.js:8-15`). A mapper that kept one sample per record is ruled out for that commit.
- *Server.* It stores any sample time, with no bound from the sync window, and an existing sample is left alone (`routers/health_connect.py:577-632`; `periodDays` bounds only the daily aggregation, `:1113`, `:1192`). `hc_zone_enrich` recomputes every HC row from stored samples on every chain run (`hc_zone_enrich.py:12-14`, `:64-68`), and `zone_session` withholds a row below coverage 0.6 (`hr_zones.py:43`, `:129-130`). So "defer zoning until coverage reaches 0.6" is already the server's behaviour: a row stays zoneless until enough samples arrive, then fills.
- *So the lead hypothesis is half right.* HR that Garmin writes to HC after the exercise record is re-read, but only for 7 days (30 by the manual button). An in-activity write later than that is never re-posted.
- *The loss is upstream of this server's storage, not a persistence defect.* Q198 (operator, 1 Oct) read `health_connect_record_sources`, which has captured one row per POSTed HR sample time since before `hr_samples` existed, and already recorded rows 69, 85 and 92 as passive 120 s only. The in-activity samples were not in the POSTs the server received, and the `hr_samples` result repeats that.
- *What is not known:* when Garmin wrote those samples to HC. Q159 recorded in-activity HR arriving about 6 days behind the workout's sync (the HCA Q22 finding, user 4), one day inside the 7-day window. #364 set that blocker aside because "the newest HR sample is 0.0-7.6 h old at each POST". That measures the freshest sample of the stream, which passive sampling refreshes constantly, and it cannot see how late in-activity HR is. So #364's dismissal does not rule the lag out, and this case is the one it would have caught (Likely; no decision changes, #364 is append-only).

**(2) Can a back-window re-sync recover 69, 85 and 92 from the phone's Health Connect store?** Probably, if they are within 30 days; it is untested.
- *Mechanism.* The 30-day button re-reads 30 days, and a `periodDays=30` POST is on record (Q198). The server inserts what arrives and the next chain run re-zones each row. Nothing re-reads beyond 30 days: there is no control for it. The start dates of 69, 85 and 92 were not read here; if any is older than 30 days at the time of the sync, the app cannot fetch it (Guessing: 69 is the oldest of the three, by id order).
- *HC side, unverified.* Whether HC still serves the older records. The manifest declares `READ_HEALTH_DATA_IN_BACKGROUND` and no history permission (`android/app/src/main/AndroidManifest.xml:18`). Guessing: without it, HC limits an app to 30 days before its first grant, which a 30-day window would not hit.
- *The test that answers it (operator).* Press the 30-day sync, then re-run the first read above. In-activity samples appearing for those rows means they were written to HC later than the re-read window. Samples still absent while HC holds them means the phone's read path is at fault, not lateness; the next read is then `health_connect_sync_events.fetch_meta -> 'heartRate'` (`truncated`, `pages`, `oldestAt`) for the POSTs after the session.

**(3) Design note for the fix. No build; Luke rules.**
- *What constrains it.* The server already defers zoning, so the gap is only the phone's fixed window. The server knows which rows are starved (`sparse` and `no_same_writer_hr` in the `hc_zone_enrich` return dict) and never tells the phone. Nothing stored before `hr_samples` records lateness; `hr_samples.created_at` is the arrival time, insert-once, so it measures lateness for every session recorded after the #364 deploy (the deploy date was not read here). For sessions before it, `created_at` is the first sync after the deploy, which is meaningless as a lag.
- *Option A: widen the scheduled window,* `days` 7 to 30 at `backgroundSync.js:52`. One line, a phone release only, no server change. It costs about 4 times the HR payload per scheduled sync, and every POST re-runs `_capture_record_sources`, which loads all of the user's existing keys (`routers/health_connect.py:544-549`) and grows with the table. The depth is still fixed, so a lag longer than the window recurs.
- *Option B: a targeted re-read.* The server names its unzoned HC session windows within N days (the sync response or a GET; no schema) and the phone re-reads HR for just those windows until covered or N days pass. It closes the gap for any lag inside N with a bounded payload, but it is a cross-repo contract change, and the server read must soft-fail.
- *Option C: measure first.* Read the lateness distribution on the next non-GPS Garmin sessions with the second query below, then size A from data.
- *Code's lean, not a ruling:* C, then A if the lag is bounded (under about 14 days), because A is one line and reversible; B only if the lag is unbounded or A's payload shows up as a cost. Whatever is chosen, a starved row is silent today (Q202, Q203), so making absence visible stands apart from recovering it.

**What this does not settle.** The located case covers the Pilates rows. Q198 already attributes 68 and 84 to Samsung exercise rows with no same-writer HR (the Samsung HR stream ends 14 Sep), and notes the Samsung HR on 79-83 starts about 3.5 minutes after the walk's start. Rows 71 and 80-83 are not accounted for by the located case. The first read, which prints each session's own writer beside the HR writers in its window, covers them.

**Second read, the lateness instrument (owed, operator; useful for sessions after the #364 deploy).** One row per HC session and HR writer among the 30 most recent, with the hours from the session's end to the first arrival of that writer's HR. Parser-checked with `pglast` and against `SCHEMA.md`; not run:

    WITH s AS (SELECT id AS sid, user_id, source_package AS session_pkg, start_time AS st, stop_time AS sp FROM aerobic_sessions WHERE user_id = 1 AND source = 'health_connect' ORDER BY start_time DESC LIMIT 30) SELECT s.sid, s.st, s.session_pkg, h.source_package AS hr_pkg, count(h.id) AS n_samples, min(h.created_at) AS first_arrived, round(extract(epoch FROM (min(h.created_at) - s.sp)) / 3600.0, 1) AS first_arrival_lag_h FROM s LEFT JOIN hr_samples h ON h.user_id = s.user_id AND h.sample_time BETWEEN s.st AND s.sp GROUP BY s.sid, s.st, s.sp, s.session_pkg, h.source_package ORDER BY s.sid, h.source_package;

**Resolution (4 Oct 2026, #369).** No app-side loss. The operator's reads show two causes: Garmin writes in-activity HR to Health Connect about 7 days after the session, and the scheduled sync was failing with "Health Connect client is not initialized" and reading nothing (#370). The 26 Sep Pilates is sid 86: its 241 Garmin samples reached `hr_samples` only after the 7-day manual sync at 13:47Z on 3 Oct, and were absent after the 30-day manual sync at 03:33Z. Rows 85 and 92 are the 22 and 29 Sep retrospective entries; no HR exists for them in any store, so they are correctly unzoned. The Findings above named the phone's fixed re-read window or a read-path fault; the reads show the window mattered only because Garmin's export lag is about its length, and no read-path fault was found. Sid 69 was not individually read. Rows 71 and 80-83 are accounted for earlier (a history gap in `hr_samples`, filled by the 30-day sync) and 68 and 84 in Q198 (Samsung HR ended 14 Sep). Q159 is reopened with the measured lag.

**State:** `DONE → #369`.

---

## Q209. Per-session sRPE capture at session save

Raised 4 Oct 2026 with the Q202 sRPE-floor brief. The brief's S1 found n = 2 paired days (Q202); the operator confirmed the cause: the bedtime check-in (`POST /pm`, one `daily_records.session_rpe` per day, overwritten on re-save, `routers/checkin_v2.py:758`) is the only RPE surface and is often skipped. Capture has to happen at session save, per session, and the value has to be an immutable snapshot at capture: a later revision must not change what a derived event was computed from (a delete-and-reinsert transform follows the live column, `load_events_metabolic.py:180-185`).

**Paths.** (a) Garmin self-evaluation (perceived effort, feel) read from Garmin Connect for watch sessions. This reopens the 1 Oct "no client built" position (Q198 inventory table), scoped to a read-only activity read; the ruling follows the probe below. (b) A companion-app notification on Polar session arrival, for H10-only sessions (companion repo, out of this tree). (c) Hevy set RPE, unchanged.

**Library fact (Code, `garminconnect==0.3.11`).** No named self-evaluation field exists, but `get_activity` and `get_activities` return Garmin's JSON unmodelled and the typed `Activity` model allows extra keys (`typed.py:77-80,396-458`), so a field Garmin sends is not dropped. The library has no RPE setter (`__init__.py:2376-2404` set name, type and description only). Operator-reported external evidence: a third-party MCP server on `python-garminconnect` exposes "perceived effort" and "feel" write tools on activities, so the fields exist; their key names and scale are unconfirmed.

**Probe status.** `scripts/garmin_selfeval_probe.py` (PR #307) is read-only: two GET requests through #361's no-refresh seam, printing only keys whose name matches `rpe|feel|eval`. **OWED (operator):** rate one recent activity in Garmin Connect, open the app's Garmin card (it refreshes and saves the token), then run the probe with that activity's `--activity-id`. A negative on an unrated activity proves nothing (FEEDBACK §17); a hit on the known rating gives the key and the scale.

**Reopened fork (4 Oct 2026, operator; a note, not a decision).** The 1 Oct position is reopened for a read-only activity read: self-evaluation now, in-activity HR as a Q159 candidate. The ruling follows the probe.

**To decide (Luke).** After the probe: whether (a) is built and where its value is stored as an immutable snapshot (a schema change, held for review when it comes); whether (b) is briefed to the companion repo; and how Q202's floor and Q189 use a per-session value. No kappa fit is possible until paired data exists.

**Resolution (4 Oct 2026, #372).** Path (a) is built and closed here. The probe ran (operator-reported): `summaryDTO.directWorkoutRpe` 40 and `directWorkoutFeel` 25 for activity 24564069469, which the operator rated 4/10 and "Weak". RPE is 0-100 in steps of 10 (CR-10 x 10); feel is 0/25/50/75/100; both are on the activity detail, not the list. The 1 Oct "no client built" position (Q198) is superseded for a read-only self-evaluation read only. The value is stored in an insert-only, capture-timed table linked to the Health Connect row (SCHEMA §042), read inside the Garmin sweep after its token refresh (#372). Landed via PR #309 (merge `bd92191`), released by the operator on 4 Oct 2026; the first live run is owed (ROADMAP NOW). Path (b), a companion-app notification on Polar session arrival, is NOT decided here: H10-only sessions (no Garmin activity) have no captured rating, and the question stays a note on Q189. How Q202's floor and Q189 use a per-session value is not decided; the input now exists for watch sessions once the first live run has captured a rated activity.

**State:** `DONE → #372`.

---

## Q210. Several metabolic `load_window` slots with disjoint sport filters in one sub-cycle: a supported shape?

Raised 4 Oct 2026 (operator, from the first real phase-change save). The phase needs run, speed, VO2 and aerobic work counted separately.

**Verified on master `c6bae6c`.**
- **Refused today.** `validate_microcycle` allows one slot per `load_window` per sub-cycle, and the only load window is `metabolic`: a second raises "duplicate load_window 'metabolic' within this sub-cycle" (pinned in `tests/test_phase_transition_order.py`). The form now refuses it at step 4 (PR #311).
- **Slot identity is `(kind, key)`.** `schedule_item.satisfies` is `{kind: key}`; `consistency_rows` (`engine/week_plan.py`) matches on it, and `_actuals_by_day` attributes each counted session to its `(kind, key)`. Two metabolic slots would share one identity, so an item satisfying `metabolic` would count against both. Likely the reason the duplicate rule exists; #307's text states the rule, not this reason.
- **The resolver already expects several.** #315's claim order: exclusions first; `activity` slots claim by sport in declared order; "the remainder -> sport-scoped `load_window` slots in declared order"; one session claims at most one slot.
- **An existing alternative.** An `activity` slot (#315) is one per activity name (casefolded), each with its own `device_sports`, counted separately. #315 says it "deposits NO load by virtue of the slot (counted sessions carry no `trimp`)".
- **Not examined before.** #307 rejected a `sport_name` filter as out of scope (revisit at preseason) and #315 then added `device_sports` scoping; no decision considered several `load_window` slots with disjoint filters.

**Options (not decided).** (a) Keep the shape: one `metabolic` slot plus one `activity` slot per sport group (run, speed, VO2, aerobic), counted separately today. (b) Allow several `load_window` slots, each given a slot name besides the window: an identity extension through the validator, the resolver's `Slot`, `satisfies`, `consistency_rows`, `_actuals_by_day`, the form and the coach write-shape docs. (c) Something else.

**To decide (Luke).** Which option; and what "counted separately" must mean for load, in particular whether a run slot's sessions need to differ from an activity slot's in what the plan reads as load.

**Correction (4 Oct 2026, Code).** The facts above omit what the claim does to an aggregate slot, and the option (a) line understated it. The claim is exclusive and ordered: activity slots claim first and one session claims at most one slot, so an aggregate metabolic slot counts only the REMAINDER (a run and a bike claimed first leave 1 of 3). Load is unaffected: the load transform never reads a slot, so all three sessions deposit load (3 events of 50.0 in the check, since pinned by `tests/test_slot_claim_vs_load.py`). The form's "never deposits load" wording was misleading and is corrected (PR #315).

**Resolution (4 Oct 2026, #376).** Option (a), ruled by the operator: per-category counts through activity slots (they claim first); one metabolic `load_window` slot sized to the remainder; load accrues for every device session whichever slot counts it. No validator or resolver change; (b) is not built.

**State:** `DONE → #376`.

---

## Q211. Direct "Open a new phase" creates a phase with no microcycle: should it require one, carry the prior one, or warn on save?

Raised 5 Oct 2026 (operator, from the 4 Oct real use). Advanced -> "Open a new phase" opened `aerobic base` with a name, posture, capacities and a review date and no microcycle, so it had no quota; only Review / change phase walks the quota step. The operator fixed it by re-running Review / change. Filed as a design question, not a defect fix.

**Verified on master `21839a4`.**
- **The backend allows it by design.** `validate_training_phase` treats `microcycle` and `capacities` as optional (`engine/training_phase.py:280-297`), and `PhaseIn.microcycle` defaults to None (`routers/training_phase.py:55`). `POST /engine/phase` calls `open_phase` with no quota step (`:69-81`).
- **The form sends one only if asked.** `PhaseForm.jsx` adds `microcycle` to the body only when the Advanced JSON box is filled (`if (micro.value !== undefined)`).
- **What a no-microcycle phase does.** The resolver falls back to the weekly template (`tests/test_resolver.py:272`, `window.source == "weekly"`), or a null window with no template. So the quota silently becomes the weekly one; nothing says so.
- **It does close the prior phase.** Direct open and the wizard both go through `_apply_open_phase`, which sets `closed_on = new.entered_on` and a reason on the open row in the same transaction (`engine/training_phase.py:428-436`; pinned by `test_opening_a_second_closes_the_first_in_one_txn`, `tests/test_training_phase.py:134`). So by the code the direct open did NOT fail to close decompression. The empty history on 4 Oct was the read-shape bug (#314), not a missing closure. **What prod holds is not read** (Code has no database access); the read is owed, ROADMAP row 39.
- **The wizard already has a "carry" form:** it prefills every slot from the outgoing microcycle, each editable, none silently applied (`PhaseTransitionFlow.jsx:125`).
- **The direct path is kept on purpose, for now.** `PhaseCard.jsx:15-17`: it stays mounted "until the 8-step flow has completed one real transition in prod" and is to be removed in a later PR "once the flow is confirmed". By the operator's 4 Oct report that condition is met (a real transition was saved through the wizard), so option (d) is the removal the code already plans. That is not a ruling.

**Options (not decided).** (a) Require a microcycle on direct open (422 without). Forbids a state the resolver's weekly fallback exists to serve. (b) Carry the prior phase's microcycle onto the new row at direct open. The new phase silently inherits the old phase's quota, the same stale-default shape as Q212. (c) Warn on save and keep allowing none; the warning names the weekly fallback. (d) Remove the direct path and leave the wizard as the one way in; this loses the escape hatch and the review-date-only phase.

**To decide (Luke).** Which option. Code's lean, not a ruling: (c), because a phase with no microcycle is a state the resolver supports, and (b) is a silent default. (d) needs no new design, since the comment above already schedules it; the cost is the escape hatch.

**Resolution (5 Oct 2026, #378).** Option (d), ruled by the operator: the direct-open path is to be removed and Review / change phase is the only phase-entry route. Recorded now; the build is not scheduled. Open, for the build brief: the backend route (its only non-test caller in the tree is `PhaseForm.jsx:98`), the direct close path, and what the wizard can express (#378).

**State:** `DONE → #378`.

---

## Q215. Same-day phase corrections leave zero-length rows and misplace close reasons: mark them, supersede in place, or leave the ledger as it is?

Raised 5 Oct 2026 (operator, once the history card rendered, #314). **Operator-reported, not read by Code:** the ledger shows two zero-length rows from the 4 Oct wizard retries, "decompression 2026-10-04 → 2026-10-04" and "Aerobic base 2026-10-04 → 2026-10-04", and the zero-length "Aerobic base" row carries the close reason "decompression completed its job". The true sequence, per the operator: decompression 09-07 → 09-21, decompression 09-21 → 10-04, Aerobic base 10-04 → open. Filed as a design question; nothing is built until ruled.

**Verified on master `1dc8bed`.**
- **The ledger is append-only, by model and application invariant, with no database enforcement.** `models.TrainingPhase` says the only UPDATE is `closed_on` and `close_reason` at closure, "model+application invariant, no DB trigger", and that rows are INSERTed, never upserted. The write sites are three: the closure and the insert in `_apply_open_phase` (`engine/training_phase.py:428-437`) and `close_phase` (`:464-465`). No DELETE of a phase row exists outside tests and migrations. `test_closure_updates_only_closure_columns` pins it.
- **Zero-length rows are #317's ruled behaviour.** "Same-day correction is PERMITTED": a second different transition with `entered_on == today` "closes the just-opened phase same-day and opens the corrected one", pinned by `test_same_day_correction_yields_one_open_phase`. The ledger worked as ruled; the artefacts are that ruling's cost.
- **Reproduced (a scratch test, run and deleted, not committed).** A wizard revise, a direct open and a wizard Move, all on one day on top of two earlier decompression rows, give exactly the operator's ledger: two zero-length rows (the interim decompression row and the directly-opened aerobic base row), and the Move's note, "decompression completed its job", lands on the zero-length aerobic base row. The interim decompression row carries the default "opened Aerobic base".
- **Phase-aware readers exclude them.** Everything that reads the open phase (`current_training_phase`: the engine, the resolver, `current_state`, the MCP read, the wizard draft) never sees a closed row. `phase_at` (half-open, `entered_on <= d < closed_on`) cannot return a zero-length row; the scratch run returned the 09-21 row for the day before and the open row for today. **No test pins the zero-length case** (the existing test pins the boundary), and `phase_at` has no non-test caller today, so nothing phase-aware reads history yet. The chart overlay (`PhaseMarkers.jsx`) reads every row but collapses boundaries that snap to one category, so a zero-length row adds no line. The history card (`PhaseHistory.jsx`) shows every row verbatim and is the only surface where they appear.
- **Why the reason lands where it does.** The wizard asks "did the block you are closing do its job" and says the note "becomes its close reason" (`PhaseTransitionFlow.jsx:56`, `:286-288`); the save writes `close_prior_reason` onto the row open at save time (`engine/training_phase.py:429-434`). The ledger's unit is the row (one per write); the wizard's is the block (one per intent). They coincide until a block has more than one row, as on 4 Oct, when the open row was a direct-open artefact and not the block the note described.
- **#378 would have halved it.** Without the direct open, a revise then a Move gives one zero-length row (decompression), and the note lands on it correctly. The remaining artefact needs only a second same-day transition, which #317 permits.

**Options (not decided).**
- *The zero-length rows.* (a) Leave them: derivable (`closed_on = entered_on`), excluded from every reader by construction, shown honestly; the cost is noise on the card. (b) A derived marker, no schema: the history route returns a computed flag for a row with no day of its own, and the card collapses or labels it "same-day, superseded". No mutation, no migration; it also covers a deliberate open-then-close on one day, which is equally never in force. (c) A stored marker, a nullable `superseded_by` (the same-day successor's id) or `voided_on`: a migration, HOLD, and a second permitted UPDATE that amends the closure-only invariant; it can mark a mistaken row that lasted days, which (b) cannot. (d) Delete: ruled out by append-only, and by the operator's own "rather than deletion".
- *Same-day correction (#317's mechanism).* (i) Append, as today. (ii) Supersede in place by updating the same-day open row: it breaks "never edited after authorship except closure" and loses what was first authored. (iii) Append plus a marker from (b) or (c). (ii) reads as the weakest: it trades the invariant for tidiness.
- *The close reasons.* (1) Skip the block-verdict review when the open row was entered today (a correction, not a block ending). (2) Name the row the save will close (label, entered date, how it was opened) beside the notes box. (3) Accept: a reason belongs to the row, and the (b) label shows it is not a block verdict. A close reason already set cannot be moved to another row without a second UPDATE.

**To decide (Luke).** Which of the above. Code's lean, not a ruling: keep appending (i); (b) for the markers; (1) for the reasons; (c) only if a mistaken multi-day row ever needs voiding; and a tests-only PR pinning the zero-length exclusion whichever is ruled.

**Resolution (5 Oct 2026, #379).** The operator adopted Code's lean: same-day correction keeps appending (#317 stands); a derived flag on the history route for zero-length rows, which the card collapses or labels (no schema, no migration, no deletion); the wizard skips the "did the block do its job" review when the open row was entered today and names the row the save will close; and a tests-only pin of the zero-length exclusion in `phase_at` and the open-phase readers. Recorded now; the build is not scheduled and may share one brief with #378.

**State:** `DONE → #379`.

---
