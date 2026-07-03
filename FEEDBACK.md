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
