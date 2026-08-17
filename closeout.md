# Session close-out

_Session of 2026-08-17. Opened at `1e6cf0c`, maxima **#217 / Q103** — the brief expected
#216 / Q102, which had already been passed by the Cystatin C landing (`47c4dc1`); the brief
was re-aimed against the actual maxima at open. Master closed at `e2b46cc`. Both fresh-clone
settings verified present at open (`core.hooksPath` = `.githooks`, local `alias.land`)._

## 1. Real commits this session

```
2e53619 fix(cbti): gate accept on decision class and put a restating confirm in front of the mint
2ece39c gov: resolve #NEXT -> #218 (master max re-read #217/Q103 at this instant)
950e90a Merge pull request #75 from Easty11/fix/cbti-accept-confirm
75dfe82 gov: strike three discharged cross-repo ROADMAP rows, re-scope the fourth
e2b46cc Merge pull request #76 from Easty11/chore/crossrepo-rows-reconcile
```

Plus this close-out commit.

**Branch terminal-state gate: PASS.** Both branches touched this session —
`fix/cbti-accept-confirm` and `chore/crossrepo-rows-reconcile` — are merged and deleted,
local and remote (`git fetch --prune` confirmed; neither appears in `git branch -a`).

Pre-existing branches enumerated by the gate, none touched this session:

- Three `claude/*` auto-named branches carry **zero** unique commits vs `origin/master`
  (`git cherry` returns neither `+` nor `-`), so none triggers the push-or-row requirement.
  They are the auto-name form `CLAUDE.md` bans for in-flight work and are safe to delete;
  left alone as not this session's to dispose of.
- **`fix/q45-nap-attribution` carries real unmerged work** (`git cherry origin/master` →
  `+ 4f77679`). It is pushed, so it satisfies the gate's push-or-row-or-discard clause, but
  it has **no `BRANCHES.md` row**. Pre-existing debt, not created here — flagged rather than
  silently passed. It is the branch behind the Q45 lane named in §3.

**Suites at close, both green with zero regressions.** Backend **869 → 877** (baseline taken
before any edit; the brief's "last known 860" was stale). Frontend vitest **32 → 41**.
Frontend lint carries 6 pre-existing errors in four files this session did not touch
(`ChatPanel`, `WorkoutPanel`, `PlainPanel`, `Settings`); nothing in `cbti/`.

**Deploy verified after settling, both services that deploy from this repo (#116/#121).**
`health-app-backend` deployment `f93368db` SUCCESS 20:31:48 and `health-app-frontend`
`15414a74` SUCCESS 20:31:47, checked in `railway deployment list` before trusting any answer
from the running image. Discriminating probes, not version strings:

- **Backend** — live `/openapi.json` shows `CBTIEvaluationOut.sufficient`
  (`boolean`, default `true`). The field exists only in the new image.
- **Frontend** — served bundle `/assets/index-MPczDSNr.js` (417,863 bytes) carries
  `Review and accept`, `Confirm — record prescription`, `resets the evaluation clock` and
  `Not enough logged nights to evaluate`, one hit each — and **zero** hits for the old
  `Accept and prescribe`. The negative is the discriminator: a cached prior bundle would
  still carry it.

## 2. Pending-queue reconciliation

This session opened on a two-branch dispatch brief, not a `;cc` PENDING queue.

- **Branch 1 — `fix/cbti-accept-confirm`.** **LANDED.** `2e53619`, resolved `2ece39c`, merged
  `950e90a` via PR #75. All five steps executed: engine discriminator, server 409, confirm
  flow, tests both directions, governance. Recorded as `DECISIONS_LOG #218`; **Q101 → DONE →
  #218**; the ROADMAP NEXT accept-confirm row struck to DONE.
- **Branch 2 — `chore/crossrepo-rows-reconcile`.** **LANDED.** `75dfe82`, merged `e2b46cc`
  via PR #76, guard green, docs-only, cut from post-merge master. Three cross-repo NOW rows
  struck; the fourth re-scoped and left OWED.

**Two adjudications where Code departed from the brief's proposed shape, both reported:**

- **The discriminator's emission point.** The brief proposed threading `sufficient` in
  `backend/cbti/replay.py`. The sufficiency gate is **not there** — it is GATE 1 in
  `backend/cbti/engine.py:422`; `replay.py` only re-exports `d.reason`. The field is minted
  at the gate on `CycleDecision` and threaded verbatim through `replay()`, mirroring
  `converged`, which already exists for exactly this job. Re-deriving it in `replay.py` from
  `n` against `MIN_VALID_NIGHTS` was rejected: it would put the threshold in two places.
  The brief's VERIFY was answered as it asked — no existing structural discriminator for
  insufficiency; the reason PREFIX was the sole carrier.
- **One test's premise was wrong and was corrected, not forced.** A test asserting the
  insufficiency 409 is distinct from the *idempotency* 409 could not reach the idempotency
  branch: a successor's own cycle begins today, so a second accept is refused by the
  **eligibility** gate at "day 0 of 4" long before the superseded-row check. Rewritten to
  assert what is actually reachable — two distinct refusals, neither carrying the nights
  message — with the unreachability documented in the test itself.

**One deviation from an invariant, recorded rather than left unwritten.** Under #176(b)
housekeeping rides its originating branch, so the `#218` Recent-landings pointer in
`CLAUDE.md` should have ridden branch 1. It did not; it was carried on branch 2 with the
block trimmed back to its 3-row cap. No content was lost — the displaced `#216` line remains
in `DECISIONS_LOG.md`, its canonical home.

**Test dependencies added.** `jsdom` and `@testing-library/react` (+ `@testing-library/dom`)
as frontend devDeps, with the environment declared per-file via a `@vitest-environment`
docblock rather than in `vite.config.js`, so the existing node-environment suites pay
nothing. CI does not run the frontend suite, so this changes no pipeline.

Nothing decided this session is uncommitted. No provisional state carries forward.

## 3. Cold-resume handoff

### What landed

`#218` closes the live #214 defect and Q101 together, because they were one event: block 2's
buried compress was a single tap on a live "Accept and prescribe" recording a decision the
engine had not reached. An insufficiency-hold is now a non-event — mints nothing, resets
nothing, information-only, refused **server-side** with a 409 rather than merely hidden. The
discriminator is structural (`CycleDecision.sufficient`), so an irreversible write's refusal
no longer rests on a reason-string prefix. A converged HOLD stays acceptable. Selection
unchanged (`complete[-1]`). `cbti_prescriptions.id`=12 let stand — an operator matter.

Cross-repo parity is now **evidenced, not assumed**: both repos' `BEGIN…END SHARED LOOP
RULES` spans are byte-identical, SHA-256
`5790ae3d527e0a3b7f5a8c0cfebcc560d6ff3e0c96b6b6ce8f111eb8ca737130`, 97 lines / 6039 bytes
LF-normalised; HCA master carries all three enforcement artefacts. Three ROADMAP NOW rows
discharged on that evidence.

### The single clearest next action

**`rx 12` is an operator decision, not a code task, and it is the only thing this landing
deliberately left undone.** The row is a faithful append-only record of what was accepted;
the fix, if wanted, is a corrective prescription entered by the operator — never a
migration. Decide it or explicitly let it stand.

After that, the largest queued lane with a met precondition is **Brief B (renal derived
metrics)** — unblocked by `#217`, its placement fork already closed, spec amended, not built.

### Open questions

**52 OPEN, 0 OWED.** Q101 left the OPEN set this session (→ `#218`). No question was minted
this session. The two newest remain the live ones from the preceding two sessions:

- **`Q102`** — `restrictions[]` is dead data; `is_contraindicated` cannot express the
  ledger's clinical language. Has a matching ROADMAP NEXT row (the contraindication design
  pass). Live defects, deliberately unpatched at `#216`.
- **`Q103`** — `lab_results.is_derived` is write-dead; no production path sets it true.
- **`Q45`** — nap day-attribution, still OPEN and still gating: every nap-excluded night
  rests on an unverified date−1 attribution, and at the 4-night cadence two nap nights starve
  a cycle. `#218` makes that stall *safe* (it can no longer be accepted into the ledger) but
  does not make it *correct*. See the branch note in §1.

### What was NOT touched — read this before choosing the next session

This session went to **the instrument, not the thing being instrumented**, and it is the
second consecutive session to do so: `#216` was a protective revision to block sets that have
never fired in prod, and `#218` is a guard rail on a write path plus a governance
reconciliation. Both were correct and both were asked for. Neither moved a product lane.

Standing still, unchanged, and unmentioned anywhere else in this file:

- **Lab upload pipeline / interpretation layer / appointment brief** — the medical spine and
  the hero consumer feature. Design Locked at `#48`/`#49`/`#50`; the interpretation producer
  is complete and delivered, the hub shell is BUILT but **held for review** and has an
  `#116`/`#121` deploy probe that was never run.
- **Brief B — renal derived metrics.** Precondition met since `#217`, fork closed, spec
  amended by chat. Still not built. It has now been "next session" for two sessions.
- **Readiness / Banister build.** OWED. The HRV data precondition has been met since
  2026-07-29; `model_forecast` and `model_confidence` exist on the response and the model
  behind them is unbuilt.
- **CBT-I beyond the trigger.** The user surface (interim) and module phase 2 (engine +
  surfaces + ISI) are both untouched. This session hardened the accept path; nobody has yet
  built the surface that path serves.
- **Multi-user paths (`Q99`) and `Q100`** — Cooper's key authenticates to an empty account.
  Blocked on Cooper, not on code, and has been for five days.

The cross-repo governance lane is now **nearly empty** — three of its four rows discharged
today — so it will not supply the next session's work by default. That is the point of
naming this list: the queue a reader would infer from this document is governance, and the
queue that actually matters is above.

### Still-owed governance, so it is not re-derived

The one surviving cross-repo row — extend the `#NEXT` rule beyond DECISIONS entries — stays
OWED with a **mechanical**, not editorial, blocker. The orphaning is structural: the guard
anchors on store headings (`^### #NEXT` / `^## Q#NEXT`) and the claim step's file scope is
the stores, so a `#NEXT` written into a docstring is invisible to **both** and lands green.
The fix is (a) a claim-time sweep outside the stores and (b) an allowlist for the guard's own
fixtures, which legitimately contain placeholder tokens.

Branch 1 exercised (a) by hand and the asymmetry is worth keeping: **13 sites — 4 anchored
per-site in the stores, 9 swept from six source files.** Anchoring is non-optional in the
stores because all three carry pre-existing `#NEXT` tokens belonging to other branches, which
is precisely the PR #71 corruption (55 lines, `#175`); the source files carried only this
branch's, verified by count, so a scoped replace was provably complete there.
