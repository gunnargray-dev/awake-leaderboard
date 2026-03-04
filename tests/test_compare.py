"""Tests for src.compare -- head-to-head comparison engine."""

from __future__ import annotations

import pytest

from src.models import AnalysisRun, Project, init_db, insert_run, upsert_project
from src.compare import (
    DimensionResult,
    ComparisonResult,
    compare_projects,
    compare_from_db,
)


@pytest.fixture
def conn(tmp_path):
    db = init_db(tmp_path / "test.db")
    yield db
    db.close()


def _run(owner, repo, overall=80.0, health=80.0, complexity=80.0, security=80.0, dead_pct=0.05):
    return {
        "owner": owner, "repo": repo,
        "overall_score": overall, "health_score": health,
        "complexity_score": complexity, "security_score": security,
        "dead_code_pct": dead_pct,
    }


def _add(conn, owner, repo, session=1, overall=80.0, health=80.0, complexity=80.0, security=80.0, dead_pct=0.0):
    upsert_project(conn, Project(owner=owner, repo=repo, url=f"https://github.com/{owner}/{repo}"))
    insert_run(conn, AnalysisRun(
        owner=owner, repo=repo, session=session,
        overall_score=overall, health_score=health,
        complexity_score=complexity, security_score=security,
        dead_code_pct=dead_pct, grade="B",
    ))


class TestCompareDimension:
    def test_a_wins_higher(self):
        d = compare_projects(_run("a", "r", overall=90.0), _run("b", "s", overall=70.0))
        overall = next(x for x in d.dimensions if x.dimension == "overall")
        assert overall.winner == "a"
        assert overall.margin == pytest.approx(20.0)

    def test_b_wins_lower(self):
        d = compare_projects(_run("a", "r", overall=60.0), _run("b", "s", overall=85.0))
        overall = next(x for x in d.dimensions if x.dimension == "overall")
        assert overall.winner == "b"

    def test_tie_within_half_point(self):
        d = compare_projects(_run("a", "r", overall=80.0), _run("b", "s", overall=80.3))
        overall = next(x for x in d.dimensions if x.dimension == "overall")
        assert overall.winner == "tie"


class TestCompareProjects:
    def test_returns_comparison_result(self):
        result = compare_projects(_run("p", "a"), _run("q", "b"))
        assert isinstance(result, ComparisonResult)

    def test_five_dimensions(self):
        result = compare_projects(_run("p", "a"), _run("q", "b"))
        assert len(result.dimensions) == 5

    def test_overall_winner_a(self):
        a = _run("p", "a", overall=90.0, health=90.0, complexity=90.0, security=90.0, dead_pct=0.0)
        b = _run("q", "b", overall=50.0, health=50.0, complexity=50.0, security=50.0, dead_pct=0.5)
        result = compare_projects(a, b)
        assert result.overall_winner == "a"
        assert result.wins_a > result.wins_b

    def test_overall_winner_b(self):
        a = _run("p", "a", overall=50.0, health=50.0, complexity=50.0, security=50.0)
        b = _run("q", "b", overall=90.0, health=90.0, complexity=90.0, security=90.0)
        result = compare_projects(a, b)
        assert result.overall_winner == "b"

    def test_dead_code_lower_is_better(self):
        a = _run("p", "a", dead_pct=0.0, overall=80.0)
        b = _run("q", "b", dead_pct=0.5, overall=80.0)
        result = compare_projects(a, b)
        dc = next(x for x in result.dimensions if x.dimension == "dead_code")
        assert dc.winner == "a"

    def test_to_dict_structure(self):
        result = compare_projects(_run("p", "a"), _run("q", "b"))
        d = result.to_dict()
        assert "project_a" in d
        assert "project_b" in d
        assert "overall_winner" in d
        assert "dimensions" in d

    def test_to_markdown_contains_header(self):
        result = compare_projects(_run("p", "a"), _run("q", "b"))
        md = result.to_markdown()
        assert "p/a" in md
        assert "q/b" in md


class TestCompareFromDb:
    def test_missing_project_returns_none(self, conn):
        assert compare_from_db(conn, "x", "y", "a", "b") is None

    def test_one_missing_returns_none(self, conn):
        _add(conn, "x", "y")
        assert compare_from_db(conn, "x", "y", "a", "b") is None

    def test_returns_comparison_result(self, conn):
        _add(conn, "x", "y", overall=80.0)
        _add(conn, "a", "b", overall=70.0)
        result = compare_from_db(conn, "x", "y", "a", "b")
        assert isinstance(result, ComparisonResult)
        assert result.score_a == 80.0
        assert result.score_b == 70.0

    def test_uses_latest_session(self, conn):
        _add(conn, "x", "y", session=1, overall=50.0)
        _add(conn, "x", "y", session=2, overall=90.0)
        _add(conn, "a", "b", session=1, overall=70.0)
        result = compare_from_db(conn, "x", "y", "a", "b")
        assert result.score_a == 90.0  # latest session
