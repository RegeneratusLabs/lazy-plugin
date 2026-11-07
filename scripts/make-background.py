#!/usr/bin/env python3
"""Turn the engraved cat plate into a full-bleed backdrop.

The source is a scan: aubergine ink on cream paper. For a dark page we want the drawing, not the
paper — so ink becomes alpha and the paper becomes nothing, then the ink is recoloured to the palette
and washed back so text and panels still win.

    ./venv/bin/python scripts/make-background.py            # writes assets/background.png
    ./venv/bin/python scripts/make-background.py --wash .34 # heavier drawing

Same source file the trailer mockup used: ~/.hermes/images/upload_ct1iv9bp.jpg
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path.home() / ".hermes/images/upload__h8o0zlh.jpg"      # 16:9 plate, no padding needed
OUT = ROOT / "assets/background.png"

# The page's paper/ink, from docs/DESIGN.md. The drawing is tinted with the accent, not white, so it
# reads as part of the same monochrome.
ACCENT = (180, 140, 217)     # CC.accent
PAPER = (239, 227, 242)      # CC.paper — the brightest line work


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wash", type=float, default=0.30, help="max alpha of the drawing (0-1)")
    ap.add_argument("--size", type=int, default=900, help="square edge in pixels")
    ap.add_argument("--width", type=int, default=1400, help="width for an already-wide source")
    ap.add_argument("--height", type=int, default=760, help="height of the wide canvas a square plate sits on")
    ap.add_argument("--gamma", type=float, default=1.15, help=">1 keeps the mid-tones darker")
    ap.add_argument("--colors", type=int, default=32, help="palette size; fewer = smaller data URI")
    ap.add_argument("--blur", type=float, default=0.7, help="soften hatching before quantising")
    args = ap.parse_args()

    src = Image.open(SOURCE).convert("L")
    src = ImageOps.autocontrast(src, cutoff=1)

    # Invert: ink is dark in the scan, and we want it opaque.
    ink = ImageOps.invert(src)
    # Lift the floor so paper dust does not become grey fog, then scale to the wash.
    def lift(v: int) -> int:
        if v < 26:
            return 0
        return min(255, int(((v - 26) / 229) ** args.gamma * 255))

    ink = Image.eval(ink, lift)
    alpha = Image.eval(ink, lambda v: int(v * args.wash))

    # Colour: a vertical ramp from paper at the top to accent at the bottom, matching the page's light.
    w, h = src.size
    rgb = Image.new("RGB", (w, h))
    px = rgb.load()
    assert px is not None
    for y in range(h):
        t = y / max(1, h - 1)
        px_row = tuple(int(PAPER[i] + (ACCENT[i] - PAPER[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = px_row

    art = rgb.convert("RGBA")
    art.putalpha(alpha)
    if src.width / src.height >= 1.4:
        art = art.resize((args.width, int(round(args.width * art.height / art.width))),
                         Image.Resampling.LANCZOS)
    else:
        art = art.resize((args.size, args.size), Image.Resampling.LANCZOS)

    # The page's own ink is the ground: flattening the drawing onto it means the backdrop is opaque,
    # needs no blend mode, and quantises to a palette (a fraction of the bytes — the plugin inlines it).
    ground = Image.new("RGBA", art.size, (27, 15, 38, 255))       # CC.ink
    flat = Image.alpha_composite(ground, art).convert("RGB")
    if args.blur:
        flat = flat.filter(ImageFilter.GaussianBlur(args.blur))

    # A square plate under `background-size: cover` gets cropped to a snout on a wide window. A wide
    # source needs no help; anything squarer than 1.4 gets padded onto a 16:9 ink canvas instead.
    if flat.width / flat.height >= 1.4:
        flat = flat.resize((args.width, int(round(args.width * flat.height / flat.width))),
                           Image.Resampling.LANCZOS)
        plate = flat
    else:
        plate_h = args.height
        plate_w = int(round(plate_h * flat.width / flat.height))
        plate = flat.resize((plate_w, plate_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (int(round(plate_h * 16 / 9)), plate_h), (27, 15, 38))
        canvas.paste(plate, ((canvas.width - plate_w) // 2, 0))
        flat = canvas
    flat = flat.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT)
    flat.save(OUT, "PNG", optimize=True)
    print(f"{OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1024:.0f} KB  {art.size[0]}x{art.size[1]}  wash={args.wash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
