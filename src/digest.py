"""Awake Leaderboard -- weekly digest generator.

Generates a structured Markdown digest summarising what changed between
the current session and recent history: new projects, biggest movers,
biggest drops, and overall stats.

Public API
----------
- ``generate_digest(conn, session)``  -> str  (full Markdown)
- ``build_digest_data(conn, session)`` -> dict (raw data for custom rendering)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from src.trends import get_movers
from src.models import get_stats, get_leaderboard


# ---------------------------------------------------------------------------
# Data builder
# ---------------------------------------------------------------------------


def build_digest_data(
    conn: sqlite3.Connection,
    session: Optional[int] = None,
    sessions_window: int = 5,
) -> dict:
    """Build the raw data that powers a digest.

    Args:
        conn:            Open database connection.
        session:         Session to describe. Defaults to the latest session.
        sessions_window: How many sessions to look back for movers.

    Returns:
        Dict with keys: session, generated_at, stats, new_projects,
        top_projects, movers_risers, movers_fallers, grade_distribution.
    """
    if session is None:
        row = conn.execute(
            "SELECT MAX(session) AS s FROM analysis_runs"
        ).fetchone()
        session = row["s"] if row and row["s"] is not None else 0

    # Overall stats
    stats = get_stats(conn)

    # Projects first analyzed in this session
    new_projects = conn.execute(
        """SELECT r.owner, r.repo, r.overall_score, r.grade, p.stars, p.category
           FROM analysis_runs r
           JOIN projects p ON r.owner = p.owner AND r.repo = p.repo
           WHERE r.session = ?
             AND NOT EXISTS (
                 SELECT 1 FROM analysis_runs r2
                 WHERE r2.owner = r.owner AND r2.repo = r.repo
                   AND r2.session < ?
             )
           ORDER BY r.overall_score DESC""",
        (session, session),
    ).fetchall()

    # Top 10 projects overall
    top_projects = get_leaderboard(conn, limit=10)

    # Movers
    movers = get_movers(conn, sessions=sessions_window, limit=5)

    # Grade distribution (latest run per project)
    grade_rows = conn.execute(
        """SELECT grade, COUNT(*) AS cnt
           FROM (
               SELECT owner, repo, grade,
                      ROW_NUMBER() OVER (
                          PARTITION BY owner, repo ORDER BY session DESC
                      ) AS rn
               FROM analysis_runs
           )
           WHERE rn = 1
           GROUP BY grade
           ORDER BY grade"""
    ).fetchall()
    grade_dist = {row["grade"]: row["cnt"] for row in grade_rows}

    return {
        "session": session,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "stats": stats,
        "new_projects": [dict(r) for r in new_projects],
        "top_projects": top_projects[:10],
        "movers_risers": movers.get("risers", []),
        "movers_fallers": movers.get("fallers", []),
        "grade_distribution": grade_dist,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def generate_digest(
    conn: sqlite3.Connection,
    session: Optional[int] = None,
    sessions_window: int = 5,
) -> str:
    """Generate a full Markdown digest for the given session.

    Args:
        conn:            Open database connection.
        session:         Session to describe. If None, uses the latest.
        sessions_window: Sessions back to use for movers.

    Returns:
        Markdown string ready to write to a file or print.
    """
    data = build_digest_data(conn, session=session, sessions_window=sessions_window)
    session = data["session"]
    stats = data["stats"]
    lines: list[str] = []

    # Header
    lines += [
        f"# Awake Leaderboard Digest -- Session {session}",
        "",
        f"*Generated: {data['generated_at']}*",
        "",
        "---",
        "",
    ]

    # Stats
    lines += [
        "## Overall Stats",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total projects | {stats['total_projects']} |",
        f"| Total analysis runs | {stats['total_runs']} |",
        f"| Average score | {stats['average_score']} |",
        "",
    ]

    # Grade distribution
    if data["grade_distribution"]:
        lines += ["## Grade Distribution", ""]
        lines += ["| Grade | Count |", "|-------|-------|"]
        for grade in ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]:
            cnt = data["grade_distribution"].get(grade, 0)
            if cnt:
                lines.append(f"| {grade} | {cnt} |")
        lines.append("")

    # New projects
    if data["new_projects"]:
        lines += [f"## New This Session ({len(data['new_projects'])} projects)", ""]
        lines += [
            "| Project | Score | Grade | Stars |",
            "|---------|-------|-------|-------|",
        ]
        for p in data["new_projects"]:
            lines.append(
                f"| {p['owner']}/{p['repo']} | {p['overall_score']:.1f} | {p['grade']} | {p.get('stars', 0):,} |"
            )
        lines.append("")

    # Top 10
    if data["top_projects"]:
        lines += ["## Top 10 Projects", ""]
        lines += [
            "| # | Project | Score | Grade | Category |",
            "|---|---------|-------|-------|----------|",
        ]
        for i, p in enumerate(data["top_projects"], 1):
            score = p.get("overall_score") or 0.0
            lines.append(
                f"| {i} | {p['owner']}/{p['repo']} | {score:.1f} | {p.get('grade', '?')} | {p.get('category', '') or '-'} |"
            )
        lines.append("")

    # Risers
    if data["movers_risers"]:
        lines += [f"## Biggest Risers (last {sessions_window} sessions)", ""]
        lines += [
            "| Project | Previous | Current | Change |",
            "|---------|----------|---------|--------|",
        ]
        for m in data["movers_risers"]:
            change = m['score_change']
            arrow = "▲" if change > 0 else "▼" if change < 0 else "–"
            lines.append(
                f"| {m['owner']}/{m['repo']} | {m['previous_score']:.1f} | {m['current_score']:.1f} | {arrow} {abs(change):.1f} |"
            )
        lines.append("")

    # Fallers
    if data["movers_fallers"]:
        lines += [f"## Biggest Drops (last {sessions_window} sessions)", ""]
        lines += [
            "| Project | Previous | Current | Change |",
            "|---------|----------|---------|--------|",
        ]
        for m in data["movers_fallers"]:
            change = m['score_change']
            arrow = "▼"
            lines.append(
                f"| {m['owner']}/{m['repo']} | {m['previous_score']:.1f} | {m['current_score']:.1f} | {arrow} {abs(change):.1f} |"
            )
        lines.append("")

    lines += ["---", "", "*Built by Computer. Powered by Awake.*"]
    return "\n".join(lines)
