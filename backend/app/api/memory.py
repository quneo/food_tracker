from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from app.ai import memory
from app.api.deps import CurrentUser, Db
from app.chat.models import ChatMessage, ChatState
from app.core.timeutil import to_local, zone
from app.database import utcnow

router = APIRouter(tags=["memory"])
Category = Literal["goal", "preference", "dislike", "allergy", "health", "habit", "food", "other"]


class FactIn(BaseModel):
    category: Category = "other"
    text: str = Field(min_length=1, max_length=500)


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: Category
    text: str
    source: Literal["ai", "user"]
    created_at: datetime
    updated_at: datetime


@router.get("/memory", response_model=list[FactOut])
def list_facts(user: CurrentUser, db: Db):
    return memory.facts(db, user.id)


@router.post("/memory", response_model=FactOut, status_code=201)
def add_fact(data: FactIn, user: CurrentUser, db: Db):
    fact = memory.add(db, user.id, data.category, data.text, "user")
    db.commit()
    return fact


@router.put("/memory/{fact_id}", response_model=FactOut)
def update_fact(fact_id: int, data: FactIn, user: CurrentUser, db: Db):
    fact = memory.owned(db, fact_id, user.id)
    fact.category = data.category
    fact.text = " ".join(data.text.split())
    fact.source = "user"
    db.commit()
    return fact


@router.delete("/memory/{fact_id}", status_code=204)
def delete_fact(fact_id: int, user: CurrentUser, db: Db):
    db.delete(memory.owned(db, fact_id, user.id))
    db.commit()
    return Response(status_code=204)


@router.get("/chat/messages")
def messages(user: CurrentUser, db: Db, before: int | None = None, limit: int = 50):
    """The conversation with the assistant, newest first."""
    query = select(ChatMessage).where(ChatMessage.user_id == user.id)
    if before:
        query = query.where(ChatMessage.id < before)
    rows = db.scalars(query.order_by(ChatMessage.id.desc()).limit(min(limit, 200))).all()
    tz = zone(user.profile.timezone)
    return [
        {
            "id": row.id,
            "role": row.role,
            "text": row.text,
            "photos": row.photos,
            "created_at": to_local(row.created_at, tz).isoformat(timespec="minutes"),
        }
        for row in rows
    ]


@router.delete("/chat/messages", status_code=204)
def clear_messages(user: CurrentUser, db: Db):
    """Forgets the conversation; saved records and memory facts stay."""
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    state = db.get(ChatState, user.id)
    if state:
        state.context_from = utcnow()
    db.commit()
    return Response(status_code=204)
