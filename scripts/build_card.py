#!/usr/bin/env python3
"""Render dark_mode.svg / light_mode.svg from config.json, the ASCII eye and cache/stats.json."""
import base64
import json
import math
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
COLS = 56                      # width of the info column, in characters
INFO_FS, INFO_LH = 15, 24      # info font size / line height (px)
EYE_T = 14.0                   # seconds in one loop of the eye's routine
FPS = 30                       # sampling rate of the eye animation
# the eye's routine: (time, dx, dy, squint 0-1, move seconds or None for a quick saccade)
GLANCES = [(0.0, 0, 0, 0, None),
           (1.4, 34, -2, 0.18, None),           # side-eye towards the stats
           (2.8, 33, -6, 0.22, None),           # ...and read them, line by line
           (3.15, 33, -2, 0.22, None),
           (3.5, 33, 2, 0.25, None),
           (3.85, 33, 6, 0.28, None),
           (4.6, 0, 0, 0, None),                # back to the middle (with a blink)
           (6.0, -30, -9, 0, None),             # up and left, pupil widening
           (7.3, -26, 8, 0.1, None),            # down and left
           (8.5, 31, 0, 0, None),               # a quick look right...
           (8.85, 0, 0, 0, None),               # ...and a double take
           (11.2, 10, -3, 0, 0.9),              # slow drift while idle
           (12.3, -8, 2, 0, 0.9),
           (13.3, 0, 0, 0, 0.7)]
BLINKS = [4.5, 9.9, 10.26]
PUPIL = [(0, 1.0), (5.9, 1.0), (6.5, 1.2), (7.3, 1.2), (7.9, 1.0), (8.4, 1.0), (8.7, 0.8), (10.8, 0.8), (11.8, 1.0)]
CW = 0.6                       # monospace advance width, in em
PAD, BAR = 28, 40

THEMES = {
    "dark": dict(bg="#0f2027", bar="#16303a", border="#2c5364", text="#c9d1d9", key="#58a6ff",
                 value="#7ee0c8", dots="#3b5b68", art="#9fd8e6", add="#3fb950", rem="#f85149"),
    "light": dict(bg="#f6f8fa", bar="#e3ebf0", border="#c5d3dc", text="#24292f", key="#0969da",
                  value="#0a7d6c", dots="#b4c3cd", art="#203a43", add="#1a7f37", rem="#cf222e"),
}


def ease(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * (3 - 2 * s)


def snap(s):
    """Saccade profile: fast start, soft landing."""
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 3


def glance_at(t):
    """(dx, dy, squint) at time t."""
    x, y, q = GLANCES[0][1:4]
    for (t1, x1, y1, q1, move) in GLANCES[1:]:
        if t >= t1:
            dur = move or 0.05 + math.hypot(x1 - x, y1 - y) * 0.0025
            k = (ease if move else snap)((t - t1) / dur)
            x, y, q = x + (x1 - x) * k, y + (y1 - y) * k, q + (q1 - q) * k
    return x, y, q


# tiny fixational jitter so the eye never looks frozen
_JIT = [(0.23 + k * 0.47 + 0.11 * math.sin(k * 7.1), 1.3 * math.sin(k * 2.3), 0.9 * math.cos(k * 3.7))
        for k in range(int(EYE_T / 0.47))]


def gaze_at(t):
    x, y, _ = glance_at(t)
    jx = jy = 0.0
    for (tj, ax, ay) in _JIT:
        if t >= tj:
            k = snap((t - tj) / 0.05)
            jx, jy = jx + (ax - jx) * k, jy + (ay - jy) * k
    return x + jx, y + jy


def pupil_at(t):
    for (t0, a), (t1, b) in zip(PUPIL, PUPIL[1:]):
        if t0 <= t < t1:
            return a + (b - a) * ease((t - t0) / (t1 - t0))
    return PUPIL[-1][1]


def lid_at(t):
    """How closed the upper lid is (0 open .. 1 shut): squints, follows a downward look, blinks."""
    x, y, q = glance_at(t)
    c = 0.9 * q + 0.004 * max(y, 0)
    for b in BLINKS:
        d = t - b
        if 0 <= d < 0.07:
            k = ease(d / 0.07)
        elif 0.07 <= d < 0.12:
            k = 1.0
        elif 0.12 <= d < 0.32:
            k = 1 - ease((d - 0.12) / 0.2)
        else:
            continue
        c += (1 - c) * k
    return c


def lid_frame(t, levels):
    """Index of the pre-drawn lid closest to the current closure, or None while fully open."""
    c = lid_at(t)
    if c < levels[0] / 2:
        return None
    return min(range(len(levels)), key=lambda k: abs(levels[k] - c))


def keyframes(name, fn):
    """Sample fn(t) -> declarations over the loop, dropping frames that repeat."""
    n = int(EYE_T * FPS)
    frames = [(k / FPS, fn(k / FPS)) for k in range(n)] + [(EYE_T, fn(0.0))]
    keep = [f for i, f in enumerate(frames)
            if i in (0, len(frames) - 1) or not (frames[i - 1][1] == f[1] == frames[i + 1][1])]
    return f"@keyframes {name}{{" + "".join(f"{t / EYE_T * 100:.2f}%{{{d}}}" for t, d in keep) + "}"


def eye_svg(c, eye, ax, ay, theme):
    """One animated eye: static picture, an iris that glances around behind the opening with a
    breathing pupil and lagging catchlights, and an upper lid that blinks and squints by
    flipping through pre-drawn lid positions.

    Every ASCII layer is a PNG pre-rendered by scripts/raster_eye.py and embedded here: as SVG
    text the eye would be some fifteen thousand characters repainted on every frame, which made
    the page stutter on phones. The animation only moves and swaps these pictures."""
    cw, ch = eye["cell_w"], eye["cell_h"]
    pts = lambda poly: " ".join(f"{ax + x:.1f},{ay + y:.1f}" for x, y in poly)

    def image(name, spr):
        png = base64.b64encode((ROOT / "assets" / "eye" / f"{name}_{theme}.png").read_bytes()).decode()
        w, h = max(len(r) for r in spr["rows"]) * cw, len(spr["rows"]) * ch
        return (f'<image x="{ax + spr["col"] * cw:.2f}" y="{ay + spr["row"] * ch:.2f}" width="{w:.2f}" '
                f'height="{h:.2f}" xlink:href="data:image/png;base64,{png}"/>')

    ix, iy = ax + eye["iris_center"][0], ay + eye["iris_center"][1]
    levels = [lid["c"] for lid in eye["lids"]]
    lids = [f"l{k}" for k in range(len(levels))]
    css = "".join([
        keyframes("gz", lambda t: "transform:translate({:.1f}px,{:.1f}px)".format(*gaze_at(t))),
        keyframes("gl", lambda t: "transform:translate({:.1f}px,{:.1f}px)".format(*(0.35 * v for v in gaze_at(t)))),
        keyframes("pp", lambda t: f"transform:scale({pupil_at(t):.3f})"),
        # lid frames are switched with visibility, not opacity: hidden elements are skipped when
        # painting, while transparent ones still cost a repaint on every frame
        *(keyframes(n, lambda t, k=k: f"visibility:{'visible' if lid_frame(t, levels) == k else 'hidden'}")
          for k, n in enumerate(lids)),
        f".gz{{animation:gz {EYE_T}s linear infinite}}.gl{{animation:gl {EYE_T}s linear infinite}}",
        f".pp{{transform-box:fill-box;transform-origin:center;animation:pp {EYE_T}s linear infinite}}",
        *(f".{n}{{visibility:hidden;animation:{n} {EYE_T}s steps(1) infinite}}" for n in lids),
        "@media (prefers-reduced-motion:reduce){" + ",".join([".gz", ".gl", ".pp"] + [f".{n}" for n in lids])
        + "{animation:none}}",
    ])
    if theme == "light":     # solid ink pupil, catchlights cut out of it
        w, d = eye["glint_shape"]["window"], eye["glint_shape"]["dot"]
        pupil = image("pupil", eye["pupil"])
        glint = (f'<polygon points="{" ".join(f"{ix + x:.1f},{iy + y:.1f}" for x, y in w)}" fill="{c["bg"]}"/>'
                 f'<circle cx="{ix + d[0]:.1f}" cy="{iy + d[1]:.1f}" r="{d[2]}" fill="{c["bg"]}"/>')
    else:                    # dark pupil, catchlights drawn in ink
        pupil, glint = "", image("glint", eye["glint"])
    out = [f'<defs><clipPath id="eyeopen"><polygon points="{pts(eye["opening"])}"/></clipPath></defs>',
           image("base", dict(col=0, row=0, rows=eye["base"])),
           f'<g clip-path="url(#eyeopen)"><g class="gz">'
           f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="{eye["r_iris"] + 1:.1f}" fill="{c["bg"]}"/>' + image("iris", eye["iris"]) +
           f'<g class="pp"><circle cx="{ix:.1f}" cy="{iy:.1f}" r="{eye["r_pupil"]:.1f}" fill="{c["bg"]}"/>{pupil}</g></g>'
           f'<g class="gl">{glint}</g></g>',
           "".join(f'<g class="l{k}"><polygon points="{pts(lid["poly"])}" fill="{c["bg"]}"/>{image(f"lid{k}", lid["text"])}</g>'
                   for k, lid in enumerate(eye["lids"]))]
    return css, "".join(out)


def uptime(since: date, today: date) -> str:
    y, m, d = today.year - since.year, today.month - since.month, today.day - since.day
    if d < 0:
        m -= 1
        prev_month_end = today.replace(day=1).toordinal() - 1
        d = today.day + max(date.fromordinal(prev_month_end).day - since.day, 0)
    if m < 0:
        y, m = y - 1, m + 12
    plural = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{plural(y, 'year')}, {plural(m, 'month')}, {plural(d, 'day')}"


def fmt(n):
    return f"{n:,}" if isinstance(n, int) else "-"


def row(key, value, width=COLS):
    """key: ..... value  -> list of (css class, text) filling exactly `width` characters."""
    dots = max(width - len(key) - len(value) - 3, 2)
    return [("key", key), ("text", ":"), ("dots", " " + "." * dots + " "), ("value", value)]


def info_lines(cfg, stats):
    user = cfg["username"]
    head = f"{user}@github "
    lines = [[("key", head), ("dots", "-" * (COLS - len(head)))]]
    since = cfg.get("birthday") or stats.get("created_at")
    up = uptime(date.fromisoformat(since[:10]), date.today()) if since else "-"
    for item in cfg["info"]:
        lines.append(row(item[0], item[1].replace("{uptime}", up)) if item else [])
    lines.append([])
    title = "- GitHub Stats "
    lines.append([("text", title), ("dots", "-" * (COLS - len(title)))])
    def pair(k1, v1, k2, v2):
        left = row(k1, v1, max((COLS - 3) // 2, len(k1) + len(v1) + 5))
        return left + [("text", " | ")] + row(k2, v2, COLS - 3 - sum(len(t) for _, t in left))

    repos = f"{fmt(stats.get('repos'))} {{Contributed: {fmt(stats.get('contributed'))}}}"
    lines.append(pair("Repos", repos, "Stars", fmt(stats.get("stars"))))
    lines.append(pair("Commits", fmt(stats.get("commits")), "Followers", fmt(stats.get("followers"))))
    days = lambda n: f"{n:,} day{'' if n == 1 else 's'}" if isinstance(n, int) else "-"
    lines.append(pair("Streak", days(stats.get("streak")), "Longest", days(stats.get("longest_streak"))))
    add, rem = stats.get("additions"), stats.get("deletions")
    net = fmt(add - rem) if isinstance(add, int) and isinstance(rem, int) else "-"
    tail = [("value", net), ("text", " ( "), ("add", fmt(add) + "++"), ("text", ", "),
            ("rem", fmt(rem) + "--"), ("text", " )")]
    used = sum(len(t) for _, t in tail)
    key = next(k for k in ("Lines of Code on GitHub", "Lines of Code", "LoC") if len(k) + used + 5 <= COLS or k == "LoC")
    dots = max(COLS - len(key) - 3 - used, 2)
    lines.append([("key", key), ("text", ":"), ("dots", " " + "." * dots + " ")] + tail)
    lines.append([])
    lines.append([("add", f"{user}@github"), ("text", ":"), ("key", "~"), ("text", "$ "), ("cursor", "█")])
    return lines


def render(theme, cfg, stats):
    c = THEMES[theme]
    eye = json.loads((ROOT / "assets" / "eye.json").read_text())
    art_w, art_h = eye["cols"] * eye["cell_w"], eye["rows"] * eye["cell_h"]
    lines = info_lines(cfg, stats)
    info_w, info_h = COLS * INFO_FS * CW, len(lines) * INFO_LH
    body_h = max(art_h, info_h)
    W = round(PAD + art_w + PAD + info_w + PAD)
    H = round(BAR + PAD + body_h + PAD)
    info_x = PAD + art_w + PAD
    eye_css, eye_markup = eye_svg(c, eye, PAD, BAR + PAD + (body_h - art_h) / 2, theme)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Consolas, \'Cascadia Mono\', \'DejaVu Sans Mono\', Menlo, monospace" role="img" '
         f'aria-label="{cfg["username"]} profile card">',
         "<style>"
         f".text{{fill:{c['text']}}}.key{{fill:{c['key']}}}.value{{fill:{c['value']}}}.dots{{fill:{c['dots']}}}"
         f".add{{fill:{c['add']}}}.rem{{fill:{c['rem']}}}.art{{fill:{c['art']}}}"
         f".cursor{{fill:{c['value']};animation:blink 1.1s steps(1) infinite}}"
         "@keyframes blink{50%{opacity:0}}text{white-space:pre}"
         f"{eye_css}</style>",
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}"/>',
         f'<path d="M0.5 {BAR}V12.5a12 12 0 0 1 12-12H{W - 12.5}a12 12 0 0 1 12 12V{BAR}z" fill="{c["bar"]}"/>',
         f'<line x1="0.5" y1="{BAR}" x2="{W - 0.5}" y2="{BAR}" stroke="{c["border"]}"/>']
    for i, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        o.append(f'<circle cx="{24 + i * 20}" cy="{BAR / 2}" r="6" fill="{col}"/>')
    o.append(f'<text x="{W / 2}" y="{BAR / 2 + 5}" text-anchor="middle" font-size="13" class="dots" '
             f'style="fill:{c["text"]};opacity:.7">{cfg["username"]} -- neofetch</text>')
    o.append(eye_markup)
    y0 = BAR + PAD + (body_h - info_h) / 2 + INFO_FS
    o.append(f'<g font-size="{INFO_FS}" xml:space="preserve">')
    for i, segs in enumerate(lines):
        if not segs:
            continue
        n = sum(len(t) for _, t in segs)
        spans = "".join(f'<tspan class="{k}">{escape(t)}</tspan>' for k, t in segs)
        o.append(f'<text x="{info_x:.1f}" y="{y0 + i * INFO_LH:.1f}" '
                 f'textLength="{n * INFO_FS * CW:.1f}">{spans}</text>')
    o.append("</g></svg>")
    return "\n".join(o) + "\n"


def main():
    cfg = json.loads((ROOT / "config.json").read_text())
    stats_file = ROOT / "cache" / "stats.json"
    stats = json.loads(stats_file.read_text()) if stats_file.exists() else {}
    for theme in THEMES:
        (ROOT / f"{theme}_mode.svg").write_text(render(theme, cfg, stats))


if __name__ == "__main__":
    main()
