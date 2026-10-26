"""Weigh notes on the site: grams written down now for a meal eaten later."""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, Db
from app.notes import service as notes

router = APIRouter(tags=["notes"])
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    # None: soon (burns in three hours).
    meal_type: MealType | None = None


class NotePatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    meal_type: MealType | None = None


class NoteOut(BaseModel):
    id: int
    text: str
    meal_type: MealType | None
    due: bool
    label: str
    due_from: str
    expires_at: str
    source: str


@router.get("/notes", response_model=list[NoteOut])
def list_notes(user: CurrentUser, db: Db):
    return [notes.out(note, user) for note in notes.active(db, user.id)]


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(data: NoteIn, user: CurrentUser, db: Db):
    note = notes.create(db, user, data.text, data.meal_type, "web")
    db.commit()
    return notes.out(note, user)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, data: NotePatch, user: CurrentUser, db: Db):
    note = notes.usable(db, note_id, user.id)
    if data.text is not None:
        note.text = notes.clean(data.text)
    if "meal_type" in data.model_fields_set:
        notes.place(note, data.meal_type, user)
    db.commit()
    return notes.out(note, user)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: CurrentUser, db: Db):
    note = notes.owned(db, note_id, user.id)
    note.status = "deleted"
    db.commit()
    return Response(status_code=204)
