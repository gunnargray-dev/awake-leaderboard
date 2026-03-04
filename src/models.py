"""Awake Leaderboard -- database models and schema.

SQLite-backed storage for open-source project profiles and analysis
scores. Pure stdlib, no ORM dependencies.

Tables
------
- ``projects``       -- project metadata (name, url, stars, language, category)
- ``analysis_runs``  -- one row per analysis session (scores, grade, timestamp)

Public API
----------
- ``init_db(db_path)``              -- create tables if not exists
- ``upsert_project(db, project)``   -- insert or update a project
- ``insert_run(db, run)``           -- record an analysis run
- ``get_project(db, owner, repo)``  -- fetch one project
- ``get_leaderboard(db, ...)``      -- ranked project list
- ``get_project_history(db, ...)``  -- score history for one project
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """A tracked open-source project."""

    owner: str
    repo: str
    url: str
    description: str = ""
    language: str = ""
    category: str = ""
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    topics: str = ""  # comma-separated
    created_at: str = ""
    last_pushed: str = ""
    added_at: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisRun:
    """Results from a single analysis of a project."""

    owner: str
    repo: str
    session: int
    health_score: float = 0.0
    complexity_score: float = 0.0
    security_score: float = 0.0
    dead_code_pct: float = 0.0
    test_coverage_pct: float = 0.0
    overall_score: float = 0.0
    grade: str = "F"
    findings_json: str = "{}"
    analyzed_at: str = ""
    files_analyzed: int = 0
    total_lines: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Grade boundaries
# ---------------------------------------------------------------------------

_GRADE_BOUNDARIES = [
    (90, "A+"), (85, "A"), (80, "A-"),
    (75, "B+"), (70, "B"), (65, "B-"),
    (60, "C+"), (55, "C"), (50, "C-"),
    (40, "D"),  (0, "F"),
]


def compute_grade(score: float) -> str:
    """Map a 0-100 score to a letter grade."""
    for threshold, grade in _GRADE_BOUNDARIES:
        if score >= threshold:
            return grade
    return "F"


def compute_overall_score(
    health: float,
    complexity: float,
    security: float,
    dead_code_pct: float,
    coverage_pct: float,
) -> float:
    """Weighted average of sub-scores into a single 0-100 overall score.

    Weights:
        health      -- 30%  (code quality basics)
        complexity  -- 20%  (maintainability)
        security    -- 25%  (safety)
        dead code   -- 10%  (cleanliness, inverted: 0% dead = 100 points)
        coverage    -- 15%  (test coverage)
    """
    dead_code_score = max(0.0, 100.0 - dead_code_pct * 100.0)
    coverage_score = min(100.0, coverage_pct)

    return (
        health * 0.30
        + complexity * 0.20
        + security * 0.25
        + dead_code_score * 0.10
        + coverage_score * 0.15
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    owner         TEXT NOT NULL,
    repo          TEXT NOT NULL,
    url           TEXT NOT NULL,
    description   TEXT DEFAULT '',
    language      TEXT DEFAULT '',
    category      TEXT DEFAULT '',
    stars         INTEGER DEFAULT 0,
    forks         INTEGER DEFAULT 0,
    open_issues   INTEGER DEFAULT 0,
    topics        TEXT DEFAULT '',
    created_at    TEXT DEFAULT '',
    last_pushed   TEXT DEFAULT '',
    added_at      TEXT DEFAULT '',
    PRIMARY KEY (owner, repo)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner           TEXT NOT NULL,
    repo            TEXT NOT NULL,
    session         INTEGER NOT NULL,
    health_score    REAL DEFAULT 0,
    complexity_score REAL DEFAULT 0,
    security_score  REAL DEFAULT 0,
    dead_code_pct   REAL DEFAULT 0,
    test_coverage_pct REAL DEFAULT 0,
    overall_score   REAL DEFAULT 0,
    grade           TEXT DEFAULT 'F',
    findings_json   TEXT DEFAULT '{}',
    analyzed_at     TEXT DEFAULT '',
    files_analyzed  INTEGER DEFAULT 0,
    total_lines     INTEGER DEFAULT 0,
    FOREIGN KEY (owner, repo) REFERENCES projects(owner, repo)
);

CREATE INDEX IF NOT EXISTS idx_runs_project ON analysis_runs(owner, repo);
CREATE INDEX IF NOT EXISTS idx_runs_session ON analysis_runs(session);
CREATE INDEX IF NOT EXISTS idx_runs_score   ON analysis_runs(overall_score DESC);
"""


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create the database and tables. Returns a connection."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def upsert_project(conn: sqlite3.Connection, project: Project) -> None:
    """Insert or update a project record."""
    now = datetime.now(timezone.utc).isoformat()
    if not project.added_at:
        project.added_at = now

    conn.execute(
        """INSERT INTO projects
           (owner, repo, url, description, language, category,
            stars, forks, open_issues, topics, created_at, last_pushed, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(owner, repo) DO UPDATE SET
               description = excluded.description,
               language    = excluded.language,
               stars       = excluded.stars,
               forks       = excluded.forks,
               open_issues = excluded.open_issues,
               topics      = excluded.topics,
               last_pushed = excluded.last_pushed
        """,
        (
            project.owner, project.repo, project.url,
            project.description, project.language, project.category,
            project.stars, project.forks, project.open_issues,
            project.topics, project.created_at, project.last_pushed,
            project.added_at,
        ),
    )
    conn.commit()


def insert_run(conn: sqlite3.Connection, run: AnalysisRun) -> int:
    """Record an analysis run. Returns the new row ID."""
    now = datetime.now(timezone.utc).isoformat()
    if not run.analyzed_at:
        run.analyzed_at = now

    cursor = conn.execute(
        """INSERT INTO analysis_runs
           (owner, repo, session, health_score, complexity_score,
            security_score, dead_code_pct, test_coverage_pct,
            overall_score, grade, findings_json, analyzed_at,
            files_analyzed, total_lines)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.owner, run.repo, run.session,
            run.health_score, run.complexity_score,
            run.security_score, run.dead_code_pct, run.test_coverage_pct,
            run.overall_score, run.grade, run.findings_json,
            run.analyzed_at, run.files_analyzed, run.total_lines,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_project(
    conn: sqlite3.Connection, owner: str, repo: str
) -> Optional[dict]:
    """Fetch a single project by owner/repo."""
    row = conn.execute(
        "SELECT * FROM projects WHERE owner = ? AND repo = ?",
        (owner, repo),
    ).fetchone()
    return dict(row) if row else None


def get_leaderboard(
    conn: sqlite3.Connection,
    *,
    category: str = "",
    language: str = "",
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "overall_score",
) -> list[dict]:
    """Return the ranked leaderboard.

    Joins the latest analysis run for each project.
    """
    valid_sorts = {
        "overall_score", "health_score", "complexity_score",
        "security_score", "stars", "repo",
    }
    if sort_by not in valid_sorts:
        sort_by = "overall_score"

    query = """
        SELECT p.*, r.overall_score, r.grade, r.health_score,
               r.complexity_score, r.security_score, r.dead_code_pct,
               r.test_coverage_pct, r.session, r.analyzed_at,
               r.files_analyzed, r.total_lines
        FROM projects p
        LEFT JOIN analysis_runs r ON p.owner = r.owner AND p.repo = r.repo
            AND r.id = (
                SELECT id FROM analysis_runs r2
                WHERE r2.owner = p.owner AND r2.repo = p.repo
                ORDER BY r2.session DESC LIMIT 1
            )
        WHERE 1=1
    """
    params: list = []

    if category:
        query += " AND p.category = ?"
        params.append(category)
    if language:
        query += " AND p.language = ?"
        params.append(language)

    if sort_by == "repo":
        query += f" ORDER BY p.repo ASC"
    else:
        query += f" ORDER BY r.{sort_by} DESC NULLS LAST"

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_project_history(
    conn: sqlite3.Connection, owner: str, repo: str
) -> list[dict]:
    """Return all analysis runs for a project, ordered by session."""
    rows = conn.execute(
        """SELECT * FROM analysis_runs
           WHERE owner = ? AND repo = ?
           ORDER BY session ASC""",
        (owner, repo),
    ).fetchall()
    return [dict(row) for row in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return aggregate leaderboard stats."""
    project_count = conn.execute(
        "SELECT COUNT(*) FROM projects"
    ).fetchone()[0]
    run_count = conn.execute(
        "SELECT COUNT(*) FROM analysis_runs"
    ).fetchone()[0]
    avg_score = conn.execute(
        """SELECT AVG(overall_score) FROM analysis_runs
           WHERE id IN (
               SELECT MAX(id) FROM analysis_runs GROUP BY owner, repo
           )"""
    ).fetchone()[0]
    return {
        "total_projects": project_count,
        "total_runs": run_count,
        "average_score": round(avg_score, 1) if avg_score else 0.0,
    }
