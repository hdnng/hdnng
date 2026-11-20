#!/usr/bin/env python3
"""Render ufo_dark.svg / ufo_light.svg: a UFO flies over the contribution calendar
and beams each week's contributions up into itself, then the grid respawns.

Every BATTLE_EVERY-th loop a rival UFO turns up first and steals the busiest
recent week; our UFO flies in, shoots it down, the stolen squares fall back
into place and our UFO pops a GitHub star before starting its usual run.

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

BATTLE_EVERY = 2              # the rival shows up in every 2nd loop
FOE_LINE, CALL_LINE, WIN_LINE = "yoink! mine now", "hey! give them back!", "GG ez!"
STANDOFF = 170                # distance between the two UFOs during the fight
BOLT = 900                    # laser speed, px/s

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
STAR = "#f5c518"


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


def saucer(ufo_y, u, lights, pilot, extra=""):
    """Saucer drawn around (0, ufo_y) at 1.4x, with its pilot under the glass."""
    out = [f'<g transform="translate(0 {ufo_y}) scale(1.4) translate(0 {-ufo_y})">',
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
    out.append(extra + "</g>")
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

    def add(self, sel, name, points, base="", timing="linear", extra=""):
        pts = sorted(points, key=lambda p: p[0])
        if pts[0][0] > 0:
            pts.insert(0, (0, pts[0][1]))
        if pts[-1][0] < self.M:
            pts.append((self.M, pts[-1][1]))
        frames = {}
        for t, decl in pts:         # a later point at the same instant wins
            frames[self.pct(t)] = decl
        body = "".join(f"{p}{{{d}}}" for p, d in frames.items())
        self.css.append(f"{sel}{{{base}animation:{name} {self.M:.2f}s {timing} infinite{extra}}}"
                        f"@keyframes {name}{{{body}}}")


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


def plan_battle(weeks, grid_x):
    """Times (from the start of the battle) for the rival's raid and the dogfight."""
    lo = STANDOFF + 22 + bubble_size(CALL_LINE)[0] + 12        # room for our bubble on the left
    hi = W - 12 - 22 - bubble_size(FOE_LINE)[0]                # room for the rival's on the right
    picks = [(sum(1 for v in w if v), sum(v or 0 for v in w), i) for i, w in enumerate(weeks)
             if any(w) and lo <= grid_x + i * STEP + CELL / 2 <= hi]
    if not picks:
        return None
    _, _, i = max(picks)
    b = {"week": i, "x": grid_x + i * STEP + CELL / 2}
    b["x_o"] = b["x"] - STANDOFF
    b["arrive"] = 0.3 + (W + 60 - b["x"]) / SPEED
    b["leave"] = b["arrive"] + BEAM
    b["foe_chat"] = (b["arrive"] + 0.25, b["arrive"] + 1.9)
    b["enter"] = b["arrive"] + 0.5
    b["in_place"] = b["enter"] + (b["x_o"] + 60) / (2 * SPEED)
    s = max(b["in_place"], b["foe_chat"][1]) + 0.05
    b["call_chat"] = (s, s + 1.5)
    f0 = s + 1.0
    b["hits"] = [f0 + 0.2, f0 + 1.1, f0 + 1.6]
    b["foe_fire"] = f0 + 0.35
    b["dodge"] = b["foe_fire"] + (b["x"] - 30 - b["x_o"]) / BOLT    # when the rival's shot passes us
    b["boom"] = b["hits"][-1] + 0.05
    b["win_chat"] = (b["boom"] + 0.4, b["boom"] + 2.2)
    b["star"] = b["boom"] + 0.5
    b["exit"] = b["boom"] + 2.4
    b["length"] = b["exit"] + (b["x_o"] + 60) / SPEED + 0.3
    return b


def render(theme, cal):
    c, lv, u = THEMES[theme], LEVELS[theme], UFO[theme]
    weeks = cal["weeks"]
    grid_w = len(weeks) * STEP - GAP
    grid_x = (W - grid_w) / 2
    prompt_y = BAR + PAD + 12
    grid_y = prompt_y + 30 + UFO_DROP + 26
    ufo_y = grid_y - UFO_DROP
    grid_h = 7 * STEP - GAP
    foot_y = grid_y + grid_h + 40
    H = round(foot_y + PAD)

    stops, chats, t_exit, T = plan_run(weeks, grid_x)
    T = max(T, 4.0)
    battle = plan_battle(weeks, grid_x) if stops else None
    B = battle["length"] if battle else 0
    loops = BATTLE_EVERY if battle else 1
    M = loops * T + B
    ob = (loops - 1) * T if battle else None          # the battle opens the last loop of the cycle
    runs = [j * T + (B if battle and j == loops - 1 else 0) for j in range(loops)]
    an = Anim(M)
    ms = lambda x, y=0: f"transform:translate({x:.1f}px,{y}px)"

    css = [
        f"text{{white-space:pre}}.p{{fill:{c['add']}}}.k{{fill:{c['key']}}}.t{{fill:{c['text']}}}"
        f".d{{fill:{c['dots']}}}.v{{fill:{c['value']}}}",
        f".cur{{fill:{c['value']};animation:blink 1.1s steps(1) infinite}}@keyframes blink{{50%{{opacity:0}}}}",
        ".bob{animation:bob 1.6s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-3px)}}",
        ".lt{animation:lt 0.9s steps(1) infinite}@keyframes lt{50%{opacity:.25}}",
        ".fx{opacity:0}",
    ]

    # --- our UFO: runs, plus the dogfight in the battle loop
    pts = []
    for o in runs:
        pts.append((o, ms(-60)))
        for n, (_, cx, a, l) in enumerate(stops):
            hold = l + (GLOAT if n == len(stops) - 1 else 0)
            pts += [(o + a, ms(cx)), (o + hold, ms(cx))]
        pts += [(o + t_exit, ms(W + 60)), (o + T - 0.01, ms(W + 60))]
    if battle:
        x_o, d = battle["x_o"], ob + battle["dodge"]
        pts += [(ob, ms(-60)), (ob + battle["enter"], ms(-60)), (ob + battle["in_place"], ms(x_o)),
                (d - 0.2, ms(x_o)), (d - 0.06, ms(x_o, -22)), (d + 0.12, ms(x_o, -22)), (d + 0.36, ms(x_o)),
                (ob + battle["exit"], ms(x_o)), (ob + battle["length"] - 0.3, ms(-60))]
    an.add("#ufo", "ufo", pts, timing="ease-in-out")

    pts = [(0, "opacity:0")]
    for o in runs:
        for _, _, a, l in stops:
            pts += [(o + a, "opacity:0"), (o + a + 0.08, "opacity:.9"), (o + l - 0.1, "opacity:.9"), (o + l, "opacity:0")]
    an.add("#beam", "beam", pts)

    def pop(windows):
        pts = [(0, "opacity:0;transform:scale(.2)")]
        for s0, e0 in windows:
            pts += [(s0, "opacity:0;transform:scale(.2)"), (s0 + 0.18, "opacity:1;transform:scale(1.08)"),
                    (s0 + 0.28, "opacity:1;transform:scale(1)"), (e0 - 0.2, "opacity:1;transform:scale(1)"),
                    (e0, "opacity:0;transform:scale(1)"), (e0 + 0.01, "opacity:0;transform:scale(.2)")]
        return pts

    bubbles = []
    for k, (line, right, s0, e0) in enumerate(chats):
        bubbles.append(bubble(f"b{k}", line, right, ufo_y, c))
        an.add(f"#b{k}", f"b{k}", pop([(o + s0, o + e0) for o in runs]),
               base=f"opacity:0;transform-box:fill-box;transform-origin:{'0% 100%' if right else '100% 100%'};")

    # --- the grid: cells ride the beam one by one (top first) and refill at the end of each run
    lift = "transform:none;opacity:1;animation-timing-function:cubic-bezier(.5,0,.9,.6)"
    shown = "transform:none;opacity:1"
    cells_css, at = [], {i: (a, l) for i, _, a, l in stops}
    for i, week in enumerate(weeks):
        lifted = [r for r, v in enumerate(week) if v]
        for n, r in enumerate(lifted):
            dy = ufo_y + 5 - (grid_y + r * STEP + CELL / 2)
            gone = f"transform:translateY({dy:.1f}px) rotate(200deg) scale(.25)"
            pts = [(0, shown)]
            for o in runs:
                s0 = o + at[i][0] + LIFT0 + n * STAGGER
                rs = o + t_exit + 0.2
                pts += [(s0, lift), (s0 + RISE, gone + ";opacity:0"), (rs, gone + ";opacity:0"),
                        (rs + 0.01, "transform:none;opacity:0"), (o + T - 0.02, shown)]
            if battle and i == battle["week"]:
                s0 = ob + battle["arrive"] + LIFT0 + n * STAGGER
                back = ob + battle["boom"] + 0.25 + n * 0.06
                pts += [(s0, lift), (s0 + RISE, gone + ";opacity:0"), (back, gone + ";opacity:0"),
                        (back + 0.01, gone + ";opacity:1;animation-timing-function:cubic-bezier(.4,0,.8,1)"),
                        (back + 0.45, shown)]
            sub = Anim(M)
            sub.add(f"#c{i}_{r}", f"c{i}_{r}", pts, base="transform-box:fill-box;transform-origin:center;")
            cells_css += sub.css

    # --- the rival and the fight
    foe_parts, fx = [], []
    if battle:
        x_s, x_o = battle["x"], battle["x_o"]
        boom = ob + battle["boom"]
        pts = [(0, ms(W + 60)), (ob + 0.3, ms(W + 60)), (ob + battle["arrive"], ms(x_s))]
        for h in battle["hits"]:
            pts += [(ob + h, ms(x_s)), (ob + h + 0.05, ms(x_s + 6)), (ob + h + 0.1, ms(x_s - 4)), (ob + h + 0.16, ms(x_s))]
        pts += [(boom + 0.3, ms(x_s)), (boom + 0.31, ms(W + 60))]
        an.add("#foe", "foe", pts, base=f"{ms(W + 60)};")
        an.add("#foebody", "foebody", [(0, "opacity:1"), (boom, "opacity:1"), (boom + 0.01, "opacity:0"),
                                       (boom + 0.32, "opacity:0"), (boom + 0.33, "opacity:1")])
        a, l = ob + battle["arrive"], ob + battle["leave"]
        an.add("#fbeam", "fbeam", [(a, "opacity:0"), (a + 0.08, "opacity:.9"), (l - 0.1, "opacity:.9"), (l, "opacity:0")])
        pts = []
        for h in battle["hits"]:
            pts += [(ob + h, "opacity:0"), (ob + h + 0.01, "opacity:.9"), (ob + h + 0.15, "opacity:0")]
        an.add("#fhit", "fhit", pts, base="opacity:0;")

        s0, e0 = battle["foe_chat"]
        an.add("#fb", "fb", pop([(ob + s0, ob + e0)]), base="opacity:0;transform-box:fill-box;transform-origin:0% 100%;")
        for bid, (s0, e0) in (("bc", battle["call_chat"]), ("bw", battle["win_chat"])):
            an.add(f"#{bid}", bid, pop([(ob + s0, ob + e0)]),
                   base="opacity:0;transform-box:fill-box;transform-origin:100% 100%;")
        bubbles.append(bubble("bc", CALL_LINE, False, ufo_y, c, "angry"))
        bubbles.append(bubble("bw", WIN_LINE, False, ufo_y, c))

        sh = (f'<g id="foebody"><g class="bob" style="animation-delay:-.7s">'
              f'<path id="fbeam" d="M-9 {ufo_y + 7}L9 {ufo_y + 7}L15 {grid_y + grid_h + 6}L-15 {grid_y + grid_h + 6}z" '
              f'fill="url(#fg)" opacity="0"/>'
              + saucer(ufo_y, FOE, FOE_LIGHTS, alien(0, ufo_y - 5.5, 9, "angry", FOE_SKIN),
                       f'<ellipse id="fhit" cx="0" cy="{ufo_y}" rx="24" ry="9" fill="#fff"/>') + "</g></g>")
        foe_parts = [f'<g id="foe">{sh}{bubble("fb", FOE_LINE, True, ufo_y, c, "angry", FOE_SKIN)}</g>']

        # our three shots hit, the rival's one shot misses as we hop over it
        for k, h in enumerate(battle["hits"]):
            h += ob
            an.add(f"#z{k}", f"z{k}", [(h - 0.2, f"{ms(x_o + 26)};opacity:0"), (h - 0.19, f"{ms(x_o + 26)};opacity:1"),
                                      (h, f"{ms(x_s - 38)};opacity:1"), (h + 0.01, f"{ms(x_s - 38)};opacity:0")])
            fx.append(f'<rect id="z{k}" class="fx" x="0" y="{ufo_y - 1.5}" width="14" height="3" rx="1.5" '
                      f'fill="{u["beam"]}"/>')
        f = ob + battle["foe_fire"]
        far = f + (x_s - 40 + 80) / BOLT
        an.add("#zf", "zf", [(f, f"{ms(x_s - 40)};opacity:0"), (f + 0.01, f"{ms(x_s - 40)};opacity:1"),
                             (far, f"{ms(-80)};opacity:1"), (far + 0.01, f"{ms(-80)};opacity:0")])
        fx.append(f'<rect id="zf" class="fx" x="0" y="{ufo_y - 1.5}" width="14" height="3" rx="1.5" fill="#ff5f56"/>')

        # explosion: flash, shock ring and debris
        grow = "transform-box:fill-box;transform-origin:center;"
        an.add("#xf", "xf", [(boom, "transform:scale(.2);opacity:1"), (boom + 0.32, "transform:scale(1.7);opacity:0")],
               base="opacity:0;" + grow)
        an.add("#xr", "xr", [(boom, "transform:scale(.3);opacity:1"), (boom + 0.6, "transform:scale(5);opacity:0")],
               base="opacity:0;" + grow)
        fx.append(f'<circle id="xf" cx="{x_s:.1f}" cy="{ufo_y}" r="16" fill="#fff3b0"/>')
        fx.append(f'<circle id="xr" cx="{x_s:.1f}" cy="{ufo_y}" r="7" fill="none" stroke="#ffbd2e" stroke-width="2"/>')
        for k in range(10):
            ang = 2 * math.pi * k / 10 + 0.3
            dx, dy = math.cos(ang) * 46, math.sin(ang) * 30 + 26
            an.add(f"#xd{k}", f"xd{k}", [(boom, "transform:none;opacity:1"),
                                         (boom + 0.75, f"transform:translate({dx:.1f}px,{dy:.1f}px) rotate({160 + k * 40}deg);opacity:0")],
                   base="opacity:0;" + grow, timing="cubic-bezier(.2,.6,.4,1)")
            col = (FOE["hull"], FOE["rim"], "#ffbd2e")[k % 3]
            fx.append(f'<rect id="xd{k}" x="{x_s - 2.5:.1f}" y="{ufo_y - 2.5}" width="5" height="5" rx="1" fill="{col}"/>')

        # our UFO pops a GitHub star to celebrate
        st = ob + battle["star"]
        an.add("#star", "star", [(st, "transform:translateY(18px) scale(0) rotate(0deg);opacity:1"),
                                 (st + 0.35, "transform:translateY(-8px) scale(1.3) rotate(250deg);opacity:1"),
                                 (st + 0.6, "transform:translateY(-12px) scale(1) rotate(360deg);opacity:1"),
                                 (st + 1.5, "transform:translateY(-20px) scale(1) rotate(360deg);opacity:1"),
                                 (st + 1.9, "transform:translateY(-34px) scale(.5) rotate(360deg);opacity:0")],
               base="opacity:0;" + grow, timing="ease-out")
        sy = ufo_y - 34
        star = " ".join(f"{x_o + r * math.sin(math.pi * k / 5):.1f},{sy - r * math.cos(math.pi * k / 5):.1f}"
                        for k, r in ((k, 12 if k % 2 == 0 else 5) for k in range(10)))
        fx.append(f'<polygon id="star" points="{star}" fill="{STAR}" stroke="#fff6c8" stroke-width="1" stroke-linejoin="round"/>')
        for k, (px, py) in enumerate(((x_o - 22, sy - 6), (x_o + 20, sy - 18), (x_o + 16, sy + 8))):
            s1 = st + 0.4 + k * 0.25
            an.add(f"#sp{k}", f"sp{k}", [(s1, "transform:scale(0);opacity:1"), (s1 + 0.25, "transform:scale(1.2);opacity:1"),
                                         (s1 + 0.5, "transform:scale(0);opacity:1"), (s1 + 0.51, "transform:scale(0);opacity:0")],
                   base="opacity:0;" + grow)
            fx.append(f'<path id="sp{k}" d="M{px} {py - 5}L{px + 1.3} {py - 1.3}L{px + 5} {py}L{px + 1.3} {py + 1.3}'
                      f'L{px} {py + 5}L{px - 1.3} {py + 1.3}L{px - 5} {py}L{px - 1.3} {py - 1.3}z" fill="{STAR}"/>')

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
             + saucer(ufo_y, u, LIGHTS, alien(0, ufo_y - 5.5, 9)) + "</g>" + "".join(bubbles) + "</g>")
    o += fx

    total = cal.get("total")
    active = sum(1 for w in weeks for v in w if v)
    msg = (f"{total:,} contributions" if isinstance(total, int) else f"{active} active days")
    o.append(f'<text x="{grid_x:.1f}" y="{foot_y}" font-size="15"><tspan class="d">&gt; </tspan>'
             f'<tspan class="v">{msg}</tspan><tspan class="t"> abducted from the last year </tspan>'
             f'<tspan class="cur">█</tspan></text>')
    o.append("</svg>")
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
