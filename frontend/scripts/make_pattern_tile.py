"""Turns the generated doodle sheet into a seamless tile with transparent background.

Doodles are cut out as connected components (strokes merged by dilation), then placed on a
new torus-shaped canvas: anything crossing an edge is drawn again on the opposite side, so
the tile repeats without seams. Output: alpha mask (line darkness -> opacity)."""

import random
import sys
from collections import deque

from PIL import Image, ImageFilter

SRC, OUT = sys.argv[1], sys.argv[2]
TILE = 720  # output tile size (px) before downscale
random.seed(7)

src = Image.open(SRC).convert("L")
W, H = src.size
ink = src.point(lambda v: 255 - v)  # lines bright
mask = ink.point(lambda v: 255 if v > 60 else 0)
grown = mask.filter(ImageFilter.MaxFilter(15))  # merge strokes of one doodle

# Connected components on a 1/2-scale grown mask (speed), mapped back to full scale.
small = grown.resize((W // 2, H // 2))
sw, sh = small.size
spx = small.load()
seen = bytearray(sw * sh)
labels = [0] * (sw * sh)
boxes = []
for y in range(sh):
    for x in range(sw):
        if spx[x, y] < 128 or seen[y * sw + x]:
            continue
        queue = deque([(x, y)])
        seen[y * sw + x] = 1
        label = len(boxes) + 1
        x0 = x1 = x
        y0 = y1 = y
        count = 0
        while queue:
            cx, cy = queue.popleft()
            labels[cy * sw + cx] = label
            count += 1
            x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < sw and 0 <= ny < sh and not seen[ny * sw + nx] and spx[nx, ny] >= 128:
                    seen[ny * sw + nx] = 1
                    queue.append((nx, ny))
        boxes.append((x0 * 2, y0 * 2, x1 * 2 + 2, y1 * 2 + 2, count, label))

# Keep whole doodles of a sensible size, one copy of each (left period only).
doodles = []
for x0, y0, x1, y1, count, label in boxes:
    w, h = x1 - x0, y1 - y0
    if x0 <= 4 or y0 <= 4 or x1 >= W - 4 or y1 >= H - 4:
        continue
    if not (40 <= w <= 230 and 40 <= h <= 230) or count < 150:
        continue
    if x0 >= 627:
        continue
    doodles.append((x0, y0, x1, y1, label))
print("doodles:", len(doodles))

tile = Image.new("L", (TILE, TILE), 0)
placed = []  # (cx, cy, r)
order = doodles[:]
random.shuffle(order)
scale = 0.62


def torus_far(cx, cy, r):
    for px, py, pr in placed:
        dx = min(abs(cx - px), TILE - abs(cx - px))
        dy = min(abs(cy - py), TILE - abs(cy - py))
        if (dx * dx + dy * dy) ** 0.5 < r + pr + 12:
            return False
    return True


for x0, y0, x1, y1, label in order * 3:  # each doodle may appear more than once
    piece = ink.crop((x0, y0, x1, y1))
    own = Image.new("L", (sw, sh), 0)
    own.putdata([255 if v == label else 0 for v in labels])
    piece_mask = own.resize((W, H)).crop((x0, y0, x1, y1))
    piece = Image.composite(piece, Image.new("L", piece.size, 0), piece_mask)
    piece = piece.resize((int(piece.width * scale), int(piece.height * scale)), Image.LANCZOS)
    piece = piece.rotate(random.uniform(-18, 18), resample=Image.BICUBIC, expand=True)
    r = max(piece.size) / 2
    for _ in range(400):
        cx, cy = random.uniform(0, TILE), random.uniform(0, TILE)
        if torus_far(cx, cy, r):
            placed.append((cx, cy, r))
            left, top = int(cx - piece.width / 2), int(cy - piece.height / 2)
            for ox in (-TILE, 0, TILE):
                for oy in (-TILE, 0, TILE):
                    region = (left + ox, top + oy)
                    current = tile.crop(
                        (*region, region[0] + piece.width, region[1] + piece.height)
                    )
                    from PIL import ImageChops

                    tile.paste(ImageChops.lighter(current, piece), region)
            break
print("placed:", len(placed))

final = tile.resize((480, 480), Image.LANCZOS)
rgba = Image.new("RGBA", final.size, (0, 0, 0, 0))
rgba.putalpha(final)
rgba.save(OUT, "WEBP", lossless=True)
preview = Image.new("RGB", (960, 960), (240, 236, 220))
for ox in (0, 480):
    for oy in (0, 480):
        preview.paste((40, 60, 50), (ox, oy), final)
preview.save(OUT.replace(".webp", "-preview.jpg"), quality=85)
