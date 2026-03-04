"""Awake Leaderboard -- category auto-detection.

Categorizes Python projects using rule-based keyword matching against
repo topics, description text, and repo name. No ML -- pure string
matching with tiered confidence.

Supported categories
--------------------
web-framework, cli-tool, data-science, devops, database, testing,
http, async, orm, api, ml, nlp, crypto, visualization, serialization,
logging, config, packaging, scraping, security, docs, gui, game, other

Public API
----------
- ``detect_category(topics, description, repo_name)`` -> str
- ``detect_category_with_confidence(topics, description, repo_name)`` -> dict
- ``list_categories()``                               -> list[str]
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Category definitions -- ordered by specificity (most specific first)
# ---------------------------------------------------------------------------

CATEGORIES: list[str] = [
    "web-framework",
    "cli-tool",
    "data-science",
    "devops",
    "database",
    "testing",
    "http",
    "async",
    "orm",
    "api",
    "ml",
    "nlp",
    "crypto",
    "visualization",
    "serialization",
    "logging",
    "config",
    "packaging",
    "scraping",
    "security",
    "docs",
    "gui",
    "game",
    "other",
]

# Rules: each entry is (category, topic_keywords, description_keywords)
# Topic keywords are matched against GitHub topics exactly (lowercased).
# Description keywords are matched as case-insensitive substrings.
_RULES: list[tuple[str, list[str], list[str]]] = [
    ("game", [
        "game", "pygame", "gamedev", "game-engine", "roguelike",
        "arcade", "godot",
    ], [
        "game engine", "game development", "2d game", "3d game",
        "pygame", "arcade game",
    ]),
    ("gui", [
        "gui", "tkinter", "pyqt", "pyside", "wxpython", "gtk",
        "desktop-app", "desktop-application", "tui", "terminal-ui",
    ], [
        "graphical user interface", "desktop app", "tkinter",
        "pyqt", "pyside", "wxpython", "textual", "rich tui",
    ]),
    ("ml", [
        "machine-learning", "deep-learning", "neural-network",
        "pytorch", "tensorflow", "keras", "sklearn", "scikit-learn",
        "xgboost", "lightgbm", "transformers", "diffusion",
    ], [
        "machine learning", "deep learning", "neural network",
        "neural net", "pytorch", "tensorflow", "transformer model",
        "large language model", "llm", "embedding",
    ]),
    ("nlp", [
        "nlp", "natural-language-processing", "text-processing",
        "tokenizer", "spacy", "nltk", "sentiment-analysis",
        "named-entity-recognition",
    ], [
        "natural language", "text processing", "tokeniz", "nlp",
        "sentiment", "named entity", "part-of-speech",
    ]),
    ("visualization", [
        "visualization", "plotting", "charts", "matplotlib",
        "seaborn", "plotly", "bokeh", "altair", "dashboard",
        "dataviz",
    ], [
        "visualization", "plotting", "charts", "matplotlib",
        "seaborn", "plotly", "bokeh", "bar chart", "line chart",
        "heatmap", "dashboard",
    ]),
    ("data-science", [
        "data-science", "data-analysis", "pandas", "numpy",
        "scipy", "jupyter", "notebook", "statistics",
        "data-engineering", "etl", "dataframe",
    ], [
        "data science", "data analysis", "dataframe", "pandas",
        "numpy", "scipy", "jupyter", "statistical", "analytics",
        "data pipeline", "etl",
    ]),
    ("web-framework", [
        "web-framework", "flask", "django", "fastapi", "starlette",
        "tornado", "sanic", "aiohttp", "bottle", "falcon",
        "pyramid", "web-server", "wsgi", "asgi",
    ], [
        "web framework", "http server", "wsgi", "asgi",
        "micro framework", "web application framework",
        "rest framework",
    ]),
    ("orm", [
        "orm", "sqlalchemy", "peewee", "tortoise-orm",
        "object-relational", "active-record",
    ], [
        "object relational", "orm", "sqlalchemy", "database models",
        "model mapper",
    ]),
    ("database", [
        "database", "sqlite", "postgresql", "mysql", "mongodb",
        "redis", "cassandra", "nosql", "sql", "db", "migration",
        "alembic",
    ], [
        "database", "sqlite", "postgresql", "mysql", "mongodb",
        "redis driver", "sql client", "db migration",
        "database migration",
    ]),
    ("http", [
        "http", "http-client", "requests", "httpx", "urllib",
        "rest-client", "api-client", "curl",
    ], [
        "http client", "rest client", "http requests",
        "api client", "curl", "fetch url",
    ]),
    ("scraping", [
        "web-scraping", "scraper", "crawler", "scrapy",
        "beautifulsoup", "playwright", "selenium", "spider",
    ], [
        "web scraping", "web crawler", "scraper", "scrapy",
        "beautifulsoup", "html parsing", "spider",
    ]),
    ("async", [
        "async", "asyncio", "aiohttp", "trio", "anyio",
        "concurrency", "coroutine", "event-loop",
    ], [
        "asyncio", "async/await", "event loop", "coroutine",
        "asynchronous", "concurrency",
    ]),
    ("api", [
        "api", "rest", "graphql", "grpc", "openapi", "swagger",
        "json-api", "webhook",
    ], [
        "rest api", "graphql", "openapi", "swagger",
        "grpc", "json api", "webhook",
    ]),
    ("devops", [
        "devops", "docker", "kubernetes", "ansible", "terraform",
        "ci-cd", "deployment", "infrastructure", "containers",
        "helm", "systemd",
    ], [
        "devops", "docker", "kubernetes", "ansible", "deployment",
        "infrastructure as code", "ci/cd", "container",
    ]),
    ("security", [
        "security", "cryptography", "ssl", "tls", "authentication",
        "authorization", "oauth", "jwt", "vulnerability",
        "penetration-testing", "firewall",
    ], [
        "security", "cryptography", "encryption", "ssl",
        "authentication", "authorization", "oauth", "jwt",
        "penetration test", "vulnerability scan",
    ]),
    ("crypto", [
        "crypto", "blockchain", "bitcoin", "ethereum", "web3",
        "defi", "nft", "smart-contract",
    ], [
        "blockchain", "bitcoin", "ethereum", "cryptocurrency",
        "smart contract", "web3", "defi",
    ]),
    ("testing", [
        "testing", "pytest", "unittest", "test", "coverage",
        "mock", "tdd", "bdd", "qa", "test-framework",
        "property-testing",
    ], [
        "testing framework", "unit test", "integration test",
        "test coverage", "mocking", "pytest plugin",
        "test runner",
    ]),
    ("logging", [
        "logging", "logger", "log", "monitoring", "tracing",
        "observability", "opentelemetry", "sentry",
    ], [
        "logging", "log management", "structured logging",
        "log aggregation", "tracing", "observability",
    ]),
    ("config", [
        "config", "configuration", "settings", "env",
        "dotenv", "yaml-config", "toml", "pydantic-settings",
    ], [
        "configuration management", "settings", "dotenv",
        "config file", "environment variables",
    ]),
    ("serialization", [
        "serialization", "json", "yaml", "toml", "msgpack",
        "protobuf", "pickle", "marshal", "avro",
    ], [
        "serialization", "json parser", "yaml parser",
        "data format", "msgpack", "protobuf", "schema",
    ]),
    ("docs", [
        "documentation", "docs", "sphinx", "mkdocs", "docstring",
        "typehints", "autodoc",
    ], [
        "documentation", "docs generator", "sphinx",
        "mkdocs", "api docs",
    ]),
    ("cli-tool", [
        "cli", "command-line", "terminal", "shell", "click",
        "argparse", "typer", "rich", "tqdm",
    ], [
        "command line", "command-line tool", "cli tool",
        "terminal app", "shell script",
    ]),
    ("packaging", [
        "packaging", "pip", "poetry", "setuptools", "wheel",
        "pypi", "package-manager", "build-tool",
    ], [
        "package manager", "pip", "python packaging",
        "build tool", "wheel", "pypi",
    ]),
]


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Split a string into lowercase tokens (words and hyphen-phrases)."""
    text = text.lower()
    return set(re.findall(r"[a-z][a-z0-9\-]*", text))


def detect_category_with_confidence(
    topics: str,
    description: str,
    repo_name: str = "",
) -> dict:
    """Detect the most likely category and return a confidence dict.

    Args:
        topics:      Comma-separated GitHub topics string.
        description: Repository description text.
        repo_name:   Repository name (used as a last-resort signal).

    Returns:
        Dict with keys: category (str), confidence (float 0-1),
        matched_topics (list), matched_keywords (list).
    """
    topic_list = [t.strip().lower() for t in topics.split(",") if t.strip()]
    topic_set = set(topic_list)
    desc_lower = (description + " " + repo_name).lower()

    best_category = "other"
    best_score = 0.0
    best_topics: list[str] = []
    best_keywords: list[str] = []

    for category, topic_keywords, desc_keywords in _RULES:
        matched_topics = [kw for kw in topic_keywords if kw in topic_set]
        matched_desc = [kw for kw in desc_keywords if kw in desc_lower]

        # Topics carry more weight (explicit GitHub labels)
        score = len(matched_topics) * 2.0 + len(matched_desc) * 1.0

        if score > best_score:
            best_score = score
            best_category = category
            best_topics = matched_topics
            best_keywords = matched_desc

    confidence = min(1.0, best_score / 4.0) if best_score > 0 else 0.0

    return {
        "category": best_category,
        "confidence": round(confidence, 2),
        "matched_topics": best_topics,
        "matched_keywords": best_keywords,
    }


def detect_category(
    topics: str,
    description: str,
    repo_name: str = "",
) -> str:
    """Detect and return the most likely category string.

    Convenience wrapper around ``detect_category_with_confidence``.

    Args:
        topics:      Comma-separated GitHub topics string.
        description: Repository description text.
        repo_name:   Repository name (optional extra signal).

    Returns:
        Category string, e.g. ``"web-framework"`` or ``"other"``.
    """
    return detect_category_with_confidence(topics, description, repo_name)["category"]


def list_categories() -> list[str]:
    """Return all supported category strings in alphabetical order."""
    return sorted(CATEGORIES)
