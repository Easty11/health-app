# Close-out — chat context renders the resolver POSITION (#308, completes #307 A2)

## Real commits this session

Session-open ref: master `4611f96` (the #307 PR2 merge). One PR, branch
`feat/resolver-position-chat-context`:

```
<gov>    gov(#308): DECISIONS, FEEDBACK §44, ROADMAP/closeout wording corrections, BRANCHES, Recent-landings
c98c014  feat(context): chat sees the resolver POSITION, not just the declared quota (#308, #307 A2)
1379b30  docs(handoff): S6b receipt — resolver position in chat context (completes #307 A2)
```

Branch merged + remote-deleted at land. Non-schema, read-only over `resolve()`. Self-merges on
green under § Merge disposition — chat-ratified brief, A2 already ratified, no new judgment.

## Pending-queue reconciliation

No `;cc` queue carried in — the S6b brief was the Chat→Code handoff. Everything it named LANDED:

- S1 `CurrentState.resolver_position = resolve(db, uid, today=today)`, try/except→None+log — `c98c014`.
- S2 `_section_training_phase(phase, resolver_position)` renders the window, per-slot done/quota
  across both kinds, `◀ DUE` via `due_slot`, counted conditioning sessions (`unzoned` when trimp 0),
  the four uncounted reasons in words, an all-met line; `_conditioning_line` folded out — `c98c014`.
- S3 the one instruction sentence (authoritative count; don't infer from history; flag intent≠quota) — `c98c014`.
- Governance: DECISIONS #308, FEEDBACK §44, the two wording corrections, BRANCHES row, Recent-landings — `<gov>`.

Gates: G1 render content + the §18 mutation EXERCISED (swap `due_slot`→`due_capacity` → the
conditioning-due assertion fails); G2 parity (`state.resolver_position == resolve()` and the section
carries those numbers); G3 null window byte-identical (golden context test green); G4 resolver raises
→ context still builds, position omitted; G5 full backend suite **1724 passed** on a 3.12 venv.

## Cold-resume handoff

**Sprint — v1 test 2 (Know): "what's due, enforced against the plan."** The lane is now complete
end to end: the due-slot resolver (#276), the metabolic `load_window` slot kind backend + frontend
(#307), and the resolver POSITION in the coach's chat context (#308). The coach can now read what
has been done against the declared plan this window — the half of Know the operator actually uses.

**Single clearest next action.** The metabolic INGEST bridge is now the ceiling and the
highest-leverage next brief (an operator brief). #307/#308 count canonical `aerobic_sessions` from
BOTH Polar sources (`polar_flow_export` + `polar_v4`), but Garmin/Samsung/HC exercise write no
`aerobic_sessions` row (HC exercise is source-captured only, `#189`'s ingestion Status unbuilt), so
those sessions are invisible to the quota and the load model. Stage-1 HC-workout ingest (zones
derived from the posted HR) vs a direct `garminconnect` pull is the fork; that brief mints the
gap's own `Q#` and is where OPEN CALL 1's session-floor becomes real.

**Still gated (operator).** Do not open the block-2 conditioning phase until the frontend bundle
(#307 PR2) is deployed and the served bundle is confirmed rendering the `load_window` slot (`#121`
grep for the "Conditioning" string on the live `assets/index-*.js`). Chat position (#308) reads
the same `resolve()` regardless, so it is correct as soon as a phase carries a conditioning slot —
but the panel must render before the phase is opened.

**Wording corrections landed this session (do not re-propagate the old forms).** (a) The
HC-exercise ingest gap is NOT `Q154` — `Q154` is Polar ingest AUTOMATION; the HC gap is `#189`'s
unbuilt Status and gets its own `Q#` from the stage-1 ingest brief. (b) The count is not
"Polar-Flow-export only" — `polar_v4` rows are `aerobic_sessions` too (`connectors/polar.py:241`),
and canonical-session counting includes them.

**Open questions gating.** Q106 — the `minutes` reading keeps dose LATER; nothing reads `minutes`.
Q158 — uncoupled chronic denominator (unrelated). The HC-ingest `Q#` — not yet minted (owed by the
stage-1 ingest brief).

**NOT touched.** No prod queries this session (pure code over an existing read). The wrap-vs-plan
view (surfacing item 2, increment 4) and the interpretation / appointment-brief lanes stood still —
substrate-complete, unstarted. Operator's own owed (not Code): plan-of-record v2 (pending knee-consult
+ club-start dates); the HCA HR-lag brief go-ahead; the stage-1 metabolic-ingest brief.

**v1-triage (NOW lanes).** The exposure/Know lane served **Know** and is now demonstrable end to end
(resolver + slot kind + frontend + chat position). No NOW lane rode by momentum without a v1 test.
The metabolic-ingest bridge, once briefed, serves Know AND the load model (readiness).

**Process note (FEEDBACK §44).** #307's S6 narrowed A2 to the declaration and I reported it as "a
bounded shape" — a divergence that should have been flagged at the gate, not folded into prose. #308
lands the real A2; §44 encodes the rule (a step landing smaller than its brief is REPORTED as a
divergence, "done" has no totality check).
