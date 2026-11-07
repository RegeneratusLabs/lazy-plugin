"""Regenerate the mascot wash baked into desktop/plugin.js.

    python3 scripts/make-mascot.py ~/.hermes/images/upload_rtzrksnb.jpg

The source is an engraving whose "transparency" was drawn in as a checkerboard, so the plate is
derived rather than used: highlights and the checker both go transparent, and the ink is recoloured
to --cc-paper with the page wash (11%) baked into the alpha. Palette PNG, because line art at 48
colours is a quarter the size of WebP and the desktop half has to carry it inline (a plugin is one
ESM file, with no asset door of its own).
"""
import base64
import io
import sys

import numpy as np
from PIL import Image

PAPER = (0xEF, 0xE3, 0xF2)
SIZE = 560
WASH = 0.11
COLOURS = 48
INK_CUTOFF = 200.0  # everything lighter than this is highlight or checkerboard


def plate(path: str) -> Image.Image:
    grey = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    alpha = np.clip((INK_CUTOFF - grey) / INK_CUTOFF, 0, 1) ** 0.9 * WASH
    rgb = np.zeros(grey.shape + (3,), dtype=np.uint8)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = PAPER
    rgba = Image.fromarray(np.dstack([rgb, (alpha * 255).astype(np.uint8)]), "RGBA")
    return rgba.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    image = plate(sys.argv[1])
    buf = io.BytesIO()
    image.quantize(colors=COLOURS, method=Image.Quantize.FASTOCTREE).save(buf, "PNG", optimize=True)
    png = buf.getvalue()
    open("assets/mascot-plate.png", "wb").write(png)
    print(f"assets/mascot-plate.png  {len(png) // 1024} KB")
    print("data URI for desktop/plugin.js (const MASCOT):")
    print("data:image/png;base64," + base64.b64encode(png).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
