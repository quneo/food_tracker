"""Image checks and resized copies (Pillow)."""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import DomainError

FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PREVIEW_SIDE = 640
AI_SIDE = 1600
Image.MAX_IMAGE_PIXELS = 60_000_000


@dataclass
class Picture:
    content_type: str
    width: int
    height: int
    preview: bytes


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise DomainError("Не удалось прочитать изображение. Подойдут JPEG, PNG или WebP") from None
    if image.format not in FORMATS:
        raise DomainError("Подойдут фотографии в JPEG, PNG или WebP")
    return image


def _resized(image: Image.Image, side: int) -> Image.Image:
    # Phones store rotation in EXIF; apply it so the copy stands upright.
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.thumbnail((side, side), Image.Resampling.LANCZOS)
    return image


def inspect(data: bytes) -> Picture:
    """Validates an upload and makes its preview (WebP, no metadata)."""
    image = _open(data)
    content_type = FORMATS[image.format]
    upright = ImageOps.exif_transpose(image)
    preview = io.BytesIO()
    _resized(image, PREVIEW_SIDE).save(preview, "WEBP", quality=80, method=4)
    return Picture(content_type, upright.width, upright.height, preview.getvalue())


def for_ai(data: bytes) -> bytes:
    """A JPEG for analysis: smaller, upright, without EXIF (no location leaves the server)."""
    image = _resized(_open(data), AI_SIDE)
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=85)
    return out.getvalue()
