"""Awake Leaderboard -- comparison engine.

Compare two projects head-to-head on every score dimension.
All comparisons are pure functions; no database writes.

Public API
----------
- ``compare_projects(a, b)``                   -> ComparisonResult
- ``compare_from_db(conn, owner1, repo1, owner2, repo2)`` -> ComparisonResult
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class DimensionResult:
    """Comparison result for a single scoring dimension."""

    dimension: str       # e.g. "health", "security"
    score_a: float
    score_b: float
    winner: str          # "a", "b", or "tie"
    margin: float        # absolute difference

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "dimension": self.dimension,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "winner": self.winner,
            "margin": self.margin,
        }


@dataclass
class ComparisonResult:
    """Full head-to-head comparison between two projects."""

    owner_a: str
    repo_a: str
    owner_b: str
    repo_b: str
    dimensions: list[DimensionResult] = field(default_factory=list)
    overall_winner: str = "tie"   # "a", "b", or "tie"
    score_a: float = 0.0
    score_b: float = 0.0
    wins_a: int = 0
    wins_b: int = 0

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "project_a": f"{self.owner_a}/{self.repo_a}",
            "project_b": f"{self.owner_b}/{self.repo_b}",
            "overall_winner": self.overall_winner,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "wins_a": self.wins_a,
            "wins_b": self.wins_b,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }

    def to_markdown(self) -> str:
        """Render the comparison as a Markdown table."""
        lines = [
            f"# {self.owner_a}/{self.repo_a} vs {self.owner_b}/{self.repo_b}",
            "",
            f"| Dimension | {self.owner_a}/{self.repo_a} | {self.owner_b}/{self.repo_b} | Winner |",
            "|-----------|" + "-" * 30 + "|" + "-" * 30 + "|--------|",
        ]
        for d in self.dimensions:
            winner_label = (
                f"**{self.owner_a}/{self.repo_a}**" if d.winner == "a"
                else f"**{self.owner_b}/{self.repo_b}**" if d.winner == "b"
                else "Tie"
            )
            lines.append(
                f"| {d.dimension.title()} | {d.score_a:.1f} | {d.score_b:.1f} | {winner_label} |"
            )
        lines += [
            "",
            f"**Overall winner:** {self.overall_winner.upper() if self.overall_winner != 'tie' else 'Tie'}",
            f"Wins: {self.owner_a}/{self.repo_a} = {self.wins_a}, {self.owner_b}/{self.repo_b} = {self.wins_b}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------


def _compare_dim(
    dimension: str,
    score_a: float,
    score_b: float,
    *,
    higher_is_better: bool = True,
) -> DimensionResult:
    """Build a DimensionResult for a single dimension."""
    margin = abs(score_a - score_b)
    if margin < 0.5:
        winner = "tie"
    elif higher_is_better:
        winner = "a" if score_a > score_b else "b"
    else:
        winner = "a" if score_a < score_b else "b"
    return DimensionResult(
        dimension=dimension,
        score_a=round(score_a, 1),
        score_b=round(score_b, 1),
        winner=winner,
        margin=round(margin, 1),
    )


def compare_projects(
    run_a: dict,
    run_b: dict,
) -> ComparisonResult:
    """Compare two analysis run dicts head-to-head.

    Args:
        run_a: Dict with keys owner, repo, overall_score, health_score,
               complexity_score, security_score, dead_code_pct.
        run_b: Same structure for the second project.

    Returns:
        ComparisonResult with dimension breakdowns and overall winner.
    """
    owner_a = run_a.get("owner", "")
    repo_a = run_a.get("repo", "")
    owner_b = run_b.get("owner", "")
    repo_b = run_b.get("repo", "")

    # dead_code: lower pct is better -- convert to a score
    dead_a = max(0.0, 100.0 - (run_a.get("dead_code_pct") or 0.0) * 100.0)
    dead_b = max(0.0, 100.0 - (run_b.get("dead_code_pct") or 0.0) * 100.0)

    dimensions = [
        _compare_dim("overall",    run_a.get("overall_score") or 0.0,    run_b.get("overall_score") or 0.0),
        _compare_dim("health",     run_a.get("health_score") or 0.0,     run_b.get("health_score") or 0.0),
        _compare_dim("complexity", run_a.get("complexity_score") or 0.0, run_b.get("complexity_score") or 0.0),
        _compare_dim("security",   run_a.get("security_score") or 0.0,   run_b.get("security_score") or 0.0),
        _compare_dim("dead_code",  dead_a,                                dead_b),
    ]

    wins_a = sum(1 for d in dimensions if d.winner == "a")
    wins_b = sum(1 for d in dimensions if d.winner == "b")

    if wins_a > wins_b:
        overall_winner = "a"
    elif wins_b > wins_a:
        overall_winner = "b"
    else:
        # Tiebreak by overall score
        oa = run_a.get("overall_score") or 0.0
        ob = run_b.get("overall_score") or 0.0
        overall_winner = "a" if oa > ob else "b" if ob > oa else "tie"

    return ComparisonResult(
        owner_a=owner_a, repo_a=repo_a,
        owner_b=owner_b, repo_b=repo_b,
        dimensions=dimensions,
        overall_winner=overall_winner,
        score_a=round(run_a.get("overall_score") or 0.0, 1),
        score_b=round(run_b.get("overall_score") or 0.0, 1),
        wins_a=wins_a,
        wins_b=wins_b,
    )


def compare_from_db(
    conn: sqlite3.Connection,
    owner1: str,
    repo1: str,
    owner2: str,
    repo2: str,
) -> Optional[ComparisonResult]:
    """Compare two projects using their latest analysis runs from the database.

    Args:
        conn:   Open database connection.
        owner1: First project owner.
        repo1:  First project repo.
        owner2: Second project owner.
        repo2:  Second project repo.

    Returns:
        ComparisonResult, or None if either project has no analysis runs.
    """
    def _latest(owner: str, repo: str) -> Optional[dict]:
        row = conn.execute(
            """SELECT owner, repo, overall_score, health_score,
                      complexity_score, security_score, dead_code_pct,
                      grade, session
               FROM analysis_runs
               WHERE owner = ? AND repo = ?
               ORDER BY session DESC LIMIT 1""",
            (owner, repo),
        ).fetchone()
        return dict(row) if row else None

    run_a = _latest(owner1, repo1)
    run_b = _latest(owner2, repo2)

    if run_a is None or run_b is None:
        return None

    return compare_projects(run_a, run_b)
