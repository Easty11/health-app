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
from engine import adaptation, profile as profile_mod, selection
from routers.knowledge import KnowledgeEntryIn, expire_stale_entries, upsert_knowledge_entry

load_dotenv()

MODEL = "claude-sonnet-4-6"

router = APIRouter(prefix="/chat", tags=["chat"])

# Regex to find <hevy_create_routine>...</hevy_create_routine> blocks
_ROUTINE_BLOCK_RE = re.compile(
    r"<hevy_create_routine>\s*(.*?)\s*</hevy_create_routine>",
    re.DOTALL,
)

# Regex to find <knowledge_update>...</knowledge_update> blocks
_KNOWLEDGE_BLOCK_RE = re.compile(
    r"<knowledge_update>\s*(.*?)\s*</knowledge_update>",
    re.DOTALL,
)

# Regex to find <capability_update>...</capability_update> blocks — the adaptation
# loop's education-idiom capture (spec §7). The user reports how a probe/fortify
# felt; Claude records the response tag against the taxonomy region.
_CAPABILITY_BLOCK_RE = re.compile(
    r"<capability_update>\s*(.*?)\s*</capability_update>",
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


# ---------- knowledge update parsing ----------

def _process_knowledge_updates(
    reply: str,
    user_id: int,
    db: Session,
) -> tuple[str, list[str]]:
    """
    Scan `reply` for <knowledge_update> blocks.

    Handles two payload formats:
    - Legacy: {category, content} → writes to UserKnowledge (free-text KB)
    - Structured: {type, key, value, ...} → writes to UserKnowledgeEntry
      - If active=false is present, deactivates the existing entry for that key
        without creating a new one.

    Returns (cleaned_reply, actions_taken).
    """
    actions_taken: list[str] = []
    matches = list(_KNOWLEDGE_BLOCK_RE.finditer(reply))

    if not matches:
        return reply, actions_taken

    cleaned = reply
    for match in matches:
        raw_json = match.group(1)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            actions_taken.append(f"⚠️ Could not parse knowledge update: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        try:
            if "type" in data and "key" in data:
                # Structured format → UserKnowledgeEntry
                key = data["key"]

                # Deactivation: active=false means remove existing entry, no new one
                if data.get("active") is False:
                    existing = (
                        db.query(models.UserKnowledgeEntry)
                        .filter_by(user_id=user_id, key=key, active=True)
                        .first()
                    )
                    if existing:
                        existing.active = False
                        db.commit()
                        actions_taken.append(f"✓ Schedule entry removed: {key}")
                    else:
                        actions_taken.append(f"ℹ️ No active entry found for key: {key}")
                else:
                    from datetime import date as _date
                    expires_raw = data.get("expires_at")
                    expires_at = None
                    if expires_raw:
                        try:
                            expires_at = _date.fromisoformat(str(expires_raw))
                        except ValueError:
                            pass

                    entry_in = KnowledgeEntryIn(
                        type=data.get("type", "schedule_item"),
                        key=key,
                        value=data.get("value", {}),
                        source=data.get("source", "chat"),
                        expires_at=expires_at,
                        notes=data.get("notes"),
                    )
                    upsert_knowledge_entry(user_id, entry_in, db)
                    actions_taken.append(f"✓ Schedule entry saved: {key}")

            else:
                # Legacy format → UserKnowledge (free-text categories)
                category = data.get("category", "Other").strip()
                new_content = data.get("content", "").strip()

                if not new_content:
                    cleaned = cleaned.replace(match.group(0), "")
                    continue

                existing = (
                    db.query(models.UserKnowledge)
                    .filter_by(user_id=user_id, category=category)
                    .order_by(models.UserKnowledge.created_at)
                    .first()
                )
                if existing:
                    existing.content = existing.content.rstrip() + "\n" + new_content
                    db.commit()
                    actions_taken.append(f"✓ Knowledge updated: {category}")
                else:
                    entry = models.UserKnowledge(
                        user_id=user_id,
                        category=category,
                        content=new_content,
                    )
                    db.add(entry)
                    db.commit()
                    actions_taken.append(f"✓ Knowledge saved: {category}")

        except Exception as exc:
            actions_taken.append(f"⚠️ Failed to save knowledge: {exc}")

        cleaned = cleaned.replace(match.group(0), "")

    return cleaned.strip(), actions_taken


# ---------- capability update parsing (adaptation loop, §7) ----------

def _process_capability_updates(
    reply: str,
    user_id: int,
    db: Session,
) -> tuple[str, list[str]]:
    """
    Scan `reply` for <capability_update> blocks and apply each as a §7 response
    tag against the capability map. Payload:
        {region_key, side?, tag, probe_result?, signal_text?}
    where tag is one of absorbed_clean | symptom_carryover | flare | capability_revealed.
    """
    actions_taken: list[str] = []
    matches = list(_CAPABILITY_BLOCK_RE.finditer(reply))
    if not matches:
        return reply, actions_taken

    cleaned = reply
    for match in matches:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            actions_taken.append(f"⚠️ Could not parse capability update: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue
        try:
            row = adaptation.apply_response(
                db, user_id,
                region_key=data["region_key"],
                side=data.get("side", "bilateral"),
                tag=data["tag"],
                probe_result=data.get("probe_result"),
                signal_text=data.get("signal_text"),
                source=data.get("source", "probe"),
            )
            actions_taken.append(f"✓ Capability logged: {row.region_key}/{row.side} → {row.status}")
        except (KeyError, ValueError) as exc:
            actions_taken.append(f"⚠️ Could not log capability: {exc}")
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

    # Expire stale knowledge entries (piggyback on chat request, no separate cron needed)
    expire_stale_entries(current_user.id, db)

    # Discover which integrations the user has connected
    integrations = db.query(models.UserIntegration).filter_by(user_id=current_user.id).all()
    connected = {row.provider: row for row in integrations}

    hevy_data: dict[str, Any] | None = None
    hevy_client: HevyClient | None = None
    if "hevy" in connected:
        raw_key = decrypt(connected["hevy"].api_key_encrypted)
        hevy_data = await _gather_hevy_context(raw_key)
        hevy_client = HevyClient(raw_key)

    knowledge_entries = (
        db.query(models.UserKnowledge)
        .filter_by(user_id=current_user.id)
        .order_by(models.UserKnowledge.category, models.UserKnowledge.created_at)
        .all()
    )

    import pytz
    from datetime import datetime as _dt
    today_aest = _dt.now(pytz.timezone("Australia/Brisbane")).date()
    today_checkin = (
        db.query(models.DailyCheckIn)
        .filter_by(user_id=current_user.id, date=today_aest)
        .first()
    )
    daily_record = (
        db.query(models.DailyRecord)
        .filter_by(user_id=current_user.id, date=today_aest)
        .first()
    )

    from datetime import timedelta as _td
    hc_since = today_aest - _td(days=2)  # today + yesterday
    health_connect_records = (
        db.query(models.HealthConnectSync)
        .filter(
            models.HealthConnectSync.user_id == current_user.id,
            models.HealthConnectSync.date >= hc_since,
        )
        .order_by(models.HealthConnectSync.date.desc())
        .all()
    )

    # Samsung Galaxy Ring scraper readings from the last 7 days (HRV/sleep,
    # extracted on-device). Latest first; used for a rolling HRV baseline.
    samsung_window_start = today_aest - _td(days=7)
    samsung_readings = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == current_user.id,
            models.SamsungHRVReading.captured_at >= samsung_window_start,
            models.SamsungHRVReading.context != 'session',
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .all()
    )

    # All active structured knowledge entries (schedule_item, load_context, injury, etc.)
    structured_entries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, active=True)
        .order_by(models.UserKnowledgeEntry.added_at.desc())
        .all()
    )

    # ---- Adaptive Exposure Engine: fortification profile + session selection ----
    # Avoidance signal (§4) reads from what the user loads in Hevy; the rest of the
    # taxonomy is the candidate deficiency set. Readiness only re-ranks vehicles,
    # never gates (DECISIONS_LOG #8).
    fort_profile = profile_mod.get_profile(db, current_user.id)
    fort_profile_dict = profile_mod.profile_to_dict(fort_profile)
    engine_selection = None
    if fort_profile is not None:
        loaded_regions = selection.infer_loaded_regions(
            (hevy_data or {}).get("recent_workouts", [])
        )
        probe_queue = selection.compute_probe_queue(
            db, current_user.id, profile=fort_profile, loaded_region_keys=loaded_regions,
        )
        if daily_record is not None and daily_record.morning_readiness is not None:
            readiness_hint = int(daily_record.morning_readiness) * 2  # 1–5 → 1–10
        elif today_checkin is not None and today_checkin.readiness_score is not None:
            readiness_hint = int(today_checkin.readiness_score)
        else:
            readiness_hint = None
        engine_selection = selection.select_next(
            db, current_user.id, profile=fort_profile,
            probe_queue=probe_queue, readiness_hint=readiness_hint,
        )

    system_prompt = build_system_prompt(
        user=current_user,
        connected_integrations=list(connected.keys()),
        hevy_data=hevy_data,
        knowledge_entries=knowledge_entries,
        today_checkin=today_checkin,
        health_connect_records=health_connect_records,
        samsung_hrv=samsung_readings,
        structured_entries=structured_entries,
        daily_record=daily_record,
        fortification_profile=fort_profile_dict,
        engine_selection=engine_selection,
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
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text

    # Parse and execute any embedded action blocks
    reply, routine_actions = await _process_routine_actions(reply, hevy_client)
    reply, knowledge_actions = _process_knowledge_updates(reply, current_user.id, db)
    reply, capability_actions = _process_capability_updates(reply, current_user.id, db)

    all_actions = routine_actions + knowledge_actions + capability_actions

    # Append confirmation messages inline so they appear in the chat bubble
    if all_actions:
        reply = reply + "\n\n" + "\n".join(all_actions)

    return ChatResponse(response=reply, actions_taken=all_actions)
