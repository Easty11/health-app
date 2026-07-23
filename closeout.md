# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-23 · secrets residuals closed by artefact (#112) + cross-repo debt convention + the anchored-audit rule (#113)

## 1. Real commits this session

Session-open ref: `779edbe`. Landed on `master` at **`7adaa46`**, pushed, in sync.

```
7adaa46 governance: DECISIONS_LOG #112, cross-repo debt convention, secrets residuals closed
```

```
2026-07-23 governance: DECISIONS_LOG #112, cross-repo debt convention, secrets residuals closed
2026-07-22 governance: DECISIONS_LOG #111, close Q43/Q44, secret-rendering prohibition
2026-07-22 chore: session close-out
2026-07-22 governance: DECISIONS_LOG #110, OPEN_QUESTIONS Q43/Q44, CLAUDE recent-landings
2026-07-22 chore: session close-out
2026-07-22 governance: DECISIONS_LOG #107/#108/#109, OPEN_QUESTIONS Q42, CLAUDE recent-landings
2026-07-22 feat(cbti): completed-block importer + reconciliation (Gate 4)
2026-07-22 chore(cbti): gitignore personal-data workbooks before import
2026-07-22 feat(cbti): data substrate — diary fields + block/prescription ledgers
2026-07-22 chore: session close-out
```

Maxima now: **DECISIONS #113 · questions Q45 · FEEDBACK §17.**
Two governance commits; no feature code touched, no migration, no test delta.

## 2. Pending-queue reconciliation

No `;cc` queue was carried in — the session ran from a pasted brief. All seven of its steps
resolved:

| Brief step | Outcome |
|---|---|
| 1 — confirm state | **VERIFIED** 0 behind, #111 / Q44 |
| 2 — which key was disabled | **RESOLVED** — Anthropic key returns 401, with a three-probe control |
| 3 — prod Hevy round-trip | **PASSED** — HTTP 200 inside the container; did *not* block |
| 4 — local cleanup | **DONE** — row deleted 1→0; `FERNET_KEY` + `SECRET_KEY` rotated |
| 5 — cross-repo convention | **DONE** — ROADMAP NOW, per #112 |
| 6 — propagate to HCA | **STOPPED**, recorded in ROADMAP NOW |
| 7 — merge | **DONE** `779edbe`→`7adaa46` |

Nothing decided this session is uncommitted.

### The three residuals, each closed by artefact rather than assumption

1. **Anthropic key — dead.** `GET /v1/models` with the `backend/.env` value returned **401**.
   The bare status could not discriminate "key rejected" from "request malformed", so three probes
   ran (the `.env` key, a bogus key, no key header): all returned `error.type='authentication_error'`
   rather than `invalid_request_error`, proving the request shape reaches auth. Its 24 transcript
   occurrences are occurrences of a disabled credential. Nothing revoked; diagnostic only.
2. **Prod Hevy — healthy.** `user_hevy_key()` → `HevyClient.get_workout_count()` → **HTTP 200**,
   run inside the container via `railway ssh` (which is why no proxy was needed). Prod's Fernet key
   decrypts the stored row and Hevy accepts the credential. Read-only; existing connector path, not
   hand-rolled; credential never printed (length only).
3. **Local — cleaned.** The single `user_integrations` row deleted (1→0), and **both** dev
   `FERNET_KEY` and `SECRET_KEY` rotated in `backend/.env`. `SECRET_KEY` was folded in because it was
   found exposed in 2 transcripts and Q43 had already established prod isolation, making the rotation
   local-only. New values verified absent from all 59 transcripts; old exposed values verified gone
   from `.env`; `api_key_encrypted` confirmed the sole Fernet-encrypted column, so nothing was orphaned.

**The local delete is characterised as mitigation-or-tidying-UNKNOWN, deliberately.** A disabled
Anthropic key proves an operator rotation happened for *that* credential and says nothing about Hevy —
different provider, different console. Prod's stored value cannot be compared to the local row's
without decrypting both, which this brief did not do. The action was identical either way; the claim
attached to it is not, and the honest claim is the unknown one.

### Two brief premises corrected at execution

- **`railway run` is local, not in-container.** Step 3 said "run inside the production environment so
  no proxy is required"; `railway run` executes locally with injected variables, so the internal host
  does not resolve from Windows. `railway ssh` does run inside the container and needed no proxy —
  the brief's intent, reached by a different route.
- **#112 lands with one instance, not two.** The brief anticipated Step 3 blocking and its owed
  verification joining the propagation debt in ROADMAP NOW. Step 3 passed, so recording a second
  instance would have been recording a hypothetical as debt.

## 3. Cold-resume handoff

**Branch:** `master` @ `7adaa46`, pushed, clean. Untracked stray: `.claude/launch.json` (known).

**Branch terminal-state gate — passes.** `chore/secrets-hygiene` and `chore/secrets-residuals` both
merged and deleted, local and remote (0 unmerged commits by patch-id). Five branches remain, all
rowed in `BRANCHES.md` and all on origin:

```
feat/cbti-engine                   1 +   rowed, on origin   (phase 2, paused mid-brief)
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

**Security posture — all three original exposures now inert or rotated.** The Railway Postgres
credential was rotated in a prior session; the Anthropic key is confirmed disabled; the dev Fernet and
Secret keys are rotated and their replacements are absent from every transcript. Prod was never
affected: Q43 established both prod keys distinct from dev, and Q44's `--kv` vector is now prohibited
by #111. **Now scheduled rather than open-by-choice:** the second Postgres digest's co-occurrence test is an
entry in **ROADMAP NOW** (#112's second instance) — it was previously recorded only inside Q44's body,
and Q44 is `DONE → #111`, so it sat in a store nobody scans for live work. Genuinely optional and
left alone: whether the transcripts are purged now the credentials in them are dead.

**OWED — cross-repo, and now with a canonical home (#112).** The `health-connect-app` shared-block
propagation is in **`ROADMAP.md` NOW**. Drift measured, not assumed: HCA carries the shared block's
`BEGIN/END` markers but greps **0** for #111's secret-rendering rule where health-app greps 1. Blocked
on three counts — `chore/secrets-residuals` is not cut in HCA, HCA's working tree is not clean, and a
canonical-store edit in a second repo is forbidden from a health-app-rooted session. Owner: Luke, from
an HCA-rooted session.

**CBT-I phase 2 resumes under its existing brief, paused at Step 3 (the engine).** Steps 1–2 landed on
`feat/cbti-engine` @ `b7908fc`. Before further work it needs a **rebase** — master moved to `7adaa46`,
so it is 1 ahead / 1 behind and `--ff-only` will refuse. Its provisional entries claim **#114/#115** (shifted when #113 landed)
and its nap question is **Q45, now minted on master** — the engine implements Q45's exclusion path rather than re-deriving it. Four amendments are outstanding on that brief: synthetic
adherence-gate tests; the tried-to-sleep vs got-into-bed mismatch named in the replay account;
`n_samsung`/`n_diary` composition per prescription; and Gate 6's production route, which this session
established still exists. Adherence is settled by measurement: Samsung `bedtime` is 0 rows inside the
replay window, so the replay runs entirely on the labelled weak source and must say so.

**OWED, carried from prior sessions:** `FEEDBACK` **§18** (mutation rule, receipted `caf5204`) and
**§19** (resolution-table rule, receipted `b3af58a`) — both need a brief to land them. `haemoglobin`'s
per-parameter figure unread from Buoro 2018. **Q41** (haematocrit band citation capture). **Q37** (I1
has no enforcement). **Q33** (shared block still says `parked`). **Q42** (12h-clock scrape failure)
belongs to HCA's store — carry it there. HCA **Q11** should close `DONE → #93`; HCA **Q9 item 1** and
**Q10** remain open there. `probe_resolver.py` container run and `hevy-resolver-activation` limb 2.

**Single clearest next action:** resume CBT-I phase 2 — rebase `feat/cbti-engine` onto the new master,
confirm `alembic heads` returns exactly one, then build Step 3's titration engine. The security work
that displaced it is finished, and nothing else on this list is time-sensitive.
