#!/usr/bin/env python3
"""Paint one detailed eye (in the style of the profile avatar) and convert it to ASCII layers.

Writes assets/eye.json, which build_card.py animates. The eye is painted as a
full-tone greyscale picture: skin, brow hairs, lid crease, a heavy lash line,
wet lower rim, shaded eye white, a fibrous iris with a dark limbal ring, pupil
and window-shaped catchlights. It is converted twice, once per theme, so it
reads as a positive picture on both: on the dark card bright parts get dense
characters, on the light card dark parts do.

Layers, so the parts can move independently:
  base    everything except the iris (static)
  iris    iris texture, slides behind the eye opening
  pupil   dark disc that dilates and narrows
  glint   catchlights, which move less than the iris
  band    the upper lid from the crease down to the lash line, stretched over
          the eye to blink and squint

Characters are picked by matching each cell against the glyph shapes of a
monospace font. Needs Pillow and numpy; run it by hand, not in the workflow.

usage: make_eye.py [FONT.ttf]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = sys.argv[1] if len(sys.argv) > 1 else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

COLS, ROWS = 152, 68              # character grid of the art column (a ~4.9px font)
ART_W = 444.0                     # px; keeps the card 1032px wide
CELL_W = ART_W / COLS
CELL_H = CELL_W * 2
ART_H = ROWS * CELL_H
GW, GH = 12, 24                   # raster size of one cell (supersampled)
S = GW / CELL_W                   # raster px per art px
GLYPHS = " .`',:;\"-_~^!|/\\()[]{}<>?=+*rcszvunxoaeLJTYVli17IkhbdpqXZOQ08&%#$BMW@"

# geometry, in art px; u runs from -1 (inner corner, left) to 1 (outer corner, right)
CX, CY, A = 222.0, 236.0, 170.0
H_UP, H_LO = 64.0, 42.0
IRIS = (CX + 6.0, CY - 8.0)
R_IRIS, R_PUPIL = 57.0, 19.0


def corner(u):
    return 4 - 6 * u                                   # inner corner sits a little lower


def lash_y(u):
    return CY + corner(u) - H_UP * max(1 - u * u, 0) ** 0.62 * (1 - 0.16 * u)


def low_y(u):
    return CY + corner(u) + H_LO * max(1 - u * u, 0) ** 0.85 * (1 + 0.3 * u)


def crease_y(u):
    return lash_y(min(u, 1)) - 20 - 12 * max(1 - u * u, 0) ** 0.8 - 30 * max(u - 1, 0)


def X(u):
    return CX + u * A


def curve(f, a=-1.0, b=1.0, n=80):
    return [(X(u), f(u)) for u in np.linspace(a, b, n)]


def opening():
    return curve(lash_y) + curve(low_y)[::-1]


# ---------------------------------------------------------------- painting

class Paint:
    """Luminance canvas (0 black .. 1 white) in art px coordinates."""

    def __init__(self, value=1.0):
        self.w, self.h = COLS * GW, ROWS * GH
        self.L = np.full((self.h, self.w), value, dtype=np.float32)
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        self.x, self.y = (xx + 0.5) / S, (yy + 0.5) / S

    def mask(self, fn, blur=0.0):
        im = Image.new("L", (self.w, self.h), 0)
        fn(ImageDraw.Draw(im))
        if blur:
            im = im.filter(ImageFilter.GaussianBlur(blur * S))
        return np.asarray(im, dtype=np.float32) / 255

    def put(self, mask, value, alpha=1.0):
        a = np.clip(mask * alpha, 0, 1)
        self.L = self.L * (1 - a) + np.asarray(value, dtype=np.float32) * a

    def stroke(self, pts, width, value, alpha=1.0, blur=0.0):
        pts = [(x * S, y * S) for x, y in pts]
        m = self.mask(lambda d: d.line(pts, fill=255, width=max(1, round(width * S)), joint="curve"), blur)
        self.put(m, value, alpha)

    def taper(self, pts, w0, w1, value, alpha=1.0):
        def draw(d):
            n = len(pts) - 1
            for k in range(n):
                w = (w0 + (w1 - w0) * k / max(n - 1, 1)) * S
                (x0, y0), (x1, y1) = pts[k], pts[k + 1]
                d.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=255, width=max(1, round(w)))
                d.ellipse((x1 * S - w / 2, y1 * S - w / 2, x1 * S + w / 2, y1 * S + w / 2), fill=255)
        self.put(self.mask(draw, 0.15), value, alpha)

    def poly(self, pts, blur=0.0):
        return self.mask(lambda d: d.polygon([(x * S, y * S) for x, y in pts], fill=255), blur)


def bezier(p0, p1, p2, n=12):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in np.linspace(0, 1, n)]


def smooth(a, b, x):
    s = np.clip((x - a) / (b - a), 0, 1)
    return s * s * (3 - 2 * s)


def paint_base(rng):
    p = Paint(0.66)
    x, y = p.x, p.y
    # skin: fine grain, brow-bone highlight, shadow under the brow, soft socket shading
    grain = rng.normal(0, 1, (p.h // 6 + 1, p.w // 6 + 1)).astype(np.float32)
    grain = np.asarray(Image.fromarray(grain).resize((p.w, p.h), Image.BICUBIC))
    p.L += 0.012 * grain
    big = np.asarray(Image.fromarray(rng.normal(0, 1, (8, 8)).astype(np.float32)).resize((p.w, p.h), Image.BICUBIC))
    p.L += 0.03 * big
    u = np.clip((x - CX) / A, -1.3, 1.3)
    brow_line = 92 - 30 * np.sin(np.clip((x - 30) / 410, 0, 1) * math.pi) ** 1.1 + 0.05 * (x - 30)
    p.L += 0.10 * np.exp(-((y - (brow_line + 52)) / 22) ** 2)                    # brow bone catches light
    p.L -= 0.16 * np.exp(-((y - (brow_line + 18)) / 10) ** 2)                    # shadow under the brow
    socket = ((x - CX) / (A * 1.12)) ** 2 + ((y - CY) / 112) ** 2
    p.L -= 0.12 * np.exp(-socket * 1.6)                                        # eye socket
    p.L -= 0.10 * np.exp(-((y - (CY + 70 + 10 * u)) / 14) ** 2) * smooth(1.3, 0.9, np.abs(u))  # under-eye fold

    # brow: thousands of fine hairs, dense and upright at the inner end, flat and thin at the tail
    def brow_draw(d):
        for _ in range(4200):
            t = rng.beta(1.2, 1.5)
            bx = 30 + 405 * t
            mid = 96 - 26 * math.sin(t * math.pi) ** 1.1 + 0.06 * (bx - 30)
            thick = 34 * (1 - 0.78 * t)
            by = mid + rng.normal(0, thick / 3.4)
            ang = math.radians(-55 + 45 * t + rng.normal(0, 9))
            ln = rng.uniform(7, 15) * (1 - 0.3 * t)
            d.line([(bx * S, by * S), ((bx + math.cos(ang) * ln) * S, (by + math.sin(ang) * ln) * S)],
                   fill=int(rng.uniform(170, 255)), width=max(1, round(rng.uniform(0.6, 1.2) * S)))
    hair = p.mask(brow_draw, 0.25)
    p.put(hair, 0.1, 0.95)

    # upper lid: a soft shadow tucked under the fold, light across the lid, then the crease line
    cr = np.interp(x, *zip(*curve(crease_y, -1.2, 1.3)))
    la = np.interp(x, *zip(*curve(lash_y, -1, 1)))
    on_lid = smooth(-1.25, -1.0, u) * smooth(1.3, 1.1, u)
    p.L -= 0.16 * np.exp(-((y - cr + 4) / 7) ** 2) * on_lid                    # overhang shadow
    p.L += 0.08 * np.exp(-((y - (cr + la) / 2) / 8) ** 2) * on_lid * (np.abs(u) < 1)  # lit lid
    p.stroke(curve(crease_y, -0.95, 1.13), 1.8, 0.25, 0.8, 1.0)                  # the crease

    # eye white: rounded shading, shadow cast by the lid, darker corners, a few faint veins
    op = p.poly(opening(), 0.4)
    top = np.interp(x, *zip(*curve(lash_y)))
    ball = ((x - IRIS[0]) / (A * 1.05)) ** 2 + ((y - IRIS[1]) / 95) ** 2
    white = 0.93 - 0.18 * ball - 0.5 * np.exp(-np.clip(y - top, 0, None) / 11) - 0.25 * smooth(0.6, 1.0, np.abs(u))
    p.put(op, np.clip(white, 0, 1))
    for k in range(7):
        side = -1 if k < 4 else 1
        x0 = X(side * 0.93)
        pts = [(x0, CY + rng.uniform(-10, 10))]
        for _ in range(5):
            px, py = pts[-1]
            pts.append((px - side * rng.uniform(6, 11), py + rng.uniform(-4, 4)))
        p.stroke(pts, 0.7, 0.55, 0.45 * op.max())
    # tear duct
    cx0, cy0 = X(-0.93), CY + corner(-0.93) + 2
    p.put(p.mask(lambda d: d.ellipse(((cx0 - 9) * S, (cy0 - 7) * S, (cx0 + 9) * S, (cy0 + 7) * S), fill=255), 1.0), 0.5)
    p.put(p.mask(lambda d: d.ellipse(((cx0 - 3) * S, (cy0 - 4) * S, (cx0 + 1) * S, (cy0 - 1) * S), fill=255), 0.4), 1.0)

    # lower lid: wet rim catching light, then a thin lash line and sparse short lashes
    p.stroke([(x0, y0 - 1.5) for x0, y0 in curve(low_y, -0.9, 0.97)], 2.0, 0.97, 0.9, 0.5)
    p.stroke([(x0, y0 + 2.5) for x0, y0 in curve(low_y, -0.85, 1.0)], 1.6, 0.25, 0.85, 0.4)
    for u0 in np.sort(rng.uniform(-0.6, 0.98, 30)):
        bx, by = X(u0), low_y(u0) + 3
        ang = math.radians(90 - 45 * (u0 + 0.6) / 1.6 + rng.normal(0, 6))
        ln = rng.uniform(4, 10) * (0.6 + 0.6 * (u0 + 0.6) / 1.6)
        p.taper([(bx, by), (bx + math.cos(ang) * ln, by + math.sin(ang) * ln)], 1.0, 0.3, 0.2, 0.8)

    # upper lash line: a heavy dark band, thickest in the middle, with a flick past the outer corner
    def band(d):
        us = np.linspace(-1, 1.1, 120)
        for k in range(len(us) - 1):
            ua, ub = us[k], us[k + 1]
            w = (3 + 5 * max(1 - (ua - 0.25) ** 2, 0)) * S
            ya = lash_y(min(ua, 1)) - 26 * max(ua - 1, 0) * 2.2
            yb = lash_y(min(ub, 1)) - 26 * max(ub - 1, 0) * 2.2
            d.line([(X(ua) * S, ya * S), (X(ub) * S, yb * S)], fill=255, width=round(w))
    p.put(p.mask(band, 0.5), 0.04)
    # upper lashes: clumped, curling up and out, longest towards the outer corner
    for u0 in np.sort(rng.uniform(-0.9, 1.1, 150)):
        u1 = u0
        bx = X(u1)
        by = lash_y(min(u1, 1)) - 26 * max(u1 - 1, 0) * 2.2 - 1
        t = min(max((u0 + 0.9) / 2.0, 0.0), 1.0)
        ln = (7 + 22 * t ** 1.5) * rng.uniform(0.55, 1.15)
        ang = math.radians(-100 + 75 * t + rng.normal(0, 5))
        p2 = (bx + math.cos(ang) * ln + 6 * t, by + math.sin(ang) * ln + 4 * t)
        p1 = (bx + math.cos(ang) * ln * 0.45, by + math.sin(ang) * ln * 0.6 - 3)
        p.taper(bezier((bx, by), p1, p2), rng.uniform(1.0, 1.7), 0.3, 0.05, 0.95)

    # a beauty mark just below and outside the outer corner
    mx, my, mr = X(1.0) + 2, CY + corner(1.0) + 22, 6.5
    p.put(p.mask(lambda d: d.ellipse(((mx - mr) * S, (my - mr * 0.85) * S, (mx + mr) * S, (my + mr * 0.85) * S),
                                     fill=255), 0.4), 0.0)
    return p


def paint_iris(rng):
    """Iris texture centred on IRIS, transparent outside the disc (returned as luminance + mask)."""
    p = Paint(0.0)
    dx, dy = p.x - IRIS[0], p.y - IRIS[1]
    r, th = np.hypot(dx, dy), np.arctan2(dy, dx)
    rr = np.clip(r / R_IRIS, 0, 1)
    ph = rng.uniform(0, 6.28, 8)
    fib = sum(np.sin(k * th + ph[i] + 0.8 * np.sin(3 * th + i)) for i, k in enumerate((19, 27, 34, 41, 53, 67, 79, 97))) / 8
    L = 0.4 + 0.14 * fib * (0.3 + rr)
    L += 0.16 * smooth(0.0, 1.0, dy / R_IRIS) * (rr < 0.85)                  # lit from below, like the avatar
    L += 0.18 * np.exp(-((rr - 0.42) / 0.07) ** 2)                            # collarette
    L -= 0.32 * smooth(0.82, 1.0, rr)                                         # dark limbal ring
    L -= 0.12 * smooth(0.2, -0.9, dy / R_IRIS)                                # lid shadow on the top
    crypt = np.asarray(Image.fromarray(rng.normal(0, 1, (40, 40)).astype(np.float32)).resize((p.w, p.h), Image.BICUBIC))
    L -= 0.08 * np.clip(crypt, 0, None) * (rr > 0.45)
    m = smooth(R_IRIS + 0.6, R_IRIS - 0.6, r)
    return np.clip(L, 0, 1), m


def glint_shapes():
    """Catchlights relative to the iris centre: a slanted window and a small dot."""
    window = [(-31, -36), (-15, -40), (-12, -27), (-28, -23)]
    dot = (19, 15, 3.6)
    return window, dot


# ---------------------------------------------------------------- ASCII

def glyph_bank():
    font = ImageFont.truetype(FONT, 20)
    asc, desc = font.getmetrics()
    bank = []
    for ch in GLYPHS:
        im = Image.new("L", (GW, GH), 0)
        ImageDraw.Draw(im).text((0, (GH - asc - desc) / 2), ch, font=font, fill=255)
        bank.append(np.asarray(im.filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32) / 255)
    return np.stack(bank), asc / (asc + desc)


def to_ascii(density, bank, tone=5.0):
    """Pick per cell the glyph whose coverage matches the cell's tone and whose shape
    matches its strokes; `tone` weighs the first against the second."""
    img = Image.fromarray((np.clip(density, 0, 1) * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.7))
    a = np.asarray(img, dtype=np.float32) / 255
    a = a.reshape(ROWS, GH, COLS, GW).transpose(0, 2, 1, 3).reshape(ROWS * COLS, GH * GW)
    g = bank.reshape(len(GLYPHS), GH * GW)
    gm = g.mean(1)
    t = a * gm.max()                               # full ink maps to the densest glyph
    tm = t.mean(1)
    tc, gc = t - tm[:, None], g - gm[:, None]      # shape, with tone removed
    shape = (tc ** 2).sum(1)[:, None] - 2 * tc @ gc.T + (gc ** 2).sum(1)[None, :]
    err = shape + tone * GH * GW * (tm[:, None] - gm[None, :]) ** 2
    best = err.argmin(1).reshape(ROWS, COLS)
    return ["".join(GLYPHS[k] for k in row) for row in best]


def density(L, fade):
    """Ink: dark parts of the picture get dense glyphs, on both cards (like a pen drawing,
    which on the dark card reads as chalk). The curve keeps the skin light and airy."""
    return np.clip((0.82 - np.clip(L, 0, 1)) / 0.78, 0, 1) ** 1.25 * fade


def sprite(rows, keep=None):
    """Crop to the cells in use: (col, row, rows). `keep(col, row)` can drop cells."""
    if keep:
        rows = ["".join(ch if keep(c, r) else " " for c, ch in enumerate(row)) for r, row in enumerate(rows)]
    used = [i for i, r in enumerate(rows) if r.strip()]
    if not used:
        return None
    c0 = min(len(r) - len(r.lstrip()) for r in rows if r.strip())
    return dict(col=c0, row=used[0], rows=[rows[i][c0:].rstrip() for i in range(used[0], used[-1] + 1)])


def inside(poly):
    m = Image.new("L", (COLS, ROWS), 0)
    ImageDraw.Draw(m).polygon([(x / CELL_W - 0.5, y / CELL_H - 0.5) for x, y in poly], fill=1)
    a = np.asarray(m)
    return lambda c, r: a[r, c] > 0


def main():
    bank, base_frac = glyph_bank()
    rng = np.random.default_rng(11)
    base = paint_base(rng)
    iris_L, iris_m = paint_iris(rng)
    pupil = Paint(0.0)
    pm = pupil.mask(lambda d: d.ellipse(((IRIS[0] - R_PUPIL) * S, (IRIS[1] - R_PUPIL) * S,
                                         (IRIS[0] + R_PUPIL) * S, (IRIS[1] + R_PUPIL) * S), fill=255), 0.3)
    window, (gx, gy, gr) = glint_shapes()
    glint = Paint(0.0)
    gm = glint.mask(lambda d: (d.polygon([((IRIS[0] + x) * S, (IRIS[1] + y) * S) for x, y in window], fill=255),
                               d.ellipse(((IRIS[0] + gx - gr) * S, (IRIS[1] + gy - gr) * S,
                                          (IRIS[0] + gx + gr) * S, (IRIS[1] + gy + gr) * S), fill=255)), 0.4)
    # fade the picture out towards the edges of the art column
    fx, fy = (base.x - ART_W / 2) / (ART_W / 2 + 6), (base.y - ART_H / 2) / (ART_H / 2 + 4)
    fade = np.clip((1 - (np.abs(fx) ** 2.6 + np.abs(fy) ** 2.6)) / 0.45, 0, 1) ** 0.9

    band_poly = curve(crease_y, -1.02, 1.16) + [(X(1.16), lash_y(1) - 26 * 0.16 * 2.2 + 6)] + \
        [(x, y + 5) for x, y in curve(lash_y, -1, 1)[::-1]]
    out = dict(cols=COLS, rows=ROWS, cell_w=CELL_W, cell_h=CELL_H, font_size=round(CELL_W / 0.6, 3),
               baseline=base_frac, iris_center=list(IRIS), r_iris=R_IRIS, r_pupil=R_PUPIL,
               glint_shape=dict(window=window, dot=[gx, gy, gr]),
               opening=[[round(x, 2), round(y, 2)] for x, y in opening()],
               band_poly=[[round(x, 2), round(y, 2)] for x, y in band_poly],
               lid_clip=[[round(x, 2), round(y, 2)] for x, y in
                         curve(crease_y, -1.05, 1.16) + [(X(1.16), low_y(1) + 4)] +
                         [(x, y + 4) for x, y in curve(low_y, -1, 1)[::-1]] + [(X(-1.05), low_y(-1) + 4)]],
               crease_top=float(min(crease_y(u) for u in np.linspace(-1, 1, 200))),
               lash_mid=float(lash_y(0.0)), low_mid=float(low_y(0.0)))
    in_band = inside(band_poly)
    # one set of layers serves both cards; the pupil is solid ink on the light card, while the
    # dark card leaves it empty (dark) and draws the catchlights in ink instead
    b = to_ascii(density(base.L, fade), bank)
    out.update(base=b, iris=sprite(to_ascii(density(iris_L, fade) * iris_m, bank)), band_text=sprite(b, in_band),
               pupil=sprite(to_ascii(fade * pm, bank)), glint=sprite(to_ascii(fade * gm, bank)))
    preview = b
    (ROOT / "assets" / "eye.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print("\n".join(r.rstrip() for r in preview))


if __name__ == "__main__":
    main()
