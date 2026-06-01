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


# ---------- endpoints ----------

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
