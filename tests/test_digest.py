"""Tests for src/digest.py -- weekly digest generator."""

from __future__ import annotations

import pytest

from src.models import init_db
from src.digest import build_digest_data, generate_digest


@pytest.fixture
def db(tmp_path):
    return init_db(tmp_path / "test.db")


def _insert_project(conn, owner, repo, category="web", stars=100):
    conn.execute(
        "INSERT OR IGNORE INTO projects (owner, repo, url, category, stars) VALUES (?,?,?,?,?)",
        (owner, repo, f"https://github.com/{owner}/{repo}", category, stars),
    )
    conn.commit()


def _insert_run(conn, owner, repo, session, score, grade="B", analyzed_at="2024-01-01T00:00:00"):
    conn.execute(
        """INSERT INTO analysis_runs
           (owner, repo, session, overall_score, health_score, complexity_score,
            security_score, dead_code_pct, grade, analyzed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (owner, repo, session, score, score, score, score, 5.0, grade, analyzed_at),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# build_digest_data
# ---------------------------------------------------------------------------


class TestBuildDigestData:
    def test_empty_db_returns_session_zero(self, db):
        data = build_digest_data(db)
        assert data["session"] == 0

    def test_uses_latest_session_by_default(self, db):
        _insert_project(db, "org", "r1")
        _insert_run(db, "org", "r1", session=3, score=70.0)
        data = build_digest_data(db)
        assert data["session"] == 3

    def test_explicit_session(self, db):
        _insert_project(db, "org", "r1")
        _insert_run(db, "org", "r1", session=2, score=70.0)
        data = build_digest_data(db, session=2)
        assert data["session"] == 2

    def test_has_expected_keys(self, db):
        data = build_digest_data(db)
        for key in ("session", "generated_at", "stats", "new_projects",
                    "top_projects", "movers_risers", "movers_fallers", "grade_distribution"):
            assert key in data

    def test_new_projects_first_session(self, db):
        _insert_project(db, "org", "newproj")
        _insert_run(db, "org", "newproj", session=1, score=75.0)
        data = build_digest_data(db, session=1)
        repos = [p["repo"] for p in data["new_projects"]]
        assert "newproj" in repos

    def test_not_new_if_appeared_before(self, db):
        _insert_project(db, "org", "oldproj")
        _insert_run(db, "org", "oldproj", session=1, score=70.0)
        _insert_run(db, "org", "oldproj", session=2, score=75.0)
        data = build_digest_data(db, session=2)
        repos = [p["repo"] for p in data["new_projects"]]
        assert "oldproj" not in repos

    def test_grade_distribution_populated(self, db):
        _insert_project(db, "org", "p1")
        _insert_project(db, "org", "p2")
        _insert_run(db, "org", "p1", session=1, score=90.0, grade="A+")
        _insert_run(db, "org", "p2", session=1, score=50.0, grade="C-")
        data = build_digest_data(db)
        dist = data["grade_distribution"]
        assert dist.get("A+") == 1
        assert dist.get("C-") == 1

    def test_generated_at_is_string(self, db):
        data = build_digest_data(db)
        assert isinstance(data["generated_at"], str)
        assert "UTC" in data["generated_at"]


# ---------------------------------------------------------------------------
# generate_digest (Markdown output)
# ---------------------------------------------------------------------------


class TestGenerateDigest:
    def test_returns_string(self, db):
        result = generate_digest(db)
        assert isinstance(result, str)

    def test_header_contains_session(self, db):
        _insert_project(db, "org", "repo1")
        _insert_run(db, "org", "repo1", session=4, score=80.0, grade="A-")
        result = generate_digest(db, session=4)
        assert "Session 4" in result

    def test_contains_stats_section(self, db):
        result = generate_digest(db)
        assert "Overall Stats" in result

    def test_top_projects_section(self, db):
        _insert_project(db, "org", "myrepo")
        _insert_run(db, "org", "myrepo", session=1, score=75.0, grade="B+")
        result = generate_digest(db, session=1)
        assert "Top 10" in result
        assert "myrepo" in result

    def test_new_projects_section(self, db):
        _insert_project(db, "org", "brandnew")
        _insert_run(db, "org", "brandnew", session=1, score=80.0, grade="A-")
        result = generate_digest(db, session=1)
        assert "New This Session" in result
        assert "brandnew" in result

    def test_no_error_empty_db(self, db):
        result = generate_digest(db)
        assert "Awake Leaderboard Digest" in result

    def test_risers_section_shown_when_movers_exist(self, db):
        _insert_project(db, "org", "mover")
        _insert_run(db, "org", "mover", session=1, score=50.0)
        _insert_run(db, "org", "mover", session=2, score=80.0)
        result = generate_digest(db, session=2)
        assert "Risers" in result

    def test_footer_present(self, db):
        result = generate_digest(db)
        assert "Awake" in result.split("---")[-1]
