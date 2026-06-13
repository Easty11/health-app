from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

VALID_CATEGORIES = {
    "Injury History",
    "Training Background",
    "Goals",
    "Constraints",
    "Nutrition",
    "Recovery",
    "Other",
}


# ---------- schemas ----------

class KnowledgeIn(BaseModel):
    category: str
    content: str


class KnowledgeOut(BaseModel):
    id: int
    category: str
    content: str

    model_config = {"from_attributes": True}


class KnowledgeEntryIn(BaseModel):
    type: str
    key: str
    value: dict[str, Any]
    source: str = "chat"
    expires_at: date | None = None
    notes: str | None = None


class KnowledgeEntryOut(BaseModel):
    id: int
    type: str
    key: str
    value: dict[str, Any]
    source: str
    added_at: date
    expires_at: date | None
    active: bool
    notes: str | None

    model_config = {"from_attributes": True}


# ---------- helpers ----------

def _validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
        )
    return category


def _get_entry(entry_id: int, user_id: int, db: Session) -> models.UserKnowledge:
    entry = db.query(models.UserKnowledge).filter_by(id=entry_id, user_id=user_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


def expire_stale_entries(user_id: int, db: Session) -> int:
    """Set active=False for all entries where expires_at < today. Returns count expired."""
    today = date.today()
    entries = (
        db.query(models.UserKnowledgeEntry)
        .filter(
            models.UserKnowledgeEntry.user_id == user_id,
            models.UserKnowledgeEntry.expires_at < today,
            models.UserKnowledgeEntry.active == True,
        )
        .all()
    )
    for e in entries:
        e.active = False
    if entries:
        db.commit()
    return len(entries)


def upsert_knowledge_entry(
    user_id: int,
    entry_in: KnowledgeEntryIn,
    db: Session,
) -> models.UserKnowledgeEntry:
    """Create a new entry, superseding any existing active entry with the same key."""
    existing = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, key=entry_in.key, active=True)
        .first()
    )

    new_entry = models.UserKnowledgeEntry(
        user_id=user_id,
        type=entry_in.type,
        key=entry_in.key,
        value=entry_in.value,
        source=entry_in.source,
        expires_at=entry_in.expires_at,
        notes=entry_in.notes,
        active=True,
    )
    db.add(new_entry)
    db.flush()  # get new_entry.id before committing

    if existing:
        existing.superseded_by = new_entry.id
        existing.active = False

    db.commit()
    db.refresh(new_entry)
    return new_entry


# ---------- legacy endpoints (UserKnowledge) ----------

@router.get("", response_model=list[KnowledgeOut])
def list_knowledge(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.UserKnowledge)
        .filter_by(user_id=current_user.id)
        .order_by(models.UserKnowledge.category, models.UserKnowledge.created_at)
        .all()
    )


@router.post("", response_model=KnowledgeOut, status_code=status.HTTP_201_CREATED)
def create_knowledge(
    body: KnowledgeIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_category(body.category)
    entry = models.UserKnowledge(
        user_id=current_user.id,
        category=body.category,
        content=body.content.strip(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=KnowledgeOut)
def update_knowledge(
    entry_id: int,
    body: KnowledgeIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_category(body.category)
    entry = _get_entry(entry_id, current_user.id, db)
    entry.category = body.category
    entry.content = body.content.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(
    entry_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _get_entry(entry_id, current_user.id, db)
    db.delete(entry)
    db.commit()


# ---------- structured knowledge endpoints ----------

@router.get("/schedule", response_model=list[KnowledgeEntryOut])
def get_schedule(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all active schedule_item entries for the current user."""
    return (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, type="schedule_item", active=True)
        .order_by(models.UserKnowledgeEntry.added_at.desc())
        .all()
    )


@router.post("/entry", response_model=KnowledgeEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: KnowledgeEntryIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update a structured knowledge entry (supersedes existing entry with same key)."""
    return upsert_knowledge_entry(current_user.id, body, db)


@router.post("/expire-stale", status_code=status.HTTP_200_OK)
def expire_stale(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Expire all entries whose expires_at is in the past."""
    count = expire_stale_entries(current_user.id, db)
    return {"expired": count}
