#!/usr/bin/env python3
"""Pre-render the eye's ASCII layers to PNG, one set per card theme.

Drawn as SVG text the eye is about fifteen thousand characters, and a browser
repaints all of them on every animation frame, which made the profile page
stutter on phones. Embedded as pictures they cost a few image draws per frame
and look the same; the animation moves and swaps the pictures instead.

Reads assets/eye.json and writes assets/eye/<layer>_<theme>.png for the static
base, the iris, the pupil, the catchlights and each lid frame. make_eye.py runs
this after it writes the JSON. Needs Pillow; run it by hand, not in the workflow.

usage: raster_eye.py [FONT.ttf]
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_card import THEMES  # noqa: E402

FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SCALE = 2                      # 2x covers retina desktops and phones (the art shows ~170px wide there)
OUT = ROOT / "assets" / "eye"


def layers(eye):
    """(name, sprite, colour key) for every layer; sprites are {col, row, rows}."""
    yield "base", dict(col=0, row=0, rows=eye["base"]), "art"
    yield "iris", eye["iris"], "value"
    yield "pupil", eye["pupil"], "art"
    yield "glint", eye["glint"], "art"
    for k, lid in enumerate(eye["lids"]):
        yield f"lid{k}", lid["text"], "art"


def render(eye, spr, font):
    cw, ch = eye["cell_w"] * SCALE, eye["cell_h"] * SCALE
    cols = max(len(r) for r in spr["rows"])
    w, h = round(cols * cw), round(len(spr["rows"]) * ch)
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    for r, row in enumerate(spr["rows"]):
        y = (r + eye["baseline"]) * ch
        for c, char in enumerate(row):
            if char != " ":
                d.text((c * cw, y), char, font=font, fill=255, anchor="ls")
    # a few alpha levels are plenty for anti-aliased glyph edges and keep the files small
    return mask.point(lambda v: round(v / 17) * 17)


def main():
    eye = json.loads((ROOT / "assets" / "eye.json").read_text())
    font = ImageFont.truetype(FONT, eye["font_size"] * SCALE)
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    total = 0
    for name, spr, key in layers(eye):
        mask = render(eye, spr, font)
        for theme, colors in THEMES.items():
            rgb = tuple(int(colors[key][i:i + 2], 16) for i in (1, 3, 5))
            img = Image.new("RGBA", mask.size, rgb + (0,))
            img.putalpha(mask)
            path = OUT / f"{name}_{theme}.png"
            img.save(path, optimize=True)
            total += path.stat().st_size
    print(f"wrote {len(list(OUT.glob('*.png')))} layers, {total // 1024} KB in all")


if __name__ == "__main__":
    main()
