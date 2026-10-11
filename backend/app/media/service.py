import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import DomainError, NotFound
from app.media import images
from app.media.models import Media, PendingDeletion
from app.media.storage import Storage, StorageError

log = logging.getLogger(__name__)


def user_prefix(user_id: int) -> str:
    return f"users/{user_id}/"


def save_photo(
    db: Session,
    storage: Storage,
    user_id: int,
    data: bytes,
    kind: str,
    meal_id: int | None = None,
    message_id: int | None = None,
) -> Media:
    """Stores the original and a preview; the caller commits."""
    limit = get_settings().max_upload_mb
    if len(data) > limit * 1024 * 1024:
        raise DomainError(f"Фото больше {limit} МБ", 413)
    picture = images.inspect(data)
    base = f"{user_prefix(user_id)}{uuid.uuid4().hex}"
    original = f"{base}/original.{images.EXTENSIONS[picture.content_type]}"
    preview = f"{base}/preview.webp"
    try:
        storage.put(original, data, picture.content_type)
        storage.put(preview, picture.preview, "image/webp")
    except StorageError:
        log.exception("photo upload failed")
        raise DomainError("Хранилище фото недоступно. Попробуйте позже", 503) from None
    media = Media(
        user_id=user_id,
        kind=kind,
        object_key=original,
        preview_key=preview,
        content_type=picture.content_type,
        size=len(data),
        width=picture.width,
        height=picture.height,
        meal_id=meal_id,
        message_id=message_id,
    )
    db.add(media)
    db.flush()
    return media


def owned(db: Session, media_id: int, user_id: int) -> Media:
    media = db.get(Media, media_id)
    if not media or media.user_id != user_id:
        raise NotFound("Фото не найдено")
    return media


def read(storage: Storage, media: Media, size: str) -> tuple[bytes, str]:
    key, content_type = (
        (media.preview_key, "image/webp")
        if size == "preview"
        else (media.object_key, media.content_type)
    )
    try:
        return storage.get(key), content_type
    except StorageError:
        log.exception("photo read failed")
        raise DomainError("Хранилище фото недоступно. Попробуйте позже", 503) from None


def drop(db: Session, items: list[Media]):
    """Deletes photo records and queues their files; the caller commits, then purge()."""
    for media in items:
        db.add_all([PendingDeletion(key=media.object_key), PendingDeletion(key=media.preview_key)])
        db.delete(media)


def drop_user_files(db: Session, user_id: int):
    db.add(PendingDeletion(key=user_prefix(user_id)))


def purge(db: Session, storage: Storage, limit: int = 200) -> int:
    """Removes queued files from storage; failures stay queued for the next try."""
    done = 0
    for item in db.scalars(select(PendingDeletion).order_by(PendingDeletion.id).limit(limit)):
        try:
            if item.key.endswith("/"):
                storage.delete_prefix(item.key)
            else:
                storage.delete(item.key)
        except StorageError as error:
            item.attempts += 1
            item.last_error = str(error)[:300]
            continue
        db.delete(item)
        done += 1
    db.commit()
    return done
