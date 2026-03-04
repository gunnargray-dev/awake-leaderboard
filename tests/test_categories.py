"""Tests for src/categories.py -- category detection and filtering."""

from __future__ import annotations

import pytest

from src.categories import (
    detect_category,
    detect_category_with_confidence,
    list_categories,
)
from src.models import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return init_db(tmp_path / "test.db")


def _insert_project(conn, owner, repo, category="", stars=100, language="Python",
                    topics="", description=""):
    conn.execute(
        """INSERT OR IGNORE INTO projects
           (owner, repo, url, category, stars, language, topics, description)
           VALUES (?,?,?,?,?,?,?,?)""",
        (owner, repo, f"https://github.com/{owner}/{repo}", category, stars,
         language, topics, description),
    )
    conn.commit()


def _insert_run(conn, owner, repo, session, score, grade="B"):
    conn.execute(
        """INSERT INTO analysis_runs
           (owner, repo, session, overall_score, health_score, complexity_score,
            security_score, dead_code_pct, grade, analyzed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (owner, repo, session, score, score, score, score, 5.0, grade, "2024-01-01"),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# list_categories
# ---------------------------------------------------------------------------


class TestListCategories:
    def test_returns_list(self):
        cats = list_categories()
        assert isinstance(cats, list)
        assert len(cats) > 0

    def test_contains_expected(self):
        cats = list_categories()
        for expected in ["web-framework", "cli-tool", "data-science", "other"]:
            assert expected in cats

    def test_sorted(self):
        cats = list_categories()
        assert cats == sorted(cats)


# ---------------------------------------------------------------------------
# detect_category
# ---------------------------------------------------------------------------


class TestDetectCategory:
    def test_web_framework_from_topics(self):
        assert detect_category("flask,web-framework", "", "myapp") == "web-framework"

    def test_ml_from_description(self):
        result = detect_category("", "deep learning training loop", "myml")
        assert result == "ml"

    def test_cli_from_topics(self):
        assert detect_category("cli,command-line", "", "mytool") == "cli-tool"

    def test_database_from_topics(self):
        assert detect_category("database,sqlite", "", "mydb") == "database"

    def test_unknown_returns_other(self):
        assert detect_category("", "", "xyz123") == "other"

    def test_empty_inputs(self):
        result = detect_category("", "", "")
        assert result == "other"

    def test_testing_from_topics(self):
        assert detect_category("pytest,testing", "", "") == "testing"

    def test_devops_from_description(self):
        result = detect_category("", "docker container deployment tool", "")
        assert result == "devops"

    def test_case_insensitive(self):
        result = detect_category("", "MACHINE LEARNING framework", "")
        assert result == "ml"


# ---------------------------------------------------------------------------
# detect_category_with_confidence
# ---------------------------------------------------------------------------


class TestDetectCategoryWithConfidence:
    def test_returns_dict(self):
        result = detect_category_with_confidence("flask", "web framework", "myapp")
        assert "category" in result
        assert "confidence" in result
        assert "matched_topics" in result
        assert "matched_keywords" in result

    def test_confidence_range(self):
        result = detect_category_with_confidence("flask,web-framework", "flask web framework", "")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_no_match_confidence_zero(self):
        result = detect_category_with_confidence("", "", "xyz")
        assert result["confidence"] == 0.0
        assert result["category"] == "other"

    def test_topic_match_recorded(self):
        result = detect_category_with_confidence("flask", "", "")
        assert "flask" in result["matched_topics"]

    def test_description_match_recorded(self):
        result = detect_category_with_confidence("", "machine learning model", "")
        assert len(result["matched_keywords"]) > 0

    def test_multi_topic_higher_confidence(self):
        single = detect_category_with_confidence("flask", "", "")
        multi = detect_category_with_confidence("flask,web-framework,wsgi", "", "")
        assert multi["confidence"] >= single["confidence"]
