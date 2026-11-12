#!/usr/bin/env python3
"""Draw the neofetch-style profile card (dark_mode.svg, light_mode.svg).

Left: assets/portrait.jpg as ASCII art. Right: who I am plus live numbers from
the GitHub API (merged upstream PRs, projects contributed to, contributions).
Runs daily in .github/workflows/card.yml; run locally with GH_TOKEN set.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFilter, ImageOps

USER = "sherySJ"
# Work for my employer's upstreams counts as day-job work, not personal open source.
EXCLUDE_REPOS = {"danny-avila/LibreChat", "BerriAI/litellm"}
EXCLUDE_OWNERS = {USER.lower(), "aim2balance-ai"}
PORTRAIT = "assets/portrait.png"  # background removed with macOS Vision subject lifting
FACE_CROP = (92, 100, 422, 530)  # head and collar, same 0.77 aspect as the ASCII box
COLS, ROWS = 72, 46
RAMP = " .,:;i1tfLCG08@"

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


def ascii_art(path, dark):
    """The portrait has its background cut out (white). Dark features become dense characters."""
    img = Image.open(path).convert("L").crop(FACE_CROP)
    subject = img.point(lambda v: 255 if v < 248 else 0)  # everything that isn't the white background
    # Stretch tones using the head only, so the dark jacket doesn't wash the face out.
    head = subject.copy()
    ImageDraw.Draw(head).rectangle((0, int(head.height * 0.72), head.width, head.height), fill=0)
    img = ImageOps.equalize(img, mask=head).filter(ImageFilter.UnsharpMask(radius=4, percent=200, threshold=1))
    img = img.resize((COLS, ROWS), Image.LANCZOS)
    keep = subject.resize((COLS, ROWS), Image.LANCZOS)
    lines = []
    for y in range(ROWS):
        row = ""
        for x in range(COLS):
            if keep.getpixel((x, y)) < 110:
                row += " "
                continue
            density = (1 - img.getpixel((x, y)) / 255) ** 1.1
            row += RAMP[max(1, min(len(RAMP) - 1, int(density * len(RAMP))))]
        lines.append(row.rstrip())
    return lines


def stars(n):
    return f"{n / 1000:.1f}k★".replace(".0k", "k") if n >= 1000 else f"{n}★"


def info_lines(s):
    projects = " · ".join(f"{name} {stars(n)}" for name, n in s["projects"] if n >= 100)
    return [
        ("title", "sher@jan"),
        ("rule", ""),
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
        True: dict(bg="#161b22", text="#c9d1d9", key="#ffa657", value="#a5d6ff", dim="#616e7f"),
        False: dict(bg="#f6f8fa", text="#24292f", key="#953800", value="#0a3069", dim="#afb8c1"),
    }[dark]
    # Every line gets an exact textLength, so the layout holds whatever monospace font the viewer has.
    width, height, line_h, char_w = 985, 530, 20, 9
    x_ascii, x_info, info_w = 18, 425, 60
    out = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="Consolas,Menlo,\'DejaVu Sans Mono\',monospace" font-size="15" fill="{c["text"]}">',
        f"<style>.k{{fill:{c['key']}}}.v{{fill:{c['value']}}}.d{{fill:{c['dim']}}}text{{white-space:pre}}</style>",
        f'<rect width="{width}" height="{height}" fill="{c["bg"]}" rx="15"/>',
    ]

    def line(x, y, parts):
        n = sum(len(t) for t, _ in parts)
        spans = "".join(f'<tspan class="{cls}">{escape(t)}</tspan>' if cls else escape(t) for t, cls in parts)
        out.append(f'<text x="{x}" y="{y}" textLength="{n * char_w}" lengthAdjust="spacingAndGlyphs">{spans}</text>')

    # The portrait uses a finer grid than the text: 72 x 46 cells in a 382 x 500 box.
    for i, row in enumerate(ascii_art(os.path.join(ROOT, PORTRAIT), dark)):
        if row:
            out.append(
                f'<text x="{x_ascii}" y="{22 + i * 10.9:.1f}" font-size="9" textLength="{len(row) * 5.3:.1f}" '
                f'lengthAdjust="spacingAndGlyphs">{escape(row)}</text>'
            )
    y = 30
    for item in info_lines(s):
        kind = item[0]
        if kind == "title":
            line(x_info, y, [(item[1], "k"), (" " + "—" * (info_w - len(item[1]) - 1), "d")])
        elif kind == "section":
            head = f"— {item[1]} "
            line(x_info, y, [(head, ""), ("—" * (info_w - len(head)), "d")])
        elif kind == "kv":
            key, value = item[1], item[2]
            dots = " " + "." * max(1, info_w - len(key) - len(value) - 3) + " "
            line(x_info, y, [(key, "k"), (":", ""), (dots, "d"), (value, "v")])
        if kind != "rule":
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
