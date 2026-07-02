"""
Login gate for the MCP OAuth flow (see oauth_provider.PersonalOAuthProvider).

authorize() parks every MCP client authorization request behind a ticket and
redirects here instead of auto-approving. This form re-checks the same
email/password pair backend/auth.py already verifies against `users`, then
hands the ticket back to the provider to mint a token bound to that user_id —
so MCP tools can resolve a real caller instead of defaulting to user 1.
"""
import html

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import auth as auth_utils
import models
from database import get_db
from mcp_server import _oauth_provider

router = APIRouter(prefix="/mcp", tags=["mcp-auth"])


def _login_page(ticket: str, error: str | None = None) -> str:
    error_html = f'<p style="color:#b00">{html.escape(error)}</p>' if error else ""
    ticket_attr = html.escape(ticket, quote=True)
    return f"""<!doctype html>
<html><head><title>Sign in</title></head>
<body style="font-family: sans-serif; max-width: 360px; margin: 4rem auto;">
<h2>Sign in to connect this app</h2>
{error_html}
<form method="post" action="/mcp/login">
<input type="hidden" name="ticket" value="{ticket_attr}">
<p><label>Email<br><input type="email" name="email" required autofocus></label></p>
<p><label>Password<br><input type="password" name="password" required></label></p>
<p><button type="submit">Sign in</button></p>
</form>
</body></html>"""


@router.get("/login", response_class=HTMLResponse)
def show_login(ticket: str):
    pending = _oauth_provider.get_pending_login(ticket)
    if pending is None:
        return HTMLResponse("<p>This login link has expired. Please retry the connection.</p>", status_code=400)
    return HTMLResponse(_login_page(ticket))


@router.post("/login")
def submit_login(
    ticket: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    pending = _oauth_provider.get_pending_login(ticket)
    if pending is None:
        return HTMLResponse("<p>This login link has expired. Please retry the connection.</p>", status_code=400)

    user = db.query(models.User).filter(models.User.email == email.lower().strip()).first()
    if not user or not auth_utils.verify_password(password, user.hashed_password):
        return HTMLResponse(_login_page(ticket, error="Incorrect email or password"), status_code=401)

    redirect_url = _oauth_provider.complete_login(ticket, user.id)
    if redirect_url is None:
        return HTMLResponse("<p>This login link has expired. Please retry the connection.</p>", status_code=400)
    return RedirectResponse(redirect_url, status_code=302)
