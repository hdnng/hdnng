#!/usr/bin/env python3
"""Render dark_mode.svg / light_mode.svg from config.json, the ASCII eyes and cache/stats.json."""
import json
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
COLS = 56                      # width of the info column, in characters
INFO_FS, INFO_LH = 15, 24      # info font size / line height (px)
GAZE_T = 12.0                  # seconds in one loop of glances and blinks
FPS = 30                       # sampling rate of the eye animation
# where the irises look (seconds, dx, dy in px) and when the lids blink (start times)
GLANCES = [(0.0, 0, 0), (1.8, -20, 1), (3.4, 21, -2), (4.9, 14, -9), (7.0, -15, 8),
           (8.6, 4, 2), (9.4, 0, 0)]
BLINKS = [6.3, 10.2, 10.58]
SACCADE = 0.16                 # seconds for the irises to jump to a new spot
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


def gaze_at(t):
    """Iris offset at time t: hold each glance, jump to the next one quickly."""
    x, y = GLANCES[0][1:]
    for (t1, x1, y1) in GLANCES[1:]:
        if t >= t1:
            k = ease((t - t1) / SACCADE)
            x, y = x + (x1 - x) * k, y + (y1 - y) * k
    return x, y


def lid_at(t, close):
    """Upper lid drop at time t: follows the gaze a little, and closes fully on blinks."""
    drop = 0.35 * gaze_at(t)[1]
    for b in BLINKS:
        d = t - b
        if 0 <= d < 0.09:
            k = ease(d / 0.09)
        elif 0.09 <= d < 0.13:
            k = 1.0
        elif 0.13 <= d < 0.28:
            k = 1 - ease((d - 0.13) / 0.15)
        else:
            continue
        drop += (close - drop) * k
    return drop


def eyes_svg(c, eyes, ax, ay):
    """The animated eyes: static base, irises behind each opening, sliding upper lids."""
    cw, ch, base = eyes["cell_w"], eyes["cell_h"], eyes["baseline"]

    def text(rows, col, row, cls):
        return "".join(f'<text class="{cls}" x="{ax + col * cw:.2f}" y="{ay + (row + i) * ch + ch * base:.2f}" '
                       f'textLength="{len(r) * cw:.2f}">{escape(r)}</text>' for i, r in enumerate(rows) if r.strip())

    n = int(GAZE_T * FPS)
    times = [k / FPS for k in range(n)] + [GAZE_T]
    pct = lambda t: f"{t / GAZE_T * 100:.2f}%"
    close = eyes["eyes"][0]["close"]
    gz = "".join(f"{pct(t)}{{transform:translate({gaze_at(t)[0]:.1f}px,{gaze_at(t)[1]:.1f}px)}}" for t in times)
    ld = "".join(f"{pct(t)}{{transform:translateY({lid_at(t, close):.1f}px)}}" for t in times)
    css = (f".gz{{animation:gz {GAZE_T}s linear infinite}}@keyframes gz{{{gz}}}"
           f".ld{{animation:ld {GAZE_T}s linear infinite}}@keyframes ld{{{ld}}}"
           f".iris{{fill:{c['value']}}}"
           "@media (prefers-reduced-motion:reduce){.gz,.ld{animation:none}}")
    out = [f'<g class="art" font-size="{eyes["font_size"]}" font-weight="bold" xml:space="preserve">',
           text(eyes["base"], 0, 0, "art")]
    defs = []
    for k, e in enumerate(eyes["eyes"]):
        poly = " ".join(f"{ax + x:.1f},{ay + y:.1f}" for x, y in e["opening"])
        defs.append(f'<clipPath id="eye{k}"><polygon points="{poly}"/></clipPath>')
        ex, ey = ax + e["center"][0], ay + e["center"][1]
        lid = e["lid_curve"]
        cover = (" ".join(f"{ax + x:.1f},{ay + y:.1f}" for x, y in lid) +
                 f" {ax + lid[-1][0]:.1f},{ay + lid[-1][1] - 140:.1f} {ax + lid[0][0]:.1f},{ay + lid[0][1] - 140:.1f}")
        out.append(f'<g clip-path="url(#eye{k})"><g class="gz">'
                   f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{e["r_iris"] + 1:.1f}" fill="{c["bg"]}"/>'
                   + text(e["iris"]["rows"], e["iris"]["col"], e["iris"]["row"], "iris")
                   + text(e["pupil"]["rows"], e["pupil"]["col"], e["pupil"]["row"], "art") + "</g>"
                   f'<polygon class="ld" points="{cover}" fill="{c["bg"]}"/></g>')
        out.append(f'<g class="ld">' + text(e["lid"]["rows"], e["lid"]["col"], e["lid"]["row"], "art") + "</g>")
    out.append("</g>")
    return css, "<defs>" + "".join(defs) + "</defs>" + "".join(out)


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
    eyes = json.loads((ROOT / "assets" / "eyes.json").read_text())
    art_w, art_h = eyes["cols"] * eyes["cell_w"], eyes["rows"] * eyes["cell_h"]
    lines = info_lines(cfg, stats)
    info_w, info_h = COLS * INFO_FS * CW, len(lines) * INFO_LH
    body_h = max(art_h, info_h)
    W = round(PAD + art_w + PAD + info_w + PAD)
    H = round(BAR + PAD + body_h + PAD)
    info_x = PAD + art_w + PAD
    eye_css, eye_svg = eyes_svg(c, eyes, PAD, BAR + PAD + (body_h - art_h) / 2)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
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
    o.append(eye_svg)
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
