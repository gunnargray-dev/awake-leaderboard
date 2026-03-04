"""Tests for src.api -- JSON API layer."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.models import AnalysisRun, Project, init_db, insert_run, upsert_project
from src.api import (
    get_leaderboard_json,
    get_project_json,
    get_trends_json,
    get_comparison_json,
    get_categories_json,
    get_stats_json,
    get_digest_json,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


def _seed(db_path, owner, repo, session=1, score=75.0, category="web-framework"):
    conn = init_db(db_path)
    upsert_project(conn, Project(
        owner=owner, repo=repo,
        url=f"https://github.com/{owner}/{repo}",
        category=category, language="Python", stars=1000,
    ))
    insert_run(conn, AnalysisRun(
        owner=owner, repo=repo, session=session,
        overall_score=score, grade="B", health_score=score,
        complexity_score=score, security_score=score, dead_code_pct=0.0,
    ))
    conn.close()


class TestGetLeaderboardJson:
    def test_empty_db(self, db_path):
        result = get_leaderboard_json(db_path)
        assert result == []

    def test_returns_list_of_dicts(self, db_path):
        _seed(db_path, "a", "flask", score=85.0)
        result = get_leaderboard_json(db_path)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["repo"] == "flask"

    def test_rank_added(self, db_path):
        _seed(db_path, "a", "flask", score=85.0)
        _seed(db_path, "a", "django", score=75.0)
        result = get_leaderboard_json(db_path, limit=10)
        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2

    def test_category_filter(self, db_path):
        _seed(db_path, "a", "flask", category="web-framework")
        _seed(db_path, "a", "pytest", category="testing")
        result = get_leaderboard_json(db_path, category="testing")
        assert len(result) == 1
        assert result[0]["repo"] == "pytest"

    def test_limit(self, db_path):
        for i in range(5):
            _seed(db_path, "a", f"repo{i}", score=float(70 + i))
        result = get_leaderboard_json(db_path, limit=3)
        assert len(result) == 3

    def test_sort_by_stars(self, db_path):
        _seed(db_path, "a", "small", score=90.0)
        conn = init_db(db_path)
        conn.execute("UPDATE projects SET stars = 100 WHERE repo = 'small'")
        conn.commit()
        conn.close()
        # Just verify it doesn't crash and returns data
        result = get_leaderboard_json(db_path, sort_by="stars")
        assert len(result) >= 1


class TestGetProjectJson:
    def test_missing(self, db_path):
        init_db(db_path)
        result = get_project_json(db_path, "ghost", "missing")
        assert result is None

    def test_returns_project_and_run(self, db_path):
        _seed(db_path, "p", "myrepo", score=80.0)
        result = get_project_json(db_path, "p", "myrepo")
        assert result is not None
        assert result["repo"] == "myrepo"
        assert result["latest_run"] is not None
        assert result["latest_run"]["overall_score"] == 80.0

    def test_no_run(self, db_path):
        conn = init_db(db_path)
        upsert_project(conn, Project(owner="x", repo="y", url="https://github.com/x/y"))
        conn.close()
        result = get_project_json(db_path, "x", "y")
        assert result is not None
        assert result["latest_run"] is None


class TestGetTrendsJson:
    def test_no_history(self, db_path):
        init_db(db_path)
        result = get_trends_json(db_path, "x", "y")
        assert result["history"] == []

    def test_with_history(self, db_path):
        _seed(db_path, "a", "b", session=1, score=60.0)
        _seed(db_path, "a", "b", session=2, score=75.0)
        result = get_trends_json(db_path, "a", "b")
        assert len(result["history"]) == 2
        assert result["stats"]["avg_score"] == pytest.approx(67.5)


class TestGetComparisonJson:
    def test_missing_returns_none(self, db_path):
        init_db(db_path)
        result = get_comparison_json(db_path, "x", "y", "a", "b")
        assert result is None

    def test_returns_comparison(self, db_path):
        _seed(db_path, "a", "alpha", score=85.0)
        _seed(db_path, "b", "beta", score=70.0)
        result = get_comparison_json(db_path, "a", "alpha", "b", "beta")
        assert result is not None
        assert result["overall_winner"] in ("a", "b", "tie")
        assert "dimensions" in result


class TestGetCategoriesJson:
    def test_empty_db(self, db_path):
        init_db(db_path)
        result = get_categories_json(db_path)
        assert "all_categories" in result
        assert len(result["all_categories"]) > 0

    def test_counts(self, db_path):
        _seed(db_path, "a", "flask", category="web-framework")
        _seed(db_path, "a", "django", category="web-framework")
        _seed(db_path, "a", "pytest", category="testing")
        result = get_categories_json(db_path)
        cats = {c["category"]: c["count"] for c in result["categories"]}
        assert cats["web-framework"] == 2
        assert cats["testing"] == 1
        assert result["total_projects"] == 3


class TestGetStatsJson:
    def test_empty_db(self, db_path):
        init_db(db_path)
        result = get_stats_json(db_path)
        assert result["total_projects"] == 0
        assert result["total_runs"] == 0

    def test_with_data(self, db_path):
        _seed(db_path, "a", "b", score=80.0)
        result = get_stats_json(db_path)
        assert result["total_projects"] == 1
        assert result["total_runs"] == 1
        assert result["average_score"] == 80.0
        assert "top_risers" in result
        assert "top_fallers" in result


class TestGetDigestJson:
    def test_empty_db(self, db_path):
        init_db(db_path)
        result = get_digest_json(db_path)
        assert "session" in result
        assert "stats" in result

    def test_with_session(self, db_path):
        _seed(db_path, "a", "b", session=3, score=75.0)
        result = get_digest_json(db_path, session=3)
        assert result["session"] == 3
