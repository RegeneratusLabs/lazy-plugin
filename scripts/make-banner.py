#!/usr/bin/env python3
"""Cut the catalog banner: the engraved plate at 2:1, which is what the catalog asks for.

`image:` in a catalog entry is "optional https image on a GitHub host, 2:1 (e.g. 1200x600)". A 2:1
crop of the same plate the page uses, so the marketplace tile and the product look like one thing.

    ./venv/bin/python scripts/make-banner.py            # assets/banner.png, 1200x600
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path.home() / ".hermes/images/upload__h8o0zlh.jpg"
OUT = ROOT / "assets/banner.png"

ACCENT = (180, 140, 217)
PAPER = (239, 227, 242)
INK = (27, 15, 38)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--ratio", type=float, default=2.0, help="width/height; the catalog asks for 2")
    ap.add_argument("--wash", type=float, default=0.62, help="banner reads at tile size, so more ink")
    ap.add_argument("--colors", type=int, default=32)
    ap.add_argument("--blur", type=float, default=0.7)
    args = ap.parse_args()
    height = int(round(args.width / args.ratio))

    src = ImageOps.autocontrast(Image.open(SOURCE).convert("L"), cutoff=1)
    ink = ImageOps.invert(src)

    def lift(v: int) -> int:
        if v < 26:
            return 0
        return min(255, int(((v - 26) / 229) ** 1.15 * 255))

    alpha = Image.eval(Image.eval(ink, lift), lambda v: int(v * args.wash))

    rgb = Image.new("RGB", src.size)
    px = rgb.load()
    assert px is not None
    for y in range(src.height):
        t = y / max(1, src.height - 1)
        row = tuple(int(PAPER[i] + (ACCENT[i] - PAPER[i]) * t) for i in range(3))
        for x in range(src.width):
            px[x, y] = row

    art = rgb.convert("RGBA")
    art.putalpha(alpha)
    flat = Image.alpha_composite(Image.new("RGBA", art.size, (*INK, 255)), art).convert("RGB")

    # Cover-fit to the ratio: crop the longer side, never squash the drawing.
    target = args.width / height
    w, h = flat.size
    if w / h > target:
        new_w = int(round(h * target))
        left = (w - new_w) // 2
        flat = flat.crop((left, 0, left + new_w, h))
    else:
        new_h = int(round(w / target))
        top = (h - new_h) // 2
        flat = flat.crop((0, top, w, top + new_h))

    flat = flat.resize((args.width, height), Image.Resampling.LANCZOS)
    if args.blur:
        flat = flat.filter(ImageFilter.GaussianBlur(args.blur))
    # A banner is read at 300x150 in a list: give the line work a little more contrast back.
    flat = ImageOps.autocontrast(flat, cutoff=1)
    flat.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT).save(OUT, "PNG", optimize=True)
    print(f"{OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1024:.0f} KB  {args.width}x{height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
