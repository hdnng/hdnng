#!/usr/bin/env python3
"""Render ufo_dark.svg / ufo_light.svg: a UFO flies over the contribution calendar
and beams each week's contributions up into itself, then the grid respawns.

Reads cache/calendar.json ({"total": int|null, "weeks": [[level|null] * 7, ...]},
levels 0-4, null for days outside the range), written by fetch_stats.py.
Pure CSS animation, so it plays inside a README image (no script, no hover).
"""
import json
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

LEVELS = {
    "dark": ["#16303a", "#1e6b6f", "#2a9d8f", "#4fc4b3", "#8ff0dc"],
    "light": ["#e3ebf0", "#b6e3dc", "#6cc7b9", "#2a9d8f", "#0a7d6c"],
}
UFO = {
    "dark": dict(hull="#7f9aa5", rim="#c4d6dc", dome="#9fd8e6", glow="#7ee0c8", beam="#7ee0c8"),
    "light": dict(hull="#4f6b76", rim="#8ea9b3", dome="#5bb6c9", glow="#0a7d6c", beam="#2a9d8f"),
}
LIGHTS = ["#ffbd2e", "#ff5f56", "#27c93f", "#58a6ff"]


def pct(t, total):
    return f"{min(max(t / total * 100, 0), 100):.3f}%"


def timeline(weeks, grid_x, ufo_y):
    """Stops for every week that has contributions: (x, arrive, leave)."""
    stops, t, x = [], 0.0, -60.0
    for i, week in enumerate(weeks):
        if not any(week):
            continue
        cx = grid_x + i * STEP + CELL / 2
        t += abs(cx - x) / SPEED
        stops.append((i, cx, t, t + BEAM))
        t, x = t + BEAM, cx
    t_exit = t + abs(W + 60 - x) / SPEED
    return stops, t_exit, t_exit + RESPAWN


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
    stops, t_exit, T = timeline(weeks, grid_x, ufo_y)
    T = max(T, 4.0)

    css = [
        f"text{{white-space:pre}}.p{{fill:{c['add']}}}.k{{fill:{c['key']}}}.t{{fill:{c['text']}}}"
        f".d{{fill:{c['dots']}}}.v{{fill:{c['value']}}}",
        f".a{{animation:{T:.2f}s infinite}}",
        f".cur{{fill:{c['value']};animation:blink 1.1s steps(1) infinite}}@keyframes blink{{50%{{opacity:0}}}}",
        ".bob{animation:bob 1.6s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-3px)}}",
        ".lt{animation:lt 0.9s steps(1) infinite}@keyframes lt{50%{opacity:.25}}",
        # reduced motion: show a still scene with the UFO parked over the middle
        f"@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}"
        f"#ufo{{transform:translate({W / 2:.1f}px,0)}}}}",
    ]

    # UFO path: enter from the left, pause over each week, exit right
    frames = [f"0%{{transform:translate(-60px,0)}}"]
    beam = ["0%{opacity:0}"]
    for _, cx, a, l in stops:
        frames.append(f"{pct(a, T)},{pct(l, T)}{{transform:translate({cx:.1f}px,0)}}")
        beam += [f"{pct(a, T)}{{opacity:0}}", f"{pct(a + 0.08, T)},{pct(l - 0.1, T)}{{opacity:.9}}",
                 f"{pct(l, T)}{{opacity:0}}"]
    frames.append(f"{pct(t_exit, T)},100%{{transform:translate({W + 60}px,0)}}")
    css.append(f"#ufo{{animation:ufo {T:.2f}s ease-in-out infinite}}@keyframes ufo{{{''.join(frames)}}}")
    css.append(f"#beam{{opacity:0;animation:beam {T:.2f}s linear infinite}}@keyframes beam{{{''.join(beam)}}}")

    # cells ride the beam one by one (top first), spinning and shrinking into the UFO
    respawn = t_exit + 0.2
    for i, cx, a, l in stops:
        lifted = [r for r, v in enumerate(weeks[i]) if v]
        for n, r in enumerate(lifted):
            s0 = a + LIFT0 + n * STAGGER
            dy = ufo_y + 5 - (grid_y + r * STEP + CELL / 2)
            css.append(
                f"#c{i}_{r}{{transform-box:fill-box;transform-origin:center;animation:c{i}_{r} {T:.2f}s infinite}}"
                f"@keyframes c{i}_{r}{{0%,{pct(s0, T)}{{transform:none;opacity:1;animation-timing-function:cubic-bezier(.5,0,.9,.6)}}"
                f"{pct(s0 + RISE, T)},{pct(respawn, T)}{{transform:translateY({dy:.1f}px) rotate(200deg) scale(.25);opacity:0}}"
                f"{pct(respawn + 0.01, T)}{{transform:none;opacity:0}}100%{{transform:none;opacity:1}}}}")

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Consolas, \'Cascadia Mono\', \'DejaVu Sans Mono\', Menlo, monospace" role="img" '
         f'aria-label="A UFO abducting the contribution calendar, one week at a time">',
         f"<style>{''.join(css)}</style>",
         f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{u["beam"]}" stop-opacity=".75"/>'
         f'<stop offset="1" stop-color="{u["beam"]}" stop-opacity=".08"/></linearGradient></defs>',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}"/>',
         f'<path d="M0.5 {BAR}V12.5a12 12 0 0 1 12-12H{W - 12.5}a12 12 0 0 1 12 12V{BAR}z" fill="{c["bar"]}"/>',
         f'<line x1="0.5" y1="{BAR}" x2="{W - 0.5}" y2="{BAR}" stroke="{c["border"]}"/>']
    for i, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        o.append(f'<circle cx="{24 + i * 20}" cy="{BAR / 2}" r="6" fill="{col}"/>')
    o.append(f'<text x="{W / 2}" y="{BAR / 2 + 5}" text-anchor="middle" font-size="13" '
             f'style="fill:{c["text"]};opacity:.7">hdnng -- ufo</text>')
    o.append(f'<text x="{grid_x:.1f}" y="{prompt_y}" font-size="15"><tspan class="p">hdnng@github</tspan>'
             f'<tspan class="t">:</tspan><tspan class="k">~</tspan><tspan class="t">$ ./ufo --abduct contributions</tspan></text>')

    # empty slots, then the contributions grouped by week so a week can be abducted as one
    o.append(f'<g fill="{lv[0]}">')
    for i, week in enumerate(weeks):
        for r, v in enumerate(week):
            if v is not None:
                o.append(f'<rect x="{grid_x + i * STEP:.1f}" y="{grid_y + r * STEP}" width="{CELL}" height="{CELL}" rx="2"/>')
    o.append("</g>")
    for i, week in enumerate(weeks):
        cells = [(r, v) for r, v in enumerate(week) if v]
        if cells:
            o.append("".join(
                f'<rect id="c{i}_{r}" x="{grid_x + i * STEP:.1f}" y="{grid_y + r * STEP}" width="{CELL}" height="{CELL}" rx="2" fill="{lv[v]}"/>'
                for r, v in cells))

    # the UFO, drawn around (0, ufo_y) and moved along x by its animation
    top = ufo_y + 7                      # underside of the (scaled) saucer
    beam_h = grid_y + grid_h + 6 - top
    o.append(f'<g id="ufo"><g class="bob">'
             f'<path id="beam" d="M-9 {top}L9 {top}L15 {top + beam_h}L-15 {top + beam_h}z" fill="url(#bg)"/>'
             f'<g transform="translate(0 {ufo_y}) scale(1.4) translate(0 {-ufo_y})">'
             f'<ellipse cx="0" cy="{ufo_y + 5}" rx="10" ry="2.6" fill="{u["glow"]}" opacity=".75"/>'
             f'<path d="M-10 {ufo_y - 2}a10 10 0 0 1 20 0z" fill="{u["dome"]}" opacity=".9"/>'
             f'<path d="M-5 {ufo_y - 6}a6 6 0 0 1 5 -4" stroke="#fff" stroke-opacity=".7" stroke-width="1.5" fill="none" stroke-linecap="round"/>'
             f'<ellipse cx="0" cy="{ufo_y + 1}" rx="23" ry="6.5" fill="{u["hull"]}"/>'
             f'<ellipse cx="0" cy="{ufo_y - 1}" rx="21" ry="3" fill="{u["rim"]}"/>')
    for k, col in enumerate(LIGHTS):
        o.append(f'<circle class="lt" style="animation-delay:-{k * 0.22:.2f}s" cx="{-13.5 + k * 9}" cy="{ufo_y + 2.5}" r="1.7" fill="{col}"/>')
    o.append("</g></g></g>")

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
