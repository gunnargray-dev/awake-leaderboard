"""Awake Leaderboard -- score history tracking and refresh pipeline.

Maintains an append-only ``data/score_history.json`` file that records
project scores over time.  Each entry captures all dimension scores for
a project at a specific point in time, enabling delta computation and
mover identification.

Public API
----------
- ``record_snapshot(data_dir, session)``       -- regenerate scores and append snapshot
- ``load_history(data_dir)``                   -- load all historical snapshots
- ``compute_deltas(history, session_a, session_b)`` -- score changes between two snapshots
- ``find_movers(history, session_a, session_b, top)`` -- biggest improvers/decliners
- ``get_latest_sessions(history, n)``          -- last N unique session numbers
- ``refresh_scores(data_dir, session, top)``   -- full refresh pipeline
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.discovery import _SEED_PROJECTS
from src.generate_leaderboard import generate_scores


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ScoreSnapshot:
    """A single project's scores at a point in time."""

    project_slug: str  # "owner/repo"
    session: int
    timestamp: str
    scores: dict  # {health, complexity, security, dead_code, coverage, overall, grade}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoreDelta:
    """Change in scores for a project between two sessions."""

    project_slug: str
    session_from: int
    session_to: int
    previous_overall: float
    current_overall: float
    overall_change: float
    dimension_changes: dict  # {health: +X, complexity: +Y, ...}
    previous_grade: str
    current_grade: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MoverReport:
    """Top movers between two sessions."""

    session_from: int
    session_to: int
    improvers: list  # list[ScoreDelta]
    decliners: list  # list[ScoreDelta]
    total_projects: int
    avg_change: float

    def to_dict(self) -> dict:
        return {
            "session_from": self.session_from,
            "session_to": self.session_to,
            "total_projects": self.total_projects,
            "avg_change": round(self.avg_change, 2),
            "improvers": [d.to_dict() for d in self.improvers],
            "decliners": [d.to_dict() for d in self.decliners],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_text(self) -> str:
        lines = [
            f"SCORE REFRESH: Session {self.session_from} -> {self.session_to}",
            "=" * 50,
            f"Projects analyzed: {self.total_projects}",
            f"Average change: {self.avg_change:+.1f}",
            "",
        ]

        if self.improvers:
            lines.append("TOP IMPROVERS")
            lines.append("-" * 40)
            for d in self.improvers:
                lines.append(
                    f"  {d.project_slug:<40} "
                    f"{d.previous_overall:.1f} -> {d.current_overall:.1f} "
                    f"({d.overall_change:+.1f})"
                )
            lines.append("")

        if self.decliners:
            lines.append("TOP DECLINERS")
            lines.append("-" * 40)
            for d in self.decliners:
                lines.append(
                    f"  {d.project_slug:<40} "
                    f"{d.previous_overall:.1f} -> {d.current_overall:.1f} "
                    f"({d.overall_change:+.1f})"
                )
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# History file I/O
# ---------------------------------------------------------------------------

HISTORY_FILENAME = "score_history.json"


def _history_path(data_dir: Path) -> Path:
    return data_dir / HISTORY_FILENAME


def load_history(data_dir: Path) -> list[dict]:
    """Load all historical snapshots from disk."""
    path = _history_path(data_dir)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return json.loads(text)


def _save_history(data_dir: Path, history: list[dict]) -> None:
    """Write the full history back to disk."""
    path = _history_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Snapshot recording
# ---------------------------------------------------------------------------


def record_snapshot(data_dir: Path, session: int) -> list[ScoreSnapshot]:
    """Regenerate scores for all seed projects and append to history.

    Returns the list of snapshots that were recorded.
    """
    now = datetime.now(timezone.utc).isoformat()
    history = load_history(data_dir)
    snapshots: list[ScoreSnapshot] = []

    for owner, repo, _category in _SEED_PROJECTS:
        slug = f"{owner}/{repo}"
        scores = generate_scores(owner, repo)
        snap = ScoreSnapshot(
            project_slug=slug,
            session=session,
            timestamp=now,
            scores=scores,
        )
        snapshots.append(snap)
        history.append(snap.to_dict())

    _save_history(data_dir, history)
    return snapshots


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


def _snapshots_by_session(
    history: list[dict], session: int,
) -> dict[str, dict]:
    """Extract a {slug: snapshot} map for a given session."""
    result: dict[str, dict] = {}
    for entry in history:
        if entry["session"] == session:
            result[entry["project_slug"]] = entry
    return result


def compute_deltas(
    history: list[dict],
    session_from: int,
    session_to: int,
) -> list[ScoreDelta]:
    """Compute per-project score changes between two sessions.

    Only includes projects present in both sessions.
    """
    old = _snapshots_by_session(history, session_from)
    new = _snapshots_by_session(history, session_to)

    common_slugs = sorted(set(old.keys()) & set(new.keys()))
    deltas: list[ScoreDelta] = []

    for slug in common_slugs:
        old_scores = old[slug]["scores"]
        new_scores = new[slug]["scores"]

        prev_overall = old_scores.get("overall", 0.0)
        curr_overall = new_scores.get("overall", 0.0)
        overall_change = round(curr_overall - prev_overall, 2)

        dim_changes = {}
        for dim in ("health", "complexity", "security", "dead_code", "coverage"):
            old_val = old_scores.get(dim, 0.0)
            new_val = new_scores.get(dim, 0.0)
            dim_changes[dim] = round(new_val - old_val, 2)

        deltas.append(ScoreDelta(
            project_slug=slug,
            session_from=session_from,
            session_to=session_to,
            previous_overall=prev_overall,
            current_overall=curr_overall,
            overall_change=overall_change,
            dimension_changes=dim_changes,
            previous_grade=old_scores.get("grade", "F"),
            current_grade=new_scores.get("grade", "F"),
        ))

    return deltas


# ---------------------------------------------------------------------------
# Mover identification
# ---------------------------------------------------------------------------


def find_movers(
    history: list[dict],
    session_from: int,
    session_to: int,
    top: int = 5,
) -> MoverReport:
    """Identify the biggest improvers and decliners between two sessions."""
    deltas = compute_deltas(history, session_from, session_to)

    if not deltas:
        return MoverReport(
            session_from=session_from,
            session_to=session_to,
            improvers=[],
            decliners=[],
            total_projects=0,
            avg_change=0.0,
        )

    sorted_by_change = sorted(deltas, key=lambda d: d.overall_change, reverse=True)
    improvers = [d for d in sorted_by_change if d.overall_change > 0][:top]
    decliners = [d for d in reversed(sorted_by_change) if d.overall_change < 0][:top]

    avg_change = sum(d.overall_change for d in deltas) / len(deltas)

    return MoverReport(
        session_from=session_from,
        session_to=session_to,
        improvers=improvers,
        decliners=decliners,
        total_projects=len(deltas),
        avg_change=avg_change,
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def get_latest_sessions(history: list[dict], n: int = 2) -> list[int]:
    """Return the last N unique session numbers from history, sorted ascending."""
    sessions = sorted({entry["session"] for entry in history})
    return sessions[-n:] if len(sessions) >= n else sessions


def get_session_summary(history: list[dict], session: int) -> dict:
    """Return aggregate stats for a single session snapshot."""
    snaps = _snapshots_by_session(history, session)
    if not snaps:
        return {"session": session, "projects": 0, "avg_score": 0.0}

    scores = [s["scores"].get("overall", 0.0) for s in snaps.values()]
    grades = [s["scores"].get("grade", "F") for s in snaps.values()]
    from collections import Counter
    grade_counts = dict(Counter(grades).most_common())

    return {
        "session": session,
        "projects": len(snaps),
        "avg_score": round(sum(scores) / len(scores), 1),
        "min_score": round(min(scores), 1),
        "max_score": round(max(scores), 1),
        "grade_distribution": grade_counts,
    }


# ---------------------------------------------------------------------------
# Full refresh pipeline
# ---------------------------------------------------------------------------


def refresh_scores(
    data_dir: Path,
    session: int,
    top: int = 5,
) -> MoverReport:
    """Full refresh: record snapshot, compute deltas, identify movers.

    If there is a previous session in history, compares against it.
    Otherwise returns a report with no movers (first snapshot).
    """
    # Record new snapshot
    record_snapshot(data_dir, session)

    # Load full history and find sessions to compare
    history = load_history(data_dir)
    sessions = get_latest_sessions(history, n=2)

    if len(sessions) < 2:
        # First-ever snapshot, no comparison possible
        snaps = _snapshots_by_session(history, session)
        return MoverReport(
            session_from=session,
            session_to=session,
            improvers=[],
            decliners=[],
            total_projects=len(snaps),
            avg_change=0.0,
        )

    session_from, session_to = sessions[-2], sessions[-1]
    return find_movers(history, session_from, session_to, top=top)
