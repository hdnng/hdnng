#!/usr/bin/env python3
"""Turn a photo into the ASCII portrait used by the profile card (assets/ascii.txt).

usage: make_ascii.py PHOTO COLS ROWS OUT_FILE [LEFT TOP RIGHT BOTTOM]
The optional box crops the photo first, as fractions (0-1) of the picture.
Works best on a photo whose background is already white: dark pixels become
dense characters and anything paler than FLOOR is left blank.
"""
import sys
from PIL import Image, ImageOps, ImageFilter
import numpy as np

SRC, COLS, ROWS, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
BOX = [float(x) for x in sys.argv[5:9]] or [0, 0, 1, 1]
RAMP = " .`:-=+*cox%#@"  # sparse -> dense, no XML-special characters
FLOOR = 0.12
GAMMA = 1.5  # above 1 lightens mid-tones (skin) so facial features stand out

im = Image.open(SRC).convert("RGB")
w, h = im.size
im = im.crop((round(BOX[0] * w), round(BOX[1] * h), round(BOX[2] * w), round(BOX[3] * h)))
g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
g = g.resize((COLS * 4, ROWS * 4), Image.LANCZOS).filter(ImageFilter.UnsharpMask(3, 120, 2))
v = np.array(g.resize((COLS, ROWS), Image.LANCZOS)).astype(float) / 255

lines = []
for r in range(ROWS):
    line = ""
    for c in range(COLS):
        t = (max(1 - v[r, c] - FLOOR, 0) / (1 - FLOOR)) ** GAMMA
        line += RAMP[min(len(RAMP) - 1, int(t * len(RAMP)))]
    lines.append(line.rstrip())
open(OUT, "w").write("\n".join(lines))
