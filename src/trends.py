"""Awake Leaderboard -- trend tracking and score history analysis.

Computes score deltas, rank changes, and identifies movers and shakers
across sessions. All analysis is performed directly against the SQLite
database -- no extra tables required; trends are derived from the
existing ``analysis_runs`` table.

Public API
----------
- ``get_score_delta(conn, owner, repo, sessions)``      -- score change over N sessions
- ``get_rank_history(conn, session)``                   -- ranked list for one session
- ``get_movers(conn, sessions, limit)``                 -- biggest score changes
- ``get_trend_summary(conn, owner, repo)``              -- full trend summary for one project
- ``get_weekly_aggregation(conn, owner, repo, weeks)``  -- weekly avg scores
"""

from __future__ import annotations

import sqlite3
from typing import Optional


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


def get_score_delta(
    conn: sqlite3.Connection,
    owner: str,
    repo: str,
    sessions: int = 5,
) -> dict:
    """Return the score delta between the latest and N-sessions-ago run.

    Args:
        conn:    Open database connection.
        owner:   Project owner.
        repo:    Project repo name.
        sessions: How many sessions back to compare. Defaults to 5.

    Returns:
        Dict with keys: owner, repo, current_score, previous_score,
        score_change, current_grade, previous_grade, current_session,
        previous_session. Returns zeros if fewer than 2 runs exist.
    """
    rows = conn.execute(
        """SELECT session, overall_score, grade
           FROM analysis_runs
           WHERE owner = ? AND repo = ?
           ORDER BY session DESC
           LIMIT ?""",
        (owner, repo, sessions + 1),
    ).fetchall()

    if not rows:
        return {
            "owner": owner, "repo": repo,
            "current_score": 0.0, "previous_score": 0.0,
            "score_change": 0.0, "current_grade": "F",
            "previous_grade": "F", "current_session": 0,
            "previous_session": 0,
        }

    current = rows[0]
    previous = rows[-1] if len(rows) > 1 else rows[0]

    return {
        "owner": owner,
        "repo": repo,
        "current_score": round(current["overall_score"] or 0.0, 1),
        "previous_score": round(previous["overall_score"] or 0.0, 1),
        "score_change": round(
            (current["overall_score"] or 0.0) - (previous["overall_score"] or 0.0), 1
        ),
        "current_grade": current["grade"],
        "previous_grade": previous["grade"],
        "current_session": current["session"],
        "previous_session": previous["session"],
    }


def get_rank_history(
    conn: sqlite3.Connection,
    session: int,
) -> list[dict]:
    """Return the full ranked leaderboard for a specific session.

    Args:
        conn:    Open database connection.
        session: Session number to query.

    Returns:
        List of dicts sorted by overall_score desc, each with rank added.
    """
    rows = conn.execute(
        """SELECT r.owner, r.repo, r.overall_score, r.grade, r.session,
                  p.stars, p.category
           FROM analysis_runs r
           JOIN projects p ON r.owner = p.owner AND r.repo = p.repo
           WHERE r.session = ?
           ORDER BY r.overall_score DESC""",
        (session,),
    ).fetchall()

    return [
        {**dict(row), "rank": i + 1}
        for i, row in enumerate(rows)
    ]


# ---------------------------------------------------------------------------
# Movers and shakers
# ---------------------------------------------------------------------------


def get_movers(
    conn: sqlite3.Connection,
    sessions: int = 5,
    limit: int = 10,
) -> dict:
    """Find the biggest score improvers and decliners in the last N sessions.

    Compares each project's latest score against its score N sessions ago.
    Projects with fewer than 2 runs are excluded.

    Args:
        conn:     Open database connection.
        sessions: Window size in sessions. Defaults to 5.
        limit:    Number of movers to return in each direction. Defaults to 10.

    Returns:
        Dict with keys 'risers' and 'fallers', each a list of delta dicts.
    """
    # Get all projects that have at least 2 runs
    projects = conn.execute(
        """SELECT DISTINCT owner, repo FROM analysis_runs
           GROUP BY owner, repo HAVING COUNT(*) >= 2"""
    ).fetchall()

    deltas = []
    for row in projects:
        delta = get_score_delta(conn, row["owner"], row["repo"], sessions=sessions)
        if delta["current_session"] != delta["previous_session"]:
            deltas.append(delta)

    deltas.sort(key=lambda d: d["score_change"], reverse=True)

    # fallers: projects with the largest negative changes (shown worst-first)
    negative = [d for d in deltas if d["score_change"] < 0]
    negative_sorted = list(reversed(negative))  # worst first (most negative)

    return {
        "risers": deltas[:limit],
        "fallers": negative_sorted[:limit],
        "sessions_window": sessions,
    }


# ---------------------------------------------------------------------------
# Project trend summary
# ---------------------------------------------------------------------------


def get_trend_summary(
    conn: sqlite3.Connection,
    owner: str,
    repo: str,
) -> dict:
    """Return a full trend summary for one project.

    Includes score history, delta vs. previous session, min/max/avg scores,
    and current rank estimate.

    Args:
        conn:  Open database connection.
        owner: Project owner.
        repo:  Project repo name.

    Returns:
        Dict with history list, stats, and delta fields.
    """
    rows = conn.execute(
        """SELECT session, overall_score, health_score, complexity_score,
                  security_score, dead_code_pct, grade, analyzed_at
           FROM analysis_runs
           WHERE owner = ? AND repo = ?
           ORDER BY session ASC""",
        (owner, repo),
    ).fetchall()

    history = [dict(r) for r in rows]

    if not history:
        return {"owner": owner, "repo": repo, "history": [], "stats": {}, "delta": {}}

    scores = [h["overall_score"] or 0.0 for h in history]
    delta = get_score_delta(conn, owner, repo, sessions=1)

    return {
        "owner": owner,
        "repo": repo,
        "history": history,
        "stats": {
            "sessions_analyzed": len(history),
            "min_score": round(min(scores), 1),
            "max_score": round(max(scores), 1),
            "avg_score": round(sum(scores) / len(scores), 1),
            "first_session": history[0]["session"],
            "latest_session": history[-1]["session"],
        },
        "delta": delta,
    }


# ---------------------------------------------------------------------------
# Weekly / monthly aggregations
# ---------------------------------------------------------------------------


def get_weekly_aggregation(
    conn: sqlite3.Connection,
    owner: str,
    repo: str,
    weeks: int = 4,
) -> list[dict]:
    """Return weekly average scores for a project.

    Groups analysis runs by ISO week (derived from ``analyzed_at`` timestamp).
    Falls back to session-based grouping if timestamps are unavailable.

    Args:
        conn:  Open database connection.
        owner: Project owner.
        repo:  Project repo name.
        weeks: How many weeks of history to return.

    Returns:
        List of dicts with week, avg_score, run_count, keyed by week string.
    """
    rows = conn.execute(
        """SELECT
               strftime('%Y-W%W', analyzed_at) AS week,
               AVG(overall_score) AS avg_score,
               COUNT(*) AS run_count
           FROM analysis_runs
           WHERE owner = ? AND repo = ?
             AND analyzed_at != ''
           GROUP BY week
           ORDER BY week DESC
           LIMIT ?""",
        (owner, repo, weeks),
    ).fetchall()

    return [
        {
            "week": row["week"],
            "avg_score": round(row["avg_score"] or 0.0, 1),
            "run_count": row["run_count"],
        }
        for row in reversed(rows)
    ]


def get_session_leaderboard_delta(
    conn: sqlite3.Connection,
    session_a: int,
    session_b: int,
) -> list[dict]:
    """Compare leaderboard rankings between two sessions.

    Args:
        conn:      Open database connection.
        session_a: Earlier session (baseline).
        session_b: Later session (current).

    Returns:
        List of dicts with owner, repo, score_a, score_b, change,
        rank_a, rank_b, rank_change. Sorted by rank_b ascending.
    """
    def _get_ranked(session: int) -> dict[tuple, dict]:
        rows = conn.execute(
            """SELECT owner, repo, overall_score, grade
               FROM analysis_runs
               WHERE session = ?
               ORDER BY overall_score DESC""",
            (session,),
        ).fetchall()
        return {
            (row["owner"], row["repo"]): {
                "score": row["overall_score"] or 0.0,
                "grade": row["grade"],
                "rank": i + 1,
            }
            for i, row in enumerate(rows)
        }

    ranked_a = _get_ranked(session_a)
    ranked_b = _get_ranked(session_b)

    all_keys = set(ranked_a) | set(ranked_b)
    results = []
    for owner, repo in sorted(all_keys):
        a = ranked_a.get((owner, repo), {"score": 0.0, "rank": 9999, "grade": "F"})
        b = ranked_b.get((owner, repo), {"score": 0.0, "rank": 9999, "grade": "F"})
        results.append({
            "owner": owner,
            "repo": repo,
            "score_a": round(a["score"], 1),
            "score_b": round(b["score"], 1),
            "score_change": round(b["score"] - a["score"], 1),
            "grade_a": a["grade"],
            "grade_b": b["grade"],
            "rank_a": a["rank"],
            "rank_b": b["rank"],
            "rank_change": a["rank"] - b["rank"],  # positive = moved up
        })

    results.sort(key=lambda r: r["rank_b"])
    return results
