#!/usr/bin/env python3
"""Capture the real Lazy Plugin page module for the trailer.

Uses the cc-preview harness (real desktop/plugin.js + fixture data), rendered by
headless Chromium. Shoots the page element itself, so the PNG is the UI object
with no harness padding around it.
"""
import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

HARNESS = pathlib.Path.home() / ".hermes/cache/scratch/cc-preview/index.html"
OUT = pathlib.Path(__file__).resolve().parent / "assets/ui"
SCALE = 2

SHOTS = {
    # name: (viewport w, viewport h, query, settle ms)
    "pane": (1224, 1400, "", 2600),
    "pane-empty": (1224, 1400, "?empty=1", 2600),
    "wide": (1600, 1500, "", 2600),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb", "--disable-lcd-text"])
        for name, (w, h, query, wait) in SHOTS.items():
            if args.only and args.only not in name:
                continue
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=SCALE)
            page.goto(f"file://{HARNESS}{query}")
            page.wait_for_timeout(wait)
            el = page.query_selector("#root > *")
            if el is None:
                print(f"{name}: no page element", file=sys.stderr)
                continue
            box = el.bounding_box()
            path = OUT / f"{name}.png"
            el.screenshot(path=str(path))
            print(f"{path}  box={box}  {path.stat().st_size // 1024} KB")
            page.close()
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
