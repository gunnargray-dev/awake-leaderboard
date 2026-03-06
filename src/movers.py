"""Awake Leaderboard -- movers and shakers analysis.

Compares score snapshots across sessions to surface interesting patterns:
grade boundary proximity, new project entrants, session-over-session
changes, and website-ready trend data.

Public API
----------
- ``GradeBoundaryAlert``       -- project near a grade change
- ``NewEntrant``               -- project that appeared in a later session
- ``SessionComparison``        -- aggregate stats between two sessions
- ``MoversReport``             -- full movers-and-shakers report
- ``find_grade_boundary_alerts(history)``  -- scan for boundary proximity
- ``find_new_entrants(history)``           -- detect roster changes
- ``compare_sessions(history, a, b)``      -- session-over-session comparison
- ``generate_movers_report(data_dir)``     -- full report
- ``dedup_history(history)``               -- remove duplicate entries
- ``export_trends_json(data_dir)``         -- write website/data/trends.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from src.models import compute_grade, _GRADE_BOUNDARIES
from src.score_history import load_history, _save_history, get_latest_sessions


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Points within a grade boundary to trigger an alert
BOUNDARY_PROXIMITY = 2.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GradeBoundaryAlert:
    """A project that is close to crossing a grade boundary."""

    project_slug: str
    current_score: float
    current_grade: str
    nearest_boundary: float
    target_grade: str     # grade it would get if it crossed
    distance: float       # how far from the boundary (positive = above, negative = below)
    direction: str        # "promotion" or "demotion"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NewEntrant:
    """A project that appeared in the history for the first time."""

    project_slug: str
    first_session: int
    score: float
    grade: str
    category: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SessionComparison:
    """Aggregate comparison between two sessions."""

    session_from: int
    session_to: int
    projects_from: int
    projects_to: int
    new_projects: list[str]
    avg_score_from: float
    avg_score_to: float
    avg_change: float
    grade_distribution_from: dict[str, int]
    grade_distribution_to: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MoversReport:
    """Full movers-and-shakers report."""

    sessions_analyzed: list[int]
    total_projects: int
    boundary_alerts: list[GradeBoundaryAlert]
    new_entrants: list[NewEntrant]
    session_comparisons: list[SessionComparison]
    duplicates_removed: int

    def to_dict(self) -> dict:
        return {
            "sessions_analyzed": self.sessions_analyzed,
            "total_projects": self.total_projects,
            "boundary_alerts": [a.to_dict() for a in self.boundary_alerts],
            "new_entrants": [e.to_dict() for e in self.new_entrants],
            "session_comparisons": [c.to_dict() for c in self.session_comparisons],
            "duplicates_removed": self.duplicates_removed,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines = [
            "# Movers and Shakers Report",
            "",
            f"**Sessions analyzed:** {', '.join(str(s) for s in self.sessions_analyzed)}",
            f"**Total projects:** {self.total_projects}",
            "",
        ]

        if self.duplicates_removed:
            lines.append(f"*Cleaned {self.duplicates_removed} duplicate history entries.*")
            lines.append("")

        # Grade boundary alerts
        if self.boundary_alerts:
            promos = [a for a in self.boundary_alerts if a.direction == "promotion"]
            demos = [a for a in self.boundary_alerts if a.direction == "demotion"]

            if promos:
                lines.append("## Near Promotion")
                lines.append("")
                lines.append("| Project | Score | Grade | Target | Distance |")
                lines.append("|---------|------:|:-----:|:------:|---------:|")
                for a in promos:
                    lines.append(
                        f"| {a.project_slug} | {a.current_score:.1f} "
                        f"| {a.current_grade} | {a.target_grade} "
                        f"| {a.distance:+.1f} |"
                    )
                lines.append("")

            if demos:
                lines.append("## Near Demotion")
                lines.append("")
                lines.append("| Project | Score | Grade | Risk | Distance |")
                lines.append("|---------|------:|:-----:|:----:|---------:|")
                for a in demos:
                    lines.append(
                        f"| {a.project_slug} | {a.current_score:.1f} "
                        f"| {a.current_grade} | {a.target_grade} "
                        f"| {a.distance:+.1f} |"
                    )
                lines.append("")

        # New entrants
        if self.new_entrants:
            lines.append("## New Entrants")
            lines.append("")
            lines.append("| Project | Session | Score | Grade | Category |")
            lines.append("|---------|:-------:|------:|:-----:|----------|")
            for e in self.new_entrants:
                lines.append(
                    f"| {e.project_slug} | {e.first_session} "
                    f"| {e.score:.1f} | {e.grade} | {e.category} |"
                )
            lines.append("")

        # Session comparisons
        if self.session_comparisons:
            lines.append("## Session Comparisons")
            lines.append("")
            for sc in self.session_comparisons:
                lines.append(
                    f"### Session {sc.session_from} -> {sc.session_to}"
                )
                lines.append("")
                lines.append(f"| Metric | Session {sc.session_from} | Session {sc.session_to} |")
                lines.append("|--------|-------:|-------:|")
                lines.append(f"| Projects | {sc.projects_from} | {sc.projects_to} |")
                lines.append(f"| Avg Score | {sc.avg_score_from:.1f} | {sc.avg_score_to:.1f} |")
                if sc.new_projects:
                    lines.append(
                        f"| New projects | -- | {len(sc.new_projects)} |"
                    )
                lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def dedup_history(history: list[dict]) -> tuple[list[dict], int]:
    """Remove duplicate entries from history.

    A duplicate is an entry with the same (project_slug, session) pair.
    Keeps the first occurrence.

    Returns (cleaned_history, duplicates_removed).
    """
    seen: set[tuple[str, int]] = set()
    cleaned: list[dict] = []
    removed = 0

    for entry in history:
        key = (entry["project_slug"], entry["session"])
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        cleaned.append(entry)

    return cleaned, removed


# ---------------------------------------------------------------------------
# Grade boundary analysis
# ---------------------------------------------------------------------------


def _find_boundaries_for_score(score: float) -> list[tuple[float, str, str, float]]:
    """Find grade boundaries near a given score.

    Returns list of (boundary, target_grade, direction, distance) tuples.
    """
    current_grade = compute_grade(score)
    results = []

    for i, (threshold, grade) in enumerate(_GRADE_BOUNDARIES):
        distance = score - threshold

        if abs(distance) > BOUNDARY_PROXIMITY:
            continue

        if distance < 0 and grade != current_grade:
            # Score is below this boundary -- promotion if it rises
            results.append((threshold, grade, "promotion", distance))
        elif distance >= 0 and distance <= BOUNDARY_PROXIMITY:
            # Score is just above this boundary -- demotion risk
            if i + 1 < len(_GRADE_BOUNDARIES):
                lower_grade = _GRADE_BOUNDARIES[i + 1][1]
                if lower_grade != current_grade:
                    results.append((threshold, lower_grade, "demotion", distance))

    return results


def find_grade_boundary_alerts(
    history: list[dict],
    proximity: float = BOUNDARY_PROXIMITY,
) -> list[GradeBoundaryAlert]:
    """Scan latest snapshot for projects near grade boundaries.

    Uses only the most recent session's data.
    """
    if not history:
        return []

    # Find the latest session
    latest_session = max(e["session"] for e in history)
    latest = [e for e in history if e["session"] == latest_session]

    alerts: list[GradeBoundaryAlert] = []
    for entry in latest:
        score = entry["scores"].get("overall", 0.0)
        current_grade = entry["scores"].get("grade", "F")

        for threshold, target_grade, direction, distance in _find_boundaries_for_score(score):
            if abs(distance) <= proximity:
                alerts.append(GradeBoundaryAlert(
                    project_slug=entry["project_slug"],
                    current_score=round(score, 1),
                    current_grade=current_grade,
                    nearest_boundary=threshold,
                    target_grade=target_grade,
                    distance=round(distance, 1),
                    direction=direction,
                ))

    # Sort: promotions first (closest), then demotions
    alerts.sort(key=lambda a: (0 if a.direction == "promotion" else 1, abs(a.distance)))
    return alerts


# ---------------------------------------------------------------------------
# New entrant detection
# ---------------------------------------------------------------------------


def find_new_entrants(
    history: list[dict],
    slug_categories: Optional[dict[str, str]] = None,
) -> list[NewEntrant]:
    """Find projects that first appeared after the earliest session."""
    if not history:
        return []

    if slug_categories is None:
        try:
            from src.discovery import _SEED_PROJECTS
            slug_categories = {
                f"{owner}/{repo}": cat for owner, repo, cat in _SEED_PROJECTS
            }
        except ImportError:
            slug_categories = {}

    # Find the earliest session
    earliest_session = min(e["session"] for e in history)

    # Find projects that are NOT in the earliest session
    earliest_slugs = {
        e["project_slug"] for e in history if e["session"] == earliest_session
    }

    # Group later entries by slug to find their first appearance
    first_appearance: dict[str, dict] = {}
    for entry in sorted(history, key=lambda e: e["session"]):
        slug = entry["project_slug"]
        if slug not in earliest_slugs and slug not in first_appearance:
            first_appearance[slug] = entry

    entrants = []
    for slug, entry in sorted(first_appearance.items()):
        entrants.append(NewEntrant(
            project_slug=slug,
            first_session=entry["session"],
            score=round(entry["scores"].get("overall", 0.0), 1),
            grade=entry["scores"].get("grade", "F"),
            category=slug_categories.get(slug, "other"),
        ))

    # Sort by session, then score descending
    entrants.sort(key=lambda e: (e.first_session, -e.score))
    return entrants


# ---------------------------------------------------------------------------
# Session comparison
# ---------------------------------------------------------------------------


def compare_sessions(
    history: list[dict],
    session_a: int,
    session_b: int,
) -> SessionComparison:
    """Compare aggregate stats between two sessions."""
    snaps_a = {
        e["project_slug"]: e for e in history if e["session"] == session_a
    }
    snaps_b = {
        e["project_slug"]: e for e in history if e["session"] == session_b
    }

    scores_a = [e["scores"].get("overall", 0.0) for e in snaps_a.values()]
    scores_b = [e["scores"].get("overall", 0.0) for e in snaps_b.values()]

    avg_a = sum(scores_a) / len(scores_a) if scores_a else 0.0
    avg_b = sum(scores_b) / len(scores_b) if scores_b else 0.0

    new_slugs = sorted(set(snaps_b.keys()) - set(snaps_a.keys()))

    from collections import Counter
    grades_a = dict(Counter(
        e["scores"].get("grade", "F") for e in snaps_a.values()
    ))
    grades_b = dict(Counter(
        e["scores"].get("grade", "F") for e in snaps_b.values()
    ))

    return SessionComparison(
        session_from=session_a,
        session_to=session_b,
        projects_from=len(snaps_a),
        projects_to=len(snaps_b),
        new_projects=new_slugs,
        avg_score_from=round(avg_a, 1),
        avg_score_to=round(avg_b, 1),
        avg_change=round(avg_b - avg_a, 2),
        grade_distribution_from=grades_a,
        grade_distribution_to=grades_b,
    )


# ---------------------------------------------------------------------------
# Website trends export
# ---------------------------------------------------------------------------


def export_trends_json(data_dir: Path, output: Optional[Path] = None) -> dict:
    """Generate website-friendly trends data and optionally write it.

    Returns the trends dict with per-project sparkline data and
    session-level aggregates.
    """
    history = load_history(data_dir)
    if not history:
        return {"sessions": [], "projects": {}, "summary": {}}

    sessions = sorted({e["session"] for e in history})

    # Per-project sparklines: {slug: [{session, score, grade}, ...]}
    projects: dict[str, list[dict]] = {}
    for entry in sorted(history, key=lambda e: (e["project_slug"], e["session"])):
        slug = entry["project_slug"]
        projects.setdefault(slug, []).append({
            "session": entry["session"],
            "score": round(entry["scores"].get("overall", 0.0), 1),
            "grade": entry["scores"].get("grade", "F"),
        })

    # Session-level aggregates
    session_summaries = []
    for s in sessions:
        snaps = [e for e in history if e["session"] == s]
        scores = [e["scores"].get("overall", 0.0) for e in snaps]
        session_summaries.append({
            "session": s,
            "project_count": len(snaps),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "min_score": round(min(scores), 1) if scores else 0.0,
            "max_score": round(max(scores), 1) if scores else 0.0,
        })

    data = {
        "sessions": sessions,
        "projects": projects,
        "summary": session_summaries,
    }

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return data


# ---------------------------------------------------------------------------
# Full report generation
# ---------------------------------------------------------------------------


def generate_movers_report(
    data_dir: Path,
    fix_duplicates: bool = True,
) -> MoversReport:
    """Generate a full movers-and-shakers report.

    If ``fix_duplicates`` is True, deduplicates history in-place and
    saves the cleaned file.
    """
    history = load_history(data_dir)
    dupes_removed = 0

    if fix_duplicates:
        history, dupes_removed = dedup_history(history)
        if dupes_removed > 0:
            _save_history(data_dir, history)

    sessions = sorted({e["session"] for e in history}) if history else []
    unique_slugs = {e["project_slug"] for e in history} if history else set()

    boundary_alerts = find_grade_boundary_alerts(history)
    new_entrants = find_new_entrants(history)

    # Compare consecutive sessions
    comparisons: list[SessionComparison] = []
    for i in range(len(sessions) - 1):
        comparisons.append(compare_sessions(history, sessions[i], sessions[i + 1]))

    return MoversReport(
        sessions_analyzed=sessions,
        total_projects=len(unique_slugs),
        boundary_alerts=boundary_alerts,
        new_entrants=new_entrants,
        session_comparisons=comparisons,
        duplicates_removed=dupes_removed,
    )
