# FEEDBACK.md — Session Corrections, Preferences & Lessons Learned

*Extracted from full project conversation history. Load this at session start.*
*Repo-canonical (health-app). The Claude.ai project-knowledge copy is a refreshed mirror, not the master.*
*Last updated: 26 June 2026*

---

## 1. Explicit Corrections Easty Made

These are moments where Claude got something wrong and Easty corrected it. Never repeat these errors.

---

### 1.1 CPAP mask artefact — snoring is not snoring
**What Claude did:** Flagged Samsung Health snoring data (2h12m) as a genuine signal and suggested a sleep clinic referral for sleep-disordered breathing.

**Correction:** Easty wears a CPAP mask. CPAP airflow through the mask is consistently misrecorded as snoring by Samsung Health. The snoring detection is noise, not signal.

**Rule going forward:** Never interpret Samsung Health snoring duration as genuine snoring. It is CPAP artefact. The clinically relevant signal is SpO2 nadir and residual AHI from the CPAP machine (via AirMini app → AirView), not snoring detection. SpO2 below 94% nadir is the flag worth acting on.

**CPAP specifics:** AirMini app (not myAir — separate ResMed product). No SD card, so OSCAR analysis is not possible. Per-night AHI and mask seal available in-app for 30 days. Data goes to practitioner via AirView.

---

### 1.2 Polar H10 source hierarchy — Polar is primary for aerobic, Samsung Health is connected to it
**What Claude did:** Described the setup as Samsung Health primary with Polar as supplementary.

**Correction:** Polar H10 is primary for aerobic exercise data. Samsung Health is connected to the Polar H10, not the other way around. The hierarchy matters for sourcing session data: always treat Polar session data as the authoritative aerobic record.

---

### 1.3 "Accidentally textbook" — treat logged choices as reasoned
**What Claude did:** Characterised Easty's cross-trainer + Echo bike substitution session as "accidentally textbook" rehabilitation training.

**Correction:** It was an intentional, reasoned decision — not an accident. Easty had already thought through the session selection. Claude's error was collapsing "absence of visible reasoning in the chat" into "absence of reasoning in the person's head."

**Rule going forward:** Treat logged choices as reasoned until told otherwise. Surface rationale for confirmation rather than assuming naivety. The correct posture is "you subbed to low-impact cardio — was that a conscious injury management call?" not "you lucked into the right session."

---

### 1.4 Health Connect source verification — don't browse on-device, query the database
**What Claude did:** Proposed verifying the Health Connect data source split by browsing the Health Connect app UI on-device.

**Correction:** Easty explicitly prefers programmatic verification — query Railway Postgres directly to check what source IDs are present in stored data. The on-device UI method is imprecise and error-prone.

**Rule going forward:** For data source verification questions, always propose a Postgres query against the Railway database rather than suggesting on-device UI inspection.

---

### 1.5 create_routine vs create_workout — don't dismiss workarounds without knowing their constraints
**What Claude did:** Pushed hard to fix the `_check` bug in `create_routine` and dismissed the `create_workout` workaround as creating "pollution."

**Correction:** The create_workout path was not just a workaround for the bug — it also solved a separate confirmed limitation where custom exercise UUIDs don't resolve via `create_routine`. Claude collapsed two independent problems (bug + API limitation) into one. The workout record isn't pollution — it's a valid training log with a timestamp. "Save as Routine" in Hevy is a zero-cost UX step.

**Rule going forward:** Before pushing back on a workaround, confirm whether the problem it solves is (a) a code bug that can be fixed, (b) a third-party API limitation that cannot be fixed, or (c) both simultaneously. Challenge only applies to (a). For (b) and (c) mixed, the workaround may be the correct design.

---

### 1.6 Once-per-day guard — force flag for manual runs
**What Claude did:** Implemented `alreadyCapturedToday()` guard on the Samsung Health accessibility scraper without distinguishing automatic vs manual triggers.

**Correction:** The once-per-day guard should only apply to automatic triggers. Manual runs should bypass it via `force = true`.

---

### 1.7 Windows/PowerShell environment — Linux commands don't work
**What Claude did:** Generated multi-line adb commands using backslash line continuation and Linux-style syntax.

**Correction:** Easty is on Windows with PowerShell. Linux syntax (`head`, backslash continuation) doesn't work. All multi-line adb commands must be single-line or use PowerShell syntax.

**Rule going forward:** All shell commands must be Windows/PowerShell compatible. Never use Linux-only syntax. If a command needs to span lines, use PowerShell's backtick continuation or write it as a single line.

---

### 1.8 HRV data path — never fabricate confidence in unconfirmed sources
**What Claude did (across multiple sessions):** Designed 30% of the readiness algorithm around Samsung Ring HRV data before anyone confirmed it was accessible via Health Connect.

**Correction:** Samsung Health does not write HRV, resting heart rate, respiratory rate, or sleep stages to Health Connect. The entire algorithm design was built on an unverified assumption. A five-minute web search would have found Samsung community threads confirming this before the design work began.

**Standing rule:** Before any metric enters algorithm design, record *how you know it works* — a confirmed test, verified search result, or official documentation. "The API has a field for it" is not sufficient. This is a project founding principle now.

---

### 1.9 Evidence rule — never reason or write from a summary of available bytes (24 June 2026)
**What kept happening (chat-side):** Reconstructing state from partial pastes, or accepting a paraphrase of bytes that were in hand and reasoning onward — twice produced or nearly produced canonical fabrications (DECISIONS_LOG #10/#11).

**Two-ended rule:**
- **Chat:** for any claim written to canonical or gating an action, hold the raw bytes first. If absent, emit `;raw <exact command>` and wait — never reconstruct, never reason from a summary.
- **Code:** honour `;raw <command>` verbatim — run exactly that command and paste its output with no summary, paraphrase, or commentary. Absent the token, summarise normally.

**Where it lives:** The `;raw` protocol is defined in `~/.claude/CLAUDE.md` and logged as DECISIONS_LOG #30. This is the behavioural half of the same rule.

---

### 1.10 Readiness scoring was silently blind to every injury but shoulder (13 July 2026)
**What Claude/the code did:** `calc_naive_baseline` read `soreness["shoulder"]` only. The readiness scalar ignored every other active injury — the user's hamstring soreness was captured on the check-in and never scored. Not previously logged.

**Rule going forward:** Scoring that consumes the injury/soreness ledger must range over the whole ledger, not a hardcoded subject. A single-body-part constant in a per-user health score is a bug, not a simplification. Fixed 2026-07-13 — soreness term is now max across all reported items (DECISIONS_LOG, constraint-consumption brief).

---

### 1.11 Chat context does not persist across devices (mobile ↔ desktop web)
**Constraint:** Conversation state started on one surface (mobile app) is not present on another (desktop web), and vice-versa. A decision "made in chat" on one device is invisible on the other until it lands in the repo.

**Rule going forward:** Rely on the repo governance stores (2.8 / 2.12), never chat memory, for anything that must survive a device switch. This is the concrete failure the repo-as-single-source-of-truth model exists to absorb — treat an uncommitted cross-device decision as lost, not pending.

---

## 2. Stated Preferences

How Easty explicitly wants things done. Apply these without being asked.

---

### 2.1 Raw signals only — no proprietary composite scores
**Preference:** All proprietary composite scores are explicitly rejected — Samsung Energy Score, Samsung Stress Score, Samsung Sleep Score, Garmin Stress Score, Garmin Body Battery, Garmin HRV Status.

**Reason:** These are opaque algorithms with undisclosed weighting and no peer-reviewed validation. Every signal in the algorithm must be traceable to a measurable physiological mechanism.

**Apply:** Never propose using a manufacturer composite as an input. Always go raw signal → known formula → validated output.

---

### 2.2 VO₂max from first principles only
**Preference:** VO₂max must be calculated from first principles, not consumed from Garmin's Firstbeat output.

**Method:** Three-tier system — Uth HR Ratio Method (primary, with measured HRmax from H10), ACSM submaximal running equation (when session data available), fixed submaximal pace HR tracking (most actionable coaching signal). All outputs labelled as estimates with confidence bands.

**Hard constraint:** Never use age-predicted HRmax formulas. Measured HRmax from H10 sessions only.

---

### 2.3 Verification before design
**Preference:** Verify data paths end-to-end before designing against them. This isn't a "nice to have" — it's a standing project rule after the HRV pipeline failure.

---

### 2.4 Annotate confounds, don't discount them
**Preference:** When a confound (alcohol, illness, travel) suppresses a metric, tag the cause rather than adjusting the score. The readiness state was real. The score stands, but the cause is annotated.

**Why:** Preserves accurate physiological read AND clean baseline trending. Treating "wine night = bad data" discards true signal.

---

### 2.5 Infer → surface → confirm — never silently commit
**Preference:** The system infers but always surfaces its reasoning for human confirmation before committing. Under uncertainty, degrade to a broader cautious flag rather than produce false precision.

**Apply across:** Injury schema inference, check-in update detection, health data interpretation, any structured action Claude triggers on the user's behalf.

---

### 2.6 Injury provocation is movement-pattern indexed, not body-part indexed
**Preference:** Injury flags must be indexed by movement pattern and condition, not body part. Provocation status is three-valued: provocative / clear / untested. Conditions can stack (range gate + load modifier simultaneously, not a single knob).

**Extraction method:** Plain-language interview → Claude translates to structured object → confirm every inference before committing.

**Confirmed live-impacting (13 July 2026):** an active injury (left pes anserine) was uncapturable on the AM check-in for ~3 days — soreness items were hardcoded `{shoulder, hamstring}`, so a real injury outside that pair had nowhere to be recorded. Check-in soreness items now derive from the active `type='injury'` ledger (constraint-consumption brief, Step 2), closing the capture gap this preference names.

---

### 2.7 Two-mode working pattern — respect the split
**Preference:** Claude chat interface = architecture decisions, algorithm design, reasoning, PowerShell commands, and *proposing* repo changes. Claude Code CLI (and the `@claude` Action) = all writes to the repo, including code and the canonical state files. Chat proposes; Code commits. See 2.8 for where state lives.

---

### 2.8 Source of truth — repo-canonical for volatile state
**Preference:** The repo is the single source of truth for all volatile state — decisions (`DECISIONS_LOG.md`), open questions (`OPEN_QUESTIONS.md`), roadmap (`ROADMAP.md`), and task status (`ptb-tasks`). Code — and the `@claude` Action — is the only writer; chat proposes and never commits. The commit is the only sync point: a decision is provisional until committed. Chat reads the repo back via Projects sync or attach.

**Never** save volatile state into Claude.ai project knowledge — that is the two-master pattern that produced the Decision #3 drift. Project knowledge holds stable orientation docs only (Clinical_Protocol, Athlete_Profile, labs, Stack, API_CONTRACTS, Hevy_Pattern, Readiness_Algorithm).

**Do not** rely on conversation memory for context that belongs in a canonical store. Full loop model: `CLAUDE.md`.

---

### 2.9 Commercial scope — personal proof case first, B2B second
**Preference:** Build for personal/family use first. The proof case (Luke's own data running end-to-end across all three modules) is the commercial asset. Do not over-engineer for commercial requirements now (multi-tenancy, billing, partner APIs).

**Commercial direction:** B2B entry point is TRT clinics and compounding pharmacies — platform is practice management and patient outcome tracking; clinic holds medical responsibility. Consumer pitch is "Never waste a medical appointment again." Keep architecture clean enough that the clinic dashboard layer can be added on top without rework.

**Exception:** Device agnosticism is required from day one — this is a commercial-readiness requirement that costs nothing to implement correctly but is expensive to retrofit.

---

### 2.10 Passive HRV collection is the priority
**Preference:** Galaxy Ring is the primary HRV source because passivity is the priority — no morning protocol, no deliberate measurement required.

**H10 role:** Re-validation instrument, not calibration layer. Ring and H10 measure in different physiological windows (nocturnal averaged vs morning supine). No correction factor between them. H10 validates Ring coherence and trend-faithfulness, not accuracy in absolute terms.

---

### 2.11 Nutrition layer — recommend Cronometer, don't build it
**Preference:** Nutrition logging is not built into the platform at MVP. Recommend Cronometer to users. Accept Health Connect daily totals as low-resolution supporting signal. Do not build a competing nutrition logging interface.

---

### 2.12 Session lifecycle — repo is the sole source for governance stores
**Preference:** Two session-lifecycle rituals keep the repo, not chat memory, as the source for governance stores:
1. **At session open**, Code reports the current `DECISIONS_LOG.md` max decision number; chat re-aims any brief against it before acting.
2. **At closeout**, Code writes the close-out body verbatim to `closeout.md` and prints only a terse pointer to stdout — path, branch, next action, and the filenames of governance stores changed that session (`DECISIONS_LOG`, `ROADMAP`, `FEEDBACK`, `OPEN_QUESTIONS`, `Ideas`; names only, never contents). It does not emit store text; pre-merge copy-back is `cat`/open of the changed store file on disk. Chat consumes those files as orientation, replaces the project copies wholesale, and never regenerates them from memory.

**Reason:** A stale project copy (`DECISIONS_LOG` #18 vs repo #31) cost a round-trip and risked fabricated entries, 26 June 2026. Truth lives in the repo; chat-memory must not masquerade as canon.

---

### 2.13 Prior Art — search before build, weight asymmetrically
**Preference:** For third-party integrations — external APIs, connectors, device SDKs, data sources — search developer forums, GitHub issues, and existing libraries for proven paths and documented limitations before proposing a build or branching to an alternate route. Weight findings asymmetrically: a community "this can't be done" is a strong lead worth banking provisionally (prevents dead-end effort; cross-checks our own tests); a community "this works" is a hypothesis to re-verify against current platform state, because positive prior art rots under vendor rewrites. Tag every finding with platform version/date. Not canon — a decision input and an independent check on our own implementation results. Excludes our own domain logic (readiness model, four-window scoring, exposure engine), where first-principles governs.

---

### 2.14 Prior art finding — Polar AccessLink per-second exercise HR (per 2.13)
**Finding:** Polar exposes two distinct HR surfaces, not one. (1) Per-session **exercise-samples** — the v3 REST endpoint and the TCX/CSV/FIT session export — carry a per-sample-type `recording-rate`; where it equals 1 (or the export's native second-by-second granularity), HR is 1Hz. (2) The **v4 REST `training-sessions/list`** endpoint (the current production transport, DECISIONS_LOG #17) returns summary only — no per-second series, by design. (3) Separately, Polar's **continuous 24/7 samples** (`TRIGGER_TIMED_247`) are a background/all-day stream, coarse relative to session recording, and not the same surface as an exercise session.

**Methodology (bounded search, tagged per 2.13):** official Polar AccessLink v4 API docs (endpoint/scope surfaces, June 2026 platform state); validated open-source v3 client `StuMason/polar-flow` (`models/exercise.py` → `ExerciseSample.recording_rate` field, confirms the per-sample-type rate exists and is queryable); Polar's own export documentation (TCX/CSV second-by-second HR, RR in FIT/.txt); corroborating aggregators (Terra, Open Wearables, vitalera) cross-checking the v3-vs-v4 surface split. This is a **bounded** search — official docs + one validated client + three aggregators, not an exhaustive forum sweep — and carries the standard positive-prior-art discount from 2.13 (re-verify before build).

**Caveat:** v3 REST is Polar's older surface; deprecation risk is unassessed this session (flagged, not resolved). PSL (chest-strap direct upload) remains the primary, higher-fidelity capture path for solo/gym sessions (1Hz HR + per-beat RR + 203Hz ACC + 130Hz ECG) — this finding does not change that. No ingest built from this finding. See DECISIONS_LOG #46.

---

## 3. Things Claude Should Do Differently

Pattern-level lessons from session observations.

---

### 3.1 Don't assume absence of visible reasoning = absence of reasoning
When Easty makes a choice and doesn't explain it in chat, assume there was a reason. Surface rationale for confirmation rather than assuming naivety or accident. Default: "was that intentional?" not "you got lucky."

---

### 3.2 Propose Postgres queries for data verification, not UI inspection
For any question about what data exists in the system, the first instinct should be a Postgres query against Railway, not "browse the Health Connect app" or "check the UI." This is faster, more precise, and matches Easty's preference.

---

### 3.3 Distinguish code bugs from API limitations before pushing back on workarounds
Before challenging a design decision or workaround, confirm whether the underlying problem is fixable (code bug) or inherent (third-party API constraint). Two different problems can exist simultaneously.

---

### 3.4 Separate SpO2 nadir from snoring — completely different signals
For Easty's data specifically: snoring = noise (CPAP artefact). SpO2 nadir = signal. Never group these. Never flag snoring as a concern. SpO2 nadir consistently below 94% warrants a clinic conversation; snoring minutes warrant nothing.

---

### 3.5 Samsung Health package name is `com.sec.android.app.shealth`, not `com.samsung.health`
The correct filter for Samsung Health data in Health Connect queries is `com.sec.android.app.shealth`. Using `com.samsung.health` returns zero records. This tripped up a diagnostic session.

---

### 3.6 Consensus MCP — targeted mechanism queries outperform broad topic searches
When using Consensus for research: query around specific mechanisms ("RMSSD parasympathetic tone HRV-guided training") rather than broad topics ("HRV training performance"). Always use `exclude_preprints: true` for algorithm science work. Running multiple targeted queries in parallel is more effective than one broad query.

---

### 3.7 MD-for-replacement is now scoped — volatile state goes through Code
The "downloadable MD for direct replacement in the project interface" workflow survives ONLY for (a) refreshing slow-volatile mirrors like this FEEDBACK.md and (b) stable orientation docs. It is retired for volatile state — decisions, open questions, roadmap, tasks are written to the repo by Code and read back via sync. When Easty says "update the decision log" or "consolidate," the output is a pending-commit queue for Code, not an MD saved into project knowledge. See 2.8.

---

### 3.8 VO₂max age formulas are a hard no
Never use age-predicted HRmax (220 − age or similar). Measured HRmax from Polar H10 sessions only. One bad HRmax value propagates error into every estimate indefinitely.

---

### 3.9 Treat injury flags as live state, not historical data
Injury flags are active session constraints affecting exercise selection right now. They are not historical health information. They live on the readiness axis, not in a health history log. Design accordingly.

---

### 3.10 Health Connect verification — Samsung Health Data SDK is the migration target, scraper is the fragility risk
The scraper (`HRVAccessibilityService.kt`) is confirmed working but is the most fragile component in the system. It is the source of the keystone signal (HRV). The Samsung Health Data SDK is the correct migration target for metrics it can serve. The agreed next action is a live SDK read with a known-populated metric as a positive control.

---

### 3.11 Health intelligence mode — Luke is the analyst, not the audience
When discussing lab results, protocol context, or health markers in the health intelligence capacity: explain mechanisms and pathways, not just meanings. Stack-aware at all times — never interpret a marker in isolation from the active protocol. Confidence-tag all claims. No reflexive clinical deferrals — if clinical input is needed, specify exactly what to ask and why.

---

## 4. Project-Level Principles (Elevated from Patterns)

These emerged organically from corrections and should be treated as first-class project rules.

| Principle | Source |
|-----------|--------|
| No metric enters algorithm design until there is a "how you know" artefact — confirmed test, verified search, or official documentation. "The API has a field for it" is insufficient. | HRV pipeline failure |
| Proprietary composite scores are rejected. Raw signals only, every signal traceable to a published physiological mechanism. | Explicit preference, multiple sessions |
| Annotate confounds, don't discount scores. The physiological state was real; the cause is what gets tagged. | Wine night session |
| Infer → surface → confirm. Never silently commit. Under uncertainty, degrade to broader caution rather than false precision. | Injury schema session |
| Treat logged choices as reasoned. Ask for rationale rather than assuming accident. | Echo bike session correction |
| Injury provocation is movement-pattern and condition indexed, not body-part indexed. Three-valued: provocative / clear / untested. | Injury schema design |
| The scraper is the fragility risk. Any metric the Samsung Health SDK can serve should migrate there to shrink the scraper's blast radius. | Architecture review session |
| Manual cardio sessions on unconnected equipment must be logged to prevent ACWR silently under-reading load. | Echo bike session |
| Platform is a health intelligence platform, not a fitness app. Three modules — Fitness, Medical Protocol, Decision Support — on a unified event timeline. | Platform reframe session, June 2026 |
| Regulatory line: explain mechanisms, list evidence-ranked levers, stop there. Never connect levers to specific recommended actions for an individual. Education is permitted; prescription is not. | Commercial direction session, June 2026 |
| Repo is the single source of truth for volatile state (decisions, open questions, roadmap, tasks). Code/`@claude` Action is the only writer; chat proposes, never commits. Volatile state is never saved to project knowledge; stable orientation docs stay there. Full model in CLAUDE.md. | Source-of-truth consolidation, June 2026 |
| Device agnosticism is an architecture constraint from day one. Source field abstracts hardware. Algorithm never references device-specific schema. New devices are integration problems, not algorithm problems. | Architecture session, June 2026 |

---

## 5. Easty's Current Injury State (as of June 2026)

*For readiness coaching — these are live constraints, not history.*

| Injury | Provocation status | Notes |
|--------|-------------------|-------|
| Left little finger | Provocative | Wrenched, swollen, bruising tracking across palm. Flagged for imaging before any load progression. Do not progress load until cleared. |
| Right shoulder | Provocative (conditional) | Upper trapezius insertion tear at posterior border of lateral clavicle. Rugby tackle ~late May 2026. US pending — specific sonographer direction required (posterior lateral clavicle, upper trap origin — not a standard shoulder protocol). Horizontal adduction provocative unloaded toward end-range; load amplifies. Overhead: caution. Pressing: untested/unknown. Playing through. |
| Right proximal semimembranosus | Provocative / playing through | Full-thickness partial-width rupture confirmed ultrasound Aug 2025 (Dr Prasad De Silva, NQX Townsville). 3.3×1.6cm, retracted fibres distally. Right kinetic chain — consistent with asymmetry pattern. DISTINCT from left hamstring issue. |
| Left hamstring | Clear below threshold / Provocative above | Functional provocation only — not imaged. Clear below velocity threshold including jogging. Provoked by striding and sprinting. Velocity is the gate, not activity type. DISTINCT from right semimembranosus tear. |

---

## 6. Easty's CPAP Context

*Relevant for interpreting sleep data.*

- Device: AirMini
- App: AirMini app (not myAir — separate ResMed product; do not conflate)
- Data sharing: Practitioner access via AirView
- No SD card: OSCAR analysis not possible
- In-app self-serve: Per-night AHI and mask seal, 30-day window
- Samsung Health snoring detection: CPAP airflow artefact — always discard
- SpO2 nadir: The relevant clinical signal; nadir below 94% warrants attention

---

## 7. Engine — `_LOADED_KEYWORDS` is a fallback, not truth (DECISIONS_LOG #74)

**What was wrong:** `infer_loaded_regions` inferred which taxonomy regions the user had loaded from Hevy
titles using `_LOADED_KEYWORDS` — ~30 lowercase substring rules in a loop with NO break on match. On the
user's live last-90d history it produced simultaneous false positives and false negatives, materially
corrupting the engine's model of what the user has loaded (which in turn corrupts probe queueing — a
falsely-loaded region is never probed — and interacts with `_RADICULAR_BLOCKS`):

- **Copenhagen Plank (Short Lever)** (×9) matched `plank` → `trunk_stability_sagittal`. It is frontal-plane
  / adductor work. The engine was blind to the frontal work the user is actively doing — the exact stimulus
  behind an active injury (left pes anserine) — and to `frontal_single_leg_stability`, one of his fortifying
  regions.
- **Shoulder External / Internal Rotation** (×22, the highest-frequency titles) matched the substring
  `rotation` → loaded `rotation`, a `_RADICULAR_BLOCKS` region. Rotator-cuff isometrics masqueraded as
  loaded trunk rotation, so the engine stopped probing rotation — the very region the user's positive slump
  / S1 pattern should keep it cautious about.
- **Cable Twist** (×6) matched nothing (`twist` is not a needle) — genuine loaded rotation entirely unseen.
- **Single Leg RDL** (×2) matched `romanian`/`deadlift` → `hinge`, laterality lost — the whole right-side
  deficit story invisible.
- ~41% of distinct titles fell through to the empty fallback.

**Rule going forward:** The authoritative exercise→region source is the `exercise_region_tags` join, not
the keyword matcher. `_LOADED_KEYWORDS` survives ONLY as a fallback for untagged templates, and every
fall-through is counted and logged — the fallback hit-rate IS the tagging-coverage metric (target: zero on
the active window). Do not add rules to `_LOADED_KEYWORDS`; tag the template instead.

### 7.1 A tag must match the movement's CAPACITY, not just its body part (DECISIONS_LOG #76)

**What was proposed and rejected:** tagging Calf Raise → `ankle_df`, and Shoulder ER/IR → `shoulder_mobility`.

**Why it's wrong:** both map a STRENGTH movement onto a MOBILITY/screening region of the same body part but
a different capacity. Calf raise is plantarflexion *strength*; `ankle_df` is dorsiflexion *mobility* — the
exact opposite movement. Tagging it would mark a live Tier-B screening region as demonstrably loaded and
suppress the engine from ever probing ankle dorsiflexion. Same failure class as Shoulder-Rotation → rotation,
just quieter. A wrong tag is worse than an empty, because an empty is honest about the gap.

**Rule going forward:** when a movement has no region of the RIGHT capacity, the answer is **adjudicated
no-pattern** (`adjudicated_at` set, zero tag rows), never the nearest-body-part region. If the missing axis is
real and evidence-grounded (e.g. the joint-level strength-ratio family — Q27), that is a versioned taxonomy
design pass, not a tag-file bolt-on. The taxonomy is external-authority precisely so its breadth does not
inherit the user's logging habits.

---

## 8. LANDED ≠ LIVE — local-green is not prod-live (DECISIONS_LOG #77)

**What happened:** three features — the Hevy template resolver (#60/#61), `create_and_resolve` (#65), and the
whole exercise-catalogue taxonomy tagging effort (#74/#75/#76) — landed on `master`, all green across 87 local
tests, and were **structurally inert in prod**. Their substrate, `hevy_exercise_templates`, had zero rows,
because `sync_exercise_templates` had never been wired to any call site (no endpoint, no job, no cron) and had
never run. The catalogue seed would have resolved 40/40 titles to None and exited 0 — a green no-op reading as
success. The catalogue work is simply the first feature whose payoff was actually *collected*, which is the
only reason the gap surfaced.

**The disease, not the instance:** no gate in this project has ever asserted a PROD PRECONDITION. Every gate
tests behaviour against a seeded local/test DB, so "local-green" is silently read as "done/live." Same signal
appeared earlier and was noted-not-fixed: `feat/constraint-consumption` (BRANCHES.md) flagged that
`get_readiness_snapshot` via the MCP connector "appears to read a non-prod DB." Data-verification-against-a-
seeded-DB is not data-verification-against-prod.

**Rule going forward:** a feature that depends on a populated table is NOT done when its tests pass — it is done
when that table is populated in prod and the payoff is observed there. State the prod precondition explicitly
(which table, expected non-zero state) and verify it before calling the feature live. Where a subsystem can be
inert, make its no-op LOUD (a warning + a non-zero exit), never a silent success — as #77 does for the sync and
the seeder.

**Proposed for a future brief (NOT yet built):** a prod-state assertion in `/closeout` — every feature that
depends on a populated table names that table and its expected non-zero state, so a landed-but-not-live feature
cannot close silently.

---

## 9. The Bash tool is Git Bash (POSIX sh) — never PowerShell here-strings in it

**What happened:** the first commit of DECISIONS_LOG #78 was written with `git commit -m @'...'@` — PowerShell
here-string syntax — run through the **Bash** tool. Git Bash is POSIX sh, not PowerShell: it parsed the argument
as a literal `@`, then a single-quoted string, then a trailing `@`, leaking a stray `@` onto its own line at the
top of the commit subject. Caught on read-back and fixed by amending the unpushed commit.

**Why it's wrong:** the two shells in this environment take *opposite* multi-line-string syntax, and the mistake
is using one shell's idiom in the other's tool. PowerShell here-strings are `@'...'@` (and the closing `'@` must
be at column 0). POSIX/Git-Bash heredocs are `<<'EOF' ... EOF`. `@'...'@` means nothing to bash; `<<'EOF'` means
nothing to PowerShell. The `@` is not a comment or string marker in sh, so it survives into the payload.

**Rule going forward:** pick the string syntax by the TOOL you're invoking, not by habit. In the **Bash tool**
(commit messages, file bodies, any multi-line literal) use a quoted heredoc — `git commit -F - <<'EOF' … EOF` —
the single-quoted delimiter keeps `$`/backticks literal. In the **PowerShell tool**, use `@'…'@`. Never cross
them. (Mirror of the standing "Windows / PowerShell only" rule, one layer down: knowing you're in PowerShell for
`.command` doesn't help when the Bash *tool* is the one running the string.)

---

## 10. False-green instruments — an unsound measurement reporting zero (mirror of §8)

**What happened:** a title-keyed tag-coverage pass over the 28-day window scored 38/38 — fallback hit-rate 0,
apparently perfect coverage. It was wrong. At that moment `Bulgarian Split Squat` had no `exercise_region_tags`
row and no `adjudicated_at`, and had been trained on 10 Jul — inside the window. Its true fallback hit-rate was
1/38. The pass counted the movement as covered because the reference file matched the stale LOGGED title, while
`infer_loaded_regions` joins on `exercise_template_id` against the CURRENT catalogue, where the bare title does
not exist. The instrument committed, inside itself, the exact title-space drift it existed to detect
(DECISIONS_LOG #79).

**The disease, not the instance:** §8 is inert code reporting *done*. This is its mirror — an unsound instrument
reporting *zero*. Both are green readings that mean nothing, and both are more dangerous than a red one, because
a zero is what you were hoping for and so nobody interrogates it. The tell is shared: the measurement and the
behaviour it claims to measure were keyed differently, so the number described a system that does not exist. A
coverage metric keyed on anything other than what the code joins on is not a weaker measurement — it is a
different measurement wearing the same name.

**Rule going forward:** measure on the key the system actually joins on (`exercise_template_id`), never the key
that is convenient to read (`title`). Before trusting any instrument's green, state which key it keys on and which
key the code under test keys on; if they differ, the instrument is unsound regardless of what it reports. Where a
measurement and its subject can drift apart, derive both from one definition rather than restating the rule —
as #79 does by extracting `selection.classify_coverage` and having the audit and the read path share it. A second
statement of a rule is a second rule.

---

## 11. A probe that presumes its own answer — fail loudly when you never reach the subject

**What happened:** `probe_resolver.py` ran against the live 494-row catalogue and measured nothing. Its scripted
turns were written against a synthetic fixture with no injuries and no profile — a world where the model has
nothing to ask. Against REAL user state the model interrogates before provisioning (readiness gates, injury flags,
session identity), and `_section_routine_creation` forbids emitting a routine block without explicit confirmation.
The scripted turns never gave one. Six turns, zero `<hevy_create_routine>` blocks, `suggest_candidates` never
called — and the harness printed a clean run and exited 0. The null result had to be reconstructed from the
transcript, because nothing announced it.

**The disease, not the instance:** same family as §10. There, an unsound instrument reported zero because it was
keyed differently from the code it measured. Here, an instrument reported nothing-wrong because it never reached
the code at all — its fixture encoded a world (no constraints, no questions) that was not the world under test, and
the probe's script silently assumed that world persisted. This is the SECOND fidelity failure in this test class:
the first (caught before it produced fiction) appended the raw model reply rather than the cleaned reply plus
actions, so the model never saw its own warning and any "it recovered" verdict would have been invented. A probe of
a live, stateful system inherits that system's state as a hidden input — and hidden inputs drift.

**Rule going forward:** a probe must fail LOUDLY when it fails to reach the code it exists to measure — non-zero
exit, naming what it never reached. Silence must never be reportable as success (the behavioural mirror of #77's
loud no-op: a subsystem that can be inert must say so, never exit 0 quietly). And when a probe drives a system
whose behaviour depends on live state, either pin the state in a fixture or expect the probe to measure the state
rather than the code. Ask of any green probe: did this actually execute the thing it claims to have tested? If it
cannot prove it did, it did not.

---

## 12. A declarative claim about an unseeable surface is an instruction to verify, not a fact (DECISIONS_LOG #88)

**What happened:** #87's brief asserted a precondition in the declarative mood — a statement about a
surface chat cannot read (the corrected `INTERPRETATION_OUTPUT_CONTRACT.md`, UI-maintained per #63, not
in the repo). Code reflected the claim back as if it were operator-attested. When the attribution was
traced, the chain terminated in chat's own sentence: no operator run, no Postgres query, no pushed ref
ever carried it. Three turns went to resolving the state of something nobody had observed.

**The disease, not the instance:** the loop already forbids "the API has a field for it" (the
**How-you-know** rule) and "a test passed = done" (§8, §10). This is the same failure one level up — a
claim's GRAMMAR mistaken for its EVIDENCE. Declarative mood is free: anyone can write "master is at #87"
or "the seed ran," and the sentence attaches no artifact. Chat can verify only what is on a pushed ref;
everything it says about local disk, prod/Railway, the operator container, or a UI-maintained file is a
claim it cannot itself check. Reflecting that claim back as attested manufactures a fact out of a
sentence — and a state nobody looked at then costs turns to unwind.

**Rule going forward:** the unseeable-surface rule (CLAUDE.md shared block) — any brief statement about a
surface chat cannot read is an INSTRUCTION TO VERIFY, never a report of fact, regardless of phrasing.
Code verifies against the surface (query, ref, run) or STOPS and reports; it never lands on a claim's
grammar. Recorded here because a rule without its generating incident reads as ceremony and gets deleted;
this is the incident that earned it.

---

## 13. A rule proven on two rows is not a rule applied to the store (DECISIONS_LOG #90)

#88 demonstrated the four-state vocabulary on `fix/probe-harness-fidelity` and `feat/recovery-metrics-rhr`, and
treated demonstration as adoption. The other sixteen `BRANCHES.md` rows kept `LANDED` / `IN FLIGHT` / `PARKED` and
`OPEN_QUESTIONS.md` kept `PENDING` / `PARKED`, so the store a returning session actually reads still spoke the
superseded dialect.

**Rule:** when a governance change alters a label, format or convention, the landing commit must either sweep every
existing instance or record the unswept remainder as OWED with the exact scope. Partial adoption is a silent-failure
mode — nothing goes red, and the store quietly carries two dialects, leaving the reader to guess which one a given
row is written in.

**Corollary — a brief's predicted verdict is a hypothesis with a hint, not a licence.** Where a brief predicts an
outcome ("expected: close DONE"), it must name the artifact that would prove it, never the memory that suggests it.
The #90 sweep's brief predicted three closures. Two held against artifacts on master. The third —
`feat/connector-error-policy`, "the key was replaced 12 Jul and See-all verified live" — came from chat scrollback,
was written in the declarative mood, and had no artifact on master or in prod behind it. It stayed OWED. An expected
closure is a place to look, not a verdict to record.

**Why it generalises:** #90 found the same defect three times in one sweep — a row whose *Unblocks on* column
vouched for its stale *Status* column (position), a branch that looked complete by merge position while consuming a
superseded contract (completeness), and a brief asserting prod state from its own recency (recency). One root: a
claim inheriting authority from where it sits rather than from what attests it. Position, completeness and recency
are not evidence. Only an artifact is.

---

## 14. A vocabulary is not adopted until its predecessor is struck from the rules (DECISIONS_LOG #91)

#88 added the four states while leaving `OPEN_QUESTIONS`' three-value set standing twelve lines away
in the same file. Both were simultaneously canonical, and a correct executor could not act: whichever
it picked, the other rule said it was wrong. Superseding a convention *in practice* while leaving its
definition *in the rules* does not retire it — it forks the rules.

**Rule:** when a convention replaces another, the landing commit must delete the old definition in the
same edit that adds the new one. And state one definition in one location — a restatement elsewhere
"for convenience" is a second copy that will drift. The contradiction resolved here began as exactly
that, and the #91 sweep found a *third* copy in `OPEN_QUESTIONS.md`'s own file header.

**Corollary — an integrity gate must name the surface it measures.** A verification method can inherit
false authority from looking objective. A raw `md5sum` is maximally mechanical and still returned the
wrong verdict here, because it measured the working tree while the thing that propagates is the index.
Every integrity gate must name the surface it measures, not just the comparison it performs — an
unspecified surface makes the gate's result unfalsifiable, since either answer can be defended after
the fact. This is #90's defect in a third costume: position, recency, and now apparent objectivity,
each vouching for an attestation none of them carry.

**Corollary — a distribution must sum to its population.** Chat asserted a store's label distribution
from a full-text word grep rather than from the status field, producing counts that exceeded the item
count (42 labels across 29 questions) — an arithmetic impossibility visible without any repo access.
Before reporting a distribution, verify it sums to the population. A measurement that cannot be wrong
in a detectable way has not been checked.

**Why it generalises:** all three costumes were worn in a single session, and the third arrived *inside
an argument about measurement discipline*. Rigour about evidence is not a state you reach and hold; it
is a check you run per claim, including on the claims you make while insisting on it.

### §14 recurrence log — counting the word instead of counting the field

The corollary above ("a distribution must sum to its population") was written after the first
occurrence. It has recurred twice more since, which means it was not yet operating as a rule.

- **Occurrence 2 (health-connect-app, 2026-07-20).** A brief reported that repo carrying
  `PENDING ×6`. There were **four** `PENDING` rows; the count swept up the file header's "stays
  PENDING until" and Q4's body text "Q4 stays PENDING". Recorded in HCA's own FEEDBACK; appended here
  because the rule lives in this repo and a recurrence logged only at the far end never reaches it.
- **Occurrence 3 (this session, caught before reporting).** The #92 exit gate was first run as a
  word-level grep across four files. It returned "Landed" ×3 in health-connect-app's `BRANCHES.md`
  and `pending` / `blocked` / `resolved` in health-app's `ROADMAP.md`. Both would have been reported
  as vocabulary violations. Re-running by **field** showed the HCA hits sit in column 4 (prose:
  "Landed on master via clean `--ff-only` …") while its status column is clean four-state, and that
  ROADMAP has no status field at all — its tables are `| Item | Notes |`, so a label cannot exist
  there to be wrong.

- **Occurrence 4 (chat, 2026-07-20, G1 verification — the dangerous shape).** The G1 shared-block
  comparison was run as extract-then-compare. The extraction failed silently, yielding two empty
  results, and the comparison of empty-against-empty returned **PASS** — the expected answer, arrived
  at by measuring nothing. This is the most dangerous variant in the family: occurrences 1–3 produced
  numbers that were *wrong* and therefore checkable, but a false PASS is indistinguishable from a true
  one at the point of reading. It looks like confirmation.
  **Rule:** assert the input is non-empty and plausibly sized *before* any comparison is allowed to
  mean anything. An equality test over two nulls is not evidence of equality; it is evidence the
  extractor ran. Gate the gate.

**What the third occurrence teaches that the first two did not:** the author of the rule nearly broke
it, in the very commit that records it, while checking someone else's compliance with it. The
substitution is not carelessness and does not yield to intent — a full-text search for a label *looks
like* counting the label at the moment you run it. The only reliable defence is structural: extract
the field by position, then check the total against the population. If a check cannot report *which
column* it counted, it has not counted a label.

---

## 15. A scope exclusion carries the same evidentiary burden as a scope inclusion (DECISIONS_LOG #93)

#92's brief placed this repo's `/closeout` ritual out of scope with the words "already struck" — a
declarative about a file the author had not read. It had not been struck; `parked` was still at line 34.
The exclusion was not a lie, it was an *assumption stated in the indicative*, and that is the failure
mode: an omission leaves a gap someone eventually trips over, but a false out-of-scope **closes the
question**. It instructs the next session not to look.

**Rule:** name the artifact that justifies an exclusion, or write it as "not examined" rather than
"already done." "Out of scope because X was verified at SHA Y" is a scope decision; "out of scope
because it's already handled" is an unverified claim wearing a scope decision's clothes. This is
[[§12]]'s unseeable-surface rule applied to the *negative* space of a brief — the same declarative-mood
problem, but harder to catch, because nobody audits the things a brief told them not to look at.

**Corollary — sweep from the most authoritative surface downward, not the most visible upward.**
The vocabulary adoption regenerated itself three times, and the layers fell in strict order of
increasing authority:

| Session | Swept | Exposed next |
|---------|-------|--------------|
| #90 / #91 | the **values** (row and question status fields) | the ritual |
| HCA #21 | the **ritual** (the generator that writes rows) | the header |
| #93 (this) | the **header** (the frame that teaches the writer) | the shared block |
| Q33 (deferred) | the **shared block** — the document that *defines* the vocabulary | — |

Each sweep met its exit condition honestly and each was followed by a session finding the dialect one
layer up. That is not four failures of thoroughness; it is one failure of *ordering*. Values are
visible, so they get swept first; definitions are authoritative, so they get swept last — by which
point the definition has re-emitted the dead dialect into every layer beneath it. Sweeping downward
from the definition would have caught all four in one pass, because nothing below can contradict a
surface that has already been fixed. Ask "what writes this?" before "what does this say?", and fix the
writer first.

---

## 16. A derived artifact with no generator is a fork (DECISIONS_LOG #94)

`CONSOLIDATED_GOVERNANCE_VIEW.md` declared itself read-only and said to regenerate it from a master
export. No such export existed. It was hand-assembled once and never again, and by 2026-07-20 it sat
65 decisions and three weeks behind master while still presenting as current.

**Rule:** where a document declares a generation source, that source must exist in a repo, or the
declaration is a fiction that makes the file look *more* trustworthy than it is. "Generated from X" is
a claim about a mechanism, and it carries the same evidentiary burden as any other claim — name the
script, or write "assembled by hand on <date>, verify before use."

**Why it is worse than an ordinary stale file.** A file with no freshness claim gets checked. This one
carried a read-only banner and a regeneration instruction, both of which read as *machinery* — and
machinery implies something keeps it true. The banner suppressed exactly the scrutiny that would have
caught the drift. This is [[§10]]'s false-green instrument in documentation form: the failure is not
that it was wrong, but that it was wrong in a costume that discouraged checking.

**Corollary — a mirror large enough to substitute for the source will be read instead of it.** The
predecessor was a verbatim dump because that fit at 34 decisions. Verbatim is not a neutral choice at
scale: it produces a second copy of the repos, complete enough to answer from and too large to audit,
which is precisely how it drifted unnoticed. A derived view should be a *digest with pointers* — enough
to know what exists and where, never enough to answer from. Size is a design constraint on
trustworthiness, not just on convenience.

