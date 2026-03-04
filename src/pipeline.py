"""Awake Leaderboard -- analysis pipeline.

Orchestrates the full flow: clone a repo, run Awake's analyzers
(health, complexity, security, dead code), compute an overall score,
and store everything in the leaderboard database.

This module is the bridge between the Awake analyzer tools (bundled in
``src/analyzers/``) and the leaderboard data layer.

Public API
----------
- ``analyze_project(repo_path, owner, repo, session)`` -> ``AnalysisRun``
- ``clone_repo(url, target_dir)`` -> ``Path``
- ``run_pipeline(db_path, owner, repo, url, session, clone_dir)`` -> ``AnalysisRun``
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.analyzers.health import HealthReport, analyze_health
from src.analyzers.complexity import ComplexityReport, analyze_complexity
from src.analyzers.security import SecurityReport, audit_security
from src.analyzers.dead_code import DeadCodeReport, find_dead_code

from src.models import (
    AnalysisRun,
    Project,
    compute_grade,
    compute_overall_score,
    init_db,
    insert_run,
    upsert_project,
)
from src.discovery import fetch_repo_metadata


# ---------------------------------------------------------------------------
# Clone helper
# ---------------------------------------------------------------------------


def clone_repo(url: str, target_dir: str | Path) -> Path:
    """Shallow-clone a repository. Returns the clone path.

    Uses ``git clone --depth 1`` to minimize bandwidth and disk usage.
    """
    target = Path(target_dir)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(target)],
        check=True,
        timeout=120,
        capture_output=True,
    )
    return target


# ---------------------------------------------------------------------------
# Analyzer wrappers
# ---------------------------------------------------------------------------


def _run_health(repo_path: Path) -> dict:
    """Run Awake's health analyzer and return a score dict."""
    try:
        report = analyze_health(repo_path)
        return {
            "score": report.overall_score,
            "total_lines": report.total_lines,
            "files_analyzed": len(report.files),
            "detail": {
                "total_lines": report.total_lines,
                "function_count": report.total_functions,
                "class_count": report.total_classes,
                "todo_count": report.total_todos,
                "long_lines": report.total_long_lines,
                "docstring_coverage": round(report.overall_docstring_coverage, 2),
            },
        }
    except Exception as exc:
        return {"score": 0.0, "error": str(exc), "files_analyzed": 0, "total_lines": 0}


def _run_complexity(repo_path: Path) -> dict:
    """Run Awake's complexity analyzer and return a score dict.

    Complexity score is inverted: lower average complexity = higher score.
    Score formula: max(0, 100 - avg_complexity * 5)
    """
    try:
        report = analyze_complexity(repo_path)
        avg = report.average_complexity
        # Invert: low complexity is good
        score = max(0.0, min(100.0, 100.0 - avg * 5.0))
        return {
            "score": round(score, 1),
            "average_complexity": round(avg, 2),
            "max_complexity": report.max_complexity,
            "high_count": len([f for f in report.functions if f.rank == "HIGH"]),
            "function_count": len(report.functions),
        }
    except Exception as exc:
        return {"score": 50.0, "error": str(exc)}


def _run_security(repo_path: Path) -> dict:
    """Run Awake's security audit and return a score dict.

    Security score: 100 - (high_findings * 15 + medium_findings * 5 + low * 1)
    """
    try:
        report = audit_security(repo_path)
        high = len([f for f in report.findings if f.severity == "HIGH"])
        medium = len([f for f in report.findings if f.severity == "MEDIUM"])
        low = len([f for f in report.findings if f.severity == "LOW"])
        penalty = high * 15 + medium * 5 + low * 1
        score = max(0.0, min(100.0, 100.0 - penalty))
        return {
            "score": round(score, 1),
            "high_findings": high,
            "medium_findings": medium,
            "low_findings": low,
            "total_findings": len(report.findings),
            "grade": report.grade,
        }
    except Exception as exc:
        return {"score": 50.0, "error": str(exc)}


def _run_dead_code(repo_path: Path) -> dict:
    """Run Awake's dead code detector and return a percentage."""
    try:
        report = find_dead_code(repo_path)
        total_defs = report.total_definitions if hasattr(report, "total_definitions") else 1
        if total_defs == 0:
            total_defs = 1
        pct = len(report.items) / total_defs if hasattr(report, "items") else 0.0
        return {
            "dead_code_pct": round(pct, 4),
            "dead_items": len(report.items) if hasattr(report, "items") else 0,
            "total_definitions": total_defs,
        }
    except Exception as exc:
        return {"dead_code_pct": 0.0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def analyze_project(
    repo_path: Path,
    owner: str,
    repo: str,
    session: int,
) -> AnalysisRun:
    """Run all analyzers on a cloned repo and return an AnalysisRun.

    This is the core function -- it takes a local repo path and produces
    a fully scored AnalysisRun ready for database insertion.
    """
    health = _run_health(repo_path)
    complexity = _run_complexity(repo_path)
    security = _run_security(repo_path)
    dead_code = _run_dead_code(repo_path)

    overall = compute_overall_score(
        health=health.get("score", 0.0),
        complexity=complexity.get("score", 50.0),
        security=security.get("score", 50.0),
        dead_code_pct=dead_code.get("dead_code_pct", 0.0),
        coverage_pct=0.0,  # Coverage requires running tests -- skip for v1
    )

    return AnalysisRun(
        owner=owner,
        repo=repo,
        session=session,
        health_score=health.get("score", 0.0),
        complexity_score=complexity.get("score", 50.0),
        security_score=security.get("score", 50.0),
        dead_code_pct=dead_code.get("dead_code_pct", 0.0),
        test_coverage_pct=0.0,
        overall_score=round(overall, 1),
        grade=compute_grade(overall),
        findings_json=json.dumps({
            "health": health,
            "complexity": complexity,
            "security": security,
            "dead_code": dead_code,
        }),
        files_analyzed=health.get("files_analyzed", 0),
        total_lines=health.get("total_lines", 0),
    )


def run_pipeline(
    db_path: str | Path,
    owner: str,
    repo: str,
    url: str,
    session: int,
    clone_dir: Optional[str | Path] = None,
    category: str = "",
    token: Optional[str] = None,
) -> Optional[AnalysisRun]:
    """Full pipeline: fetch metadata, clone, analyze, store.

    Returns the AnalysisRun on success, None on failure.
    """
    # 1. Fetch latest metadata from GitHub
    meta = fetch_repo_metadata(owner, repo, token=token)

    # 2. Open / init database
    conn = init_db(db_path)

    # 3. Upsert project
    project = Project(
        owner=owner,
        repo=repo,
        url=url,
        description=meta.get("description", "") if meta else "",
        language=meta.get("language", "") if meta else "",
        category=category,
        stars=meta.get("stars", 0) if meta else 0,
        forks=meta.get("forks", 0) if meta else 0,
        open_issues=meta.get("open_issues", 0) if meta else 0,
        topics=meta.get("topics", "") if meta else "",
        created_at=meta.get("created_at", "") if meta else "",
        last_pushed=meta.get("last_pushed", "") if meta else "",
    )
    upsert_project(conn, project)

    # 4. Clone
    if clone_dir is None:
        clone_dir = tempfile.mkdtemp(prefix="awake_lb_")
    repo_path = clone_repo(url, Path(clone_dir) / repo)

    try:
        # 5. Analyze
        run = analyze_project(repo_path, owner, repo, session)

        # 6. Store
        insert_run(conn, run)
        return run
    finally:
        # 7. Cleanup clone
        if repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)
        conn.close()
