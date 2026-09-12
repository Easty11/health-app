# FEEDBACK.md — Corrections, Principles & Verification Rules

*Load this at session start. Repo-canonical (health-app); the Claude.ai project-knowledge*
*copy is a refreshed mirror, not the master. Full provenance — the behavioural-correction*
*essays (§§1–3), the superseded injury snapshot (§5), and the 25 verification-rule essays*
*(§§7–30, §32) — lives in `FEEDBACK_ARCHIVE.md`, which is NOT read at session start.*
*Last updated: 9 August 2026.*

---

## 1. Project principles

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
| A held PR is held for the RELEASE DECISION only. On release, Code executes the entire land end-to-end — resolve `#NEXT` at the re-read master max → push → confirm guard green → un-draft → merge (merge commit) → delete branch → verify the Railway deploy reaches SUCCESS and the migration applied in boot logs. The operator's residue is the release decision, prod-credentialed execution, and data-judgement calls; nothing mechanical. Refines `#238`. | Q6 gate 2 land, `#242` |

---

## 2. Design principles

*How the system is built and how Easty wants inference handled — apply without being asked.*

- **Raw signals only — no proprietary composite scores (2.1).** Reject every manufacturer composite (Samsung Energy/Stress/Sleep, Garmin Stress/Body Battery/HRV Status); each input must trace raw signal → known formula → validated output.
- **Annotate confounds, don't discount them (2.4).** When alcohol/illness/travel suppresses a metric, tag the cause — the score stands (the physiological state was real), the cause is annotated; preserves accurate read and clean baseline trend.
- **Infer → surface → confirm; never silently commit (2.5).** The system infers but always surfaces its reasoning for human confirmation before any structured action; under uncertainty degrade to a broader cautious flag, never false precision.
- **Injury provocation is movement-pattern-indexed, not body-part-indexed (2.6).** Three-valued (provocative / clear / untested); conditions stack (range gate + load modifier); plain-language interview → structured object → confirm before commit.
- **Passive HRV collection is the priority (2.10).** Galaxy Ring is primary HRV (passivity — no morning protocol); the H10 is a re-validation instrument for trend-faithfulness, not a calibration layer — different physiological windows, no correction factor.
- **Prior art — search before build, weight asymmetrically (2.13).** For third-party integrations search forums/issues/libraries first; a community “can't be done” is a strong lead to bank provisionally, a “this works” is a hypothesis to re-verify (positive prior art rots under vendor rewrites); tag every finding with platform version/date. Excludes our own domain logic.

---

## 7. Verification rules (condensed — provenance in FEEDBACK_ARCHIVE.md, same numbering)

- §7  `_LOADED_KEYWORDS` is a fallback, not truth (#74)
- §8  LANDED ≠ LIVE — local-green is not prod-live (#77)
- §9  The Bash tool is Git Bash — `<<'EOF'` heredocs, never PowerShell here-strings
- §10 A false-green instrument is an unsound measurement reporting zero
- §11 A probe that presumes its own answer must fail loudly when it never reaches the subject
- §12 A declarative claim about an unseeable surface is an instruction to verify (#88)
- §13 A rule proven on two rows is not a rule applied to the store (#90)
- §14 A vocabulary is not adopted until its predecessor is struck from the rules (#91)
- §15 A scope exclusion carries the same evidentiary burden as an inclusion (#93)
- §16 A derived artifact with no generator is a fork (#94)
- §17 An unpaired negative is not a finding; a control must discriminate on identity (#103)
- §18 State inferred from an adjacent attestation is not measured state
- §19 Analysis-loop integrity failures (#129–#132) — see archive
- §20 Hardcoded governance numbers on held branches accrue renumber debt
- §21 `git commit` succeeding ≠ committed what you meant — stage governance by name
- §22 A brief citing governance from memory sends Code to verify an invention — carry the quote
- §23 Defer live proof only where failure is non-destructive; fake below the defect, not above
- §24 Chat cannot make verbatim claims about file content — paraphrase doesn't announce itself
- §25 Fail-closed contract + fail-opaque handler = an undiagnosable defect
- §26 In semi-structured extraction, every non-Optional scalar is a latent fail-closed point
- §27 Null-on-sparse-row class closed — re-open conditions in archive §27
- §28 The §7 unit guard held under real over-collapse pressure
- §29 Railway's dashboard editor silently no-ops a multi-statement paste — one statement per prod check
- §30 Backend `application/json` carries no `charset`; PowerShell 5.1 falls back to ISO-8859-1 in BOTH directions — READ mojibakes the response (client-side, display only), WRITE downgrades the request body before it is sent, so non-ASCII is lost at rest (em-dashes persisted as hyphens, `POST /knowledge/entry` ids 75–78); a client-side read symptom does not license "the data is fine", and this entry asserted exactly that until the write half was found
- §31 Auditing a vocabulary's members does not audit its coverage — the channel axis (`onboarding | chat | system`) was audited in #227 and one day later took four writes it has no member for, all silently defaulted to `chat`
- §32 A cross-reference in an append-only entry is a propagation source, not a leaf — `#123`'s own Rationale (`DECISIONS_LOG.md:3938`) miscites `#112` for the below-the-fold rule, and both mutable copies (`OPEN_QUESTIONS.md:1123`, `ROADMAP.md:84`) were faithfully echoing it rather than slipping independently; trace a wrong cross-ref to its deciding entry before treating it as isolated, because existence-checking cannot catch it — the target is real and resolves, it is simply the wrong entry (`1d028d5`, `205566f`; the origin is append-only and stays wrong)
- §33 A test substrate that omits an integrity constraint prod enforces tests a fiction — SQLite ships `PRAGMA foreign_keys` OFF, so a `hevy_sets`-before-`hevy_workouts` FK-ordering bug (`autoflush=False` + no `relationship()`, unit-of-work emits child before parent) passed a green suite and failed on the first prod backfill (`hevy_sets_workout_id_fkey`, rolled back). The test engine must enforce what the deployed engine enforces; the fix made it FK-enforced + `autoflush=False` and seeded the 71 fixtures the blindness had hidden — prevention is substrate parity, not a spot-fix on the one caught bug (#239/#240)
- §34 A named external-API constant whose value is silently load-bearing needs a value-guard test, not just a comment — `connectors/polar.ZONE_FEATURE` MUST be lowercase `zones`; an uppercase or unrecognised value returns HTTP 200 with zero zones (no error), so a refactor that "tidies" the constant passes CI (the transport-fake test fakes the response) while enriching nothing in prod. The comment documents the requirement; only a test that asserts the literal — or exercises a real zoned fixture through the live token path — catches the silent no-op (#261)
- §35 When amending a disposition or rule in CLAUDE.md, grep the WHOLE file for the superseded wording before closing — not only the section rewritten. #257 verified "§ Merge disposition, amended in this commit" and missed the same absolute 150 lines later at L190 (`Code and schema changes always take full human review`), which contradicted the amendment and re-stalled #169 on 2026-09-09 (Code held a green code-only PR for review when § Merge disposition says self-merge on green). Section-scoped verification cannot see a contradiction outside the section; the fix is this commit's CLAUDE.md L190 replacement
- §38 To prove a status check is REQUIRED (gates the merge) vs merely reported, fail it deliberately with every OTHER required check green and read the PR's `mergeable_state`: `blocked` = required, `unstable` = reported-but-not-required (still mergeable). A green merge never proves binding — it proves the checks passed, never that a red one would block (#176). Never read binding off a green run; read the ruleset directly, or run this probe. Probe PR #178 (2026-09-10) found BOTH `frontend tests (vitest)` and `backend tests (pytest)` yield `unstable` when failed → NOT bound on ruleset `20414758`; the #273 binding is still OWED. Close the probe PR UNMERGED; never fire the real merge (a broken merge pollutes master — the observed `mergeable_state` is the whole proof)
- §37 Resolve a number-at-merge token by writing the integer into the NEW text; never a repo-wide replace on an append-only store — a global `sed 's/#NEXT/#274/g'` over `DECISIONS_LOG`/`ROADMAP`/`BRANCHES` at #274's land clobbered historical `#NEXT` mentions in unrelated rows (the convention is quoted verbatim across the append-only history), the §113 substring-vs-anchor trap in write form. Caught pre-commit and reverted, but #176's report flagged it without recording it. Prevention: having re-read master's max, type the resolved integer directly into the entry/row you are adding; if a token must be replaced, anchor it (the `### #NEXT` heading line), never a bare `#NEXT` substring across the whole file
- §36 A merge gate that runs only the governance guard lets a test regression self-merge on a green guard — #271 and #272 both merged on LOCAL test runs, CI never ran a suite (`self-merge on green` was true of the guard, not the suites). `#273` added `frontend tests (vitest)` + `backend tests (pytest)` on every PR; from binding onward `green` means guard + both suites. Lint debt uncovered while building the lane and deliberately left un-gated (gating pre-existing errors would block every PR; a non-required lint job would set `mergeable_state: unstable` and re-stall the self-merge, the L190 class): **6 eslint errors** to clear in a dedicated PR before adding `frontend lint (eslint)` as its own required job — `ChatPanel.jsx:56:83` `no-empty`; `ChatPanel.jsx:96:7`, `WorkoutPanel.jsx:166:23`, `WorkoutPanel.jsx:418:21`, `interpretation/PlainPanel.jsx:35:13`, `Settings.jsx:182:5` all `react-hooks/set-state-in-effect`
- §39 The #154 "repoint the test onto the engine's clock" pattern must anchor on the AEST helper THE PATH UNDER TEST uses, not a single canonical one — health-app has three (`routers/checkin_v2._today_aest`, `engine/observations._today`, `load_metrics._local_day`), all `datetime.now(AEST).date()` today but independently defined. Q137 repointed three tests onto TWO helpers (`observations._today`, `_local_day`), neither the `_today_aest` that #154 happened to use; importing whichever helper is nearest passes today and silently re-skews if the helpers ever diverge (#103 identity, not just value). Pick the function the code path actually calls (#182)
- §40 A shared axis is a shared-unit claim; a discrete per-day quantity is bars, not lines — increment-1's `LoadChart` (#277) overlaid mechanical (`kg_reps`) and neuromuscular (`nm_au`) on ONE y-axis, incommensurable units on one scale, a meaningless plot a green suite passed because nothing asserted the units matched. Fix: small multiples (one `TimeSeriesChart` per window, own unit-labelled y-axis, shared x-domain) and `daily_load` drawn as bars (zero/rest days → no bar; cold-start bars muted). Prevention is not "remember to check": `TimeSeriesChart` now THROWS in dev/test when the series on one axis don't share a `unit`, with a test that asserts the throw — an encoded invariant, the wall that makes "just add another line" fail loudly rather than draw a lie. A rendering choice (which encoding, which axis) is a data-meaning claim and gets an assertion, same as any other (`fix/load-chart-units`, amends #277). **EXTENDED (increment 2, `#187`):** the guard catches a units overlay at render, but not a comparison that is meaningless or a series that is empty — so the check moves UPSTREAM to the brief. A chart brief must VERIFY the scale, unit, and population of every series BEFORE the chart is specced: increment 2's brief specced `morning_readiness` (1–5 ordinal, "primary OUTCOME") against `model_forecast` (0–10, written nowhere) as a residual — a subtraction across scales over a column null in prod, which a green vitest render would have "passed" while meaning nothing (dropped to Q141). Before the endpoint shape is fixed, confirm for each series (a) its scale and unit, (b) that any two series drawn together share them or get separate axes, and (c) that the field is actually populated — two briefs in a row now would have rendered fine and said nothing true
- §41 A new surface gets a home before it gets a chart — mounting a distinct concern additively onto an existing page defers an IA decision it doesn't remove. `/metrics` grew from a lab-ingestion page (upload/extract/confirm + stored-results read-back) by having the Banister-view charts (increments 1–3) mounted ABOVE the lab surface on the same route; two unrelated concerns then shared one URL, one nav doorway (the tile LABELLED "Labs" routed to `/metrics`), and one page header. "Additive mount" reads as free because each increment renders fine in isolation — but the debt is navigational, invisible to a render test, and it compounds every increment. Increment 4 STEP 0 split them: lab surface → `/labs` (nav "Labs"), charts → `/metrics` (nav "Metrics"). Prevention: when a brief adds a concern to a page, first ask whether it belongs on that page at all; a route+nav split is cheap early and a migration once users and deep-links have accreted (the split had to repoint `InterpretationView`'s "add a draw" link and `context_builder`'s `_LAB_INTERPRETATION_VIEW_LABEL` chat pointer, both of which had silently come to mean "the lab page" while pointing at `/metrics`). Gate the split with a per-route render test — each route renders ONLY its own surface — so a later increment can't quietly re-merge them (`claude/split-labs-metrics-routes-c46gi6`, increment 4 STEP 0)
- §42 An endpoint-consumer grep must anchor on the LITERAL path a client sends, not an endpoint-constant name — #283 and Q143 both concluded "`frontend/` has no chat component and no `/chat` caller" and routed the entire WS4 consuming gate out-of-repo on it, while `frontend/src/components/ChatPanel.jsx:78` calls `api.post('/chat', …)` with the route as a bare string literal (no constant to grep for), and FEEDBACK §36 — landed one entry earlier, in #273 — had already cited `ChatPanel.jsx` by name. The miss was internally contradicted at the time. A client that inlines the route string is invisible to a search for a symbol; grep the literal (`'/chat'`, `api.post('/chat'`) and read the hits, don't count a symbol's absence as the surface's absence (the §113 anchor discipline in consumer form). The wrong conclusion was load-bearing: it placed the truthfulness gate in a companion/agent layer as if that were its only possible home, when the gate landed in-repo server-side (#284) (Q143 / #284)

---

*Full provenance — §§1–3 correction essays, the §5 superseded injury snapshot, and the §§7–30*
*and §32 verification-rule essays — is in `FEEDBACK_ARCHIVE.md` (not read at session start).*
