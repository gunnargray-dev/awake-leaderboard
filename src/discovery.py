"""Awake Leaderboard -- project discovery engine.

Finds notable open-source projects to analyze and add to the leaderboard.
Uses the GitHub REST API (no auth token required for public data, but
rate-limited to 60 req/hr without one).

Discovery strategies
--------------------
1. Top Python repos by star count
2. Trending repos (via GitHub search sorted by stars + recently pushed)
3. Curated seed list of well-known projects

Public API
----------
- ``discover_top_repos(language, limit)``   -- top repos by stars
- ``discover_trending(language, limit)``    -- recently active + popular
- ``get_seed_projects()``                   -- curated starter list
- ``fetch_repo_metadata(owner, repo)``      -- full metadata for one repo
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# GitHub API helpers (stdlib only)
# ---------------------------------------------------------------------------

_GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "Awake-Leaderboard/1.0",
}


def _github_get(
    path: str,
    params: Optional[dict] = None,
    token: Optional[str] = None,
) -> dict:
    """Make a GET request to the GitHub API. Returns parsed JSON."""
    url = f"{_GITHUB_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    headers = dict(_HEADERS)
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": str(exc), "status": exc.code}


def _parse_repo(item: dict) -> dict:
    """Extract relevant fields from a GitHub repo API response."""
    return {
        "owner": item.get("owner", {}).get("login", ""),
        "repo": item.get("name", ""),
        "url": item.get("html_url", ""),
        "description": (item.get("description") or "")[:500],
        "language": item.get("language") or "",
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "open_issues": item.get("open_issues_count", 0),
        "topics": ",".join(item.get("topics", [])),
        "created_at": item.get("created_at", ""),
        "last_pushed": item.get("pushed_at", ""),
    }


# ---------------------------------------------------------------------------
# Discovery strategies
# ---------------------------------------------------------------------------


def discover_top_repos(
    language: str = "Python",
    limit: int = 30,
    token: Optional[str] = None,
) -> list[dict]:
    """Find top repos by star count for a given language.

    Uses GitHub search API: ``/search/repositories?q=language:X&sort=stars``
    Limited to ``limit`` results (max 100 per page).
    """
    per_page = min(limit, 100)
    data = _github_get(
        "/search/repositories",
        params={
            "q": f"language:{language} stars:>1000",
            "sort": "stars",
            "order": "desc",
            "per_page": str(per_page),
        },
        token=token,
    )
    if "error" in data:
        return []

    items = data.get("items", [])
    return [_parse_repo(item) for item in items[:limit]]


def discover_trending(
    language: str = "Python",
    limit: int = 30,
    days: int = 30,
    token: Optional[str] = None,
) -> list[dict]:
    """Find recently active popular repos.

    Searches for repos pushed in the last ``days`` days with > 500 stars,
    sorted by stars descending.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%d")

    per_page = min(limit, 100)
    data = _github_get(
        "/search/repositories",
        params={
            "q": f"language:{language} stars:>500 pushed:>{cutoff}",
            "sort": "stars",
            "order": "desc",
            "per_page": str(per_page),
        },
        token=token,
    )
    if "error" in data:
        return []

    items = data.get("items", [])
    return [_parse_repo(item) for item in items[:limit]]


def fetch_repo_metadata(
    owner: str,
    repo: str,
    token: Optional[str] = None,
) -> Optional[dict]:
    """Fetch full metadata for a specific repo."""
    data = _github_get(f"/repos/{owner}/{repo}", token=token)
    if "error" in data:
        return None
    return _parse_repo(data)


# ---------------------------------------------------------------------------
# Seed list -- well-known Python projects
# ---------------------------------------------------------------------------

_SEED_PROJECTS: list[tuple[str, str, str]] = [
    # (owner, repo, category)
    ("pallets", "flask", "web-framework"),
    ("django", "django", "web-framework"),
    ("fastapi", "fastapi", "web-framework"),
    ("psf", "requests", "http-client"),
    ("encode", "httpx", "http-client"),
    ("pandas-dev", "pandas", "data-science"),
    ("numpy", "numpy", "data-science"),
    ("scikit-learn", "scikit-learn", "data-science"),
    ("matplotlib", "matplotlib", "data-science"),
    ("python-poetry", "poetry", "package-manager"),
    ("pypa", "pip", "package-manager"),
    ("pytest-dev", "pytest", "testing"),
    ("pallets", "click", "cli-framework"),
    ("tiangolo", "typer", "cli-framework"),
    ("psf", "black", "code-quality"),
    ("astral-sh", "ruff", "code-quality"),
    ("PyCQA", "pylint", "code-quality"),
    ("python", "mypy", "type-checker"),
    ("pydantic", "pydantic", "data-validation"),
    ("sqlalchemy", "sqlalchemy", "database"),
    ("encode", "starlette", "web-framework"),
    ("aio-libs", "aiohttp", "http-client"),
    ("celery", "celery", "task-queue"),
    ("huge-success", "sanic", "web-framework"),
    ("tornadoweb", "tornado", "web-framework"),
    ("scrapy", "scrapy", "web-scraping"),
    ("python-pillow", "Pillow", "image-processing"),
    ("yaml", "pyyaml", "serialization"),
    ("boto", "boto3", "cloud-sdk"),
    ("docker", "docker-py", "devops"),
    ("ansible", "ansible", "devops"),
    ("saltstack", "salt", "devops"),
    ("paramiko", "paramiko", "networking"),
    ("Textualize", "rich", "cli-framework"),
    ("Textualize", "textual", "tui-framework"),
    ("huggingface", "transformers", "machine-learning"),
    ("pytorch", "pytorch", "machine-learning"),
    ("keras-team", "keras", "machine-learning"),
    ("langchain-ai", "langchain", "ai-framework"),
    ("openai", "openai-python", "ai-framework"),
    ("httpie", "cli", "cli-tool"),
    ("tqdm", "tqdm", "cli-tool"),
    ("pallets", "jinja", "template-engine"),
    ("pallets", "werkzeug", "web-framework"),
    ("mitmproxy", "mitmproxy", "networking"),
    ("locustio", "locust", "testing"),
    ("joke2k", "faker", "testing"),
    ("samuelcolvin", "watchfiles", "devops"),
    ("arrow-py", "arrow", "utilities"),
    ("dateutil", "dateutil", "utilities"),
]


def get_seed_projects() -> list[dict]:
    """Return the curated seed list as dicts ready for discovery."""
    return [
        {
            "owner": owner,
            "repo": repo,
            "category": category,
            "url": f"https://github.com/{owner}/{repo}",
        }
        for owner, repo, category in _SEED_PROJECTS
    ]
