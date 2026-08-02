# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-02. Branch at close: `feat/hub-shell` (pushed, **not merged**).
Session-open ref: `35e8a1d`.

**The `#150` hub shell is built and held for review.** `/dashboard` is a module tile grid with
chat docked; the two panels now have their own routes. Nothing is on master.

## 1. Real commits this session

`git log --oneline 35e8a1d..HEAD`:

```
001df4c feat(frontend): #150 hub shell — tile grid on /dashboard, chat docked, panels relocated
```

Plus this close-out commit. Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-08-02 feat(frontend): #150 hub shell — tile grid on /dashboard, chat docked, panels relocated
2026-08-02 governance: question-state vocab (carve+sweep), Q65 collapse, Q73/Q74, FEEDBACK §22, CLAUDE accretion compress, ROADMAP NEXT reconcile
2026-08-02 governance: renumber #NEXT -> #161 and land; Q72 carries the owner's position
2026-08-02 governance: #NEXT (verdict-vs-measurement scoping), Q72, BRANCHES row
2026-08-02 feat(engine): capability_observations — graded, timestamped measurement
2026-08-01 chore: session close-out
2026-08-01 governance: resolve #NEXT -> #160 (on-branch, pre-ff)
2026-08-01 governance: #NEXT — the group as-of derivation, and the label #159 actually asked for
2026-08-01 fix(interpretation): a member defers its date badge to the group that already stated it
2026-08-01 feat(interpretation): link the interpretation view from the dashboard
```

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried in. The input was a **code-ready brief** (hub shell,
`#150`), reconciled step by step. Everything in it is either landed at `001df4c` or listed as
outstanding — nothing is silently dropped.

| Brief step | Outcome |
|---|---|
| 0 — cut branch, report max decision number | **Landed.** Max is **#161** (period-agnostic `^### [0-9]+`), matching the brief. Branch cut from master. |
| 1 — chat-dock layout wrapper | **Landed.** `HubLayout` docks one `ChatPanel`: static right rail ≥ md, fixed bottom sheet < md. **No prop or data-path change** — `pendingFeedback` / `onFeedbackSent` exactly as `Dashboard` passed them; `ChatPanel.jsx` unedited. No standing-context wiring added. |
| 2 — relocate the two panels | **Landed.** `/recovery` and `/training` host `HealthPanel` / `WorkoutPanel` full-width under `RequireAuth`. Neither panel's internals edited. |
| 3 — tile grid on `/dashboard` | **Landed.** Six tiles + prominent AM/PM. Every prior header destination enumerated and re-homed *before* any link was deleted (table in §3). |
| 4 — interpretation tile, `Q63` → (a) | **Landed, amended.** Copy is `What Moved: <n> · Stable: <m> · collected <date>` — *not* `generated`. See §3 "Corrections". |
| 5 — Constraint B | **N/A — no forecast on tile.** The Recovery tile is navigation-only (label + static description); it previews no readiness number, so `#150` Constraint B does not engage. |
| 6 — no chat-context seeding | **Held.** Tiles are plain doorways. Nothing touches the standing prompt or the request-scoped `find_marker` → `render_asked_lab_value` path (`#59`). |
| LOG | **Landed** as `### #NEXT` in `DECISIONS_LOG.md`; `OPEN_QUESTIONS` `Q63` → `DONE → #NEXT`. Adjudicated as a standalone decision, not pure application of Constraint A — `#150` permits candidate (a) but does not select it over (b)/(c), and the `generated`→`collected` amendment needs its own "How you know". |

**Provisional, not done:** `#NEXT` is unresolved and `Q63` reads `DONE → #NEXT` because the branch
is **not merged**. The integer is claimed only at the fast-forward, per number-at-merge.

## 3. Cold-resume handoff

### What exists now

`feat/hub-shell` at `001df4c`, pushed to `origin`, **not merged**. Frontend only; no backend delta.

- `frontend/src/components/HubLayout.jsx` — the shell. Header (back / title / mobile chat toggle /
  Sign-out), module area as `{children}`, and **one** `ChatPanel`. The single instance is
  load-bearing: a rail plus a separate drawer would mount twice, both receive `pendingFeedback`,
  both `POST /chat`, and both write the same `chat_history_<sub>` key. One element, position
  switched at the breakpoint. Sheet rules are `max-md:`-scoped so the rail needs no `md:` resets.
  A `fill` prop bounds the module area for the panel pages so their `h-full` + internal scroll
  behave as they did in the old Dashboard column.
- `frontend/src/components/hub/HubChatContext.js` — `sendToChat`. A separate module only because
  react-refresh requires a component file to export components and nothing else.
- `frontend/src/components/hub/{Tile,InterpretationTile}.jsx`, `interpretationTileCopy.js`.
- `frontend/src/pages/{Recovery,Training}.jsx`; `Dashboard.jsx` rewritten as the hub;
  `App.jsx` + two routes.

### Corrections made to the brief (expected output, not failure)

1. **`generated` → `collected` on the interpretation tile.** `Q63` (a) and the brief both said
   "generated `<date>`". `meta.generated_at` exists but `GET /interpretation` builds the payload per
   request (`producer.py:560` stamps `datetime.now`), so it is always "now" — the tile would read
   "generated 2 Aug" on 2 Aug over an unchanged draw. Shipped `collected`, from
   `meta.trigger_panel.collected`. `Q63`'s own "30 May" *is* that collection date in the fixture.
2. **The header was seven links, not six.** `#150` rule 2 lists six; `Interpretation` was added
   since (`#158`, with a comment anticipating this retirement). All seven re-homed.
3. **"How you know" is not a test.** The brief's LOG draft asserted a test on the tile string. This
   repo has **no frontend test runner** — no vitest/jest, no `test` script, no spec files under
   `frontend/src`. Adding one is tooling adoption, not a layout job. The copy was extracted into a
   pure function and evaluated through Vite's own resolver instead; the assertion is recorded OWED.
4. **ANCHOR could not hold as written.** `git cherry origin/master` was not empty at branch cut —
   `master` was already **ahead 1** of `origin/master` (`35e8a1d`, from the prior session). Not this
   session's work; flagged rather than silently pushed. See "Outstanding".

### Gate evidence

- **Step 1** — no prop/data-path change (expected: none, confirmed). `ChatPanel.jsx` not in the diff.
- **Step 2 coupling finding** — `HealthPanel` is self-contained (fetches `/health/summary`, held no
  Dashboard state). `WorkoutPanel` is **not**: it takes `onFeedback`, which in the old Dashboard set
  Dashboard-held `pendingFeedback` that fed `ChatPanel` — panel → Dashboard state → chat. That state
  moved to `HubLayout` and is reached via `useHubChat`; the panel itself is unedited.
  `git diff --stat` shows new pages + `App.jsx` + `Dashboard.jsx` only — **not** `HealthPanel` /
  `WorkoutPanel` / `ChatPanel`.
- **Step 3 orphan check** — every prior header destination, re-homed before deletion:

  | Old header control | Destination | Now |
  |---|---|---|
  | AM | `/checkin-am` | Prominent `CheckInButtons` above the grid |
  | PM | `/nightly` | Prominent `CheckInButtons` above the grid |
  | History | `/checkin-history` | History tile |
  | Labs | `/metrics` | Labs tile |
  | Interpretation | `/interpretation` | Interpretation tile |
  | Settings | `/settings` | Settings tile |
  | Sign out | (action) | `HubLayout` header, on every route |

  Verified in-browser: 8 `main` destinations render — the six tiles plus both check-in buttons.
  `/recovery` and `/training` are new reachable surfaces. `/checkin` was already URL-only on master
  (no link anywhere) — unchanged, not a regression introduced here.
- **Step 4 copy string**, evaluated through Vite's own resolver against the committed fixture and a
  synthetic payload:
  `What Moved: 2 · Stable: 0 · collected 30 May` (fixture)
  `What Moved: 2 · Stable: 5 · collected 30 May` (2-moved / 5-stable)
  Counts and a date only; no priority phrasing. Counts come from `splitSections` — the view's own
  placement function, consuming `should_surface` rather than recomputing it.
- **Build / lint** — `npm run build` clean (401.69 kB). eslint **5 errors, unchanged from the master
  baseline** (`ChatPanel`, `WorkoutPanel`, `Settings` — all pre-existing; an added 6th was fixed by
  moving the chat context to its own module). Frontend-only; backend untouched, no suite delta.
- **Browser verification** (offline harness: backend pointed at a closed port so the 401 redirect
  does not fire). At **375×812**: sheet off-screen when closed (`top` = 812 = viewport height); open
  places it flush-bottom with the chat input visible and the backdrop present; backdrop tap
  re-closes. At **1280×800**: rail `position: static`, side-by-side with `main` (853 + 427 = 1280),
  full height, border-left, no sheet radius/shadow, toggle and Close hidden. **One** `ChatPanel`
  instance at both widths. Note: the preview pane does not composite
  (`document.visibilityState === "hidden"`), so CSS transitions never advance — settled positions
  were read with the transition disabled. A harness artifact, not a defect; it briefly presented as
  a stuck-translate bug and is not one.

### Open questions touched

- `Q63` — **DONE → #NEXT** (integer at ff). Resolved to candidate (a), amended to `collected`.
- No other question's state changed.

### Outstanding (owner: Luke)

1. **Merge decision on `feat/hub-shell`.** Held for review per the brief, not merged.
2. On merge: resolve `#NEXT` on-branch pre-ff (re-read master max at that instant — do **not** reuse
   #161), then `git land feat/hub-shell`.
3. **Deploy probe, not yet run** (post-merge; `#116` timing + `#121` coverage):
   `railway service health-app-frontend`, then `railway deployment list` → SUCCESS, then fetch the
   live `assets/index-*.js` and grep `HRV, sleep and overnight vitals` — confirmed present in the
   local production bundle, so it survives minification.
4. **`master` is ahead 1 of `origin/master`** (`35e8a1d`, prior session). Not touched this session
   and not pushed here — the owner's call. It is reachable on `origin` via `feat/hub-shell`, so chat
   can read it, but `origin/master` itself still lags. Resolve with `git push origin master`.
5. **No frontend test runner.** The `#47` no-priority-phrasing assertion on the tile string is
   inspection-backed, not test-backed. Standing up vitest is its own decision.
6. **`BRANCHES.md` column drift** (pre-existing, not introduced here): rows from
   `governance/q69-resolution` onward carry **6** columns against a **5**-column header, so their
   trailing cell is dropped when rendered. The new row matches the header at 5.

### Single next action

Review `feat/hub-shell` (`001df4c`, pushed) and decide merge. If merging: resolve `#NEXT` on-branch
pre-ff, `git land feat/hub-shell`, then run the frontend deploy probe in item 3.

### Governance stores changed this session

`DECISIONS_LOG.md` · `OPEN_QUESTIONS.md` · `ROADMAP.md` · `BRANCHES.md` · `CLAUDE.md`
(`FEEDBACK.md` and `Ideas.md` unchanged.)
