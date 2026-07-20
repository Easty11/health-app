# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

2026-07-21 · marker vocabulary v0.3 (#95)

## 1. Real commits this session

Session-open ref: `965e0aa`. Landed on `master` at **`3bb200e`**, pushed.

```
3bb200e governance: DECISIONS_LOG #95 — three-class blocker taxonomy, I1 extends to read-constants
478e6ea reference: canonical v0.3, binds_to, _deferred restructure
```

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-07-21 governance: DECISIONS_LOG #95 — three-class blocker taxonomy, I1 extends to read-constants
2026-07-21 reference: canonical v0.3, binds_to, _deferred restructure
2026-07-20 chore: session close-out
2026-07-20 gov: DECISIONS_LOG #94 + FEEDBACK §16 — generated view supersedes the hand-assembled mirror
2026-07-20 feat(scripts): generate the consolidated governance view from master
2026-07-20 gov(handoff): record the 10-hour timestamp error, append-only
2026-07-20 gov(handoff): receipt — governance view generator brief received, not started
2026-07-20 chore: session close-out
2026-07-20 gov: DECISIONS_LOG #93 — adoption completes at the frame; sweeps run definition-first
2026-07-20 gov(feedback): §14 occurrence 4 (the false PASS); mint §15
```

Scope held: 5 files — `backend/reference/` ×3, `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`.
**No migration, no producer change, no ingestion.** Backend suite **206 passed**, unchanged.

## 2. Pending-queue reconciliation

| Brief item | Outcome |
|---|---|
| Step 1 — `marker_canonical.json` v0.3, +34 entries | **LANDED** `478e6ea`. 31 → 65, pure additions |
| Step 2 — `lever_dictionary._meta.binds_to` → v0.3 | **LANDED** `478e6ea`. One-line diff; `_meta.version` left at `v0` (fixtures pin it) |
| Step 3 — `_deferred` restructure, 5 sub-items | **LANDED** `478e6ea`. All five |
| Step 4 — backfill dry run, expect zero | **RAN, DID NOT VERIFY.** See below — this gate is not discharged |
| LOG — DECISIONS + OPEN_QUESTIONS | **LANDED** `3bb200e` as **#95**, Q34, Q35 |

### The anchor was stale

The brief anchored to master **#87 (`eed3c76`)**; master was at **#94 (`965e0aa`)**, seven decisions
on. Minted **#95**, and `binds_to` reads `v0.3 (#95)`.

### The marker table arrived flattened

The brief's table lost its delimiters in transit and arrived as one run-on string — the rendered-view
flattening `CLAUDE.md`'s chat→Code transport rule exists to prevent. Reconstructed 34 rows,
**round-tripped back to the brief's exact bytes**, and the count independently matched the stated 34.
A round-trip proves the split is *a* valid decomposition, not necessarily *the* intended one, and
`marker_name_raw` is verbatim-critical under exact match. Judgement calls, still unconfirmed by a
byte-faithful source: `Transferrin`/`transferrin`/`g/L` · `Saturation`/`transferrin_saturation`/`%` ·
`Non HDLC`/`non_hdl`/`mmol/L` · `Tot Chol/HDL`/`chol_hdl_ratio`/`null` ·
`Zinc-plasma`/`zinc_plasma`/`umol/L`. **A label wrong by one space fails silently.**

### Two gates NOT claimed

- **The backfill dry run verified nothing.** It returned `0 rows across 65 mappings` — the expected
  answer. But `backend/.env` sets `DATABASE_URL` to **local SQLite, not Railway**, and that database
  holds 24 `lab_results` rows with **zero** `marker_canonical IS NULL`. With no NULL rows to match, the
  query cannot return anything but zero: it is structurally incapable of detecting the raw-label
  variant it exists to catch. §11's probe-that-presumes-its-own-answer, wearing a passed gate's
  costume. **Re-run against Railway before trusting it.**
- **I1's extension has no enforcement and one live violation.**
  `backend/interpretation/gates.py:39-53` falls back only when the entry is absent or `value is None`,
  and explicitly projects `evidence_refs` away — its docstring states they "are NOT part of a delta".
  Under extended I1, `alt` (`value: 0.45`, `evidence_refs: []`) must fall back to `_defaults` 0.30 and
  does not. **Canon and code now disagree by design.** Recorded in #95's body only — it has no
  `OPEN_QUESTIONS` row, so nothing points at it. Offered before merge, not taken up; **still owed.**

### Ritual breach, recorded not hidden

**No `CHAT→CODE` receipt was written before work began.** This brief carried no step 0 and the standing
rule (`HANDOFF.md` header, #88) was not applied from memory. The omission defeats the receipt's entire
purpose — an interruption mid-session would have left no trace of what was being attempted. A
`CODE→CHAT` entry was appended at close instead, which is not a substitute.

### A process correction mid-session

The first pass wrote all three JSON files via `json.dump` round-trips. That reflowed
`marker_groups.json`'s hand-aligned columns across all 31 hunks and rewrote `\uXXXX` escapes to
literal characters — value-identical churn that buried a 47-line change inside a 316-line diff, and
touched two files the brief said to change one string and append entries in. Both commits were reset
and redone surgically. `lever_dictionary.json` is now a **1-line** diff; for `marker_groups.json` the
bytes before `_deferred` are asserted unchanged and every non-`_deferred` key equal to master.

## 3. Cold-resume handoff

**Branch:** `master` @ `3bb200e` (+ this close-out), pushed, clean. Untracked stray:
`.claude/launch.json` (known).

| Check | Result |
|---|---|
| `marker_canonical.json` | v0.2 → **v0.3**, entries **31 → 65** |
| Duplicate `marker_name_raw` / `marker_canonical` | **zero / zero** across all 65 (`_CANONICAL_MAP` is a plain dict — a dupe silently wins last) |
| `glucose_fasting` vs `glucose_random` | both present, distinct, not merged |
| Tests asserting entry count or map version | **none** — verified, not taken on report |
| Over-collapse guard | untouched; cannot fire on null `unit_established` (`haematocrit`, `chol_hdl_ratio`) |
| Backend tests | **206 passed**, unchanged |
| Shared block G1 | `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232 — untouched |

**Branch terminal-state gate — passes.** Only `feat/marker-canonical-v03` was touched (ff-merged,
deleted; never pushed, so no remote ref). The four pre-existing locals all carry `+` commits and are
all rowed in `BRANCHES.md`:

```
feat/checkin-injury-probe          2 +   rowed, pushed
feat/feedback-ledger               4 +   rowed, pushed
feat/interpretation-view-skeleton  3 +   rowed, pushed
feat/recovery-metrics-rhr          1 +   rowed (UNSTARTED), local-only by design
```

**Open questions** — 35 total. New this session: **Q34** (is `safety_threshold` a third read-constant
class? due 4b with D3/PV1) and **Q35** (the over-collapse guard is unit-only and blind to same-unit
semantic collapse; `glucose_fasting`/`glucose_random` is the live pair, both `mmol/L`).

**Ready to promote, follow-on brief:** `_deferred.groups.erythroid` and
`_deferred.relations.trt_erythrocytosis_watch` now carry `blocked_on: []` and
`status: "ready_to_promote"` — their vocabulary blockers cleared at v0.3. Group authoring was
explicitly out of scope here.

**OWED — this session:** re-run the backfill dry run against Railway; and either enforce extended I1 in
`gates.py` or record it as a question. Neither is tracked anywhere but #95's body and this file.

**OWED, carried:** HCA **Q11** should close `DONE → #93` from an HCA-rooted session; HCA **Q9 item 1**
and **Q10** remain open there. **Q33** — the shared block's `parked`, needing its own mirror-first
brief. `probe_resolver.py` container run and `hevy-resolver-activation` limb 2, both blocked on
Anthropic API credit, owner Luke.

**Single clearest next action:** re-run `python backend/backfill_marker_canonical.py` with
`DATABASE_URL` pointed at Railway. Until then the vocabulary bump has landed with its one data-safety
gate unverified, and that gate exists precisely because a raw-label variant would otherwise
double-count a marker across the COALESCE partition.
