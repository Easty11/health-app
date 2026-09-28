# Close-out — Typed `constraint` and `finding` entries (#342, #343)

## Real commits this session

Session open: master `360b385` at G0 (read-only). Reset onto `11be50e` after #269 merged, then onto `8324a28`
after #270, before any commit. Branch `claude/blissful-brahmagupta-mk7hcf` (harness-assigned; recorded in BRANCHES).

`git log --format="%h %ad %s" --date=short 8324a28..a363061`:

```
a363061 2026-09-28 Merge pull request #271 from Easty11/claude/blissful-brahmagupta-mk7hcf
580d8d2 2026-09-28 gov(typed-entries): #342/#343, Q9/Q20 ruled, Q181–Q184, SCHEMA §037/§038, paste addressing (S7)
85ce419 2026-09-28 chore: resolve this branch's #NEXT code references to #342 (constraint) / #343 (finding)
0b63466 2026-09-28 feat(scripts): seed_constraints.py — injury restrictions to advisory constraints, dry-run first (S6)
ce16bb6 2026-09-28 fix(sweep): a constraint parented to the swept injury without with_parent survives it (G5 ruling 1)
5d1b732 2026-09-28 feat(sweep): the restriction audit recognises typed constraints (S5)
1f64edc 2026-09-28 feat(context,mcp): render typed constraints and findings; chat proposal guidance (S4)
24273cb 2026-09-28 feat(engine): is_contraindicated reads confirmed engine-tier constraints (S3)
e1ace6c 2026-09-27 feat(knowledge): typed `finding` entries, confirm/retract, and the read lift (S2)
814fe01 2026-09-27 feat(knowledge): typed `constraint` entries — validator, confirm/resolve routes, chat guards (S1)
```

PR #271 merged `--merge` on green as `a363061`, and the remote branch was auto-deleted. Master's maxima were
re-read immediately before the merge: #341 / Q180 → #342/#343, Q181–Q184. Deploys `196d3121` (backend) and
`8ee3b839` (frontend) both show SUCCESS. Plus this close-out commit (`chore: session close-out`) on the same
branch, restarted from `a363061`.

Tests: backend 2031 → 2216, frontend 240 → 241; eslint clean on the touched frontend files.

## Pending-queue reconciliation

No `;cc` pending-commit queue was carried in. The brief and the chat rulings below arrived as addressed paste
blocks, and every one landed:

- **G0 rulings.** R1–R5 yes. D1 (engine tier = region keys only), D2 (#60 firewall, not #181), D3 (shared pure
  lift), D4 (key-collision + chat-cannot-retire guards, resolve route), D5 (36 regions). S5 parent rule. Q9 split.
  CLAUDE.md paste-addressing rule. ROADMAP step-(3) narrowing. → `814fe01`…`580d8d2`.
- **G1 rulings.** Chat guidance with a declared byte difference; `confirmed_on` stamped by the route only;
  finding statuses; the onboarding edge left as a known limit (comment only). → `1f64edc`, `e1ace6c`.
- **G2 rulings.** Optional engine-tier `side`; engine tier = `block` only (Q183); due tags. → `24273cb`,
  `1f64edc`.
- **G3 ruling.** Findings budget 2,000 chars with 280-char statements; Constraints unbudgeted; the extra
  probe-queue query noted in #342. → `1f64edc`, `580d8d2`.
- **G4 ratification.** The chat channel stamps the proposal defaults (#230 pattern). → recorded in #342
  (`580d8d2`).
- **G5 rulings.** `parent_resolved_survives` label (`ce16bb6`); G6 operator-run; #121 literal.
- **G5/S6 sequencing.** Merge before G6; G6 becomes a post-deploy gate. → #342 Status (`580d8d2`).
- **G6 (prod, operator, 2026-09-28).** The served bundle carries `ends with this injury`. The dry-run planned 4
  rows (3 × #94 lumbar, 1 × #77 finger); I reviewed it against the fixture expectation. The only divergence is
  #77's restriction, absent from the fixture listing. `--confirm` wrote ids 95–98 and constraints went 0 → 4. The
  counts are recorded in #342's How-you-know by this close-out commit.
- **Not done, owed:** propagating the shared paste-addressing rule to `health-connect-app` (ROADMAP NOW row;
  Code, next HCA session).
- **One deviation from the S7 checklist, flagged at merge:** no new Q for server-side chat history. Q180
  already asks it, so it was annotated and given the ROADMAP LATER row. New Qs are therefore Q181–Q184, not
  Q181–Q185.

**Nits (batched, no gate):** the seed stamps `kind: "block"` on every row, so #77 ("requires buddy taping…")
renders as BLOCK where `caution` fits. This is an optional operator rewrite; advisory rows have no engine effect.

## Cold-resume handoff

**Where things stand.** v1 = See (MET) / Know / Walk in / Loop (ROADMAP "v1 — definition of done"). Master is
`a363061` plus this close-out. Decisions max **#343**, questions max **Q184**. Typed constraints and findings are
live in prod. Four advisory constraints are seeded for user 1 (ids 95–98, rendered in the coach's
`## Constraints`). No engine-tier constraint exists yet. No findings exist yet.

**NOW lanes — the v1 test each serves:**
- **Injury clearance (operator)** — Know + Walk in. OWED: step (3) is now the narrowed per-line plan (delete
  2/0, 5/37, 2/52 after checking row 94's detail, 2/53; rewrite 2/65; retitle row 5's bloods header).
- **Typed constraints G6** — Know. DONE → #342.
- **Lab upload pipeline** — Walk in. Substrate largely built; the row is long-lived.
- **Interpretation layer build** — Walk in. Increments 2/3/5 remain.
- **Appointment brief** — Walk in. **NOT STARTED; substrate complete.** It can now read constraints and
  findings through `current_state`.
- **Cross-repo rows** — no v1 test. Pinned in NOW by #112 as the canonical home for cross-repo debt. The new
  paste-addressing propagation row is one of these.
- **Triage flag:** three rows sitting in NOW are already DONE and are demotion/cleanup candidates, not work:
  the tags seed (#339), CBT-I Q45 (#219) and the eval trigger (#213).

**Open questions.** 100 OPEN, 4 OWED:
- **OWED:** Q78 (nap exclusion at a 4-night cadence), Q176 (ring validation window), Q178 (waking-cause
  rename, migration), Q181 (retire the `user_knowledge` store — brief 2, GO ruled, not yet cut).
- **New OPEN this session:** Q182 (default engine constraints from the in-code block maps), Q183 (engine-tier
  cap/caution — watch, no action until the dose seam lands), Q184 (budgeted context builder — LATER, #275).
- **Closed this session:** Q9 and Q20 → DONE → #343.

**What was NOT touched this session (and the questions gating it).**
- **Appointment brief v1 (Walk in, sequence position 3):** no design brief, no code. It is the synthesising
  consumer that sets build order, and it has stood still through #334–#343. Those were four consecutive
  sessions of instrument work: taxonomy tagging, the injury clearance sweep, and now typed entries. Each was
  justified as substrate for Know / Walk in, but the brief itself has not moved. Name it plainly: the next
  session's default should be the brief, not more substrate.
- **Interpretation layer increments 2/3/5** (rephrase pass, lever-tap threads, go-live) and the **lab pipeline
  residuals** (Q104): untouched.
- **Loop test surface-debt** (session cards, dual-panel scroll, chat persistence — Q180 now also carries the
  server-side history item): untouched.
- **Q27** (quota slot keying / restrictions-are-not-planes): untouched, and it still gates the Stability quota
  reading.
- **Q181 / brief 2** (retire free-text `user_knowledge`): ruled GO, not cut. Until it lands, the coach still
  reads the 66-line free-text rows every turn beside the new typed rows.
- **Engine-tier constraints:** none written. The right-shoulder ER one (right painful at 11.25 kg, left clean)
  is the first candidate: an explicit operator write via `POST /knowledge/entry` then `/confirm`, with
  `scope.side: "right"`.

**Single clearest next action.** Chat cuts the **Appointment brief v1 design brief** (Walk in). The substrate is
complete: labs, interpretation, the injury ledger, typed constraints and findings, and training state are all
readable through `current_state`. In parallel, operator-side: injury clearance step (3), then write the
right-shoulder engine constraint.
