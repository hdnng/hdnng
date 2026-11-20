#!/usr/bin/env python3
"""Render ufo_dark.svg / ufo_light.svg: a UFO flies over the contribution calendar
and beams each week's contributions up into itself, then the grid respawns.

Every BATTLE_EVERY-th loop, just after our UFO finishes a week, a rival UFO
swoops in and steals a busy week further ahead. The two dogfight along smooth
curved paths: the rival dodges our first shot and fires back, we loop over its
shots, land two hits and a charged blast; it spins out and explodes, the stolen
squares fall back into place, our UFO does a victory roll, pops a GitHub star
and goes back to work.

Reads cache/calendar.json ({"total": int|null, "weeks": [[level|null] * 7, ...]},
levels 0-4, null for days outside the range), written by fetch_stats.py.
Pure CSS animation, so it plays inside a README image (no script, no hover).
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_card import THEMES  # noqa: E402  same palette as the profile card

W = 1032                      # same width as the profile card, so they stack cleanly
BAR, PAD = 40, 28
CELL, GAP = 12, 4
STEP = CELL + GAP
SKY = 40                      # extra headroom above the cruising altitude for the dogfight
UFO_DROP = 62                 # distance from the UFO's centre to the top of the grid
SPEED = 420                   # UFO cruising speed, px/s
LIFT0, STAGGER, RISE = 0.1, 0.045, 0.34   # first lift-off, gap between cells, flight time (s)
BEAM = LIFT0 + 6 * STAGGER + RISE + 0.1   # seconds spent abducting one week
RESPAWN = 1.4                 # seconds the empty grid takes to refill at the end of a loop
GLOAT = 1.8                   # seconds the UFO lingers after the last week, saying its final line
CHAT_MIN_CELLS = 6            # a week with at least this many cells earns a speech bubble
CHAT_GAP = 3.5                # minimum seconds between two bubbles
CHAT_TIME = 1.5               # seconds a bubble stays up
CHAT_LINES = ["haha!", "nom nom nom", "yummy commits", "more pls!", "so many squares", "delicious"]
FINAL_LINE = "haha, all mine! see you tomorrow"
CHAT_FS = 13                  # bubble font size (px)

BATTLE_EVERY = 2              # the rival raids every 2nd loop
MIN_GAP = 260                 # how far ahead of us the rival's target week must be
FPS = 25                      # sampling rate of the curved dogfight paths
BOLT, BLAST = 900, 1300       # laser and charged-blast speeds, px/s

LEVELS = {
    "dark": ["#16303a", "#1e6b6f", "#2a9d8f", "#4fc4b3", "#8ff0dc"],
    "light": ["#e3ebf0", "#b6e3dc", "#6cc7b9", "#2a9d8f", "#0a7d6c"],
}
UFO = {
    "dark": dict(hull="#7f9aa5", rim="#c4d6dc", dome="#9fd8e6", glow="#7ee0c8", beam="#7ee0c8"),
    "light": dict(hull="#4f6b76", rim="#8ea9b3", dome="#5bb6c9", glow="#0a7d6c", beam="#2a9d8f"),
}
FOE = dict(hull="#8b2f3c", rim="#d9707a", dome="#f0a6b4", glow="#ff5f56", beam="#ff5f56")
LIGHTS = ["#ffbd2e", "#ff5f56", "#27c93f", "#58a6ff"]
FOE_LIGHTS = ["#ff5f56", "#ffbd2e", "#ff5f56", "#ffbd2e"]
SKIN, FOE_SKIN, FACE = "#8be38b", "#c38bf0", "#10302a"
STAR, SPARK = "#f5c518", "#ffbd2e"


# ---------------------------------------------------------------- drawing helpers

def alien(x, y, size, mood="laugh", skin=SKIN):
    """A little alien head centred on (x, y), `size` px tall, laughing or angry."""
    k = size / 14
    if mood == "laugh":   # squinting ^ ^ eyes, open mouth
        face = (f'<path d="M-4.6 -0.6q1.9 -1.9 3.4 0.3M4.6 -0.6q-1.9 -1.9 -3.4 0.3" stroke="{FACE}" '
                f'stroke-width="1.5" fill="none" stroke-linecap="round"/>'
                f'<path d="M-2.4 2.4q2.4 2.6 4.8 0z" fill="{FACE}"/>')
    else:                 # slanted eyes, frown
        face = (f'<path d="M-5 -1.6L-1.2 0.2L-4.4 1.2zM5 -1.6L1.2 0.2L4.4 1.2z" fill="{FACE}"/>'
                f'<path d="M-2.2 4.2q2.2 -1.8 4.4 0" stroke="{FACE}" stroke-width="1.3" fill="none" stroke-linecap="round"/>')
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({k:.3f})">'
            f'<path d="M0 -7C6 -7 7.2 -1.5 5 3C3.2 6.2 1.2 7 0 7C-1.2 7 -3.2 6.2 -5 3C-7.2 -1.5 -6 -7 0 -7z" '
            f'fill="{skin}"/>{face}</g>')


def saucer(tid, ufo_y, u, lights, pilot, extra=""):
    """Saucer drawn around (0, ufo_y) at 1.4x inside a tilt group `tid`, pilot under the glass."""
    out = [f'<g id="{tid}"><g transform="translate(0 {ufo_y}) scale(1.4) translate(0 {-ufo_y})">',
           f'<ellipse cx="0" cy="{ufo_y + 5}" rx="10" ry="2.6" fill="{u["glow"]}" opacity=".75"/>',
           pilot,
           f'<path d="M-10 {ufo_y - 2}a10 10 0 0 1 20 0z" fill="{u["dome"]}" opacity=".45"/>',
           f'<path d="M-5 {ufo_y - 6}a6 6 0 0 1 5 -4" stroke="#fff" stroke-opacity=".7" stroke-width="1.5" '
           f'fill="none" stroke-linecap="round"/>',
           f'<ellipse cx="0" cy="{ufo_y + 1}" rx="23" ry="6.5" fill="{u["hull"]}"/>',
           f'<ellipse cx="0" cy="{ufo_y - 1}" rx="21" ry="3" fill="{u["rim"]}"/>']
    for k, col in enumerate(lights):
        out.append(f'<circle class="lt" style="animation-delay:-{k * 0.22:.2f}s" cx="{-13.5 + k * 9}" '
                   f'cy="{ufo_y + 2.5}" r="1.7" fill="{col}"/>')
    out.append(extra + "</g></g>")
    return "".join(out)


def bubble_size(line):
    return len(line) * CHAT_FS * 0.6 + 40, CHAT_FS + 14


def bubble(bid, line, right, ufo_y, c, mood="laugh", skin=SKIN):
    """Speech bubble beside a UFO at (0, ufo_y); `right` puts it on the UFO's right."""
    bw, bh = bubble_size(line)
    x0 = 22 if right else -22 - bw
    y0 = ufo_y - 22 - bh
    tail = (f"M{x0 + 10} {y0 + bh - 0.5}L6 {ufo_y - 12}L{x0 + 24} {y0 + bh - 0.5}" if right else
            f"M{x0 + bw - 10} {y0 + bh - 0.5}L-6 {ufo_y - 12}L{x0 + bw - 24} {y0 + bh - 0.5}")
    return (f'<g id="{bid}"><path d="{tail}" fill="{c["bar"]}" stroke="{c["value"]}"/>'
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{bh}" rx="7" fill="{c["bar"]}" stroke="{c["value"]}"/>'
            f'<path d="M{x0 + 8 if right else x0 + bw - 26} {y0 + bh}h18" stroke="{c["bar"]}" stroke-width="2"/>'
            + alien(x0 + 16, y0 + bh / 2, 16, mood, skin) +
            f'<text x="{x0 + 30:.1f}" y="{y0 + bh / 2 + CHAT_FS * 0.36:.1f}" font-size="{CHAT_FS}" class="v">{line}</text></g>')


class Anim:
    """Collects one CSS animation per element, all sharing the master cycle M."""

    def __init__(self, M):
        self.M, self.css = M, []

    def pct(self, t):
        return f"{min(max(t / self.M * 100, 0), 100):.3f}%"

    def add(self, sel, name, points, base="", timing="linear"):
        """`points` are (seconds, declarations); the first and last are held to 0% and 100%,
        so effects that should start hidden must say so in their first point."""
        pts = sorted(points, key=lambda p: p[0])
        if pts[0][0] > 0:
            pts.insert(0, (0, pts[0][1]))
        if pts[-1][0] < self.M:
            pts.append((self.M, pts[-1][1]))
        frames = {}
        for t, decl in pts:         # a later point at the same instant wins
            frames[self.pct(t)] = decl
        body = "".join(f"{p}{{{d}}}" for p, d in frames.items())
        self.css.append(f"{sel}{{{base}animation:{name} {self.M:.2f}s {timing} infinite}}"
                        f"@keyframes {name}{{{body}}}")


# ---------------------------------------------------------------- motion

class Path:
    """Smooth path through timed waypoints (t, x, y[, vx, vy]) using cubic Hermite curves.
    Repeated points are holds; `special` maps (t0, t1) to a function overriding the curve."""

    def __init__(self, wps, special=None):
        self.w = wps
        self.special = special or {}
        n = len(wps)
        self.m = []
        for i, p in enumerate(wps):
            if len(p) == 5:
                self.m.append((p[3], p[4]))
            elif i in (0, n - 1) or p[1:3] == wps[i - 1][1:3] or p[1:3] == wps[i + 1][1:3]:
                self.m.append((0.0, 0.0))
            else:
                a, b = wps[i - 1], wps[i + 1]
                dt = b[0] - a[0]
                self.m.append(((b[1] - a[1]) / dt, (b[2] - a[2]) / dt))

    def __call__(self, t):
        for (t0, t1), f in self.special.items():
            if t0 <= t <= t1:
                return f(t)
        w = self.w
        if t <= w[0][0]:
            return w[0][1], w[0][2]
        if t >= w[-1][0]:
            return w[-1][1], w[-1][2]
        i = max(k for k in range(len(w) - 1) if w[k][0] <= t)
        (ta, xa, ya, *_), (tb, xb, yb, *_) = w[i], w[i + 1]
        h, s = tb - ta, (t - ta) / (tb - ta)
        h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
        (ma, na), (mb, nb) = self.m[i], self.m[i + 1]
        return (h00 * xa + h10 * h * ma + h01 * xb + h11 * h * mb,
                h00 * ya + h10 * h * na + h01 * yb + h11 * h * nb)


def smooth(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * (3 - 2 * s)


def loop_the_loop(t0, t1, cx, cy, r, drift):
    """Vertical loop: starts at the bottom of the circle heading right, ends `drift` px further."""
    def f(t):
        s = (t - t0) / (t1 - t0)
        th = 2 * math.pi * s
        return cx + r * math.sin(th) + drift * s, cy + r * math.cos(th)
    v = 2 * math.pi * r / (t1 - t0) + drift / (t1 - t0)
    return f, (t0, cx, cy + r, v, 0.0), (t1, cx + drift, cy + r, v, 0.0)


# ---------------------------------------------------------------- planning

def plan_run(weeks, grid_x):
    """One abduction run: stops (week, x, arrive, leave), bubbles, exit time, length."""
    stops, t, x = [], 0.0, -60.0
    for i, week in enumerate(weeks):
        if not any(week):
            continue
        cx = grid_x + i * STEP + CELL / 2
        t += abs(cx - x) / SPEED
        stops.append((i, cx, t, t + BEAM))
        t, x = t + BEAM, cx
    t_exit = t + (GLOAT if stops else 0) + abs(W + 60 - x) / SPEED
    chats, last = [], -CHAT_GAP
    for n, (i, cx, a, l) in enumerate(stops):
        if n == len(stops) - 1:
            line, reach, s0, e0 = FINAL_LINE, cx, l + 0.1, l + GLOAT + 0.5
        elif (sum(1 for v in weeks[i] if v) >= CHAT_MIN_CELLS and l - last >= CHAT_GAP
              and l + CHAT_TIME + 0.3 <= stops[-1][3]):  # keep clear of the final line
            line, reach, s0, e0 = CHAT_LINES[len(chats) % len(CHAT_LINES)], max(cx, stops[n + 1][1]), l, l + CHAT_TIME
            last = l
        else:
            continue
        right = reach + 22 + bubble_size(line)[0] < W - 12   # flip to the left near the right edge
        chats.append((line, right, s0, e0))
    return stops, chats, t_exit, t_exit + RESPAWN


def plan_battle(weeks, stops, grid_x):
    """Pick the stolen week and the stop after which the raid starts; script the dogfight.

    Times are seconds from the start of the raid, positions are (x, y) with y relative
    to cruising altitude (negative is up)."""
    lo = 400                                                   # room for our bubbles on the left
    hi = W - 12 - 22 - bubble_size("yoink! mine now")[0] - 10   # and the rival's on the right
    picks = []
    for i, w in enumerate(weeks):
        x = grid_x + i * STEP + CELL / 2
        before = [n for n, s in enumerate(stops) if s[1] <= x - MIN_GAP]
        if any(w) and lo <= x <= hi and before:
            picks.append((sum(1 for v in w if v), sum(v or 0 for v in w), i, before[-1]))
    if not picks:
        return None
    _, _, j, k = max(picks)
    X = grid_x + j * STEP + CELL / 2
    xk = stops[k][1]

    # the rival: swoop in, steal, rise, dive under our first shot, fire twice, flee in a wave,
    # take two hits and a charged blast, then spin out
    foe = Path([(0.0, W + 60, -70), (0.7, X + 110, -55), (1.15, X + 25, -14), (1.35, X, 0), (2.16, X, 0),
                (2.55, X + 35, -24), (3.0, X + 12, -36), (3.2, X + 30, -8), (3.42, X + 8, 18), (3.68, X - 28, 4),
                (3.95, X - 30, -22), (4.25, X - 12, -32), (4.6, X - 4, -30), (4.95, X + 22, -12),
                (5.25, X + 55, -8), (5.55, X + 70, -30), (5.9, X + 42, -46), (6.2, X + 10, -30),
                (6.45, X + 18, -12), (6.6, X + 30, -14), (6.8, X + 50, -2), (6.98, X + 36, 12), (7.15, X + 48, 8)])
    # us: wait, rush over, fire, drop back, loop the loop over its shots, chase, charge, blast,
    # victory roll in place, then fly back to where we left off
    f_loop, l0, l1 = loop_the_loop(4.15, 4.9, X - 175, -24, 24, 40)
    hold = (X - 120, -18)
    back = max(0.9, abs(hold[0] - xk) / 430)
    end = 7.95 + back
    us = Path([(0.0, xk, 0), (1.9, xk, 0), (2.55, xk + (X - 170 - xk) * 0.65, -30), (3.05, X - 170, -18),
               (3.6, X - 188, -8), l0, l1, (5.2, X - 125, -14), (5.6, X - 104, -28), (6.0, X - 112, -16),
               (6.4, X - 112, -16), (6.62, hold[0], hold[1]), (7.35, *hold), (7.95, *hold), (end, xk, 0)],
              {(l0[0], l1[0]): f_loop})
    return dict(week=j, stop=k, X=X, xk=xk, foe=foe, us=us, length=end + 0.05,
                steal=1.35, steal_end=2.16, boom=7.15, roll=(7.35, 7.95), loop=(l0[0], l1[0]),
                spin=(6.6, 7.15), charge=(6.0, 6.4), star=7.45,
                bubbles=[("us", "hey! give them back!", "angry", 2.2, 3.6),
                         ("foe", "yoink! mine now", "angry", 1.45, 2.95),
                         ("foe", "missed me!", "laugh", 3.75, 4.9),
                         ("us", "eat this!", "angry", 5.95, 6.55),
                         ("foe", "nooo!", "angry", 6.65, 7.12),
                         ("us", "GG ez!", "laugh", 7.5, 8.8)],
                # (shooter, kind, time): "hit" times are impact times, "miss" times are firing times
                shots=[("us", "miss", 3.05), ("foe", "miss", 4.33), ("foe", "miss", 4.65),
                       ("us", "hit", 5.3), ("us", "hit", 5.85), ("us", "blast", 6.6)])


# ---------------------------------------------------------------- render

def render(theme, cal):
    c, lv, u = THEMES[theme], LEVELS[theme], UFO[theme]
    weeks = cal["weeks"]
    grid_w = len(weeks) * STEP - GAP
    grid_x = (W - grid_w) / 2
    prompt_y = BAR + PAD + 12
    grid_y = prompt_y + 30 + SKY + UFO_DROP + 26
    ufo_y = grid_y - UFO_DROP
    grid_h = 7 * STEP - GAP
    foot_y = grid_y + grid_h + 40
    H = round(foot_y + PAD)

    stops, chats, t_exit, T = plan_run(weeks, grid_x)
    T = max(T, 4.0)
    bt = plan_battle(weeks, stops, grid_x) if stops else None
    B = bt["length"] if bt else 0
    loops = BATTLE_EVERY if bt else 1
    M = loops * T + B
    runs = [j * T for j in range(loops)]
    if bt:
        ob = runs[-1]                                   # the battle loop
        t0 = ob + stops[bt["stop"]][3]                  # raid starts as we finish that week
    an = Anim(M)
    ms = lambda x, y=0: f"transform:translate({x:.1f}px,{y:.1f}px)"
    lin = ";animation-timing-function:linear"

    def at(o, t):
        """Time `t` of the run starting at `o`, pushed back by the raid in the battle loop."""
        return o + t + (B if bt and o == ob and o + t > t0 + 1e-9 else 0)

    css = [
        f"text{{white-space:pre}}.p{{fill:{c['add']}}}.k{{fill:{c['key']}}}.t{{fill:{c['text']}}}"
        f".d{{fill:{c['dots']}}}.v{{fill:{c['value']}}}",
        f".cur{{fill:{c['value']};animation:blink 1.1s steps(1) infinite}}@keyframes blink{{50%{{opacity:0}}}}",
        ".bob{animation:bob 1.6s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-3px)}}",
        ".lt{animation:lt 0.9s steps(1) infinite}@keyframes lt{50%{opacity:.25}}",
        ".fx{opacity:0}",
    ]
    grow = "transform-box:fill-box;transform-origin:center;"
    fx, bubbles, foe_bubbles = [], [], []

    def pop(windows):
        pts = [(0, "opacity:0;transform:scale(.2)")]
        for s0, e0 in windows:
            pts += [(s0 - 0.01, "opacity:0;transform:scale(.2)"), (s0 + 0.18, "opacity:1;transform:scale(1.08)"),
                    (s0 + 0.28, "opacity:1;transform:scale(1)"), (e0 - 0.2, "opacity:1;transform:scale(1)"),
                    (e0, "opacity:0;transform:scale(1)"), (e0 + 0.01, "opacity:0;transform:scale(.2)")]
        return pts

    # --- our UFO along each run, with the dogfight spliced into the battle loop
    pts, tilt = [], [(0, "transform:none")]
    for o in runs:
        pts.append((at(o, 0), ms(-60)))
        for n, (_, cx, a, l) in enumerate(stops):
            hold = l + (GLOAT if n == len(stops) - 1 else 0)
            pts += [(at(o, a), ms(cx)), (at(o, hold), ms(cx))]
        pts += [(at(o, t_exit), ms(W + 60)), (at(o, T) - 0.01, ms(W + 60))]

    def ufo_frames(path, t_start, length, spins):
        """Dense keyframes along `path`, with banking from the horizontal speed plus extra spins."""
        move, turn, prev = [], [], 0.0
        n = int(length * FPS)
        for s in range(n + 1):
            t = s / FPS if s < n else length
            x, y = path(t)
            x2, _ = path(min(t + 0.04, length))
            x1, _ = path(max(t - 0.04, 0))
            bank = max(-16.0, min(16.0, (x2 - x1) / 0.08 * 0.03))
            extra = sum(deg * smooth((t - a) / (b - a)) for (a, b), deg in spins)
            ang = bank + extra
            ang += 360 * round((prev - ang) / 360)    # keep the angle continuous
            prev = ang
            move.append((t_start + t, ms(x, y) + lin))
            turn.append((t_start + t, f"transform:translate(0px,{ufo_y}px) rotate({ang:.1f}deg) "
                                      f"translate(0px,{-ufo_y}px){lin}"))
        return move, turn

    if bt:
        move, turn = ufo_frames(bt["us"], t0, B, [(bt["loop"], -360), (bt["roll"], 360)])
        pts += move
        tilt += [(t0 - 0.01, "transform:none")] + turn + [(t0 + B + 0.01, "transform:none")]
    an.add("#ufo", "ufo", pts, timing="ease-in-out")
    an.add("#tilt", "tilt", tilt)

    pts = [(0, "opacity:0")]
    for o in runs:
        for _, _, a, l in stops:
            pts += [(at(o, a), "opacity:0"), (at(o, a) + 0.08, "opacity:.9"), (at(o, l) - 0.1, "opacity:.9"),
                    (at(o, l), "opacity:0")]
    an.add("#beam", "beam", pts)

    for k, (line, right, s0, e0) in enumerate(chats):
        bubbles.append(bubble(f"b{k}", line, right, ufo_y, c))
        an.add(f"#b{k}", f"b{k}", pop([(at(o, s0), at(o, s0) + e0 - s0) for o in runs]),
               base=f"opacity:0;transform-box:fill-box;transform-origin:{'0% 100%' if right else '100% 100%'};")

    # --- the grid: cells ride the beam one by one (top first) and refill at the end of each run
    lift = "transform:none;opacity:1;animation-timing-function:cubic-bezier(.5,0,.9,.6)"
    shown = "transform:none;opacity:1"
    cells_css, when = [], {i: a for i, _, a, _ in stops}
    for i, week in enumerate(weeks):
        lifted = [r for r, v in enumerate(week) if v]
        for n, r in enumerate(lifted):
            cx, cy = grid_x + i * STEP + CELL / 2, grid_y + r * STEP + CELL / 2
            gone = f"transform:translateY({ufo_y + 5 - cy:.1f}px) rotate(200deg) scale(.25)"
            pts = [(0, shown)]
            for o in runs:
                s0 = at(o, when[i] + LIFT0 + n * STAGGER)
                rs = at(o, t_exit + 0.2)
                pts += [(s0, lift), (s0 + RISE, gone + ";opacity:0"), (rs, gone + ";opacity:0"),
                        (rs + 0.01, "transform:none;opacity:0"), (at(o, T) - 0.02, shown)]
            if bt and i == bt["week"]:
                s0 = t0 + bt["steal"] + LIFT0 + n * STAGGER
                bx, by = bt["foe"](bt["boom"])
                back = t0 + bt["boom"] + 0.12 + n * 0.06
                fall = f"transform:translate({bx - cx:.1f}px,{ufo_y + by - cy:.1f}px) rotate(200deg) scale(.25)"
                pts += [(s0, lift), (s0 + RISE, gone + ";opacity:0"), (back - 0.01, fall + ";opacity:0"),
                        (back, fall + ";opacity:1;animation-timing-function:cubic-bezier(.3,0,.7,1)"),
                        (back + 0.55, shown)]
            sub = Anim(M)
            sub.add(f"#c{i}_{r}", f"c{i}_{r}", pts, base="transform-box:fill-box;transform-origin:center;")
            cells_css += sub.css

    # --- the rival and the fight
    foe_parts = []
    if bt:
        boom = t0 + bt["boom"]
        move, turn = ufo_frames(bt["foe"], t0, bt["boom"] + 0.02, [(bt["spin"], 540)])
        # shudder when hit
        hits = [t for who, kind, t in bt["shots"] if who == "us" and kind != "miss"]
        for idx, (t, decl) in enumerate(move):
            for h in hits:
                d = t - (t0 + h)
                if 0 <= d <= 0.2:
                    x, y = bt["foe"](t - t0)
                    jig = 6 * math.sin(d * 70) * (1 - d / 0.2)
                    move[idx] = (t, ms(x + jig, y - jig / 2) + lin)
        an.add("#foe", "foe", [(t0 - 0.01, ms(W + 60, -70))] + move + [(boom + 0.3, ms(W + 60, -70))],
               base=f"{ms(W + 60, -70)};")
        an.add("#ftilt", "ftilt", [(t0 - 0.01, "transform:none")] + turn + [(boom + 0.3, "transform:none")])
        an.add("#foebody", "foebody", [(0, "opacity:1"), (boom, "opacity:1"), (boom + 0.01, "opacity:0"),
                                       (boom + 0.32, "opacity:0"), (boom + 0.33, "opacity:1")])
        a, l = t0 + bt["steal"], t0 + bt["steal_end"]
        an.add("#fbeam", "fbeam", [(a, "opacity:0"), (a + 0.08, "opacity:.9"), (l - 0.1, "opacity:.9"), (l, "opacity:0")])
        pts = [(0, "opacity:0")]
        for h in hits:
            pts += [(t0 + h, "opacity:0"), (t0 + h + 0.01, "opacity:.6"), (t0 + h + 0.15, "opacity:0")]
        an.add("#fhit", "fhit", pts, base="opacity:0;")

        # bubbles: each side picks the side of its UFO where the text fits
        for k, (who, line, mood, s0, e0) in enumerate(bt["bubbles"]):
            path = bt[who]
            xs = [path(s0 + (e0 - s0) * q / 10)[0] for q in range(11)]
            bw = bubble_size(line)[0]
            fits_left, fits_right = min(xs) - 22 - bw >= 12, max(xs) + 22 + bw <= W - 12
            right = (fits_right or not fits_left) if who == "foe" else (not fits_left and fits_right)
            bid = f"q{k}"
            el = bubble(bid, line, right, ufo_y, c, mood, FOE_SKIN if who == "foe" else SKIN)
            (foe_bubbles if who == "foe" else bubbles).append(el)
            an.add(f"#{bid}", bid, pop([(t0 + s0, t0 + e0)]),
                   base=f"opacity:0;transform-box:fill-box;transform-origin:{'0% 100%' if right else '100% 100%'};")

        sh = (f'<g id="foebody"><g class="bob" style="animation-delay:-.7s">'
              f'<path id="fbeam" d="M-9 {ufo_y + 7}L9 {ufo_y + 7}L15 {grid_y + grid_h + 6}L-15 {grid_y + grid_h + 6}z" '
              f'fill="url(#fg)" opacity="0"/>'
              + saucer("ftilt", ufo_y, FOE, FOE_LIGHTS, alien(0, ufo_y - 5.5, 9, "angry", FOE_SKIN),
                       f'<ellipse id="fhit" cx="0" cy="{ufo_y}" rx="24" ry="9" fill="#ffe6a0"/>') + "</g></g>")
        foe_parts = [f'<g id="foe">{sh}{"".join(foe_bubbles)}</g>']

        # shots: hits are aimed where the target will be; misses where it is when we fire
        def abs_pos(who, t):
            x, y = bt[who](t)
            return x, ufo_y + y

        report = []
        for k, (who, kind, t) in enumerate(bt["shots"]):
            other = "foe" if who == "us" else "us"
            speed = BLAST if kind == "blast" else BOLT
            if kind == "miss":
                fire = t
                sx, sy = abs_pos(who, fire)
                tx, ty = abs_pos(other, fire)
            else:
                fire = t - 0.2
                for _ in range(6):    # solve for the firing time that meets the target at time t
                    sx, sy = abs_pos(who, fire)
                    tx, ty = abs_pos(other, t)
                    fire = t - math.hypot(tx - sx, ty - sy) / speed
            ang = math.atan2(ty - sy, tx - sx)
            sx, sy = sx + 26 * math.cos(ang), sy + 26 * math.sin(ang)          # leave from the hull's edge
            if kind == "miss":
                tx, ty = sx + 520 * math.cos(ang), sy + 520 * math.sin(ang)    # sail on past
            dist = math.hypot(tx - sx, ty - sy)
            land = fire + dist / speed
            if kind == "miss":    # how close did it get?
                near = min(math.hypot(sx + (tx - sx) * q / 60 - abs_pos(other, fire + (land - fire) * q / 60)[0],
                                      sy + (ty - sy) * q / 60 - abs_pos(other, fire + (land - fire) * q / 60)[1])
                           for q in range(61))
                report.append(f"{who} miss at {t:.2f}s passes {near:.0f}px from its target")
            deg = math.degrees(ang)
            go = lambda x, y: f"transform:translate({x:.1f}px,{y:.1f}px) rotate({deg:.1f}deg)"
            an.add(f"#s{k}", f"s{k}", [(t0 + fire - 0.01, go(sx, sy) + ";opacity:0"), (t0 + fire, go(sx, sy) + ";opacity:1"),
                                      (t0 + land, go(tx, ty) + ";opacity:1"), (t0 + land + 0.01, go(tx, ty) + ";opacity:0")])
            col = u["beam"] if who == "us" else "#ff5f56"
            if kind == "blast":
                fx.append(f'<g id="s{k}" class="fx"><rect x="-20" y="-6" width="40" height="12" rx="6" fill="{col}" opacity=".35"/>'
                          f'<rect x="-15" y="-3" width="30" height="6" rx="3" fill="#fff"/></g>')
                # charging orb in front of us
                cs, ce = bt["charge"]
                ox, oy = abs_pos("us", ce)
                ox += 26 * math.cos(ang)
                oy += 26 * math.sin(ang)
                an.add("#orb", "orb", [(t0 + cs - 0.01, "transform:scale(.1);opacity:0"), (t0 + cs, "transform:scale(.1);opacity:1"),
                                       (t0 + ce, "transform:scale(1.2);opacity:1"), (t0 + fire, "transform:scale(1.4);opacity:1"),
                                       (t0 + fire + 0.05, "transform:scale(.2);opacity:0")], base="opacity:0;" + grow)
                fx.append(f'<g id="orb"><circle cx="{ox:.1f}" cy="{oy:.1f}" r="9" fill="{col}" opacity=".35"/>'
                          f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="4.5" fill="#fff"/></g>')
            else:
                fx.append(f'<rect id="s{k}" class="fx" x="-7" y="-1.5" width="14" height="3" rx="1.5" fill="{col}"/>')
            if kind != "miss":    # sparks where it lands
                big = kind == "blast"
                an.add(f"#k{k}", f"k{k}", [(t0 + land - 0.01, "transform:scale(.3);opacity:0"),
                                          (t0 + land, "transform:scale(.3);opacity:1"),
                                          (t0 + land + 0.3, f"transform:scale({3.5 if big else 2.4});opacity:0")],
                       base="opacity:0;" + grow)
                fx.append(f'<circle id="k{k}" cx="{tx:.1f}" cy="{ty:.1f}" r="5" fill="none" stroke="{SPARK}" stroke-width="2"/>')
                for m in range(5):
                    a2 = ang + math.pi + (m - 2) * 0.55
                    dx, dy = math.cos(a2) * (22 if big else 15), math.sin(a2) * (22 if big else 15)
                    an.add(f"#k{k}_{m}", f"k{k}_{m}", [(t0 + land - 0.01, "transform:none;opacity:0"),
                                                      (t0 + land, "transform:none;opacity:1"),
                                                      (t0 + land + 0.35, f"transform:translate({dx:.1f}px,{dy:.1f}px) scale(.3);opacity:0")],
                           base="opacity:0;" + grow, timing="ease-out")
                    fx.append(f'<rect id="k{k}_{m}" x="{tx - 1.5:.1f}" y="{ty - 1.5:.1f}" width="3" height="3" fill="{SPARK}"/>')
        bt["report"] = report

        # explosion: flash, shock ring and debris where the rival ends up
        bx, by = abs_pos("foe", bt["boom"])
        an.add("#xf", "xf", [(boom - 0.01, "transform:scale(.2);opacity:0"), (boom, "transform:scale(.2);opacity:1"),
                             (boom + 0.35, "transform:scale(2);opacity:0")], base="opacity:0;" + grow)
        an.add("#xr", "xr", [(boom - 0.01, "transform:scale(.3);opacity:0"), (boom, "transform:scale(.3);opacity:1"),
                             (boom + 0.65, "transform:scale(6);opacity:0")], base="opacity:0;" + grow)
        fx.append(f'<circle id="xf" cx="{bx:.1f}" cy="{by:.1f}" r="18" fill="#fff3b0"/>')
        fx.append(f'<circle id="xr" cx="{bx:.1f}" cy="{by:.1f}" r="7" fill="none" stroke="{SPARK}" stroke-width="2"/>')
        for k in range(12):
            ang = 2 * math.pi * k / 12 + 0.3
            dx, dy = math.cos(ang) * 52, math.sin(ang) * 34 + 30
            an.add(f"#xd{k}", f"xd{k}", [(boom - 0.01, "transform:none;opacity:0"), (boom, "transform:none;opacity:1"),
                                         (boom + 0.8, f"transform:translate({dx:.1f}px,{dy:.1f}px) rotate({160 + k * 40}deg);opacity:0")],
                   base="opacity:0;" + grow, timing="cubic-bezier(.2,.6,.4,1)")
            col = (FOE["hull"], FOE["rim"], SPARK)[k % 3]
            fx.append(f'<rect id="xd{k}" x="{bx - 2.5:.1f}" y="{by - 2.5:.1f}" width="5" height="5" rx="1" fill="{col}"/>')

        # victory: a GitHub star pops out above us
        st = t0 + bt["star"]
        px, py = abs_pos("us", bt["star"])
        sy = py - 36
        an.add("#star", "star", [(st - 0.01, "transform:translateY(18px) scale(0) rotate(0deg);opacity:0"),
                                 (st, "transform:translateY(18px) scale(0) rotate(0deg);opacity:1"),
                                 (st + 0.35, "transform:translateY(-8px) scale(1.3) rotate(250deg);opacity:1"),
                                 (st + 0.6, "transform:translateY(-12px) scale(1) rotate(360deg);opacity:1"),
                                 (st + 1.0, "transform:translateY(-20px) scale(1) rotate(360deg);opacity:1"),
                                 (st + 1.35, "transform:translateY(-34px) scale(.5) rotate(360deg);opacity:0")],
               base="opacity:0;" + grow, timing="ease-out")
        star = " ".join(f"{px + r * math.sin(math.pi * k / 5):.1f},{sy - r * math.cos(math.pi * k / 5):.1f}"
                        for k, r in ((k, 12 if k % 2 == 0 else 5) for k in range(10)))
        fx.append(f'<polygon id="star" points="{star}" fill="{STAR}" stroke="#fff6c8" stroke-width="1" stroke-linejoin="round"/>')
        for k, (qx, qy) in enumerate(((px - 22, sy - 6), (px + 20, sy - 18), (px + 16, sy + 8))):
            s1 = st + 0.4 + k * 0.25
            an.add(f"#sp{k}", f"sp{k}", [(s1 - 0.01, "transform:scale(0);opacity:0"), (s1, "transform:scale(0);opacity:1"),
                                         (s1 + 0.25, "transform:scale(1.2);opacity:1"), (s1 + 0.5, "transform:scale(0);opacity:1"),
                                         (s1 + 0.51, "transform:scale(0);opacity:0")], base="opacity:0;" + grow)
            fx.append(f'<path id="sp{k}" d="M{qx} {qy - 5}L{qx + 1.3} {qy - 1.3}L{qx + 5} {qy}L{qx + 1.3} {qy + 1.3}'
                      f'L{qx} {qy + 5}L{qx - 1.3} {qy + 1.3}L{qx - 5} {qy}L{qx - 1.3} {qy - 1.3}z" fill="{STAR}"/>')

    # reduced motion: a still scene with our UFO parked over the middle
    css.append(f"@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}"
               f"#ufo{{transform:translate({W / 2:.1f}px,0)}}}}")

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Consolas, \'Cascadia Mono\', \'DejaVu Sans Mono\', Menlo, monospace" role="img" '
         f'aria-label="A UFO abducting the contribution calendar, one week at a time">',
         f"<style>{''.join(css + an.css + cells_css)}</style>",
         f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{u["beam"]}" stop-opacity=".75"/>'
         f'<stop offset="1" stop-color="{u["beam"]}" stop-opacity=".08"/></linearGradient>'
         f'<linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{FOE["beam"]}" stop-opacity=".7"/>'
         f'<stop offset="1" stop-color="{FOE["beam"]}" stop-opacity=".08"/></linearGradient></defs>',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}"/>',
         f'<path d="M0.5 {BAR}V12.5a12 12 0 0 1 12-12H{W - 12.5}a12 12 0 0 1 12 12V{BAR}z" fill="{c["bar"]}"/>',
         f'<line x1="0.5" y1="{BAR}" x2="{W - 0.5}" y2="{BAR}" stroke="{c["border"]}"/>']
    for i, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        o.append(f'<circle cx="{24 + i * 20}" cy="{BAR / 2}" r="6" fill="{col}"/>')
    o.append(f'<text x="{W / 2}" y="{BAR / 2 + 5}" text-anchor="middle" font-size="13" '
             f'style="fill:{c["text"]};opacity:.7">hdnng -- ufo</text>')
    o.append(f'<text x="{grid_x:.1f}" y="{prompt_y}" font-size="15"><tspan class="p">hdnng@github</tspan>'
             f'<tspan class="t">:</tspan><tspan class="k">~</tspan><tspan class="t">$ ./ufo --abduct contributions</tspan></text>')

    # empty slots, then the contributions on top
    o.append(f'<g fill="{lv[0]}">')
    for i, week in enumerate(weeks):
        for r, v in enumerate(week):
            if v is not None:
                o.append(f'<rect x="{grid_x + i * STEP:.1f}" y="{grid_y + r * STEP}" width="{CELL}" height="{CELL}" rx="2"/>')
    o.append("</g>")
    for i, week in enumerate(weeks):
        o.append("".join(
            f'<rect id="c{i}_{r}" x="{grid_x + i * STEP:.1f}" y="{grid_y + r * STEP}" width="{CELL}" height="{CELL}" rx="2" fill="{lv[v]}"/>'
            for r, v in enumerate(week) if v))

    o += foe_parts
    top = ufo_y + 7                      # underside of the (scaled) saucer
    o.append(f'<g id="ufo"><g class="bob">'
             f'<path id="beam" d="M-9 {top}L9 {top}L15 {grid_y + grid_h + 6}L-15 {grid_y + grid_h + 6}z" fill="url(#bg)" opacity="0"/>'
             + saucer("tilt", ufo_y, u, LIGHTS, alien(0, ufo_y - 5.5, 9)) + "</g>" + "".join(bubbles) + "</g>")
    o += fx

    total = cal.get("total")
    active = sum(1 for w in weeks for v in w if v)
    msg = (f"{total:,} contributions" if isinstance(total, int) else f"{active} active days")
    o.append(f'<text x="{grid_x:.1f}" y="{foot_y}" font-size="15"><tspan class="d">&gt; </tspan>'
             f'<tspan class="v">{msg}</tspan><tspan class="t"> abducted from the last year </tspan>'
             f'<tspan class="cur">█</tspan></text>')
    o.append("</svg>")
    if bt:
        render.info = dict(T=T, B=B, M=M, t0=t0, report=bt["report"], week=bt["week"], stop=bt["stop"])
    return "\n".join(o) + "\n"


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "cache" / "calendar.json"
    if not src.exists():
        print(f"{src} not found; skipping UFO animation")
        return
    cal = json.loads(src.read_text())
    for theme in THEMES:
        (ROOT / f"ufo_{theme}.svg").write_text(render(theme, cal))


if __name__ == "__main__":
    main()
