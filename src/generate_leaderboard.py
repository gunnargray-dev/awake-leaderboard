"""Awake Leaderboard -- static leaderboard.json generator.

Generates ``website/data/leaderboard.json`` from the seed list with
synthetic but plausible analysis scores.  Scores are deterministic --
the same seed list always produces the same JSON, so the output is
reproducible across machines.

Usage (standalone)::

    python -m src.generate_leaderboard            # writes website/data/leaderboard.json
    python -m src.generate_leaderboard -o out.json # custom output path

Usage (as library)::

    from src.generate_leaderboard import generate_leaderboard
    data = generate_leaderboard()                  # returns the dict
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.discovery import _SEED_PROJECTS
from src.models import compute_grade, compute_overall_score

# ---------------------------------------------------------------------------
# Project descriptions (short summaries for the website)
# ---------------------------------------------------------------------------

_DESCRIPTIONS: dict[str, str] = {
    "flask": "The Python micro framework for building web applications",
    "django": "The web framework for perfectionists with deadlines",
    "fastapi": "FastAPI framework, high performance, easy to learn, fast to code",
    "requests": "A simple, yet elegant, HTTP library",
    "httpx": "A next generation HTTP client for Python",
    "pandas": "Flexible and powerful data analysis / manipulation library",
    "numpy": "The fundamental package for scientific computing with Python",
    "scikit-learn": "Machine learning in Python",
    "matplotlib": "Comprehensive library for creating visualizations in Python",
    "poetry": "Python packaging and dependency management made easy",
    "pip": "The Python package installer",
    "pytest": "The pytest framework makes it easy to write small tests",
    "click": "Python composable command line interface toolkit",
    "typer": "Build great CLIs. Easy to code. Based on Python type hints.",
    "black": "The uncompromising Python code formatter",
    "ruff": "An extremely fast Python linter and code formatter",
    "pylint": "A static code analysis tool for Python",
    "mypy": "Optional static typing for Python",
    "pydantic": "Data validation using Python type annotations",
    "sqlalchemy": "The Database Toolkit for Python",
    "starlette": "The little ASGI framework that shines",
    "aiohttp": "Asynchronous HTTP client/server framework for asyncio",
    "celery": "Distributed Task Queue for Python",
    "sanic": "Accelerate your web app development. Build fast. Run fast.",
    "tornado": "Python web framework and asynchronous networking library",
    "scrapy": "A fast high-level web crawling & scraping framework",
    "Pillow": "Python Imaging Library (Fork)",
    "pyyaml": "Full-featured YAML framework for Python",
    "boto3": "AWS SDK for Python",
    "docker-py": "A Python library for the Docker Engine API",
    "ansible": "Radically simple IT automation platform",
    "salt": "Software to automate the management of any infrastructure",
    "paramiko": "The leading native Python SSHv2 protocol library",
    "rich": "Rich text and beautiful formatting in the terminal",
    "textual": "TUI framework for Python inspired by modern web development",
    "transformers": "State-of-the-art Machine Learning for PyTorch, TensorFlow, JAX",
    "pytorch": "Tensors and Dynamic neural networks with strong GPU acceleration",
    "keras": "Deep learning for humans",
    "langchain": "Build context-aware reasoning applications",
    "openai-python": "The official Python library for the OpenAI API",
    "cli": "A command-line HTTP client for the API era",
    "tqdm": "A fast, extensible progress bar for Python and CLI",
    "jinja": "A very fast and expressive template engine",
    "werkzeug": "The comprehensive WSGI web application library",
    "mitmproxy": "An interactive TLS-capable intercepting HTTP proxy",
    "locust": "Write scalable load tests in plain Python",
    "faker": "A Python package that generates fake data for you",
    "watchfiles": "Simple, modern file watching and code reload in Python",
    "arrow": "Better dates & times for Python",
    "dateutil": "Useful extensions to the standard Python datetime features",
    "open-webui": "User-friendly AI interface for running LLMs locally",
    "langflow": "Low-code app builder for RAG and multi-agent AI applications",
    "markitdown": "Python tool for converting various document formats to Markdown",
    "awesome-llm-apps": "A curated collection of awesome LLM apps built with RAG and AI agents",
    "yt-dlp": "A feature-rich command-line audio/video downloader",
}

# Approximate star counts for realistic rendering
_STARS: dict[str, int] = {
    "flask": 69200, "django": 82100, "fastapi": 80500,
    "requests": 52700, "httpx": 13800, "pandas": 44500,
    "numpy": 28400, "scikit-learn": 61000, "matplotlib": 20900,
    "poetry": 32200, "pip": 9800, "pytest": 12500,
    "click": 16000, "typer": 16500, "black": 39500,
    "ruff": 35800, "pylint": 5400, "mypy": 19000,
    "pydantic": 21800, "sqlalchemy": 10000, "starlette": 10400,
    "aiohttp": 15400, "celery": 25400, "sanic": 18200,
    "tornado": 21900, "scrapy": 53000, "Pillow": 12600,
    "pyyaml": 2500, "boto3": 9300, "docker-py": 7000,
    "ansible": 63500, "salt": 14300, "paramiko": 9100,
    "rich": 51000, "textual": 26200, "transformers": 140000,
    "pytorch": 86000, "keras": 62500, "langchain": 99000,
    "openai-python": 24500, "cli": 34200, "tqdm": 29000,
    "jinja": 10600, "werkzeug": 6800, "mitmproxy": 37500,
    "locust": 25200, "faker": 18100, "watchfiles": 2000,
    "arrow": 8800, "dateutil": 2300,
    "open-webui": 125600, "langflow": 145200,
    "markitdown": 90000, "awesome-llm-apps": 99400, "yt-dlp": 149500,
}

_FORKS: dict[str, int] = {
    "flask": 16500, "django": 32500, "fastapi": 6800,
    "requests": 9500, "httpx": 890, "pandas": 17900,
    "numpy": 10300, "scikit-learn": 25800, "matplotlib": 7800,
    "poetry": 2400, "pip": 3200, "pytest": 2700,
    "click": 2200, "typer": 700, "black": 2500,
    "ruff": 1300, "pylint": 1200, "mypy": 2900,
    "pydantic": 1950, "sqlalchemy": 1600, "starlette": 940,
    "aiohttp": 2050, "celery": 4800, "sanic": 1550,
    "tornado": 5600, "scrapy": 10700, "Pillow": 2400,
    "pyyaml": 520, "boto3": 1950, "docker-py": 1750,
    "ansible": 24000, "salt": 5600, "paramiko": 2000,
    "rich": 1750, "textual": 850, "transformers": 27500,
    "pytorch": 23000, "keras": 19700, "langchain": 15800,
    "openai-python": 3500, "cli": 1550, "tqdm": 1400,
    "jinja": 1700, "werkzeug": 1800, "mitmproxy": 4000,
    "locust": 3000, "faker": 2000, "watchfiles": 110,
    "arrow": 680, "dateutil": 520,
    "open-webui": 15000, "langflow": 21000,
    "markitdown": 5200, "awesome-llm-apps": 11000, "yt-dlp": 11800,
}

# ---------------------------------------------------------------------------
# Category display names (nicer labels for the website)
# ---------------------------------------------------------------------------

_CATEGORY_DISPLAY: dict[str, str] = {
    "web-framework": "Web Frameworks",
    "http-client": "HTTP",
    "data-science": "Data Science",
    "package-manager": "DevOps",
    "testing": "Testing",
    "cli-framework": "CLI Tools",
    "code-quality": "DevOps",
    "type-checker": "DevOps",
    "data-validation": "Data Science",
    "database": "Databases",
    "task-queue": "Async",
    "web-scraping": "HTTP",
    "image-processing": "Data Science",
    "serialization": "Utilities",
    "cloud-sdk": "DevOps",
    "devops": "DevOps",
    "networking": "Networking",
    "cli-tool": "CLI Tools",
    "template-engine": "Web Frameworks",
    "machine-learning": "ML/AI",
    "ai-framework": "ML/AI",
    "tui-framework": "CLI Tools",
    "utilities": "Utilities",
}


# ---------------------------------------------------------------------------
# Deterministic score generation
# ---------------------------------------------------------------------------


def _hash_score(owner: str, repo: str, dimension: str) -> float:
    """Generate a deterministic 0-100 score from a project+dimension key.

    Uses SHA-256 so the output looks random but is perfectly reproducible.
    """
    h = hashlib.sha256(f"{owner}/{repo}:{dimension}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF * 100.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def generate_scores(owner: str, repo: str) -> dict:
    """Return synthetic dimension scores and composite for one project.

    Scores cluster in a realistic 55-98 range. The hash-based approach
    ensures determinism while spreading projects across the grade curve.
    """
    raw_health = _hash_score(owner, repo, "health")
    raw_complexity = _hash_score(owner, repo, "complexity")
    raw_security = _hash_score(owner, repo, "security")
    raw_dead_code = _hash_score(owner, repo, "dead_code")
    raw_coverage = _hash_score(owner, repo, "coverage")

    # Map raw [0-100] into realistic ranges
    health = _clamp(55 + raw_health * 0.43, 55, 98)
    complexity = _clamp(52 + raw_complexity * 0.46, 52, 98)
    security = _clamp(58 + raw_security * 0.40, 58, 98)
    dead_code = _clamp(raw_dead_code * 0.35, 0, 35)  # percent dead code
    coverage = _clamp(55 + raw_coverage * 0.43, 55, 98)

    # dead_code_pct as fraction for compute_overall_score
    dead_code_pct = dead_code / 100.0

    overall = compute_overall_score(
        health=health,
        complexity=complexity,
        security=security,
        dead_code_pct=dead_code_pct,
        coverage_pct=coverage,
    )
    overall = round(overall, 1)
    grade = compute_grade(overall)

    # For the website JSON, dead_code dimension = inverted score (100 - pct*100)
    dead_code_display = round(max(0, 100 - dead_code), 1)

    return {
        "health": round(health, 1),
        "complexity": round(complexity, 1),
        "security": round(security, 1),
        "dead_code": round(dead_code_display, 1),
        "coverage": round(coverage, 1),
        "overall": overall,
        "grade": grade,
    }


# ---------------------------------------------------------------------------
# Leaderboard generation
# ---------------------------------------------------------------------------


def generate_leaderboard() -> dict:
    """Build the full leaderboard data structure from the seed list.

    Returns a dict matching the ``website/data/leaderboard.json`` schema.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    projects = []

    for owner, repo, category in _SEED_PROJECTS:
        scores = generate_scores(owner, repo)
        display_cat = _CATEGORY_DISPLAY.get(category, category)

        projects.append({
            "name": repo,
            "owner": owner,
            "description": _DESCRIPTIONS.get(repo, ""),
            "score": scores["overall"],
            "grade": scores["grade"],
            "stars": _STARS.get(repo, 1000),
            "forks": _FORKS.get(repo, 100),
            "language": "Python",
            "category": display_cat,
            "last_analyzed": now,
            "dimensions": {
                "health": scores["health"],
                "complexity": scores["complexity"],
                "security": scores["security"],
                "dead_code": scores["dead_code"],
                "coverage": scores["coverage"],
            },
        })

    # Sort by score descending and assign ranks
    projects.sort(key=lambda p: p["score"], reverse=True)
    for i, p in enumerate(projects, 1):
        p["rank"] = i

    return {
        "metadata": {
            "generated_at": now,
            "total_projects": len(projects),
            "version": "1.1.0",
        },
        "projects": projects,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = Path("website/data/leaderboard.json")


def main(argv: Optional[list[str]] = None) -> None:
    """Generate leaderboard.json and write it to disk."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate website/data/leaderboard.json from seed data",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    data = generate_leaderboard()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")

    total = data["metadata"]["total_projects"]
    scores = [p["score"] for p in data["projects"]]
    avg = sum(scores) / len(scores)
    print(f"Generated {args.output} with {total} projects (avg score: {avg:.1f})")


if __name__ == "__main__":
    main()
