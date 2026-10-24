"""Cuts the app icons from one square picture: full-bleed ones for launchers that shape
icons themselves, rounded tiles (transparent corners) for the rest and the app's mark.

The picture (icon-source.webp, a lime slice whose segments read as a macro chart) was made
with Codex image generation. Run: python frontend/scripts/make_icons.py [picture]"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent
source = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "icon-source.webp"
public = HERE.parent / "public"
assets = HERE.parent / "src" / "assets"

art = Image.open(source).convert("RGB")
side = min(art.size)
left, top = (art.width - side) // 2, (art.height - side) // 2
art = art.crop((left, top, left + side, top + side)).resize((1024, 1024), Image.LANCZOS)


def tile(size: int) -> Image.Image:
    """Rounded square like the launcher's: 22.5% corners, drawn at 4x for smooth edges."""
    big = size * 4
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=int(big * 0.225), fill=255
    )
    mask = mask.resize((size, size), Image.LANCZOS)
    out = art.resize((size, size), Image.LANCZOS).convert("RGBA")
    out.putalpha(mask)
    return out


def padded(scale: float) -> Image.Image:
    """The picture a bit smaller on its own background, so a launcher's circle never cuts
    the subject: the background is the picture's left edge stretched across (it is a
    vertical gradient), the shrunk picture fades into it at the edges."""
    column = art.crop((0, 0, 1, 1024)).resize((1024, 1024))
    inner = int(1024 * scale)
    small = art.resize((inner, inner), Image.LANCZOS)
    feather = Image.new("L", (inner, inner), 0)
    edge = int(inner * 0.06)
    ImageDraw.Draw(feather).rounded_rectangle(
        (edge, edge, inner - edge, inner - edge), radius=edge * 3, fill=255
    )
    feather = feather.filter(ImageFilter.GaussianBlur(edge / 2))
    offset = (1024 - inner) // 2
    column.paste(small, (offset, offset), feather)
    return column


padded(0.84).resize((512, 512), Image.LANCZOS).save(public / "icon-maskable-512.png", optimize=True)
art.resize((180, 180), Image.LANCZOS).save(public / "apple-touch-icon.png", optimize=True)
tile(512).save(public / "icon-512.png", optimize=True)
tile(192).save(public / "icon-192.png", optimize=True)
tile(64).save(public / "favicon.png", optimize=True)
# The mark in the app's rail, sign-in and splash: 96 px covers 48 px at 2x.
tile(96).save(assets / "app-mark.png", optimize=True)
for path in [*public.glob("*.png"), assets / "app-mark.png"]:
    print(path.name, path.stat().st_size)
