# Close-out — Stability quota miscount → taxonomy v0.1 + exercise-tag coverage (#334–#338)

## Real commits this session

Session-open ref: master `57e858d` (the #333 merge). Two PRs, branch
`claude/stability-quota-classification-jk8n1k` (harness-pinned), each merged + remote-deleted:

```
5e0eb36 Merge pull request #265 from Easty11/claude/stability-quota-classification-jk8n1k
cf31f20 gov(tags): #338, Q179 (unconfirmed-tag ruling), Q27 restrictions-not-planes note
94e19e4 feat(tags): IR/ER sided variants, Deficit KB RDL -> mobility, seed preflight + prune, vote explainer
d772db4 Merge pull request #264 from Easty11/claude/stability-quota-classification-jk8n1k
5fbbb6a gov(taxonomy): #334-#337 decisions, Q27 scope extension, roadmap/branches/landings
4de5e0c feat(taxonomy): v0.1 tag-coverage regions + ID-keyed seed, sided-variant inheritance, --dry-run
```

This close-out lands as a third, governance-only PR on the same branch (`chore: session close-out`).
There is no migration anywhere. Both code PRs self-merged on green (placeholder guard, pytest, vitest). The Railway deploy of
`5e0eb36` reports SUCCESS on both services (2026-09-26 22:28 UTC).

## Pending-queue reconciliation

No `;cc` queue was carried in. Chat handed off two briefs in-session; each item is reconciled below:

- **Diagnosis (the Stability 0/3 read).** Rule 1 counts PRIMARY tags only. Routine, folder and title are never read. The tag
  seed was frozen at 2026-07 history. This was reported in chat, and the finding is recorded in #334's Context.
- **Brief 1, D1 five regions.** LANDED `4de5e0c` → #334. `shoulder_stability` shipped as `shoulder_er_ir`, with capacity
  STRENGTH by operator ruling (Q27's read), not STABILITY. All five are probe-inert. `TAXONOMY_VERSION` is `v0.1`.
- **Brief 1, D2 admission guardrail.** LANDED `5fbbb6a` → #335. Its tension with #76 is recorded, not left implicit.
- **Brief 1, D3 IR/ER reversal.** LANDED → #336. Also moved by operator ruling: the leg curls, Hip Adduction (Machine)
  and Copenhagen (Short Lever), the last flagged as Code's inclusion.
- **Brief 1, D4 sided-variant inheritance.** LANDED `4de5e0c` → #337, together with ID-keyed entries and `--dry-run`.
- **Brief 1, D5 34 tags.** LANDED across `4de5e0c` and `94e19e4`. The 4 IR/ER variants landed once the full parent IDs arrived.
- **Brief 1, Q27 slot-keying scope.** LANDED `5fbbb6a`.
- **Brief 2, item 1 (IR/ER parent IDs).** LANDED `94e19e4` → #338. The parents are now ID-keyed, so a wrong ID shows as
  UNRESOLVED. **Near-twin check against the DB: owed.** Code cannot reach prod, so the dry-run prints `NEAR-TWIN` lines
  and the result has not been relayed.
- **Brief 2, item 2 (unconfirmed tags).** Tooling LANDED `94e19e4` (dry-run report, opt-in `--prune-unconfirmed`), with the
  proposed ruling as Q179. **The ruling is PROVISIONAL.** The operator reports the seed complete but has not relayed
  whether prune was used. Q179 stays OPEN in the store until that is relayed.
- **Brief 2, item 3 (Deficit KB RDL → MOBILITY).** LANDED `94e19e4` → #338. The router consequence is recorded: that
  region now routes TRAIN, not the ASLR screen.
- **Brief 2, item 4 (Q27 restrictions are not planes).** LANDED `cf31f20`. Q27 stays OPEN.
- **Operator prod seed + recount.** The operator reports it DONE (2026-09-27). **Unverified by Code**, because the output
  was not relayed. The per-capacity votes for 09-21 / 09-24 are therefore **not yet reported**.

## Cold-resume handoff

**Sprint: v1 test 2 (Know), "what's due, enforced against the plan."** This session fixed *what the
quota counts*:
- five STRENGTH regions, probe-inert (#334);
- ID-keyed tags covering the 21-day audit's 34 untagged movements (#334/#338);
- sided L/R variants inheriting through an explicit parent ID (#337);
- the first MOBILITY tag (#338);
- a seeder that can preview (`--dry-run`) and report its own preconditions.

It did not fix *what a slot means*. Decompression's intent is a permission ("strength, but not the provocative
movements"), and a capacity slot cannot express it. That is now Q27's scope. The recorded restrictions (#338 / Q27
note) are lumbar EOR flexion + rotation, L-knee depth and L-thumb position. None is plane-level, which is evidence
against capacity × plane and toward a counting/permission split plus a restriction record.

**Open questions touched:**
- **OPEN:** Q27, now v1 axes + slot keying + restriction record, which gates the decompression phase's real design.
- **OPEN:** Q179, the unconfirmed-tag ruling; closes on the operator's relay.
- **OPEN:** Q145 (typo'd `b4bab549…4166…`). Unchanged; the preflight now surfaces the twin if it is live.
- **PENDING (operator):** Q27 lumbar item 1, whether any operator-chosen ceiling remains on heavy / end-range hinge.

**Single clearest next action.** Relay the four seed outputs named in the ROADMAP NOW row: dry-run
`UNRESOLVED`/`NEAR-TWIN`, whether prune was used, the `explain_quota_votes` 09-21/09-24 votes, and the coverage audit.
That closes Q179 and confirms whether Stability now reads correctly. Until then the Stability figure on the card is
unconfirmed.

**What was NOT touched this session (named, not implied finished):**
- **Know, the plan of record.** The interim swap (the Stability slot becomes a Strength slot until Q27) is an operator
  action on the Phase card. It was recommended, not done, and nothing in the tree records it as done.
- **Know, the metabolic INGEST bridge.** The prior close-out's named ceiling; untouched.
- **See (visuals lane), Walk in (appointment brief), Loop (surface-debt sweep).** All untouched. The lab upload
  pipeline, the interpretation-layer build and the appointment brief sit in NOW unchanged.
- **CBT-I** (Q177 items 1/3, Q178 migration). Untouched.
- **Honest pattern note.** This session went to *classification instrument*: taxonomy, tags, seeder tooling and
  governance. That was warranted, because the quota was reporting a false 0/3, but it was not Know's product surface.
  The next Know step is Q27's slot-keying design, not more tagging.

**v1 triage of NOW:**
- **Training seed row:** serves Know (test 2).
- **Lab upload pipeline, interpretation-layer build:** serve Walk in (test 3); they feed the brief.
- **Appointment brief:** serves Walk in (test 3).
- **Cross-repo shared-block edit (owed):** serves no v1 test. It is in NOW only by #112's pin for cross-repo debt, which
  makes it a demotion candidate if the pin is revisited.
- **The two CBT-I rows:** both DONE and should drop out of NOW at the next ROADMAP sweep.
