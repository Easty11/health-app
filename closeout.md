# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

2026-07-22 · safety-threshold gate (#104 → #106, Q34 closed, Q41 minted) + §19 receipt

## 1. Real commits this session

Session-open ref: `d22eeba`. Landed on `master` at **`b3af58a`**, pushed, in sync.

```
b3af58a gov(handoff): receipt — resolution-table-is-a-hypothesis rule (FEEDBACK §19 candidate)
4f3582b chore: session close-out
caf5204 gov(handoff): written go for f078f1c; mutation-verification rule receipted
f078f1c governance: DECISIONS_LOG #104/#105/#106, Q34 closed, Q41 minted
262c9ac feat(interpretation): safety_gate as gate 3; news_gate gains a non-demotable arm
436111a reference: safety_thresholds.json schema + guard, no live entries
95808fe gov(handoff): receipt — safety-threshold gate brief received, not started
```

`4f3582b` was this session's first close-out (the safety-gate work). `b3af58a` is a
**ledger-only** commit since — the §19 receipt — carrying no `#N` and no code/store change, so
the "Recent landings" block is unchanged and correct at `#104/#105/#106`.

Maxima now: **DECISIONS #106 · questions Q41 · FEEDBACK §17.**
Backend suite **258 passed** (206 → 222 → 258). No `alembic/`, `routers/` or `frontend/` touched.

## 2. Pending-queue reconciliation

Substantive brief (safety-threshold gate) — all landed; full detail in the commit bodies:

| Brief item | Outcome |
|---|---|
| Step 0 — receipt before touching anything | **LANDED** `95808fe`, alone |
| Step 1 — four verifications with controls | **VERIFIED**; the whole-dict premise was narrowed |
| Steps 2–3 — asset + schema test with negative control | **LANDED** `436111a`, 16 tests |
| Steps 4–5 — `safety_gate()` + non-demotable `news_gate` arm | **LANDED** `262c9ac` |
| Step 6 — producer wiring + `is_moved` → `should_surface` | **LANDED** `262c9ac`; **three** tests moved, not two |
| Step 7 — gate tests + the added shape guard | **LANDED** `262c9ac`, 36 tests |
| LOG | **LANDED** `f078f1c` — #104/#105/#106, Q34 `DONE → #104`, Q41 minted |
| Written go (#102) | **LANDED** `caf5204` before the merge acted |

### The three deliberate divergences (unchanged from the safety-gate close-out)

1. The live constraint was **three exact-dict asserts on `news_gate`**, not the oracle tests — forcing
   the safety arm to append to `basis`, never add a sibling key. Verified by mutation (see §18 below).
2. The resolution table's *agreeing-operator, bound-below-all-bands* case (`>0.30` vs a 0.50 band)
   falls through to a false `not_in_band` — a false negative on a safety gate. Resolved to
   `censored_indeterminate` (#105). This is the worked instance behind §19.
3. The rename moved **three** tests; the third is the G6 non-vacuity guard, now
   `test_all_stable_group_does_not_surface`, still asserting `False`.

### Two standing rules agreed this session, both receipted, both still owed to FEEDBACK

- **§18 — a guard is verified by mutation, not by passing.** Earned when the `news_gate` shape guard
  was confirmed by reimplementing the arm as a sibling key and watching 6 tests fail. Receipted at
  `caf5204`. **Not landed.**
- **§19 — a resolution table is a hypothesis about the input space until Code enumerates it.** Prose
  has no totality check; code must return something for every input, which is what exposed both #104's
  and #105's table gaps. Receipted at `b3af58a`. **Not landed.**

Both were held to the ledger rather than folded into `FEEDBACK.md`: each is chat-agreed canon that
needs a brief to carry it across and a read before it merges, and the safety-gate go authorised
*verified bytes*, not a later `FEEDBACK` section. The receipt is the in-flight protection; the landing
is a deliberate act. They land as **§18** and **§19** (numbers pinned in the receipts) when a brief
next actions the pair.

## 3. Cold-resume handoff

**Branch:** `master` @ `b3af58a`, pushed, clean, in sync. Untracked stray: `.claude/launch.json` (known).

| Check | Result |
|---|---|
| Gate 3 | `gates.safety_gate(current, prior, thresholds=None)` — level vs authored policy constant |
| Gate 1 second arm | appends `safety_band_<change>` to `basis`; shape exactly `{is_news, basis}`; **not demotable**, recorded in the module docstring before demotion logic exists |
| Asset | `thresholds` **empty**; `_deferred.haematocrit` holds 0.50/0.52/0.54 + `contested` + `value_plausibility`, blocked on citation capture |
| Schema guard | validator **raises** on `recommended_action`; 16 tests, every rule paired with a positive control |
| Contract key | `is_moved` → `should_surface`; `grep is_moved backend/ --include=*.py` = 2, both inside the explaining docstring |
| #98 guard | new asset `isascii()` True, **0** literal em dashes |
| Shared block G1 | `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232 — untouched |
| `interpretation_s2.json` / `marker_groups` / `lever_dictionary` / `marker_canonical` | untouched |
| Backend tests | **258 passed** |

**Branch terminal-state gate — passes.** No feature branch was touched this session (the safety-gate
branch merged + deleted at the first close-out; `b3af58a` committed directly to master as a ledger
line). The four pre-existing locals are all rowed and all on origin:

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
session of the Coşkun shape; landing them uncited would be exactly what #99 refused for `haemoglobin`.

**OWED, this session:** `FEEDBACK` **§18** (mutation rule, receipted `caf5204`) and **§19**
(resolution-table rule, receipted `b3af58a`) — both need a brief to land them.

**OWED, carried:** `haemoglobin`'s per-parameter figure unread from Buoro 2018 full text. **Q37** (I1
has no enforcement; `alt` is a live violation). **Q33** (shared block still says `parked`). HCA **Q11**
should close `DONE → #93` from an HCA-rooted session; HCA **Q9 item 1** and **Q10** remain open there.
O3's re-verify of `feat/interpretation-view-skeleton` now also covers the `should_surface` rename.
`probe_resolver.py` container run and `hevy-resolver-activation` limb 2, both blocked on Anthropic API
credit.

**4b list, all correctness rather than coverage:** Q36 (discriminator semantics), Q37 (I1 enforcement),
Q38 (interval-banding), Q39 (`effect_locus`), Q40 (asymmetrical RCV).

**Single clearest next action:** capture DOIs for the three haematocrit band values and the two
contested-position claims (Q41), then promote `_deferred.haematocrit` into `thresholds` in one edit —
at which point the schema test starts validating something and a haematocrit of 0.52 produces a
surfaced band with its sources, at a value the lab will not flag and the delta gate will not catch.
The two owed `FEEDBACK` rules (§18/§19) can ride the same or a separate governance brief.
