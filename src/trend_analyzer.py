"""Awake Leaderboard -- trend analysis from score history.

Analyses ``data/score_history.json`` snapshots to compute per-project
score trends over time: moving averages, direction (improving / declining
/ stable), momentum, and per-category aggregates.

Public API
----------
- ``analyze_project_trend(snapshots)``        -- single project trend
- ``analyze_all_trends(data_dir)``            -- all projects
- ``categorize_trends(trends)``               -- group by direction
- ``analyze_category_trends(trends, seed)``   -- per-category aggregates
- ``generate_trend_report(data_dir, top, category)`` -- full report
- ``TrendReport.to_markdown() / .to_json()``  -- output formats
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from src.discovery import _SEED_PROJECTS
from src.score_history import load_history, record_snapshot, get_latest_sessions


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum snapshots needed to compute a trend direction
MIN_SNAPSHOTS_FOR_TREND = 2

# Threshold for "stable" classification: abs(momentum) below this is stable
STABILITY_THRESHOLD = 1.5

# Moving average window
MA_WINDOW = 3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ProjectTrend:
    """Trend data for a single project."""

    project_slug: str
    snapshots: int          # number of score snapshots
    scores: list[float]     # overall scores, oldest first
    sessions: list[int]     # session numbers, oldest first
    current_score: float
    moving_average: float   # MA of last MA_WINDOW scores
    direction: str          # "improving", "declining", "stable"
    momentum: float         # average per-session change
    min_score: float
    max_score: float
    score_range: float      # max - min
    current_grade: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CategoryTrend:
    """Aggregate trend for a category."""

    category: str
    project_count: int
    avg_score: float
    avg_momentum: float
    direction: str          # overall direction for the category
    improving_count: int
    declining_count: int
    stable_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrendReport:
    """Full trend analysis report."""

    total_projects: int
    sessions_analyzed: list[int]
    improving: list[ProjectTrend]
    declining: list[ProjectTrend]
    stable: list[ProjectTrend]
    category_trends: list[CategoryTrend]
    avg_score: float
    avg_momentum: float

    def to_dict(self) -> dict:
        return {
            "total_projects": self.total_projects,
            "sessions_analyzed": self.sessions_analyzed,
            "avg_score": round(self.avg_score, 1),
            "avg_momentum": round(self.avg_momentum, 2),
            "improving": [t.to_dict() for t in self.improving],
            "declining": [t.to_dict() for t in self.declining],
            "stable": [t.to_dict() for t in self.stable],
            "category_trends": [c.to_dict() for c in self.category_trends],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines = [
            "# Trend Analysis Report",
            "",
            f"**Projects analyzed:** {self.total_projects}",
            f"**Sessions:** {', '.join(str(s) for s in self.sessions_analyzed)}",
            f"**Average score:** {self.avg_score:.1f}",
            f"**Average momentum:** {self.avg_momentum:+.2f} per session",
            "",
        ]

        if self.improving:
            lines.append("## Top Improvers")
            lines.append("")
            lines.append("| Project | Score | Momentum | Direction | Grade |")
            lines.append("|---------|------:|:--------:|:---------:|:-----:|")
            for t in self.improving:
                lines.append(
                    f"| {t.project_slug} | {t.current_score:.1f} "
                    f"| {t.momentum:+.2f} | {t.direction} | {t.current_grade} |"
                )
            lines.append("")

        if self.declining:
            lines.append("## Top Decliners")
            lines.append("")
            lines.append("| Project | Score | Momentum | Direction | Grade |")
            lines.append("|---------|------:|:--------:|:---------:|:-----:|")
            for t in self.declining:
                lines.append(
                    f"| {t.project_slug} | {t.current_score:.1f} "
                    f"| {t.momentum:+.2f} | {t.direction} | {t.current_grade} |"
                )
            lines.append("")

        if self.stable:
            lines.append("## Stable Projects")
            lines.append("")
            lines.append("| Project | Score | Momentum | Grade |")
            lines.append("|---------|------:|:--------:|:-----:|")
            for t in self.stable:
                lines.append(
                    f"| {t.project_slug} | {t.current_score:.1f} "
                    f"| {t.momentum:+.2f} | {t.current_grade} |"
                )
            lines.append("")

        if self.category_trends:
            lines.append("## Category Trends")
            lines.append("")
            lines.append("| Category | Projects | Avg Score | Momentum | Direction |")
            lines.append("|----------|:--------:|----------:|:--------:|:---------:|")
            for c in self.category_trends:
                lines.append(
                    f"| {c.category} | {c.project_count} "
                    f"| {c.avg_score:.1f} | {c.avg_momentum:+.2f} "
                    f"| {c.direction} |"
                )
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _compute_moving_average(scores: list[float], window: int = MA_WINDOW) -> float:
    """Compute the moving average of the last ``window`` scores."""
    if not scores:
        return 0.0
    tail = scores[-window:]
    return round(sum(tail) / len(tail), 2)


def _compute_momentum(scores: list[float]) -> float:
    """Average per-step change across consecutive scores."""
    if len(scores) < 2:
        return 0.0
    changes = [scores[i + 1] - scores[i] for i in range(len(scores) - 1)]
    return round(sum(changes) / len(changes), 2)


def _classify_direction(momentum: float) -> str:
    """Classify trend direction from momentum value."""
    if momentum > STABILITY_THRESHOLD:
        return "improving"
    elif momentum < -STABILITY_THRESHOLD:
        return "declining"
    return "stable"


def analyze_project_trend(
    slug: str,
    snapshots: list[dict],
) -> ProjectTrend:
    """Analyze trend for a single project given its ordered snapshots.

    ``snapshots`` should be sorted by session (ascending) and each
    entry must have ``session``, ``scores.overall``, ``scores.grade``.
    """
    scores = [s["scores"].get("overall", 0.0) for s in snapshots]
    sessions = [s["session"] for s in snapshots]
    current = scores[-1] if scores else 0.0
    grade = snapshots[-1]["scores"].get("grade", "F") if snapshots else "F"
    ma = _compute_moving_average(scores)
    momentum = _compute_momentum(scores)
    direction = _classify_direction(momentum)

    return ProjectTrend(
        project_slug=slug,
        snapshots=len(snapshots),
        scores=[round(s, 1) for s in scores],
        sessions=sessions,
        current_score=round(current, 1),
        moving_average=ma,
        direction=direction,
        momentum=momentum,
        min_score=round(min(scores), 1) if scores else 0.0,
        max_score=round(max(scores), 1) if scores else 0.0,
        score_range=round(max(scores) - min(scores), 1) if scores else 0.0,
        current_grade=grade,
    )


def _group_history_by_project(history: list[dict]) -> dict[str, list[dict]]:
    """Group history entries by project_slug, sorted by session."""
    groups: dict[str, list[dict]] = {}
    for entry in history:
        slug = entry["project_slug"]
        groups.setdefault(slug, []).append(entry)
    # Sort each group by session
    for slug in groups:
        groups[slug].sort(key=lambda e: e["session"])
    return groups


def analyze_all_trends(data_dir: Path) -> list[ProjectTrend]:
    """Load history and compute trends for every project.

    Returns a list of ``ProjectTrend`` sorted by momentum (best first).
    """
    history = load_history(data_dir)
    if not history:
        return []

    groups = _group_history_by_project(history)
    trends = []
    for slug, snaps in groups.items():
        if len(snaps) >= MIN_SNAPSHOTS_FOR_TREND:
            trends.append(analyze_project_trend(slug, snaps))

    # Sort by momentum descending
    trends.sort(key=lambda t: t.momentum, reverse=True)
    return trends


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------


def categorize_trends(
    trends: list[ProjectTrend],
) -> tuple[list[ProjectTrend], list[ProjectTrend], list[ProjectTrend]]:
    """Split trends into improving, declining, and stable lists."""
    improving = [t for t in trends if t.direction == "improving"]
    declining = [t for t in trends if t.direction == "declining"]
    stable = [t for t in trends if t.direction == "stable"]
    # Sort each: improving by momentum desc, declining by momentum asc
    improving.sort(key=lambda t: t.momentum, reverse=True)
    declining.sort(key=lambda t: t.momentum)
    stable.sort(key=lambda t: t.current_score, reverse=True)
    return improving, declining, stable


def _slug_to_category() -> dict[str, str]:
    """Build a {slug: category} map from seed projects."""
    return {
        f"{owner}/{repo}": category
        for owner, repo, category in _SEED_PROJECTS
    }


def analyze_category_trends(
    trends: list[ProjectTrend],
    slug_categories: Optional[dict[str, str]] = None,
) -> list[CategoryTrend]:
    """Compute per-category aggregate trends."""
    if slug_categories is None:
        slug_categories = _slug_to_category()

    # Group trends by category
    by_cat: dict[str, list[ProjectTrend]] = {}
    for t in trends:
        cat = slug_categories.get(t.project_slug, "other")
        by_cat.setdefault(cat, []).append(t)

    results = []
    for cat, cat_trends in sorted(by_cat.items()):
        scores = [t.current_score for t in cat_trends]
        momenta = [t.momentum for t in cat_trends]
        avg_score = sum(scores) / len(scores)
        avg_momentum = sum(momenta) / len(momenta)

        improving_count = sum(1 for t in cat_trends if t.direction == "improving")
        declining_count = sum(1 for t in cat_trends if t.direction == "declining")
        stable_count = sum(1 for t in cat_trends if t.direction == "stable")

        results.append(CategoryTrend(
            category=cat,
            project_count=len(cat_trends),
            avg_score=round(avg_score, 1),
            avg_momentum=round(avg_momentum, 2),
            direction=_classify_direction(avg_momentum),
            improving_count=improving_count,
            declining_count=declining_count,
            stable_count=stable_count,
        ))

    # Sort by avg_momentum descending
    results.sort(key=lambda c: c.avg_momentum, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Full report generation
# ---------------------------------------------------------------------------


def generate_trend_report(
    data_dir: Path,
    top: int = 10,
    category: Optional[str] = None,
) -> TrendReport:
    """Generate a complete trend analysis report.

    Args:
        data_dir:  Directory containing ``score_history.json``.
        top:       Max number of projects per section.
        category:  Optional category filter (seed category name).

    Returns:
        A ``TrendReport`` with improving/declining/stable lists and
        category-level aggregates.
    """
    history = load_history(data_dir)
    sessions = sorted({e["session"] for e in history}) if history else []

    groups = _group_history_by_project(history) if history else {}
    slug_categories = _slug_to_category()

    # Build per-project trends
    all_trends: list[ProjectTrend] = []
    for slug, snaps in groups.items():
        if len(snaps) >= MIN_SNAPSHOTS_FOR_TREND:
            all_trends.append(analyze_project_trend(slug, snaps))

    # Optional category filter
    if category:
        all_trends = [
            t for t in all_trends
            if slug_categories.get(t.project_slug, "other") == category
        ]

    improving, declining, stable = categorize_trends(all_trends)

    # Per-category trends (unfiltered for the full picture)
    cat_trends = analyze_category_trends(all_trends, slug_categories)

    # Aggregate stats
    all_scores = [t.current_score for t in all_trends]
    all_momenta = [t.momentum for t in all_trends]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
    avg_momentum = sum(all_momenta) / len(all_momenta) if all_momenta else 0.0

    return TrendReport(
        total_projects=len(all_trends),
        sessions_analyzed=sessions,
        improving=improving[:top],
        declining=declining[:top],
        stable=stable[:top],
        category_trends=cat_trends,
        avg_score=round(avg_score, 1),
        avg_momentum=round(avg_momentum, 2),
    )


def ensure_baseline_snapshots(
    data_dir: Path,
    sessions: Optional[list[int]] = None,
) -> int:
    """Create baseline snapshots if none exist.

    Records snapshots for the specified sessions (default: [1, 2]) so
    that trend analysis has at least two data points.

    Returns the number of new snapshots recorded.
    """
    if sessions is None:
        sessions = [1, 2]

    history = load_history(data_dir)
    existing_sessions = {e["session"] for e in history}

    recorded = 0
    for s in sessions:
        if s not in existing_sessions:
            record_snapshot(data_dir, s)
            recorded += 1

    return recorded
