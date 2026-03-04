"""Awake Leaderboard -- JSON API layer.

Pure functions that return JSON-serialisable dicts. Not a web server --
these are the data functions that a future HTTP layer (Flask, FastAPI, etc.)
would call. Each function opens and closes its own DB connection.

Public API
----------
- ``get_leaderboard_json(db_path, limit, category, sort_by)``
- ``get_project_json(db_path, owner, repo)``
- ``get_trends_json(db_path, owner, repo)``
- ``get_comparison_json(db_path, owner1, repo1, owner2, repo2)``
- ``get_categories_json(db_path)``
- ``get_stats_json(db_path)``
- ``get_digest_json(db_path, session)``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.models import init_db, get_leaderboard, get_project, get_stats
from src.trends import get_trend_summary, get_movers
from src.compare import compare_from_db
from src.categories import list_categories
from src.digest import build_digest_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open(db_path: str | Path):
    """Open a read/write database connection."""
    return init_db(db_path)


# ---------------------------------------------------------------------------
# API functions
# ---------------------------------------------------------------------------


def get_leaderboard_json(
    db_path: str | Path,
    limit: int = 100,
    category: str = "",
    sort_by: str = "overall_score",
    offset: int = 0,
) -> list[dict]:
    """Return the ranked leaderboard as a list of JSON-serialisable dicts.

    Args:
        db_path:  Path to the SQLite database file.
        limit:    Maximum number of rows to return.
        category: Filter by category slug, or ``""`` for all.
        sort_by:  Column to sort by. One of: overall_score, health_score,
                  complexity_score, security_score, stars.
        offset:   Row offset for pagination.

    Returns:
        List of project dicts, each enriched with rank (1-indexed).
    """
    conn = _open(db_path)
    try:
        rows = get_leaderboard(conn, category=category, limit=limit,
                               offset=offset, sort_by=sort_by)
        return [{"rank": i + 1 + offset, **row} for i, row in enumerate(rows)]
    finally:
        conn.close()


def get_project_json(
    db_path: str | Path,
    owner: str,
    repo: str,
) -> Optional[dict]:
    """Return full metadata + latest analysis for a single project.

    Args:
        db_path: Path to the SQLite database file.
        owner:   Repository owner.
        repo:    Repository name.

    Returns:
        Dict with project metadata and latest scores, or None if not found.
    """
    conn = _open(db_path)
    try:
        project = get_project(conn, owner, repo)
        if not project:
            return None

        run = conn.execute(
            """SELECT * FROM analysis_runs
               WHERE owner = ? AND repo = ?
               ORDER BY session DESC LIMIT 1""",
            (owner, repo),
        ).fetchone()

        return {
            **project,
            "latest_run": dict(run) if run else None,
        }
    finally:
        conn.close()


def get_trends_json(
    db_path: str | Path,
    owner: str,
    repo: str,
) -> dict:
    """Return the full trend summary for a project.

    Args:
        db_path: Path to the SQLite database file.
        owner:   Repository owner.
        repo:    Repository name.

    Returns:
        Dict with history, stats, and delta fields from ``get_trend_summary``.
    """
    conn = _open(db_path)
    try:
        return get_trend_summary(conn, owner, repo)
    finally:
        conn.close()


def get_comparison_json(
    db_path: str | Path,
    owner1: str,
    repo1: str,
    owner2: str,
    repo2: str,
) -> Optional[dict]:
    """Compare two projects and return JSON-serialisable comparison data.

    Args:
        db_path: Path to the SQLite database file.
        owner1:  First project owner.
        repo1:   First project repo.
        owner2:  Second project owner.
        repo2:   Second project repo.

    Returns:
        Comparison dict, or None if either project has no data.
    """
    conn = _open(db_path)
    try:
        result = compare_from_db(conn, owner1, repo1, owner2, repo2)
        return result.to_dict() if result else None
    finally:
        conn.close()


def get_categories_json(
    db_path: str | Path,
) -> dict:
    """Return categories with project counts from the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dict with keys: categories (list of dicts with name/count),
        all_categories (list of all supported category strings).
    """
    conn = _open(db_path)
    try:
        rows = conn.execute(
            """SELECT category, COUNT(*) AS count
               FROM projects
               GROUP BY category
               ORDER BY count DESC"""
        ).fetchall()

        counts = [{"category": r["category"] or "other", "count": r["count"]} for r in rows]
        return {
            "categories": counts,
            "all_categories": list_categories(),
            "total_projects": sum(c["count"] for c in counts),
        }
    finally:
        conn.close()


def get_stats_json(
    db_path: str | Path,
) -> dict:
    """Return aggregate leaderboard statistics.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dict with total_projects, total_runs, average_score,
        and movers (top risers/fallers).
    """
    conn = _open(db_path)
    try:
        stats = get_stats(conn)
        movers = get_movers(conn, sessions=5, limit=5)
        return {
            **stats,
            "top_risers": movers.get("risers", []),
            "top_fallers": movers.get("fallers", []),
        }
    finally:
        conn.close()


def get_digest_json(
    db_path: str | Path,
    session: Optional[int] = None,
) -> dict:
    """Return digest data as a JSON-serialisable dict.

    Args:
        db_path: Path to the SQLite database file.
        session: Session to describe. Defaults to the latest.

    Returns:
        Full digest data dict from ``build_digest_data``.
    """
    conn = _open(db_path)
    try:
        return build_digest_data(conn, session=session)
    finally:
        conn.close()
