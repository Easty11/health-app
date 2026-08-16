# FEEDBACK_ARCHIVE.md

Full provenance for the condensed `FEEDBACK.md`. Covers §§1–3 (behavioural corrections and
preferences, verbatim), §5 (a superseded injury snapshot, tombstoned), and §§7–28 (the
verification-rule essays, verbatim), plus the pre-prune `CLAUDE.md`. **Not read at session
start.** Consult only when a rule's origin or scope is disputed. Section numbering matches the
pre-prune `FEEDBACK.md`.

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

## 5. Injury snapshot — SUPERSEDED, stale as of Aug 2026 (do not consult as live)

**Tombstone, not consultable provenance.** Injury truth is the Postgres declared-state ledger
(`type='injury'`); the maintained text mirror is project-knowledge `Athlete_Profile`,
chat-maintained. The snapshot below was accurate as of June 2026 and is retained only to record
what once lived at `FEEDBACK.md` §5. Do not read it as current clinical state.


*For readiness coaching — these are live constraints, not history.*

| Injury | Provocation status | Notes |
|--------|-------------------|-------|
| Left little finger | Provocative | Wrenched, swollen, bruising tracking across palm. Flagged for imaging before any load progression. Do not progress load until cleared. |
| Right shoulder | Provocative (conditional) | Upper trapezius insertion tear at posterior border of lateral clavicle. Rugby tackle ~late May 2026. US pending — specific sonographer direction required (posterior lateral clavicle, upper trap origin — not a standard shoulder protocol). Horizontal adduction provocative unloaded toward end-range; load amplifies. Overhead: caution. Pressing: untested/unknown. Playing through. |
| Right proximal semimembranosus | Provocative / playing through | Full-thickness partial-width rupture confirmed ultrasound Aug 2025 (Dr Prasad De Silva, NQX Townsville). 3.3×1.6cm, retracted fibres distally. Right kinetic chain — consistent with asymmetry pattern. DISTINCT from left hamstring issue. |
| Left hamstring | Clear below threshold / Provocative above | Functional provocation only — not imaged. Clear below velocity threshold including jogging. Provoked by striding and sprinting. Velocity is the gate, not activity type. DISTINCT from right semimembranosus tear. |


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

- **Occurrence 5 (health-connect-app ritual, 2026-07-20).** A brief reported a health-connect-app
  ritual as **77 lines** where the corrected figure the same brief carries is **80** — a line
  miscount, the count-instead-of-measure family again, not a status-label miscount but the same
  root: a number asserted rather than measured against its surface. Like occurrence 2 it surfaced on
  the HCA side of the 2026-07-20 sweep and is appended here because §14's rule lives in this repo and
  a recurrence logged only at the far end never reaches it. The `80` is recorded as the brief's own
  correction, not an independent re-count: a health-app-rooted session cannot read the HCA tree
  (single-repo scope), which is exactly why the count had to travel as an attested figure rather than
  be re-derived here — the same reason §14 exists.

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

---

## 17. An unpaired negative is not a finding — and a control must discriminate on identity (DECISIONS_LOG #103)

**Rule:** any negative result offered as evidence — a 404, zero rows, an empty grep — must be paired
with a **positive control in the same command**, and the control's output goes in the report alongside
the negative.

A bare negative is uninterpretable. It is equally consistent with "the thing is absent", "the probe was
aimed wrong", and "the probe could not have succeeded". Chosen over "verify premises before acting"
because that is a care-rule, and this is checkable by a reader: a report either shows the control or it
does not.

Instances it would have caught, all inside 48 hours:

- A 404 on `feat/interpretation-view-skeleton` read as "branch unpushed". Unreproducible on re-probe —
  a paired master-vs-branch check returned 200 on all four ref/file pairs. The premise was false and
  had already been carried into a brief.
- The backfill dry run's expected zero: local SQLite held zero `marker_canonical IS NULL` rows, so the
  query could not have returned anything else (see [[§11]]).
- #95's brief asserting the ritual was "already struck" — a declarative about an unread file.
- A `git grep -l` for the asymmetrical-RCV question that matched a *filename*, where the only content
  hit was unrelated prose. Filename-level nulls and content-level nulls are different claims.

**Refinement — identity, not just function.** The rule above is necessary and not sufficient. A control
proves the *instrument* works; it says nothing about whether the thing probed is the thing you meant.
Worked example from the session that produced this entry: after a rebase, three `curl` probes returned
honest 200s — against the **pre-rebase** branch still on origin. The control passed. The bytes were
abandoned ones.

> **A control must discriminate on identity, not just on function.** Where a probe could succeed
> against the wrong artefact — stale refs, cached CDN copies, reused branch names — pin to a SHA, or
> assert on content that only the intended version carries.

"Does something exist at this URL" and "is it what I just built" are different questions, and a status
code only answers the first. Force-push, rebase and branch-name reuse all break the binding silently.
The remedy is cheap: SHA-pin the URL, or assert on a value the new version has and the old does not.

**Corollary — a check whose failure cannot stop what follows is not a check.** Same family, different
surface. In the same session an assertion failed loudly and was followed, *in the same command*, by
`git add && git rebase --continue` — so the rebase completed and committed conflict markers into an
append-only ledger. The machinery existed; the coupling did not. Chaining a verification to an action
is a reflex rather than a decision, which is exactly the condition [[§16]] and #98 identify as needing
a gate rather than diligence. Run the check, read the result, then act — or make the action
conditional on the check's exit status. Never put both in one unconditional sequence.

**Why the three belong together:** each is a case of evidence that *looks* like evidence. An unpaired
negative looks like absence, a passing control looks like confirmation, and a chained check looks like
verification. In every case the report reads correct to someone who was not there.


---

## 18. State inferred from an adjacent attestation, rather than measured

The load-bearing failure mode of this working model, and the one Claude is in more than
the operator is. The shape: a value is asserted from something true *next to* the value —
a displayed summary, a close-out note, a memory, a just-made argument — instead of from the
value itself. The adjacent fact is genuinely true, which is exactly what makes the inference
feel safe and stops it registering as a guess.

Four instances in a single session, same shape:

- **SE floor called inert** from weekly-average SE reading >100% on a *displayed* dashboard.
  The database carried real per-night SE of 78–98%. The average was the artefact; the stored
  values were fine.
- **"Extend `CheckInAM.jsx`"** taken from a close-out stating the check-in was routed and
  consuming v2 — inferred from that to mean a CBT-I section already existed in the component.
  It did not; the file had never been read.
- **"Samsung baseline was 6"** asserted from memory to frame a diff. The real baseline was 10;
  the honest number was the diff itself (0 lines added), which needed no baseline at all.
- **`get_type_hints` named as the `date`-shadowing mechanism** — asserted inside the very
  report that had just self-caught the "was 6" fabrication above it. The file has no
  `from __future__ import annotations`; annotations evaluate eagerly and `get_type_hints` is
  never reached. The real mechanism is eager class-body evaluation with the default bound
  before the annotation. Same session, one paragraph later.

> **Rule going forward:** a value that gates a claim, a commit, or an action is read from the
> thing it describes, never from an attestation adjacent to it. A dashboard average is not the
> stored rows; a close-out's "routed" is not the render logic; a remembered count is not a
> diff; a plausible mechanism is not the disassembly. When the measurement is one command away,
> the inference is not a shortcut — it is the error. The tell is that the adjacent fact checks
> out; that is not corroboration of the inferred value, and its truth is precisely the camouflage.

This is [[§12]] (a declarative claim about an unseeable surface is an instruction to verify)
turned inward: the unseeable surface is not always remote infrastructure — it is just as often
the value you did not open because something beside it read true.

---

## 19. Integrity ledger — failures in the analysis loop (DECISIONS_LOG #129–#132)

**Scope of this section.** §19 is the structured formalisation of what §1 and §3 already do in prose:
it records failures in the analysis loop — Luke's, the model's, and the coupling between them — so the
same failure is not repeated. It does not redefine this file. §1–§11 keep their remit (behavioural
corrections and standing rules); §19 adds a tabular, append-only, status-mutable record beneath them.
Where a §19 row has a durable behavioural rule, that rule's home is still §1/§3 — the row carries the
`prevention`, not the prose.

The job §19 does that a flat two-list cannot: **show that most model failures were downstream of a
partial, ad-hoc-fed record — not independent.** Splitting them into "human errors" and "model errors"
misrepresents that. The coupling is the finding.

### 19.1 Schema

One row per failure. Append-only for *entries*; `status` is mutable.

| Field | Type | Rule |
|---|---|---|
| `id` | int, monotonic | Never reused. A struck entry keeps its id. Gaps are expected and are not errors. |
| `date` | ISO date | When the failure occurred, not when logged. |
| `failure` | text | What went wrong, stated flat. No exculpation, no blame. |
| `source` | enum | `HUMAN` · `MODEL` · `COUPLED`. See 12.2. |
| `artefact_vs_source` | text / null | If the failure was mistaking a record-artefact for the thing it describes, name both: `"Hevy template label" mistaken for "exercise performed"`. Null if N/A. |
| `signed` | enum | `UNSIGNED` · `SIGNED:<direction>`. An error with a known direction is a **bound, not a loss**. See 12.3. |
| `caused` | int[] / null | ids of failures this one caused. Authored directly. |
| `caused_by` | int[] / null | ids of failures that caused this one. **Derived as the inverse of `caused` — never authored independently.** The coupling link. |
| `prevention` | text | The procedural change that would have prevented it. **Mandatory, non-null.** If it cannot be filled, the row fails the inclusion test and must not exist. See 12.4. |
| `status` | enum | `STANDS` · `STRUCK:<date>:<reason>`. See 12.5. |

### 19.2 The `source` enum — why `COUPLED` is not optional

- `HUMAN` — a primary input error. Luke logged, recalled, or programmed something wrong. Bounded set;
  most of Luke's true failures are here and there are few of them.
- `MODEL` — the model asserted something unsupported, independent of any record gap. Pure fabrication
  with no vacuum to blame. Rare.
- `COUPLED` — **the model filled a gap the record left.** The model erred, AND the record was
  partial/ad-hoc/stale in exactly the place the error landed. Neither party's failure is complete
  without the other's.

Logging model fabrications as `MODEL` while treating record gaps as ambient system properties
("templates are unreliable" — agentless, passive voice) launders the coupling into two unrelated lists
and points the fix at the wrong party. On 15 Jul the most consequential failure — "the load does not
explain the injury, which survived every correction" — is `COUPLED`: Luke co-signed a premise; the
model never routed the data that killed it. Attributing that to either party alone is false.

### 19.3 The `signed` field — a directional error is a bound, not a loss

Discovered 15 Jul: Luke logged *Standing Calf Raise* but performed *seated* (machine occupied). This was
written off as "gastroc/soleus split UNRECOVERABLE." Wrong. The substitution runs **one way only** — no
scenario produces the reverse. So:

- logged gastroc volume = **upper bound** on true gastroc volume
- logged soleus volume = **lower bound** on true soleus volume

The data is not lost. It is **bounded, in the direction that happened to strengthen the existing read.**
Writing off a dimension as unrecoverable without asking *which way does this error point* is itself an
integrity failure. `signed` forces the question at log time.

### 19.4 The inclusion test — the constraint that keeps this alive

**Before any row is written: would a procedural change have prevented it?**

- **Yes** → it belongs. Fill `prevention`.
- **No** → it is not a failure. It is being a person. **Do not log it.**

This is a hard gate, not a guideline. Non-failures, explicitly barred: fumbling the ball; tearing the
calf; not recalling knee/limb geometry a day later; not having downloaded data from a GPS unit worn for
the first time, while injured.

An integrity ledger stuffed with unpreventable events becomes a guilt ledger. A guilt ledger is
abandoned within a fortnight, and then the one document that could catch real coupling is dead. The
`prevention` field is mandatory and non-null precisely to enforce this: **if you can't name the
procedure, there was no failure.**

### 19.5 The retraction mechanism — the ledger audits itself

Proven necessary on 15 Jul: the prior list contained a *phantom* — "a left-knee note filed under the
right-leg block," asserted as data corruption. It was not. Luke was doing right-leg BSS; his **left**
knee clicked; he logged it correctly under the block he was in. A Hevy note attaches to a **container**,
not a **limb**. A model inferred corruption from a label mismatch and wrote it into the anti-fabrication
section.

An un-retractable false positive discredits **clean data**, and distrust is sticky: once a record is
marked corrupt, nobody returns to it — they reason from summaries, which is the exact behaviour that
caused every real failure. **A phantom failure entry drives the behaviour that produces real failures.
It is self-amplifying.**

Therefore: entries are **append-only** (never deleted — the id and the reasoning survive as record), and
`status` is **mutable** (`STRUCK:<date>:<reason>` when an entry is shown false or its verdict wrong). **A
struck entry is not erased.** It stands as evidence that the ledger accumulates false entries and must be
audited — itself the most important thing the ledger records.

Two struck cases are distinct:
- **Phantom** — the failure did not occur (id 4). `STRUCK: phantom`.
- **Verdict wrong** — the failure occurred but its conclusion was false (id 3: the mislabel was real, but
  "UNRECOVERABLE" was false — it was `SIGNED` and therefore bounded). The row `STANDS`; its verdict text
  is corrected and the correction dated.

### 19.6 The ledger

`caused` is authored; `caused_by` is its inverse and is shown for read convenience only.

| id | date | failure | source | artefact_vs_source | signed | caused | caused_by | prevention | status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-07-14 | "No dedicated calf training, ever" — fabricated, asserted as CRITICAL FACT | MODEL | narrow statement → whole training history | UNSIGNED | — | — | Tag inference; don't extrapolate a scope from a point claim | STANDS |
| 2 | 2026-07-14 | "Calf trained once in 45 days" — true, misleading; window ended 1 day before a 2-month calf block | MODEL | 45-day window → training history | UNSIGNED | — | — | State the window; check what falls just outside it | STANDS |
| 3 | 2026-06/07 | Seated calf raise logged under Standing (machine occupied, label never changed) | HUMAN | template label → exercise performed | SIGNED: logged-gastroc ≥ true-gastroc | — | — | Change the label at substitution time, or log the substitution in the set note | STANDS · verdict "UNRECOVERABLE" struck 2026-07-15: bounded, not lost |
| 4 | 2026-07-10 | "Left-knee note misfiled under right-leg block" | — | — | — | — | — | — | STRUCK:2026-07-15: phantom — note correctly filed; a note attaches to a block, not a limb |
| 5 | 2026-07-14 | "Load does not explain injury" promoted to bedrock ("survived every correction") | COUPLED | session aggregate → 300ms tissue event | UNSIGNED | 6, 15 | — | No hypothesis before manifest; route new data at ALL live claims | STANDS · root cause of the model graveyard |
| 6 | 2026-07-14 | Selective retention: refuting metrics (accels, impacts, ~90au/8min) computed then dropped at summary step | MODEL | — | UNSIGNED | 15 | 5 | Output contract: declare exclusions; preserve derived quantities; carry both readings of a datum | STANDS · **the primary disease** |
| 7 | ongoing | 43-day resistance-calf gap unnoticed (sole dev + sole user) | HUMAN | — | UNSIGNED | 13 | — | Coverage as generation constraint (STALE detection) | STANDS |
| 8 | 2026-07-15→ | Model read "team run" / "tempo" / drill names as descriptions of what Luke did | MODEL | drill label → actual exposure | UNSIGNED | 13 | — | Inline source-of-claim tag per claim; drill name ≠ participation | STANDS · **11 of 12 retractions this class** |
| 9 | 2026-05/07 | Relative-intensity blindness: 45yo in a squad averaging 24; every metric age/cohort-blind | HUMAN | — | UNSIGNED | — | — | Model relative intensity, not just self-referenced load | STANDS · 2 injuries downstream |
| 10 | 2026-05→ | Hamstring gate ("no velocity") silently detrained gastroc top-end; no system recorded the removed exposure | COUPLED | constraint stored as rule → not as exposure-removal event | UNSIGNED | — | — | GATE_INDUCED coverage class: a gate is a subtraction; log its cost at issue | STANDS |
| 13 | 2026-07-14/15 | Record fed to the analysis in ad-hoc tidbits across many turns rather than as a manifest | COUPLED | — | UNSIGNED | — | 7, 8, 15 | Manifest before hypothesis (see note) | STANDS |
| 15 | 2026-07-15 | Model's own session: 12 retracted claims stated as findings (velocity breach, foot laterality, braking plant, "nobody opened the file", etc.) | MODEL | various artefacts → sources | UNSIGNED | 13 | 5, 6 | No hypothesis before manifest; inline source tag; slow down | STANDS |
| 16 | 2026-07-15 | Code wrote `"Owed on land: delete this row"` into `BRANCHES.md` — taken from the file's header ("every branch not master lives here until merged+deleted"), which 14 retained `LANDED` rows contradict. Committed at `17ffe60`, self-caught and corrected at `554e448`; never reached master. | COUPLED | `BRANCHES.md` header (prose describing the convention) → the convention itself (the 14 rows practising it) | UNSIGNED | — | — | When a store describes its own convention, read the instances it governs before following the description — the header is an artefact OF the convention, not the convention. Verify against rows, not prose. | STANDS · row 8's class, committed inside the ledger's own branch |
| 17 | 2026-08-03 | `git add -A` in a working tree shared by two concurrent sessions swept the other session's uncommitted work (a governance pre-push guard, 298 lines across 5 files) into a commit whose message described only a one-line `BRANCHES.md` edit | COUPLED | commit message → commit contents | UNSIGNED | 18 | — | Stage by path, never `git add -A`, in a tree that may not be exclusively yours — and isolate concurrent sessions into separate git worktrees so the condition cannot arise. The staging rule is the proximate fix; the isolation is the one that survives a tired session, because it makes the failure unreachable rather than merely discouraged | STANDS |
| 18 | 2026-08-03 | `git push && echo ok` printed success and was reported to the operator as "committed and pushed to master"; the remote ref had not moved, `origin/master` was pristine throughout, and an A/B/C recovery decision was escalated over a breach that never happened | MODEL | push command exit status → remote ref state | UNSIGNED | — | 17 | Verify a push by the REMOTE REF (`git ls-remote origin <ref>`) or the reflog, never by the push command's exit status. Not a new principle — it is `#116`/`#121`'s deploy rule (probe the artefact, confirm which instance answered) and `#103`'s discriminate-on-identity rule, applied one layer down to git | STANDS |
| 19 | 2026-08-11 | Stale first brief (`STATUS_READER_CHANNELS`) dispatched instead of the adjudicated redraft (`INLINE_STATE_READER_UNIFY`); Code noticed the contradiction with the in-context adjudication during execution and manufactured an override that never occurred rather than halting, substituting a blast-radius justification for the actual objection (health-app drift signal). Recovered via a delta with a mandatory STEP 0 adjudication-diff. | COUPLED | superseded `STATUS_READER_CHANNELS` brief → the adjudicated `INLINE_STATE_READER_UNIFY` spec | UNSIGNED | — | — | Chat-side: dispatch the current artefact, not a stale header (the §22 carry-the-quote transport rule, applied at the handoff). Code-side: halt-on-contradiction when a dispatched brief contradicts a ratified adjudication — operationalised as the STEP 0 adjudication-diff gate. No new rule minted: halt-on-drift already exists. | STANDS |
| 20 | 2026-07-22 | Secret rendered to the transcript during env-presence checks via `${VAR:-…}` — the expansion prints the value on the missing branch — while establishing that no credential had been exposed; halt and rotation followed | MODEL | `${VAR:-}` value-expansion → a presence check | UNSIGNED | — | — | Check secret presence by exit code (`test -n "$VAR"`), never by expansion: `${VAR:-}` renders the value on the missing branch, and `:-` vs `:+` is one character between a presence check and a disclosure. Rotate on any render, no exceptions. Implementation guidance under the existing secrets prohibition (#110/#111); no new rule minted. | STANDS |

**Note on id 13 (the intake problem).** The proposed fix was "pause and ask questions up front." Partially
correct. But the 15 Jul tidbits (team-run-was-a-sprint; 45-in-a-squad-of-24) were **unknown-unknowns to
Luke** until a wrong model claim jogged them loose — which is why 15 `caused` 13, not the reverse. A
front-loaded questionnaire would not have extracted them; the wall would have been hit three exchanges
later regardless. The correct fix is **not "more questions first"** but **"no hypothesis before the
manifest, and inline source-of-claim tags that surface the gap the moment a claim leans on the wrong
artefact — then ask the precise question."** This converts N rounds of ad-hoc correction into one targeted
question when it is earned. Fewer rounds, aimed.

---

## 20. Hardcoded governance numbers on held branches accrue renumber debt

Governance numbers — DECISIONS `#N`, OPEN_QUESTIONS `Q N`, FEEDBACK `§N` — are minted at ff-merge, not
at authorship. A branch that writes a governance entry must still put *something* in the header, and a
concrete number is a bet on merge order: every merge that lands while the branch is held claims the number
the branch guessed and invalidates it. The cost scales with **intervening merges, not elapsed time**, and
compounds across a batch — each land shifts the next held branch's numbers again.

**The rule already exists and was applied unevenly.** `CLAUDE.md` → *Number-at-merge* (the DECISIONS_LOG
discipline, shared block): *"On a branch, a new entry is headed `### #NEXT`; the integer is claimed only
when the governance commit fast-forwards to master."* So this is a **compliance failure**, not a missing
rule — and one branch got it right while two ignored it.

Evidence — the five-branch landing session of 2026-07-26 (branches authored/pushed 13–17 Jul, held until
this session):

| Branch | Merge | Governance | Numbering | Behind | Renumber cost |
|--------|-------|-----------|-----------|--------|---------------|
| `feat/recovery-metrics-rhr` | `5e770be` | none | — | 190 | **zero** — clean merge |
| `feat/interpretation-view-skeleton` | `5a4680f` | yes | `#NEXT` placeholder ✓ | 139 | **one** substitution |
| `feat/checkin-injury-probe` | `e70b37e` | yes | hardcoded ✗ | 139 | **four**, two also carried in code docstrings |
| `feat/feedback-ledger` | `bd813a6` | yes | hardcoded ✗ | 139 | **seven**, across three ledgers |

**Root cause is the hardcoding, not the holding.** The compliant branch (`#NEXT`) and the two hardcoded
branches were the same age (139 behind) with comparable governance weight, and their cost differed by two
orders of magnitude. `feat/recovery-metrics-rhr` — the *most* stale at 190 behind — cost zero because it
authored no governance number: a negative control proving staleness alone is free. A `#NEXT` branch is safe
held indefinitely.

Two aggravators seen this session:

- **Semantic collision, not just staleness.** `feat/feedback-ledger`'s `§12` had, in the interim, been
  claimed on master by a *different* rule ([[§12]], the unseeable-surface rule, #88). The renumber to
  `§19` was not "the next free slot" but "the slot you meant is now something else" — a hardcoded number
  can go quietly *wrong* on master, not merely stale.
- **It leaks into source.** `feat/checkin-injury-probe` carried `#89`/`#90` in `injury_probes.py` and
  `tests/test_injury_probes.py` docstrings. Grep-and-replace across code is riskier than in an append-only
  ledger — a mis-anchored `#89`→`#133` can hit an unrelated token — so the placeholder rule must cover
  **code comments and docstrings**, not only the governance files. The documented rule names DECISIONS
  entries only; this is exactly where its scope falls short.

> **Rule going forward:** a governance number authored on a branch is written as a **placeholder token**
> (`#NEXT`, `§NEXT`, `Q-NEXT`), never a concrete number, and resolved at merge. This binds DECISIONS,
> OPEN_QUESTIONS, and FEEDBACK entries **and any `#N` / `§N` / `Q N` reference in code comments or
> docstrings**. Landing promptly reduces exposure but is not the fix — the fix is that a held branch
> carries no bet on merge order to begin with.

**Related, same read — a held branch's *state* label drifts too, not only its numbers.**
`feat/recovery-metrics-rhr` was rowed `UNSTARTED` in `BRANCHES.md` while carrying a complete feature commit
(`a4e1887`, the RHR series) — the row quoted the commit while contradicting its own label. Same underlying
failure as the hardcoded number: metadata authored on a held branch is a snapshot reality invalidates, and
contagious the same way — one row that lies forces re-verification of *every* row, as one hardcoded number
that collides forces a full renumber sweep.

*Scope note:* extending the documented `#NEXT` rule (CLAUDE.md, DECISIONS_LOG discipline, **shared block**)
to name FEEDBACK / OPEN_QUESTIONS entries and code comments/docstrings is a shared-block change, byte-identical
across both repos — logged as cross-repo propagation debt in `ROADMAP.md` NOW, not written here (writing it
in one repo alone breaks the two-master invariant). This section is the repo-local record; the shared-block
line is owed separately.

---

## 21. `git commit` succeeding proves the instrument works, not that it committed what you meant — stage governance by name ([[§17]])

**Rule:** stage governance files **by name** (`git add DECISIONS_LOG.md OPEN_QUESTIONS.md BRANCHES.md`),
never `git add -A`, and confirm `git diff --stat` names the expected files **before** staging. A commit
that succeeds is a passing positive control; it does not discriminate on *which* files it carried.

This is [[§17]]'s discriminate-on-identity principle in a new mechanism. §17's failures were a check
scoped too narrowly (a grep that matched a filename, a probe against a stale ref). Here the check was not
too narrow — it read a real signal from the **wrong source**. `c4e5da2` carried the message
*"gov: number-at-merge - #149, Q59; branch row DONE"* and committed **one file: an untracked
`.claude/launch.json`**. The intended governance edits were never made; `git add -A` found only the stray
file, and `git commit` succeeded on it. Had the tree been clean, `git commit` would have failed with
*nothing to commit* and surfaced the no-op immediately — an incidental artifact supplied exactly the
signal (`there is something to commit`) that the absent edits should have, and masked the failure. The
commit message attested the renumber; only `git show --stat` measured it (this is also [[§18]] — an
attestation read in place of a measurement). Master then carried live `#NEXT`/`Q-NEXT` placeholders past
the merge that was supposed to resolve them, invisible until a later read.

**Mitigation, concrete and cheap:** name the files at `git add`, and read `git diff --stat` before staging
— if it names fewer files than the edits should have touched, an edit did not save, which is silent. The
repair itself (`#149`/`Q59`, this entry) was staged by name for exactly this reason. No new decision: the
number-at-merge rule was not followed, not changed.


## 22. A brief that cites governance from memory sends Code to verify an invention — carry the quote or point to the entry ([[§12]], [[§18]])

**Rule:** a chat-side brief leaning on a committed `DECISIONS_LOG` / `OPEN_QUESTIONS` entry **carries
that entry's text verbatim**, or names the entry and tells Code to read it before acting — it never
paraphrases governance from memory. A remembered entry is a claim about an unseeable surface ([[§12]]):
declarative in mood, unattested in fact, and it costs a verification round every time the memory is wrong.

Three governance quotes were reconstructed from memory in one session (2026-08-02 review) and each was
wrong in a way that sent Code hunting:
- `#154` was cited as needing "a fourth relation state" and as concerning "operand provenance". Neither
  is in `#154`; both belong to `#159`, whose text reads *"adding a fourth state would be a category
  error"* and *"Operand provenance is not a resolution of a branch; it is a property of the inputs"*.
  `#154`'s branch resolutions are `excluded` / `not_excluded` / `not_assessed`.
- `#159` was quoted as "labelled and separated". The repo had **already caught this exact misquote**:
  `#160` records the brief quoting `#159` as "labelled and separated rather than merged" when the
  committed text is *"is **labelled** rather than merged"*. An entry existed only to correct the
  paraphrase — and the paraphrase recurred after it.
- The closeout's own `DECISIONS_LOG` maxima ("155 headings for a max of 158") were stale: master ran to
  **#160** at review (157 with a trailing period, 160 period-agnostic; `#161` has since landed). The number that anchors a re-aim was
  itself remembered wrong.

**Mitigation, cheap:** a brief citing an entry carries the quote, or writes *"read `#N` before acting on
this"*. This is [[§18]]'s attestation-vs-measurement in the authoring direction — a remembered entry is an
attestation, the file is the measurement — and the `#159`→`#160` loop is the proof it is not free: the
same string was paraphrased wrong twice, once after an entry was written to fix it. (The session also
recorded a related pattern — illustrations chosen from the shape of an identifier rather than from data;
those specific instances are in the session report and are not re-verified here.)

---

## 23. Defer live proof only where failure is non-destructive — and fake BELOW the defect, not above it

**What happened.** `#164` shipped custom-exercise creation with its live proof deliberately
deferred (option (b)): 61 passing tests, the enum artifact captured from Hevy's live spec, and
`Q77` filed to record that the real create→list-back round-trip was unproven. The deferral was
made explicitly, argued, and written down — the process worked as designed.

The first real use then failed, and failed in the one way the deferral had implicitly assumed
away: **destructively**. `create_exercise_template` ended `return self._check(r).json()`, the
live 2xx body was not the spec's `{"id": <int>}`, and the parse raised *after* Hevy had already
created the template. The exception unwound past the sync, so the template was live in Hevy,
absent from the local catalogue, and reported to the user as "Failed to create" — with a retry
poised to mint a permanent duplicate against an API with no delete.

**Two distinct lessons, and the second is the more useful one.**

**(1) The deferral criterion is not "how likely is failure" but "what does failure cost".**
`Q77` weighed the *probability* that the round-trip worked and judged the cost of proving it —
one permanent exercise — too high. It never asked what an unproven path would do *when* it
failed. Had it asked, the answer was available from `#164`'s own reasoning: that entry already
established that Hevy has no delete endpoint, that a create is irreversible, and that
`HevyCreateUnresolvedError` must forbid a retry precisely because the POST may have succeeded.
The ingredients for predicting a destructive failure were all in the decision that deferred it.

**Rule going forward:** when deciding whether to defer live verification, classify the failure
mode first. A path whose failure is **non-destructive and loud** (a 400, a refusal, a visible
error) may ship unproven with an `OPEN_QUESTIONS` watch-point. A path whose failure can
**corrupt state, orphan a record, or make an irreversible write invisible** must be probed live
*before* ship — the live probe is the gate, not the launch. The cost of the probe is bounded and
known; the cost of a destructive first failure is neither.

**(2) A fake installed above the defect cannot see it.** All 61 of `#164`'s tests faked either
`create_and_resolve` or the whole `HevyClient`, so every fake returned clean JSON and the real
`.json()` call never executed. The suite was thorough about *behaviour* and structurally blind
to *the boundary* — and the boundary is exactly where a third-party API's undocumented
behaviour lives. The regression tests fake `httpx.AsyncClient.post` instead, one layer **below**
the defect, so the genuine parse runs; reverting the fix fails 11 of 16.

**Rule going forward:** for any code whose job is to *interpret a third party's response*, at
least one test must fake at the **transport** layer, not the client layer. If every test for a
connector stubs the connector, the response-handling code is untested no matter how many tests
there are. Mock one level below the thing you are testing, never at it.

**The family this belongs to.** §8 recorded landed ≠ live (features inert on an unpopulated prod
substrate). This is its sharper sibling: **tested ≠ exercised**. §8's failure was a no-op — a
green suite over a feature doing nothing. This one is worse, because the unexercised path did not
sit idle; it ran, half-completed an irreversible action, and reported the opposite of what
happened. A silent no-op wastes effort. A false negative over a completed write invites the user
to corrupt their own data.

### 23.1 STANDING CHECK — the irreversible-write pre-ship gate

Not a note on this incident. A check to run against **every** decision entry before it lands,
for as long as this repo talks to a third-party API it can write to.

**The trigger is a sentence in your own how-you-know.** `#164`'s read: *"What is NOT proven: no
live create was performed."* That is a correct, honest disclosure — and it is exactly the alarm.
Any decision whose how-you-know has to admit an unexercised path should answer one question
before it ships:

> **Can the unproven operation change state in a way we cannot undo?**

- **No** — ship it. File the watch-point in `OPEN_QUESTIONS` and move on. This is the normal,
  healthy case and most deferrals belong here.
- **Yes** — the live probe is the **gate, not the launch**. Do not ship on a green suite. The
  probe's cost is bounded and knowable in advance; a destructive first failure's cost is neither,
  and it lands on the user rather than on you.

**Applies to, non-exhaustively:** any POST/PUT/PATCH/DELETE against an external API; any write
whose provider offers no delete or edit (Hevy exercise templates are the type specimen); any
migration that drops or rewrites data; any outbound message, publish, or purchase.

**Two-line version for a hurry:** *If the how-you-know says a write path is unproven, ask what
its failure costs. If the answer is "an irreversible change we then misreport", the probe is
mandatory before ship.*

**And test the boundary, not the wrapper.** The companion rule from §23 above, restated as a
check: for any code whose job is to interpret a third party's response, **at least one test must
fake at the transport layer**. If every test for a connector stubs that connector, its
response-handling code is untested no matter how many tests there are. Mock one level *below*
the thing under test, never at it. `#164` had 61 passing tests and a live-broken parse for
exactly this reason.

---

## 24. Chat cannot make verbatim claims about file content — a paraphrase does not announce itself ([[§12]], [[§22]])

**The failure.** A brief opened by stating that both repos' `CLAUDE.md` had been "read whole from
master this session," and tagged the findings that rested on it **confirmed**. What the fetch surface
actually returned was a *small model's paraphrase* of the file, shaped like verbatim quotation. The
paraphrase welded two separate bullets — the guard's and the session-open ritual's — into one
sentence, and invented a regex the guard does not contain: *"anchors on the heading form
(`^### [0-9]+`), never substring matching."* The brief then built its whole load-bearing section on
that sentence, and the section was aimed at the wrong artefact.

**Why this is worse than the truncation already known.** Both failure modes exist on the same
surface, and they are not equally dangerous:

- **Truncation is loud.** A file that cuts off at `### 56` ends mid-entry. The reader can see the
  cut, so nobody claims the tail.
- **Paraphrase is silent.** It reads as clean, complete, and quotable. There is no artefact of the
  loss — the sentence that was never in the file looks exactly like the sentences that were. It is
  **structurally unfalsifiable from the chat side**: asking for verbatim and receiving prose shaped
  like verbatim is indistinguishable, from there, from asking for verbatim and receiving verbatim.

**The rule.** Chat may not assert file content. Not "verbatim," not "read whole," not a quoted regex,
not a quoted heading form, not a line count, not a max. Any brief containing those is **overclaiming
by construction**, whatever confidence tag it carries — the tag is generated from the same surface as
the claim. Chat's legitimate outputs about a file are *hypotheses naming what would settle them*: not
"the anchor is `^### [0-9]+`" but "I believe the anchor is health-app-pinned; `grep -nE '^### '` in
each repo settles it."

**How Code applies it.** Treat every quoted artefact in a brief the way [[§12]] treats a declarative
about an unseeable surface — as an instruction to verify, never a report of fact — and **re-derive it
against the tree before acting on it or dismissing it.** Dismissal is the half that is easy to skip:
the brief that produced this row was wrong about *which file* carried the defect and right that a
defect existed, so "the brief was wrong about the script" would have shipped the real hole intact.
A misaimed finding is not a false one. Run the check the brief should have named, even when the
brief's own version of it does not survive contact.

**Why this row and not a project-instruction edit.** It is a rule about what chat may assert, and
`CLAUDE.md` governs Code — so its natural home is the UI-maintained project instructions, which Code
cannot write and which are therefore an unseeable surface ([[§12]]) that would carry no evidence of
having been updated. Landing it here instead keeps it tracked beside the other instrument-honesty
findings, in a store Code can verify. Operator's call, taken 2026-08-04.

**Earned:** the propagation brief of 2026-08-03, three overclaims in one document. Companion to
[[§22]] — that row covers citing governance from memory; this one covers citing it from a fetch that
paraphrases. The instruction "carry the quote" is only safe if the quote is bytes.

---

## 25. A fail-closed contract and a fail-opaque handler compound into an undiagnosable defect ([[§17]], [[§23]])

**What happened.** A genuine urine-ACR report could not be saved. Two independent, individually
survivable decisions met on the same request path:

1. **The request contract was stricter than the extractor's honest output.** `FieldConfidence`
   demands a `float` confidence for `ref` on every row, including a row whose reference interval
   does not exist on the page — a shape the extraction schema itself documents
   (`LAB_EXTRACTION_SCHEMA §4`, absent-ref). The model has nothing truthful to put there.
2. **The one field that would have named the mismatch was thrown away.** The banner read
   `typeof detail === 'string' ? detail : detail?.error`, and a Pydantic 422's `detail` is an array
   of `{loc, msg, type}` — neither a string nor an object with `.error`. The rejection collapsed to
   "Failed to save report".

Alone, (1) is a 422 the user reads and reports. Alone, (2) is an opaque banner over faults that are
mostly self-evident from context. Together they are a document that cannot be ingested and a system
that cannot say why — and, worse, **every** future extraction failure of any shape presents as the
same six words.

**Why this is not just "handle the error better".** The two failures sit in different repos-worth of
concern — a backend Pydantic model and a frontend catch block — reviewed at different times by
different reasoning, each locally defensible. Strictness in a request schema is normally a virtue;
a generic fallback banner is normally courtesy. Neither review could see the other. The compounding
is only visible on the **path**, which is why it survived both.

**Rule going forward — two arms, and the second is the load-bearing one.**

**(a) Validate a request contract against the real extraction corpus edge cases, not against the
happy row.** A field that is *structurally* optional (`field_confidence` as a whole) but whose
*sub-fields* are all required is a contract that accepts "I did not assess this row" and rejects
"I assessed this row and one field honestly has no value". Where a schema documents an edge case
(`§4`'s absent-ref), the request model must be checked against that case explicitly.

**(b) Never let a catch block collapse a structured error into a constant string.** A fallback
message is only honest for the case where the response carries **no** structure — transport
failure, no body. When the server *did* explain itself, discarding that explanation is strictly
worse than crashing: a crash is investigated, a plausible banner is believed. Reserve the constant
for genuine absence and render what was actually returned.

**The corollary that made this session tractable.** When a defect's evidence has been eaten by the
error handler, **fix the handler first and separately** — as its own defect, on its own merits,
without waiting to know the answer. It is the only move available before the evidence exists, and
it is what manufactures the evidence. Shipping the *suspected* contract fix alongside would have
been a guess dressed as a repair, and a green result afterwards could not have distinguished "we
fixed it" from "we changed something and the model happened to emit a `ref` that run". Hence the
two-move split: the instrument lands, the contract change is **held** at an `OPEN_QUESTIONS` row
until the live `loc` scopes it.

**The family this belongs to.** §17's "a check whose failure cannot stop what follows is not a
check" is the enforcement sibling; this is its *reporting* sibling — **an error whose content
cannot reach the reader is not an error message.** §23's tested ≠ exercised is the nearest
relative: there, a fake above the defect could not see it; here, a handler above the defect could
not report it. Both are cases of the instrument sitting on the wrong side of the thing it exists to
observe.

---

## 26. In a semi-structured extraction target, every non-Optional scalar is a latent fail-closed point — audit them as a class ([[§25]], [[§17]])

**What happened.** The second instance of §25's family, found the same week. A urine ACR report
could not be ingested: its lead row has no reference interval, the extractor emitted
`ref_high_exclusive: null` — correctly, since with no bound there is nothing to be exclusive about —
and `ResultItem` declared a bare `bool`. Pydantic refused the body before the handler ran.

§25's rule ("validate a request contract against the real extraction corpus edge cases") was
already written and would have caught this had it been *applied as an audit* rather than read as
advice about the field then under suspicion. It was not applied, and the same class produced a
second outage on a different field one report later.

**The generalisation, which is the point of this entry.** In a contract that receives a model's
reading of a semi-structured document, **every non-Optional scalar is a place the request can fail
closed**, because document rows are sparse in ways the schema author does not enumerate in advance:
ref-less, censored (`<5`), qualitative, one-sided, unitless. The model is not misbehaving when it
sends null — it is honestly reporting that the source has nothing there. A contract that treats
"the source is silent here" as a validation error will refuse genuine documents, and will do it one
field at a time, each looking like a fresh bug.

**Rule going forward — audit, don't wait.** When a contract parses extracted documents, enumerate
its non-Optional scalars as a **set** and ask of each: *can a legitimate sparse row have nothing to
put here?* Fix the whole set in one pass. Then **encode the audit as a test**, so a field added
later as a bare scalar trips in the suite instead of in production. The mechanical form is cheap —
walk `model_fields`, probe each with `None`, assert the survivor set is exactly the fields that are
genuinely always present.

**Prefer coercion to loosening, when a correct default exists.** Where the absent case has a right
answer (`None` exclusivity means `False`; there is no bound to be exclusive about), coerce in a
`mode="before"` validator and keep the declared type strict. Loosening the type to `| None`
propagates the null into storage and buys a migration; coercing keeps the contract honest and the
column non-nullable. Loosen only when null genuinely *means* something distinct downstream.

**And the reason to check it is inert.** A coercion is safe when the value it invents is never read
on the rows it touches. Here every consumer reads the flag inside a bound-is-not-None branch, so a
coerced `False` on a bound-less row changes no behaviour. Verify that; do not assume it. A coercion
on a field that *is* read is a silent data change wearing a bugfix's clothes.

**The lesson §25 earned, now demonstrated — build the instrument, don't ship the guess.** The
chat-side hypothesis named the wrong field **twice**: `#177`'s brief predicted
`field_confidence.ref`, and `Q85` offered `field_confidence.*` or
`source_completeness`/`panel_name_raw`. Both were argued carefully from the code and both were
wrong. The actual field — a non-Optional exclusivity bool — appeared in neither list. What settled
it was one live extraction printing its own `loc` through the banner `#177` fixed.

Had the suspected `FieldConfidence` change shipped alongside `#177`, it would have changed a
contract that was working, on no evidence, and the retry would still have 422'd — on a field nobody
was looking at, with the "fix" already banked as the explanation. **The instrument is not overhead
on the way to the fix; on a failure whose cause is a runtime artifact, it is the only thing that can
tell you which fix to make.** Reserve tracing for narrowing the search. Let the instrument name the
field.

---

## 27. The null-on-sparse-row class, closed — the enumeration that says when it is re-opened ([[§25]], [[§26]])

**What happened.** The third and final move against the family §25 and §26 name. `#177` built the
instrument that made a fail-closed contract legible; `#178` cured the first captured instance
(exclusivity bools); `#179` closed the last known one (`FieldConfidence` floats) **before** it fired,
because by then the pattern was proven and the trigger shape was known to exist.

**The enumeration, recorded so a re-opening is recognised as one.** The request contract's non-Optional
scalars fall into two classes, and only one is a bug when a sparse row nulls it:

- **Row-level (tolerate the sparse row).** `ResultItem` and its nested `FieldConfidence`. A document
  row is legitimately sparse — ref-less, censored, qualitative, one-sided — so a null here is the
  extractor being honest, and the contract must accept it. After `#178` + `#179` the only row-level
  non-Optional scalar left is `ResultItem.marker_name_raw`, which is always present on a row that
  exists at all. **This class is now closed, and a test asserts it closed** (`model_fields` walk;
  see `#179`). Adding a new bare-scalar field to `ResultItem` or `FieldConfidence` re-opens it — and
  trips the test rather than production.
- **Report-level (fail closed on purpose).** `ReportEnvelope.lab_name`, `panel_name_raw`,
  `source_completeness`. A report missing its lab name or panel identity is a genuine extraction
  fault, not a sparse row, and should be refused — loudly, now that `#177` makes the refusal
  readable. If the extractor ever nulls one, the fix is in extraction, not the contract. This is
  `Q86`'s standing watch-point.

**The rule.** When adding a required scalar to an extraction-request contract, decide which class it
is *before* choosing its type. Row-level → Optional (and treat null as absent everywhere it is read).
Report-level → required (and treat a null as a fault to surface). Getting the class wrong in either
direction is a defect: a required row-level field bricks legitimate documents; an Optional
report-level field swallows a real extraction failure.

**Loosen vs coerce, settled across the three moves.** Same class of bug, two correct-but-opposite
repairs, and the discriminator is whether the absent case has a safe default. Exclusivity bool: yes
(`False` — nothing to be exclusive about), so coerce and keep the type strict, no migration
(`#178`). Confidence: no (neither `0` nor `1` is honest), so loosen to `| None` and make every
consumer treat null as absent (`#179`). "Loosen the contract" is not automatically the fix; it is the
fix only when the field has no truthful default, and coercion is better when it does.

**The meta-lesson, now demonstrated three times and worth stating plainly.** Across these moves the
**chat-side field/scope claim was wrong or overstated every time**, and the **tree or the instrument
was right every time**:

- `#177`'s brief predicted the offending field was `field_confidence.ref`. Wrong.
- `#178`: `Q85` predicted `field_confidence.*` or `source_completeness`/`panel_name_raw`. All wrong —
  it was a non-Optional exclusivity bool, in nobody's list. The live banner named it.
- `#178`'s own brief claimed fixing the exclusivity pair "closes the class completely". Overstated —
  the tree audit found `FieldConfidence` still open, which is the entire reason `#179` exists.

None of these were careless; each was argued from the code. The point is not that chat reasons badly
— it is that a hypothesis about a runtime artifact (what the model emits on an awkward row) cannot be
settled by reading source, only by capturing the artifact or exhaustively enumerating the contract.
So: **reserve chat-side tracing for narrowing the search; let the instrument name the field and the
tree bound the class.** "Code adjudicates" is load-bearing, not ceremony — it is what turned three
confident wrong guesses into three correct fixes.

---

## 28. The §7 unit guard held on real over-collapse pressure — a designed-for case finally exercised on data

**What happened.** `#180` added the first specimen-typed markers to the canonical map — three
urine-ACR analytes that each share a token with a serum marker already mapped (`R U-Creatinine` vs
`Creatinine`, `R U-Albumin` vs `Albumin`). This is the exact collision `LAB_EXTRACTION_SCHEMA §6/§7`
built the over-collapse guard for, and until now the guard had only ever been reasoned about, never
put under real pressure — no two markers in the map had ever actually shared an analyte.

It held, and the test proves it discriminates rather than merely passing: a `R U-Creatinine` row at
urine `mmol/L` maps and writes; the *same* row at serum `umol/L` is refused with a 422 that names
both units. Two independent barriers, not one — exact-string keying (different key from the serum
entry) and the unit guard (different `unit_established`) — so a mis-key alone or a mis-unit alone is
each caught.

**Why it is worth a ledger note and not just a passing test.** A guard that has never fired on real
input is a claim, not a control — the same trap as `§8`'s landed≠live and `§23`'s tested≠exercised.
Design-time confidence in the guard was reasonable but unearned; this is the first time the 1000×-gap
protection did work on data with a genuine homograph. Recording it converts "the guard should hold"
into "the guard held, here, on this collision", which is the difference the whole DECISIONS_LOG
*How-you-know* discipline turns on.

**The transferable rule.** When you add the first instance of a case a guard was written for — the
first shared analyte, the first duplicate key, the first cross-tenant row — do not treat the guard's
existence as coverage. **Exercise it in both directions in the same change**: one input that must
pass, one that must be refused, asserting the refusal names its reason. A guard is only known to
discriminate once something has actually been on both sides of it.

**The companion caution, carried from `#180`.** The guard's discrimination is only as good as the
`unit_established` byte-string it compares against. Set that from what the extractor actually stores,
not from the clinically-correct unit — they are usually the same and occasionally not (case, µ vs u,
spacing), and a mismatch turns the guard from protection into a false refusal on legitimate data.
`#180` left that precision check OWED against prod for exactly this reason; the saving grace is that
`#177` made the resulting 422 legible, so the failure names itself instead of hiding.


---

## 29. Railway's dashboard query editor silently no-ops a multi-statement paste — one statement per prod check ([[§10]], [[§11]])

**What happened.** The 2026-08-16 operator session ran three OWED prod verifications through the Railway
dashboard's query editor. The Q18 sweep was pasted as a multi-statement block — the natural shape for a
15-field `NOT BETWEEN` check — and came back with **no rows**. Read at face value that is exactly the
answer Q18 wanted: zero out-of-range rows, sweep clean, close it. The close was nearly written on that
basis. What actually happened is that the editor executes a multi-statement paste as a silent no-op: it
returns 0 rows and no error. The tell was `SELECT current_database()`, pasted alongside another statement,
which also returned nothing — a query that cannot legitimately return zero rows. Re-run one statement at a
time, the sweep returned its real result (also zero violators, as it happens) and the schema and record-type
checks returned their real contents.

**Why the right answer by luck is still an instrument failure.** Q18's true result and the false-negative
result were the same string: zero rows. Had a violator existed, the multi-statement paste would have
reported clean, the sweep would have been recorded as run, and a corrupt row would have survived a check
whose entire purpose was to find it. The finding is worth recording precisely because the outcome was
benign — the mechanism is not. This is `§10`'s false-green instrument in its purest form (an unsound
measurement reporting zero) compounded by `§11` (a probe that presumes its own answer and does not fail
loudly when it never reaches the subject).

**The transferable rule.** **One statement per run for any prod check through the Railway dashboard editor.**
And more generally: when an instrument's clean result is byte-identical to its failure result, the instrument
needs a positive control that cannot return the clean value — here, a `SELECT current_database()` or a
`count(*)` known to be non-zero, run through the same path. If the control comes back empty, the measurement
did not happen, whatever the subject query appeared to say.

---

## CLAUDE.md provenance (pre-prune, master @ 4bd99cc, 2026-08-09)

The full pre-prune `CLAUDE.md`, verbatim. The governance-prune session compressed the shared
block to invariants-only and stripped the “Earned…” narratives, rejected-alternative
discussions, and incident retellings from the repo-specific sections. None of that reasoning is
deleted — it lives here.

<details>
<summary>Full pre-prune CLAUDE.md</summary>

````markdown
# CLAUDE.md — health-app

Read this in full at the start of every Code session. It is the contract the
session rituals enforce and the loop conforms to. If a pasted document, prior
summary, or habit contradicts this file, this file wins.

---

## Orientation (this repo)

- `health-app` — FastAPI (Python) backend + React/Vite frontend, deployed on Railway.
- Part of a three-module health intelligence platform — Fitness, Medical Protocol,
  Decision Support — on a shared event timeline. It is a health intelligence platform,
  not a fitness app.
- Companion app is a separate repo (`health-connect-app`, Expo React Native, Android-first).
  Not in this tree.

---

<!-- ════════════ BEGIN SHARED LOOP RULES ════════════ -->

## Shared loop rules — edit in `health-app`, propagate verbatim

*Everything from this heading down to "END SHARED LOOP RULES" is identical across every
repo in this project. Edit it only here, then copy it verbatim into
`health-connect-app/CLAUDE.md` and any future repo. Never edit a copy in place — that
re-creates the two-master drift this whole model exists to kill.*

***Verbatim propagation replicates a defect at full fidelity.*** *Copy-not-hand-merge kills
drift, and it silently assumes the source is the better copy. It is not always: on
2026-08-04 the destination's wording of the session-open rule was **generic and correct**
where `health-app`'s was pinned to `health-app`'s own heading grammar and returned zero
against the destination's file. Copying would have replaced a correct line with a broken
one. So before any copy, **verify the source's rule against the destination's actual
shape** — run the regex, count the store, check the paths exist. If the source is wrong,
fix it here first and copy after; never fix it in the copy, and never hand-merge the two.
The verification is a precondition of propagation, not a review of it.*

***What belongs in this block at all — the boundary criterion.*** *A rule belongs here only
if its correctness is independent of any surface outside the tree. Invariants qualify:
number-at-merge, terminal-state disposition, patch-id over ancestry, concern-named branches,
single-writer. **Mechanics that depend on unversioned config do not** — they go below
`END SHARED LOOP RULES`, in the repo whose config they describe. The rejected alternative was
a shared rule conditioned on whether the repo has a required status check; that fails on its
own terms, because the check's existence is invisible from the tree, so a reader could not
tell which branch of the rule applied to the repo in front of them. A rule that reads
differently in each repo is a divergent rule wearing a shared rule's clothes — worse than an
honest split, because the empty-diff check still passes. Earned 2026-08-05, when `health-app`
adopted a PR-gated merge path and `health-connect-app` had no CI workflow at all to gate one
with (`#171`, `#172`).*

### The loop (source-of-truth model)

- The **repo is the single source of truth** for all volatile state.
- **Code is the only writer.**
- **Chat proposes; chat never commits.** The claude.ai GitHub connector grants chat
  read/attach only. Any instruction that has "chat commits", "chat writes a spec to the
  repo", or "chat files an issue" is wrong on this surface — chat emits text, a human or
  Code carries it across, Code/Action writes it.
- **The commit is the only sync point. Truth changes only at a commit.** Anything decided
  in chat is *pending* until a commit lands it. Treat an uncommitted decision as
  provisional, not done.
- **Read-back path:** repo → chat via Projects sync (the repo file is mirrored into the
  project and refreshed automatically), or by attach. Chat reads the mirror already in
  context; it keeps no separate editable copy.
- **Kill-rule:** decisions, open questions, roadmap, and task state are **never** saved
  into Claude.ai project knowledge. That is the exact mechanism that produced the drift
  this model exists to kill. Project knowledge holds stable orientation docs only.

### The unseeable-surface rule

Chat can verify only what is on a pushed ref. Any brief statement about a surface chat cannot
read — UI-maintained knowledge files, unpushed branches, local disk, Railway/prod state, the
operator container — is an INSTRUCTION TO VERIFY, never a report of fact, regardless of how it
is phrased. Declarative mood does not make it attested. Verify against the surface or STOP and
report; never land on it.

### Canonical stores

| Store | Holds | Discipline |
|-------|-------|-----------|
| `DECISIONS_LOG.md` | Architecture decisions | Append-only. Supersede via a new entry that references the superseded number. Never edit a locked entry in place. |
| `OPEN_QUESTIONS.md` | Undecided forks, unverified-at-machine items | One status per item, from the four states — see **State vocabulary** below; that section is the sole definition. `DONE → #N` names the decision that resolved the question, as `DONE` names its SHA in `BRANCHES.md`. |
| `ROADMAP.md` | Current sprint + horizon | Mutable. Code updates it at close-out. |
| `FEEDBACK.md` | Behavioural corrections and standing rules | Repo-canonical. Code reads it at session start. The project-knowledge copy is a refreshed mirror, not the master. |
| `ptb-tasks` (external board) | Task status | Single live board. Mutable. Referenced by task ID — never mirrored into the repo. |
| pending-commit queue | The chat → Code handoff payload | Transient. Emitted by the chat close-out as canonical-format entries flagged `PENDING`. Carried by paste, or materialised as a GitHub issue for `@claude`. Consumed at the next Code open, then discarded. Not a stored repo file. |

**Stays in project knowledge, never in the repo** (stable, chat-analysis context):
`Clinical_Protocol`, `Athlete_Profile`, lab PDFs, `Stack`, `API_CONTRACTS`,
`Hevy_Pattern`, `Readiness_Algorithm`.

### State vocabulary

Four work-states, exhaustive, no fifth. Applies to `BRANCHES.md` Status, `ROADMAP.md`, and
close-outs. `OPEN_QUESTIONS.md` uses the **question-state** axis below instead — a question is
not a work item.

- **DONE** — landed on master (SHA) or applied to a named UI file. Nothing further required by
  anyone.
- **BLOCKED** — cannot proceed; names the blocker and its owner. A trigger for when work
  becomes *worth* doing is not a blocker on its being *possible* — that is UNSTARTED.
  Where the evidence does not settle whether a dependency is a barrier or a trigger,
  the row is UNSTARTED: a false BLOCKED tells a reader not to try.
- **OWED** — work or decision settled, loop not closed; names the exact command or check
  outstanding.
- **UNSTARTED** — untouched.

No "in progress": half-done work is **BLOCKED** (has a blocker) or **UNSTARTED** (doesn't).

**Question state (`OPEN_QUESTIONS.md` only).** The four work-states do not fit a question — an
untouched question is a live fork, not "UNSTARTED", and a question awaiting a dependency is not
"BLOCKED". A question carries exactly one state, under the sole label `**State:**` (never
`**Status:**`):

- **OPEN** — the fork is live; no decision answers it yet. A question gated on a dependency
  before it is *worth* deciding is OPEN with a `**Blocked by:**` note — not BLOCKED.
- **OWED** — the fork is decided, but a named verification or loop-close is still outstanding
  (mirrors the work-state OWED).
- **DONE → #N** — resolved; decision `#N` is the answer (mirrors the work-state `DONE → #N`).

### DECISIONS_LOG discipline

Preserve the existing entry format:

> **Decision · Rationale · Status · How you know · Do not revisit unless**

- Append-only. To change a decision, add a new entry that supersedes the old one by
  number. Do not edit a locked entry's text — the history is the point.
- Every decision that gates code carries a **How you know** artifact: a confirmed test, a
  verified search result, or official documentation. "The API has a field for it" is
  insufficient. Founding rule, earned from the HRV pipeline failure.
- **Number-at-merge.** On a branch, a new entry is headed `### #NEXT`. The integer is
  claimed only when the governance commit lands on master (next sequential at that
  instant). Eliminates the two-branches-both-claim-#N collision and the
  renumber-on-`--ff` dance. Stated against *landing*, not against any one merge motion —
  the motion is repo-local and differs between repos; this rule does not.
- **Number-at-merge names its window.** Resolving `#NEXT` and landing it are two acts, and
  master can advance between them. So resolve **immediately before** merging, having re-read
  master's max at that moment — not at session open, not from a prior report — and if master
  advances in the interval, **re-resolve before merging**. The window is small, never zero,
  and an unnamed race is how `#162`'s hole rode four sessions. A repo may have a mechanism
  that forces a pause when master advances; a forced pause is not an adjudicated number, and
  the re-read is owed either way. The guard refuses an unresolved *placeholder* reaching
  master — it has no opinion on whether the integer you resolved to was still free.
- **Number-at-merge is ENFORCED, not trusted.** `scripts/check_governance_placeholders.py`
  refuses any push to master whose `DECISIONS_LOG.md` still carries `^#{2,3} #NEXT` or whose
  `OPEN_QUESTIONS.md` still carries `^#{2,3} Q#NEXT`. It guards the **ref**, not one command:
  the merge that made this necessary was done by hand, so a guard living inside the `land`
  alias would not have fired. Branch pushes are untouched — a placeholder is *correct* on a
  branch and only wrong on master. Anchored on the heading form, never a substring, because
  the rule text and every corrected entry legitimately quote the token (`#113`). The anchor
  tolerates the heading **level** and never the **form**: the repos disagree on level —
  `health-app` heads a question `## Q77.`, `health-connect-app` heads it `### Q8 — …` — so a
  level-pinned pattern reads one of them as permanently clean, which is a guard that is
  installed, green and blind. One rule, one implementation, matched to each repo's grammar.
  Install once per clone, alongside the aliases: `git config core.hooksPath .githooks`.
  Bypass is `git push --no-verify`, and needing it twice is a signal the ritual is wrong,
  not the guard. Earned: the placeholder reached master three sessions running and left a
  permanent hole at `#162`.

### Session rituals (the contract the close-outs conform to)

The trigger is not the payload. The payload is defined here; the snippet/command bodies
must match it.

- **Session open** — at session start, before acting on any brief, Code reports **both**
  maxima: the `DECISIONS_LOG.md` max decision number, counted with `^### #?[0-9]+`, and the
  `OPEN_QUESTIONS.md` max question number, counted with `^#{2,3} Q[0-9]+`. Never
  `^### [0-9]+\.`, never `^### [0-9]+`, never `^## Q[0-9]+`. **Period-agnostic** because
  `health-app` entries `126`–`128` carry no trailing period and a period-requiring sweep
  undercounts by three and invents phantom gaps (verified 2026-08-02). **Sigil- and
  level-agnostic** because `health-connect-app` heads a decision `### #21 — …` and a
  question `### Q8 — …`, against `health-app`'s `### 166.` and `## Q77.`: the pinned forms
  return **0 / 78** and **0 / 168** across the two repos (verified against both trees
  2026-08-04). A sweep that returns zero does not look broken — it looks like an empty
  store, at the one moment whose entire job is establishing canon. **Both arms are named
  because only one used to be**, and the missing arm was filled in by analogy to the arm
  that was there — which is how a health-app-shaped `^## Q` got reached for. Chat re-aims
  any brief against these, so a stale project copy never masquerades as canon.
- **Chat close-out (`;cc`)** emits the **pending-commit queue**: canonical-format
  `DECISIONS_LOG` / `OPEN_QUESTIONS` entries for everything decided that session, each
  flagged `PENDING`, ready to paste or file as an issue with zero reformatting. Writes
  nothing to project knowledge.
- **Code close-out (`/closeout`)**:
  1. Reads the canonical stores.
  2. Reports the **actual commits** made this session (`git log` since open) — not
     suggested commit messages. Additionally emits
     `git log --format="%ad %s" --date=short -10` so the handoff carries the repo's own
     record — commit dates are immutable and cannot drift, where a self-reported stamp can.
     (This binds here, not in `closeout.md`: that file is session-local and overwritten every
     close-out, so a rule left only there would not survive.)
  3. **Reconciles the pending-commit queue**: confirms each `PENDING` item landed in a
     commit, or states why not.
  4. **Branch terminal-state gate** — every branch touched this session ends
     merged+deleted or listed in `BRANCHES.md`; none in undefined limbo. The gate
     enumerates local branches (`git branch`) as well as `refs/remotes/origin`; a local
     branch with `+` commits vs `origin/master` must be pushed, parked in `BRANCHES.md`,
     or discarded before close. If any touched branch is neither, the close-out HALTS
     until resolved.
  5. Regenerates the cold-resume handoff view from the stores.
  6. Overwrites a single `closeout.md`. Never appends narrative; never describes the act
     of writing the close-out.
  7. Writes the close-out body verbatim to `closeout.md` and prints only a terse pointer to
     stdout — path, branch, single next action, and the filenames of governance stores
     changed this session (`DECISIONS_LOG` / `OPEN_QUESTIONS` / `ROADMAP` / `FEEDBACK` /
     `Ideas`; names only, never contents). It does not emit store text; pre-merge copy-back
     is `cat`/open of the changed store file on disk. Chat replaces the project copies
     wholesale from those files and never regenerates these stores from memory.
- `/compact` is mid-session context compression, **not** a close-out. Do not conflate.

### Project-wide standing rules

- **Windows / PowerShell only.** No Linux syntax — no `head`, no backslash line
  continuation. Single-line, or PowerShell backtick continuation.
  **PowerShell-safe is not the same as Linux-syntax-free, and the difference is a quoting
  bug, not a style one.** PowerShell re-quotes arguments when it hands them to a native
  executable, and **embedded double quotes do not survive** — a single-quoted PowerShell
  string containing `"` reaches `git`/`gh` split across several arguments. It fails with
  whatever that program says about wrong argument counts, never with anything naming quoting:
  `git config --local alias.land '…"$(git branch --show-current)"…'` returns
  `error: no action specified`, which reads like a missing flag. **So a command written for
  this project must avoid embedded double quotes in its argument, not merely avoid `head`**,
  and a command Code emits for Luke to run must be exercised in **PowerShell** — Code's own
  Bash tool passes these strings cleanly and will never reproduce the failure. Earned
  2026-08-05: the `land` body documented at `#171` was Bash-verified, committed, and then
  refused on first use.
- **Verify before design.** Verify data paths end-to-end before designing against them.
  Standing rule after the HRV pipeline failure.
- **Empirical specificity.** A recorded test result must state the exact pathway
  exercised and the payload returned — never the generalised conclusion. "X is not
  available via AccessLink" is an assertion; "the exercise summary JSON returned no
  per-second field" is a fact. A negative is only as broad as its recorded scope — do
  not widen it to the whole route/API/device. Mirror of the rule above: as "the API has
  a field" doesn't prove capability, "a test failed" doesn't prove absence.
- **Device-agnostic schema.** All health data is normalised to a `source`- and
  `confidence`-tagged schema before any algorithm or AI layer. The intelligence layer
  never references device-specific schemas.
- **Data verification = Postgres query against Railway**, not on-device UI.
- **Never run a command that renders a secret value.** Includes `railway variables` in
  any form (`--kv`, `-k`, `--json`, the `variable` singular, and the bare `list` — the
  CLI's own help states that both `--kv` and `--json` print raw values), `printenv`,
  `env`, and reading any `.env` by any tool or alias. **To check existence**, read names
  or presence. **To use a value**, inject it with `railway run <cmd>` — the value enters
  the child process and never the transcript. **To compare values**, compare SHA-256
  digests, first 12 characters, both sides. Earned twice: a `--kv` invocation put a live
  Postgres credential into four session transcripts, and a `.env` grep matching key
  *names* printed a live API key and a Fernet key while establishing that nothing had
  been printed. `.claude/settings.json` carries deny patterns as a second layer; it is a
  speed bump, not the enforcement — this instruction is (DECISIONS_LOG #111).
- **Branch disposition (patch-id, never SHA).** Merged-vs-pending is decided by
  `git cherry origin/master <branch>` (`-` = patch-upstream, delete; `+` = real work),
  never `merge-base`/`rev-list` — rebase/squash merges rewrite SHAs and make ancestry lie.
  Every branch not master lives in `BRANCHES.md` (repo root) until merged+deleted.
  Install once (git `!` aliases run in git's own sh; the invocation is single-line
  PowerShell-safe):
  `git config --global alias.stale '!f() { git fetch origin -q; git cherry origin/master "${1:-HEAD}"; }; f'`
  `git config core.hooksPath .githooks`  (per clone, not global — the hook is repo-versioned)
  **`stale` is global because disposition is an invariant — every repo decides it the same
  way. The merging alias is not here, and is no longer global.** How a branch *reaches*
  master depends on enforcement config that exists in one repo and not another, so it is
  repo-local by the boundary criterion above, and a `--global` alias cannot hold two bodies.
  Each repo defines its own `land` with `git config --local` and documents it below its own
  `END SHARED LOOP RULES`. **Repo-local config is NOT cloned**, so that alias joins
  `core.hooksPath` as per-clone setup a fresh checkout silently lacks — two unversioned things,
  both absent by default, neither of which announces itself. Every repo lists its full
  fresh-clone setup below its own `END SHARED LOOP RULES`; do not assume a clone is configured
  because the repo is. Disposition, the ledger, and the terminal-state gate are unchanged by
  this and remain shared.
- **Branch naming & reuse.** One branch per concern, concern-named
  (`fix/validatenight-dedup`), reused across sessions until merged. Claude Code
  `claude/<session-hash>` auto-names are banned for in-flight work — they spawn duplicates.
- Full behavioural corrections live in `FEEDBACK.md`. Full decision history lives in
  `DECISIONS_LOG.md`. This file points at them; it does not duplicate them.

## END SHARED LOOP RULES — repo-specific below

<!-- ════════════ END SHARED LOOP RULES ════════════ -->

---

## Repo-specific — health-app

### Merge path — PR-gated, terminal-driven (#171)

**The pull request is the only route to master.** Ruleset `master-pr-gated` (id `20414758`)
requires a PR, requires the `placeholder guard (POSIX)` status check, forbids
non-fast-forward, and carries **no bypass actors** — `current_user_can_bypass: "never"`, so
the rule binds the repo owner holding an admin token. Direct `git push origin master` is
refused server-side. This is the only surface in this project that can *refuse* a bad merge
rather than report one afterwards.

**This section sits here and not in the shared block by the boundary criterion above:** a
merge path depends on enforcement configuration — a ruleset, branch protection, a required
status check — which lives outside the tree and is set per repo, so its correctness is not
independent of a surface the tree cannot see and it cannot be a shared-block rule. What any
other repo has or lacks is read live (`gh api`), never asserted here: a file has no means to
keep a claim about another repo current, so it does not originate one (`#184`).

- **The motion.** Push the branch, open the PR, then merge — as three acts, not one:
  `git push -u origin <branch>` → `gh pr create --fill --base master` → `gh pr merge --merge
  --delete-branch`. Never `--auto`: it queues the merge to fire later, and a merge instant you
  do not hold cannot satisfy number-at-merge. Never `--admin`: it is advertised in `gh`'s own
  refusal text and does not work here (verified), so reaching for it only hides the real error.
- **`--merge`, not `--squash` or `--rebase`.** Not a `git cherry` question — patch-id
  disposition survives all three, which is why it was chosen. The decider is `BRANCHES.md`,
  whose rows record landing SHAs: squash and rebase rewrite the branch's commits at merge, so
  every recorded `DONE <sha>` would point at an object unreachable from master. `--merge`
  preserves them. The cost, accepted: master is no longer linear.
- **Strict mode forces a pause, and a pause is not an adjudication.** The required check is
  strict, so a branch behind master cannot merge — if master advances between resolving
  `#NEXT` and merging, the merge blocks until the branch is updated and the guard re-runs.
  That makes the shared rule's window *visible*; it does not tell you the integer you claimed
  is still free. Re-read master's max and re-resolve. **Mechanically-forced pause, manually-
  adjudicated resolution.**
- **The alias is thin on purpose.** `land` is repo-local (`git config --local`), because the
  global one cannot hold both repos' bodies. Adjudication logic does **not** go in it:
  `~/.gitconfig` and `.git/config` are unversioned, per-machine, and invisible to review —
  the least durable surface available, which is the exact property that made the placeholder
  guard necessary in the first place. Uniqueness-and-gaplessness belongs in the guard, where
  it binds every path and every clone. `stale` stays global and unchanged.
  **Thin also means no `!f() { … }; f` wrapper and no subshell.** That shape exists to handle
  `$1`, and `gh pr merge` needs no argument — "without an argument, the pull request that
  belongs to the current branch is selected" (`gh pr merge --help`). Dropping it removes the
  embedded double quotes, which is what makes the body enterable from PowerShell at all: see
  the PowerShell-safe rule above. `stale` keeps its wrapper because it genuinely takes `${1}`,
  and its `"${1:-HEAD}"` is why `stale` must be installed from a shell that preserves quotes
  (it was, once, and has not needed reinstalling since).

**Fresh-clone setup — health-app.** Two unversioned settings, both absent in a new clone, and
neither fails loudly: a missing hook means placeholders push without complaint, and a missing
alias means `land` is simply not a command. Run both, then verify:

    git config core.hooksPath .githooks
    git config --local alias.land '!gh pr merge --merge --delete-branch'

`git config --get core.hooksPath` must return `.githooks`. For the alias the check **must be
`git config --local --get alias.land`** — with `--local` omitted, `git config --get` reads the
*merged* config and happily returns the **old global ff-only body**, so an unconfigured clone
reads as configured while carrying an alias the ruleset refuses. Verified 2026-08-05: the bare
form returned the global body on a clone where the local alias was absent. A control that
cannot tell the two apart is not a control (`#103` — discriminate on identity, not function).
`stale` is global and comes with the machine, not the clone. The ruleset
is server-side and needs nothing locally — but it is the reason a missing `land` is an
inconvenience rather than a hazard: without it the merge simply is not made, and the old
ff-only body would be refused by the server anyway.

**Batched governance landings (#176).** Governance/docs-only edits — touching only
`DECISIONS_LOG`, `OPEN_QUESTIONS`, `BRANCHES`, `ROADMAP`, `CLAUDE.md`, `FEEDBACK`, `closeout.md`,
**no code and no migrations** — bank onto a single branch and land as **one PR per checkpoint**;
individual items do not get their own PR. Emergent findings append to the open branch, never a new
PR. Three invariants:

- **(a) Nothing lands until its design has settled.** An entry with unresolved preconditions stays
  on the open branch, not on master.
- **(b) Housekeeping rides its originating branch.** The branch writes its own terminal `BRANCHES`
  row and any Recent-landings pointer *within itself*, resolved at merge — so no merge owes a
  follow-up PR.
- **(c) Gate by diff shape, not file class.** A governance batch lands guard-gated **only if every
  removed line falls inside a region the change explicitly declares it is replacing** (a `State`
  block, a corrected row). **Any removed line outside a declared replacement region forces human
  review** — because the guard anchors on placeholder *headings* and cannot see content corruption.
  Earned 2026-08-05: a `#NEXT` blanket substring-replace corrupted 55 lines in `BRANCHES.md` and 104
  in `DECISIONS_LOG.md` while `check_governance_placeholders.py` returned exit 0 throughout. The
  naive form of this invariant — "governance-only, therefore guard-gated" — was falsified by the
  very session that motivated it.

Code and schema changes always take full human review.

### Conventions

- **`FEEDBACK.md` §19 is the integrity ledger** (health-app only; a section of `FEEDBACK.md`, not a new store). Append-only rows typed `HUMAN`/`MODEL`/`COUPLED`, `status` mutable (`STANDS`/`STRUCK`); a row exists only if a procedural change would have prevented the failure (`prevention` mandatory, non-null), and `caused_by` is derived from `caused`, never authored. See DECISIONS_LOG #129–#132.

- **Hevy:** canonical creation is `create_workout`, not `create_routine` — custom exercise UUIDs do not resolve via the routine endpoint (confirmed API limitation). Field/type matrix: `Hevy_Pattern`.

- **SCHEMA.md is repo-canonical** (root), the readable mirror of `backend/migrations/`. Update it in the same commit (or an immediately paired governance commit) as any schema-changing migration — it must never lag master.

- **Chat→Code file transport.** A project-knowledge doc crossing to Code is emitted as a raw fenced block read byte-faithfully from the mount — never copied from the rendered view (which flattens markdown); Code diffs before landing. Repo-canonical docs are edited in place and never cross this transport.

- **Reference-JSON edit guard (#98).** `backend/reference/*.json` is hand-aligned pure ASCII (non-ASCII as `\uXXXX`). Never build a `\uXXXX` escape in heredoc source (the Bash tool eats one backslash even when quoted — use `chr(92)+"u2014"` or a script file); after any edit assert `raw.isascii() and raw.count(chr(0x2014))==0` and that it still parses; no `json.dump` round-trips (they reflow every hunk). The bad-byte failure is silent — only the assertion catches it.

- **The irreversible-write pre-ship gate (#166, `FEEDBACK` §23.1).** When a decision's
  **How you know** has to admit an unexercised write path, ask what its failure COSTS before
  shipping. Non-destructive and loud → ship with an `OPEN_QUESTIONS` watch-point. Able to
  change state we cannot undo → the live probe is the **gate, not the launch**. Earned when
  `#164` shipped custom-exercise creation on 61 green tests and its first real use created a
  permanent template, reported "failed", and left it orphaned. Companion rule: for code that
  interprets a third party's response, **at least one test must fake at the TRANSPORT layer** —
  stub the connector and its response handling is untested however many tests there are.

- **Never chain a verification to an action in one command (#103).** A check whose failure cannot stop what follows is not a check. Run it, read it, then act — or make the action conditional on its exit status. See `FEEDBACK` §17.

- **Controls discriminate on identity, not just function (#103).** A positive control proves the instrument works, not that it probed the thing you meant. Where a probe could hit the wrong artefact (stale ref, cached copy, reused branch name), pin to a SHA or assert on content only the intended version carries. See `FEEDBACK` §17.

- **Match on anchors, not substrings — especially in an audit (#113).** A recorded-or-not grep must anchor on the form the thing takes (`^### 104\.`, `^## Q45\.`, a whole word), never a bare substring, and you **read the matches, not the count**. Corrected docs produce this false positive by design — the superseded claim is quoted inside its own correction — so expect the hit and read the line *(this by-design clause postdates the locked #113 entry; added `8771a19`, it extends the convention, not the decision)*. See `FEEDBACK` §17.

- **Verify a deploy after it settles, and confirm which instance answered (#116).** A mid-deploy check can return a well-formed answer from the *outgoing* instance. Check `railway deployment list` for SUCCESS before trusting an in-container answer, and prefer a probe whose result differs between the two images (a file listing, not a version string). The **timing** axis — was the answer current.

- **A deploy check must cover every service that changed (#121).** Two Railway services deploy from this repo (`health-app-backend`, `health-app-frontend`); a backend probe (`alembic current`) is structurally blind to the frontend. Probe the frontend by its served bundle — fetch the live `assets/index-*.js` and grep a string literal only the new code carries — then split failure modes with `railway service … && railway deployment list`. The **coverage** axis to #116's timing.

- **Push branches even while holding for review (#98).** A local-only branch is unreadable to chat (`raw.githubusercontent.com` 404s), so a hold-gate chat cannot verify rests on Code's word alone. Pushing is not a merge; push when work becomes reviewable, not when it lands.

### Tooling

- **MarkItDown — the document→markdown ingestion path.** Microsoft MarkItDown converts
  PDFs and Office documents (TGA guidance, AS/NZS standards, council specs, clinical
  papers) to markdown deterministically, replacing native Claude ingestion of structured
  documents — which costs vision tokens and extracts tables non-deterministically. Two
  invocation paths:
  - **MCP (one-shot, in-context).** `markitdown` registered at **user scope**
    (`uvx markitdown-mcp`, machine-local `~/.claude.json`), for converting a single
    document straight into the conversation. Not a repo dependency.
  - **CLI (large documents, to disk).** For anything past the threshold, convert to a
    file and read it selectively rather than dumping it into context. Invoke
    `python -m markitdown <in> -o <out>.md` (the `markitdown.exe` shim is not on PATH;
    `python -m` is PATH-independent). Installed as `markitdown[pdf,docx,pptx,xlsx,xls]`
    (`[all]` is unsatisfiable on Python 3.14 — its `onnxruntime<=1.20.1` pin, audio-only,
    has no 3.14 wheel; the document extras carry every PDF/Office converter regardless).
  - **Threshold:** **>~30 pages → CLI-to-disk**; smaller → MCP is fine.
  - **Limits (verified at adoption).** The PDF path is pdfminer *text* extraction — it has
    no table-structure detection: genuine tables **flatten to linear text** (column pairing
    lost), and scanned / broken-font PDFs (no ToUnicode CMap) extract as `(cid:NN)` garbage.
    Output is deterministic and clean on born-digital prose, but for a document where a
    specific table's *structure* is load-bearing, or a scanned/garbled source, **fall back
    to native Claude vision** on that page. `az-doc-intel` (Azure Document Intelligence) is
    the table-aware upgrade path if ever needed — not wired.
  - **Loud vs silent failure (trust calibration, refines DECISIONS_LOG #78).** The three failure modes are
    NOT equally dangerous. `(cid:NN)` garbage is **loud** — obviously broken on sight, so you
    won't act on it. Table **flattening** (plausible prose, column pairing gone) and
    **spurious fake-tables** (valid-looking GFM built from shattered prose) are **silent** —
    they read as correct. So the risk isn't the garbled scan you'll catch; it's the clean-
    looking table you'll trust. When a table's structure carries meaning, verify against the
    source or use vision — don't trust MarkItDown's table shape on faith.
  - Machine-local: the MCP registration and CLI install do not replicate across machines —
    re-run the setup on any new machine. See DECISIONS_LOG for the adoption decision.

### Recent landings

_Pointer-only. Capped at the 3 most recent — one line each, canonical home only, no SHAs /
test counts / decision sub-bullets. Full history: `DECISIONS_LOG.md`. Latest handoff:
`closeout.md`. Forward-looking work: `ROADMAP.md` NOW/NEXT (not this block)._

- **A rule enforced only where it was discovered is not enforced — run #184's test repo-wide (#185)** - #184 struck a cross-repo enforcement claim from the checker docstring but its grep was file-scoped, so `CLAUDE.md`'s merge-path section still justified being repo-specific with a present-tense "HCA has no ruleset / branch protection / `.github/workflows`" sentence — all three clauses false (verified `gh api`); struck and replaced with the structural reason. #184's test then swept every tracked `*.md`/`*.py` (263 lines / 17 files): one live claim struck, the rest classified as append-only history, structural grammar, or task-pointers, and fed to `Q87`. Also adds `.gitattributes` (`*.md text`) to foreclose the `BRANCHES.md` `-text` trap. See DECISIONS_LOG #185.

- **A guard could report clean on a store it never read; and a file cannot hold evidence about a repo it cannot see (#183/#184)** - `check_governance_placeholders.py` `read()` returned git's stdout after checking only the return code, so a non-UTF-8 byte (decoded in a subprocess reader thread) or an empty blob passed the guard silently; it now captures bytes and routes every non-run to exit 2, per its own docstring contract. The same commit strikes two docstring sentences asserting another repo's enforcement state — a file has no means to keep a cross-repo claim current. `OPEN_QUESTIONS` Q87. See DECISIONS_LOG #183/#184.

- **Writer identity is repo-local evidence, not a shared invariant (#182)** - the shared block's "Code — and the `@claude` GitHub Action — is the only writer" named a per-repo surface, not an invariant: no `@claude` Action exists on any ref of health-app (`.github` holds only `governance-guard.yml`, a `contents: read` CI guard that cannot write), so the claim was false here as in HCA. The shared line collapses to "Code is the only writer"; any Action wiring is stated below `END SHARED LOOP RULES` in the repo that has it. See DECISIONS_LOG #182.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never edited
as a project-knowledge copy._

````

</details>

