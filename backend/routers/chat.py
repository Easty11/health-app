from typing import Any
import json
import os
import re

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

# Regex to find <hevy_create_routine>...</hevy_create_routine> blocks
_ROUTINE_BLOCK_RE = re.compile(
    r"<hevy_create_routine>\s*(.*?)\s*</hevy_create_routine>",
    re.DOTALL,
)


# ---------- schemas ----------

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str
    actions_taken: list[str] = []   # e.g. ["✓ Routine 'Push Day' created in Hevy"]


# ---------- context gathering ----------

async def _gather_hevy_context(api_key: str) -> dict[str, Any]:
    client = HevyClient(api_key)
    try:
        count_data = await client.get_workout_count()
        workouts_data = await client.get_workouts(page=1, page_size=10)
        return {
            "workout_count": count_data.get("workout_count", 0),
            "recent_workouts": workouts_data.get("workouts", []),
        }
    except HevyAuthError:
        return {"workout_count": 0, "recent_workouts": [], "error": "invalid_key"}


# ---------- routine action parsing ----------

async def _process_routine_actions(
    reply: str,
    hevy_client: HevyClient | None,
) -> tuple[str, list[str]]:
    """
    Scan `reply` for <hevy_create_routine> blocks.
    For each one found:
      - Parse the JSON payload
      - Call hevy_client.create_routine()
      - Strip the raw block from the displayed text
      - Record a confirmation message in actions_taken

    Returns (cleaned_reply, actions_taken).
    """
    actions_taken: list[str] = []
    matches = list(_ROUTINE_BLOCK_RE.finditer(reply))

    if not matches:
        return reply, actions_taken

    if hevy_client is None:
        # Hevy not connected — strip blocks and explain
        cleaned = _ROUTINE_BLOCK_RE.sub("", reply).strip()
        actions_taken.append("⚠️ Routine not created — Hevy is not connected.")
        return cleaned, actions_taken

    cleaned = reply
    for match in matches:
        raw_json = match.group(1)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            actions_taken.append(f"⚠️ Could not parse routine JSON: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        title = data.get("title", "Untitled Routine")
        exercises = data.get("exercises", [])
        folder_id = data.get("folder_id")

        try:
            await hevy_client.create_routine(
                title=title,
                exercises=exercises,
                folder_id=folder_id,
            )
            actions_taken.append(f"✓ Routine '{title}' created in Hevy")
        except Exception as exc:
            actions_taken.append(f"⚠️ Failed to create routine '{title}': {exc}")

        # Remove the raw block from the visible response
        cleaned = cleaned.replace(match.group(0), "")

    return cleaned.strip(), actions_taken


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
    hevy_client: HevyClient | None = None
    if "hevy" in connected:
        raw_key = decrypt(connected["hevy"].api_key_encrypted)
        hevy_data = await _gather_hevy_context(raw_key)
        hevy_client = HevyClient(raw_key)

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
        max_tokens=2048,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text

    # Parse and execute any routine creation blocks embedded in the reply
    reply, actions_taken = await _process_routine_actions(reply, hevy_client)

    # Append confirmation messages inline so they appear in the chat bubble
    if actions_taken:
        action_text = "\n\n" + "\n".join(actions_taken)
        reply = reply + action_text

    return ChatResponse(response=reply, actions_taken=actions_taken)
