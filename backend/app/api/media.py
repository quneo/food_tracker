from typing import Literal

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser, Db, Files
from app.media import service

router = APIRouter(tags=["media"])


@router.get("/media/{media_id}")
def photo(
    media_id: int,
    user: CurrentUser,
    db: Db,
    files: Files,
    size: Literal["preview", "original"] = "preview",
):
    """Photos are private: served only to their owner, never from a public bucket URL."""
    item = service.owned(db, media_id, user.id)
    data, content_type = service.read(files, item, size)
    return Response(
        data,
        media_type=content_type,
        headers={
            # Object keys never change, so the browser may keep its copy (privately).
            "Cache-Control": "private, max-age=604800, immutable",
            "Content-Disposition": "inline",
        },
    )
