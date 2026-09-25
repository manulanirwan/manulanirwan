#!/usr/bin/env python3
"""Refresh profile README stats SVGs and featured projects table."""

from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


USERNAME = os.environ.get("GITHUB_USERNAME", "manulanirwan")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
README = ROOT / "README.md"
FEATURED_FILE = ROOT / "featured-projects.json"

LANG_COLORS = {
    "Kotlin": "#7F52FF",
    "JavaScript": "#F7DF1E",
    "TypeScript": "#3178C6",
    "HTML": "#E34F26",
    "CSS": "#1572B6",
    "Python": "#3776AB",
    "Shell": "#89E051",
    "Java": "#B07219",
    "C": "#555555",
    "C++": "#F34B7D",
    "Go": "#00ADD8",
    "PHP": "#777BB4",
    "Ruby": "#701516",
    "Rust": "#DEA584",
    "Dart": "#00B4AB",
    "Swift": "#F05138",
    "Vue": "#41B883",
    "SCSS": "#C6538C",
    "Markdown": "#083FA1",
}

FALLBACK_COLORS = [
    "#00FF88",
    "#58A6FF",
    "#F778BA",
    "#FFA657",
    "#A371F7",
    "#39D353",
]


def request_json(url: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "manulanirwan-profile-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=context, timeout=45) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:400]}") from exc


def get_user() -> dict[str, Any]:
    return request_json(f"{API}/users/{USERNAME}")


def list_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while page <= 10:
        url = (
            f"{API}/users/{USERNAME}/repos"
            f"?per_page=100&page={page}&type=owner&sort=updated"
        )
        chunk = request_json(url)
        if not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return repos


def repo_languages(owner: str, name: str) -> dict[str, int]:
    return request_json(f"{API}/repos/{owner}/{name}/languages") or {}


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = request_json(GRAPHQL, {"query": query, "variables": variables})
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload.get("data") or {}


def lifetime_contributions(created_at: str) -> int:
    created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    total = 0
    year = created.year
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { totalContributions }
        }
      }
    }
    """
    while year <= now.year:
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        if start < created:
            start = created
        end = dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        if end > now:
            end = now
        data = graphql(
            query,
            {
                "login": USERNAME,
                "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        calendar = (
            data.get("user", {})
            .get("contributionsCollection", {})
            .get("contributionCalendar", {})
        )
        total += int(calendar.get("totalContributions") or 0)
        year += 1
    return total


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&")
        .replace("<", "<")
        .replace(">", ">")
        .replace('"', """)
    )


def build_stats_svg(public_repos: int, followers: int, following: int, contributions: int) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="195" viewBox="0 0 420 195" role="img" aria-label="GitHub stats">
  <rect width="420" height="195" rx="12" fill="#0D1117" stroke="#1F3A2E"/>
  <text x="22" y="34" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="15" font-weight="700" fill="#00FF88">Manula's GitHub stats</text>
  <g font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="13">
    <text x="22" y="72" fill="#8B949E">Public Repos</text>
    <text x="250" y="72" fill="#E6EDF3">{public_repos}</text>
    <text x="22" y="100" fill="#8B949E">Followers</text>
    <text x="250" y="100" fill="#E6EDF3">{followers}</text>
    <text x="22" y="128" fill="#8B949E">Following</text>
    <text x="250" y="128" fill="#E6EDF3">{following}</text>
    <text x="22" y="156" fill="#8B949E">Contributions</text>
    <text x="250" y="156" fill="#E6EDF3">{contributions}</text>
  </g>
  <circle cx="372" cy="36" r="8" fill="#00FF88"/>
</svg>
"""


def build_languages_svg(langs: list[tuple[str, float]]) -> str:
    bar_x = 22
    bar_w = 376
    segments = []
    offset = 0.0
    for name, pct in langs:
        width = max(2.0, bar_w * (pct / 100.0)) if pct >= 1 else max(1.5, bar_w * (pct / 100.0))
        color = LANG_COLORS.get(name, FALLBACK_COLORS[len(segments) % len(FALLBACK_COLORS)])
        rx = ' rx="5"' if offset == 0 else ""
        segments.append(
            f'<rect x="{bar_x + offset:.1f}" y="54" width="{width:.1f}" height="10"{rx} fill="{color}"/>'
        )
        offset += width

    rows = []
    y = 90
    for i, (name, pct) in enumerate(langs[:4]):
        color = LANG_COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        label = f"{pct:.0f}%" if pct >= 1 else "<1%"
        rows.append(
            f"""    <circle cx="28" cy="{y}" r="5" fill="{color}"/>
    <text x="42" y="{y + 5}" fill="#C9D1D9">{xml_escape(name)}</text>
    <text x="360" y="{y + 5}" fill="#8B949E">{label}</text>"""
        )
        y += 28

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="195" viewBox="0 0 420 195" role="img" aria-label="Top languages">
  <rect width="420" height="195" rx="12" fill="#0D1117" stroke="#1F3A2E"/>
  <text x="22" y="34" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="15" font-weight="700" fill="#00FF88">Top languages</text>
  <rect x="22" y="54" width="376" height="10" rx="5" fill="#161B22"/>
  {''.join(segments)}
  <g font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="13">
{chr(10).join(rows)}
  </g>
</svg>
"""


def top_languages(repos: list[dict[str, Any]]) -> list[tuple[str, float]]:
    totals: dict[str, int] = defaultdict(int)
    for repo in repos:
        if repo.get("fork") or repo.get("archived") or repo.get("private"):
            continue
        if repo.get("name") == USERNAME:
            continue
        langs = repo_languages(repo["owner"]["login"], repo["name"])
        for lang, bytes_count in langs.items():
            totals[lang] += int(bytes_count)
    grand = sum(totals.values())
    if grand <= 0:
        return [("Kotlin", 89.0), ("JavaScript", 10.0), ("TypeScript", 1.0), ("HTML", 0.4)]
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:4]
    return [(name, (count / grand) * 100.0) for name, count in ranked]


def load_featured() -> dict[str, Any]:
    if FEATURED_FILE.exists():
        return json.loads(FEATURED_FILE.read_text(encoding="utf-8"))
    return {"exclude": [USERNAME], "projects": []}


def featured_table(config: dict[str, Any], repos: list[dict[str, Any]]) -> str:
    by_name = {repo["name"]: repo for repo in repos}
    exclude = set(config.get("exclude") or [])
    exclude.add(USERNAME)
    rows = []
    seen = set()

    for item in config.get("projects") or []:
        name = item["name"]
        seen.add(name)
        repo = by_name.get(name, {})
        what = item.get("what") or repo.get("description") or "Project"
        live = item.get("live") or repo.get("homepage") or ""
        live_cell = f"[Demo]({live})" if live else "—"
        url = repo.get("html_url") or f"https://github.com/{USERNAME}/{name}"
        rows.append((name, url, what, live_cell))

    extras = []
    for repo in repos:
        name = repo.get("name")
        if not name or name in seen or name in exclude:
            continue
        if repo.get("fork") or repo.get("archived") or repo.get("private"):
            continue
        extras.append(repo)
    extras.sort(key=lambda r: r.get("pushed_at") or r.get("updated_at") or "", reverse=True)

    for repo in extras:
        name = repo["name"]
        what = repo.get("description") or "Public project"
        live = repo.get("homepage") or ""
        live_cell = f"[Demo]({live})" if live else "—"
        rows.append((name, repo["html_url"], what, live_cell))

    header = (
        "| Project | What it does | Live |\n"
        "| :--- | :--- | :---: |"
    )
    body = []
    for name, url, what, live_cell in rows:
        safe_what = what.replace("|", "-").replace("\n", " ").strip()
        body.append(f"| [{name}]({url}) | {safe_what} | {live_cell} |")
    return header + "\n" + "\n".join(body)


def replace_between(text: str, start: str, end: str, inner: str) -> str:
    if start not in text or end not in text:
        raise RuntimeError(f"Missing markers {start} / {end} in README.md")
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    return f"{before}{start}\n{inner}\n{end}{after}"


def patch_cache_bust(text: str, stamp: str) -> str:
    import re

    text = re.sub(r"([&?])cache_bust=\d+", rf"\1cache_bust={stamp}", text)
    if "cache_bust=" not in text:
        text = text.replace(
            "hide_border=true",
            f"hide_border=true&cache_bust={stamp}",
        )
        text = text.replace(
            "https://ghchart.rshah.org/00c853/manulanirwan",
            f"https://ghchart.rshah.org/00c853/manulanirwan?{stamp}",
        )
    else:
        text = re.sub(
            r"https://ghchart\.rshah\.org/00c853/manulanirwan(?:\?\d+)?",
            f"https://ghchart.rshah.org/00c853/manulanirwan?{stamp}",
            text,
        )
    return text


def main() -> int:
    if not TOKEN:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 1

    user = get_user()
    repos = list_repos()
    public_repos = int(user.get("public_repos") or 0)
    followers = int(user.get("followers") or 0)
    following = int(user.get("following") or 0)
    contributions = lifetime_contributions(user.get("created_at") or "2024-06-03T00:00:00Z")
    langs = top_languages(repos)

    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "stats-card.svg").write_text(
        build_stats_svg(public_repos, followers, following, contributions),
        encoding="utf-8",
    )
    (ASSETS / "languages.svg").write_text(build_languages_svg(langs), encoding="utf-8")

    featured = load_featured()
    table = featured_table(featured, repos)
    readme = README.read_text(encoding="utf-8")
    readme = replace_between(
        readme,
        "<!-- FEATURED-PROJECTS:START -->",
        "<!-- FEATURED-PROJECTS:END -->",
        table,
    )
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    readme = patch_cache_bust(readme, stamp)
    README.write_text(readme, encoding="utf-8")

    print(
        f"Updated stats: repos={public_repos} followers={followers} "
        f"following={following} contributions={contributions}"
    )
    print("Languages:", ", ".join(f"{n} {p:.1f}%" for n, p in langs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
