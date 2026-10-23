# Rotation runbook, October 2026 (Railway incident, DECISIONS_LOG #442)

The operator's ordered procedure for `OPEN_QUESTIONS` Q238. Names only: no value, no digest, no
key appears in this file or should be pasted back into any Code session (#111). Where a step needs
a value, the operator does it in the Railway dashboard or in their own PowerShell window, never in
a Code session.

Exposure model this works to (#442 (a)): every variable on the three services (`health-app-backend`,
`health-app-frontend`, `health-app-DB`) is treated as read. `DATABASE_PUBLIC_URL` exists, so the
database was reachable from outside with the exposed credential: every table is treated as read,
including `user_integrations` ciphertext and `users` password hashes. `FERNET_KEY` read plus
ciphertext read means the Hevy key, the Garmin token blob and the Polar tokens are recoverable in
plaintext. Rotating the Fernet key is therefore necessary but not sufficient: each stored credential
is also re-issued at its provider (Phase 4).

Order matters. Each phase ends with a check before the next starts. "Dashboard" means the Railway
web UI. Nothing here is typed into a Code session except the two in-container script runs
(Phase 3), which print ids and states only.

## Corrections to the brief's draft

Reading the code before committing this file forced three changes to the procedure as first written.

1. **Garmin re-login runs on the operator's machine, not in the container.** `scripts/garmin_login.py`
   prompts for the Garmin email, password and MFA code locally and prints the token blob to stdout;
   the blob is then POSTed to `/integrations/garmin/token`. Its own docstring is the procedure. The
   draft said to run it in the container; it cannot prompt there and its prerequisites (Python
   3.12 or newer, `garminconnect`) are local (V3).
2. **Polar re-authorisation moves after the Phase 5 redeploy.** The new Polar client secret is
   set in Phase 5; re-authorising a user connection before that deploys would run the connect flow
   (`/integrations/polar/auth-url`, `/callback`) against the old secret. The Polar step is split:
   regenerate the secret in Phase 4, re-authorise in Phase 5b.
3. **Garmin's password change is unverified.** That changing the Garmin account password is the
   only lever that invalidates an existing garth session is the author's reading, not a tested fact
   (tagged Guessing in the `DECISIONS_LOG` entry). The Phase 4 check (the nightly sweep or
   `scripts.garmin_verify`) is what shows the new session works; it does not show the old one is dead.

V1 and V2 forced no change: `encryption.py` was the single-key module with `encrypt` and `decrypt`
as the only exports used elsewhere, and `user_integrations.api_key_encrypted` is the only ciphertext
column in the schema.

## Phase 0: before anything

Read Railway's email (affected-customer notice, if any) and the Railway guides published 2026-10-22
for Postgres rotation and GitHub reconnection; note the plan tier. Review the `health-app-backend`
HTTP logs for 2026-10-21 00:00Z to 2026-10-23 00:00Z for requests you did not make, and the
Anthropic console usage for the same window. Record what you saw (one line each) for Q238's last row.

## Phase 1: Code (this PR)

This PR lands and deploys the backend (the service's folder changed: expect SUCCESS on the backend,
SKIPPED on the frontend, #442 (e)). Nothing changes for the running app: with `FERNET_KEY_PREVIOUS`
unset the module behaves exactly as before.

## Phase 2: Postgres credential (`health-app-DB`)

Follow Railway's own guide for rotating the Postgres password (the role password is changed in the
database, then the service's password variable and every URL that embeds it; if `DATABASE_URL` on the
backend is a reference to the DB service's variable, it follows automatically; if it is a literal,
update it). Redeploy the backend.

Check: `GET /health` is 200 on the new deployment, and the boot log reads
`Application startup complete` and `startup freshness OK`.

This runbook does not restate Railway's steps because they are Railway's to change; link the guide
you used in the Q238 row.

## Phase 3: Fernet key

In your own PowerShell window (not a Code session), from `backend\` with the venv active:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the printed key. In the dashboard, on `health-app-backend`: set `FERNET_KEY_PREVIOUS` to the
current `FERNET_KEY` value, then set `FERNET_KEY` to the new key. Redeploy. Check `GET /health` is 200.
Then:

```
railway ssh --service health-app-backend
cd /app
/opt/venv/bin/python -m scripts.rotate_fernet --dry-run
```

Read it. Expected: every row `previous`, none `unreadable`. Then, as a separate command after reading:

```
/opt/venv/bin/python -m scripts.rotate_fernet --confirm
```

Expected: every row `rotated`, exit zero. Then run `--dry-run` once more: every row `current`. Only
then, in the dashboard, delete `FERNET_KEY_PREVIOUS` and redeploy. Final check: `--dry-run` again
reports every row `current` with `active_keys=1`.

Paste the three dry-run outputs (ids and states only) for the Q238 row. Clear the key from the
PowerShell window's scrollback and history (`Clear-History`; close the window).

`--confirm` refuses to run with one active key or with any `unreadable` row, and writes nothing in
either case. If it reports `unreadable`, stop: do not delete `FERNET_KEY_PREVIOUS`, and bring the ids
back to chat.

## Phase 4: re-issue the stored provider credentials

Each re-store encrypts under the new key, and this is what retires the plaintexts the incident may
have exposed.

- **Hevy:** generate a new API key in Hevy's settings, revoke the old if Hevy offers it, enter the new
  key on the app's Integrations page. Check: `get_hevy_workouts` from chat returns workouts.
- **Garmin:** change the Garmin account password (Guessing: see correction 3), then mint a new token
  locally with `scripts.garmin_login` and POST it to `/integrations/garmin/token`, following the
  script's own docstring (see correction 1). Delete the local token file afterward. Check: the next
  nightly sweep's Garmin leg records no auth error, or run `scripts.garmin_verify` in the container
  per its usage text.
- **Polar:** regenerate the client secret in `admin.polaraccesslink.com`. Set it in Phase 5 with the
  other variables; re-authorise in Phase 5b.

## Phase 5: plain variable swaps on `health-app-backend`

One batch, one redeploy:

- `SECRET_KEY`: a new random string. Every web login is invalidated: sign in again, and reset your
  web-app password since the hash was readable.
- `ANTHROPIC_API_KEY`: new key in the Anthropic console, revoke the old, note the window's usage.
- `POLAR_CLIENT_SECRET`: from Phase 4 (and `POLAR_CLIENT_ID` if it changed).
- `RESEND_API_KEY`: new key in Resend, revoke the old.

Not rotated, with reason, for the Q238 row: `FRONTEND_URL`, `RESET_FROM_EMAIL`, `ALGORITHM`,
`ACCESS_TOKEN_EXPIRE_MINUTES`, the two `MCP_*_TTL_SECONDS`, and `VITE_API_URL` on the frontend are
configuration, not secrets; `DATABASE_PUBLIC_URL` is handled by Phase 2.

Check after the redeploy: `GET /health` is 200, a chat turn answers, a password-reset email arrives.

### Phase 5b: Polar re-authorisation

Re-authorise the user connection through the app's Polar connect flow, which writes a new token
payload under the new Fernet key. Check: the Training page's Polar sync succeeds.

## Phase 6: MCP OAuth

MCP tokens are opaque and stored hashed in `mcp_oauth_tokens`; no signing key is read from the
environment. Via `railway connect health-app-DB` (one statement per run; set `PGCLIENTENCODING=UTF8`
first):

```
DELETE FROM mcp_oauth_tokens;
DELETE FROM mcp_oauth_clients;
```

Reconnect the claude.ai connector (and any other MCP client) once. Check: a chat MCP read succeeds.

## Phase 7: Railway and GitHub

`railway logout` then `railway login` on the laptop; reconnect the Railway-to-GitHub connection per
Railway's guide; read GitHub's security log for the window. Check: the next merge records a
deployment on both services (#442 (e)).

## Phase 8: Code, later session

Paste the ledger rows (names, dates, who, consumers redeployed) under a block addressed to a new
session. Code fills Q238 and closes it when every row carries a date or a reasoned non-rotation.
