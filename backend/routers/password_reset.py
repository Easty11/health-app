import os
import secrets
from datetime import datetime, timedelta, timezone

import resend
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

import models
from auth import hash_password
from database import get_db

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

RESET_LINK_BASE = os.getenv("FRONTEND_URL", "https://health-app-production-e0ff.up.railway.app") + "/reset-password"
TOKEN_EXPIRY_HOURS = 1


# ---------- schemas ----------

class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


# ---------- helpers ----------

def _send_reset_email(to_email: str, token: str) -> None:
    api_key = os.getenv("RESEND_API_KEY", "")
    from_email = os.getenv("RESET_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        # Fail silently in dev if key not set — log to stdout for debugging
        print(f"[DEV] Password reset link: {RESET_LINK_BASE}?token={token}")
        return

    resend.api_key = api_key
    reset_url = f"{RESET_LINK_BASE}?token={token}"

    resend.Emails.send({
        "from": from_email,
        "to": to_email,
        "subject": "Reset your Health & Performance password",
        "html": f"""
            <p>Hi,</p>
            <p>We received a request to reset your password.</p>
            <p>
              <a href="{reset_url}" style="
                display:inline-block;
                background:#4f46e5;
                color:#fff;
                padding:12px 24px;
                border-radius:8px;
                text-decoration:none;
                font-weight:600;
              ">Reset password</a>
            </p>
            <p>This link expires in {TOKEN_EXPIRY_HOURS} hour(s).</p>
            <p>If you didn't request this, you can safely ignore this email.</p>
        """,
    })


# ---------- endpoints ----------

@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    # Always return the same message — never reveal whether email exists
    generic_response = {"message": "If that email exists you'll receive a reset link"}

    email = body.email.lower().strip()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        return generic_response

    # Expire any existing unused tokens for this user
    db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.user_id == user.id,
        models.PasswordResetToken.used.is_(False),
    ).update({"used": True})

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)

    db.add(models.PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    ))
    db.commit()

    _send_reset_email(user.email, token)
    return generic_response


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    record = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token == body.token)
        .first()
    )

    if not record or record.used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    # expires_at may be naive (SQLite) or aware (Postgres) — normalise for comparison
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.query(models.User).filter(models.User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user.hashed_password = hash_password(body.new_password)
    record.used = True
    db.commit()

    return {"message": "Password reset successfully"}
