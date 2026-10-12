from typing import Literal

from fastapi import APIRouter, Response

from app.api.deps import CurrentSession, CurrentUser, Db, Files
from app.media import images, service
from app.users import photo_lock

router = APIRouter(tags=["media"])


@router.get("/media/{media_id}")
def photo(
    media_id: int,
    user: CurrentUser,
    session: CurrentSession,
    db: Db,
    files: Files,
    size: Literal["preview", "original"] = "preview",
):
    """Photos are private: served only to their owner, never from a public bucket URL.
    Body photos behind a code come blurred until the code is entered in this browser."""
    item = service.owned(db, media_id, user.id)
    # Object keys never change, so the browser may keep its copy (privately); body photos
    # are never kept, so locking again hides them at once.
    cache = "private, max-age=604800, immutable"
    if item.kind == "body":
        cache = "private, no-store"
        if not photo_lock.visible(user.profile, session):
            data, _ = service.read(files, item, "preview")
            return Response(
                images.veiled(data),
                media_type="image/webp",
                headers={"Cache-Control": cache, "Content-Disposition": "inline"},
            )
    data, content_type = service.read(files, item, size)
    return Response(
        data,
        media_type=content_type,
        headers={"Cache-Control": cache, "Content-Disposition": "inline"},
    )
