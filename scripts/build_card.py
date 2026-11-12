#!/usr/bin/env python3
"""Draw the terminal-style profile card (dark_mode.svg, light_mode.svg).

Who I am plus live numbers from the GitHub API (merged upstream PRs,
projects contributed to, contributions).
Runs daily in .github/workflows/card.yml; run locally with GH_TOKEN set.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

USER = "sherySJ"
# Work for my employer's upstreams counts as day-job work, not personal open source.
EXCLUDE_REPOS = {"danny-avila/LibreChat", "BerriAI/litellm"}
EXCLUDE_OWNERS = {USER.lower(), "aim2balance-ai"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(body["errors"])
    return body["data"]


def stats():
    user = gql(
        """query($u:String!){user(login:$u){createdAt
        contributionsCollection{contributionCalendar{totalContributions}}}}""",
        u=USER,
    )["user"]
    prs, cursor = [], None
    while True:
        page = gql(
            """query($q:String!,$c:String){search(query:$q,type:ISSUE,first:100,after:$c){
            pageInfo{hasNextPage endCursor}
            nodes{...on PullRequest{repository{nameWithOwner stargazerCount owner{login}}}}}}""",
            q=f"author:{USER} is:pr is:merged", c=cursor,
        )["search"]
        prs += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    upstream = [
        p["repository"] for p in prs
        if p["repository"]["owner"]["login"].lower() not in EXCLUDE_OWNERS
        and p["repository"]["nameWithOwner"] not in EXCLUDE_REPOS
    ]
    projects = {}
    for r in upstream:
        name = r["nameWithOwner"].split("/")[1]
        projects[name] = r["stargazerCount"]
    years = (datetime.now(timezone.utc) - datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))).days // 365
    return {
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "merged": len(upstream),
        "projects": sorted(projects.items(), key=lambda kv: -kv[1]),
        "years": years,
    }


def stars(n):
    return f"{n / 1000:.1f}k★".replace(".0k", "k") if n >= 1000 else f"{n}★"


def info_lines(s):
    projects = " · ".join(f"{name} {stars(n)}" for name, n in s["projects"] if n >= 100)
    return [
        ("section", "About"),
        ("kv", "Role", "Platform & security engineer, AI chat product"),
        ("kv", "Focus", "Agent tooling · MCP servers · AI security"),
        ("kv", "Building", "Saveyard, a local-first archive for what you save"),
        ("kv", "Stack", "TypeScript · Python · Swift · Docker"),
        ("kv", "Location", "Islamabad, PK · open to remote roles"),
        ("blank",),
        ("section", "Open source"),
        ("kv", "Upstream PRs merged", str(s["merged"])),
        ("kv", "Contributed to", projects),
        ("blank",),
        ("section", "Contact"),
        ("kv", "LinkedIn", "in/sher-jan"),
        ("kv", "GitHub", f"@{USER}"),
        ("blank",),
        ("section", "GitHub stats"),
        ("kv", "Contributions (last year)", f"{s['contributions']:,}"),
        ("kv", "On GitHub", f"{s['years']} years"),
    ]


def svg(s, dark):
    c = {
        True: dict(bg="#161b22", bar="#21262d", border="#30363d", text="#c9d1d9",
                   key="#ffa657", value="#a5d6ff", dim="#484f58", title="#8b949e"),
        False: dict(bg="#ffffff", bar="#f6f8fa", border="#d0d7de", text="#24292f",
                    key="#953800", value="#0a3069", dim="#d0d7de", title="#57606a"),
    }[dark]
    # Every line gets an exact textLength, so the layout holds whatever monospace font the viewer has.
    pad, bar_h, line_h, char_w, info_w = 30, 38, 22, 9, 60
    lines = info_lines(s)
    width = pad * 2 + info_w * char_w
    height = bar_h + 26 + len(lines) * line_h + 10
    out = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="Consolas,Menlo,\'DejaVu Sans Mono\',monospace" font-size="15" fill="{c["text"]}">',
        f"<style>.k{{fill:{c['key']}}}.v{{fill:{c['value']}}}.d{{fill:{c['dim']}}}text{{white-space:pre}}</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}"/>',
        f'<path d="M0.5 {bar_h} V12.5 a12 12 0 0 1 12 -12 H{width - 12.5} a12 12 0 0 1 12 12 V{bar_h} Z" fill="{c["bar"]}"/>',
        f'<line x1="0.5" y1="{bar_h}" x2="{width - 0.5}" y2="{bar_h}" stroke="{c["border"]}"/>',
    ]
    for i, dot in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        out.append(f'<circle cx="{22 + i * 20}" cy="{bar_h / 2}" r="6" fill="{dot}"/>')
    out.append(
        f'<text x="{width / 2}" y="{bar_h / 2 + 5}" text-anchor="middle" font-size="13" fill="{c["title"]}">'
        f"sher@jan: ~</text>"
    )

    def line(y, parts):
        n = sum(len(t) for t, _ in parts)
        spans = "".join(f'<tspan class="{cls}">{escape(t)}</tspan>' if cls else escape(t) for t, cls in parts)
        out.append(f'<text x="{pad}" y="{y}" textLength="{n * char_w}" lengthAdjust="spacingAndGlyphs">{spans}</text>')

    y = bar_h + 30
    for item in lines:
        kind = item[0]
        if kind == "section":
            head = f"— {item[1]} "
            line(y, [(head, ""), ("—" * (info_w - len(head)), "d")])
        elif kind == "kv":
            key, value = item[1], item[2]
            dots = " " + "." * max(1, info_w - len(key) - len(value) - 3) + " "
            line(y, [(key, "k"), (":", ""), (dots, "d"), (value, "v")])
        y += line_h
    out.append("</svg>")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("set GH_TOKEN or GITHUB_TOKEN")
    data = stats()
    for dark, name in ((True, "dark_mode.svg"), (False, "light_mode.svg")):
        with open(os.path.join(ROOT, name), "w") as f:
            f.write(svg(data, dark))
    print(json.dumps(data))
