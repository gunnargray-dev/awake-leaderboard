"""Tests for src.pipeline -- analysis pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest

from src.models import (
    AnalysisRun,
    Project,
    compute_grade,
    init_db,
    get_project,
    get_project_history,
    upsert_project,
)
from src.pipeline import (
    _run_health,
    _run_complexity,
    _run_security,
    _run_dead_code,
    analyze_project,
    clone_repo,
)


# ---------------------------------------------------------------------------
# Mock analyzer results
# ---------------------------------------------------------------------------


@dataclass
class _MockHealthReport:
    overall_score: float = 82.0
    total_lines: int = 5000
    total_functions: int = 120
    total_classes: int = 15
    total_todos: int = 3
    total_long_lines: int = 10
    overall_docstring_coverage: float = 0.75
    files: list = None

    def __post_init__(self):
        if self.files is None:
            self.files = [1] * 20  # 20 fake files


@dataclass
class _MockFunctionComplexity:
    rank: str = "LOW"


@dataclass
class _MockComplexityReport:
    average_complexity: float = 4.2
    max_complexity: int = 12
    functions: list = None

    def __post_init__(self):
        if self.functions is None:
            self.functions = [
                _MockFunctionComplexity("LOW"),
                _MockFunctionComplexity("MEDIUM"),
                _MockFunctionComplexity("HIGH"),
            ]


@dataclass
class _MockSecurityFinding:
    severity: str = "MEDIUM"


@dataclass
class _MockSecurityReport:
    findings: list = None
    grade: str = "B"

    def __post_init__(self):
        if self.findings is None:
            self.findings = [
                _MockSecurityFinding("HIGH"),
                _MockSecurityFinding("MEDIUM"),
                _MockSecurityFinding("LOW"),
            ]


@dataclass
class _MockDeadCodeReport:
    items: list = None
    total_definitions: int = 100

    def __post_init__(self):
        if self.items is None:
            self.items = ["dead1", "dead2", "dead3"]


# ---------------------------------------------------------------------------
# Analyzer wrapper tests
# ---------------------------------------------------------------------------


class TestRunHealth:
    @patch("src.pipeline.analyze_health")
    def test_returns_score(self, mock_health):
        mock_health.return_value = _MockHealthReport()
        result = _run_health(Path("/fake"))
        assert result["score"] == 82.0
        assert result["total_lines"] == 5000
        assert result["files_analyzed"] == 20

    @patch("src.pipeline.analyze_health")
    def test_handles_error(self, mock_health):
        mock_health.side_effect = Exception("parse error")
        result = _run_health(Path("/fake"))
        assert result["score"] == 0.0
        assert "error" in result


class TestRunComplexity:
    @patch("src.pipeline.analyze_complexity")
    def test_inverts_score(self, mock_cx):
        mock_cx.return_value = _MockComplexityReport(average_complexity=4.0)
        result = _run_complexity(Path("/fake"))
        # score = 100 - 4.0 * 5 = 80
        assert result["score"] == 80.0

    @patch("src.pipeline.analyze_complexity")
    def test_very_complex_code(self, mock_cx):
        mock_cx.return_value = _MockComplexityReport(average_complexity=25.0)
        result = _run_complexity(Path("/fake"))
        assert result["score"] == 0.0  # clamped to 0

    @patch("src.pipeline.analyze_complexity")
    def test_handles_error(self, mock_cx):
        mock_cx.side_effect = Exception("ast error")
        result = _run_complexity(Path("/fake"))
        assert result["score"] == 50.0  # fallback


class TestRunSecurity:
    @patch("src.pipeline.audit_security")
    def test_computes_penalty(self, mock_sec):
        mock_sec.return_value = _MockSecurityReport()
        result = _run_security(Path("/fake"))
        # 1 HIGH (15) + 1 MEDIUM (5) + 1 LOW (1) = 21 penalty
        assert result["score"] == 79.0

    @patch("src.pipeline.audit_security")
    def test_clean_code(self, mock_sec):
        report = _MockSecurityReport()
        report.findings = []
        mock_sec.return_value = report
        result = _run_security(Path("/fake"))
        assert result["score"] == 100.0

    @patch("src.pipeline.audit_security")
    def test_handles_error(self, mock_sec):
        mock_sec.side_effect = Exception("scan error")
        result = _run_security(Path("/fake"))
        assert result["score"] == 50.0


class TestRunDeadCode:
    @patch("src.pipeline.find_dead_code")
    def test_computes_percentage(self, mock_dc):
        mock_dc.return_value = _MockDeadCodeReport()
        result = _run_dead_code(Path("/fake"))
        assert result["dead_code_pct"] == 0.03  # 3/100

    @patch("src.pipeline.find_dead_code")
    def test_handles_error(self, mock_dc):
        mock_dc.side_effect = Exception("scan error")
        result = _run_dead_code(Path("/fake"))
        assert result["dead_code_pct"] == 0.0


# ---------------------------------------------------------------------------
# analyze_project tests
# ---------------------------------------------------------------------------


class TestAnalyzeProject:
    @patch("src.pipeline.find_dead_code")
    @patch("src.pipeline.audit_security")
    @patch("src.pipeline.analyze_complexity")
    @patch("src.pipeline.analyze_health")
    def test_produces_analysis_run(
        self, mock_health, mock_cx, mock_sec, mock_dc
    ):
        mock_health.return_value = _MockHealthReport()
        mock_cx.return_value = _MockComplexityReport()
        mock_sec.return_value = _MockSecurityReport()
        mock_dc.return_value = _MockDeadCodeReport()

        run = analyze_project(Path("/fake"), "pallets", "flask", session=1)

        assert isinstance(run, AnalysisRun)
        assert run.owner == "pallets"
        assert run.repo == "flask"
        assert run.session == 1
        assert run.health_score == 82.0
        assert run.overall_score > 0
        assert run.grade in ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F")

    @patch("src.pipeline.find_dead_code")
    @patch("src.pipeline.audit_security")
    @patch("src.pipeline.analyze_complexity")
    @patch("src.pipeline.analyze_health")
    def test_findings_json_is_valid(
        self, mock_health, mock_cx, mock_sec, mock_dc
    ):
        mock_health.return_value = _MockHealthReport()
        mock_cx.return_value = _MockComplexityReport()
        mock_sec.return_value = _MockSecurityReport()
        mock_dc.return_value = _MockDeadCodeReport()

        run = analyze_project(Path("/fake"), "test", "repo", session=1)
        findings = json.loads(run.findings_json)
        assert "health" in findings
        assert "complexity" in findings
        assert "security" in findings
        assert "dead_code" in findings


# ---------------------------------------------------------------------------
# clone_repo tests
# ---------------------------------------------------------------------------


class TestCloneRepo:
    @patch("src.pipeline.subprocess.run")
    def test_calls_git_clone(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        target = tmp_path / "test_repo"
        clone_repo("https://github.com/test/repo.git", target)
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "clone" in call_args
        assert "--depth" in call_args
        assert "1" in call_args

    @patch("src.pipeline.subprocess.run")
    def test_cleans_existing_dir(self, mock_run, tmp_path):
        target = tmp_path / "test_repo"
        target.mkdir()
        (target / "old_file.txt").write_text("stale")
        mock_run.return_value = MagicMock(returncode=0)
        clone_repo("https://github.com/test/repo.git", target)
        # Old dir should have been removed before clone
        mock_run.assert_called_once()
