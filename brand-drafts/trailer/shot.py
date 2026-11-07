#!/usr/bin/env python3
"""Screenshot an HTML page at an exact viewport — the storyboard/look-lock loop."""
import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", help="html file relative to this dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--wait", type=int, default=1400)
    ap.add_argument("--query", default="")
    ap.add_argument("--el", default=None, help="screenshot this selector instead of the viewport")
    ap.add_argument("--scale", type=float, default=1)
    args = ap.parse_args()

    url = (HERE / args.page).resolve().as_uri() + (args.query and f"?{args.query}" or "")
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-color-profile=srgb", "--disable-lcd-text",
                                    "--hide-scrollbars"])
        pg = b.new_page(viewport={"width": args.w, "height": args.h},
                        device_scale_factor=args.scale)
        pg.goto(url)
        pg.wait_for_timeout(args.wait)
        pg.evaluate("document.fonts.ready.then(()=>{window.READY=true})")
        pg.wait_for_timeout(300)
        if args.el:
            pg.locator(args.el).screenshot(path=str(out))
        else:
            pg.screenshot(path=str(out))
        b.close()
    print(out, f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    sys.exit(main())
