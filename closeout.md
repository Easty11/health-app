# Code session close-out — 2026-09-09

## 1. Real commits this session

Session-open ref: `52a12ce` (master tip at session start, PR #171 merge). All work landed
via PR #172 (merge commit `81c1fb9`), branch `claude/exposure-ui-read-increment-5j86um`
(merged + remote-deleted).

```
81c1fb9 Merge pull request #172 from Easty11/claude/exposure-ui-read-increment-5j86um
5f9b0d3 gov: Exposure UI increment 1 (read) — DECISIONS #272, ROADMAP, BRANCHES
63abd49 feat(frontend): Exposure UI increment 1 (read) — the app consumes /engine/next
```

- `63abd49` — **feature (F1–F5).** `exposureTileCopy.js` (pure, tested); `ExposureTile.jsx`
  (four states, REPLACES the static Dashboard Training tile); `ExposurePanel.jsx` (full
  read surface on `/training`, above `WorkoutPanel`); `Training.jsx` (stack owns its own
  scroll, `HubLayout`/`WorkoutPanel`/`Tile` unedited); `Dashboard.jsx` (tile swap). Two
  fixtures — `engineNextDecompression.json` (live prod payload, user 1, verbatim) and
  `engineNextHeld.json` (hand-authored, probe + within-phase-warning path). 23 new vitest
  tests; full frontend suite green (10 files, 91 tests).
- `5f9b0d3` — **governance (F6), disjoint commit.** DECISIONS #272; ROADMAP NEXT rows for
  Exposure UI increment 2 (write) and increment 3 (dose, blocked on Q106); BRANCHES row.
  Additions only — #176(c) diff-shape clean; `placeholder guard (POSIX)` green.

The close-out commit itself (this file + CLAUDE.md Recent-landings) is separate, below.

## 2. Pending-queue reconciliation

**No pending-commit queue was carried in.** This session did not open from a chat `;cc`
handoff; it implemented the attached `claude_EXPOSURE_UI_READ_BRIEF.md` directly
(chat-ratified, non-migration → self-merge on green under § Merge disposition). The one
missing input — the `engineNextDecompression.json` payload, referenced as "the JSON below"
but absent from the brief — was supplied by the operator on request and written verbatim;
no item is provisional. Everything decided this session is committed (§1) and merged.

## 3. Cold-resume handoff

**Maxima:** DECISIONS `#272` · OPEN_QUESTIONS `Q139`.

**Branch:** `claude/exposure-ui-read-increment-5j86um` — merged (PR #172, `81c1fb9`),
remote deleted, rowed in `BRANCHES.md` DONE → #272. Local copy can be deleted. On `master`.

### What landed
Exposure UI increment 1 (read), `#272` — the React app consumes `/engine/next` for the
first time. Data-backed Training tile + `ExposurePanel` on `/training`. Read-only; no chat
seeding (#59 — `context_builder` serves the standing prompt); no backend/schema change. The
no-profile mapping (404 OR 200-with-no-`fortify.target` → empty; else error) was determined
in-tree, not from the brief.

### What was NOT touched — the standing lanes, unchanged this session
This was a **frontend read increment**; two feature lanes stood still and remain the real
queue:

- **Exposure UI increment 2 (write)** — open next phase / close to baseline / phase history
  from the panel; the review badge (#232/#228) becomes actionable. First `POST` from this
  surface. Needs the phase open/retire write endpoints verified server-side first.
  (ROADMAP NEXT, added this session.)
- **Exposure UI increment 3 (dose)** — **blocked on `Q106`** (how a slot's `minutes`
  reaches the prescription — still OPEN, nothing changed) and the Weekly-resolver lane
  (#221-deferred due-slot resolver, ROADMAP NOW). The panel would show the declared
  microcycle and say *declared, not scheduled*.
- **Interpretation increment 3 frontend (`Q139`, OPEN)** — the tap-to-thread surface
  (build-sequence step 5). Backend spine landed at `#268`; the frontend surface is
  unbuilt and needs served-bundle verification (#121, unseeable-surface rule). Untouched
  this session.
- **Dated NOW items** (Lab upload pipeline, Interpretation layer go-live follow-ups,
  Appointment brief) — unchanged.

Note for the next session: the last several sessions have been engine-tidy (#271) and now
its UI read (#272) plus governance. The exposure lane now has a *read* surface but no
*write* surface, and the interpretation lane's increment 3 has a backend but no frontend —
both are frontend-surface picks gated on verification, not on undecided design.

### Single clearest next action
Pick **Exposure UI increment 2 (write)** — it is unblocked once the phase open/retire write
endpoints are confirmed present (verify in `backend/routers/training_phase.py` first), and
it makes the #272 read panel actionable. Alternative small pick: the **Interpretation
increment 3 frontend (`Q139`)**. Increment 3 (dose) stays blocked on `Q106`.
