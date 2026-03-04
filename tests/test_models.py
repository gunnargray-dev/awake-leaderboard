"""Tests for src.models -- database schema, CRUD, and scoring."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.models import (
    AnalysisRun,
    Project,
    compute_grade,
    compute_overall_score,
    get_leaderboard,
    get_project,
    get_project_history,
    get_stats,
    init_db,
    insert_run,
    upsert_project,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_leaderboard.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    c = init_db(db_path)
    yield c
    c.close()


def _make_project(**overrides) -> Project:
    defaults = dict(
        owner="pallets",
        repo="flask",
        url="https://github.com/pallets/flask",
        description="A micro web framework",
        language="Python",
        category="web-framework",
        stars=65000,
        forks=16000,
    )
    defaults.update(overrides)
    return Project(**defaults)


def _make_run(**overrides) -> AnalysisRun:
    defaults = dict(
        owner="pallets",
        repo="flask",
        session=1,
        health_score=82.0,
        complexity_score=70.0,
        security_score=90.0,
        dead_code_pct=0.03,
        test_coverage_pct=0.0,
        overall_score=78.5,
        grade="B+",
        findings_json="{}",
        files_analyzed=120,
        total_lines=15000,
    )
    defaults.update(overrides)
    return AnalysisRun(**defaults)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_creates_database_file(self, db_path: Path):
        conn = init_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_creates_tables(self, conn: sqlite3.Connection):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "projects" in table_names
        assert "analysis_runs" in table_names

    def test_idempotent(self, db_path: Path):
        """Calling init_db twice should not error."""
        c1 = init_db(db_path)
        c2 = init_db(db_path)
        c1.close()
        c2.close()

    def test_creates_parent_dirs(self, tmp_path: Path):
        deep = tmp_path / "a" / "b" / "c" / "test.db"
        conn = init_db(deep)
        assert deep.exists()
        conn.close()


# ---------------------------------------------------------------------------
# Project CRUD tests
# ---------------------------------------------------------------------------


class TestUpsertProject:
    def test_insert_new(self, conn: sqlite3.Connection):
        p = _make_project()
        upsert_project(conn, p)
        row = get_project(conn, "pallets", "flask")
        assert row is not None
        assert row["stars"] == 65000
        assert row["language"] == "Python"

    def test_update_existing(self, conn: sqlite3.Connection):
        p = _make_project(stars=65000)
        upsert_project(conn, p)
        p2 = _make_project(stars=66000)
        upsert_project(conn, p2)
        row = get_project(conn, "pallets", "flask")
        assert row["stars"] == 66000

    def test_preserves_added_at(self, conn: sqlite3.Connection):
        p = _make_project()
        upsert_project(conn, p)
        first_added = get_project(conn, "pallets", "flask")["added_at"]
        p2 = _make_project(stars=70000)
        upsert_project(conn, p2)
        second_added = get_project(conn, "pallets", "flask")["added_at"]
        assert first_added == second_added

    def test_get_missing_project(self, conn: sqlite3.Connection):
        assert get_project(conn, "ghost", "missing") is None


# ---------------------------------------------------------------------------
# Analysis run tests
# ---------------------------------------------------------------------------


class TestInsertRun:
    def test_insert_and_retrieve(self, conn: sqlite3.Connection):
        upsert_project(conn, _make_project())
        run = _make_run()
        row_id = insert_run(conn, run)
        assert row_id is not None
        assert row_id > 0

    def test_multiple_runs(self, conn: sqlite3.Connection):
        upsert_project(conn, _make_project())
        insert_run(conn, _make_run(session=1, overall_score=70.0))
        insert_run(conn, _make_run(session=2, overall_score=75.0))
        insert_run(conn, _make_run(session=3, overall_score=80.0))
        history = get_project_history(conn, "pallets", "flask")
        assert len(history) == 3
        scores = [h["overall_score"] for h in history]
        assert scores == [70.0, 75.0, 80.0]


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


class TestComputeGrade:
    @pytest.mark.parametrize("score,expected", [
        (95, "A+"), (90, "A+"), (87, "A"), (85, "A"),
        (82, "A-"), (80, "A-"), (77, "B+"), (75, "B+"),
        (72, "B"), (70, "B"), (67, "B-"), (65, "B-"),
        (62, "C+"), (60, "C+"), (57, "C"), (55, "C"),
        (52, "C-"), (50, "C-"), (45, "D"), (40, "D"),
        (35, "F"), (0, "F"), (-5, "F"),
    ])
    def test_grade_boundaries(self, score, expected):
        assert compute_grade(score) == expected


class TestComputeOverallScore:
    def test_perfect_scores(self):
        score = compute_overall_score(100, 100, 100, 0.0, 100.0)
        assert score == 100.0

    def test_zero_scores(self):
        score = compute_overall_score(0, 0, 0, 1.0, 0.0)
        assert score == 0.0

    def test_mixed_scores(self):
        score = compute_overall_score(80, 70, 90, 0.05, 60.0)
        assert 50 < score < 90

    def test_dead_code_penalty(self):
        clean = compute_overall_score(80, 80, 80, 0.0, 50.0)
        dirty = compute_overall_score(80, 80, 80, 0.5, 50.0)
        assert clean > dirty


# ---------------------------------------------------------------------------
# Leaderboard query tests
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    def _seed(self, conn):
        for name, stars, score in [
            ("flask", 65000, 85.0),
            ("django", 75000, 80.0),
            ("fastapi", 70000, 90.0),
        ]:
            upsert_project(conn, _make_project(
                owner="test", repo=name, stars=stars,
                url=f"https://github.com/test/{name}",
            ))
            insert_run(conn, _make_run(
                owner="test", repo=name, session=1,
                overall_score=score,
                grade=compute_grade(score),
            ))

    def test_default_sort_by_score(self, conn):
        self._seed(conn)
        lb = get_leaderboard(conn)
        scores = [r["overall_score"] for r in lb]
        assert scores == sorted(scores, reverse=True)

    def test_limit(self, conn):
        self._seed(conn)
        lb = get_leaderboard(conn, limit=2)
        assert len(lb) == 2

    def test_filter_by_language(self, conn):
        self._seed(conn)
        lb = get_leaderboard(conn, language="Python")
        assert len(lb) == 3  # all are Python

    def test_invalid_sort_falls_back(self, conn):
        self._seed(conn)
        lb = get_leaderboard(conn, sort_by="invalid_col")
        assert len(lb) > 0  # falls back to overall_score


class TestGetStats:
    def test_empty_db(self, conn):
        stats = get_stats(conn)
        assert stats["total_projects"] == 0
        assert stats["total_runs"] == 0
        assert stats["average_score"] == 0.0

    def test_with_data(self, conn):
        upsert_project(conn, _make_project())
        insert_run(conn, _make_run(overall_score=80.0))
        stats = get_stats(conn)
        assert stats["total_projects"] == 1
        assert stats["total_runs"] == 1
        assert stats["average_score"] == 80.0


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_project_full_name(self):
        p = _make_project()
        assert p.full_name == "pallets/flask"

    def test_project_to_dict(self):
        p = _make_project()
        d = p.to_dict()
        assert d["owner"] == "pallets"
        assert d["repo"] == "flask"

    def test_run_to_dict(self):
        r = _make_run()
        d = r.to_dict()
        assert d["session"] == 1
        assert d["overall_score"] == 78.5
