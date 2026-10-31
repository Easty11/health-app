# 0007 — In-app chat architecture
**State:** ideation
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#543. Folded questions: Q163, Q180, Q184, Q246. The triage placed this as architecture-scale, ideation (LATER per #275).

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q163 | A real tool-use runtime for the in-app chat? (tool runtime) | none yet | none recorded | unclassified | open |
| Q180 | Browser chat history is a single non-expiring conversation re-sent every turn (history) | none yet | none recorded | unclassified | open |
| Q184 | Budgeted context builder with history behind a tool (budgeted builder) | none yet | none recorded | unclassified | open |
| Q246 | Should the in-app /chat get read tools, instead of everything standing in its prompt? (read tools) | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q163 — A real tool-use runtime for the in-app chat?</summary>

````
## Q163. A real tool-use runtime for the in-app chat?

Raised 2026-09-20 with #314. The in-app coach has NO tool loop — it acts through embedded tags (`<hevy_create_routine>`, `<hevy_update_routine>`, `<knowledge_update>`, `<capability_update>`) parsed out of a single completion, and reads everything it needs (routines included, #314) from the prepared context. The MCP tools (`search_hevy_routines`, `get_hevy_routine`, …) exist only for EXTERNAL MCP clients. #314's GUARD: do NOT build a tool runtime there — it is a larger decision.

**To decide:** whether the in-app chat should gain a genuine Anthropic tool-use loop (`tools=` + tool-call turns), letting the coach fetch a routine on demand rather than reading a bounded working set from context, and folding create/update into tool calls. Trade-offs: per-turn latency + cost of multi-step tool turns vs the current single-pass + tags; and how the write-result/footer truthfulness discipline (#283/#313/#314) maps onto tool results.

**State:** OPEN. Not blocking — the tag lane works and #314's read/update ride it. A capability question, revisited if the working-set-from-context model proves too limiting.
````

</details>

<details><summary>Q180 — Browser chat history is a single non-expiring conversation re-sent every turn</summary>

````
## Q180. Browser chat history is a single non-expiring conversation re-sent every turn

Raised 2026-09-27 with the injury clearance sweep (#340; G0 ruling 5). The chat panel keeps ONE conversation per user in
browser `localStorage` (`chat_history_{sub}`, `ChatPanel.jsx`) and sends all of it as `conversation_history` on every
turn (`chat.py`). Nothing expires or trims it. Two costs:
1. **Unsearchable copy store.** A resolved injury (or any retired fact) discussed in chat stays in context on every
   later turn, re-imposing it. The backend never sees the history at rest, so the clearance sweep cannot search it;
   it is on the sweep's fixed manual checklist ("browser chat history") only.
2. **Unbounded token growth.** Every turn re-sends the whole conversation.

**To decide:** a server-side, bounded history (summarised, or windowed with older turns behind a tool), or a
client-side window/expiry, or an explicit "new conversation" affordance — and whether resolved-fact copies in it
are handled by the summary or by the operator.

**Annotation (2026-09-28, typed entries #342/#343).** The typed-entries brief's "server-side, summarised chat
history" item IS this question — routed here rather than minted twice. LATER per #275 ("chat not required" for
v1); ROADMAP LATER row.

**State:** OPEN. No blocker.
````

</details>

<details><summary>Q184 — Budgeted context builder with history behind a tool</summary>

````
## Q184. Budgeted context builder with history behind a tool

Raised with #342/#343 (brief S7). The standing prompt grows section by section, each with its own cap: the
#314 routines budget, the #343 findings budget (2,000 chars, overflow named), and the knowledge-update guidance
(+1113 bytes at #342). A whole-prompt budget with lower-priority and historical material behind read tools
(the `get_findings` pattern) would replace per-section caps.

**State:** OPEN — LATER per #275 ("chat not required" for v1); ROADMAP LATER row.
````

</details>

<details><summary>Q246 — Should the in-app /chat get read tools, instead of everything standing in its prompt?</summary>

````
## Q246. Should the in-app /chat get read tools, instead of everything standing in its prompt?

Raised with #458, on the operator's brief; a deferred fork, recorded and not built.

**What is true.** `/chat` is one Messages call with no `tools` (`routers/chat.py`): it can only use what the prompt carries, and the prompt grows section by section (Q184). The 7 Oct failure was precedence, not access (#458), so tools would not have fixed it; the fork is about the next failure, where the coach needs history or a record the standing prompt does not carry and cannot fetch it.

**To decide.** Whether `/chat` should call the read surface the MCP already has (the plan, recovery, sessions, findings), which would let the prompt shrink toward the Q184 budgeted builder; how a tool-using turn composes with the single-pass write lanes and the narrate-after-write second call (a tool loop changes the turn's shape); and what a turn costs (a loop multiplies the calls #458's usage line now counts).

**State:** OPEN. Owner: Luke. Not blocking. Related: Q184, Q181, #458.
````

</details>
