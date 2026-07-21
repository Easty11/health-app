# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

2026-07-21 · erythroid constants, RCV supersession, evidence rules (#99 → #103)

## 1. Real commits this session

Session-open ref: `1d49000`. Landed on `master` at **`8065135`**, pushed.

```
8065135 governance: DECISIONS_LOG #103, FEEDBACK §17 — evidence that looks like evidence
ed5491d gov(handoff): receipt — control-identity and check-coupling rules received
c7795c1 governance: DECISIONS_LOG #101/#102, OPEN_QUESTIONS Q40, Q38 append
b0ccc8b reference: four erythroid RCV constants from Coskun et al.
fa10b70 gov(handoff): receipt — erythroid RCV-constants brief received, not started
6bdbb7b governance: DECISIONS_LOG #99/#100, OPEN_QUESTIONS Q38/Q39
4cf635a reference: haematocrit constant, plasma_volume_status promoted, erythroid levers
4384c14 gov(handoff): receipt — erythroid constants + lever brief received, not started
```

The last three predate this session's brief: they are the **prerequisite merge**, completed here.
See §2.

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-07-21 governance: DECISIONS_LOG #103, FEEDBACK §17 — evidence that looks like evidence
2026-07-21 gov(handoff): receipt — control-identity and check-coupling rules received
2026-07-21 governance: DECISIONS_LOG #101/#102, OPEN_QUESTIONS Q40, Q38 append
2026-07-21 reference: four erythroid RCV constants from Coskun et al.
2026-07-21 gov(handoff): receipt — erythroid RCV-constants brief received, not started
2026-07-21 governance: DECISIONS_LOG #99/#100, OPEN_QUESTIONS Q38/Q39
2026-07-21 reference: haematocrit constant, plasma_volume_status promoted, erythroid levers
2026-07-21 gov(handoff): receipt — erythroid constants + lever brief received, not started
2026-07-21 gov(handoff): receipt — paired-positive-control rule; O3 unblocked
2026-07-21 chore: session close-out
```

Maxima now: **DECISIONS #103 · questions Q40 · FEEDBACK §17.**
Backend suite **206 passed**, unchanged. No `interpretation/`, `alembic/`, `tests/`, `routers/` or
`frontend/` paths touched at any point.

## 2. Pending-queue reconciliation

**The session opened on a blocking finding.** The incoming brief assumed master carried #99/#100 and
haematocrit at 0.12. It did not: master was `1d49000` at **#98 / Q37**, and #99/#100/Q38/Q39 existed
only on `feat/erythroid-constants-and-lever` — complete, gated and pushed, but **unmerged**, because
the previous session held for a go that was given in chat and never reached Code. So the brief's
supersession premise had already failed before step 1. Reported; ANCHOR was replaced; the prerequisite
was merged on a written go, then this branch rebased onto it. That failure is what #102 records.

| Brief item | Outcome |
|---|---|
| Step 0 — receipt | **LANDED** `fa10b70`, alone, before work |
| Prerequisite merge | **LANDED** `6bdbb7b` → master; premises re-verified post-rebase |
| Step 1 — verify shape / no test pins 0.12 | **VERIFIED** with control |
| Step 2 — arithmetic self-check | **RUN**; one row anomalous, adjudicated by chat — see below |
| Step 3 — four constants | **LANDED** `b0ccc8b` |
| Step 4 — leave `marker_groups.json` alone | **HELD** — untouched |
| LOG | **LANDED** `c7795c1` (#101/#102, Q40, Q38 append) + `8065135` (#103, §17) |

### The haematocrit arithmetic anomaly, recorded not resolved

Three of four RCVs reproduce exactly from the source's own equation: hb **7.7632**, rbc **7.8930**,
mcv **2.0572**. `haematocrit` computes **8.0093** against a published **8.00**. Chat adjudicated
against a second independent identity from the same table (`B_APS`), which fails on that row alone by
a larger margin and cannot be reconciled with any published CVG for the measurand. Confined to one
row, immaterial at the resolution landed — 8.00 and 8.01 both give `0.08` — and **no input was
reconstructed to force agreement**. The artefact may originate in the PDF text extraction rather than
the source. Control run alongside: substituting a desirable-APS CVa gives 9.09% against a published
7.76, confirming the RCV column uses measured CVA and that the check discriminates.

### Two errors made and caught in-session — both now rules

- **Conflict markers were committed.** Resolving the rebase, an assertion failed — and `git add &&
  git rebase --continue` sat in the *same command*, so the rebase completed and wrote `<<<<<<< HEAD`
  into an append-only ledger. Caught on inspection, resolved, amended. **A check whose failure cannot
  stop what follows is not a check** → `CLAUDE.md` standing line + `FEEDBACK` §17.
- **Readability was nearly reported on stale bytes.** A push was rejected (rebase → non-fast-forward)
  while three `curl` probes in the same block returned honest **200**s — against the *pre-rebase*
  branch still on origin. The positive control passed; the bytes were abandoned. **A control must
  discriminate on identity, not just function** → same two homes. Re-run SHA-pinned, and the pushed
  copy asserted to carry `0.08/0.08/0.08/0.02` rather than trusted on status code.

## 3. Cold-resume handoff

**Branch:** `master` @ `8065135`, pushed, clean. Untracked stray: `.claude/launch.json` (known).

| Check | Result |
|---|---|
| Four constants | `haemoglobin` 0.08 · `haematocrit` 0.08 · `rbc` 0.08 · `mcv` 0.02, all Coşkun `10.1515/cclm-2017-1155`; Thirup retained on `haematocrit` only, as caveat source |
| `oestradiol` / `alt` / `ast` / `bilirubin_total` | untouched |
| `binds_to`, `levers`, `_deferred_levers` | unchanged; `marker_groups.json` untouched |
| #98 guard | all three reference files `isascii()`, **zero** literal em dashes |
| Shared block G1 | `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232 — untouched all session |
| Backend tests | **206 passed** — unchanged, not verified (`marker_interpretation` is 4b-latent; no test covers these four markers) |
| Post-push verification | by **identity**: fetched `FEEDBACK.md` carries 1 × `§17`, `DECISIONS_LOG.md` 1 × `#103`, control `#104` = 0 |

**Branch terminal-state gate — passes.** Three branches touched, all merged + deleted local and
remote: `feat/erythroid-constants-and-lever`, `feat/erythroid-rcv-constants`,
`gov/control-identity-and-coupling`. The four pre-existing locals are all rowed and all on origin:

```
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

**Where the fork stands.** `erythroid` is **content-complete and delta-instrumented**: group, members,
roles, two relations, `plasma_volume_status` with verified citations, and four published constants.
`haemoconcentration_discriminator` **can now fail** — at the 0.30 default MCV could move ~15× its real
RCV and still read as flat, so the relation would have confirmed itself against essentially any data;
at 0.02 it is a real test. The August panel has a gate that can plausibly fire: `haematocrit` ≥ 0.475
trips at 0.08, against ≥ 0.493 at the superseded 0.12.

**Still dark: the 0.50–0.54 band.** `min_meaningful_delta` is a *delta* gate; it says nothing about
whether a value is dangerous now. **Q34 (`safety_threshold`) is the only open item standing between
the repo and the clinical concern that opened this fork.** Everything else on the 4b list — Q36
(discriminator semantics), Q37 (I1 enforcement), Q38 (interval-banding), Q39 (`effect_locus`), Q40
(asymmetrical RCV) — is correctness.

**OWED, carried:** `haemoglobin`'s per-parameter figure was never read from Buoro 2018 full text — it
now has a published constant from Coşkun instead, so #99's withholding is discharged by supersession
rather than by reading. The backfill dry run still needs a Railway run (`backend/.env` points at local
SQLite with zero NULL rows, so it cannot return anything but its expected zero). HCA **Q11** should
close `DONE → #93` from an HCA-rooted session; HCA **Q9 item 1** and **Q10** remain open there.
**Q33** — the shared block's `parked`, needing its own mirror-first brief. `probe_resolver.py`
container run and `hevy-resolver-activation` limb 2, both blocked on Anthropic API credit.

**Single clearest next action:** **Q34 — `safety_threshold`.** It is the last thing between a
group that reports movement and one that reports risk, and the 0.50–0.54 band is uninstrumented until
it exists.
