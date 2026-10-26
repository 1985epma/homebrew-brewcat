"""brewcat logo: a black cat on an amber badge. Drawn from shapes, so no image assets are needed at runtime."""
from __future__ import annotations

import struct
import zlib
from typing import List, Tuple

# Shapes in unit coordinates (0..1), painted back to front.
BADGE = ("round", 0.0, 0.0, 1.0, 1.0, 0.22, "#f2b84b")
SHAPES: List[tuple] = [
    ("tri", (0.20, 0.48), (0.21, 0.14), (0.44, 0.33), "#111111"),
    ("tri", (0.80, 0.48), (0.79, 0.14), (0.56, 0.33), "#111111"),
    ("tri", (0.26, 0.40), (0.27, 0.24), (0.38, 0.34), "#e58aa0"),
    ("tri", (0.74, 0.40), (0.73, 0.24), (0.62, 0.34), "#e58aa0"),
    ("oval", 0.5, 0.60, 0.33, 0.28, "#111111"),
    ("oval", 0.37, 0.56, 0.075, 0.055, "#7be26b"),
    ("oval", 0.63, 0.56, 0.075, 0.055, "#7be26b"),
    ("oval", 0.37, 0.56, 0.014, 0.05, "#111111"),
    ("oval", 0.63, 0.56, 0.014, 0.05, "#111111"),
    ("tri", (0.46, 0.66), (0.54, 0.66), (0.5, 0.71), "#e58aa0"),
]


def draw_canvas(canvas, size: int) -> None:
    """Draw the logo on a tkinter Canvas of size x size pixels."""
    def px(v: float) -> float:
        return v * size
    _, x0, y0, x1, y1, r, color = BADGE
    r = px(r)
    pts = [(px(x0) + r, px(y0)), (px(x1) - r, px(y0)), (px(x1), px(y0)), (px(x1), px(y0) + r),
           (px(x1), px(y1) - r), (px(x1), px(y1)), (px(x1) - r, px(y1)), (px(x0) + r, px(y1)),
           (px(x0), px(y1)), (px(x0), px(y1) - r), (px(x0), px(y0) + r), (px(x0), px(y0))]
    canvas.create_polygon([c for p in pts for c in p], smooth=True, fill=color, outline=color)
    for s in SHAPES:
        if s[0] == "tri":
            canvas.create_polygon([px(c) for p in s[1:4] for c in p], fill=s[4], outline=s[4])
        else:
            _, cx, cy, rx, ry, col = s
            canvas.create_oval(px(cx - rx), px(cy - ry), px(cx + rx), px(cy + ry), fill=col, outline=col)


def _rgb(h: str) -> Tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _in_tri(p, a, b, c) -> bool:
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def _in_round(x, y, r) -> bool:
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def write_png(path: str, size: int = 512, ss: int = 3) -> None:
    """Rasterize the logo to an RGBA PNG (pure Python, supersampled)."""
    rows = []
    for j in range(size):
        row = bytearray([0])
        for i in range(size):
            acc = [0, 0, 0, 0]
            for sj in range(ss):
                for si in range(ss):
                    x, y = (i + (si + .5) / ss) / size, (j + (sj + .5) / ss) / size
                    col = None
                    if _in_round(x, y, BADGE[5]):
                        col = _rgb(BADGE[6])
                        for s in SHAPES:
                            if s[0] == "tri":
                                hit = _in_tri((x, y), s[1], s[2], s[3])
                                c = s[4]
                            else:
                                hit = ((x - s[1]) / s[3]) ** 2 + ((y - s[2]) / s[4]) ** 2 <= 1
                                c = s[5]
                            if hit:
                                col = _rgb(c)
                    if col:
                        acc[0] += col[0]
                        acc[1] += col[1]
                        acc[2] += col[2]
                        acc[3] += 255
            n = ss * ss
            a = acc[3] // n
            k = max(acc[3] // 255, 1)
            row += bytes([acc[0] // k, acc[1] // k, acc[2] // k, a])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


if __name__ == "__main__":
    write_png("assets/brewcat.png", 1024)
