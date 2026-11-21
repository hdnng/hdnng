#!/usr/bin/env python3
"""Draw a detailed pair of eyes and convert it to ASCII layers for the profile card.

Writes assets/eyes.json, which build_card.py turns into an animated SVG: the
irises glance around and the upper lids blink. Each eye is split into layers so
the parts can move independently:

  base   brows, creases, lower lids and lashes, eye whites (static)
  iris   iris texture and pupil, a sprite that slides behind the eye opening
  lid    upper lid line and lashes, a sprite that slides down to blink

Characters are picked by matching each cell against the glyph shapes of a
monospace font, so lashes and lid lines come out as / \\ | _ strokes rather than
plain shading. Needs Pillow and numpy; run it by hand, not in the workflow.

usage: make_eyes.py [FONT.ttf]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

COLS, ROWS = 152, 68            # character grid of the art column (a 5px font)
ART_W = 444.0                   # px, same width as the old portrait (card stays 1032px wide)
CELL_W, CELL_H = ART_W / COLS, ART_W / COLS * 2   # ~4.22 x 8.44 px, i.e. a 7px monospace font
GW, GH = 12, 24                 # raster size of one cell (supersampled)
SX, SY = GW / CELL_W, GH / CELL_H
GLYPHS = " .,:;'`\"-_~^!|/\\()[]{}?=+*#%@$ocvuxzeaVYTLJlIi17"

# eye geometry, in art px
EYES = [dict(side=-1, cx=113.0), dict(side=1, cx=331.0)]
CY = 222.0
A, H_UP, H_LO, TILT = 96.0, 50.0, 32.0, 7.0
R_IRIS, R_PUPIL = 40.0, 15.5


def upper(u):
    """Upper lid height above the centre line at u (-1 inner corner .. 1 outer corner)."""
    return H_UP * max(1 - u * u, 0) ** 0.7 * (1 - 0.18 * u) + TILT * u


def lower(u):
    return H_LO * max(1 - u * u, 0) ** 0.85 * (1 + 0.22 * u) - 0.4 * TILT * u


def pt(eye, u, dy):
    return eye["cx"] + eye["side"] * u * A, CY + dy


def opening(eye, n=48):
    us = np.linspace(-1, 1, n)
    top = [pt(eye, u, -upper(u)) for u in us]
    bot = [pt(eye, u, lower(u)) for u in us[::-1]]
    return top + bot


class Canvas:
    """Grayscale ink canvas in art px coordinates (0 = paper, 1 = full ink)."""

    def __init__(self):
        self.img = Image.new("F", (COLS * GW, ROWS * GH), 0.0)
        self.d = ImageDraw.Draw(self.img)

    def line(self, pts, width, ink):
        self.d.line([(x * SX, y * SY) for x, y in pts], fill=ink, width=max(1, round(width * SX)), joint="curve")

    def stroke(self, pts, w0, w1, ink):
        """Tapered stroke: width goes from w0 to w1 along the points."""
        n = len(pts) - 1
        for k in range(n):
            w = w0 + (w1 - w0) * k / max(n - 1, 1)
            self.line(pts[k:k + 2], w, ink)
            r = w * SX / 2
            x, y = pts[k + 1][0] * SX, pts[k + 1][1] * SY
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=ink)

    def poly(self, pts, ink):
        self.d.polygon([(x * SX, y * SY) for x, y in pts], fill=ink)

    def ellipse(self, cx, cy, rx, ry, ink):
        self.d.ellipse(((cx - rx) * SX, (cy - ry) * SY, (cx + rx) * SX, (cy + ry) * SY), fill=ink)

    def array(self):
        return np.clip(np.array(self.img), 0, 1)


def bezier(p0, p1, p2, n=10):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in np.linspace(0, 1, n)]


def draw_base(cv, eye, rng):
    s = eye["side"]
    us = np.linspace(-1, 1, 60)
    # eye white: faint shading, darker under the upper lid and towards the corners
    mask = Image.new("L", cv.img.size, 0)
    ImageDraw.Draw(mask).polygon([(x * SX, y * SY) for x, y in opening(eye)], fill=255)
    m = np.array(mask) / 255.0
    yy, xx = np.mgrid[0:cv.img.size[1], 0:cv.img.size[0]]
    ax, ay = xx / SX, yy / SY
    u = np.clip((ax - eye["cx"]) * s / A, -1, 1)
    top = CY - np.vectorize(upper)(u)
    shade = 0.32 * np.exp(-(ay - top) / 4.0)
    arr = np.array(cv.img)
    arr = np.maximum(arr, shade * m)
    cv.img = Image.fromarray(arr.astype("float32"))
    cv.d = ImageDraw.Draw(cv.img)
    # inner corner
    x, y = pt(eye, -0.93, 2)
    cv.ellipse(x, y, 4, 3.5, 0.35)
    # lower lid line, with a soft rim just below
    cv.stroke([pt(eye, u, lower(u)) for u in us], 1.4, 1.4, 0.75)
    cv.stroke([pt(eye, u, lower(u) + 4) for u in np.linspace(-0.85, 0.9, 40)], 1.0, 1.0, 0.25)
    # crease above the upper lid
    cv.stroke([pt(eye, u, -upper(u) - 15 - 5 * max(1 - u * u, 0)) for u in np.linspace(-0.82, 1.02, 50)], 1.2, 1.8, 0.55)
    # lower lashes: short, pointing down and out
    for u0 in np.linspace(-0.45, 0.95, 13):
        x, y = pt(eye, u0, lower(u0) + 1)
        ln = 4 + 6 * (u0 + 0.5) / 1.45
        ang = math.radians(90 - 35 * u0) if s > 0 else math.radians(90 + 35 * u0)
        cv.stroke([(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln)], 1.1, 0.5, 0.8)
    # brow: evenly combed hairs in a few rows along an arch, fuller at the inner end
    for row in range(4):
        for u0 in np.linspace(-1.02, 1.1, 46):
            t = (u0 + 1.02) / 2.12
            if row >= 3 and t > 0.45 or row >= 2 and t > 0.8:
                continue
            mid = -H_UP - 44 - 13 * max(1 - (u0 - 0.15) ** 2, 0) + 6 * u0
            x, y = pt(eye, u0 + rng.uniform(-0.01, 0.01), mid + (row - 1.2) * 3.4)
            lean = math.radians(-58 + 40 * t)              # upright at the inner end, flat at the tail
            ln = 9 - 3 * t
            cv.stroke([(x, y), (x + math.cos(lean) * s * ln, y + math.sin(lean) * ln)], 0.9, 0.45, 0.85)


def draw_lid(cv, eye):
    s = eye["side"]
    us = np.linspace(-1, 1.08, 70)
    # thick lid line with a small flick past the outer corner
    pts = [pt(eye, u, -upper(min(u, 1)) - (max(u - 1, 0) * 60)) for u in us]
    for k in range(len(pts) - 1):
        u = us[k]
        w = 1.6 + 1.6 * max(1 - abs(u - 0.2) ** 2, 0)
        cv.stroke(pts[k:k + 2], w, w, 1.0)
    # upper lashes: curved, longer and more swept towards the outer corner
    for u0 in np.linspace(-0.75, 1.02, 21):
        x, y = pt(eye, u0, -upper(u0))
        t = (u0 + 0.8) / 1.82
        ln = 9 + 15 * t ** 1.3
        ang = math.radians(-90 - 10 + 70 * t)                 # up, sweeping outwards
        dx, dy = math.cos(ang) * s, math.sin(ang)
        p2 = (x + dx * ln + s * 4 * t, y + dy * ln + 3)
        p1 = (x + dx * ln * 0.5, y + dy * ln * 0.6 - 2)
        cv.stroke(bezier((x, y), p1, p2, 10), 1.3, 0.35, 1.0)


def draw_iris(cv, cx, cy):
    yy, xx = np.mgrid[0:cv.img.size[1], 0:cv.img.size[0]]
    dx, dy = xx / SX - cx, yy / SY - cy
    r, th = np.hypot(dx, dy), np.arctan2(dy, dx)
    rr = np.clip((r - R_PUPIL) / (R_IRIS - R_PUPIL), 0, 1)
    rng = np.random.default_rng(3)
    phase = rng.uniform(0, 6.28, 6)
    fib = sum(np.sin(k * th + phase[i]) for i, k in enumerate((23, 31, 37, 47, 53, 61))) / 6
    spokes = np.clip(np.sin(26 * th + 1.7 * np.sin(5 * th)) * 0.5 + 0.5, 0, 1) ** 3
    ink = 0.12 + 0.42 * spokes * (0.35 + 0.65 * rr) + 0.12 * fib
    ink += 0.75 * np.clip((rr - 0.8) / 0.2, 0, 1) ** 1.2         # dark limbal ring
    ink += 0.35 * np.exp(-((rr - 0.12) / 0.07) ** 2)             # collarette around the pupil
    ink = np.where(r < R_PUPIL, 1.0, ink)
    ink = np.where(r > R_IRIS, 0.0, ink)
    for hx, hy, hr in ((-11, -12, 7.5), (10, 9, 3)):              # catchlights
        ink = np.where(np.hypot(dx - hx, dy - hy) < hr, 0.0, ink)
    cv.img = Image.fromarray(np.clip(ink, 0, 1).astype("float32"))
    cv.d = ImageDraw.Draw(cv.img)


def glyph_bank():
    font = ImageFont.truetype(FONT, 20)
    asc, desc = font.getmetrics()
    bank = []
    for ch in GLYPHS:
        im = Image.new("L", (GW, GH), 0)
        ImageDraw.Draw(im).text((0, (GH - asc - desc) / 2), ch, font=font, fill=255)
        bank.append(np.array(im.filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32) / 255)
    return np.stack(bank), asc / (asc + desc)


def to_ascii(arr, bank, gain=1.0):
    """Best-matching glyph per cell; returns rows of text."""
    img = Image.fromarray((np.clip(arr * gain, 0, 1) * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.8))
    a = np.array(img, dtype=np.float32) / 255
    a = a.reshape(ROWS, GH, COLS, GW).transpose(0, 2, 1, 3).reshape(ROWS * COLS, GH * GW)
    g = bank.reshape(len(GLYPHS), GH * GW)
    target = a * 0.62                                  # densest glyphs cover ~60% of a cell
    err = (target ** 2).sum(1)[:, None] - 2 * target @ g.T + (g ** 2).sum(1)[None, :]
    err[:, 0] -= 0.4                                   # prefer blanks for near-empty cells
    best = err.argmin(1).reshape(ROWS, COLS)
    return ["".join(GLYPHS[k] for k in row) for row in best]


def sprite(rows):
    """Crop a layer to its bounding box: (col0, row0, rows)."""
    used = [i for i, r in enumerate(rows) if r.strip()]
    if not used:
        return None
    c0 = min(len(r) - len(r.lstrip()) for r in rows if r.strip())
    c1 = max(len(r.rstrip()) for r in rows)
    return dict(col=c0, row=used[0], rows=[rows[i][c0:c1].rstrip() for i in range(used[0], used[-1] + 1)])


def main():
    bank, base_frac = glyph_bank()
    rng = np.random.default_rng(7)
    base, lid = Canvas(), Canvas()
    for eye in EYES:
        draw_base(base, eye, rng)
        draw_lid(lid, eye)
    base_rows = to_ascii(base.array(), bank)
    lid_rows = to_ascii(lid.array(), bank, gain=1.2)
    # the lid sprite sits on top: clear those cells from the base layer
    base_rows = ["".join(" " if l != " " else b for b, l in zip(br, lr)) for br, lr in zip(base_rows, lid_rows)]

    out = dict(cols=COLS, rows=ROWS, cell_w=CELL_W, cell_h=CELL_H, font_size=round(CELL_W / 0.6, 3),
               baseline=base_frac, base=base_rows, eyes=[])
    for eye in EYES:
        # iris drawn centred on a whole cell so the sprite lines up with the grid at rest
        col, row = round(eye["cx"] / CELL_W), round(CY / CELL_H)
        icx, icy = (col + 0.5) * CELL_W, (row + 0.5) * CELL_H
        iris = Canvas()
        draw_iris(iris, icx, icy)
        rows = to_ascii(iris.array(), bank)
        pupil = Canvas()
        pupil.ellipse(icx, icy, R_PUPIL, R_PUPIL, 1.0)
        pmask = to_ascii(pupil.array(), bank)
        iris_rows = ["".join(c if p == " " else " " for c, p in zip(r, m)) for r, m in zip(rows, pmask)]
        pupil_rows = ["".join(c if p != " " else " " for c, p in zip(r, m)) for r, m in zip(rows, pmask)]
        lid_eye = [("".join(ch if (abs((k + 0.5) * CELL_W - eye["cx"]) < A + 40) else " " for k, ch in enumerate(r)))
                   for r in lid_rows]
        lid_spr = sprite(lid_eye)
        us = np.linspace(-1, 1, 48)
        lid_curve = [pt(eye, u, -upper(u)) for u in us]
        out["eyes"].append(dict(
            center=[icx, icy], r_iris=R_IRIS,
            opening=[[round(x, 2), round(y, 2)] for x, y in opening(eye)],
            lid_curve=[[round(x, 2), round(y, 2)] for x, y in lid_curve],
            close=round(H_UP + H_LO + 2, 1),
            iris=sprite(iris_rows), pupil=sprite(pupil_rows), lid=lid_spr))
    (ROOT / "assets" / "eyes.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print("\n".join(r.rstrip() for r in base_rows))
    print("-" * COLS)
    for r in lid_rows:
        if r.strip():
            print(r.rstrip())
    print("-" * COLS)
    e = out["eyes"][0]
    for a, b in zip(e["iris"]["rows"], e["pupil"]["rows"]):
        print(a, "|", b)


if __name__ == "__main__":
    main()
