# Session close-out — Garmin auth: curl_cffi-era garminconnect 0.3.11, drop garth (#263, PR #147)

## Real commits this session

Session-open ref: `8fc514e` (origin/master at open). Feature branch `fix/garmin-curl-cffi-pin`
cut off it; governance close-out on `gov/263-garmin-curl-cffi-closeout`.

```
git log --oneline 8fc514e..HEAD   (feature+merge, pre-closeout)
6d756c0 Merge pull request #147 from Easty11/fix/garmin-curl-cffi-pin
7f3e1d2 gov(garmin): resolve Q133, log #263 — curl_cffi-era garminconnect, drop garth
7dd022a fix(garmin): move to curl_cffi-era garminconnect 0.3.11, drop garth
```

- `7dd022a` **fix** — `backend/requirements.txt` (`garminconnect` 0.3.2→0.3.11; `garth==0.8.0`
  line removed; pin rationale rewritten to "track the fixed version, don't freeze the broken
  one", Python ≥3.12 noted) + doc-only comment/docstring corrections in
  `backend/connectors/garmin.py`, `backend/routers/garmin.py`, `backend/scripts/garmin_login.py`
  (blob is garminconnect-native, not a "Garth token"; 0.3.11 exposes `get_hrv_data_range`, so
  the per-day loop is deliberate, not forced). Connector diff is comments/docstrings only — zero
  logic change.
- `7f3e1d2` **governance** — `OPEN_QUESTIONS.md` Q133 reframed + resolved (DONE → #263, residual
  cat-and-mouse watch carried), `DECISIONS_LOG.md` #263 appended. Committed separately from the fix.
- `6d756c0` **merge** — PR #147 to master via `--merge`, remote branch auto-deleted.

The close-out commit (`chore: session close-out`) lands `closeout.md`, the CLAUDE.md
Recent-landings roll, the `BRANCHES.md` DONE row, on `gov/263-garmin-curl-cffi-closeout`.

## Pending-queue reconciliation

No `;cc` pending-commit queue was carried in — the session ran directly from the chat proposal
(the Garmin curl_cffi brief). Every brief line landed:

- Requirements pin (0.3.11, garth dropped) → `7dd022a`. **Landed.**
- Connector compatibility (STEP-3 VERIFY) → confirmed against installed 0.3.11; no logic change,
  doc-only edits → `7dd022a`. **Landed.**
- Tests unchanged, green on 0.3.11 → verified (full suite 1307 passed / 1 skipped; the 1 failure
  is the pre-existing `3360ed5` shallow-clone `test_current_state` artifact, unrelated;
  `test_garmin_hrv.py` 16 passed, file unchanged). **Verified, no commit needed.**
- Governance Q133 + DECISIONS #263, separate commit → `7f3e1d2`. **Landed.**
- Deploy verified live: backend deploy `18f0db72` **SUCCESS** — installs `garminconnect-0.3.11`
  + `curl_cffi-0.16.2`, garth gone; prod on Python 3.12 (cp312 wheels), satisfying 0.3.11's
  `Requires-Python >=3.12`; no migration ran. **Verified.**

Nothing provisional. Two brief assumptions were corrected in-flight (both verified, neither a
blocker): 0.3.11 requires Python ≥3.12 (prod is on 3.12); 0.3.11 *added* `get_hrv_data_range`
(0.3.2 lacked it — docstrings corrected, per-day loop kept as deliberate). `curl_cffi` was NOT
pinned explicitly (no general transitive-pinning convention in the repo — `pydantic-core` reads
as a version-lock special case); flag for the operator if a freeze is wanted.

## Cold-resume handoff

**What this was.** A single dependency + governance fix. Garmin's March-2026 Cloudflare TLS
fingerprinting broke the pre-curl_cffi `garth` auth server-side, so `garmin_login.py` could not
authenticate. Moved to `garminconnect==0.3.11` (rebuilt on curl_cffi, garth-free); garth removed
from requirements. Connector logic untouched (token/exception surface unchanged 0.3.2→0.3.11).

**Single clearest next action (operator, out-of-band — Code cannot do this):** run
`backend/scripts/garmin_login.py` locally (email / password / MFA; prints only the token blob,
password never leaves the machine) → POST the blob to `POST /integrations/garmin/token` →
trigger `POST /integrations/garmin/sync` (or `scripts/garmin_sync.py` via `railway run`). Then
confirm `hrv_readings` rows for the target user (Deb) — nightly `rmssd_ms` + `hrv_samples` 5-min
series. **This live login is the real proof-point** — it is where curl_cffi either defeats
Garmin's fingerprinting or does not. If it fails (Garmin tightened again), the fix is to move
*forward* to the next working `garminconnect` release, never to pin backward (Q133 residual watch).

**Open questions (Garmin-adjacent).**
- **Q133 — DONE → #263.** garth durability resolved (garth dropped; server-side block, not mere
  deprecation). Residual: cat-and-mouse watch — bump the pin forward when Garmin next tightens
  (TLS fingerprinting now, OAuth 1.0a retiring end-2026).
- **Q130 — OPEN.** HRV *consumption* is still deferred: Samsung HRV migration into `hrv_readings`
  + the `recovery.py` HRV-read rewire onto `reads/recovery_reads.canonical_hrv`. The store and
  read-time arbitration exist (#259) but nothing reads them yet. This is the next real Garmin/HRV
  build, and it did not move this session.
- **Q131 — contingent.** `_SOURCE_RANK` (garmin>samsung) re-tuning, only once a single user has
  both sources.

**What was NOT touched (name the standing lanes).** This session, like the two before it in the
Garmin lane, went to the *transport* (auth/deps), not to the *use* of the data. Untouched:
- **HRV consumption (Q130)** — `recovery.py` still does not read `canonical_hrv`; the HRV pair is
  populated-but-unconsumed. This is the load-bearing follow-on and has now been deferred across
  #258/#259 and #263.
- **CBT-I (Q78)** — per-user nap-cadence over-threshold starvation, OPEN and unblocked (by #219)
  but unbuilt; no engine change this session.
- **Frontend / product surface** — no change. The Garmin lane has no UI (operator-run scripts +
  endpoints only).

The next session that opens on "Garmin" should resist doing more transport: the durable next step
is Q130 (consume the HRV that now flows), not further auth hardening — unless the operator's live
login (above) fails, in which case it is a pin-forward bump, not a redesign.
