# Close-out — 2026-08-08 (Brief D rev 2: checker exit-contract repair + docstring de-propagation)

Branch at write: `chore/session-closeout-0808`. Master after the session's feature landing: `b4cf1ac` (PR #36).

---

## 1. Real commits this session

Session-open ref: `73d5cb8` (master at open). Work landed on `gov/checker-exit-contract` via **PR #36** (merge `b4cf1ac`).

```
d48956a  fix: check_governance_placeholders — a read that cannot run must exit 2
ba6d319  docs: check_governance_placeholders — strike two cross-repo enforcement claims
faecf8b  gov: DECISIONS_LOG #183/#184 + OPEN_QUESTIONS Q87
b4cf1ac  Merge pull request #36 from Easty11/gov/checker-exit-contract
```

Plus this close-out commit on `chore/session-closeout-0808` (not yet landed at write).

Immutable dates (`git log --format="%ad %s" --date=short`):

```
2026-08-08  Merge pull request #36 from Easty11/gov/checker-exit-contract
2026-08-08  gov: DECISIONS_LOG #183/#184 + OPEN_QUESTIONS Q87
2026-08-08  docs: check_governance_placeholders — strike two cross-repo enforcement claims
2026-08-08  fix: check_governance_placeholders — a read that cannot run must exit 2
2026-08-07  Merge pull request #35 from Easty11/chore/session-closeout-0807
2026-08-07  chore: session close-out
```

---

## 2. Pending-commit queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — the work came from **Brief D (rev 2)**, a Code-executed brief, not a chat close-out handoff. Every deliverable landed on master:

- `read()` exit-contract fix .................. LANDED  `d48956a` (→ #183)
- docstring de-propagation (two strikes) ...... LANDED  `ba6d319` (→ #184)
- DECISIONS_LOG #183, #184 ................... LANDED  `faecf8b`
- OPEN_QUESTIONS Q87 ......................... LANDED  `faecf8b`
- `#NEXT` → #183/#184, `Q#NEXT` → Q87 ......... resolved at the merge window (master re-read == 182 / Q86, local == origin/master, nothing advanced)

Nothing decided-but-uncommitted. Brief E's handoff payload (§3) is *emitted* here, not committed — it is a cross-repo (HCA) input, not a health-app artefact.

---

## 3. Cold-resume handoff

### What landed
**Checker exit-contract repair + docstring de-propagation (Brief D).** The placeholder guard `scripts/check_governance_placeholders.py` — the surface every other governance control rests on — had a `read()` that returned git's `stdout` after checking only the return code:

- a **non-UTF-8 byte** was decoded in a subprocess reader thread → the thread dies, `returncode` stays `0`, a non-string is returned → `re.finditer` raises `TypeError`, a traceback exiting **1** (indistinguishable to CI from a genuine `REFUSED`) where the docstring's contract reserves exit **2** for "a check that could not run";
- an **empty blob** passed silently at **exit 0** — a governance store with no content read as clean.

`read()` now captures bytes, decodes explicitly, and routes every non-run to **exit 2** (non-zero git, `UnicodeDecodeError` naming path+ref, empty/whitespace-only content), on both the `--ref` arm and the working-tree arm. Both defects were reproduced on scratch refs against the unfixed script first (#170); after the fix, four controls with exit codes asserted — clean `0`, placeholder `1`, non-UTF-8 `2`, empty blob `2` — and the scratch refs were torn down (`git ls-remote` clean). The same PR struck two docstring sentences asserting another repo's enforcement state; a file has no means to keep a cross-repo claim current, so the state is read live via `gh api`, not held in the file.

Decisions: **#183** (guard read exit-contract — conformance to the docstring's own contract, not new policy), **#184** (cross-repo docstring strike — extends #182 / HCA #24: evidence is repo-local, not originated about another repo). Question: **Q87** (which cross-repo-parity artefacts are governed, and by what rule — the checker and `closeout.md` are drifted and undeclared; question *stated*, register **not** built — Brief D scope).

### Cross-repo handoff — Brief E (HCA-rooted, NOT runnable from health-app)
HCA mirrors the `read()` fix. Anchors from `origin/master` `b4cf1ac` (git LF blob):

- `read()` mirror target: **33 lines**, md5 `154e1871fab988fda9ce72170db4071f`
- docstring-stripped executable body (dropped through `body[0].end_lineno` = line 51): **97 lines**, md5 `ca648f466a30f6b7a6704e83a2bce490`
- whole file (LF): **148 lines**, md5 `17391735f209a5526ab364954e20bf5d`

After mirroring `read()`, the two docstring-stripped executable bodies differ by **exactly one hunk** — `main()`'s advisory string (health-app "before it lands"; HCA "before the fast-forward"). Expect **one** hunk, not zero; do **not** expect the executable-body md5 to match HCA's.

### Current sprint (ROADMAP NOW — unchanged this session)
- **CBT-I:** resolve **Q45** nap day-attribution — the engine's `naps_min` `date−1` read is live for block 3 and rests on an unverified attribution. Close from VA CBT-I protocol docs / the administering clinician, not the workbook. DATED / contaminating capture now. Owner: Luke.
- Cross-repo propagation debt is pinned in ROADMAP NOW per #112.

### Open questions of note
- **Q87 (NEW)** — cross-repo-parity artefact register: **OPEN**, owner Luke. Build a register naming each cross-repo file, its governing mechanism, and its equivalence criterion — or keep parity ad hoc. Not built here.
- **Q86** — does any report-level required scalar get nulled by a real extraction: **OPEN** watch-point (needs a live 422). Owner: Luke.
- Q85 → `DONE → #178`; Q83 → HC sleep source admission (#175); Q45 gates NOW.

### What was NOT touched (named explicitly, per close-out step 5)
**This is the second consecutive session to go to the governance/guard instrument rather than to the product** (the 0807 session was the shared-block writer-claim correction; this one the checker). The standing feature/product lanes stood still, and the questions gating them:

- **Interpretation layer** — increments 2 (rephrase) → 3 (lever-tap) → 5 (go-live), the sequenced product lane. Not advanced.
- **`feat/cbti-eval-trigger` rework** — OWED and obsolete against master's 4-night engine (`BRANCHES.md` row); its 5-step rework checklist is unstarted. Owner: Luke.
- **Interpretation hub shell (#150 / #162)** — merged, but its #116/#121 frontend deploy probe was never run.
- **CBT-I user surface** — engine built, invisible in-app; gated on **#47** (state-only vs directive) and **Q60**. Untouched.
- **Banister readiness build** — unblocked (HRV data precondition met) but the model is unbuilt.
- **Security:** identify the second credential digest (`9688f2…`) in the transcripts — OWED, cheap, unstarted.
- **Guard:** canonical-surface consistency test (SCHEMA.md vs `models.py`; CLAUDE.md conventions vs DECISIONS_LOG; Samsung-context filter vs call sites) — OWED. Adjacent to Q87: both are "nothing enforces cross-surface / cross-repo consistency."
- **SCHEMA.md** stale for the entire lab family — OWED doc task.

### Single clearest next action
Break the instrument-over-product streak. Two candidates by lane:
- **Cross-repo:** run **Brief E** in HCA — mirror `read()` to md5 `154e1871…` (33 lines), then expect exactly one `main()`-string hunk. (Not runnable from health-app.)
- **health-app product:** start **interpretation increment 2 (rephrase)**, or the **`feat/cbti-eval-trigger` rework** (BRANCHES row checklist).

### Branch terminal states (gate satisfied)
- `gov/checker-exit-contract` — **DONE**, merged PR #36 at `b4cf1ac`, local + remote deleted. Self-row was missed on-branch; rowed by this close-out.
- `chore/session-closeout-0808` — this close-out; **DONE** at land (self-row convention).
- `feat/cbti-eval-trigger` — **OWED**, pushed `fec0324`, rowed in `BRANCHES.md`, pre-existing and untouched this session.

### Governance stores changed this session
`DECISIONS_LOG.md`, `OPEN_QUESTIONS.md` — both landed via PR #36. `CLAUDE.md` (Recent-landings), `BRANCHES.md`, and `closeout.md` are updated by this close-out.
