# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

2026-07-22 · safety-threshold gate (#104 → #106, Q34 closed, Q41 minted)

## 1. Real commits this session

Session-open ref: `d22eeba`. Landed on `master` at **`caf5204`**, pushed.

```
caf5204 gov(handoff): written go for f078f1c; mutation-verification rule receipted
f078f1c governance: DECISIONS_LOG #104/#105/#106, Q34 closed, Q41 minted
262c9ac feat(interpretation): safety_gate as gate 3; news_gate gains a non-demotable arm
436111a reference: safety_thresholds.json schema + guard, no live entries
95808fe gov(handoff): receipt — safety-threshold gate brief received, not started
```

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-07-22 gov(handoff): written go for f078f1c; mutation-verification rule receipted
2026-07-22 governance: DECISIONS_LOG #104/#105/#106, Q34 closed, Q41 minted
2026-07-22 feat(interpretation): safety_gate as gate 3; news_gate gains a non-demotable arm
2026-07-22 reference: safety_thresholds.json schema + guard, no live entries
2026-07-22 gov(handoff): receipt — safety-threshold gate brief received, not started
2026-07-21 chore: session close-out
2026-07-21 governance: DECISIONS_LOG #103, FEEDBACK §17 — evidence that looks like evidence
2026-07-21 gov(handoff): receipt — control-identity and check-coupling rules received
2026-07-21 governance: DECISIONS_LOG #101/#102, OPEN_QUESTIONS Q40, Q38 append
2026-07-21 reference: four erythroid RCV constants from Coskun et al.
```

Maxima now: **DECISIONS #106 · questions Q41 · FEEDBACK §17.**
Backend suite **258 passed** (206 → 222 → 258). No `alembic/`, `routers/` or `frontend/` touched.

## 2. Pending-queue reconciliation

| Brief item | Outcome |
|---|---|
| Step 0 — receipt before touching anything | **LANDED** `95808fe`, alone |
| Step 1 — four verifications with controls | **VERIFIED**; one premise narrowed — see below |
| Step 2 — `safety_thresholds.json`, no live entries | **LANDED** `436111a` |
| Step 3 — schema test + negative control | **LANDED** `436111a`, 16 tests |
| Step 4 — `gates.safety_gate()` | **LANDED** `262c9ac`; one deviation — see below |
| Step 5 — `news_gate` second arm, non-demotable | **LANDED** `262c9ac` |
| Step 6 — producer wiring + key rename | **LANDED** `262c9ac`; **three** tests moved, not two |
| Step 7 — gate tests (+ the added shape guard) | **LANDED** `262c9ac`, 36 tests |
| LOG | **LANDED** `f078f1c` — #104/#105/#106, Q34 `DONE → #104`, Q41 minted |
| Written go (#102) | **LANDED** `caf5204` before the merge acted on it |

### Three divergences from the brief, all deliberate

1. **The whole-dict risk was misidentified — and the correction changed the implementation.** The
   brief gated on the oracle tests being field-by-field; they are. But the live constraint is **three
   exact-dict asserts on `news_gate`** (`fsh:219`, `ast:227`, `vitamin_d:266`) pinning that return
   shape whole. They forced the safety arm to be an **append to `basis`**, never a sibling key. Had
   the arm been added as a key it would have passed today (no live asset → `band_change` always null)
   and broken the moment an asset landed.
2. **The resolution table has an unenumerated case that fails in the worst direction.** *Agreeing
   operator, bound below all bands* — `>0.30` against a band at 0.50. First-match-wins falls through
   to the plain comparison and reports `not_in_band`, but the true value is unbounded above and could
   sit in any band: a **false negative on a safety gate**. Resolved to `censored_indeterminate`.
   The brief's principle is preserved in the other direction — `>0.55` against 0.54 is decidable.
   Chat confirmed the correction: an agreeing operator is decidable **only when the bound alone
   settles it**.
3. **The rename moved three tests, not two.** The third is `test_all_stable_group_is_not_moved` — the
   G6 non-vacuity guard proving the predicate is not hardwired true. Now
   `test_all_stable_group_does_not_surface`, still asserting `False`, so the predicate stays
   falsifiable at exactly the moment it gained a third input.

### The guard was verified by mutation, not by passing

The added shape test was confirmed by **reimplementing the safety arm as a sibling key** and running
the suite: **6 tests fail**, including the shape assertion. Restored, and the restoration verified by
identity — `basis.append(...)` present ×1, mutant form ×0. This matters because the three pre-existing
exact-dict asserts **cannot do that work yet**: with no live asset, `band_change` is always null and
`basis` is never touched, so they are inert with respect to the thing they would protect — the §11
shape. Agreed as a standing rule and receipted at `caf5204`: **a guard is verified by mutation, not by
passing.** Canonical home is `FEEDBACK` §18 when a brief actions it. **Not yet landed — owed.**

## 3. Cold-resume handoff

**Branch:** `master` @ `caf5204`, pushed, clean. Untracked stray: `.claude/launch.json` (known).

| Check | Result |
|---|---|
| Gate 3 | `gates.safety_gate(current, prior, thresholds=None)` — level vs authored policy constant |
| Gate 1 second arm | `news_gate(delta_obj, safety_gate=None)`; appends `safety_band_<change>` to `basis`, return shape exactly `{is_news, basis}` on every path; **not demotable**, recorded in the module docstring before demotion logic exists |
| Asset | `thresholds` **empty**; `_deferred.haematocrit` holds 0.50/0.52/0.54 + `contested` + `value_plausibility`, blocked on citation capture |
| Schema guard | Validator **raises** on `recommended_action`; 16 tests, every rule paired with a positive control |
| Contract key | `is_moved` → `should_surface`; `grep is_moved backend/ --include=*.py` = 2, both inside the docstring explaining the rename |
| #98 guard | new asset `isascii()` True, **0** literal em dashes (the guard caught 3 typed into prose) |
| Shared block G1 | `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232 — untouched |
| `interpretation_s2.json` | **UNCHANGED** |
| `marker_groups` / `lever_dictionary` / `marker_canonical` | untouched |
| Backend tests | **258 passed** |
| Post-push identity check | `producer.py` on the pushed SHA: `safety_gate` ×6, `"is_moved"` ×**0**, `should_surface` ×2; control master README 200 |

**Branch terminal-state gate — passes.** One branch touched (`feat/safety-threshold-gate`), merged and
deleted local + remote. The four pre-existing locals are all rowed and all on origin:

```
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

**Where the fork stands — the mechanism for danger exists and is tested; the content is empty.**
`safety_gate` returns `no_asset` for every marker, so **the 0.50–0.54 band is still dark**. That is
**Q41**, owner Luke: three band values (0.50 cohort definitions, 0.52 AUA / Endocrine Society, 0.54
Canadian guidance) and two contested-position claims, none with a verified DOI. A citation-capture
session of the same shape as the Coşkun work. Landing them uncited would be exactly what #99 refused
for `haemoglobin` — a citation pointing at a source that does not state the number.

**OWED, this session:** `FEEDBACK` §18 (mutation rule) is receipted in `HANDOFF.md` but not landed.

**OWED, carried:** `haemoglobin`'s per-parameter figure unread from Buoro 2018 full text. **Q37** (I1
has no enforcement; `alt` is a live violation). **Q33** (shared block still says `parked`). HCA **Q11**
should close `DONE → #93` from an HCA-rooted session; HCA **Q9 item 1** and **Q10** remain open there.
O3's re-verify of `feat/interpretation-view-skeleton` now also covers the `should_surface` rename.
`probe_resolver.py` container run and `hevy-resolver-activation` limb 2, both blocked on Anthropic API
credit.

**4b list, all correctness rather than coverage:** Q36 (discriminator semantics — `#96` took a side,
making it 2-to-1), Q37 (I1 enforcement), Q38 (interval-banding), Q39 (`effect_locus`), Q40
(asymmetrical RCV).

**Single clearest next action:** capture DOIs for the three haematocrit band values and the two
contested-position claims, then promote `_deferred.haematocrit` into `thresholds`. That is the last
thing between this repo and the 0.50–0.54 band, and the schema test starts validating something the
moment it lands.
