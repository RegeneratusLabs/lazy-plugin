#!/usr/bin/env python3
"""Cut the catalog banner from the plate, as printed.

The catalog wants a 2:1 picture on a GitHub host. The plate is a dark-ink engraving on pale paper, and
that is what goes up: crop to 2:1, keep the paper, keep the ink. The page inverts and washes the same
drawing for its dark ground, but a marketplace tile should look like the print, not like a UI state.

    ./venv/bin/python scripts/make-banner.py           # assets/banner.png, 1200x600
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path.home() / ".hermes/images/upload_fga4yhrg.jpg"
OUT = ROOT / "assets/banner.png"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--ratio", type=float, default=2.0, help="width/height; the catalog asks for 2")
    ap.add_argument("--colors", type=int, default=48)
    ap.add_argument("--contrast", type=float, default=1.06)   # a tile is read at 300x150
    args = ap.parse_args()
    height = int(round(args.width / args.ratio))

    art = Image.open(SOURCE).convert("RGB")

    # Cover-fit to the ratio: crop the longer side, never squash the drawing.
    target = args.width / height
    w, h = art.size
    if w / h > target:
        new_w = int(round(h * target))
        left = (w - new_w) // 2
        art = art.crop((left, 0, left + new_w, h))
    else:
        new_h = int(round(w / target))
        top = (h - new_h) // 2
        art = art.crop((0, top, w, top + new_h))

    art = art.resize((args.width, height), Image.Resampling.LANCZOS)
    art = ImageEnhance.Contrast(art).enhance(args.contrast)

    # Palette PNG: the engraving is nearly two-tone, so 48 colours is visually lossless here.
    art.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT).save(OUT, "PNG", optimize=True)
    print(f"{OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1024:.0f} KB  {args.width}x{height}  (as printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
