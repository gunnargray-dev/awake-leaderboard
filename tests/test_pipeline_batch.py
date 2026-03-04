"""Tests for src.pipeline -- run_batch_analysis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models import AnalysisRun, Project, init_db, insert_run, upsert_project
from src.pipeline import run_batch_analysis


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "batch_test.db"


def _add_project(db_path, owner, repo):
    conn = init_db(db_path)
    upsert_project(conn, Project(
        owner=owner, repo=repo,
        url=f"https://github.com/{owner}/{repo}",
    ))
    conn.close()


class TestRunBatchAnalysis:
    def test_empty_db_returns_zero(self, db_path):
        init_db(db_path)
        result = run_batch_analysis(db_path, session=1)
        assert result["total"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0
        assert result["results"] == []

    def test_returns_session_number(self, db_path):
        init_db(db_path)
        result = run_batch_analysis(db_path, session=5)
        assert result["session"] == 5

    @patch("src.pipeline.run_pipeline")
    def test_calls_run_pipeline_for_each_project(self, mock_run, db_path):
        _add_project(db_path, "a", "alpha")
        _add_project(db_path, "b", "beta")

        fake_run = AnalysisRun(
            owner="a", repo="alpha", session=1,
            overall_score=75.0, grade="B",
        )
        mock_run.return_value = fake_run

        result = run_batch_analysis(db_path, session=1)
        assert mock_run.call_count == 2
        assert result["total"] == 2

    @patch("src.pipeline.run_pipeline")
    def test_counts_successes(self, mock_run, db_path):
        _add_project(db_path, "a", "alpha")
        _add_project(db_path, "b", "beta")

        fake_run = AnalysisRun(owner="a", repo="alpha", session=1, overall_score=70.0, grade="B")
        mock_run.return_value = fake_run

        result = run_batch_analysis(db_path, session=1)
        assert result["success"] == 2
        assert result["failed"] == 0

    @patch("src.pipeline.run_pipeline")
    def test_counts_failures(self, mock_run, db_path):
        _add_project(db_path, "a", "alpha")
        _add_project(db_path, "b", "beta")

        mock_run.side_effect = [
            AnalysisRun(owner="a", repo="alpha", session=1, overall_score=70.0, grade="B"),
            Exception("clone failed"),
        ]

        result = run_batch_analysis(db_path, session=1)
        assert result["success"] == 1
        assert result["failed"] == 1

    @patch("src.pipeline.run_pipeline")
    def test_failed_result_has_error_field(self, mock_run, db_path):
        _add_project(db_path, "a", "alpha")
        mock_run.side_effect = Exception("timeout")

        result = run_batch_analysis(db_path, session=1)
        assert result["results"][0]["status"] == "error"
        assert "timeout" in result["results"][0]["error"]

    @patch("src.pipeline.run_pipeline")
    def test_success_result_has_score(self, mock_run, db_path):
        _add_project(db_path, "a", "alpha")
        mock_run.return_value = AnalysisRun(
            owner="a", repo="alpha", session=1,
            overall_score=82.0, grade="A-",
        )

        result = run_batch_analysis(db_path, session=1)
        assert result["results"][0]["status"] == "ok"
        assert result["results"][0]["score"] == 82.0
        assert result["results"][0]["grade"] == "A-"
