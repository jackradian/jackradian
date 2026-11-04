#!/usr/bin/env python3
"""Draw an SVG pie chart of the languages used across your public GitHub repos.

Usage:  python lang_pie.py YOUR_USERNAME
   or:  GH_USERNAME=you GITHUB_TOKEN=... python lang_pie.py
No third-party packages needed.
"""
import html
import json
import math
import os
import sys
import urllib.request

USERNAME = os.environ.get("GH_USERNAME") or (sys.argv[1] if len(sys.argv) > 1 else None)
TOKEN = os.environ.get("GITHUB_TOKEN")
OUTPUT = "languages.svg"
TOP_N = 6                      # languages shown individually; the rest become "Other"
IGNORED = set()                # e.g. {"HTML", "CSS", "Jupyter Notebook"}

# GitHub's own language colors for common languages
COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Java": "#b07219", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Go": "#00ADD8", "Rust": "#dea584", "Ruby": "#701516", "PHP": "#4F5D95",
    "Swift": "#F05138", "Kotlin": "#A97BFF", "Shell": "#89e051",
    "HTML": "#e34c26", "CSS": "#563d7c", "Dart": "#00B4AB", "Vue": "#41b883",
    "Jupyter Notebook": "#DA5B0B", "Lua": "#000080", "Other": "#8b949e",
}
FALLBACK = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0"]


def api(url):
    headers = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as r:
        return json.load(r)


def collect_languages():
    totals, page = {}, 1
    while True:
        repos = api(f"https://api.github.com/user/repos"
            f"?per_page=100&page={page}&affiliation=owner&visibility=all")
        if not repos:
            break
        for repo in repos:
            if repo["fork"] or repo["archived"]:
                continue
            for lang, size in api(repo["languages_url"]).items():
                if lang not in IGNORED:
                    totals[lang] = totals.get(lang, 0) + size
        page += 1
    return totals


def slice_path(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if a1 - a0 > math.pi else 0
    return f"M{cx},{cy} L{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f} Z"


def draw(totals):
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top = items[:TOP_N]
    rest = sum(size for _, size in items[TOP_N:])
    if rest:
        top.append(("Other", rest))
    total = sum(size for _, size in top) or 1

    cx, cy, r = 120, 135, 90
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="250" viewBox="0 0 420 250">',
        '<style>text{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;fill:#8b949e}</style>',
        '<text x="20" y="28" font-size="16" font-weight="600">Most Used Languages</text>',
    ]
    angle = -math.pi / 2  # start at 12 o'clock
    for i, (lang, size) in enumerate(top):
        frac = size / total
        color = COLORS.get(lang, FALLBACK[i % len(FALLBACK)])
        if frac > 0.9999:  # a single language fills the whole circle
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')
        else:
            end = angle + frac * 2 * math.pi
            parts.append(f'<path d="{slice_path(cx, cy, r, angle, end)}" fill="{color}" '
                         f'stroke="#ffffff" stroke-width="1"/>')
            angle = end
        y = 70 + i * 24  # legend row
        parts.append(f'<rect x="250" y="{y - 11}" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="270" y="{y}" font-size="13">'
                     f'{html.escape(lang)} {frac * 100:.1f}%</text>')
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    if not USERNAME:
        sys.exit("Give a username: python lang_pie.py YOUR_USERNAME")
    svg = draw(collect_languages())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {OUTPUT}")
