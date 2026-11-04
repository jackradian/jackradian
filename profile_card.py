#!/usr/bin/env python3
"""Draw a GitHub profile card (commits, PRs, issues + language pie) as an SVG.

Usage:  GITHUB_TOKEN=... python profile_card.py
        DEBUG=1 GITHUB_TOKEN=... python profile_card.py   # also print a per-repo report
No third-party packages needed.
"""
import colorsys
import datetime as dt
import hashlib
import html
import json
import math
import os
import sys
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN")
OUTPUT = "profile-card.svg"
TITLE = None                   # None = "<your name>'s GitHub Stats"
TOP_N = 9                      # None = show every language; a number = top N + "Other"
ROWS_PER_COLUMN = 7            # legend wraps into a new column after this many rows
IGNORED = set()                # languages to hide, e.g. {"HTML", "CSS"}
SKIPPED_REPOS = {"dqhouse"} #set()          # repo names to leave out, e.g. {"dotfiles"}
INCLUDE_PRIVATE = True         # count private repos (languages) and private contributions
INCLUDE_ARCHIVED = True        # count archived repos
INCLUDE_FORKS = False          # count forked repos
DEBUG = os.environ.get("DEBUG") == "1"

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


# ---------------------------------------------------------------- GitHub API

def _request(url, body=None):
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {TOKEN}"}
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers)) as r:
        return json.load(r)


def rest(url):
    return _request(url)


def graphql(query):
    result = _request("https://api.github.com/graphql", {"query": query})
    if result.get("errors"):
        sys.exit(f"GraphQL error: {result['errors']}")
    return result["data"]


def collect_stats():
    """Total commits (all years), PRs and issues for the token's owner."""
    me = graphql("""{ viewer { login name createdAt
                     pullRequests { totalCount } issues { totalCount } } }""")["viewer"]

    # contributionsCollection covers at most one year, so ask for every year at once
    first_year = int(me["createdAt"][:4])
    this_year = dt.datetime.now(dt.timezone.utc).year
    years = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", '
        f'to: "{y}-12-31T23:59:59Z") {{ totalCommitContributions restrictedContributionsCount }}'
        for y in range(first_year, this_year + 1))
    per_year = graphql(f"{{ viewer {{ {years} }} }}")["viewer"]

    commits = 0
    for key, c in sorted(per_year.items()):
        n = c["totalCommitContributions"]
        if INCLUDE_PRIVATE:
            n += c["restrictedContributionsCount"]
        commits += n
        if DEBUG:
            print(f"{key[1:]}: {n:,} commits")

    stats = {
        "name": me["name"] or me["login"],
        "commits": commits,
        "prs": me["pullRequests"]["totalCount"],
        "issues": me["issues"]["totalCount"],
    }
    if DEBUG:
        print(f"PRs: {stats['prs']:,}  Issues: {stats['issues']:,}\n")
    return stats


def collect_languages():
    totals, page = {}, 1
    skipped = {n.lower() for n in SKIPPED_REPOS}
    while True:
        # /user/repos = the token owner's repos, including private ones
        repos = rest(f"https://api.github.com/user/repos"
                     f"?per_page=100&page={page}&affiliation=owner&visibility=all")
        if not repos:
            break
        for repo in repos:
            reason = None
            if repo["name"].lower() in skipped:
                reason = "skipped"
            elif repo["fork"] and not INCLUDE_FORKS:
                reason = "fork"
            elif repo["archived"] and not INCLUDE_ARCHIVED:
                reason = "archived"
            elif repo["private"] and not INCLUDE_PRIVATE:
                reason = "private"
            langs = rest(repo["languages_url"]) if not reason or DEBUG else {}
            if DEBUG:
                tags = [t for t in ("private", "archived", "fork") if repo[t]]
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
    return totals


# ------------------------------------------------------------------- drawing

def slice_path(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if a1 - a0 > math.pi else 0
    return f"M{cx},{cy} L{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f} Z"


# Small line icons, drawn around (0, 0)
ICONS = {
    "commits": '<line x1="-9" y1="0" x2="-4" y2="0"/><circle r="4"/><line x1="4" y1="0" x2="9" y2="0"/>',
    "prs": ('<circle cx="-4" cy="-6" r="2.3"/><circle cx="-4" cy="6" r="2.3"/>'
            '<line x1="-4" y1="-3.7" x2="-4" y2="3.7"/><circle cx="5" cy="6" r="2.3"/>'
            '<path d="M5 3.7 V-3 Q5 -6 2 -6 H0.5"/><path d="M2.5 -8 L0.5 -6 L2.5 -4"/>'),
    "issues": '<circle r="7"/><circle r="1.6" class="dot"/>',
}


def draw_card(stats, totals):
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    if TOP_N is not None and len(items) > TOP_N:
        rest_size = sum(size for _, size in items[TOP_N:])
        items = items[:TOP_N] + [("Other", rest_size)]
    lang_total = sum(size for _, size in items) or 1

    # Layout: stats on the left, pie in the middle, legend on the right
    rows = max(1, min(len(items), ROWS_PER_COLUMN))
    cols = max(1, math.ceil(len(items) / ROWS_PER_COLUMN))
    row_h, col_w, legend_x, legend_top = 22, 165, 455, 80
    width = legend_x + cols * col_w
    height = max(240, legend_top + rows * row_h + 15)
    cx, r = 370, 62
    cy = 60 + (height - 60) / 2

    title = TITLE or f"{stats['name']}’s GitHub Stats"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height:.0f}" '
        f'viewBox="0 0 {width} {height:.0f}">',
        "<style>",
        "  .card{fill:#ffffff;stroke:#d0d7de} .title{fill:#2f80ed} .text{fill:#57606a}",
        "  .value{fill:#1f2328} .icon{fill:none;stroke:#2f80ed;stroke-width:1.6;stroke-linecap:round}",
        "  .icon .dot{fill:#2f80ed;stroke:none} .slice{stroke:#ffffff} .divider{stroke:#d0d7de}",
        "  @media (prefers-color-scheme: dark){",
        "    .card{fill:#0d1117;stroke:#30363d} .title{fill:#58a6ff} .text{fill:#8b949e}",
        "    .value{fill:#e6edf3} .icon{stroke:#58a6ff} .icon .dot{fill:#58a6ff}",
        "    .slice{stroke:#0d1117} .divider{stroke:#30363d} }",
        "  text{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif}",
        "</style>",
        f'<rect class="card" x="0.5" y="0.5" rx="10" width="{width - 1}" height="{height - 1:.0f}"/>',
        f'<text class="title" x="25" y="38" font-size="19" font-weight="600">{html.escape(title)}</text>',
    ]

    # --- stats column
    rows_y = [95, 140, 185]
    for (key, label), y in zip((("commits", "Total Commits"), ("prs", "Total PRs"),
                                ("issues", "Total Issues")), rows_y):
        out.append(f'<g class="icon" transform="translate(37,{y - 5})">{ICONS[key]}</g>')
        out.append(f'<text class="text" x="58" y="{y}" font-size="14">{label}</text>')
        out.append(f'<text class="value" x="265" y="{y}" font-size="15" font-weight="700" '
                   f'text-anchor="end">{stats[key]:,}</text>')
    out.append(f'<line class="divider" x1="290" y1="60" x2="290" y2="{height - 20:.0f}"/>')

    # --- languages
    out.append(f'<text class="text" x="310" y="68" font-size="13" font-weight="600">'
               f'Most Used Languages</text>')
    angle = -math.pi / 2
    for i, (lang, size) in enumerate(items):
        frac = size / lang_total
        color = COLORS.get(lang) or fallback_color(lang)
        if frac > 0.9999:
            out.append(f'<circle cx="{cx}" cy="{cy + 12:.1f}" r="{r}" fill="{color}"/>')
        else:
            end = angle + frac * 2 * math.pi
            out.append(f'<path class="slice" stroke-width="0.6" fill="{color}" '
                       f'd="{slice_path(cx, round(cy + 12, 1), r, angle, end)}"/>')
            angle = end
        x = legend_x + (i // ROWS_PER_COLUMN) * col_w
        y = legend_top + 15 + (i % ROWS_PER_COLUMN) * row_h
        pct = frac * 100
        label = f"{pct:.1f}%" if pct >= 0.1 else "<0.1%"
        out.append(f'<rect x="{x}" y="{y - 10}" width="11" height="11" rx="2" fill="{color}"/>')
        out.append(f'<text class="text" x="{x + 18}" y="{y}" font-size="13">'
                   f'{html.escape(f"{lang} {label}")}</text>')
    if not items:
        out.append(f'<text class="text" x="{cx}" y="{cy + 12:.0f}" font-size="13" '
                   f'text-anchor="middle">No languages found</text>')

    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("Set GITHUB_TOKEN to a personal access token")
    svg = draw_card(collect_stats(), collect_languages())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {OUTPUT}")
