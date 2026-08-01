# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-01 (fifth session that day; the prior close-out is `6c3be0e`).
Branch at close: `master` (clean). Session-open ref: `0b65357`.

**1b is complete.** The interpretation view reads live data and is reachable by clicking.

## 1. Real commits this session

Six commits, all on master and pushed. `git log --oneline 0b65357..HEAD`:

```
f7aa6bc governance: resolve #NEXT -> #160 (on-branch, pre-ff)
d8e366c governance: #NEXT — the group as-of derivation, and the label #159 actually asked for
192ed54 fix(interpretation): a member defers its date badge to the group that already stated it
edb8f13 feat(interpretation): link the interpretation view from the dashboard
7192b6d feat(interpretation): the view reads GET /interpretation instead of the fixture
dc99faa feat(interpretation): group-level as-of date, labelled when off the trigger draw
```

`git log --format="%ad %s" --date=short -10`:

```
2026-08-01 governance: resolve #NEXT -> #160 (on-branch, pre-ff)
2026-08-01 governance: #NEXT — the group as-of derivation, and the label #159 actually asked for
2026-08-01 fix(interpretation): a member defers its date badge to the group that already stated it
2026-08-01 feat(interpretation): link the interpretation view from the dashboard
2026-08-01 feat(interpretation): the view reads GET /interpretation instead of the fixture
2026-08-01 feat(interpretation): group-level as-of date, labelled when off the trigger draw
2026-08-01 governance(branches): row for governance/q69-resolution (DONE, #159 + Q71)
2026-08-01 governance: resolve #NEXT -> #159, Q-NEXT -> Q71 (on-branch, pre-ff)
2026-08-01 governance: #NEXT — Q69 resolves to (e), provenance partitioning; interval sensitivity split out
2026-08-01 chore: session close-out
```

Suite **545 passed**, from a **539** baseline — reconciled. +6 from
`backend/tests/test_group_as_of.py`. **The fixture-based tests still pass**: the oracle is
backend-side and the view switch could not touch it (G6).

**Branch gate.** Three branches, all merged + deleted local and remote, `git cherry origin/master`
empty for each: `feat/1b-step5-wiring` (`edb8f13`), `fix/date-badge-dedup` (`192ed54`),
`governance/as-of-derivation` (`f7aa6bc`). Rows in `BRANCHES.md`. No branch in limbo.

**One process slip, self-corrected:** the badge-dedup fix was first committed onto `master`
directly. Caught before pushing, soft-reset onto `fix/date-badge-dedup`, and landed by ff-merge.

## 2. Pending-queue reconciliation

The brief carried **one conditional** `PENDING` item, gated on *"Step 1's VERIFY finds `#159` does
not fix the derivation."*

| Item | Disposition |
|------|-------------|
| DECISIONS `### #NEXT` — group as-of derivation | **Condition HELD — minted** as **#160** in `d8e366c`, renumbered in `f7aa6bc`. `#159` requires the field and says "derived from its members" without fixing the derivation. |

Master max is now **#160 / Q71**. Nothing decided is uncommitted.

## 3. Cold-resume handoff

### The as-of derivation (`#160`)

**Current side only.** Where members agree it is that date; where they differ the group states the
span and each member carries its own date. The prior side is deliberately excluded: it is `Q71`
(comparison intervals), and a both-sides derivation would mark part of `Q71` resolved by a decision
that does not address it. Live `hpg_axis` is the proof — coherent current side at `2026-05-30`, prior
side spanning `2026-04-20` / `2026-01-07` / `2025-12-27`. A test pins the boundary.

Emitted by the producer, not derived in the view: a view computing `min(member dates)` would be the
second source of truth `sections.js` had before it read `should_surface`.

**`#159` says "labelled", not "labelled and separated"** — the brief misquoted it. An in-place label
is exactly compliant; no minimum-vs-sectioning trade-off was made. Sectioning remains part of (e),
unstarted.

### G2 — shape parity, demonstrated BEFORE the switch

157 deployed-endpoint key paths vs 138 fixture. **Zero structural differences.** Every delta is
either the group `as_of` this increment adds, or a data-dependent optional key:
`protocol_context_snapshot.factors[]` nested keys (fixture user has no declared state; live has 23
factors), `ungrouped[].delta`/`.prior` (the fixture's one ungrouped row has no prior), and the
resolved-vs-unresolved branches of the precondition object (`observed_phase`,
`precondition_factor`, `missing_factor_key`).

Optional keys in both directions are exactly the risk for a hard-reading view, so a **null-audit**
was run over the live payload — 15 grouped members, 51 ungrouped rows, 7 levers — and no field the
view hard-reads is null there.

### G3 — the three non-happy states

| state | render |
|---|---|
| loading | spinner, *"Reading your latest panel…"* |
| empty (404) | *"No lab results yet"*, neutral card, CTA to Metrics |
| error (any other) | **red** panel, *"Could not load your interpretation"* + *"This is a fault, not an empty result"* + the detail |

404 is treated as EMPTY because it is the endpoint's documented no-reports-confirmed case, not a
failure. Error is red, empty is neutral — an error can never render as an empty interpretation.

### G4/G5 — how "live" and "reachable" were confirmed, and the one limit

- The deployed backend serves the route: `GET /interpretation` → **401** without a token, versus
  **404** for a nonexistent path. Discriminating, not just "a response".
- The deployed served bundle carries `to:\`/interpretation\`` (dashboard nav), `L.get(\`/interpretation\`)`
  (the view's call) and `path:\`/interpretation\`` (the route). The fixture is **gone** from the app
  bundle — `Example Pathology` greps 0, and the bundle shrank 407 → 397 kB.
- The view was rendered against the **deployed backend's actual payload**, captured verbatim from
  the container (80 KB, 3 groups, 51 ungrouped) — not invented data. Clicking "Interpretation" on
  the dashboard navigated to `/interpretation` and rendered it.

**The limit, stated plainly:** the browser→production authenticated round trip was not exercised,
because that needs the operator's login and I will not handle a password. Everything either side of
it is verified. One click by the operator closes it.

### Step 4 — reading it as the operator

**It reads honestly.** The header says `Prostate Specific Antigen (PSA) · collected 2026-05-30`, and
the first thing under *What Moved* is the liver group headed **"as of 2026-03-06 · not this panel"**.
The three out-of-range markers — AST 47 H, ALT 53 H, Bilirubin 28 — sit under that label, each with
`vs 2025-12-27` on its delta line. A reader is told the values are from March, and told what they
were compared against. That is the thing this lane existed to fix.

The floor descriptors read as worth reading rather than as boilerplate — they are short, sit under
the heading, and say something the rest of the card does not. They will become skippable once read
a few times, which is exactly what `#158`'s do-not-revisit clause is armed for; nothing to act on
yet.

**Two things noticed, one fixed:**

1. **FIXED —** forty "not this panel" badges on one page, five of them repeating the group header
   verbatim. Signal becoming wallpaper. The member badge now defers to a coherent group; 40 → 35.
   Every automated check passed on the noisy version.
2. **NOT fixed, reported —** the declared-state block renders **23 chips** between the panel header
   and the first finding (`trt · steady`, `tirzepatide · washout`, … ). It is honest and it is
   correct, but it is the largest single block on the page and it sits in front of the content.
   Two of the chips (`hgh`, `ultra_muscleze_night`) render as bare keys because their phase is null.
   Restyling declared-state display is a design decision, not a wiring fix, and was out of scope.

### Open questions unchanged

`Q66`, `Q67`, `Q68`, `Q70`, `Q71` all open and untouched. `Q69` is `DONE → #159`.

### Single clearest next action

**Log in and click Interpretation** — the one step of the round trip I could not exercise.

Then the next substantive lane, and the strongest small one available: **persist `lab_accession`**.
It is parsed at extract and discarded at confirm, and one column unlocks report identity, a dedupe
key above the result rows (`Q68`), and episode scoping (`#159`'s do-not-revisit dependency).
