"""Awake Leaderboard -- aggregate statistics summary.

Computes leaderboard-wide statistics from the generated project data:
mean, median, standard deviation, grade distribution, and per-category
averages.  Output in Markdown and JSON for easy sharing.

Public API
----------
- ``compute_stats(projects)``               -- aggregate stats from project list
- ``generate_stats_report(data_dir)``       -- full report from leaderboard.json
- ``StatsSummary.to_markdown() / .to_json()``
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from src.generate_leaderboard import generate_leaderboard


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GradeDistribution:
    """Count of projects per letter grade."""

    grade: str
    count: int
    percentage: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CategoryStats:
    """Aggregate stats for a single display category."""

    category: str
    project_count: int
    avg_score: float
    min_score: float
    max_score: float
    avg_health: float
    avg_complexity: float
    avg_security: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StatsSummary:
    """Full leaderboard statistics report."""

    total_projects: int
    mean_score: float
    median_score: float
    std_score: float
    min_score: float
    max_score: float
    grade_distribution: list[GradeDistribution]
    category_stats: list[CategoryStats]
    top_project: str
    bottom_project: str
    dimension_averages: dict  # {health, complexity, security, dead_code, coverage}

    def to_dict(self) -> dict:
        return {
            "total_projects": self.total_projects,
            "mean_score": round(self.mean_score, 1),
            "median_score": round(self.median_score, 1),
            "std_score": round(self.std_score, 1),
            "min_score": round(self.min_score, 1),
            "max_score": round(self.max_score, 1),
            "grade_distribution": [g.to_dict() for g in self.grade_distribution],
            "category_stats": [c.to_dict() for c in self.category_stats],
            "top_project": self.top_project,
            "bottom_project": self.bottom_project,
            "dimension_averages": {
                k: round(v, 1) for k, v in self.dimension_averages.items()
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines = [
            "# Awake Leaderboard Stats",
            "",
            f"**{self.total_projects} projects** scored across the Python ecosystem.",
            "",
            "## Score Overview",
            "",
            f"| Metric | Value |",
            f"|--------|------:|",
            f"| Mean   | {self.mean_score:.1f} |",
            f"| Median | {self.median_score:.1f} |",
            f"| Std Dev| {self.std_score:.1f} |",
            f"| Min    | {self.min_score:.1f} |",
            f"| Max    | {self.max_score:.1f} |",
            f"| Top    | {self.top_project} |",
            f"| Bottom | {self.bottom_project} |",
            "",
            "## Dimension Averages",
            "",
            "| Dimension | Average |",
            "|-----------|--------:|",
        ]
        for dim, val in self.dimension_averages.items():
            lines.append(f"| {dim.replace('_', ' ').title()} | {val:.1f} |")

        lines.extend(["", "## Grade Distribution", ""])
        lines.append("| Grade | Count | % |")
        lines.append("|:-----:|------:|--:|")
        for g in self.grade_distribution:
            lines.append(f"| {g.grade} | {g.count} | {g.percentage:.0f}% |")

        lines.extend(["", "## Category Averages", ""])
        lines.append("| Category | Projects | Avg Score | Health | Complexity | Security |")
        lines.append("|----------|:--------:|----------:|-------:|-----------:|---------:|")
        for c in self.category_stats:
            lines.append(
                f"| {c.category} | {c.project_count} | {c.avg_score:.1f} "
                f"| {c.avg_health:.1f} | {c.avg_complexity:.1f} | {c.avg_security:.1f} |"
            )

        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


def _median(values: list[float]) -> float:
    """Compute the median of a sorted list."""
    n = len(values)
    if n == 0:
        return 0.0
    s = sorted(values)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return s[mid]


def _std_dev(values: list[float], mean: float) -> float:
    """Compute population standard deviation."""
    if len(values) < 2:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def compute_stats(projects: list[dict]) -> StatsSummary:
    """Compute aggregate statistics from a list of project dicts.

    Each project dict should have ``score``, ``grade``, ``category``,
    ``owner``, ``name``, and ``dimensions`` with sub-scores.
    """
    if not projects:
        return StatsSummary(
            total_projects=0,
            mean_score=0.0,
            median_score=0.0,
            std_score=0.0,
            min_score=0.0,
            max_score=0.0,
            grade_distribution=[],
            category_stats=[],
            top_project="",
            bottom_project="",
            dimension_averages={},
        )

    scores = [p["score"] for p in projects]
    mean = sum(scores) / len(scores)
    median = _median(scores)
    std = _std_dev(scores, mean)

    # Sort to find top/bottom
    ranked = sorted(projects, key=lambda p: p["score"], reverse=True)
    top = ranked[0]
    bottom = ranked[-1]
    top_name = f"{top['owner']}/{top['name']} ({top['score']:.1f})"
    bottom_name = f"{bottom['owner']}/{bottom['name']} ({bottom['score']:.1f})"

    # Grade distribution
    from collections import Counter
    grade_counts = Counter(p["grade"] for p in projects)
    grade_order = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]
    grade_dist = []
    for g in grade_order:
        cnt = grade_counts.get(g, 0)
        if cnt > 0:
            grade_dist.append(GradeDistribution(
                grade=g,
                count=cnt,
                percentage=round(cnt / len(projects) * 100, 1),
            ))

    # Per-category stats
    by_cat: dict[str, list[dict]] = {}
    for p in projects:
        by_cat.setdefault(p["category"], []).append(p)

    cat_stats = []
    for cat in sorted(by_cat.keys()):
        cat_projects = by_cat[cat]
        cat_scores = [p["score"] for p in cat_projects]
        cat_health = [p["dimensions"]["health"] for p in cat_projects]
        cat_complexity = [p["dimensions"]["complexity"] for p in cat_projects]
        cat_security = [p["dimensions"]["security"] for p in cat_projects]

        cat_stats.append(CategoryStats(
            category=cat,
            project_count=len(cat_projects),
            avg_score=round(sum(cat_scores) / len(cat_scores), 1),
            min_score=round(min(cat_scores), 1),
            max_score=round(max(cat_scores), 1),
            avg_health=round(sum(cat_health) / len(cat_health), 1),
            avg_complexity=round(sum(cat_complexity) / len(cat_complexity), 1),
            avg_security=round(sum(cat_security) / len(cat_security), 1),
        ))

    # Sort by avg_score descending
    cat_stats.sort(key=lambda c: c.avg_score, reverse=True)

    # Dimension averages
    dims = ["health", "complexity", "security", "dead_code", "coverage"]
    dim_avgs = {}
    for dim in dims:
        vals = [p["dimensions"][dim] for p in projects]
        dim_avgs[dim] = sum(vals) / len(vals)

    return StatsSummary(
        total_projects=len(projects),
        mean_score=round(mean, 1),
        median_score=round(median, 1),
        std_score=round(std, 1),
        min_score=round(min(scores), 1),
        max_score=round(max(scores), 1),
        grade_distribution=grade_dist,
        category_stats=cat_stats,
        top_project=top_name,
        bottom_project=bottom_name,
        dimension_averages=dim_avgs,
    )


def generate_stats_report(data_dir: Optional[Path] = None) -> StatsSummary:
    """Generate stats from the leaderboard data.

    If ``data_dir`` is provided, reads ``leaderboard.json`` from there.
    Otherwise generates fresh data from the seed list.
    """
    if data_dir is not None:
        lb_path = data_dir / "leaderboard.json"
        if lb_path.exists():
            data = json.loads(lb_path.read_text(encoding="utf-8"))
            return compute_stats(data["projects"])

    data = generate_leaderboard()
    return compute_stats(data["projects"])
