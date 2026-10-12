"""Image checks and resized copies (Pillow)."""

import io
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

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


def veiled(data: bytes) -> bytes:
    """A copy with nothing recognisable left: a few pixels across, scaled back and blurred."""
    image = Image.open(io.BytesIO(data)).convert("RGB")
    width, height = image.size
    tiny = image.resize(
        (max(1, 6 * width // max(width, height)), max(1, 6 * height // max(width, height)))
    )
    side = 360
    size = (side * width // max(width, height), side * height // max(width, height))
    soft = tiny.resize(size, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(24))
    out = io.BytesIO()
    soft.save(out, "WEBP", quality=60)
    return out.getvalue()


def for_ai(data: bytes, side: int = AI_SIDE) -> bytes:
    """A JPEG for analysis: smaller, upright, without EXIF (no location leaves the server)."""
    image = _resized(_open(data), side)
    out = io.BytesIO()
    image.convert("RGB").save(out, "JPEG", quality=85)
    return out.getvalue()
