from typing import Any
import os

import anthropic
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.hevy import HevyAuthError, HevyClient
from context_builder import build_system_prompt
from database import get_db
from encryption import decrypt

load_dotenv()

MODEL = "claude-sonnet-4-5"

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------- schemas ----------

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str


# ---------- context gathering ----------

async def _gather_hevy_context(api_key: str) -> dict[str, Any]:
    client = HevyClient(api_key)
    try:
        count_data = await client.get_workout_count()
        workouts_data = await client.get_workouts(page=1, page_size=5)
        return {
            "workout_count": count_data.get("workout_count", 0),
            "recent_workouts": workouts_data.get("workouts", []),
        }
    except HevyAuthError:
        # Key saved but now invalid — return empty context rather than hard-failing
        return {"workout_count": 0, "recent_workouts": [], "error": "invalid_key"}


# ---------- endpoint ----------

@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )

    # Discover which integrations the user has connected
    integrations = db.query(models.UserIntegration).filter_by(user_id=current_user.id).all()
    connected = {row.provider: row for row in integrations}

    hevy_data: dict[str, Any] | None = None
    if "hevy" in connected:
        raw_key = decrypt(connected["hevy"].api_key_encrypted)
        hevy_data = await _gather_hevy_context(raw_key)

    system_prompt = build_system_prompt(
        user=current_user,
        connected_integrations=list(connected.keys()),
        hevy_data=hevy_data,
    )

    # Build messages list: history + current user message
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in body.conversation_history
    ]
    messages.append({"role": "user", "content": body.message})

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text
    return ChatResponse(response=reply)
