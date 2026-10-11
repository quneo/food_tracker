from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.analytics import service
from app.api.deps import CurrentUser, Db

router = APIRouter(prefix="/analytics", tags=["analytics"])


class DayMarkIn(BaseModel):
    complete: bool | None  # null = decide by the numbers again


@router.get("/daily")
def daily(
    user: CurrentUser, db: Db, start: date = Query(alias="from"), end: date = Query(alias="to")
):
    return service.daily(db, user, start, end)


@router.get("/report")
def report(
    user: CurrentUser,
    db: Db,
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    include_partial: bool = False,
):
    return service.report(db, user, start, end, include_partial)


@router.put("/days/{day}", status_code=204)
def mark_day(day: date, data: DayMarkIn, user: CurrentUser, db: Db):
    service.mark_day(db, user, day, data.complete)
