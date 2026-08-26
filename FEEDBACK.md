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

---

*Full provenance — §§1–3 correction essays, the §5 superseded injury snapshot, and the §§7–30*
*and §32 verification-rule essays — is in `FEEDBACK_ARCHIVE.md` (not read at session start).*
