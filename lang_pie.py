#!/usr/bin/env python3
"""Draw an SVG pie chart of the languages used across your public GitHub repos.

Usage:  python lang_pie.py YOUR_USERNAME
   or:  GH_USERNAME=you GITHUB_TOKEN=... python lang_pie.py
No third-party packages needed.
"""
import colorsys
import hashlib
import html
import json
import math
import os
import sys
import urllib.request

USERNAME = os.environ.get("GH_USERNAME") or (sys.argv[1] if len(sys.argv) > 1 else None)
TOKEN = os.environ.get("GITHUB_TOKEN")
OUTPUT = "languages.svg"
TOP_N = None                   # None = show every language; a number = top N + "Other"
ROWS_PER_COLUMN = 8            # legend wraps into a new column after this many rows
IGNORED = set()                # e.g. {"HTML", "CSS", "Jupyter Notebook"}
SKIPPED_REPOS = {"dqhouse"} # set()          # repo names to leave out, e.g. {"dotfiles", "old-homework"}
INCLUDE_PRIVATE = True         # count private repos
INCLUDE_ARCHIVED = True        # count archived repos (github-readme-stats counts them)
DEBUG = os.environ.get("DEBUG") == "1"   # print a per-repo report

# GitHub's own language colors for common languages
COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Java": "#b07219", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Go": "#00ADD8", "Rust": "#dea584", "Ruby": "#701516", "PHP": "#4F5D95",
    "Swift": "#F05138", "Kotlin": "#A97BFF", "Shell": "#89e051",
    "HTML": "#e34c26", "CSS": "#563d7c", "Dart": "#00B4AB", "Vue": "#41b883",
    "Jupyter Notebook": "#DA5B0B", "Lua": "#000080", "Svelte": "#ff3e00",
    "Blade": "#f7523f", "SCSS": "#c6538c", "Other": "#8b949e",
}


def fallback_color(lang):
    """Stable color for languages not in COLORS (same language = same color every run)."""
    hue = int(hashlib.md5(lang.encode()).hexdigest(), 16) % 360 / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.65)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def api(url):
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as r:
        return json.load(r)


def collect_languages():
    totals, page = {}, 1
    while True:
        # /user/repos = the token owner's repos, including private ones
        repos = api(f"https://api.github.com/user/repos"
                    f"?per_page=100&page={page}&affiliation=owner&visibility=all")
        if not repos:
            break
        for repo in repos:
            reason = None
            if repo["name"].lower() in {n.lower() for n in SKIPPED_REPOS}:
                reason = "skipped"
            elif repo["fork"]:
                reason = "fork"
            elif repo["archived"] and not INCLUDE_ARCHIVED:
                reason = "archived"
            elif repo["private"] and not INCLUDE_PRIVATE:
                reason = "private"
            langs = api(repo["languages_url"]) if not reason or DEBUG else {}
            if DEBUG:
                tags = [t for t, on in (("private", repo["private"]),
                                         ("archived", repo["archived"]),
                                         ("fork", repo["fork"])) if on]
                top = ", ".join(f"{k} {v:,}" for k, v in
                                sorted(langs.items(), key=lambda kv: -kv[1])[:3])
                status = f"SKIPPED ({reason})" if reason else "counted"
                print(f"{repo['full_name']:40} [{' '.join(tags) or 'public'}] "
                      f"{status:20} {top or '(no languages)'}")
            if reason:
                continue
            for lang, size in langs.items():
                if lang not in IGNORED:
                    totals[lang] = totals.get(lang, 0) + size
        page += 1
    if DEBUG:
        total = sum(totals.values()) or 1
        print("\nTotals (bytes):")
        for lang, size in sorted(totals.items(), key=lambda kv: -kv[1]):
            print(f"  {lang:20} {size:>12,}  {size / total * 100:5.1f}%")
    return totals


def slice_path(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if a1 - a0 > math.pi else 0
    return f"M{cx},{cy} L{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f} Z"


def draw(totals):
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    if TOP_N is not None and len(items) > TOP_N:
        rest = sum(size for _, size in items[TOP_N:])
        items = items[:TOP_N] + [("Other", rest)]
    total = sum(size for _, size in items) or 1

    rows = min(len(items), ROWS_PER_COLUMN) or 1
    cols = math.ceil(len(items) / ROWS_PER_COLUMN) or 1
    col_w, row_h, legend_x, legend_y = 170, 22, 250, 70
    width = legend_x + cols * col_w
    height = max(250, legend_y + rows * row_h + 10)
    cx, cy, r = 120, max(135, height / 2 + 12), 90

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height:.0f}" '
        f'viewBox="0 0 {width} {height:.0f}">',
        '<style>text{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;fill:#8b949e}</style>',
        '<text x="20" y="28" font-size="16" font-weight="600">Most Used Languages</text>',
    ]
    angle = -math.pi / 2  # start at 12 o'clock
    for i, (lang, size) in enumerate(items):
        frac = size / total
        color = COLORS.get(lang) or fallback_color(lang)
        if frac > 0.9999:  # a single language fills the whole circle
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')
        else:
            end = angle + frac * 2 * math.pi
            parts.append(f'<path d="{slice_path(cx, cy, r, angle, end)}" fill="{color}" '
                         f'stroke="#ffffff" stroke-width="0.5"/>')
            angle = end
        x = legend_x + (i // ROWS_PER_COLUMN) * col_w
        y = legend_y + (i % ROWS_PER_COLUMN) * row_h
        pct = frac * 100
        label = f"{pct:.1f}%" if pct >= 0.1 else "<0.1%"
        parts.append(f'<rect x="{x}" y="{y - 11}" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{x + 20}" y="{y}" font-size="13">'
                     f'{html.escape(f"{lang} {label}")}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("Set GITHUB_TOKEN to a token that can read your private repos")
    svg = draw(collect_languages())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {OUTPUT}")
