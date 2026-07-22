# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-22 · CBT-I phase 1 built, rebased, merged (#107–#109) + the null-result/redaction guard (#110)

## 1. Real commits this session

Landed on `master` at **`d97c992`**, pushed, in sync. Master was at `8658145` at merge time.

```
d97c992 governance: DECISIONS_LOG #110, OPEN_QUESTIONS Q43/Q44, CLAUDE recent-landings
d98b740 chore: session close-out
384b246 governance: DECISIONS_LOG #107/#108/#109, OPEN_QUESTIONS Q42, CLAUDE recent-landings
9c9e482 feat(cbti): completed-block importer + reconciliation (Gate 4)
5d0a462 chore(cbti): gitignore personal-data workbooks before import
6b43860 feat(cbti): data substrate — diary fields + block/prescription ledgers
```

```
2026-07-22 governance: DECISIONS_LOG #110, OPEN_QUESTIONS Q43/Q44, CLAUDE recent-landings
2026-07-22 chore: session close-out
2026-07-22 governance: DECISIONS_LOG #107/#108/#109, OPEN_QUESTIONS Q42, CLAUDE recent-landings
2026-07-22 feat(cbti): completed-block importer + reconciliation (Gate 4)
2026-07-22 chore(cbti): gitignore personal-data workbooks before import
2026-07-22 feat(cbti): data substrate — diary fields + block/prescription ledgers
2026-07-22 chore: session close-out
2026-07-22 gov(handoff): receipt — resolution-table-is-a-hypothesis rule (FEEDBACK §19 candidate)
2026-07-22 chore: session close-out
2026-07-22 gov(handoff): written go for f078f1c; mutation-verification rule receipted
```

Maxima now: **DECISIONS #110 · questions Q44 · FEEDBACK §17.**
Backend suite **275 passed** (master's 258 + 17: 10 substrate, 7 import).

**The branch was rebased mid-flight.** Master advanced 8 commits while `feat/cbti-module` was held
for review, taking #104/#105/#106 and Q41 — so the branch diverged (5 ahead / 8 behind) and
`--ff-only` became impossible. Rebased onto `origin/master`, renumbered by anchored pattern
(#104→#107, #105→#108, #106→#109, Q41→Q42), then ff-merged. Pre-rebase range was
`f0899eb`→`5fb625d`; recovery ref `backup/cbti-pre-rebase` deleted after Gate 6.

`alembic heads` returned exactly **one** after the rebase — master added no migration, so
`c3a2d8e5f109` remained the sole predecessor and the prod-pinned revision needed no re-chaining.

## 2. Pending-queue reconciliation

Two briefs ran: CBT-I phase 1 (Steps 1–4) and the closure re-issue. All items landed.

| Brief item | Outcome |
|---|---|
| Gate 1 — single alembic head | **VERIFIED** `c3a2d8e5f109`; brief's 21-head count was a regex artefact |
| Gate 2 — migration up/down; suite green | **LANDED** `6b43860`; up/down/up on SQLite in isolation |
| Gate 3 — both tables, append-only | **LANDED** `6b43860`; `ck_cbti_prescription_decision` DB-enforced |
| Gate 4 — 53 nights + 9 prescriptions, SE ±0.001 | **LANDED** `9c9e482`; 0/53 mismatch, negative control fires |
| LOG (phase 1) | **LANDED** `384b246` — #107/#108/#109, Q42 |
| Closure Step 2 — correct a "confabulated" claim | **WITHDRAWN by chat** — the claim was chat's and was wrong; `closeout.md` unchanged, rotation note stands |
| Closure Step 2′ — provenance by block type | **DONE**, read-only; recorded in #110 evidence |
| Closure Step 3/4 — #110, Q43, Q44 | **LANDED** `d97c992`, single governance commit |
| Closure Step 5 — `--ff-only` merge | **DONE** `8658145`→`d97c992`, pushed |
| Closure Step 6 — prod reconcile | **DONE** — `alembic current` = `e5f2a9c7b104`, revision present on master |

Nothing decided this session is uncommitted.

### Three findings that changed the work

1. **A false security claim was refused rather than written.** The re-issued brief asked Code to
   record that a credential leak had been confabulated. The artefact contradicted it: 54 of 79
   credential-shaped matches were digest-identical to the reference, across 7 transcripts. Writing
   the correction would have put a false statement into an append-only store and retracted a valid
   rotation recommendation. Chat withdrew the step. This is #110's worked example.
2. **Provenance is settled by content block type, not record role.** `tool_result` blocks persist as
   `user`-role records, so role is function and block type is identity. Census: `tool_result` ×4 (all
   `Bash`), `tool_use` ×16, plain-string user ×3, `queue-operation` ×2, `text` ×1. **Both mechanisms
   are real** — four sessions carry the credential only as tool output, three as operator input.
3. **Dangling brief-provisional refs.** `models.py` and `import_cbti_block.py` still carried `#101`/
   `#102` from the brief's draft numbering; on master those are erythroid RCV constants and the
   merge-receipt rule. Corrected to #107/#108. Found only because the brief required a
   grep-for-dangling-references after renumbering.

## 3. Cold-resume handoff

**Branch:** `master` @ `d97c992`, pushed, clean. Untracked stray: `.claude/launch.json` (known).

**Branch terminal-state gate — passes.** `feat/cbti-module` merged + deleted (local and remote), row
**DONE** at `d97c992`. The four pre-existing locals are all rowed and all on origin:

```
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

**Prod/master divergence CLOSED.** For the branch's lifetime the migration was applied to Railway
while its file existed only on the branch. Gate 6: `railway run --service health-app-DB` →
`alembic current` = `e5f2a9c7b104`, and that revision now exists on master. Prod and master agree.

**OPEN — security, and the most urgent thing here.** The Railway Postgres credential is **live and
exposed**. It sits in **7 session transcripts** on disk, earliest file dated **2026-07-06** — over two
weeks. A second distinct credential digest appears in 4 of those, consistent with an earlier rotation.

- **Rotate the Railway Postgres password.** Operator action, outside the repo.
- **Q44** — `railway variables --kv` prints values and is the vector in 4 transcripts; `railway run`
  is the credential-free substitute (proven at Gate 6). Decide whether `--kv` is banned outright.
- **Q44** also carries: confirm the second digest is a retired credential, and decide whether the
  transcripts are purged or retained — they remain the exposure surface until the credential is dead.
- **Q43** — does prod share `FERNET_KEY`/`SECRET_KEY` with the dev `.env`? Compare SHA-256 digests,
  digests only. If shared, rotation carries a re-encryption migration over `api_key_encrypted`.

**OPEN — CBT-I phase 2 (Steps 5–7), a separate brief, none started.**
Titration engine (weekly eval; sufficiency/regularity/adherence gates; TST-plateau exit with SE≥85%
as a *floor*; adherence reads `samsung_hrv_readings` only via the `passive_overnight` allowlist;
**replay against the imported block = its Gate 5**); AM/PM surfaces (diary fields render only while a
block is open; never prefill `sleep_latency_min`/`waso_min`; reject a prefill >~4h from prescription);
ISI 7-item capture. **Confirm the VA diary's nap-timing convention before the engine trusts the
`naps_min` date−1 read** — it is silent when wrong; 2 nap nights in the imported block.

**OWED, carried from prior sessions:** `FEEDBACK` **§18** (mutation rule, receipted `caf5204`) and
**§19** (resolution-table rule, receipted `b3af58a`) — both need a brief to land them. `haemoglobin`'s
per-parameter figure unread from Buoro 2018. **Q41** (haematocrit band citation capture). **Q37** (I1
has no enforcement). **Q33** (shared block still says `parked`). HCA **Q11** should close `DONE → #93`
from an HCA-rooted session; HCA **Q9 item 1** and **Q10** remain open there. `probe_resolver.py`
container run and `hevy-resolver-activation` limb 2, both blocked on Anthropic API credit.
**Q42** (12h-clock scrape failure) belongs to `health-connect-app`'s store — carry it there.

**Single clearest next action:** rotate the Railway Postgres password, then confirm the second
credential digest is retired. It has been live and in-transcript for over two weeks, and every other
open item on this list tolerates delay better than this one does.
