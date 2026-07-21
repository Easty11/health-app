# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

2026-07-21 · erythroid group authoring (#96 / #97 / #98)

## 1. Real commits this session

Session-open ref: `fcb7530`. Landed on `master` at **`970224c`**, pushed.

```
970224c governance: DECISIONS_LOG #98 — three standing guards replacing care with mechanism
47c6d68 governance: DECISIONS_LOG #96/#97, OPEN_QUESTIONS Q36/Q37
9fc2f4e reference: trt_erythrocytosis_watch reclassified; plasma_volume_status deferred
0cf3212 reference: author the erythroid group as structure only
cdff7a4 gov(handoff): receipt — erythroid group-authoring brief received, not started
```

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-07-21 governance: DECISIONS_LOG #98 — three standing guards replacing care with mechanism
2026-07-21 governance: DECISIONS_LOG #96/#97, OPEN_QUESTIONS Q36/Q37
2026-07-21 reference: trt_erythrocytosis_watch reclassified; plasma_volume_status deferred
2026-07-21 reference: author the erythroid group as structure only
2026-07-21 gov(handoff): receipt — erythroid group-authoring brief received, not started
2026-07-21 chore: session close-out
2026-07-21 governance: DECISIONS_LOG #95 — three-class blocker taxonomy, I1 extends to read-constants
2026-07-21 reference: canonical v0.3, binds_to, _deferred restructure
2026-07-20 chore: session close-out
2026-07-20 gov: DECISIONS_LOG #94 + FEEDBACK §16 — generated view supersedes the hand-assembled mirror
```

Step 0 was honoured this session: the `CHAT→CODE` receipt (`cdff7a4`) was committed alone before
any work, correcting the previous session's breach. No `backend/interpretation/`, `alembic/`,
`tests/` or `routers/` touched; no fixture or oracle moved. Backend suite **206 passed**.

## 2. Pending-queue reconciliation

| Brief item | Outcome |
|---|---|
| Step 0 — HANDOFF receipt | **LANDED** `cdff7a4`, alone, before anchor work |
| Step 1 — verify shape | **VERIFIED** against the file. `groups` is a list; schema matches the `hepatocellular` element; `relation_kinds` retains `co_movement` + `discriminator` |
| Step 2 — append `erythroid` | **LANDED** `0cf3212`. 30 insertions, 0 deletions |
| Step 3 — no `group_levers` | **LANDED**, empty array |
| Step 4 — correct `trt_erythrocytosis_watch` | **LANDED** `9fc2f4e` — **one blocker, not two.** See below |
| Step 5 — withhold constants | **HELD.** `plasma_volume_status` added to `_deferred_levers` in the existing three-field shape |
| LOG | **LANDED** `47c6d68` + `970224c` — **#96, #97, #98, Q36, Q37** |

Minted from actual maxima verified at open — DECISIONS `#95`, questions `Q35` — not from the
numbers stated in the brief.

### Step 4: one of the two proposed blockers was not real

The brief proposed `blocked_on: [cross-group references, precondition_phase]`. Verification killed
the second. `hpg_gonadotropin_suppression` — an **authored, live relation inside the promoted
`hpg_axis` group** — already carries `precondition_phase: "on_trt"`, *and* a `driver` key. Authored
relations demonstrably hold arbitrary keys beyond the base schema, so `precondition_phase` is
precedented and disqualifies nothing. Recorded in #97 as **checked and cleared** so it is not
re-opened.

The companion rationale — "the 4a producer does not consume it" — was rejected as a criterion
outright: it is equally true of `group_levers` and every `relations` block, **including the
`erythroid` content authored one commit earlier**. A criterion that would disqualify the commit just
authorised is not a promotion criterion.

Landed as `blocked_on: ["4b contract: cross-group relation references"]`,
`status: "blocked_on_contract"`. `references` has no precedent: zero across the eight authored
relations in both groups.

### The test gate is weak by construction — reported as unchanged, not verified

`producer.py`'s docstring lists `relations_rendered` and `shared_levers` under "Emits NONE of"
(4b), and greps confirm zero consumption of `relations`, `group_levers`, `precondition_phase` or
`references` anywhere in `backend/interpretation/`. The producer reads membership, roles and display
names only. **206 green means nothing broke, not that anything works** — this session's content is
4b-latent by design.

### A premise corrected during the go

The 404 that prompted #98's push-branches rule was on `feat/erythroid-group-authoring`, which was
genuinely local-only. It was generalised to `feat/interpretation-view-skeleton`, which is **pushed
and fully readable** — verified: all three raw URL forms (plain, `refs/heads/`, SHA-pinned) return
**200** for `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md` and both reference JSONs. **O3's re-verify is not
blocked by branch visibility and can proceed now.** The genuinely unpushed branch was
`feat/recovery-metrics-rhr` — now pushed under the new rule, and its `BRANCHES.md` row corrected,
since it read "local-only (never pushed)".

## 3. Cold-resume handoff

**Branch:** `master` @ `970224c` (+ this close-out), pushed, clean. Untracked stray:
`.claude/launch.json` (known).

| Check | Result |
|---|---|
| `erythroid` group | members ×4, relations ×2, `group_levers: []`; all six referenced ids resolve in `marker_canonical.json` v0.3 |
| Diff confinement | `erythroid` 30 insertions / 0 deletions; `_deferred` correction 4 / 2, confined to the one relation object; non-`groups` keys and both pre-existing groups byte-identical to master |
| Reference-JSON guard (#98) | all three files `isascii() == True`, **zero** literal em dashes |
| Backend tests | **206 passed**, unchanged |
| Shared block G1 | `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232 — untouched; all three new rules are repo-specific or `HANDOFF`-local, so no G1 breach and no paired obligation |

**Branch terminal-state gate — passes, and every branch is now on origin.**
`feat/erythroid-group-authoring` was pushed *before* merge (per #98 rule 2), ff-merged, then deleted
local + remote.

```
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin — readable, verified 200
feat/recovery-metrics-rhr          1 +   rowed, pushed this session
```

**Open questions** — 37 total. New this session: **Q36** (`discriminator` field semantics inverted
between `ggt_hepatobiliary_discriminator` and `bilirubin_isolation`; `haemoconcentration_discriminator`
took the `ggt` side, making it 2-to-1, so a renderer built on the other reading renders it backwards —
plus `protein_total` is a second evidence marker with nowhere to live in a single-string field) and
**Q37** (I1's extension has no enforcement and one live violation, `alt`; parent question to #96's
withholding). Both due 4b with Q34, D3, PV1.

**OWED — Luke, receipted in `HANDOFF.md` at the moment of agreement (#98 rule 3):** citation capture —
DOIs for the haematocrit RCV work and the plasma-volume papers. On landing they promote
`plasma_volume_status` out of `_deferred_levers` and let the `haematocrit`/`haemoglobin`
`min_meaningful_delta` constants land cited, discharging #96's withholding. Until then **`erythroid`
produces no news beyond the default gates and the TRT→Hct concern stays uninstrumented.**

**OWED, carried:** the backfill dry run still needs a Railway run — `backend/.env` points
`DATABASE_URL` at local SQLite, where zero NULL rows make the check structurally incapable of
returning anything but its expected zero. HCA **Q11** should close `DONE → #93` from an HCA-rooted
session; HCA **Q9 item 1** and **Q10** remain open there. **Q33** — the shared block's `parked`, needing
its own mirror-first brief. `probe_resolver.py` container run and `hevy-resolver-activation` limb 2,
both blocked on Anthropic API credit.

**Single clearest next action:** Luke's citation capture. It is the only thing standing between the
authored `erythroid` structure and a group that actually produces news — everything else in the
follow-up brief is mechanical once the DOIs exist.
